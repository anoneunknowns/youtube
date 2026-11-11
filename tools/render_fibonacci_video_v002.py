"""Episode-local acting revision; accepted arithmetic and v001 sources stay frozen.

The five new PNGs are direct built-in image-generation outputs. Rendering only
uses their registered common physical scales, anatomical feet and RGBA layers.
Discrete held keyposes form two forepaw excursions and an explicit return; no
actor dissolves, image masks, local retouching or number/audio timing changes.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from functools import lru_cache
import json
from pathlib import Path
import subprocess

from PIL import Image

try:
    import render_fibonacci_video as previous
except ModuleNotFoundError:
    from tools import render_fibonacci_video as previous

ROOT, FPS, SIZE = previous.ROOT, previous.FPS, previous.SIZE
m, Frame = previous.m, previous.Frame
VIDEO_NAME = previous.VIDEO_NAME
stage = previous.stage
OLD_RENDERER_SHA256 = '92ab38464ad197dacfea3d70abfd7a3a02f15a55d25cd5e66a2cd5f80647de45'
DEFAULT_REGISTRY = ROOT / 'assets/library/characters/siamese-cat/generation-batches/fibonacci-recheck-v002-01a1cae3/registration.json'
UNCHANGED_FIELDS = ('events', 'voice_events', 'counted_states', 'visual_segments',
                    'scenes', 'duration_s', 'duration_frames', 'master_audio', 'timing')


def resolve(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def receipt(path):
    return {'path': previous.local(path), 'sha256': previous.digest(path)}


def checked(reference):
    path = resolve(reference['path'])
    if previous.digest(path) != reference['sha256']:
        raise ValueError(f'Bound source changed: {path}')
    return path


def all_poses(registration):
    selection = json.loads((previous.DESIGN/'character-selection.json').read_text())['adopted_character']
    legacy = selection['key_poses']
    poses = {'neutral': {**selection['neutral'], 'eyes_closed': False}}
    for ident, row in legacy['poses'].items():
        poses[ident] = {**row, 'reference_height_px': legacy['common_reference_height_px'],
                        'eyes_closed': ident == 'blink'}
    old_extra = json.loads(m.CAT.read_text())
    for row in old_extra['frames']:
        poses[row['id']] = {**row, 'reference_height_px': old_extra['common_reference_height_px'],
                            'eyes_closed': row['id'] == 'delighted'}
    for row in registration['frames']:
        poses[row['id']] = row
    return {ident: {key: row[key] for key in ('path', 'sha256', 'anchor_px',
                    'reference_height_px', 'eyes_closed')} for ident, row in poses.items()}


def make_motion(base, source, registry_reference):
    registry = json.loads(checked(registry_reference).read_text())
    if registry['source_pixels_modified'] or registry['creative_composites_used']:
        raise ValueError('This revision requires unmodified direct tool-output PNGs')
    events = {e['id']: e for e in base['voice_events']}
    poses = all_poses(registry)
    windows = []

    def add(ident, cue, cue_edge, offset, sequence, kind, cycles, reason):
        start = previous.frame_at(events[cue][cue_edge] + offset)
        keys, cursor = [], start
        for pose, length in sequence:
            keys.append({'at_s': cursor/FPS, 'at_frame': cursor, 'pose_id': pose,
                         'hold_frames': length, 'interpolation': 'hold'})
            cursor += length
        windows.append({'id': ident, 'kind': kind, 'start_s': start/FPS,
                        'end_s': cursor/FPS, 'start_frame': start, 'end_frame': cursor,
                        'wave_cycles': cycles, 'source_cue': {'id': cue, 'edge': cue_edge,
                        'offset_s': offset, 'unquantized_s': events[cue][cue_edge]+offset},
                        'reason': reason, 'keyframes': keys})

    wave = [('neutral', 3), ('wave_prepare', 6), ('wave_in', 6), ('wave_out', 7),
            ('wave_in', 7), ('wave_out', 7), ('wave_in', 6), ('wave_prepare', 6), ('neutral', 6)]
    add('opening-wave', 'I01', 'start_s', .1, wave, 'wave', 2,
        'A greeting: raise, two outward-and-return forepaw excursions, lower, settle.')
    add('million-notice', 'N031', 'end_s', .05,
        [('watch_left', 4), ('notice_prepare', 4), ('notice_full', 12),
         ('notice_prepare', 4), ('watch_left', 4)], 'notice', 0,
        'One small upward-left eye reaction after the first million reading, within its existing two-second gap.')
    add('completion-smile', 'O01', 'end_s', .1,
        [('neutral', 4), ('delighted', 36), ('neutral', 6)], 'smile', 0,
        'A brief 1.2-second closed-eye smile, then open eyes; replace the previous long closed-eye hold.')
    add('goodbye-wave', 'O04', 'start_s', .1, wave, 'wave', 2,
        'A clear goodbye wave with an explicit return to the original open-eye normal pose.')
    windows.sort(key=lambda w: w['start_frame'])
    for left, right in zip(windows, windows[1:]):
        if left['end_frame'] > right['start_frame']:
            raise ValueError('Character action windows overlap')
    million = next(w for w in windows if w['id'] == 'million-notice')
    if million['end_s'] > events['N031']['end_s']+2:
        raise ValueError('Notice leaves the existing post-reading gap')
    goodbye = next(w for w in windows if w['id'] == 'goodbye-wave')
    if goodbye['end_s'] > events['O04']['end_s'] or goodbye['end_s'] > base['duration_s']-2:
        raise ValueError('Goodbye leaves its voice cue or enters the closing fade')
    return {'schema_version': 1, 'kind': 'fibonacci-v002-purposeful-character-motion',
            'source_timeline': source, 'fps': FPS, 'duration_frames': base['duration_frames'],
            'registry': registry_reference, 'poses': poses,
            'body_height_px': 400, 'ground_foot_anchor_px': [1655, 990],
            'interpolation': 'hold', 'full_actor_crossfade': False,
            'source_art_modified_at_render': False,
            'default_pose_policy': 'v001 educational poses retained; opening and finale use original neutral. New action windows override only character pose, never lesson content.',
            'episode_editing_requirements': {'max_continuous_closed_eyes_s': 2,
                'scope': 'This Fibonacci revision addresses its previously prolonged finale closed-eye hold; this is not a general blink-rate rule.'},
            'windows': windows}


def prepare_timeline(base_path, top, registry=DEFAULT_REGISTRY):
    """First-create the visual timeline without mutating the measured audio base."""
    base_path, top = Path(base_path), Path(top)
    base = json.loads(base_path.read_text())
    source, regref = receipt(base_path), receipt(registry)
    motion = make_motion(base, source, regref)
    motion_path = top.with_name('character-motion.json')
    previous.save_new(motion_path, motion)
    plan = {**base, 'renderer_implementation': 'tools/render_fibonacci_video_v002.py',
            'source_timeline': source, 'character_motion': receipt(motion_path),
            'character_animation': {'kind': motion['kind'], 'registration': regref,
                'body_height_px': 400, 'ground_foot_anchor_px': [1655, 990],
                'direct_generated_pose_count': 5, 'frame_interpolation': 'held keyposes'},
            'encoded_audio_acceptance': receipt(base_path.with_name('aac-acceptance.json')),
            'renderer_source': receipt(Path(__file__))}
    previous.save_new(top, plan)
    return plan


class Artwork(m.Siamese):
    def __init__(self, registration):
        super().__init__()
        self.additional = {r['id']: r for r in registration['frames']}

    @lru_cache(maxsize=32)
    def sprite(self, pose):
        if pose not in self.additional:
            return super().sprite(pose)
        row = self.additional[pose]
        path = checked(row)
        image = Image.open(path).convert('RGBA')
        scale = self.height/row['reference_height_px']
        image = image.resize((round(image.width*scale), round(image.height*scale)), Image.Resampling.LANCZOS)
        xy = tuple(round(a-b*scale) for a, b in zip(self.foot, row['anchor_px']))
        box = m.visible(image, 8)
        bounds = [box[0]+xy[0], box[1]+xy[1], box[2]+xy[0], box[3]+xy[1]]
        if not (bounds[0] >= 1410 and bounds[2] <= 1885 and bounds[1] >= 540 and bounds[3] <= 1020):
            raise ValueError(f'New actor artwork leaves its clear region: {pose}: {bounds}')
        self.receipts[pose] = {'pose': pose, 'path': row['path'], 'sha256': row['sha256'],
            'body_height_px': self.height, 'source_scale': scale, 'foot_anchor_px': list(self.foot),
            'source_anchor_px': row['anchor_px'], 'source_reference_height_px': row['reference_height_px'],
            'visible_box_xyxy': bounds, 'source_pixels_modified': False, 'mirrored': False,
            'placement_intent': 'anatomical foot support; common physical family scale'}
        return image, xy


class Scene(previous.Scene):
    def __init__(self, plan):
        if previous.digest(Path(previous.__file__)) != OLD_RENDERER_SHA256:
            raise ValueError('The retained v001 renderer changed')
        base_path = checked(plan['source_timeline'])
        base = json.loads(base_path.read_text())
        for key in UNCHANGED_FIELDS:
            if plan[key] != base[key]:
                raise ValueError(f'Visual revision changes measured audio/content: {key}')
        self.motion = json.loads(checked(plan['character_motion']).read_text())
        if self.motion != make_motion(base, plan['source_timeline'], self.motion['registry']):
            raise ValueError('Character schedule differs from its event-relative plan')
        super().__init__(plan)
        self.character = Artwork(json.loads(checked(self.motion['registry']).read_text()))
        self.motion_starts = [w['start_frame'] for w in self.motion['windows']]
        self.frozen_sources += [receipt(Path(previous.__file__)), plan['source_timeline'],
                                self.motion['registry'], plan['character_motion']]

    def action_at(self, index):
        n = bisect_right(self.motion_starts, index)-1
        if n < 0:
            return None
        window = self.motion['windows'][n]
        return window if index < window['end_frame'] else None

    def pose_for(self, mode, n, elapsed, length, t, seg):
        frame = int(round((t-1e-9)*FPS))
        window = self.action_at(frame)
        if window:
            keys = window['keyframes']
            i = bisect_right([k['at_frame'] for k in keys], frame)-1
            return keys[i]['pose_id']
        if mode in ('opening', 'finale'):
            return 'neutral'
        return super().pose_for(mode, n, elapsed, length, t, seg)


def encode(index, audio, output, frames, ffmpeg, preset='veryfast', crf=18):
    """Encode new H264 only; copy the already measured accepted AAC packets."""
    output, audio = Path(output), Path(audio)
    if audio.suffix.lower() not in ('.m4a', '.mp4'):
        raise ValueError('v002 requires accepted AAC M4A/MP4 input; WAV re-encoding is not allowed')
    filters = ('scale=in_range=full:out_range=limited:out_color_matrix=bt709,'
               'setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,'
               f'fps={FPS},trim=end_frame={frames}')
    command = [str(ffmpeg), '-hide_banner', '-loglevel', 'warning', '-stats', '-stats_period', '10',
        '-nostdin', '-n', '-f', 'concat', '-safe', '0', '-i', str(index), '-i', str(audio),
        '-map', '0:v:0', '-map', '1:a:0', '-vf', filters, '-c:v', 'libx264', '-preset', preset,
        '-crf', str(crf), '-pix_fmt', 'yuv420p', '-color_range', 'tv', '-color_primaries', 'bt709',
        '-color_trc', 'bt709', '-colorspace', 'bt709', '-c:a', 'copy', '-movflags', '+faststart', str(output)]
    with output.with_suffix('.ffmpeg.log').open('x') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    if aac_hash(audio, ffmpeg) != aac_hash(output, ffmpeg):
        raise ValueError('Final movie AAC packets differ from accepted encoded audio')
    return command


def aac_hash(path, ffmpeg):
    command = [str(ffmpeg), '-nostdin', '-v', 'error', '-i', str(path), '-map', '0:a:0',
               '-c:a', 'copy', '-f', 'adts', 'pipe:1']
    return __import__('hashlib').sha256(subprocess.check_output(command)).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-timeline', type=Path, required=True)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--registration', type=Path, default=DEFAULT_REGISTRY)
    args = parser.parse_args()
    prepare_timeline(args.base_timeline, args.timeline, args.registration)


if __name__ == '__main__':
    main()
