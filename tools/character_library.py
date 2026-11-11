"""Inspect, render and export the portable Num-Num Numbers character library.

All operational paths are relative to the selected library root. Absolute paths
in original generation and QA records are historical provenance only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PureWindowsPath
import sys
import zipfile

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
INDEX = 'catalogs/character-library-v1.json'
FILES = 'catalogs/character-library-files-v1.json'
STOCK = 'assets/library/collections/animal-stock/v001/manifest.json'
MOTIONS = 'assets/library/collections/animal-motions/v001/manifest.json'
STYLE = 'assets/library/collections/animal-motions/v001/qa-evidence/series-style-review.json'
SCOPES = ['assets/library/characters', 'assets/library/collections/animal-stock/v001',
          'assets/library/collections/animal-motions/v001']
EXTRAS = ['assets/library/README.md', 'assets/library/AGENTS.md', 'tools/character_library.py',
          'requirements.txt', INDEX]
NAMES = {'bear-beret': ('赤い帽子のクマ', 'Bear'), 'rabbit-beret': ('ピンクのウサギ', 'Rabbit'),
         'tora': ('とら', 'Tora'), 'little-bird': ('小鳥', 'Little Bird'),
         'siamese-cat': ('シャム猫', 'Siamese Cat'), 'red-panda': ('レッサーパンダ', 'Red Panda'),
         'meerkat': ('ミーアキャット', 'Meerkat'), 'kangaroo': ('カンガルー', 'Kangaroo'),
         'hedgehog': ('ハリネズミ', 'Hedgehog'), 'fairy-pitta': ('ヤイロチョウ', 'Fairy Pitta'),
         'onagadori': ('オナガドリ', 'Onagadori')}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def resolve(root, relative):
    if not isinstance(relative, str) or Path(relative).is_absolute() or PureWindowsPath(relative).drive:
        raise ValueError(f'Operational path must be root-relative: {relative}')
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'Path leaves library root: {relative}')
    return path


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def inventory_paths(root):
    paths = set(EXTRAS)
    for scope in SCOPES:
        for path in resolve(root, scope).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                paths.add(path.relative_to(root).as_posix())
    return sorted(paths)


def refresh(root):
    stock, motions, style = [read(resolve(root, path)) for path in (STOCK, MOTIONS, STYLE)]
    selected = {item['id']: item for item in stock['items']}
    movements = {item['id']: item for item in motions['items']}
    records = {item['id']: item for item in style['records']}
    characters = []
    for identity, (ja, en) in NAMES.items():
        source = records[identity]
        with Image.open(resolve(root, source['path'])) as image:
            size = list(image.size)
        region = source.get('crop_px', [0, 0, *size])
        item = {
            'id': identity, 'name_ja': ja, 'name_en': en,
            'availability': 'reviewed-neutral-and-six-key-poses' if identity in selected else 'reviewed-neutral-and-legacy-episode-assets',
            'neutral': {'path': source['path'], 'sha256': source['sha256'], 'source_size_px': size,
                        'image_region_px': region, 'body_bbox_px': source['body_bbox_px'],
                        'anchor_px': source['anchor_px'],
                        'reference_height_px': source['body_bbox_px'][3] - source['body_bbox_px'][1],
                        'coordinate_space': 'original source PNG canvas; subtract image_region origin when loading a cropped neutral'},
            'comparison_body_height_px': source['height_px'],
        }
        if identity in selected:
            canonical = selected[identity]
            movement = movements[identity]
            registration = read(resolve(root, movement['registration']))
            item['canonical_source_version'] = canonical['source_version']
            item['neutral']['source_manifest'] = canonical['source_manifest_path']
            item['neutral']['source_manifest_sha256'] = canonical['source_manifest_sha256']
            item['key_poses'] = {
                'version': 'v001', 'registration': movement['registration'],
                'registration_sha256': movement['registration_sha256'],
                'common_reference_height_px': registration['common_reference_height_px'],
                'coordinate_space': 'individual exact cell PNG',
                'poses': {frame['id']: {key: frame[key] for key in
                         ['path', 'sha256', 'size_px', 'anchor_px', 'body_bbox_px', 'tail_bbox_px', 'reference_height_px']}
                         for frame in registration['frames']},
                'preview': movement['preview'], 'motion_preview': movement['motion_preview'],
            }
        else:
            item['legacy_usage'] = 'Use existing episode adapters for legacy reactions. The generic key-pose loader exposes this reviewed neutral only.'
        characters.append(item)
    index = {
        'schema_version': 1, 'kind': 'portable-character-library-index',
        'path_base': 'library-root', 'guide': 'assets/library/README.md',
        'agent_instructions': 'assets/library/AGENTS.md',
        'coordinate_units': 'source pixels; xyxy boxes use exclusive right/bottom',
        'selection_policy': 'Use these explicit adopted paths, never the largest version number or an unselected trial.',
        'source_collections': [{'path': path, 'sha256': sha(resolve(root, path))} for path in (STOCK, MOTIONS)],
        'usage_rules': ['Preserve the canonical face, palette, texture, contour and species markings.',
                        'Use target_body_height / reference_height as one isotropic scale for all key poses of a species.',
                        'Align the anatomical foot anchor; do not fit each pose bounding box or long tail footprint.',
                        'Saved PNG alpha and pixels are originals or lossless cell extractions. Alpha254 is valid.',
                        'Absolute generation/QA paths are historical records, not runtime dependencies.',
                        'Peck keys are downward gestures; exact beak/ground contact is not guaranteed.',
                        'Key poses are reviewed stock. Actual episode timing, clearance and continuous movement need scene review.'],
        'characters': characters,
    }
    write(resolve(root, INDEX), index)
    files = []
    for relative in inventory_paths(root):
        path = resolve(root, relative)
        files.append({'path': relative, 'bytes': path.stat().st_size, 'sha256': sha(path)})
    write(resolve(root, FILES), {'schema_version': 1, 'kind': 'character-library-file-inventory',
                               'path_base': 'library-root', 'files': files,
                               'scope': 'Complete eleven character folders, both stock collections, AI guide, loader and requirements; historical trials retained.'})
    return {'status': 'pass', 'action': 'refresh', 'characters': len(characters), 'files': len(files)}


def load_pose(root, identity, pose='neutral'):
    """Return (RGBA image, image-local foot anchor, common reference height)."""
    index = read(resolve(root, INDEX))
    matches = [item for item in index['characters'] if item['id'] == identity]
    if len(matches) != 1:
        raise ValueError(f'Unknown character: {identity}')
    character = matches[0]
    if pose == 'neutral':
        record = character['neutral']
        region = record['image_region_px']
        with Image.open(resolve(root, record['path'])) as opened:
            image = opened.crop(region)
        anchor = [record['anchor_px'][0] - region[0], record['anchor_px'][1] - region[1]]
    else:
        record = character.get('key_poses', {}).get('poses', {}).get(pose)
        if record is None:
            raise ValueError(f'No generic reviewed pose {identity}/{pose}; see the library guide for legacy adapters')
        with Image.open(resolve(root, record['path'])) as opened:
            image = opened.copy()
        anchor = record['anchor_px']
    return image, anchor, record['reference_height_px']


def verify(root):
    inventory = read(resolve(root, FILES))
    expected = {entry['path'] for entry in inventory['files']}
    if expected != set(inventory_paths(root)):
        raise ValueError('Library inventory is stale; review changes and run refresh')
    for entry in inventory['files']:
        path = resolve(root, entry['path'])
        if not path.is_file() or path.stat().st_size != entry['bytes'] or sha(path) != entry['sha256']:
            raise ValueError(f'Missing or changed library file: {entry["path"]}')
    index = read(resolve(root, INDEX))
    frames = 0
    for collection in index['source_collections']:
        if sha(resolve(root, collection['path'])) != collection['sha256']:
            raise ValueError('Adopted collection changed')
    for character in index['characters']:
        neutral = character['neutral']
        if sha(resolve(root, neutral['path'])) != neutral['sha256']:
            raise ValueError(f'Neutral changed: {character["id"]}')
        image, anchor, height = load_pose(root, character['id'])
        if image.mode != 'RGBA' or not (0 <= anchor[0] <= image.width and 0 <= anchor[1] <= image.height) or height <= 0:
            raise ValueError('Invalid neutral geometry')
        keys = character.get('key_poses')
        if not keys:
            continue
        if sha(resolve(root, keys['registration'])) != keys['registration_sha256']:
            raise ValueError('Pose registration changed')
        registration = read(resolve(root, keys['registration']))
        with Image.open(resolve(root, registration['source_sheet'])) as sheet:
            if sha(resolve(root, registration['source_sheet'])) != registration['source_sheet_sha256']:
                raise ValueError('Generated source sheet changed')
            for frame in registration['frames']:
                image, anchor, height = load_pose(root, character['id'], frame['id'])
                if (image.mode != 'RGBA' or image.tobytes() != sheet.crop(frame['crop_from_sheet_xyxy']).tobytes()
                        or height != keys['common_reference_height_px']
                        or sha(resolve(root, frame['path'])) != frame['sha256']):
                    raise ValueError(f'Pose pixels or common scale changed: {character["id"]}/{frame["id"]}')
                alpha = image.getchannel('A')
                if alpha.getextrema()[0] != 0 or alpha.getextrema()[1] < 240:
                    raise ValueError('Invalid source transparency')
                if character['id'] == 'onagadori':
                    union = Image.new('L', image.size, 0)
                    draw = ImageDraw.Draw(union)
                    for box in [frame['body_bbox_px'], frame['tail_bbox_px']]:
                        draw.rectangle((box[0], box[1], box[2] - 1, box[3] - 1), fill=255)
                    if ImageChops.subtract(alpha.point(lambda a: 255 if a >= 8 else 0), union).getbbox():
                        raise ValueError('Long tail leaves its registered body/tail bounds')
                frames += 1
    return {'status': 'pass', 'characters': len(index['characters']), 'neutral_png_sources': 11,
            'generic_key_pose_pngs': frames, 'files': len(inventory['files']),
            'bytes': sum(entry['bytes'] for entry in inventory['files']),
            'absolute_provenance_paths_required_for_runtime': False}


def preview(root, identity, pose, height, output, background):
    if not 1 <= height <= 8192:
        raise ValueError('Preview body height must be 1..8192 pixels')
    output = Path(output).resolve()
    if output.exists() or output.is_relative_to(resolve(root, 'assets/library')):
        raise ValueError('Choose a new preview output outside the source asset library')
    image, anchor, reference = load_pose(root, identity, pose)
    bounds = image.getchannel('A').point(lambda a: 255 if a >= 8 else 0).getbbox()
    if bounds is None:
        raise ValueError('Empty source image')
    scale = height / reference
    sprite = image.crop(bounds)
    sprite = sprite.resize((max(1, round(sprite.width * scale)), max(1, round(sprite.height * scale))), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (sprite.width + 48, sprite.height + 48), (0, 0, 0, 0) if background == 'transparent' else background)
    canvas.alpha_composite(sprite, (24, 24))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    return {'status': 'pass', 'output': str(output), 'scale': scale,
            'support_anchor_px': [24 + (anchor[0] - bounds[0]) * scale, 24 + (anchor[1] - bounds[1]) * scale],
            'reference_height_px': reference, 'source_pixels_modified': False}


def export(root, output):
    result = verify(root)
    output = Path(output).resolve()
    if (any(path.exists() for path in [output, output.with_suffix(output.suffix + '.sha256'), output.with_suffix(output.suffix + '.json')])
            or output.is_relative_to(resolve(root, 'assets/library'))):
        raise ValueError('Choose a new ZIP output outside the source asset library')
    output.parent.mkdir(parents=True, exist_ok=True)
    inventory = read(resolve(root, FILES))
    entries = [*inventory['files'], {'path': FILES, 'bytes': resolve(root, FILES).stat().st_size, 'sha256': sha(resolve(root, FILES))}]
    sums = {entry['path']: entry['sha256'] for entry in entries}
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for entry in entries:
            archive.write(resolve(root, entry['path']), 'character-library/' + entry['path'])
        archive.writestr('character-library/SHA256SUMS.json', json.dumps(sums, indent=2) + '\n')
    with zipfile.ZipFile(output) as archive:
        for relative, expected in sums.items():
            with archive.open('character-library/' + relative) as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                    raise ValueError(f'ZIP verification failed: {relative}')
    checksum = sha(output)
    output.with_suffix(output.suffix + '.sha256').write_text(checksum + '  ' + output.name + '\n', encoding='utf-8')
    receipt = {'status': 'pass', 'created_at_utc': datetime.now(timezone.utc).isoformat(), 'archive': str(output),
               'archive_sha256': checksum, 'archive_bytes': output.stat().st_size, 'member_files': len(entries) + 1,
               'all_members_hash_verified': True, 'library': result,
               'scope': 'Self-contained character-library bundle; does not include complete video productions or caches.'}
    write(output.with_suffix(output.suffix + '.json'), receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    listing = sub.add_parser('list')
    listing.add_argument('--json', action='store_true')
    checking = sub.add_parser('verify')
    checking.add_argument('--report', type=Path)
    sub.add_parser('refresh')
    rendering = sub.add_parser('preview')
    rendering.add_argument('--character', required=True)
    rendering.add_argument('--pose', default='neutral')
    rendering.add_argument('--height', type=int, default=430)
    rendering.add_argument('--background', default='#fff8e8')
    rendering.add_argument('--output', required=True, type=Path)
    packaging = sub.add_parser('export')
    packaging.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == 'list':
            index = read(resolve(root, INDEX))
            if args.json:
                print(json.dumps(index, ensure_ascii=False, indent=2))
            else:
                for item in index['characters']:
                    print(f'{item["id"]}\t{item["name_ja"]}\tneutral + {len(item.get("key_poses", {}).get("poses", {}))} generic poses')
            return 0
        if args.command == 'refresh':
            result = refresh(root)
        elif args.command == 'verify':
            result = verify(root)
            if args.report:
                destination = args.report.resolve()
                if destination.exists() or destination.is_relative_to(resolve(root, 'assets/library')):
                    raise ValueError('Choose a new verification report outside the source asset library')
                write(destination, result)
        elif args.command == 'preview':
            result = preview(root, args.character, args.pose, args.height, args.output, args.background)
        else:
            result = export(root, args.output)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print(f'Character library error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
