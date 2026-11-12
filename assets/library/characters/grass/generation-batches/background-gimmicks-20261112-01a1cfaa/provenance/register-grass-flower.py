"""Losslessly register the two delegated plant gimmicks; never publish catalogs."""
from pathlib import Path
import hashlib
import json
import math
import shutil
import sys

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[7]
sys.path.insert(0, str(ROOT))
from tools import character_library as library

OWNER = 'codex:gimmicks-20261112:01a1cfaa'
BATCH = 'background-gimmicks-20261112-01a1cfaa'
ORDER = ['neutral', 'sway_left_soft', 'sway_left_strong', 'sway_right_soft', 'sway_right_strong', 'settle']
CLIPS = {
    'gentle_sway': {'frames': ['neutral', 'sway_left_soft', 'neutral', 'sway_right_soft', 'neutral'],
                    'durations_ms': [650, 320, 450, 320, 650], 'loop': True},
    'gust_left': {'frames': ['neutral', 'sway_left_soft', 'sway_left_strong', 'sway_left_soft', 'neutral'],
                  'durations_ms': [550, 240, 380, 240, 550], 'loop': True},
    'gust_right': {'frames': ['neutral', 'sway_right_soft', 'sway_right_strong', 'sway_right_soft', 'neutral'],
                   'durations_ms': [550, 240, 380, 240, 550], 'loop': True},
    'settle': {'frames': ['sway_left_strong', 'sway_left_soft', 'neutral', 'sway_right_soft', 'settle', 'neutral'],
               'durations_ms': [300, 280, 400, 260, 450, 600], 'loop': True},
}


def relative(path):
    return Path(path).relative_to(ROOT).as_posix()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def mask(image, threshold):
    return image.getchannel('A').point(lambda value: 255 if value >= threshold else 0)


def source_geometry(identity, image):
    visible = mask(image, 8).getbbox()
    solid = mask(image, 128).getbbox()
    if visible is None or solid is None:
        raise ValueError('Empty pose')
    margins = [visible[0], visible[1], image.width-visible[2], image.height-visible[3]]
    if min(margins) < 2:
        raise ValueError(f'Insufficient source alpha8 clearance: {identity}, {margins}')
    bottom = solid[3]
    if identity == 'grass':
        roi = [0, bottom-12, image.width, bottom-4]
        method = 'Root strip: alpha>=128 in the native 8px horizontal band from support-bottom-12 to support-bottom-4; upper flexing leaves excluded.'
    else:
        roi = [0, bottom-math.ceil((solid[3]-solid[1])*.35), image.width, bottom]
        method = 'Soil-and-stone base: alpha>=128 lower35percent ROI; the rigid wide bed, rather than flexing flower tips, defines its horizontal support span.'
    box = mask(image, 128).crop(roi).getbbox()
    base = [box[0]+roi[0], box[1]+roi[1], box[2]+roi[0], box[3]+roi[1]]
    return {'visible_bbox_px': list(visible), 'body_bbox_px': list(visible),
            'subject_bbox_px': list(visible), 'alpha128_bbox_px': list(solid),
            'alpha8_margins_px': margins, 'alpha_extrema': list(image.getchannel('A').getextrema()),
            'base_roi_px': roi, 'base_span_bbox_px': base,
            'base_width_px': base[2]-base[0], 'anchor_px': [(base[0]+base[2])/2, bottom],
            'anchor_kind': 'base', 'anchor_method': method + ' Anchor x is the base span center; y is the measured actual alpha128 subject/base support bottom.',
            'ground_estimated': False}


