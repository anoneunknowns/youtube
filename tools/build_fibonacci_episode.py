"""Build the Fibonacci lesson from individually accepted, hash-bound source speech.

Speech is never stretched. Its measured 24kHz sample lengths drive every cue.
The shared series mixer applies only recorded linear gains and resampling.
"""
from __future__ import annotations

import argparse
from array import array
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import subprocess
from pathlib import Path
import wave

try:
    from .build_prime_episode import mix, probe_loudness, digest, save_new, local, resolve, srt_time, chapter
except ImportError:
    from build_prime_episode import mix, probe_loudness, digest, save_new, local, resolve, srt_time, chapter

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/fibonacci-counting-v1'
OUT = ROOT / 'output/fibonacci-counting-001-v001'
RATE, FPS = 24000, 30
CHECKPOINTS = (2, 8, 13, 18, 26, 39)
VALUES = [0, 1]
for _ in range(39):
    VALUES.append(VALUES[-2] + VALUES[-1])
VIDEO_NAME = 'paspla-studio-fibonacci-numbers-0-to-102334155-1080p.mp4'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def samples(seconds):
    return round(seconds * RATE)


def accepted_sources(manifest_path, gate_path):
    manifest, gate = read(manifest_path), read(gate_path)
    if manifest.get('measurement_status') != 'measured' or gate.get('accepted') is not True:
        raise ValueError('Measured speech and accepted individual source gate required')
    if gate.get('unresolved') or gate.get('summary', {}).get('unresolved', 0):
        raise ValueError('Unresolved speech warnings')
    if gate.get('source_manifest_sha256') != digest(manifest_path):
        raise ValueError('Speech gate does not bind the current manifest')
    voice = manifest['voice']
    if voice['voice_id'] != 'af_heart' or voice['generation_speed'] != .98 or voice['dtype'] != 'fp32':
        raise ValueError('Voice/model policy mismatch')
    authored = read(DESIGN / 'narration.json')
    expected = {r['id']: r for r in authored}
    approvals = {r['id']: r for r in gate['results']}
    checked = set()

    def evidence(node):
        if isinstance(node, dict):
            if isinstance(node.get('path'), str) and isinstance(node.get('sha256'), str):
                path = resolve(node['path'])
                if not path.exists():
                    path = resolve(node['path'], gate_path.parent)
                key = (str(path), node['sha256'])
                if key not in checked:
                    if not path.is_file() or digest(path) != node['sha256']:
                        raise ValueError(f'Acceptance evidence changed: {path}')
                    checked.add(key)
            for child in node.values():
                evidence(child)
        elif isinstance(node, list):
            for child in node:
                evidence(child)

    evidence(gate.get('inputs', {}))
    result = {}
    for row in manifest['numbers'] + manifest['dialogue']:
        ident = row['id']
        if ident not in expected or ident in result:
            raise ValueError(f'Unexpected or duplicate source {ident}')
        cue = expected[ident]
        text = row.get('spoken_text', row.get('text'))
        if text != cue['text']:
            raise ValueError(f'Authored text changed: {ident}')
        if cue['kind'] == 'count' and row['number'] != cue['value']:
            raise ValueError(f'Value/index confusion: {ident}')
        source = resolve(row['path'], manifest_path.parent)
        if not source.exists():
            source = resolve(row['path'])
        if digest(source) != row['sha256']:
            raise ValueError(f'Source checksum mismatch: {ident}')
        with wave.open(str(source)) as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (RATE, 1, 2):
                raise ValueError(f'Expected 24k mono16 source: {ident}')
            length = wav.getnframes()
        if abs(length / RATE - row['duration_s']) > 1 / RATE:
            raise ValueError(f'Incorrect duration: {ident}')
        approval = approvals.get(ident, {})
        if (approval.get('accepted') is not True or approval.get('failures')
                or approval.get('source_sha256') != row['sha256']):
            raise ValueError(f'Individual source is not approved: {ident}')
        result[ident] = {**row, 'text': text, 'spoken_text': text,
                         'path': local(source), 'source_path': local(source), 'source_sha256': row['sha256'],
                         'sample_frames_24k': length, 'duration_s': length / RATE}
    if set(result) != set(expected) or len(result) != 104:
        raise ValueError('All 104 authored utterances are required')
    return authored, result


