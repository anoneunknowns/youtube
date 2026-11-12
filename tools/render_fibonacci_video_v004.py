"""Render richer cue-driven cat acting over the unchanged v003 teaching canvas.

Values, voice cues, measured audio, mathematical motion and the F20 type easing
remain frozen. Only the registered cat drawings and their acting schedule change.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path

from PIL import Image

try:
    import render_fibonacci_video as lesson
    import render_fibonacci_video_v002 as pipeline
    import render_fibonacci_video_v003 as retained
    import fibonacci_character_animation_v004 as animation
except ModuleNotFoundError:
    from tools import render_fibonacci_video as lesson
    from tools import render_fibonacci_video_v002 as pipeline
    from tools import render_fibonacci_video_v003 as retained
    from tools import fibonacci_character_animation_v004 as animation

ROOT, FPS, SIZE = lesson.ROOT, lesson.FPS, lesson.SIZE
m, Frame, VIDEO_NAME = lesson.m, lesson.Frame, lesson.VIDEO_NAME
stage, encode, aac_hash = lesson.stage, pipeline.encode, pipeline.aac_hash
RETAINED_RENDERERS = (
    (lesson, '92ab38464ad197dacfea3d70abfd7a3a02f15a55d25cd5e66a2cd5f80647de45'),
    (pipeline, 'c72a2e4c221f3c99243ffe04ea35a8a0804afd33a1f343a48036aeb6465923da'),
    (retained, '7eafca5114b9cc7ceec22d4c97580eb2080ac2f7f5aec137fc8ad6737f0e9cf1'))


class Scene(lesson.Scene):
    def __init__(self, plan):
        for module, expected in RETAINED_RENDERERS:
            if lesson.digest(Path(module.__file__)) != expected:
                raise ValueError(f'Retained renderer changed: {module.__name__}')
        base = animation.read(plan['source_timeline'])
        for key in pipeline.UNCHANGED_FIELDS:
            if plan[key] != base[key]:
                raise ValueError(f'Character revision changes measured audio/content: {key}')
        self.motion = animation.read(plan['character_motion'])
        expected = animation.make_motion(base, plan['source_timeline'], self.motion['source_motion'],
                                        self.motion['registry'], self.motion['source_schedule'])
        if self.motion != expected:
            raise ValueError('Character motion differs from its accepted artwork/cue schedule')
        super().__init__(plan)
        self.schedule = animation.Schedule(self.motion)
        self.character = animation.Artwork(self.motion)
        self.frozen_sources += [pipeline.receipt(Path(module.__file__)) for module, _ in RETAINED_RENDERERS]
        self.frozen_sources += [plan['source_timeline'], plan['character_motion'],
            self.motion['source_motion'], self.motion['source_schedule'],
            self.motion['registry'], self.motion['retained_registry'],
            pipeline.receipt(Path(animation.__file__))]

    def state(self, index):
        state = super().state(index)
        return replace(state, pose=self.schedule.state(index, state.mode).pose)

    def image(self, state):
        # The v003-only font override is local to these two copied glyphs.
        is_f20 = state.mode == 'count' and state.n == 20 and state.stage == 'transfer'
        name = json.dumps(asdict(state), sort_keys=True)
        c = (retained.Canvas(self.background, name, retained.transfer_font_px(state.transfer_tick/30))
             if is_f20 else lesson.Canvas(self.background, name))
        m.header(c)
        if state.mode == 'opening':
            lesson.opening(c)
        elif state.mode == 'seeds':
            m.seeds(c) if state.n is None else lesson.seed_count(c, state.n)
        elif state.mode == 'rule':
            lesson.legend(c, 'indices') if state.legend in ('indices', 'I04') else m.general_rule(c)
        elif state.mode == 'legend':
            lesson.legend(c, state.legend)
        elif state.mode == 'count':
            if state.n < 2:
                lesson.seed_count(c, state.n)
            elif is_f20:
                retained.f20_handoff(c, state.transfer_tick/30)
            else:
                lesson.equation(c, state.n, state.stage, state.transfer_tick/30)
        elif state.mode == 'replay':
            lesson.replay(c, state)
        elif state.mode == 'finale':
            m.history(c) if state.legend in ('history', 'recap', 'O01', 'O03') else m.finale(c)
        else:
            raise ValueError(f'Unknown visual mode: {state.mode}')
        self.character.draw(c, state.pose)
        c.check_foreground_clearance()
        image = Image.blend(c.image, self.cream, state.cream/255) if state.cream else c.image
        report = {'state': asdict(state), 'components': c.records,
                  'intentional_absences': c.absent, 'scene_data': c.data,
                  'native_layout_tolerance_px': .5,
                  'underlying_layout_passed': all(row['passed'] for row in c.records),
                  'foreground_groups_do_not_overlap': c.data['foreground_groups_do_not_overlap'],
                  'whole_frame_fade': bool(state.cream)}
        return image.convert('RGB'), report


def prepare_timeline(source_top, destination, registration, schedule):
    """First-create v004 metadata, binding the unchanged immutable audio parent."""
    source_top, destination = Path(source_top), Path(destination)
    old = json.loads(source_top.read_text())
    base = animation.read(old['source_timeline'])
    for key in pipeline.UNCHANGED_FIELDS:
        if old[key] != base[key]:
            raise ValueError(f'Retained lesson differs from measured base: {key}')
    motion = animation.make_motion(base, old['source_timeline'], old['character_motion'],
                                   pipeline.receipt(registration), pipeline.receipt(schedule))
    destination.parent.mkdir(parents=True, exist_ok=True)
    motion_path = destination.with_name('character-motion.json')
    lesson.save_new(motion_path, motion)
    plan = {**old, 'revision_id': 'fibonacci-counting-v004',
        'renderer_implementation': 'tools/render_fibonacci_video_v004.py',
        'source_visual_revision': pipeline.receipt(source_top),
        'character_motion': pipeline.receipt(motion_path),
        'renderer_source': pipeline.receipt(Path(__file__)),
        'character_animation': {'kind': motion['kind'], 'registration': motion['registry'],
            'source_schedule': motion['source_schedule'],
            'implementation': pipeline.receipt(Path(animation.__file__)),
            'body_height_px': 400, 'ground_foot_anchor_px': [1655, 990],
            'direct_generated_pose_count': len(animation.REQUIRED_NEW_POSES),
            'frame_interpolation': 'one intact held drawing; no actor crossfade or body bounce',
            'retained_artwork_count': len(animation.read(old['character_motion'])['poses'])}}
    lesson.save_new(destination, plan)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-timeline', type=Path, required=True)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--registration', type=Path, required=True)
    parser.add_argument('--schedule', type=Path, required=True)
    args = parser.parse_args()
    prepare_timeline(args.source_timeline, args.timeline, args.registration, args.schedule)


if __name__ == '__main__':
    main()