def render(frame, image, reference, canonical_reference, scale_a, canvas_size, target):
    scale = canonical_reference*scale_a/reference
    size = [max(1, round(image.width*scale)), max(1, round(image.height*scale))]
    resized = image.resize(size, Image.Resampling.LANCZOS)
    origin = [round(target[0]-frame['anchor_px'][0]*scale), round(target[1]-frame['anchor_px'][1]*scale)]
    layer = Image.new('RGBA', canvas_size, (0, 0, 0, 0))
    layer.alpha_composite(resized, tuple(origin))
    support_mask = mask(layer, 128)
    bounds = support_mask.getbbox()
    roi = frame['base_roi_px']
    mapped = [round(origin[0]+roi[0]*scale), round(origin[1]+roi[1]*scale),
              round(origin[0]+roi[2]*scale), round(origin[1]+roi[3]*scale)]
    base = support_mask.crop(mapped).getbbox()
    actual = [(base[0]+base[2])/2+mapped[0], bounds[3]]
    # Correct integer placement only after measuring the actual resized raster.
    # Source pixels and registered native geometry are never changed.
    correction = [round(target[0]-actual[0]), round(target[1]-actual[1])]
    if correction != [0, 0]:
        origin = [origin[i]+correction[i] for i in (0, 1)]
        layer = Image.new('RGBA', canvas_size, (0, 0, 0, 0))
        layer.alpha_composite(resized, tuple(origin))
        mapped = [mapped[0]+correction[0], mapped[1]+correction[1], mapped[2]+correction[0], mapped[3]+correction[1]]
        support_mask = mask(layer, 128)
        bounds = support_mask.getbbox()
        base = support_mask.crop(mapped).getbbox()
        actual = [(base[0]+base[2])/2+mapped[0], bounds[3]]
    visible = mask(layer, 8).getbbox()
    content = [24, 24, canvas_size[0]-24, canvas_size[1]-24]
    dx, dy = actual[0]-target[0], actual[1]-target[1]
    contained = all([content[0] <= visible[0], content[1] <= visible[1], visible[2] <= content[2], visible[3] <= content[3]])
    report = {'pose': frame['id'], 'horizontal_intent': 'base-center', 'vertical_intent': 'base-baseline',
        'content_box': content, 'visible_box_alpha8': list(visible), 'target_base_anchor_px': target,
        'measured_base_anchor_px': actual, 'delta_x_px': dx, 'delta_y_px': dy,
        'tolerance_px': .5, 'horizontal_pass': abs(dx) <= .5, 'vertical_pass': abs(dy) <= .5,
        'contained': contained, 'clipped': not contained, 'empty': False,
        'passed': contained and abs(dx) <= .5 and abs(dy) <= .5,
        'scale': scale, 'registered_native_origin_scaled_px': origin,
        'raster_rounding_translation_correction_px': correction,
        'measurement': 'Actual rendered alpha128 root-strip/soil ROI horizontal center and alpha128 base support bottom; full alpha8 ink separately checked for containment.'}
    return layer, report