def operator_times(event, phoneme_rows):
    """Use independently decoded operator tokens when present; label fallback."""
    tokens = phoneme_rows.get(event['id'], {}).get('tokens', [])
    # Some CTC vocabulary entries contain several phones (for example əl).
    normalized = [(ch, r) for r in tokens for ch in r['token'].replace('ː', '').replace('ᵻ', 'ɪ')]
    plus = equals = None
    for i in range(len(normalized) - 3):
        if (normalized[i][0] == 'p' and normalized[i + 1][0] == 'l'
                and normalized[i + 2][0] in ('ʌ', 'a') and normalized[i + 3][0] == 's'):
            plus = (normalized[i][1]['start_s'], normalized[i + 3][1]['end_s'])
    for i in range(len(normalized) - 4):
        if [x[0] for x in normalized[i:i + 5]] == ['k', 'w', 'ə', 'l', 'z']:
            equals = normalized[i][1]['start_s']
            if i and normalized[i - 1][0] in ('i', 'ɪ', 'e'):
                equals = normalized[i - 1][1]['start_s']
    if plus and equals and plus[1] < equals < event['duration_s']:
        return {'method': 'independent-CTC-operator-token-sequences; approximate20ms resolution',
                'plus_start_s': event['start_s'] + plus[0],
                'b_start_s': event['start_s'] + plus[1],
                'equals_start_s': event['start_s'] + equals,
                'source_sha256': event['source_sha256']}
    left, right = event['text'].removesuffix(' equals').split(' plus ')
    a_words = len(left.replace('-', ' ').split())
    b_words = len(right.replace('-', ' ').split())
    total = a_words + b_words + 2
    return {'method': 'word-count proportional visual emphasis estimate; not measured word alignment',
            'plus_start_s': event['start_s'] + event['duration_s'] * a_words / total,
            'b_start_s': event['start_s'] + event['duration_s'] * (a_words + 1) / total,
            'equals_start_s': event['start_s'] + event['duration_s'] * (a_words + b_words + 1) / total,
            'source_sha256': event['source_sha256']}


