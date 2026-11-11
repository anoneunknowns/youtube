"""Render the even-number episode from measured, contiguous scene intervals."""

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
from render_even_mockups import (
    BACKGROUND, BOARD, CHARACTER, CREAM, INK, MUTED, ROOT, SIZE, TEAL,
    TEACHING_FIELD, LittleBird, Shot, checked_text, draw_block, file_hash,
    render, rounded, validate_all_values,
)
from render_octal_video import encode, stage_frames


FPS = 30
VIDEO_NAME = 'paspla-studio-even-numbers-0-to-200-1080p.mp4'
FADE_COLOR = Image.new('RGB', SIZE, CREAM)


@dataclass(frozen=True)
class Frame:
    phase: str = 'intro'
    value: int | None = None
    intro_mode: str = 'blank'
    motion_progress: int = 0
    diagram_alpha: int = 0
    teaching: str = ''
    show_step: bool = True
    checkmark: bool = False
    cream: int = 0


def alpha_ramp(age: float, duration: float) -> int:
    return max(0, min(255, round(255 * age / duration)))


def planning_contract(plan: dict) -> dict:
    """Adapt the saved design estimate for still previews, never video delivery."""
    teaching = {row['decimal_value_held']: row for row in plan['teaching']}
    scenes = [{'scene': 'intro', 'start_s': 0, 'end_s': plan['intro']['end_s']}]
    for row in plan['number_states']:
        scene = {'scene': 'count', 'decimal_value': row['decimal_value'],
                 'start_s': row['estimated_display_start_s'], 'end_s': row['estimated_display_end_s'],
                 'voice_start_s': row['estimated_voice_start_s'], 'voice_end_s': row['estimated_voice_end_s']}
        if row['decimal_value'] in teaching:
            pause = teaching[row['decimal_value']]
            scene['teaching'] = {'id': pause['id'], 'start_s': pause['estimated_start_s'],
                                 'end_s': pause['estimated_end_s']}
        scenes.append(scene)
    scenes.append({'scene': 'finale', 'start_s': plan['finale']['estimated_start_s'],
                   'end_s': plan['finale']['estimated_end_s']})
    duration = plan['totals']['estimated_video_s']
    return {'fps': FPS, 'duration_s': duration, 'duration_frames': math.ceil(duration * FPS - 1e-7),
            'scenes': scenes, 'voice_events': [], 'preview_only': True}


