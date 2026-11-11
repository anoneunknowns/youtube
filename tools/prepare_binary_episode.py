"""Create binary episode preproduction data. Never synthesize audio or render video."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = [64, 32, 16, 8, 4, 2, 1]
INTRO_LINES = [
    ('Hello, number explorers! Let\'s count in binary.', .8, 4.8),
    ('Binary uses only two digits: zero and one.', 5, 8.8),
    ('We read each digit from left to right.', 9, 12.2),
    ('This says one zero. Its value is two.', 12.4, 16.2),
    ('The small number shows the value.', 16.4, 19.2),
    ('Bright means one. Dark means zero.', 19.4, 22.5),
    ('Blank places are not spoken.', 22.7, 25.3),
    ('Our example is finished. Now let\'s start at zero.', 25.5, 31.2),
]
FINALE_LINES = [('We did it!', 1.25, 2.55), ('Seven places, all ones!', 3.2, 5.9),
                ('Thanks for counting with me!', 7, 9.6), ('Bye for now!', 11, 12.7)]


def spoken_tokens(text: str) -> list[str]:
    """Strict words for this binary lesson, deliberately not a decimal number parser."""
    clean = re.sub(r'[,.!?]', ' ', text.lower()).split()
    if not clean or any(word not in ('zero', 'one') for word in clean):
        raise ValueError('Binary reading must contain only zero/one words')
    return clean


def make_count_rows() -> list[dict]:
    rows = []
    for value in range(128):
        bits = format(value, 'b')
        tokens = ['one' if bit == '1' else 'zero' for bit in bits]
        rows.append({'decimal_value': value, 'display_binary': bits,
                     'display_slots': [None] * (7 - len(bits)) + [int(bit) for bit in bits],
                     'place_weights_left_to_right': WEIGHTS,
                     'spoken_tokens': tokens, 'spoken_text': ', '.join(tokens) + '.',
                     'speech_role': 'binary-digit-sequence', 'decimal_value_is_narrated': False,
                     'active_slot_indices': list(range(7 - len(bits), 7))})
    validate_rows(rows)
    return rows


def validate_rows(rows: list[dict]) -> None:
    if [row['decimal_value'] for row in rows] != list(range(128)):
        raise ValueError('Counted values must be exactly 0 through 127 once each')
    for row in rows:
        bits = row['display_binary']
        if bits != format(row['decimal_value'], 'b'):
            raise ValueError('Noncanonical or incorrect binary representation')
        expected = ['one' if bit == '1' else 'zero' for bit in bits]
        if row['spoken_tokens'] != expected or spoken_tokens(row['spoken_text']) != expected:
            raise ValueError('Spoken digits differ from visible binary digits')
        if row['display_slots'] != [None] * (7 - len(bits)) + [int(bit) for bit in bits]:
            raise ValueError('Unused places must be blank and active places right aligned')
        if row['place_weights_left_to_right'] != WEIGHTS:
            raise ValueError('Incorrect place weights')
        if sum((bit or 0) * weight for bit, weight in zip(row['display_slots'], WEIGHTS)) != row['decimal_value']:
            raise ValueError('Place-value sum differs from decimal value')


def build_estimate(rows, one_duration: float, zero_duration: float = .52):
    if not .1 <= zero_duration <= 2:
        raise ValueError('Zero estimate is not a plausible positive speech duration')
    pre, post, inside = .12, .18, .055
    cursor = 32.0
    states, tokens, pauses, sfx = [], [], [], []
    for row in rows:
        value = row['decimal_value']; start = cursor; cursor += pre
        highlights = []
        for ordinal, token in enumerate(row['spoken_tokens']):
            end = cursor + (one_duration if token == 'one' else zero_duration)
            event = {'role': 'binary-digit', 'decimal_value': value, 'token': token,
                     'ordinal': ordinal, 'slot_index': row['active_slot_indices'][ordinal],
                     'estimated_start_s': cursor, 'estimated_end_s': end}
            highlights.append(event); tokens.append(event); cursor = end
            if ordinal < len(row['spoken_tokens']) - 1: cursor += inside
        speech_end = cursor; cursor += post
        if value in (2, 4, 8, 16, 32, 64):
            sfx.append({'id': 'SE_PLACE', 'estimated_start_s': start + .01,
                        'estimated_end_s': start + .09, 'before_decimal_value': value,
                        'status': 'new-sound-not-generated'})
        if value in (7, 31, 63):
            length = 8 if value == 31 else 3
            dialogue = ([{'text': "Let's stretch.", 'relative_window_s': [.2, 1.5]},
                         {'text': "Ready? Let's keep going!", 'relative_window_s': [5.7, 7.5]}]
                        if value == 31 else [{'text': 'A new place is ready.', 'relative_window_s': [.35, 2.65]}])
            pauses.append({'after_decimal_value': value, 'held_binary': row['display_binary'],
                           'estimated_start_s': cursor, 'duration_s': length,
                           'kind': 'stretch' if value == 31 else 'new-place-comparison', 'dialogue': dialogue})
            cursor += length
        states.append({'decimal_value': value, 'display_binary': row['display_binary'],
                       'estimated_display_start_s': start, 'estimated_speech_end_s': speech_end,
                       'estimated_display_end_s': cursor, 'bit_highlights': highlights})
    finale_start = cursor; cursor += 15
    states[-1]['estimated_display_end_s'] = cursor
    sfx.append({'id': 'SE_FINISH', 'estimated_start_s': finale_start + .08,
                'estimated_end_s': finale_start + 1.08, 'status': 'existing-original-sfx-candidate'})
    return {'schema_version': 1, 'kind': 'estimated-binary-counting-timeline',
            'measurement_status': 'unmeasured-zero-and-new-dialogue', 'production_ready': False,
            'duration_s_estimate': cursor, 'target_band_s': [480, 540],
            'target_upper_bound_exclusive': True, 'counted_states': states, 'bit_speech_events': tokens,
            'pauses': pauses, 'sfx_events': sfx,
            'intro': {'duration_s': 32, 'opening_sfx': False,
                      'dialogue': [{'text': text, 'provisional_window_s': [a, b]} for text, a, b in INTRO_LINES]},
            'finale': {'estimated_start_s': finale_start, 'duration_s': 15,
                       'dialogue': [{'text': text, 'relative_window_s': [a, b]} for text, a, b in FINALE_LINES],
                       'relative_cream_fade_s': [13, 15]},
            'assumptions': {'one_s': one_duration, 'one_measured_in_existing_library': True,
                            'zero_s': zero_duration, 'zero_measured': False,
                            'within_number_gap_s': inside, 'pre_speech_settle_s': pre,
                            'post_speech_hold_s': post, 'endpoint_provisional': True,
                            'existing_one_quality_in_new_sequence_review_pending': True},
            'warning': 'This is a planning estimate, not measured speech or a renderable production timeline. Replace zero/new-dialogue estimates before locking duration or endpoint; no post-generation time stretch.'}


def prepare(out: Path):
    files = ['episode-plan.json', 'count-lines.json', 'count-lines.tsv', 'estimated-timeline.json', 'cue-sheet.json']
    if any((out / name).exists() for name in files):
        raise ValueError('Preproduction files already exist; choose a new staging directory')
    manifest_path = ROOT / 'assets/library/audio/speech/kokoro-af-heart/v002/measurements.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    one = next(row for row in manifest['numbers'] if row['number'] == 1)
    one_file = manifest_path.parent / one['path']
    if hashlib.sha256(one_file.read_bytes()).hexdigest() != one['sha256']:
        raise ValueError('Approved one source checksum changed')
    rows = make_count_rows(); counts = Counter(token for row in rows for token in row['spoken_tokens'])
    estimate = build_estimate(rows, one['duration_s'])
    visual_types = ['new-place-comparison', 'moth-arc', 'cloud-drift', 'stretch', 'leaf-boat', 'small-rainbow', 'flower-sway', 'new-place-comparison', 'moth-return', 'cloud-pair', 'soft-petal', 'pond-ripple', 'leaf-arc', 'small-rainbow', 'flower-sway', 'finale']
    cues = [{'after_decimal_value': value, 'after_binary': format(value, 'b'), 'visual': visual_types[i],
             'mode': 'pause' if value in (7, 31, 63) else ('finale' if value == 127 else 'background-visual-only'),
             'extra_duration_s': {7: 3, 31: 8, 63: 3, 127: 15}.get(value, 0),
             'effect_duration_s': 1.2 if value not in (7, 31, 63, 127) else None,
             'never_occlude_digits_or_face': True, 'extra_spoken_count': False} for i, value in enumerate(range(7, 128, 8))]
    plan = {'schema_version': 1, 'kind': 'binary-episode-preproduction-plan', 'episode_id': 'binary-counting-001',
            'series': {'name': 'Num-Num Numbers', 'url': 'https://pasplastudio.com/num-num-numbers/'},
            'status': 'concept-script-and-static-mockup', 'production_ready': False, 'audio_generated': False, 'video_generated': False,
            'range': {'decimal_start': 0, 'decimal_end': 127, 'display_start': '0', 'display_end': '1111111',
                      'states_including_zero': 128, 'endpoint_provisional': True},
            'duration': {'min_inclusive_s': 480, 'max_exclusive_s': 540, 'source': 'Inherited first-episode preference; current planning assumption',
                         'estimate_s': estimate['duration_s_estimate'], 'measured': False},
            'reading': {'language': 'en-US', 'mode': 'left-to-right digit words', 'allowed_tokens': ['zero', 'one'],
                        'leading_slots': 'blank, not spoken', 'decimal_values_narrated_during_count': False,
                        'tts_input': 'Explicit zero/one word list or reviewed digit clips; never raw numeric strings',
                        'bit_words': sum(counts.values()), 'one_words': counts['one'], 'zero_words': counts['zero']},
            'visual': {'theme_id': 'binary-lantern-garden-v001', 'canvas': [1920, 1080], 'max_slots': 7,
                       'slot_order': WEIGHTS, 'cell_alignment': 'Visible ink centered within each cell; fixed right-aligned places',
                       'background': 'assets/library/worlds/binary-lantern-garden/backgrounds/v001/lantern-garden-background.png',
                       'mockup_source': 'design/binary-counting-v1/mockup/index.html',
                       'reference_directory': 'assets/library/references/binary-counting/v001',
                       'canonical_character': 'assets/library/characters/bear-beret/references/canonical-neutral-v001.png',
                       'color_is_not_the_only_state_marker': True},
            'audio': {'voice_candidate': 'af_heart', 'generation_speed': .98, 'bgm': False, 'opening_noise': False,
                      'one_candidate': {'path': one_file.relative_to(ROOT).as_posix(), 'duration_s': one['duration_s'], 'sha256': one['sha256']},
                      'zero_status': 'not-generated-not-measured', 'sfx_types': 2, 'sfx_uses': 7,
                      'sfx_gain_relative_to_voice_rms_db': -18,
                      'master_target_lufs': -16, 'master_true_peak_max_dbtp': -1},
            'production_gates': ['Dedicated zero-based binary planner/renderer adapter', 'Review new zero/dialogue voices and repeated-digit sequences',
                                 'Measure all adopted speech and recompute duration before endpoint lock', 'Token-by-token hash-bound audio QA; decimal ASR parsing cannot approve binary strings',
                                 'Review actual carry animation and per-bit highlighting in video; static mockups do not approve motion',
                                 'Complete full encoded-video and final-audio QA before delivery'],
            'existing_first_episode_is_modified': False}
    count_file = {'schema_version': 1, 'kind': 'binary-count-script', 'count_start_decimal': 0, 'count_end_decimal': 127,
                  'counted_states': 128, 'status': 'text-validated-audio-not-generated', 'rows': rows}
    cue_file = {'schema_version': 1, 'kind': 'binary-cue-preproduction', 'status': 'design-only',
                'checkpoint_rule': 'After each block of eight counted states: decimal 7,15,...,127. These are binary grouping cues, not decimal tens.',
                'checkpoints': cues, 'place_chime_before_decimal_values': [2, 4, 8, 16, 32, 64],
                'palette': [{'id': 'SE_PLACE', 'duration_s': .08, 'status': 'not-generated', 'method': 'Short pure-tone chime with fade, no noise component',
                             'frequency_hz': 880, 'source_peak_dbfs': -24, 'attack_s': .008, 'release_s': .008},
                            {'id': 'SE_FINISH', 'duration_s': 1.0, 'status': 'existing-candidate', 'path': 'assets/library/audio/sfx/garden/v001/SE_FINISH.wav'}],
                'spoken_digit_overlap_allowed': False, 'bgm': False, 'opening_sfx': False,
                'carry_policy': 'Right-to-left carry cues are separate from left-to-right reading. No changing/invalid intermediate numeric row during speech.'}
    out.mkdir(parents=True, exist_ok=True)
    for name, data in [('episode-plan.json', plan), ('count-lines.json', count_file), ('estimated-timeline.json', estimate), ('cue-sheet.json', cue_file)]:
        with (out / name).open('x', encoding='utf-8') as target:
            json.dump(data, target, ensure_ascii=False, indent=2); target.write('\n')
    with (out / 'count-lines.tsv').open('x', encoding='utf-8', newline='') as target:
        target.write('decimal_reference\tdisplay_binary\tspoken_english\tleft_to_right_slots_64_32_16_8_4_2_1\n')
        for row in rows:
            target.write(f"{row['decimal_value']}\t{row['display_binary']}\t{row['spoken_text']}\t{' '.join('_' if v is None else str(v) for v in row['display_slots'])}\n")
    return {'states': len(rows), 'bit_words': sum(counts.values()), **dict(counts),
            'duration_s_estimate': estimate['duration_s_estimate'], 'audio_generated': False, 'video_generated': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, default=ROOT / 'design/binary-counting-v1')
    print(json.dumps(prepare(parser.parse_args().out_dir)))
