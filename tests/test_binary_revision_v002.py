"""Preserve v001 bounds and reject unapproved pacing or altered speech."""
from copy import deepcopy
from pathlib import Path
import unittest

from tests.test_binary_production import fixture
from tools.verify_binary_production import BinaryValidationError, validate_timeline
from tools.verify_binary_production_v002 import PACING, POLICY, unchanged_speech, validate_policy
from tools.verify_video import PipelineError, verify_video


def revision_policy():
    return {'revision_id': 'binary-counting-v002', 'duration_policy': dict(POLICY),
            'pacing': dict(PACING, playback_speed_changed=False)}


def speech_plan():
    return {'events': [{'type': 'digit_voice', 'id': 'bit-002-0', 'speech_id': 'binary-one',
                        'source_sha256': 'a'*64, 'token': 'one', 'display_binary': '10',
                        'bit_index': 0, 'slot_index': 5, 'start_s': 10, 'end_s': 10.5}]}


class BinaryRevisionTests(unittest.TestCase):
    def test_longer_policy_is_explicit_and_version_scoped(self):
        self.assertEqual(validate_policy(revision_policy()), (480, 600))
        for key in ('revision_id', 'duration_policy'):
            broken = revision_policy()
            broken.pop(key)
            with self.subTest(missing=key), self.assertRaises(BinaryValidationError):
                validate_policy(broken)
        broken = revision_policy()
        broken['duration_policy']['reason'] = 'arbitrary'
        with self.assertRaises(BinaryValidationError):
            validate_policy(broken)

    def test_rejects_changed_voice_speed_and_old_digit_gap(self):
        for field, value in (('playback_speed_changed', True), ('within_number_gap_s', .055), ('post_speech_s', .18)):
            broken = revision_policy()
            broken['pacing'][field] = value
            with self.subTest(field=field), self.assertRaises(BinaryValidationError):
                validate_policy(broken)

    def test_added_pause_may_move_speech_without_altering_samples(self):
        original = speech_plan()
        revised = deepcopy(original)
        revised['events'][0].update(start_s=14, end_s=14.5)
        unchanged_speech(revised, original)

    def test_rejects_changed_clip_hash_or_binary_content(self):
        original = speech_plan()
        for field, value in (('source_sha256', 'b'*64), ('token', 'zero'), ('slot_index', 6)):
            broken = deepcopy(original)
            broken['events'][0][field] = value
            with self.subTest(field=field), self.assertRaises(BinaryValidationError):
                unchanged_speech(broken, original)

    def test_rejects_time_stretched_or_missing_speech(self):
        original = speech_plan()
        broken = deepcopy(original)
        broken['events'][0]['end_s'] += .05
        with self.assertRaisesRegex(BinaryValidationError, 'playback duration'):
            unchanged_speech(broken, original)
        with self.assertRaisesRegex(BinaryValidationError, 'retain all'):
            unchanged_speech({'events': []}, original)

    def test_v001_still_rejects_duration_above_nine_minutes(self):
        timeline, speech = fixture()
        timeline['duration_s'] = 575
        with self.assertRaises(BinaryValidationError):
            validate_timeline(timeline, speech)
        self.assertTrue(validate_timeline(timeline, speech, duration_bounds=(480, 600))['passed'])

    def test_bad_duration_bounds_fail_before_video_access(self):
        for bounds in ((600, 480), (True, 600), (480, float('nan')), (480,)):
            with self.subTest(bounds=bounds), self.assertRaises((PipelineError, ValueError)):
                verify_video(Path('missing.mp4'), Path('missing-qa'), duration_bounds=bounds)


if __name__ == '__main__':
    unittest.main()
