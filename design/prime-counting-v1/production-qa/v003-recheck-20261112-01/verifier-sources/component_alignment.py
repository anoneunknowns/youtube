"""Measure both axes of intended frame-centered foreground components.

Use half-open xyxy rectangles in output pixels and a dedicated foreground mask.
The parent frame, background and shadows must be absent from that mask.
"""
from __future__ import annotations

import math
from numbers import Real

from PIL import Image


def _rectangle(value, name):
    if len(value) != 4 or any(isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v) for v in value):
        raise ValueError(f'{name} must contain four finite coordinates')
    left, top, right, bottom = value
    if left >= right or top >= bottom:
        raise ValueError(f'{name} must have positive width and height')
    return tuple(value)


def centering_report(content_box, visible_box, *, name='component', tolerance_px=.5):
    """Check visible bounds against an explicitly defined usable frame interior."""
    content = _rectangle(content_box, 'content_box')
    visible = _rectangle(visible_box, 'visible_box')
    if (isinstance(tolerance_px, bool) or not isinstance(tolerance_px, Real)
            or not math.isfinite(tolerance_px) or tolerance_px < 0):
        raise ValueError('tolerance_px must be finite and nonnegative')
    target = [(content[0] + content[2]) / 2, (content[1] + content[3]) / 2]
    center = [(visible[0] + visible[2]) / 2, (visible[1] + visible[3]) / 2]
    dx, dy = center[0] - target[0], center[1] - target[1]
    horizontal, vertical = abs(dx) <= tolerance_px, abs(dy) <= tolerance_px
    contained = (content[0] <= visible[0] and content[1] <= visible[1]
                 and visible[2] <= content[2] and visible[3] <= content[3])
    failures = []
    if not horizontal:
        failures.append('horizontal_center_mismatch')
    if not vertical:
        failures.append('vertical_center_mismatch')
    if not contained:
        failures.append('outside_content_box')
    return {
        'name': name, 'content_box_xyxy': list(content), 'visible_box_xyxy': list(visible),
        'target_center_px': target, 'visible_center_px': center,
        'delta_x_px': dx, 'delta_y_px': dy, 'tolerance_px': tolerance_px,
        'horizontal_centered': horizontal, 'vertical_centered': vertical,
        'contained': contained,
        'margins_px': {'left': visible[0] - content[0], 'right': content[2] - visible[2],
                       'top': visible[1] - content[1], 'bottom': content[3] - visible[3]},
        'passed': not failures, 'failures': failures,
    }


def raster_centering_report(layer: Image.Image, content_box, *, origin_xy=(0, 0),
                            name='component', tolerance_px=.5, alpha_threshold=128):
    """Measure actual foreground, not font metrics or a padded image canvas.

Keep a clear margin around the whole component. Edge contact is rejected because
a clipped group could appear centered. RGB video needs a foreground mask first.
"""
    if (len(origin_xy) != 2 or any(isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v) for v in origin_xy)):
        raise ValueError('origin_xy must contain two finite coordinates')
    if isinstance(alpha_threshold, bool) or not isinstance(alpha_threshold, int) or not 1 <= alpha_threshold <= 255:
        raise ValueError('alpha_threshold must be an integer from 1 to 255')
    if layer.mode == 'RGBA':
        mask = layer.getchannel('A')
    elif layer.mode in ('L', '1'):
        mask = layer.convert('L')
    else:
        raise ValueError('Supply a dedicated RGBA foreground layer or L/1 mask, not an opaque RGB frame')
    bounds = mask.point(lambda value: 255 if value >= alpha_threshold else 0).getbbox()
    if bounds is None:
        raise ValueError(f'No measurable foreground in {name}; an empty component cannot pass')
    absolute = [bounds[0] + origin_xy[0], bounds[1] + origin_xy[1],
                bounds[2] + origin_xy[0], bounds[3] + origin_xy[1]]
    report = centering_report(content_box, absolute, name=name, tolerance_px=tolerance_px)
    touches = bounds[0] == 0 or bounds[1] == 0 or bounds[2] == layer.width or bounds[3] == layer.height
    report.update(measurement='foreground-raster-bounds', alpha_threshold=alpha_threshold,
                  measurement_origin_px=list(origin_xy), touches_measurement_edge=touches)
    if touches:
        report['failures'].append('foreground_touches_measurement_edge')
        report['passed'] = False
    return report
