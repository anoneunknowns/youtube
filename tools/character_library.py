"""Inspect, render and export the portable Num-Num Numbers character library.

All operational paths are relative to the selected library root. Absolute paths
in original generation and QA records are historical provenance only.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import sys
import uuid
import zipfile

from PIL import Image, ImageChops, ImageDraw

try:
    from . import manage_character_assets as management
except ImportError:  # Direct CLI execution, including an extracted bundle.
    import manage_character_assets as management

ROOT = Path(__file__).resolve().parents[1]
INDEX = 'catalogs/character-library-v1.json'
FILES = 'catalogs/character-library-files-v1.json'
PUBLICATION = 'catalogs/github-publication-v1.json'
STOCK = 'assets/library/collections/animal-stock/v001/manifest.json'
MOTIONS = 'assets/library/collections/animal-motions/v001/manifest.json'
STYLE = 'assets/library/collections/animal-motions/v001/qa-evidence/series-style-review.json'
EXPANSION = 'assets/library/collections/character-expansion/v001/manifest.json'
EYECATCHES = 'assets/library/collections/character-eyecatches/v001/manifest.json'
GIMMICKS = 'assets/library/collections/background-gimmicks/v001/manifest.json'
SUPPLEMENT = 'assets/library/collections/app-character-stock/v001/manifest.json'
MANAGEMENT = 'catalogs/character-asset-management-v1.json'
ADOPTIONS = 'catalogs/character-adoptions-v1.json'
SCOPES = ['assets/library/characters', 'assets/library/collections/animal-stock/v001',
          'assets/library/collections/animal-motions/v001',
          'assets/library/collections/character-expansion/v001',
          'assets/library/collections/character-eyecatches/v001',
          'assets/library/collections/character-style-audit/v001',
          'assets/library/collections/character-management/v001',
          'assets/library/collections/background-gimmicks/v001',
          'assets/library/collections/app-character-stock/v001']
EXTRAS = ['assets/library/README.md', 'assets/library/AGENTS.md', 'tools/character_library.py',
          'tools/register_character_expansion.py', 'tools/register_character_eyecatches.py', 'tools/component_alignment.py',
          'tools/manage_character_assets.py', 'tools/audit_character_style.py',
          'docs/IMAGE-ASSET-MANAGEMENT.md', 'docs/LAYOUT-ALIGNMENT.md',
          'assets/library/character-assets.html', MANAGEMENT,
          'catalogs/character-asset-registry-v1.json', 'requirements.txt', INDEX]
OPTIONAL_EXTRAS = ['catalogs/asset-library-current-v1.json', 'tools/unified_asset_library.py',
                   'tools/image_remake_review.py', 'tools/image_remake_review.html', ADOPTIONS]
# Videos are optional local production evidence. They are not published with
# the portable artwork library; recorded provenance and registrations stay intact.
LOCAL_VIDEO_EXTENSIONS = frozenset({
    '.mp4', '.m4v', '.mov', '.mkv', '.webm', '.avi', '.wmv', '.flv', '.f4v',
    '.mpeg', '.mpg', '.mpe', '.3gp', '.3g2', '.mts', '.m2ts', '.ts', '.vob',
    '.ogv', '.m2v', '.divx', '.mxf', '.asf', '.qt', '.rm', '.rmvb',
})
NAMES = {'bear-beret': ('赤い帽子のクマ', 'Bear'), 'rabbit-beret': ('ピンクのウサギ', 'Rabbit'),
         'tora': ('とら', 'Tora'), 'little-bird': ('小鳥', 'Little Bird'),
         'siamese-cat': ('シャム猫', 'Siamese Cat'), 'red-panda': ('レッサーパンダ', 'Red Panda'),
         'meerkat': ('ミーアキャット', 'Meerkat'), 'kangaroo': ('カンガルー', 'Kangaroo'),
         'hedgehog': ('ハリネズミ', 'Hedgehog'), 'fairy-pitta': ('ヤイロチョウ', 'Fairy Pitta'),
         'onagadori': ('オナガドリ', 'Onagadori')}
GIMMICK_ANCHORS = {'ground', 'base', 'center'}


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


def pending_generation_roots(root):
    """Keep a new live-writer tree pending without hiding inventoried originals."""
    root = Path(root).resolve()
    config_path = publication_path(root, MANAGEMENT)
    if not config_path.is_file():
        return []
    config = read(config_path)
    previous_path = publication_path(root, FILES)
    previous = read(previous_path)['files'] if previous_path.is_file() else []
    pending = []
    for reservation in config.get('reservations', []):
        if reservation.get('status') != 'active':
            continue
        if not reservation.get('id') or not reservation.get('owner'):
            raise ValueError('Active asset reservation needs an id and owner')
        path = management.lexical_path(root, reservation['root'])
        relative = management.lexical_relative(root, path)
        if not relative.startswith('assets/library/characters/') or len(Path(relative).parts) < 5:
            raise ValueError('Generation reservation must name a new character batch')
        if any(management.contains(relative, entry['path']) for entry in previous):
            raise ValueError('Active reservation cannot hide already inventoried files; use a new generation batch')
        pending.append(path)
    return pending


@contextmanager
def reservation_snapshot(root):
    """Keep reservations stable until the last source read in an operation."""
    root = Path(root).resolve()
    config = publication_path(root, MANAGEMENT)
    with management.lock(config.with_suffix(config.suffix + '.lock')):
        yield root


def inventory_paths(root):
    with reservation_snapshot(root) as root:
        return _inventory_paths_locked(root)


def _inventory_paths_locked(root):
    root = Path(root).resolve()
    pending = pending_generation_roots(root)
    profile = publication_path(root, PUBLICATION)
    if profile.is_file():
        return _published_inventory_paths_locked(root, read(profile), pending)
    def is_pending(path):
        return any(management.contains(prefix.as_posix(), path.as_posix()) for prefix in pending)
    paths = {relative for relative in EXTRAS
             if Path(relative).suffix.lower() not in LOCAL_VIDEO_EXTENSIONS
             and not is_pending(management.lexical_path(root, relative))}
    paths.update(relative for relative in OPTIONAL_EXTRAS
                 if readable_source(root, relative, pending).is_file())
    for adopted in _read_adoptions_locked(root, pending).values():
        paths.update(item['path'] for item in adopted['selection_evidence'])
    for scope in SCOPES:
        directory = management.lexical_path(root, scope)
        if is_pending(directory):
            continue
        for current, directories, names in os.walk(readable_source(root, scope, pending), followlinks=False):
            here = Path(current)
            # Exclude the lexical writer tree before following file links or
            # visiting its contents. A live input-reference link can resolve
            # onto a frozen original outside this tree without being finished.
            if is_pending(here):
                directories[:] = []
                continue
            directories[:] = [name for name in directories if name != '__pycache__'
                              and not is_pending(here / name)]
            for name in names:
                path = here / name
                if is_pending(path) or path.suffix.lower() in LOCAL_VIDEO_EXTENSIONS:
                    continue
                if path.is_symlink():
                    raise ValueError(f'Library source file must not be a symlink: {path.relative_to(root).as_posix()}')
                if path.is_file() and path.suffix != '.pyc':
                    paths.add(path.relative_to(root).as_posix())
    return sorted(paths)


def _publication_paths(value, label):
    if not isinstance(value, list) or any(not isinstance(path, str) for path in value):
        raise ValueError(f'Publication {label} must be a list of relative path strings')
    if len(value) != len(set(value)):
        raise ValueError(f'Publication {label} contains duplicate paths')
    for path in value:
        if (not path or '\\' in path or Path(path).is_absolute() or PureWindowsPath(path).drive
                or any(part in ('', '.', '..') for part in path.split('/'))):
            raise ValueError(f'Publication path must be canonical and root-relative: {path}')
    return set(value)


def _registration_generation_path(root, document, reference):
    """Resolve portable auxiliary receipts without probing historical absolute paths."""
    if (not isinstance(reference, str) or not reference or '\\' in reference
            or Path(reference).is_absolute() or PureWindowsPath(reference).drive):
        raise ValueError(f'Generation metadata must be project-relative: {reference}')
    prefixes = ('assets/', 'catalogs/', 'tools/', 'docs/', 'design/', 'materials/',
                'reproducibility/', 'tests/', 'templates/', 'episodes/')
    if not reference.startswith(prefixes):
        reference = (Path(document).parent / reference).as_posix()
    return management.lexical_relative(root, management.lexical_path(root, reference))


def _required_current_library_paths_locked(root, pending):
    """Derive required adopted sources independently of the publication list."""
    index = _build_index_locked(root)
    required = {PUBLICATION, *EXTRAS, STYLE}
    required.update(relative for relative in OPTIONAL_EXTRAS
                    if readable_source(root, relative, pending).is_file())
    if publication_path(root, 'catalogs/asset-library-current-v1.json').is_file():
        try:
            from .unified_asset_library import required_paths as current_view_paths
        except ImportError:
            from unified_asset_library import required_paths as current_view_paths
        required.update(current_view_paths(root))
    required.update(item['path'] for item in index['source_collections'])
    if any(item['path'] == SUPPLEMENT for item in index['source_collections']):
        supplement = read(readable_source(root, SUPPLEMENT, pending))
        required.update(item['path'] for item in supplement['review_evidence'])
    for adopted in _read_adoptions_locked(root, pending).values():
        required.update(item['path'] for item in adopted['selection_evidence'])
    for character in index['characters']:
        neutral = character['neutral']
        required.update(neutral[key] for key in ('path', 'source_manifest') if neutral.get(key))
        required.update(icon['path'] for icon in character.get('icons', {}).values())
        if character.get('category') == 'gimmick' or (character.get('supplemental_collection') and neutral.get('source_manifest')):
            manifest_relative = neutral['source_manifest']
            manifest = read(readable_source(root, manifest_relative, pending))
            for record in manifest.get('files', []):
                relative = record['path']
                if not relative.startswith('assets/'):
                    relative = (Path(manifest_relative).parent / relative).as_posix()
                required.add(relative)
        for block in [character.get(name) for name in ('key_poses', 'expanded_key_poses', 'eyecatch_key_poses')] + character.get('pose_sets', []):
            if not block:
                continue
            required.update(block[key] for key in ('registration', 'preview', 'motion_preview') if block.get(key))
            required.update(frame['path'] for frame in block['poses'].values())
            registration = read(readable_source(root, block['registration'], pending))
            if registration.get('source_sheet'):
                required.add(registration['source_sheet'])
            required.update(_registration_generation_path(root, block['registration'], registration[key])
                            for key in ('generation_input', 'generation_prompt') if registration.get(key))
            for sheet in registration.get('sheets', []):
                required.add(sheet['source_sheet'])
                required.update(_registration_generation_path(root, block['registration'], sheet[key])
                                for key in ('generation_input', 'generation_prompt') if sheet.get(key))
    return required


def _published_inventory_paths_locked(root, profile, pending):
    if (not isinstance(profile, dict) or profile.get('schema_version') != 1
            or profile.get('scope') != 'current-only-nonvideo'):
        raise ValueError('Unsupported character publication profile')
    published = _publication_paths(profile.get('files'), 'files')
    selected = _publication_paths(profile.get('character_library_files'), 'character_library_files')
    if not selected <= published:
        raise ValueError('Character publication files must be included in published files')
    if FILES in selected:
        raise ValueError('Character publication cannot inventory its own file inventory')
    for relative in selected:
        if Path(relative).suffix.lower() in LOCAL_VIDEO_EXTENSIONS:
            raise ValueError(f'Video media cannot be a required publication file: {relative}')
        if any(part.casefold() in ('candidates', 'generation-candidates') for part in Path(relative).parts):
            raise ValueError(f'Unselected candidate directory cannot be published: {relative}')
        readable_source(root, relative, pending)
    required = _required_current_library_paths_locked(root, pending)
    if missing := sorted(required - selected):
        raise ValueError(f'Publication omits required adopted library source: {missing[0]}')
    return sorted(selected)


def readable_source(root, relative, pending):
    """Reject live paths and aliases before resolving or opening a source."""
    if not isinstance(relative, str) or Path(relative).is_absolute() or PureWindowsPath(relative).drive:
        raise ValueError(f'Operational path must be root-relative: {relative}')
    base = Path(root).resolve()
    lexical = Path(os.path.abspath(base / relative))
    if not lexical.is_relative_to(base):
        raise ValueError(f'Path leaves library root: {relative}')
    if any(management.contains(prefix.as_posix(), lexical.as_posix()) for prefix in pending):
        raise ValueError(f'Library source is inside an active generation tree: {relative}')
    path = base
    for part in lexical.relative_to(base).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f'Library source path must not contain a symlink: {relative}')
    return lexical


def _positive_reference(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value > 0)


def _gimmick_geometry(record, size, label):
    if record.get('anchor_kind') not in GIMMICK_ANCHORS:
        raise ValueError(f'Gimmick anchor_kind must be ground, base or center: {label}')
    anchor = record.get('anchor_px')
    if (not isinstance(anchor, list) or len(anchor) != 2
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in anchor)
            or not 0 <= anchor[0] <= size[0] or not 0 <= anchor[1] <= size[1]):
        raise ValueError(f'Invalid gimmick anchor: {label}')
    box = record.get('body_bbox_px')
    if (not isinstance(box, list) or len(box) != 4
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in box)
            or not 0 <= box[0] < box[2] <= size[0] or not 0 <= box[1] < box[3] <= size[1]):
        raise ValueError(f'Invalid gimmick subject bounds: {label}')
    if 'subject_bbox_px' in record and record['subject_bbox_px'] != box:
        raise ValueError(f'Gimmick subject/body bounds differ: {label}')
    if not _positive_reference(record.get('reference_height_px')):
        raise ValueError(f'Invalid gimmick reference height: {label}')


def _validate_gimmick_registration(registration, identity):
    if (registration.get('schema_version') != 3 or registration.get('category') != 'gimmick'
            or registration.get('character_id') != identity):
        raise ValueError(f'Gimmick registration identity/category/schema differs: {identity}')
    reference = registration.get('common_reference_height_px')
    if not _positive_reference(reference):
        raise ValueError(f'Invalid gimmick common reference height: {identity}')
    frames = registration.get('frames')
    if not isinstance(frames, list) or not frames:
        raise ValueError(f'Gimmick registration needs frames: {identity}')
    sheets = {}
    if 'sheets' in registration:
        declared = registration['sheets']
        if not isinstance(declared, list) or not declared:
            raise ValueError(f'Gimmick sheets must be nonempty: {identity}')
        for sheet in declared:
            sheet_id = sheet.get('id')
            if (not isinstance(sheet_id, str) or not sheet_id or sheet_id in sheets
                    or not _positive_reference(sheet.get('reference_height_px'))):
                raise ValueError(f'Invalid or duplicate gimmick sheet identifier/reference: {identity}')
            sheets[sheet_id] = sheet
    ids = set()
    for frame in frames:
        pose_id = frame.get('id')
        if not isinstance(pose_id, str) or not re.fullmatch(r'[a-z][a-z0-9_-]*', pose_id) or pose_id in ids:
            raise ValueError(f'Invalid or duplicate gimmick pose id: {identity}')
        ids.add(pose_id)
        size = frame.get('size_px')
        if (not isinstance(size, list) or len(size) != 2
                or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in size)):
            raise ValueError(f'Invalid gimmick frame size: {identity}/{pose_id}')
        _gimmick_geometry(frame, size, identity + '/' + pose_id)
        sheet_reference = reference
        if sheets:
            sheet = sheets.get(frame.get('sheet_id'))
            if sheet is None:
                raise ValueError(f'Unknown gimmick source sheet: {identity}/{pose_id}')
            if (frame.get('source_sheet') != sheet['source_sheet']
                    or frame.get('source_sheet_sha256') != sheet['source_sheet_sha256']):
                raise ValueError(f'Gimmick pose source differs from its sheet: {identity}/{pose_id}')
            sheet_reference = sheet['reference_height_px']
        if frame['reference_height_px'] != sheet_reference:
            raise ValueError(f'Gimmick poses must share a calibrated reference height: {identity}')
    canonical = registration.get('canonical_neutral', {})
    neutral_id = canonical.get('frame_id', canonical.get('source_frame_id'))
    matches = [frame for frame in frames
               if (neutral_id is None or frame['id'] == neutral_id)
               and frame.get('sha256') == canonical.get('sha256')
               and frame['reference_height_px'] == reference]
    if not matches:
        raise ValueError(f'Gimmick canonical neutral is not bound to a source frame/reference: {identity}')
    clips = registration.get('clips', {})
    if not isinstance(clips, dict):
        raise ValueError(f'Gimmick clips must be named records: {identity}')
    for name, clip in clips.items():
        if not isinstance(name, str) or not name or not isinstance(clip, dict):
            raise ValueError(f'Invalid gimmick clip: {identity}')
        targets, durations = clip.get('frames'), clip.get('durations_ms')
        if (not isinstance(targets, list) or not targets
                or any(not isinstance(target, str) or target not in ids for target in targets)):
            raise ValueError(f'Gimmick clip references an unknown pose: {identity}/{name}')
        if (not isinstance(durations, list) or len(durations) != len(targets)
                or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in durations)
                or not isinstance(clip.get('loop'), bool)):
            raise ValueError(f'Invalid gimmick clip timing: {identity}/{name}')
    return matches[0]


def _gimmick_index_item_locked(root, selected, pending):
    identity = selected.get('id')
    if (not isinstance(identity, str) or not re.fullmatch(r'[a-z][a-z0-9-]*', identity)
            or selected.get('category') != 'gimmick'
            or not all(isinstance(selected.get(key), str) and selected[key] for key in ('name_ja', 'name_en'))):
        raise ValueError('Gimmick collection needs explicit id, names and category')
    prefix = 'assets/library/characters/' + identity + '/'
    def source_path(relative):
        if not isinstance(relative, str) or not relative.startswith(prefix):
            raise ValueError(f'Gimmick source must stay in its asset directory: {identity}')
        path = readable_source(root, relative, pending)
        if not path.relative_to(Path(root).resolve()).as_posix().startswith(prefix):
            raise ValueError(f'Gimmick source must stay in its asset directory: {identity}')
        return path
    manifest_relative = selected['source_manifest_path']
    manifest_path = source_path(manifest_relative)
    if sha(manifest_path) != selected['source_manifest_sha256']:
        raise ValueError(f'Gimmick source manifest changed: {identity}')
    manifest = read(manifest_path)
    if manifest.get('category') != 'gimmick' or manifest.get('character_id') != identity:
        raise ValueError(f'Gimmick source manifest identity differs: {identity}')
    render = manifest['render_registration']
    neutral_relative = render['neutral_path']
    if not neutral_relative.startswith('assets/'):
        neutral_relative = (Path(manifest_relative).parent / neutral_relative).as_posix()
    neutral_path = source_path(neutral_relative)
    if sha(neutral_path) != render['neutral_sha256']:
        raise ValueError(f'Gimmick neutral changed: {identity}')
    with Image.open(neutral_path) as image:
        size = list(image.size)
    if render['size_px'] != size:
        raise ValueError(f'Gimmick neutral size differs: {identity}')
    neutral = {'path': neutral_relative, 'sha256': render['neutral_sha256'],
               'source_size_px': size, 'image_region_px': [0, 0, *size],
               'body_bbox_px': render['body_bbox_px'], 'subject_bbox_px': render['body_bbox_px'],
               'anchor_px': render['neutral_anchor_px'], 'anchor_kind': render['anchor_kind'],
               'reference_height_px': render['neutral_natural_height_px'],
               'source_manifest': manifest_relative, 'source_manifest_sha256': selected['source_manifest_sha256'],
               'coordinate_space': 'original subject PNG canvas; reference height and anchor are explicitly calibrated'}
    _gimmick_geometry(neutral, size, identity + '/neutral')
    registration_relative = selected['registration']
    registration_path = source_path(registration_relative)
    if sha(registration_path) != selected['registration_sha256']:
        raise ValueError(f'Gimmick registration changed: {identity}')
    registration = read(registration_path)
    neutral_frame = _validate_gimmick_registration(registration, identity)
    canonical = registration['canonical_neutral']
    if (canonical['path'] != neutral_relative or canonical['sha256'] != neutral['sha256']
            or registration['common_reference_height_px'] != neutral['reference_height_px']):
        raise ValueError(f'Gimmick canonical neutral differs from selected source: {identity}')
    if (neutral_frame['size_px'] != size or neutral_frame['anchor_px'] != neutral['anchor_px']
            or neutral_frame['anchor_kind'] != neutral['anchor_kind']
            or neutral_frame['body_bbox_px'] != neutral['body_bbox_px']):
        raise ValueError(f'Gimmick neutral geometry differs from its source frame: {identity}')
    if registration.get('sheets'):
        for sheet in registration['sheets']:
            source_path(sheet['source_sheet'])
    else:
        source_path(registration['source_sheet'])
    poses = {}
    for frame in registration['frames']:
        source_path(frame['path'])
        poses[frame['id']] = {key: frame[key] for key in
            ('path', 'sha256', 'size_px', 'anchor_px', 'anchor_kind', 'body_bbox_px', 'tail_bbox_px', 'reference_height_px')}
        poses[frame['id']]['subject_bbox_px'] = frame['body_bbox_px']
        if registration.get('sheets'):
            poses[frame['id']].update(frame_id=frame['id'], sheet_id=frame['sheet_id'],
                                      source_sheet=frame['source_sheet'], source_sheet_sha256=frame['source_sheet_sha256'])
    for key in ('preview', 'motion_preview'):
        source_path(selected[key])
    return {'id': identity, 'name_ja': selected['name_ja'], 'name_en': selected['name_en'],
            'category': 'gimmick', 'availability': 'reviewed-neutral-and-gimmick-key-poses',
            'neutral': neutral, 'comparison_body_height_px': neutral['reference_height_px'],
            'key_poses': {'version': registration.get('version', 'v001'),
                          'namespace': 'gimmick/', 'registration': registration_relative,
                          'registration_sha256': selected['registration_sha256'],
                          'common_reference_height_px': registration['common_reference_height_px'],
                          'sheet_reference_heights_px': {sheet['id']: sheet['reference_height_px']
                                                        for sheet in registration.get('sheets', [])},
                          'reference_height_policy': 'One fixed calibrated reference per native source sheet; common reference describes the selected canonical neutral. Never fit individual pose bounds.',
                          'coordinate_space': 'individual exact cell PNG', 'poses': poses,
                          'preview': selected['preview'], 'motion_preview': selected['motion_preview'],
                          'clips': registration.get('clips', {})}}


def _adoption_keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f'Invalid explicit adoption fields: {label}')


def _adoption_geometry(record, size, label, *, neutral=False):
    if (not isinstance(size, list) or len(size) != 2
            or any(type(value) is not int or value <= 0 for value in size)):
        raise ValueError(f'Invalid adopted PNG size: {label}')
    body, anchor, reference = (record.get(key) for key in
                               ('body_bbox_px', 'anchor_px', 'reference_height_px'))
    def finite(values, count):
        return (isinstance(values, list) and len(values) == count
                and all(not isinstance(value, bool) and isinstance(value, (int, float))
                        and math.isfinite(value) for value in values))
    if (not finite(body, 4) or not 0 <= body[0] < body[2] <= size[0]
            or not 0 <= body[1] < body[3] <= size[1]
            or not finite(anchor, 2) or not 0 <= anchor[0] <= size[0]
            or not 0 <= anchor[1] <= size[1]
            or isinstance(reference, bool) or not isinstance(reference, (int, float))
            or not math.isfinite(reference) or reference <= 0):
        raise ValueError(f'Invalid adopted geometry: {label}')
    if neutral:
        region = record.get('image_region_px')
        if (not isinstance(region, list) or len(region) != 4
                or any(type(value) is not int for value in region)
                or not 0 <= region[0] <= body[0] < body[2] <= region[2] <= size[0]
                or not 0 <= region[1] <= body[1] < body[3] <= region[3] <= size[1]
                or not region[0] <= anchor[0] <= region[2]
                or not region[1] <= anchor[1] <= region[3]
                or reference != body[3] - body[1]):
            raise ValueError(f'Invalid adopted neutral crop/reference: {label}')


def _read_adoptions_locked(root, pending):
    """Read explicit selections without rewriting historical style/collection QA."""
    config = readable_source(root, ADOPTIONS, pending)
    if not config.is_file():
        return {}
    document = read(config)
    _adoption_keys(document, ('schema_version', 'kind', 'adoptions'), ADOPTIONS)
    if (type(document['schema_version']) is not int or document['schema_version'] != 1
            or document['kind'] != 'explicit-character-adoptions'
            or not isinstance(document['adoptions'], list)):
        raise ValueError('Unsupported explicit character adoption document')

    def source(relative, expected=None):
        _publication_paths([relative], 'explicit adoption')
        if Path(relative).suffix.lower() in LOCAL_VIDEO_EXTENSIONS:
            raise ValueError('Video cannot be a required explicit adoption source/evidence')
        path = readable_source(root, relative, pending)
        if not path.is_file():
            raise ValueError(f'Explicit adoption source is missing: {relative}')
        if expected is not None:
            if (not isinstance(expected, str) or re.fullmatch(r'[a-f0-9]{64}', expected) is None
                    or sha(path) != expected):
                raise ValueError(f'Explicit adoption SHA-256 differs: {relative}')
        return path

    adopted = {}
    neutral_keys = ('path', 'sha256', 'source_size_px', 'image_region_px',
                    'body_bbox_px', 'anchor_px', 'reference_height_px')
    for entry in document['adoptions']:
        _adoption_keys(entry, ('id', 'status', 'neutral', 'eyecatch', 'selection_evidence'), 'entry')
        identity = entry['id']
        if not isinstance(identity, str) or identity not in NAMES or identity in adopted:
            raise ValueError(f'Unknown or duplicate explicit adoption identity: {identity}')
        if entry['status'] != 'adopted':
            raise ValueError(f'Explicit character selection must be adopted: {identity}')
        prefix = f'assets/library/characters/{identity}/'
        neutral = entry['neutral']
        _adoption_keys(neutral, neutral_keys, identity + '/neutral')
        neutral_path = source(neutral['path'], neutral['sha256'])
        if not neutral['path'].startswith(prefix) or '/current/' in neutral['path']:
            raise ValueError('Explicit neutral must use its own original character source')
        _adoption_geometry(neutral, neutral['source_size_px'], identity, neutral=True)
        with Image.open(neutral_path) as image:
            if (image.mode != 'RGBA' or image.format != 'PNG'
                    or list(image.size) != neutral['source_size_px']):
                raise ValueError(f'Explicit neutral PNG differs: {identity}')
            alpha = image.getchannel('A')
            bounds = alpha.point(lambda value: 255 if value >= 8 else 0).getbbox()
            if (bounds is None or alpha.getextrema()[0] != 0 or alpha.getextrema()[1] < 240
                    or min(bounds[0], bounds[1], image.width-bounds[2], image.height-bounds[3]) < 2):
                raise ValueError(f'Explicit neutral is empty, clipped or not transparent: {identity}')

        movement = entry['eyecatch']
        _adoption_keys(movement, ('version', 'registration', 'registration_sha256',
                                  'preview', 'motion_preview'), identity + '/eyecatch')
        if not isinstance(movement['version'], str) or re.fullmatch(r'v[0-9]+', movement['version']) is None:
            raise ValueError('Invalid explicit eye-catch version')
        registration = read(source(movement['registration'], movement['registration_sha256']))
        for key in ('registration', 'preview', 'motion_preview'):
            if not isinstance(movement[key], str) or not movement[key].startswith(prefix) or '/current/' in movement[key]:
                raise ValueError('Explicit eye-catch must use its own original character sources')
            source(movement[key])
        if (type(registration.get('schema_version')) is not int or registration['schema_version'] not in (2, 3)
                or registration.get('kind') != 'generated-character-eyecatch-key-pose-stock'
                or registration.get('character_id') != identity
                or registration.get('version') != movement['version']
                or registration.get('status') != 'stocked-and-assistant-reviewed'
                or registration.get('category', 'character') != 'character'):
            raise ValueError(f'Explicit eye-catch registration identity/status differs: {identity}')
        canonical = registration.get('canonical_neutral', {})
        if not isinstance(canonical, dict) or any(canonical.get(key) != neutral[key] for key in neutral_keys):
            raise ValueError(f'Explicit eye-catch canonical neutral differs: {identity}')
        if (not isinstance(registration.get('sheets'), list) or not registration['sheets']
                or not isinstance(registration.get('frames'), list) or not registration['frames']):
            raise ValueError('Explicit eye-catch needs source sheets and frames')
        sheet_sizes = {}
        for sheet in registration['sheets']:
            if (not isinstance(sheet, dict) or not isinstance(sheet.get('id'), str)
                    or not sheet['id'] or not {'source_sheet', 'source_sheet_sha256', 'reference_height_px'} <= set(sheet)):
                raise ValueError('Invalid explicit eye-catch source sheet')
            sheet_path = source(sheet['source_sheet'], sheet['source_sheet_sha256'])
            if not sheet['source_sheet'].startswith(prefix) or '/current/' in sheet['source_sheet']:
                raise ValueError('Explicit source sheet must use its own original character source')
            with Image.open(sheet_path) as image:
                if image.format != 'PNG' or image.mode != 'RGBA':
                    raise ValueError('Explicit pose source sheet must be RGBA PNG')
                sheet_sizes[sheet['id']] = image.size
        for frame in registration['frames']:
            if (not isinstance(frame, dict) or not isinstance(frame.get('id'), str)
                    or re.fullmatch(r'[a-z][a-z0-9_-]*', frame['id']) is None
                    or not {'path', 'sha256', 'size_px', 'sheet_id', 'source_sheet', 'source_sheet_sha256',
                            'crop_from_sheet_xyxy', 'body_bbox_px', 'anchor_px', 'reference_height_px',
                            'tail_bbox_px'} <= set(frame)):
                raise ValueError('Invalid explicit eye-catch frame')
        sheet_ids = {sheet['id'] for sheet in registration['sheets']}
        if any(not isinstance(frame['sheet_id'], str) or frame['sheet_id'] not in sheet_ids
               for frame in registration['frames']):
            raise ValueError('Explicit pose refers to an unknown source sheet')
        for frame in registration['frames']:
            crop = frame['crop_from_sheet_xyxy']
            width, height = sheet_sizes[frame['sheet_id']]
            if (not isinstance(crop, list) or len(crop) != 4
                    or any(type(value) is not int for value in crop)
                    or not 0 <= crop[0] < crop[2] <= width or not 0 <= crop[1] < crop[3] <= height):
                raise ValueError('Invalid explicit pose native crop')
        frames = _verify_pose_registration_locked(root, registration, identity, pending=pending)
        neutral_frames = [frame for frame in frames if frame['id'] == 'neutral']
        if len(neutral_frames) != 1:
            raise ValueError('Explicit eye-catch must include one canonical neutral frame')
        for frame in frames:
            if not frame['path'].startswith(prefix) or '/current/' in frame['path']:
                raise ValueError('Explicit pose must use its own original character source')
            _adoption_geometry(frame, frame['size_px'], identity + '/' + frame['id'])
            if frame['tail_bbox_px'] is not None:
                _adoption_geometry({**frame, 'body_bbox_px': frame['tail_bbox_px']},
                                   frame['size_px'], identity + '/tail')
            with Image.open(source(frame['path'])) as image:
                if image.format != 'PNG':
                    raise ValueError('Explicit pose must be a PNG')
        frame = neutral_frames[0]
        if (frame['sha256'] != neutral['sha256'] or frame['size_px'] != neutral['source_size_px']
                or neutral['image_region_px'] != [0, 0, *neutral['source_size_px']]
                or any(frame[key] != neutral[key] for key in ('body_bbox_px', 'anchor_px', 'reference_height_px'))):
            raise ValueError('Explicit eye-catch neutral frame geometry differs from its canonical source')
        clips = registration.get('clips')
        if not isinstance(clips, dict) or not clips:
            raise ValueError('Explicit eye-catch needs named clips')
        names = {frame['id'] for frame in frames}
        for name, clip in clips.items():
            if not isinstance(name, str) or re.fullmatch(r'[a-z][a-z0-9_-]*', name) is None:
                raise ValueError('Invalid explicit eye-catch clip name')
            sequence = clip.get('frames') if isinstance(clip, dict) else clip
            if (not isinstance(sequence, list) or not sequence
                    or any(not isinstance(name, str) or name not in names for name in sequence)):
                raise ValueError('Explicit eye-catch clip refers to an unknown pose')

        evidence = entry['selection_evidence']
        if not isinstance(evidence, list) or not evidence:
            raise ValueError('Explicit adoption needs selection evidence')
        seen = set()
        for item in evidence:
            _adoption_keys(item, ('path', 'sha256'), identity + '/selection_evidence')
            source(item['path'], item['sha256'])
            if item['path'] in seen:
                raise ValueError('Duplicate explicit selection evidence')
            seen.add(item['path'])
        adopted[identity] = entry
    return adopted


def _stock_identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_-]*', value):
        raise ValueError(f'Invalid supplemental stock identifier: {value}')
    return value


def _stock_owned_path(root, relative, identity, pending):
    _publication_paths([relative], 'supplemental source')
    if not relative.startswith(f'assets/library/characters/{identity}/') or '/current/' in relative:
        raise ValueError('Supplemental stock must use its own character source')
    return readable_source(root, relative, pending)


def _stock_picture_locked(root, record, identity, pending, *, icon=False):
    """Validate native adopted PNGs without inventing body registration for icons."""
    path = _stock_owned_path(root, record['path'], identity, pending)
    if '/current/' in record['path'] or sha(path) != record['sha256']:
        raise ValueError('Supplemental PNG changed or points into current/')
    with Image.open(path) as image:
        size = list(image.size)
        if image.format != 'PNG' or image.mode != 'RGBA':
            raise ValueError('Supplemental stock must use native RGBA PNGs')
        alpha = image.getchannel('A')
        visible = alpha.point(lambda a: 255 if a >= 8 else 0).getbbox()
        if (alpha.getextrema()[0] != 0 or alpha.getextrema()[1] < 240 or visible is None
                or min(visible[0], visible[1], size[0]-visible[2], size[1]-visible[3]) < 2):
            raise ValueError('Supplemental stock is empty, opaque or clipped')
    if record.get('size_px' if icon else 'source_size_px') != size:
        raise ValueError('Supplemental stock size differs from PNG')
    if icon:
        box = record.get('subject_bbox_px')
        if (record.get('role') != 'face-icon' or not isinstance(box, list) or len(box) != 4
                or any(type(v) is not int for v in box)
                or not 0 <= box[0] < box[2] <= size[0] or not 0 <= box[1] < box[3] <= size[1]
                or box[0] > visible[0] or box[1] > visible[1] or box[2] < visible[2] or box[3] < visible[3]
                or any(key in record for key in ('body_bbox_px', 'reference_height_px', 'anchor_px'))):
            raise ValueError('Face icon needs separate subject bounds and no body registration')
    else:
        _adoption_geometry(record, size, record['path'], neutral=True)
    return dict(record)


def _supplement_pose_set_locked(root, selected, neutral, identity, pending):
    namespace = _stock_identifier(selected['namespace'])
    if namespace in {'basic', 'expanded', 'eyecatch', 'gimmick', 'neutral', 'icons'}:
        raise ValueError('Supplemental pose namespace collides with a reserved namespace')
    relative = selected['registration']
    path = _stock_owned_path(root, relative, identity, pending)
    if sha(path) != selected['registration_sha256']:
        raise ValueError('Supplemental pose registration changed')
    registration = read(path)
    if registration.get('character_id') != identity:
        raise ValueError('Supplemental pose registration has a different character identity')
    if (registration.get('canonical_neutral', {}).get('path') != neutral['path']
            or registration.get('canonical_neutral', {}).get('sha256') != neutral['sha256']):
        raise ValueError('Supplemental poses differ from the adopted neutral')
    for source in registration.get('sheets') or [registration]:
        _stock_owned_path(root, source['source_sheet'], identity, pending)
    for frame in registration['frames']:
        _stock_owned_path(root, frame['path'], identity, pending)
    frames = _verify_pose_registration_locked(root, registration, identity, pending=pending)
    if not frames:
        raise ValueError('Supplemental pose set must not be empty')
    poses = {}
    for frame in frames:
        _stock_identifier(frame['id'])
        _adoption_geometry(frame, frame['size_px'], identity+'/'+frame['id'])
        poses[frame['id']] = {key: value for key, value in frame.items() if key != 'id'}
        poses[frame['id']]['frame_id'] = frame['id']
    clips = registration.get('clips', {})
    if not isinstance(clips, dict):
        raise ValueError('Supplemental clips must be named')
    for name, value in clips.items():
        _stock_identifier(name)
        sequence = value.get('frames') if isinstance(value, dict) else value
        if not isinstance(sequence, list) or not sequence or any(frame not in poses for frame in sequence):
            raise ValueError('Supplemental clip refers to an unknown pose')
    return {'namespace': namespace, 'registration': relative,
            'registration_sha256': selected['registration_sha256'], 'poses': poses, 'clips': clips,
            'coordinate_space': 'individual exact cell PNG',
            'reference_height_policy': 'Use each source sheet calibration unchanged; scene relative scale is separate.'}


def _apply_supplement_locked(root, characters, pending):
    """Optional reviewed stock can extend identities without rewriting historical QA."""
    path = readable_source(root, SUPPLEMENT, pending)
    if not path.is_file():
        return False
    document = read(path)
    if (document.get('schema_version') != 1 or document.get('status') != 'stocked-and-assistant-reviewed'
            or not isinstance(document.get('items'), list) or not document.get('review_evidence')):
        raise ValueError('Only an explicitly reviewed supplemental stock collection may be adopted')
    for evidence in document['review_evidence']:
        if sha(readable_source(root, evidence['path'], pending)) != evidence['sha256']:
            raise ValueError('Supplemental stock review evidence changed')
    known = {item['id']: item for item in characters}
    seen = set()
    for selected in document['items']:
        identity = _stock_identifier(selected['id'])
        if identity in seen:
            raise ValueError('Duplicate supplemental stock identity')
        seen.add(identity)
        if identity in known:
            item = known[identity]
            if 'neutral' in selected or selected.get('neutral_reference') != {
                    key: item['neutral'][key] for key in ('path', 'sha256')}:
                raise ValueError('Supplemental stock must preserve the existing adopted neutral')
        else:
            if not all(isinstance(selected.get(key), str) and selected[key] for key in ('name_ja', 'name_en')):
                raise ValueError('New supplemental stock needs explicit names')
            neutral = _stock_picture_locked(root, selected['neutral'], identity, pending)
            item = {'id': identity, 'name_ja': selected['name_ja'], 'name_en': selected['name_en'],
                    'category': 'character', 'availability': 'reviewed-supplemental-stock', 'neutral': neutral}
            characters.append(item)
            known[identity] = item
        pose_sets = selected.get('pose_sets', [])
        if not isinstance(pose_sets, list):
            raise ValueError('Supplemental pose sets must be a list')
        namespaces = {block['namespace'] for block in item.get('pose_sets', [])}
        for source in pose_sets:
            block = _supplement_pose_set_locked(root, source, item['neutral'], identity, pending)
            if block['namespace'] in namespaces:
                raise ValueError('Duplicate supplemental pose namespace')
            namespaces.add(block['namespace'])
            item.setdefault('pose_sets', []).append(block)
        if selected.get('icons'):
            if item.get('icons') or not isinstance(selected['icons'], dict):
                raise ValueError('Supplemental icons cannot replace existing icons')
            item['icons'] = {_stock_identifier(name): _stock_picture_locked(root, record, identity, pending, icon=True)
                             for name, record in selected['icons'].items()}
        if 'scene_relative_scale' in selected:
            scale = selected['scene_relative_scale']
            ratio = scale.get('body_height_ratio') if isinstance(scale, dict) else None
            if (not isinstance(scale, dict) or set(scale) != {'relative_to', 'body_height_ratio'}
                    or scale['relative_to'] == identity or not isinstance(scale['relative_to'], str)
                    or isinstance(ratio, bool) or not isinstance(ratio, (int, float))
                    or not math.isfinite(ratio) or ratio <= 0 or 'scene_relative_scale' in item):
                raise ValueError('Invalid supplemental scene relative scale')
            item['scene_relative_scale'] = dict(scale)
        item['supplemental_collection'] = SUPPLEMENT
    for item in characters:
        if item.get('scene_relative_scale', {}).get('relative_to', item['id']) not in known:
            raise ValueError('Scene relative scale refers to an unknown character')
    return True


def build_index(root):
    with reservation_snapshot(root) as root:
        return _build_index_locked(root)


def _build_index_locked(root):
    pending = pending_generation_roots(root)
    def source_path(relative):
        return readable_source(root, relative, pending)
    def registration_source(relative):
        registration = read(source_path(relative))
        if registration.get('source_sheet'):
            source_path(registration['source_sheet'])
        for sheet in registration.get('sheets', []):
            source_path(sheet['source_sheet'])
        for frame in registration['frames']:
            source_path(frame['path'])
        return registration
    stock, motions, style = [read(source_path(path)) for path in (STOCK, MOTIONS, STYLE)]
    adoptions = _read_adoptions_locked(root, pending)
    selected = {item['id']: item for item in stock['items']}
    movements = {item['id']: item for item in motions['items']}
    records = {item['id']: item for item in style['records']}
    expansion = read(source_path(EXPANSION)) if source_path(EXPANSION).is_file() else None
    additions = {item['id']: item for item in expansion['items']} if expansion else {}
    if expansion and expansion.get('status') != 'stocked-and-assistant-reviewed':
        raise ValueError('Only an explicitly reviewed expansion may be adopted')
    eyecatches = read(source_path(EYECATCHES)) if source_path(EYECATCHES).is_file() else None
    eye_additions = {item['id']: item for item in eyecatches['items']} if eyecatches else {}
    eye_additions.update({identity: entry['eyecatch'] for identity, entry in adoptions.items()})
    if eyecatches and eyecatches.get('status') != 'stocked-and-assistant-reviewed':
        raise ValueError('Only an explicitly reviewed eye-catch collection may be adopted')
    characters = []
    for identity, (ja, en) in NAMES.items():
        source = adoptions[identity]['neutral'] if identity in adoptions else records[identity]
        with Image.open(readable_source(root, source['path'], pending)) as image:
            size = list(image.size)
        region = source.get('image_region_px', source.get('crop_px', [0, 0, *size]))
        item = {
            'id': identity, 'name_ja': ja, 'name_en': en, 'category': 'character',
            'availability': 'reviewed-neutral-and-six-key-poses' if identity in selected else 'reviewed-neutral-and-legacy-episode-assets',
            'neutral': {'path': source['path'], 'sha256': source['sha256'], 'source_size_px': size,
                        'image_region_px': region, 'body_bbox_px': source['body_bbox_px'],
                        'anchor_px': source['anchor_px'],
                        'reference_height_px': source.get('reference_height_px', source['body_bbox_px'][3] - source['body_bbox_px'][1]),
                        'coordinate_space': 'original source PNG canvas; subtract image_region origin when loading a cropped neutral'},
            'comparison_body_height_px': records[identity]['height_px'],
        }
        if identity in selected:
            canonical = selected[identity]
            movement = movements[identity]
            registration = registration_source(movement['registration'])
            item['canonical_source_version'] = canonical['source_version']
            if identity not in adoptions:
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
        if identity in adoptions:
            item['adoption_selection'] = {'path': ADOPTIONS,
                                          'selection_evidence': adoptions[identity]['selection_evidence']}
        if identity in additions:
            movement = additions[identity]
            if sha(readable_source(root, movement['registration'], pending)) != movement['registration_sha256']:
                raise ValueError(f'Expansion registration changed: {identity}')
            registration = registration_source(movement['registration'])
            if (registration.get('canonical_neutral', {}).get('path') != item['neutral']['path']
                    or registration.get('canonical_neutral', {}).get('sha256') != item['neutral']['sha256']):
                raise ValueError(f'Expansion canonical neutral differs from adopted source: {identity}')
            # Add an explicit namespace. Existing adapters index key_poses and
            # its common scale directly; changing that block would silently
            # change concurrent episodes merely because new stock was saved.
            poses = {}
            for frame in registration['frames']:
                pose_id = frame['id']
                poses[pose_id] = {key: frame[key] for key in
                    ['path', 'sha256', 'size_px', 'anchor_px', 'body_bbox_px', 'tail_bbox_px', 'reference_height_px']}
                poses[pose_id].update(sheet_id=frame['sheet_id'], frame_id=frame['id'])
            item['expanded_key_poses'] = {
                'version': 'v002', 'registration': movement['registration'],
                'registration_sha256': movement['registration_sha256'],
                'namespace': 'expanded/', 'coordinate_space': 'individual exact cell PNG',
                'reference_height_policy': 'One calibrated standing reference height per source sheet; each frame carries its sheet reference. Never fit each pose.',
                'sheet_reference_heights_px': {sheet['id']: sheet['reference_height_px'] for sheet in registration['sheets']},
                'poses': poses, 'preview': movement['preview'], 'motion_preview': movement['motion_preview'],
            }
            item['availability'] = 'reviewed-neutral-and-expanded-key-poses'
            item['expansion_collection'] = EXPANSION
        if identity in eye_additions:
            movement = eye_additions[identity]
            if sha(readable_source(root, movement['registration'], pending)) != movement['registration_sha256']:
                raise ValueError(f'Eye-catch registration changed: {identity}')
            registration = registration_source(movement['registration'])
            if (registration.get('canonical_neutral', {}).get('path') != item['neutral']['path']
                    or registration.get('canonical_neutral', {}).get('sha256') != item['neutral']['sha256']):
                raise ValueError(f'Eye-catch canonical neutral differs from adopted source: {identity}')
            # Add an explicit namespace. Existing adapters index key_poses and
            # its common scale directly; changing that block would silently
            # change concurrent episodes merely because new stock was saved.
            poses = {}
            for frame in registration['frames']:
                pose_id = frame['id']
                poses[pose_id] = {key: frame[key] for key in
                    ['path', 'sha256', 'size_px', 'anchor_px', 'body_bbox_px', 'tail_bbox_px', 'reference_height_px']}
                poses[pose_id].update(sheet_id=frame['sheet_id'], frame_id=frame['id'])
            item['eyecatch_key_poses'] = {
                'version': movement.get('version', 'v001'), 'registration': movement['registration'],
                'registration_sha256': movement['registration_sha256'],
                'namespace': 'eyecatch/', 'coordinate_space': 'individual exact cell PNG',
                'reference_height_policy': 'One calibrated standing reference height per source sheet; each frame carries its sheet reference. Never fit each pose.',
                'sheet_reference_heights_px': {sheet['id']: sheet['reference_height_px'] for sheet in registration['sheets']},
                'poses': poses, 'preview': movement['preview'], 'motion_preview': movement['motion_preview'],
                'clips': registration.get('clips', {}),
            }
            item['availability'] = 'reviewed-neutral-with-supplemental-eyecatches'
            item['eyecatch_collection'] = ADOPTIONS if identity in adoptions else EYECATCHES
        characters.append(item)
    gimmicks = read(source_path(GIMMICKS)) if source_path(GIMMICKS).is_file() else None
    if gimmicks is not None:
        if (not isinstance(gimmicks, dict) or gimmicks.get('schema_version') != 1
                or gimmicks.get('status') != 'stocked-and-assistant-reviewed'
                or not isinstance(gimmicks.get('items'), list)):
            raise ValueError('Only an explicitly reviewed gimmick collection may be adopted')
        known = {item['id'] for item in characters}
        for selected_gimmick in gimmicks['items']:
            item = _gimmick_index_item_locked(root, selected_gimmick, pending)
            if item['id'] in known:
                raise ValueError(f'Duplicate character/gimmick identity: {item["id"]}')
            known.add(item['id'])
            characters.append(item)
    has_supplement = _apply_supplement_locked(root, characters, pending)
    index = {
        'schema_version': 1, 'kind': 'portable-character-library-index',
        'path_base': 'library-root', 'guide': 'assets/library/README.md',
        'agent_instructions': 'assets/library/AGENTS.md',
        'coordinate_units': 'source pixels; xyxy boxes use exclusive right/bottom',
        'selection_policy': 'Use these explicit adopted paths, never the largest version number or an unselected trial.',
        'source_collections': [{'path': path, 'sha256': sha(readable_source(root, path, pending))} for path in
                               ([STOCK, MOTIONS] + ([EXPANSION] if expansion else [])
                                + ([EYECATCHES] if eyecatches else []) + ([GIMMICKS] if gimmicks is not None else [])
                                + ([SUPPLEMENT] if has_supplement else [])
                                + ([ADOPTIONS] if adoptions else []))],
        'usage_rules': ['Preserve the canonical face, palette, texture, contour and species markings.',
                        'Use target_body_height / reference_height as one isotropic scale for all poses from a calibrated source sheet; never fit individual poses.',
                        'Align the anatomical foot anchor; do not fit each pose bounding box or long tail footprint.',
                        'Saved PNG alpha and pixels are originals or lossless cell extractions. Alpha254 is valid.',
                        'Absolute generation/QA paths are historical records, not runtime dependencies.',
                        'Peck keys are downward gestures; exact beak/ground contact is not guaranteed.',
                        'New expansion poses require expanded/<pose>; unprefixed poses and the canonical neutral retain their original selections.',
                        'Eye-catch poses require eyecatch/<pose>; prior original and expanded selections are unchanged.',
                        'Key poses are reviewed stock. Actual episode timing, clearance and continuous movement need scene review.'],
        'characters': characters,
    }
    if adoptions:
        index['usage_rules'].append(
            'Explicit approvals in catalogs/character-adoptions-v1.json select replacement neutral/eye-catch sources. '
            'Historical selection defaults above apply to entries without an override; episode adapters remain independent.')
    for character in characters:
        for key in ('path', 'source_manifest'):
            if character['neutral'].get(key) is not None:
                readable_source(root, character['neutral'][key], pending)
        for block_name in ('key_poses', 'expanded_key_poses', 'eyecatch_key_poses'):
            block = character.get(block_name)
            if block:
                for key in ('registration', 'preview', 'motion_preview'):
                    if block.get(key) is not None:
                        readable_source(root, block[key], pending)
    return index


def publication_path(root, relative):
    """Keep fixed catalog outputs from resolving onto original asset files."""
    path = Path(root).resolve()
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f'Library publication path must not contain a symlink: {path}')
    return path


def snapshot_files(root, index_payload):
    with reservation_snapshot(root) as root:
        return _snapshot_files_locked(root, index_payload)


def _snapshot_files_locked(root, index_payload):
    """Measure a stable source set while accounting for the proposed index."""
    pending = pending_generation_roots(root)
    files = []
    paths = set(_inventory_paths_locked(root)) | {INDEX}
    # These control files are not source data, even in a caller's broader scan.
    paths -= {FILES, *(path + '.lock' for path in (MANAGEMENT, INDEX, FILES))}
    for relative in sorted(paths):
        if relative == INDEX:
            files.append({'path': INDEX, 'bytes': len(index_payload),
                          'sha256': management.checksum(index_payload)})
        else:
            record, _ = management.file_record(root, readable_source(root, relative, pending))
            record['path'] = relative
            files.append(record)
    return files


def refresh(root):
    root = Path(root).resolve()
    config = publication_path(root, MANAGEMENT)
    index_path, files_path = [publication_path(root, relative) for relative in (INDEX, FILES)]
    guards = {path: management.current_hash(path)
              for path in (config, index_path, files_path, publication_path(root, PUBLICATION))}
    temporary = []
    # reserve/release and management publication use the same config lock.
    # Hold it throughout the scans and publication so new writer claims cannot
    # turn a source set we just measured into an active generation tree.
    with ExitStack() as stack:
        for path in (config, index_path, files_path):
            stack.enter_context(management.lock(path.with_suffix(path.suffix + '.lock')))
        def check_guards():
            for path, expected in guards.items():
                if management.current_hash(path) != expected:
                    raise ValueError(f'Concurrent library/config edit detected: {path}')
        check_guards()
        first_index = _build_index_locked(root)
        first_payload = management.canonical_json(first_index)
        first_files = _snapshot_files_locked(root, first_payload)
        index = _build_index_locked(root)
        index_payload = management.canonical_json(index)
        files = _snapshot_files_locked(root, index_payload)
        check_guards()
        if first_index != index or first_files != files:
            raise ValueError('Library sources changed during scan; reserve active writer roots and retry')
        scope = ('Current adopted character sources and explicitly selected publication files; local historical trials and video media are excluded. Historical metadata references do not make omitted files required.'
                 if publication_path(root, PUBLICATION).is_file() else
                 'Frozen character folders, stock and management evidence, guides and tools; historical trials retained. Video media is optional local evidence and excluded from this inventory and portable ZIP; provenance references are preserved. New active writer roots are pending in the management registry and excluded until handoff.')
        inventory = {'schema_version': 1, 'kind': 'character-library-file-inventory',
                     'path_base': 'library-root', 'files': files,
                     'scope': scope}
        try:
            # Prepare both complete files before replacing either. The two
            # replacements are guarded publication, not a multi-file transaction.
            for path, payload in [(index_path, index_payload), (files_path, management.canonical_json(inventory))]:
                staged = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
                temporary.append(staged)
                with staged.open('xb') as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
            check_guards()
            for relative in (INDEX, FILES):
                publication_path(root, relative)
            for staged, destination in zip(temporary, (index_path, files_path)):
                os.replace(staged, destination)
        finally:
            for staged in temporary:
                if staged.exists():
                    staged.unlink()
    return {'status': 'pass', 'action': 'refresh', 'characters': len(index['characters']), 'files': len(files)}


def load_pose(root, identity, pose='neutral'):
    """Return (RGBA image, local support anchor, calibrated sheet reference height)."""
    with reservation_snapshot(root) as root:
        return _load_pose_locked(root, identity, pose)


def _load_pose_locked(root, identity, pose='neutral', pending=None):
    if pending is None:
        pending = pending_generation_roots(root)
    def source_path(relative):
        return readable_source(root, relative, pending)
    index = read(source_path(INDEX))
    matches = [item for item in index['characters'] if item['id'] == identity]
    if len(matches) != 1:
        raise ValueError(f'Unknown character: {identity}')
    character = matches[0]
    supplemental = {block['namespace']: block for block in character.get('pose_sets', [])}
    if '/' in pose and pose.split('/', 1)[0] in supplemental:
        prefix, name = pose.split('/', 1)
        record = supplemental[prefix]['poses'].get(name)
        if record is None:
            raise ValueError(f'No explicitly adopted {prefix} pose {identity}/{name}')
        with Image.open(source_path(record['path'])) as opened:
            image = opened.copy()
        anchor = record['anchor_px']
    elif pose.startswith(('expanded/', 'eyecatch/', 'gimmick/')):
        prefix, name = pose.split('/', 1)
        block = {'expanded': 'expanded_key_poses', 'eyecatch': 'eyecatch_key_poses', 'gimmick': 'key_poses'}[prefix]
        if prefix == 'gimmick' and character.get('category') != 'gimmick':
            raise ValueError(f'Character is not a gimmick: {identity}')
        record = character.get(block, {}).get('poses', {}).get(name)
        if record is None:
            raise ValueError(f'No explicitly adopted {prefix} pose {identity}/{name}')
        with Image.open(source_path(record['path'])) as opened:
            image = opened.copy()
        anchor = record['anchor_px']
    elif pose == 'neutral':
        record = character['neutral']
        region = record['image_region_px']
        with Image.open(source_path(record['path'])) as opened:
            image = opened.crop(region)
        anchor = [record['anchor_px'][0] - region[0], record['anchor_px'][1] - region[1]]
    else:
        if character.get('category') == 'gimmick':
            raise ValueError(f'Gimmick poses require gimmick/<pose>: {identity}/{pose}')
        record = character.get('key_poses', {}).get('poses', {}).get(pose)
        if record is None:
            raise ValueError(f'No generic reviewed pose {identity}/{pose}; see the library guide for legacy adapters')
        with Image.open(source_path(record['path'])) as opened:
            image = opened.copy()
        anchor = record['anchor_px']
    return image, anchor, record['reference_height_px']


def verify_pose_registration(root, registration, identity):
    """Validate old and multi-sheet registrations independently of pose aliases."""
    with reservation_snapshot(root) as root:
        return _verify_pose_registration_locked(root, registration, identity)


def _verify_pose_registration_locked(root, registration, identity, pending=None):
    if pending is None:
        pending = pending_generation_roots(root)
    def source_path(relative):
        return readable_source(root, relative, pending)
    if registration.get('category') == 'gimmick':
        _validate_gimmick_registration(registration, identity)
    sheets = ({sheet['id']: sheet for sheet in registration['sheets']}
              if registration.get('sheets') else None)
    if sheets and len(sheets) != len(registration['sheets']):
        raise ValueError('Duplicate source sheet identifier')
    seen, output, opened_sheets = set(), [], {}
    for frame in registration['frames']:
        if frame['id'] in seen:
            raise ValueError('Duplicate registered pose identifier')
        seen.add(frame['id'])
        source = sheets[frame['sheet_id']] if sheets else registration
        reference = source['reference_height_px'] if sheets else registration['common_reference_height_px']
        if (isinstance(reference, bool) or not isinstance(reference, (int, float))
                or not math.isfinite(reference) or reference <= 0
                or frame['reference_height_px'] != reference):
            raise ValueError(f'Pose sheet scale changed: {identity}/{frame["id"]}')
        if sheets and (frame['source_sheet'] != source['source_sheet']
                       or frame['source_sheet_sha256'] != source['source_sheet_sha256']):
            raise ValueError('Pose source sheet differs from its calibration')
        sheet_path = source_path(source['source_sheet'])
        if source['source_sheet'] not in opened_sheets:
            if sha(sheet_path) != source['source_sheet_sha256']:
                raise ValueError('Generated source sheet changed')
            with Image.open(sheet_path) as opened:
                opened_sheets[source['source_sheet']] = opened.copy()
        sheet = opened_sheets[source['source_sheet']]
        path = source_path(frame['path'])
        if sha(path) != frame['sha256']:
            raise ValueError('Pose PNG changed')
        with Image.open(path) as image:
            crop = sheet.crop(frame['crop_from_sheet_xyxy'])
            if (image.mode != 'RGBA' or image.size != crop.size or image.size != tuple(frame['size_px'])
                    or image.tobytes() != crop.tobytes()):
                raise ValueError(f'Pose pixels changed: {identity}/{frame["id"]}')
            anchor = frame['anchor_px']
            if (len(anchor) != 2 or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in anchor)
                    or not 0 <= anchor[0] <= image.width or not 0 <= anchor[1] <= image.height):
                raise ValueError('Invalid pose support anchor')
            alpha = image.getchannel('A')
            if alpha.getextrema()[0] != 0 or alpha.getextrema()[1] < 240:
                raise ValueError('Invalid source transparency')
            visible = alpha.point(lambda a: 255 if a >= 8 else 0).getbbox()
            if visible is None or min(visible[0], visible[1], image.width - visible[2], image.height - visible[3]) < 2:
                raise ValueError('Empty or clipped source pose')
            if identity == 'onagadori':
                union = Image.new('L', image.size, 0)
                draw = ImageDraw.Draw(union)
                for box in [frame['body_bbox_px'], frame['tail_bbox_px']]:
                    if box is None:
                        raise ValueError('Onagadori needs separate body and tail bounds')
                    draw.rectangle((box[0], box[1], box[2] - 1, box[3] - 1), fill=255)
                if ImageChops.subtract(alpha.point(lambda a: 255 if a >= 8 else 0), union).getbbox():
                    raise ValueError('Long tail leaves its registered body/tail bounds')
        output.append(frame)
    return output


def verify(root):
    with reservation_snapshot(root) as root:
        return _verify_locked(root)


def _verify_locked(root):
    pending = pending_generation_roots(root)
    def source_path(relative):
        return readable_source(root, relative, pending)
    inventory = read(source_path(FILES))
    expected = {entry['path'] for entry in inventory['files']}
    if expected != set(_inventory_paths_locked(root)):
        raise ValueError('Library inventory is stale; review changes and run refresh')
    for entry in inventory['files']:
        path = source_path(entry['path'])
        if not path.is_file() or path.stat().st_size != entry['bytes'] or sha(path) != entry['sha256']:
            raise ValueError(f'Missing or changed library file: {entry["path"]}')
    index = read(source_path(INDEX))
    frames = 0
    neutral_sources = set()
    for collection in index['source_collections']:
        if sha(source_path(collection['path'])) != collection['sha256']:
            raise ValueError('Adopted collection changed')
    for character in index['characters']:
        neutral = character['neutral']
        if sha(source_path(neutral['path'])) != neutral['sha256']:
            raise ValueError(f'Neutral changed: {character["id"]}')
        neutral_sources.add(source_path(neutral['path']))
        image, anchor, height = _load_pose_locked(root, character['id'], pending=pending)
        if image.mode != 'RGBA' or not (0 <= anchor[0] <= image.width and 0 <= anchor[1] <= image.height) or height <= 0:
            raise ValueError('Invalid neutral geometry')
        for block, prefix in [('key_poses', ''), ('expanded_key_poses', 'expanded/'), ('eyecatch_key_poses', 'eyecatch/')]:
            keys = character.get(block)
            if not keys:
                continue
            if sha(source_path(keys['registration'])) != keys['registration_sha256']:
                raise ValueError('Pose registration changed')
            registration = read(source_path(keys['registration']))
            if character.get('category') == 'gimmick':
                if (keys.get('namespace') != 'gimmick/'
                        or keys.get('clips', {}) != registration.get('clips', {})
                        or keys.get('sheet_reference_heights_px', {}) != {
                            sheet['id']: sheet['reference_height_px'] for sheet in registration.get('sheets', [])}):
                    raise ValueError('Selected gimmick namespace/clips differ from registration')
                _gimmick_geometry(neutral, neutral['source_size_px'], character['id'] + '/neutral')
            if block == 'key_poses' and keys['common_reference_height_px'] != registration['common_reference_height_px']:
                raise ValueError('Original pose common scale differs from registration')
            if block in ('expanded_key_poses', 'eyecatch_key_poses') and keys['sheet_reference_heights_px'] != {
                    sheet['id']: sheet['reference_height_px'] for sheet in registration['sheets']}:
                raise ValueError('Supplemental pose sheet scales differ from registration')
            native_frames = _verify_pose_registration_locked(root, registration, character['id'], pending=pending)
            registered = {frame['id']: frame for frame in native_frames}
            if len(registered) != len(native_frames) or set(registered) != set(keys['poses']):
                raise ValueError('Selected pose coverage differs from registration')
            for pose_id, record in keys['poses'].items():
                frame = registered[pose_id]
                if character.get('category') == 'gimmick' and (
                        record.get('anchor_kind') != frame['anchor_kind']
                        or record.get('subject_bbox_px') != frame['body_bbox_px']):
                    raise ValueError('Selected gimmick geometry differs from registration')
                if (record['path'] != frame['path']
                        or ('frame_id' in record and record['frame_id'] != pose_id)
                        or ('sheet_id' in record and record['sheet_id'] != frame.get('sheet_id'))
                        or (block in ('expanded_key_poses', 'eyecatch_key_poses')
                            and (record.get('frame_id') != pose_id or record.get('sheet_id') != frame.get('sheet_id')))):
                    raise ValueError(f'Pose name or sheet differs from registration: {character["id"]}/{prefix}{pose_id}')
                if any(record[key] != frame[key] for key in
                        ['sha256', 'size_px', 'anchor_px', 'body_bbox_px', 'tail_bbox_px', 'reference_height_px']):
                    raise ValueError(f'Pose geometry differs from registration: {character["id"]}/{prefix}{pose_id}')
                pose_name = ('gimmick/' if character.get('category') == 'gimmick' else prefix) + pose_id
                image, anchor, height = _load_pose_locked(root, character['id'], pose_name, pending=pending)
                if image.mode != 'RGBA' or height != frame['reference_height_px']:
                    raise ValueError('Invalid loaded pose')
                frames += 1
        for keys in character.get('pose_sets', []):
            verified = _supplement_pose_set_locked(root, keys, neutral, character['id'], pending)
            if verified != keys:
                raise ValueError('Selected supplemental pose set differs from its native registration')
            for pose_id, frame in keys['poses'].items():
                image, anchor, height = _load_pose_locked(root, character['id'], keys['namespace']+'/'+pose_id, pending=pending)
                if image.mode != 'RGBA' or height != frame['reference_height_px']:
                    raise ValueError('Invalid loaded supplemental pose')
                frames += 1
        for icon in character.get('icons', {}).values():
            _stock_picture_locked(root, icon, character['id'], pending, icon=True)
    return {'status': 'pass', 'characters': len(index['characters']), 'neutral_png_sources': len(neutral_sources),
            'generic_key_pose_pngs': frames, 'files': len(inventory['files']),
            'bytes': sum(entry['bytes'] for entry in inventory['files']),
            'absolute_provenance_paths_required_for_runtime': False}


def preview(root, identity, pose, height, output, background):
    with reservation_snapshot(root) as root:
        return _preview_locked(root, identity, pose, height, output, background)


def _preview_locked(root, identity, pose, height, output, background):
    if not 1 <= height <= 8192:
        raise ValueError('Preview body height must be 1..8192 pixels')
    output = Path(output).resolve()
    if output.exists() or output.is_relative_to(resolve(root, 'assets/library')):
        raise ValueError('Choose a new preview output outside the source asset library')
    image, anchor, reference = _load_pose_locked(root, identity, pose)
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
    with reservation_snapshot(root) as root:
        return _export_locked(root, output)


def _export_locked(root, output):
    result = _verify_locked(root)
    pending = pending_generation_roots(root)
    def source_path(relative):
        return readable_source(root, relative, pending)
    output = Path(output).resolve()
    if (any(path.exists() for path in [output, output.with_suffix(output.suffix + '.sha256'), output.with_suffix(output.suffix + '.json')])
            or output.is_relative_to(source_path('assets/library'))):
        raise ValueError('Choose a new ZIP output outside the source asset library')
    output.parent.mkdir(parents=True, exist_ok=True)
    inventory = read(source_path(FILES))
    entries = [*inventory['files'], {'path': FILES, 'bytes': source_path(FILES).stat().st_size, 'sha256': sha(source_path(FILES))}]
    sums = {entry['path']: entry['sha256'] for entry in entries}
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for entry in entries:
            archive.write(source_path(entry['path']), 'character-library/' + entry['path'])
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
               'scope': ('Current-only character-library publication; omitted historical trials and videos are optional local records.'
                         if publication_path(root, PUBLICATION).is_file() else
                         'Self-contained character-library bundle; video media and caches are excluded. References to optional local video evidence remain in historical records.')}
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
            with reservation_snapshot(root):
                index = read(publication_path(root, INDEX))
            if args.json:
                print(json.dumps(index, ensure_ascii=False, indent=2))
            else:
                for item in index['characters']:
                    summary = f'{item["id"]}\t{item["name_ja"]}\t{item.get("category", "character")}\tneutral + {len(item.get("key_poses", {}).get("poses", {}))} original poses + {len(item.get("expanded_key_poses", {}).get("poses", {}))} expanded poses + {len(item.get("eyecatch_key_poses", {}).get("poses", {}))} eye-catch poses'
                    for block in item.get('pose_sets', []):
                        summary += f' + {len(block["poses"])} {block["namespace"]} poses'
                    if item.get('icons'):
                        summary += f' + {len(item["icons"])} icons'
                    print(summary)
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
