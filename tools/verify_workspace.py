"""Read-only checks of managed workspace metadata, references and source media.

The existing character and production verifiers perform their deeper media
checks separately. This command checks cross-catalog structure and never
selects an adoption, changes a hash, or descends into an active writer tree.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re

try:
    from .manage_character_assets import lock as management_lock
except ImportError:  # Direct execution from tools/.
    from manage_character_assets import lock as management_lock


ROOT = Path(__file__).resolve().parents[1]
MAIN = 'catalogs/library-v1.json'
MANAGEMENT = 'catalogs/character-asset-management-v1.json'
RENDER = 'catalogs/render-assets-v1.json'
JSON_SCOPES = ('catalogs', 'episodes', 'assets/library', 'reproducibility')
PATH_ROOTS = ('assets/', 'catalogs/', 'design/', 'episodes/', 'output/',
              'reproducibility/', 'tools/', 'tests/', 'licenses/', 'materials/')
IGNORED_DIRECTORIES = {'__pycache__', '.git', 'node_modules', '.venv', '.cache', '.model-cache'}
LFS_HEADER = b'version https://git-lfs.github.com/spec/v1\n'
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
# This frozen CLI capture predates the current naming convention. Its bytes
# are evidence, so validate each recorded JSON object without rewriting it.
HISTORICAL_JSON_STREAMS = {'reproducibility/validation-20261111/model-check.json'}


class DuplicateKey(ValueError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKey(f'Duplicate JSON object key: {key}')
        result[key] = value
    return result


def pointer(parts):
    return ''.join('/' + str(part).replace('~', '~0').replace('/', '~1') for part in parts)


def at_pointer(document, value):
    if not isinstance(value, str) or not value.startswith('/') or re.search(r'~(?:[^01]|$)', value):
        raise ValueError('Expected an RFC 6901 JSON pointer to a field')
    current = document
    for part in value[1:].split('/'):
        part = part.replace('~1', '/').replace('~0', '~')
        if isinstance(current, list):
            if not part.isdecimal() or (part.startswith('0') and part != '0'):
                raise ValueError('Invalid JSON pointer array index')
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise ValueError('JSON pointer does not resolve to a field')
    return current


class Auditor:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.errors = []
        self.notes = []
        self.active = []
        self.documents = {}
        self.json_checked = set()
        self.hashes = {}
        self.references = set()
        self.lfs_pointers = set()
        self.overrides = {}
        self.used_overrides = set()
        self.explicit_hashes = 0
        self.seen_messages = set()
        self.control_hashes = {}
        self.required_items = set()
        self.required_references = set()
        self.required_branding = set()

    def message(self, severity, code, location, message, path=None, **details):
        identity = (severity, code, location, path)
        if identity in self.seen_messages:
            return
        self.seen_messages.add(identity)
        row = {'code': code, 'location': location, 'message': message}
        if path is not None:
            row['path'] = path
        row.update(details)
        (self.errors if severity == 'error' else self.notes).append(row)

    def relative_path(self, value):
        if (not isinstance(value, str) or not value or '\\' in value
                or PureWindowsPath(value).drive or PurePosixPath(value).is_absolute()
                or '..' in PurePosixPath(value).parts or '<' in value or '>' in value):
            raise ValueError(f'Expected a project-relative path: {value}')
        return PurePosixPath(value).as_posix()

    def pending(self, relative):
        # Treat case aliases as pending even on case-sensitive filesystems.
        # Resolve nothing here: a writer's tree is opaque before any probe.
        relative = self.relative_path(relative).casefold()
        return any(relative == item['root'].casefold()
                   or relative.startswith(item['root'].casefold() + '/') for item in self.active)

    def safe_path(self, relative):
        relative = self.relative_path(relative)
        if self.pending(relative):
            raise ValueError(f'Active generation input is pending: {relative}')
        path = self.root
        for part in PurePosixPath(relative).parts:
            path = path / part
            # Do not follow aliases into another source tree or a writer tree.
            if path.is_symlink():
                raise ValueError(f'Managed reference contains a symlink: {relative}')
        return path

    def read_json(self, relative, retain=False):
        relative = self.relative_path(relative)
        if self.pending(relative):
            return None
        if relative in self.documents:
            return self.documents[relative]
        try:
            path = self.safe_path(relative)
            before = path.stat()
            data = path.read_bytes()
            after = path.stat()
            signature = lambda item: (item.st_ino, item.st_size, item.st_mtime_ns)
            if signature(before) != signature(after):
                raise ValueError('File changed while being read; retry after the writer finishes')
            if relative.startswith('catalogs/'):
                observed = hashlib.sha256(data).hexdigest()
                expected = self.control_hashes.setdefault(relative, observed)
                if observed != expected or self.hashes.get(relative, observed) != observed:
                    self.message('error', 'concurrent_metadata_change', relative,
                                 'Catalog bytes changed between observations; retry against a stable snapshot.', relative)
            text = data.decode('utf-8-sig')
            try:
                document = json.loads(text, object_pairs_hook=unique_object)
            except json.JSONDecodeError:
                if relative not in HISTORICAL_JSON_STREAMS:
                    raise
                decoder = json.JSONDecoder(object_pairs_hook=unique_object)
                document, offset = [], 0
                while offset < len(text):
                    if text[offset].isspace():
                        offset += 1
                        continue
                    row, offset = decoder.raw_decode(text, offset)
                    document.append(row)
                if not document or not all(isinstance(row, dict) for row in document):
                    raise ValueError('Historical CLI capture must contain a stream of JSON objects')
                self.message('note', 'historical_json_stream', relative,
                             'Preserved CLI capture concatenates JSON objects despite its .json suffix; every object was validated.', relative)
            self.json_checked.add(relative)
            if retain:
                self.documents[relative] = document
            return document
        except (OSError, ValueError, UnicodeError) as error:
            self.message('error', 'invalid_json', relative, str(error), relative)
            return None

    def load_reservations(self):
        path = self.root / MANAGEMENT
        if not path.is_file():
            self.message('error', 'missing_management_config', MANAGEMENT,
                         'Cannot establish writer exclusions without the management config.', MANAGEMENT)
            return False
        document = self.read_json(MANAGEMENT, retain=True)
        if (not isinstance(document, dict) or document.get('schema_version') != 1
                or not isinstance(document.get('reservations', []), list)
                or not isinstance(document.get('batches', []), list)):
            self.message('error', 'invalid_management_config', MANAGEMENT,
                         'Cannot safely scan until the management config is a valid schema-version-1 object.')
            return False
        seen = set()
        valid = True
        for index, row in enumerate(document.get('reservations', [])):
            location = MANAGEMENT + pointer(('reservations', index))
            if not isinstance(row, dict) or row.get('status') not in ('active', 'released'):
                self.message('error', 'invalid_reservation', location, 'Reservation must have an active/released status.')
                valid = False
                continue
            if row['status'] != 'active':
                continue
            try:
                relative = self.relative_path(row['root'])
                if not relative.startswith('assets/library/characters/') or len(PurePosixPath(relative).parts) < 5:
                    raise ValueError('Active generation must name a character batch')
                if (not isinstance(row.get('id'), str) or not row['id'].strip()
                        or not isinstance(row.get('owner'), str) or not row['owner'].strip()
                        or row['id'] in seen):
                    raise ValueError('Active reservation requires a unique id and an owner')
                seen.add(row['id'])
                self.active.append({**row, 'root': relative})
                self.message('note', 'active_generation', location,
                             'Pending writer tree excluded from reading and filesystem traversal.',
                             relative, owner=row['owner'])
            except (KeyError, ValueError) as error:
                self.message('error', 'invalid_reservation', location, str(error))
                valid = False
        for index, batch in enumerate(document.get('batches', [])):
            if not isinstance(batch, dict):
                continue
            for review in batch.get('quality_reviews', []):
                if isinstance(review, dict) and review.get('status') in ('needs_revision', 'needs_review'):
                    self.message('note', 'recorded_quality_finding',
                                 MANAGEMENT + pointer(('batches', index)),
                                 'An unresolved quality review is recorded; file integrity does not clear it.',
                                 batch.get('root'), review_status=review['status'])
        return valid

    def walk_files(self, scope):
        if self.pending(scope):
            return
        directory = self.root / scope
        if not directory.is_dir():
            return
        def unreadable(error):
            self.message('error', 'unreadable_directory', scope, str(error), str(error.filename))
        for current, directories, names in os.walk(directory, topdown=True, followlinks=False, onerror=unreadable):
            here = Path(current)
            here_relative = here.relative_to(self.root).as_posix()
            if self.pending(here_relative):
                directories[:] = []
                continue
            # Prune by lexical location before inspecting links or descendants.
            directories[:] = [name for name in directories
                              if name not in IGNORED_DIRECTORIES
                              and not self.pending((here / name).relative_to(self.root).as_posix())]
            for name in list(directories):
                path = here / name
                if path.is_symlink():
                    self.message('error', 'managed_symlink', scope,
                                 'Managed metadata trees must not hide sources behind symlink directories.',
                                 path.relative_to(self.root).as_posix())
                    directories.remove(name)
            for name in sorted(names):
                relative = (here / name).relative_to(self.root).as_posix()
                if self.pending(relative) or name == '.DS_Store' or name.endswith('.pyc'):
                    continue
                path = here / name
                if path.is_symlink():
                    self.message('error', 'managed_symlink', scope,
                                 'Managed source files must be owned regular files.', relative)
                    continue
                yield relative, path

    def scan_managed_files(self):
        for scope in JSON_SCOPES:
            for relative, path in self.walk_files(scope):
                if path.suffix.lower() == '.json' and relative not in self.json_checked:
                    self.read_json(relative)
                if scope == 'assets/library':
                    self.check_pointer(relative, path)

    def check_pointer(self, relative, path):
        relative = self.relative_path(relative)
        if self.pending(relative):
            return False
        if relative in self.lfs_pointers:
            return True
        try:
            if path.stat().st_size <= 1024:
                with path.open('rb') as stream:
                    if stream.read(len(LFS_HEADER)) == LFS_HEADER:
                        self.lfs_pointers.add(relative)
                        self.message('error', 'lfs_pointer', relative,
                                     'Source media is an unmaterialized Git LFS pointer.', relative)
                        return True
        except OSError as error:
            self.message('error', 'unreadable_file', relative, str(error), relative)
        return False

    def digest(self, relative, path):
        relative = self.relative_path(relative)
        if self.pending(relative):
            raise ValueError(f'Active generation input is pending: {relative}')
        if relative not in self.hashes:
            before = path.stat()
            with path.open('rb') as stream:
                value = hashlib.file_digest(stream, 'sha256').hexdigest()
            after = path.stat()
            if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError('File changed while hashing; retry after the writer finishes')
            self.hashes[relative] = value
        return self.hashes[relative]

    def reference(self, value, document, parts, historical=False, expected_sha=None, expected_bytes=None, required=False):
        location = document + pointer(parts)
        try:
            relative = self.relative_path(value)
            self.references.add(relative)
            if self.pending(relative):
                self.message('error' if required else 'note',
                             'pending_required_input' if required else 'pending_reference', location,
                             'Required current input is unverified in an active writer tree.' if required else
                             'Reference points into an active generation batch; verification is pending.', relative)
                return
            path = self.safe_path(relative)
            if not path.exists():
                key = (document, pointer(parts))
                if key in self.overrides:
                    self.used_overrides.add(key)
                    self.message('note', 'declared_unavailable_evidence', location,
                                 'Exact frozen evidence reference is explicitly unavailable; no replacement is approved.', relative)
                else:
                    self.message('note' if historical else 'error',
                                 'historical_file_unavailable' if historical else 'missing_file',
                                 location, 'Referenced file is not present.', relative)
                return
            if expected_sha is not None:
                self.explicit_hashes += 1
                if not isinstance(expected_sha, str) or not SHA256.fullmatch(expected_sha):
                    raise ValueError('Declared SHA-256 must be 64 lowercase hexadecimal characters')
                if not path.is_file():
                    raise ValueError('SHA-256 reference does not name a file')
                if self.digest(relative, path) != expected_sha:
                    self.message('error', 'sha256_mismatch', location,
                                 'Referenced file differs from its declared SHA-256.', relative)
            if expected_bytes is not None and path.stat().st_size != expected_bytes:
                self.message('error', 'byte_count_mismatch', location,
                             'Referenced file differs from its declared byte count.', relative)
            if path.is_file():
                self.check_pointer(relative, path)
                if path.suffix.lower() == '.json' and relative not in self.json_checked:
                    self.read_json(relative)
        except (OSError, ValueError) as error:
            self.message('error', 'invalid_reference', location, str(error), str(value))

    def load_overrides(self, catalog):
        for index, row in enumerate(catalog.get('metadata_availability_overrides', [])):
            location = MAIN + pointer(('metadata_availability_overrides', index))
            try:
                if not isinstance(row, dict):
                    raise ValueError('Evidence override must be an object')
                source = self.relative_path(row['source_document'])
                field = row['json_pointer']
                if source == MAIN or not source.startswith('catalogs/') or not source.endswith('.json'):
                    raise ValueError('Unavailable evidence overrides require a separate frozen catalog document')
                if not isinstance(field, str) or not re.search(r'(?:qa|review|report)', field.rsplit('/', 1)[-1], re.I):
                    raise ValueError('Override must target a QA/review/report field, not a primary source')
                if row.get('status') != 'unavailable_historical_evidence' or row.get('replacement_path', 'missing') is not None:
                    raise ValueError('Only explicit unavailable historical evidence with null replacement is supported')
                original = self.relative_path(row['original_path'])
                if self.pending(source) or self.pending(original):
                    raise ValueError('An override must not target an active writer tree')
                source_path = self.safe_path(source)
                if not SHA256.fullmatch(str(row.get('source_sha256', ''))) or self.digest(source, source_path) != row['source_sha256']:
                    raise ValueError('Override source SHA-256 differs from the frozen document')
                document = self.read_json(source, retain=True)
                if at_pointer(document, field) != row['original_path']:
                    raise ValueError('Override JSON pointer does not name the declared original path')
                if self.safe_path(original).exists():
                    raise ValueError('Unavailable override is stale: the original file is present')
                key = (source, field)
                if key in self.overrides:
                    raise ValueError('Duplicate evidence override for the same source field')
                self.overrides[key] = row
            except (KeyError, IndexError, TypeError, OSError, ValueError) as error:
                self.message('error', 'invalid_availability_override', location, str(error))

    def check_ids(self, catalog):
        maps = {}
        for name in ('items', 'reference_sets', 'production_sets', 'preproduction_sets', 'branding_sets', 'character_stock_sets'):
            value = catalog.get(name, {})
            if not isinstance(value, dict):
                self.message('error', 'invalid_id_map', MAIN + '/' + name, 'ID collection must be an object.')
                value = {}
            maps[name] = value
        for collection in ('reference', 'production', 'preproduction', 'branding'):
            name = 'active_' + collection + '_set_ids'
            selected = catalog.get(name, [])
            if not isinstance(selected, list) or any(not isinstance(item, str) for item in selected) or len(selected) != len(set(selected)):
                self.message('error', 'invalid_active_ids', MAIN + '/' + name, 'Active IDs must be a unique string list.')
                continue
            for identity in selected:
                if identity not in maps[collection + '_sets']:
                    self.message('error', 'missing_active_id', MAIN + '/' + name,
                                 'Active ID does not resolve in its declared collection.', identity)
        targets = {'canonical_identity_id':'items', 'identity_reference_id':'items', 'style_reference_id':'items',
                   'reference_set_id':'reference_sets', 'visual_reference_set_id':'reference_sets',
                   'source_reference_set_id':'reference_sets', 'supersedes_reference_set_id':'reference_sets',
                   'production_set_id':'production_sets', 'implemented_by_production_set_id':'production_sets',
                   'supersedes_production_set_id':'production_sets', 'superseded_by':'production_sets',
                   'revised_by':'production_sets', 'supersedes_preproduction_set_id':'preproduction_sets'}
        def selected(name):
            value = catalog.get(name, [])
            return {item for item in value if isinstance(item, str)} if isinstance(value, list) else set()
        self.required_references = selected('active_reference_set_ids')
        self.required_branding = selected('active_branding_set_ids')
        for identity in selected('active_production_set_ids'):
            production = maps['production_sets'].get(identity)
            if not isinstance(production, dict):
                continue
            items = production.get('items', [])
            if isinstance(items, list):
                self.required_items.update(item for item in items if isinstance(item, str))
            reference = production.get('visual_reference_set_id')
            if isinstance(reference, str):
                self.required_references.add(reference)
        for collection, identities in (('reference_sets', self.required_references),
                                       ('branding_sets', self.required_branding)):
            for identity in identities:
                record = maps[collection].get(identity)
                if isinstance(record, dict) and isinstance(record.get('items'), list):
                    self.required_items.update(item for item in record['items'] if isinstance(item, str))
        def target_for(key):
            if key in targets:
                return targets[key]
            for kind in ('preproduction', 'production', 'reference', 'branding', 'character_stock'):
                suffix = kind + '_set_id'
                if key == suffix or key.endswith('_' + suffix):
                    return kind + '_sets'
            return None
        def visit(value, parts=()):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == 'items' and isinstance(item, list):
                        for identity in item:
                            if not isinstance(identity, str) or identity not in maps['items']:
                                self.message('error', 'missing_item_id', MAIN + pointer(parts + (key,)),
                                             'Item ID does not resolve.', str(identity))
                    elif (target := target_for(key)) and item is not None:
                        if not isinstance(item, str):
                            self.message('error', 'invalid_id_reference', MAIN + pointer(parts + (key,)),
                                         f'ID reference to {target} must be a string.')
                        elif item not in maps[target]:
                            self.message('error', 'missing_id', MAIN + pointer(parts + (key,)),
                                         f'ID does not resolve in {target}.', item)
                    visit(item, parts + (key,))
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    visit(item, parts + (index,))
        visit(catalog)

    def check_references(self, document, source, active_productions):
        def historical(parts):
            if len(parts) >= 2 and parts[0] == 'production_sets' and parts[1] not in active_productions:
                return True
            # Only schema-defined history locations may lower a missing file
            # to a note. IDs such as historical_hero remain ordinary IDs.
            return bool(parts) and parts[0] == 'historical_output_availability'
        def required(parts):
            if source == RENDER:
                return True
            if len(parts) < 2:
                return False
            collection, identity = parts[:2]
            return ((collection == 'production_sets' and identity in active_productions)
                    or (collection == 'items' and identity in self.required_items)
                    or (collection == 'reference_sets' and identity in self.required_references)
                    or (collection == 'branding_sets' and identity in self.required_branding))
        def looks_like_path(value):
            return isinstance(value, str) and value.startswith(PATH_ROOTS) and '\n' not in value
        def visit(value, parts=(), parent=None, name=None):
            if isinstance(value, dict):
                bound = {}
                if value.get('sha256') is not None:
                    for field in ('path', 'manifest'):
                        if looks_like_path(value.get(field)):
                            bound[field] = ('sha256', value.get('bytes'))
                            break
                    if not bound and isinstance(name, str) and name.endswith('_evidence') and isinstance(parent, dict):
                        target = name[:-len('_evidence')]
                        if looks_like_path(parent.get(target)):
                            self.reference(parent[target], source, parts[:-1] + (target,), historical(parts),
                                           value['sha256'], value.get('bytes'), required(parts))
                for key, item in value.items():
                    if key.endswith('_sha256') and item is not None:
                        target = key[:-len('_sha256')]
                        if target == 'video' and 'output' in value:
                            target = 'output'
                        if looks_like_path(value.get(target)):
                            bound[target] = (key, value.get('video_bytes') if key == 'video_sha256' else None)
                for key, item in value.items():
                    if key == 'metadata_availability_overrides' or key in ('origin', 'source_projects'):
                        continue
                    if key in ('original_path', 'previous_path'):
                        continue  # History is resolved through its preserved-copy metadata.
                    current = parts + (key,)
                    if source == MAIN and current == ('storage_policy', 'new_reusable_materials_default_location'):
                        continue  # Storage template, never an operational source path.
                    if looks_like_path(item) or (key == 'path' and isinstance(item, str)):
                        # A JSON selector identifies part of an existing file.
                        path = item.split(':', 1)[0]
                        expected = bound.get(key)
                        self.reference(path, source, current, historical(current),
                                       value[expected[0]] if expected else None,
                                       expected[1] if expected else None, required(current))
                    else:
                        visit(item, current, value, key)
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    if looks_like_path(item):
                        self.reference(item.split(':', 1)[0], source, parts + (index,), historical(parts),
                                       required=required(parts))
                    else:
                        visit(item, parts + (index,))
        visit(document)

    def audit_content(self):
        if not self.load_reservations():
            return
        catalog = self.read_json(MAIN, retain=True)
        if isinstance(catalog, dict):
            if catalog.get('schema_version') != 1:
                self.message('error', 'unsupported_catalog_schema', MAIN + '/schema_version',
                             'The workspace verifier supports main catalog schema_version 1.')
            policy = catalog.get('storage_policy', {})
            for key, expected in {'latest_production_only':False, 'latest_adopted_versions_only':False,
                                  'retain_superseded_outputs':True}.items():
                if not isinstance(policy, dict) or policy.get(key) is not expected:
                    self.message('error', 'retention_policy_mismatch', MAIN + '/storage_policy/' + key,
                                 f'Expected {key} to be {str(expected).lower()} to preserve adopted history and dependencies.')
            self.check_ids(catalog)
            self.load_overrides(catalog)
            selected = catalog.get('active_production_set_ids', [])
            active = {item for item in selected if isinstance(item, str)} if isinstance(selected, list) else set()
            self.check_references(catalog, MAIN, active)
            if (self.root / RENDER).is_file():
                render = self.read_json(RENDER, retain=True)
                if isinstance(render, dict):
                    self.check_references(render, RENDER, active)
        elif catalog is not None:
            self.message('error', 'invalid_main_catalog', MAIN, 'Main catalog must be a JSON object.')
        self.scan_managed_files()
        for key in self.overrides.keys() - self.used_overrides:
            self.message('error', 'unused_availability_override', MAIN,
                         'Override did not match a missing checked evidence reference.', key[0] + key[1])

    def control_hash(self, relative):
        path = self.safe_path(relative)
        if not path.exists():
            return 'missing'
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()

    def run(self):
        # reserve/release and the character index writer use this same short
        # lock. It prevents a new live tree appearing after exclusions were
        # established but before the filesystem walk visits its parent.
        try:
            config = self.safe_path(MANAGEMENT)
            if not config.is_file():
                self.message('error', 'missing_management_config', MANAGEMENT,
                             'Cannot establish writer exclusions without the management config.', MANAGEMENT)
            else:
                with management_lock(config.with_suffix(config.suffix + '.lock')):
                    self.control_hashes = {name:self.control_hash(name) for name in (MAIN, MANAGEMENT)}
                    self.audit_content()
                    for name, expected in self.control_hashes.items():
                        if self.control_hash(name) != expected:
                            self.message('error', 'concurrent_metadata_change', name,
                                         'Metadata changed during verification; retry against a stable snapshot.', name)
        except (OSError, ValueError, TypeError, KeyError) as error:
            code = 'management_lock_busy' if 'writer lock exists' in str(error) else 'invalid_structure'
            self.message('error', code, MANAGEMENT, str(error))
        return {'schema_version':1, 'kind':'read-only-workspace-integrity-verification',
                'checked_at_utc':datetime.now(timezone.utc).isoformat(),
                'status':'fail' if self.errors else 'pass', 'root':str(self.root),
                'errors':self.errors, 'notes':self.notes,
                'counts':{'json_documents':len(self.json_checked), 'file_references':len(self.references),
                          'explicit_hash_checks':self.explicit_hashes, 'lfs_pointer_files':len(self.lfs_pointers),
                          'pending_generation_batches':len(self.active), 'unavailable_evidence_overrides':len(self.used_overrides)},
                'excluded_active_roots':[item['root'] for item in self.active],
                'control_file_sha256':self.control_hashes,
                'scope':{'json_trees':list(JSON_SCOPES), 'runtime_reference_catalogs':[MAIN, RENDER],
                         'additional_json':'JSON files directly referenced by checked catalogs.',
                         'not_checked':['Full video rendering, speech recognition and visual quality acceptance.',
                                        'Git commit/push state and arbitrary unregistered output caches.']}}


def verify(root=ROOT):
    return Auditor(root).run()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args(argv)
    result = verify(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
