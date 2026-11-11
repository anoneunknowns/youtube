"""Reject centering mistakes that one-axis or canvas-only checks miss."""
import unittest

from PIL import Image, ImageDraw

from tools.component_alignment import centering_report, raster_centering_report


class ComponentCenteringTests(unittest.TestCase):
    field = (20, 10, 120, 90)  # Independent target center: (70, 50).

    def layer(self, box, size=(160, 100), alpha=255):
        image = Image.new('RGBA', size)
        left, top, right, bottom = box
        ImageDraw.Draw(image).rectangle((left, top, right - 1, bottom - 1), fill=(90, 40, 5, alpha))
        return image

    def test_both_axes_and_equal_opposing_margins_pass(self):
        report = raster_centering_report(self.layer((50, 30, 90, 70)), self.field)
        self.assertTrue(report['passed'])
        self.assertEqual((report['delta_x_px'], report['delta_y_px']), (0, 0))
        self.assertEqual(report['margins_px'], {'left': 30, 'right': 30, 'top': 20, 'bottom': 20})

    def test_horizontal_center_alone_does_not_pass(self):
        report = raster_centering_report(self.layer((50, 36, 90, 76)), self.field)
        self.assertTrue(report['horizontal_centered'])
        self.assertFalse(report['vertical_centered'])
        self.assertEqual(report['delta_y_px'], 6)
        self.assertFalse(report['passed'])

    def test_vertical_center_alone_does_not_pass(self):
        report = raster_centering_report(self.layer((59, 30, 99, 70)), self.field)
        self.assertFalse(report['horizontal_centered'])
        self.assertTrue(report['vertical_centered'])
        self.assertEqual(report['delta_x_px'], 9)
        self.assertFalse(report['passed'])

    def test_opposite_offsets_cannot_cancel(self):
        report = raster_centering_report(self.layer((54, 26, 94, 66)), self.field)
        self.assertEqual((report['delta_x_px'], report['delta_y_px']), (4, -4))
        self.assertFalse(report['passed'])

    def test_centered_but_overflowing_group_fails(self):
        report = centering_report(self.field, (10, 20, 130, 80))
        self.assertTrue(report['horizontal_centered'] and report['vertical_centered'])
        self.assertFalse(report['contained'])
        self.assertFalse(report['passed'])

    def test_asymmetric_padding_uses_declared_content_box(self):
        report = centering_report((10, 30, 110, 90), (40, 45, 80, 75))
        self.assertEqual(report['target_center_px'], [60, 60])
        self.assertTrue(report['passed'])

    def test_half_pixel_rounding_limit_is_explicit_on_each_axis(self):
        report = centering_report(self.field, (51, 31, 90, 70))
        self.assertEqual((report['delta_x_px'], report['delta_y_px']), (.5, .5))
        self.assertTrue(report['passed'])
        self.assertFalse(centering_report(self.field, (52, 31, 90, 70))['passed'])

    def test_crop_origin_is_translated_into_frame_coordinates(self):
        report = raster_centering_report(self.layer((10, 10, 50, 50), size=(80, 80)), self.field,
                                         origin_xy=(40, 20))
        self.assertEqual(report['visible_box_xyxy'], [50, 30, 90, 70])
        self.assertTrue(report['passed'])

    def test_multiline_component_uses_union_of_visible_lines(self):
        mask = Image.new('L', (160, 100), 0)
        draw = ImageDraw.Draw(mask)
        draw.rectangle((50, 25, 89, 39), fill=255)
        draw.rectangle((60, 60, 79, 74), fill=255)
        report = raster_centering_report(mask, self.field)
        self.assertEqual(report['visible_box_xyxy'], [50, 25, 90, 75])
        self.assertTrue(report['passed'])

    def test_transparent_canvas_center_is_not_component_center(self):
        report = raster_centering_report(self.layer((64, 22, 104, 62)), self.field)
        self.assertEqual((report['delta_x_px'], report['delta_y_px']), (14, -8))
        self.assertFalse(report['passed'])

    def test_low_alpha_fringe_is_not_ink_but_alpha254_is_valid(self):
        image = self.layer((50, 30, 90, 70), alpha=254)
        ImageDraw.Draw(image).rectangle((3, 3, 5, 5), fill=(90, 40, 5, 1))
        self.assertTrue(raster_centering_report(image, self.field)['passed'])

    def test_measurement_edge_contact_fails_instead_of_hiding_clipping(self):
        report = raster_centering_report(self.layer((0, 10, 40, 50), size=(40, 60)), (0, 0, 40, 60))
        self.assertTrue(report['horizontal_centered'] and report['vertical_centered'])
        self.assertTrue(report['touches_measurement_edge'])
        self.assertFalse(report['passed'])

    def test_empty_mask_and_opaque_rgb_frame_cannot_pass(self):
        for image in [Image.new('L', (100, 100)), Image.new('RGB', (100, 100), 'white')]:
            with self.subTest(mode=image.mode), self.assertRaises(ValueError):
                raster_centering_report(image, self.field)

    def test_invalid_geometry_and_tolerance_are_rejected(self):
        for box in [(0, 0, 0, 10), (0, 10, 20, 0), (0, 0, float('nan'), 10), (0, 0, float('inf'), 10)]:
            with self.subTest(box=box), self.assertRaises(ValueError):
                centering_report(self.field, box)
        for tolerance in [-1, float('nan'), float('inf')]:
            with self.subTest(tolerance=tolerance), self.assertRaises(ValueError):
                centering_report(self.field, (50, 30, 90, 70), tolerance_px=tolerance)


if __name__ == '__main__':
    unittest.main()