class Scene:
    def __init__(self, timeline: dict):
        self.timeline = timeline
        self.duration = float(timeline['duration_s'])
        self.frame_count = math.ceil(self.duration * FPS - 1e-7)
        if not math.isfinite(self.duration) or self.duration <= 0 or timeline['fps'] != FPS:
            raise ValueError('A finite positive timeline at 30 fps is required')
        if timeline.get('duration_frames', self.frame_count) != self.frame_count:
            raise ValueError('duration_frames must be ceil(duration_s * 30)')
        self.scenes = timeline['scenes']
        self.starts = [row['start_s'] for row in self.scenes]
        self.counts = [row for row in self.scenes if row['scene'] == 'count']
        self.intro = self.scenes[0]
        self.finale = self.scenes[-1]
        self.finale_start = self.finale['start_s']
        self.voice_events = timeline.get('voice_events', [])
        self.validation = self.validate_timeline()
        self.layout_validation = validate_all_values()
        with Image.open(BACKGROUND) as source:
            self.background_size = source.size
            self.background = ImageOps.fit(source.convert('RGBA'), SIZE, Image.Resampling.LANCZOS)
        self.bird = LittleBird(height=280, root=(1675, 950), character_manifest=CHARACTER)

    def validate_timeline(self) -> dict:
        if self.intro['scene'] != 'intro' or self.finale['scene'] != 'finale':
            raise ValueError('Expected intro, 101 counts, finale')
        if len(self.scenes) != 103 or [row['decimal_value'] for row in self.counts] != list(range(0, 201, 2)):
            raise ValueError('Expected all 101 even values, zero through two hundred')
        previous = 0.0
        for row in self.scenes:
            if abs(row['start_s'] - previous) > 1e-6 or row['end_s'] <= row['start_s']:
                raise ValueError(f'Invalid or noncontiguous scene: {row}')
            previous = row['end_s']
        if abs(previous - self.duration) > 1e-6 or abs(self.intro['end_s'] - 36) > 1e-6:
            raise ValueError('Intro must end at 36 seconds; final scene must end at duration_s')
        if abs(self.finale['end_s'] - self.finale['start_s'] - 14) > 1e-6:
            raise ValueError('The approved finale lasts fourteen seconds')
        for index, row in enumerate(self.counts):
            if abs(row['voice_start_s'] - row['start_s'] - .12) > 1e-6:
                raise ValueError('Every number display must lead its voice by .12 seconds')
            if not row['voice_start_s'] < row['voice_end_s'] <= row['end_s']:
                raise ValueError('A number voice lies outside its display state')
            value = row['decimal_value']
            if index < 100:
                expected = 10 if value in (20, 100) else 2
                if abs(self.counts[index + 1]['voice_start_s'] - row['voice_end_s'] - expected) > 1e-6:
                    raise ValueError(f'Incorrect inter-number voice gap after {value}')
            elif abs(row['end_s'] - row['voice_end_s'] - .28) > 1e-6:
                raise ValueError('The last number must have a .28-second posthold')
            pause = row.get('teaching')
            if value in (20, 100):
                if not pause or pause['id'] != f'T{value:03d}':
                    raise ValueError(f'Missing teaching window for {value}')
                if abs(pause['start_s'] - row['voice_end_s'] - .4) > 1e-6 or abs(pause['end_s'] - pause['start_s'] - 8) > 1e-6:
                    raise ValueError('Teaching must start .4 seconds after its number and last eight seconds')
                if pause['end_s'] > row['end_s']:
                    raise ValueError('Teaching window extends beyond the held value')
            elif pause:
                raise ValueError('Only twenty and one hundred have teaching windows')
        return {'contiguous_scenes': len(self.scenes), 'count_values_checked': 101,
                'ordinary_voice_gaps_checked': 98, 'teaching_voice_gaps_checked': 2,
                'display_lead_s': .12, 'final_posthold_s': .28,
                'no_word_by_word_animation': True, 'no_continuous_motion_loops': True}

    def opening(self, t: float) -> Frame:
        if t < 8.3:
            return Frame(show_step=t >= 4.9)
        if t < 12.3:
            return Frame(value=2, intro_mode='pair', motion_progress=alpha_ramp(t - 8.3, .6))
        if t < 23.8:
            return Frame(value=6, intro_mode='six', diagram_alpha=alpha_ramp(t - 12.3, .6))
        if t < 24.2:
            return Frame(value=6, intro_mode='six', diagram_alpha=255 - alpha_ramp(t - 23.8, .4))
        return Frame(value=0, intro_mode='zero')

    def count(self, t: float, row: dict) -> Frame:
        alpha = 0
        kind = ''
        if pause := row.get('teaching'):
            age = t - pause['start_s']
            if 0 <= age < 8:
                kind = pause['id']
                alpha = alpha_ramp(age, .5) if age < .5 else 255 if age < 7.4 else 255 - alpha_ramp(age - 7.4, .5)
        return Frame(phase='count', value=row['decimal_value'], teaching=kind,
                     diagram_alpha=alpha, intro_mode='')

    def state(self, index: int) -> Frame:
        if not 0 <= index < self.frame_count:
            raise IndexError(index)
        t = index / FPS + 1e-9
        row = self.scenes[bisect_right(self.starts, t) - 1]
        if row['scene'] == 'intro':
            frame = self.opening(t)
        elif row['scene'] == 'count':
            frame = self.count(t, row)
        else:
            frame = Frame(phase='finale', value=200, intro_mode='', checkmark=t >= self.finale_start + 1)
        cream = 0
        if t < .8:
            cream = 255 - alpha_ramp(t, .8)
        elif t >= self.duration - 2:
            cream = alpha_ramp(t - (self.duration - 2), (self.frame_count - 1) / FPS - (self.duration - 2))
        if cream:
            frame = Frame(**{**asdict(frame), 'cream': cream})
        return frame

    @lru_cache(maxsize=6)
    def still(self, value: int, kind: str = 'count') -> Image.Image:
        return render(self.background, self.bird, Shot('', '', value, kind))[0]

    def blank_intro(self, show_step: bool) -> Image.Image:
        image = self.still(0).copy()
        draw = ImageDraw.Draw(image)
        # The frame, title, badge and background retain the approved geometry.
        draw.rectangle((90, 242, BOARD[2] - 30, BOARD[3] - 22), fill='#fffaf0')
        checked_text(draw, 'COUNT BY TWOS', (680, 270), 26, MUTED)
        if show_step:
            badge = (1170, 383, 1362, 511)
            rounded(draw, badge, '#e1efe4', '#95b6a0', 3, 26)
            checked_text(draw, '+2', (1266, 447), 73, TEAL, badge)
        return image

    def pair_intro(self, progress: int) -> Image.Image:
        image = self.still(2).copy()
        draw = ImageDraw.Draw(image)
        rounded(draw, TEACHING_FIELD, '#f9f0dd', '#e1cfb2', 2, 21)
        checked_text(draw, '2 BLOCKS  ·  1 PAIR', (750, 716), 31, TEAL, TEACHING_FIELD)
        u = progress / 255
        ease = u * u * (3 - 2 * u)
        if progress == 255:
            rounded(draw, (694, 740, 806, 844), '#fff0d8', '#c6a174', 2, 16)
        for start, finish in (((450, 775), (725, 750)), ((1000, 775), (725, 800))):
            x = round(start[0] + (finish[0] - start[0]) * ease)
            y = round(start[1] + (finish[1] - start[1]) * ease)
            draw_block(draw, x, y, 50, 30)
        return image

    def image(self, frame: Frame) -> Image.Image:
        if frame.cream == 255:
            return FADE_COLOR
        if frame.phase == 'intro':
            if frame.intro_mode == 'blank':
                image = self.blank_intro(frame.show_step)
            elif frame.intro_mode == 'pair':
                image = self.pair_intro(frame.motion_progress)
            elif frame.intro_mode == 'six':
                blank = self.still(6).copy()
                draw = ImageDraw.Draw(blank)
                rounded(draw, TEACHING_FIELD, '#f9f0dd', '#e1cfb2', 2, 21)
                image = Image.blend(blank, self.still(6, 'pairs'), frame.diagram_alpha / 255)
            else:
                image = self.still(0, 'zero').copy()
        elif frame.phase == 'count':
            image = self.still(frame.value, 'zero' if frame.value == 0 else 'count')
            if frame.teaching and frame.diagram_alpha:
                kind = 'twenty-pairs' if frame.teaching == 'T020' else 'final-digit-rule'
                image = Image.blend(image, self.still(frame.value, kind), frame.diagram_alpha / 255)
        else:
            image = self.still(200, 'finale').copy()
            if not frame.checkmark:
                ImageDraw.Draw(image).rectangle((1244, 740, 1320, 801), fill='#f9f0dd')
        return Image.blend(image, FADE_COLOR, frame.cream / 255) if frame.cream else image

    def audit(self) -> dict:
        records = []
        for row in self.counts:
            value = row['decimal_value']
            indices = sorted({math.ceil(row['start_s'] * FPS - 1e-7),
                              math.ceil(row['voice_start_s'] * FPS - 1e-7),
                              math.ceil(row['voice_end_s'] * FPS - 1e-7) - 1,
                              math.ceil(row['end_s'] * FPS - 1e-7) - 1})
            if any(self.state(index).value != value for index in indices):
                raise ValueError(f'Frame-grid display mismatch for {value}')
            records.append({'decimal_value': value, 'sample_indices': indices})
        return {'timeline': self.validation, 'layout': self.layout_validation,
                'frame_grid_values_checked': records,
                'intro_animation': {'two_block_glide_s': [8.3, 8.9], 'six_reveal_s': [12.3, 12.9],
                                    'six_clear_s': [23.8, 24.2], 'zero_visible_from_s': 24.2},
                'teaching_animation_relative_s': {'show': [0, .5], 'hide': [7.4, 7.9]},
                'finale_checkmark_relative_s': 1, 'final_fade_last_s': 2,
                'character_registration': self.bird.metadata,
                'background_sha256': file_hash(BACKGROUND),
                'background_source_size_px': list(self.background_size),
                'background_fit': 'centered isotropic cover',
                'renderer_sha256': file_hash(Path(__file__)),
                'mockup_renderer_sha256': file_hash(ROOT / 'tools/render_even_mockups.py')}


