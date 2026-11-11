"""Check the delivered octal MP4 and sample every displayed count and digit highlight."""

from __future__ import annotations

import argparse
from collections import defaultdict
from fractions import Fraction
from functools import lru_cache
from itertools import groupby
import json
import math
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageChops, ImageDraw, ImageStat

if __package__:
    from .export_octal_delivery import (
        DIGIT_WORDS, SERIES_URL, TITLE, caption_rows, chapter_lines, count_readings, format_srt,
    )
    from .render_binary_video import INK as SIGN_INK, font, text_center
    from .verify_video import sha256_file, verify_video
else:
    from export_octal_delivery import (
        DIGIT_WORDS, SERIES_URL, TITLE, caption_rows, chapter_lines, count_readings, format_srt,
    )
    from render_binary_video import INK as SIGN_INK, font, text_center
    from verify_video import sha256_file, verify_video


FPS = 30
SAMPLE_SIZE = (480, 270)
BYTES_PER_FRAME = SAMPLE_SIZE[0] * SAMPLE_SIZE[1] * 3
DIGIT_CENTERS = (860, 1230, 1600)
DIGIT_BOXES = ((756, 352, 964, 476), (1128, 352, 1332, 476), (1496, 352, 1704, 476))
SIGN_BOX = (156, 700, 460, 800)
SIGN_FILL = '#fff7df'
ACTIVE_FILL = (174, 229, 206)
WORD_FILL = (211, 237, 223)
CREAM_FILL = (255, 248, 232)
INK_THRESHOLD = 137
MINIMUM_GLYPH_IOU = 0.90
LEGACY_LAYOUT = 'legacy'
COMMON_BASELINE = 'common-baseline'
READING_BASELINE = 765
READING_CENTER = 1230
READING_STEP = 170
READING_FIELD_CENTER = 719.5
RANGE_FILL = (226, 243, 230)
WARM_EDGE = (178, 121, 67)
PEACH_FILL = (255, 234, 208)


def first_frame(seconds):
    return math.ceil(seconds * FPS - 1e-7)


def metadata_checks(timeline, delivery_dir, video_filename):
    expected = format_srt(caption_rows(timeline))
    srt = (delivery_dir / 'english-captions.srt').read_text(encoding='utf-8')
    chapters = (delivery_dir / 'chapters.txt').read_text(encoding='utf-8')
    upload = (delivery_dir / 'upload-details.txt').read_text(encoding='utf-8')
    return {
        'english_srt_matches_measured_speech': srt == expected,
        'chapter_timestamps_match_measured_sections': chapters == '\n'.join(chapter_lines(timeline)) + '\n',
        'upload_metadata_matches_delivery': (
            upload.startswith(f'Title\n{TITLE}\n') and SERIES_URL in upload and chapters in upload
            and f'Video: {video_filename}\n' in upload and 'Captions: english-captions.srt (English)\n' in upload
        ),
    }


def scene_samples(timeline):
    readings = count_readings(timeline)
    states = timeline['counted_states']
    if [state['decimal_value'] for state in states] != list(readings):
        raise ValueError('Timeline must present all 128 measured counts in order')
    samples = defaultdict(list)
    last_end = first_frame(timeline['intro']['duration_s'])
    for value, state in enumerate(states):
        digits = format(value, 'o')
        if digits != state['display_octal']:
            raise ValueError(f'Incorrect state text for decimal {value}')
        start = first_frame(state['estimated_display_start_s'])
        stop = first_frame(state['estimated_display_end_s'])
        if start != last_end or start >= stop:
            raise ValueError(f'Count states are not continuous at {digits}')
        last_end = stop
        samples[start].append((value, None, 'state_start'))
        samples[stop - 1].append((value, None, 'state_end'))
        for event in readings[value]:
            begin = first_frame(event['start_s'])
            end = first_frame(event['end_s'])
            slot = event['slot_index']
            if not start < begin < end < stop:
                raise ValueError(f'Digit event falls outside the display interval for {digits}')
            samples[begin - 1].append((value, None, 'before_highlight'))
            samples[begin].append((value, slot, 'highlight_start'))
            samples[end - 1].append((value, slot, 'highlight_end'))
            samples[end].append((value, None, 'after_highlight'))
    if last_end != first_frame(timeline['finale']['estimated_start_s']):
        raise ValueError('Last count does not reach the finale')
    intro_digits = [event for event in timeline['events']
                    if event['type'] == 'digit_voice' and event['phase'] == 'intro']
    if [(event['decimal_value'], event['slot_index'], event['token']) for event in intro_digits] != [
        (10, 1, 'one'), (10, 2, 'two'),
    ]:
        raise ValueError('The intro example requires measured speech for each digit of octal 12')
    for event in intro_digits:
        begin, end = first_frame(event['start_s']), first_frame(event['end_s'])
        samples[begin].append((10, event['slot_index'], 'intro_highlight_start'))
        samples[end - 1].append((10, event['slot_index'], 'intro_highlight_end'))
    return samples


