"""Register seven reviewed transparent animal originals without editing pixels.

Input JSON paths for source images/research are absolute or relative to the
configuration file. Style-reference paths are project-relative. Body/support
annotations are measured in source-canvas pixels, not thumbnail coordinates.
No existing production or original character is modified.
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
import re
import tempfile

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SPECIES = {
    'siamese-cat': ('シャム猫', 'Siamese Cat'),
    'red-panda': ('レッサーパンダ', 'Red Panda'),
    'meerkat': ('ミーアキャット', 'Meerkat'),
    'kangaroo': ('カンガルー', 'Kangaroo'),
    'hedgehog': ('ハリネズミ', 'Hedgehog'),
    'fairy-pitta': ('ヤイロチョウ', 'Fairy Pitta'),
    'onagadori': ('オナガドリ', 'Onagadori'),
}
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
COLLECTION = Path('assets/library/collections/animal-stock/v001')
COLLECTION_ID = 'animal-stock-v001'
CATALOG_PATH = ROOT / 'catalogs/library-v1.json'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def local(path):
    return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()


def write_new(path, value):
    path = Path(path)
    with path.open('x', encoding='utf-8', newline='\n') as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write('\n')


def copy_new_or_identical(source, target):
    source, target = Path(source), Path(target)
    if target.exists():
        if not target.is_file() or digest(source) != digest(target):
            raise FileExistsError(f'Refusing to replace existing artwork: {target}')
        return
    with target.open('xb') as output:
        output.write(source.read_bytes())
    if digest(source) != digest(target):
        raise ValueError(f'Copy verification failed: {target}')


def source_path(value, config_dir):
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (config_dir / path).resolve()


def source_folder(item):
    version = item.get('source_version', 'v001')
    if not isinstance(version, str) or not re.fullmatch(r'v\d{3,}', version):
        raise ValueError(f'Use an explicit immutable source_version such as v001/v002: {version}')
    return ROOT / 'assets/library/characters' / item['id'] / 'sources' / version


def project_path(value):
    path = Path(value)
    result = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    if not result.is_relative_to(ROOT.resolve()):
        raise ValueError(f'Project reference leaves this checkout: {value}')
    return result


def rectangle(value, width, height, label):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f'{label} needs [x0,y0,x1,y1]')
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise ValueError(f'{label} coordinates must be finite')
    box = tuple(round(v) for v in value)
    if not 0 <= box[0] < box[2] <= width or not 0 <= box[1] < box[3] <= height:
        raise ValueError(f'{label} leaves the source canvas: {box}')
    return box


def inspect(item, config_dir, reviewed):
    identity = item['id']
    source_folder(item)
    source = source_path(item['source_path'], config_dir)
    if not source.is_file():
        raise FileNotFoundError(source)
    source_checksum = digest(source)
    annotation_checksum = item.get('annotation_source_sha256')
    if annotation_checksum and annotation_checksum != source_checksum:
        raise ValueError(f'Body/support annotations belong to a different source revision: {identity}')
    if reviewed and not annotation_checksum:
        raise ValueError(f'{identity} reviewed geometry needs annotation_source_sha256 for this exact PNG')
    if reviewed and 'body_bbox_px' not in item:
        raise ValueError(f'{identity} reviewed stock needs an explicit anatomical body_bbox_px')
    prompt = item.get('prompt')
    prompt_path = source_path(item['prompt_path'], config_dir) if item.get('prompt_path') else source.parent / 'generation-prompt.txt'
    if not prompt and prompt_path.is_file():
        prompt = prompt_path.read_text(encoding='utf-8-sig')
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError(f'Exact generation prompt is missing for {identity}')
    if prompt_path.is_file() and prompt.strip() != prompt_path.read_text(encoding='utf-8-sig').strip():
        raise ValueError(f'Provided prompt differs from preserved generation-prompt.txt: {identity}')
    sidecar_path = source_path(item['generation_input_path'], config_dir) if item.get('generation_input_path') else source.parent / 'generation-input.json'
    sidecar = read(sidecar_path) if sidecar_path.is_file() else {}
    supplied_generation = item.get('generation', {})
    intent = supplied_generation.get('intent', sidecar.get('intent', 'generate'))
    if sidecar.get('intent') and supplied_generation.get('intent') and sidecar['intent'] != supplied_generation['intent']:
        raise ValueError(f'Generation intent disagrees with preserved generation-input.json: {identity}')
    if intent not in ('generate', 'edit'):
        raise ValueError(f'{identity} generation.intent must be generate or edit')
    if sidecar.get('exact_model_identifier_exposed') is False and supplied_generation.get('model_id') is not None:
        raise ValueError(f'The actual built-in model identifier was not exposed for {identity}; use requested_model for a preference')
    input_references = []
    actual_references = item.get('input_references') or sidecar.get('input_references', [])
    if item.get('input_references') and sidecar.get('input_references'):
        declared = [(ref['role'], project_path(ref['path'])) for ref in item['input_references']]
        recorded = [(ref['role'], project_path(ref['path'])) for ref in sidecar['input_references']]
        if declared != recorded:
            raise ValueError(f'Input references disagree with preserved generation-input.json: {identity}')
    for reference in actual_references:
        path = project_path(reference['path'])
        checksum = digest(path)
        if reference.get('sha256') and reference['sha256'] != checksum:
            raise ValueError(f'Input reference changed: {path}')
        input_references.append({'role': reference['role'], 'path': local(path), 'sha256': checksum})
    if intent == 'edit' and not any(ref['role'] == 'edit-target' for ref in input_references):
        raise ValueError(f'Edited source needs a preserved edit-target reference: {identity}')
    with Image.open(source) as image:
        if image.format != 'PNG' or image.mode != 'RGBA':
            raise ValueError(f'Original must be a true RGBA PNG; no conversion is performed: {source}')
        alpha = image.getchannel('A')
        width, height = image.size
        histogram = alpha.histogram()
        visible = alpha.point(lambda a: 255 if a >= 8 else 0).getbbox()
        nonzero = alpha.getbbox()
        if visible is None or alpha.getextrema() != (0, 255) or histogram[0] / (width * height) < .01:
            raise ValueError(f'Missing subject or genuine transparent canvas: {source}')
        if min(visible[0], visible[1], width - visible[2], height - visible[3]) < 1:
            raise ValueError(f'Visible subject touches a canvas edge; review cropping first: {source}')
        body = rectangle(item.get('body_bbox_px', list(visible)), width, height, f'{identity} body bbox')
        if alpha.crop(body).getbbox() is None:
            raise ValueError(f'Body bbox contains no character: {identity}')
        anchor = item.get('support_anchor_px')
        if (not isinstance(anchor, list) or len(anchor) != 2
                or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in anchor)):
            raise ValueError(f'{identity} needs a measured support_anchor_px [foot-center-x,foot-baseline-y]')
        if not body[0] <= anchor[0] <= body[2] or not body[1] < anchor[1] <= min(height, body[3] + 3):
            raise ValueError(f'Support anchor is outside the body/support bounds: {identity}')
        tail = item.get('tail_bbox_px')
        if identity == 'onagadori' and (tail is None or 'body_bbox_px' not in item):
            raise ValueError('Onagadori requires separate measured body_bbox_px and tail_bbox_px')
        tail = rectangle(tail, width, height, f'{identity} tail bbox') if tail else None
        if tail is not None and alpha.crop(tail).getbbox() is None:
            raise ValueError(f'Tail bbox contains no feather/tail: {identity}')
    review = item.get('review', {})
    if reviewed and (not review.get('anatomy') or not review.get('style') or not review.get('alpha')):
        raise ValueError(f'{identity} needs explicit anatomy, style and alpha review notes before reviewed registration')
    margin = [visible[0], visible[1], width - visible[2], height - visible[3]]
    return {
        'source': source, 'sha256': source_checksum, 'size_px': [width, height],
        'prompt': prompt, 'prompt_path': str(prompt_path) if prompt_path.is_file() else None,
        'intent': intent, 'input_references': input_references,
        'generation_input_path': str(sidecar_path) if sidecar_path.is_file() else None,
        'generation_input_sha256': digest(sidecar_path) if sidecar_path.is_file() else None,
        'generation_input': sidecar,
        'visible_bbox_px': list(visible), 'alpha_nonzero_bbox_px': list(nonzero),
        'body_bbox_px': list(body), 'support_anchor_px': anchor,
        'reference_body_height_px': body[3] - body[1],
        'tail_bbox_px': list(tail) if tail else None,
        'alpha_extrema': [0, 255], 'fully_transparent_fraction': histogram[0] / (width * height),
        'visible_alpha8_margins_px': margin,
        'nonzero_alpha_margins_px': [nonzero[0], nonzero[1], width - nonzero[2], height - nonzero[3]],
        'warnings': ['transparent margin below 16 pixels; inspect the uncropped source'] if min(margin) < 16 else [],
    }


def preview_source(path, bounds, size):
    with Image.open(path) as source:
        sprite = source.crop(bounds)
        ratio = min(size[0] / sprite.width, size[1] / sprite.height, 1)
        return sprite.resize((round(sprite.width * ratio), round(sprite.height * ratio)), Image.Resampling.LANCZOS)


def fixed_body_preview(entry):
    target_height = 280 if entry['id'] in ('fairy-pitta', 'onagadori') else 430
    body = entry['body_bbox_px']
    scale = target_height / (body[3] - body[1])
    if scale > 1:
        raise ValueError(f'Stock source is too small for the fixed-body review size: {entry["id"]}')
    with Image.open(ROOT / entry['neutral_path']) as source:
        bounds = entry['visible_bbox_px']
        crop = (max(0, bounds[0] - 8), max(0, bounds[1] - 8),
                min(source.width, bounds[2] + 8), min(source.height, bounds[3] + 8))
        sprite = source.crop(crop)
        sprite = sprite.resize((round(sprite.width * scale), round(sprite.height * scale)), Image.Resampling.LANCZOS)
    anchor = entry['support_anchor_px']
    return sprite, ((anchor[0] - crop[0]) * scale, (anchor[1] - crop[1]) * scale), scale, target_height


def contact_sheet(entries, collection):
    # This is a labelled preview only; original art and its alpha are not edited.
    previews = [fixed_body_preview(entry) for entry in entries]
    card_w = max(600, max(sprite.width + 44 for sprite, _, _, _ in previews[:6]))
    width = card_w * 3 + 60
    card_h = max(620, max(sprite.height + 130 for sprite, _, _, _ in previews[:6]))
    last_h = max(445, previews[6][0].height + 130)
    last_y = 82 + 2 * (card_h + 20)
    canvas = Image.new('RGBA', (width, last_y + last_h + 20), '#faf4e8')
    draw = ImageDraw.Draw(canvas)
    title_font, label_font, english_font = [ImageFont.truetype(str(FONT), size) for size in (38, 31, 24)]
    draw.text((30, 18), 'Animal Character Stock', fill='#63390d', font=title_font)
    layout = []
    for index, (entry, preview) in enumerate(zip(entries, previews, strict=True)):
        identity = entry['id']
        if index < 6:
            x, y, w, h = 15 + (index % 3) * (card_w + 15), 82 + (index // 3) * (card_h + 20), card_w, card_h
        else:
            x, y, w, h = 15, last_y, width - 30, last_h
        draw.rounded_rectangle((x, y, x + w, y + h), radius=22, fill='#fffdf5', outline='#d5c5ae', width=2)
        ja, en = SPECIES[identity]
        draw.text((x + 22, y + 14), ja, fill='#63390d', font=label_font)
        draw.text((x + 22, y + 55), en, fill='#36716b', font=english_font)
        sprite, source_anchor, scale, body_height = preview
        position_x = x + (w - sprite.width) // 2
        support_y = y + h - 28 - max(0, sprite.height - source_anchor[1])
        position_y = round(support_y - source_anchor[1])
        if position_y < y + 98 or position_x < x + 18 or position_x + sprite.width > x + w - 18:
            raise ValueError(f'Fixed-body preview does not fit without clipping: {identity}')
        canvas.alpha_composite(sprite, (position_x, position_y))
        layout.append({'id': identity, 'body_height_px': body_height, 'source_scale': scale,
                       'support_anchor_px_on_sheet': [position_x + source_anchor[0], support_y],
                       'sprite_bounds_px_on_sheet': [position_x, position_y, position_x + sprite.width, position_y + sprite.height],
                       'tail_footprint_fit_applied': False})
    canvas.convert('RGB').save(collection / 'contact-sheet.png')
    # Three backgrounds expose matte fragments without changing the stock PNG.
    thumb_w, thumb_h, left = 340, 350, 310
    diagnostic = Image.new('RGB', (left + thumb_w * 3, thumb_h * 7 + 64), '#e9dfd0')
    d = ImageDraw.Draw(diagnostic)
    for column, (name, color) in enumerate([('WHITE', '#ffffff'), ('CREAM', '#fff8e8'), ('DARK', '#20383c')]):
        d.text((left + column * thumb_w + 20, 15), name, font=english_font, fill='#63390d')
        for index, entry in enumerate(entries):
            x, y = left + column * thumb_w, 64 + index * thumb_h
            patch = Image.new('RGBA', (thumb_w, thumb_h), color)
            sprite = preview_source(ROOT / entry['neutral_path'], entry['alpha_nonzero_bbox_px'], (thumb_w - 24, thumb_h - 28))
            patch.alpha_composite(sprite, ((thumb_w - sprite.width) // 2, (thumb_h - sprite.height) // 2))
            diagnostic.paste(patch.convert('RGB'), (x, y))
    for index, entry in enumerate(entries):
        ja, en = SPECIES[entry['id']]
        d.text((14, 80 + index * thumb_h), ja, font=label_font, fill='#63390d')
        d.text((14, 125 + index * thumb_h), en, font=english_font, fill='#36716b')
    diagnostic.save(collection / 'alpha-review.png')
    return {'primary_overview': 'Fixed anatomical body height: mammals430px, birds280px. Cards expand to preserve full tails; no tail-footprint scale fitting.',
            'alpha_review': 'Small footprint-fit diagnostics only, not a body-scale or line-width comparison.', 'items': layout}


def stock_index(entries, collection, has_research):
    cards = []
    for entry in entries:
        identity = entry['id']
        ja, en = SPECIES[identity]
        image = html.escape(Path(os.path.relpath(ROOT / entry['neutral_path'], collection)).as_posix(), quote=True)
        metadata = html.escape(Path(os.path.relpath(ROOT / entry['source_manifest_path'], collection)).as_posix(), quote=True)
        kind = 'card wide' if identity == 'onagadori' else 'card'
        cards.append(f'<article class="{kind}"><h2>{html.escape(ja)} <small>{html.escape(en)}</small></h2>'
                     f'<p class="version">採用版：{html.escape(entry["source_version"])}</p>'
                     f'<a class="art" href="{image}"><img src="{image}" alt="{html.escape(ja)}の透過素材" loading="lazy"></a>'
                     f'<p class="links"><a href="{image}">透過PNGを原寸で開く</a> <a href="{metadata}">source-manifest.json</a></p></article>')
    research_link = ' · <a href="research.json">種の資料・公式URL</a>' if has_research else ''
    document = ('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>動物キャラクターストック — Num-Num Numbers</title><style>'
                '*{box-sizing:border-box}body{margin:0;background:#f6efdf;color:#523414;font-family:system-ui,"Yu Gothic",sans-serif;line-height:1.65}'
                'main{max-width:1500px;margin:auto;padding:24px}h1{line-height:1.3;font-size:clamp(25px,4vw,38px)}'
                'a{color:#205b57;text-underline-offset:3px}nav{margin:18px 0}.overview{width:100%;height:auto;border-radius:18px;background:#fff8e8}'
                '.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:20px;margin-top:28px}'
                '.card{border:1px solid #cfb897;border-radius:18px;overflow:hidden;background:#fffaf0;padding:18px}'
                '.card h2{font-size:23px;line-height:1.4;margin:0}.card small{display:block;font-size:16px;font-weight:500;color:#3c6661}'
                '.version{margin:5px 0 14px;font-weight:650}.art{display:flex;align-items:center;justify-content:center;min-height:330px;'
                'background-color:#fff;background-image:linear-gradient(45deg,#e5e1d9 25%,transparent 25%),linear-gradient(-45deg,#e5e1d9 25%,transparent 25%),'
                'linear-gradient(45deg,transparent 75%,#e5e1d9 75%),linear-gradient(-45deg,transparent 75%,#e5e1d9 75%);'
                'background-size:24px 24px;background-position:0 0,0 12px,12px -12px,-12px 0;border-radius:10px}'
                '.art img{display:block;max-width:100%;height:330px;object-fit:contain}.wide{grid-column:1/-1}.wide .art img{height:420px;max-height:65vh}'
                '.links{display:flex;gap:18px;flex-wrap:wrap;margin:14px 0 0}.note{font-size:14px;color:#6c5d48}</style>'
                '<main><h1>動物キャラクターストック</h1><p>7種類の通常姿・透過PNG。各カードに最終採用版を明記しています。</p>'
                '<p class="note">動画への組込み前のストックです。実際の配置・輪郭線・動作は作品ごとに確認します。市松模様はこの閲覧ページの背景で、PNGへ焼き込まれていません。</p>'
                f'<nav><a href="manifest.json">コレクション一覧</a> · <a href="prompts.txt">生成プロンプト</a>{research_link} · <a href="qa.json">登録検査</a></nav>'
                '<h2>固定体格での一覧</h2><p class="note">哺乳類の身体高430px、鳥280px。長い尾に合わせて身体を縮めていません。</p>'
                '<a href="contact-sheet.png"><img class="overview" src="contact-sheet.png" alt="7種類の採用版一覧"></a>'
                f'<section class="grid">{"".join(cards)}</section></main></html>')
    with (collection / 'index.html').open('x', encoding='utf-8', newline='\n') as output:
        output.write(document)
        output.write('\n')


def catalog_additions(catalog, entries, collection, collection_hash):
    result = copy.deepcopy(catalog)
    for entry in entries:
        key = f'{entry["id"]}-stock-source-{entry["source_version"]}'
        if key in result['items']:
            raise FileExistsError(f'Catalog stock item already exists: {key}')
        result['items'][key] = {
            'kind': 'generated-character-stock-bundle', 'version': entry['source_version'],
            'status': entry['status'], 'production_asset': False, 'reusable_across_episodes': True,
            'path': entry['source_manifest_path'], 'sha256': entry['source_manifest_sha256'],
            'new_art_generated': True,
        }
    sets = result.setdefault('character_stock_sets', {})
    if COLLECTION_ID in sets:
        raise FileExistsError(f'Catalog collection already exists: {COLLECTION_ID}')
    sets[COLLECTION_ID] = {
        'status': 'stocked-and-assistant-reviewed', 'production_asset': False,
        'items': [f'{entry["id"]}-stock-source-{entry["source_version"]}' for entry in entries],
        'manifest': local(collection / 'manifest.json'), 'sha256': collection_hash,
        'preview': local(collection / 'contact-sheet.png'),
        'integration_policy': 'Reusable neutral originals only; each future production must review scale, outline, support and any motion separately.',
    }
    # Assert every old object/value and every active-production/reference ID stays intact.
    for key, value in catalog.items():
        if key in ('items', 'character_stock_sets'):
            for old_id, old_value in value.items():
                if result[key][old_id] != old_value:
                    raise ValueError(f'Existing catalog object changed: {key}/{old_id}')
        elif result[key] != value:
            raise ValueError(f'Existing catalog field changed: {key}')
    return result


def register(config_path, reviewed=False, update_catalog=False, check_only=False, snapshot_dir=None):
    config_path = Path(config_path).resolve()
    config = read(config_path)
    items = config['items']
    if len(items) != 7 or {item['id'] for item in items} != set(SPECIES):
        raise ValueError('Exactly the seven requested identities must be registered once each')
    items = sorted(items, key=lambda item: list(SPECIES).index(item['id']))
    inspections = [inspect(item, config_path.parent, reviewed) for item in items]
    if len({check['sha256'] for check in inspections}) != 7:
        raise ValueError('Distinct animal identities must not map to identical original PNG files')
    references = []
    for reference in config.get('style_references', []):
        path = project_path(reference['path'])
        checksum = digest(path)
        if reference.get('sha256') and reference['sha256'] != checksum:
            raise ValueError(f'Style reference changed: {path}')
        references.append({'role': reference.get('role', 'style-reference-only'), 'path': local(path), 'sha256': checksum})
    if not references:
        raise ValueError('Project-local style reference paths/hashes must be recorded')
    if update_catalog and not reviewed:
        raise ValueError('Catalog update requires explicit --reviewed and seven image review notes')
    research = None
    research_reference = None
    if config.get('research_path'):
        research = source_path(config['research_path'], config_path.parent)
        read(research)
        checksum = digest(research)
        if config.get('research_sha256') and config['research_sha256'] != checksum:
            raise ValueError('Species research JSON changed after the registration config was prepared')
        research_reference = {'source_path': str(research), 'sha256': checksum, 'transfer': 'Factual JSON/official URLs only; no external photographs.'}
    if check_only:
        return {'status': 'pass', 'mode': 'check-only', 'identities': [item['id'] for item in items],
                'files_checked': 7, 'style_references': references, 'research': research_reference,
                'warnings': {item['id']: check['warnings'] for item, check in zip(items, inspections, strict=True)}}
    collection = ROOT / COLLECTION
    if collection.exists():
        raise FileExistsError(f'Refusing to overwrite an existing stock collection: {collection}')
    ImageFont.truetype(str(FONT), 24)
    for item, check in zip(items, inspections, strict=True):
        folder = source_folder(item)
        if any((folder / name).exists() for name in ['source-manifest.json', 'generation-record.json', 'README.txt']):
            raise FileExistsError(f'Stock identity is already registered: {folder}')
        for name in ['neutral.png', 'generation-original.png']:
            candidate = folder / name
            if candidate.exists() and (not candidate.is_file() or digest(candidate) != check['sha256']):
                raise FileExistsError(f'Refusing to replace different existing artwork: {candidate}')
    catalog_before_bytes = CATALOG_PATH.read_bytes()
    catalog_before = json.loads(catalog_before_bytes.decode('utf-8-sig'))
    if update_catalog:
        for item in items:
            key = f'{item["id"]}-stock-source-{source_folder(item).name}'
            if key in catalog_before['items']:
                raise FileExistsError(f'Catalog stock item already exists: {key}')
        if COLLECTION_ID in catalog_before.get('character_stock_sets', {}):
            raise FileExistsError(f'Catalog collection already exists: {COLLECTION_ID}')
    now = datetime.now(timezone.utc).isoformat()
    entries = []
    prompts = []
    collection.mkdir(parents=True, exist_ok=False)
    for item, check in zip(items, inspections, strict=True):
        identity = item['id']
        folder = source_folder(item)
        folder.mkdir(parents=True, exist_ok=True)
        neutral, original = folder / 'neutral.png', folder / 'generation-original.png'
        copy_new_or_identical(check['source'], neutral)
        copy_new_or_identical(check['source'], original)
        generation = {
            'schema_version': 1, 'provider': 'built-in-image-gen',
            'model_id': item.get('generation', {}).get('model_id'),
            'created_at_utc': now, 'intent': check['intent'],
            'prompt': check['prompt'], 'style_references': references,
            'origin_path': str(check['source']), 'original_sha256': check['sha256'],
            'source_pixels_modified': False, 'alpha_processing': 'Original generated alpha retained without color key, erosion or repainting.',
        }
        extras = item.get('generation', {})
        for key in ['tool_request_id', 'output_hint', 'requested_model']:
            if key in extras:
                generation[key] = extras[key]
        generation['input_references'] = check['input_references']
        generation['exact_model_identifier_exposed'] = check['generation_input'].get('exact_model_identifier_exposed', False)
        generation['original_generated_file_provenance'] = check['generation_input'].get('original_generated_file')
        if check['generation_input_path']:
            sidecar_target = folder / 'generation-input.json'
            copy_new_or_identical(check['generation_input_path'], sidecar_target)
            generation['preserved_generation_input'] = {'path': 'generation-input.json', 'sha256': digest(sidecar_target)}
        if not (folder / 'generation-prompt.txt').exists():
            with (folder / 'generation-prompt.txt').open('x', encoding='utf-8', newline='\n') as output:
                output.write(check['prompt'])
        write_new(folder / 'generation-record.json', generation)
        status = 'stocked-and-assistant-reviewed' if reviewed else 'stocked-pending-visual-review'
        manifest = {
            'schema_version': 1, 'kind': 'generated-character-stock-bundle', 'character_id': identity,
            'source_version': folder.name,
            'display_name': SPECIES[identity][1], 'japanese_name': SPECIES[identity][0],
            'status': status, 'new_art_generated': True, 'source_pixels_modified': False,
            'production_asset': False, 'reusable_across_episodes': True,
            'render_registration': {
                'neutral_path': 'neutral.png', 'neutral_sha256': check['sha256'], 'size_px': check['size_px'],
                'neutral_visible_bbox_px': check['visible_bbox_px'], 'alpha_nonzero_bbox_px': check['alpha_nonzero_bbox_px'],
                'body_bbox_px': check['body_bbox_px'], 'neutral_anchor_px': check['support_anchor_px'],
                'neutral_natural_height_px': check['reference_body_height_px'], 'tail_bbox_px': check['tail_bbox_px'],
                'measurement_note': 'Explicit foot/support anchor; body scale is independent of long-tail extent. Alpha>=8 visible bounds; original pixels and full tail retained.',
            },
            'style_policy': {'target_ink_rgb': [121, 55, 5], 'future_video_target_width_ratio': .0065,
                             'future_video_target_width_px_at_1080': 7.02,
                             'note': 'Reference rendering policy, not a claim that a generated bitmap is pixel-identical at arbitrary future scales. Protect species markings, face, beak, toes and spines.'},
            'review': item.get('review', {}), 'species_notes': item.get('species_notes', {}),
            'alpha_qa': {key: check[key] for key in ['alpha_extrema', 'fully_transparent_fraction', 'visible_alpha8_margins_px', 'nonzero_alpha_margins_px', 'warnings']},
            'motion_policy': 'Neutral stock only. Production-specific outline, scale, fixed support and motion review is required before video adoption.',
            'files': [{'path': name, 'sha256': digest(folder / name), 'bytes': (folder / name).stat().st_size}
                      for name in ['neutral.png', 'generation-original.png', 'generation-record.json', 'generation-prompt.txt'] +
                      (['generation-input.json'] if (folder / 'generation-input.json').is_file() else [])],
            'additional_license_grant': False,
        }
        write_new(folder / 'source-manifest.json', manifest)
        with (folder / 'README.txt').open('x', encoding='utf-8') as output:
            output.write(f'{SPECIES[identity][0]} / {SPECIES[identity][1]}\n\n'
                         '新規に描いた透過の通常姿ストック。原画像は無加工で保持しています。\n'
                         '既存の完成動画やactive制作セットへは追加していません。\n'
                         '今後の動画で使用する際は体格、輪郭線、足元支点とモーションを別途確認してください。\n'
                         '詳細：source-manifest.json、再生成条件：generation-record.json。\n'
                         'この記録は新しい再配布ライセンスを付与しません。\n')
        entry = {'id': identity, 'source_version': folder.name, 'status': status, 'neutral_path': local(neutral), 'neutral_sha256': check['sha256'],
                 'source_manifest_path': local(folder / 'source-manifest.json'), 'source_manifest_sha256': digest(folder / 'source-manifest.json'),
                 'alpha_nonzero_bbox_px': check['alpha_nonzero_bbox_px'], 'visible_bbox_px': check['visible_bbox_px'], 'body_bbox_px': check['body_bbox_px'],
                 'support_anchor_px': check['support_anchor_px'], 'tail_bbox_px': check['tail_bbox_px']}
        entries.append(entry)
        prompts.append(f'[{identity} / {folder.name}]\n{check["prompt"]}\n')
    preview_layout = contact_sheet(entries, collection)
    with (collection / 'prompts.txt').open('x', encoding='utf-8') as output:
        output.write('\n'.join(prompts))
    if research:
        copy_new_or_identical(research, collection / 'research.json')
    stock_index(entries, collection, research is not None)
    write_new(collection / 'registration-input.json', config)
    manifest = {'schema_version': 1, 'kind': 'animal-character-stock-collection', 'collection_id': COLLECTION_ID,
                'created_at_utc': now, 'status': 'stocked-and-assistant-reviewed' if reviewed else 'stocked-pending-visual-review',
                'production_asset': False, 'active_productions_modified': False, 'items': entries,
                'style_references': references, 'preview': 'contact-sheet.png', 'alpha_review': 'alpha-review.png',
                'index': 'index.html',
                'preview_layout': preview_layout,
                'prompts': 'prompts.txt', 'registered_by': 'tools/register_animal_stock.py',
                'research': {'path': 'research.json', 'sha256': digest(collection / 'research.json'),
                             'scope': 'Factual species notes and official source URLs; no external photograph transferred.'} if research else None,
                'final_qa': config.get('final_qa', 'qa-evidence/final-review.json'),
                'selection_history': config.get('selection_history', 'selection-history.json'),
                'additional_license_grant': False}
    write_new(collection / 'manifest.json', manifest)
    write_new(collection / 'qa.json', {'status': 'pass', 'scope': 'Original PNG identity, alpha/bounds, declared support/body geometry, immutable copies and required review notes.',
                                     'visual_anatomy_and_style_approved': reviewed, 'production_integration_approved': False,
                                     'checks': [{'id': item['id'], 'source_version': source_folder(item).name,
                                                 **{k: v for k, v in check.items() if k != 'source'}}
                                                for item, check in zip(items, inspections, strict=True)]})
    if update_catalog:
        # Other work may have added items/productions while previews were written.
        # Re-read the latest complete bytes immediately before the catalog merge.
        catalog_before_bytes = CATALOG_PATH.read_bytes()
        catalog_before = json.loads(catalog_before_bytes.decode('utf-8-sig'))
        result = catalog_additions(catalog_before, entries, collection, digest(collection / 'manifest.json'))
        temp_base = Path('D:/temp') if Path('D:/').exists() else Path(tempfile.gettempdir())
        snapshots = Path(snapshot_dir) if snapshot_dir else temp_base / 'animal-stock-registry-snapshots'
        snapshots.mkdir(parents=True, exist_ok=True)
        snapshot_name = 'library-before-animal-stock-' + hashlib.sha256(catalog_before_bytes).hexdigest()[:16] + '.json'
        snapshot = snapshots / snapshot_name
        if snapshot.exists():
            if snapshot.read_bytes() != catalog_before_bytes:
                raise ValueError(f'Existing catalog snapshot differs: {snapshot}')
        else:
            with snapshot.open('xb') as output:
                output.write(catalog_before_bytes)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n', suffix='.tmp',
                                         prefix='animal-stock-', dir=CATALOG_PATH.parent, delete=False) as output:
            json.dump(result, output, ensure_ascii=False, indent=2)
            output.write('\n')
            temporary_catalog = Path(output.name)
        if CATALOG_PATH.read_bytes() != catalog_before_bytes:
            temporary_catalog.unlink()
            raise ValueError('Catalog changed concurrently; new stock files are saved, but catalog was not overwritten')
        temporary_catalog.replace(CATALOG_PATH)
        if read(CATALOG_PATH) != result:
            raise ValueError('Catalog changed immediately after registration; inspect concurrent work before retrying')
    return {'status': 'pass', 'collection': local(collection), 'identities': list(SPECIES),
            'catalog_updated': update_catalog, 'production_asset': False, 'active_productions_modified': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--reviewed', action='store_true')
    parser.add_argument('--update-catalog', action='store_true')
    parser.add_argument('--snapshot-dir', type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(register(args.config, args.reviewed, args.update_catalog, args.check_only, args.snapshot_dir), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
