"""Maintain the exact output files required by the adopted video productions."""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
from contextlib import contextmanager, ExitStack
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
POLICY = Path('reproducibility/archive-policy.json')
MANIFEST = Path('reproducibility/production-inputs.json')
CATALOG = Path('catalogs/library-v1.json')
MANAGEMENT = Path('catalogs/character-asset-management-v1.json')
BEGIN = '# BEGIN GENERATED PRODUCTION OUTPUT ARCHIVE'
END = '# END GENERATED PRODUCTION OUTPUT ARCHIVE'
PREFIXES = ('output/', 'assets/', 'design/', 'catalogs/', 'tools/', 'episodes/', 'tests/')
RELATIVE_FILE = re.compile(r'\.(?:json|png|jpg|jpeg|wav|mp4|m4a|txt|md|py|mjs|js|srt|ttf|otf|csv|tsv|log)$', re.I)


class ArchiveError(ValueError):
    """A required production input or archive configuration is invalid."""


def read_json(path: Path):
    before = path.stat()
    data = path.read_bytes()
    if file_signature(before) != file_signature(path.stat()) or len(data) != before.st_size:
        raise ArchiveError(f'Archive input changed while reading: {path}')
    return json.loads(data.decode('utf-8-sig'))


def file_signature(stat):
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def sha256(path: Path) -> str:
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def inside(path: Path, root: Path) -> bool:
    try:
        Path(os.path.abspath(path)).relative_to(root)
        return True
    except ValueError:
        return False


def source_path(root: Path, path: Path, reserved=()) -> Path:
    """Reject active roots lexically, before probing files or following links."""
    path = Path(os.path.abspath(path))
    if not inside(path, root):
        raise ArchiveError(f'Production input leaves the checkout: {path}')
    relative = path.relative_to(root).as_posix()
    # Conservatively reject case aliases even on a case-sensitive checkout,
    # so a Mac/Windows source spelling cannot bypass its owner's reservation.
    folded = relative.casefold()
    if any(folded == value.casefold() or folded.startswith(value.casefold() + '/') for value in reserved):
        raise ArchiveError(f'Active generation source must not be read: {relative}')
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if current.is_symlink():
            raise ArchiveError(f'Archive path must not contain a symlink: {current}')
    return path


def current_hash(path: Path) -> str:
    if not path.exists():
        return 'missing'
    before = path.stat()
    value = sha256(path)
    if file_signature(before) != file_signature(path.stat()):
        raise ArchiveError(f'Archive control changed while reading: {path}')
    return value


@contextmanager
def writer_lock(path: Path):
    """Use the same exclusive lock paths/token protocol as image management."""
    path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ArchiveError(f'Archive writer lock exists; do not steal or expire it automatically: {path}') from error
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(token)
        yield
    finally:
        if path.exists() and path.read_text() == token:
            path.unlink()


def build_manifest(root: Path) -> dict:
    """Build runtime closure while keeping active generation reservations stable."""
    root = root.resolve()
    config = source_path(root, root / MANAGEMENT)
    with writer_lock(config.with_suffix(config.suffix + '.lock')):
        return _build_manifest(root)


