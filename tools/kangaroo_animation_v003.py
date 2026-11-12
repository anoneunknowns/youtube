"""Purposeful museum-guide acting with a stable standing head, body and tail.

Generated arm drawings replace only their measured local regions. The source
PNGs remain unchanged; grouped physical scales and anatomical feet are explicit.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

try:
    import kangaroo_animation as previous
except ModuleNotFoundError:
    from tools import kangaroo_animation as previous

ROOT = previous.ROOT
FPS = 30
BODY_HEIGHT = 470
FOOT_ROOT = (1625, 1014)
CORRIDOR = previous.CORRIDOR
DEFAULT_REGISTRATION = ROOT / 'assets/library/characters/kangaroo/animations/prime-v002/registration.json'
ActorState = previous.ActorState
Action = previous.Action
repeat = previous.repeat
sha = previous.sha
resolve = previous.resolve
REQUIRED_POSES = (*previous.REQUIRED_POSES, 'takeoff', 'posture_neutral',
    'present_prepare', 'present_open', 'present_point',
    'clap_open', 'clap_touch', 'clap_near',
    'half_seated', 'seated_neutral', 'seated_stretch_half', 'seated_stretch', 'stand_half')


def wave(cycles=1):
    result = repeat('neutral', 3) + repeat('wave_raise', 4) + repeat('wave_high', 4)
    for _ in range(cycles + 1):
        result += repeat('wave_left', 5) + repeat('wave_right', 5)
    return tuple(result + repeat('wave_high', 4) + repeat('wave_raise', 4) + repeat('settle', 3) + repeat('neutral', 5))


def present(hold=15):
    return tuple(repeat('present_prepare', 5) + repeat('present_open', 6)
        + repeat('present_point', hold) + repeat('present_open', 5)
        + repeat('present_prepare', 4) + repeat('neutral', 5))


def clap():
    return tuple(repeat('neutral', 2) + repeat('clap_open', 4)
        + repeat('clap_near', 3) + repeat('clap_touch', 3)
        + repeat('clap_near', 3) + repeat('clap_open', 4)
        + repeat('clap_near', 3) + repeat('clap_touch', 3)
        + repeat('clap_near', 3) + repeat('clap_open', 4)
        + repeat('settle', 3) + repeat('neutral', 4))


def rest():
    return tuple(repeat('neutral', 6) + repeat('half_seated', 12)
        + repeat('seated_neutral', 50) + repeat('seated_stretch_half', 10)
        + repeat('seated_stretch', 34) + repeat('seated_stretch_half', 10)
        + repeat('seated_neutral', 184) + repeat('stand_half', 18)
        + repeat('neutral', 36))


class Schedule:
    def __init__(self, plan, available_poses=REQUIRED_POSES):
        self.plan = plan
        self.available_poses = set(available_poses)
        self.total_frames = plan['duration_frames']
        missing = set(REQUIRED_POSES) - self.available_poses
        if missing:
            raise ValueError(f'Incomplete museum acting material: {sorted(missing)}')
        events = sorted(plan['voice_events'], key=lambda row: row['start_s'])
        by_id = {row['id']: row for row in events}
        counts = {row['ordinal']: row for row in events if row['kind'] == 'count'}
        actions = []

        def add(name, seconds, frames, reason):
            action = Action(name, max(0, round(seconds * FPS)), tuple(frames), reason)
            if action.end_frame >= math.floor((plan['duration_s'] - 2) * FPS):
                raise ValueError(f'Action intersects closing fade: {name}')
            if any(action.start_frame < other.end_frame and other.start_frame < action.end_frame for other in actions):
                raise ValueError(f'Overlapping guide actions: {name}')
            actions.append(action)

        add('opening-wave', 1.1, wave(), 'A brief greeting with fixed head and body.')
        add('factor-presentation', by_id['I03']['start_s'] + .2, present(), 'Show the factor explanation with an open guide hand.')
        add('five-discovery', by_id['I05']['end_s'] + .15, previous.discovery(), 'A small realization after the five-tile example.')
        add('composite-presentation', by_id['I06']['start_s'] + .2, present(22), 'Present the six-tile composite exhibit.')
        add('not-one-think', by_id['I08']['start_s'] + .2, previous.think(), 'Consider the excluded one-factor number.')
        add('two-factor-presentation', by_id['T002a']['start_s'] + .2, present(), 'Show the pair of positive factors.')
        add('nine-thinking', by_id['T009a']['start_s'] + .2, previous.think(), 'Consider the three-by-three exhibit.')
        add('nine-discovery', by_id['T009b']['end_s'] + .15, previous.discovery(), 'Acknowledge why an odd number may be composite.')
        add('bridge-presentation', by_id['T101a']['start_s'] + .2, present(22), 'Show the rejected numbers between 97 and 101.')
        add('gap-discovery', by_id['T101b']['end_s'] + .15, previous.discovery(), 'Acknowledge the next prime after the gap.')
        milestones = (
            (21, 'early-presentation', present(12), 'Guide the viewer back to the changing prime card.'),
            (42, 'quarter-clap', clap(), 'Two small, calm applause beats at the first quarter.'),
            (63, 'middle-rest', rest(), 'One twelve-second sit, stretch, rest and stand sequence; counting continues.'),
            (84, 'halfway-hop', previous.hop(True, True), 'One crouch, takeoff, lift and landing at halfway.'),
            (105, 'later-presentation', present(12), 'A calm open-hand gesture toward the current number.'),
            (126, 'three-quarter-clap', clap(), 'Two small applause beats at three quarters.'),
            (147, 'last-presentation', present(12), 'Present the current prime as the mosaic nears completion.'),
        )
        for ordinal, name, frames, reason in milestones:
            add(name, counts[ordinal]['end_s'] + .35, frames, reason)
        finale = plan['finale']['start_s']
        add('finale-hop', finale + 1.5, previous.hop(True, True), 'A second and final hop celebrates all 168 primes.')
        add('finale-smile', finale + 10, previous.smile(), 'A happy expression supports the final thanks.')
        add('goodbye-wave', finale + 16.2, wave(5), 'A three-second goodbye gives the closing gesture time to read.')

        next_blink = 6.0
        intervals = (5.0, 6.1, 5.6, 6.4, 4.9, 5.8)
        blink_count = 0
        for current, following in zip(events, events[1:]):
            when = max(current['end_s'] + .25, next_blink)
            if following['start_s'] - when < .34:
                continue
            start, frames = round(when * FPS), previous.blink()
            if any(start < action.end_frame and action.start_frame < start + len(frames) for action in actions):
                continue
            add(f'blink-{blink_count + 1:03d}', when, frames, 'One irregular blink in an existing silent gap.')
            next_blink = when + intervals[blink_count % len(intervals)]
            blink_count += 1
        self.actions = sorted(actions, key=lambda row: row.start_frame)
        self.starts = [row.start_frame for row in self.actions]
        self.validate()

    def action_at(self, frame):
        i = bisect_right(self.starts, frame) - 1
        return self.actions[i] if i >= 0 and frame < self.actions[i].end_frame else None

    def state(self, frame):
        if not 0 <= frame < self.total_frames:
            raise IndexError(frame)
        action = self.action_at(frame)
        return action.frames[frame-action.start_frame] if action else ActorState()

    def validate(self):
        for a,b in zip(self.actions,self.actions[1:]):
            if a.end_frame > b.start_frame:
                raise ValueError('Guide actions overlap')
        used = {state.pose for action in self.actions for state in action.frames}
        if not set(REQUIRED_POSES) <= used:
            raise ValueError(f'Unused required guide drawings: {sorted(set(REQUIRED_POSES)-used)}')
        for action in self.actions:
            if action.name.startswith('blink-') or action.name in {'early-presentation','quarter-clap','halfway-hop','later-presentation','three-quarter-clap','last-presentation'}:
                if any(action.start_frame/FPS < row['end_s'] and row['start_s'] < action.end_frame/FPS for row in self.plan['voice_events']):
                    raise ValueError(f'Quiet-gap action overlaps speech: {action.name}')
        return True

    def receipt(self):
        return {'kind':'prime-kangaroo-museum-guide-schedule-v003','fps':FPS,
            'duration_frames':self.total_frames,'body_height_px':BODY_HEIGHT,
            'ground_foot_anchor_px':list(FOOT_ROOT),'audio_timing_changed':False,
            'pose_interpolation':'Original local arm drawings over a fixed neutral; measured complete posture drawings for sit/stretch/hop; no full-actor dissolves or pose-specific fit.',
            'actions':[{'id':a.name,'start_frame':a.start_frame,'end_frame':a.end_frame,
                'start_s':a.start_frame/FPS,'end_s':a.end_frame/FPS,'reason':a.reason,
                'frames':[{'pose':s.pose,'offset_y_px':s.offset_y} for s in a.frames]} for a in self.actions]}


class Artwork(previous.Artwork):
    def __init__(self, registration=DEFAULT_REGISTRATION, height=BODY_HEIGHT, root=FOOT_ROOT):
        self.arm_rig_reports = {}
        super().__init__(registration,height,root)

    def apply_face_overlays(self):
        super().apply_face_overlays()
        for identity, config in self.registration.get('arm_overlays',{}).items():
            base_id = config.get('base_pose','neutral')
            source_id = config.get('source_pose',identity)
            base, source = self.raw_images[base_id].copy(), self.raw_images[source_id]
            transform = config['source_to_base']
            scale = float(transform['scale'])
            translate = [round(v) for v in transform['translate_xy']]
            aligned = Image.new('RGBA',base.size)
            resized = source.resize((round(source.width*scale),round(source.height*scale)),Image.Resampling.LANCZOS)
            aligned.paste(resized,translate)
            mask = Image.new('L',base.size)
            ImageDraw.Draw(mask).polygon([tuple(point) for point in config['replace_polygon_xy']],fill=255)
            feather = float(config.get('feather_px',1.5))
            if feather:
                mask = mask.filter(ImageFilter.GaussianBlur(feather))
            if config.get('lower_body_fade_y'):
                start,end=config['lower_body_fade_y']
                if not 0<=start<end<=base.height:
                    raise ValueError('Invalid measured torso fade interval')
                rows=Image.new('L',(1,base.height));rows.putdata([
                    255 if y<=start else 0 if y>=end else round(255*(end-y)/(end-start))
                    for y in range(base.height)])
                mask=ImageChops.multiply(mask,rows.resize(base.size))
            result = Image.composite(aligned,base,mask)
            render_scale = self.scales[base_id]
            self.images[identity] = result.resize((round(result.width*render_scale),round(result.height*render_scale)),Image.Resampling.LANCZOS)
            self.scales[identity] = render_scale
            self.render_anchors[identity] = self.render_anchors[base_id]
            changed = ImageChops.difference(result,base)
            self.arm_rig_reports[identity] = {'base_pose':base_id,'source_pose':source_id,
                'source_to_base':transform,'replace_polygon_xy':config['replace_polygon_xy'],
                'feather_px':feather,'lower_body_fade_y':config.get('lower_body_fade_y'),
                'changed_source_bounds_px':changed.convert('RGB').getbbox(),
                'source_png_modified':False,'whole_character_rescaling':False}
        self.position.cache_clear();self.bounds.cache_clear();self.layer.cache_clear()

    def receipt(self):
        return {**super().receipt(),'arm_rig':self.arm_rig_reports,
            'rig_method':'Grouped-scale generated source arm pixels replace measured local polygons of one neutral RGBA canvas; its head/ears/pouch/feet/tail remain coherent.'}
