"""Maintain the exact output files required by the adopted video productions."""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
POLICY = Path('reproducibility/archive-policy.json')
MANIFEST = Path('reproducibility/production-inputs.json')
BEGIN = '# BEGIN GENERATED PRODUCTION OUTPUT ARCHIVE'
END = '# END GENERATED PRODUCTION OUTPUT ARCHIVE'
PREFIXES = ('output/', 'assets/', 'design/', 'catalogs/', 'tools/', 'episodes/', 'tests/')
RELATIVE_FILE = re.compile(r'\.(?:json|png|jpg|jpeg|wav|mp4|m4a|txt|md|py|mjs|js|srt|ttf|otf|csv|tsv|log)$', re.I)


class ArchiveError(ValueError):
    """A required production input or archive configuration is invalid."""


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha256(path: Path) -> str:
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False


def build_manifest(root: Path) -> dict:
    root = root.resolve()
    policy = read_json(root / POLICY)
    if policy.get('schema_version') != 1:
        raise ArchiveError('Unsupported archive policy version')
    catalog = read_json(root / 'catalogs/library-v1.json')
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
        path = path.resolve()
        if not inside(path, root):
            raise ArchiveError(f'Production input leaves the checkout: {path}')
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
                path = root / normalized
                if not inside(path, root):
                    raise ArchiveError(f'Unsafe project-relative input: {normalized}')
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
                if path.is_file() and inside(path, root):
                    add(path, reason)

    for key in active:
        production = catalog['production_sets'][key]
        record_path = root / production['production_record']
        add(record_path, key, required=True)
        inspect(production, root / 'catalogs/library-v1.json', key)
        output = root / production['output']
        add(output, key, required=True)
        for name in policy['current_delivery_filenames']:
            candidate = output.parent / name
            if candidate.is_file():
                add(candidate, key)
        if not record_path.is_file():
            continue
        inventory = read_json(record_path).get('files', [])
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
        value = read_json(path)
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
        checksum = sha256(path)
        expected = expected_output_hashes.get(name)
        if expected and expected != {checksum}:
            raise ArchiveError(f'Output differs from the completed production inventory: {name}')
        entries.append({'path': name, 'sha256': checksum, 'bytes': path.stat().st_size, 'reasons': sorted(reasons[name])})
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
    manifest = build_manifest(root)
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
    ignore_path = root / '.gitignore'
    existing_ignore = ignore_path.read_text(encoding='utf-8-sig') if ignore_path.is_file() else ''
    ignore_text = expected_ignore(existing_ignore, manifest)
    manifest_path = root / MANIFEST
    current_manifest = manifest_path.read_text(encoding='utf-8-sig') if manifest_path.is_file() else None
    differences = []
    if current_manifest != manifest_text:
        differences.append(MANIFEST.as_posix())
    if existing_ignore != ignore_text:
        differences.append('.gitignore')
    if write:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        if MANIFEST.as_posix() in differences:
            manifest_path.write_text(manifest_text, encoding='utf-8', newline='\n')
        if '.gitignore' in differences:
            ignore_path.write_text(ignore_text, encoding='utf-8', newline='\n')
    elif differences:
        raise ArchiveError('Archive metadata is stale; run --write: ' + ', '.join(differences))
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
