"""F20 handoff type continuity, raster centers and frozen lesson regressions."""
from dataclasses import replace
import json
import math
from pathlib import Path
import unittest

from PIL import Image, ImageChops, ImageDraw
from tools import render_fibonacci_video_v003 as r


def item(report, ident):
    return next(x for x in report['components'] if x['name'].endswith('/'+ident))


class FibonacciTypeTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = json.loads((r.ROOT/'output/fibonacci-counting-001-v003/timeline.json').read_text())
        cls.scene = r.Scene(cls.plan)
        old = json.loads((r.ROOT/'output/fibonacci-counting-001-v002/timeline.json').read_text())
        cls.old = r.previous.Scene(old)

    def test_old_renderers_stay_frozen(self):
        self.assertEqual(r.previous.receipt(Path(r.previous.__file__))['sha256'], r.OLD_V002_RENDERER_SHA256)
        self.assertEqual(r.previous.previous.digest(Path(r.previous.previous.__file__)), r.previous.OLD_RENDERER_SHA256)

    def test_same_measured_audio_and_every_lesson_cue(self):
        base = json.loads(r.previous.checked(self.plan['source_timeline']).read_text())
        for key in r.previous.UNCHANGED_FIELDS:
            self.assertEqual(self.plan[key], base[key], key)
        self.assertEqual(self.plan['encoded_audio_acceptance'], self.old.plan['encoded_audio_acceptance'])
        self.assertEqual(r.previous.checked(self.plan['character_motion']).read_bytes(),
                         r.previous.checked(self.old.plan['character_motion']).read_bytes())

    def test_all31_raster_states_center_on_both_registered_moving_axes(self):
        for tick in range(31):
            _, report = self.scene.image(r.Frame('count', 20, 'transfer', tick))
            t = tick/30
            for i in range(2):
                x = (714 if i == 0 else 1154)-440*t
                y = 417+135*math.sin(math.pi*t)
                number, label = item(report, f'transferred-{i}'), item(report, f'transferred-index-{i}')
                self.assertLessEqual(abs(number['visible_center_px'][0]-x), .5)
                self.assertLessEqual(abs(number['visible_center_px'][1]-y), .5)
                for measured in (number, label):
                    self.assertTrue(measured['horizontal_centered'])
                    self.assertTrue(measured['vertical_centered'])
                    self.assertTrue(measured['contained'])
                    self.assertFalse(measured['touches_measurement_edge'])
                    self.assertTrue(measured['passed'])
                self.assertEqual(label['font_size_px'], 23)
            self.assertTrue(report['foreground_groups_do_not_overlap'])

    def test_arrived_pair_has_identical_numeric_glyph_boxes_to_next_inputs(self):
        _, settled = self.scene.image(r.Frame('count', 20, 'transfer', 30))
        _, following = self.scene.image(r.Frame('count', 21, 'input-a'))
        for i in range(2):
            a, b = item(settled, f'transferred-{i}'), item(following, f'operand-{i}')
            for key in ('text', 'font_size_px', 'visible_box_xyxy'):
                self.assertEqual(a[key], b[key], key)
            self.assertEqual(a['font_size_px'], 47)

    def test_type_changes_only_the_two_copy_glyph_regions(self):
        state = r.Frame('count', 20, 'transfer', 15)
        new, qa = self.scene.image(state)
        old, _ = self.old.image(state)
        mask = Image.new('L', new.size, 255)
        draw = ImageDraw.Draw(mask)
        for i in range(2):
            draw.rectangle(item(qa, f'transferred-{i}')['content_box_xyxy'], fill=0)
        difference = ImageChops.difference(old, new)
        maximum = ImageChops.lighter(difference.getchannel('R'),
                    ImageChops.lighter(difference.getchannel('G'), difference.getchannel('B')))
        self.assertIsNone(ImageChops.multiply(maximum, mask).getbbox())
        self.assertIsNotNone(maximum.getbbox())

    def test_other_math_modes_and_character_pixels_are_identical(self):
        for state in (r.Frame('count', 19, 'transfer', 15), r.Frame('count', 20, 'result'),
                      r.Frame('count', 21, 'input-a'), r.Frame('count', 40, 'result'),
                      r.Frame('replay', 13, carry_column=1, carry_stage='move', carry_tick=15),
                      r.Frame('finale', 40, pose='neutral', legend='history')):
            self.assertEqual(self.scene.image(state)[0].tobytes(), self.old.image(state)[0].tobytes())

    def test_actual_frame_font_cadence_detects_old_one_frame_jump(self):
        row = self.scene.counted[20]
        start = r.previous.previous.frame_at(row['transfer_start_s'])
        end = r.previous.previous.frame_at(self.scene.counted[21]['formula_start_s'])
        new, old = [], []
        for index in range(start, end+1):
            state = self.scene.state(index)
            if state.n == 20:
                new.append(item(self.scene.image(state)[1], 'transferred-0')['font_size_px'])
                old.append(item(self.old.image(state)[1], 'transferred-0')['font_size_px'])
            else:
                new.append(item(self.scene.image(state)[1], 'operand-0')['font_size_px'])
                old.append(item(self.old.image(state)[1], 'operand-0')['font_size_px'])
        self.assertEqual((new[0], new[-1]), (88, 47))
        self.assertTrue(all(a >= b for a, b in zip(new, new[1:])))
        self.assertLessEqual(max(abs(a-b) for a, b in zip(new, new[1:])), 3)
        self.assertEqual(max(abs(a-b) for a, b in zip(old, old[1:])), 41)

    def test_nonfinite_progress_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            r.transfer_font_px(float('nan'))


if __name__ == '__main__':
    unittest.main()
