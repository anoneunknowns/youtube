"""Regression checks for teaching labels that overlapped in the v001 video."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

from PIL import ImageChops


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import render_even_video as previous
import render_even_video_v002 as fixed


class EvenTransitionRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        estimate = json.loads((ROOT / 'design/even-counting-v1/estimated-timeline.json').read_text(encoding='utf-8'))
        cls.scene = fixed.Scene(previous.planning_contract(estimate))

    def assert_no_instruction_ghost(self, value, teaching, kind):
        frame = previous.Frame(phase='count', value=value, intro_mode='',
                               teaching=teaching, diagram_alpha=128)
        actual = self.scene.image(frame)
        normal = self.scene.still(value)
        diagram = self.scene.still(value, kind)
        actual_pixels, normal_pixels, diagram_pixels = actual.load(), normal.load(), diagram.load()
        checked = 0
        for y in range(745, 795):
            for x in range(400, 1100):
                # At these pixels the old normal instruction has solid ink,
                # while the diagram contains only the plain field background.
                if normal_pixels[x, y] == (32, 91, 87) and diagram_pixels[x, y] == (249, 240, 221):
                    self.assertEqual(actual_pixels[x, y], (249, 240, 221))
                    checked += 1
        self.assertGreater(checked, 500)

    def test_intro_six_half_fade_has_only_pair_check_header(self):
        frame = previous.Frame(value=6, intro_mode='six', diagram_alpha=128)
        actual = self.scene.image(frame)
        target = self.scene.still(6, 'pairs')
        header = (480, 242, 900, 290)
        self.assertIsNone(ImageChops.difference(actual.crop(header), target.crop(header)).getbbox())

    def test_twenty_half_fade_does_not_show_normal_instruction(self):
        self.assert_no_instruction_ghost(20, 'T020', 'twenty-pairs')

    def test_hundred_half_fade_does_not_show_normal_instruction(self):
        self.assert_no_instruction_ghost(100, 'T100', 'final-digit-rule')

    def test_hundred_outline_is_fixed_during_diagram_fade(self):
        frame = previous.Frame(phase='count', value=100, intro_mode='',
                               teaching='T100', diagram_alpha=128)
        actual = self.scene.image(frame)
        target = self.scene.still(100, 'final-digit-rule')
        main = (132, 292, 1100, 600)
        self.assertIsNone(ImageChops.difference(actual.crop(main), target.crop(main)).getbbox())

    def test_ordinary_counting_and_finale_are_unchanged(self):
        baseline = previous.Scene(self.scene.timeline)
        for frame in (previous.Frame(phase='count', value=48, intro_mode=''),
                      previous.Frame(phase='finale', value=200, intro_mode='', checkmark=True)):
            with self.subTest(frame=frame):
                self.assertIsNone(ImageChops.difference(self.scene.image(frame), baseline.image(frame)).getbbox())


if __name__ == '__main__':
    unittest.main()