def make_plan(authored, sources, phonemes=None):
    events = []
    cursor = samples(.8)
    for i, cue in enumerate(authored):
        source = sources[cue['id']]
        end = cursor + source['sample_frames_24k']
        n = cue.get('index')
        row = {**source, 'id': cue['id'], 'kind': cue['kind'], 'role': 'number' if cue['kind'] == 'count' else 'dialogue',
               'index': n, 'n': n, 'value': cue.get('value'), 'decimal_value': cue.get('value'),
               'scene_id': cue['scene_id'], 'translation_ja': cue['translation_ja'],
               'start_s': cursor / RATE, 'end_s': end / RATE,
               'start_sample_24k': cursor, 'end_sample_24k': end}
        events.append(row)
        cursor = end
        if cue['kind'] in ('intro', 'outro'):
            cursor += samples(.6)
        elif cue['kind'] == 'formula_prefix':
            cursor += samples(.16)
        elif cue['kind'] == 'count':
            cursor += samples(.6 if n in CHECKPOINTS or n == 40 else 2)
        elif cue['kind'] == 'explanation':
            cursor += samples(.6)
            if i + 1 < len(authored) and authored[i + 1]['kind'] != 'explanation':
                cursor += samples(2)
        else:
            raise ValueError(cue['kind'])
    cursor += samples(1.4)
    by_id = {r['id']: r for r in events}
    phoneme_rows = {r['id']: r for r in (phonemes or {}).get('results', [])}
    for row in events:
        if row['kind'] == 'formula_prefix':
            row['highlight_timing'] = operator_times(row, phoneme_rows)
    duration = cursor / RATE
    finale_start = by_id['O01']['start_s'] - .12
    counted, visual, teaching = [], [], []

    def segment(mode, start, end, n=None, **params):
        if end - start <= 1e-8:
            return
        visual.append({'mode': mode, 'scene': mode, 'index': n, 'n': n,
                       'start_s': start, 'end_s': end, 'params': params})

    boundaries = [(0, 'opening'), (by_id['I02']['start_s'] - .12, 'seeds'),
                  (by_id['I03']['start_s'] - .12, 'rule'),
                  (by_id['I05']['start_s'] - .12, 'legend'),
                  (by_id['I08']['start_s'] - .12, 'opening'),
                  (by_id['N000']['start_s'] - .12, None)]
    for (start, mode), (end, _) in zip(boundaries, boundaries[1:]):
        segment(mode, start, end, None, phase='intro', reveal_final_value=False)
    for n, value in enumerate(VALUES):
        event = by_id[f'N{n:03}']
        prefix = by_id.get(f'E{n:03}')
        display = event['start_s'] - .12
        start = prefix['start_s'] if prefix else display
        if n < 39:
            end = by_id[f'E{n + 1:03}']['start_s'] if n >= 1 else by_id['N001']['start_s'] - .12
        elif n == 39:
            end = by_id['E040']['start_s']
        else:
            end = finale_start
        explanations = [e for e in events if e['kind'] == 'explanation' and e['index'] == n]
        if explanations:
            transfer_start = explanations[-1]['end_s'] + .6
            transfer_end = transfer_start + 1.2
        elif 2 <= n < 40:
            transfer_start, transfer_end = event['end_s'] + .35, event['end_s'] + 1.55
        else:
            transfer_start = transfer_end = None
        a, b = (VALUES[n - 2], VALUES[n - 1]) if n >= 2 else (None, None)
        state = {'index': n, 'n': n, 'value': value, 'decimal_value': value, 'ordinal': n + 1,
                 'a': a, 'b': b, 'c': value, 'operands': [a, b] if n >= 2 else [],
                 'cycle_start_s': start, 'cycle_end_s': end, 'start_s': start, 'end_s': end,
                 'formula_start_s': prefix['start_s'] if prefix else None,
                 'formula_end_s': prefix['end_s'] if prefix else None,
                 'expression_start_s': prefix['start_s'] if prefix else None,
                 'expression_end_s': prefix['end_s'] if prefix else None,
                 'result_start_s': display, 'result_end_s': event['end_s'],
                 'display_start_s': display, 'display_end_s': end,
                 'voice_start_s': event['start_s'], 'voice_end_s': event['end_s'],
                 'voice_event_id': event['id'], 'formula_event_id': prefix['id'] if prefix else None,
                 'transfer_start_s': transfer_start, 'transfer_end_s': transfer_end,
                 'spoken_text': event['text']}
        counted.append(state)
        if n < 2:
            segment('seeds', start, end, n, phase='count', seed_index=n, stage='result')
            continue
        timing = prefix['highlight_timing']
        split_a = max(start + 1 / RATE, min(timing['plus_start_s'], display - 2 / RATE))
        split_b = max(split_a + 1 / RATE, min(timing['equals_start_s'], display - 1 / RATE))
        segment('count', start, split_a, n, stage='input-a', highlight_timing=timing)
        segment('count', split_a, split_b, n, stage='input-b', highlight_timing=timing)
        segment('count', split_b, display, n, stage='flow', highlight_timing=timing)
        if explanations:
            replay_start = explanations[0]['start_s'] - .12
            segment('count', display, replay_start, n, stage='result')
            for i, ex in enumerate(explanations):
                finish = explanations[i + 1]['start_s'] - .12 if i + 1 < len(explanations) else transfer_start
                segment('replay', ex['start_s'] - .12, finish, n,
                        after_index=n, explanation_scene_id=ex['scene_id'],
                        voice_event_id=ex['id'], step=i, show_replay_label=True)
            teaching.append({'index': n, 'after_index': n, 'start_s': replay_start,
                             'end_s': transfer_start, 'scene_ids': [e['scene_id'] for e in explanations],
                             'voice_event_ids': [e['id'] for e in explanations]})
        elif transfer_start is not None:
            segment('count', display, transfer_start, n, stage='result')
        else:
            segment('count', display, end, n, stage='result')
        if transfer_start is not None:
            segment('count', transfer_start, end, n, stage='transfer',
                    transfer_start_s=transfer_start, transfer_end_s=transfer_end,
                    next_pair=[b, value], next_pair_indices=[n - 1, n])
    segment('finale', finale_start, duration, 40, reveal_final_value=True,
            history_indices=list(range(41)))
    scenes = [{'scene': row['mode'], **row} for row in visual]
    plan = {'schema_version': 1, 'kind': 'measured-fibonacci-counting-timeline',
            'episode_id': 'fibonacci-counting-001', 'revision_id': 'fibonacci-counting-v001',
            'status': 'measured-accepted-speech', 'fps': FPS, 'width': 1920, 'height': 1080,
            'duration_s': duration, 'duration_frames': math.ceil(duration * FPS - 1e-8),
            'count_index_start': 0, 'count_index_end': 40, 'count_start': 0,
            'count_end': VALUES[-1], 'counted_values': 41, 'voice_event_count': len(events),
            'source_sample_rate_hz': RATE, 'master_sample_rate_hz': 48000,
            'master_channels': 2, 'voice_events': events, 'events': events,
            'counted_states': counted, 'visual_segments': visual, 'scenes': scenes,
            'teaching': teaching, 'intro': {'start_s': 0, 'end_s': counted[0]['start_s'], 'fade_in_s': .8},
            'finale': {'start_s': finale_start, 'end_s': duration, 'fade_last_s': 2},
            'timing': {'result_display_lead_s': .12, 'formula_prefix_to_result_gap_s': .16,
                       'ordinary_result_end_to_next_formula_start_s': 2,
                       'checkpoint_after_indices': list(CHECKPOINTS),
                       'fixed_transition_sum_s': 107.04,
                       'highlight_word_boundary_policy': 'independent CTC operator-token timings where available; clearly labeled word-count estimate otherwise'},
            'voice_sum_s': sum(e['duration_s'] for e in events),
            'bgm': False, 'sound_effects': [],
            'source_script': {'path': local(DESIGN / 'narration.json'), 'sha256': digest(DESIGN / 'narration.json')},
            'renderer_implementation': 'tools/render_fibonacci_video.py',
            'verifier_implementation': 'tools/verify_fibonacci_video.py'}
    validate(plan)
    return plan