def _build_manifest(root: Path, *, json_guards=None) -> dict:
    """Scan only the adopted runtime closure; caller holds the config lock."""
    root = root.resolve()
    management_path = source_path(root, root / MANAGEMENT)
    management_hash = current_hash(management_path)
    management = read_json(management_path) if management_hash != 'missing' else {}
    reserved = []
    for reservation in management.get('reservations', []):
        if reservation.get('status') != 'active':
            continue
        value = reservation.get('root')
        if (not isinstance(value, str) or '\\' in value or PureWindowsPath(value).drive
                or PurePosixPath(value).is_absolute() or '..' in PurePosixPath(value).parts
                or not value.startswith('assets/library/characters/')):
            raise ArchiveError(f'Invalid active reservation root: {value}')
        reserved.append(PurePosixPath(value).as_posix())

    def guarded(path):
        source_path(root, management_path)
        if current_hash(management_path) != management_hash:
            raise ArchiveError('Character management config changed during archive scan')
        return source_path(root, path, reserved)

    json_guards = {} if json_guards is None else json_guards

    def read_dependency(path):
        path = guarded(path)
        before = current_hash(path)
        if path in json_guards and json_guards[path] != before:
            raise ArchiveError(f'Archive dependency JSON changed during scan: {path.relative_to(root)}')
        value = read_json(path)
        if current_hash(path) != before:
            raise ArchiveError(f'Archive dependency JSON changed during scan: {path.relative_to(root)}')
        json_guards[path] = before
        return value

    policy = read_dependency(root / POLICY)
    if policy.get('schema_version') != 1:
        raise ArchiveError('Unsupported archive policy version')
    catalog = read_dependency(root / CATALOG)
    active = catalog['active_production_set_ids']
    if not active or len(set(active)) != len(active):
        raise ArchiveError('Active production IDs must be nonempty and unique')
    current_records = {catalog['production_sets'][key]['production_record'] for key in active}
    functional = set(policy['functional_json_names'])
    producer_roots = [root.as_posix(), *policy['source_repository_prefixes']]
    files: dict[str, Path] = {}
    reasons: dict[str, set[str]] = defaultdict(set)
    missing: dict[str, set[str]] = defaultdict(set)
    external: dict[str, set[str]] = defaultdict(set)
    pending: deque[Path] = deque()
    visited: set[str] = set()
    expected_output_hashes: dict[str, set[str]] = defaultdict(set)

    def add(path: Path, reason: str, *, required: bool = False) -> None:
        path = guarded(path)
        relative = path.relative_to(root).as_posix()
        if not path.is_file():
            if required:
                missing[relative].add(reason)
            return
        reasons[relative].add(reason)
        if relative in files:
            return
        files[relative] = path
        if path.suffix.lower() == '.json' and (relative in current_records or path.name in functional):
            pending.append(path)

    def normalize(text: str) -> str:
        normalized = text.replace('\\', '/').strip()
        for prefix in producer_roots:
            prefix = prefix.rstrip('/')
            if normalized.casefold().startswith(prefix.casefold() + '/'):
                return normalized[len(prefix) + 1:]
        return normalized

    def inspect(value, base: Path, reason: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                inspect(key, base, reason)
                inspect(item, base, reason)
        elif isinstance(value, list):
            for item in value:
                inspect(item, base, reason)
        elif isinstance(value, str) and len(value) <= 600:
            normalized = normalize(value)
            if normalized.startswith(PREFIXES):
                if not inside(root / normalized, root):
                    raise ArchiveError(f'Unsafe project-relative input: {normalized}')
                path = guarded(root / normalized)
                if path.is_file():
                    add(path, reason)
                elif not path.is_dir() and not any(c in normalized for c in '\n<>*|') and ' --' not in normalized:
                    missing[normalized].add(reason)
            elif re.match(r'^[A-Za-z]:/', normalized):
                if RELATIVE_FILE.search(normalized):
                    external[normalized].add(reason)
            elif not normalized.startswith(('https:', 'http:')):
                if '/' not in normalized and not RELATIVE_FILE.search(normalized):
                    return
                path = base.parent / normalized
                if inside(path, root) and guarded(path).is_file():
                    add(path, reason)

    for key in active:
        production = catalog['production_sets'][key]
        record_path = guarded(root / production['production_record'])
        add(record_path, key, required=True)
        inspect(production, root / 'catalogs/library-v1.json', key)
        output = guarded(root / production['output'])
        add(output, key, required=True)
        for name in policy['current_delivery_filenames']:
            candidate = guarded(output.parent / name)
            if candidate.is_file():
                add(candidate, key)
        if not record_path.is_file():
            continue
        inventory = read_dependency(record_path).get('files', [])
        if isinstance(inventory, dict):
            inventory = [{'path': path, 'sha256': checksum} for path, checksum in inventory.items()]
        if not isinstance(inventory, list):
            raise ArchiveError(f'Invalid files inventory: {production["production_record"]}')
        for entry in inventory:
            name = normalize(entry['path'])
            add(root / name, production['production_record'], required=True)
            if name.startswith('output/') and entry.get('sha256'):
                expected_output_hashes[name].add(entry['sha256'].casefold())

    for entry in policy['additional_required_files']:
        add(root / entry['path'], entry['reason'], required=True)

    while pending:
        path = pending.popleft()
        name = path.relative_to(root).as_posix()
        if name in visited:
            continue
        visited.add(name)
        value = read_dependency(path)
        if path.name == 'speech-acceptance.json':
            inspect(value.get('inputs', {}), path, name)
            for entry in value.get('results', []):
                inspect(entry.get('pronunciation_evidence', []), path, name)
        else:
            inspect(value, path, name)

    if missing:
        details = '\n'.join(f'  {name} ({", ".join(sorted(origins))})' for name, origins in sorted(missing.items()))
        raise ArchiveError(f'Missing required project inputs:\n{details}')
    entries = []
    for name, path in sorted(files.items()):
        if not name.startswith('output/'):
            continue
        path = guarded(path)
        before = path.stat()
        checksum = sha256(path)
        if file_signature(before) != file_signature(path.stat()):
            raise ArchiveError(f'Archive input changed while hashing: {name}')
        if path in json_guards and json_guards[path] != checksum:
            raise ArchiveError(f'Archive dependency JSON changed during scan: {name}')
        expected = expected_output_hashes.get(name)
        if expected and expected != {checksum}:
            raise ArchiveError(f'Output differs from the completed production inventory: {name}')
        entries.append({'path': name, 'sha256': checksum, 'bytes': before.st_size, 'reasons': sorted(reasons[name])})
    for path, expected in json_guards.items():
        if current_hash(guarded(path)) != expected:
            raise ArchiveError(f'Archive dependency JSON changed during scan: {path.relative_to(root)}')
    return {
        'schema_version': 1,
        'kind': 'production-output-inputs-archive',
        'active_production_set_ids': active,
        'policy_file': POLICY.as_posix(),
        'totals': {'files': len(entries), 'bytes': sum(entry['bytes'] for entry in entries)},
        'files': entries,
        'informational_external_references': [{'path': name, 'referenced_by': sorted(origins)} for name, origins in sorted(external.items())],
        'scope': 'Exact output allowlist for adopted production inputs and records. Assets, tools, design and materials remain ordinary repository content. Machine-local historical provenance does not become a clone requirement.'
    }


def archive_ignore_block(manifest: dict) -> str:
    directories = {'output/'}
    for entry in manifest['files']:
        path = PurePosixPath(entry['path'])
        if path.parts[0] != 'output' or '..' in path.parts:
            raise ArchiveError(f'Invalid output allowlist entry: {path}')
        for parent in path.parents:
            if parent.as_posix() != '.':
                directories.add(parent.as_posix() + '/')
    lines = [BEGIN, '# Generated by tools/update_production_archive.py --write.', '/output/**']
    lines += ['!/' + directory for directory in sorted(directories)]
    lines += ['!/' + entry['path'] for entry in manifest['files']]
    lines.append(END)
    return '\n'.join(lines)


def expected_ignore(original: str, manifest: dict) -> str:
    if original.count(BEGIN) != original.count(END) or original.count(BEGIN) > 1:
        raise ArchiveError('Malformed generated output archive markers in .gitignore')
    if BEGIN in original:
        before, rest = original.split(BEGIN, 1)
        _, after = rest.split(END, 1)
        original = before.rstrip('\r\n') + '\n' + after.lstrip('\r\n')
    lines = [line for line in original.splitlines() if line.strip() not in {'output/', '/output/', 'output/**', '/output/**'}]
    return '\n'.join(lines).rstrip() + '\n\n' + archive_ignore_block(manifest) + '\n'


def run(root: Path, *, write: bool) -> dict:
    root = root.resolve()
    # Config first matches reserve/release and character-library lock ordering.
    # The main catalog lock is also the lock for a cooperating adoption writer.
    controls = [source_path(root, root / relative)
                for relative in (MANAGEMENT, CATALOG, POLICY, MANIFEST, Path('.gitignore'))]
    guards = {path: current_hash(path) for path in controls}
    manifest_path, ignore_path = controls[-2:]
    json_guards = {}

    def check_guards():
        for path, expected in guards.items():
            source_path(root, path)
            if current_hash(path) != expected:
                raise ArchiveError(f'Concurrent archive control edit detected: {path.relative_to(root)}')
        for path, expected in json_guards.items():
            source_path(root, path)
            if current_hash(path) != expected:
                raise ArchiveError(f'Archive dependency JSON changed before publication: {path.relative_to(root)}')

    temporary = []
    published = []
    with ExitStack() as stack:
        # Checks also hold the reservation lock throughout the scan: a
        # cooperating reserve must not turn the next source into an active tree
        # between our config check and the filesystem probe. No other check-only
        # locks or persistent writes are needed.
        for path in controls:
            if write or path == controls[0]:
                stack.enter_context(writer_lock(path.with_suffix(path.suffix + '.lock')))
        check_guards()
        manifest = _build_manifest(root, json_guards=json_guards)
        check_guards()
        manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
        existing_ignore = ignore_path.read_text(encoding='utf-8-sig') if guards[ignore_path] != 'missing' else ''
        current_manifest = manifest_path.read_text(encoding='utf-8-sig') if guards[manifest_path] != 'missing' else None
        ignore_text = expected_ignore(existing_ignore, manifest)
        check_guards()
        differences = []
        if current_manifest != manifest_text:
            differences.append(MANIFEST.as_posix())
        if existing_ignore != ignore_text:
            differences.append('.gitignore')
        if write and differences:
            try:
                # Stage both complete payloads before publishing either. Each
                # replacement is atomic; the pair is not a filesystem transaction.
                payloads = [(manifest_path, manifest_text.encode('utf-8')),
                            (ignore_path, ignore_text.encode('utf-8'))]
                for path, payload in payloads:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    staged = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
                    temporary.append(staged)
                    with staged.open('xb') as stream:
                        stream.write(payload)
                        stream.flush()
                        os.fsync(stream.fileno())
                check_guards()
                for staged, (destination, payload) in zip(temporary, payloads):
                    if destination.relative_to(root).as_posix() not in differences:
                        continue
                    check_guards()
                    os.replace(staged, destination)
                    published.append(destination.relative_to(root).as_posix())
                    guards[destination] = hashlib.sha256(payload).hexdigest()
                check_guards()
            except (OSError, ValueError) as error:
                if published:
                    raise ArchiveError('Archive publication interrupted after individual atomic replacement of '
                                       + ', '.join(published)
                                       + '; inspect the concurrent change and rerun --check/--write: ' + str(error)) from error
                raise
            finally:
                for staged in temporary:
                    if staged.exists():
                        staged.unlink()
        elif not write and differences:
            raise ArchiveError('Archive metadata is stale; run --write: ' + ', '.join(differences))
        check_guards()
    return {'status': 'pass', 'mode': 'write' if write else 'check', **manifest['totals'],
            'active_productions': len(manifest['active_production_set_ids']),
            'updated_files': differences if write else [],
            'informational_external_references': len(manifest['informational_external_references'])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--check', action='store_true', help='Verify hashes, policy and exact .gitignore allowlist without writing.')
    modes.add_argument('--write', action='store_true', help='Regenerate archive metadata and .gitignore after a new adopted production.')
    parser.add_argument('--root', type=Path, default=ROOT, help='Checkout root; defaults to this tool\'s repository.')
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.root, write=args.write), ensure_ascii=False))
        return 0
    except (ArchiveError, OSError, KeyError, ValueError, TypeError) as error:
        print(f'Production archive check failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
