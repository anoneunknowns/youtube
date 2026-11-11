"""Render the Tora Hexadecimal Count episode from its measured narration timeline."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import time
import wave

from PIL import Image, ImageDraw, ImageOps

from render_counting_video import FPS, find_ffmpeg
from render_hexadecimal_mockups import (
    BACKGROUND, CREAM, INK, PEACH, SIZE, SLOT_CENTERS, SYMBOLS, TEAL, WEIGHTS,
    Shot, Tora, place_text, render, rounded,
)
from render_octal_video import encode, preview, stage_frames


FADE_COLOR = Image.new('RGB', SIZE, CREAM)
PLACE_CHECK_CUE = '3 × 16 + 15 = 63'


@dataclass(frozen=True)
class Frame:
    value: int = 0
    focus: int | None = None
    pose: str = 'neutral'
    cue: str = ''
    inventory: int | None = None
    letter_table: bool = False
    weight_slot: int | None = None
    blank_slot: bool = False
    carry_from: int | None = None
    cream: int = 0


class Scene:
    def __init__(self, timeline: dict):
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
            raise ValueError('Expected all 128 hexadecimal count states in decimal order')
        self.carries = [cue for cue in timeline['carry_cues'] if cue['after_decimal_value'] != 63]
        comparisons = {
            pause['after_decimal_value']: pause['estimated_start_s']
            for pause in timeline['pauses'] if pause['kind'] == 'new-place-comparison'
        }
        self.carry_starts = [
            comparisons.get(cue['after_decimal_value'], cue['estimated_start_s'])
            for cue in self.carries
        ]
        self.place_check = next(pause for pause in timeline['pauses'] if pause['after_decimal_value'] == 63)
        self.dialogue = {
            cue['id']: tuple(cue['relative_window_s'])
            for cue in timeline['intro']['dialogue']
        }
        self.dialogue.update({
            cue['id']: tuple(self.finale_start + point for point in cue['relative_window_s'])
            for cue in timeline['finale']['dialogue']
        })
        self.intro_digits = []
        for event in timeline.get('events', []):
            if event['type'] == 'dialogue':
                self.dialogue[event['id']] = (event['start_s'], event['end_s'])
            elif event['type'] == 'digit_voice' and event.get('phase') == 'intro':
                self.intro_digits.append((event['start_s'], event['end_s'], event['slot_index']))
        if not self.intro_digits:
            # Planning previews use provisional positions until the edited speech is available.
            start = self.dialogue['I05'][0] + .7
            for index, length in enumerate((.475833333, .55)):
                self.intro_digits.append((start, start + length, index))
                start += length + .9
        self.mapping_starts = [self.dialogue[f'I03{letter}'][0] for letter in 'ABCDEF']
        with Image.open(BACKGROUND) as source:
            self.background = ImageOps.fit(source.convert('RGBA'), SIZE, Image.Resampling.LANCZOS)
        self.tora = Tora()

    def opening(self, t: float) -> Frame:
        inventory_start, inventory_end = self.dialogue['I02']
        if t < inventory_start:
            greeting_start, greeting_end = self.dialogue['I01']
            return Frame(pose='aha' if greeting_start <= t < greeting_end else 'neutral', inventory=-1)
        if t < self.mapping_starts[0]:
            progress = (t - inventory_start) / (inventory_end - inventory_start)
            return Frame(inventory=min(15, int(16 * progress)))
        if t < self.dialogue['I04'][0]:
            letter = bisect_right(self.mapping_starts, t) - 1
            return Frame(value=10 + letter, letter_table=True)
        if t >= self.dialogue['I08'][0]:
            return Frame(blank_slot=t < self.dialogue['I08'][1])
        focus = next((index for start, end, index in self.intro_digits if start <= t < end), None)
        weight_slot = None
        weight_start, weight_end = self.dialogue['I07']
        if weight_start <= t < weight_end:
            weight_slot = 1 if t < (weight_start + weight_end) / 2 else 0
        return Frame(value=26, focus=focus, weight_slot=weight_slot)

    def count(self, t: float) -> Frame:
        state = self.counts[bisect_right(self.count_starts, t) - 1]
        value = state['decimal_value']
        focus = next((
            token['ordinal'] for token in state['digit_highlights']
            if token['estimated_start_s'] <= t < token['estimated_end_s']
        ), None)
        frame = Frame(value=value, focus=focus)
        in_check = t - self.place_check['estimated_start_s']
        if 0 <= in_check < self.place_check['duration_s']:
            weight_slot = 0 if .20 <= in_check < 3.40 else 1 if 3.40 <= in_check < 5.70 else None
            return replace(frame, cue=PLACE_CHECK_CUE, weight_slot=weight_slot)
        carry_index = bisect_right(self.carry_starts, t) - 1
        if carry_index >= 0 and t < self.carries[carry_index]['estimated_end_s']:
            frame = replace(frame, carry_from=self.carries[carry_index]['after_decimal_value'], cue='')
        return frame

    def state(self, index: int) -> Frame:
        t = index / FPS + 1e-9
        if t < self.intro_end:
            frame = self.opening(t)
        elif t < self.finale_start:
            frame = self.count(t)
        else:
            frame = Frame(value=127, pose='aha' if self.dialogue['F09'][0] <= t < self.finale_fade_start else 'neutral')
        if t < .8:
            frame = replace(frame, cream=round(255 * (1 - t / .8)))
        elif t >= self.finale_fade_start:
            last_frame_s = (self.frame_count - 1) / FPS
            progress = (t - self.finale_fade_start) / (last_frame_s - self.finale_fade_start)
            frame = replace(frame, cream=min(255, round(255 * progress)))
        return frame

    def image(self, frame: Frame) -> Image.Image:
        if frame.cream == 255:
            return FADE_COLOR
        new_place = frame.carry_from == 15 and frame.value == 15
        shot = Shot('', '', frame.value, frame.focus, frame.cue, frame.pose,
                    letter_table=frame.letter_table, transition=new_place)
        image = render(self.background, self.tora, shot)
        draw = ImageDraw.Draw(image)
        if frame.inventory is not None:
            draw_inventory(draw, frame.inventory)
        if frame.weight_slot is not None:
            x = SLOT_CENTERS[frame.weight_slot]
            rounded(draw, (x - 51, 503, x + 51, 561), '#d3eddf', '#2e7e71', 2, 15)
            place_text(draw, str(WEIGHTS[frame.weight_slot]), (x, 532), 34, TEAL)
        if frame.blank_slot:
            rounded(draw, (765, 315, 1215, 574), None, '#b27943', 5, 30)
        if frame.carry_from is not None and not new_place:
            text = f'{frame.carry_from:X} + 1  =  {frame.carry_from + 1:X}   (BASE 16)'
            rounded(draw, (662, 835, 1798, 904), PEACH, '#c6955e', 2, 23)
            place_text(draw, text, (1230, 869), 34, INK)
            if frame.carry_from == 15:
                rounded(draw, (765, 315, 1215, 574), None, '#b27943', 5, 30)
        if frame.cream:
            image = Image.blend(image, FADE_COLOR, frame.cream / 255)
        return image


def draw_inventory(draw: ImageDraw.ImageDraw, active_symbol: int) -> None:
    draw.rectangle((664, 298, 1796, 792), fill=CREAM)
    draw.rectangle((157, 700, 459, 797), fill='#fff7df')
    if active_symbol < 0:
        return
    for index, symbol in enumerate(SYMBOLS):
        number = index < 10
        center = 735 + 110 * index if number else 805 + 170 * (index - 10)
        top, bottom = (370, 505) if number else (550, 685)
        half_width = 46 if number else 65
        active = index == active_symbol
        rounded(draw, (center - half_width, top, center + half_width, bottom),
                '#aee5ce' if active else '#e5f2df', '#2e7e71' if active else '#94b79c',
                4 if active else 2, 20)
        place_text(draw, symbol, (center, (top + bottom) / 2), 65, INK)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--audio', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--preview-dir', type=Path)
    parser.add_argument('--preview-at', type=float, nargs='+', default=[0, 2, 8, 12, 25, 35, 37, 48, 53, 59])
    parser.add_argument('--ffmpeg')
    parser.add_argument('--crf', type=int, default=18)
    parser.add_argument('--preset', default='veryfast')
    parser.add_argument('--audio-gain-db', type=float, default=0)
    args = parser.parse_args()
    if args.preview_dir is None and (args.audio is None or args.output is None):
        parser.error('Pass --audio and --output for video, or --preview-dir for stills')
    if args.output is not None and args.audio is None:
        parser.error('--output requires --audio')
    if not math.isfinite(args.audio_gain_db):
        parser.error('--audio-gain-db must be finite')
    timeline = json.loads(args.timeline.read_text(encoding='utf-8'))
    scene = Scene(timeline)
    if args.preview_dir is not None:
        preview(scene, args.preview_dir, args.preview_at)
        if args.output is None:
            return
    if 'duration_s' not in timeline or len(scene.intro_digits) != 2 or not any(
        event['type'] == 'digit_voice' and event.get('phase') == 'intro'
        for event in timeline.get('events', [])
    ):
        raise ValueError('The video requires the measured timeline and its I05 digit events')
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
    with TemporaryDirectory(prefix='hexadecimal-render-', dir=temp_root) as directory:
        folder = Path(directory)
        index, unique, runs = stage_frames(scene, folder)
        print(f'Staged {unique} distinct images in {runs} holds for {scene.frame_count} frames.', flush=True)
        result = folder / 'hexadecimal.mp4'
        encode(index, audio, result, scene.frame_count, ffmpeg, args.crf, args.preset, args.audio_gain_db)
        if output.exists():
            raise FileExistsError(output)
        shutil.move(result, output)
    print(json.dumps({
        'output': str(output), 'frame_count': scene.frame_count, 'fps': FPS,
        'audio_duration_s': scene.duration, 'video_duration_s': scene.frame_count / FPS,
        'audio_gain_db': args.audio_gain_db,
        'render_elapsed_s': round(time.perf_counter() - start, 3),
    }))


if __name__ == '__main__':
    main()
