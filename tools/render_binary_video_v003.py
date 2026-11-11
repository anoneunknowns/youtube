"""Render the clear-pause revision with measured, vertically centered text groups."""
from __future__ import annotations

import argparse
from functools import lru_cache
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

try:
    import render_binary_video_v002 as previous
    from render_counting_video import Segment, encode, find_ffmpeg
except ModuleNotFoundError:
    from tools import render_binary_video_v002 as previous
    from tools.render_counting_video import Segment, encode, find_ffmpeg

ROOT = previous.ROOT
FPS = previous.FPS
CREAM = previous.CREAM
INK = previous.INK
BinaryTimeline = previous.BinaryTimeline
font = previous.font
file_hash = previous.file_hash
text_center = previous.text_center
rounded = previous.rounded
SIGN_BBOX = previous.SIGN_BBOX
SIGN_VALUE_ROI = previous.SIGN_VALUE_ROI
SIGN_VALUE_CENTER = previous.SIGN_VALUE_CENTER
SIGN_VALUE_FONT_SIZE = previous.SIGN_VALUE_FONT_SIZE
SIGN_GRIP_BBOXES = previous.SIGN_GRIP_BBOXES
sign_geometry = previous.sign_geometry

MAIN_CONTENT_BOX = (658, 622, 1802, 798)
CARRY_CONTENT_BOX = (670, 823, 1790, 893)
RANGE_CARD_TOP = 935
RANGE_CARD_BOTTOM = 1046
RANGE_CARD_WIDTH = (1772 - 18 * 6) / 7


def transparent_layer():
    return Image.new('RGBA', (1920, 1080))


def group_alignment(layer, field):
    """Use actual alpha ink bounds, including each line, rather than font height."""
    # Ignore nearly transparent antialias fringes. The half-coverage ink bounds
    # agree with the independent dark-ink masks measured from decoded RGB.
    bounds = layer.getchannel('A').point(lambda value: 255 if value >= 128 else 0).getbbox()
    if bounds is None:
        raise ValueError('A centered content group must contain visible ink')
    center = (bounds[1] + bounds[3]) / 2
    target = (field[1] + field[3]) / 2
    shift = math.floor(target - center + .5)
    shifted = [bounds[0], bounds[1] + shift, bounds[2], bounds[3] + shift]
    return {'content_box': list(field), 'target_center_y': target,
            'before_ink_bbox': list(bounds), 'before_ink_center_y': center,
            'before_center_delta_px': center - target, 'shift_y_px': shift,
            'after_ink_bbox': shifted, 'after_ink_center_y': center + shift,
            'after_center_delta_px': center + shift - target,
            'bbox_convention': 'Half-open raster bounds at alpha>=128; center=(top+bottom)/2.'}


def main_text_layer(number, focus, mode):
    layer = transparent_layer()
    draw = ImageDraw.Draw(layer)
    label = 'EVERYDAY NUMBER · DECIMAL' if mode == 'intro' else 'DECIMAL'
    label_width = draw.textlength(label, font=font(27))
    value_width = draw.textlength(str(number), font=font(49))
    total = label_width + 20 + value_width
    text_center(draw, label, (1230 - total / 2 + label_width / 2, 671), 27, '#806c55')
    text_center(draw, str(number), (1230 + total / 2 - value_width / 2, 671), 49)
    tokens = ['one' if bit == '1' else 'zero' for bit in format(number, 'b')]
    highlights = []
    if mode == 'stretch':
        text_center(draw, "Let's stretch!", (1230, 745), 32)
    else:
        widths = [draw.textlength(token, font=font(32)) + 12 for token in tokens]
        total = sum(widths) + 9 * (len(tokens) - 1) + 70
        x = 1230 - total / 2
        text_center(draw, 'Say:', (x + 28, 745), 28, '#826a53')
        x += 70
        for index, (token, width) in enumerate(zip(tokens, widths)):
            if index == focus:
                highlights.append((x, 718, x + width, 772))
            text_center(draw, token, (x + width / 2, 745), 32,
                        '#236575' if index == focus else INK)
            x += width + 9
    return layer, highlights


