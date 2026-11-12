"""Ease the registered F20 pair into the fixed large-number type size.

All v002 character artwork, acting, mathematical values, voice cues and audio
remain unchanged. Only the two copied F20 handoff numbers shrink, on the same
registered movement progress, before they settle into F21's47px input size.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path

from PIL import Image

try:
    import render_fibonacci_video_v002 as previous
except ModuleNotFoundError:
    from tools import render_fibonacci_video_v002 as previous

ROOT, FPS, SIZE = previous.ROOT, previous.FPS, previous.SIZE
m, Frame, VIDEO_NAME = previous.m, previous.Frame, previous.VIDEO_NAME
stage, encode, aac_hash = previous.stage, previous.encode, previous.aac_hash
OLD_V002_RENDERER_SHA256 = 'c72a2e4c221f3c99243ffe04ea35a8a0804afd33a1f343a48036aeb6465923da'


def transfer_font_px(progress):
    """Already-eased, quantized movement progress; deliberately no second ease."""
    if not math.isfinite(progress):
        raise ValueError('Transfer progress must be finite')
    progress = min(1.0, max(0.0, progress))
    return round(88 + (47-88)*progress)


class Canvas(previous.previous.Canvas):
    def __init__(self, image, name, copied_number_font_px):
        super().__init__(image, name)
        self.copied_number_font_px = copied_number_font_px

    def text(self, text, field, size, color=m.INK, ident=None, opacity=1):
        if ident in ('transferred-0', 'transferred-1'):
            size = self.copied_number_font_px
        return super().text(text, field, size, color, ident, opacity)


def f20_handoff(c, progress):
    """Explicit local dispatch; never replaces an old module/global function."""
    previous.previous.equation(c, 20, 'transfer', progress)
    c.data.update(equation_font_px=c.copied_number_font_px,
                  copied_pair_font_px=c.copied_number_font_px,
                  type_transition={'from_px': 88, 'to_px': 47,
                      'progress': progress, 'progress_eased_again': False,
                      'applies_to': ['transferred-0', 'transferred-1'],
                      'size_fitted_to_individual_value': False})


class Scene(previous.Scene):
    def __init__(self, plan):
        if previous.previous.digest(Path(previous.__file__)) != OLD_V002_RENDERER_SHA256:
            raise ValueError('The retained v002 renderer changed')
        super().__init__(plan)
        self.frozen_sources += [previous.receipt(Path(previous.__file__))]

    def image(self, state):
        if not (state.mode == 'count' and state.n == 20 and state.stage == 'transfer'):
            return super().image(state)
        progress = state.transfer_tick/30
        c = Canvas(self.background, json.dumps(asdict(state), sort_keys=True), transfer_font_px(progress))
        m.header(c)
        f20_handoff(c, progress)
        self.character.draw(c, state.pose)
        c.check_foreground_clearance()
        image = Image.blend(c.image, self.cream, state.cream/255) if state.cream else c.image
        report = {'state': asdict(state), 'components': c.records,
                  'intentional_absences': c.absent, 'scene_data': c.data,
                  'native_layout_tolerance_px': .5,
                  'underlying_layout_passed': all(r['passed'] for r in c.records),
                  'foreground_groups_do_not_overlap': c.data['foreground_groups_do_not_overlap'],
                  'whole_frame_fade': bool(state.cream)}
        return image.convert('RGB'), report


def prepare_timeline(source_top, destination):
    """Create new visual files; the immutable audio-build remains the parent."""
    source_top, destination = Path(source_top), Path(destination)
    old = json.loads(source_top.read_text())
    base = json.loads(previous.checked(old['source_timeline']).read_text())
    for key in previous.UNCHANGED_FIELDS:
        if old[key] != base[key]:
            raise ValueError(f'v002 no longer matches its measured base: {key}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    motion_source = previous.checked(old['character_motion'])
    motion_path = destination.with_name('character-motion.json')
    with motion_path.open('xb') as stream:
        stream.write(motion_source.read_bytes())
    plan = {**old, 'revision_id': 'fibonacci-counting-v003',
            'renderer_implementation': 'tools/render_fibonacci_video_v003.py',
            'character_motion': previous.receipt(motion_path),
            'source_visual_revision': previous.receipt(source_top),
            'renderer_source': previous.receipt(Path(__file__)),
            'mathematics_animation': {'kind': 'explicit-F20-to-F21-pair-type-transition',
                'index': 20, 'copied_values': [4181, 6765],
                'source_size_px': 88, 'settled_size_px': 47,
                'progress': 'The existing transfer_tick/30; transfer_tick=round(smoothstep(clamp((t-start)/(end-start)))*30). No second easing.',
                'font_raster_size': 'round(88+(47-88)*progress)',
                'unchanged': ['all values', 'main result126px', 'English reading32px', 'F labels23px',
                    'movement centers', 'character', 'all voice and lesson cue times'],
                'individual_value_fit': False}}
    previous.previous.save_new(destination, plan)
    for name in ('subtitles.srt', 'english-captions.srt', 'chapters.txt',
                 'youtube-title.txt', 'youtube-description.txt', 'upload-details.txt'):
        source = source_top.parent/name
        if source.exists():
            with (destination.parent/name).open('xb') as stream:
                stream.write(source.read_bytes())
    return plan


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-timeline', type=Path, required=True)
    parser.add_argument('--timeline', type=Path, required=True)
    args = parser.parse_args()
    prepare_timeline(args.source_timeline, args.timeline)
