"""Regression for fractional final frames cutting off the audio timeline."""
import math
import unittest
from tools.render_counting_video import FPS, covering_frame_count


class RenderTimingTests(unittest.TestCase):
    def test_output_covers_entire_audio_interval_with_less_than_one_extra_frame(self):
        for duration in [.01, 1 / 30, .1, .101, 496.93833333333527, 497.16108333333]:
            with self.subTest(duration=duration):
                output = covering_frame_count(duration) / FPS
                self.assertGreaterEqual(output + 1e-10, duration)
                self.assertLess(output - duration, 1 / FPS)

    def test_exact_frame_duration_does_not_add_an_unnecessary_frame(self):
        self.assertEqual(covering_frame_count(1), 30)
        self.assertEqual(covering_frame_count(14909 / 30), 14909)

    def test_invalid_durations_fail(self):
        for duration in [0, -1, math.nan, math.inf]:
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                covering_frame_count(duration)


if __name__ == '__main__':
    unittest.main()
