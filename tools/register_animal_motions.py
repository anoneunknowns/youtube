"""Inspect and stock generated animal key poses without repainting source pixels.

`inspect` extracts exact grid cells into a scratch directory and emits a geometry
draft. `register` requires reviewed, hash-bound anatomical annotations for all
seven requested animals. Existing neutral art and active productions are read-only.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path
import tempfile

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
STOCK = ROOT / 'assets/library/collections/animal-stock/v001/manifest.json'
COLLECTION = ROOT / 'assets/library/collections/animal-motions/v001'
COLLECTION_ID = 'animal-motions-v001'
CATALOG = ROOT / 'catalogs/library-v1.json'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
NAMES = {
    'siamese-cat': ('シャム猫', 'Siamese Cat'),
    'red-panda': ('レッサーパンダ', 'Red Panda'),
    'meerkat': ('ミーアキャット', 'Meerkat'),
    'kangaroo': ('カンガルー', 'Kangaroo'),
    'hedgehog': ('ハリネズミ', 'Hedgehog'),
    'fairy-pitta': ('ヤイロチョウ', 'Fairy Pitta'),
    'onagadori': ('オナガドリ', 'Onagadori'),
}
MAMMAL_POSES = ['blink', 'greet', 'think', 'aha', 'cheer', 'species_action']
BIRD_POSES = ['blink', 'wing_half', 'wing_up', 'peck_half', 'peck_down', 'cheer']


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def local(path):
    return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()


def external_path(value, base):
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def project_path(value):
    path = external_path(value, ROOT)
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError(f'Project reference leaves the checkout: {value}')
    return path


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write('\n')


def copy_identical(source, destination):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        if not destination.is_file() or sha(source) != sha(destination):
            raise FileExistsError(f'Refusing to overwrite: {destination}')
    else:
        with destination.open('xb') as output:
            output.write(source.read_bytes())
    if sha(source) != sha(destination):
        raise ValueError(f'Copy verification failed: {destination}')


def poses_for(identity):
    return BIRD_POSES if identity in ('fairy-pitta', 'onagadori') else MAMMAL_POSES


def grid_for(identity):
    return {'columns': 2, 'rows': 3} if identity == 'onagadori' else {'columns': 3, 'rows': 2}


def box(value, size, label):
    if (not isinstance(value, list) or len(value) != 4
            or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in value)):
        raise ValueError(f'{label} needs finite [x0,y0,x1,y1]')
    result = [round(v) for v in value]
    if not 0 <= result[0] < result[2] <= size[0] or not 0 <= result[1] < result[3] <= size[1]:
        raise ValueError(f'{label} leaves its source cell: {result}/{size}')
    return result


def rgba_details(image):
    if image.mode != 'RGBA':
        raise ValueError('Generated original must be RGBA; no conversion is performed')
    alpha = image.getchannel('A')
    bbox = alpha.point(lambda a: 255 if a >= 8 else 0).getbbox()
    alpha_range = alpha.getextrema()
    if bbox is None or alpha_range[0] != 0 or alpha_range[1] < 240:
        raise ValueError('Missing complete subject or genuine transparent alpha')
    width, height = image.size
    margins = [bbox[0], bbox[1], width - bbox[2], height - bbox[3]]
    if min(margins) < 2:
        raise ValueError(f'Visible artwork reaches cell edge: {margins}; regenerate rather than masking')
    return {
        'size_px': [width, height], 'visible_bbox_px': list(bbox),
        'alpha_extrema': list(alpha_range), 'visible_alpha8_margins_px': margins,
        'transparent_fraction': alpha.histogram()[0] / (width * height),
        'rgba_pixel_sha256': hashlib.sha256(image.tobytes()).hexdigest(),
    }


def sheet_cells(sheet, identity, grid):
    if grid != grid_for(identity):
        raise ValueError(f'{identity} requires grid {grid_for(identity)}')
    with Image.open(sheet) as source:
        if source.format != 'PNG' or source.mode != 'RGBA':
            raise ValueError('Source sheet must be an actual RGBA PNG')
        details = rgba_details(source)
        width, height = source.size
        columns, rows = grid['columns'], grid['rows']
        cells = []
        for index, name in enumerate(poses_for(identity)):
            column, row = index % columns, index // columns
            region = [round(column * width / columns), round(row * height / rows),
                      round((column + 1) * width / columns), round((row + 1) * height / rows)]
            frame = source.crop(region)
            cells.append({'id': name, 'index': index, 'region_xyxy': region,
                          'image': frame, **rgba_details(frame)})
        return {'sha256': sha(sheet), **details}, cells


def inspect_sheet(identity, sheet, output):
    if identity not in NAMES:
        raise ValueError(f'Unknown animal: {identity}')
    sheet, output = Path(sheet).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(f'Use a new scratch inspection folder: {output}')
    metadata, cells = sheet_cells(sheet, identity, grid_for(identity))
    output.mkdir(parents=True)
    for cell in cells:
        destination = output / (cell['id'] + '.png')
        cell['image'].save(destination)
        with Image.open(destination) as saved:
            if saved.mode != 'RGBA' or saved.tobytes() != cell['image'].tobytes():
                raise ValueError(f'Exact crop verification failed: {destination}')
    write_new(output / 'inspection.json', {
        'id': identity, 'source_sheet': str(sheet), 'sheet': metadata,
        'grid': grid_for(identity), 'pixel_edits': False,
        'cells': [{k: v for k, v in cell.items() if k != 'image'} for cell in cells],
    })
    draft = {
        'id': identity, 'source_sheet_path': str(sheet), 'source_sheet_sha256': metadata['sha256'],
        'prompt_path': str(sheet.parent / 'generation-prompt.txt'),
        'generation_input_path': str(sheet.parent / 'generation-input.json'),
        'grid': grid_for(identity), 'common_reference_height_px': None,
        'review': {'identity': '', 'style': '', 'alpha': '', 'motion': ''},
        'poses': [{
            'id': cell['id'], 'index': cell['index'], 'body_bbox_px': None,
            'support_anchor_px': None,
            **({'tail_bbox_px': None} if identity == 'onagadori' else {}),
        } for cell in cells],
    }
    write_new(output / 'annotation-draft.json', draft)
    return {'status': 'pass', 'id': identity, 'frames': len(cells), 'output': str(output),
            'source_sheet_sha256': metadata['sha256'], 'source_pixels_modified': False}


def generation_references(provenance, neutral_path, extra_preserved=()):
    """Resolve a preserved edit chain without rewriting its historical raw paths."""
    chain, visited = [], set()

    def resolve(record, extras=()):
        mappings = [*record.get('preserved_input_references', []), *extras]
        resolved, found_neutral = [], False
        for reference in record.get('input_references', []):
            actual = external_path(reference['path'], ROOT)
            preserved = None
            if actual.is_relative_to(ROOT.resolve()):
                path = actual
            else:
                matches = [mapping for mapping in mappings
                           if external_path(mapping['original_path'], ROOT) == actual]
                if len(matches) != 1:
                    raise ValueError(f'External edit input needs one preserved project copy: {actual}')
                preserved = matches[0]
                path = project_path(preserved['path'])
                if not preserved.get('sha256') or preserved['sha256'] != sha(path):
                    raise ValueError(f'Preserved edit input hash mismatch: {path}')
                if actual.is_file() and sha(actual) != preserved['sha256']:
                    raise ValueError(f'Original and preserved edit input differ: {actual}')
            checksum = sha(path)
            if reference.get('sha256') and reference['sha256'] != checksum:
                raise ValueError(f'Generation reference changed: {path}')
            entry = {'role': reference['role'], 'path': local(path), 'sha256': checksum,
                     'original_input_path': reference['path']}
            if preserved:
                entry['preserved_input_reference'] = preserved
            resolved.append(entry)
            if entry['path'] == neutral_path:
                found_neutral = True
            elif path.name == 'source-sheet.png':
                ancestor = path.parent / 'generation-input.json'
                if ancestor.is_file() and ancestor not in visited:
                    visited.add(ancestor)
                    ancestral_refs, ancestral_neutral = resolve(read(ancestor))
                    chain.append({'generation_input': local(ancestor), 'sha256': sha(ancestor),
                                  'input_references': ancestral_refs})
                    found_neutral = found_neutral or ancestral_neutral
        return resolved, found_neutral

    references, found_neutral = resolve(provenance, extra_preserved)
    if not found_neutral:
        raise ValueError('Generation edit chain must resolve to the selected neutral original')
    return references, chain


def validate_item(item, base, neutral, reviewed):
    identity = item['id']
    sheet = external_path(item['source_sheet_path'], base)
    details, cells = sheet_cells(sheet, identity, item['grid'])
    if item.get('source_sheet_sha256') != details['sha256']:
        raise ValueError(f'Annotations are not bound to this exact sheet: {identity}')
    reference_height = item.get('common_reference_height_px')
    if (not isinstance(reference_height, (int, float)) or not math.isfinite(reference_height)
            or reference_height <= 0 or reference_height > cells[0]['size_px'][1]):
        raise ValueError(f'{identity} needs one valid standing reference height for all poses')
    if [pose.get('id') for pose in item['poses']] != poses_for(identity):
        raise ValueError(f'{identity} pose order differs from the agreed six-cell pack')
    prompt = external_path(item.get('prompt_path', str(sheet.parent / 'generation-prompt.txt')), base)
    generation = external_path(item.get('generation_input_path', str(sheet.parent / 'generation-input.json')), base)
    if not prompt.read_text(encoding='utf-8-sig').strip():
        raise ValueError(f'Missing exact prompt: {identity}')
    provenance = read(generation)
    references, ancestry = generation_references(provenance, neutral['neutral_path'], item.get('preserved_input_references', []))
    if provenance.get('exact_model_identifier_exposed') is False and provenance.get('model_id'):
        raise ValueError('Do not invent a model identifier that the built-in tool did not expose')
    notes = item.get('review', {})
    if reviewed and any(not notes.get(key) for key in ['identity', 'style', 'alpha', 'motion']):
        raise ValueError(f'{identity} needs identity/style/alpha/motion review notes')
    for cell, pose in zip(cells, item['poses'], strict=True):
        if pose.get('index') != cell['index']:
            raise ValueError(f'Pose index mismatch: {identity}/{cell["id"]}')
        body = box(pose.get('body_bbox_px'), cell['size_px'], f'{identity}/{cell["id"]} body')
        if cell['image'].getchannel('A').crop(body).getbbox() is None:
            raise ValueError('Body annotation contains no animal')
        anchor = pose.get('support_anchor_px')
        if (not isinstance(anchor, list) or len(anchor) != 2
                or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in anchor)
                or not 0 <= anchor[0] <= cell['size_px'][0]
                or not body[1] < anchor[1] <= min(cell['size_px'][1], body[3] + 3)
                or not body[0] <= anchor[0] <= body[2]):
            raise ValueError(f'{identity}/{cell["id"]} needs an anatomical foot/support anchor')
        cell['body_bbox_px'] = body
        cell['anchor_px'] = anchor
        tail = pose.get('tail_bbox_px')
        if identity == 'onagadori' and tail is None:
            raise ValueError('Each Onagadori pose requires separate body and tail annotations')
        cell['tail_bbox_px'] = box(tail, cell['size_px'], f'{identity} tail') if tail else None
        if cell['tail_bbox_px'] and cell['image'].getchannel('A').crop(cell['tail_bbox_px']).getextrema()[1] < 8:
            raise ValueError(f'{identity}/{cell["id"]} tail annotation contains no visible feathers')
        cell['review'] = pose.get('review', '')
    neutral_manifest = project_path(neutral['source_manifest_path'])
    if sha(neutral_manifest) != neutral['source_manifest_sha256'] or sha(project_path(neutral['neutral_path'])) != neutral['neutral_sha256']:
        raise ValueError(f'Selected neutral or its manifest changed: {identity}')
    return {'item': item, 'sheet': sheet, 'sheet_details': details, 'cells': cells,
            'prompt_path': prompt, 'generation_input_path': generation,
            'generation_input': provenance, 'references': references, 'generation_ancestry': ancestry, 'neutral': neutral,
            'common_reference_height_px': reference_height}


def preview_frames(check, folder):
    identity = check['item']['id']
    bird = identity in ('fairy-pitta', 'onagadori')
    target = 280 if bird else 430
    cell_w, cell_h = (1050, 440) if identity == 'onagadori' else (600, 560)
    baseline = cell_h - 25
    label = ImageFont.truetype(str(FONT), 24)
    small = ImageFont.truetype(str(FONT), 18)
    neutral = check['neutral']
    neutral_image = Image.open(project_path(neutral['neutral_path'])).copy()
    neutral_height = neutral['body_bbox_px'][3] - neutral['body_bbox_px'][1]
    poses = [('neutral', neutral_image, neutral['support_anchor_px'], target / neutral_height)]
    for cell in check['cells']:
        poses.append((cell['id'], cell['image'], cell['anchor_px'], target / check['common_reference_height_px']))
    images, dark = [], []
    for name, image, anchor, scale in poses:
        # Display compositing only; no derivative source PNG or alpha is altered.
        visible = image.getchannel('A').point(lambda a: 255 if a >= 8 else 0).getbbox()
        sprite = image.crop(visible)
        sprite = sprite.resize((round(sprite.width * scale), round(sprite.height * scale)), Image.Resampling.LANCZOS)
        x = round(cell_w * .43 - (anchor[0] - visible[0]) * scale)
        y = round(baseline - (anchor[1] - visible[1]) * scale)
        if not 0 <= x or not 0 <= y or x + sprite.width > cell_w or y + sprite.height > cell_h:
            raise ValueError(f'Review preview would clip {identity}/{name}; inspect annotation or expand preview cell')
        for backdrop, output in [('#fff8e8', images), ('#203b3e', dark)]:
            canvas = Image.new('RGBA', (cell_w, cell_h), backdrop)
            canvas.alpha_composite(sprite, (x, y))
            draw = ImageDraw.Draw(canvas)
            fill = '#713b12' if backdrop == '#fff8e8' else '#fff8e8'
            draw.text((15, 12), name, font=label, fill=fill)
            draw.text((15, 44), f'one scale / body {target}px', font=small, fill=fill)
            output.append(canvas.convert('RGB'))
    columns = 2 if identity == 'onagadori' else 3
    rows = math.ceil(len(images) / columns)
    for name, sources, backdrop in [('pose-review.png', images, '#fff8e8'), ('pose-review-dark.png', dark, '#203b3e')]:
        sheet = Image.new('RGB', (cell_w * columns, cell_h * rows), backdrop)
        for index, canvas in enumerate(sources):
            sheet.paste(canvas, ((index % columns) * cell_w, (index // columns) * cell_h))
        sheet.save(folder / name)
    # Key-pose playback is a stock review, not a claim of interpolated animation.
    sequence = ([0, 1, 0, 2, 3, 2, 0, 4, 5, 4, 0, 6, 0] if bird
                else [0, 1, 0, 2, 0, 3, 4, 0, 5, 0, 6, 0])
    durations = ([500, 150, 400, 140, 180, 140, 400, 180, 200, 180, 400, 600, 500] if bird
                 else [500, 150, 450, 500, 350, 500, 500, 350, 600, 350, 600, 600])
    frames = [images[index] for index in sequence]
    frames[0].save(folder / 'key-pose-preview.gif', save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, disposal=2)
    preview_files = ['pose-review.png', 'pose-review-dark.png', 'key-pose-preview.gif']
    if bird:
        for filename, sequence in [('flutter-preview.gif', [0, 2, 3, 2, 0]), ('peck-preview.gif', [0, 4, 5, 4, 0])]:
            frames = [images[index] for index in sequence]
            frames[0].save(folder / filename, save_all=True, append_images=frames[1:],
                           duration=[500, 140, 200, 140, 500], loop=0, disposal=2)
            preview_files.append(filename)
    return {'target_body_height_px': target, 'one_common_scale': target / check['common_reference_height_px'],
            'preview_files': preview_files,
            'playback_note': 'Discrete key-pose review only. Future video timing and any interpolation require episode-specific acceptance.'}


def add_catalog(catalog, entries, manifest_sha):
    result = copy.deepcopy(catalog)
    for entry in entries:
        key = entry['id'] + '-stock-motions-v001'
        if key in result['items']:
            raise FileExistsError(f'Catalog item already exists: {key}')
        result['items'][key] = {
            'kind': 'generated-character-key-pose-stock', 'version': 'v001',
            'status': 'stocked-and-assistant-reviewed', 'production_asset': False,
            'path': entry['registration'], 'sha256': entry['registration_sha256'],
            'reusable_across_episodes': True,
        }
    sets = result.setdefault('character_stock_sets', {})
    if COLLECTION_ID in sets:
        raise FileExistsError('Motion collection is already catalogued')
    sets[COLLECTION_ID] = {
        'status': 'stocked-and-assistant-reviewed', 'production_asset': False,
        'items': [entry['id'] + '-stock-motions-v001' for entry in entries],
        'manifest': local(COLLECTION / 'manifest.json'), 'sha256': manifest_sha,
        'index': local(COLLECTION / 'index.html'),
        'integration_policy': 'Reusable key poses with common scale and anatomical support; future production must review motion and scene clearance.',
    }
    for key, old in catalog.items():
        if key in ('items', 'character_stock_sets'):
            if any(result[key][identity] != value for identity, value in old.items()):
                raise ValueError(f'Existing catalog entries changed: {key}')
        elif result[key] != old:
            raise ValueError(f'Existing catalog field changed: {key}')
    return result


def preview_config(config_path, output):
    """Render geometry proposals in scratch before approving persistent stock."""
    config_path, output = Path(config_path).resolve(), Path(output).resolve()
    config = read(config_path)
    items = config['items']
    identities = [item['id'] for item in items]
    if not identities or len(set(identities)) != len(identities) or not set(identities) <= set(NAMES):
        raise ValueError('Preview needs one or more unique known animal ids')
    neutrals = {item['id']: item for item in read(STOCK)['items']}
    checks = [validate_item(item, config_path.parent, neutrals[item['id']], False) for item in items]
    if output.exists():
        raise FileExistsError(f'Use a new preview folder: {output}')
    output.mkdir(parents=True)
    previews = []
    for check in checks:
        folder = output / check['item']['id']
        folder.mkdir()
        previews.append({'id': check['item']['id'], **preview_frames(check, folder)})
    write_new(output / 'preview-input.json', config)
    write_new(output / 'preview-report.json', {'status': 'pass', 'scope': 'Scratch common-scale key-pose review; no stock/catalog write.', 'items': previews})
    return {'status': 'pass', 'animals': len(checks), 'output': str(output), 'stock_or_catalog_modified': False}


def gallery(entries):
    cards = []
    for entry in entries:
        folder = ROOT / entry['folder']
        relative = Path(os.path.relpath(folder, COLLECTION)).as_posix()
        ja, en = NAMES[entry['id']]
        extra_motion = (f' · <a href="{relative}/flutter-preview.gif">羽ばたき</a> · <a href="{relative}/peck-preview.gif">くちばしを下げる動作</a>'
                        if entry['id'] in ('fairy-pitta', 'onagadori') else '')
        cards.append(f'<article><h2>{html.escape(ja)} <small>{html.escape(en)}</small></h2>'
                     f'<a href="{relative}/pose-review.png"><img src="{relative}/pose-review.png" alt="{html.escape(ja)} poses"></a>'
                     f'<p><a href="{relative}/key-pose-preview.gif">動きの確認</a> · '
                     f'<a href="{relative}/pose-review-dark.png">暗背景</a> · '
                     f'<a href="{relative}/registration.json">登録情報</a>{extra_motion}</p>'
                     '<p>' + ' · '.join(f'<a href="{relative}/{name}.png">{name}</a>' for name in poses_for(entry['id'])) + '</p></article>')
    markup = '<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    markup += '<title>Animal key-pose stock</title><style>body{font-family:system-ui,sans-serif;background:#faf4e8;color:#63390d;margin:24px auto;max-width:1450px;padding:0 20px}article{background:#fffdf6;border:1px solid #d5c5ae;border-radius:18px;padding:20px;margin:22px 0}img{width:100%;height:auto}small{font-size:.6em;color:#36716b}a{color:#28625e}p{line-height:1.8}</style>'
    markup += '<h1>動物キャラクター 基本表情・動作素材</h1><p>採用した通常姿を基準にした各6ポーズの透過PNGです。画像をクリックすると原寸の比較図を開きます。</p>'
    markup += '<p><a href="manifest.json">素材台帳</a> · <a href="prompts.txt">生成プロンプト集</a></p><a href="overview.png"><img src="overview.png" alt="7種類の動作例"></a>' + ''.join(cards) + '</html>'
    with (COLLECTION / 'index.html').open('x', encoding='utf-8') as output:
        output.write(markup)


def overview(checks):
    """Seven signature examples at fixed body scales; a preview, never source art."""
    width, height = 1860, 1780
    canvas = Image.new('RGBA', (width, height), '#faf4e8')
    draw = ImageDraw.Draw(canvas)
    title = ImageFont.truetype(str(FONT), 38)
    label = ImageFont.truetype(str(FONT), 29)
    small = ImageFont.truetype(str(FONT), 21)
    draw.text((28, 18), 'Animal Character Motions', font=title, fill='#63390d')
    for index, check in enumerate(checks):
        identity = check['item']['id']
        if index < 6:
            x, y, card_w, card_h = 15 + (index % 3) * 615, 82 + (index // 3) * 610, 600, 590
        else:
            x, y, card_w, card_h = 15, 1310, 1830, 450
        draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=22, fill='#fffdf5', outline='#d5c5ae', width=2)
        bird = identity in ('fairy-pitta', 'onagadori')
        pose_id = 'wing_up' if bird else 'species_action'
        cell = next(cell for cell in check['cells'] if cell['id'] == pose_id)
        target = 280 if bird else 430
        scale = target / check['common_reference_height_px']
        visible = cell['visible_bbox_px']
        sprite = cell['image'].crop(visible)
        sprite = sprite.resize((round(sprite.width * scale), round(sprite.height * scale)), Image.Resampling.LANCZOS)
        sprite_x = x + (card_w - sprite.width) // 2
        sprite_y = round(y + card_h - 22 - (cell['anchor_px'][1] - visible[1]) * scale)
        if sprite_x < x or sprite_y < y + 80 or sprite_x + sprite.width > x + card_w or sprite_y + sprite.height > y + card_h:
            raise ValueError(f'Overview would clip {identity}; expand its preview card')
        canvas.alpha_composite(sprite, (sprite_x, sprite_y))
        draw.text((x + 20, y + 12), NAMES[identity][0], font=label, fill='#63390d')
        draw.text((x + 20, y + 51), f'{NAMES[identity][1]} / {pose_id}', font=small, fill='#36716b')
    canvas.convert('RGB').save(COLLECTION / 'overview.png')


def register(config_path, reviewed=False, update_catalog=False, check_only=False, snapshot_dir=None):
    config_path = Path(config_path).resolve()
    config = read(config_path)
    items = config['items']
    if len(items) != 7 or {item['id'] for item in items} != set(NAMES):
        raise ValueError('Register exactly seven requested species, once each')
    if update_catalog and not reviewed:
        raise ValueError('Catalog updates require completed visual/motion review')
    items = sorted(items, key=lambda item: list(NAMES).index(item['id']))
    stock = read(STOCK)
    neutrals = {item['id']: item for item in stock['items']}
    checks = [validate_item(item, config_path.parent, neutrals[item['id']], reviewed) for item in items]
    style_review = None
    if config.get('style_review_path'):
        style_review = external_path(config['style_review_path'], config_path.parent)
        if reviewed and read(style_review).get('status') != 'pass':
            raise ValueError('Overall series style review must pass before reviewed registration')
    if check_only:
        return {'status': 'pass', 'mode': 'check-only', 'animals': len(checks), 'exact_crops': 42,
                'source_pixels_modified': False}
    if COLLECTION.exists():
        raise FileExistsError(f'Refusing to overwrite collection: {COLLECTION}')
    for check in checks:
        folder = ROOT / 'assets/library/characters' / check['item']['id'] / 'motions/v001'
        if folder.exists():
            raise FileExistsError(f'Refusing to overwrite motion stock: {folder}')
    # Font validation and all semantic/pixel inspection precede persistent writes.
    ImageFont.truetype(str(FONT), 24)
    temp_base = Path('D:/temp') if Path('D:/').exists() else Path(tempfile.gettempdir())
    preview_root = Path(tempfile.mkdtemp(prefix='animal-motion-registration-preview-', dir=temp_base))
    preview_results = {}
    for check in checks:
        identity = check['item']['id']
        scratch = preview_root / identity
        scratch.mkdir()
        # Preflight all preview bounds before creating an immutable stock folder.
        preview_results[identity] = preview_frames(check, scratch)
    COLLECTION.mkdir(parents=True)
    style_record = None
    if style_review:
        evidence = COLLECTION / 'qa-evidence'
        evidence.mkdir()
        preserved_style_review = evidence / 'series-style-review.json'
        copy_identical(style_review, preserved_style_review)
        style_record = {'path': 'qa-evidence/series-style-review.json', 'sha256': sha(preserved_style_review)}
    now = datetime.now(timezone.utc).isoformat()
    entries, prompts = [], []
    for check in checks:
        item, identity = check['item'], check['item']['id']
        folder = ROOT / 'assets/library/characters' / identity / 'motions/v001'
        folder.mkdir(parents=True)
        copy_identical(check['sheet'], folder / 'source-sheet.png')
        copy_identical(check['prompt_path'], folder / 'generation-prompt.txt')
        copy_identical(check['generation_input_path'], folder / 'generation-input.json')
        frames = []
        for cell in check['cells']:
            target = folder / (cell['id'] + '.png')
            cell['image'].save(target)
            with Image.open(target) as saved:
                if saved.mode != 'RGBA' or saved.tobytes() != cell['image'].tobytes():
                    raise ValueError('Saved frame differs from exact source cell pixels')
            frames.append({
                'id': cell['id'], 'index': cell['index'], 'path': local(target), 'sha256': sha(target),
                'crop_from_sheet_xyxy': cell['region_xyxy'], 'size_px': cell['size_px'],
                'visible_bbox_px': cell['visible_bbox_px'], 'body_bbox_px': cell['body_bbox_px'],
                'tail_bbox_px': cell['tail_bbox_px'], 'anchor_px': cell['anchor_px'],
                'reference_height_px': check['common_reference_height_px'],
                'visible_alpha8_margins_px': cell['visible_alpha8_margins_px'],
                'rgba_pixel_sha256': cell['rgba_pixel_sha256'], 'exact_cell_pixel_match': True,
                'review': cell['review'],
                **({'foot_roi_px': item['poses'][cell['index']]['foot_roi_px']}
                   if item['poses'][cell['index']].get('foot_roi_px') else {}),
            })
        preview = preview_results[identity]
        for name in preview['preview_files']:
            copy_identical(preview_root / identity / name, folder / name)
        registration = {
            'schema_version': 1, 'kind': 'generated-character-key-pose-stock', 'character_id': identity,
            'version': 'v001', 'created_at_utc': now,
            'status': 'stocked-and-assistant-reviewed' if reviewed else 'stocked-pending-review',
            'production_asset': False, 'source_pixels_modified': False,
            'source_sheet': local(folder / 'source-sheet.png'), 'source_sheet_sha256': check['sheet_details']['sha256'],
            'neutral_manifest': check['neutral']['source_manifest_path'],
            'neutral_sha256': check['neutral']['neutral_sha256'],
            'grid': item['grid'], 'common_reference_height_px': check['common_reference_height_px'],
            'scale_policy': 'One isotropic art scale for every pose, including crouch/peck. Never fit each pose to its own visible bounding box. Long tail extent is excluded from body calibration.',
            'support_policy': 'Anatomical foot-center/ground support is annotated per cell. Full tail pixels remain unchanged.',
            'source_sheet_details': check['sheet_details'], 'frames': frames, 'preview': preview,
            'review': item['review'], 'generation_input': 'generation-input.json',
            'measurement_notes': item.get('measurement_notes', []),
            'generation_prompt': 'generation-prompt.txt', 'generation_references': check['references'],
            'generation_ancestry': check['generation_ancestry'],
            'pixel_processing': 'Lossless exact cell extraction only; no creative painting, contour processing, alpha cleanup or per-pose scaling.',
        }
        write_new(folder / 'registration.json', registration)
        entry = {
            'id': identity, 'name_ja': NAMES[identity][0], 'folder': local(folder),
            'registration': local(folder / 'registration.json'), 'registration_sha256': sha(folder / 'registration.json'),
            'poses': poses_for(identity), 'preview': local(folder / 'pose-review.png'),
            'motion_preview': local(folder / 'key-pose-preview.gif'),
        }
        entries.append(entry)
        prompts.append('[' + identity + ']\n' + check['prompt_path'].read_text(encoding='utf-8-sig') + '\n')
    with (COLLECTION / 'prompts.txt').open('x', encoding='utf-8') as output:
        output.write('\n'.join(prompts))
    gallery(entries)
    overview(checks)
    manifest = {
        'schema_version': 1, 'kind': 'animal-key-pose-stock-collection', 'collection_id': COLLECTION_ID,
        'created_at_utc': now, 'status': 'stocked-and-assistant-reviewed' if reviewed else 'stocked-pending-review',
        'production_asset': False, 'active_productions_modified': False, 'neutral_originals_modified': False,
        'items': entries, 'source_stock': local(STOCK), 'source_stock_sha256': sha(STOCK),
        'index': 'index.html', 'overview': 'overview.png', 'prompts': 'prompts.txt', 'pose_count': 42,
        'style_review': style_record,
        'future_production_policy': 'Ready as reusable reviewed key poses. Each actual episode still reviews timing, scene clearance and any continuous motion in its intended composition.',
    }
    write_new(COLLECTION / 'manifest.json', manifest)
    write_new(COLLECTION / 'registration-input.json', config)
    write_new(COLLECTION / 'qa.json', {
        'status': 'pass', 'scope': 'Exact sheet/cell bytes, alpha/bounds, hash-bound geometry, common scale and required review notes.',
        'source_png_pixels_repainted': False, 'per_pose_rescaling_applied': False,
        'animals': 7, 'frames': 42, 'items': [{'id': check['item']['id'], 'sheet_sha256': check['sheet_details']['sha256']} for check in checks],
    })
    catalog_snapshot = None
    if update_catalog:
        before_bytes = CATALOG.read_bytes()
        before = json.loads(before_bytes.decode('utf-8-sig'))
        result = add_catalog(before, entries, sha(COLLECTION / 'manifest.json'))
        snapshots = Path(snapshot_dir) if snapshot_dir else Path('D:/temp/animal-stock-expansion-20261111/catalog-snapshots')
        snapshots.mkdir(parents=True, exist_ok=True)
        catalog_snapshot = snapshots / ('library-before-animal-motions-' + hashlib.sha256(before_bytes).hexdigest()[:16] + '.json')
        if catalog_snapshot.exists():
            if catalog_snapshot.read_bytes() != before_bytes:
                raise ValueError('Existing catalog snapshot differs')
        else:
            with catalog_snapshot.open('xb') as output:
                output.write(before_bytes)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n', suffix='.tmp',
                                         prefix='animal-motions-', dir=CATALOG.parent, delete=False) as output:
            json.dump(result, output, ensure_ascii=False, indent=2)
            output.write('\n')
            pending = Path(output.name)
        if CATALOG.read_bytes() != before_bytes:
            pending.unlink()
            raise ValueError('Catalog changed concurrently; motion stock saved, catalog unchanged')
        pending.replace(CATALOG)
        if read(CATALOG) != result:
            raise ValueError('Catalog changed immediately after registration; inspect concurrent work')
    return {'status': 'pass', 'collection': local(COLLECTION), 'animals': 7, 'frames': 42,
            'catalog_updated': update_catalog, 'catalog_snapshot': str(catalog_snapshot) if catalog_snapshot else None,
            'neutral_originals_modified': False, 'active_productions_modified': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('--id', required=True, choices=NAMES)
    inspect.add_argument('--sheet', required=True, type=Path)
    inspect.add_argument('--output', required=True, type=Path)
    preview = commands.add_parser('preview')
    preview.add_argument('--config', required=True, type=Path)
    preview.add_argument('--output', required=True, type=Path)
    stock = commands.add_parser('register')
    stock.add_argument('--config', required=True, type=Path)
    stock.add_argument('--check-only', action='store_true')
    stock.add_argument('--reviewed', action='store_true')
    stock.add_argument('--update-catalog', action='store_true')
    stock.add_argument('--snapshot-dir', type=Path)
    args = parser.parse_args(argv)
    if args.command == 'inspect':
        result = inspect_sheet(args.id, args.sheet, args.output)
    elif args.command == 'preview':
        result = preview_config(args.config, args.output)
    else:
        result = register(args.config, args.reviewed, args.update_catalog, args.check_only, args.snapshot_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
