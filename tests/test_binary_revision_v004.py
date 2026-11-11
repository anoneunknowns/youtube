"""Keep word pauses distinct from post-count holds and verify actual silence."""
from array import array
from pathlib import Path
import sys
import tempfile
import unittest
import wave

from tools.verify_binary_production import BinaryValidationError
from tools.verify_binary_production_v002 import validate_policy as validate_v002_policy
from tools.verify_binary_production_v004 import (
    PACING, POLICY, digit_gap_windows, inspect_gap_windows, validate_policy,
)


def policy():
    return {'revision_id': 'binary-counting-v004', 'duration_policy': dict(POLICY),
            'pacing': dict(PACING, playback_speed_changed=False)}


def two_word_count(gap=.9):
    return {'events': [{'type': 'count', 'decimal_value': 2, 'voice_end_s': 1.12 + gap,
                        'end_s': 1.40 + gap, 'bit_events': [
                            {'id': 'one', 'start_s': .12, 'end_s': .62},
                            {'id': 'zero', 'start_s': .62 + gap, 'end_s': 1.12 + gap},
                        ]}]}


class LongerWordPauseTests(unittest.TestCase):
    def test_v004_policy_requires_nine_hundred_millisecond_word_gaps(self):
        self.assertEqual(validate_policy(policy()), (480, 1200))
        for old_gap in (.055, .10, .20, .30, .60, .80):
            broken = policy()
            broken['pacing']['within_number_gap_s'] = old_gap
            with self.subTest(gap=old_gap), self.assertRaises(BinaryValidationError):
                validate_policy(broken)

    def test_long_duration_cannot_be_enabled_by_an_unrelated_policy(self):
        for key, value in (('revision_id', 'binary-counting-v002'),
                           ('duration_policy', dict(POLICY, reason='arbitrary'))):
            broken = policy()
            broken[key] = value
            with self.subTest(field=key), self.assertRaises(BinaryValidationError):
                validate_policy(broken)
        with self.assertRaises(BinaryValidationError):
            validate_v002_policy(policy())

    def test_voice_speed_and_post_count_hold_remain_unchanged(self):
        for key, value in (('playback_speed_changed', True), ('post_speech_s', .5)):
            broken = policy()
            broken['pacing'][key] = value
            with self.subTest(field=key), self.assertRaises(BinaryValidationError):
                validate_policy(broken)

    def test_word_gap_is_measured_from_audio_end_to_next_audio_start(self):
        count = two_word_count()
        windows = digit_gap_windows(count)
        self.assertEqual(len(windows), 1)
        self.assertAlmostEqual(windows[0]['duration_s'], .9)
        self.assertEqual(windows[0]['from_id'], 'one')
        # Changing the time after the complete count cannot substitute for a
        # pause between its two words.
        count['events'][0]['end_s'] += 10
        self.assertEqual(digit_gap_windows(count), windows)
        with self.assertRaisesRegex(BinaryValidationError, 'not 900ms'):
            digit_gap_windows(two_word_count(.1))

    def inspect(self, noises=(), guard=.002, limit=1):
        windows = [{'from_id': 'one', 'to_id': 'zero', 'decimal_value': 2,
                    'start_s': .3, 'end_s': 1.2, 'duration_s': .9}]
        data = array('h', [0] * 72000)
        for start, end, amplitude in noises:
            for index in range(round(start * 48000), round(end * 48000)):
                data[index] = amplitude
        if sys.byteorder != 'little':
            data.byteswap()
        task_temp = Path('D:/temp')
        with tempfile.TemporaryDirectory(prefix='gap-unit-', dir=task_temp if task_temp.is_dir() else None) as folder:
            path = Path(folder) / 'samples.wav'
            with wave.open(str(path), 'wb') as output:
                output.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
                output.writeframes(data.tobytes())
            with wave.open(str(path), 'rb') as reader:
                return inspect_gap_windows(reader, windows, guard, limit)

    def test_actual_pcm_has_a_long_silent_gap(self):
        result = self.inspect(noises=((.1, .29, 5000), (1.21, 1.4, 5000)))
        self.assertEqual(result[0]['interior_peak_pcm16'], 0)
        self.assertAlmostEqual(result[0]['silent_interior_s'], .896)

    def test_an_audio_event_hidden_in_a_declared_pause_is_rejected(self):
        with self.assertRaisesRegex(BinaryValidationError, 'contains sound'):
            self.inspect(noises=((.4, .41, 5000),))

    def test_aac_guards_allow_boundary_preecho_but_not_middle_speech(self):
        result = self.inspect(noises=((.3, .31, 500), (1.19, 1.2, 500)), guard=.03, limit=3)
        self.assertAlmostEqual(result[0]['silent_interior_s'], .84)
        with self.assertRaisesRegex(BinaryValidationError, 'contains sound'):
            self.inspect(noises=((.4, .41, 500),), guard=.03, limit=3)


if __name__ == '__main__':
    unittest.main()
