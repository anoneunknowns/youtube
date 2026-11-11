"""Checks that the prime QA rejects content and raster faults, not just metadata."""
from pathlib import Path
import unittest

from PIL import Image, ImageChops

from tools import verify_prime_video as verify

ROOT = Path(__file__).resolve().parents[1]
MOCKUPS = ROOT/'design/prime-counting-v1/mockups'


class IndependentPrimeMath(unittest.TestCase):
    def test_complete_prime_set_has_independent_invariants(self):
        values=verify.sieve()
        self.assertEqual((len(values),sum(values),values[0],values[-1]),(168,76127,2,997))
        self.assertTrue({1,4,6,9,98,99,100,999}.isdisjoint(values))

    def test_inverse_parser_accepts_us_cardinals_and_rejects_bad_combinations(self):
        for text,expected in [('two',2),('ninety-seven',97),('one hundred one',101),
                              ('seven hundred seventy-three',773),('nine hundred ninety-seven',997),
                              ('one two',None),('one hundred hundred',None),('twenty thirteen',None),
                              ('one hundred and one',None),('one thousand',None)]:
            with self.subTest(text=text):self.assertEqual(verify.parse_cardinal(text),expected)

    def test_approved_design_is_inverse_checked(self):
        values,words,authored=verify.checked_design()
        self.assertEqual(len(authored),188)
        self.assertEqual([verify.parse_cardinal(words[n]) for n in values],list(values))


class RasterFaultDetection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=MOCKUPS/'key-visual.png'
        if not path.exists() or path.read_bytes().startswith(b'version https://git-lfs'):
            raise unittest.SkipTest('Prime preproduction PNG bodies are needed for raster checks')
        cls.key=Image.open(path).convert('RGB')
        cls.rotation=Image.open(MOCKUPS/'03b-turning-a-row.png').convert('RGB')
        cls.words=verify.checked_design()[1]

    def test_visible_count_ink_matches_at_native_and_whole_frame_quarter_grid(self):
        for divisor in (1,4):
            image=self.key if divisor==1 else self.key.resize((480,270),Image.Resampling.BOX)
            for name,text,size,field in verify.count_fields(101,self.words):
                actual=verify.darkness(image.crop(tuple(x//divisor for x in field)))
                with self.subTest(divisor=divisor,field=name):
                    self.assertGreater(verify.field_score(actual,text,size,field,divisor),.99)

    def test_wrong_main_value_is_rejected_by_glyph_shape(self):
        actual=verify.darkness(self.key.crop(verify.MAIN))
        self.assertLess(verify.field_score(actual,'103',285,verify.MAIN,1),.9)

    def test_vertical_offset_fails_even_when_horizontal_axis_is_centered(self):
        field=verify.READING
        actual=ImageChops.offset(verify.darkness(self.key.crop(field)),0,3)
        report=verify.raster_centering_report(actual,field,origin_xy=field[:2],tolerance_px=1)
        self.assertTrue(report['horizontal_centered'])
        self.assertFalse(report['vertical_centered'])
        self.assertFalse(report['passed'])

    def test_warm_wall_rotation_has_zero_or_exact_five_tiles_through_fade(self):
        for alpha,quantity in ((0,0),(.5,5),(1,5)):
            image=Image.blend(verify.clean_background(),self.rotation,alpha)
            for name,field,color,_ in verify.TILE_FIELDS['rotation']:
                with self.subTest(alpha=alpha,group=name):
                    self.assertEqual(len(verify.tile_components(image,field,color,name=name,alpha=alpha)),quantity)
                    self.assertTrue(verify.opacity_checks(image,name,field,color,alpha)['passed'])

    def test_full_opacity_cannot_pass_as_mid_fade(self):
        name,field,color,_=verify.TILE_FIELDS['rotation'][0]
        self.assertFalse(verify.opacity_checks(self.rotation,name,field,color,.5)['passed'])

    def test_missing_tile_is_observed_from_pixels(self):
        image=self.rotation.copy()
        # Erase the leftmost tile with the independently loaded clean wall.
        field=verify.TILE_FIELDS['rotation'][0][1]
        image.paste(verify.clean_background().crop((220,550,300,640)),(220,550))
        self.assertEqual(len(verify.tile_components(image,field,'teal',name='horizontal-five')),4)

    def test_ancillary_labels_exclude_parent_plaque_edges_and_warm_floor(self):
        files={'comparison':'03-five-and-six.png','rotation':'03b-turning-a-row.png',
               'one':'04-one-is-not-prime.png','nine':'05-nine-is-not-prime.png',
               'bridge':'06-97-to-101.png','finale':'10-finale.png'}
        for mode,filename in files.items():
            image=Image.open(MOCKUPS/filename).convert('RGB')
            for report in verify.native_labels(image,verify.approved_teacher_labels()[mode],0,mode):
                with self.subTest(mode=mode,text=report['text']):self.assertTrue(report['passed'],report)

    def test_wrong_coloured_factor_equation_cannot_pass_shape_check(self):
        labels=[dict(row) for row in verify.approved_teacher_labels()['rotation']]
        label=next(row for row in labels if row['text']=='1 × 5')
        label['text']='1 × 7'
        reports=verify.native_labels(self.rotation,[label],0,'rotation')
        self.assertFalse(reports[0]['passed'])
        self.assertLess(reports[0]['independent_glyph_iou'],reports[0]['minimum_glyph_iou'])


if __name__=='__main__':unittest.main()