def range_text_layer(index, active):
    layer = transparent_layer()
    draw = ImageDraw.Draw(layer)
    x = 74 + index * (RANGE_CARD_WIDTH + 18)
    text_center(draw, f'{index + 1} {"digit" if index == 0 else "digits"}',
                (x + RANGE_CARD_WIDTH / 2, 971), 28, '#286a73' if active else '#6a526d')
    text_center(draw, previous.original.RANGES[index], (x + RANGE_CARD_WIDTH / 2, 1010),
                22, '#6c4f32')
    return layer


def carry_text_layer(carry, seconds):
    layer = transparent_layer()
    draw = ImageDraw.Draw(layer)
    source = carry.get('from_binary', format(carry['from_decimal'], 'b'))
    target = carry.get('to_binary', format(carry['to_decimal'], 'b'))
    label = f'{source} + 1 → {target}'
    size = previous.original.fit_size(draw, label, 33, 1060)
    text_center(draw, label, (1230, 844), size)
    steps = min(7, len(source) + 1)
    progress = (seconds - carry['start_s']) / (carry['end_s'] - carry['start_s'])
    active = min(steps - 1, int(progress * steps))
    for index in range(steps):
        x = 1305 - index * 25
        draw.ellipse((x - 5, 875, x + 5, 885),
                     fill=previous.original.TEAL if index == active else '#d9d1bd')
    return layer


def alignment_layout(number=7, focus=None, mode='place', carry=None):
    main, _ = main_text_layer(number, focus, mode)
    rows = []
    for index in range(7):
        x = 74 + index * (RANGE_CARD_WIDTH + 18)
        layer = range_text_layer(index, index + 1 == len(format(number, 'b')))
        rows.append(dict(index=index, **group_alignment(layer, (x, 935, x + RANGE_CARD_WIDTH, 1046))))
    if carry is None:
        carry = {'from_decimal': 7, 'to_decimal': 8, 'start_s': 0, 'end_s': 1}
    carry_layer = carry_text_layer(carry, (carry['start_s'] + carry['end_s']) / 2)
    return {'main_lower_content': group_alignment(main, MAIN_CONTENT_BOX),
            'carry_title_and_markers': group_alignment(carry_layer, CARRY_CONTENT_BOX),
            'range_cards': rows,
            'alignment_mode': 'Visible raster ink bounds of each complete multiline content group.'}


class CenteredDecimalSignScene(previous.DecimalSignScene):
    @lru_cache(maxsize=20)
    def composition(self, number, focus, mode):
        frame = super().composition(number, focus, mode).copy()
        draw = ImageDraw.Draw(frame)
        # Erase only the lower text and its focus background. The separator,
        # rounded board border, numeric cells and registered artwork stay intact.
        draw.rectangle((650, 634, 1810, 784), fill='#fff8ea')
        layer, highlights = main_text_layer(number, focus, mode)
        audit = group_alignment(layer, MAIN_CONTENT_BOX)
        shift = audit['shift_y_px']
        for x1, y1, x2, y2 in highlights:
            rounded(draw, (x1, y1 + shift, x2, y2 + shift), '#d5edeb', radius=12)
            draw.line((x1 + 7, y2 - 4 + shift, x2 - 7, y2 - 4 + shift), fill='#64a9af', width=4)
        frame.paste(layer, (0, shift), layer)
        for index in range(7):
            x = 74 + index * (RANGE_CARD_WIDTH + 18)
            active = index + 1 == len(format(number, 'b'))
            rounded(draw, (x, 941, x + RANGE_CARD_WIDTH, 1052), '#bdb2b8', radius=24)
            rounded(draw, (x, 935, x + RANGE_CARD_WIDTH, 1046), '#fff1bd' if active else '#fff8ee',
                    '#337f88' if active else '#a695b6', 5 if active else 3, 24)
            if active:
                rounded(draw, (x + RANGE_CARD_WIDTH / 2 - 18, 935,
                               x + RANGE_CARD_WIDTH / 2 + 18, 941), previous.original.TEAL, radius=3)
            text = range_text_layer(index, active)
            audit = group_alignment(text, (x, 935, x + RANGE_CARD_WIDTH, 1046))
            frame.paste(text, (0, audit['shift_y_px']), text)
        return frame

    def carry_strip(self, frame, carry, seconds):
        draw = ImageDraw.Draw(frame)
        rounded(draw, CARRY_CONTENT_BOX, '#fffaf0', '#c4b89c', 2, 22)
        layer = carry_text_layer(carry, seconds)
        audit = group_alignment(layer, CARRY_CONTENT_BOX)
        frame.paste(layer, (0, audit['shift_y_px']), layer)