def validate(plan, require_minimum=True):
    events, states = plan['voice_events'], plan['counted_states']
    if len(events) != 104 or len({e['id'] for e in events}) != 104:
        raise ValueError('Incorrect utterance coverage')
    if [s['value'] for s in states] != VALUES or [s['index'] for s in states] != list(range(41)):
        raise ValueError('Fibonacci sequence/index mismatch')
    by_id = {e['id']: e for e in events}
    if [by_id[f'N{n:03}']['value'] for n in range(41)] != VALUES:
        raise ValueError('Count voice values do not match the indexed sequence')
    for left, right in zip(events, events[1:]):
        if left['end_sample_24k'] > right['start_sample_24k']:
            raise ValueError('Overlapping utterances')
    for n, state in enumerate(states):
        if abs(state['voice_start_s'] - state['result_start_s'] - .12) > 1e-8:
            raise ValueError('Incorrect result-display lead')
        if n >= 2:
            expected_prefix = by_id[f'N{n-2:03}']['text'] + ' plus ' + by_id[f'N{n-1:03}']['text'] + ' equals'
            if by_id[f'E{n:03}']['text'] != expected_prefix:
                raise ValueError('Expression prefix must contain the two operands and no repeated result')
            if state['a'] + state['b'] != state['value']:
                raise ValueError('Incorrect operands')
            if abs(by_id[f'N{n:03}']['start_s'] - by_id[f'E{n:03}']['end_s'] - .16) > 1e-8:
                raise ValueError('Incorrect formula/result boundary')
        if n not in CHECKPOINTS and 1 <= n < 40:
            if abs(by_id[f'E{n+1:03}']['start_s'] - by_id[f'N{n:03}']['end_s'] - 2) > 1e-8:
                raise ValueError('Ordinary 2-second handoff changed')
    if abs(by_id['N001']['start_s'] - by_id['N000']['end_s'] - 2) > 1e-8:
        raise ValueError('Initial seed pace changed')
    previous = 0
    for row in plan['visual_segments']:
        if abs(row['start_s'] - previous) > 1e-7 or row['end_s'] <= row['start_s']:
            raise ValueError(f'Noncontiguous visual segment: {row}')
        previous = row['end_s']
    if abs(previous - plan['duration_s']) > 1e-7:
        raise ValueError('Visual timeline does not cover delivery')
    if abs(plan['duration_s'] - plan['voice_sum_s'] - 107.04) > 1e-7:
        raise ValueError('Measured fixed transition sum changed')
    if require_minimum and plan['duration_s'] < 480:
        raise ValueError('Measured delivery is shorter than eight minutes; useful script/range revision required')
    return {'passed': True, 'voice_events': 104, 'counted_states': 41,
            'duration_s': plan['duration_s'], 'fixed_transition_sum_s': 107.04}


