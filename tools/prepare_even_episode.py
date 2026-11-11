"""Prepare even-count planning data from existing reviewed speech, without synthesis."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import wave


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'design/even-counting-v1'
RATE = 24000
INTRO_SECONDS = 36
FINALE_SECONDS = 14
TEACHING_SECONDS = {20: 8, 100: 8}


def digest(path: Path) -> str:
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def write_json(path: Path, value) -> None:
    with path.open('x', encoding='utf-8', newline='\n') as target:
        json.dump(value, target, ensure_ascii=False, indent=2)
        target.write('\n')


def speech_sources() -> dict[int, dict]:
    sources = {}
    library = ROOT / 'assets/library/audio/speech/kokoro-af-heart'
    for version, values in (('binary-v001', [0]), ('v002', range(2, 201, 2))):
        manifest_path = library / version / 'measurements.json'
        acceptance_path = manifest_path.with_name('speech-acceptance.json')
        measured = json.loads(manifest_path.read_text(encoding='utf-8'))
        acceptance = json.loads(acceptance_path.read_text(encoding='utf-8'))
        if (acceptance['accepted'] is not True
                or acceptance['inputs']['manifest']['sha256'] != digest(manifest_path)
                or measured['measurement_status'] != 'measured'
                or measured['voice']['sample_rate'] != RATE):
            raise ValueError(f'Unbound measurement or acceptance: {manifest_path}')
        numbers = {row['number']: row for row in measured['numbers']}
        reviewed = {row['number']: row for row in acceptance['results'] if row['role'] == 'number'}
        for value in values:
            row, review = numbers[value], reviewed[value]
            path = manifest_path.parent / row['path']
            checksum = digest(path)
            if (review['accepted'] is not True or review['expected_text'] != row['spoken_text']
                    or any(item['sha256'] != checksum for item in (row, review))):
                raise ValueError(f'Number {value} has no matching source review')
            with wave.open(str(path), 'rb') as stream:
                frames = stream.getnframes()
                if (stream.getframerate(), stream.getnchannels(), stream.getsampwidth()) != (RATE, 1, 2):
                    raise ValueError(f'Unexpected PCM format: {value}')
                if len(stream.readframes(frames)) != frames * 2:
                    raise ValueError(f'Truncated PCM: {value}')
            if frames <= 0 or abs(row['duration_s'] - frames / RATE) > 1e-9:
                raise ValueError(f'Measured length differs: {value}')
            sources[value] = {
                'path': relative(path), 'sha256': checksum, 'sample_frames': frames,
                'duration_s': frames / RATE, 'spoken_text': row['spoken_text'],
                'voice_id': measured['voice']['voice_id'],
                'generation_speed': measured['voice']['generation_speed'],
                'measurement_manifest': relative(manifest_path),
                'measurement_manifest_sha256': digest(manifest_path),
                'acceptance_record': relative(acceptance_path),
                'acceptance_record_sha256': digest(acceptance_path),
            }
    return sources


def main() -> None:
    names = ['count-lines.json', 'count-lines.tsv', 'estimated-timeline.json', 'planning-data-review.json']
    if any((OUT / name).exists() for name in names):
        raise FileExistsError('Planning outputs already exist; do not overwrite review artifacts')
    sources = speech_sources()
    if list(sources) != list(range(0, 201, 2)):
        raise ValueError('Even sequence is incomplete or out of order')
    cursor = INTRO_SECONDS * RATE
    rows, states, pauses = [], [], []
    for index, value in enumerate(range(0, 201, 2)):
        source = sources[value]
        display_start = cursor
        voice_start = display_start + round(.12 * RATE)
        voice_end = voice_start + source['sample_frames']
        if value < 200:
            gap = 2 + TEACHING_SECONDS.get(value, 0)
            next_voice_start = voice_end + gap * RATE
            display_end = next_voice_start - round(.12 * RATE)
        else:
            gap = None
            display_end = voice_end + round(.28 * RATE)
        row = {'id': f'N{value:03d}', 'decimal_value': value, 'display_number': str(value),
               'even_index_zero_based': index, 'spoken_text': source['spoken_text'],
               'narration_base': 10, 'reading_mode': 'natural-en-US-number', 'source': source}
        state = {'id': row['id'], 'decimal_value': value,
                 'estimated_display_start_s': display_start / RATE,
                 'estimated_voice_start_s': voice_start / RATE,
                 'estimated_voice_end_s': voice_end / RATE,
                 'estimated_display_end_s': display_end / RATE,
                 'gap_to_next_number_s': gap, 'source_duration_s': source['duration_s']}
        rows.append(row)
        states.append(state)
        if value in TEACHING_SECONDS:
            # The ordinary two-second gap includes a .4-second quiet lead and
            # 1.6 seconds after the eight-second teaching insert.
            pauses.append({'id': f'T{value:03d}', 'decimal_value_held': value,
                           'estimated_start_s': voice_end / RATE + .4,
                           'estimated_end_s': voice_end / RATE + .4 + TEACHING_SECONDS[value],
                           'additional_seconds': TEACHING_SECONDS[value],
                           'number_speech_end_to_next_number_speech_start_s': 10,
                           'dialogue_status': 'unrecorded-duration-budget-only'})
        cursor = display_end
    count_seconds = cursor / RATE - INTRO_SECONDS
    duration = cursor / RATE + FINALE_SECONDS
    count_speech = sum(row['source']['sample_frames'] for row in rows) / RATE
    if abs(count_seconds - (count_speech + 200 + 16 + .4)) > 1e-9:
        raise ValueError('Count duration arithmetic differs')
    for current, following in zip(states, states[1:]):
        actual_gap = following['estimated_voice_start_s'] - current['estimated_voice_end_s']
        if abs(actual_gap - current['gap_to_next_number_s']) > 1e-9:
            raise ValueError('Number-to-number spacing differs')
    timeline = {
        'schema_version': 1, 'episode_id': 'even-counting-001', 'status': 'preproduction-estimate',
        'production_ready': False, 'video_generated': False, 'new_speech_generated': False,
        'scope': {'start': 0, 'end': 200, 'step': 2, 'count_states': 101, 'count_boundaries': 100},
        'source_number_durations': 'Measured existing PCM, SHA and prior acceptance verified',
        'new_dialogue_durations': 'Unrecorded. Intro, teaching and finale are editing budgets',
        'sample_rate': RATE, 'display_lead_s': .12, 'final_value_hold_s': .28,
        'ordinary_number_gap_s': 2, 'ordinary_boundaries': 98,
        'teaching_boundaries': 2, 'teaching_number_gap_s': 10,
        'intro': {'start_s': 0, 'end_s': INTRO_SECONDS, 'budget_s': INTRO_SECONDS},
        'number_states': states, 'teaching': pauses,
        'finale': {'estimated_start_s': cursor / RATE, 'estimated_end_s': duration,
                   'budget_s': FINALE_SECONDS, 'value_held': 200, 'fade_last_s': 2},
        'totals': {'number_speech_s': count_speech, 'normal_gaps_s': 200,
                   'additional_teaching_s': 16, 'count_pre_post_s': .4,
                   'count_with_teaching_s': count_seconds, 'estimated_video_s': duration},
        'warning': 'Not a final audio timeline. Measure and review new dialogue before production. '
                   'Do not stretch speech or assume all teaching fits the budget without measurement.',
    }
    review = {'status': 'planning-data-checked', 'even_values_checked': len(rows),
              'source_wav_sha256_checks': len(rows), 'source_pcm_format_and_length_checks': len(rows),
              'source_prior_acceptance_checks': len(rows), 'new_asr_or_listening_performed': False,
              'ordinary_boundaries_2s': 98, 'teaching_boundaries_10s': 2,
              'zero_is_included': True, 'last_count_value': 200,
              'numeric_reading_examples': {str(n): sources[n]['spoken_text'] for n in (0, 2, 20, 100, 102, 178, 200)},
              'estimated_video_s': duration, 'final_video_or_audio_qa': False,
              'generator': relative(Path(__file__)), 'generator_sha256': digest(Path(__file__))}
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / names[0], rows)
    with (OUT / names[1]).open('x', encoding='utf-8-sig', newline='') as target:
        writer = csv.writer(target, delimiter='\t')
        writer.writerow(['id', 'decimal_value', 'spoken_text', 'source_duration_s', 'source_path'])
        for row in rows:
            writer.writerow([row['id'], row['decimal_value'], row['spoken_text'],
                             f'{row["source"]["duration_s"]:.9f}', row['source']['path']])
    write_json(OUT / names[2], timeline)
    write_json(OUT / names[3], review)
    print(json.dumps({'output': str(OUT), 'count': len(rows), 'duration_s': duration,
                      'number_speech_s': count_speech}, ensure_ascii=False))


if __name__ == '__main__':
    main()