def quarter_box(box):
    return tuple(coordinate // 4 for coordinate in box)


def glyph_mask(image):
    return image.convert('L').point(lambda sample: 255 if sample < INK_THRESHOLD else 0)


def draw_centered_ink(draw, text, center, size, fill):
    face = font(size)
    mask, (origin_x, origin_y) = face.getmask2(text, mode='L')
    left, top, right, bottom = mask.getbbox()
    x = round(center[0] - origin_x - (left + right) / 2)
    y = round(center[1] - origin_y - (top + bottom) / 2)
    draw.text((x, y), text, font=face, fill=fill)


@lru_cache(maxsize=152)
def expected_glyph(value, slot):
    box = SIGN_BOX if slot is None else DIGIT_BOXES[slot]
    size = (box[2] - box[0], box[3] - box[1])
    # Match the decimal sign's colors before downsampling. Black-on-white
    # text would cross the dark-pixel threshold at lower edge coverage.
    patch = Image.new('RGB', size, SIGN_FILL) if slot is None else Image.new('L', size, 255)
    draw = ImageDraw.Draw(patch)
    if slot is None:
        text_center(draw, str(value), (308 - box[0], 752 - box[1]), 112, SIGN_INK)
    elif value != ' ':
        draw_centered_ink(draw, value, (DIGIT_CENTERS[slot] - box[0], 412 - box[1]), 140, 0)
    return glyph_mask(patch.resize((patch.width // 4, patch.height // 4), Image.Resampling.BOX))


def mask_similarity(actual, expected):
    union = ImageChops.lighter(actual, expected).histogram()[255]
    if not union:
        return 1.0
    return ImageChops.darker(actual, expected).histogram()[255] / union


def glyph_similarity(image, value, slot):
    box = SIGN_BOX if slot is None else DIGIT_BOXES[slot]
    return mask_similarity(glyph_mask(image.crop(quarter_box(box))), expected_glyph(value, slot))


def close_to_color(frame, x, y, expected):
    actual = ImageStat.Stat(frame.crop((x - 1, y - 1, x + 2, y + 2))).mean
    return max(abs(channel - wanted) for channel, wanted in zip(actual, expected, strict=True)) <= 12


def close_to_fill(frame, x, y, expected):
    return close_to_color(frame, x // 4, y // 4, expected)


def reading_centers(word_count):
    return [READING_CENTER + (2 * index - word_count + 1) * (READING_STEP // 2)
            for index in range(word_count)]


@lru_cache(maxsize=256)
def word_badge_samples(value, reading_layout=LEGACY_LAYOUT):
    if reading_layout == COMMON_BASELINE:
        # At quarter resolution the 3x3 probe must clear the ink of "seven".
        return [center - 70 for center in reading_centers(len(format(value, 'o')))]
    widths = [round(font(43).getlength(DIGIT_WORDS[int(digit)])) + 42 for digit in format(value, 'o')]
    x = (2460 - sum(widths) - 12 * (len(widths) - 1)) / 2
    samples = []
    for width in widths:
        samples.append(round(x + 12))
        x += width + 12
    return samples


def check_count_frame(frame, value, active_slot, reading_layout=LEGACY_LAYOUT):
    digits = format(value, 'o')
    observed_slots = [slot for slot, x in enumerate((727, 1097, 1467))
                      if close_to_fill(frame, x, 350, ACTIVE_FILL)]
    expected_slots = [] if active_slot is None else [active_slot]
    errors = []
    if observed_slots != expected_slots:
        errors.append(f'slot highlight {observed_slots}, expected {expected_slots}')
    first_slot = 3 - len(digits)
    observed_words = [slot for slot, x in enumerate(word_badge_samples(value, reading_layout), first_slot)
                      if close_to_fill(frame, x, 752, WORD_FILL)]
    if observed_words != expected_slots:
        errors.append(f'word highlight {observed_words}, expected {expected_slots}')
    for slot, digit in enumerate(digits.rjust(3)):
        score = glyph_similarity(frame, digit, slot)
        if score < MINIMUM_GLYPH_IOU:
            errors.append(f'octal glyph {slot} {digit!r} overlap {score:.3f}')
    score = glyph_similarity(frame, value, None)
    if score < MINIMUM_GLYPH_IOU:
        errors.append(f'decimal sign glyph overlap {score:.3f}')
    if reading_layout == COMMON_BASELINE:
        active_ranges = [width for width, x in enumerate((100, 696, 1292), 1)
                         if close_to_fill(frame, x, 975, RANGE_FILL)]
        if active_ranges != [len(digits)]:
            errors.append(f'range badge highlight {active_ranges}, expected {[len(digits)]}')
    return errors


def select_expression(indices):
    runs = []
    for _, group in groupby(enumerate(indices), key=lambda row: row[1] - row[0]):
        first, *rest = (index for _, index in group)
        runs.append(f'between(n\\,{first}\\,{rest[-1]})' if rest else f'eq(n\\,{first})')
    # A long left-associated sum exceeds FFmpeg's expression depth limit.
    while len(runs) > 1:
        paired = [f'({left}+{right})' for left, right in zip(runs[::2], runs[1::2])]
        if len(runs) % 2:
            paired.append(runs[-1])
        runs = paired
    return runs[0]


def decoded_native_frame(video, ffmpeg, index):
    # Seek half a frame early so the exact frame survives timestamp rounding.
    seek = max(0, (index - .5) / FPS)
    result = subprocess.run(
        [str(ffmpeg), '-nostdin', '-v', 'error', '-xerror', '-ss', f'{seek:.9f}', '-i', str(video),
         '-map', '0:v:0', '-an', '-frames:v', '1', '-vf', 'scale=in_color_matrix=bt709,format=rgb24',
         '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'],
        capture_output=True, check=True,
    )
    return Image.frombytes('RGB', (1920, 1080), result.stdout)


def color_bbox(frame, box, color):
    matches = [band.point(lambda value: 255 if abs(value - wanted) <= 12 else 0)
               for band, wanted in zip(frame.crop(box).split(), color, strict=True)]
    bounds = ImageChops.multiply(ImageChops.multiply(matches[0], matches[1]), matches[2]).getbbox()
    return tuple(pos + box[index % 2] for index, pos in enumerate(bounds)) if bounds else None


def native_reading(frame, value, active_ordinal):
    words = [DIGIT_WORDS[int(digit)] for digit in format(value, 'o')]
    label = glyph_mask(frame.crop((1090, 654, 1370, 705))).getbbox()
    errors, results = [], []
    if label is None:
        errors.append('READ ALOUD label is absent')
    bottom = 0
    for index, (word, x) in enumerate(zip(words, reading_centers(len(words)), strict=True)):
        active = index == active_ordinal
        box = (x - 80 - x % 2, 712, x + 80, 784)
        observed = glyph_mask(frame.crop(box))
        bounds = observed.getbbox()
        if bounds is None:
            errors.append(f'{word} has no visible ink')
            continue
        face = font(43)
        mask, (offset_x, _) = face.getmask2(word, mode='L', anchor='ls')
        left, _, right, _ = mask.getbbox()
        expected = Image.new('RGB', observed.size, WORD_FILL if active else CREAM_FILL)
        ImageDraw.Draw(expected).text(
            (round(x - box[0] - offset_x - (left + right) / 2), READING_BASELINE - box[1]),
            word, font=face, anchor='ls', fill='#205b57' if active else '#51341f',
        )
        expected_ink = glyph_mask(expected)
        similarity = mask_similarity(observed, expected_ink)
        x_center = (bounds[0] + bounds[2]) / 2 + box[0]
        y_bottom = bounds[3] + box[1]
        baseline = READING_BASELINE + bounds[3] - expected_ink.getbbox()[3]
        bottom = max(bottom, y_bottom)
        results.append({'word': word, 'center_x_px': x_center, 'baseline_y_px': baseline,
                        'glyph_overlap': round(similarity, 4)})
        if abs(baseline - READING_BASELINE) > 1 or abs(x_center - x) > 2 or similarity < MINIMUM_GLYPH_IOU:
            errors.append(f'{word} position or shape differs (x={x_center}, baseline={baseline}, overlap={similarity:.3f})')
        if active:
            badge = color_bbox(frame, (x - 84, 716, x + 84, 781), WORD_FILL)
            expected_badge = (x - 79, 727, x + 80, 772)
            if badge is None or any(abs(actual - expected) > 2
                                    for actual, expected in zip(badge, expected_badge, strict=True)):
                errors.append(f'{word} badge bounds {badge}, expected {expected_badge}')
            if badge:
                bottom = max(bottom, badge[3])
    center = (654 + label[1] + bottom) / 2 if label and bottom else None
    if center is None or abs(center - READING_FIELD_CENTER) > 2:
        errors.append(f'READ ALOUD block center {center}, expected {READING_FIELD_CENTER} ±2 px')
    baselines = [word['baseline_y_px'] for word in results]
    if baselines and max(baselines) - min(baselines) > 1:
        errors.append(f'READ ALOUD words use different baselines {baselines}')
    return {'words': results, 'block_center_y_px': center, 'errors': errors}


def native_text_matches(frame, text, center, size, box, ink='#51341f'):
    actual = glyph_mask(frame.crop(box))
    fill = frame.getpixel((box[0] + 2, box[1] + 2))
    expected = Image.new('RGB', actual.size, fill)
    draw_centered_ink(ImageDraw.Draw(expected), text, (center[0] - box[0], center[1] - box[1]), size, ink)
    return mask_similarity(actual, glyph_mask(expected)) >= MINIMUM_GLYPH_IOU


def native_range_errors(frame, occupied):
    errors = []
    for width, (x, span) in enumerate(zip((364, 960, 1556), ('0–7', '10–77', '100–177'), strict=True), 1):
        label = '1 digit' if width == 1 else f'{width} digits'
        box = (x - 102, 956, x + 102, 1028)
        observed = glyph_mask(frame.crop(box))
        bounds = observed.getbbox()
        if bounds is None or abs(box[1] + (bounds[1] + bounds[3]) / 2 - 992.5) > 2:
            errors.append(f'{width}-digit range text is not vertically centered')
            continue
        heights = []
        for text, size in ((label, 27), (span, 25)):
            _, top, _, bottom = font(size).getmask2(text, mode='L')[0].getbbox()
            heights.append(bottom - top)
        shift = 992.5 - (975 - heights[0] / 2 + 1010 + heights[1] / 2) / 2
        if not native_text_matches(frame, label, (x, 975 + shift), 27, (x - 102, 956, x + 102, 994),
                                   '#205b57' if width == occupied else '#51341f'):
            errors.append(f'{width}-digit range label differs')
        if not native_text_matches(frame, span, (x, 1010 + shift), 25, (x - 102, 994, x + 102, 1028)):
            errors.append(f'{width}-digit range span {span} differs')
    return errors


def decoded_layout_checks(video, timeline, ffmpeg):
    errors, reading = [], []
    states = timeline['counted_states']
    probes = [(first_frame(states[value]['estimated_display_start_s']), value, None)
              for value in (0, 10, 28, 46, 111)]
    probes.extend((first_frame(digit['estimated_start_s']), 111, digit['ordinal'])
                  for digit in states[111]['digit_highlights'])
    for index, value, active_ordinal in probes:
        frame = decoded_native_frame(video, ffmpeg, index)
        result = native_reading(frame, value, active_ordinal)
        reading.append({'frame': index, 'octal': format(value, 'o'), 'active_ordinal': active_ordinal, **result})
        errors.extend(f'Frame {index}: {error}' for error in result['errors'])
        occupied = len(format(value, 'o'))
        errors.extend(f'Frame {index}: {error}' for error in native_range_errors(frame, occupied))
        for slot, (x, weight) in enumerate(zip(DIGIT_CENTERS, ('64', '8', '1'), strict=True)):
            ink = '#205b57' if slot >= 3 - occupied else '#756352'
            if not native_text_matches(frame, weight, (x, 532), 34, (x - 36, 508, x + 36, 558), ink):
                errors.append(f'Frame {index}: place value {weight} differs')

    events = {event['id']: event for event in timeline['events']}
    inventory = decoded_native_frame(video, ffmpeg, first_frame(events['I03']['start_s']) - 1)
    for digit in range(8):
        x = 754 + 136 * digit
        if not native_text_matches(inventory, str(digit), (x, 480), 92, (x - 52, 436, x + 52, 524)):
            errors.append(f'Opening digit inventory differs at {digit}')

    cue = events['I07']
    cue_probes = ((first_frame(cue['start_s']) - 1, False),
                  (first_frame((cue['start_s'] + cue['end_s']) / 2), True),
                  (first_frame(cue['end_s']), False))
    for index, active in cue_probes:
        frame = decoded_native_frame(video, ffmpeg, index)
        border = close_to_color(frame, 860, 317, WARM_EDGE)
        has_cue = native_text_matches(frame, 'Skip the blank places', (1230, 869), 34, (680, 844, 1780, 893),
                                      '#205b57')
        if border != active or has_cue != active:
            errors.append(f'Frame {index}: opening blank-place cue border/text differ (expected active={active})')

    pauses = {pause['after_decimal_value']: pause for pause in timeline['pauses']}
    for value in (7, 15, 63):
        carry = next(cue for cue in timeline['carry_cues'] if cue['after_decimal_value'] == value)
        start = pauses[value]['estimated_start_s'] if value in (7, 63) else carry['estimated_start_s']
        cut = states[value + 1]['estimated_display_start_s']
        index = first_frame((start + cut) / 2)
        frame = decoded_native_frame(video, ffmpeg, index)
        expression = f'{value:o} + 1  =  {value + 1:o}   (BASE 8)'
        if not native_text_matches(frame, expression, (1230, 869), 34, (680, 844, 1780, 893)):
            errors.append(f'Frame {index}: carry expression {expression} differs')
        if value in (7, 63):
            new_slot = 3 - len(format(value + 1, 'o'))
            if not close_to_color(frame, DIGIT_CENTERS[new_slot], 350, PEACH_FILL):
                errors.append(f'Frame {index}: carry does not mark the new place')

    return {'reading_probes': reading, 'opening_inventory_digits_checked': 8,
            'opening_blank_place_frames_checked': len(cue_probes), 'carry_banners_checked': 3, 'errors': errors}


def visual_checks(video, timeline, ffmpeg, reading_layout=LEGACY_LAYOUT):
    samples = scene_samples(timeline)
    frames = first_frame(timeline['duration_s'])
    finale = timeline['finale']
    fade_start = first_frame(finale['estimated_start_s'] + finale['relative_cream_fade_s'][0])
    sampled_frames = sorted(set(samples) | {0, fade_start - 1, frames - 1})
    # The selected frames are ordered by decode frame index. Downsample only the
    # retained frames and stream them so the decoded pixels never fill a temp drive.
    select = select_expression(sampled_frames)
    filters = f'select={select},scale=480:270:flags=area:in_color_matrix=bt709,format=rgb24'
    command = [str(ffmpeg), '-nostdin', '-hide_banner', '-loglevel', 'error', '-xerror',
               '-i', str(video), '-map', '0:v:0', '-an', '-vf', filters,
               '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1']
    errors = []
    stats = defaultdict(int)
    decoded_samples = 0
    with subprocess.Popen(command, stdout=subprocess.PIPE) as decoder:
        for index in sampled_frames:
            data = decoder.stdout.read(BYTES_PER_FRAME)
            if len(data) != BYTES_PER_FRAME:
                errors.append(f'Decode ended before selected frame {index}')
                break
            decoded_samples += 1
            frame = Image.frombytes('RGB', SAMPLE_SIZE, data)
            if index in (0, frames - 1):
                for point in ((480, 240), (1200, 500), (100, 700), (1810, 1000)):
                    if not close_to_fill(frame, *point, CREAM_FILL):
                        errors.append(f'Fade endpoint frame {index} is not cream at {point}')
            if index == fade_start - 1:
                errors.extend(f'Before fade: {error}' for error in check_count_frame(frame, 127, None, reading_layout))
            for value, active_slot, role in samples.get(index, ()):
                stats[role] += 1
                errors.extend(f'Frame {index}, octal {value:o}, {role}: {error}'
                              for error in check_count_frame(frame, value, active_slot, reading_layout))
        if decoder.stdout.read(1):
            errors.append('Decoder returned an unexpected extra selected frame')
            decoder.stdout.close()
        if decoder.wait() != 0:
            errors.append('Visual frame decode failed')
    native = decoded_layout_checks(video, timeline, ffmpeg) if reading_layout == COMMON_BASELINE else None
    if native:
        errors.extend(native['errors'])
    return {'sampled_frames': decoded_samples, 'planned_samples': len(sampled_frames),
            'checks_by_scene_role': dict(stats), 'reading_layout': reading_layout, 'native_layout': native,
            'all_samples_match': not errors, 'errors': errors}


def check_video_timestamps(video, duration, ffprobe):
    """Check that the video packets cover every frame PTS on a uniform grid."""
    result = subprocess.run(
        [str(ffprobe), '-v', 'error', '-select_streams', 'v:0', '-show_packets',
         '-show_streams', '-show_entries', 'packet=pts,duration:stream=time_base', '-of', 'json', str(video)],
        capture_output=True, check=True, text=True,
    )
    data = json.loads(result.stdout)
    time_base = Fraction(data['streams'][0]['time_base'])
    packets = sorted((int(packet['pts']), int(packet['duration'])) for packet in data['packets'])
    step = Fraction(1, FPS) / time_base
    return (step.denominator == 1 and len(packets) == first_frame(duration)
            and all(pts == index * step and length == step for index, (pts, length) in enumerate(packets)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--delivery-dir', type=Path, help='Caption and chapter directory, defaults to the MP4 directory')
    parser.add_argument('--technical-report', type=Path,
                        help='Reuse passing technical QA for these exact video and timeline files')
    parser.add_argument('--reading-layout', choices=(LEGACY_LAYOUT, COMMON_BASELINE), default=LEGACY_LAYOUT,
                        help='Use common-baseline for the revised word positions and opening cue')
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg'))
    parser.add_argument('--ffprobe', default=shutil.which('ffprobe'))
    args = parser.parse_args()
    timeline = json.loads(args.timeline.read_text(encoding='utf-8-sig'))
    if timeline['fps'] != FPS:
        raise ValueError('Octal delivery requires a 30 fps timeline')
    timeline_sha256 = sha256_file(args.timeline)
    if args.technical_report:
        technical = json.loads(args.technical_report.read_text(encoding='utf-8-sig'))
        if (technical.get('status') != 'pass' or technical.get('sha256') != sha256_file(args.video)
                or (technical.get('timeline') or {}).get('sha256') != timeline_sha256):
            raise ValueError('Technical QA must pass and match the exact video and timeline hashes')
        args.output_dir.mkdir(parents=True, exist_ok=True)
    else:
        technical = verify_video(args.video, args.output_dir, args.timeline, args.ffmpeg, args.ffprobe,
                                 duration_bounds=(1, 900))
    checks = metadata_checks(timeline, args.delivery_dir or args.video.parent, args.video.name)
    checks['exact_video_timestamp_grid'] = check_video_timestamps(args.video, timeline['duration_s'], args.ffprobe)
    visual = visual_checks(args.video, timeline, args.ffmpeg, args.reading_layout)
    checks['all_sampled_count_visuals_match'] = visual['all_samples_match']
    checks['technical_media_report_passes'] = technical['status'] == 'pass'
    report = {'status': 'pass' if all(checks.values()) else 'fail', 'checks': checks, 'visual': visual,
              'video_sha256': technical['sha256'], 'timeline_sha256': timeline_sha256}
    output = args.output_dir / 'octal-final-qa.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(output), 'checks': checks,
                      'visual_failures': len(visual['errors'])}, ensure_ascii=False))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