def deliveries(plan, out):
    subtitles = '\n'.join(f'{i}\n{srt_time(e["start_s"])} --> {srt_time(e["end_s"])}\n{e["text"]}\n'
                          for i, e in enumerate(plan['voice_events'], 1))
    for name in ('subtitles.srt', 'english-captions.srt'):
        with (out / name).open('x') as stream:
            stream.write(subtitles)
    states = {s['index']: s for s in plan['counted_states']}
    marks = [(0, 'Welcome to the Cloud Post Office'),
             (states[0]['start_s'], 'Zero and one, then add the previous two'),
             (next(t['start_s'] for t in plan['teaching'] if t['index'] == 8), 'A closer look at carrying'),
             (states[21]['start_s'], 'Bigger values, the same rule'),
             (states[31]['start_s'], 'Into the millions'),
             (states[40]['start_s'], 'The first term above 100 million'),
             (plan['finale']['start_s'], '41 terms, one continuing rule')]
    # The published timestamps use whole seconds; validate those actual values.
    stamps = [int(t) for t, _ in marks]
    if (len(stamps) < 3 or stamps[0] != 0
            or any(b - a < 10 for a, b in zip(stamps, stamps[1:]))
            or plan['duration_s'] - stamps[-1] < 10):
        raise ValueError('YouTube chapter list needs at least3 entries and10seconds per chapter')
    chapters = '\n'.join(f'{chapter(t)} {title}' for t, title in marks) + '\n'
    title = 'Fibonacci Numbers: Watch the Formula Work | 0 to 102,334,155 | Num-Num Numbers'
    description = ("Watch each new Fibonacci number emerge from the previous two, with our Siamese cat guide above the clouds!\n\n"
                   "We start at F0 = 0 and F1 = 1, keep both ones, and count all 41 terms through F40 = 102,334,155, the first term above 100 million. Two starting values and 39 additions make 41 indexed terms. For n >= 2, Fn = F(n-2) + F(n-1).\n\n"
                   "Two number windows enter an addition, a new value appears, and the newest pair moves into the next calculation. Close views show place value and carrying. Natural American English reads each expression prefix and then its result once.\n\n"
                   "No background music or sound effects. Number windows show numerical values; they do not stand for that many physical objects.\n\nCHAPTERS\n"
                   + chapters + '\nPaspla Studio — Num-Num Numbers\n#Fibonacci #LearnNumbers #MathForKids\n')
    for name, text in (('chapters.txt', chapters), ('youtube-title.txt', title + '\n'),
                       ('youtube-description.txt', description), ('upload-details.txt', title + '\n\n' + description)):
        with (out / name).open('x') as stream:
            stream.write(text)


