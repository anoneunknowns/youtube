"""Distinguish full-value pauses from digit gaps and registered teaching audio."""
from array import array
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
import wave

from tools.verify_binary_production import BinaryValidationError
from tools.verify_binary_production_v004 import validate_policy as validate_v004_policy
from tools.verify_binary_production_v005 import (
    PACING, POLICY, inspect_number_silence, number_silence_segments,
    number_transition_windows, validate_policy,
)


def policy():
    return {'revision_id': 'binary-counting-v005', 'duration_policy': dict(POLICY),
            'pacing': dict(PACING, playback_speed_changed=False)}


def transition_fixture():
    """Minimal boundary fixture; digit spelling is covered by the base tests."""
    events = []
    cursor = .12
    extras = {7: 3, 31: 8, 63: 3}
    for number in range(128):
        end = cursor + .5
        events.append({'type': 'count', 'number': number, 'decimal_value': number,
                       'start_s': cursor - .12, 'voice_end_s': end,
                       'bit_events': [{'id': f'number-{number}', 'start_s': cursor, 'end_s': end}]})
        if number in extras:
            events.append({'type': 'pause', 'after_decimal_value': number,
                           'start_s': end + 1.88, 'end_s': end + 1.88 + extras[number]})
        cursor = end + 2 + extras.get(number, 0)
    return {'events': events}


class CompleteValuePauseTests(unittest.TestCase):
    def test_two_second_policy_is_explicit_and_version_scoped(self):
        self.assertEqual(validate_policy(policy()), (480, 1440))
        with self.assertRaises(BinaryValidationError):
            validate_v004_policy(policy())
        broken = policy()
        broken['duration_policy']['reason'] = 'arbitrary'
        with self.assertRaises(BinaryValidationError):
            validate_policy(broken)

    def test_digit_gap_final_hold_and_voice_speed_cannot_substitute(self):
        for field, value in (('within_number_gap_s', .6), ('post_speech_s', .28),
                             ('between_number_voice_gap_s', .4), ('final_post_speech_s', 1.88),
                             ('playback_speed_changed', True)):
            broken = policy()
            broken['pacing'][field] = value
            with self.subTest(field=field), self.assertRaises(BinaryValidationError):
                validate_policy(broken)

    def test_all_127_boundaries_have_correct_teaching_exceptions(self):
        rows = number_transition_windows(transition_fixture())
        self.assertEqual(len(rows), 127)
        self.assertEqual(sum(row['kind'] == 'ordinary' for row in rows), 124)
        self.assertEqual([round(row['duration_s']) for row in rows if row['kind'] == 'teaching'], [5, 10, 5])
        self.assertTrue(all(abs(row['duration_s'] - 2) < 1e-8 for row in rows if row['kind'] == 'ordinary'))

    def test_actual_next_value_start_is_checked(self):
        for delta in (-.1, .1):
            broken = transition_fixture()
            row = next(row for row in broken['events'] if row['type'] == 'count' and row['number'] == 2)
            row['bit_events'][0]['start_s'] += delta
            with self.subTest(delta=delta), self.assertRaisesRegex(BinaryValidationError, 'not two seconds'):
                number_transition_windows(broken)

    def test_only_registered_chime_and_teaching_narration_can_be_excluded(self):
        timeline = transition_fixture()
        transitions = number_transition_windows(timeline)
        boundary = transitions[1]
        chime = {'type': 'sfx', 'id': 'SE_PLACE', 'before_decimal_value': 2,
                 'start_s': boundary['end_s'] - .11, 'end_s': boundary['end_s'] - .03}
        timeline['events'].append(chime)
        segments, exclusions = number_silence_segments(timeline, transitions)
        self.assertEqual(len(exclusions), 1)
        self.assertAlmostEqual(sum(row['end_s'] - row['start_s'] for row in segments if row['after_decimal_value'] == 1), 1.92)
        for replacement in ({'id': 'SE_FAKE'}, {'before_decimal_value': 4},
                            {'type': 'dialogue', 'phase': 'stretch'}):
            broken = deepcopy(timeline)
            broken['events'][-1].update(replacement)
            with self.subTest(replacement=replacement), self.assertRaises(BinaryValidationError):
                number_silence_segments(broken, transitions)

    def inspect(self, segments, noises=(), guard=.002, limit=1):
        data = array('h', [0] * 120000)
        for start, end, amplitude in noises:
            for index in range(round(start * 48000), round(end * 48000)):
                data[index] = amplitude
        if sys.byteorder != 'little':
            data.byteswap()
        temp = Path('D:/temp')
        with tempfile.TemporaryDirectory(prefix='number-pause-unit-', dir=temp if temp.is_dir() else None) as folder:
            path = Path(folder) / 'audio.wav'
            with wave.open(str(path), 'wb') as output:
                output.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
                output.writeframes(data.tobytes())
            with wave.open(str(path), 'rb') as reader:
                return inspect_number_silence(reader, segments, guard, limit)

    def test_actual_two_second_pcm_pause_is_silent(self):
        segments = [{'after_decimal_value': 1, 'start_s': .3, 'end_s': 2.3}]
        result = self.inspect(segments, noises=((.1, .29, 5000), (2.31, 2.4, 5000)))
        self.assertAlmostEqual(result[0]['verified_silence_s'], 1.996)
        self.assertEqual(result[0]['interior_peak_pcm16'], 0)
        with self.assertRaisesRegex(BinaryValidationError, 'Unexpected sound'):
            self.inspect(segments, noises=((1.0, 1.1, 5000),))

    def test_codec_guards_handle_the_short_tail_after_a_chime(self):
        segments = [{'after_decimal_value': 1, 'start_s': .3, 'end_s': 2.19},
                    {'after_decimal_value': 1, 'start_s': 2.27, 'end_s': 2.3}]
        result = self.inspect(segments, noises=((2.19, 2.27, 5000),), guard=.03, limit=3)
        self.assertAlmostEqual(result[0]['verified_silence_s'], 1.83)
        self.assertEqual(result[1]['reason'], 'codec-boundary-guards')
        with self.assertRaisesRegex(BinaryValidationError, 'Unexpected sound'):
            self.inspect(segments, noises=((1.0, 1.1, 5000),), guard=.03, limit=3)


if __name__ == '__main__':
    unittest.main()
