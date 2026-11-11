"""Build the odd-counting lesson exclusively to 299 from source-bound speech, retaining the two-second viewing pace."""

from __future__ import annotations

import argparse
from collections import Counter
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile

from build_four_base_episode import delivery_probe, mix_balanced
from build_octal_episode import checked_wav, event, local_path
from export_octal_delivery import format_srt
from video_pipeline import english_number


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/odd-counting-v1'
OUTPUT = ROOT / 'output/odd-counting-001-v002'
RATE, FPS = 24000, 30
VALUES = tuple(range(1, 300, 2))
VIDEO_NAME = 'paspla-studio-odd-numbers-1-to-299-1080p.mp4'
CUE_IDS = {'I01', 'I02', 'I03', 'I04', 'I05', 'I06', 'I07', 'T009', 'T101', 'F01', 'F02', 'F03', 'F04'}


def digest(path: Path) -> str:
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def read(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def save(path: Path, value) -> None:
    with path.open('x', encoding='utf-8', newline='\n') as target:
        json.dump(value, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.write('\n')


def path_for(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def samples(seconds: float) -> int:
    return round(seconds * RATE)


def script_cues() -> list[dict]:
    result = []
    for line in (DESIGN / 'script-and-sound-cues-v002.txt').read_text(encoding='utf-8').splitlines():
        cells = line.split(' | ')
        if not re.fullmatch(r'I\d{2}|T\d{3}|F\d{2}', cells[0]):
            continue
        offset = int(cells[0].startswith('T'))
        begin, end = map(float, cells[1 + offset].split('–'))
        result.append({'id': cells[0], 'relative_window_s': [begin, end],
                       'text': cells[2 + offset], 'japanese': cells[3 + offset],
                       'direction': cells[4 + offset],
                       'phase': 'intro' if cells[0].startswith('I') else
                                'teaching' if cells[0].startswith('T') else 'finale'})
    if len(result) != 13 or {row['id'] for row in result} != CUE_IDS:
        raise ValueError('Expected thirteen unique authored odd-episode dialogue cues')
    return result


def accepted_speech(manifest_path: Path, gate_path: Path, cues: list[dict]) -> tuple[dict, dict]:
    measured, gate = read(manifest_path), read(gate_path)
    if (measured.get('measurement_status') != 'measured' or gate.get('accepted') is not True
            or gate.get('unresolved') or gate.get('summary', {}).get('unresolved', 0)):
        raise ValueError('Odd-episode speech is not measured and fully accepted')
    binding = gate.get('inputs', {}).get('manifest')
    if binding is None or binding['sha256'] != digest(manifest_path):
        raise ValueError('Speech acceptance is not bound to the current measurements')
    verified = set()
    def references(node):
        if isinstance(node, dict):
            if 'path' in node and 'sha256' in node:
                path = path_for(node['path'])
                key = (str(path.resolve()), node['sha256'])
                if key not in verified:
                    if digest(path) != node['sha256']:
                        raise ValueError(f'Speech evidence changed: {path}')
                    verified.add(key)
            for value in node.values():
                references(value)
        elif isinstance(node, list):
            for value in node:
                references(value)
    references(gate)
    raw_numbers, raw_dialogue = measured['numbers'], measured['dialogue']
    if (len(raw_numbers) != 150 or {row['number'] for row in raw_numbers} != set(VALUES)
            or len(raw_dialogue) != 13 or {row['id'] for row in raw_dialogue} != CUE_IDS):
        raise ValueError('Speech measurements do not cover exactly 150 odd numbers and thirteen dialogue cues')
    expected_dialogue = {row['id']: row['text'] for row in cues}
    numbers, dialogue = {}, {}
    for role, rows in (('number', raw_numbers), ('dialogue', raw_dialogue)):
        for row in rows:
            identifier = row['number'] if role == 'number' else row['id']
            text = row.get('spoken_text', row.get('text'))
            expected = english_number(identifier) if role == 'number' else expected_dialogue[identifier]
            if text != expected:
                raise ValueError(f'Wrong authored speech text: {identifier}')
            source = path_for(row['path'])
            matching = [approval for approval in gate.get('results', [])
                        if approval.get('role') == role
                        and (approval.get('number') == identifier if role == 'number' else approval.get('id') == identifier)]
            if len(matching) != 1:
                raise ValueError(f'Missing or duplicate individual speech approval: {identifier}')
            approval = matching[0]
            if (approval.get('accepted') is not True or approval.get('failures')
                    or approval.get('expected_text') != expected or approval.get('sha256') != row['sha256']
                    or path_for(approval['path']).resolve() != source.resolve()
                    or abs(approval['duration_s'] - row['duration_s']) > 1e-9):
                raise ValueError(f'Individual acceptance does not match source: {identifier}')
            count = checked_wav(source, row['sha256'], row['duration_s'], RATE, 1)
            if row.get('sample_frames', count) != count:
                raise ValueError('The measured source frame count is inconsistent')
            entry = {**copy.deepcopy(row), 'path': local_path(source), 'text': text, 'spoken_text': text,
                     'sample_frames': count, 'duration_s': count / RATE,
                     'measurement_manifest': local_path(manifest_path), 'measurement_manifest_sha256': digest(manifest_path),
                     'acceptance_record': local_path(gate_path), 'acceptance_record_sha256': digest(gate_path)}
            (numbers if role == 'number' else dialogue)[identifier] = entry
    return {value: numbers[value] for value in VALUES}, dialogue


def make_plan(numbers: dict, dialogue: dict, cues: list[dict]) -> dict:
    scenes, events, counted, teaching = [{'scene': 'intro', 'start_s': 0, 'end_s': 36}], [], [], []
    cursor = samples(36)
    for value in VALUES:
        source = numbers[value]
        begin = cursor
        item = event(source, f'N{value:03d}', 'number_voice', 'count', begin + samples(.12),
                     source['spoken_text'], decimal_value=value, narration_base=10)
        item['role'] = item['type']
        end = item['end_sample_24k']
        cursor = end + samples(.28 if value == 299 else 1.88) + (samples(8) if value in (9, 101) else 0)
        scene = {'scene': 'count', 'decimal_value': value, 'start_s': begin / RATE, 'end_s': cursor / RATE,
                 'voice_start_s': item['start_s'], 'voice_end_s': item['end_s'], 'spoken_text': item['text']}
        if value in (9, 101):
            pause = {'id': f'T{value:03d}', 'decimal_value': value,
                     'start_s': (end + samples(.4)) / RATE, 'end_s': (end + samples(8.4)) / RATE}
            scene['teaching'] = pause
            teaching.append(pause)
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
        start, limit = (samples(origin) + samples(value) for value in cue['relative_window_s'])
        item = event(dialogue[cue['id']], cue['id'], 'dialogue', cue['phase'], start, cue['text'])
        item['role'] = item['type']
        if item['end_sample_24k'] > limit:
            raise ValueError(f'Actual dialogue exceeds its editing window: {cue["id"]}')
        cue.update(start_s=item['start_s'], end_s=item['end_s'])
        events.append(item)
    events.sort(key=lambda row: row['start_sample_24k'])
    plan = {'schema_version': 1, 'episode_id': 'odd-counting-001', 'revision_id': 'odd-counting-v002',
            'kind': 'measured-odd-counting-timeline', 'status': 'measured-and-reviewed-speech',
            'count_start': 1, 'count_end': 299, 'count_step': 2, 'fps': FPS,
            'duration_s': duration, 'duration_frames': math.ceil(duration * FPS - 1e-7),
            'master_sample_rate_hz': 48000, 'master_channels': 2, 'source_sample_rate_hz': RATE,
            'bgm': False, 'sound_effects': [], 'numeric_sources': numbers,
            'dialogue_cues': cues, 'voice_events': events, 'events': events,
            'scenes': scenes, 'counted_states': counted, 'teaching': teaching,
            'intro': {'start_s': 0, 'end_s': 36}, 'finale': {'start_s': finale_start, 'end_s': duration, 'fade_last_s': 2},
            'format': 'standard-video',
            'pacing_policy': {'ordinary_gap_s': 2, 'teaching_gap_s': 10, 'minimum_duration_s': 480},
            'timing': {'display_lead_s': .12, 'ordinary_number_gap_s': 2, 'ordinary_boundaries': 147,
                       'teaching_number_gap_s': 10, 'teaching_boundaries': 2, 'final_number_hold_s': .28},
            'source_script': {'path': local_path(DESIGN / 'script-and-sound-cues-v002.txt'),
                              'sha256': digest(DESIGN / 'script-and-sound-cues-v002.txt')},
            'renderer_implementation': 'tools/render_odd_video_v002.py', 'verifier_implementation': 'tools/verify_odd_video.py',
            'audio_generated': True, 'video_generated': False}
    validate(plan)
    return plan


def validate(plan: dict) -> dict:
    if (plan.get('count_start'), plan.get('count_end'), plan.get('count_step')) != (1, 299, 2):
        raise ValueError('The extended odd lesson must cover one through 299 by twos')
    if plan.get('pacing_policy') != {'ordinary_gap_s': 2, 'teaching_gap_s': 10, 'minimum_duration_s': 480}:
        raise ValueError('Preserve the existing pace and the eight-minute minimum')
    events = plan['voice_events']
    counted = [row for row in events if row['phase'] == 'count']
    if [row['decimal_value'] for row in counted] != list(VALUES):
        raise ValueError('Count events must cover exactly the 150 odd values one through 299')
    if (len(events) != 163 or len({row['id'] for row in events}) != 163
            or Counter(row['type'] for row in events) != {'number_voice': 150, 'dialogue': 13}):
        raise ValueError('Missing, duplicate or unexpected voice events')
    if any(left['end_sample_24k'] > right['start_sample_24k'] for left, right in zip(events, events[1:])):
        raise ValueError('Speech overlaps another event')
    if any(left['end_s'] != right['start_s'] for left, right in zip(plan['scenes'], plan['scenes'][1:])):
        raise ValueError('Visual states are not contiguous')
    gaps = Counter()
    for state, item in zip(plan['counted_states'], counted, strict=True):
        if samples(item['start_s'] - state['start_s']) != samples(.12):
            raise ValueError('Wrong number display lead')
    for left, right in zip(counted, counted[1:]):
        gap = right['start_sample_24k'] - left['end_sample_24k']
        if gap != samples(10 if left['decimal_value'] in (9, 101) else 2):
            raise ValueError('Wrong completed-number voice spacing')
        gaps[gap] += 1
    if gaps != {samples(2): 147, samples(10): 2}:
        raise ValueError('Wrong odd count boundary coverage')
    if samples(plan['finale']['start_s']) - counted[-1]['end_sample_24k'] != samples(.28):
        raise ValueError('Wrong last-number hold')
    expected = sum(row['sample_frames'] for row in plan['numeric_sources'].values()) / RATE + 364.4
    if abs(plan['duration_s'] - expected) > 1 / RATE:
        raise ValueError('Measured duration differs from numeric PCM plus fixed editing waits')
    if plan['duration_s'] < 480 or plan['duration_frames'] / FPS < 480:
        raise ValueError('Standard videos must last at least eight minutes')
    return {'counted_values': 150, 'voice_events': 163, 'ordinary_boundaries_2s': 147,
            'teaching_boundaries_10s': 2, 'duration_s': plan['duration_s'],
            'duration_frames': plan['duration_frames'], 'all_dialogue_fits_windows': True}


def export_delivery(plan: dict, output: Path) -> dict:
    rows = [(row['start_s'], row['end_s'], row['text'][0].upper() + row['text'][1:]
             + ('.' if row['type'] == 'number_voice' else '')) for row in plan['voice_events']]
    marks = [(0, 'What Are Odd Numbers?'), (36, 'Count by Twos from One')]
    marks += [(math.floor(row['start_s']), 'Nine Tickets, Four Pairs and One Left Over' if row['id'] == 'T009'
               else 'From Ninety-Nine to One Hundred One') for row in plan['teaching']]
    marks.append((math.floor(plan['finale']['start_s']), 'We Reached Two Hundred Ninety-Nine'))
    if len(rows) != 163 or any(right[0] - left[0] < 10 for left, right in zip(marks, marks[1:])):
        raise ValueError('Incorrect captions or chapter spacing')
    chapters = '\n'.join(f'{value // 60:02}:{value % 60:02} {text}' for value, text in marks) + '\n'
    title = 'Count Odd Numbers from 1 to 299 | Count by Twos | Num-Num Numbers'
    description = ('Count odd numbers from one to two hundred ninety-nine with Red Panda at a mountain cable-car station.\n'
                   'Listen to each number in English and count by twos: 1, 3, 5, 7, 9, and onward. '
                   'Use tickets to make pairs and see one left over. Watch how adding two takes us from 99 to 101.\n\n'
                   f'{chapters}\nNum-Num Numbers — Paspla Studio\nhttps://pasplastudio.com/num-num-numbers/\n')
    data = {'english-captions.srt': format_srt(rows), 'chapters.txt': chapters,
            'upload-details.txt': f'Title\n{title}\n\nDescription\n{description}\nFiles\nVideo: {VIDEO_NAME}\nCaptions: english-captions.srt (English)\n'}
    for name, text in data.items():
        with (output / name).open('x', encoding='utf-8', newline='\n') as target:
            target.write(text)
    return {'captions': len(rows), 'chapters': len(marks), 'files': list(data)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--speech', type=Path, default=OUTPUT / 'speech/measurements.json')
    parser.add_argument('--acceptance', type=Path, default=OUTPUT / 'speech/speech-acceptance.json')
    parser.add_argument('--out', type=Path, default=OUTPUT)
    parser.add_argument('--work-dir', type=Path, default=Path('D:/temp/odd-production-build'))
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg'))
    args = parser.parse_args()
    output = args.out.resolve()
    if not args.ffmpeg or any((output / name).exists() for name in ('timeline.json', 'master.wav', 'audio-qa.json')):
        raise ValueError('FFmpeg is required and existing measured/audio build artifacts cannot be overwritten')
    cues = script_cues()
    numbers, dialogue = accepted_speech(args.speech.resolve(), args.acceptance.resolve(), cues)
    plan = make_plan(numbers, dialogue, cues)
    plan['speech_measurements'] = {'path': local_path(args.speech), 'sha256': digest(args.speech)}
    plan['speech_acceptance'] = {'path': local_path(args.acceptance), 'sha256': digest(args.acceptance)}
    output.mkdir(parents=True, exist_ok=True)
    rows = [{'id': f'N{value:03d}', 'decimal_value': value, 'spoken_text': source['spoken_text'], 'source': source}
            for value, source in numbers.items()]
    save(output / 'count-lines.json', rows)
    with (output / 'count-lines.tsv').open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow(['id', 'decimal_value', 'spoken_text', 'duration_s', 'source_path'])
        for row in rows:
            writer.writerow([row['id'], row['decimal_value'], row['spoken_text'], row['source']['duration_s'], row['source']['path']])
    plan['count_lines'] = {'path': local_path(output / 'count-lines.json'), 'sha256': digest(output / 'count-lines.json')}
    args.work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='mix-', dir=args.work_dir) as temporary:
        work = Path(temporary)
        master = work / 'master.wav'
        receipt = mix_balanced(plan, master, work, args.ffmpeg, {})
        receipt['delivery_probe'] = delivery_probe(master, work, args.ffmpeg, output)
        plan['delivery_gain_db'] = receipt['required_delivery_gain_db']
        plan['audio_mix'] = receipt
        save(output / 'timeline.json', plan)
        receipt.update(kind='odd-counting-master-audio-qa', timeline_sha256=digest(output / 'timeline.json'),
                       timeline_validation=validate(plan))
        save(output / 'audio-qa.json', receipt)
        shutil.copyfile(master, output / 'master.wav')
    delivery = export_delivery(plan, output)
    print(json.dumps({'output': str(output), 'validation': validate(plan), 'delivery': delivery,
                      'aac_probe': receipt['delivery_probe']}))


if __name__ == '__main__':
    main()
