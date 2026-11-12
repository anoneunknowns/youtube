"""Independent finite-math, decoded-pixel and audio verification for Collatz.

No Collatz producer or renderer is imported.  The measured timeline is checked
against a new integer trace and inverse English parser; glyphs are separately
rasterized from the licensed font and observed in the encoded movie.
"""
from __future__ import annotations

import argparse
from array import array
from bisect import bisect_right
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
import gzip
import hashlib
import inspect
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import wave

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat, ImageOps, ImageMath

if __package__:
    from .component_alignment import raster_centering_report
    from . import verify_video as technical
else:
    from component_alignment import raster_centering_report
    import verify_video as technical

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/collatz-counting-v1'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
BACKDROP = DESIGN / 'generation-batches/collatz-preproduction-20261112-01a1cd57/source/waterworks-clean-plate.png'
FPS, RATE, SIZE = 30, 48000, (1920, 1080)
INK, TEAL, CLAY, BLUE = '#344f54', '#267b80', '#ad6143', '#537ca0'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def path_of(path):
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def sample(seconds):
    return round(seconds * RATE)


def first_frame(seconds):
    return math.ceil(seconds * FPS - 1e-7)


def independent_trace(seed):
    """Unaccelerated recurrence, stopping on first one; integer-only."""
    values = [seed]
    while values[-1] != 1:
        previous = values[-1]
        next_value = previous >> 1 if previous & 1 == 0 else previous + previous + previous + 1
        require(next_value > 0, 'Non-positive integer in trace')
        require((next_value * 2 == previous) if previous % 2 == 0 else ((next_value - 1) // 3 == previous), 'Inverse trace identity failed')
        values.append(next_value)
        require(len(values) < 10000, 'Finite trace guard exceeded')
    return values


SMALL = dict(zip(('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen').split(), range(20)))
TENS = dict(zip(('twenty thirty forty fifty sixty seventy eighty ninety').split(), range(20, 100, 10)))


def parse_under_thousand(tokens):
    require(tokens, 'Empty number group')
    hundreds = 0
    if len(tokens) >= 2 and tokens[1] == 'hundred':
        require(tokens[0] in SMALL and 1 <= SMALL[tokens[0]] <= 9, 'Invalid hundreds coefficient')
        hundreds = 100 * SMALL[tokens[0]]
        tokens = tokens[2:]
        if not tokens:
            return hundreds
    if len(tokens) == 1 and tokens[0] in SMALL:
        require(not hundreds or SMALL[tokens[0]] > 0, 'Redundant zero after hundred')
        return hundreds + SMALL[tokens[0]]
    require(len(tokens) in (1, 2) and tokens[0] in TENS, 'Invalid US-English number grammar')
    units = 0
    if len(tokens) == 2:
        require(tokens[1] in SMALL and 1 <= SMALL[tokens[1]] <= 9, 'Invalid tens units')
        units = SMALL[tokens[1]]
    return hundreds + TENS[tokens[0]] + units


def parse_cardinal(text):
    tokens = text.lower().replace('-', ' ').split()
    require('and' not in tokens, 'Unexpected and in US-English cardinal')
    if 'thousand' in tokens:
        require(tokens.count('thousand') == 1, 'Repeated thousand')
        split = tokens.index('thousand')
        coefficient = parse_under_thousand(tokens[:split])
        require(coefficient > 0, 'Zero thousand coefficient')
        return coefficient * 1000 + (parse_under_thousand(tokens[split + 1:]) if tokens[split + 1:] else 0)
    return parse_under_thousand(tokens)


def count_identity(row):
    match = re.fullmatch(r'C(7|27)_(\d{3})', row['id'])
    require(match, f'Invalid count cue {row["id"]}')
    return int(match[1]), int(match[2])


def equation(previous, result):
    return f'{previous:,} × 3 + 1 = {result:,}' if previous % 2 else f'{previous:,} ÷ 2 = {result:,}'


def validate_script():
    script_path = DESIGN / 'script/script.json'
    script = json.loads(script_path.read_text())
    rows = script['events']
    counts = [row for row in rows if row['kind'] == 'count']
    truths = {seed: independent_trace(seed) for seed in (7, 27)}
    expected_ids = [f'C{seed}_{i:03}' for seed, values in truths.items() for i in range(len(values))]
    require([r['id'] for r in counts] == expected_ids, 'Script count scope/order differs from independent trace')
    require(len(rows) == 143 and len({r['id'] for r in rows}) == 143, 'Script must have 143 unique cues')
    for row in counts:
        seed, index = count_identity(row)
        value = truths[seed][index]
        require((row['value'], row['index'], row['term_ordinal'], row['step_number']) == (value, index, index + 1, index), f'Script number/index mismatch {row["id"]}')
        require(row['display'] == f'{value:,}' and parse_cardinal(row['text']) == value, f'Script display/words mismatch {row["id"]}')
        incoming = None if index == 0 else equation(truths[seed][index - 1], value)
        require(row.get('incoming_equation') == incoming, f'Incoming equation differs {row["id"]}')
    require((len(truths[7]), len(truths[27]), max(truths[27]), truths[27].index(9232)) == (17, 112, 9232, 77), 'Independent finite trace landmarks differ')
    return script, truths, {'passed': True, 'script_path': str(script_path.relative_to(ROOT)), 'script_sha256': sha(script_path),
                            'counted_occurrences': 129, 'transitions': 127, 'distinct_values': len(set(truths[7] + truths[27])),
                            'method': 'new exact-integer recurrence using shift/addition, reverse arithmetic identities, strict inverse US-English cardinal parser',
                            'scope': 'Finite seeds7 and27 only; no proof for all positive integers'}


def validate_schedule(plan):
    script, truths, math_report = validate_script()
    events = plan.get('voice_events', plan.get('events'))
    require(isinstance(events, list), 'No measured voice events')
    if 'events' in plan and 'voice_events' in plan:
        require(plan['events'] == plan['voice_events'], 'Timeline event aliases differ')
    expected = script['events']
    require([r['id'] for r in events] == [r['id'] for r in expected], 'Measured cue order/scope differs from authored143 cues')
    require(plan['fps'] == FPS and plan['duration_frames'] == math.ceil(plan['duration_s'] * FPS - 1e-7), 'Timeline fps/frame count differs')
    require(plan['duration_s'] >= 480, 'Completed episode must be at least eight minutes')
    count_rows, cue_rows = [], {r['id']: r for r in events}
    previous_end = 0
    for event, authored in zip(events, expected):
        require(event['start_s'] >= previous_end - 1 / RATE, f'Voice overlap {event["id"]}')
        require(0 <= event['start_s'] < event['end_s'] <= plan['duration_s'], f'Voice outside timeline {event["id"]}')
        require(event['text'] == authored['text'] and event.get('spoken_text', event['text']) == authored['text'], f'Actual cue text differs {event["id"]}')
        require(abs(event['end_s'] - event['start_s'] - event['duration_s']) <= 1 / RATE, f'Measured cue duration differs {event["id"]}')
        source = path_of(event['source_path'])
        require(sha(source) == event['source_sha256'], f'Adopted source changed {event["id"]}')
        with wave.open(str(source), 'rb') as reader:
            actual_duration = reader.getnframes() / reader.getframerate()
        require(abs(actual_duration - event['duration_s']) <= 2 / RATE, f'Actual source length differs {event["id"]}')
        if authored['kind'] == 'count':
            seed, index = count_identity(event)
            value = truths[seed][index]
            require(event['value'] == value and event['index'] == index and event['display'] == f'{value:,}', f'Measured count value differs {event["id"]}')
            require(parse_cardinal(event['text']) == value, f'Measured words differ {event["id"]}')
            require(abs(event['start_s'] - event['result_start_s'] - .12) <= 1 / RATE, f'Result lead differs {event["id"]}')
            if index:
                require(event['operation_start_s'] < event['result_start_s'], f'Operation has no active interval {event["id"]}')
            else:
                require(event['operation_start_s'] is None, f'A new seed cannot inherit a Collatz operation {event["id"]}')
            count_rows.append(event)
        previous_end = event['end_s']
    ordinary, explained = [], []
    lessons = {r['after']: r['cue'] for r in script['edit_policy']['explanation_boundaries']}
    for left, right in zip(count_rows, count_rows[1:]):
        seed_a, _ = count_identity(left)
        seed_b, _ = count_identity(right)
        if seed_a != seed_b:
            bridge = cue_rows['B01']
            require(left['value'] == 1 and right['value'] == 27, 'Journey boundary differs')
            require(abs(bridge['start_s'] - left['end_s'] - .5) <= 1 / RATE and abs(right['start_s'] - bridge['end_s'] - 1.5) <= 1 / RATE, 'New journey bridge timing differs')
            continue
        actual = right['start_s'] - left['end_s']
        if left['id'] in lessons:
            lesson = cue_rows[lessons[left['id']]]
            require(abs(lesson['start_s'] - left['end_s'] - .5) <= 1 / RATE and abs(right['start_s'] - lesson['end_s'] - 1.5) <= 1 / RATE, f'Explanation boundary differs {left["id"]}')
            require(right['operation_start_s'] >= lesson['end_s'] - 1 / RATE, f'Next calculation overlaps explanation replay {right["id"]}')
            require(abs(right['operation_start_s'] - lesson['end_s'] - .22) <= 1 / RATE, f'Explanation operation onset must be end+.22: {right["id"]}')
            explained.append({'after': left['id'], 'cue': lesson['id'], 'gap_s': actual, 'explaining_s': lesson['duration_s']})
        else:
            require(abs(actual - 2) <= 1 / RATE, f'Ordinary gap differs {left["id"]}: {actual}')
            require(right['operation_start_s'] >= left['end_s'] - 1 / RATE, f'Calculation starts before prior voice ends {right["id"]}')
            require(abs(right['operation_start_s'] - left['end_s'] - .22) <= 1 / RATE, f'Ordinary operation onset must be prior end+.22: {right["id"]}')
            ordinary.append({'after': left['id'], 'gap_s': actual})
    require(len(ordinary) == 123 and len(explained) == 4, 'Expected123 ordinary and4 explained within-tour boundaries')
    states = plan.get('counted_states', [])
    require([r['id'] for r in states] == [r['id'] for r in count_rows], 'Counted-state scope differs')
    for ordinal, (state, event) in enumerate(zip(states, count_rows)):
        seed, index = count_identity(event)
        previous = truths[seed][index - 1] if index else None
        require((state['value'], state['index'], state['term_ordinal'], state['step_number']) == (truths[seed][index], index, index + 1, index), f'Counted-state value/index differs {event["id"]}')
        require(state['seed'] == seed, f'Counted-state seed differs {event["id"]}')
        require(state['previous_value'] == previous, f'New journey has a prior operation or previous value differs {event["id"]}')
        require(state['previous_index'] == (index - 1 if index else None), f'Previous index differs {event["id"]}')
        require(state['incoming_rule'] == (None if previous is None else 'odd' if previous % 2 else 'even'), f'Incoming rule differs {event["id"]}')
        require(state['display'] == f"{event['value']:,}" and state['text'] == event['text'] and state['sequence_id'] == f'seed-{seed}', f'Counted state display/reading/journey differs {event["id"]}')
        require(state['voice_event_id'] == event['id'], f'State voice binding differs {event["id"]}')
        for key, expected_time in [('result_start_s', event['result_start_s']), ('start_s', event['result_start_s']),
                                   ('display_start_s', event['result_start_s']), ('voice_start_s', event['start_s']),
                                   ('voice_end_s', event['end_s'])]:
            require(abs(state[key] - expected_time) <= 1 / RATE, f'Counted-state timestamp differs {event["id"]}/{key}')
        require(state['operation_start_s'] == event['operation_start_s'], f'State operation timestamp differs {event["id"]}')
        if ordinal + 1 < len(count_rows) and count_identity(count_rows[ordinal + 1])[0] == seed:
            expected_end = count_rows[ordinal + 1]['result_start_s']
        else:
            expected_end = cue_rows['B01' if seed == 7 else 'O01']['start_s'] - .12
        require(abs(state['end_s'] - expected_end) <= 1 / RATE and abs(state['display_end_s'] - expected_end) <= 1 / RATE, f'Counted-state display end differs {event["id"]}')
        work_value = None if previous is None else 3 * previous if previous % 2 else previous // 2
        require(state['intermediate_value'] == work_value, f'Calculation-work state differs {event["id"]}')
        require(abs(state['progress_commit_s'] - event['end_s']) <= 1 / RATE, f'Progress commit must follow completed voice {event["id"]}')
    require(abs(events[0]['start_s'] - .8) <= 1 / RATE, 'Opening voice onset differs')
    for left_id, right_id, gap in [('I01', 'I02', .6), ('I02', 'I03', .6), ('I03', 'I04', .6), ('I04', 'I05', .6), ('I05', 'I06', .6), ('I06', 'C7_000', .6), ('C27_111', 'O01', .5), ('O01', 'O02', .6), ('O02', 'O03', .6)]:
        require(abs(cue_rows[right_id]['start_s'] - cue_rows[left_id]['end_s'] - gap) <= 1 / RATE, f'Scripted chapter boundary differs {left_id}→{right_id}')
    require(abs(plan['duration_s'] - cue_rows['O03']['end_s'] - .8) <= 1 / RATE, 'Final hold differs')
    math_report['measured_cues_match'] = True
    timing = {'passed': True, 'voice_events': 143, 'normal_two_second_boundaries': len(ordinary), 'explained_boundaries': explained,
              'within_tour_boundaries': 127, 'new_journey_bridge_not_a_collatz_operation': True,
              'normal_boundary_min_s': min(r['gap_s'] for r in ordinary), 'normal_boundary_max_s': max(r['gap_s'] for r in ordinary),
              'duration_s': plan['duration_s'], 'frames': plan['duration_frames'], 'result_lead_s': .12}
    timing.update(operation_start_contract='exactly prior count end+.22, or explanation end+.22 at four explicit boundaries',
                  all_counted_state_fields_checked=True)
    return events, count_rows, truths, math_report, timing


def srt_seconds(text):
    h, m, tail = text.split(':')
    sec, ms = tail.split(',')
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000


def captions_checks(events, captions):
    raw = Path(captions).read_text(encoding='utf-8-sig').strip()
    blocks = re.split(r'\n\s*\n', raw)
    require(len(blocks) == len(events), 'SRT cue count differs')
    checks = []
    for i, (block, event) in enumerate(zip(blocks, events), 1):
        lines = block.splitlines()
        require(int(lines[0]) == i and len(lines) >= 3, f'Invalid SRT cue {i}')
        start, end = map(srt_seconds, lines[1].split(' --> '))
        text = '\n'.join(lines[2:])
        require(text == event.get('subtitle_text', event['text']), f'SRT text differs {event["id"]}')
        require(abs(start - event['start_s']) <= .0011 and abs(end - event['end_s']) <= .0011, f'SRT time differs {event["id"]}')
        checks.append({'id': event['id'], 'start_s': start, 'end_s': end, 'text': text, 'passed': True})
    return {'passed': True, 'path': str(captions), 'sha256': sha(captions), 'cue_count': len(checks), 'timestamp_tolerance_s': .0011, 'cues': checks}


def pcm16(data):
    values = array('h')
    values.frombytes(data)
    if __import__('sys').byteorder != 'little':
        values.byteswap()
    return values


def correlation(reference, observed, guard=8, stride=16):
    ref = reference[::stride]
    energy = sum(v * v for v in ref)
    best = (-1, 0, 0)
    for lag in range(-guard, guard + 1):
        obs = observed[guard + lag:guard + lag + len(reference):stride]
        if len(obs) != len(ref):
            continue
        actual_energy = sum(v * v for v in obs)
        if not actual_energy or not energy:
            continue
        corr = sum(a * b for a, b in zip(ref, obs)) / math.sqrt(energy * actual_energy)
        if corr > best[0]:
            best = corr, lag, 10 * math.log10(actual_energy / energy)
    return best


def audio_checks(plan, events, video, master, ffmpeg, directory, include_final_aac=True):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    references, outcomes = {}, []
    with tempfile.TemporaryDirectory(prefix='collatz-independent-audio-') as temp:
        temp = Path(temp)
        for event in events:
            source = path_of(event['source_path'])
            if source in references:
                continue
            destination = temp / f'reference-{len(references):03}.wav'
            subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-xerror', '-n', '-i', str(source), '-ar', str(RATE), '-ac', '2', '-c:a', 'pcm_s16le', str(destination)], check=True)
            with wave.open(str(destination), 'rb') as reader:
                references[source] = pcm16(reader.readframes(reader.getnframes()))[::2]
        tracks = [('master', master, False)] + ([('final-aac', video, True)] if include_final_aac else [])
        for name, source, lossy in tracks:
            destination = temp / f'{name}.wav'
            subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-xerror', '-n', '-i', str(source), '-map', '0:a:0', '-ar', str(RATE), '-ac', '2', '-c:a', 'pcm_s16le', str(destination)], check=True)
            rows, silence, cursor = [], [], 0
            guard = sample(.03 if lossy else .002)
            with wave.open(str(destination), 'rb') as reader:
                require(abs(reader.getnframes() - sample(plan['duration_s'])) <= (2048 if lossy else 1), f'{name} endpoint differs from timeline')
                for event in events:
                    start, end = sample(event['start_s']), sample(event['end_s'])
                    reference = references[path_of(event['source_path'])]
                    require(abs(len(reference) - (end - start)) <= 2, f'Reference length differs {event["id"]}')
                    a, b = cursor + (guard if cursor else 0), start - guard
                    if b > a:
                        reader.setpos(a)
                        peak = max(map(abs, pcm16(reader.readframes(b - a))), default=0)
                        silence.append({'start_s': a / RATE, 'end_s': b / RATE, 'peak_pcm16': peak})
                    reader.setpos(max(0, start - 8))
                    actual = pcm16(reader.readframes(len(reference) + 16))
                    channels = [correlation(reference, actual[channel::2]) for channel in (0, 1)]
                    require(min(item[0] for item in channels) >= .97, f'{name} waveform differs {event["id"]}: {channels}')
                    common = plan.get('master', {}).get('common_gain_db', plan.get('common_gain_db', 0))
                    gain = event.get('mix_gain_db', 0) + common
                    require(all(abs(item[2] - gain) <= (.35 if lossy else .06) for item in channels), f'{name} gain differs {event["id"]}: observed{channels}, expected{gain}')
                    rows.append({'id': event['id'], 'source_sha256': event['source_sha256'], 'left_correlation': channels[0][0], 'right_correlation': channels[1][0],
                                 'left_lag_samples': channels[0][1], 'right_lag_samples': channels[1][1], 'left_gain_db': channels[0][2], 'right_gain_db': channels[1][2],
                                 'expected_gain_db': gain, 'stereo_gain_difference_db': abs(channels[0][2] - channels[1][2])})
                    cursor = end
                if cursor + guard < reader.getnframes():
                    reader.setpos(cursor + guard)
                    silence.append({'start_s': (cursor + guard) / RATE, 'end_s': reader.getnframes() / RATE, 'peak_pcm16': max(map(abs, pcm16(reader.readframes(reader.getnframes()))), default=0)})
            peak = max((r['peak_pcm16'] for r in silence), default=0)
            require(peak <= (3 if lossy else 1), f'{name} unexpected sound outside cues: peak{peak}')
            report = {'passed': True, 'path': str(source), 'sha256': sha(source), 'events': rows, 'silence_intervals': silence,
                      'minimum_waveform_correlation': min(min(r['left_correlation'], r['right_correlation']) for r in rows),
                      'maximum_silent_interior_peak_pcm16': peak, 'boundary_guard_s': guard / RATE,
                      'maximum_left_right_gain_difference_db': max(r['stereo_gain_difference_db'] for r in rows),
                      'source_channel_mapping': 'FFmpeg48k stereo reference; mono→stereo equal-power upmix applied before declared per-clip/common gain',
                      'asr_or_human_listening_claimed': False}
            save(directory / f'{name}.json', report)
            outcomes.append(report)
    return {'passed': True, 'tracks': outcomes, 'scope': 'All143 exact-source WAV waveforms against ' + ('master and both decoded final AAC channels' if include_final_aac else 'master only; final AAC not yet available') + '; gains, synchronization and all guarded silent interiors. New ASR/CTC is separate.'}


def export_final_aac_clips(plan, events, video, ffmpeg, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    manifest = {'schema_version': 1, 'kind': 'collatz-final-aac-excerpts', 'measurement_status': 'measured', 'numbers': [], 'dialogue': [],
                'source_video_sha256': sha(video), 'scope': 'Actual final AAC left channel with at most80ms context. Fresh unconstrained ASR/CTC inputs; not adopted source WAVs.'}
    with tempfile.TemporaryDirectory(prefix='collatz-final-aac-') as temp:
        decoded = Path(temp) / 'final.wav'
        subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-xerror', '-i', str(video), '-map', '0:a:0', '-ar', str(RATE), '-ac', '2', '-c:a', 'pcm_s16le', str(decoded)], check=True)
        with wave.open(str(decoded), 'rb') as reader:
            for i, event in enumerate(events):
                previous = events[i - 1]['end_s'] if i else 0
                following = events[i + 1]['start_s'] if i + 1 < len(events) else plan['duration_s']
                start = sample(event['start_s'] - min(.08, max(0, (event['start_s'] - previous) / 2)))
                end = sample(event['end_s'] + min(.08, max(0, (following - event['end_s']) / 2)))
                reader.setpos(start)
                pcm = array('h', pcm16(reader.readframes(end - start))[::2])
                target = out_dir / f'{event["id"]}.wav'
                with wave.open(str(target), 'wb') as clip:
                    clip.setparams((1, 2, RATE, len(pcm), 'NONE', 'not compressed'))
                    clip.writeframes(pcm.tobytes())
                row = {'id': event['id'], 'text': event['text'], 'spoken_text': event['text'], 'path': str(target.resolve()),
                       'sha256': sha(target), 'duration_s': len(pcm) / RATE, 'clip_duration_s': len(pcm) / RATE,
                       'event_start_s': event['start_s'], 'event_end_s': event['end_s'], 'excerpt_start_s': start / RATE, 'excerpt_end_s': end / RATE,
                       'speech_offset_s': event['start_s'] - start / RATE, 'number': event.get('value'), 'index': event.get('index')}
                manifest['numbers' if event['id'].startswith('C') else 'dialogue'].append(row)
    save(out_dir / 'measurements.json', manifest)
    save(out_dir / 'final-aac-manifest.json', manifest)
    save(out_dir / 'takes.json', [{'id': row['id'], 'text': row['text'], 'path': str(path_of(row['path'])), 'sha256': row['sha256']} for row in manifest['numbers'] + manifest['dialogue']])
    return {'manifest': str(out_dir / 'final-aac-manifest.json'), 'events': len(events), 'source_video_sha256': manifest['source_video_sha256']}


@lru_cache(maxsize=64)
def font(size):
    return ImageFont.truetype(str(FONT), size)


@lru_cache(maxsize=8192)
def glyph_alpha(text, size):
    if '\n' in text:
        pieces = [glyph_alpha(line, size) for line in text.split('\n')]
        bounds = [piece.point(lambda a: 255 if a >= 128 else 0).getbbox() for piece in pieces]
        width = max(b[2] - b[0] for b in bounds)
        height = sum(b[3] - b[1] for b in bounds) + 14 * (len(pieces) - 1)
        result = Image.new('L', (width + 64, height + 64))
        y = 32
        for piece, b in zip(pieces, bounds):
            result.paste(piece.crop(b), (round(32 + (width - b[2] + b[0]) / 2), y))
            y += b[3] - b[1] + 14
        return result
    face = font(size)
    b = face.getbbox(text)
    result = Image.new('L', (b[2] - b[0] + 64, b[3] - b[1] + 64))
    ImageDraw.Draw(result).text((32 - b[0], 32 - b[1]), text, font=face, fill=255)
    return result


def rgb(color):
    return tuple(bytes.fromhex(color.lstrip('#')))


def observed_ink(image, color, fill='#fffaf0'):
    """Observed foreground color cores; no producer masks or parent borders."""
    fg, bg = rgb(color), rgb(fill)
    channel = max(range(3), key=lambda k: abs(bg[k] - fg[k]))
    midpoint = (bg[channel] + fg[channel]) / 2
    result = image.getchannel(channel).point(lambda value: 255 if (value < midpoint if fg[channel] < bg[channel] else value > midpoint) else 0)
    for part, target in zip(image.split(), fg):
        result = ImageChops.darker(result, part.point(lambda value, target=target: 255 if abs(value - target) <= 78 else 0))
    return result


@lru_cache(maxsize=2)
def backdrop(divisor):
    source = ImageOps.fit(Image.open(BACKDROP).convert('RGB'), SIZE, Image.Resampling.LANCZOS)
    return source if divisor == 1 else source.resize((SIZE[0] // divisor, SIZE[1] // divisor), Image.Resampling.BOX)


def component_ink(image, row, observation, divisor):
    """Infer foreground coverage along the known backdrop→ink RGB vector.

    The clean art is independently resized from the immutable source. This
    removes matching-color pipes or texture without any expected glyph shape.
    """
    area = tuple(v // divisor for v in observation)
    actual = image.crop(area)
    base = Image.new('RGB', actual.size, row['fill']) if row.get('fill') else backdrop(divisor).crop(area)
    target = rgb(row.get('color', INK))
    inputs = {f'b{i}': channel.convert('I') for i, channel in enumerate(base.split())}
    inputs.update({f'c{i}': channel.convert('I') for i, channel in enumerate(actual.split())})
    def coverage(env):
        if divisor == 1 and row.get('native_luminance'):
            weights = (2126, 7152, 722)
            base_y = sum(env[f'b{i}'] * weights[i] for i in range(3))
            actual_y = sum(env[f'c{i}'] * weights[i] for i in range(3))
            ink_y = sum(target[i] * weights[i] for i in range(3))
            return (base_y - actual_y) * 255 / (base_y - ink_y + 1)
        direction = [env[f'b{i}'] - target[i] for i in range(3)]
        difference = [env[f'b{i}'] - env[f'c{i}'] for i in range(3)]
        return sum(d * v for d, v in zip(direction, difference)) * 255 / (sum(d * d for d in direction) + 1)
    alpha = ImageMath.lambda_eval(coverage, **inputs).convert('L')
    result = alpha.point(lambda value: 255 if value >= 128 else 0)
    if divisor == 1 and row.get('native_luminance'):
        return result
    for channel, color in zip(actual.split(), target):
        result = ImageChops.darker(result, channel.point(lambda value, color=color: 255 if abs(value - color) <= 90 else 0))
    return result


def iou(actual, expected):
    union = ImageChops.lighter(actual, expected).histogram()[255]
    return ImageChops.darker(actual, expected).histogram()[255] / union if union else 0


@lru_cache(maxsize=4096)
def label_reference(text, size, box, divisor=1, shift_x=0, shift_y=0, margin=4):
    alpha = glyph_alpha(text, size)
    b = alpha.point(lambda value: 255 if value >= 128 else 0).getbbox()
    origin = (round((box[0] + box[2] - b[0] - b[2]) / 2), round((box[1] + box[3] - b[1] - b[3]) / 2))
    visible = (b[0] + origin[0], b[1] + origin[1], b[2] + origin[0], b[3] + origin[1])
    observation = (max(0, (visible[0] - margin) // divisor * divisor), max(0, (visible[1] - margin) // divisor * divisor),
                   min(SIZE[0], math.ceil((visible[2] + margin) / divisor) * divisor), min(SIZE[1], math.ceil((visible[3] + margin) / divisor) * divisor))
    expected = Image.new('L', (observation[2] - observation[0], observation[3] - observation[1]))
    expected.paste(alpha, (origin[0] - observation[0] + shift_x, origin[1] - observation[1] + shift_y))
    if divisor != 1:
        expected = expected.resize((expected.width // divisor, expected.height // divisor), Image.Resampling.BOX)
    return expected.point(lambda a: 255 if a >= 128 else 0), observation


def inspect_label(image, row, frame, divisor=1, alignment=True):
    box = tuple(row['box'])
    margin = 2 if row['name'] in ('route-start', 'route-end') else 4
    expected, observation = label_reference(row['text'], row['size'], box, divisor, margin=margin)
    actual = component_ink(image, row, observation, divisor)
    scores = [(iou(actual, label_reference(row['text'], row['size'], box, divisor, dx, dy, margin)[0]), dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
    score, dx, dy = max(scores)
    threshold = .91 if divisor == 1 else .82
    nonempty = actual.getbbox() is not None
    result = {'name': row['name'], 'numeric_role': row.get('numeric_role'), 'frame': frame, 'time_s': frame / FPS, 'text': row['text'], 'font_size_px': row['size'],
              'content_box_xyxy': list(box), 'observation_box_xyxy': list(observation), 'resolution_divisor': divisor,
              'independent_glyph_iou': score, 'minimum_glyph_iou': threshold, 'best_template_shift_px': [dx, dy], 'nonempty': nonempty,
              'passed': nonempty and score >= threshold}
    character_rows = []
    if '\n' not in row['text']:
        alpha = glyph_alpha(row['text'], row['size'])
        bounds = alpha.point(lambda a: 255 if a >= 128 else 0).getbbox()
        origin = (round((box[0] + box[2] - bounds[0] - bounds[2]) / 2), round((box[1] + box[3] - bounds[1] - bounds[3]) / 2))
        face = font(row['size'])
        font_box = face.getbbox(row['text'])
        baseline = (origin[0] + 32 - font_box[0], origin[1] + 32 - font_box[1])
        shifted_expected = label_reference(row['text'], row['size'], box, divisor, dx, dy, margin)[0]
        for k, character in enumerate(row['text']):
            if character.isspace():
                continue
            b = face.getbbox(character)
            advance = face.getlength(row['text'][:k])
            rect = (math.floor((baseline[0] + advance + b[0] - observation[0] - 1) / divisor),
                    math.floor((baseline[1] + b[1] - observation[1] - 1) / divisor),
                    math.ceil((baseline[0] + advance + b[2] - observation[0] + 1) / divisor),
                    math.ceil((baseline[1] + b[3] - observation[1] + 1) / divisor))
            char_score = iou(actual.crop(rect), shifted_expected.crop(rect))
            char_limit = (.80 if row['size'] >= 26 else .70) if divisor == 1 else .60
            character_rows.append({'position': k, 'character': character, 'iou': char_score, 'passed': char_score >= char_limit})
        if character_rows:
            result['minimum_character_iou'] = min(r['iou'] for r in character_rows)
            result['character_count'] = len(character_rows)
            result['characters_passed'] = all(r['passed'] for r in character_rows)
            result['passed'] = result['passed'] and result['characters_passed']
            if divisor == 1 or not result['characters_passed']:
                result['character_checks'] = character_rows
    if divisor == 1 and alignment and nonempty:
        glyph_passed = result['passed']
        measured = raster_centering_report(actual, box, origin_xy=observation[:2], name=f'{frame}/{row["name"]}', tolerance_px=1)
        result.update(measured, horizontal='center', vertical='center', resolution_px=list(SIZE))
        result['passed'] = glyph_passed and measured['passed']
    return result


def test_negative_controls(directory):
    """Exercise actual pixel classifiers with wrong math and offset glyphs."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    row = {'name': 'negative-control-main', 'numeric_role': 'main', 'text': '9,232', 'size': 164,
           'box': (600, 263, 1320, 444), 'color': INK, 'fill': '#fffaf0'}
    def fixture(text, shift=(0, 0)):
        im = Image.new('RGB', SIZE, '#fffaf0')
        alpha = glyph_alpha(text, row['size'])
        b = alpha.point(lambda a: 255 if a >= 128 else 0).getbbox()
        x = round((row['box'][0] + row['box'][2] - b[0] - b[2]) / 2) + shift[0]
        y = round((row['box'][1] + row['box'][3] - b[1] - b[3]) / 2) + shift[1]
        im.paste(INK, (x, y), alpha)
        return im
    correct = fixture('9,232')
    wrong = fixture('9,233')
    offset = fixture('9,232', (4, -4))
    cases = [('correct', correct, True), ('wrong-final-digit', wrong, False), ('offcenter-both-axes', offset, False)]
    results = []
    for name, image, should_pass in cases:
        record = inspect_label(image, row, 0)
        require(record['passed'] == should_pass, f'Pixel negative control failed: {name}')
        image.save(directory / f'{name}.png')
        results.append({'case': name, 'expected_pass': should_pass, 'observed_pass': record['passed'], 'passed': True, 'observation': record})
    # A frozen previous result would otherwise look correctly centered.
    frozen = fixture('9,232')
    after = dict(row, text='4,616', name='negative-control-after-even-operation')
    observation = inspect_label(frozen, after, 1)
    require(not observation['passed'], 'Frozen previous-result control was accepted')
    results.append({'case': 'frozen-previous-result', 'expected_pass': False, 'observed_pass': observation['passed'], 'passed': True, 'observation': observation})
    report = {'passed': True, 'scope': 'Pixel-engine sensitivity controls; actual-video operation freeze control is additional.', 'cases': results}
    save(directory / 'pixel-engine-controls.json', report)
    return report


def label(name, text, size, box, color=INK, role='label', fill=None):
    return {'name': name, 'text': str(text), 'size': size, 'box': tuple(box), 'color': color, 'numeric_role': role, 'fill': fill}


def smooth(raw):
    p = max(0, min(1, raw))
    return p * p * (3 - 2 * p)


class VisualOracle:
    """Separate implementation of the agreed edit contract, without renderer imports."""
    def __init__(self, plan, events, counts, truths):
        self.plan, self.events, self.counts, self.truths = plan, events, counts, truths
        self.by = {e['id']: e for e in events}
        self.event_starts = [e['start_s'] for e in events]
        self.result_starts = [e['result_start_s'] for e in counts]
        self.count_ends = [e['end_s'] for e in counts]

    def state(self, frame):
        t = frame / FPS
        current_k = bisect_right(self.result_starts, t) - 1
        completed = bisect_right(self.count_ends, t)
        event = self.events[max(0, bisect_right(self.event_starts, t) - 1)]
        ident = event['id']
        mode = 'count' if current_k >= 0 else 'intro'
        n, phase, replay, operation_index = None, -1, False, None
        if ident.startswith('I') and current_k < 0:
            mode = ident
            if ident in ('I03', 'I04'):
                n = 8 if ident == 'I03' else 5
                phase = max(0, min(1, (t - event['start_s']) / event['duration_s']))
        elif ident == 'B01' and (current_k < 17 or t < self.result_starts[17]):
            mode = 'bridge'
        elif ident.startswith('T27_') and t < event['end_s'] + .22:
            mode, replay = ident, True
            if ident in ('T27_001', 'T27_036'):
                operation_index = 0 if ident == 'T27_001' else 35
                n = self.truths[27][operation_index]
                phase = max(0, min(1, (t - event['start_s']) / event['duration_s']))
        elif ident.startswith('O'):
            mode = ident
        if mode == 'count' and 0 <= current_k < len(self.counts) - 1:
            current, following = self.counts[current_k:current_k + 2]
            seed, index = count_identity(current)
            next_seed, _ = count_identity(following)
            if seed == next_seed and following['operation_start_s'] <= t < following['result_start_s']:
                n, operation_index = self.truths[seed][index], index
                phase = (t - following['operation_start_s']) / (following['result_start_s'] - following['operation_start_s'])
        phase_tick = round(phase * 30) if phase >= 0 else -1
        fade = round(255 * (1 - t / .6)) if t < .6 else round(255 * (t - (self.plan['duration_s'] - .8)) / .8) if t > self.plan['duration_s'] - .8 else 0
        return {'mode': mode, 'k': current_k, 'completed': completed, 'op_n': n, 'op_index': operation_index,
                'phase_tick': phase_tick, 'phase': phase_tick / 30, 'replay': replay, 'fade': max(0, min(255, fade))}

    @staticmethod
    def header(subtitle, title='COLLATZ SEQUENCE'):
        return [label('heading', title, 47, (270, 70, 1650, 144)),
                label('index', subtitle, 25, (300, 166, 1620, 211), TEAL, 'index' if subtitle.startswith('START ') else 'label')]

    @staticmethod
    def mirror(value, x, y=638, radius=125, name='mirror', role='copy'):
        return label(name, f'{value:,}', 50, (x - radius + 14, y - radius * .54 + 10, x + radius - 14, y + radius * .54 - 10), TEAL, role, '#e0f2ea')

    def operation_labels(self, n, p, seed, replay=False):
        out = n * 3 + 1 if n % 2 else n // 2
        odd = n % 2 == 1
        title = ('REPLAY · ALREADY COUNTED' if replay else 'NEXT: ODD · THREE COPIES, THEN +1') if odd else 'NEXT: EVEN · TWO EQUAL HALVES'
        if seed is None:
            title = 'RULE DEMO · ' + ('ODD: ×3, THEN +1' if odd else 'EVEN: ÷2')
        if odd and .42 <= p < .9:
            title = ('REPLAY · ' if replay else 'RULE DEMO · ' if seed is None else '') + 'CALCULATION ONLY · ' + ('MULTIPLY BY THREE' if p < .7 else 'THEN ADD ONE')
        rows = [label('operation-label', title, 25, (350, 529, 1570, 561), CLAY if odd else TEAL)]
        if odd:
            positions = [960] if p < .22 else [620, 960, 1300]
            rows.extend(self.mirror(n, x, name=f'copy-{j}', role='copy') for j, x in enumerate(positions))
            if p < .42:
                expression = f'{n:,} × 3 = ?'
            elif p < .70:
                expression = f'{n:,} × 3 = {3 * n:,}'
            elif p < .9:
                expression = f'{3 * n:,} + 1 = ?'
            else:
                expression = f'{3 * n:,} + 1 = {out:,}'
            if .42 <= p < .9:
                x, y = 1635, round(580 + smooth((p - .42) / .48) * 125)
                rows.append(label('one-droplet', '+1', 29, (x - 34, y - 27, x + 34, y + 27), CLAY, fill='#d8eee9'))
        else:
            if smooth(min(1, p / .5)) >= .94:
                rows.extend(self.mirror(out, x, name=f'half-{j}', role='half') for j, x in enumerate([750, 1170]))
            expression = f'{n:,} ÷ 2 = {out:,}' if p >= .8 else f'{n:,} ÷ 2 = ?'
        rows.append(label('equation', expression, 52, (350, 699, 1570, 777), CLAY if odd else TEAL, 'equation', '#fff9ed'))
        return rows

    def footer(self, state):
        if state['k'] < 0:
            return []
        current = self.counts[state['k']]
        seed, _ = count_identity(current)
        complete = [event for event in self.counts[:state['completed']] if count_identity(event)[0] == seed]
        recent = complete[-3:]
        total = len(self.truths[seed])
        return [dict(label('recent-label', 'RECENT TERMS', 23, (255, 834, 745, 875), TEAL), native_luminance=True),
                label('recent-terms', ' → '.join(f"{event['value']:,}" for event in recent) if recent else 'READY', 29, (250, 889, 750, 952), INK, 'recent'),
                label('progress-label', 'TERMS COMPLETED', 23, (1175, 834, 1665, 875), TEAL),
                label('progress', f'{len(complete)} / {total}', 37, (1170, 889, 1670, 952), INK, 'progress')]

    def labels(self, frame):
        state = self.state(frame)
        mode, rows = state['mode'], []
        if mode.startswith('I') or mode == 'intro':
            rows.extend(self.header('ONE NUMBER. TWO RULES. A SURPRISING JOURNEY.'))
            if mode in ('I03', 'I04'):
                rows.append(label('demo-input', str(state['op_n']), 164, (600, 263, 1320, 444), INK, 'demo-input', '#fffaf0'))
                rows.append(label('demo-label', 'RULE DEMO · NOT A COUNTED JOURNEY', 30, (240, 470, 1680, 525), BLUE))
                rows.extend(self.operation_labels(state['op_n'], state['phase'], None))
            elif mode == 'I02':
                rows.extend([label('positive-integers', '1, 2, 3, 4, 5, …', 102, (410, 309, 1510, 450), TEAL, fill='#fffaf0'),
                             label('domain-description', 'Start with a positive whole number.\nEach rule makes the next number.', 39, (400, 503, 1520, 688), fill='#fffaf0')])
            elif mode == 'I05':
                rows.extend(self.mirror(5, x, y=378, name=f'value-copy-{j}', role='demo-copy') for j, x in enumerate([620, 960, 1300]))
                rows.append(label('value-not-water', 'THREE COPIES OF THE VALUE\n5 + 5 + 5 = 15\nNumbers, not amounts of water.', 38, (405, 497, 1515, 716), fill='#fffaf0'))
            else:
                rows.extend([label('start-symbol', '7' if mode == 'I06' else 'n', 164, (640, 276, 1280, 498), TEAL, fill='#fffaf0'),
                             label('start-label', 'START HERE', 28, (710, 510, 1210, 555), TEAL, fill='#fffaf0'),
                             label('even-rule', 'EVEN: n ÷ 2', 42, (330, 658, 770, 721), TEAL, fill='#fffaf0'),
                             label('odd-rule', 'ODD: 3 × n + 1', 37, (1140, 658, 1600, 721), CLAY, fill='#fffaf0')])
            return rows, state
        if mode == 'bridge':
            rows.extend(self.header('FIRST JOURNEY FINISHED · NEXT JOURNEY BEGINS AT 27', 'A NEW START. THE SAME TWO RULES.'))
            rows.extend([label('first-trip', '7 → 1', 108, (450, 300, 1470, 432), TEAL, fill='#fffaf0'),
                         label('first-trip-total', '17 TERMS · 16 STEPS', 34, (450, 453, 1470, 512), TEAL, fill='#fffaf0'),
                         label('new-start', 'NEW START: 27', 75, (450, 567, 1470, 695), CLAY, fill='#fffaf0')])
            return rows, state
        event = self.counts[state['k']]
        seed, index = count_identity(event)
        value = self.truths[seed][index]
        if mode.startswith('O'):
            rows.extend(self.header('7: 16 STEPS · 27: 111 STEPS · BOTH STOP AT 1', 'TWO JOURNEYS. THE SAME TWO RULES.'))
        else:
            rows.extend(self.header(f'START {seed} · STEP {index} · TERM {index + 1} OF {len(self.truths[seed])}'))
        rows.extend([label('main', f'{value:,}', 164, (600, 263, 1320, 444), INK, 'main', '#fffaf0'),
                     label('reading', event['text'], 35, (240, 470, 1680, 525), TEAL, 'reading')])
        if mode in ('T27_001', 'T27_036'):
            rows.extend(self.operation_labels(state['op_n'], state['phase'], 27, True))
        elif mode == 'T27_077':
            rows.append(label('peak-label', 'HIGHEST VALUE OF THIS JOURNEY', 32, (330, 545, 1590, 592), CLAY))
            rows.extend(self.graph_labels(77, partial=True))
        elif mode == 'T27_103':
            rows.extend([label('same-rule', 'SAME VALUE. SAME RULE. SAME ENDING.', 28, (300, 594, 1620, 637), TEAL, fill='#fffaf0'),
                         label('familiar-ending', '40 → 20 → 10 → 5 → 16 → 8 → 4 → 2 → 1', 42, (310, 669, 1610, 752), fill='#fffaf0')])
        elif mode == 'O01':
            rows.append(label('stop-and-loop', 'WE STOP AT 1.\nIF WE CONTINUE: 1 → 4 → 2 → 1', 39, (375, 609, 1545, 752), TEAL, fill='#fffaf0'))
        elif mode == 'O02':
            rows.append(label('unproved-conjecture', 'Will every positive integer reach 1?\nTHE COLLATZ CONJECTURE · STILL UNPROVED', 35, (365, 609, 1555, 752), fill='#fffaf0'))
        elif mode == 'O03':
            rows.extend(self.graph_labels(111, partial=False))
        elif state['op_n'] is not None:
            rows.extend(self.operation_labels(state['op_n'], state['phase'], seed))
        else:
            rows.append(label('operation-label', 'HOW THIS TERM WAS MADE' if index else 'A NEW JOURNEY STARTS HERE', 25, (350, 542, 1570, 579), TEAL))
            if index:
                previous = self.truths[seed][index - 1]
                rows.append(label('equation', equation(previous, value), 56, (400, 619, 1520, 738), CLAY if previous % 2 else TEAL, 'incoming-equation', '#fff9ed'))
            else:
                rows.append(label('start-instructions', f'START WITH {value}\nSTOP WHEN WE FIRST REACH 1', 37, (400, 615, 1520, 752), TEAL, fill='#fff9ed'))
        rows.extend(self.footer(state))
        return rows, state

    def graph_labels(self, end_index, partial):
        rows = [label('route-start', '27', 21, (344, 710, 396, 750), TEAL, fill='#fffaf0'),
                label('route-scale', 'HEIGHT: log₂(value) · HORIZONTAL: COLLATZ STEP', 18, (400, 604, 1520, 626), BLUE, fill='#fffaf0')]
        if end_index == 111:
            rows.append(label('route-end', '1', 21, (1528, 713, 1570, 753), TEAL, fill='#fffaf0'))
        return rows


@lru_cache(maxsize=4)
def graph_reference(last, divisor):
    area = (384, 638, 1536, 754)
    values = independent_trace(27)[:last + 1]
    points = [(390 + i / 111 * 1140 - area[0], 748 - math.log2(value) / math.log2(9232) * 103 - area[1]) for i, value in enumerate(values)]
    expected = Image.new('L', (area[2] - area[0], area[3] - area[1]))
    draw = ImageDraw.Draw(expected)
    draw.line(points, fill=255, width=3)
    for i, (x, y) in enumerate(points):
        radius = 5 if i in (0, 77, last) else 2
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)
    if divisor != 1:
        expected = expected.resize((expected.width // divisor, expected.height // divisor), Image.Resampling.BOX)
    return area, expected.point(lambda a: 255 if a >= 128 else 0)


def inspect_graph(image, last, frame, divisor=1):
    area, expected = graph_reference(last, divisor)
    crop = image.crop(tuple(value // divisor for value in area))
    observed = ImageChops.lighter(observed_ink(crop, TEAL), observed_ink(crop, CLAY))
    score = iou(observed, expected)
    threshold = .88 if divisor == 1 else .73
    return {'frame': frame, 'last_index': last, 'term_count': last + 1, 'x_scale': 'step index0..111', 'y_scale': 'log2(value)',
            'resolution_divisor': divisor, 'independent_trace_shape_iou': score, 'minimum_iou': threshold,
            'not_a_proof_for_all_starting_values': True, 'future_terms_expected': False, 'passed': score >= threshold}


def native_indices(plan, events, counts):
    frames = {0, plan['duration_frames'] - 1}
    for event in events:
        for t in (event['start_s'] - 1 / FPS, event['start_s'], (event['start_s'] + event['end_s']) / 2,
                  event['end_s'] - 1 / FPS, event['end_s'], event['end_s'] + .12):
            frames.add(first_frame(t))
    for event in counts:
        commit = first_frame(event['result_start_s'])
        frames.update((commit - 1, commit, commit + 1))
        if event['index']:
            start, end = event['operation_start_s'], event['result_start_s']
            for p in (0, .1, .21, .23, .41, .43, .69, .71, .79, .81, .89, .91, .99):
                frames.add(first_frame(start + p * (end - start)))
    for ident in ('I03', 'I04', 'T27_001', 'T27_036'):
        event = next(e for e in events if e['id'] == ident)
        frames.update(first_frame(event['start_s'] + event['duration_s'] * p) for p in (0, .21, .23, .41, .43, .69, .71, .89, .91, 1))
    return sorted(frame for frame in frames if 0 <= frame < plan['duration_frames'])


def decoded_frames(video, ffmpeg, log, divisor=2, indices=None):
    width, height = SIZE[0] // divisor, SIZE[1] // divisor
    filters = []
    if indices is not None:
        # FFmpeg's expression parser recursively evaluates a left-associative
        # sum. A balanced tree keeps thousands of selected frames shallow.
        def balanced(parts):
            if len(parts) == 1:
                return parts[0]
            middle = len(parts) // 2
            return '(' + balanced(parts[:middle]) + '+' + balanced(parts[middle:]) + ')'
        filters.append('select=' + balanced([f'eq(n\\,{frame})' for frame in indices]))
    if divisor != 1:
        filters.append(f'scale={width}:{height}:flags=area')
    command = [str(ffmpeg), '-nostdin', '-v', 'error', '-xerror', '-i', str(video), '-map', '0:v:0', '-an']
    if filters:
        command.extend(['-vf', ','.join(filters)])
    command.extend(['-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'])
    with Path(log).open('wb') as errors:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
        ordinal = 0
        try:
            while True:
                raw = proc.stdout.read(width * height * 3)
                if not raw:
                    break
                require(len(raw) == width * height * 3, 'Partial decoded RGB frame')
                frame = indices[ordinal] if indices is not None else ordinal
                yield frame, Image.frombytes('RGB', (width, height), raw)
                ordinal += 1
            require(proc.wait() == 0, f'Decoded-frame process failed; see{log}')
            if indices is not None:
                require(ordinal == len(indices), 'Selected native frame count differs')
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait()


def visually_checked_label(row):
    # Every visible mathematical/reading component is included. These labels
    # also cover the domain, 1-stop convention, finite scope and graph scale.
    return True


def pixel_engine_fingerprint():
    return hashlib.sha256(''.join(inspect.getsource(x) for x in [VisualOracle, inspect_label, component_ink, glyph_alpha, label_reference, inspect_graph, graph_reference]).encode()).hexdigest()


def visual_checks(plan, events, counts, truths, video, ffmpeg, directory, reuse_half=None, timeline_path=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    oracle = VisualOracle(plan, events, counts, truths)
    frames_native = native_indices(plan, events, counts)
    evidence_frames = {first_frame(e['start_s'] + min(.4, e['duration_s'] / 2)) for e in events
                       if e['id'] in ('I03', 'I04', 'C7_000', 'B01', 'C27_000', 'T27_001', 'C27_035', 'C27_036', 'T27_036', 'C27_063', 'C27_065', 'C27_067', 'C27_077', 'T27_077', 'C27_111', 'O01', 'O02', 'O03')}
    summaries, failure_rows, negative_source = [], [], {}
    half_flags = []
    if reuse_half:
        reuse_half = Path(reuse_half)
        receipt = json.loads((reuse_half / 'half-evidence-receipt.json').read_text())
        require(receipt['video_sha256'] == sha(video) and receipt['timeline_sha256'] == sha(timeline_path), 'Half-evidence target changed')
        require(receipt['independent_pixel_engine_fingerprint'] == pixel_engine_fingerprint(), 'Half-evidence pixel engine changed')
        for name, field in [('all-frames-half-resolution.jsonl.gz', 'half_records_sha256'), ('all-frames-half-resolution-summary.json', 'half_summary_sha256')]:
            require(sha(reuse_half / name) == receipt[field], f'Half-evidence changed {name}')
        with gzip.open(reuse_half / 'all-frames-half-resolution.jsonl.gz', 'rt') as source:
            half_flags = [json.loads(line) for line in source if line and not json.loads(line)['passed']]
        summaries.append({**json.loads((reuse_half / 'all-frames-half-resolution-summary.json').read_text()),
                          'evidence_reused_from': str(reuse_half), 'target_and_engine_receipt': receipt,
                          'half_flags_escalated_to_native': len(half_flags)})
        frames_native = sorted(set(frames_native) | {row['frame'] for row in half_flags})
        passes = [(1, frames_native, 'native-boundaries-and-transitions')]
    else:
        passes = [(2, None, 'all-frames-half-resolution'), (1, frames_native, 'native-boundaries-and-transitions')]
    native_rechecks = []
    for divisor, indices, name in passes:
        observations = 0
        frames_seen = 0
        faint_frames = []
        min_iou = 1
        max_dx = max_dy = 0
        graph_rows = []
        with gzip.open(directory / f'{name}.jsonl.gz', 'wt', encoding='utf-8') as details:
            for frame, image in decoded_frames(video, ffmpeg, directory / f'{name}-decode.log', divisor, indices):
                frames_seen += 1
                rows, state = oracle.labels(frame)
                if state['fade']:
                    # Fades are audited separately from the literal glyph masks.
                    faint_frames.append(frame)
                    continue
                for row in rows:
                    if not visually_checked_label(row):
                        continue
                    result = inspect_label(image, row, frame, divisor)
                    result['scene'] = state['mode']
                    details.write(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
                    observations += 1
                    min_iou = min(min_iou, result['independent_glyph_iou'])
                    if divisor == 1 and result.get('delta_x_px') is not None:
                        max_dx, max_dy = max(max_dx, abs(result['delta_x_px'])), max(max_dy, abs(result['delta_y_px']))
                    if not result['passed']:
                        if divisor == 2:
                            half_flags.append(result)
                        elif len(failure_rows) < 500:
                            failure_rows.append(result)
                    if divisor == 1 and any(flag['frame'] == frame and flag.get('name') == row['name'] for flag in half_flags):
                        native_rechecks.append(result)
                if state['mode'] in ('T27_077', 'O03'):
                    graph = inspect_graph(image, 77 if state['mode'] == 'T27_077' else 111, frame, divisor)
                    details.write(json.dumps({'kind': 'graph', **graph}, ensure_ascii=False, separators=(',', ':')) + '\n')
                    graph_rows.append(graph)
                    if not graph['passed'] and len(failure_rows) < 500:
                        failure_rows.append(graph)
                if divisor == 1 and frame in evidence_frames:
                    image.save(directory / f'evidence-f{frame:06d}-{state["mode"]}.png')
                if divisor == 1 and state['op_n'] == 27 and not state['replay']:
                    if .05 <= state['phase'] <= .15:
                        negative_source.setdefault('operation_start', (frame, image.copy()))
                    if .42 <= state['phase'] <= .69:
                        negative_source.setdefault('operation_middle', (frame, image.copy()))
                if frames_seen % 900 == 0:
                    print(json.dumps({'qa': name, 'decoded_frames': frames_seen, 'observations': observations}), flush=True)
        if divisor == 2:
            require(frames_seen == plan['duration_frames'], 'All-frame mathematical decode count differs')
            frames_native = sorted(set(frames_native) | {row['frame'] for row in half_flags})
            passes[1] = (1, frames_native, 'native-boundaries-and-transitions')
        summary = {'passed': not half_flags if divisor == 2 else not failure_rows, 'name': name, 'resolution_divisor': divisor, 'decoded_frames': frames_seen,
                   'component_observations': observations, 'minimum_glyph_iou': min_iou, 'native_max_abs_dx_px': max_dx if divisor == 1 else None,
                   'native_max_abs_dy_px': max_dy if divisor == 1 else None, 'fade_frames_audited_separately': faint_frames,
                   'graph_observations': len(graph_rows), 'graph_all_passed': all(row['passed'] for row in graph_rows),
                   'half_flags_requiring_native_resolution': len(half_flags) if divisor == 2 else None}
        save(directory / f'{name}-summary.json', summary)
        summaries.append(summary)
    operation_control = actual_operation_freeze_control(negative_source, oracle, directory)
    require(len(native_rechecks) == len(half_flags), 'Every half-resolution glyph flag needs native re-observation')
    save(directory / 'half-flags-native-rechecks.json', {'half_flags': half_flags, 'native_rechecks': native_rechecks,
                                                       'all_native_rechecks_passed': all(row['passed'] for row in native_rechecks),
                                                       'thresholds_relaxed': False})
    save(directory / 'failures.json', failure_rows)
    report = {'passed': not failure_rows and operation_control['passed'], 'passes': summaries, 'native_frames_requested': len(frames_native),
              'independence': 'Fresh integer recurrence and inverse speech parser; separately implemented editorial phase/geometry; no Collatz renderer imported; actual encoded RGB foreground masks and separately rasterized font templates.',
              'actual_operation_freeze_control': operation_control,
              'half_resolution_flags': len(half_flags), 'native_resolution_flag_rechecks': len(native_rechecks),
              'half_flags_all_resolved_by_native_pixels': all(row['passed'] for row in native_rechecks),
              'failure_count_recorded': len(failure_rows), 'failure_record_cap': 500,
              'limits': ['Half-resolution glyph identity checks cover every decoded nonfade frame; native both-axis bounds cover all cue boundaries, all127 transition phases, explanations and extremes.',
                         'Artistic motion sufficiency, face identity and meaningful gestures are evaluated separately.']}
    save(directory / 'visual-verification.json', report)
    return report


def actual_operation_freeze_control(source, oracle, directory):
    require('operation_start' in source and 'operation_middle' in source, 'Actual operation control needs two phases')
    first_frame_id, first = source['operation_start']
    later_frame_id, later = source['operation_middle']
    # Replace only the operation area; keep the current value and footer intact.
    frozen = later.copy()
    area = (310, 580, 1608, 790)
    frozen.paste(first.crop(area), area)
    rows, _ = oracle.labels(later_frame_id)
    operation_rows = [row for row in rows if row['name'] == 'equation' or row['numeric_role'] in ('copy', 'half')]
    normal = [inspect_label(later, row, later_frame_id) for row in operation_rows]
    changed = [inspect_label(frozen, row, later_frame_id) for row in operation_rows]
    require(all(row['passed'] for row in normal), 'Real encoded operation phase failed its own control baseline')
    rejected = any(not row['passed'] for row in changed)
    require(rejected, 'Frozen operation was not detected while main value remained correct')
    frozen.save(directory / 'negative-control-frozen-operation.png')
    result = {'passed': True, 'start_frame': first_frame_id, 'middle_frame': later_frame_id,
              'only_operation_region_replaced_xyxy': list(area), 'main_and_progress_kept': True,
              'normal_baseline_passed': True, 'frozen_region_detected': rejected, 'observations': changed}
    save(directory / 'negative-control-frozen-operation.json', result)
    return result


def fade_checks(plan, video, ffmpeg, directory):
    """Measure encoded glyph-core colors against the explicit fade curve."""
    indices = list(range(first_frame(.6))) + list(range(first_frame(plan['duration_s'] - .8), plan['duration_frames']))
    records = []
    for frame, image in decoded_frames(video, ffmpeg, Path(directory) / 'fade-decode.log', 1, indices):
        t = frame / FPS
        opening = t < .6
        text, box, color = ('n', (640, 276, 1280, 498), TEAL) if opening else ('1', (600, 263, 1320, 444), INK)
        alpha = glyph_alpha(text, 164)
        b = alpha.point(lambda a: 255 if a >= 128 else 0).getbbox()
        x = round((box[0] + box[2] - b[0] - b[2]) / 2)
        y = round((box[1] + box[3] - b[1] - b[3]) / 2)
        actual = image.crop((x, y, x + alpha.width, y + alpha.height))
        core = alpha.point(lambda a: 255 if a >= 250 else 0)
        mean = ImageStat.Stat(actual, core).mean
        opacity = max(0, min(255, round(255 * (1 - t / .6)) if opening else round(255 * (t - (plan['duration_s'] - .8)) / .8)))
        expected = [int(a * (1 - opacity / 255) + b * opacity / 255) for a, b in zip(rgb(color), rgb('#fffaf0'))]
        error = max(abs(a - b) for a, b in zip(mean, expected))
        records.append({'frame': frame, 'time_s': t, 'opening': opening, 'declared_fade_alpha': opacity,
                        'actual_core_mean_rgb': mean, 'expected_core_rgb': expected, 'maximum_rgb_error': error, 'passed': error <= 5})
    report = {'passed': all(r['passed'] for r in records), 'frames': len(records), 'maximum_rgb_error': max(r['maximum_rgb_error'] for r in records),
              'scope': 'Every opening/closing fade frame, glyph-core mean from actual decoded final movie; independent .6/.8s linear alpha contract.', 'records': records}
    save(Path(directory) / 'fade-verification.json', report)
    return report


@lru_cache(maxsize=2048)
def digit_templates(text, size, box, position, divisor):
    """Ten alternatives at this exact character slot, with natural group centering."""
    face = font(size)
    candidates, bounds = [], []
    for digit in '0123456789':
        changed = text[:position] + digit + text[position + 1:]
        alpha = glyph_alpha(changed, size)
        b = alpha.point(lambda a: 255 if a >= 128 else 0).getbbox()
        origin = (round((box[0] + box[2] - b[0] - b[2]) / 2), round((box[1] + box[3] - b[1] - b[3]) / 2))
        fb = face.getbbox(changed)
        baseline = (origin[0] + 32 - fb[0], origin[1] + 32 - fb[1])
        advance = face.getlength(changed[:position])
        db = face.getbbox(digit)
        bounds.append((baseline[0] + advance + db[0], baseline[1] + db[1], baseline[0] + advance + db[2], baseline[1] + db[3]))
        candidates.append((alpha, origin))
    area = (max(0, math.floor((min(b[0] for b in bounds) - 2) / divisor) * divisor),
            max(0, math.floor((min(b[1] for b in bounds) - 2) / divisor) * divisor),
            min(SIZE[0], math.ceil((max(b[2] for b in bounds) + 2) / divisor) * divisor),
            min(SIZE[1], math.ceil((max(b[3] for b in bounds) + 2) / divisor) * divisor))
    masks = []
    for alpha, origin in candidates:
        mask = Image.new('L', (area[2] - area[0], area[3] - area[1]))
        mask.paste(alpha, (origin[0] - area[0], origin[1] - area[1]))
        if divisor != 1:
            mask = mask.resize((mask.width // divisor, mask.height // divisor), Image.Resampling.BOX)
        masks.append(mask.point(lambda a: 255 if a >= 128 else 0))
    return area, masks


_DIGIT_OBSERVATION_CACHE = {}


def inspect_digits(image, row, frame, divisor=2):
    observations = []
    for position, expected in enumerate(row['text']):
        if expected not in '0123456789':
            continue
        area, templates = digit_templates(row['text'], row['size'], tuple(row['box']), position, divisor)
        actual = component_ink(image, row, area, divisor)
        identity = (row['text'], row['size'], tuple(row['box']), row.get('color'), row.get('fill'), row.get('native_luminance'), position, divisor,
                    hashlib.blake2b(actual.tobytes(), digest_size=12).digest())
        result = _DIGIT_OBSERVATION_CACHE.get(identity)
        if result is None:
            scores = [iou(actual, template) for template in templates]
            order = sorted(range(10), key=lambda n: scores[n], reverse=True)
            # Encoded half-resolution thin strokes can be displaced one pixel;
            # compare every candidate under the same small translation search.
            if scores[order[0]] < .85 or scores[order[0]] - scores[order[1]] < .06 or order[0] != int(expected):
                expanded = []
                for template in templates:
                    best = iou(actual, template)
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            if dx == dy == 0:
                                continue
                            moved = Image.new('L', template.size)
                            moved.paste(template, (dx, dy))
                            best = max(best, iou(actual, moved))
                    expanded.append(best)
                scores = expanded
                order = sorted(range(10), key=lambda n: scores[n], reverse=True)
            winner = str(order[0])
            margin = scores[order[0]] - scores[order[1]]
            minimum = .60 if divisor == 2 else .75
            result = {'position': position, 'expected_digit': expected, 'closest_digit': winner,
                      'candidate_ious_0_to_9': scores, 'winner_iou': scores[order[0]], 'runner_up_digit': str(order[1]),
                      'winner_margin': margin, 'minimum_iou': minimum, 'minimum_margin': .005,
                      'actual_nonempty': actual.getbbox() is not None,
                      'passed': actual.getbbox() is not None and winner == expected and scores[order[0]] >= minimum and margin >= .005}
            if len(_DIGIT_OBSERVATION_CACHE) > 50000:
                _DIGIT_OBSERVATION_CACHE.clear()
            _DIGIT_OBSERVATION_CACHE[identity] = result
        observations.append(result)
    return {'name': row['name'], 'numeric_role': row.get('numeric_role'), 'frame': frame, 'time_s': frame / FPS,
            'text': row['text'], 'font_size_px': row['size'], 'resolution_divisor': divisor,
            'digits': observations, 'digit_count': len(observations), 'passed': all(r['passed'] for r in observations)}


def expanded_numeric_rows(rows):
    """Keep multiline group centering and14px gaps while identifying each line."""
    expanded = []
    for row in rows:
        if '\n' not in row['text']:
            if any(c in '0123456789' for c in row['text']):
                expanded.append(row)
            continue
        pieces = [glyph_alpha(line, row['size']) for line in row['text'].split('\n')]
        bounds = [piece.point(lambda a: 255 if a >= 128 else 0).getbbox() for piece in pieces]
        width = max(b[2] - b[0] for b in bounds)
        group = glyph_alpha(row['text'], row['size'])
        b = group.point(lambda a: 255 if a >= 128 else 0).getbbox()
        box = row['box']
        origin = (round((box[0] + box[2] - b[0] - b[2]) / 2), round((box[1] + box[3] - b[1] - b[3]) / 2))
        y = 32
        for i, (line, line_bounds) in enumerate(zip(row['text'].split('\n'), bounds)):
            height = line_bounds[3] - line_bounds[1]
            if any(c in '0123456789' for c in line):
                expanded.append({**row, 'name': f'{row["name"]}/line-{i}', 'text': line,
                                 'box': (origin[0] + 32, origin[1] + y, origin[0] + 32 + width, origin[1] + y + height),
                                 'parent_multiline_component': row['name'], 'group_box': list(box), 'line_number': i})
            y += height + 14
    return expanded


def numeric_identity_controls(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    cases = []
    examples = [
        (label('main', '9,232', 164, (600, 263, 1320, 444), INK, 'main', '#fffaf0'), ['9,232', '9,252', '9,282']),
        (label('index', 'START 7 · STEP 3 · TERM 4 OF 17', 25, (300, 166, 1620, 211), TEAL, 'index', '#fffaf0'),
         ['START 7 · STEP 3 · TERM 4 OF 17', 'START 7 · STEP 5 · TERM 4 OF 17']),
        (label('index', 'START 27 · STEP 35 · TERM 36 OF 112', 25, (300, 166, 1620, 211), TEAL, 'index', '#fffaf0'),
         ['START 27 · STEP 35 · TERM 36 OF 112', 'START 27 · STEP 55 · TERM 36 OF 112']),
        (label('index', 'START 27 · STEP 77 · TERM 78 OF 112', 25, (300, 166, 1620, 211), TEAL, 'index', '#fffaf0'),
         ['START 27 · STEP 77 · TERM 78 OF 112', 'START 27 · STEP 77 · TERM 76 OF 112']),
        (label('value-not-water', 'THREE COPIES OF THE VALUE\n5 + 5 + 5 = 15\nNumbers, not amounts of water.', 38, (405, 497, 1515, 716), INK, fill='#fffaf0'),
         ['THREE COPIES OF THE VALUE\n5 + 5 + 5 = 15\nNumbers, not amounts of water.', 'THREE COPIES OF THE VALUE\n5 + 5 + 5 = 16\nNumbers, not amounts of water.']),
        (label('stop-and-loop', 'WE STOP AT 1.\nIF WE CONTINUE: 1 → 4 → 2 → 1', 39, (375, 609, 1545, 752), TEAL, fill='#fffaf0'),
         ['WE STOP AT 1.\nIF WE CONTINUE: 1 → 4 → 2 → 1', 'WE STOP AT 1.\nIF WE CONTINUE: 1 → 5 → 2 → 1']),
    ]
    # Every actual digit0..9 competes with the full ten-digit set.
    examples.append((label('digit-alphabet', '0', 50, (800, 300, 1120, 400), TEAL, 'copy', '#fffaf0'), list('0123456789')))
    for row, actual_texts in examples:
        for actual_text in actual_texts:
            current_row = dict(row, text=actual_text) if row['name'] == 'digit-alphabet' else row
            expected_pass = actual_text == current_row['text']
            alpha = glyph_alpha(actual_text, row['size'])
            b = alpha.point(lambda a: 255 if a >= 128 else 0).getbbox()
            x = round((row['box'][0] + row['box'][2] - b[0] - b[2]) / 2)
            y = round((row['box'][1] + row['box'][3] - b[1] - b[3]) / 2)
            full = Image.new('RGB', SIZE, '#fffaf0')
            full.paste(row['color'], (x, y), alpha)
            for divisor in (1, 2):
                image = full if divisor == 1 else full.resize((960, 540), Image.Resampling.BOX)
                if '\n' in current_row['text']:
                    lines = [inspect_digits(image, line, 0, divisor) for line in expanded_numeric_rows([current_row])]
                    result = {'passed': all(line['passed'] for line in lines), 'lines': lines}
                else:
                    result = inspect_digits(image, current_row, 0, divisor)
                require(result['passed'] == expected_pass, f'Digit identity control failed: {current_row["text"]} versus {actual_text}, divisor{divisor}')
                cases.append({'expected_text': current_row['text'], 'actual_text': actual_text, 'resolution_divisor': divisor,
                              'expected_pass': expected_pass, 'observed_pass': result['passed'], 'passed': True, 'observation': result})
    report = {'passed': True, 'candidate_digits': list('0123456789'), 'cases': cases,
              'scope': 'Main wrong3→5/8, production index3→5/35→55/78→76, multiline5+5+5=15→16 and loop4→5 at native and half resolution, plus identification of all ten individual digits.'}
    save(directory / 'closest-digit-negative-controls.json', report)
    return report


def numeric_identity_checks(plan, events, counts, truths, video, ffmpeg, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    oracle = VisualOracle(plan, events, counts, truths)
    flags, native_results = [], []
    frames_seen = components = digit_count = 0
    with gzip.open(directory / 'all-frame-digit-identities.jsonl.gz', 'wt', encoding='utf-8') as output:
        for frame, image in decoded_frames(video, ffmpeg, directory / 'all-frame-digit-decode.log', 2):
            frames_seen += 1
            rows, state = oracle.labels(frame)
            if state['fade']:
                continue
            for row in expanded_numeric_rows(rows):
                result = inspect_digits(image, row, frame, 2)
                components += 1
                digit_count += result['digit_count']
                output.write(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
                if not result['passed']:
                    flags.append({'frame': frame, 'name': row['name'], 'half_observation': result})
            if frames_seen % 900 == 0:
                print(json.dumps({'qa': 'closest-digit-all-frames', 'frames': frames_seen, 'components': components, 'digits': digit_count}), flush=True)
    require(frames_seen == plan['duration_frames'], 'Numeric identity full-frame count differs')
    flagged_frames = sorted({r['frame'] for r in flags})
    by_frame = {}
    for flag in flags:
        by_frame.setdefault(flag['frame'], set()).add(flag['name'])
    if flagged_frames:
        for frame, image in decoded_frames(video, ffmpeg, directory / 'native-digit-escalation-decode.log', 1, flagged_frames):
            rows, _ = oracle.labels(frame)
            for row in expanded_numeric_rows(rows):
                if row['name'] not in by_frame[frame]:
                    continue
                result = inspect_digits(image, row, frame, 1)
                native_results.append(result)
                if not result['passed']:
                    safe_name = row['name'].replace('/', '__')
                    image.save(directory / f'failed-digit-native-f{frame:06d}-{safe_name}.png')
    require(len(flags) == len(native_results), 'Every ambiguous/wrong half-resolution digit needs native inspection')
    failures = [r for r in native_results if not r['passed']]
    report = {'passed': not failures, 'source_video_sha256': sha(video), 'decoded_frames': frames_seen,
              'numeric_component_observations': components, 'digit_observations': digit_count, 'candidate_digits': list('0123456789'),
              'half_resolution_flags': len(flags), 'native_flag_frames': len(flagged_frames), 'native_component_rechecks': len(native_results),
              'unresolved_native_identity_failures': len(failures), 'failures': failures,
              'half_flags': flags, 'native_rechecks': native_results,
              'scope': 'Every ASCII digit in every visible nonfade numeric/current/index/equation/copy/half/progress/recent/math label, including each line of multiline mathematical groups with their shared centering and14px line spacing. Independent0..9 competition per glyph slot; ambiguous results re-observed at full resolution. Fade frames have separate full-frame color-curve QA.',
              'method': 'Expected numeric text from independent finite recurrence/oracle; natural group centering for each single-digit counterfactual, foreground inferred from actual decoded pixels, ten-candidate local IoU and a common translation search. No producer pixels used.'}
    save(directory / 'numeric-identity-verification.json', report)
    return report


def schedule_negative_controls(plan, directory):
    rows = []
    mutations = [
        ('one-millisecond-operation', lambda p: p['voice_events'][7].update(operation_start_s=p['voice_events'][7]['result_start_s'] - .001)),
        ('incorrect-state-display', lambda p: p['counted_states'][1].update(display='999')),
        ('negative-state-time', lambda p: p['counted_states'][1].update(display_start_s=-99, voice_end_s=-98)),
        ('incorrect-even-rule', lambda p: p['counted_states'][2].update(incoming_rule='odd')),
    ]
    for name, mutate in mutations:
        changed = deepcopy(plan)
        mutate(changed)
        # Keep the redundant event aliases consistent so that the intended
        # timing validator, rather than only the alias guard, rejects the edit.
        changed['events'] = deepcopy(changed['voice_events'])
        try:
            validate_schedule(changed)
        except ValueError as error:
            rows.append({'case': name, 'rejected': True, 'reason': str(error), 'passed': True})
        else:
            raise ValueError(f'Schedule mutation was accepted: {name}')
    result = {'passed': True, 'cases': rows}
    save(Path(directory) / 'strict-schedule-negative-controls.json', result)
    return result


def speech_gate_checks(plan, events):
    receipt = plan['speech_acceptance']
    gate_path = path_of(receipt['path'])
    require(sha(gate_path) == receipt['sha256'], 'Adopted speech gate changed')
    gate = json.loads(gate_path.read_text())
    require(gate.get('accepted') is True and not gate.get('unresolved'), 'Speech source gate has unresolved items')
    input_receipts = []
    for name, bound in gate.get('inputs', {}).items():
        if isinstance(bound, dict) and 'path' in bound and 'sha256' in bound:
            path = path_of(bound['path'])
            require(sha(path) == bound['sha256'], f'Source-gate evidence changed: {name}')
            input_receipts.append({'role': name, 'path': str(path), 'sha256': bound['sha256']})
    rows = {row['id']: row for row in gate['results']}
    require(set(rows) == {event['id'] for event in events}, 'Speech gate cue coverage differs')
    for event in events:
        row = rows[event['id']]
        require(row.get('accepted') is True, f'Clip not accepted {event["id"]}')
        source_hash = row.get('source_sha256', row.get('sha256'))
        require(source_hash == event['source_sha256'], f'Gate source hash differs {event["id"]}')
    return {'passed': True, 'path': str(gate_path), 'sha256': receipt['sha256'], 'source_cues': len(rows), 'input_evidence': input_receipts, 'original_source_acceptance_only': True,
            'limits': 'This gate is source pronunciation provenance. Final encoded AAC is separately decoded, waveform-tested and freshly recognized.'}


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--timeline', type=Path, required=True)
    p.add_argument('--video', type=Path)
    p.add_argument('--master', type=Path)
    p.add_argument('--captions', type=Path)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--ffmpeg', type=Path, default=ROOT / '.venv/bin/ffmpeg')
    p.add_argument('--ffprobe', type=Path, default=ROOT / '.venv/bin/ffprobe')
    p.add_argument('--precheck-only', action='store_true')
    p.add_argument('--export-final-aac', action='store_true')
    p.add_argument('--visual-only', action='store_true')
    p.add_argument('--reuse-half-dir', type=Path)
    p.add_argument('--recognition-review', type=Path)
    p.add_argument('--content-identity', type=Path)
    p.add_argument('--extend-report', type=Path)
    p.add_argument('--base-snapshot', type=Path)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.out_dir / 'verification.json'
    require(not report_path.exists(), 'Choose an unused report destination; past QA must be preserved')
    plan = json.loads(args.timeline.read_text())
    events, counts, truths, math_report, timing_report = validate_schedule(plan)
    gate = speech_gate_checks(plan, events)
    master = args.master or path_of(plan['master_path'])
    require(sha(master) == plan['master']['sha256'], 'Adopted audio master changed')
    report = {'schema_version': 1, 'kind': 'independent-collatz-final-media-verification', 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'inputs': {'timeline': {'path': str(args.timeline), 'sha256': sha(args.timeline)}, 'verifier': {'path': str(Path(__file__)), 'sha256': sha(__file__)},
                         'font': {'path': str(FONT), 'sha256': sha(FONT)}},
              'math': math_report, 'timing': timing_report, 'source_gate': gate,
              'selected_mode': 'source-precheck-only' if args.precheck_only else 'visual-only' if args.visual_only else 'full-finished-media',
              'limits': ['Source or waveform identity alone does not certify perfect articulation.', 'New final AAC recognition and artistic quality review have separate reports.', 'No human full-episode listening claim.']}
    snapshot = args.out_dir / 'verifier-snapshot.py'
    require(not snapshot.exists(), 'QA verifier snapshot already exists; choose a new output directory')
    shutil.copyfile(Path(__file__), snapshot)
    report['inputs']['verifier_snapshot'] = {'path': str(snapshot), 'sha256': sha(snapshot)}
    if args.captions:
        report['captions'] = captions_checks(events, args.captions)
    if args.precheck_only:
        report['audio'] = audio_checks(plan, events, None, master, args.ffmpeg, args.out_dir / 'audio', include_final_aac=False)
        report['status'] = 'pass-source-precheck-only'
    else:
        require(args.video and args.video.is_file(), '--video is required for finished-media verification')
        report['inputs']['video'] = {'path': str(args.video), 'sha256': sha(args.video)}
        if args.recognition_review:
            review = json.loads(args.recognition_review.read_text())
            require(review.get('accepted') is True and not review.get('unresolved'), 'Final AAC pronunciation review unresolved')
            recognition_source = review['source_video_sha256']
            inheritance = None
            if recognition_source != report['inputs']['video']['sha256']:
                require(args.content_identity, 'Recognition on another media hash needs complete content identity evidence')
                identity = json.loads(args.content_identity.read_text())
                require(identity['source']['sha256'] == recognition_source and identity['final']['sha256'] == report['inputs']['video']['sha256'], 'Encoded content inheritance hash mismatch')
                require(identity['all_rgb_frames_identical'] and identity['aac_packets_and_timestamps_identical'] and identity['frame_count'] == plan['duration_frames'], 'Content identity incomplete')
                inheritance = {'path': str(args.content_identity), 'sha256': sha(args.content_identity), 'all_rgb_frames': identity['frame_count'], 'all_aac_packets': identity['aac_packet_count']}
            for bound in review.get('inputs', {}).values():
                require(sha(path_of(bound['path'])) == bound['sha256'], 'Final AAC review evidence changed')
            report['final_aac_recognition'] = {'passed': True, 'path': str(args.recognition_review), 'sha256': sha(args.recognition_review),
                                               'summary': review['summary'], 'inheritance': inheritance, 'human_full_listening_claimed': False}
        if args.extend_report:
            base = json.loads(args.extend_report.read_text())
            require(base['status'] == 'pass', 'Only a complete passed base report can be extended')
            require(base['selected_mode'] == 'full-finished-media', 'Base report must include technical/audio/visual/captions checks')
            require(base['inputs']['video']['sha256'] == report['inputs']['video']['sha256'] and base['inputs']['timeline']['sha256'] == report['inputs']['timeline']['sha256'], 'Base target changed')
            base_snapshot = args.base_snapshot or args.extend_report.parent / 'verifier-snapshot.py'
            require(sha(base_snapshot) == base['inputs']['verifier']['sha256'], 'Base verifier implementation must be preserved at the mapped snapshot')
            for section in ('technical', 'audio', 'captions', 'visual', 'fades', 'pixel_engine_controls'):
                require(section in base, f'Missing base section {section}')
                report[section] = base[section]
            report['base_report'] = {'path': str(args.extend_report), 'sha256': sha(args.extend_report),
                                     'target_and_timeline_unchanged': True, 'original_verifier_path': base['inputs']['verifier']['path'],
                                     'original_verifier_sha256': base['inputs']['verifier']['sha256'],
                                     'immutable_verifier_snapshot': {'path': str(base_snapshot), 'sha256': sha(base_snapshot)},
                                     'inherited_sections': ['technical', 'audio', 'captions', 'visual', 'fades', 'pixel_engine_controls'],
                                     'policy': 'Old report, flags and implementation are preserved; stronger independent checks are added without rewriting original outcomes.'}
            report['schedule_negative_controls'] = schedule_negative_controls(plan, args.out_dir)
            report['numeric_identity_controls'] = numeric_identity_controls(args.out_dir / 'numeric-controls')
            report['numeric_identity'] = numeric_identity_checks(plan, events, counts, truths, args.video, args.ffmpeg, args.out_dir / 'numeric-identity')
            report['selected_mode'] = 'consolidated-extended-actual-media-qa'
            report['status'] = 'pass' if report['numeric_identity']['passed'] else 'fail'
            save(report_path, report)
            print(json.dumps({'status': report['status'], 'report': str(report_path)}, ensure_ascii=False), flush=True)
            return 0 if report['status'] == 'pass' else 1
        if not args.visual_only:
            report['technical'] = technical.verify_video(args.video, args.out_dir / 'technical', args.timeline, str(args.ffmpeg), str(args.ffprobe), duration_bounds=(480, 1200))
            report['audio'] = audio_checks(plan, events, args.video, master, args.ffmpeg, args.out_dir / 'audio')
        report['pixel_engine_controls'] = test_negative_controls(args.out_dir / 'pixel-controls')
        report['visual'] = visual_checks(plan, events, counts, truths, args.video, args.ffmpeg, args.out_dir / 'visual', args.reuse_half_dir, args.timeline)
        report['fades'] = fade_checks(plan, args.video, args.ffmpeg, args.out_dir / 'visual')
        report['schedule_negative_controls'] = schedule_negative_controls(plan, args.out_dir)
        report['numeric_identity_controls'] = numeric_identity_controls(args.out_dir / 'numeric-controls')
        report['numeric_identity'] = numeric_identity_checks(plan, events, counts, truths, args.video, args.ffmpeg, args.out_dir / 'numeric-identity')
        if args.export_final_aac:
            report['final_aac_excerpts'] = export_final_aac_clips(plan, events, args.video, args.ffmpeg, args.out_dir / 'final-aac-clips')
        sections = [report['math']['passed'], report['timing']['passed'], gate['passed'], report['visual']['passed'], report['fades']['passed'], report['numeric_identity']['passed']]
        if 'technical' in report:
            sections.append(report['technical']['status'] == 'pass')
        report['status'] = 'pass' if all(sections) else 'fail'
    save(report_path, report)
    print(json.dumps({'status': report['status'], 'report': str(report_path)}, ensure_ascii=False), flush=True)
    return 0 if report['status'].startswith('pass') else 1


if __name__ == '__main__':
    raise SystemExit(main())

