"""Bind reviewed speech, schedule the even-number lesson and mix its master."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import shutil
import tempfile

from build_four_base_episode import delivery_probe, mix_balanced
from build_four_base_episode_v002 import accepted_numbers
from build_octal_episode import checked_wav, dialogue_key, event, local_path
from export_octal_delivery import format_srt
from prepare_even_episode import digest


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/even-counting-v1'
OUTPUT = ROOT / 'output/even-counting-001-v001'
RATE = 24000
FPS = 30
VIDEO_NAME = 'paspla-studio-even-numbers-0-to-200-1080p.mp4'


def read(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def save(path: Path, value) -> None:
    with path.open('x', encoding='utf-8', newline='\n') as target:
        json.dump(value, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.write('\n')


def source_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def samples(seconds: float) -> int:
    return round(seconds * RATE)


def script_cues() -> list[dict]:
    result = []
    for line in (DESIGN / 'script-and-sound-cues.txt').read_text(encoding='utf-8').splitlines():
        fields = line.split(' | ')
        if not re.fullmatch(r'I\d{2}[A-Z]?|T\d{3}|F\d{2}', fields[0]):
            continue
        offset = 1 if fields[0].startswith('T') else 0
        begin, end = map(float, fields[1 + offset].split('–'))
        result.append({'id': fields[0], 'relative_window_s': [begin, end],
                       'text': fields[2 + offset], 'japanese': fields[3 + offset],
                       'direction': fields[4 + offset],
                       'phase': 'intro' if fields[0].startswith('I') else
                                'teaching' if fields[0].startswith('T') else 'finale'})
    expected = {'I01', 'I02', 'I03', 'I04', 'I05', 'I06', 'I06B', 'I07',
                'T020', 'T100', 'F01', 'F02', 'F03', 'F04'}
    if len(result) != 14 or {row['id'] for row in result} != expected:
        raise ValueError('The script does not have exactly fourteen unique spoken cues')
    return result


def reviewed_dialogue(measurements_path: Path, gate_path: Path, cues: list[dict]) -> dict:
    manifest, gate = read(measurements_path), read(gate_path)
    if (gate.get('accepted') is not True or gate.get('unresolved')
            or gate.get('summary', {}).get('unresolved', 0)):
        raise ValueError('Dialogue acceptance still has unresolved findings')
    inputs = gate.get('inputs', {})
    bound = inputs.get('manifest', inputs.get('measurements'))
    if bound is None or bound['sha256'] != digest(measurements_path):
        raise ValueError('Dialogue acceptance is not bound to these measurements')
    for reference in inputs.values():
        if isinstance(reference, dict) and 'path' in reference and 'sha256' in reference:
            if digest(source_path(reference['path'])) != reference['sha256']:
                raise ValueError(f'Changed dialogue review input: {reference["path"]}')
    raw = manifest['dialogue']
    rows = {row['id']: row for row in raw} if isinstance(raw, list) else raw
    if set(rows) != {row['id'] for row in cues}:
        raise ValueError('Adopted dialogue IDs differ from the actual script')
    result = {}
    for cue in cues:
        row = rows[cue['id']]
        text = row.get('text', row.get('spoken_text', ''))
        if text != cue['text']:
            raise ValueError(f'Adopted text differs: {cue["id"]}')
        path = source_path(row['path'])
        count = checked_wav(path, row['sha256'], row['duration_s'], RATE, 1)
        if row.get('sample_frames', count) != count:
            raise ValueError(f'Wrong source frame count: {cue["id"]}')
        result[cue['id']] = {**row, 'path': local_path(path), 'sample_frames': count,
                              'duration_s': count / RATE, 'text': text}
    return result


def make_plan(numbers: dict, dialogue: dict, cues: list[dict]) -> dict:
    estimate = read(DESIGN / 'estimated-timeline.json')
    counted, scenes, events, teaching = [], [], [], []
    scenes.append({'scene': 'intro', 'start_s': 0, 'end_s': 36})
    cursor = samples(36)
    for value in range(0, 201, 2):
        source = numbers[value]
        start = cursor
        item = event(source, f'N{value:03d}', 'number_voice', 'count', start + samples(.12),
                     source['spoken_text'], decimal_value=value, narration_base=10)
        item['role'] = item['type']
        end = item['end_sample_24k']
        cursor = end + samples(.28 if value == 200 else 1.88)
        extra = None
        if value in (20, 100):
            cursor += samples(8)
            extra = {'id': f'T{value:03d}', 'start_s': (end + samples(.4)) / RATE,
                     'end_s': (end + samples(8.4)) / RATE, 'decimal_value': value}
            teaching.append(extra)
        scene = {'scene': 'count', 'decimal_value': value, 'start_s': start / RATE,
                 'end_s': cursor / RATE, 'voice_start_s': item['start_s'],
                 'voice_end_s': item['end_s'], 'spoken_text': item['text']}
        if extra:
            scene['teaching'] = extra
        scenes.append(scene)
        counted.append({**scene, 'display_start_s': scene['start_s'], 'display_end_s': scene['end_s'],
                        'voice_event_id': item['id']})
        events.append(item)
    finale_start = cursor / RATE
    duration = (cursor + samples(14)) / RATE
    scenes.append({'scene': 'finale', 'start_s': finale_start, 'end_s': duration})
    origins = {row['id']: row['start_s'] for row in teaching}
    for cue in cues:
        origin = 0 if cue['phase'] == 'intro' else finale_start if cue['phase'] == 'finale' else origins[cue['id']]
        begin, limit = (samples(origin) + samples(t) for t in cue['relative_window_s'])
        source = dialogue[cue['id']]
        item = event(source, cue['id'], 'dialogue', cue['phase'], begin, cue['text'])
        item['role'] = item['type']
        if item['end_sample_24k'] > limit:
            raise ValueError(f'Actual speech does not fit {cue["id"]}: '
                             f'{source["duration_s"]} seconds in {(limit - begin) / RATE}')
        cue.update(start_s=item['start_s'], end_s=item['end_s'])
        events.append(item)
    events.sort(key=lambda row: row['start_sample_24k'])
    plan = {
        'schema_version': 1, 'episode_id': 'even-counting-001', 'revision_id': 'even-counting-v001',
        'kind': 'measured-even-counting-timeline', 'status': 'measured-and-reviewed-speech',
        'count_start': 0, 'count_end': 200, 'count_step': 2, 'fps': FPS,
        'duration_s': duration, 'duration_frames': math.ceil(duration * FPS - 1e-7),
        'master_sample_rate_hz': 48000, 'master_channels': 2,
        'source_sample_rate_hz': RATE, 'bgm': False, 'sound_effects': [],
        'source_script': {'path': local_path(DESIGN / 'script-and-sound-cues.txt'),
                          'sha256': digest(DESIGN / 'script-and-sound-cues.txt')},
        'count_lines': {'path': local_path(DESIGN / 'count-lines.json'),
                        'sha256': digest(DESIGN / 'count-lines.json')},
        'numeric_sources': numbers, 'dialogue_cues': cues,
        'scenes': scenes, 'counted_states': counted, 'teaching': teaching,
        'voice_events': events, 'events': events,
        'intro': {'start_s': 0, 'end_s': 36},
        'finale': {'start_s': finale_start, 'end_s': duration, 'fade_last_s': 2},
        'timing': {'display_lead_s': .12, 'ordinary_number_gap_s': 2,
                   'ordinary_boundaries': 98, 'teaching_number_gap_s': 10,
                   'teaching_boundaries': 2, 'final_number_hold_s': .28},
        'audio_generated': True, 'video_generated': False,
        'estimate_cross_check_s': estimate['totals']['estimated_video_s'],
    }
    validate(plan)
    return plan


def validate(plan: dict) -> dict:
    events, scenes = plan['events'], plan['scenes']
    counted = [row for row in events if row['phase'] == 'count']
    if [row['decimal_value'] for row in counted] != list(range(0, 201, 2)):
        raise ValueError('Count sequence is not all 101 evens from zero to two hundred')
    if len(events) != 115 or len({row['id'] for row in events}) != 115:
        raise ValueError('There must be 101 number events and fourteen dialogue events')
    if any(a['end_sample_24k'] > b['start_sample_24k'] for a, b in zip(events, events[1:])):
        raise ValueError('Speech events overlap')
    if any(a['end_s'] != b['start_s'] for a, b in zip(scenes, scenes[1:])):
        raise ValueError('Visual scenes are not continuous')
    gaps = Counter()
    for state, utterance in zip(plan['counted_states'], counted, strict=True):
        if samples(utterance['start_s'] - state['start_s']) != samples(.12):
            raise ValueError('A count does not have the requested display lead')
    for current, following in zip(counted, counted[1:]):
        gap = following['start_sample_24k'] - current['end_sample_24k']
        if gap != samples(10 if current['decimal_value'] in (20, 100) else 2):
            raise ValueError('Incorrect number-to-number speech spacing')
        gaps[gap] += 1
    if gaps != {samples(2): 98, samples(10): 2}:
        raise ValueError('Incorrect boundary coverage')
    if samples(plan['finale']['start_s']) - counted[-1]['end_sample_24k'] != samples(.28):
        raise ValueError('Final value hold is incorrect')
    if abs(plan['duration_s'] - plan['estimate_cross_check_s']) > 1 / RATE:
        raise ValueError('Measured scheduling differs from the approved estimate')
    return {'counted_values': 101, 'voice_events': 115, 'ordinary_boundaries_2s': 98,
            'teaching_boundaries_10s': 2, 'duration_s': plan['duration_s'],
            'duration_frames': plan['duration_frames'], 'all_actual_dialogue_fits_windows': True}


def export_delivery(plan: dict, output: Path) -> dict:
    rows = [(row['start_s'], row['end_s'], row['text'][0].upper() + row['text'][1:]
             + ('.' if row['type'] == 'number_voice' else '')) for row in plan['events']]
    if len(rows) != 115 or any(a[1] > b[0] for a, b in zip(rows, rows[1:])):
        raise ValueError('Captions overlap or have missing events')
    marks = [(0, 'What Are Even Numbers?'), (36, 'Count by Twos from Zero')]
    marks += [(math.floor(row['start_s']), 'Twenty Blocks, Ten Pairs' if row['id'] == 'T020'
               else 'The Last Digit of an Even Number') for row in plan['teaching']]
    marks.append((math.floor(plan['finale']['start_s']), 'We Reached Two Hundred'))
    if any(b[0] - a[0] < 10 for a, b in zip(marks, marks[1:])):
        raise ValueError('A chapter is shorter than ten seconds')
    chapters = '\n'.join(f'{time // 60:02}:{time % 60:02} {text}' for time, text in marks) + '\n'
    title = 'Count Even Numbers from 0 to 200 | Count by Twos | Num-Num Numbers'
    description = ("Count even numbers from zero to two hundred with Little Bird in a wooden toy workshop.\n"
                   "Listen to each number in English and count by twos: 0, 2, 4, 6, 8, and onward. "
                   "See how blocks form pairs with none left over, learn that zero is even, "
                   "and look for the last digits 0, 2, 4, 6, and 8.\n\n"
                   f'{chapters}\nNum-Num Numbers — Paspla Studio\n'
                   'https://pasplastudio.com/num-num-numbers/\n')
    texts = {'english-captions.srt': format_srt(rows), 'chapters.txt': chapters,
             'upload-details.txt': f'Title\n{title}\n\nDescription\n{description}\n'
                                   f'Files\nVideo: {VIDEO_NAME}\nCaptions: english-captions.srt (English)\n'}
    for filename, text in texts.items():
        with (output / filename).open('x', encoding='utf-8', newline='\n') as target:
            target.write(text)
    return {'captions': len(rows), 'chapters': len(marks), 'files': list(texts)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--speech', type=Path, default=OUTPUT / 'speech/measurements.json')
    parser.add_argument('--acceptance', type=Path, default=OUTPUT / 'speech/speech-acceptance.json')
    parser.add_argument('--out', type=Path, default=OUTPUT)
    parser.add_argument('--work-dir', type=Path, default=Path('D:/temp/even-production-build'))
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg'))
    args = parser.parse_args()
    if not args.ffmpeg:
        raise ValueError('Registered FFmpeg is required')
    output = args.out.resolve()
    if any((output / name).exists() for name in ('timeline.json', 'master.wav', 'audio-qa.json')):
        raise FileExistsError('An audio build already exists; choose a new output location')
    cues = script_cues()
    numbers, number_gates = accepted_numbers({})
    numbers = {value: numbers[value] for value in range(0, 201, 2)}
    dialogue = reviewed_dialogue(args.speech.resolve(), args.acceptance.resolve(), cues)
    plan = make_plan(numbers, dialogue, cues)
    plan['number_library_gates'] = number_gates
    plan['speech_measurements'] = {'path': local_path(args.speech), 'sha256': digest(args.speech)}
    plan['speech_acceptance'] = {'path': local_path(args.acceptance), 'sha256': digest(args.acceptance)}
    output.mkdir(parents=True, exist_ok=True)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='mix-', dir=args.work_dir) as temporary:
        work = Path(temporary)
        master = work / 'master.wav'
        receipt = mix_balanced(plan, master, work, args.ffmpeg, {})
        receipt['delivery_probe'] = delivery_probe(master, work, args.ffmpeg, output)
        plan['delivery_gain_db'] = receipt['required_delivery_gain_db']
        plan['audio_mix'] = receipt
        save(output / 'timeline.json', plan)
        receipt.update(kind='even-number-master-audio-qa', timeline_sha256=digest(output / 'timeline.json'),
                       timeline_validation=validate(plan))
        save(output / 'audio-qa.json', receipt)
        shutil.copyfile(master, output / 'master.wav')
    delivery = export_delivery(plan, output)
    print(json.dumps({'output': str(output), 'validation': validate(plan),
                      'master': {key: receipt[key] for key in
                                 ('master_sha256', 'loudness_lufs', 'true_peak_dbtp',
                                  'required_delivery_gain_db')},
                      'delivery_probe': receipt['delivery_probe'],
                      'delivery': delivery}, ensure_ascii=False))


if __name__ == '__main__':
    main()
