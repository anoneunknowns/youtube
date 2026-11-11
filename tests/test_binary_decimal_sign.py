"""Check the revised sign preserves the face and follows state boundaries."""
import unittest
from pathlib import Path
import json

from PIL import ImageChops, ImageStat

from tools.render_binary_video import BinaryScene
from tools.render_binary_video_v002 import (
    DecimalSignScene, BinaryTimeline, FACE_SAFE_BBOX, SIGN_BBOX,
    SIGN_VALUE_ROI, SIGN_VALUE_CENTER, SIGN_VALUE_FONT_SIZE, font, sign_geometry,
)

ROOT = Path(__file__).resolve().parents[1]


class DecimalSignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        plan = json.loads((ROOT/'output/binary-counting-001-v001/timeline.json').read_text(encoding='utf-8'))
        cls.scene = DecimalSignScene(BinaryTimeline(plan))
        cls.baseline = BinaryScene(BinaryTimeline(plan))

    def test_decimal_matches_binary_at_every_count_boundary(self):
        for count in self.scene.timeline.counts:
            start = count['start_s']
            with self.subTest(value=count['decimal_value']):
                current = self.scene.state(start)
                self.assertEqual(current['number'], int(count['display_binary'], 2))
                if count['number']:
                    previous = self.scene.state(start-1/48000)
                    self.assertEqual(previous['number'], count['number']-1)

    def test_sign_and_all_decimal_ink_have_clear_margins(self):
        self.assertGreaterEqual(SIGN_BBOX[1]-FACE_SAFE_BBOX[3], 20)
        face = font(SIGN_VALUE_FONT_SIZE)
        for value in range(128):
            with self.subTest(value=value):
                bounds = face.getbbox(str(value))
                x = SIGN_VALUE_CENTER[0]-(bounds[0]+bounds[2])/2
                y = SIGN_VALUE_CENTER[1]-(bounds[1]+bounds[3])/2
                actual = (x+bounds[0],y+bounds[1],x+bounds[2],y+bounds[3])
                self.assertGreaterEqual(actual[0]-SIGN_VALUE_ROI[0], 5)
                self.assertGreaterEqual(SIGN_VALUE_ROI[2]-actual[2], 5)
                self.assertGreaterEqual(actual[1]-SIGN_VALUE_ROI[1], 5)
                self.assertGreaterEqual(SIGN_VALUE_ROI[3]-actual[3], 5)

    def test_neutral_face_pixels_remain_identical_to_accepted_renderer(self):
        count = self.scene.timeline.counts[45]
        time = (count['bit_events'][0]['start_s']+count['bit_events'][0]['end_s'])/2
        actual = self.scene.frame(time).crop(FACE_SAFE_BBOX)
        original = self.baseline.frame(time).crop(FACE_SAFE_BBOX)
        self.assertEqual(sum(ImageStat.Stat(ImageChops.difference(actual,original)).sum), 0)

    def test_grips_allow_stretch_and_one_paw_wave_without_extra_hands(self):
        self.assertEqual(len(sign_geometry('neutral')['grip_paw_bboxes']), 2)
        self.assertEqual(len(sign_geometry('seated_stretch')['grip_paw_bboxes']), 0)
        self.assertEqual(sign_geometry('seated_stretch')['style'], 'resting')
        self.assertEqual(len(sign_geometry('wave_1')['grip_paw_bboxes']), 1)
        self.assertEqual(sign_geometry('wave_1')['style'], 'one-paw')


if __name__=='__main__':
    unittest.main()