BinaryScene = CenteredDecimalSignScene
DecimalSignScene = CenteredDecimalSignScene


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--audio', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--preset', default='veryfast')
    parser.add_argument('--crf', type=int, default=18)
    parser.add_argument('--ffmpeg')
    parser.add_argument('--frames-dir', type=Path)
    parser.add_argument('--contact-sheet', type=Path)
    parser.add_argument('--alignment-audit', type=Path)
    parser.add_argument('--sample-reel', action='store_true')
    args = parser.parse_args()
    if not any((args.output, args.frames_dir, args.contact_sheet, args.alignment_audit)):
        parser.error('Provide an output, previews or an alignment audit')
    for target in (args.output, args.frames_dir, args.contact_sheet, args.alignment_audit):
        if target and target.exists():
            raise ValueError(f'Refusing to overwrite artifact: {target}')
    timeline = BinaryTimeline(json.loads(args.timeline.read_text(encoding='utf-8-sig')))
    scene = BinaryScene(timeline)
    records = previous.original.previews(scene, args.frames_dir, args.contact_sheet) if args.frames_dir or args.contact_sheet else []
    if args.alignment_audit:
        args.alignment_audit.parent.mkdir(parents=True, exist_ok=True)
        args.alignment_audit.write_text(json.dumps(alignment_layout(), indent=2) + '\n', encoding='utf-8')
    if not args.output:
        print(json.dumps({'preview_frames': len(records), 'duration_s': scene.duration,
                          'alignment': alignment_layout()}, indent=2), flush=True)
        return
    if args.sample_reel:
        segments = [Segment(max(0, t - .4), min(1.6, scene.duration - max(0, t - .4)), label)
                    for label, t in scene.sample_times()]
    else:
        if not args.audio or not args.audio.is_file():
            raise ValueError('The full movie requires the measured master WAV')
        segments = [Segment(0, scene.duration, 'clear-paused centered binary count 0–127')]
    report = encode(scene, segments, args.output, find_ffmpeg(args.ffmpeg),
                    None if args.sample_reel else args.audio, args.crf, args.preset)
    report.update({'timeline': str(args.timeline), 'timeline_sha256': file_hash(args.timeline),
                   'renderer': 'tools/render_binary_video_v003.py', 'renderer_sha256': file_hash(__file__),
                   'base_decimal_renderer_sha256': file_hash(ROOT / 'tools/render_binary_video_v002.py'),
                   'base_binary_renderer_sha256': file_hash(ROOT / 'tools/render_binary_video.py'),
                   'shared_encoder_and_bear_sha256': file_hash(ROOT / 'tools/render_counting_video.py'),
                   'source_assets': previous.original.source_receipts(),
                   'audio_sha256': file_hash(args.audio) if args.audio and not args.sample_reel else None,
                   'synthetic_timing': False, 'sample_reel': args.sample_reel,
                   'counted_states': 128, 'spoken_bit_words': sum(len(row['bit_events']) for row in timeline.counts),
                   'decimal_sign': sign_geometry(), 'alignment': alignment_layout(),
                   'layout': {'bit_grid_xywh': [650, 330, 1160, 234], 'cell_gap_px': 14,
                              'digit_visible_ink_center_y': 426, 'digit_font_size': 116,
                              'place_weights_y': 529, 'slot_order': list(previous.WEIGHTS)}})
    args.output.with_suffix('.render.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
