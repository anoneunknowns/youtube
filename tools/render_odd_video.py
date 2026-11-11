"""Render the measured odd-count episode with clean ticket-diagram transitions."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import asdict, dataclass
from functools import lru_cache
import json
import math
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import time
import wave

from PIL import Image, ImageDraw, ImageOps

from render_counting_video import find_ffmpeg
from render_octal_video import encode, stage_frames
from render_odd_mockups import (
    BACKGROUND, BOARD, CHARACTER, CREAM, ROOT, SIZE, TEAL, TEACHING_FIELD,
    RedPanda, Shot, checked_text, file_hash, render, rounded, validate_all_values,
)


FPS = 30
VIDEO_NAME = 'paspla-studio-odd-numbers-1-to-199-1080p.mp4'
FADE_COLOR = Image.new('RGB', SIZE, CREAM)


@dataclass(frozen=True)
class Frame:
    phase: str = 'intro'
    value: int | None = None
    diagram: str = ''
    diagram_alpha: int = 0
    indicator: int = 255
    stamp: bool = False
    cream: int = 0


def ramp(age, duration):
    return max(0, min(255, round(255 * age / duration)))


class Scene:
    def __init__(self, timeline):
        self.timeline = timeline
        self.duration = float(timeline['duration_s'])
        self.frame_count = math.ceil(self.duration * FPS - 1e-7)
        if not math.isfinite(self.duration) or self.duration <= 0 or timeline['fps'] != FPS:
            raise ValueError('A positive finite 30fps timeline is required')
        if timeline.get('duration_frames', self.frame_count) != self.frame_count:
            raise ValueError('duration_frames differs from the 30fps frame grid')
        self.scenes = timeline['scenes']
        self.starts = [row['start_s'] for row in self.scenes]
        self.counts = self.scenes[1:-1]
        self.finale_start = self.scenes[-1]['start_s']
        self.voice_events = timeline.get('voice_events', [])
        self.validation = self.validate_timeline()
        self.layout_validation = validate_all_values()
        with Image.open(BACKGROUND) as source:
            self.background_size = source.size
            self.background = ImageOps.fit(source.convert('RGBA'), SIZE, Image.Resampling.LANCZOS)
        self.character = RedPanda(height=420, root=(1615, 950))

    def validate_timeline(self):
        if [row['scene'] for row in self.scenes] != ['intro'] + ['count'] * 100 + ['finale']:
            raise ValueError('Expected intro, one hundred odd values, and finale')
        if [row['decimal_value'] for row in self.counts] != list(range(1, 200, 2)):
            raise ValueError('Count scenes must be the exact odd sequence 1–199')
        previous = 0.0
        for row in self.scenes:
            if abs(row['start_s'] - previous) > 1e-6 or not row['start_s'] < row['end_s']:
                raise ValueError('Visual scene intervals must be positive and continuous')
            previous = row['end_s']
        if abs(previous - self.duration) > 1e-6 or abs(self.scenes[0]['end_s'] - 36) > 1e-6:
            raise ValueError('The approved intro lasts 36 seconds')
        if abs(self.duration - self.finale_start - 14) > 1e-6:
            raise ValueError('The approved finale lasts fourteen seconds')
        ordinary = teaching = 0
        for index, row in enumerate(self.counts):
            value = row['decimal_value']
            if abs(row['voice_start_s'] - row['start_s'] - .12) > 1e-6:
                raise ValueError(f'Incorrect display lead for {value}')
            if not row['voice_start_s'] < row['voice_end_s'] <= row['end_s']:
                raise ValueError(f'Voice lies outside count state {value}')
            if index < 99:
                expected = 10 if value in (9, 101) else 2
                if abs(self.counts[index + 1]['voice_start_s'] - row['voice_end_s'] - expected) > 1e-6:
                    raise ValueError(f'Incorrect number-to-number gap after {value}')
                ordinary += expected == 2
                teaching += expected == 10
            elif abs(row['end_s'] - row['voice_end_s'] - .28) > 1e-6:
                raise ValueError('The final number must be held for .28 seconds')
            pause = row.get('teaching')
            if value in (9, 101):
                if (not pause or pause['id'] != f'T{value:03d}'
                        or abs(pause['start_s'] - row['voice_end_s'] - .4) > 1e-6
                        or abs(pause['end_s'] - pause['start_s'] - 8) > 1e-6):
                    raise ValueError(f'Incorrect eight-second teaching window for {value}')
            elif pause:
                raise ValueError('Teaching is only scheduled at 9 and 101')
        return {'contiguous_scenes': 102, 'odd_values_checked': 100,
                'ordinary_two_second_boundaries': ordinary, 'teaching_ten_second_boundaries': teaching,
                'display_lead_s': .12, 'final_number_hold_s': .28}

    def state(self, index):
        if not 0 <= index < self.frame_count:
            raise IndexError(index)
        t = index / FPS + 1e-9
        row = self.scenes[bisect_right(self.starts, t) - 1]
        if row['scene'] == 'intro':
            if t < 5:
                frame = Frame()
            elif t < 12.4:
                frame = Frame(value=1, diagram='single', diagram_alpha=255)
            elif t < 24.9:
                alpha = ramp(t - 12.4, .5) if t < 12.9 else 255 if t < 24.4 else 255 - ramp(t - 24.4, .5)
                frame = Frame(value=5, diagram='five', diagram_alpha=alpha)
            else:
                frame = Frame(value=1, diagram='single', diagram_alpha=255)
        elif row['scene'] == 'count':
            frame = Frame(phase='count', value=row['decimal_value'])
            if pause := row.get('teaching'):
                age = t - pause['start_s']
                if 0 <= age < 8:
                    alpha = ramp(age, .5) if age < .5 else 255 if age < 7.4 else 255 - ramp(age - 7.4, .5)
                    frame = Frame(phase='count', value=row['decimal_value'],
                                  diagram='nine' if row['decimal_value'] == 9 else 'cross-hundred',
                                  diagram_alpha=alpha, indicator=ramp(age, .5))
        else:
            frame = Frame(phase='finale', value=199, stamp=t >= self.finale_start + 1)
        cream = 0
        if t < .8:
            cream = 255 - ramp(t, .8)
        elif t >= self.duration - 2:
            cream = ramp(t - (self.duration - 2), (self.frame_count - 1) / FPS - (self.duration - 2))
        return Frame(**{**asdict(frame), 'cream': cream}) if cream else frame

    @lru_cache(maxsize=8)
    def still(self, value, kind='count', indicator=255):
        return render(self.background, self.character, Shot('', '', value, kind), indicator)[0]

    def image(self, frame):
        if frame.cream == 255:
            return FADE_COLOR
        if frame.value is None:
            image = self.still(1).copy()
            ImageDraw.Draw(image).rectangle((90, 242, BOARD[2] - 30, BOARD[3] - 22), fill='#fffaf0')
        elif frame.diagram:
            target = self.still(frame.value, frame.diagram, frame.indicator)
            base = target.copy()
            rounded(ImageDraw.Draw(base), TEACHING_FIELD, '#f9f0dd', '#e1cfb2', 2, 21)
            # Only diagram content differs: headers and large numerals never
            # crossfade against incompatible words or the normal instruction.
            image = Image.blend(base, target, frame.diagram_alpha / 255)
        elif frame.phase == 'finale':
            image = self.still(199, 'finale').copy()
            if not frame.stamp:
                ImageDraw.Draw(image).rectangle((1141, 722, 1299, 824), fill='#f9f0dd')
        else:
            image = self.still(frame.value)
        return Image.blend(image, FADE_COLOR, frame.cream / 255) if frame.cream else image

    def audit(self):
        records = []
        for row in self.counts:
            indices = sorted({math.ceil(row['start_s'] * FPS - 1e-7),
                              math.ceil(row['voice_start_s'] * FPS - 1e-7),
                              math.ceil(row['voice_end_s'] * FPS - 1e-7) - 1,
                              math.ceil(row['end_s'] * FPS - 1e-7) - 1})
            if any(self.state(index).value != row['decimal_value'] for index in indices):
                raise ValueError('A frame-grid count sample displays the wrong number')
            records.append({'decimal_value': row['decimal_value'], 'indices': indices})
        return {'timeline': self.validation, 'layout': self.layout_validation, 'count_frame_grid_samples': records,
                'character_registration': self.character.metadata,
                'background': {'path': BACKGROUND.relative_to(ROOT).as_posix(), 'sha256': file_hash(BACKGROUND),
                               'source_size_px': list(self.background_size)},
                'renderer': Path(__file__).relative_to(ROOT).as_posix(), 'renderer_sha256': file_hash(Path(__file__)),
                'mockup_renderer_sha256': file_hash(ROOT / 'tools/render_odd_mockups.py'),
                'diagram_fade_policy': 'Only diagram against a blank field; fixed header and no instruction underneath.',
                'intro': {'single_s': [5, 12.4], 'five_reveal_s': [12.4, 12.9],
                          'five_clear_s': [24.4, 24.9], 'reset_to_single_s': 24.9},
                'teaching': {'show_s': [0, .5], 'hide_s': [7.4, 7.9], '101_indicator_one_pass_s': [0, .5]},
                'finale': {'stamp_at_s': 1, 'fade_last_s': 2},
                'new_character_art_generated': False, 'continuous_character_motion': False}


def previews(scene, folder, positions):
    if folder.exists():
        raise FileExistsError('Choose a new preview directory')
    folder.mkdir(parents=True)
    rows = []
    for at in positions:
        if not 0 <= at < scene.duration:
            raise ValueError(f'Preview outside the timeline: {at}')
        index = min(scene.frame_count - 1, math.ceil(at * FPS - 1e-7))
        state = scene.state(index)
        path = folder / f'frame-{index:06d}.png'
        scene.image(state).save(path)
        rows.append({'time_s': index / FPS, 'frame': index, 'state': asdict(state),
                     'path': path.name, 'sha256': file_hash(path)})
    report = {'status': 'preview-prepared', 'frames': rows, 'audit': scene.audit()}
    (folder / 'renderer-preview-qa.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'output': str(folder), 'frames': len(rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--audio', type=Path)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, default=Path('D:/temp/odd-counting-render'))
    parser.add_argument('--ffmpeg')
    parser.add_argument('--preview', type=float, nargs='+')
    parser.add_argument('--preview-dir', type=Path)
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--crf', type=int, default=18)
    parser.add_argument('--preset', default='medium')
    parser.add_argument('--audio-gain-db', type=float)
    args = parser.parse_args()
    if not args.render and not args.preview:
        parser.error('Choose --preview <times> or --render --audio <master.wav>')
    plan = json.loads(args.timeline.read_text(encoding='utf-8-sig'))
    scene = Scene(plan)
    if args.preview:
        print(json.dumps(previews(scene, args.preview_dir or args.out_dir / 'renderer-previews', args.preview)), flush=True)
    if not args.render:
        return
    if not args.audio or plan.get('preview_only') or not scene.voice_events:
        raise ValueError('Final rendering requires measured voice_events and the matching master WAV')
    with wave.open(str(args.audio), 'rb') as stream:
        if abs(stream.getnframes() - round(scene.duration * stream.getframerate())) > 1:
            raise ValueError('Audio master duration differs from the measured timeline')
    gain = args.audio_gain_db
    if gain is None:
        gain = plan.get('audio_mix', {}).get('required_delivery_gain_db', plan.get('delivery_gain_db', 0))
    if not math.isfinite(gain):
        raise ValueError('Delivery gain must be finite')
    output = args.out_dir.resolve()
    video, report_path = output / VIDEO_NAME, output / 'render-report.json'
    if video.exists() or report_path.exists():
        raise FileExistsError('Final output artifacts already exist')
    output.mkdir(parents=True, exist_ok=True)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg(args.ffmpeg)
    started = time.perf_counter()
    audit = scene.audit()
    with TemporaryDirectory(prefix='odd-render-', dir=args.work_dir) as temporary:
        folder = Path(temporary)
        concat, unique, holds = stage_frames(scene, folder)
        print(f'Staged {unique} images in {holds} holds for {scene.frame_count} frames.', flush=True)
        result = folder / 'odd.mp4'
        encode(concat, args.audio, result, scene.frame_count, ffmpeg, args.crf, args.preset, gain)
        shutil.move(result, video)
    report = {'output': str(video), 'video_sha256': file_hash(video),
              'timeline': str(args.timeline.resolve()), 'timeline_sha256': file_hash(args.timeline),
              'audio': str(args.audio.resolve()), 'audio_sha256': file_hash(args.audio),
              'audio_gain_db': gain, 'frame_size_px': list(SIZE), 'fps': FPS,
              'duration_frames': scene.frame_count, 'video_duration_s': scene.frame_count / FPS,
              'audio_duration_s': scene.duration, 'distinct_images': unique, 'holds': holds,
              'render_elapsed_s': round(time.perf_counter() - started, 3), 'crf': args.crf,
              'preset': args.preset, 'ffmpeg': ffmpeg, 'audit': audit, 'final_encoded_qa_pending': True}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('output', 'duration_frames', 'video_duration_s', 'render_elapsed_s')}))


if __name__ == '__main__':
    main()
