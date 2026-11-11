"""Render simultaneous binary/decimal/octal/hexadecimal counting with decimal speech."""
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
from render_four_base_mockups import (BACKGROUND, CHARACTER, CREAM, ROOT, ROWS, SIZE, TEAL,
                                     LittleBird, Shot, file_hash, render, rounded)
from render_octal_video import encode, preview, stage_frames

FADE_COLOR = Image.new('RGB', SIZE, CREAM)
ROW_IDS = tuple(row[0] for row in ROWS)


@dataclass(frozen=True)
class Frame:
    value: int = 0
    voice_active: bool = False
    teaching_marks: tuple[tuple[str, int], ...] = ()
    row_focus: str | None = None
    bird_pose: str = 'neutral'
    bird_lift: int = 0
    bird_shadow_percent: int = 100
    cream: int = 0


def count_events(timeline):
    result = {}
    for event in timeline.get('events', []):
        if event.get('phase') == 'count' and 'decimal_value' in event and event['type'] != 'sfx':
            value = event['decimal_value']
            if value in result:
                raise ValueError(f'More than one decimal utterance for {value}')
            result[value] = event
    if result and sorted(result) != list(range(128)):
        raise ValueError('Measured voices must contain one complete utterance for each value 0–127')
    return result


class BirdActor:
    """Draw exact registered sprites; optional approved poses share a fixed stage root."""
    def __init__(self, motion_manifest: Path | None = None):
        self.base = LittleBird(height=280, root=(1675, 950), character_manifest=CHARACTER)
        self.height, self.root = 280, (1675, 950)
        self.poses = {'neutral': (self.base.sprite, self.base.position)}
        self.cues = []
        self.frame = Frame()
        if motion_manifest is not None:
            document = json.loads(motion_manifest.read_text(encoding='utf-8'))
            for name, entry in document.get('poses', {}).items():
                if name == 'neutral':
                    raise ValueError('The canonical neutral cannot be replaced by a motion pose')
                path = ROOT / entry['path']
                if file_hash(path) != entry['sha256']:
                    raise ValueError(f'Motion source changed: {path}')
                with Image.open(path) as source:
                    sprite = source.convert('RGBA')
                if 'crop_xyxy' in entry:
                    sprite = sprite.crop(entry['crop_xyxy'])
                scale = self.height / entry['reference_height_px']
                sprite = sprite.resize((round(sprite.width * scale), round(sprite.height * scale)), Image.Resampling.LANCZOS)
                anchor = entry['anchor_px']
                position = tuple(round(origin - offset * scale) for origin, offset in zip(self.root, anchor, strict=True))
                bounds = sprite.getchannel('A').point(lambda alpha: 255 if alpha >= 8 else 0).getbbox()
                visible = (bounds[0]+position[0], bounds[1]+position[1], bounds[2]+position[0], bounds[3]+position[1])
                if visible[0] <= 1440 or visible[2] >= 1920 or visible[1] < 150 or visible[3] >= 1080:
                    raise ValueError(f'Motion pose leaves the bird stage: {name} {visible}')
                self.poses[name] = sprite, position
            self.cues = document.get('cues', [])
            previous = 0.0
            for cue in self.cues:
                if not previous <= cue['start_s'] < cue['end_s']:
                    raise ValueError('Motion cues must be positive, ordered and nonoverlapping')
                previous = cue['end_s']
                sequence = cue.get('sequence', [{'at_s': 0, 'pose': 'neutral'}])
                if sequence[0]['at_s'] != 0 or any(row['pose'] not in self.poses for row in sequence):
                    raise ValueError('Motion cues reference an unregistered pose')
                if [row['at_s'] for row in sequence] != sorted({row['at_s'] for row in sequence}):
                    raise ValueError('Motion pose times must be unique and ordered')
                if sequence[-1]['at_s'] >= cue['end_s'] - cue['start_s']:
                    raise ValueError('A motion pose lies after its cue')
                if cue.get('lift_px', 0) < 0 or not 0 <= cue.get('shadow_shrink', 0) <= .5:
                    raise ValueError('Invalid hop lift or shadow change')

    def state(self, t):
        for cue in self.cues:
            if cue['start_s'] <= t < cue['end_s']:
                age = t - cue['start_s']
                sequence = cue.get('sequence', [{'at_s': 0, 'pose': 'neutral'}])
                pose = next(row['pose'] for row in reversed(sequence) if row['at_s'] <= age)
                progress = math.sin(math.pi * age / (cue['end_s'] - cue['start_s']))
                lift = round(cue.get('lift_px', 0) * progress)
                shrink = cue.get('shadow_shrink', .15 if cue.get('lift_px', 0) else 0)
                return pose, lift, round(100 * (1 - shrink * progress))
        return 'neutral', 0, 100

    def draw(self, image):
        sprite, position = self.poses[self.frame.bird_pose]
        lift = self.frame.bird_lift
        shadow = Image.new('RGBA', SIZE)
        draw = ImageDraw.Draw(shadow)
        x, y = self.root
        ratio = self.height / 430
        shrink = self.frame.bird_shadow_percent / 100
        draw.ellipse((x - 145 * ratio * shrink, y - 3 * ratio,
                      x + 145 * ratio * shrink, y + 25 * ratio), fill=(82, 69, 57, 33))
        image.alpha_composite(shadow)
        image.alpha_composite(sprite, (position[0], position[1] - lift))


