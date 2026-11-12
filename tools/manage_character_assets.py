"""Inventory character-image batches without moving art or choosing an adoption.

The management config declares ownership/selection. Discovery only finds storage
batches. Active reservations are opaque to scans; writers publish a finished
batch before releasing their reservation. Only this tool's registry/config and
derived human index are written, with atomic replacement and concurrency checks.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path, PureWindowsPath
import re
import sys
import uuid
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
CHARACTERS = 'assets/library/characters'
CONFIG = 'catalogs/character-asset-management-v1.json'
REGISTRY = 'catalogs/character-asset-registry-v1.json'
REGISTRY_KIND = 'non-destructive-character-asset-batch-registry'
HUMAN_INDEX = 'assets/library/character-assets.html'
STATES = {'canonical', 'shared_stock', 'episode_selected', 'preproduction',
          'candidate', 'archive', 'unclassified'}
RASTER = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
VERSION = re.compile(r'(?:^v\d+|.+-v\d+)$')
IGNORED = {'__pycache__', '.DS_Store'}


def canonical_json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def current_hash(path):
    path = Path(path)
    if not path.exists():
        return 'missing'
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def lexical_path(root, value):
    """Normalize a project path without probing a potentially live source."""
    if (not isinstance(value, str) or Path(value).is_absolute()
            or PureWindowsPath(value).drive):
        raise ValueError(f'Expected a project-relative path: {value}')
    base = Path(os.path.abspath(root))
    path = Path(os.path.abspath(base / value))
    if not path.is_relative_to(base):
        raise ValueError(f'Path leaves project: {value}')
    return path


def lexical_relative(root, path):
    return Path(os.path.abspath(path)).relative_to(Path(os.path.abspath(root))).as_posix()


def project_path(root, value):
    path = lexical_path(root, value)
    here = Path(os.path.abspath(root))
    for part in path.relative_to(here).parts:
        here = here / part
        if here.is_symlink():
            raise ValueError(f'Project path must not contain a symlink: {value}')
    return path


def relative(root, path):
    return Path(path).resolve().relative_to(root.resolve()).as_posix()


def human_index_path(root):
    """Keep the fixed derived page from resolving onto another owned file."""
    path = Path(root).resolve()
    for part in Path(HUMAN_INDEX).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f'Human index publication path must not contain a symlink: {path}')
    return path


def contains(parent, child):
    # Be conservative even on case-sensitive hosts: these paths may later be
    # used on a case-insensitive checkout. Never probe the source to decide.
    parent, child = parent.rstrip('/').casefold(), child.rstrip('/').casefold()
    return child == parent or child.startswith(parent.rstrip('/') + '/')


def overlaps(a, b):
    return contains(a, b) or contains(b, a)


def batch_path(root, value):
    path = lexical_path(root, value)
    rel = lexical_relative(root, path)
    if not rel.startswith(CHARACTERS + '/') or len(Path(rel).parts) < 5:
        raise ValueError(f'Batch/reservation needs a character subdirectory: {value}')
    return rel


def require_unfrozen_reservation(root, value):
    """A live-writer marker must never hide previously inventoried originals."""
    inventory = root / 'catalogs/character-library-files-v1.json'
    if inventory.is_file():
        document = json.loads(inventory.read_text(encoding='utf-8-sig'))
        protected = [entry['path'] for entry in document['files'] if contains(value, entry['path'])]
        if protected:
            raise ValueError(f'Active reservation contains frozen inventoried files: {value}: {protected[0]}')


def read_config(root, path, validate_reservation_freeze=True):
    data = Path(path).read_bytes()
    config = json.loads(data.decode('utf-8-sig'))
    if config.get('schema_version') != 1 or not isinstance(config.get('batches'), list):
        raise ValueError('Management config needs schema_version:1 and batches:[]')
    roots = []
    for item in config['batches']:
        value = batch_path(root, item['root'])
        if item.get('state') not in STATES:
            raise ValueError(f'Unknown management state for {value}')
        if item.get('category', 'character') not in {'character', 'gimmick'}:
            raise ValueError(f'Unknown asset category for {value}')
        if any(overlaps(value, other) for other in roots):
            raise ValueError(f'Configured batch roots overlap: {value}')
        roots.append(value)
        if item.get('character_id', Path(value).parts[3]) != Path(value).parts[3]:
            raise ValueError(f'Character id differs from batch path: {value}')
    active = []
    ids = set()
    for reservation in config.get('reservations', []):
        if reservation.get('id') in ids or not reservation.get('id'):
            raise ValueError('Reservation ids must be nonempty and unique')
        ids.add(reservation['id'])
        if reservation.get('status') not in ('active', 'released') or not reservation.get('owner'):
            raise ValueError('Reservation needs owner and active/released status')
        value = batch_path(root, reservation['root'])
        if reservation['status'] == 'active':
            if validate_reservation_freeze:
                require_unfrozen_reservation(root, value)
            if any(overlaps(value, other['root']) and reservation['owner'] != other['owner'] for other in active):
                raise ValueError(f'Active reservation collision: {value}')
            active.append({**reservation, 'root': value})
    return config, checksum(data), sorted(active, key=lambda x: (x['root'], x['id']))


def walk_files(root, directory, reserved):
    """Do not read or descend into a live writer's tree."""
    if any(contains(r, lexical_relative(root, directory)) for r in reserved):
        return []
    directory = project_path(root, lexical_relative(root, directory))
    if not directory.exists():
        return []
    result = []
    for current, dirs, names in os.walk(directory, followlinks=False):
        here = Path(current)
        if any(contains(r, lexical_relative(root, here)) for r in reserved):
            dirs[:] = []
            continue
        dirs[:] = sorted(d for d in dirs if d not in IGNORED
                         and not any(contains(r, lexical_relative(root, here / d)) for r in reserved)
                         and not (here / d).is_symlink())
        for name in sorted(names):
            path = here / name
            if (name in IGNORED or name.endswith('.pyc')
                    or any(contains(r, lexical_relative(root, path)) for r in reserved)):
                continue
            if path.is_symlink():
                raise ValueError(f'Symlink is not an owned source file: {lexical_relative(root, path)}')
            result.append(path)
    return result


