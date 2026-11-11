"""Independently verify the even-number delivery, all count boundaries and AAC."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import wave

from PIL import Image, ImageChops, ImageDraw, ImageStat

if __package__:
    from . import verify_video as technical
    from . import verify_octal_video as visual_shared
    from .portable_production import module as legacy_module
    from .verify_binary_production import _pcm_values, waveform_correlation
    from .render_binary_video import font
    source_references = legacy_module('verify_octal_audio').source_references
else:
    import verify_video as technical
    import verify_octal_video as visual_shared
    from verify_octal_audio import source_references
    from verify_binary_production import _pcm_values, waveform_correlation
    from render_binary_video import font


ROOT = Path(__file__).resolve().parents[1]
FPS, RATE = 30, 48000
SIZE = (1920, 1080)
MAIN = (132, 292, 1100, 600)
READING = (120, 604, 1380, 668)
CARDS = ((352, 920, 568, 988), (640, 920, 860, 988), (932, 920, 1148, 988))
CARD_CENTERS = (460, 750, 1040)
INK, TEAL, MUTED = '#51341f', '#205b57', '#756352'
INTRO_IDS = ('I01', 'I02', 'I03', 'I04', 'I05', 'I06', 'I06B', 'I07')


def english_number(value):
    """Construct the canonical US cardinal without using the episode renderer."""
    small = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
             'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
             'seventeen', 'eighteen', 'nineteen')
    tens = ('', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety')
    if not isinstance(value, int) or not 0 <= value <= 200:
        raise ValueError('Expected an integer zero through two hundred')
    if value < 20:
        return small[value]
    if value < 100:
        return tens[value // 10] + ('-' + small[value % 10] if value % 10 else '')
    return small[value // 100] + ' hundred' + (' ' + english_number(value % 100) if value % 100 else '')


def sample(seconds):
    return round(seconds * RATE)


def frame_at(seconds):
    return math.ceil(seconds * FPS - 1e-7)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_schedule(plan):
    require(plan['fps'] == FPS, 'Expected 30 fps')
    require(plan['duration_frames'] == frame_at(plan['duration_s']), 'Frame count disagrees with duration')
    scenes = plan['scenes']
    require([s['scene'] for s in scenes] == ['intro'] + ['count'] * 101 + ['finale'],
            'The scene sequence must have one intro, 101 counts and one finale')
    states = scenes[1:-1]
    require([s['decimal_value'] for s in states] == list(range(0, 201, 2)),
            'Count scenes must include every even value zero through 200 exactly once')
    require(sample(scenes[0]['start_s']) == 0 and sample(scenes[0]['end_s']) == sample(36),
            'Intro must cover zero through 36 seconds')
    for left, right in zip(scenes, scenes[1:]):
        require(sample(left['end_s']) == sample(right['start_s']), 'Scene intervals must be continuous')
    require(sample(scenes[-1]['end_s']) == sample(plan['duration_s']), 'Finale does not reach the end')
    require(sample(scenes[-1]['end_s'] - scenes[-1]['start_s']) == sample(14), 'Finale must last 14 seconds')

    events = sorted(plan['voice_events'], key=lambda event: event['start_s'])
    expected_ids = set(INTRO_IDS) | {'T020', 'T100', 'F01', 'F02', 'F03', 'F04'}
    expected_ids |= {f'N{value:03}' for value in range(0, 201, 2)}
    require(len(events) == 115 and {e['id'] for e in events} == expected_ids, 'Missing, duplicate or unexpected voice events')
    require(Counter(e['type'] for e in events) == {'number_voice': 101, 'dialogue': 14}, 'Unexpected audio event types')
    require(plan.get('events', events) == plan['voice_events'], 'events and voice_events disagree')
    cursor = sample(.8)
    for event in events:
        start, end = sample(event['start_s']), sample(event['end_s'])
        require(cursor <= start < end <= sample(plan['duration_s']), f'Invalid or overlapping voice {event["id"]}')
        require(start == event['start_sample_24k'] * 2 and end == event['end_sample_24k'] * 2,
                f'Event is not on the source PCM grid: {event["id"]}')
        require(event['phase'] in ('intro', 'count', 'teaching', 'finale'), 'Unexpected event phase')
        cursor = end
    count = [e for e in events if e['phase'] == 'count']
    require([e.get('decimal_value') for e in count] == list(range(0, 201, 2)), 'Count audio sequence differs')
    gaps = []
    for state, event, value in zip(states, count, range(0, 201, 2), strict=True):
        require(event['id'] == f'N{value:03}' and event['text'] == english_number(value), f'Incorrect cardinal at {value}')
        require(sample(event['start_s'] - state['start_s']) == sample(.12), f'Incorrect display lead at {value}')
        require(sample(event['start_s']) == sample(state['voice_start_s']) and
                sample(event['end_s']) == sample(state['voice_end_s']), f'Voice and scene mismatch at {value}')
        require(sample(event['end_s']) < sample(state['end_s']), f'Count speech exceeds its display at {value}')
        if value in (20, 100):
            teaching = state['teaching']
            require(teaching['id'] == f'T{value:03}', 'Teaching ID mismatch')
            require(sample(teaching['start_s'] - event['end_s']) == sample(.4), 'Teaching must start 0.4 seconds after the number')
            require(sample(teaching['end_s'] - teaching['start_s']) == sample(8), 'Teaching must last eight seconds')
            line = next(e for e in events if e['id'] == teaching['id'])
            require(teaching['start_s'] <= line['start_s'] < line['end_s'] <= teaching['end_s'], 'Teaching speech exceeds its scene')
        else:
            require(not state.get('teaching'), f'Unexpected teaching at {value}')
    for left, right in zip(count, count[1:]):
        gap = sample(right['start_s']) - sample(left['end_s'])
        require(gap == sample(10 if left['decimal_value'] in (20, 100) else 2), f'Incorrect gap after {left["id"]}')
        gaps.append(gap)
    require(sample(scenes[-1]['start_s'] - count[-1]['end_s']) == sample(.28), 'Incorrect final count hold')
    require(events[-1]['end_s'] <= plan['duration_s'] - 2, 'Speech overlaps the closing fade')
    return events, {'count_values': 101, 'independent_english_cardinals': 101, 'audio_events': 115,
                    'ordinary_two_second_gaps': gaps.count(sample(2)), 'teaching_ten_second_gaps': gaps.count(sample(10)),
                    'scene_continuity_boundaries': len(scenes) - 1, 'final_value': 200}


def validate_authored_dialogue(events, script):
    authored = {}
    for line in script.read_text(encoding='utf-8-sig').splitlines():
        cells = [part.strip() for part in line.split('|')]
        if cells and re.fullmatch(r'I\d+[A-Z]?|T\d+|F\d+', cells[0]):
            authored[cells[0]] = cells[3] if cells[0].startswith('T') else cells[2]
    actual = {e['id']: e['text'] for e in events if e['type'] == 'dialogue'}
    require(actual == authored, 'Recorded dialogue differs from the authored English script')
    return len(actual)


def glyph_mask(image):
    return image.convert('L').point(lambda value: 255 if value < 137 else 0)


def overlap(actual, expected):
    union = ImageChops.lighter(actual, expected).histogram()[255]
    return ImageChops.darker(actual, expected).histogram()[255] / union if union else 1.0


@lru_cache(maxsize=1000)
def expected_text(text, center, size, color, fill, box, divisor):
    image = Image.new('RGB', (box[2] - box[0], box[3] - box[1]), fill)
    if text:
        face = font(size)
        mask, (ox, oy) = face.getmask2(text, mode='L')
        left, top, right, bottom = mask.getbbox()
        x = round(center[0] - (left + right + 2 * ox) / 2) - box[0]
        y = round(center[1] - (top + bottom + 2 * oy) / 2) - box[1]
        ImageDraw.Draw(image).text((x, y), text, font=face, fill=color)
    if divisor != 1:
        image = image.resize((image.width // divisor, image.height // divisor), Image.Resampling.BOX)
    return glyph_mask(image)


def count_frame_checks(image, value, divisor, include_cards=True):
    checks = {}
    fields = [('number', str(value), (680, 447), 360, INK, '#fffaf0', MAIN),
              ('reading', english_number(value), (750, 635), 42, TEAL, '#fffaf0', READING)]
    if include_cards:
        neighbors = (value - 2 if value else None, value, value + 2 if value < 200 else None)
        for index, (number, center, box) in enumerate(zip(neighbors, CARD_CENTERS, CARDS, strict=True)):
            text = str(number) if number is not None else 'START' if value == 0 else 'END'
            fields.append((('previous', 'current', 'next')[index], text, (center, 953), 61 if number is not None else 25,
                           TEAL if index == 1 else MUTED, '#e0efe4' if index == 1 else '#f6efdf', box))
    for name, text, center, size, color, fill, box in fields:
        crop = image.crop(tuple(v // divisor for v in box))
        checks[name] = overlap(glyph_mask(crop), expected_text(text, center, size, color, fill, box, divisor))
    return checks


def visible_blocks(image):
    """Count disconnected warm block interiors from decoded pixels, not draw metadata."""
    box = (120, 735, 1380, 852)
    crop = image.crop(box)
    width, height = crop.size
    pending = {index for index, (r, g, b) in enumerate(crop.get_flattened_data())
               if r > 220 and 170 < g < 211 and 105 < b < 156}
    components = []
    while pending:
        seed = pending.pop()
        stack, points = [seed], [seed]
        while stack:
            at = stack.pop()
            x, y = at % width, at // width
            neighbors = []
            if x:
                neighbors.append(at - 1)
            if x + 1 < width:
                neighbors.append(at + 1)
            if y:
                neighbors.append(at - width)
            if y + 1 < height:
                neighbors.append(at + width)
            for neighbor in neighbors:
                if neighbor in pending:
                    pending.remove(neighbor)
                    stack.append(neighbor)
                    points.append(neighbor)
        if len(points) >= 100:
            xs, ys = [p % width for p in points], [p // width for p in points]
            components.append({'pixels': len(points), 'center': [(min(xs) + max(xs)) / 2 + box[0],
                                                                (min(ys) + max(ys)) / 2 + box[1]]})
    return sorted(components, key=lambda item: (item['center'][1], item['center'][0]))


def check_block_arrangement(image, quantity):
    components = visible_blocks(image)
    require(len(components) == quantity, f'Decoded teaching diagram contains {len(components)} blocks, expected {quantity}')
    if quantity:
        columns = (750,) if quantity == 2 else (485, 750, 1015) if quantity == 6 else tuple(364 + 82 * i for i in range(10))
        rows = (756, 815) if quantity == 20 else (765, 815)
        expected = [(x, y) for y in rows for x in columns]
        unmatched = list(components)
        for center in expected:
            match = next((item for item in unmatched if max(abs(a - b) for a, b in
                         zip(item['center'], center, strict=True)) < 4), None)
            require(match is not None, 'Blocks must form two rows with one vertical pair in every column')
            unmatched.remove(match)
    return {'quantity': quantity, 'vertical_pairs': quantity // 2, 'components': components}


def check_last_digit_examples(image):
    records = []
    for digit, center in zip((0, 2, 4, 6, 8), (530, 640, 750, 860, 970), strict=True):
        box = (center - 35, 754, center + 35, 823)
        score = overlap(glyph_mask(image.crop(box)),
                        expected_text(str(digit), (center, 788), 51, TEAL, '#e1efe2', box, 1))
        require(score >= .95, f'Last-digit candidate {digit} differs in the delivered image')
        records.append({'digit': digit, 'glyph_iou': score})
    return records


def decoded_frames(video, indices, ffmpeg, divisor, log):
    width, height = SIZE[0] // divisor, SIZE[1] // divisor
    expression = visual_shared.select_expression(indices)
    filters = f'select={expression}'
    if divisor != 1:
        filters += f',scale={width}:{height}:flags=area:in_color_matrix=bt709'
    filters += ',format=rgb24'
    command = [ffmpeg, '-nostdin', '-v', 'error', '-xerror', '-i', str(video), '-an',
               '-vf', filters, '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1']
    with log.open('xb') as errors, subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors) as process:
        for index in indices:
            raw = process.stdout.read(width * height * 3)
            require(len(raw) == width * height * 3, f'Frame decoder ended before frame {index}')
            yield index, Image.frombytes('RGB', (width, height), raw)
        require(not process.stdout.read(1), 'Unexpected extra selected frame')
        require(process.wait() == 0, 'Selected-frame decode failed')


def visual_checks(video, plan, ffmpeg, directory):
    # The mathematical values and expected text do not come from Scene.state().
    if __package__:
        Scene = legacy_module('render_even_video').Scene
    else:
        from render_even_video import Scene
    scene = Scene(plan)
    probes = defaultdict(list)
    for state in plan['scenes'][1:-1]:
        value = state['decimal_value']
        start, end = frame_at(state['start_s']), frame_at(state['end_s'])
        begin, stop = frame_at(state['voice_start_s']), frame_at(state['voice_end_s'])
        for at, role in ((start, 'display_start'), (end - 1, 'display_end'), (begin - 1, 'before_voice'),
                         (begin, 'voice_start'), (stop - 1, 'voice_end'), (stop, 'after_voice')):
            probes[at].append((value, role))
    native = {}
    for state in plan['scenes'][1:-1]:
        if state['decimal_value'] in (0, 2, 8, 20, 98, 100, 102, 178, 198, 200):
            native[frame_at(state['voice_start_s'])] = ('count', state['decimal_value'])
        if state.get('teaching'):
            t = state['teaching']
            for offset in (0, .5, 3, 7.3, 7.95):
                native[frame_at(t['start_s'] + offset)] = ('teaching', state['decimal_value'])
    for at in (0, 8.2, 8.9, 12.2, 12.9, 18, 24.1, 24.3, 29.9, 35.5,
               plan['scenes'][-1]['start_s'] + .9, plan['scenes'][-1]['start_s'] + 1.1,
               plan['duration_s'] - 2.1, plan['duration_s'] - 1, (plan['duration_frames'] - 1) / FPS):
        native[frame_at(at)] = ('special', None)
    errors, records = [], []
    minimum = defaultdict(lambda: 1.0)
    role_counts = Counter()
    for index, image in decoded_frames(video, sorted(probes), ffmpeg, 4, directory / 'sample-decode.log'):
        for value, role in probes[index]:
            scores = count_frame_checks(image, value, 4)
            role_counts[role] += 1
            for field, score in scores.items():
                minimum[field] = min(minimum[field], score)
                if score < .89:
                    errors.append(f'Frame {index}/{value}/{role}/{field}: glyph overlap {score:.5f}')
    native_records = []
    intro_quantities = {frame_at(8.9): 2, frame_at(12.9): 6, frame_at(18): 6,
                        frame_at(24.3): 0, frame_at(29.9): 0, frame_at(35.5): 0}
    for index, image in decoded_frames(video, sorted(native), ffmpeg, 1, directory / 'native-decode.log'):
        kind, value = native[index]
        expected = scene.image(scene.state(index)).convert('RGB')
        item = {'frame': index, 'kind': kind, 'value': value}
        item['mean_absolute_rgb_error'] = ImageStat.Stat(ImageChops.difference(image, expected)).mean
        if max(item['mean_absolute_rgb_error']) > 4:
            errors.append(f'Native frame {index}: scene colors or transition differ')
        # Scene comparison supplements independent text checks for diagrams,
        # registered character, clipping, transition frames and fade endpoints.
        for name, box in [('main', MAIN), ('reading', READING), ('teaching', (120, 687, 1380, 855)),
                          ('progression', (120, 860, 1380, 1010)), ('bird', (1460, 600, 1880, 990)),
                          ('title', (60, 30, 1440, 202))]:
            score = overlap(glyph_mask(image.crop(box)), glyph_mask(expected.crop(box)))
            item[name + '_glyph_iou'] = score
            if score < .94:
                errors.append(f'Native frame {index}/{name}: expected-scene overlap {score:.5f}')
        if kind == 'count':
            independent = count_frame_checks(image, value, 1)
            item['independent_cardinals'] = independent
            for field, score in independent.items():
                if score < .95:
                    errors.append(f'Native frame {index}/{field}: independent text overlap {score:.5f}')
        try:
            if index in intro_quantities:
                quantity = intro_quantities[index]
                item['independent_blocks'] = check_block_arrangement(image, quantity)
                scores = count_frame_checks(image, quantity, 1, include_cards=False)
                require(min(scores.values()) >= .95, 'Intro example and its displayed cardinal disagree')
                item['independent_intro_cardinal'] = scores
            if kind == 'teaching':
                teaching = next(s['teaching'] for s in plan['scenes'][1:-1] if s['decimal_value'] == value)
                age = index / FPS - teaching['start_s']
                if .5 <= age < 7.4:
                    if value == 20:
                        item['independent_blocks'] = check_block_arrangement(image, 20)
                    else:
                        item['independent_last_digits'] = check_last_digit_examples(image)
        except ValueError as error:
            errors.append(f'Native frame {index}: {error}')
        if index == plan['duration_frames'] - 1:
            channel_max = max(max(channel.getextrema()) for channel in ImageChops.difference(image, expected).split())
            item['final_fade_max_rgb_error'] = channel_max
            if channel_max > 5:
                errors.append('Final frame does not reach its expected cream fade endpoint')
        native_records.append(item)
        if kind != 'count':
            thumb = image.copy()
            thumb.thumbnail((640, 360))
            records.append((index, thumb))
    if records:
        contact = Image.new('RGB', (1280, math.ceil(len(records) / 2) * 390), '#fff8e8')
        draw = ImageDraw.Draw(contact)
        for ordinal, (index, image) in enumerate(records):
            x, y = ordinal % 2 * 640, ordinal // 2 * 390
            contact.paste(image, (x, y))
            draw.text((x + 10, y + 362), f'frame {index} / {index / FPS:.3f}s', fill='black')
        contact.save(directory / 'scene-contact-sheet.png')
    return {'passed': not errors, 'decoded_count_samples': len(probes), 'count_checks_by_role': dict(role_counts),
            'independent_minimum_glyph_iou': dict(minimum), 'native_samples': native_records,
            'expected_scene_comparison_uses_renderer': True, 'independent_text_uses_renderer': False,
            'errors': errors}


def stereo_audio_checks(source, events, clips, duration, ffmpeg, directory, lossy):
    destination = directory / ('aac-stereo.wav' if lossy else 'master-stereo.wav')
    subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-xerror', '-n', '-i', str(source), '-map', '0:a:0',
                    '-ar', str(RATE), '-ac', '2', '-c:a', 'pcm_s16le', str(destination)], check=True)
    guard, limit = sample(.03 if lossy else .002), 3 if lossy else 1
    observations, silence_peaks = [], []
    with wave.open(str(destination), 'rb') as track:
        require(abs(track.getnframes() - sample(duration)) <= (2048 if lossy else 0), 'Audio track duration differs')
        cursor = 0
        for event in events:
            start, end = sample(event['start_s']), sample(event['end_s'])
            gap_start = cursor + (guard if cursor else 0)
            gap_size = start - guard - gap_start
            if gap_size > 0:
                track.setpos(gap_start)
                silence_peaks.append(max(map(abs, _pcm_values(track.readframes(gap_size))), default=0))
            cursor = end
            _, reference = clips[ROOT / event['source_path']]
            require(abs(len(reference) - (end - start)) <= 2, f'Source duration differs at {event["id"]}')
            track.setpos(start - 8)
            interleaved = _pcm_values(track.readframes(len(reference) + 16))
            channels = [waveform_correlation(reference, interleaved[channel::2], 8) for channel in range(2)]
            require(min(correlation for correlation, _ in channels) >= .97,
                    f'Stereo speech differs at {event["id"]}: {channels}')
            observations.append({'id': event['id'], 'source_sha256': event['source_sha256'],
                                 'left_correlation': channels[0][0], 'left_lag_samples': channels[0][1],
                                 'right_correlation': channels[1][0], 'right_lag_samples': channels[1][1]})
        track.setpos(cursor + guard)
        silence_peaks.append(max(map(abs, _pcm_values(track.readframes(track.getnframes()))), default=0))
    maximum = max(silence_peaks)
    require(maximum <= limit, f'Unexpected sound outside voice events: {maximum} PCM16')
    return {'passed': True, 'source_sha256': technical.sha256_file(source), 'events_checked': len(observations),
            'channels_checked_per_event': 2, 'minimum_correlation': min(min(e['left_correlation'], e['right_correlation']) for e in observations),
            'silent_intervals_checked': len(silence_peaks), 'silence_boundary_guard_s': guard / RATE,
            'maximum_silent_interior_peak_pcm16': maximum, 'events': observations}


def caption_checks(plan, directory):
    text = (directory / 'english-captions.srt').read_text(encoding='utf-8-sig').replace('\r\n', '\n')
    blocks = text.strip().split('\n\n')
    events = sorted(plan['voice_events'], key=lambda event: event['start_s'])
    require(len(blocks) == len(events) == 115, 'Expected 115 caption cues')
    def stamp(seconds):
        total = round(seconds * 1000)
        return f'{total // 3600000:02}:{total // 60000 % 60:02}:{total // 1000 % 60:02},{total % 1000:03}'
    for index, (block, event) in enumerate(zip(blocks, events, strict=True), 1):
        lines = block.splitlines()
        require(len(lines) == 3 and lines[0] == str(index), 'Caption format or numbering differs')
        require(lines[1] == f'{stamp(event["start_s"])} --> {stamp(event["end_s"])}', f'Caption timing differs at {event["id"]}')
        require(re.sub(r'[^a-z0-9]', '', lines[2].lower()) == re.sub(r'[^a-z0-9]', '', event['text'].lower()),
                f'Caption text differs at {event["id"]}')
    return {'passed': True, 'caption_cues_checked': len(blocks)}


def delivery_metadata_checks(plan, directory, video_name):
    chapters = (directory / 'chapters.txt').read_text(encoding='utf-8-sig').splitlines()
    stamps = []
    for line in chapters:
        matched = re.fullmatch(r'(\d+):(\d{2}) .+', line)
        require(matched is not None, 'Malformed chapter line')
        stamps.append(int(matched[1]) * 60 + int(matched[2]))
    teaching = [scene['teaching']['start_s'] for scene in plan['scenes'][1:-1] if scene.get('teaching')]
    expected = [0, math.floor(plan['scenes'][0]['end_s']), *map(math.floor, teaching),
                math.floor(plan['scenes'][-1]['start_s'])]
    require(stamps == expected, 'Chapter timestamps differ from measured sections')
    require(all(right - left >= 10 for left, right in zip(stamps, stamps[1:] + [plan['duration_s']])),
            'Every chapter must contain at least ten seconds')
    upload = (directory / 'upload-details.txt').read_text(encoding='utf-8-sig')
    require(upload.startswith('Title\nCount Even Numbers from 0 to 200 | Count by Twos | Num-Num Numbers\n'),
            'Upload title does not identify the completed range')
    require('\n'.join(chapters) in upload and f'Video: {video_name}\n' in upload and
            'Captions: english-captions.srt (English)' in upload, 'Upload copy refers to different delivery files or chapters')
    return {'passed': True, 'measured_chapters_checked': len(chapters), 'video_and_caption_references_checked': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--master', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--delivery-dir', type=Path)
    parser.add_argument('--script', type=Path, default=ROOT / 'design/even-counting-v1/script-and-sound-cues.txt')
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg'))
    parser.add_argument('--ffprobe', default=shutil.which('ffprobe'))
    parser.add_argument('--work-dir', type=Path, default=Path('D:/temp/even-production-qa'))
    args = parser.parse_args(argv)
    plan = json.loads(args.timeline.read_text(encoding='utf-8-sig'))
    events, schedule = validate_schedule(plan)
    schedule['authored_dialogue_checked'] = validate_authored_dialogue(events, args.script)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    require(not (args.output_dir / 'even-final-qa.json').exists(), 'Refusing to overwrite an existing final QA record')
    technical_report = technical.verify_video(args.video, args.output_dir, args.timeline, args.ffmpeg, args.ffprobe,
                                              duration_bounds=(1, 900))
    visual = visual_checks(args.video, plan, args.ffmpeg, args.output_dir)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='verify-', dir=args.work_dir) as temporary:
        directory = Path(temporary)
        clips = source_references(events, args.ffmpeg, directory)
        master = stereo_audio_checks(args.master, events, clips, plan['duration_s'], args.ffmpeg, directory, False)
        encoded = stereo_audio_checks(args.video, events, clips, plan['duration_s'], args.ffmpeg, directory, True)
    captions = caption_checks(plan, args.delivery_dir or args.video.parent)
    delivery = delivery_metadata_checks(plan, args.delivery_dir or args.video.parent, args.video.name)
    checks = {'technical_media': technical_report['status'] == 'pass', 'visual_samples': visual['passed'],
              'uniform_frame_timestamps': visual_shared.check_video_timestamps(args.video, plan['duration_s'], args.ffprobe),
              'master_audio': master['passed'], 'final_aac_audio': encoded['passed'], 'captions': captions['passed'],
              'delivery_metadata': delivery['passed']}
    report = {'status': 'pass' if all(checks.values()) else 'fail', 'checks': checks,
              'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'schedule': schedule, 'visual': visual,
              'master': master, 'encoded_audio': encoded, 'captions': captions, 'delivery_metadata': delivery,
              'video_sha256': technical.sha256_file(args.video), 'timeline_sha256': technical.sha256_file(args.timeline),
              'verifier_sha256': technical.sha256_file(Path(__file__)),
              'scope': 'Full media decode; all 101 count values around display and voice boundaries; representative native diagrams, intro, character and fade; each of 115 source voices versus both master and final AAC stereo channels; all non-event interiors and captions.',
              'new_asr_or_human_full_listening_claimed': False}
    destination = args.output_dir / 'even-final-qa.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(destination), 'checks': checks,
                      'visual_errors': len(visual['errors']), 'aac_minimum_correlation': encoded['minimum_correlation']}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
