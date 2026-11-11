"""Exercise ticket-range edges and regressions for overlapping teaching labels."""

import math
from pathlib import Path
import unittest

from PIL import ImageChops

from tools.portable_production import module
from tools.video_pipeline import english_number

renderer = module('render_odd_video_v002')
mockups = module('render_odd_mockups_v002')


def fixture():
    cursor = 36
    scenes = [{'scene': 'intro', 'start_s': 0, 'end_s': cursor}]
    for value in range(1, 300, 2):
        start = cursor
        voice_start, voice_end = start + .12, start + .72
        cursor = voice_end + (.28 if value == 299 else 1.88) + (8 if value in (9, 101) else 0)
        row = {'scene': 'count', 'decimal_value': value, 'start_s': start, 'end_s': cursor,
               'voice_start_s': voice_start, 'voice_end_s': voice_end}
        if value in (9, 101):
            row['teaching'] = {'id': f'T{value:03}', 'start_s': voice_end + .4, 'end_s': voice_end + 8.4}
        scenes.append(row)
    scenes.append({'scene': 'finale', 'start_s': cursor, 'end_s': cursor + 14})
    return {'fps': 30, 'duration_s': cursor + 14, 'duration_frames': math.ceil((cursor + 14) * 30 - 1e-7),
            'scenes': scenes, 'voice_events': [], 'preview_only': True}


class OddRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = renderer.Scene(fixture())

    def test_integer_ticket_range_keeps_start_and_end_inside_episode(self):
        self.assertEqual(mockups.numberline(1), tuple(range(1, 8)))
        self.assertEqual(mockups.numberline(7), tuple(range(4, 11)))
        self.assertEqual(mockups.numberline(299), tuple(range(293, 300)))
        with self.assertRaises(ValueError):
            mockups.numberline(300)

    def test_all_extended_readings_match_independent_number_words_and_fit(self):
        result = mockups.validate_all_values()
        self.assertEqual(result['all_values_checked'], 150)
        for row in result['values']:
            self.assertEqual(row['spoken_text'], english_number(row['decimal_value']))
            self.assertIn(row['decimal_value'], row['numberline_values'])
            self.assertTrue(all(1 <= value <= 299 for value in row['numberline_values']))
        self.assertEqual(result['maximum_reading_width']['decimal_value'], 277)

    def test_all_one_hundred_fifty_count_states_follow_the_voice_grid(self):
        self.assertEqual(self.scene.audit()['timeline']['odd_values_checked'], 150)
        for row in self.scene.counts:
            at = math.ceil(row['voice_start_s'] * 30 - 1e-7)
            self.assertEqual(self.scene.state(at).value, row['decimal_value'])

    def test_intro_partial_fade_uses_only_the_odd_pair_header(self):
        state = self.scene.state(math.ceil(12.65 * 30))
        actual = self.scene.image(state)
        full = self.scene.still(5, 'five')
        self.assertIsNone(ImageChops.difference(actual.crop((120, 242, 1100, 290)),
                                               full.crop((120, 242, 1100, 290))).getbbox())

    def test_teaching_fade_does_not_retain_normal_instruction_ink(self):
        for value, kind in ((9, 'nine'), (101, 'cross-hundred')):
            actual = self.scene.image(renderer.Frame(phase='count', value=value, diagram=kind,
                                                     diagram_alpha=128, indicator=255))
            target = self.scene.still(value, kind)
            normal = self.scene.still(value)
            checked = 0
            for y in range(748, 792):
                for x in range(300, 1160):
                    if max(normal.getpixel((x, y))) < 140 and min(target.getpixel((x, y))) > 210:
                        self.assertGreater(min(actual.getpixel((x, y))), 190)
                        checked += 1
            self.assertGreater(checked, 100)

    def test_stamp_appears_once_after_finale_start(self):
        before = self.scene.state(math.ceil((self.scene.finale_start + .5) * 30))
        after = self.scene.state(math.ceil((self.scene.finale_start + 1.2) * 30))
        self.assertFalse(before.stamp)
        self.assertTrue(after.stamp)
        self.assertEqual(before.value, 299)
        self.assertEqual(after.value, 299)

    def test_final_frame_reaches_the_cream_endpoint(self):
        image = self.scene.image(self.scene.state(self.scene.frame_count - 1))
        self.assertIsNone(ImageChops.difference(image, renderer.FADE_COLOR).getbbox())


if __name__ == '__main__':
    unittest.main()
