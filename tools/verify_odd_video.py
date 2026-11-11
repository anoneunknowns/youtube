"""Independently check odd-count content, every decoded frame, media and audio."""

from __future__ import annotations

import argparse
from bisect import bisect_right
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
    from . import verify_even_video as shared
else:
    import verify_even_video as shared


ROOT = Path(__file__).resolve().parents[1]
FPS, RATE = 30, 48000
SIZE = (1920, 1080)
MAIN = (132, 292, 1100, 600)
READING = (120, 604, 1340, 668)
TEACHING = (120, 687, 1340, 855)
CARD_CENTERS = (250, 410, 570, 730, 890, 1050, 1210)
INK, TEAL, MUTED = '#51341f', '#205b57', '#756352'
INTRO_IDS = ('I01', 'I02', 'I03', 'I04', 'I05', 'I06', 'I07')
TEACHING_VALUES = (9, 101)
EXPECTED_VALUES = tuple(range(1, 200, 2))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sample(seconds):
    return round(seconds * RATE)


def frame_at(seconds):
    return math.ceil(seconds * FPS - 1e-7)


def english_number(value):
    """Own US-cardinal construction; no producer word function is imported."""
    ones = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
            'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
            'seventeen', 'eighteen', 'nineteen')
    tens = ('', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety')
    require(type(value) is int and 0 <= value <= 300, 'Expected a cardinal integer in 0..300')
    if value < 20:
        return ones[value]
    if value < 100:
        return tens[value // 10] + ('-' + ones[value % 10] if value % 10 else '')
    return ones[value // 100] + ' hundred' + (' ' + english_number(value % 100) if value % 100 else '')


def pacing_policy(plan):
    """Keep historical v001 reproducible and require the new long-form policy."""
    policy = plan.get('pacing_policy')
    revised = plan.get('revision_id') == 'odd-counting-v002'
    if policy is None:
        require(not revised, 'v002 requires an explicit long-form pacing policy')
        return {'ordinary_gap_s': 2.0, 'teaching_gap_s': 10.0, 'minimum_duration_s': 0.0,
                'historical_policy': True}
    ordinary = policy.get('ordinary_gap_s')
    teaching = policy.get('teaching_gap_s')
    minimum = policy.get('minimum_duration_s')
    require(all(type(value) in (float, int) and math.isfinite(value) for value in (ordinary, teaching, minimum)),
            'Pacing policy must declare finite ordinary/teaching gaps and minimum duration')
    require(ordinary >= 2 and sample(teaching - ordinary) == sample(8),
            'Teaching gap must retain exactly eight extra seconds')
    require(minimum >= 480, 'Long-form pacing policy must require at least 480 seconds')
    if revised:
        require(sample(ordinary) == sample(2) and sample(teaching) == sample(10),
                'v002 must preserve two-second ordinary gaps and ten-second teaching gaps')
    require(plan['duration_s'] >= minimum, 'Long-form duration is below the declared minimum of 480 seconds')
    return {'ordinary_gap_s': ordinary, 'teaching_gap_s': teaching, 'minimum_duration_s': minimum,
            'historical_policy': False}


def episode_values(plan):
    last = plan.get('count_end', 199)
    require(plan.get('count_start', 1) == 1 and plan.get('count_step', 2) == 2,
            'Odd episode must start at one and count by two')
    require(last in (199, 299), 'Expected supported odd endpoint 199 or 299')
    if plan.get('revision_id') == 'odd-counting-v002':
        require(last == 299, 'v002 must cover the complete range one through 299')
    return tuple(range(1, last + 1, 2))


def validate_schedule(plan):
    require(plan['fps'] == FPS, 'Expected 30 fps')
    require(plan['duration_frames'] == frame_at(plan['duration_s']), 'Frame count disagrees with duration')
    pacing = pacing_policy(plan)
    values = episode_values(plan)
    count_total, event_total = len(values), len(values) + 13
    scenes = plan['scenes']
    require([scene['scene'] for scene in scenes] == ['intro'] + ['count'] * count_total + ['finale'],
            f'Expected one intro, {count_total} count scenes and one finale')
    states = scenes[1:-1]
    require([state['decimal_value'] for state in states] == list(values),
            f'Count scenes must contain every odd integer 1..{values[-1]} exactly once')
    require(sample(scenes[0]['start_s']) == 0 and sample(scenes[0]['end_s']) == sample(36),
            'Intro must cover zero through 36 seconds')
    for left, right in zip(scenes, scenes[1:]):
        require(sample(left['end_s']) == sample(right['start_s']), 'Scenes must be continuous')
    require(sample(scenes[-1]['end_s']) == sample(plan['duration_s']), 'Finale does not reach the end')
    require(sample(scenes[-1]['end_s'] - scenes[-1]['start_s']) == sample(14), 'Finale must last fourteen seconds')
    events = sorted(plan['voice_events'], key=lambda row: row['start_s'])
    expected_ids = set(INTRO_IDS) | {'T009', 'T101', 'F01', 'F02', 'F03', 'F04'}
    expected_ids |= {f'N{value:03d}' for value in values}
    require(len(events) == event_total and {row['id'] for row in events} == expected_ids,
            'Missing, duplicate or unexpected voice events')
    require(Counter(row['type'] for row in events) == {'number_voice': count_total, 'dialogue': 13},
            f'Expected {count_total} number voices and thirteen dialogue events')
    require(plan.get('events', events) == plan['voice_events'], 'events and voice_events disagree')
    cursor = sample(.8)
    for row in events:
        start, end = sample(row['start_s']), sample(row['end_s'])
        require(cursor <= start < end <= sample(plan['duration_s']), f'Invalid or overlapping voice {row["id"]}')
        require(start == row['start_sample_24k'] * 2 and end == row['end_sample_24k'] * 2,
                f'Voice is off the source sample grid: {row["id"]}')
        require(row['phase'] in ('intro', 'count', 'teaching', 'finale'), 'Unexpected voice phase')
        cursor = end
    counted = [row for row in events if row['phase'] == 'count']
    require([row.get('decimal_value') for row in counted] == list(values), 'Count audio sequence differs')
    for state, row, value in zip(states, counted, values, strict=True):
        require(row['id'] == f'N{value:03d}' and row['text'] == english_number(value),
                f'Incorrect US cardinal at {value}')
        require(sample(row['start_s'] - state['start_s']) == sample(.12), f'Incorrect display lead at {value}')
        require(sample(row['start_s']) == sample(state['voice_start_s']) and
                sample(row['end_s']) == sample(state['voice_end_s']), f'Scene and voice disagree at {value}')
        require(sample(row['end_s']) < sample(state['end_s']), 'A count voice exceeds its display')
        if value in TEACHING_VALUES:
            pause = state.get('teaching')
            require(pause and pause['id'] == f'T{value:03d}', f'Missing teaching scene at {value}')
            require(sample(pause['start_s'] - row['end_s']) == sample(.4), 'Teaching must start after .4 seconds')
            require(sample(pause['end_s'] - pause['start_s']) == sample(8), 'Teaching must last eight seconds')
            line = next(event for event in events if event['id'] == pause['id'])
            require(pause['start_s'] <= line['start_s'] < line['end_s'] <= pause['end_s'],
                    'Teaching voice exceeds its scene')
        else:
            require(not state.get('teaching'), f'Unexpected teaching at {value}')
    gaps = Counter()
    for left, right in zip(counted, counted[1:]):
        gap = sample(right['start_s']) - sample(left['end_s'])
        require(gap == sample(pacing['teaching_gap_s'] if left['decimal_value'] in TEACHING_VALUES else pacing['ordinary_gap_s']),
                f'Incorrect count gap after {left["id"]}')
        gaps[gap] += 1
    require(gaps == {sample(pacing['ordinary_gap_s']): count_total - 3, sample(pacing['teaching_gap_s']): 2},
            'Incorrect ordinary/teaching boundary coverage')
    require(sample(scenes[-1]['start_s'] - counted[-1]['end_s']) == sample(.28), 'Incorrect final-value hold')
    require(events[-1]['end_s'] <= plan['duration_s'] - 2, 'Speech overlaps the final fade')
    numeric_speech_s = sum(row['end_sample_24k'] - row['start_sample_24k'] for row in counted) / 24000
    fixed_edit_s = 36 + 14 + (count_total - 1) * pacing['ordinary_gap_s'] + 16 + .12 + .28
    require(sample(plan['duration_s']) == sample(numeric_speech_s + fixed_edit_s),
            'Total duration differs from actual number voices plus fixed editing waits')
    return events, {'count_values': count_total, 'independent_us_cardinals': count_total, 'audio_events': event_total,
                    'ordinary_gap_s': pacing['ordinary_gap_s'], 'ordinary_boundaries': count_total - 3,
                    'teaching_gap_s': pacing['teaching_gap_s'], 'teaching_boundaries': 2,
                    'minimum_duration_s': pacing['minimum_duration_s'], 'historical_policy': pacing['historical_policy'],
                    'numeric_voice_duration_s': numeric_speech_s, 'fixed_editing_duration_s': fixed_edit_s,
                    **({'ordinary_two_second_gaps': 97, 'teaching_ten_second_gaps': 2} if pacing['historical_policy'] else {}),
                    'scene_continuity_boundaries': len(scenes) - 1, 'final_count_value': values[-1],
                    'even_context_tickets_are_not_count_audio': True}


def authored_dialogue(events, path, plan=None):
    lines, windows = {}, {}
    for raw in path.read_text(encoding='utf-8-sig').splitlines():
        cells = [cell.strip() for cell in raw.split('|')]
        if cells and re.fullmatch(r'I\d+[A-Z]?|T\d+|F\d+', cells[0]):
            lines[cells[0]] = cells[3] if cells[0].startswith('T') else cells[2]
            windows[cells[0]] = tuple(map(float, cells[2 if cells[0].startswith('T') else 1].split('–')))
    actual = {row['id']: row['text'] for row in events if row['type'] == 'dialogue'}
    require(actual == lines and len(actual) == 13, 'Measured dialogue differs from the authored thirteen lines')
    if plan is not None:
        origins = {scene['teaching']['id']: scene['teaching']['start_s']
                   for scene in plan['scenes'][1:-1] if scene.get('teaching')}
        for event in events:
            if event['type'] != 'dialogue':
                continue
            identifier = event['id']
            origin = 0 if identifier.startswith('I') else plan['scenes'][-1]['start_s'] if identifier.startswith('F') else origins[identifier]
            start, stop = windows[identifier]
            require(sample(event['start_s']) == sample(origin + start) and
                    sample(event['end_s']) <= sample(origin + stop),
                    f'Dialogue {identifier} lies outside its authored edit window')
    return len(actual)


def caption_checks(plan, directory):
    text = (directory / 'english-captions.srt').read_text(encoding='utf-8-sig').replace('\r\n', '\n')
    blocks = text.strip().split('\n\n')
    events = sorted(plan['voice_events'], key=lambda row: row['start_s'])
    expected_total = len(episode_values(plan)) + 13
    require(len(blocks) == len(events) == expected_total, f'Expected {expected_total} caption cues')
    def stamp(seconds):
        total = round(seconds * 1000)
        return f'{total // 3600000:02}:{total // 60000 % 60:02}:{total // 1000 % 60:02},{total % 1000:03}'
    for index, (block, row) in enumerate(zip(blocks, events, strict=True), 1):
        cells = block.splitlines()
        require(len(cells) == 3 and cells[0] == str(index), 'Caption numbering/format differs')
        require(cells[1] == f'{stamp(row["start_s"])} --> {stamp(row["end_s"])}', f'Wrong caption time: {row["id"]}')
        require(re.sub('[^a-z0-9]', '', cells[2].lower()) == re.sub('[^a-z0-9]', '', row['text'].lower()),
                f'Wrong caption text: {row["id"]}')
    return {'passed': True, 'caption_cues_checked': expected_total}


def metadata_checks(plan, directory, video_name):
    lines = (directory / 'chapters.txt').read_text(encoding='utf-8-sig').splitlines()
    marks = []
    for line in lines:
        match = re.fullmatch(r'(\d+):(\d{2}) .+', line)
        require(match is not None, 'Malformed chapter line')
        marks.append(int(match[1]) * 60 + int(match[2]))
    pauses = [row['teaching']['start_s'] for row in plan['scenes'][1:-1] if row.get('teaching')]
    require(marks == [0, 36, *map(math.floor, pauses), math.floor(plan['scenes'][-1]['start_s'])],
            'Chapter times do not match measured sections')
    require(all(b - a >= 10 for a, b in zip(marks, marks[1:] + [plan['duration_s']])), 'A chapter is shorter than ten seconds')
    upload = (directory / 'upload-details.txt').read_text(encoding='utf-8-sig')
    last = episode_values(plan)[-1]
    require(lines[-1].endswith(' We Reached ' + english_number(last).title()),
            'Final chapter title has the wrong ending number')
    require(upload.startswith(f'Title\nCount Odd Numbers from 1 to {last} | Count by Twos | Num-Num Numbers\n'),
            'Upload title has the wrong sequence or range')
    require('\n'.join(lines) in upload and f'Video: {video_name}\n' in upload and
            'Captions: english-captions.srt (English)' in upload, 'Upload copy has the wrong files/chapters')
    require(f'Count odd numbers from one to {english_number(last)} with Red Panda' in upload,
            'Description has the wrong ending number')
    return {'passed': True, 'chapters_checked': len(marks), 'video_and_caption_references_checked': True}


def pcm_contract_checks(events, master, duration):
    """Inspect original PCM headers and bound lengths before any resampling."""
    sources = {}
    for row in events:
        path = ROOT / row['source_path']
        require(shared.technical.sha256_file(path) == row['source_sha256'], f'Source hash differs at {row["id"]}')
        with wave.open(str(path), 'rb') as reader:
            require((reader.getframerate(), reader.getnchannels(), reader.getsampwidth(), reader.getcomptype()) ==
                    (24000, 1, 2, 'NONE'), f'Expected original mono PCM16 24 kHz source at {row["id"]}')
            frames = reader.getnframes()
        require(frames == row['end_sample_24k'] - row['start_sample_24k'], f'Original source length differs at {row["id"]}')
        sources[str(path)] = {'sha256': row['source_sha256'], 'sample_frames_24k': frames}
    with wave.open(str(master), 'rb') as reader:
        require((reader.getframerate(), reader.getnchannels(), reader.getsampwidth(), reader.getcomptype()) ==
                (48000, 2, 3, 'NONE'), 'Expected stereo PCM24 48 kHz master')
        require(reader.getnframes() == sample(duration), 'PCM24 master frame count differs')
    return {'passed': True, 'original_sources_checked': len(sources), 'source_format': 'PCM16 mono 24000 Hz',
            'master_format': 'PCM24 stereo 48000 Hz', 'sources': sources}


def numberline_values(value, count_end=199):
    require(type(value) is int and count_end in (199, 299) and value in range(1, count_end + 1, 2),
            f'Number-line current value must be an odd integer in 1..{count_end}')
    start = max(1, min(count_end - 6, value - 3))
    return tuple(range(start, start + 7))


def expected_value_at(plan, index):
    """Authored cue interpretation, independent of the producer's state method."""
    at = index / FPS
    if at < 5:
        return None
    if at < 12.4:
        return 1
    if at < 24.9:
        return 5
    if at < 36:
        return 1
    states = plan['scenes'][1:-1]
    starts = [row['start_s'] for row in states]
    return states[bisect_right(starts, at + 1e-9) - 1]['decimal_value']


def mask(image, threshold=137):
    return image.convert('L').point(lambda value: 255 if value < threshold else 0)


@lru_cache(maxsize=2000)
def text_mask(text, center, size, color, fill, box, divisor=1, threshold=137):
    image = Image.new('RGB', (box[2] - box[0], box[3] - box[1]), fill)
    if text:
        face = shared.font(size)
        glyph, (ox, oy) = face.getmask2(text, mode='L')
        left, top, right, bottom = glyph.getbbox()
        origin = (round(center[0] - (left + right + 2 * ox) / 2) - box[0],
                  round(center[1] - (top + bottom + 2 * oy) / 2) - box[1])
        ImageDraw.Draw(image).text(origin, text, font=face, fill=color)
    if divisor != 1:
        image = image.resize((image.width // divisor, image.height // divisor), Image.Resampling.BOX)
    return mask(image, threshold)


def field_scores(image, value, divisor=4, cards=True, count_end=199):
    fields = [('number', str(value) if value is not None else '', (680, 447), 360, INK, '#fffaf0', MAIN, 137),
              ('reading', english_number(value) if value is not None else '', (730, 635), 42, TEAL, '#fffaf0', READING, 137)]
    if cards and value is not None:
        for number, center in zip(numberline_values(value, count_end), CARD_CENTERS, strict=True):
            fill = '#cfe5d5' if number == value else '#eef2df' if number % 2 else '#f4f0e6'
            fields.append((f'ticket-{center}', str(number), (center, 955), 46,
                           TEAL if number % 2 else '#aaa596', fill,
                           (center - 58, 928, center + 58, 984), 200))
    scores = {}
    for name, text, center, size, color, fill, box, threshold in fields:
        crop = image.crop(tuple(coordinate // divisor for coordinate in box))
        expected = text_mask(text, center, size, color, fill, box, divisor, threshold)
        scores[name] = shared.overlap(mask(crop, threshold), expected)
    return scores


def decoded_frames(video, ffmpeg, divisor, log, indices=None):
    width, height = SIZE[0] // divisor, SIZE[1] // divisor
    filters = []
    if indices is not None:
        filters.append(f'select={shared.visual_shared.select_expression(indices)}')
    if divisor != 1:
        filters.append(f'scale={width}:{height}:flags=area:in_color_matrix=bt709')
    filters.append('format=rgb24')
    command = [ffmpeg, '-nostdin', '-v', 'error', '-xerror', '-i', str(video), '-an',
               '-vf', ','.join(filters), '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1']
    with log.open('xb') as errors, subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors) as process:
        sequence = iter(indices) if indices is not None else iter(range(10000000))
        for index in sequence:
            raw = process.stdout.read(width * height * 3)
            if not raw and indices is None:
                break
            require(len(raw) == width * height * 3, f'Decoder ended inside selected frame {index}')
            yield index, Image.frombytes('RGB', (width, height), raw)
        require(not process.stdout.read(1), 'Decoder emitted an extra selected frame')
        require(process.wait() == 0, 'Selected-frame decode failed')


def _draw_centered(draw, text, center, size, color):
    face = shared.font(size)
    glyph, (ox, oy) = face.getmask2(text, mode='L')
    left, top, right, bottom = glyph.getbbox()
    draw.text((round(center[0] - (left + right + 2 * ox) / 2),
               round(center[1] - (top + bottom + 2 * oy) / 2)), text, font=face, fill=color)


def teaching_surface(kind, alpha=255, indicator=255):
    """Authored ticket/equation oracle, independent of producer drawing functions."""
    target = Image.new('RGB', SIZE, '#f9f0dd')
    draw = ImageDraw.Draw(target)
    if kind in (1, 5, 9):
        pair_count = kind // 2
        title = '1 TICKET  ·  NO PARTNER' if kind == 1 else f'{kind} TICKETS  ·  {pair_count} PAIRS + 1'
        _draw_centered(draw, title, (730, 713), 30, TEAL)
        centers = () if kind == 1 else (480, 750) if kind == 5 else (330, 520, 710, 900)
        for center in centers:
            draw.rounded_rectangle((center - 58, 740, center + 58, 839), radius=14,
                                   fill='#f3f2df', outline='#bac9ae', width=2)
        tickets = [(center, y, False) for center in centers for y in (749, 797)]
        extra_x = 730 if kind == 1 else 1040 if kind == 5 else 1120
        tickets.append((extra_x, 770, True))
        for center, top, extra in tickets:
            left = center - 44
            draw.rounded_rectangle((left, top, left + 88, top + 30), radius=6,
                                   fill='#f3cf91' if extra else '#dce9dd',
                                   outline='#ac7b37' if extra else '#799884', width=2)
            for side in (left, left + 88):
                draw.ellipse((side - 3, top + 12, side + 3, top + 18), fill='#f9f0dd')
        _draw_centered(draw, 'ONE LEFT OVER', (extra_x, 831), 20, '#956a2e')
    elif kind == 'bridge':
        _draw_centered(draw, '99 + 2 = 101', (730, 709), 31, TEAL)
        for value, center in zip((99, 100, 101), (430, 730, 1030), strict=True):
            even = value == 100
            draw.rounded_rectangle((center - 95, 747, center + 95, 824), radius=13,
                                   fill='#f0eee4' if even else '#e1efdf',
                                   outline='#d8d1c2' if even else '#98b393', width=2)
            color = '#aaa596' if even else TEAL
            _draw_centered(draw, str(value), (center, 775), 42, color)
            _draw_centered(draw, 'EVEN' if even else 'ODD', (center, 811), 15, color)
        progress = max(0, min(255, indicator)) / 255
        center = round(430 + 600 * (progress * progress * (3 - 2 * progress)))
        draw.polygon(((center - 9, 733), (center + 9, 733), (center, 744)), fill='#be8b3b')
    elif kind == 'normal':
        _draw_centered(draw, 'START AT ONE  ·  ADD TWO', (730, 770), 33, TEAL)
    else:
        raise ValueError('Unknown independent teaching oracle')
    blank = Image.new('RGB', SIZE, '#f9f0dd')
    return Image.blend(blank, target, alpha / 255)


def ticket_components(image):
    """Count green paired faces and the unique amber extra from actual pixels."""
    box = (120, 735, 1340, 832)
    crop = image.crop(box)
    width, height = crop.size
    result = {}
    for name, rgb in (('paired', (220, 233, 221)), ('extra', (243, 207, 145))):
        pending = {index for index, pixel in enumerate(crop.get_flattened_data())
                   if max(abs(a - b) for a, b in zip(pixel, rgb, strict=True)) <= 10}
        components = []
        while pending:
            seed = pending.pop()
            stack, points = [seed], [seed]
            while stack:
                point = stack.pop()
                x, y = point % width, point // width
                neighbors = []
                if x:
                    neighbors.append(point - 1)
                if x + 1 < width:
                    neighbors.append(point + 1)
                if y:
                    neighbors.append(point - width)
                if y + 1 < height:
                    neighbors.append(point + width)
                for other in neighbors:
                    if other in pending:
                        pending.remove(other)
                        stack.append(other)
                        points.append(other)
            if len(points) >= 100:
                xs, ys = [p % width for p in points], [p // width for p in points]
                components.append({'pixels': len(points), 'center': [(min(xs) + max(xs)) / 2 + box[0],
                                                                    (min(ys) + max(ys)) / 2 + box[1]]})
        result[name] = components
    return result


def check_ticket_pairs(image, quantity):
    require(quantity in (1, 5, 9), 'Odd ticket examples must contain one, five or nine tickets')
    components = ticket_components(image)
    require(len(components['extra']) == 1, 'An odd diagram must have exactly one amber ticket left over')
    require(len(components['paired']) == quantity - 1, f'Ticket total differs from {quantity}')
    columns = () if quantity == 1 else (480, 750) if quantity == 5 else (330, 520, 710, 900)
    expected = [(x, y) for x in columns for y in (764, 812)]
    actual = list(components['paired'])
    for center in expected:
        match = next((item for item in actual if max(abs(a - b) for a, b in
                     zip(item['center'], center, strict=True)) <= 4), None)
        require(match is not None, 'Paired tickets must form vertical groups of two')
        actual.remove(match)
    extra_x = 730 if quantity == 1 else 1040 if quantity == 5 else 1120
    require(max(abs(a - b) for a, b in zip(components['extra'][0]['center'], (extra_x, 785), strict=True)) <= 4,
            'The single extra ticket is misplaced')
    return {'quantity': quantity, 'vertical_pairs': len(columns), 'left_over': 1, 'components': components}


def native_semantics(plan, at):
    """Expected fixed header and diagram opacity from authored cue windows."""
    if at < 5:
        return None
    if at < 12.4:
        return 'ONE LEFT OVER', 1, 255, 255
    if at < 24.9:
        alpha = min(255, max(0, round(255 * (at - 12.4) / .5))) if at < 24.4 else max(0, 255 - round(255 * (at - 24.4) / .5))
        return 'ONE LEFT OVER', 5, alpha, 255
    if at < 36:
        return 'ONE LEFT OVER', 1, 255, 255
    for row in plan['scenes'][1:-1]:
        pause = row.get('teaching')
        if pause and pause['start_s'] <= at < pause['end_s']:
            age = at - pause['start_s']
            alpha = min(255, max(0, round(255 * age / .5))) if age < .5 else 255 if age < 7.4 else max(0, 255 - round(255 * (age - 7.4) / .5))
            return ('ONE LEFT OVER' if row['decimal_value'] == 9 else 'ODD NUMBER',
                    9 if row['decimal_value'] == 9 else 'bridge', alpha, min(255, max(0, round(255 * age / .5))))
    return 'ODD NUMBER', 'normal', 255, 255


def instruction_scores(image, header, kind, alpha, indicator=255):
    box = (150, 248, 1110, 291)
    header_score = shared.overlap(mask(image.crop(box)),
                                  text_mask(header, (680, 270), 26, MUTED, '#fffaf0', box))
    box = (128, 695, 1332, 848)
    expected = teaching_surface(kind, alpha, indicator).crop(box)
    surface_score = shared.overlap(mask(image.crop(box), 200), mask(expected, 200))
    return {'header_glyph_iou': header_score, 'independent_teaching_iou': surface_score}


def visual_checks(video, plan, ffmpeg, directory):
    values = episode_values(plan)
    errors, minimum = [], defaultdict(lambda: 1.0)
    counts = Counter()
    per_value = Counter()
    static_reference = None
    static_peak = 0
    opening, closing = [], []
    decoded = 0
    for index, image in decoded_frames(video, ffmpeg, 4, directory / 'all-frame-decode.log'):
        at = index / FPS
        decoded += 1
        if .8 <= at < plan['duration_s'] - 2:
            value = expected_value_at(plan, index)
            scores = field_scores(image, value, 4, count_end=values[-1])
            for name, score in scores.items():
                minimum[name] = min(minimum[name], score)
                counts[name] += 1
                threshold = .88 if name.startswith('ticket-') else .89
                if score < threshold and len(errors) < 100:
                    errors.append(f'Frame {index}/{name}/{value}: independent glyph IoU {score:.6f}')
            if at >= 36 and at < plan['scenes'][-1]['start_s']:
                per_value[value] += 1
            static = image.crop((355, 40, 475, 255))
            if static_reference is None:
                static_reference = static.copy()
            change = max(ImageStat.Stat(ImageChops.difference(static, static_reference)).mean)
            static_peak = max(static_peak, change)
            if change > 4 and len(errors) < 100:
                errors.append(f'Frame {index}: unexpected background or red-panda change {change:.4f}')
        if at < .8 or at >= plan['duration_s'] - 2:
            distance = sum(ImageStat.Stat(ImageChops.difference(image, Image.new('RGB', image.size, '#fff8e8'))).mean)
            (opening if at < .8 else closing).append(distance)
    require(decoded == plan['duration_frames'], 'Decoded frame count differs from the full expected frame grid')
    if set(per_value) != set(values):
        errors.append(f'Full-frame tracking did not see each of the {len(values)} odd count values')
    if any(right + .5 < left for left, right in zip(opening, opening[1:])):
        errors.append('Opening fade is unexpectedly nonmonotonic')
    if any(right > left + .5 for left, right in zip(closing, closing[1:])):
        errors.append('Closing fade is unexpectedly nonmonotonic')
    native_times = [5.2, 12.65, 13.2, 23.7, 24.65, 25.1]
    native_times.extend(plan['scenes'][-1]['start_s'] + offset for offset in (.9, 1.1))
    for row in plan['scenes'][1:-1]:
        if row.get('teaching'):
            native_times.extend(row['teaching']['start_s'] + offset for offset in (.25, .75, 3, 7.65, 7.95))
    native_indices = sorted({frame_at(at) for at in native_times} | {plan['duration_frames'] - 1})
    native_records, thumbnails = [], []
    for index, image in decoded_frames(video, ffmpeg, 1, directory / 'native-decode.log', native_indices):
        at = index / FPS
        record = {'frame': index, 'at_s': at}
        if index == plan['duration_frames'] - 1:
            error = [max(channel.getextrema()) for channel in ImageChops.difference(image, Image.new('RGB', SIZE, '#fff8e8')).split()]
            record['cream_max_rgb_error'] = error
            if max(error) > 5:
                errors.append('Closing frame retains a visible image rather than uniform cream')
        elif at >= plan['scenes'][-1]['start_s']:
            expected_stamp = at >= plan['scenes'][-1]['start_s'] + 1
            box = (1153, 737, 1287, 781)
            expected = text_mask(str(values[-1]) if expected_stamp else '', (1220, 758), 37, TEAL,
                                 '#e1eddf' if expected_stamp else '#f9f0dd', box)
            score = shared.overlap(mask(image.crop(box)), expected)
            record.update(completed_stamp_expected=expected_stamp, completed_stamp_iou=score)
            if score < .95:
                errors.append(f'Native frame {index}: completion stamp has wrong value or timing')
        else:
            header, kind, alpha, indicator = native_semantics(plan, at)
            scores = instruction_scores(image, header, kind, alpha, indicator)
            header_score = scores['header_glyph_iou']
            record.update(header=header, header_glyph_iou=header_score, teaching_kind=kind, alpha=alpha)
            if header_score < .95:
                errors.append(f'Native frame {index}: header differs or contains overlapping labels ({header_score:.6f})')
            surface_score = scores['independent_teaching_iou']
            record['independent_teaching_iou'] = surface_score
            if surface_score < .88:
                errors.append(f'Native frame {index}: diagram/normal instruction overlap or teaching mismatch ({surface_score:.6f})')
            if kind in (1, 5, 9) and alpha == 255:
                try:
                    record['independent_ticket_quantity'] = check_ticket_pairs(image, kind)
                except ValueError as error:
                    errors.append(f'Native frame {index}: {error}')
            if kind == 'bridge' and alpha == 255:
                bridge = []
                for number, center in zip((99, 100, 101), (430, 730, 1030), strict=True):
                    box = (center - 88, 752, center + 88, 797)
                    score = shared.overlap(mask(image.crop(box), 200), text_mask(str(number), (center, 775), 42,
                                           '#aaa596' if number == 100 else TEAL,
                                           '#f0eee4' if number == 100 else '#e1efdf', box, 1, 200))
                    bridge.append({'value': number, 'odd': number % 2 == 1, 'iou': score})
                    if score < .95:
                        errors.append(f'Native frame {index}: bridge number {number} is wrong')
                record['bridge_values'] = bridge
        native_records.append(record)
        path = directory / f'native-frame-{index:06d}.png'
        image.save(path)
        thumb = image.copy()
        thumb.thumbnail((640, 360))
        thumbnails.append((index, thumb))
    contact = Image.new('RGB', (1280, math.ceil(len(thumbnails) / 2) * 390), '#fff8e8')
    draw = ImageDraw.Draw(contact)
    for ordinal, (index, image) in enumerate(thumbnails):
        x, y = ordinal % 2 * 640, ordinal // 2 * 390
        contact.paste(image, (x, y))
        draw.text((x + 10, y + 362), f'frame {index} / {index / FPS:.3f}s', fill='black')
    contact.save(directory / 'scene-contact-sheet.png')
    return {'passed': not errors, 'decoded_frames': decoded, 'all_frame_field_checks': dict(counts),
            'minimum_independent_glyph_iou': dict(minimum), 'per_count_value_frames': dict(per_value),
            'static_background_and_character_peak_mean_change': static_peak,
            'native_samples': native_records, 'closing_fade_monotonic': not any(b > a + .5 for a, b in zip(closing, closing[1:])),
            'producer_scene_or_word_function_used_for_expected_values': False, 'errors': errors}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', required=True, type=Path)
    parser.add_argument('--video', required=True, type=Path)
    parser.add_argument('--master', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--delivery-dir', type=Path)
    parser.add_argument('--script', type=Path)
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg'))
    parser.add_argument('--ffprobe', default=shutil.which('ffprobe'))
    parser.add_argument('--work-dir', type=Path, default=Path('D:/temp/odd-video-qa'))
    args = parser.parse_args(argv)
    plan = json.loads(args.timeline.read_text(encoding='utf-8-sig'))
    events, schedule = validate_schedule(plan)
    script = args.script or ROOT / plan.get('source_script', {}).get('path', 'design/odd-counting-v1/script-and-sound-cues.txt')
    if plan.get('source_script', {}).get('sha256'):
        require(shared.technical.sha256_file(script) == plan['source_script']['sha256'], 'Authored script hash differs from the timeline')
    schedule['authored_dialogue_checked'] = authored_dialogue(events, script, plan)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    require(not (args.output_dir / 'odd-final-qa.json').exists(), 'Refusing to overwrite an existing final QA')
    pcm_contract = pcm_contract_checks(events, args.master, plan['duration_s'])
    tech = shared.technical.verify_video(args.video, args.output_dir, args.timeline, args.ffmpeg, args.ffprobe,
                                         duration_bounds=(max(1, schedule['minimum_duration_s']), 900))
    visual = visual_checks(args.video, plan, args.ffmpeg, args.output_dir)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='verify-', dir=args.work_dir) as temporary:
        directory = Path(temporary)
        clips = shared.source_references(events, args.ffmpeg, directory)
        master = shared.stereo_audio_checks(args.master, events, clips, plan['duration_s'], args.ffmpeg, directory, False)
        encoded = shared.stereo_audio_checks(args.video, events, clips, plan['duration_s'], args.ffmpeg, directory, True)
    captions = caption_checks(plan, args.delivery_dir or args.video.parent)
    metadata = metadata_checks(plan, args.delivery_dir or args.video.parent, args.video.name)
    checks = {'technical_media': tech['status'] == 'pass', 'all_frame_visual': visual['passed'],
              'uniform_frame_timestamps': shared.visual_shared.check_video_timestamps(args.video, plan['duration_s'], args.ffprobe),
              'master_audio': master['passed'], 'final_aac_audio': encoded['passed'],
              'original_pcm_contract': pcm_contract['passed'],
              'captions': captions['passed'], 'delivery_metadata': metadata['passed']}
    report = {'schema_version': 1, 'status': 'pass' if all(checks.values()) else 'fail', 'checks': checks,
              'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'schedule': schedule,
              'visual': visual, 'master': master, 'encoded_audio': encoded, 'captions': captions,
              'original_pcm_contract': pcm_contract,
              'delivery_metadata': metadata, 'video_sha256': shared.technical.sha256_file(args.video),
              'timeline_sha256': shared.technical.sha256_file(args.timeline),
              'verifier_sha256': shared.technical.sha256_file(Path(__file__)),
              'scope': f'Full media decode; every decoded frame tracked against independently constructed odd numerals, US cardinals and seven-integer number line before closing fade; native ticket diagrams and partial fades; {len(events)} source voices against both stereo channels of master and final AAC; silence, subtitles and delivery metadata.',
              'fresh_asr_or_full_human_listening_claimed': False}
    destination = args.output_dir / 'odd-final-qa.json'
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'report': str(destination), 'checks': checks,
                      'visual_errors': len(visual['errors']), 'aac_minimum_source_correlation': encoded['minimum_correlation']}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
