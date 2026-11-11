"""Prepare four-base count copy and measured-source timing estimates, without new media."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import wave

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'design/four-base-counting-v1'
SCRIPT = OUTPUT / 'script-and-sound-cues.txt'
RATE = 24000
INTRO = 30
FINALE = 12
TEACHING = {8: ('T08', ['octal']), 16: ('T16', ['hexadecimal']), 64: ('T64', ['binary', 'octal'])}


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def local(path):
    return path.relative_to(ROOT).as_posix()


def write(path, value):
    with path.open('x', encoding='utf-8') as target:
        json.dump(value, target, ensure_ascii=False, indent=2)
        target.write('\n')


def clips():
    sources = {}
    library = ROOT / 'assets/library/audio/speech/kokoro-af-heart'
    for version, values in (('binary-v001', [0]), ('v002', range(1, 128))):
        manifest_path = library / version / 'measurements.json'
        acceptance_path = manifest_path.with_name('speech-acceptance.json')
        measured = json.loads(manifest_path.read_text(encoding='utf-8'))
        accepted = json.loads(acceptance_path.read_text(encoding='utf-8'))
        if (accepted['accepted'] is not True or accepted['inputs']['manifest']['sha256'] != digest(manifest_path)
                or measured['measurement_status'] != 'measured' or measured['voice']['sample_rate'] != RATE):
            raise ValueError(f'Unbound speech library {manifest_path}')
        numbers = {row['number']: row for row in measured['numbers']}
        reviewed = {row['number']: row for row in accepted['results'] if row['role'] == 'number'}
        for value in values:
            row, review = numbers[value], reviewed[value]
            path = manifest_path.parent / row['path']
            checksum = digest(path)
            if (review['accepted'] is not True or review['expected_text'] != row['spoken_text']
                    or any(item['sha256'] != checksum for item in (row, review))):
                raise ValueError(f'Unreviewed number {value}')
            with wave.open(str(path), 'rb') as stream:
                count = stream.getnframes()
                if (stream.getframerate(), stream.getnchannels(), stream.getsampwidth()) != (RATE, 1, 2):
                    raise ValueError(f'Unexpected PCM format {value}')
                if len(stream.readframes(count)) != count * 2:
                    raise ValueError(f'Truncated number {value}')
            if count <= 0 or abs(row['duration_s'] - count / RATE) > 1e-9:
                raise ValueError(f'Wrong measured length {value}')
            sources[value] = {
                'path': local(path), 'sha256': checksum, 'sample_frames': count, 'duration_s': count / RATE,
                'spoken_text': row['spoken_text'], 'voice_id': measured['voice']['voice_id'],
                'generation_speed': measured['voice']['generation_speed'],
                'measurement_manifest': local(manifest_path), 'measurement_manifest_sha256': digest(manifest_path),
                'acceptance_record': local(acceptance_path), 'acceptance_record_sha256': digest(acceptance_path),
            }
    return sources


def script_cues():
    cues = []
    for line in SCRIPT.read_text(encoding='utf-8').splitlines():
        fields = line.split(' | ')
        if not re.fullmatch(r'I\d{2}(?:-[A-Z]+|[A-Z])?|T\d{2}|F\d{2}', fields[0]):
            continue
        cue_id = fields[0]
        index = 2 if cue_id.startswith('T') else 1
        begin, end = map(float, fields[index].split('–'))
        cue = {'id': cue_id, 'relative_window_s': [begin, end], 'text': fields[index + 1],
               'direction': fields[index + 2], 'audio_status': 'not-generated-for-this-episode'}
        if cue_id.startswith('T'):
            cue['decimal_value'] = int(fields[1])
        cues.append(cue)
    expected = {'I01', 'I02', 'I03', 'I04-TEN', 'I04B', 'I05', 'I06', 'T08', 'T16', 'T64', 'F01', 'F02', 'F03', 'F04'}
    if {cue['id'] for cue in cues} != expected or len(cues) != len(expected):
        raise ValueError('Script cues are missing or duplicated')
    return cues


def prepare(output):
    names = ['count-lines.json', 'count-lines.tsv', 'estimated-timeline.json']
    if any((output / name).exists() for name in names):
        raise FileExistsError('Use a fresh output location for generated planning data')
    speech, cues = clips(), script_cues()
    rows, states, pauses = [], [], []
    cursor = INTRO * RATE
    for value in range(128):
        representations = {'binary': format(value, 'b'), 'decimal': str(value),
                           'octal': format(value, 'o'), 'hexadecimal': format(value, 'X')}
        if any(int(representations[name], base) != value
               for name, base in (('binary', 2), ('decimal', 10), ('octal', 8), ('hexadecimal', 16))):
            raise ValueError('Base-conversion mismatch')
        source = speech[value]
        rows.append({'decimal_value': value, **representations, 'spoken_text': source['spoken_text'],
                     'narration_base': 10, 'speech_role': 'natural-decimal-number', 'source': source})
        begin = cursor
        voice_start = begin + round(.12 * RATE)
        voice_end = voice_start + source['sample_frames']
        cursor = voice_end + round((.28 if value == 127 else 1.88) * RATE)
        if value in TEACHING:
            cue_id, focus = TEACHING[value]
            pause_start = cursor
            cursor += 3 * RATE
            cue = next(cue for cue in cues if cue['id'] == cue_id)
            pauses.append({'after_decimal_value': value, 'kind': 'new-place-check', 'duration_s': 3,
                           'estimated_start_s': pause_start / RATE, 'estimated_end_s': cursor / RATE,
                           'focus_rows': focus, 'focus_ordinal': 0, 'dialogue': cue})
        states.append({'decimal_value': value, 'representations': representations,
                       'estimated_display_start_s': begin / RATE, 'estimated_voice_start_s': voice_start / RATE,
                       'estimated_voice_end_s': voice_end / RATE, 'estimated_display_end_s': cursor / RATE,
                       'spoken_text': source['spoken_text'], 'source_path': source['path'],
                       'source_sha256': source['sha256'], 'all_rows_update_together': True})
    for left, right in zip(states, states[1:]):
        expected = 5 if left['decimal_value'] in TEACHING else 2
        if round((right['estimated_voice_start_s'] - left['estimated_voice_end_s']) * RATE) != expected * RATE:
            raise ValueError('Completed-value gap mismatch')
    intro = {'duration_s': INTRO, 'dialogue': [cue for cue in cues if cue['id'].startswith('I')]}
    ten = next(cue for cue in intro['dialogue'] if cue['id'] == 'I04-TEN')
    ten.update(audio_status='accepted-existing-number-for-planned-reuse', source=speech[10])
    if abs((ten['relative_window_s'][1] - ten['relative_window_s'][0]) - speech[10]['duration_s']) > 1e-9:
        raise ValueError('Intro ten does not match the measured source')
    finale = {'estimated_start_s': cursor / RATE, 'duration_s': FINALE, 'relative_cream_fade_s': [10, 12],
              'dialogue': [cue for cue in cues if cue['id'].startswith('F')]}
    duration = cursor / RATE + FINALE
    plan = {
        'schema_version': 1, 'episode_id': 'four-base-counting-001',
        'kind': 'preproduction-four-base-timeline', 'status': 'estimated-new-dialogue-not-recorded',
        'audio_generated': False, 'video_generated': False, 'source_script': local(SCRIPT),
        'source_script_sha256': digest(SCRIPT), 'fps': 30, 'duration_s_estimate': duration,
        'row_order': ['binary', 'decimal', 'octal', 'hexadecimal'], 'narration_base': 10,
        'numeric_sources': speech, 'intro': intro, 'counted_states': states, 'pauses': pauses, 'finale': finale,
        'timing': {'counted_values': 128, 'count_voice_duration_s_measured_total': sum(s['sample_frames'] for s in speech.values()) / RATE,
                   'ordinary_two_second_transitions': 124, 'teaching_five_second_transitions': 3,
                   'voice_start_after_display_s': .12, 'normal_post_voice_hold_s': 1.88,
                   'last_post_voice_hold_s': .28, 'within_number_gap_policy': 'Use existing natural whole-number speech; insert no inter-digit or inter-word gaps.',
                   'count_section_s_without_additional_checks': (cursor - INTRO * RATE) / RATE - 9},
        'estimate_limit': 'Count WAV lengths are measured. New dialogue remains unrecorded and must fit the editorial windows before production readiness.',
        'sound_effects': [{'id': 'SE_FINISH', 'required': False,
                           'source_path': 'assets/library/audio/sfx/binary/v001/SE_FINISH.wav',
                           'estimated_start_s': cursor / RATE + .08, 'estimated_end_s': cursor / RATE + 1.08}],
    }
    output.mkdir(parents=True, exist_ok=True)
    write(output / names[0], rows)
    with (output / names[1]).open('x', encoding='utf-8', newline='') as target:
        writer = csv.writer(target, delimiter='\t')
        writer.writerow(['decimal_value', 'binary', 'decimal', 'octal', 'hexadecimal', 'spoken_text', 'source_duration_s'])
        for row in rows:
            writer.writerow([row[key] for key in ('decimal_value', 'binary', 'decimal', 'octal', 'hexadecimal', 'spoken_text')] + [f'{row["source"]["duration_s"]:.9f}'])
    write(output / names[2], plan)
    return {'counted_values': len(rows), 'voice_sources_verified': len(speech), 'duration_s_estimate': duration,
            'maximum_digits': {name: max(len(row[name]) for row in rows) for name in plan['row_order']},
            'ordinary_two_second_transitions': 124, 'teaching_five_second_transitions': 3}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(prepare(args.out.resolve())))


if __name__ == '__main__':
    main()