def discover_batches(root, configured, active):
    reserved = [r['root'] for r in active]
    roots = set(configured)
    for path in walk_files(root, root / CHARACTERS, reserved):
        if path.suffix.lower() not in RASTER and not ('registration' in path.name and path.suffix == '.json'):
            continue
        rel = relative(root, path)
        # Explicit batches may have a unique task id rather than a version.
        # Test the actual file before structural grouping shortens its path;
        # otherwise generation-batches/<task-id> invents an empty parent batch.
        if any(contains(other, rel) for other in configured):
            continue
        parts = Path(rel).parts
        # File roles/adoption never come from this structural version grouping.
        parent = parts[:-1]
        version_at = next((i for i in range(5, len(parent)) if VERSION.fullmatch(parent[i])), None)
        value = Path(*parent[:version_at + 1]).as_posix() if version_at is not None else Path(*parent[:5]).as_posix()
        roots.add(value)
    for reservation in active:
        if not any(overlaps(reservation['root'], value) for value in roots):
            roots.add(reservation['root'])
    # A broad unknown root may contain a loose image beside versioned children.
    # Keep it, and exclude child batches when collecting that parent's files.
    return sorted(roots)


def file_record(root, path):
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    if signature(before) != signature(after) or len(data) != after.st_size:
        raise ValueError(f'Source changed during scan: {relative(root, path)}')
    record = {'path': relative(root, path), 'bytes': len(data), 'sha256': checksum(data)}
    return record, data


def evidence(root, items):
    records = []
    for entry in items:
        value = {'path': entry} if isinstance(entry, str) else dict(entry)
        path = project_path(root, value['path'])
        record, _ = file_record(root, path)
        if value.get('sha256') and value['sha256'] != record['sha256']:
            raise ValueError(f'Declared evidence changed: {value["path"]}')
        records.append({**value, **record})
    return records


