"""Binary reading is a zero/one token sequence, not a decimal number name."""
from collections import Counter
from copy import deepcopy
import unittest
from tools.prepare_binary_episode import build_estimate, make_count_rows, spoken_tokens, validate_rows


class BinaryPlanTests(unittest.TestCase):
    def setUp(self):
        self.rows = make_count_rows()

    def test_known_values_and_seven_place_weights(self):
        for value, bits in [(0, '0'), (1, '1'), (2, '10'), (3, '11'), (4, '100'), (45, '101101'), (64, '1000000'), (127, '1111111')]:
            self.assertEqual(self.rows[value]['display_binary'], bits)
            self.assertEqual(sum((b or 0) * w for b, w in zip(self.rows[value]['display_slots'], [64, 32, 16, 8, 4, 2, 1])), value)

    def test_complete_count_and_repeated_digit_word_totals(self):
        totals = Counter(t for row in self.rows for t in row['spoken_tokens'])
        self.assertEqual(len(self.rows), 128)
        self.assertEqual(totals, {'one': 448, 'zero': 322})

    def test_digit_reading_does_not_accept_decimal_or_raw_numeric_strings(self):
        self.assertEqual(spoken_tokens('one, zero.'), ['one', 'zero'])
        for invalid in ['ten', '10', 'one hundred', 'one oh', '']:
            with self.subTest(text=invalid), self.assertRaises(ValueError):
                spoken_tokens(invalid)

    def test_leading_unused_places_are_blank(self):
        self.assertEqual(self.rows[0]['display_slots'], [None] * 6 + [0])
        self.assertEqual(self.rows[2]['display_slots'], [None] * 5 + [1, 0])

    def test_rejects_skips_repetition_wrong_tokens_and_leading_zero(self):
        for mutate in [lambda r: r.pop(5), lambda r: r.__setitem__(5, r[4]),
                       lambda r: r[2].update(spoken_text='two.'), lambda r: r[0].update(display_binary='00')]:
            rows = deepcopy(self.rows); mutate(rows)
            with self.assertRaises(ValueError): validate_rows(rows)

    def test_estimates_are_not_measured_or_production_ready(self):
        plan = build_estimate(self.rows, .47583333333333333)
        self.assertFalse(plan['production_ready'])
        self.assertFalse(plan['assumptions']['zero_measured'])
        self.assertAlmostEqual(plan['duration_s_estimate'], 515.3233333333333)
        self.assertEqual(len(plan['bit_speech_events']), 770)
        self.assertEqual(len(plan['sfx_events']), 7)
        for sound in plan['sfx_events']:
            self.assertFalse(any(token['estimated_start_s'] < sound['estimated_end_s'] and token['estimated_end_s'] > sound['estimated_start_s'] for token in plan['bit_speech_events']))


if __name__ == '__main__':
    unittest.main()
