"""Check the longer lesson preserves pacing and rejects a sub-eight-minute plan."""

from copy import deepcopy
import unittest

from tools.portable_production import module

builder = module('build_odd_episode_v002')


def sources(seconds=1):
    def clip(text):
        return {'path': 'synthetic-test.wav', 'sha256': '0' * 64,
                'sample_frames': round(seconds * 24000), 'spoken_text': text}
    cues = builder.script_cues()
    numbers = {value: clip(builder.english_number(value)) for value in range(1, 300, 2)}
    dialogue = {row['id']: {**clip(row['text']), 'sample_frames': 2400} for row in cues}
    return numbers, dialogue, cues


class OddBuilderV002Tests(unittest.TestCase):
    def test_extended_range_reuses_the_two_second_pace(self):
        plan = builder.make_plan(*sources())
        self.assertEqual([row['decimal_value'] for row in plan['counted_states']], list(range(1, 300, 2)))
        self.assertEqual(len(plan['voice_events']), 163)
        self.assertEqual(plan['timing']['ordinary_number_gap_s'], 2)
        self.assertEqual(plan['timing']['ordinary_boundaries'], 147)
        self.assertAlmostEqual(plan['duration_s'], 150 + 364.4)
        self.assertEqual(plan['pacing_policy']['minimum_duration_s'], 480)

    def test_under_eight_minutes_is_rejected_without_stretching_speech(self):
        with self.assertRaisesRegex(ValueError, 'at least eight minutes'):
            builder.make_plan(*sources(seconds=.2))

    def test_changing_the_gap_to_reach_duration_is_rejected(self):
        plan = builder.make_plan(*sources())
        plan['voice_events'][8]['start_sample_24k'] += 28800
        with self.assertRaises(ValueError):
            builder.validate(plan)

    def test_stop_at_199_or_an_even_number_is_rejected(self):
        plan = builder.make_plan(*sources())
        for bad in (199, 298, 301):
            changed = deepcopy(plan)
            final = next(row for row in changed['voice_events'] if row.get('decimal_value') == 299)
            final['decimal_value'] = bad
            with self.assertRaisesRegex(ValueError, '150 odd values'):
                builder.validate(changed)


if __name__ == '__main__':
    unittest.main()