def mix_truepeak_scalars(plan, out, ffmpeg, balance_rms_dbfs=-19, codec_corrections=None):
    """One constant scalar per source, preserving the established raw PCM cap.

    Source-specific resampled true peaks are measured before choosing scalars.
    This addresses intersample overshoot in a few utterances that would otherwise
    constrain the common delivery gain. There is no time-varying gain, limiter,
    compression, source editing or stretching.
    """
    work = out / '.work/linear-truepeak-v001'
    work.mkdir(parents=True, exist_ok=False)
    codec_gains = {}
    events_by_id = {e['id']: e for e in plan['voice_events']}
    for correction in (codec_corrections or {}).get('results', []):
        row = events_by_id.get(correction['id'])
        if (row is None or correction['source_sha256'] != row['source_sha256']
                or not -12 <= correction['gain_db'] <= 0):
            raise ValueError('AAC correction does not bind this source, or is not a nonpositive whole-utterance scalar')
        codec_gains[row['id']] = correction['gain_db']

    def converted(row, gain_db):
        raw = subprocess.check_output([ffmpeg, '-v', 'error', '-i', str(resolve(row['source_path'])),
                                       '-af', f'volume={gain_db:.12f}dB:precision=double',
                                       '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s24le', '-f', 's24le', 'pipe:1'])
        if len(raw) != row['sample_frames_24k'] * 2 * 2 * 3:
            raise ValueError('Source length changed during linear resampling')
        return raw

    def write_wave(path, pcm):
        with wave.open(str(path), 'wb') as wav:
            wav.setnchannels(2)
            wav.setsampwidth(3)
            wav.setframerate(48000)
            wav.writeframes(pcm)

    def measure(row):
        with wave.open(str(resolve(row['source_path']))) as wav:
            values = array('h', wav.readframes(wav.getnframes()))
        peak = 20 * math.log10(max(abs(v) for v in values) / 32768)
        rms = 20 * math.log10(math.sqrt(sum(v * v for v in values) / len(values)) / 32768)
        base = min(max(0, balance_rms_dbfs - rms), -4.5 - peak)
        path = work / f'{row["id"]}-base48k.wav'
        write_wave(path, converted(row, base))
        probe = probe_loudness(ffmpeg, path)
        return {'id': row['id'], 'source_sha256': row['source_sha256'], 'source_peak_dbfs': peak,
                'source_rms_dbfs': rms, 'base_gain_db': base, 'base_48k_probe': probe,
                'base_48k_path': local(path), 'base_48k_sha256': digest(path)}

    with ThreadPoolExecutor(max_workers=4) as pool:
        measured = list(pool.map(measure, plan['voice_events']))
    reference_tp = min(float(r['base_48k_probe']['input_tp']) for r in measured) - .03
    by_id = {r['id']: r for r in measured}
    total_frames = samples(plan['duration_s']) * 2
    data = bytearray(total_frames * 2 * 3)
    for row in plan['voice_events']:
        receipt = by_id[row['id']]
        additional = reference_tp - float(receipt['base_48k_probe']['input_tp'])
        codec_gain = codec_gains.get(row['id'], 0)
        gain = receipt['base_gain_db'] + additional + codec_gain
        if gain + receipt['source_peak_dbfs'] > -4.5 + 1e-9 or additional > 1e-9:
            raise ValueError('Established per-source PCM peak cap changed')
        row.update(source_peak_dbfs=receipt['source_peak_dbfs'], source_rms_dbfs=receipt['source_rms_dbfs'],
                   mix_gain_db=gain, per_source_truepeak_calibration_db=additional,
                   aac_codec_calibration_gain_db=codec_gain)
        receipt.update(additional_constant_gain_db=additional, aac_codec_calibration_gain_db=codec_gain,
                       final_source_gain_db=gain)
        pcm = converted(row, gain)
        start = row['start_sample_24k'] * 2 * 2 * 3
        data[start:start + len(pcm)] = pcm
    raw = work / 'master-linear-truepeak-balanced.wav'
    write_wave(raw, data)
    before = probe_loudness(ffmpeg, raw)
    gain = min(-16 - float(before['input_i']), -2.04 - float(before['input_tp']))
    candidate = work / 'master-level-test.wav'
    subprocess.run([ffmpeg, '-v', 'error', '-i', str(raw), '-af', f'volume={gain:.12f}dB:precision=double',
                    '-c:a', 'pcm_s24le', str(candidate)], check=True)
    after = probe_loudness(ffmpeg, candidate)
    passed = float(after['input_tp']) <= -2 and abs(float(after['input_i']) + 16) <= 1
    receipt = {'kind': 'constant-per-source-truepeak-linear-master-calibration', 'passed': passed,
               'raw_source_peak_cap_dbfs': -4.5, 'rms_reference_dbfs': balance_rms_dbfs,
               'resampled_reference_truepeak_dbfs': reference_tp, 'source_measurements': measured,
               'common_gain_db': gain, 'before': before, 'after': after,
               'codec_whole_utterance_corrections': codec_corrections or {},
               'policy': 'A single scalar for the entire utterance, plus one common scalar. No dynamic processing. Every source file is unchanged; exact source lengths and silent gaps are preserved.'}
    save_new(work / 'level-report.json', receipt)
    if not passed:
        candidate.rename(work / 'master-level-rejected.wav')
        raise ValueError(f'Constant-scalar truepeak calibration failed: {after}')
    master = out / 'master.wav'
    candidate.rename(master)
    return {'path': local(master), 'sha256': digest(master), 'sample_rate_hz': 48000,
            'channels': 2, 'sample_width_bits': 24, 'duration_s': plan['duration_s'],
            'source_gain_db': gain, 'common_gain_db': gain, 'per_source_balancing_applied': True,
            'per_source_policy': 'Established -4.5dBFS raw-source cap and RMS reference, followed by an additional nonpositive constant scalar chosen from each48k resampled true peak.',
            'source_gains': [{'id': e['id'], 'source_sha256': e['source_sha256'], 'gain_db': e['mix_gain_db']}
                             for e in plan['voice_events']],
            'master_level_attempt': local(work / 'level-report.json'),
            'before': before, 'after': after,
            'method': 'Nonoverlapping original speech, one constant gain per source,48k24bit stereo resampling and one common delivery gain. No compression, limiting, time stretch or source overwrites.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--speech-manifest', type=Path, default=OUT / 'speech/measurements.json')
    parser.add_argument('--speech-gate', type=Path, default=OUT / 'speech/speech-acceptance.json')
    parser.add_argument('--phonemes', type=Path, default=OUT / 'speech/isolated-phonemes-selected.json')
    parser.add_argument('--out-dir', type=Path, default=OUT)
    parser.add_argument('--revision-id', default='fibonacci-counting-v001',
                        help='Audio input revision label; default preserves the original v001 recipe')
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--plan-only', action='store_true')
    parser.add_argument('--balance-rms-dbfs', type=float, default=-19)
    parser.add_argument('--linear-truepeak-calibration', action='store_true', default=True,
                        help='Default: calibrate resampled true peaks using only constant nonpositive source scalars')
    parser.add_argument('--series-rms-only', action='store_false', dest='linear_truepeak_calibration',
                        help='Diagnostic legacy RMS-only mix; retained for reproducing the initial rejected level attempts')
    parser.add_argument('--codec-corrections', type=Path, default=OUT / 'speech/aac-scalar-corrections.json',
                        help='Adopted source-hash-bound, nonpositive whole-utterance AAC calibration scalars, when present')
    args = parser.parse_args()
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    for name in ('timeline.json', 'master.wav', 'subtitles.srt', 'build-record.json'):
        if (out / name).exists():
            raise FileExistsError(f'Refusing to replace {out / name}')
    authored, sources = accepted_sources(args.speech_manifest.resolve(), args.speech_gate.resolve())
    phonemes = read(args.phonemes) if args.phonemes.exists() else None
    plan = make_plan(authored, sources, phonemes)
    plan['revision_id'] = args.revision_id
    if args.plan_only:
        save_new(out / 'timeline.json', plan)
        print(json.dumps(validate(plan)))
        return
    codec_corrections = read(args.codec_corrections) if args.codec_corrections.exists() else None
    levels = (mix_truepeak_scalars(plan, out, args.ffmpeg, args.balance_rms_dbfs, codec_corrections)
              if args.linear_truepeak_calibration else mix(plan, out, args.ffmpeg, args.balance_rms_dbfs))
    plan['audio'] = levels
    plan['master'] = levels
    plan['master_audio'] = levels
    plan['speech_manifest'] = {'path': local(args.speech_manifest), 'sha256': digest(args.speech_manifest)}
    plan['speech_acceptance'] = {'path': local(args.speech_gate), 'sha256': digest(args.speech_gate)}
    if codec_corrections:
        plan['codec_scalar_corrections'] = {'path': local(args.codec_corrections), 'sha256': digest(args.codec_corrections)}
    save_new(out / 'timeline.json', plan)
    deliveries(plan, out)
    record = {'kind': 'fibonacci-production-input-build', 'status': 'measured-speech-and-master-built',
              'timeline': {'path': local(out / 'timeline.json'), 'sha256': digest(out / 'timeline.json')},
              'speech_manifest': {'path': local(args.speech_manifest), 'sha256': digest(args.speech_manifest)},
              'speech_gate': {'path': local(args.speech_gate), 'sha256': digest(args.speech_gate)},
              'master': levels, 'validation': validate(plan), 'video_rendered': False,
              'source_audio_retimed_or_overwritten': False, 'video_filename': VIDEO_NAME}
    save_new(out / 'build-record.json', record)
    print(json.dumps({'duration_s': plan['duration_s'], 'frames': plan['duration_frames'],
                      'speech_events': len(plan['voice_events']), 'master': levels['after']}))


if __name__ == '__main__':
    main()
