"""Prepare hexadecimal count copy and estimates without generating speech or video."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import wave

if __package__:
    from .prepare_octal_episode import (
        LIBRARY, ROOT, SAMPLE_RATE, accepted_digit_clips, dialogue_windows, frames, seconds,
    )
else:
    from prepare_octal_episode import (
        LIBRARY, ROOT, SAMPLE_RATE, accepted_digit_clips, dialogue_windows, frames, seconds,
    )


OUTPUT = ROOT / 'design/hexadecimal-counting-v1'
SCRIPT = OUTPUT / 'script-and-sound-cues.txt'
SYMBOLS = '0123456789ABCDEF'
NUMBER_WORDS = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine')
LETTER_GUIDES = dict(zip('ABCDEF', ('ay', 'bee', 'see', 'dee', 'ee', 'eff'), strict=True))
WORDS = dict(zip(SYMBOLS, (*NUMBER_WORDS, *'ABCDEF'), strict=True))
PRONUNCIATIONS = {**dict(zip(SYMBOLS[:10], NUMBER_WORDS, strict=True)), **LETTER_GUIDES}
LETTER_DURATION_ESTIMATE = .50
PAUSE_DURATIONS = {15: 3, 63: 8}
INTRO_SECONDS = 58
FINALE_SECONDS = 15


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def numeric_clips() -> dict:
    adopted = accepted_digit_clips()
    clips = {symbol: adopted[WORDS[symbol]] for symbol in SYMBOLS[:8]}
    manifest_path = LIBRARY / 'v002/measurements.json'
    acceptance_path = manifest_path.with_name('speech-acceptance.json')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    accepted = json.loads(acceptance_path.read_text(encoding='utf-8'))
    if (
        accepted['accepted'] is not True
        or accepted['kind'] != 'hash-bound-speech-acceptance'
        or accepted['inputs']['manifest']['sha256'] != digest(manifest_path)
        or manifest['measurement_status'] != 'measured'
        or manifest['voice']['sample_rate'] != SAMPLE_RATE
    ):
        raise ValueError('The numeric source manifest has no matching acceptance')
    for value in (8, 9):
        word = NUMBER_WORDS[value]
        measured, = (row for row in manifest['numbers'] if row['number'] == value)
        reviewed, = (
            row for row in accepted['results']
            if row['role'] == 'number' and row['number'] == value
        )
        path = manifest_path.parent / measured['path']
        checksum = digest(path)
        if (
            reviewed['accepted'] is not True or reviewed['expected_text'] != word
            or any(row['spoken_text'] != word or row['sha256'] != checksum for row in (measured, reviewed))
            or measured['measurement_status'] != 'measured'
        ):
            raise ValueError(f'The source for {word} is not approved')
        with wave.open(str(path), 'rb') as clip:
            count = clip.getnframes()
            if (
                clip.getframerate() != SAMPLE_RATE or clip.getnchannels() != 1
                or clip.getsampwidth() != 2 or len(clip.readframes(count)) != count * 2
            ):
                raise ValueError(f'The source format for {word} is invalid')
        if count <= 0 or any(
            not math.isclose(row['duration_s'], count / SAMPLE_RATE, abs_tol=1e-9)
            for row in (measured, reviewed)
        ):
            raise ValueError(f'The source duration for {word} is invalid')
        clips[str(value)] = {
            'digit': value, 'path': path.relative_to(ROOT).as_posix(), 'sha256': checksum,
            'sample_frames': count, 'duration_s': count / SAMPLE_RATE,
            'voice_id': manifest['voice']['voice_id'],
            'generation_speed': manifest['voice']['generation_speed'],
            'measurement_manifest': manifest_path.relative_to(ROOT).as_posix(),
            'measurement_manifest_sha256': digest(manifest_path),
            'acceptance_record': acceptance_path.relative_to(ROOT).as_posix(),
            'acceptance_record_sha256': digest(acceptance_path),
        }
    return clips


def scripted_cues() -> dict:
    cues = {}
    pattern = re.compile(r'^(I[0-9]{2}[A-F]?|P15|S63[AB]|F[0-9]{2}) \|')
    for line in SCRIPT.read_text(encoding='utf-8').splitlines():
        if pattern.match(line):
            fields = line.split(' | ')
            start, end = (float(value) for value in fields[-3].split('–'))
            cue_id = fields[0]
            if cue_id in cues:
                raise ValueError(f'Duplicate script cue {cue_id}')
            cues[cue_id] = (cue_id, fields[-2], start, end)
    expected = {
        'I01', 'I02', 'I03A', 'I03B', 'I03C', 'I03D', 'I03E', 'I03F',
        'I04', 'I05', 'I06', 'I07', 'I08', 'P15', 'S63A', 'S63B',
        'F03', 'F05', 'F07', 'F09',
    }
    if set(cues) != expected:
        raise ValueError('The hexadecimal script has missing or unexpected dialogue IDs')
    return cues


def count_rows() -> list[dict]:
    rows = []
    for value in range(128):
        display = format(value, 'X')
        slots = [None] * (2 - len(display)) + list(display)
        if sum((int(symbol, 16) if symbol else 0) * weight for symbol, weight in zip(slots, (16, 1))) != value:
            raise ValueError(f'Place-value mismatch for {display}')
        rows.append({
            'decimal_value': value, 'display_hexadecimal': display, 'display_slots': slots,
            'place_weights_left_to_right': [16, 1], 'active_slot_indices': list(range(2 - len(display), 2)),
            'spoken_tokens': [WORDS[symbol] for symbol in display],
            'pronunciation_tokens': [PRONUNCIATIONS[symbol] for symbol in display],
            'spoken_text': ', '.join(WORDS[symbol] for symbol in display) + '.',
            'speech_role': 'hexadecimal-symbol-sequence', 'decimal_value_is_narrated': False,
        })
    return rows


def estimate(rows: list[dict], clips: dict, cues: dict) -> dict:
    states, pauses, carries, sfx = [], [], [], []
    cursor = frames(INTRO_SECONDS)
    previous_end = None
    words = gaps = 0
    numeric_frames = estimated_letter_frames = 0
    for row in rows:
        value, start = row['decimal_value'], cursor
        cursor += frames(.12)
        if previous_end is not None:
            if cursor - previous_end != frames(2 + PAUSE_DURATIONS.get(value - 1, 0)):
                raise ValueError(f'Unexpected gap before decimal {value}')
            if value % 16 == 0:
                carries.append({
                    'after_decimal_value': value - 1, 'before_decimal_value': value,
                    'from_hexadecimal': format(value - 1, 'X'), 'to_hexadecimal': row['display_hexadecimal'],
                    'estimated_start_s': seconds(max(previous_end + frames(.015), start - frames(.45))),
                    'estimated_end_s': seconds(start + frames(.10)), 'spoken': False,
                })
        if value == 16:
            sfx.append({
                'id': 'SE_PLACE', 'path': 'assets/library/audio/sfx/binary/v001/SE_PLACE.wav',
                'before_decimal_value': value, 'estimated_start_s': seconds(start + frames(.01)),
                'estimated_end_s': seconds(start + frames(.09)), 'status': 'optional-existing-cue',
            })
        highlights = []
        for ordinal, symbol in enumerate(row['display_hexadecimal']):
            if ordinal:
                cursor += frames(.9)
                gaps += 1
            measured = symbol in clips
            length = clips[symbol]['sample_frames'] if measured else frames(LETTER_DURATION_ESTIMATE)
            end = cursor + length
            highlights.append({
                'symbol': symbol, 'token': WORDS[symbol], 'pronunciation_guide': PRONUNCIATIONS[symbol],
                'ordinal': ordinal, 'slot_index': row['active_slot_indices'][ordinal],
                'duration_measured': measured, 'estimated_start_s': seconds(cursor), 'estimated_end_s': seconds(end),
            })
            cursor = end
            words += 1
            numeric_frames += length if measured else 0
            estimated_letter_frames += 0 if measured else length
        previous_end = cursor
        cursor += frames(.28 if value == 127 else 1.88)
        if value in PAUSE_DURATIONS:
            duration = PAUSE_DURATIONS[value]
            ids = ('P15',) if value == 15 else ('S63A', 'S63B')
            pauses.append({
                'after_decimal_value': value, 'held_hexadecimal': row['display_hexadecimal'],
                'estimated_start_s': seconds(cursor), 'duration_s': duration,
                'kind': 'new-place-comparison' if value == 15 else 'place-value-check',
                'dialogue': dialogue_windows(tuple(cues[key] for key in ids), duration),
            })
            cursor += frames(duration)
        states.append({
            'decimal_value': value, 'display_hexadecimal': row['display_hexadecimal'],
            'estimated_display_start_s': seconds(start), 'estimated_speech_end_s': seconds(previous_end),
            'estimated_display_end_s': seconds(cursor), 'digit_highlights': highlights,
        })
    finale_start = cursor
    cursor += frames(FINALE_SECONDS)
    if (len(states), words, gaps, len(carries)) != (128, 240, 112, 7):
        raise ValueError('Unexpected count, speech, gap or carry total')
    sfx.append({
        'id': 'SE_FINISH', 'path': 'assets/library/audio/sfx/binary/v001/SE_FINISH.wav',
        'estimated_start_s': seconds(finale_start + frames(.08)),
        'estimated_end_s': seconds(finale_start + frames(1.08)), 'status': 'optional-existing-cue',
    })
    return {
        'schema_version': 1, 'kind': 'estimated-hexadecimal-counting-timeline',
        'status': 'preproduction', 'production_ready': False, 'audio_generated': False, 'video_generated': False,
        'measurement_status': 'numeric-clips-measured; A-F-durations-estimated; new-dialogue-unmeasured',
        'duration_s_estimate': seconds(cursor), 'sample_rate_hz': SAMPLE_RATE,
        'source_script': SCRIPT.relative_to(ROOT).as_posix(), 'source_script_sha256': digest(SCRIPT),
        'intro': {
            'duration_s': INTRO_SECONDS, 'opening_sfx': False,
            'dialogue': dialogue_windows(tuple(cue for key, cue in cues.items() if key.startswith('I')), INTRO_SECONDS),
            'example_reading': {
                'cue_id': 'I05', 'display_hexadecimal': '1A', 'decimal_value': 26,
                'spoken_tokens': ['one', 'A'], 'within_number_gap_s': .90, 'measured': False,
                'relative_window_s': [cues['I05'][2], cues['I05'][3]],
            },
        },
        'counted_states': states, 'pauses': pauses, 'carry_cues': carries, 'sfx_events': sfx,
        'finale': {
            'estimated_start_s': seconds(finale_start), 'duration_s': FINALE_SECONDS,
            'dialogue': dialogue_windows(tuple(cue for key, cue in cues.items() if key.startswith('F')), FINALE_SECONDS),
            'relative_cream_fade_s': [13, 15],
        },
        'timing': {
            'symbol_word_count': words, 'numeric_clip_duration_s_total': seconds(numeric_frames),
            'estimated_letter_duration_s_total': seconds(estimated_letter_frames),
            'within_number_gap_count': gaps, 'within_number_gap_s': .90,
            'ordinary_gap_between_count_readings_s': 2.0, 'between_count_gap_count': 127,
            'ordinary_count_gap_count': 125, 'pre_speech_settle_s': .12, 'ordinary_post_speech_hold_s': 1.88,
            'final_post_speech_hold_s': .28, 'added_holds_s_total': sum(PAUSE_DURATIONS.values()),
            'gap_boundary': 'End of the previous symbol clip to the start of the next symbol clip',
        },
        'accepted_numeric_clips': clips,
        'letter_voice_estimates': {
            symbol: {
                'letter_name': symbol, 'pronunciation_guide': guide, 'duration_s_estimate': LETTER_DURATION_ESTIMATE,
                'measured': False, 'audio_generated': False, 'tts_rule': 'Use the English letter name',
            } for symbol, guide in LETTER_GUIDES.items()
        },
        'assumptions': {
            'range_provisional': True, 'new_dialogue_must_fit_scripted_editing_windows': True,
            'letter_duration_replacement_required_after_recording': True,
            'bgm': False, 'opening_sfx': False,
        },
    }


def prepare(output: Path) -> dict:
    names = ('count-lines.json', 'count-lines.tsv', 'estimated-timeline.json')
    if any((output / name).exists() for name in names):
        raise ValueError('Preproduction data already exists. Choose a fresh output directory.')
    rows, clips, cues = count_rows(), numeric_clips(), scripted_cues()
    timeline = estimate(rows, clips, cues)
    counts = Counter(symbol for row in rows for symbol in row['display_hexadecimal'])
    count_data = {
        'schema_version': 1, 'kind': 'hexadecimal-count-script', 'status': 'text-validated-audio-not-generated',
        'language': 'en-US', 'count_start_decimal': 0, 'count_end_decimal': 127, 'counted_states': 128,
        'symbol_word_counts': dict(sorted(counts.items())), 'rows': rows,
    }
    output.mkdir(parents=True, exist_ok=True)
    for name, data in (('count-lines.json', count_data), ('estimated-timeline.json', timeline)):
        with (output / name).open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
    with (output / 'count-lines.tsv').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write('decimal_reference\tdisplay_hexadecimal\tspoken_english\tpronunciation_guide\tleft_to_right_slots_16_1\n')
        for row in rows:
            slots = ' '.join('_' if slot is None else slot for slot in row['display_slots'])
            stream.write(f"{row['decimal_value']}\t{row['display_hexadecimal']}\t{row['spoken_text']}\t"
                         f"{' '.join(row['pronunciation_tokens'])}\t{slots}\n")
    return {
        'counted_states': len(rows), 'spoken_symbols': sum(counts.values()), 'within_number_gaps': 112,
        'symbol_word_counts': count_data['symbol_word_counts'], 'duration_s_estimate': timeline['duration_s_estimate'],
        'A_F_duration_each_s_estimate': LETTER_DURATION_ESTIMATE, 'letter_durations_measured': False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(prepare(args.out), indent=2))


if __name__ == '__main__':
    main()
