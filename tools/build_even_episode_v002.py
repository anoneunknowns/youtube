"""Rebuild the even lesson with reviewed replacement number takes, retaining v001."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import shutil
import tempfile

import build_even_episode as base


OUTPUT = base.ROOT / 'output/even-counting-001-v002'
BASE_VALIDATOR = base.validate


def replacement_numbers(manifest_path: Path, acceptance_path: Path, numbers: dict) -> dict:
    measured, gate = base.read(manifest_path), base.read(acceptance_path)
    if (gate.get('accepted') is not True or gate.get('unresolved')
            or gate.get('summary', {}).get('unresolved', 0)):
        raise ValueError('Replacement pronunciation review has unresolved findings')
    binding = gate['inputs'].get('manifest', gate['inputs'].get('measurements'))
    if not binding or binding['sha256'] != base.digest(manifest_path):
        raise ValueError('Replacement acceptance is bound to a different manifest')
    checked = set()
    def references(value):
        if isinstance(value, dict):
            if 'path' in value and 'sha256' in value:
                path = base.source_path(value['path'])
                key = (str(path), value['sha256'])
                if key not in checked:
                    if base.digest(path) != value['sha256']:
                        raise ValueError(f'Changed replacement evidence: {path}')
                    checked.add(key)
            for item in value.values():
                references(item)
        elif isinstance(value, list):
            for item in value:
                references(item)
    references(gate)
    rows = measured.get('numbers', [])
    if not rows:
        raise ValueError('Replacement manifest has no number clips')
    replacements = {}
    for row in rows:
        number = row.get('number', row.get('decimal_value'))
        if number is None and row.get('id', '').startswith('N'):
            number = int(row['id'][1:])
        if number not in numbers or number in replacements:
            raise ValueError('Duplicate or out-of-range replacement')
        text = row.get('spoken_text', row.get('text'))
        if text != numbers[number]['spoken_text']:
            raise ValueError(f'Replacement changed the natural number reading at {number}')
        path = base.source_path(row['path'])
        approvals = [item for item in gate.get('results', [])
                     if item.get('role') == 'number' and item.get('number') == number]
        if len(approvals) != 1:
            raise ValueError(f'Replacement {number} must have one matching individual gate result')
        approval = approvals[0]
        if (approval.get('accepted') is not True or approval.get('failures')
                or approval.get('expected_text') != text or approval.get('sha256') != row['sha256']
                or base.source_path(approval['path']).resolve() != path.resolve()
                or abs(approval['duration_s'] - row['duration_s']) > 1e-9):
            raise ValueError(f'Replacement {number} differs from its individual source acceptance')
        count = base.checked_wav(path, row['sha256'], row['duration_s'], base.RATE, 1)
        replacements[number] = {
            'path': base.local_path(path), 'sha256': row['sha256'], 'sample_frames': count,
            'duration_s': count / base.RATE, 'spoken_text': text,
            'voice_id': 'af_heart', 'generation_speed': .98,
            'measurement_manifest': base.local_path(manifest_path),
            'measurement_manifest_sha256': base.digest(manifest_path),
            'acceptance_record': base.local_path(acceptance_path),
            'acceptance_record_sha256': base.digest(acceptance_path),
            'supersedes_source': {'path': numbers[number]['path'], 'sha256': numbers[number]['sha256']},
        }
    return replacements


def validate_revised(plan: dict) -> dict:
    # New takes change real count durations; the editorial waits remain fixed.
    expected = sum(row['sample_frames'] for row in plan['numeric_sources'].values()) / base.RATE + 266.4
    if abs(plan['duration_s'] - expected) > 1 / base.RATE:
        raise ValueError('Revised duration differs from measured speech plus fixed editing waits')
    plan['original_preproduction_estimate_s'] = plan.get('original_preproduction_estimate_s', plan['estimate_cross_check_s'])
    plan['estimate_cross_check_s'] = expected
    return BASE_VALIDATOR(plan)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--numbers', type=Path, default=OUTPUT / 'speech/measurements.json')
    parser.add_argument('--number-acceptance', type=Path, default=OUTPUT / 'speech/speech-acceptance.json')
    parser.add_argument('--dialogue', type=Path, default=base.OUTPUT / 'speech/measurements.json')
    parser.add_argument('--dialogue-acceptance', type=Path, default=base.OUTPUT / 'speech/speech-acceptance.json')
    parser.add_argument('--out', type=Path, default=OUTPUT)
    parser.add_argument('--work-dir', type=Path, default=Path('D:/temp/even-production-build-v002'))
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg'))
    args = parser.parse_args()
    output = args.out.resolve()
    if not args.ffmpeg or any((output / name).exists() for name in ('master.wav', 'timeline.json', 'audio-qa.json')):
        raise ValueError('FFmpeg is required and the destination must not contain an existing audio build')
    numbers, old_gates = base.accepted_numbers({})
    numbers = {value: numbers[value] for value in range(0, 201, 2)}
    replacements = replacement_numbers(args.numbers.resolve(), args.number_acceptance.resolve(), numbers)
    numbers.update(replacements)
    cues = base.script_cues()
    dialogue = base.reviewed_dialogue(args.dialogue.resolve(), args.dialogue_acceptance.resolve(), cues)
    original = base.validate
    try:
        base.validate = validate_revised
        plan = base.make_plan(numbers, dialogue, cues)
    finally:
        base.validate = original
    plan.update(revision_id='even-counting-v002',
                renderer_implementation='tools/render_even_video_v002.py',
                verifier_implementation='tools/verify_even_video_v002.py',
                replacement_number_values=sorted(replacements),
                number_library_gates=old_gates,
                speech_measurements={'path': base.local_path(args.dialogue), 'sha256': base.digest(args.dialogue)},
                speech_acceptance={'path': base.local_path(args.dialogue_acceptance), 'sha256': base.digest(args.dialogue_acceptance)},
                replacement_measurements={'path': base.local_path(args.numbers), 'sha256': base.digest(args.numbers)},
                replacement_acceptance={'path': base.local_path(args.number_acceptance), 'sha256': base.digest(args.number_acceptance)},
                predecessor={'production_record': 'design/even-counting-v1/production-run-v001.json',
                             'sha256': base.digest(base.DESIGN / 'production-run-v001.json')})
    output.mkdir(parents=True, exist_ok=True)
    rows = [{'id': f'N{value:03d}', 'decimal_value': value, 'spoken_text': source['spoken_text'],
             'source': source} for value, source in sorted(numbers.items())]
    base.save(output / 'count-lines.json', rows)
    with (output / 'count-lines.tsv').open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow(['id', 'decimal_value', 'spoken_text', 'duration_s', 'path'])
        for row in rows:
            writer.writerow([row['id'], row['decimal_value'], row['spoken_text'], row['source']['duration_s'], row['source']['path']])
    plan['count_lines'] = {'path': base.local_path(output / 'count-lines.json'), 'sha256': base.digest(output / 'count-lines.json')}
    args.work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='mix-', dir=args.work_dir) as temporary:
        work = Path(temporary)
        master = work / 'master.wav'
        receipt = base.mix_balanced(plan, master, work, args.ffmpeg, {})
        receipt['delivery_probe'] = base.delivery_probe(master, work, args.ffmpeg, output)
        plan['delivery_gain_db'] = receipt['required_delivery_gain_db']
        plan['audio_mix'] = receipt
        base.save(output / 'timeline.json', plan)
        receipt.update(kind='even-number-v002-master-audio-qa', timeline_sha256=base.digest(output / 'timeline.json'),
                       timeline_validation=validate_revised(plan))
        base.save(output / 'audio-qa.json', receipt)
        shutil.copyfile(master, output / 'master.wav')
    delivery = base.export_delivery(plan, output)
    import json
    print(json.dumps({'output': str(output), 'replaced_values': sorted(replacements),
                      'validation': validate_revised(plan), 'delivery': delivery,
                      'aac_probe': receipt['delivery_probe']}))


if __name__ == '__main__':
    main()
