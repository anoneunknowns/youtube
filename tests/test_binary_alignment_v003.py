"""Verify the requested ink-group centers and unchanged upper artwork."""
from pathlib import Path
import json
import unittest

from PIL import ImageChops

from tools.render_binary_video_v003 import BinaryScene, BinaryTimeline, alignment_layout
from tools.render_binary_video_v002 import DecimalSignScene

ROOT = Path(__file__).resolve().parents[1]


class BinaryAlignmentTests(unittest.TestCase):
    def test_each_requested_group_is_raster_centered(self):
        for number in (0, 7, 45, 64, 127):
            for mode in ('normal', 'stretch', 'intro'):
                audit = alignment_layout(number, 0, mode)
                groups = [audit['main_lower_content'], audit['carry_title_and_markers'], *audit['range_cards']]
                for group in groups:
                    with self.subTest(number=number, mode=mode, group=group['content_box']):
                        self.assertLessEqual(abs(group['after_center_delta_px']), .5)

    def test_accepted_numeric_grid_is_pixel_identical(self):
        timeline = BinaryTimeline(json.loads((ROOT/'output/binary-counting-001-v002/timeline.json').read_text(encoding='utf-8')))
        old, new = DecimalSignScene(timeline), BinaryScene(timeline)
        for value, focus in ((0, 0), (7, 1), (45, 3), (127, 6)):
            with self.subTest(value=value):
                old_grid = old.composition(value, focus, 'normal').crop((610, 228, 1850, 622))
                new_grid = new.composition(value, focus, 'normal').crop((610, 228, 1850, 622))
                self.assertIsNone(ImageChops.difference(old_grid, new_grid).getbbox())

    def test_measured_baseline_offsets_are_retained_for_review(self):
        audit = alignment_layout()
        self.assertEqual(audit['main_lower_content']['before_center_delta_px'], -4.5)
        self.assertEqual(audit['main_lower_content']['shift_y_px'], 5)
        self.assertEqual(audit['carry_title_and_markers']['before_center_delta_px'], 1)
        self.assertEqual(audit['carry_title_and_markers']['shift_y_px'], -1)
        self.assertTrue(all(group['before_center_delta_px'] == -3 for group in audit['range_cards']))


if __name__ == '__main__':
    unittest.main()
