"""Immutable sheet extraction and diagnostic registration for app-character issues.

Only exact integer RGBA crops and byte copies become source assets. Resampling
is confined to explicitly labelled previews; no alpha cleanup or body fitting.
This work helper does not change shared inventories, adoption, or Git state.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import tempfile

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / '.work/app-character-issues-20261113'
BODY_SUPPORT = {'drawn-ground-contact', 'drawn-airborne-foot', 'inferred-ground', 'body-contact'}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def payload(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def local(path):
    path = Path(path).resolve()
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def resolve(value):
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', value):
        raise ValueError(f'Invalid immutable ID: {value!r}')
    return value


def vector(value, count, label):
    if (not isinstance(value, (list, tuple)) or len(value) != count
            or any(isinstance(x, bool) or not isinstance(x, (int, float))
                   or not math.isfinite(x) for x in value)):
        raise ValueError(f'{label} must contain {count} finite numbers')
    return list(value)


def box(value, size, label):
    value = vector(value, 4, label)
    if any(int(x) != x for x in value):
        raise ValueError(f'{label} is an integer native-pixel crop/ROI, not a resampling operation')
    value = [int(x) for x in value]
    if not (0 <= value[0] < value[2] <= size[0] and 0 <= value[1] < value[3] <= size[1]):
        raise ValueError(f'{label} outside canvas {size}: {value}')
    return value


def checked_record(record, label):
    if not isinstance(record, dict) or not record.get('sha256'):
        raise ValueError(f'{label} requires an immutable path and SHA-256')
    path = resolve(record['path'])
    if not path.is_file() or digest(path) != record['sha256']:
        raise ValueError(f'{label} missing or SHA changed: {path}')
    return path


def rgba(path):
    with Image.open(path) as image:
        if image.format != 'PNG' or image.mode != 'RGBA':
            raise ValueError(f'Expected native RGBA PNG; no conversion performed: {path}')
        return image.copy()


def alpha_box(image, threshold=8):
    return image.getchannel('A').point(lambda a: 255 if a >= threshold else 0).getbbox()


def components(image, threshold=8):
    """Run-length 8-connected components for diagnostics, never alpha editing."""
    mask = image.getchannel('A').point(lambda a: 255 if a >= threshold else 0)
    data = mask.tobytes()
    parents, stats, previous = [], [], []

    def find(n):
        while parents[n] != n:
            parents[n] = parents[parents[n]]
            n = parents[n]
        return n

    def join(a, b):
        a, b = find(a), find(b)
        if a != b:
            parents[b] = a

    for y in range(image.height):
        current = []
        row = data[y * image.width:(y + 1) * image.width]
        pointer = 0
        for match in re.finditer(b'\xff+', row):
            x0, x1 = match.span()
            n = len(parents)
            parents.append(n)
            stats.append([x1 - x0, x0, y, x1, y + 1])
            while pointer < len(previous) and previous[pointer][1] < x0:
                pointer += 1
            for px0, px1, pn in previous[pointer:]:
                if px0 > x1:
                    break
                if px1 >= x0:
                    join(n, pn)
            current.append((x0, x1, n))
        previous = current
    combined = {}
    for n, (area, x0, y0, x1, y1) in enumerate(stats):
        r = find(n)
        if r not in combined:
            combined[r] = [area, x0, y0, x1, y1]
        else:
            s = combined[r]
            s[0] += area
            s[1], s[2], s[3], s[4] = min(s[1], x0), min(s[2], y0), max(s[3], x1), max(s[4], y1)
    return [{'area_px': s[0], 'bbox_px': s[1:]} for s in sorted(combined.values(), key=lambda s: (-s[0], s[2], s[1]))]


def alpha_diagnostics(image):
    alpha = image.getchannel('A')
    boxes = {str(t): alpha_box(image, t) for t in (1, 8, 128)}
    comp = components(image)
    visible = boxes['8']
    margins = ([visible[0], visible[1], image.width - visible[2], image.height - visible[3]]
               if visible else None)
    return {
        'size_px': list(image.size), 'alpha_extrema': list(alpha.getextrema()),
        'transparent_fraction': alpha.histogram()[0] / (image.width * image.height),
        'visible_bbox_by_alpha_threshold': boxes,
        'alpha8_margins_px': margins, 'alpha8_touches_cell_edge': bool(margins and min(margins) == 0),
        'component_threshold': 8, 'component_connectivity': 8,
        'component_count': len(comp), 'components': comp,
        'component_interpretation': 'Diagnostics only: separated ears/feet/ornaments/texture can be valid; all original pixels retained.',
    }


def feature(image, roi, mode, threshold=128):
    region = image.crop(roi)
    bounds = alpha_box(region, threshold)
    if bounds is None:
        raise ValueError(f'No alpha{threshold} feature in ROI {roi}')
    b = [bounds[0] + roi[0], bounds[1] + roi[1], bounds[2] + roi[0], bounds[3] + roi[1]]
    if mode == 'bbox-center':
        point = [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]
    elif mode == 'bbox-center-bottom':
        point = [(b[0] + b[2]) / 2, b[3]]
    else:
        raise ValueError(f'Unknown observation mode: {mode}')
    return point, b


def inspect(path, columns, rows, out):
    path, out = resolve(path), resolve(out)
    if not out.is_relative_to(WORK):
        raise ValueError('Inspection output must stay in this task work directory')
    image = rgba(path)
    if columns < 1 or rows < 1:
        raise ValueError('Positive sheet grid required')
    cells = []
    for r in range(rows):
        for c in range(columns):
            rect = [round(c * image.width / columns), round(r * image.height / rows),
                    round((c + 1) * image.width / columns), round((r + 1) * image.height / rows)]
            cells.append({'index': len(cells), 'cell_xyxy': rect, 'proposal_only': True,
                          'diagnostics': alpha_diagnostics(image.crop(rect))})
    doc = {'kind': 'unreviewed-native-sheet-grid-inspection', 'schema_version': 1,
           'source': {'path': local(path), 'sha256': digest(path)},
           'size_px': list(image.size), 'grid': [columns, rows], 'cells': cells,
           'note': 'Grid is only a proposal. A reviewer must confirm cell boundaries and provide anatomical body/foot landmarks. No automatic body-height fitting.'}
    out.parent.mkdir(parents=True, exist_ok=True)
    write_identical(out, payload(doc))
    return doc


def write_identical(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise FileExistsError(f'Refusing to overwrite different immutable output: {path}')
    else:
        with path.open('xb') as stream:
            stream.write(data)


def png_bytes(image):
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()


def validate(spec):
    identifier(spec['character_id'])
    identifier(spec['batch_id'])
    seen, sheets = set(), []
    for sheet in spec['sheets']:
        identifier(sheet['id'])
        source = checked_record(sheet['source'], f'{sheet["id"]} raw source')
        image = rgba(source)
        prompt = checked_record(sheet['prompt'], f'{sheet["id"]} exact prompt')
        if not prompt.read_text().strip():
            raise ValueError('Empty exact prompt')
        request = checked_record(sheet['request'], f'{sheet["id"]} exact generation request')
        for item in sheet['input_references']:
            if not item.get('role'):
                raise ValueError('Every input reference needs an explicit role')
            checked_record(item, 'generation input reference')
        calibration = sheet.get('calibration')
        if any(f.get('role', 'body') == 'body' for f in sheet['frames']):
            if not calibration or not calibration.get('method'):
                raise ValueError('Each body sheet needs explicit shared standing/body calibration')
            reference = calibration['reference_height_px']
            if isinstance(reference, bool) or not isinstance(reference, (int, float)) or not math.isfinite(reference) or reference <= 0:
                raise ValueError('reference_height_px must be positive and calibrated, never pose bbox fitted')
            checked_record(calibration['reference_source'], 'calibration reference')
        frames = []
        for frame in sheet['frames']:
            name = identifier(frame['id'])
            if name in seen:
                raise ValueError(f'Duplicate frame ID: {name}')
            seen.add(name)
            cell = box(frame['cell_xyxy'], image.size, name + ' cell')
            crop = image.crop(cell)
            if crop.tobytes() != image.crop(cell).tobytes():
                raise ValueError('Unexpected crop mutation')
            diagnostic = alpha_diagnostics(crop)
            if not diagnostic['visible_bbox_by_alpha_threshold']['8']:
                raise ValueError(f'{name} contains no measurable image')
            if diagnostic['alpha8_touches_cell_edge']:
                raise ValueError(f'{name} visible foreground touches a cell edge; revise grid or regenerate')
            if diagnostic['transparent_fraction'] < .01:
                raise ValueError(f'{name} has no meaningful transparent margin; inspect native output')
            role = frame.get('role', 'body')
            if role not in {'body', 'head-icon'}:
                raise ValueError(f'Unknown source role: {role}')
            body = box(frame['body_bbox_px'], crop.size, name + ' explicit anatomical body bbox')
            if alpha_box(crop.crop(body)) is None:
                raise ValueError(f'{name} anatomical bbox contains no image')
            anchor = vector(frame['anchor_px'], 2, name + ' anatomy anchor')
            foot = vector(frame['source_foot_point_px'], 2, name + ' drawn support/foot point') if role == 'body' else None
            kind = frame['support_kind']
            if kind not in (BODY_SUPPORT if role == 'body' else {'head-icon-center'}):
                raise ValueError(f'{name} support_kind {kind!r} does not match role {role}')
            if any(not 0 <= x <= limit for x, limit in zip(anchor, crop.size)):
                raise ValueError(f'{name} anchor outside cell')
            if not frame.get('support_notes'):
                raise ValueError(f'{name} needs measured/estimated support rationale')
            if role == 'body':
                if not isinstance(frame.get('ground_estimated'), bool):
                    raise ValueError(f'{name} needs explicit ground_estimated')
                lift = frame.get('baked_in_lift_px')
                if not isinstance(lift, (int, float)) or not math.isfinite(lift) or lift < 0:
                    raise ValueError(f'{name} needs nonnegative baked_in_lift_px')
                if kind == 'drawn-airborne-foot':
                    if anchor != foot or frame['ground_estimated'] or lift:
                        raise ValueError(f'{name} airborne anatomy anchor must equal drawn feet; scene adds all lift')
                    if frame.get('scene_motion_policy') != 'app-adds-parabolic-lift; no-native-lift':
                        raise ValueError(f'{name} must explicitly avoid double jump/lift')
                if kind == 'inferred-ground' and (not frame['ground_estimated'] or abs(anchor[1] - foot[1] - lift) > .5):
                    raise ValueError(f'{name} inferred-ground lift must retain drawn foot/ground separation')
                if kind in {'drawn-ground-contact', 'body-contact'} and lift:
                    raise ValueError(f'{name} grounded/body contact cannot hide a baked-in jump')
            observation = frame['observation']
            roi = box(observation['roi_px'], crop.size, name + ' feature ROI')
            mode = observation['mode']
            threshold = observation.get('alpha_threshold', 128)
            if threshold not in range(1, 256):
                raise ValueError('Observation alpha threshold must be 1..255')
            point, observed_box = feature(crop, roi, mode, threshold)
            # ROI must include transparent margins, so a clipped feature cannot pass.
            margins = [observed_box[0] - roi[0], observed_box[1] - roi[1], roi[2] - observed_box[2], roi[3] - observed_box[3]]
            if observation.get('role') == 'contact-band' and mode == 'bbox-center-bottom':
                # A declared foot-contact band deliberately intersects the lower
                # leg at its top. Only its x extent and lowest row are observed.
                margins.pop(1)
            if min(margins) <= 0:
                raise ValueError(f'{name} feature touches observation ROI; use a complete feature with margin')
            frames.append({'spec': frame, 'crop': crop, 'cell': cell, 'body': body, 'role': role,
                           'anchor': anchor, 'foot': foot, 'diagnostic': diagnostic,
                           'source_feature': point, 'source_feature_bbox': observed_box})
        sheets.append({'spec': sheet, 'source': source, 'image': image, 'frames': frames})
    allowed = seen | set(spec.get('external_frames', []))
    for name, clip in spec.get('clips', {}).items():
        identifier(name)
        if not clip or any(frame not in allowed for frame in clip):
            raise ValueError(f'Clip {name} has an unknown or empty frame sequence')
    return sheets


def render_frame(frame, reference_height, display, *, injected_shift_px=(0, 0)):
    # Test-only observer controls. Normal builds always use the zero fault.
    injected_shift_px = vector(injected_shift_px, 2, 'controlled raster shift')
    image = frame['crop']
    canvas = tuple(display.get('canvas_size_px', [1008, 567]))
    content = display.get('content_box_px', [8, 8, canvas[0] - 8, canvas[1] - 8])
    role = frame['role']
    if role == 'head-icon':
        scale = display.get('icon_height_px', 430) / (frame['body'][3] - frame['body'][1])
        target_anchor = display.get('icon_anchor_px', [canvas[0] / 2, canvas[1] / 2])
        intentions = {'horizontal': 'head-icon-center', 'vertical': 'head-icon-center'}
    else:
        scale = display.get('reference_body_height_px', 350) * display.get('scene_scale_ratio', 1) / reference_height
        target_anchor = display.get('anchor_px', [canvas[0] / 2, canvas[1] - 35])
        intentions = {'horizontal': 'anatomical-support-at-scene-x', 'vertical': 'anatomical-support-at-scene-baseline'}
    tx, ty = target_anchor[0] - scale * frame['anchor'][0], target_anchor[1] - scale * frame['anchor'][1]
    observation = frame['spec']['observation']
    # Render the original ROI through the exact same transform and independently
    # measure its alpha. Its native offset to anatomy is retained, not re-zeroed.
    source_mask = Image.new('RGBA', image.size)
    roi = observation['roi_px']
    source_mask.paste(image.crop(roi), (roi[0], roi[1]))
    expected = [frame['source_feature'][0] * scale + tx, frame['source_feature'][1] * scale + ty]
    correction, attempts = [0., 0.], []
    for attempt in range(3):
        inverse = (1 / scale, 0, -(tx + correction[0] + injected_shift_px[0]) / scale,
                   0, 1 / scale, -(ty + correction[1] + injected_shift_px[1]) / scale)
        layer = image.transform(canvas, Image.Transform.AFFINE, inverse,
                                resample=Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0))
        mask_layer = source_mask.transform(canvas, Image.Transform.AFFINE, inverse,
                                          resample=Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0))
        try:
            measured, bbox = feature(mask_layer, [0, 0, *canvas], observation['mode'], observation.get('alpha_threshold', 128))
            delta = [measured[0] - expected[0], measured[1] - expected[1]]
        except ValueError:
            measured, bbox, delta = None, None, None
        attempts.append({'delta_x_px': delta[0] if delta else None, 'delta_y_px': delta[1] if delta else None,
                         'correction_px': list(correction)})
        if delta is None or all(abs(v) <= .5 for v in delta) or attempt == 2:
            break
        proposed = [correction[i] - delta[i] for i in (0, 1)]
        # Same bounded diagnostic placement calibration as the repository's
        # image_remake_review._preview. Native pixels and declared registration
        # never change, and the expected observed feature stays fixed.
        if any(abs(v) > 1.5 for v in proposed):
            break
        correction = proposed
    if (delta is not None and not all(abs(v) <= .5 for v in delta)
            and all(abs(attempts[0][f'delta_{axis}_px']) <= 1.5 for axis in ('x', 'y'))):
        # Integer alpha bounds can cycle when simultaneous x/y feedback crosses
        # a sampling phase boundary. Search a fixed bounded phase grid without
        # moving the source target or enlarging tolerance. A >1.5px initial
        # error is never eligible, so large placement faults remain rejected.
        phases = [(x / 4, y / 4) for x in range(-6, 7) for y in range(-6, 7)]
        phases.sort(key=lambda xy: (xy[0] ** 2 + xy[1] ** 2, abs(xy[0]), abs(xy[1]), xy))
        for candidate in phases:
            correction = list(candidate)
            inverse = (1 / scale, 0, -(tx + correction[0] + injected_shift_px[0]) / scale,
                       0, 1 / scale, -(ty + correction[1] + injected_shift_px[1]) / scale)
            layer = image.transform(canvas, Image.Transform.AFFINE, inverse,
                                    resample=Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0))
            mask_layer = source_mask.transform(canvas, Image.Transform.AFFINE, inverse,
                                              resample=Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0))
            try:
                measured, bbox = feature(mask_layer, [0, 0, *canvas], observation['mode'], observation.get('alpha_threshold', 128))
                delta = [measured[0] - expected[0], measured[1] - expected[1]]
            except ValueError:
                measured, bbox, delta = None, None, None
            attempts.append({'delta_x_px': delta[0] if delta else None, 'delta_y_px': delta[1] if delta else None,
                             'correction_px': list(correction), 'phase_search_step_px': .25})
            if delta is not None and all(abs(v) <= .5 for v in delta):
                break
    visible = alpha_box(layer)
    contained = bool(visible and content[0] < visible[0] and content[1] < visible[1]
                     and visible[2] < content[2] and visible[3] < content[3])
    native_visible = frame['diagnostic']['visible_bbox_by_alpha_threshold']['8']
    projected = [native_visible[0] * scale + tx, native_visible[1] * scale + ty,
                 native_visible[2] * scale + tx, native_visible[3] * scale + ty]
    expected_contained = (content[0] < projected[0] and content[1] < projected[1]
                          and projected[2] < content[2] and projected[3] < content[3])
    passed_x = bool(delta is not None and abs(delta[0]) <= .5)
    passed_y = bool(delta is not None and abs(delta[1]) <= .5)
    report = {
        'canvas_size_px': list(canvas), 'content_box_px': content, 'intentions': intentions,
        'controlled_raster_shift_px': injected_shift_px,
        'alpha_threshold_visible': 8, 'alpha_threshold_feature': observation.get('alpha_threshold', 128),
        'isotropic_scale': scale, 'common_sheet_reference_height_px': reference_height,
        'per_pose_height_fit': False, 'upsampling': scale > 1,
        'target_anatomical_anchor_px': target_anchor, 'source_observation_roi_px': roi,
        'source_observed_feature_px': frame['source_feature'],
        'source_feature_offset_from_anatomical_anchor_px': [frame['source_feature'][i] - frame['anchor'][i] for i in range(2)],
        'projected_feature_px': expected, 'measured_feature_px': measured, 'measured_feature_bbox_px': bbox,
        'delta_x_px': delta[0] if delta else None, 'delta_y_px': delta[1] if delta else None,
        'placement_calibration': {'method': 'bounded preview-only raster placement against fixed projected source feature',
                                  'correction_px': correction, 'maximum_correction_px_each_axis': 1.5,
                                  'measurements': attempts, 'source_bytes_changed': False,
                                  'declared_anchor_changed': False, 'scale_changed': False,
                                  'content_box_changed': False, 'tolerance_changed': False},
        'tolerance_px_each_axis': .5, 'horizontal_passed': passed_x, 'vertical_passed': passed_y,
        'actual_visible_bbox_px': visible, 'projected_visible_bbox_px': projected,
        'actual_contained_with_margin': contained, 'expected_contained_with_margin': expected_contained,
        'passed': passed_x and passed_y and contained and expected_contained,
        'scope': 'SOURCE native preview raster alignment only; anatomy/style/sequence review remains required.',
    }
    return layer, report


def build(spec_path, out):
    spec_path, out = resolve(spec_path), resolve(out)
    spec_bytes = spec_path.read_bytes()
    spec = json.loads(spec_bytes)
    owned_batch = ROOT / 'assets/library/characters' / identifier(spec['character_id']) / 'generation-batches/app-stock-20261113-v001'
    if not ((out.is_relative_to(WORK) and out != WORK)
            or (out.is_relative_to(owned_batch) and out != owned_batch)):
        raise ValueError('Output must be in this task work root or the character reserved app-stock batch')
    if out.exists():
        raise FileExistsError(f'Use a new immutable output revision: {out}')
    sheets = validate(spec)  # Validate every input before publishing any output.
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=out.name + '-preparing-', dir=out.parent))
    try:
        (temporary / 'registration-spec.json').write_bytes(spec_bytes)
        registration = {
            'schema_version': 1, 'kind': 'app-character-native-pose-registration',
            'character_id': spec['character_id'], 'batch_id': spec['batch_id'],
            'status': 'candidate-prepared; visual-review-and-manager-adoption-required',
            'source_pixels_modified': False, 'alpha_cleanup_applied': False,
            'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'spec': {'path': local(out / 'registration-spec.json'), 'sha256': hashlib.sha256(spec_bytes).hexdigest()},
            'sheets': [], 'frames': [], 'clips': spec.get('clips', {}),
            'scale_policy': 'One calibrated standing/body reference per sheet, common isotropic scene scale; no individual pose bbox fitting. Head icons use a separate role.',
        }
        previews, layouts, image_thumbs = {}, {}, []
        for sheet in sheets:
            s = sheet['spec']
            raw_dest = temporary / 'raw' / (s['id'] + '.png')
            raw_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(sheet['source'], raw_dest)
            if digest(raw_dest) != s['source']['sha256']:
                raise ValueError('Raw byte copy verification failed')
            provenance = dict(s)
            provenance['original_source'] = s['source']
            provenance['archived_source'] = {'path': local(out / 'raw' / raw_dest.name), 'sha256': digest(raw_dest)}
            provenance['archived_input_references'] = []
            for ref in s['input_references']:
                ref_source = checked_record(ref, 'generation reference')
                archived = dict(ref)
                if ref_source.is_relative_to(ROOT / '.work'):
                    dest_name = ref_source.stem + '-' + ref['sha256'][:10] + ref_source.suffix
                    dest = temporary / 'inputs' / dest_name
                    write_identical(dest, ref_source.read_bytes())
                    archived['original_generation_input_path'] = ref['path']
                    archived['path'] = local(out / 'inputs' / dest_name)
                provenance['archived_input_references'].append(archived)
            for key in ('prompt', 'request'):
                record = s[key]
                source_path = checked_record(record, key)
                suffix = '.txt' if key == 'prompt' else '.json'
                dest = temporary / 'provenance' / (s['id'] + '-' + key + suffix)
                write_identical(dest, source_path.read_bytes())
                provenance[key] = {'path': local(out / 'provenance' / dest.name), 'sha256': digest(dest)}
            prov_dest = temporary / 'provenance' / (s['id'] + '.json')
            write_identical(prov_dest, payload(provenance))
            reference_height = s.get('calibration', {}).get('reference_height_px')
            registration['sheets'].append({
                'id': s['id'], 'source_sheet': local(out / 'raw' / raw_dest.name),
                'source_sheet_sha256': digest(raw_dest), 'source_size_px': list(sheet['image'].size),
                'reference_height_px': reference_height, 'calibration': s.get('calibration'),
                'generation_input': local(out / 'provenance' / prov_dest.name),
                'generation_prompt': provenance['prompt']['path'],
            })
            for frame in sheet['frames']:
                f, name, crop = frame['spec'], frame['spec']['id'], frame['crop']
                dest = temporary / 'poses' / (name + '.png')
                write_identical(dest, png_bytes(crop))
                saved = rgba(dest)
                if saved.size != crop.size or saved.tobytes() != sheet['image'].crop(frame['cell']).tobytes():
                    raise ValueError('Saved crop is not pixel-identical to source cell')
                record = {k: f[k] for k in f if k not in {'cell_xyxy', 'observation'}}
                record.update(path=local(out / 'poses' / dest.name), sha256=digest(dest),
                              size_px=list(crop.size), body_bbox_px=frame['body'],
                              role=frame['role'], source_sheet=local(out / 'raw' / raw_dest.name),
                              source_sheet_sha256=digest(raw_dest), sheet_id=s['id'],
                              crop_from_sheet_xyxy=frame['cell'], exact_cell_pixel_match=True,
                              source_pixels_modified=False,
                              tail_bbox_px=f.get('tail_bbox_px'),
                              reference_height_px=reference_height if frame['role'] == 'body' else None,
                              generation_provenance=local(out / 'provenance' / prov_dest.name))
                if frame['role'] == 'body':
                    record.update(anchor_kind=f.get('anchor_kind', f['support_kind']),
                                  anchor_measurement=f.get('anchor_measurement', 'measured-native-anatomical-support'),
                                  anchor_basis=f.get('anchor_basis', f['support_notes']),
                                  vertical_motion_policy=f.get('vertical_motion_policy', f.get('scene_motion_policy', 'grounded; no scene lift by default')))
                registration['frames'].append(record)
                write_identical(temporary / 'qa' / (name + '-native.json'), payload(frame['diagnostic']))
                layer, layout = render_frame(frame, reference_height, spec.get('display', {}))
                layouts[name] = layout
                previews[name] = {}
                for theme, color in [('light', '#faf4e8'), ('dark', '#192634')]:
                    bg = Image.new('RGBA', layer.size, color)
                    bg.alpha_composite(layer)
                    path = temporary / 'previews' / theme / (name + '.png')
                    write_identical(path, png_bytes(bg))
                    previews[name][theme] = {'path': local(out / 'previews' / theme / path.name), 'sha256': digest(path)}
                    if theme == 'light':
                        thumb = bg.resize((336, 189), Image.Resampling.LANCZOS)
                        card = Image.new('RGB', (336, 215), '#faf4e8')
                        card.paste(thumb.convert('RGB'), (0, 22))
                        ImageDraw.Draw(card).text((8, 5), name, fill='#182432')
                        image_thumbs.append(card)
        for name, clip in spec.get('clips', {}).items():
            local_clip = [f for f in clip if f in previews]
            if len(local_clip) != len(clip):
                continue  # Never silently substitute a missing external neutral.
            sequence = []
            for frame_name in local_clip:
                path = temporary / 'previews/light' / (frame_name + '.png')
                with Image.open(path) as image:
                    sequence.append(image.convert('RGB').resize((504, 284), Image.Resampling.LANCZOS))
            stream = io.BytesIO()
            sequence[0].save(stream, format='GIF', save_all=True, append_images=sequence[1:],
                             duration=display_duration(spec), loop=0, disposal=2, optimize=False)
            write_identical(temporary / 'previews' / (name + '-key-poses.gif'), stream.getvalue())
        if image_thumbs:
            grid = Image.new('RGB', (1008, 215 * math.ceil(len(image_thumbs) / 3)), '#faf4e8')
            for n, card in enumerate(image_thumbs):
                grid.paste(card, ((n % 3) * 336, (n // 3) * 215))
            write_identical(temporary / 'previews/contact-sheet-light.png', png_bytes(grid))
        neutral = next((f for f in registration['frames'] if f['id'] == 'neutral' and f['role'] == 'body'), None)
        if spec.get('canonical_neutral'):
            checked_record(spec['canonical_neutral'], 'canonical neutral')
            registration['canonical_neutral'] = spec['canonical_neutral']
        elif neutral:
            registration['canonical_neutral'] = {'path': neutral['path'], 'sha256': neutral['sha256']}
        else:
            raise ValueError('Body registration requires an explicit fixed canonical_neutral')
        write_identical(temporary / 'registration.json', payload(registration))
        qa = {
            'schema_version': 1, 'kind': 'app-character-source-diagnostics',
            'status': 'requires-visual-review', 'registration': local(out / 'registration.json'),
            'registration_sha256': digest(temporary / 'registration.json'),
            'all_source_cells_pixel_exact': True, 'alpha_cleanup_applied': False,
            'layout_all_passed': all(v['passed'] for v in layouts.values()),
            'layouts': layouts, 'previews': previews,
            'manual_review_required': ['identity and markings', 'native stroke/texture at maximum app display size',
                                       'anatomical body reference and support landmarks',
                                       'alpha fringe and every disconnected component on light/dark',
                                       'standing-to-success and seated-title-to-tap sequence',
                                       'pond anatomical airborne feet and scene parabola without duplicate lift',
                                       'native maximum canvas display of 567px; no quality inference from bitmap dimensions alone'],
            'limits': 'A deterministic diagnostic cannot establish visual quality, smooth interpolation, or final application acceptance. Candidate status is not official adoption.',
        }
        observer = temporary / 'qa/observer.py'
        write_identical(observer, Path(__file__).read_bytes())
        qa['observer'] = {'path': local(out / 'qa/observer.py'), 'sha256': digest(observer)}
        write_identical(temporary / 'qa/diagnostics.json', payload(qa))
        # Write receipt last. The final directory appears only once all input and
        # native-cell checks finish. No shared catalog is touched.
        receipt = {'kind': 'immutable-pose-preparation-receipt', 'character_id': spec['character_id'],
                   'output': local(out), 'frames': len(registration['frames']),
                   'layout_all_passed': qa['layout_all_passed'],
                   'files': [{'path': local(out / p.relative_to(temporary)), 'sha256': digest(p), 'bytes': p.stat().st_size}
                             for p in sorted(temporary.rglob('*')) if p.is_file()]}
        write_identical(temporary / 'receipt.json', payload(receipt))
        # Recheck immutable inputs immediately before publishing prepared output.
        validate(spec)
        if spec_path.read_bytes() != spec_bytes:
            raise ValueError('Specification changed while preparing output')
        temporary.rename(out)
        return receipt
    except BaseException:
        shutil.rmtree(temporary)
        raise


def display_duration(spec):
    value = spec.get('display', {}).get('key_pose_duration_ms', 400)
    if not isinstance(value, int) or not 100 <= value <= 2000:
        raise ValueError('Key-pose diagnostic GIF duration must be explicit 100..2000ms')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('inspect')
    p.add_argument('source')
    p.add_argument('--columns', type=int, default=2)
    p.add_argument('--rows', type=int, default=2)
    p.add_argument('--out', required=True)
    p = sub.add_parser('build')
    p.add_argument('spec')
    p.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    if args.command == 'inspect':
        result = inspect(args.source, args.columns, args.rows, args.out)
        print(json.dumps({'source': result['source'], 'size_px': result['size_px'],
                          'cells': [{'index': c['index'], 'cell_xyxy': c['cell_xyxy'],
                                     'bbox': c['diagnostics']['visible_bbox_by_alpha_threshold']['8'],
                                     'components': c['diagnostics']['component_count'],
                                     'touches_cell_edge': c['diagnostics']['alpha8_touches_cell_edge']}
                                    for c in result['cells']]}, ensure_ascii=False))
    else:
        result = build(args.spec, args.out)
        print(json.dumps({k: result[k] for k in ['character_id', 'output', 'frames', 'layout_all_passed']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