def previews(scene: Scene, folder: Path, positions: list[float]) -> dict:
    if folder.exists():
        raise FileExistsError('Choose a new preview folder')
    folder.mkdir(parents=True)
    records = []
    for position in positions:
        if not 0 <= position < scene.duration:
            raise ValueError(f'Preview outside the timeline: {position}')
        index = min(scene.frame_count - 1, math.ceil(position * FPS - 1e-7))
        frame = scene.state(index)
        path = folder / f'frame-{index:06d}.png'
        scene.image(frame).save(path)
        records.append({'requested_time_s': position, 'frame_index': index, 'time_s': index / FPS,
                        'size_px': list(SIZE), 'state': asdict(frame), 'path': path.name,
                        'sha256': file_hash(path)})
    manifest = {'status': 'renderer-preview', 'preview_only': True, 'duration_s': scene.duration,
                'duration_frames': scene.frame_count, 'fps': FPS, 'frames': records, 'audit': scene.audit()}
    (folder / 'renderer-preview-qa.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'preview_dir': str(folder), 'frames': len(records), 'all_values_checked': 101}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--audio', type=Path)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, default=Path('D:/temp/even-counting-render'))
    parser.add_argument('--ffmpeg')
    parser.add_argument('--preview', type=float, nargs='+')
    parser.add_argument('--preview-dir', type=Path)
    parser.add_argument('--planning-preview', action='store_true')
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--crf', type=int, default=18)
    parser.add_argument('--preset', default='medium')
    parser.add_argument('--audio-gain-db', type=float)
    args = parser.parse_args()
    if not args.render and not args.preview:
        parser.error('Use --preview <times> for stills or --render --audio <master.wav> for delivery')
    if args.render and (args.audio is None or args.planning_preview):
        parser.error('Delivery requires measured --timeline and --audio; planning previews cannot be rendered')
    document = json.loads(args.timeline.read_text(encoding='utf-8-sig'))
    if args.planning_preview:
        document = planning_contract(document)
    scene = Scene(document)
    if args.preview:
        print(json.dumps(previews(scene, args.preview_dir or args.out_dir / 'renderer-previews', args.preview)), flush=True)
    if not args.render:
        return
    if document.get('preview_only') or not scene.voice_events:
        raise ValueError('Delivery requires measured voice_events')
    audio = args.audio.resolve()
    with wave.open(str(audio), 'rb') as track:
        audio_properties = {'sample_rate': track.getframerate(), 'channels': track.getnchannels(),
                            'sample_width_bytes': track.getsampwidth(), 'samples': track.getnframes()}
        if abs(track.getnframes() - round(scene.duration * track.getframerate())) > 1:
            raise ValueError('The WAV duration differs from the measured timeline by more than one sample')
    gain = args.audio_gain_db
    if gain is None:
        gain = document.get('audio_mix', {}).get('required_delivery_gain_db', document.get('delivery_gain_db', 0))
    if not math.isfinite(gain):
        raise ValueError('Delivery gain must be finite')
    destination = args.out_dir.resolve()
    video_path = destination / VIDEO_NAME
    report_path = destination / 'render-report.json'
    if video_path.exists() or report_path.exists():
        raise FileExistsError('Delivery artifacts already exist; choose a new output directory')
    destination.mkdir(parents=True, exist_ok=True)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg(args.ffmpeg)
    start = time.perf_counter()
    audit = scene.audit()
    with TemporaryDirectory(prefix='even-render-', dir=args.work_dir) as directory:
        folder = Path(directory)
        concat, unique, runs = stage_frames(scene, folder)
        print(f'Staged {unique} distinct images in {runs} holds for {scene.frame_count} frames.', flush=True)
        result = folder / 'even.mp4'
        encode(concat, audio, result, scene.frame_count, ffmpeg, args.crf, args.preset, gain)
        if video_path.exists():
            raise FileExistsError(video_path)
        shutil.move(result, video_path)
    report = {'output': str(video_path), 'video_sha256': file_hash(video_path),
              'timeline': str(args.timeline.resolve()), 'timeline_sha256': file_hash(args.timeline),
              'audio': str(audio), 'audio_sha256': file_hash(audio), 'audio_properties': audio_properties,
              'audio_gain_db': gain, 'frame_size_px': list(SIZE), 'fps': FPS,
              'duration_frames': scene.frame_count, 'audio_duration_s': scene.duration,
              'video_duration_s': scene.frame_count / FPS, 'distinct_images': unique, 'holds': runs,
              'crf': args.crf, 'preset': args.preset, 'ffmpeg': ffmpeg,
              'render_elapsed_s': round(time.perf_counter() - start, 3), 'audit': audit,
              'final_encoded_video_qa_pending': True}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('output', 'duration_frames', 'video_duration_s',
                                                 'audio_gain_db', 'render_elapsed_s')}))


if __name__ == '__main__':
    main()
