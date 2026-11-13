"""Build and verify a common current/ entry for adopted characters and gimmicks.

The adopted character index remains authoritative. This tool copies or losslessly
crops derived PNGs, never moves source art, edits adoption, or releases reservations.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import sys
import uuid

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
INDEX = 'catalogs/character-library-v1.json'
MASTER = 'catalogs/asset-library-current-v1.json'
TOOL = 'tools/unified_asset_library.py'


def payload(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(root, relative):
    if (not isinstance(relative, str) or not relative or '\\' in relative
            or Path(relative).is_absolute() or PureWindowsPath(relative).drive
            or any(part in ('', '.', '..') for part in relative.split('/'))):
        raise ValueError(f'Expected a canonical project-relative path: {relative}')
    here = Path(root).resolve()
    for part in relative.split('/'):
        here /= part
        if here.is_symlink():
            raise ValueError(f'Unified library paths must not contain symlinks: {relative}')
    return here


def read_stable(root, relative, guards=None, expected=None):
    path = safe_path(root, relative)
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    signature = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
    if signature(before) != signature(after):
        raise ValueError(f'Source changed during reading: {relative}')
    observed = digest(data)
    if expected is not None and observed != expected:
        raise ValueError(f'Source SHA-256 differs from adopted index: {relative}')
    if guards is not None:
        previous = guards.setdefault(relative, observed)
        if previous != observed:
            raise ValueError(f'Source changed during build: {relative}')
    return data


def json_source(root, relative, guards=None, expected=None):
    return json.loads(read_stable(root, relative, guards, expected).decode('utf-8-sig'))


def check_guards(root, guards):
    for relative, expected in guards.items():
        if digest(read_stable(root, relative)) != expected:
            raise ValueError(f'Source changed during build: {relative}')


def component(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_-]*', value):
        raise ValueError(f'Invalid asset/pose identifier: {value}')
    return value


def adjusted_geometry(record, origin, size):
    result = {}
    for field in ('anchor_px', 'body_bbox_px', 'subject_bbox_px', 'tail_bbox_px'):
        if field not in record:
            continue
        values = record[field]
        if values is None:
            result[field] = None
            continue
        length = 2 if field == 'anchor_px' else 4
        if (not isinstance(values, list) or len(values) != length
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values)):
            raise ValueError(f'Invalid adopted geometry: {field}')
        shifted = [value-origin[n % 2] for n, value in enumerate(values)]
        if length == 2:
            contained = 0 <= shifted[0] <= size[0] and 0 <= shifted[1] <= size[1]
        else:
            contained = 0 <= shifted[0] < shifted[2] <= size[0] and 0 <= shifted[1] < shifted[3] <= size[1]
        if not contained:
            raise ValueError(f'Adopted geometry leaves the current PNG: {field}')
        result[field] = shifted
    reference = record.get('reference_height_px')
    if (isinstance(reference, bool) or not isinstance(reference, (int, float))
            or not math.isfinite(reference) or reference <= 0):
        raise ValueError('Invalid adopted reference height')
    result['reference_height_px'] = reference
    for field in ('anchor_kind', 'anchor_measurement', 'anchor_basis', 'vertical_motion_policy',
                  'sheet_id', 'frame_id', 'source_sheet', 'source_sheet_sha256'):
        if field in record:
            result[field] = record[field]
    return result


def picture(root, source, destination, local_path, guards, *, neutral=False, icon=False, verifying=False):
    relative = source['path']
    if '/current/' in relative:
        raise ValueError('Adopted sources must not point back into a generated current/ view')
    data = read_stable(root, relative, guards, source['sha256'])
    with Image.open(io.BytesIO(data)) as opened:
        if opened.mode != 'RGBA' or opened.format != 'PNG':
            raise ValueError(f'Adopted source must be an RGBA PNG: {relative}')
        original = opened.copy()
    recorded_size = source.get('source_size_px' if neutral else 'size_px')
    if recorded_size != list(original.size):
        raise ValueError(f'Adopted PNG size differs: {relative}')
    region = source.get('image_region_px', [0, 0, *original.size]) if neutral else [0, 0, *original.size]
    if (not isinstance(region, list) or len(region) != 4
            or any(isinstance(v, bool) or not isinstance(v, int) for v in region)
            or not 0 <= region[0] < region[2] <= original.width
            or not 0 <= region[1] < region[3] <= original.height):
        raise ValueError(f'Invalid adopted neutral crop: {relative}')
    cropped = original.crop(region)
    operation = 'byte-copy' if region == [0, 0, *original.size] else 'lossless-native-pixel-crop'
    output_data = None
    if operation == 'byte-copy':
        output_hash = source['sha256']
    else:
        buffer = io.BytesIO()
        cropped.save(buffer, format='PNG')
        output_data = buffer.getvalue()
        output_hash = digest(output_data)
        if verifying:
            existing = read_stable(root, destination)
            with Image.open(io.BytesIO(existing)) as alias:
                if alias.mode != 'RGBA' or alias.size != cropped.size or alias.tobytes() != cropped.tobytes():
                    raise ValueError(f'Current neutral pixels differ from the adopted native crop: {destination}')
            output_hash = digest(existing)
    if icon:
        box = source.get('subject_bbox_px')
        if (source.get('role') != 'face-icon' or not isinstance(box, list) or len(box) != 4
                or any(type(value) is not int for value in box)
                or not 0 <= box[0] < box[2] <= cropped.width or not 0 <= box[1] < box[3] <= cropped.height
                or any(key in source for key in ('body_bbox_px', 'reference_height_px', 'anchor_px'))):
            raise ValueError('Icon needs subject bounds and a role separate from body registration')
        geometry = {'role': source['role'], 'subject_bbox_px': box}
    else:
        geometry = adjusted_geometry(source, region[:2], cropped.size)
    record = {'path': local_path, 'sha256': output_hash, 'size_px': list(cropped.size),
              'source_path': relative, 'source_sha256': source['sha256'],
              'source_image_region_px': region, 'source_size_px': list(original.size),
              'operation': operation, **geometry}
    return record, {'path': destination, 'source': relative, 'sha256': output_hash, 'data': output_data}


def clip_record(value, namespace, targets, origin):
    if isinstance(value, list):
        clip = {'frames': value, 'timing': 'Not specified by the source registration; choose and verify timing in the scene.'}
    elif isinstance(value, dict):
        clip = dict(value)
    else:
        raise ValueError('Source clips must be frame lists or clip records')
    frames = clip.get('frames')
    if not isinstance(frames, list) or not frames:
        raise ValueError('Source clip has no frames')
    qualified = []
    for frame in frames:
        if not isinstance(frame, str):
            raise ValueError('Source clip frame must be a pose name')
        key = frame if '/' in frame else namespace + '/' + frame
        if key not in targets or not key.startswith(namespace + '/'):
            raise ValueError(f'Source clip refers to an unknown namespaced pose: {key}')
        qualified.append(key)
    clip.update(frames=qualified, source_registration=origin)
    return clip


def plan(root, *, verifying=False):
    guards = {}
    index = json_source(root, INDEX, guards)
    source_index = {'path': INDEX, 'sha256': guards[INDEX]}
    assets, seen = [], set()
    for selected in index['characters']:
        identity = component(selected['id'])
        if identity in seen:
            raise ValueError(f'Duplicate adopted asset id: {identity}')
        seen.add(identity)
        category = selected.get('category', 'character')
        if category not in ('character', 'gimmick'):
            raise ValueError(f'Unknown adopted asset category: {category}')
        base = f'assets/library/characters/{identity}/current/'
        neutral, alias = picture(root, selected['neutral'], base+'neutral.png', 'neutral.png', guards,
                                 neutral=True, verifying=verifying)
        aliases, poses, clips, registrations = [alias], {}, {}, []
        blocks = [(namespace, selected.get(block_name)) for block_name, namespace in
                  [('key_poses', 'gimmick' if category == 'gimmick' else 'basic'),
                   ('expanded_key_poses', 'expanded'), ('eyecatch_key_poses', 'eyecatch')]]
        namespaces = {'basic', 'gimmick', 'expanded', 'eyecatch', 'neutral', 'icons'}
        for block in selected.get('pose_sets', []):
            namespace = component(block['namespace'])
            if namespace in namespaces:
                raise ValueError('Supplemental pose namespace is duplicated or reserved')
            namespaces.add(namespace)
            blocks.append((namespace, block))
        for namespace, block in blocks:
            if not block:
                continue
            registration = json_source(root, block['registration'], guards, block['registration_sha256'])
            origin = {'path': block['registration'], 'sha256': block['registration_sha256']}
            for pose_id, source in block['poses'].items():
                key = namespace+'/'+component(pose_id)
                local = 'poses/'+key+'.png'
                poses[key], alias = picture(root, source, base+local, local, guards, verifying=verifying)
                aliases.append(alias)
            available = block.get('clips') or registration.get('clips') or {}
            if not isinstance(available, dict):
                raise ValueError('Source registration clips must be named')
            for name, value in available.items():
                clips[namespace+'/'+component(name)] = clip_record(value, namespace, poses, origin)
            registrations.append({'namespace': namespace, **origin, 'clips_available': bool(available)})
            for override in block.get('pose_overrides', []):
                json_source(root, override['registration'], guards, override['registration_sha256'])
                registrations.append({'namespace': namespace, 'path': override['registration'],
                    'sha256': override['registration_sha256'], 'role': 'explicit-pose-override',
                    'pose_ids': sorted(override['replacements']), 'clips_available': False,
                    'selection': 'catalogs/character-adoptions-v1.json'})
        icons = {}
        for name, source in selected.get('icons', {}).items():
            local = 'icons/'+component(name)+'.png'
            icons[name], alias = picture(root, source, base+local, local, guards, icon=True, verifying=verifying)
            aliases.append(alias)
        clip_document = {'schema_version': 1, 'kind': 'unified-current-asset-clips',
                         'id': identity, 'clips': clips, 'source_registrations': registrations}
        manifest = {'schema_version': 1, 'kind': 'unified-current-asset',
            'id': identity, 'name_ja': selected['name_ja'], 'name_en': selected['name_en'],
            'category': category, 'source_index': source_index, 'neutral': neutral, 'poses': poses,
            'clips': {'path': 'clips.json', 'sha256': digest(payload(clip_document))},
            'source_registrations': registrations,
            'geometry_policy': 'Native pixels and adopted per-frame references retained. Atlas neutral coordinates are shifted only by the adopted crop origin.'}
        if icons:
            manifest['icons'] = icons
        if 'scene_relative_scale' in selected:
            scale = selected['scene_relative_scale']
            ratio = scale.get('body_height_ratio') if isinstance(scale, dict) else None
            if (not isinstance(scale, dict) or set(scale) != {'relative_to', 'body_height_ratio'}
                    or scale['relative_to'] == identity
                    or scale['relative_to'] not in {item['id'] for item in index['characters']}
                    or isinstance(ratio, bool) or not isinstance(ratio, (int, float))
                    or not math.isfinite(ratio) or ratio <= 0):
                raise ValueError('Invalid scene relative scale')
            manifest['scene_relative_scale'] = dict(scale)
        assets.append({'base': base, 'manifest': manifest, 'clips': clip_document, 'aliases': aliases})
    master = {'schema_version': 1, 'kind': 'unified-current-asset-library', 'source_index': source_index,
        'selection_policy': 'Explicit adopted index entries, independent of version numbers; current/ is a derived entry layer and originals remain authoritative.',
        'assets': [{'id': item['manifest']['id'], 'name_ja': item['manifest']['name_ja'],
                    'name_en': item['manifest']['name_en'], 'category': item['manifest']['category'],
                    'manifest': item['base']+'asset.json', 'sha256': digest(payload(item['manifest']))} for item in assets]}
    return assets, master, guards


def current_files(root, base):
    path = safe_path(root, base.rstrip('/'))
    if not path.exists():
        return set()
    found = set()
    for folder, directories, names in os.walk(path, followlinks=False):
        for name in [*directories, *names]:
            candidate = Path(folder)/name
            if candidate.is_symlink():
                raise ValueError(f'Symlink inside generated current/ view: {candidate}')
        found.update((Path(folder)/name).relative_to(Path(root).resolve()).as_posix() for name in names)
    return found


def expected_paths(item):
    return {item['base']+'asset.json', item['base']+'clips.json', *(alias['path'] for alias in item['aliases'])}


def atomic_metadata(root, relative, value):
    path = safe_path(root, relative)
    data = payload(value)
    if path.is_file() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.tmp-'+uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def create_alias(root, alias, guards):
    path = safe_path(root, alias['path'])
    if path.exists():
        if digest(path.read_bytes()) != alias['sha256']:
            raise ValueError(f'Refusing to overwrite a different current PNG: {alias["path"]}')
        return
    data = alias['data']
    if data is None:
        data = read_stable(root, alias['source'], guards, alias['sha256'])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.tmp-'+uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Create-only publication; a concurrent file can never be overwritten.
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build(root=ROOT):
    root = Path(root).resolve()
    assets, master, guards = plan(root)
    for item in assets:
        unknown = current_files(root, item['base'])-expected_paths(item)
        if unknown:
            raise ValueError(f'Unlisted files in generated current/ view; no files deleted: {sorted(unknown)[0]}')
        for alias in item['aliases']:
            path = safe_path(root, alias['path'])
            if path.exists() and digest(path.read_bytes()) != alias['sha256']:
                raise ValueError(f'Refusing to overwrite a different current PNG: {alias["path"]}')
    for item in assets:
        for alias in item['aliases']:
            create_alias(root, alias, guards)
    check_guards(root, guards)
    for item in assets:
        atomic_metadata(root, item['base']+'clips.json', item['clips'])
        atomic_metadata(root, item['base']+'asset.json', item['manifest'])
    check_guards(root, guards)
    atomic_metadata(root, MASTER, master)
    return {'status': 'pass', 'action': 'build', 'assets': len(assets),
            'pngs': sum(len(item['aliases']) for item in assets), 'master': MASTER,
            'sources_modified': False, 'reservations_modified': False}


def verify(root=ROOT):
    root = Path(root).resolve()
    actual_master = json_source(root, MASTER)
    assets, expected_master, guards = plan(root, verifying=True)
    if actual_master != expected_master:
        raise ValueError('Unified master differs from the adopted index/current manifests')
    for item, summary in zip(assets, actual_master['assets']):
        if current_files(root, item['base']) != expected_paths(item):
            raise ValueError(f'Missing or unlisted files in current/ view: {item["manifest"]["id"]}')
        if json_source(root, summary['manifest'], expected=summary['sha256']) != item['manifest']:
            raise ValueError('Current asset metadata differs from adopted source geometry/paths')
        if json_source(root, item['base']+'clips.json', expected=item['manifest']['clips']['sha256']) != item['clips']:
            raise ValueError('Current clip targets differ from adopted source clips')
        for alias in item['aliases']:
            if digest(read_stable(root, alias['path'])) != alias['sha256']:
                raise ValueError(f'Current PNG differs from its source/manifest: {alias["path"]}')
    check_guards(root, guards)
    return {'status': 'pass', 'action': 'verify', 'assets': len(assets),
            'pngs': sum(len(item['aliases']) for item in assets), 'source_index_sha256': guards[INDEX],
            'native_crop_and_copy_pixels_verified': True}


def required_paths(root=ROOT):
    """Return the published current layer closure without scanning historical art."""
    root = Path(root).resolve()
    master = json_source(root, MASTER)
    paths = {MASTER, master['source_index']['path']}
    if safe_path(root, TOOL).is_file():
        paths.add(TOOL)
    for summary in master['assets']:
        identity = component(summary['id'])
        base = f'assets/library/characters/{identity}/current/'
        if summary['manifest'] != base+'asset.json':
            raise ValueError('Unified master manifest leaves the asset current/ directory')
        manifest = json_source(root, summary['manifest'], expected=summary['sha256'])
        paths.add(summary['manifest'])
        for record in [manifest['neutral'], *manifest['poses'].values(), *manifest.get('icons', {}).values(), manifest['clips']]:
            relative = base+record['path']
            safe_path(root, relative)
            paths.add(relative)
    return paths


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('command', choices=['build', 'verify'])
    args = parser.parse_args(argv)
    try:
        result = build(args.root) if args.command == 'build' else verify(args.root)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Unified asset library error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
