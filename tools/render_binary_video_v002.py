"""Render the slower binary revision with a large decimal sign held by the bear.

The accepted character drawings remain unchanged. A code-drawn sign and small
foreground grips cover the original lowered hands, while the face stays clear.
During the seated stretch the sign rests on short feet; during waving the other
paw keeps holding it. The sign's value uses the same current state as the bits.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

try:
    import render_binary_video as original
    from render_counting_video import Segment, encode, find_ffmpeg
except ModuleNotFoundError:
    from tools import render_binary_video as original
    from tools.render_counting_video import Segment, encode, find_ffmpeg

ROOT = original.ROOT
FPS = original.FPS
CREAM = original.CREAM
INK = original.INK
WEIGHTS = original.WEIGHTS
BinaryTimeline = original.BinaryTimeline
font = original.font
file_hash = original.file_hash
text_center = original.text_center
rounded = original.rounded

SIGN_BBOX = (125, 646, 491, 810)
SIGN_VALUE_ROI = (157, 700, 459, 800)
SIGN_VALUE_CENTER = (308, 752)
SIGN_VALUE_FONT_SIZE = 112
SIGN_HEADER_CENTER = (308, 677)
SIGN_HEADER_FONT_SIZE = 26
SIGN_PAW_BBOXES = ((113, 685, 151, 743), (467, 685, 505, 743))
SIGN_GRIP_BBOXES = SIGN_PAW_BBOXES
FACE_SAFE_BBOX = (115, 258, 502, 626)
RESTING_FACE_SAFE_BBOX = (115, 265, 545, 641)
FACE_CLEARANCE_PX = 20


def sign_geometry(pose='neutral'):
    resting = pose in ('half_seated', 'seated_neutral', 'seated_stretch')
    waving = pose.startswith('wave_')
    return {'bbox': list(SIGN_BBOX), 'value_roi': list(SIGN_VALUE_ROI),
            'value_center': list(SIGN_VALUE_CENTER), 'value_font_size': SIGN_VALUE_FONT_SIZE,
            'header_center': list(SIGN_HEADER_CENTER), 'header_font_size': SIGN_HEADER_FONT_SIZE,
            'style': 'resting' if resting else 'one-paw' if waving else 'held',
            'grip_paw_bboxes': [] if resting else [list(SIGN_PAW_BBOXES[0])] if waving else [list(box) for box in SIGN_PAW_BBOXES],
            'face_safe_bbox': list(RESTING_FACE_SAFE_BBOX if resting else FACE_SAFE_BBOX),
            'face_clearance_px': SIGN_BBOX[1]-(RESTING_FACE_SAFE_BBOX if resting else FACE_SAFE_BBOX)[3]}


class DecimalSignScene(original.BinaryScene):
    def pose(self, seconds, state):
        pose = super().pose(seconds, state)
        # Holding the board occupies the lowered paws. Keep the registered
        # stretch and one-paw wave, without adding a third hand to thinking or
        # cheering poses. The original character PNG itself is not changed.
        return 'neutral' if pose in ('think', 'cheer', 'success_ready') else pose

    @staticmethod
    def sign_support(frame, pose):
        if sign_geometry(pose)['style'] != 'resting':
            return
        draw = ImageDraw.Draw(frame)
        # Behind the character: the little feet ground the board during the
        # short stretch, so its value remains visible while both arms rise.
        for x in (192, 414):
            rounded(draw, (x-9, 795, x+9, 879), '#b78b52', '#795125', 4, 5)
            rounded(draw, (x-25, 870, x+25, 884), '#b78b52', '#795125', 3, 5)

    @staticmethod
    def draw_decimal_sign(frame, value, pose):
        if type(value) is not int or not 0 <= value <= 127:
            raise ValueError('The held sign requires the actual current decimal value')
        draw = ImageDraw.Draw(frame)
        # Warm, simple code-native board matching the existing picture-book
        # outlines; no letters or numbers are generated in a bitmap model.
        rounded(draw, (125, 653, 491, 817), '#987447', radius=23)
        rounded(draw, SIGN_BBOX, '#fff7df', '#9a6b38', 7, 23)
        rounded(draw, (135, 656, 481, 800), None, '#ead2a1', 2, 15)
        text_center(draw, 'DECIMAL', SIGN_HEADER_CENTER, SIGN_HEADER_FONT_SIZE, '#80623e')
        draw.line((156, 696, 460, 696), fill='#e5d3ac', width=2)
        text_center(draw, str(value), SIGN_VALUE_CENTER, SIGN_VALUE_FONT_SIZE, INK)
        for index, box in enumerate(sign_geometry(pose)['grip_paw_bboxes']):
            draw.ellipse(box, fill='#fff0b4', outline='#70420e', width=7)
            if index == 0:
                draw.arc((130, 700, 147, 727), 275, 80, fill='#9b6d2a', width=3)
            else:
                draw.arc((471, 700, 488, 727), 100, 265, fill='#9b6d2a', width=3)

    def frame(self, seconds):
        state = self.state(seconds)
        checkpoint = self.timeline.active('checkpoint', seconds)
        carry = state['carry']
        pose = self.pose(seconds, state)
        intro_alpha = min(1, max(0, seconds/.8))
        fade_start = float(self.timeline.plan.get('fade_out_start_s', self.duration-2))
        fade_length = self.duration-fade_start
        if fade_length <= 0:
            raise ValueError('Fade-out must begin before the timeline ends')
        alpha = min(intro_alpha, min(1, max(0, (self.duration-seconds)/fade_length)))
        motion = round(seconds*FPS) if checkpoint or carry or state['mode']=='place' or alpha<1 else None
        key = (state['number'], state['focus'], state['mode'], pose, motion)
        if key == self._last_key:
            return self._last_frame
        frame = self.composition(state['number'], state['focus'], state['mode']).copy()
        self.checkpoint_effect(frame, checkpoint, seconds)
        if carry:
            self.carry_strip(frame, carry, seconds)
        elif state['mode'] == 'place':
            pause = state['pause']
            source = int(pause['after_decimal_value'])
            comparison = {'from_decimal':source,'to_decimal':source+1,
                          'start_s':pause['start_s'],'end_s':pause['end_s']}
            self.carry_strip(frame, comparison, seconds)
        self.sign_support(frame, pose)
        self.bear.draw(frame, [(pose, 1)])
        self.draw_decimal_sign(frame, state['number'], pose)
        if alpha < 1:
            frame = Image.blend(self.cream, frame, alpha)
        self._last_key, self._last_frame = key, frame
        return frame


# The alias lets independent verification select this revision without changing
# any of its common binary-slot checks or the old renderer implementation.
BinaryScene = DecimalSignScene


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline',type=Path,required=True)
    parser.add_argument('--audio',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--preset',default='veryfast')
    parser.add_argument('--crf',type=int,default=18)
    parser.add_argument('--ffmpeg')
    parser.add_argument('--frames-dir',type=Path)
    parser.add_argument('--contact-sheet',type=Path)
    parser.add_argument('--sample-reel',action='store_true')
    args = parser.parse_args()
    if not any((args.output,args.frames_dir,args.contact_sheet)):
        parser.error('Provide --output, --frames-dir or --contact-sheet')
    for target in (args.output,args.frames_dir,args.contact_sheet):
        if target and target.exists():
            raise ValueError(f'Refusing to overwrite existing artifact: {target}')
    timeline = BinaryTimeline(json.loads(args.timeline.read_text(encoding='utf-8-sig')))
    scene = DecimalSignScene(timeline)
    records = original.previews(scene,args.frames_dir,args.contact_sheet) if args.frames_dir or args.contact_sheet else []
    if not args.output:
        print(json.dumps({'preview_frames':len(records),'duration_s':scene.duration,'decimal_sign':sign_geometry()}),flush=True)
        return
    if args.sample_reel:
        segments = [Segment(max(0,t-.4),min(1.6,scene.duration-max(0,t-.4)),label) for label,t in scene.sample_times()]
    else:
        if not args.audio or not args.audio.is_file():
            raise ValueError('Full binary movie requires the measured final master WAV')
        segments = [Segment(0,scene.duration,'slower binary counting with decimal sign 0–127')]
    report = encode(scene,segments,args.output,find_ffmpeg(args.ffmpeg),None if args.sample_reel else args.audio,args.crf,args.preset)
    report.update({'timeline':str(args.timeline),'timeline_sha256':file_hash(args.timeline),
                   'renderer':'tools/render_binary_video_v002.py','renderer_sha256':file_hash(__file__),
                   'base_binary_renderer_sha256':file_hash(ROOT/'tools/render_binary_video.py'),
                   'shared_encoder_and_bear_sha256':file_hash(ROOT/'tools/render_counting_video.py'),
                   'source_assets':original.source_receipts(),
                   'audio_sha256':file_hash(args.audio) if args.audio and not args.sample_reel else None,
                   'synthetic_timing':False,'sample_reel':args.sample_reel,
                   'counted_states':128,'spoken_bit_words':sum(len(row['bit_events']) for row in timeline.counts),
                   'decimal_sign':sign_geometry(),
                   'decimal_sign_state_source':'Same current count state as the binary main display; intro example2; holds during pause/finale.',
                   'decimal_sign_artwork':'Original code-native board and foreground paw grips; unchanged canonical character behind.',
                   'layout':{'bit_grid_xywh':[650,330,1160,234],'cell_gap_px':14,
                             'digit_visible_ink_center_y':426,'digit_font_size':116,
                             'place_weights_y':529,'slot_order':list(WEIGHTS)}})
    args.output.with_suffix('.render.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':
    main()
