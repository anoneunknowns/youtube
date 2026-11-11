"""Verify the final hexadecimal movie, captions, count states and symbol highlights."""

from __future__ import annotations

import argparse
from collections import defaultdict
from functools import lru_cache
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageOps, ImageStat

if __package__:
    from . import export_hexadecimal_delivery as delivery
    from . import verify_octal_video as shared
else:
    import export_hexadecimal_delivery as delivery
    import verify_octal_video as shared


FPS = 30
SLOT_CENTERS = (990, 1470)
# Align the source crop to the quarter-resolution decoder's pixel grid.
SYMBOL_BOXES = ((888, 352, 1092, 476), (1368, 352, 1572, 476))
BASELINE = 751
CREAM = '#fff8e8'
INK = '#51341f'
TEAL = '#205b57'
ACTIVE_FILL = '#aee5ce'
USED_FILL = '#e5f2df'
WORD_FILL = (211, 237, 223)
GLYPH_IOU = .90


def metadata_checks(timeline, directory, video_name):
    srt = (directory / 'english-captions.srt').read_text(encoding='utf-8')
    chapters = (directory / 'chapters.txt').read_text(encoding='utf-8')
    upload = (directory / 'upload-details.txt').read_text(encoding='utf-8')
    return {
        'english_srt_matches_measured_speech': srt == delivery.format_srt(delivery.caption_rows(timeline)),
        'chapter_times_match_measured_sections': chapters == '\n'.join(delivery.chapter_lines(timeline)) + '\n',
        'upload_metadata_matches_delivery': (
            upload.startswith(f'Title\n{delivery.TITLE}\n') and delivery.SERIES_URL in upload and chapters in upload
            and f'Video: {video_name}\n' in upload and 'Captions: english-captions.srt (English)\n' in upload
        ),
    }


def scene_samples(timeline):
    readings = delivery.count_readings(timeline)
    states = timeline['counted_states']
    if [row['decimal_value'] for row in states] != list(range(128)):
        raise ValueError('Display states must cover values 0 through 127 in order')
    samples = defaultdict(list)
    previous_end = shared.first_frame(timeline['intro']['duration_s'])
    for value, state in enumerate(states):
        if state['display_hexadecimal'] != format(value, 'X'):
            raise ValueError(f'Incorrect displayed hexadecimal value for {value}')
        begin = shared.first_frame(state['estimated_display_start_s'])
        end = shared.first_frame(state['estimated_display_end_s'])
        if begin != previous_end or begin >= end:
            raise ValueError(f'Non-contiguous display interval at decimal {value}')
        previous_end = end
        samples[begin].append((value, None, 'state_start'))
        samples[end - 1].append((value, None, 'state_end'))
        for event in readings[value]:
            start, stop = shared.first_frame(event['start_s']), shared.first_frame(event['end_s'])
            if not begin < start < stop < end:
                raise ValueError(f'Symbol speech exceeds its display interval at decimal {value}')
            slot = event['slot_index']
            samples[start - 1].append((value, None, 'before_highlight'))
            samples[start].append((value, slot, 'highlight_start'))
            samples[stop - 1].append((value, slot, 'highlight_end'))
            samples[stop].append((value, None, 'after_highlight'))
    if previous_end != shared.first_frame(timeline['finale']['estimated_start_s']):
        raise ValueError('Final count does not reach the finale')
    example = [event for event in timeline['events']
               if event['type'] == 'digit_voice' and event['phase'] == 'intro']
    if [(event['decimal_value'], event['slot_index'], event['token']) for event in example] != [(26, 0, 'one'), (26, 1, 'A')]:
        raise ValueError('The intro must demonstrate one A in left-to-right order')
    for event in example:
        samples[shared.first_frame(event['start_s'])].append((26, event['slot_index'], 'intro_highlight_start'))
        samples[shared.first_frame(event['end_s']) - 1].append((26, event['slot_index'], 'intro_highlight_end'))
    return samples