def register(identity, name_ja, name_en, preview_width):
    asset = ROOT/'assets/library/characters'/identity
    batch = asset/'generation-batches'/BATCH
    motions, sources = asset/'motions/v001', asset/'sources/v001'
    if any(path.exists() and any(path.iterdir()) for path in (motions, sources)):
        raise ValueError('Registration writes only new empty version directories')
    motions.mkdir(parents=True, exist_ok=True)
    sources.mkdir(parents=True, exist_ok=True)
    original_hashes = {}
    frames, images, sheets = [], {}, []
    for direction, start in [('left', 0), ('right', 3)]:
        original = batch/'source'/f'sway-{direction}-original.png'
        original_hashes[relative(original)] = sha(original)
        expected = json.loads((batch/'provenance'/f'sway-{direction}-output.json').read_text())
        if expected['sha256'] != sha(original):
            raise ValueError('Original changed since generation')
        with Image.open(original) as opened:
            if opened.mode != 'RGBA' or opened.size != (1254, 1254):
                raise ValueError('Expected native RGBA square source')
            raw = opened.copy()
        boundaries = [0, 418, 816, 1254] if identity == 'grass' and direction == 'right' else [0, 418, 836, 1254]
        for row in range(3):
            pose_id = ORDER[start+row]
            crop = [0, boundaries[row], raw.width, boundaries[row+1]]
            image = raw.crop(crop)
            path = motions/(pose_id+'.png')
            image.save(path)
            geometry = source_geometry(identity, image)
            frame = {'id': pose_id, 'path': relative(path), 'sha256': sha(path),
                     'size_px': list(image.size), 'crop_from_sheet_xyxy': crop,
                     'sheet_id': direction, 'source_sheet': relative(original),
                     'source_sheet_sha256': sha(original), 'tail_bbox_px': None, **geometry}
            frames.append(frame)
            images[pose_id] = image
        sheets.append({'id': direction, 'source_sheet': relative(original), 'source_sheet_sha256': sha(original),
                       'generation_input': relative(batch/'provenance'/f'sway-{direction}-input.json'),
                       'generation_prompt': relative(batch/'provenance'/f'sway-{direction}-prompt.txt'),
                       'crop_boundaries_y_px': boundaries,
                       'crop_boundary_note': 'Native transparent gaps; right-grass boundary816 preserves the full settle tip with>=2px alpha8 clearance.' if identity == 'grass' and direction == 'right' else 'Original equal-third row boundaries preserve full native subjects.'})
        for background, color in [('light', '#fff8e8'), ('dark', '#24303a')]:
            composite = Image.new('RGBA', raw.size, color)
            composite.alpha_composite(raw)
            composite.convert('RGB').save(motions/f'native-{direction}-{background}.png')
    neutral, settle = frames[0], frames[-1]
    common_reference = neutral['body_bbox_px'][3]-neutral['body_bbox_px'][1]
    width_a, width_b = neutral['base_width_px'], settle['base_width_px']
    reference_b = common_reference*width_b/width_a
    for sheet, reference, calibration_pose in [(sheets[0], common_reference, 'neutral'), (sheets[1], reference_b, 'settle')]:
        sheet.update(reference_height_px=reference, calibration={
            'neutral_source_reference_height_px': common_reference,
            'neutral_base_width_px': width_a, 'this_sheet_settle_base_width_px': width_b,
            'reference_pose': calibration_pose,
            'method': 'Canonical subject height for A; B reference transferred by stable root-strip/soil-and-stone base width of B settle divided by A neutral base width. Every pose in each sheet uses that one fixed reference; no posed leaf/flower bbox fit.'})
    for frame in frames:
        frame['reference_height_px'] = common_reference if frame['sheet_id'] == 'left' else reference_b
    shutil.copyfile(motions/'neutral.png', sources/'neutral.png')
    assert sha(motions/'neutral.png') == sha(sources/'neutral.png')
    canvas = (900, 500) if identity == 'grass' else (820, 380)
    target = [canvas[0]/2, 420 if identity == 'grass' else 300]
    scale_a = preview_width/(neutral['body_bbox_px'][2]-neutral['body_bbox_px'][0])
    rendered, reports = {}, []
    for frame in frames:
        rendered[frame['id']], report = render(frame, images[frame['id']], frame['reference_height_px'], common_reference, scale_a, canvas, target)
        reports.append(report)
    for background, color in [('light', '#fff8e8'), ('dark', '#24303a')]:
        contact = Image.new('RGB', (canvas[0]*3, canvas[1]*2), color)
        for n, pose_id in enumerate(ORDER):
            composite = Image.new('RGBA', canvas, color)
            composite.alpha_composite(rendered[pose_id])
            contact.paste(composite.convert('RGB'), ((n%3)*canvas[0], (n//3)*canvas[1]))
        contact.save(motions/('pose-review.png' if background == 'light' else 'pose-review-dark.png'))
        for name, clip in CLIPS.items():
            sequence = []
            for pose_id in clip['frames']:
                composite = Image.new('RGBA', canvas, color)
                composite.alpha_composite(rendered[pose_id])
                sequence.append(composite.convert('RGB'))
            destination = motions/(name+('-dark' if background == 'dark' else '')+'.gif')
            sequence[0].save(destination, save_all=True, append_images=sequence[1:], duration=clip['durations_ms'], loop=0, disposal=2)
    shutil.copyfile(motions/'gentle_sway.gif', motions/'key-pose-preview.gif')
    registration = {'schema_version': 3, 'kind': 'generated-gimmick-key-pose-stock', 'version': 'v001',
        'category': 'gimmick', 'character_id': identity, 'owner': OWNER,
        'canonical_neutral': {'path': relative(sources/'neutral.png'), 'sha256': sha(sources/'neutral.png'), 'frame_id': 'neutral'},
        'common_reference_height_px': common_reference, 'sheets': sheets, 'frames': frames, 'clips': CLIPS,
        'source_pixels_modified': False, 'per_pose_bbox_fitting': False,
        'anchor_policy': {'description': 'Native measured root/soil support center and bottom; upper leaves/flowers flex, base remains grounded.', 'ground_estimated': False},
        'scope': 'Six discrete generated key poses; preview GIFs are key-pose loops, not a completed video or a claim of interpolated motion.'}
    write_new(motions/'registration.json', registration)
    library._verify_pose_registration_locked(ROOT, registration, identity, pending=[])
    base_widths = {frame['id']: frame['base_width_px']*common_reference/frame['reference_height_px'] for frame in frames}
    qa = {'schema_version': 1, 'character_id': identity, 'source_hashes_before_after': original_hashes,
        'raw_sources_unchanged': all(sha(ROOT/p) == value for p, value in original_hashes.items()),
        'pose_order': ORDER, 'native_rgba_cell_crops': True, 'all_margins_alpha8_at_least_2px': True,
        'no_alpha_rgb_cleanup': True, 'no_original_resampling': True,
        'calibrated_root_or_bed_widths_in_A_units': base_widths,
        'base_redraw_width_spread_percent': (max(base_widths.values())/min(base_widths.values())-1)*100,
        'review_note': 'Registration aligns actual support centers/baselines and uses fixed sheet scales. Generated base contours are close but not byte-identical; remaining redraw/texture differences are recorded, not repaired by per-pose scaling.',
        'preview_reference_subject_width_px': preview_width, 'preview_canvas_px': list(canvas),
        'both_axes_rendered_checks': reports, 'all_preview_layout_checks_passed': all(r['passed'] for r in reports),
        'native_source_composites': [relative(motions/f'native-{side}-{bg}.png') for side in ('left', 'right') for bg in ('light', 'dark')],
        'verification_scope': 'Original hashes, exact native cell pixel equality, source clearance, support alignment and actual decoded GIF checks; continuous episode motion and scene integration remain future scene QA.'}
    write_new(motions/'geometry-qa.json', qa)
    files = [sources/'neutral.png', Path(__file__).resolve(), motions/'geometry-qa.json']
    for side in ('left', 'right'):
        files.append(batch/'source'/f'sway-{side}-original.png')
        files.extend(batch/'provenance'/f'sway-{side}-{suffix}' for suffix in ('input.json', 'output.json', 'prompt.txt'))
    manifest = {'schema_version': 1, 'kind': 'generated-background-gimmick-source-bundle', 'category': 'gimmick',
        'character_id': identity, 'source_version': 'v001', 'status': 'stocked-and-assistant-reviewed',
        'owner': OWNER, 'source_pixels_modified': False,
        'render_registration': {'neutral_path': 'neutral.png', 'neutral_sha256': sha(sources/'neutral.png'),
            'size_px': neutral['size_px'], 'body_bbox_px': neutral['body_bbox_px'],
            'neutral_anchor_px': neutral['anchor_px'], 'neutral_natural_height_px': common_reference, 'anchor_kind': 'base'},
        'files': [{'path': relative(path), 'sha256': sha(path), 'bytes': path.stat().st_size} for path in files],
        'additional_license_grant': False,
        'provenance_note': 'Raw tool outputs and exact prompts/inputs/outputs remain in this asset generation batch. Bear and red panda were style-only references; B additionally used A top-row neutral as identity reference.'}
    write_new(sources/'source-manifest.json', manifest)
    item = {'id': identity, 'name_ja': name_ja, 'name_en': name_en, 'category': 'gimmick',
        'source_manifest_path': relative(sources/'source-manifest.json'), 'source_manifest_sha256': sha(sources/'source-manifest.json'),
        'registration': relative(motions/'registration.json'), 'registration_sha256': sha(motions/'registration.json'),
        'preview': relative(motions/'pose-review.png'), 'motion_preview': relative(motions/'key-pose-preview.gif')}
    library._gimmick_index_item_locked(ROOT, item, pending=[])
    return item, qa


if __name__ == '__main__':
    entries, summaries = [], []
    for args in [('grass', '草むら', 'Grass', 600), ('flower-bed', '花壇', 'Flower Bed', 520)]:
        item, qa = register(*args)
        entries.append(item)
        summaries.append({'id': item['id'], 'frames': 6, 'layout_pass': qa['all_preview_layout_checks_passed'],
                          'base_redraw_width_spread_percent': qa['base_redraw_width_spread_percent']})
    write_new('/tmp/gimmick-items-grass-flower-bed.json', entries)
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
