"""Keep pixel alignment audits independent of font origins and decorations."""
import unittest

from PIL import Image,ImageDraw

from tools.binary_alignment_measure import bbox_report,marker_mask,typography_mask


class RasterAlignmentTests(unittest.TestCase):
    def test_teal_glyphs_survive_but_pale_focus_underline_does_not(self):
        image=Image.new('RGB',(80,80),'#fff8ea')
        draw=ImageDraw.Draw(image)
        draw.rectangle((10,20,30,39),fill='#286a73')
        draw.rectangle((5,60,60,63),fill='#64a9af')
        self.assertEqual(typography_mask(image).getbbox(),(10,20,31,40))

    def test_visible_group_reports_known_offset_without_font_metrics(self):
        image=Image.new('L',(60,80),0)
        ImageDraw.Draw(image).rectangle((10,20,49,39),fill=255)
        report=bbox_report(image,(200,300,260,380),(200,300,260,380),'shifted')
        self.assertEqual(report['ink_bbox'],[210,320,250,340])
        self.assertEqual(report['vertical_center_delta_px'],-10)

    def test_pale_carry_markers_are_included_without_board_material(self):
        image=Image.new('RGB',(90,50),'#fffaf0')
        draw=ImageDraw.Draw(image)
        draw.ellipse((10,20,20,30),fill='#d9d1bd')
        draw.ellipse((40,20,50,30),fill='#257d8c')
        self.assertEqual(marker_mask(image).getbbox(),(10,20,51,31))


if __name__=='__main__':unittest.main()
