"""Registered, cue-driven acting for the Fibonacci Siamese cat.

Each state uses one intact accepted drawing. Small gaze, neck-nod and eyelid
changes belong to those drawings, not to a whole-body stretch, bounce, dissolve
or a locally patched outline. The common family scale and anatomical feet are
preserved, including when the head intentionally inclines during a nod.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from functools import lru_cache
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

try:
    import render_fibonacci_video_v002 as retained
except ModuleNotFoundError:
    from tools import render_fibonacci_video_v002 as retained

ROOT, FPS, SIZE = retained.ROOT, retained.FPS, retained.SIZE
BODY_HEIGHT = 400
FOOT_ROOT = (1655, 990)
CORRIDOR = (1410, 540, 1885, 1020)
REQUIRED_NEW_POSES = ('watch_upper_left', 'watch_lower_left', 'nod_mid',
                      'nod_down', 'blink_half', 'blink_closed')
POSE_FIELDS = ('path', 'sha256', 'anchor_px', 'reference_height_px', 'eyes_closed')
receipt, checked, resolve = retained.receipt, retained.checked, retained.resolve


def read(reference):
    return json.loads(checked(reference).read_text())


def _integer(value, label, positive=False):
    if isinstance(value, bool) or not isinstance(value, int) or value < int(positive):
        raise ValueError(f'{label} must be a nonnegative integer' if not positive
                         else f'{label} must be a positive integer')
    return value


def _pose(ident, row):
    if any(key not in row for key in POSE_FIELDS):
        raise ValueError(f'Incomplete pose registration: {ident}')
    if not isinstance(row['eyes_closed'], bool):
        raise ValueError(f'eyes_closed must be explicit: {ident}')
    anchor = row['anchor_px']
    height = row['reference_height_px']
    if len(anchor) != 2 or not all(isinstance(v, (float, int)) and math.isfinite(v) for v in anchor):
        raise ValueError(f'Nonfinite anatomical foot: {ident}')
    if not isinstance(height, (int, float)) or not math.isfinite(height) or height <= 0:
        raise ValueError(f'Invalid common reference height: {ident}')
    if len(row['sha256']) != 64:
        raise ValueError(f'Invalid source SHA: {ident}')
    result = {key: row[key] for key in POSE_FIELDS}
    for key in ('eye_state', 'family', 'intent'):
        if key in row:
            result[key] = row[key]
    return result


def _validate_windows(windows, poses, total, events=None):
    previous_end = 0
    names = set()
    for window in windows:
        ident = window['id']
        if ident in names:
            raise ValueError(f'Duplicate action id: {ident}')
        names.add(ident)
        start = _integer(window['start_frame'], f'{ident} start_frame')
        end = _integer(window['end_frame'], f'{ident} end_frame', True)
        if start < previous_end or end <= start or end > total:
            raise ValueError(f'Overlapping, unordered or out-of-range action: {ident}')
        for key, frame in (('start_s', start), ('end_s', end)):
            if not math.isfinite(window[key]) or abs(window[key]-frame/FPS) > 1e-7:
                raise ValueError(f'Action seconds differ from its frame grid: {ident}')
        keys = window['keyframes']
        if not keys:
            raise ValueError(f'Empty action: {ident}')
        cursor = start
        for key in keys:
            frame = _integer(key['at_frame'], f'{ident} at_frame')
            length = _integer(key['hold_frames'], f'{ident} hold_frames', True)
            if frame != cursor or abs(key['at_s']-frame/FPS) > 1e-7:
                raise ValueError(f'Gap/overlap inside action: {ident}')
            if key['interpolation'] != 'hold':
                raise ValueError('Only one intact held drawing is allowed; no crossfade')
            if key['pose_id'] not in poses:
                raise ValueError(f'Unavailable drawing {key["pose_id"]} in {ident}')
            cursor += length
        if cursor != end:
            raise ValueError(f'Keypose duration differs from window: {ident}')
        cue = window.get('source_cue')
        if cue and events is not None and 'id' in cue and 'edge' in cue and 'offset_s' in cue:
            if cue['id'] not in events or cue['edge'] not in ('start_s', 'end_s'):
                raise ValueError(f'Unknown source cue: {ident}')
            exact = events[cue['id']][cue['edge']] + cue['offset_s']
            expected = retained.previous.frame_at(exact)
            if start != expected:
                raise ValueError(f'Action no longer follows its measured cue: {ident}')
        previous_end = end


def validate_motion(motion, base=None, source_reference=None):
    if motion['fps'] != FPS or motion['body_height_px'] != BODY_HEIGHT:
        raise ValueError('Fibonacci character requires its fixed 400px physical scale at30fps')
    if motion['ground_foot_anchor_px'] != list(FOOT_ROOT):
        raise ValueError('Fibonacci anatomical foot support changed')
    if motion.get('full_actor_crossfade') is not False or motion.get('source_art_modified_at_render') is not False:
        raise ValueError('Full-actor dissolve or source-art editing is forbidden')
    if motion.get('drawing_transform') != 'common-isotropic-family-scale-and-registered-foot-translation':
        raise ValueError('Unsupported character transform')
    total = _integer(motion['duration_frames'], 'duration_frames', True)
    poses = {ident: _pose(ident, row) for ident, row in motion['poses'].items()}
    defaults = [motion.get('default_pose', 'watch_left'),
                *motion.get('default_pose_by_mode', {}).values()]
    if not set(defaults) <= poses.keys():
        raise ValueError('Default character drawing is unregistered')
    missing = set(REQUIRED_NEW_POSES)-poses.keys()
    if missing:
        raise ValueError(f'New accepted acting drawings are missing: {sorted(missing)}')
    if not poses['blink_closed']['eyes_closed'] or poses['blink_half']['eyes_closed']:
        raise ValueError('Half and closed eyelid registrations are inconsistent')
    events = None
    if base is not None:
        if total != base['duration_frames']:
            raise ValueError('Acting changed the measured lesson duration')
        events = {event['id']: event for event in base['voice_events']}
    if source_reference is not None and motion['source_timeline'] != source_reference:
        raise ValueError('Acting is not bound to the immutable measured base')
    _validate_windows(motion['windows'], poses, total, events)
    used = {key['pose_id'] for window in motion['windows'] for key in window['keyframes']}
    if not set(REQUIRED_NEW_POSES) <= used:
        raise ValueError(f'Accepted new drawings are not scheduled: {sorted(set(REQUIRED_NEW_POSES)-used)}')
    schedule = Schedule(motion, _already_validated=True)
    longest_closed = run = 0
    for frame in range(total):
        closed = poses[schedule.state(frame).pose]['eyes_closed']
        run = run+1 if closed else 0
        longest_closed = max(longest_closed, run)
    max_closed = motion.get('episode_editing_requirements', {}).get('max_continuous_closed_eyes_s', 2)
    if longest_closed > math.floor(max_closed*FPS+1e-7):
        raise ValueError('Unintended long closed-eye hold')
    return {'passed': True, 'windows': len(motion['windows']), 'registered_drawings': len(poses),
            'longest_closed_eye_hold_frames': longest_closed,
            'all_new_drawings_scheduled': True, 'fixed_body_and_feet': True}


def make_motion(base, source_reference, retained_motion_reference, registration_reference, schedule_reference):
    """Freeze accepted old/new drawings and the separately authored cue schedule."""
    old = read(retained_motion_reference)
    registration, program = read(registration_reference), read(schedule_reference)
    if old['source_timeline'] != source_reference or program['source_timeline'] != source_reference:
        raise ValueError('The old/new acting does not share the immutable measured audio base')
    if program['fps'] != FPS or program['duration_frames'] != base['duration_frames']:
        raise ValueError('Acting schedule changes measured time')
    if not str(registration.get('status', '')).startswith('accepted'):
        raise ValueError('New artwork must be accepted; a placeholder/candidate cannot be adopted')
    if registration.get('source_pixels_modified') is not False or registration.get('creative_composites_used') is not False:
        raise ValueError('Accepted new drawings must be intact direct generated artwork')
    common_height = registration.get('common_reference_height_px')
    if not isinstance(common_height, (int, float)) or not math.isfinite(common_height) or common_height <= 0:
        raise ValueError('The new watch-family must declare one common physical reference height')
    poses = {ident: _pose(ident, row) for ident, row in old['poses'].items()}
    for row in registration['frames']:
        ident = row['id']
        if ident in poses:
            raise ValueError(f'New registration tries to replace a retained drawing: {ident}')
        if row['reference_height_px'] != common_height:
            raise ValueError(f'Individual-pose fitting is forbidden: {ident}')
        poses[ident] = _pose(ident, row)
        poses[ident].setdefault('family', 'fibonacci-v004-watch-left-common-physical-scale')
        poses[ident].setdefault('eye_state', 'closed' if row['eyes_closed'] else
                               'half' if ident == 'blink_half' else 'open')
        poses[ident].setdefault('intent', 'intentional small neck/head nod; torso and feet stay supported'
                               if ident.startswith('nod_') else 'eyelids only'
                               if ident.startswith('blink_') else 'pupil gaze toward the teaching canvas')
        checked(row)
    motion = {'schema_version': 1, 'kind': 'fibonacci-v004-cue-driven-gaze-nod-blink-acting',
        'source_timeline': source_reference, 'fps': FPS, 'duration_frames': base['duration_frames'],
        'source_motion': retained_motion_reference, 'source_schedule': schedule_reference,
        'registry': registration_reference, 'retained_registry': old['registry'],
        'poses': poses, 'body_height_px': BODY_HEIGHT, 'ground_foot_anchor_px': list(FOOT_ROOT),
        'drawing_transform': 'common-isotropic-family-scale-and-registered-foot-translation',
        'interpolation': 'hold', 'full_actor_crossfade': False, 'source_art_modified_at_render': False,
        'default_pose': program.get('default_pose', 'watch_left'),
        'default_pose_by_mode': program.get('default_pose_by_mode', {'opening': 'neutral', 'seeds': 'neutral', 'finale': 'neutral'}),
        'episode_editing_requirements': {'max_continuous_closed_eyes_s': 2,
            'scope': 'This episode retains brief expressions and an open-eye return; not a universal blink-rate standard.',
            'no_substitute_breath_transform': 'No accepted breath drawing exists, so no whole-body periodic scaling or bouncing is used.'},
        'windows': program['windows'], 'schedule_design': program.get('design', {})}
    validate_motion(motion, base, source_reference)
    return motion


@dataclass(frozen=True)
class ActorState:
    pose: str
    action_id: str | None = None
    keyframe_index: int | None = None


class Schedule:
    def __init__(self, motion, _already_validated=False):
        if not _already_validated:
            validate_motion(motion)
        self.motion = motion
        self.total_frames = motion['duration_frames']
        self.windows = motion['windows']
        self.starts = [window['start_frame'] for window in self.windows]
        self.key_starts = [[key['at_frame'] for key in window['keyframes']] for window in self.windows]

    def action_at(self, frame):
        i = bisect_right(self.starts, frame)-1
        return i if i >= 0 and frame < self.windows[i]['end_frame'] else None

    def state(self, frame, mode=None):
        if not isinstance(frame, int) or isinstance(frame, bool) or not 0 <= frame < self.total_frames:
            raise IndexError(frame)
        action = self.action_at(frame)
        if action is None:
            pose = self.motion.get('default_pose_by_mode', {}).get(mode,
                    self.motion.get('default_pose', 'watch_left'))
            return ActorState(pose)
        window = self.windows[action]
        key = bisect_right(self.key_starts[action], frame)-1
        return ActorState(window['keyframes'][key]['pose_id'], window['id'], key)


class Artwork:
    def __init__(self, motion):
        self.poses = motion['poses']
        self.height, self.foot = BODY_HEIGHT, FOOT_ROOT
        self.receipts = {}

    @lru_cache(maxsize=64)
    def sprite(self, pose):
        row = self.poses[pose]
        path = checked(row)
        with Image.open(path) as original:
            image = original.convert('RGBA')
        source_size = image.size
        source_bounds = retained.m.visible(image, 8)
        if not source_bounds or min(source_bounds[:2]) <= 0 or source_bounds[2] >= image.width or source_bounds[3] >= image.height:
            raise ValueError(f'Empty or source-edge-clipped character drawing: {pose}')
        scale = self.height/row['reference_height_px']
        image = image.resize((round(image.width*scale), round(image.height*scale)), Image.Resampling.LANCZOS)
        xy = tuple(round(a-b*scale) for a, b in zip(self.foot, row['anchor_px']))
        box = retained.m.visible(image, 8)
        bounds = [box[0]+xy[0], box[1]+xy[1], box[2]+xy[0], box[3]+xy[1]]
        x0, y0, x1, y1 = CORRIDOR
        if not (x0 <= bounds[0] < bounds[2] <= x1 and y0 <= bounds[1] < bounds[3] <= y1):
            raise ValueError(f'Character drawing enters teaching area or clips: {pose}: {bounds}')
        self.receipts[pose] = {'pose': pose, **row, 'body_height_px': self.height,
            'source_size_px': list(source_size), 'source_scale': scale,
            'foot_anchor_px': list(self.foot), 'source_anchor_px': row['anchor_px'],
            'source_reference_height_px': row['reference_height_px'], 'visible_box_xyxy': bounds,
            'source_pixels_modified': False, 'mirrored': False, 'actor_crossfade': False,
            'placement_intent': 'anatomical foot support and common physical family scale; no individual bbox fit'}
        return image, xy

    def draw(self, canvas, pose):
        shadow = Image.new('RGBA', SIZE)
        ImageDraw.Draw(shadow).ellipse((1530, 977, 1815, 1007), fill=(74, 88, 89, 22))
        canvas.image.alpha_composite(shadow)
        image, xy = self.sprite(pose)
        canvas.image.alpha_composite(image, xy)
        canvas.data['character'] = self.receipts[pose]

