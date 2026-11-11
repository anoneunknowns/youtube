"""Register the reviewed, non-destructive ten-character expansion.

Source art is never repainted: frames are exact 3x3 cell crops. Each sheet has
one independently calibrated standing reference height, shared by its nine poses.
The canonical neutral and old productions remain unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFont

try:
    from .component_alignment import raster_centering_report
except ImportError:
    from component_alignment import raster_centering_report

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = 'assets/library/collections/character-expansion/v001'
INDEX = 'catalogs/character-library-v1.json'
GROUPS = {
    'reactions': ['neutral', 'blink', 'tap_down', 'tap_pop', 'think', 'aha', 'oops', 'retry', 'signature'],
    'actions': ['success_ready', 'success_air', 'success_land', 'cheer', 'clap_open', 'wave_low', 'wave_high_in', 'wave_high_out', 'wave_rest'],
    'postures': ['half_seated', 'seated_neutral', 'seated_stretch_half', 'seated_stretch', 'seated_nap', 'seated_look_up', 'seated_look_board', 'stand_half', 'nod_down'],
}
TARGETS = ['rabbit-beret', 'tora', 'little-bird', 'siamese-cat', 'red-panda', 'meerkat', 'kangaroo', 'hedgehog', 'fairy-pitta', 'onagadori']


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write('\n')


def project_path(root, value):
    path = Path(value).expanduser()
    path = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'Reference leaves checkout: {value}')
    return path


def local(root, path):
    return Path(path).resolve().relative_to(root.resolve()).as_posix()


def positive(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'{label} needs a finite positive number')
    return value


def rectangle(value, size, label):
    if not isinstance(value, list) or len(value) != 4 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise ValueError(f'{label} needs a finite xyxy box')
    if not 0 <= value[0] < value[2] <= size[0] or not 0 <= value[1] < value[3] <= size[1]:
        raise ValueError(f'{label} leaves cell')
    return value


def rgba_details(image):
    if image.mode != 'RGBA':
        raise ValueError('Source must be RGBA; no conversion or alpha cleaning is performed')
    alpha = image.getchannel('A')
    extrema = alpha.getextrema()
    bounds = alpha.point(lambda a: 255 if a >= 8 else 0).getbbox()
    if bounds is None or extrema[0] != 0 or extrema[1] < 240:
        raise ValueError('Source needs a nonempty subject and genuine transparent alpha')
    margins = [bounds[0], bounds[1], image.width - bounds[2], image.height - bounds[3]]
    if min(margins) < 2:
        raise ValueError(f'Subject touches cell edge: {margins}; regenerate source')
    return {'size_px': list(image.size), 'visible_bbox_px': list(bounds),
            'alpha_extrema': list(extrema), 'visible_alpha8_margins_px': margins,
            'rgba_pixel_sha256': hashlib.sha256(image.tobytes()).hexdigest()}


def cells(sheet_path, group):
    if group not in GROUPS:
        raise ValueError(f'Unknown sheet group: {group}')
    with Image.open(sheet_path) as source:
        if source.format != 'PNG' or source.mode != 'RGBA':
            raise ValueError('Source must be a genuine RGBA PNG')
        metadata = rgba_details(source)
        output = []
        for index, identity in enumerate(GROUPS[group]):
            col, row = index % 3, index // 3
            region = [round(col * source.width / 3), round(row * source.height / 3),
                      round((col + 1) * source.width / 3), round((row + 1) * source.height / 3)]
            image = source.crop(region)
            output.append({'id': identity, 'index': index, 'crop_from_sheet_xyxy': region,
                           'image': image, **rgba_details(image)})
    return {'sha256': sha(sheet_path), **metadata}, output


def inspect_sheet(character, group, sheet, output):
    if character not in TARGETS:
        raise ValueError(f'Unknown expansion character: {character}')
    output = Path(output)
    if output.exists():
        raise FileExistsError(f'Use a new inspection directory: {output}')
    sheet = Path(sheet).resolve()
    details, frames = cells(sheet, group)
    output.mkdir(parents=True)
    for frame in frames:
        frame['image'].save(output / (frame['id'] + '.png'))
    draft = {'id': group, 'source_sheet': str(sheet), 'source_sheet_sha256': details['sha256'],
             'prompt_path': str(sheet.with_name(group + '-prompt.txt')),
             'generation_input_path': str(sheet.with_name(group + '-input.json')),
             'reference_height_px': None,
             'calibration': {'method': '', 'reference_pose': 'neutral' if group == 'reactions' else 'wave_rest' if group == 'actions' else 'seated_neutral', 'notes': ''},
             'frames': [{'id': frame['id'], 'index': frame['index'],
                         'body_bbox_px': frame['visible_bbox_px'], 'anchor_px': None,
                         'support_kind': 'inferred-ground-plane' if frame['id'] in ('tap_pop', 'success_air') else 'anatomical-support',
                         'support_notes': '',
                         **({'tail_bbox_px': None} if character == 'onagadori' else {}),
                         'review': ''} for frame in frames]}
    write_new(output / 'annotation-draft.json', draft)
    write_new(output / 'inspection.json', {'character_id': character, 'group': group,
              'source_sheet': str(sheet), 'sheet': details, 'source_pixels_modified': False,
              'frames': [{key: value for key, value in frame.items() if key != 'image'} for frame in frames]})
    return {'status': 'pass', 'character_id': character, 'group': group, 'frames': len(frames), 'output': str(output)}


def validate_item(root, item, canonical, reviewed):
    identity = item['id']
    if identity not in TARGETS or item.get('version', 'v002') != 'v002':
        raise ValueError('Expansion expects known non-bear characters at v002')
    notes = item.get('review', {})
    if reviewed and any(not notes.get(key, '').strip() for key in ['identity', 'style', 'alpha', 'motion']):
        raise ValueError(f'{identity}: identity/style/alpha/motion review notes required')
    sheets = item['sheets']
    if [sheet['id'] for sheet in sheets] != list(GROUPS):
        raise ValueError(f'{identity}: all three ordered sheet groups required')
    neutral = canonical['neutral']
    if sha(project_path(root, neutral['path'])) != neutral['sha256']:
        raise ValueError(f'{identity}: canonical neutral changed')
    checked = []
    for annotation in sheets:
        group = annotation['id']
        sheet = project_path(root, annotation['source_sheet'])
        details, frames = cells(sheet, group)
        if annotation.get('source_sheet_sha256') != details['sha256']:
            raise ValueError(f'{identity}/{group}: annotation sheet hash mismatch')
        reference = positive(annotation.get('reference_height_px'), f'{identity}/{group} reference height')
        calibration = annotation.get('calibration', {})
        if reviewed and any(not calibration.get(key) for key in ['method', 'reference_pose', 'notes']):
            raise ValueError(f'{identity}/{group}: reviewed scale calibration required')
        prompt_path = project_path(root, annotation['prompt_path'])
        generation_path = project_path(root, annotation['generation_input_path'])
        if not prompt_path.read_text(encoding='utf-8-sig').strip():
            raise ValueError('Exact generation prompt is empty')
        provenance = read(generation_path)
        if provenance.get('exact_model_identifier_exposed') is False and provenance.get('model_id'):
            raise ValueError('Do not invent a hidden generation model identifier')
        references = []
        for reference_input in provenance.get('input_references', []):
            path = project_path(root, reference_input['path'])
            checksum = sha(path)
            if not reference_input.get('sha256') or reference_input['sha256'] != checksum:
                raise ValueError(f'{identity}/{group}: missing or changed generation reference hash')
            references.append({**reference_input, 'path': local(root, path)})
        if not any(ref['path'] == neutral['path'] and ref.get('role') for ref in references):
            raise ValueError(f'{identity}/{group}: selected canonical neutral reference required')
        if [frame['id'] for frame in annotation['frames']] != GROUPS[group]:
            raise ValueError(f'{identity}/{group}: wrong frame coverage/order')
        for frame, geometry in zip(frames, annotation['frames'], strict=True):
            if geometry.get('index') != frame['index']:
                raise ValueError('Cell index mismatch')
            body = rectangle(geometry.get('body_bbox_px'), frame['size_px'], 'body')
            if frame['image'].getchannel('A').crop(body).getbbox() is None:
                raise ValueError('Annotated body is empty')
            anchor = geometry.get('anchor_px') or geometry.get('support_anchor_px')
            if (not isinstance(anchor, list) or len(anchor) != 2
                    or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in anchor)
                    or not body[0] <= anchor[0] <= body[2] or not body[1] < anchor[1] <= frame['size_px'][1]):
                raise ValueError(f'{identity}/{frame["id"]}: anatomical support anchor required')
            tail = geometry.get('tail_bbox_px')
            if identity == 'onagadori' and tail is None:
                raise ValueError('Onagadori body and tail must be annotated separately')
            if tail:
                rectangle(tail, frame['size_px'], 'tail')
                if frame['image'].getchannel('A').crop(tail).getextrema()[1] < 8:
                    raise ValueError('Annotated tail is empty')
                if identity == 'onagadori':
                    union = Image.new('L', frame['image'].size, 0)
                    annotation_draw = ImageDraw.Draw(union)
                    for bounds in [body, tail]:
                        annotation_draw.rectangle((bounds[0], bounds[1], bounds[2] - 1, bounds[3] - 1), fill=255)
                    visible_mask = frame['image'].getchannel('A').point(lambda a: 255 if a >= 8 else 0)
                    if ImageChops.subtract(visible_mask, union).getbbox():
                        raise ValueError('Onagadori artwork leaves annotated body/tail bounds')
            if reviewed and frame['id'] in ('tap_pop', 'success_air') and (
                    geometry.get('support_kind') != 'inferred-ground-plane' or not geometry.get('support_notes')):
                raise ValueError('Airborne support must be explicitly recorded as an inferred ground plane')
            frame.update(body_bbox_px=body, anchor_px=anchor, tail_bbox_px=tail,
                         reference_height_px=reference, source_sheet=local(root, sheet),
                         source_sheet_sha256=details['sha256'], sheet_id=group,
                         review=geometry.get('review', ''),
                         support_kind=geometry.get('support_kind', 'anatomical-support'),
                         support_notes=geometry.get('support_notes', ''),
                         measurement_notes=geometry.get('measurement_notes', []))
        checked.append({'id': group, 'path': sheet, 'details': details, 'frames': frames,
                        'reference_height_px': reference, 'calibration': calibration,
                        'generation_input': local(root, generation_path),
                        'generation_input_sha256': sha(generation_path),
                        'generation_prompt': local(root, prompt_path), 'generation_prompt_sha256': sha(prompt_path),
                        'generation_references': references})
    return {'id': identity, 'item': item, 'canonical': canonical, 'sheets': checked,
            'frames': [frame for sheet in checked for frame in sheet['frames']]}


def font(root, size):
    path = root / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
    return ImageFont.truetype(str(path), size) if path.is_file() else ImageFont.load_default()


def previews(root, check, output):
    """Centered tiles are for inspection; playback uses fixed scale/foot anchors."""
    frames = check['frames']
    tile_w, tile_h = (850, 450) if check['id'] == 'onagadori' else (460, 450)
    content = [16, 62, tile_w - 16, tile_h - 16]
    title_font = font(root, 17)
    reports = []
    # Only the inspection overview fits each sprite. Playback below never does.
    pages = {name: Image.new('RGB', (tile_w * 3, tile_h * 9), bg)
             for name, bg in [('pose-review.png', '#fff8e8'), ('pose-review-dark.png', '#203b3e')]}
    for index, frame in enumerate(frames):
        bounds = frame['visible_bbox_px']
        sprite = frame['image'].crop(bounds)
        scale = min((content[2] - content[0] - 8) / sprite.width, (content[3] - content[1] - 8) / sprite.height)
        sprite = sprite.resize((max(1, round(sprite.width * scale)), max(1, round(sprite.height * scale))), Image.Resampling.LANCZOS)
        actual = sprite.getchannel('A').point(lambda a: 255 if a >= 8 else 0).getbbox()
        x = round((content[0] + content[2] - actual[0] - actual[2]) / 2)
        y = round((content[1] + content[3] - actual[1] - actual[3]) / 2)
        layer = Image.new('RGBA', (tile_w, tile_h), 0)
        layer.alpha_composite(sprite, (x, y))
        report = raster_centering_report(layer, content, name=f'{check["id"]}/{frame["id"]}', alpha_threshold=8)
        report.update(state=frame['id'], resolution_px=[tile_w, tile_h],
                      alignment_intent={'horizontal': 'center', 'vertical': 'center'},
                      preview_scale=scale, source_pixels_modified=False)
        if not report['passed']:
            raise ValueError(f'Inspection tile alignment failed: {report}')
        reports.append(report)
        for filename, page in pages.items():
            bg = '#fff8e8' if filename == 'pose-review.png' else '#203b3e'
            tile = Image.new('RGBA', (tile_w, tile_h), bg)
            tile.alpha_composite(layer)
            ImageDraw.Draw(tile).text((16, 18), f'{frame["sheet_id"]} / {frame["id"]}', font=title_font,
                                     fill='#63390d' if filename == 'pose-review.png' else '#fff8e8')
            page.paste(tile.convert('RGB'), ((index % 3) * tile_w, (index // 3) * tile_h))
    for filename, page in pages.items():
        page.save(output / filename)
    write_new(output / 'alignment-report.json', {'status': 'pass', 'scope': 'All 27 centered inspection sprites; playback is foot-anchored, not center-aligned.',
              'alpha_threshold': 8, 'tolerance_px': .5, 'records': reports})
    # Compute one fixed support point large enough for every state at calibrated scale.
    target_height = 280
    scaled = {}
    left = right = top = bottom = 0
    for frame in frames:
        scale = target_height / frame['reference_height_px']
        bounds = frame['visible_bbox_px']
        sprite = frame['image'].crop(bounds)
        sprite = sprite.resize((max(1, round(sprite.width * scale)), max(1, round(sprite.height * scale))), Image.Resampling.LANCZOS)
        offset = [round((bounds[0] - frame['anchor_px'][0]) * scale), round((bounds[1] - frame['anchor_px'][1]) * scale)]
        scaled[frame['id']] = (sprite, offset, scale)
        left = min(left, offset[0]); top = min(top, offset[1])
        right = max(right, offset[0] + sprite.width); bottom = max(bottom, offset[1] + sprite.height)
    size = (right - left + 64, bottom - top + 96)
    support = [32 - left, 64 - top]
    playback = {}
    playback_records = []
    for frame in frames:
        sprite, offset, scale = scaled[frame['id']]
        canvas = Image.new('RGBA', size, '#fff8e8')
        xy = [support[0] + offset[0], support[1] + offset[1]]
        if xy[0] < 1 or xy[1] < 1 or xy[0] + sprite.width >= size[0] or xy[1] + sprite.height >= size[1]:
            raise ValueError('Foot-anchored motion preview clips a sprite')
        canvas.alpha_composite(sprite, tuple(xy))
        ImageDraw.Draw(canvas).text((10, 10), frame['id'], font=title_font, fill='#63390d')
        playback[frame['id']] = canvas.convert('RGB')
        playback_records.append({'id': frame['id'], 'sheet_id': frame['sheet_id'], 'scale': scale,
                                 'reference_height_px': frame['reference_height_px'],
                                 'support_point_px': support, 'sprite_xy_px': xy, 'clipped': False})
    sequences = {
        'key-pose-preview.gif': [frame['id'] for frame in frames],
        'wave-preview.gif': ['wave_rest', 'wave_low', 'wave_high_in', 'wave_high_out', 'wave_high_in', 'wave_low', 'wave_rest'],
        'success-preview.gif': ['neutral', 'success_ready', 'success_air', 'success_land', 'neutral'],
        'postures-preview.gif': ['neutral', 'half_seated', 'seated_neutral', 'seated_stretch_half', 'seated_stretch', 'seated_stretch_half', 'seated_neutral', 'stand_half', 'neutral'],
    }
    for filename, sequence in sequences.items():
        images = [playback[name] for name in sequence]
        images[0].save(output / filename, save_all=True, append_images=images[1:], duration=200 if filename != 'key-pose-preview.gif' else 400, loop=0, disposal=2)
    write_new(output / 'playback-geometry.json', {'status': 'pass', 'target_standing_height_px': target_height,
              'resolution_px': list(size), 'fixed_support_point_px': support,
              'scale_policy': 'One calibrated isotropic scale per source sheet; no individual pose fitting.',
              'note': 'Discrete key poses. Episode timing, clearance, airborne translation and continuous movement require scene review.',
              'frames': playback_records})
    return {'preview': local(root, output / 'pose-review.png'), 'motion_preview': local(root, output / 'key-pose-preview.gif'),
            'alignment_report': local(root, output / 'alignment-report.json')}


def register(root, config_path, reviewed=False, check_only=False):
    config_path = Path(config_path).resolve()
    config = read(config_path)
    items = config['items']
    if len(items) != len(TARGETS) or {item['id'] for item in items} != set(TARGETS):
        raise ValueError('Register exactly ten expansion characters, once each')
    index = read(root / INDEX)
    canonicals = {item['id']: item for item in index['characters']}
    checks = [validate_item(root, item, canonicals[item['id']], reviewed) for item in items]
    if check_only:
        return {'status': 'pass', 'characters': len(checks), 'frames': 270, 'mode': 'check-only'}
    if not reviewed:
        raise ValueError('Persistent expansion registration requires completed visual review')
    collection = root / COLLECTION
    if collection.exists():
        raise FileExistsError(f'Refusing to overwrite collection: {collection}')
    for check in checks:
        folder = root / 'assets/library/characters' / check['id'] / 'motions/v002'
        if (folder / 'registration.json').exists() or any((folder / (frame['id'] + '.png')).exists() for frame in check['frames']):
            raise FileExistsError(f'Refusing to overwrite registered frames: {folder}')
    # All source, provenance, coverage and annotations validate before writes.
    entries = []
    now = datetime.now(timezone.utc).isoformat()
    for check in checks:
        folder = root / 'assets/library/characters' / check['id'] / 'motions/v002'
        folder.mkdir(parents=True, exist_ok=True)
        for frame in check['frames']:
            destination = folder / (frame['id'] + '.png')
            frame['image'].save(destination)
            with Image.open(destination) as saved:
                if saved.mode != 'RGBA' or saved.tobytes() != frame['image'].tobytes():
                    raise ValueError('Lossless cell verification failed')
            frame.update(path=local(root, destination), sha256=sha(destination), exact_cell_pixel_match=True)
        preview = previews(root, check, folder)
        sheets = [{key: value for key, value in sheet.items() if key not in ('frames', 'path')} |
                  {'source_sheet': local(root, sheet['path']), 'source_sheet_sha256': sheet['details']['sha256']}
                  for sheet in check['sheets']]
        registration = {'schema_version': 2, 'kind': 'generated-character-multisheet-key-pose-stock',
            'character_id': check['id'], 'version': 'v002', 'created_at_utc': now,
            'status': 'stocked-and-assistant-reviewed', 'production_asset': False,
            'source_pixels_modified': False, 'neutral_original_modified': False,
            'canonical_neutral': check['canonical']['neutral'], 'sheets': sheets,
            'scale_policy': 'Each source sheet has one calibrated standing reference height shared by its nine poses. Never fit each posture to its bbox.',
            'frames': [{key: value for key, value in frame.items() if key != 'image'} for frame in check['frames']],
            'review': check['item']['review'], 'preview': preview,
            'pixel_processing': 'Lossless exact cell crops only. No repainting, alpha cleanup, contour edits or source rescaling.'}
        write_new(folder / 'registration.json', registration)
        entries.append({'id': check['id'], 'registration': local(root, folder / 'registration.json'),
                        'registration_sha256': sha(folder / 'registration.json'), 'frame_count': len(check['frames']), **preview})
    collection.mkdir(parents=True)
    write_new(collection / 'manifest.json', {'schema_version': 1, 'collection_id': 'character-expansion-v001',
              'kind': 'reviewed-character-expansion-collection', 'status': 'stocked-and-assistant-reviewed',
              'production_asset': False, 'active_productions_modified': False, 'neutral_originals_modified': False,
              'created_at_utc': now, 'items': entries, 'character_count': len(entries), 'pose_count': 270,
              'selection_policy': 'Explicit supplemental expansion; canonical neutrals and existing production selections remain unchanged.'})
    write_new(collection / 'registration-input.json', config)
    cards = []
    for entry in entries:
        # Compute actual relative paths instead of relying on folder depth.
        rel = Path(os.path.relpath(root / entry['registration'], collection)).parent.as_posix()
        cards.append(f'<article><h2>{html.escape(entry["id"])}</h2><p><a href="{rel}/pose-review.png">27 poses / light</a> · <a href="{rel}/pose-review-dark.png">dark</a> · <a href="{rel}/key-pose-preview.gif">playback</a> · <a href="{rel}/registration.json">registration</a></p><img src="{rel}/pose-review.png" alt="{html.escape(entry["id"])} new poses"></article>')
    markup = '<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Character expansion</title><style>body{max-width:1400px;margin:24px auto;padding:0 18px;background:#faf4e8;color:#63390d;font-family:system-ui}img{width:100%;height:auto}article{margin:30px 0}a{color:#28625e}</style><h1>キャラクター表情・動作拡充</h1><p>10種類 × 27枚。通常姿の参照と旧素材を保持した、新規生成の再利用素材です。</p><p><a href="manifest.json">Manifest</a> · <a href="registration-input.json">Reviewed geometry</a></p>' + ''.join(cards) + '</html>'
    with (collection / 'index.html').open('x', encoding='utf-8') as output:
        output.write(markup)
    return {'status': 'pass', 'characters': len(entries), 'frames': 270, 'collection': COLLECTION,
            'active_productions_modified': False, 'canonical_neutrals_modified': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('--character', required=True, choices=TARGETS)
    inspect.add_argument('--group', required=True, choices=GROUPS)
    inspect.add_argument('--sheet', type=Path, required=True)
    inspect.add_argument('--output', type=Path, required=True)
    registering = commands.add_parser('register')
    registering.add_argument('--config', type=Path, required=True)
    registering.add_argument('--reviewed', action='store_true')
    registering.add_argument('--check-only', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = inspect_sheet(args.character, args.group, args.sheet, args.output) if args.command == 'inspect' else register(args.root.resolve(), args.config, args.reviewed, args.check_only)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Character expansion error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
