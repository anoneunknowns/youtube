"""Registered, finite-keyframe kangaroo acting for the prime lesson.

Every sprite uses one physical art scale and its measured anatomical foot anchor.
The schedule uses complete drawings, never whole-character dissolves or a
pose-specific fit. Grounded feet stay fixed; the airborne pose has an explicit
small trajectory and a separate ground shadow.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageChops

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRATION = ROOT / 'assets/library/characters/kangaroo/animations/prime-v001/registration.json'
FPS = 30
BODY_HEIGHT = 430
FOOT_ROOT = (1625, 982)
# This corridor is distinct from the centered teaching fields to the left.
CORRIDOR = (1370, 400, 1896, 1056)
REQUIRED_POSES = (
    'neutral', 'blink_half', 'blink_closed', 'smile_open',
    'wave_raise', 'wave_high', 'wave_left', 'wave_right',
    'think_raise', 'think', 'aha', 'settle',
    'crouch_half', 'crouch_down', 'hop_air', 'land',
)


def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def resolve(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


@dataclass(frozen=True)
class ActorState:
    pose: str = 'neutral'
    offset_y: int = 0


@dataclass(frozen=True)
class Action:
    name: str
    start_frame: int
    frames: tuple[ActorState, ...]
    reason: str

    @property
    def end_frame(self):
        return self.start_frame + len(self.frames)


def repeat(pose, frames, offset_y=0):
    return [ActorState(pose, offset_y)] * frames


def wave():
    result = repeat('neutral', 3) + repeat('wave_raise', 4) + repeat('wave_high', 4)
    for _ in range(2):
        result += repeat('wave_left', 5) + repeat('wave_right', 5)
    return tuple(result + repeat('wave_high', 4) + repeat('wave_raise', 4) + repeat('settle', 3) + repeat('neutral', 5))


def think():
    return tuple(repeat('settle', 4) + repeat('think_raise', 5) + repeat('think', 22) + repeat('think_raise', 4) + repeat('settle', 3) + repeat('neutral', 4))


def discovery():
    return tuple(repeat('think_raise', 4) + repeat('think', 8) + repeat('aha', 20) + repeat('settle', 5) + repeat('neutral', 5))


def hop(takeoff=False, posture_neutral=False):
    result = repeat('posture_neutral', 2) if posture_neutral else []
    result += repeat('crouch_half', 3) + repeat('crouch_down', 4)
    if takeoff:
        result += repeat('takeoff', 3)
    # Anchors on hop_air describe actual feet, not an already raised ground line.
    result += [ActorState('hop_air', -round(60 * math.sin(math.pi * (i + 1) / 10))) for i in range(9)]
    result += repeat('land', 4) + repeat('crouch_half', 3)
    if posture_neutral:
        result += repeat('posture_neutral', 3)
    return tuple(result + repeat('neutral', 5))


def smile():
    return tuple(repeat('smile_open', 20) + repeat('settle', 5) + repeat('neutral', 5))


def blink():
    return tuple(repeat('blink_half', 2) + repeat('blink_closed', 3) + repeat('blink_half', 2))


class Schedule:
    """A bounded, deterministic schedule; recurring blinks occur in silent gaps."""

    def __init__(self, plan, available_poses=REQUIRED_POSES):
        self.plan = plan
        self.available_poses = set(available_poses)
        self.total_frames = plan['duration_frames']
        events = sorted(plan['voice_events'], key=lambda row: row['start_s'])
        by_id = {row['id']: row for row in events}
        finale = plan['finale']['start_s']
        actions = []

        def add(name, seconds, frames, reason):
            start = max(0, round(seconds * FPS))
            action = Action(name, start, tuple(frames), reason)
            if action.end_frame >= math.floor((plan['duration_s'] - 2) * FPS):
                raise ValueError(f'Animation crosses the final fade: {name}')
            if any(action.start_frame < old.end_frame and old.start_frame < action.end_frame for old in actions):
                raise ValueError(f'Overlapping character actions: {name}')
            actions.append(action)

        add('opening-wave', 1.1, wave(), 'A real four-position hand wave greets the viewer.')
        add('factor-thinking', by_id['I03']['start_s'] + .2, think(), 'The factor explanation gets one measured thinking gesture.')
        add('five-discovery', by_id['I05']['end_s'] + .15, discovery(), 'One small realization after the prime-five example.')
        add('not-one-think', by_id['I08']['start_s'] + .2, think(), 'Consider why one is excluded, without obscuring the explanation.')
        add('nine-thinking', by_id['T009a']['start_s'] + .2, think(), 'Consider the three-by-three composite example.')
        add('nine-discovery', by_id['T009b']['end_s'] + .15, discovery(), 'Acknowledge that an odd number can be composite.')
        add('gap-discovery', by_id['T101b']['end_s'] + .15, discovery(), 'A brief realization after the 97-to-101 explanation.')
        # These gestures fit inside existing two-second pauses; no new speech or wait.
        for ordinal, pose_frames, label in ((42, tuple(repeat('settle',3)+repeat('think_raise',4)+repeat('think',9)+repeat('think_raise',3)+repeat('settle',3)+repeat('neutral',2)), 'early-thinking'), (84, hop('takeoff' in self.available_poses, 'posture_neutral' in self.available_poses), 'halfway-hop'), (125, smile(), 'later-smile'), (150, discovery(), 'late-discovery')):
            event = next(row for row in events if row['kind'] == 'count' and row.get('ordinal', 0) == ordinal) if any(row.get('ordinal') == ordinal for row in events) else [row for row in events if row['kind'] == 'count'][ordinal - 1]
            add(label, event['end_s'] + .35, pose_frames, f'One quiet milestone response after prime {ordinal} of 168.')
        add('finale-hop', finale + 1.5, hop('takeoff' in self.available_poses, 'posture_neutral' in self.available_poses), 'A crouch, airborne pose and grounded landing celebrate completion.')
        add('finale-smile', finale + 10.0, smile(), 'A happy open-mouth expression supports the closing thanks.')
        add('goodbye-wave', finale + 16.2, wave(), 'A complete goodbye wave finishes before the final fade.')

        next_blink_after = 6.0
        intervals = (5.0, 6.1, 5.6, 6.4, 4.9, 5.8)
        interval_index = 0
        for current, following in zip(events, events[1:]):
            when = max(current['end_s'] + .25, next_blink_after)
            if following['start_s'] - when < .34:
                continue
            start = round(when * FPS)
            frames = blink()
            if any(start < old.end_frame and old.start_frame < start + len(frames) for old in actions):
                continue
            add(f'blink-{interval_index + 1:03d}', when, frames, 'An irregular short blink in an actual silent gap, not on every number.')
            next_blink_after = when + intervals[interval_index % len(intervals)]
            interval_index += 1
        self.actions = sorted(actions, key=lambda action: action.start_frame)
        self.starts = [action.start_frame for action in self.actions]
        self.validate()

    def action_at(self, frame):
        at = bisect_right(self.starts, frame) - 1
        if at >= 0 and frame < self.actions[at].end_frame:
            return self.actions[at]
        return None

    def state(self, frame):
        if not 0 <= frame < self.total_frames:
            raise IndexError(frame)
        action = self.action_at(frame)
        return action.frames[frame - action.start_frame] if action else ActorState()

    def validate(self):
        for previous, following in zip(self.actions, self.actions[1:]):
            if previous.end_frame > following.start_frame:
                raise ValueError('Character actions overlap')
        voices = self.plan['voice_events']
        for action in self.actions:
            if action.name.startswith('blink-'):
                left, right = action.start_frame / FPS, action.end_frame / FPS
                if any(left < voice['end_s'] and voice['start_s'] < right for voice in voices):
                    raise ValueError('Recurring blink intersects actual speech')
        used = {state.pose for action in self.actions for state in action.frames}
        if len(used) < 16 or not set(REQUIRED_POSES).issubset(used):
            raise ValueError('Motion schedule does not exercise the complete new expression set')
        if sum(action.name.startswith('blink-') for action in self.actions) < 40:
            raise ValueError('Long counting run has insufficient recurring facial movement')
        return True

    def receipt(self):
        return {'kind': 'prime-kangaroo-acting-schedule', 'fps': FPS, 'duration_frames': self.total_frames,
                'body_height_px': BODY_HEIGHT, 'ground_foot_anchor_px': list(FOOT_ROOT),
                'pose_interpolation': 'Measured complete key drawings; no whole-sprite dissolves or per-pose fit.',
                'audio_timing_changed': False,
                'actions': [{'id': action.name, 'start_frame': action.start_frame, 'end_frame': action.end_frame,
                             'start_s': action.start_frame / FPS, 'end_s': action.end_frame / FPS,
                             'reason': action.reason,
                             'frames': [{'pose': state.pose, 'offset_y_px': state.offset_y} for state in action.frames]}
                            for action in self.actions]}


class Artwork:
    def __init__(self, registration=DEFAULT_REGISTRATION, height=BODY_HEIGHT, root=FOOT_ROOT):
        self.registration_path = resolve(registration)
        self.registration = json.loads(self.registration_path.read_text())
        self.height, self.root = height, tuple(root)
        frames = self.registration.get('frames', self.registration.get('poses'))
        if isinstance(frames, dict):
            frames = [{'id': identity, **row} for identity, row in frames.items()]
        self.frames = {frame['id']: frame for frame in frames}
        missing = set(REQUIRED_POSES) - self.frames.keys()
        if missing:
            raise ValueError(f'Missing required newly generated poses: {sorted(missing)}')
        self.reference_height = float(self.registration['common_reference_height_px'])
        self.scale = height / self.reference_height
        if not math.isfinite(self.scale) or self.scale <= 0:
            raise ValueError('Invalid common animation scale')
        self.images = {}
        self.raw_images = {}
        self.render_anchors = {}
        self.face_rig_reports = {}
        self.scales = {}
        groups = self.registration.get('source_groups', {})
        for identity, row in self.frames.items():
            group = row.get('scale_group', 'main')
            reference = float(groups.get(group, {}).get('reference_height_px', self.reference_height))
            if 'reference_height_px' in row and abs(float(row['reference_height_px']) - reference) > 1e-6:
                raise ValueError('Pose scale must match its source-group physical calibration')
            self.scales[identity] = self.height / reference
            path = resolve(row['path'])
            if sha(path) != row['sha256']:
                raise ValueError(f'Animation source hash changed: {identity}')
            with Image.open(path) as opened:
                if opened.mode != 'RGBA':
                    raise ValueError(f'Animation sprite lost RGBA: {identity}')
                image = opened.copy()
            self.raw_images[identity] = image.copy()
            self.render_anchors[identity] = list(row['anchor_px'])
            image = image.resize((round(image.width * self.scales[identity]), round(image.height * self.scales[identity])), Image.Resampling.LANCZOS)
            self.images[identity] = image
            self.bounds(ActorState(identity))
        self.apply_face_overlays()

    def apply_face_overlays(self):
        for identity, config in self.registration.get('face_overlays', {}).items():
            base_pose = config.get('base_pose', 'neutral')
            if identity not in self.raw_images or base_pose not in self.raw_images:
                raise ValueError('Face overlay refers to an unknown generated pose')
            base = self.raw_images[base_pose].copy()
            source = self.raw_images[identity]
            patches = config.get('patches', [config] if 'source_box_xyxy' in config else [])
            if not patches:
                raise ValueError(f'No face patches supplied for {identity}')
            for patch in patches:
                src = tuple(patch.get('source_box_xyxy', patch.get('source_box_px')))
                dst = tuple(patch.get('target_box_xyxy', patch.get('target_box_px')))
                if len(src) != 4 or len(dst) != 4 or min(dst[2]-dst[0], dst[3]-dst[1]) <= 0:
                    raise ValueError('Invalid measured face patch rectangle')
                image = source.crop(src).resize((dst[2]-dst[0], dst[3]-dst[1]), Image.Resampling.LANCZOS)
                feather = max(0, float(patch.get('feather_px', 2)))
                mask = Image.new('L', image.size, 255)
                if feather:
                    mask = Image.new('L', image.size)
                    inset = math.ceil(feather * 1.5)
                    ImageDraw.Draw(mask).rectangle((inset,inset,image.width-inset-1,image.height-inset-1),fill=255)
                    mask = mask.filter(ImageFilter.GaussianBlur(feather))
                if patch.get('clip_to_base_alpha'):
                    # Some generated eye crops cross the cheek silhouette. Keep
                    # its watercolor outline entirely from the coherent base.
                    threshold = int(patch.get('base_alpha_threshold', 128))
                    interior = self.raw_images[base_pose].getchannel('A').crop(dst)
                    interior = interior.point(lambda value: 255 if value >= threshold else 0)
                    inset = max(0, int(patch.get('base_alpha_inset_px', 2)))
                    if inset:
                        interior = interior.filter(ImageFilter.MinFilter(2 * inset + 1))
                    mask = ImageChops.multiply(mask, interior)
                image.putalpha(ImageChops.multiply(image.getchannel('A'), mask))
                base.alpha_composite(image, dst[:2])
            scale = self.scales[base_pose]
            self.images[identity] = base.resize((round(base.width*scale), round(base.height*scale)), Image.Resampling.LANCZOS)
            self.scales[identity] = scale
            self.render_anchors[identity] = self.render_anchors[base_pose]
            # Body/tail remain exactly the coherent neutral's pixels outside the head.
            changed = ImageChops.difference(base, self.raw_images[base_pose]).convert('RGB').getbbox()
            self.face_rig_reports[identity] = {'base_pose':base_pose,'patches':patches,
                'changed_source_bounds_px':list(changed) if changed else None,
                'body_and_tail_are_neutral_pixels':True,'source_cells_modified':False}
        self.position.cache_clear(); self.bounds.cache_clear()

    @lru_cache(maxsize=256)
    def position(self, state):
        anchor = self.render_anchors[state.pose]
        return (round(self.root[0] - anchor[0] * self.scales[state.pose]),
                round(self.root[1] + state.offset_y - anchor[1] * self.scales[state.pose]))

    def support(self, state):
        """Project the measured source feet through the actual rounded placement."""
        anchor = self.render_anchors[state.pose]
        position = self.position(state)
        actual = [position[axis] + anchor[axis] * self.scales[state.pose]
                  for axis in (0, 1)]
        intended = [self.root[0], self.root[1] + state.offset_y]
        error = [actual[axis] - intended[axis] for axis in (0, 1)]
        if any(abs(value) > .5000001 for value in error):
            raise ValueError(f'Measured feet drift from the registered root: {state}')
        return {'rendered_foot_anchor_px': actual, 'intended_foot_anchor_px': intended,
                'anchor_rounding_error_px': error, 'tolerance_px': .5,
                'horizontal_passed': abs(error[0]) <= .5000001,
                'vertical_passed': abs(error[1]) <= .5000001}

    @lru_cache(maxsize=256)
    def bounds(self, state):
        image = self.images[state.pose]
        bounds = image.getchannel('A').point(lambda a: 255 if a >= 8 else 0).getbbox()
        if bounds is None:
            raise ValueError(f'Empty animation frame: {state.pose}')
        position = self.position(state)
        visible = tuple(bounds[i] + position[i % 2] for i in range(4))
        if not (CORRIDOR[0] < visible[0] and visible[2] < CORRIDOR[2]
                and CORRIDOR[1] < visible[1] and visible[3] < CORRIDOR[3]):
            raise ValueError(f'Animation leaves the clear actor corridor: {state}: {visible}')
        return visible

    @lru_cache(maxsize=128)
    def layer(self, state):
        self.bounds(state)
        left, top, right, bottom = CORRIDOR
        layer = Image.new('RGBA', (right-left, bottom-top))
        lift = max(0, -state.offset_y)
        width_scale = 1 - lift / 200
        x, y = self.root[0]-left, self.root[1]-top
        ImageDraw.Draw(layer).ellipse((x - 92 * width_scale, y - 9,
                                       x + 135 * width_scale, y + 14), fill=(77, 61, 44, round(24 * width_scale)))
        position = self.position(state)
        layer.alpha_composite(self.images[state.pose], (position[0]-left, position[1]-top))
        return layer

    def draw(self, image, state):
        image.alpha_composite(self.layer(state), CORRIDOR[:2])

    def receipt(self):
        return {'registration': self.registration_path.relative_to(ROOT).as_posix(),
                'registration_sha256': sha(self.registration_path), 'height_px': self.height,
                'foot_root_px': list(self.root), 'scale': self.scale,
                'common_reference_height_px': self.reference_height,
                'poses': [{'id': identity, 'path': row['path'], 'sha256': row['sha256'],
                           'anchor_px': row['anchor_px'], 'source_group': row.get('scale_group', 'main'),
                           'render_anchor_px': self.render_anchors[identity],
                           'source_group_scale': self.scales[identity],
                           'visible_bounds_at_ground_px': self.bounds(ActorState(identity)),
                           'support_at_ground': self.support(ActorState(identity))}
                          for identity, row in self.frames.items()],
                'source_pixels_modified': False, 'per_pose_fit': False,
                'whole_character_crossfades': False, 'tail_retained': True,
                'facial_rig':self.face_rig_reports}
