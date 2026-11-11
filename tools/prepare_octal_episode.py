"""Prepare octal count copy and timing estimates from accepted digit recordings."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import wave


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'design/octal-counting-v1'
LIBRARY = ROOT / 'assets/library/audio/speech/kokoro-af-heart'
SFX_LIBRARY = 'assets/library/audio/sfx/binary/v001'
WORDS = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven')
PLACE_WEIGHTS = (64, 8, 1)
SAMPLE_RATE = 24_000
INTRO_SECONDS = 32
FINALE_SECONDS = 15
WITHIN_NUMBER_GAP = .9
PRE_SPEECH_HOLD = .12
BETWEEN_NUMBERS_GAP = 2.0
FINAL_NUMBER_HOLD = .28
INTRO_DIALOGUE = (
    ('I01', "Hi! Let's count in base eight. We call it octal.", .8, 4.8),
    ('I02', 'Octal uses eight digits, from zero through seven.', 5, 8.8),
    ('I03', "We'll read each digit from left to right.", 9, 12.2),
    ('I04', 'This says one, two. Its value is ten.', 12.3, 16.3),
    ('I05', 'My sign shows the decimal value.', 16.4, 19.2),
    ('I06', 'Each place to the left is worth eight times as much.', 19.4, 23.7),
    ('I07', 'We skip the blank places.', 23.9, 26.3),
    ('I08', "Now let's start our count at zero.", 26.5, 31.2),
)
PAUSES = {
    7: ('new-place-comparison', 3, (
        ('P07', 'One more makes a new place.', .35, 2.65),
    )),
    31: ('stretch', 8, (
        ('S31A', "Let's stretch.", .2, 1.5),
        ('S31B', "Ready? Let's keep going!", 5.7, 7.5),
    )),
    63: ('new-place-comparison', 3, (
        ('P63', 'The next number has three digits.', .35, 2.65),
    )),
}
FINALE_DIALOGUE = (
    ('F03', 'We did it!', 1.25, 2.55),
    ('F05', 'We reached one seven seven in octal!', 3.2, 5.9),
    ('F07', 'Thanks for counting with me!', 7, 9.6),
    ('F09', 'Bye for now!', 11, 12.7),
)


def frames(seconds: float) -> int:
    return round(seconds * SAMPLE_RATE)


def seconds(frame_count: int) -> float:
    return round(frame_count / SAMPLE_RATE, 9)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_digit_clips() -> dict[str, dict]:
    clips = {}
    expected_voice = None
    for source, digits in (('binary-v001', (0,)), ('v002', range(1, 8))):
        manifest_path = LIBRARY / source / 'measurements.json'
        acceptance_path = manifest_path.with_name('speech-acceptance.json')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        acceptance = json.loads(acceptance_path.read_text(encoding='utf-8'))
        manifest_hash = sha256(manifest_path)
        acceptance_hash = sha256(acceptance_path)
        if (
            manifest['measurement_status'] != 'measured'
            or acceptance['kind'] != 'hash-bound-speech-acceptance'
            or acceptance['accepted'] is not True
            or acceptance['inputs']['manifest']['sha256'] != manifest_hash
        ):
            raise ValueError(f'No matching acceptance record for {manifest_path}')
        voice = manifest['voice']
        if voice['voice_id'] != 'af_heart' or voice['sample_rate'] != SAMPLE_RATE:
            raise ValueError(f'Unexpected voice or sample rate in {manifest_path}')
        if expected_voice is not None and voice != expected_voice:
            raise ValueError('Approved digit libraries use different voice settings')
        expected_voice = voice
        for digit in digits:
            word = WORDS[digit]
            measured, = (row for row in manifest['numbers'] if row['number'] == digit)
            approved, = (
                row for row in acceptance['results']
                if row['role'] == 'number' and row['number'] == digit
            )
            clip_path = manifest_path.parent / measured['path']
            clip_hash = sha256(clip_path)
            if (
                approved['accepted'] is not True
                or measured['measurement_status'] != 'measured'
                or approved['expected_text'] != word
                or any(row['spoken_text'] != word for row in (measured, approved))
                or any(row['sha256'] != clip_hash for row in (measured, approved))
                or measured['path'] != approved['path']
            ):
                raise ValueError(f'Clip for {word} does not match the accepted record')
            with wave.open(str(clip_path), 'rb') as clip:
                frame_count = clip.getnframes()
                if (
                    clip.getframerate() != SAMPLE_RATE
                    or clip.getnchannels() != 1
                    or clip.getsampwidth() != 2
                    or len(clip.readframes(frame_count)) != frame_count * 2
                ):
                    raise ValueError(f'Invalid 24 kHz mono PCM16 clip for {word}')
            if frame_count <= 0 or any(
                not math.isclose(row['duration_s'], frame_count / SAMPLE_RATE, abs_tol=1e-9)
                for row in (measured, approved)
            ):
                raise ValueError(f'Invalid measured duration for {word}')
            clips[word] = {
                'digit': digit,
                'path': clip_path.relative_to(ROOT).as_posix(),
                'sha256': clip_hash,
                'sample_frames': frame_count,
                'duration_s': frame_count / SAMPLE_RATE,
                'voice_id': voice['voice_id'],
                'generation_speed': voice['generation_speed'],
                'measurement_manifest': manifest_path.relative_to(ROOT).as_posix(),
                'measurement_manifest_sha256': manifest_hash,
                'acceptance_record': acceptance_path.relative_to(ROOT).as_posix(),
                'acceptance_record_sha256': acceptance_hash,
            }
    return clips


def count_rows() -> list[dict]:
    rows = []
    for value in range(128):
        display = format(value, 'o')
        digits = [int(digit) for digit in display]
        first_slot = len(PLACE_WEIGHTS) - len(digits)
        slots = [None] * first_slot + digits
        if sum((digit or 0) * weight for digit, weight in zip(slots, PLACE_WEIGHTS)) != value:
            raise ValueError(f'Place weights do not match decimal value {value}')
        spoken = [WORDS[digit] for digit in digits]
        rows.append({
            'decimal_value': value,
            'display_octal': display,
            'display_slots': slots,
            'place_weights_left_to_right': list(PLACE_WEIGHTS),
            'active_slot_indices': list(range(first_slot, len(PLACE_WEIGHTS))),
            'spoken_tokens': spoken,
            'spoken_text': ', '.join(spoken) + '.',
            'speech_role': 'octal-digit-sequence',
            'decimal_value_is_narrated': False,
        })
    return rows


def dialogue_windows(lines: tuple, duration: float) -> list[dict]:
    windows = []
    previous_end = 0
    for cue, text, start, end in lines:
        if not previous_end <= start < end <= duration:
            raise ValueError(f'Invalid or overlapping dialogue window for {cue}')
        windows.append({'id': cue, 'text': text, 'relative_window_s': [start, end]})
        previous_end = end
    return windows


def build_timeline(rows: list[dict], clips: dict[str, dict]) -> dict:
    cursor = frames(INTRO_SECONDS)
    gap = frames(WITHIN_NUMBER_GAP)
    pre = frames(PRE_SPEECH_HOLD)
    post = frames(BETWEEN_NUMBERS_GAP) - pre
    states, pauses, carry_cues, sfx = [], [], [], []
    previous_speech_end = None
    spoken_frames = 0
    word_count = 0
    within_gap_count = 0

    for row in rows:
        value = row['decimal_value']
        start = cursor
        cursor += pre
        if previous_speech_end is not None:
            previous_value = value - 1
            added_hold = PAUSES[previous_value][1] if previous_value in PAUSES else 0
            if cursor - previous_speech_end != frames(BETWEEN_NUMBERS_GAP + added_hold):
                raise ValueError(f'Count-to-count gap differs from the plan before {value}')
            if previous_value % 8 == 7:
                cue_start = max(previous_speech_end + frames(.015), start - frames(.45))
                carry_cues.append({
                    'after_decimal_value': previous_value,
                    'before_decimal_value': value,
                    'from_octal': rows[previous_value]['display_octal'],
                    'to_octal': row['display_octal'],
                    'estimated_start_s': seconds(cue_start),
                    'estimated_end_s': seconds(start + frames(.10)),
                    'spoken': False,
                })
        if value in (8, 64):
            sfx.append({
                'id': 'SE_PLACE',
                'path': f'{SFX_LIBRARY}/SE_PLACE.wav',
                'before_decimal_value': value,
                'estimated_start_s': seconds(start + frames(.01)),
                'estimated_end_s': seconds(start + frames(.09)),
                'status': 'optional-existing-cue',
            })

        highlights = []
        for ordinal, word in enumerate(row['spoken_tokens']):
            if ordinal:
                cursor += gap
                within_gap_count += 1
            clip_frames = clips[word]['sample_frames']
            end = cursor + clip_frames
            highlights.append({
                'token': word,
                'ordinal': ordinal,
                'slot_index': row['active_slot_indices'][ordinal],
                'estimated_start_s': seconds(cursor),
                'estimated_end_s': seconds(end),
            })
            cursor = end
            spoken_frames += clip_frames
            word_count += 1
        previous_speech_end = cursor
        cursor += frames(FINAL_NUMBER_HOLD) if value == rows[-1]['decimal_value'] else post
        if value in PAUSES:
            kind, duration, dialogue = PAUSES[value]
            pause = {
                'after_decimal_value': value,
                'held_octal': row['display_octal'],
                'estimated_start_s': seconds(cursor),
                'duration_s': duration,
                'kind': kind,
                'dialogue': dialogue_windows(dialogue, duration),
            }
            if kind == 'new-place-comparison':
                pause['next_octal'] = rows[value + 1]['display_octal']
            pauses.append(pause)
            cursor += frames(duration)
        states.append({
            'decimal_value': value,
            'display_octal': row['display_octal'],
            'estimated_display_start_s': seconds(start),
            'estimated_speech_end_s': seconds(previous_speech_end),
            'estimated_display_end_s': seconds(cursor),
            'digit_highlights': highlights,
        })

    finale_start = cursor
    cursor += frames(FINALE_SECONDS)
    sfx.append({
        'id': 'SE_FINISH',
        'path': f'{SFX_LIBRARY}/SE_FINISH.wav',
        'estimated_start_s': seconds(finale_start + frames(.08)),
        'estimated_end_s': seconds(finale_start + frames(1.08)),
        'status': 'optional-existing-cue',
    })
    if (len(states), word_count, within_gap_count, len(carry_cues)) != (128, 312, 184, 15):
        raise ValueError('Unexpected number of counted states, words, gaps, or carries')

    return {
        'schema_version': 1,
        'kind': 'estimated-octal-counting-timeline',
        'status': 'preproduction',
        'measurement_status': 'existing-digit-clips-measured; new-dialogue-windows-provisional',
        'production_ready': False,
        'audio_generated': False,
        'video_generated': False,
        'duration_s_estimate': seconds(cursor),
        'sample_rate_hz': SAMPLE_RATE,
        'intro': {
            'duration_s': INTRO_SECONDS,
            'opening_sfx': False,
            'dialogue': dialogue_windows(INTRO_DIALOGUE, INTRO_SECONDS),
        },
        'counted_states': states,
        'pauses': pauses,
        'carry_cues': carry_cues,
        'sfx_events': sfx,
        'finale': {
            'estimated_start_s': seconds(finale_start),
            'duration_s': FINALE_SECONDS,
            'dialogue': dialogue_windows(FINALE_DIALOGUE, FINALE_SECONDS),
            'relative_cream_fade_s': [13, 15],
        },
        'timing': {
            'digit_word_count': word_count,
            'digit_clip_duration_s_total': seconds(spoken_frames),
            'within_number_gap_count': within_gap_count,
            'within_number_gap_s': WITHIN_NUMBER_GAP,
            'ordinary_gap_between_count_readings_s': BETWEEN_NUMBERS_GAP,
            'between_count_gap_count': len(states) - 1,
            'pre_speech_settle_s': PRE_SPEECH_HOLD,
            'ordinary_post_speech_hold_s': seconds(post),
            'final_post_speech_hold_s': FINAL_NUMBER_HOLD,
            'added_holds_s_total': sum(pause['duration_s'] for pause in pauses),
            'gap_boundary': 'End of the last digit clip to the start of the next digit clip',
        },
        'accepted_digit_clips': clips,
    }


def prepare(output: Path) -> dict:
    count_json = output / 'count-lines.json'
    count_tsv = output / 'count-lines.tsv'
    timing_json = output / 'estimated-timeline.json'
    if any(path.exists() for path in (count_json, count_tsv, timing_json)):
        raise ValueError('Preproduction data already exists. Choose a fresh output directory.')
    rows = count_rows()
    clips = accepted_digit_clips()
    estimate = build_timeline(rows, clips)
    counts = Counter(word for row in rows for word in row['spoken_tokens'])
    count_data = {
        'schema_version': 1,
        'kind': 'octal-count-script',
        'status': 'text-validated-audio-not-generated',
        'language': 'en-US',
        'count_start_decimal': rows[0]['decimal_value'],
        'count_end_decimal': rows[-1]['decimal_value'],
        'counted_states': len(rows),
        'digit_word_counts': {word: counts[word] for word in WORDS},
        'rows': rows,
    }
    output.mkdir(parents=True, exist_ok=True)
    for path, data in ((count_json, count_data), (timing_json, estimate)):
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    with count_tsv.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write('decimal_reference\tdisplay_octal\tspoken_english\tleft_to_right_slots_64_8_1\n')
        for row in rows:
            slots = ' '.join('_' if slot is None else str(slot) for slot in row['display_slots'])
            stream.write(f"{row['decimal_value']}\t{row['display_octal']}\t{row['spoken_text']}\t{slots}\n")
    return {
        'counted_states': len(rows),
        'digit_word_counts': count_data['digit_word_counts'],
        'within_number_gaps': estimate['timing']['within_number_gap_count'],
        'duration_s_estimate': estimate['duration_s_estimate'],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(prepare(args.out), indent=2))


if __name__ == '__main__':
    main()