@lru_cache(maxsize=64)
def expected_symbol(symbol, slot, active):
    box = SYMBOL_BOXES[slot]
    patch = Image.new('RGB', (box[2] - box[0], box[3] - box[1]), ACTIVE_FILL if active else USED_FILL)
    if symbol != ' ':
        shared.draw_centered_ink(ImageDraw.Draw(patch), symbol, (SLOT_CENTERS[slot] - box[0], 412 - box[1]), 144, INK)
    return shared.glyph_mask(patch.resize((patch.width // 4, patch.height // 4), Image.Resampling.BOX))


def check_count_frame(frame, value, active_slot):
    symbols = format(value, 'X')
    expected_slots = [] if active_slot is None else [active_slot]
    errors = []
    actual_slots = [index for index, x in enumerate((805, 1285))
                    if shared.close_to_fill(frame, x, 350, (174, 229, 206))]
    if actual_slots != expected_slots:
        errors.append(f'symbol highlight {actual_slots}, expected {expected_slots}')
    centers = shared.reading_centers(len(symbols))
    # The 3x3 quarter-resolution probe must fit entirely between the badge edge
    # and the widest word's ink. At the second center its native footprint is
    # x1240..1251, clear of the leading 's' in 'seven' at x1254.
    actual_words = [index for index, center in enumerate(centers, 2 - len(symbols))
                    if shared.close_to_fill(frame, center - 70, 740, WORD_FILL)]
    if actual_words != expected_slots:
        errors.append(f'word highlight {actual_words}, expected {expected_slots}')
    for slot, symbol in enumerate(symbols.rjust(2)):
        observed = shared.glyph_mask(frame.crop(shared.quarter_box(SYMBOL_BOXES[slot])))
        score = shared.mask_similarity(observed, expected_symbol(symbol, slot, slot == active_slot))
        if score < GLYPH_IOU:
            errors.append(f'symbol {slot} {symbol!r} overlap {score:.3f}')
    score = shared.glyph_similarity(frame, value, None)
    if score < GLYPH_IOU:
        errors.append(f'decimal sign overlap {score:.3f}')
    selected = [width for width, x in enumerate((100, 994), 1)
                if shared.close_to_fill(frame, x, 975, shared.RANGE_FILL)]
    if selected != [len(symbols)]:
        errors.append(f'range badge highlight {selected}, expected {[len(symbols)]}')
    return errors


def native_reading(frame, value, active_ordinal):
    symbols = format(value, 'X')
    results, errors = [], []
    for index, (symbol, center) in enumerate(zip(symbols, shared.reading_centers(len(symbols)), strict=True)):
        token = delivery.TOKENS[int(symbol, 16)]
        active = index == active_ordinal
        box = (center - 80 - center % 2, 700, center + 80, 778)
        observed = shared.glyph_mask(frame.crop(box))
        bounds = observed.getbbox()
        if bounds is None:
            errors.append(f'{token} is absent')
            continue
        expected = Image.new('RGB', observed.size, WORD_FILL if active else CREAM)
        face = shared.font(43)
        mask, (offset, _) = face.getmask2(token, mode='L', anchor='ls')
        left, _, right, _ = mask.getbbox()
        ImageDraw.Draw(expected).text((round(center - box[0] - offset - (left + right) / 2), BASELINE - box[1]),
                                      token, font=face, anchor='ls', fill=TEAL if active else INK)
        reference = shared.glyph_mask(expected)
        baseline = BASELINE + bounds[3] - reference.getbbox()[3]
        x_center = box[0] + (bounds[0] + bounds[2]) / 2
        overlap = shared.mask_similarity(observed, reference)
        record = {'token': token, 'baseline_y_px': baseline, 'center_x_px': x_center,
                  'glyph_overlap': round(overlap, 4)}
        if abs(baseline - BASELINE) > 1 or abs(x_center - center) > 2 or overlap < GLYPH_IOU:
            errors.append(f'{token} position or shape differs ({record})')
        if active:
            badge = shared.color_bbox(frame, (center - 84, 704, center + 84, 776), WORD_FILL)
            expected_badge = (center - 79, 712, center + 80, 769)
            if badge is None or any(abs(actual - wanted) > 2 for actual, wanted in zip(badge, expected_badge, strict=True)):
                errors.append(f'{token} badge bounds {badge}, expected {expected_badge}')
            if badge:
                padding = [bounds[1] + box[1] - badge[1], badge[3] - bounds[3] - box[1]]
                record['badge_vertical_padding_px'] = padding
                if min(padding) < 4:
                    errors.append(f'{token} does not fit the badge with four pixels of clear padding')
        results.append(record)
    return {'tokens': results, 'errors': errors}


def native_range_errors(frame, occupied):
    errors = []
    for width, (center, span) in enumerate(zip((513, 1407), ('0–F', '10–7F'), strict=True), 1):
        label = '1 digit' if width == 1 else '2 digits'
        heights = []
        for text, size in ((label, 27), (span, 25)):
            _, top, _, bottom = shared.font(size).getmask2(text, mode='L')[0].getbbox()
            heights.append(bottom - top)
        shift = 992.5 - (975 - heights[0] / 2 + 1010 + heights[1] / 2) / 2
        ink = TEAL if width == occupied else INK
        if not shared.native_text_matches(frame, label, (center, 975 + shift), 27,
                                          (center - 103, 956, center + 103, 994), ink):
            errors.append(f'{width}-digit range label differs')
        if not shared.native_text_matches(frame, span, (center, 1010 + shift), 25,
                                          (center - 103, 994, center + 103, 1028)):
            errors.append(f'{width}-digit range {span} differs')
    return errors


def native_layout_checks(video, timeline, ffmpeg):
    states = timeline['counted_states']
    probes = [(shared.first_frame(states[value]['estimated_display_start_s']), value, None) for value in range(16)]
    probes += [(shared.first_frame(states[value]['digit_highlights'][0]['estimated_start_s']), value, 0) for value in range(16)]
    probes += [(shared.first_frame(states[value]['estimated_display_start_s']), value, None) for value in (23, 26, 104, 127)]
    probes += [(shared.first_frame(digit['estimated_start_s']), value, digit['ordinal'])
               for value in (23, 104) for digit in states[value]['digit_highlights']]
    observations, errors = [], []
    for index, value, active in probes:
        frame = shared.decoded_native_frame(video, ffmpeg, index)
        reading = native_reading(frame, value, active)
        observations.append({'frame': index, 'hexadecimal': format(value, 'X'), 'active_ordinal': active, **reading})
        errors.extend(f'Frame {index}: {error}' for error in reading['errors'])
        errors.extend(f'Frame {index}: {error}' for error in native_range_errors(frame, len(format(value, 'X'))))
        for slot, (center, weight) in enumerate(zip(SLOT_CENTERS, ('16', '1'), strict=True)):
            ink = TEAL if slot >= 2 - len(format(value, 'X')) else '#756352'
            if not shared.native_text_matches(frame, weight, (center, 532), 34,
                                              (center - 36, 508, center + 36, 558), ink):
                errors.append(f'Frame {index}: place weight {weight} differs')
    scenes = native_scene_checks(video, timeline, ffmpeg)
    errors.extend(scenes['errors'])
    return {'reading_probes': observations, 'distinct_symbol_tokens_checked': len(delivery.TOKENS),
            'scene_checks': scenes, 'errors': errors}


def native_scene_checks(video, timeline, ffmpeg):
    events = {event['id']: event for event in timeline['events']}
    errors = []
    inventory_index = shared.first_frame(events['I03A']['start_s']) - 1
    inventory = shared.decoded_native_frame(video, ffmpeg, inventory_index)
    for index, symbol in enumerate(delivery.SYMBOLS):
        numeric = index < 10
        x = 735 + 110 * index if numeric else 805 + 170 * (index - 10)
        y = 437.5 if numeric else 617.5
        top = 394 if numeric else 574
        if not shared.native_text_matches(inventory, symbol, (x, y), 65,
                                          (x - 42 - x % 2, top, x + 42, top + 88)):
            errors.append(f'Opening inventory {symbol} differs')
    for index, letter in enumerate('ABCDEF'):
        cue = events[f'I03{letter}']
        at = shared.first_frame((cue['start_s'] + cue['end_s']) / 2)
        frame = shared.decoded_native_frame(video, ffmpeg, at)
        if not shared.native_text_matches(frame, letter, (1470, 412), 144, SYMBOL_BOXES[1]):
            errors.append(f'Letter mapping {letter} has the wrong main symbol')
        sign_score = shared.glyph_similarity(frame.resize(shared.SAMPLE_SIZE, Image.Resampling.BOX), index + 10, None)
        if sign_score < GLYPH_IOU:
            errors.append(f'Letter mapping {letter} has the wrong decimal sign')
        for entry, symbol in enumerate('ABCDEF'):
            x = 215 + 298 * entry
            ink = TEAL if entry == index else INK
            if not shared.native_text_matches(frame, symbol, (x, 974), 30, (x - 60 - x % 2, 952, x + 60, 994), ink):
                errors.append(f'Letter mapping table symbol {symbol} differs')
            if not shared.native_text_matches(frame, str(10 + entry), (x, 1010), 27,
                                              (x - 60 - x % 2, 994, x + 60, 1032)):
                errors.append(f'Letter mapping table value {10 + entry} differs')
            selected = shared.close_to_color(frame, x - 112, 975, shared.RANGE_FILL)
            if selected != (entry == index):
                errors.append(f'Letter mapping table highlight differs at {letter}/{symbol}')

    blank = events['I08']
    blank_probes = ((shared.first_frame(blank['start_s']) - 1, False),
                    (shared.first_frame((blank['start_s'] + blank['end_s']) / 2), True),
                    (shared.first_frame(blank['end_s']), False))
    for at, active in blank_probes:
        frame = shared.decoded_native_frame(video, ffmpeg, at)
        if shared.close_to_color(frame, 990, 317, shared.WARM_EDGE) != active:
            errors.append(f'Opening blank-slot border differs at frame {at}')

    weight_checks = []
    introduction = events['I07']
    length = introduction['end_s'] - introduction['start_s']
    weight_checks.extend((shared.first_frame(introduction['start_s'] + length * fraction), slot, 'intro')
                         for fraction, slot in ((.25, 1), (.75, 0)))
    pause = next(pause for pause in timeline['pauses'] if pause['after_decimal_value'] == 63)
    if pause['kind'] != 'place-value-check' or pause['duration_s'] != 8:
        raise ValueError('The 3F pause must be an eight-second place-value check')
    weight_checks.extend((shared.first_frame(pause['estimated_start_s'] + offset), slot, 'place_check')
                         for offset, slot in ((.1, None), (1.5, 0), (4.5, 1), (6.0, None), (7.8, None)))
    for at, slot, phase in weight_checks:
        frame = shared.decoded_native_frame(video, ffmpeg, at)
        observed = [position for position, x in enumerate(SLOT_CENTERS)
                    if shared.close_to_color(frame, x - 32, 510, WORD_FILL)]
        expected = [] if slot is None else [slot]
        if observed != expected:
            errors.append(f'Weight focus at frame {at} is {observed}, expected {expected}')
        if phase == 'place_check':
            if not shared.native_text_matches(frame, '3 × 16 + 15 = 63', (1230, 869), 34,
                                              (680, 844, 1780, 894), TEAL):
                errors.append(f'Place-value equation differs at frame {at}')
            sign_score = shared.glyph_similarity(frame.resize(shared.SAMPLE_SIZE, Image.Resampling.BOX), 63, None)
            if sign_score < GLYPH_IOU:
                errors.append(f'Place-value check sign differs at frame {at}')

    states = timeline['counted_states']
    comparisons = {row['after_decimal_value']: row['estimated_start_s']
                   for row in timeline['pauses'] if row['kind'] == 'new-place-comparison'}
    carries = [cue for cue in timeline['carry_cues'] if cue['after_decimal_value'] != 63]
    for carry in carries:
        value = carry['after_decimal_value']
        start = comparisons.get(value, carry['estimated_start_s'])
        cut = states[value + 1]['estimated_display_start_s']
        at = shared.first_frame((start + cut) / 2)
        frame = shared.decoded_native_frame(video, ffmpeg, at)
        text = f'{value:X} + 1  =  {value + 1:X}   (BASE 16)'
        if not shared.native_text_matches(frame, text, (1230, 869), 34, (680, 844, 1780, 894)):
            errors.append(f'Carry equation {text} differs at frame {at}')
        if value == 15 and not shared.close_to_color(frame, 990, 350, shared.PEACH_FILL):
            errors.append('First carry does not mark the new sixteens place')

    # The place check leads directly into 40, without a brief redundant carry strip.
    omitted = next(cue for cue in timeline['carry_cues'] if cue['after_decimal_value'] == 63)
    normal_probes = range(shared.first_frame(states[64]['estimated_display_start_s']),
                          shared.first_frame(omitted['estimated_end_s']) + 1)
    background_path = (Path(__file__).resolve().parents[1]
                       / 'assets/library/worlds/starry-observatory/backgrounds/v001/starry-observatory-background.png')
    with Image.open(background_path) as source:
        background = ImageOps.fit(source.convert('RGB'), (1920, 1080), Image.Resampling.LANCZOS)
    strip_samples = [(x, y) for x in (700, 1000, 1230, 1500, 1760) for y in (850, 870, 890)]
    for at in normal_probes:
        frame = shared.decoded_native_frame(video, ffmpeg, at)
        for x, y in strip_samples:
            expected = ImageStat.Stat(background.crop((x - 1, y - 1, x + 2, y + 2))).mean
            if not shared.close_to_color(frame, x, y, expected):
                errors.append(f'Unexpected strip after the place check at frame {at}')
                break
        for slot, symbol in enumerate('40'):
            if not shared.native_text_matches(frame, symbol, (SLOT_CENTERS[slot], 412), 144,
                                              SYMBOL_BOXES[slot]):
                errors.append(f'Post-check hexadecimal 40 differs at frame {at}')
        if shared.glyph_similarity(frame.resize(shared.SAMPLE_SIZE, Image.Resampling.BOX), 64, None) < GLYPH_IOU:
            errors.append(f'Post-check decimal 64 differs at frame {at}')
    return {'inventory_symbols_checked': 16, 'letter_mappings_checked': 6,
            'blank_slot_frames_checked': len(blank_probes), 'weight_focus_frames_checked': len(weight_checks),
            'carry_equations_checked': len(carries), 'post_check_frames_checked': len(normal_probes),
            'errors': errors}


def visual_checks(video, timeline, ffmpeg):
    samples = scene_samples(timeline)
    total = shared.first_frame(timeline['duration_s'])
    finale = timeline['finale']
    fade_start = shared.first_frame(finale['estimated_start_s'] + finale['relative_cream_fade_s'][0])
    indices = sorted(set(samples) | {0, fade_start - 1, total - 1})
    filters = f'select={shared.select_expression(indices)},scale=480:270:flags=area:in_color_matrix=bt709,format=rgb24'
    command = [str(ffmpeg), '-nostdin', '-v', 'error', '-xerror', '-i', str(video), '-map', '0:v:0', '-an',
               '-vf', filters, '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1']
    errors, stats = [], defaultdict(int)
    decoded = 0
    with subprocess.Popen(command, stdout=subprocess.PIPE) as process:
        for index in indices:
            raw = process.stdout.read(shared.BYTES_PER_FRAME)
            if len(raw) != shared.BYTES_PER_FRAME:
                errors.append(f'Decode ended before frame {index}')
                break
            decoded += 1
            frame = Image.frombytes('RGB', shared.SAMPLE_SIZE, raw)
            if index in (0, total - 1):
                for point in ((480, 240), (1200, 500), (100, 700), (1810, 1000)):
                    if not shared.close_to_fill(frame, *point, shared.CREAM_FILL):
                        errors.append(f'Fade endpoint frame {index} differs at {point}')
            if index == fade_start - 1:
                errors.extend(f'Before fade: {error}' for error in check_count_frame(frame, 127, None))
            for value, active, role in samples.get(index, ()):
                stats[role] += 1
                errors.extend(f'Frame {index}, hexadecimal {value:X}, {role}: {error}'
                              for error in check_count_frame(frame, value, active))
        if process.stdout.read(1):
            errors.append('Decoder returned an unexpected extra frame')
            process.stdout.close()
        if process.wait():
            errors.append('Frame decoder failed')
    native = native_layout_checks(video, timeline, ffmpeg)
    errors.extend(native['errors'])
    return {'sampled_frames': decoded, 'planned_samples': len(indices), 'checks_by_role': dict(stats),
            'native_layout': native, 'all_samples_match': not errors, 'errors': errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', required=True, type=Path)
    parser.add_argument('--video', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--delivery-dir', type=Path)
    parser.add_argument('--technical-report', type=Path, help='Reuse passing QA bound to the same video and timeline hashes')
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg'))
    parser.add_argument('--ffprobe', default=shutil.which('ffprobe'))
    args = parser.parse_args()
    timeline = json.loads(args.timeline.read_text(encoding='utf-8-sig'))
    if timeline['fps'] != FPS:
        raise ValueError('The hexadecimal episode requires 30 fps')
    timeline_hash = shared.sha256_file(args.timeline)
    if args.technical_report:
        technical = json.loads(args.technical_report.read_text(encoding='utf-8-sig'))
        if (technical.get('status') != 'pass' or technical.get('sha256') != shared.sha256_file(args.video)
                or (technical.get('timeline') or {}).get('sha256') != timeline_hash):
            raise ValueError('Technical report does not pass or match the video and timeline hashes')
        args.output_dir.mkdir(parents=True, exist_ok=True)
    else:
        technical = shared.verify_video(args.video, args.output_dir, args.timeline, args.ffmpeg, args.ffprobe,
                                         duration_bounds=(1, 900))
    checks = metadata_checks(timeline, args.delivery_dir or args.video.parent, args.video.name)
    checks['exact_video_frame_timestamp_grid'] = shared.check_video_timestamps(args.video, timeline['duration_s'], args.ffprobe)
    visual = visual_checks(args.video, timeline, args.ffmpeg)
    checks['all_sampled_count_visuals_match'] = visual['all_samples_match']
    checks['technical_media_report_passes'] = technical['status'] == 'pass'
    report = {'status': 'pass' if all(checks.values()) else 'fail', 'checks': checks, 'visual': visual,
              'timeline_sha256': timeline_hash, 'video_sha256': technical['sha256']}
    destination = args.output_dir / 'hexadecimal-final-qa.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(destination), 'checks': checks,
                      'visual_failures': len(visual['errors'])}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
