"""Render the Octal Count episode from its measured narration timeline."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import dataclass, replace
from itertools import groupby
import json
import math
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import time
import wave

from PIL import Image, ImageDraw, ImageOps

from render_binary_video import FPS
from render_counting_video import find_ffmpeg
from render_octal_mockups import (
    CREAM, INK, PEACH, ROOT, RABBIT_REGISTRATION, SIZE, TEAL, WEIGHTS,
    Rabbit, Shot, draw_ranges, place_text, render, rounded,
)


BACKGROUND = ROOT / 'assets/library/worlds/aurora-garden/backgrounds/v002/aurora-garden-background.png'
OPENING_FADE_S = .8
INTRO_CUE = 'Read each digit from left to right'
DIGIT_CUE = 'Use the digits 0 through 7'
FADE_COLOR = Image.new('RGB', SIZE, CREAM)


@dataclass(frozen=True)
class Frame:
    value: int = 0
    focus: int | None = None
    pose: str = 'neutral'
    cue: str = ''
    demo_digit: int | None = None
    weight_slot: int | None = None
    blank_slot: bool = False
    carry_from: int | None = None
    cream: int = 0


class Scene:
    def __init__(self, timeline: dict, reading_layout: str = 'legacy'):
        self.legacy_reading_layout = reading_layout == 'legacy'
        self.duration = timeline.get('duration_s', timeline.get('duration_s_estimate'))
        if self.duration is None or self.duration <= 0 or timeline.get('fps', FPS) != FPS:
            raise ValueError(f'The timeline needs a positive duration at {FPS} fps')
        self.frame_count = math.ceil(self.duration * FPS - 1e-7)
        self.intro_end = timeline['intro']['duration_s']
        self.finale_start = timeline['finale']['estimated_start_s']
        self.finale_fade_start = self.finale_start + timeline['finale']['relative_cream_fade_s'][0]
        self.counts = timeline['counted_states']
        self.count_starts = [state['estimated_display_start_s'] for state in self.counts]
        if [state['decimal_value'] for state in self.counts] != list(range(128)):
            raise ValueError('Expected all 128 count states in decimal order')
        self.carries = timeline['carry_cues']
        self.comparisons = {
            pause['after_decimal_value']: pause['estimated_start_s']
            for pause in timeline['pauses'] if pause['kind'] == 'new-place-comparison'
        }
        self.carry_starts = [
            self.comparisons.get(cue['after_decimal_value'], cue['estimated_start_s'])
            for cue in self.carries
        ]
        self.stretch = next(pause for pause in timeline['pauses'] if pause['kind'] == 'stretch')
        self.dialogue = {
            cue['id']: tuple(cue['relative_window_s'])
            for cue in timeline['intro']['dialogue']
        }
        self.dialogue.update({
            cue['id']: tuple(self.finale_start + t for t in cue['relative_window_s'])
            for cue in timeline['finale']['dialogue']
        })
        self.intro_digits = []
        for event in timeline.get('events', []):
            if event['type'] == 'dialogue':
                self.dialogue[event['id']] = (event['start_s'], event['end_s'])
            elif event['type'] == 'digit_voice' and event.get('phase') == 'intro':
                self.intro_digits.append((event['start_s'], event['end_s'], event['slot_index'] - 1))
        if not self.intro_digits:
            # Still previews can use the planning timeline before the voice edit exists.
            start = self.dialogue['I04'][0] + .55
            for index, token in enumerate(('one', 'two')):
                end = start + timeline['accepted_digit_clips'][token]['duration_s']
                self.intro_digits.append((start, end, index))
                start = end + .9
        with Image.open(BACKGROUND) as source:
            self.background = ImageOps.fit(source.convert('RGBA'), SIZE, Image.Resampling.LANCZOS)
        self.rabbit = Rabbit(RABBIT_REGISTRATION)

    def opening(self, t: float) -> Frame:
        digits_start, digits_end = self.dialogue['I02']
        if t < digits_start:
            pose = 'wave_2' if 1.00 <= t < 2.50 else 'neutral'
            return Frame(pose=pose, demo_digit=-1)
        if t < self.dialogue['I03'][0]:
            progress = (t - digits_start) / (digits_end - digits_start)
            return Frame(cue=DIGIT_CUE, demo_digit=min(7, int(8 * progress)))
        if t >= self.dialogue['I08'][0]:
            return Frame(cue=DIGIT_CUE)

        focus = next((index for start, end, index in self.intro_digits if start <= t < end), None)
        weight_start, weight_end = self.dialogue['I06']
        weight_slot = None
        if weight_start <= t < weight_end:
            weight_slot = 2 - min(2, int(3 * (t - weight_start) / (weight_end - weight_start)))
        blank_start, blank_end = self.dialogue['I07']
        blank_slot = not self.legacy_reading_layout and blank_start <= t < blank_end
        cue = 'Skip the blank places' if blank_slot else INTRO_CUE
        return Frame(value=10, focus=focus, weight_slot=weight_slot, blank_slot=blank_slot, cue=cue)

    def count(self, t: float) -> Frame:
        state = self.counts[bisect_right(self.count_starts, t) - 1]
        value = state['decimal_value']
        focus = next((
            digit['ordinal'] for digit in state['digit_highlights']
            if digit['estimated_start_s'] <= t < digit['estimated_end_s']
        ), None)
        pose = 'neutral'
        cue = DIGIT_CUE if value == 0 else ''
        since_stretch_start = t - self.stretch['estimated_start_s']
        if 0 <= since_stretch_start < self.stretch['duration_s']:
            cue = 'Stretch break'
            if 1.50 <= since_stretch_start < 5.70:
                pose = 'seated_stretch'
        carry_from = None
        index = bisect_right(self.carry_starts, t) - 1
        if index >= 0 and t < self.carries[index]['estimated_end_s']:
            carry_from = self.carries[index]['after_decimal_value']
            cue = ''
        return Frame(value=value, focus=focus, pose=pose, cue=cue, carry_from=carry_from)

    def state(self, index: int) -> Frame:
        # Start/end times in the timeline are rounded to nanoseconds.
        t = index / FPS + 1e-9
        if t < self.intro_end:
            frame = self.opening(t)
        elif t < self.finale_start:
            frame = self.count(t)
        else:
            since_goodbye = t - self.dialogue['F09'][0]
            waving = 0 <= since_goodbye < .65 or .85 <= since_goodbye < 1.55
            frame = Frame(value=127, pose='wave_3' if waving else 'neutral', cue='Great counting!')

        if frame.pose == 'neutral' and self.intro_end <= t < self.finale_start and (index - 25) % 157 < 3:
            frame = replace(frame, pose='blink')
        if t < OPENING_FADE_S:
            frame = replace(frame, cream=round(255 * (1 - t / OPENING_FADE_S)))
        elif t >= self.finale_fade_start:
            last_frame_s = (self.frame_count - 1) / FPS
            progress = (t - self.finale_fade_start) / (last_frame_s - self.finale_fade_start)
            frame = replace(frame, cream=min(255, round(255 * progress)))
        return frame

    def image(self, frame: Frame) -> Image.Image:
        if frame.cream == 255:
            return FADE_COLOR
        new_place = frame.carry_from in (7, 63) and frame.value == frame.carry_from
        shot = Shot('', '', frame.value, frame.cue, frame.focus, new_place, frame.pose)
        image = render(self.background, self.rabbit, shot, footer_badge=True,
                       legacy_reading_layout=self.legacy_reading_layout)
        draw = ImageDraw.Draw(image)
        if frame.demo_digit is not None:
            draw_demo(draw, frame.demo_digit)
        if frame.weight_slot is not None:
            x = 860 + 370 * frame.weight_slot
            rounded(draw, (x - 51, 503, x + 51, 561), '#d3eddf', '#2e7e71', 2, 15)
            place_text(draw, str(WEIGHTS[frame.weight_slot]), (x, 532), 34, TEAL)
        if frame.blank_slot:
            rounded(draw, (687, 315, 1033, 574), None, '#b27943', 5, 30)
        if frame.carry_from is not None and not new_place:
            cue = f'{frame.carry_from:o} + 1  =  {frame.carry_from + 1:o}   (BASE 8)'
            rounded(draw, (662, 835, 1798, 904), PEACH, '#c6955e', 2, 23)
            place_text(draw, cue, (1230, 869), 34, INK)
        if frame.cream:
            image = Image.blend(image, FADE_COLOR, frame.cream / 255)
        return image


def draw_demo(draw: ImageDraw.ImageDraw, last_digit: int) -> None:
    draw.rectangle((664, 298, 1796, 792), fill=CREAM)
    draw.rectangle((157, 700, 459, 797), fill='#fff7df')
    draw_ranges(draw, 0, footer_badge=True)
    for digit in range(last_digit + 1):
        x = 754 + 136 * digit
        active = digit == last_digit
        fill = '#aee5ce' if active else '#e5f2df'
        edge = '#2e7e71' if active else '#94b79c'
        rounded(draw, (x - 58, 392, x + 58, 568), fill, edge, 4 if active else 2, 22)
        place_text(draw, str(digit), (x, 480), 92, INK)


def stage_frames(scene: Scene, folder: Path) -> tuple[Path, int, int]:
    cache: dict[Frame, str] = {}
    concat = ['ffconcat version 1.0']
    frame_end = runs = 0
    for frame, group in groupby(scene.state(index) for index in range(scene.frame_count)):
        name = cache.get(frame)
        if name is None:
            name = f'frame-{len(cache):04d}.png'
            scene.image(frame).save(folder / name, compress_level=1)
            cache[frame] = name
            if len(cache) % 100 == 0:
                print(f'Staged {len(cache)} distinct images.', flush=True)
        frame_start = frame_end
        frame_end += sum(1 for _ in group)
        # Keep the concat clock on the frame grid without accumulating microsecond errors.
        duration_us = round(frame_end * 1e6 / FPS) - round(frame_start * 1e6 / FPS)
        concat.extend((f"file '{name}'", f'option framerate {FPS}', f'duration {duration_us / 1e6:.6f}'))
        runs += 1
    # A final sentinel lets the FPS filter emit the complete last still hold.
    concat.extend((f"file '{name}'", f'option framerate {FPS}'))
    index_path = folder / 'frames.ffconcat'
    index_path.write_text('\n'.join(concat) + '\n', encoding='ascii')
    return index_path, len(cache), runs


def encode(index: Path, audio: Path, output: Path, frame_count: int, ffmpeg: str,
           crf: int, preset: str, audio_gain_db: float = 0) -> None:
    filters = (
        'scale=in_range=full:out_range=limited:out_color_matrix=bt709,'
        'setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,'
        f'fps={FPS},trim=end_frame={frame_count}'
    )
    audio_filter = ['-af', f'volume={audio_gain_db:g}dB:precision=double'] if audio_gain_db else []
    command = [
        ffmpeg, '-hide_banner', '-loglevel', 'warning', '-stats', '-stats_period', '10', '-nostdin', '-n',
        '-f', 'concat', '-safe', '0', '-i', str(index), '-i', str(audio),
        '-map', '0:v:0', '-map', '1:a:0', '-vf', filters,
        '-c:v', 'libx264', '-preset', preset, '-crf', str(crf), '-pix_fmt', 'yuv420p',
        '-color_range', 'tv', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
        *audio_filter, '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
        '-movflags', '+faststart', str(output),
    ]
    subprocess.run(command, check=True)


def preview(scene: Scene, folder: Path, positions: list[float]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for position in positions:
        if not 0 <= position <= scene.duration:
            raise ValueError(f'Preview time outside the timeline: {position}')
        index = min(scene.frame_count - 1, math.ceil(position * FPS - 1e-7))
        scene.image(scene.state(index)).save(folder / f'frame-{index:06d}.png')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--audio', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--preview-dir', type=Path)
    parser.add_argument('--preview-at', type=float, nargs='+', default=[0, 6, 12.8, 32.2, 55, 152, 286, 288, 639])
    parser.add_argument('--ffmpeg')
    parser.add_argument('--crf', type=int, default=18)
    parser.add_argument('--preset', default='medium')
    parser.add_argument('--audio-gain-db', type=float, default=0, help='Linear gain applied when encoding AAC')
    parser.add_argument('--reading-layout', choices=('legacy', 'common-baseline'), default='legacy')
    args = parser.parse_args()
    if args.preview_dir is None and (args.audio is None or args.output is None):
        parser.error('Pass --audio and --output for video, or --preview-dir for stills')
    if args.output is not None and args.audio is None:
        parser.error('--output requires --audio')
    if not math.isfinite(args.audio_gain_db):
        parser.error('--audio-gain-db must be finite')

    timeline = json.loads(args.timeline.read_text(encoding='utf-8'))
    scene = Scene(timeline, args.reading_layout)
    if args.preview_dir is not None:
        preview(scene, args.preview_dir, args.preview_at)
        if args.output is None:
            return

    if 'duration_s' not in timeline or len(scene.intro_digits) != 2 or not any(
        event['type'] == 'digit_voice' and event.get('phase') == 'intro'
        for event in timeline.get('events', [])
    ):
        raise ValueError('The video requires the measured timeline and its I04 digit events')
    audio = args.audio.resolve()
    with wave.open(str(audio), 'rb') as track:
        if abs(track.getnframes() - round(scene.duration * track.getframerate())) > 1:
            raise ValueError('The WAV length does not match the measured timeline')
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg(args.ffmpeg)
    temp_root = Path('D:/temp')
    if not temp_root.is_dir():
        temp_root = None
    start = time.perf_counter()
    with TemporaryDirectory(prefix='octal-render-', dir=temp_root) as directory:
        folder = Path(directory)
        index, unique, runs = stage_frames(scene, folder)
        print(f'Staged {unique} distinct images in {runs} holds for {scene.frame_count} frames.', flush=True)
        result = folder / 'octal.mp4'
        encode(index, audio, result, scene.frame_count, ffmpeg, args.crf, args.preset, args.audio_gain_db)
        if output.exists():
            raise FileExistsError(output)
        shutil.move(result, output)
    print(json.dumps({
        'output': str(output), 'frame_count': scene.frame_count, 'fps': FPS,
        'audio_duration_s': scene.duration, 'video_duration_s': scene.frame_count / FPS,
        'audio_gain_db': args.audio_gain_db,
        'reading_layout': args.reading_layout,
        'render_elapsed_s': round(time.perf_counter() - start, 3),
    }))


if __name__ == '__main__':
    main()