class Scene:
    def __init__(self, timeline, motion_manifest=None):
        self.timeline = timeline
        self.duration = timeline.get('duration_s', timeline.get('duration_s_estimate'))
        if self.duration is None or self.duration <= 0 or timeline.get('fps', FPS) != FPS:
            raise ValueError('A positive measured or planning timeline at 30fps is required')
        self.frame_count = math.ceil(self.duration * FPS - 1e-7)
        self.intro_end = timeline['intro']['duration_s']
        self.finale_start = timeline['finale']['estimated_start_s']
        self.fade_start = self.finale_start + timeline['finale']['relative_cream_fade_s'][0]
        self.counts = timeline['counted_states']
        if [state['decimal_value'] for state in self.counts] != list(range(128)):
            raise ValueError('The display states must cover each value 0–127')
        self.starts = [state['estimated_display_start_s'] for state in self.counts]
        self.voices = count_events(timeline)
        self.dialogue = {cue['id']: tuple(cue['relative_window_s']) for cue in timeline['intro']['dialogue']}
        for event in timeline.get('events', []):
            self.dialogue[event['id']] = (event['start_s'], event['end_s'])
        self.base_cues = timeline['intro'].get('base_name_cues', timeline.get('base_name_cues', []))
        self.actor = BirdActor(motion_manifest)
        for cue in self.actor.cues:
            if cue['end_s'] > self.duration:
                raise ValueError('Motion exceeds the episode')
            for event in timeline.get('events', []):
                if event['type'] != 'sfx' and max(cue['start_s'], event['start_s']) < min(cue['end_s'], event['end_s']):
                    raise ValueError(f'Motion {cue["id"]} overlaps speech {event["id"]}')
            cuts = self.starts + [self.finale_start]
            if any(cue['start_s'] < cut < cue['end_s'] for cut in cuts):
                raise ValueError(f'Motion {cue["id"]} crosses a value change')
        with Image.open(BACKGROUND) as source:
            self.background = ImageOps.fit(source.convert('RGBA'), SIZE, Image.Resampling.LANCZOS)

    def opening(self, t):
        example = self.timeline['intro'].get('example', {})
        display_start = example.get('display_start_s', self.dialogue['I04-TEN'][0] - .12)
        display_end = example.get('display_end_s', self.dialogue['I06'][0] - .12)
        value = 10 if display_start <= t < display_end else 0
        active = self.dialogue['I04-TEN'][0] <= t < self.dialogue['I04-TEN'][1]
        focus = None
        start, end = self.dialogue['I02']
        if start <= t < end:
            if self.base_cues:
                focus = next((cue.get('row', cue.get('base_id')) for cue in self.base_cues
                              if cue['start_s'] <= t < cue['end_s']), None)
            else:
                focus = ROW_IDS[min(3, int(4 * (t - start) / (end - start)))]
        elif self.dialogue['I03'][0] <= t < self.dialogue['I03'][1]:
            focus = 'decimal'
        return Frame(value=value, voice_active=active, row_focus=focus)

    def count(self, t):
        state = self.counts[bisect_right(self.starts, t) - 1]
        value = state['decimal_value']
        event = self.voices.get(value)
        start = event['start_s'] if event else state['estimated_voice_start_s']
        end = event['end_s'] if event else state['estimated_voice_end_s']
        frame = Frame(value=value, voice_active=start <= t < end)
        for pause in self.timeline['pauses']:
            age = t - pause['estimated_start_s']
            if .2 <= age < min(2.7, pause['duration_s']):
                frame = replace(frame, teaching_marks=tuple((row, 0) for row in pause['focus_rows']))
                break
        return frame

    def state(self, index):
        t = index / FPS + 1e-9
        frame = self.opening(t) if t < self.intro_end else self.count(t) if t < self.finale_start else Frame(value=127)
        pose, lift, shadow = self.actor.state(t)
        frame = replace(frame, bird_pose=pose, bird_lift=lift, bird_shadow_percent=shadow)
        if t < .8:
            frame = replace(frame, cream=round(255 * (1 - t / .8)))
        elif t >= self.fade_start:
            progress = (t - self.fade_start) / ((self.frame_count - 1) / FPS - self.fade_start)
            frame = replace(frame, cream=min(255, round(255 * progress)))
        return frame

    def image(self, frame):
        if frame.cream == 255:
            return FADE_COLOR
        self.actor.frame = frame
        shot = Shot('', '', frame.value, frame.voice_active, frame.teaching_marks)
        image, _ = render(self.background, self.actor, shot)
        if frame.row_focus is not None:
            box = next(box for row, _, _, box in ROWS if row == frame.row_focus)
            rounded(ImageDraw.Draw(image), box, None, TEAL, 5, 21)
        if frame.cream:
            image = Image.blend(image, FADE_COLOR, frame.cream / 255)
        return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--audio', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--motion-manifest', type=Path)
    parser.add_argument('--preview-dir', type=Path)
    parser.add_argument('--preview-at', type=float, nargs='+', default=[0, 2, 6, 12, 15.5, 20, 27, 31, 85, 200, 410])
    parser.add_argument('--ffmpeg')
    parser.add_argument('--crf', type=int, default=18)
    parser.add_argument('--preset', default='veryfast')
    parser.add_argument('--audio-gain-db', type=float, default=0)
    args = parser.parse_args()
    if args.preview_dir is None and (args.audio is None or args.output is None):
        parser.error('Pass --audio and --output for video or --preview-dir for stills')
    timeline = json.loads(args.timeline.read_text(encoding='utf-8-sig'))
    scene = Scene(timeline, args.motion_manifest)
    if args.preview_dir:
        preview(scene, args.preview_dir, args.preview_at)
        if args.output is None:
            return
    if 'duration_s' not in timeline or not scene.voices:
        raise ValueError('A measured timeline is required for the movie')
    if not math.isfinite(args.audio_gain_db):
        raise ValueError('Audio gain must be finite')
    with wave.open(str(args.audio), 'rb') as track:
        if abs(track.getnframes() - round(scene.duration * track.getframerate())) > 1:
            raise ValueError('The audio length differs from the measured timeline')
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg(args.ffmpeg)
    start = time.perf_counter()
    with TemporaryDirectory(prefix='four-base-render-', dir='D:/temp') as directory:
        index, unique, runs = stage_frames(scene, Path(directory))
        print(f'Staged {unique} distinct images in {runs} holds for {scene.frame_count} frames.', flush=True)
        result = Path(directory) / 'four-base.mp4'
        encode(index, args.audio.resolve(), result, scene.frame_count, ffmpeg, args.crf, args.preset, args.audio_gain_db)
        if output.exists():
            raise FileExistsError(output)
        shutil.move(result, output)
    print(json.dumps({'output':str(output), 'frame_count':scene.frame_count,'fps':FPS,
                      'audio_duration_s':scene.duration,'video_duration_s':scene.frame_count/FPS,
                      'audio_gain_db':args.audio_gain_db,'render_elapsed_s':round(time.perf_counter()-start,3)}))


if __name__ == '__main__':
    main()