def declared_roles(root, folder, files, config):
    roles = {}
    def assign(value, role, origin):
        if not isinstance(value, str):
            return
        if value.startswith(CHARACTERS + '/'):
            candidate = lexical_path(root, value)
        else:
            if Path(value).is_absolute() or PureWindowsPath(value).drive:
                return  # Historical external paths are not runtime dependencies.
            candidate = Path(os.path.abspath(folder / value))
            if not candidate.is_relative_to(Path(os.path.abspath(root))):
                return
        rel = lexical_relative(root, candidate)
        if rel in files:
            roles.setdefault(rel, []).append({'role': role, 'evidence': origin})
    for value, role in config.get('file_roles', {}).items():
        if isinstance(role, str):
            assign(value, role, 'explicit management config')
    for rel, (record, data) in files.items():
        path = root / rel
        if path.suffix != '.json' or not ('registration' in path.name or 'manifest' in path.name):
            continue
        try:
            document = json.loads(data.decode('utf-8-sig'))
        except (ValueError, UnicodeDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        frames = document.get('frames', [])
        if isinstance(frames, list):
            for frame in frames:
                if isinstance(frame, dict):
                    assign(frame.get('path'), 'registered_frame', rel + ':frames[].path')
        assign(document.get('source_sheet'), 'source_sheet', rel + ':source_sheet')
        for sheet in document.get('sheets', []):
            if isinstance(sheet, dict):
                assign(sheet.get('source_sheet'), 'source_sheet', rel + ':sheets[].source_sheet')
        for key in ['neutral', 'canonical_neutral', 'neutral_reference']:
            if isinstance(document.get(key), dict):
                assign(document[key].get('path'), 'identity_reference', rel + ':' + key)
    return roles


def inferred_role(path):
    parts, name = path.parts, path.name.lower()
    if 'candidates' in parts or 'generation-candidates' in parts or 'candidate' in name or 'rejected' in name:
        return 'generation_candidate', 'candidate/rejected storage marker; not an adoption'
    if path.suffix.lower() in RASTER:
        if 'preview' in name or 'review' in name or 'contact' in name:
            return 'diagnostic_preview', 'preview/review/contact storage marker'
        if 'original' in name:
            return 'preserved_original', 'original storage marker; selection is separate'
        return 'unclassified_image', 'no explicit registration role found'
    if path.suffix == '.json' and 'registration' in name:
        return 'registration_record', 'registration filename'
    if 'prompt' in name:
        return 'generation_prompt', 'prompt filename'
    if 'generation' in name or 'input' in name:
        return 'provenance_record', 'generation/input filename'
    return 'supporting_record', 'supporting file in batch'


def snapshot(root, config, config_hash, active):
    """Scan under the caller's config lock and matching reservation snapshot."""
    configured = {batch_path(root, item['root']): item for item in config['batches']}
    reserved = [r['root'] for r in active]
    batches = []
    batch_roots = discover_batches(root, configured, active)
    for value in batch_roots:
        item = dict(configured.get(value, {}))
        live = [r for r in active if overlaps(value, r['root'])]
        entirely_reserved = any(contains(r['root'], value) for r in live)
        folder = lexical_path(root, value) if entirely_reserved else project_path(root, value)
        if not entirely_reserved and not folder.is_dir():
            raise ValueError(f'Configured/discovered batch missing: {value}')
        files = {}
        child_batches = [other for other in batch_roots if other != value and contains(value, other)]
        if not entirely_reserved:
            for path in walk_files(root, folder, reserved + child_batches):
                record, data = file_record(root, path)
                files[record['path']] = (record, data)
        roles = declared_roles(root, folder, files, item)
        inventory = []
        for rel, (record, _) in sorted(files.items()):
            role, origin = inferred_role(Path(rel))
            inventory.append({**record, 'roles': roles.get(rel, [{'role': role, 'evidence': origin}])})
        status = 'pending-active-writer' if live else 'snapshotted'
        declarations = {k: v for k, v in item.items() if k not in {
            'root', 'character_id', 'state', 'registration_paths', 'selection_evidence',
            'quality_reviews', 'file_roles', 'canonical_reference'}}
        refs = {}
        # Never hash config references inside reserved trees, including from
        # another completed batch that happens to mention work in progress.
        for field in ['registration_paths', 'selection_evidence', 'quality_reviews']:
            entries = item.get(field, [])
            ready, pending = [], []
            for entry in entries:
                path = lexical_relative(root, lexical_path(root, entry if isinstance(entry, str) else entry['path']))
                (pending if any(contains(r, path) for r in reserved) else ready).append(entry)
            refs[field] = evidence(root, ready)
            if pending:
                refs[field + '_pending'] = pending
        if item.get('canonical_reference'):
            canonical = item['canonical_reference']
            path = lexical_relative(root, lexical_path(root, canonical if isinstance(canonical, str) else canonical['path']))
            if any(contains(r, path) for r in reserved):
                refs['canonical_reference_pending'] = canonical
            else:
                refs['canonical_reference'] = evidence(root, [canonical])[0]
        batches.append({'root': value, 'character_id': Path(value).parts[3],
                        'category': item.get('category', 'character'),
                        'state': item.get('state', 'unclassified'), 'explicitly_classified': value in configured,
                        'inventory_status': status, **declarations,
                        'selection_policy': 'Management classification only; use existing adopted catalogs/episode registrations for playback.',
                        'active_reservations': live, 'excluded_child_batch_roots': child_batches,
                        **refs, 'file_count': len(inventory),
                        'bytes': sum(f['bytes'] for f in inventory),
                        'content_sha256': checksum(canonical_json(inventory)), 'files': inventory})
    return {'schema_version': 1, 'kind': REGISTRY_KIND,
            'path_base': 'project-root', 'config_sha256': config_hash,
            'selection_policy': 'No adoption inferred from version, date, filename or discovery. Existing production selections are authoritative.',
            'active_reservations': active, 'batches': batches,
            'totals': {'batches': len(batches), 'files': sum(b['file_count'] for b in batches),
                       'bytes': sum(b['bytes'] for b in batches),
                       'unclassified_batches': sum(b['state'] == 'unclassified' for b in batches),
                       'pending_batches': sum(b['inventory_status'] != 'snapshotted' for b in batches)}}


def build_snapshot(root, config_path):
    with lock(Path(config_path).with_suffix(Path(config_path).suffix + '.lock')):
        return _build_snapshot_locked(root, config_path)


def _build_snapshot_locked(root, config_path):
    config, config_hash, active = read_config(root, config_path)
    first = snapshot(root, config, config_hash, active)
    second = snapshot(root, config, config_hash, active)
    if first != second:
        raise ValueError('Source changed during scan; reserve active writer roots and retry')
    if current_hash(config_path) != config_hash:
        raise ValueError('Management config changed during scan')
    return second


@contextmanager
def lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ValueError(f'Management writer lock exists; do not steal or expire it automatically: {path}') from error
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(token)
        yield
    finally:
        if path.exists() and path.read_text() == token:
            path.unlink()


def atomic_write(path, value, expected_hash, guards=()):
    path = Path(path)
    with lock(path.with_suffix(path.suffix + '.lock')):
        return _atomic_write_locked(path, value, expected_hash, guards)


def _atomic_write_locked(path, value, expected_hash, guards=()):
    path = Path(path)
    if current_hash(path) != expected_hash:
        raise ValueError(f'Concurrent management edit detected: {path}')
    for guarded, expected in guards:
        if current_hash(guarded) != expected:
            raise ValueError(f'Concurrent management config edit detected: {guarded}')
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(canonical_json(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def inspect(root, config_path):
    result, _ = prepare_publication(root, config_path)
    return result


def render_index(root, result, config, config_relative=CONFIG, registry_relative=REGISTRY):
    """Render the one fixed derived human index; no original HTML/art is edited."""
    parent = human_index_path(root).parent
    def esc(value):
        return html.escape(str(value))
    def link(value, label):
        # A link is a declared location, including opaque pending batches.
        # Rendering its URL must not inspect the linked writer's directory.
        path = lexical_path(root, value)
        href = quote(Path(os.path.relpath(path, parent)).as_posix(), safe='/.-_~')
        return f'<a href="{esc(href)}">{esc(label)}</a>'
    states = {'canonical':'採用通常姿', 'shared_stock':'共有ストック', 'episode_selected':'作品採用',
              'preproduction':'作品制作準備', 'candidate':'候補', 'archive':'保管', 'unclassified':'未分類'}
    labels = config.get('owner_labels', {})
    quality_labels = {'needs_revision':'修正推奨', 'needs_review':'要確認',
                      'episode_reviewed':'作品の動作検査済（414姿勢の画風監査外）',
                      'accepted_for_episode_rendering':'作品用原画の確認済（414姿勢の画風監査外）',
                      'episode_motion_reviewed':'完成映像の演技確認済（414姿勢の画風監査外）',
                      'pass':'記録された範囲の検査に合格',
                      'acceptable_with_notes':'概ね良好・軽微差'}
    totals = result['totals']
    parts = ['<!doctype html><html lang="ja"><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>キャラクター画像の管理一覧</title>',
        '<style>body{font-family:system-ui,sans-serif;max-width:1500px;margin:28px auto;padding:0 20px;',
        'background:#fff8e8;color:#49351e;line-height:1.7}table{border-collapse:collapse;width:100%;background:white}',
        'th,td{border:1px solid #d9cbb2;padding:9px;text-align:left;vertical-align:top}',
        'th{background:#eee0c8}code{overflow-wrap:anywhere}a{color:#21666d}small{color:#695a49}</style>',
        '<h1>キャラクター画像の管理一覧</h1>',
        f'<p>{totals["batches"]}バッチ／確定範囲{totals["files"]}ファイル／生成中{totals["pending_batches"]}バッチ／未分類{totals["unclassified_batches"]}バッチ</p>',
        '<p>この一覧は管理設定と在庫から自動生成します。用途分類と品質判定は別の情報です。収録だけで採用先は変わりません。生成中の予約範囲は読み取り・確定ハッシュ計算から除外しています。</p>',
        '<p>' + ' · '.join([link(config.get('specification', 'docs/IMAGE-ASSET-MANAGEMENT.md'), '画像管理仕様'),
                             link(config_relative, '管理設定'), link(registry_relative, '管理在庫'),
                             link('catalogs/character-library-v1.json', '採用通常姿・汎用動作'),
                             link('assets/library/collections/character-management/v001/initial-reconciliation.json',
                                  '初回整理の根拠')]) + '</p>']
    if config.get('style_review'):
        entry = config['style_review']
        path = entry if isinstance(entry, str) else entry['path']
        parts.append('<p>' + link(path, '細部の画風監査') + ' · ' +
                     link('assets/library/collections/character-style-audit/v001/index.html', '画風比較画像') + '</p>')
    parts.append('<table><tr><th>バッチ</th><th>用途分類</th><th>担当／用途</th><th>品質</th><th>在庫</th><th>登録・根拠</th></tr>')
    for batch in result['batches']:
        owner = batch.get('owner', '未特定')
        owner_label = labels.get(owner, owner)
        quality = []
        for review in batch.get('quality_reviews', []):
            # A character-wide assessment may refer to another batch. Prefer
            # the current batch's status and leave broader conclusions in its
            # linked report, rather than falsely rejecting a closer eye set.
            status = review.get('status') or review.get('quality_status') or review.get('style_status')
            label = quality_labels.get(status, status or '検査記録')
            quality.append(link(review['path'], label))
        references = []
        for field, label in [('registration_paths','登録'), ('selection_evidence','採用・分類の根拠')]:
            for entry in batch.get(field, []):
                references.append(link(entry['path'], label))
        pending = batch['inventory_status'] != 'snapshotted'
        parts.append('<tr><td>' + link(batch['root'], batch['character_id']) + '<br><small>' +
            esc('背景ギミック' if batch.get('category') == 'gimmick' else 'キャラクター') + '</small><br><code>' + esc(batch['root']) + '</code></td>' +
            '<td>' + esc(states[batch['state']]) + '</td><td>' + esc(owner_label) + '<br><small>' + esc(owner) +
            '</small><br>' + esc(batch.get('scope','')) + '</td><td>' + ('<br>'.join(quality) or 'この一覧では品質合格を推定しない') +
            '</td><td>' + ('生成中・確定保留' if pending else '確定範囲') + '<br>' + str(batch['file_count']) +
            'ファイル</td><td>' + ('<br>'.join(references) or '登録なし／分類根拠は管理設定を参照') + '</td></tr>')
    parts.append('</table><h2>同一内容の別名（整理時点の記録）</h2><p>同一SHA-256でも来歴と参照元を保ち、削除・置換・リンク化しません。</p>')
    for group in config.get('duplicate_media_groups', []):
        parts.append('<p><code>' + esc(group.get('sha256','')) + '</code><br>' +
                     '<br>'.join(link(path, path) for path in group.get('paths', [])) + '</p>')
    parts.append('</html>')
    return ''.join(parts).encode('utf-8')


def prepare_publication(root, config_path, registry_path=None):
    with lock(Path(config_path).with_suffix(Path(config_path).suffix + '.lock')):
        return _prepare_publication_locked(root, config_path, registry_path)


def _prepare_publication_locked(root, config_path, registry_path=None):
    result = _build_snapshot_locked(root, config_path)
    data = Path(config_path).read_bytes()
    if checksum(data) != result['config_sha256']:
        raise ValueError('Concurrent management config edit detected while rendering index')
    markup = render_index(root, result, json.loads(data.decode('utf-8-sig')),
                          relative(root, config_path),
                          relative(root, registry_path) if registry_path is not None else REGISTRY)
    result['derived_views'] = [{'path': HUMAN_INDEX, 'bytes':len(markup), 'sha256':checksum(markup)}]
    return result, markup


def require_management_target(root, path):
    value = relative(root, path)
    if not value.startswith('catalogs/') or Path(value).suffix != '.json':
        raise ValueError('Management writes are limited to JSON metadata under catalogs/')


def refresh(root, config_path, registry_path, expected_registry_hash=None):
    with lock(Path(config_path).with_suffix(Path(config_path).suffix + '.lock')):
        return _refresh_locked(root, config_path, registry_path, expected_registry_hash)


def _refresh_locked(root, config_path, registry_path, expected_registry_hash=None):
    require_management_target(root, registry_path)
    if Path(registry_path).resolve() == Path(config_path).resolve():
        raise ValueError('Registry must not overwrite its management config')
    before = current_hash(registry_path)
    index_path = human_index_path(root)
    before_index = current_hash(index_path)
    if expected_registry_hash is not None and before != expected_registry_hash:
        raise ValueError('Expected registry hash differs; inspect the latest registry before publishing')
    if before != 'missing':
        previous = json.loads(Path(registry_path).read_text(encoding='utf-8-sig'))
        if not isinstance(previous, dict) or previous.get('kind') != REGISTRY_KIND:
            raise ValueError('Refusing to overwrite a catalog that is not this management registry')
    result, markup = _prepare_publication_locked(root, config_path, registry_path)
    # Two atomic replacements are a guarded publication sequence, not a claim
    # that multiple files can become visible in one filesystem transaction.
    # The public wrapper holds the reserve/release config lock from before
    # discovery through both replacements, so no writer claim can start during
    # source reads or publication of the snapshot.
    with lock(Path(registry_path).with_suffix(Path(registry_path).suffix + '.lock')):
        with lock(index_path.with_suffix(index_path.suffix + '.lock')):
            if current_hash(registry_path) != before or current_hash(index_path) != before_index:
                raise ValueError('Concurrent management edit detected before registry/index publication')
            if current_hash(config_path) != result['config_sha256']:
                raise ValueError('Concurrent management config edit detected before publication')
            # Recheck after taking locks in case the index was redirected
            # while its derived content was being prepared.
            human_index_path(root)
            for path, payload in [(index_path, markup), (Path(registry_path), canonical_json(result))]:
                temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
                try:
                    with temporary.open('xb') as stream:
                        stream.write(payload)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, path)
                finally:
                    if temporary.exists():
                        temporary.unlink()
    return {'status': 'pass', 'action': 'refresh', 'registry': relative(root, registry_path),
            'registry_sha256': current_hash(registry_path), 'index':HUMAN_INDEX,
            'index_sha256':current_hash(index_path), **result['totals']}


def check(root, config_path, registry_path):
    with lock(Path(config_path).with_suffix(Path(config_path).suffix + '.lock')):
        return _check_locked(root, config_path, registry_path)


def _check_locked(root, config_path, registry_path):
    before = current_hash(registry_path)
    expected = json.loads(Path(registry_path).read_text(encoding='utf-8-sig'))
    actual, markup = _prepare_publication_locked(root, config_path, registry_path)
    if current_hash(registry_path) != before:
        raise ValueError('Registry changed during check')
    if expected != actual:
        raise ValueError('Asset management registry is stale; inspect changes before refresh')
    index = human_index_path(root)
    if not index.is_file() or index.read_bytes() != markup:
        raise ValueError('Human asset index is missing or stale; inspect before refresh')
    return {'status': 'pass', 'action': 'check', 'registry': relative(root, registry_path),
            'registry_sha256': before, **actual['totals']}


def reserve(root, config_path, batch_root, owner, reservation_id):
    with lock(Path(config_path).with_suffix(Path(config_path).suffix + '.lock')):
        return _reserve_locked(root, config_path, batch_root, owner, reservation_id)


def _reserve_locked(root, config_path, batch_root, owner, reservation_id):
    require_management_target(root, config_path)
    config, before, active = read_config(root, config_path)
    value = batch_path(root, batch_root)
    require_unfrozen_reservation(root, value)
    if not owner.strip() or not reservation_id.strip():
        raise ValueError('Reservation owner/id must be nonempty')
    if any(r['id'] == reservation_id for r in config.get('reservations', [])):
        raise ValueError('Reservation id already exists; retain history and choose a new id')
    if any(overlaps(value, r['root']) and r['owner'] != owner for r in active):
        raise ValueError('Active reservation collision; coordinate ownership before writing')
    if not any(contains(r['root'], value) for r in active):
        # This root is not live yet. Reject a new alias before granting it;
        # already-active roots remain opaque, including to the same owner.
        project_path(root, value)
    config.setdefault('reservations', []).append({'id': reservation_id, 'root': value, 'owner': owner,
        'status': 'active', 'created_at_utc': datetime.now(timezone.utc).isoformat()})
    _atomic_write_locked(config_path, config, before)
    return {'status': 'pass', 'action': 'reserve', 'root': value, 'owner': owner, 'id': reservation_id}


def release(root, config_path, reservation_id, owner):
    with lock(Path(config_path).with_suffix(Path(config_path).suffix + '.lock')):
        return _release_locked(root, config_path, reservation_id, owner)


def _release_locked(root, config_path, reservation_id, owner):
    require_management_target(root, config_path)
    # Releasing makes files visible again, so allow the owner to repair a stale
    # claim even if another legacy inventory writer included the claimed files.
    config, before, _ = read_config(root, config_path, validate_reservation_freeze=False)
    matches = [r for r in config.get('reservations', []) if r['id'] == reservation_id]
    if len(matches) != 1 or matches[0]['owner'] != owner or matches[0]['status'] != 'active':
        raise ValueError('Only the matching active reservation owner can release it')
    matches[0].update(status='released', released_at_utc=datetime.now(timezone.utc).isoformat())
    _atomic_write_locked(config_path, config, before)
    return {'status': 'pass', 'action': 'release', 'id': reservation_id, 'owner': owner}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--config', default=CONFIG)
    parser.add_argument('--registry', default=REGISTRY)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('inspect')
    commands.add_parser('check')
    update = commands.add_parser('refresh')
    update.add_argument('--expected-registry-sha256')
    claim = commands.add_parser('reserve')
    claim.add_argument('--batch-root', required=True)
    claim.add_argument('--owner', required=True)
    claim.add_argument('--id', required=True)
    done = commands.add_parser('release')
    done.add_argument('--reservation-id', required=True)
    done.add_argument('--owner', required=True)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        config = project_path(root, args.config)
        registry = project_path(root, args.registry)
        if args.command == 'inspect':
            result = inspect(root, config)
        elif args.command == 'check':
            result = check(root, config, registry)
        elif args.command == 'refresh':
            result = refresh(root, config, registry, args.expected_registry_sha256)
        elif args.command == 'reserve':
            result = reserve(root, config, args.batch_root, args.owner, args.id)
        else:
            result = release(root, config, args.reservation_id, args.owner)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f'Character asset management error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
