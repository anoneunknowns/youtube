"""Exercise ownership, no-adoption discovery and concurrent-write rejection."""
from __future__ import annotations

import copy
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import manage_character_assets as management


@contextmanager
def reject_writer_probes(active):
    """Watch lexical aliases as well as the actual spelling, before any I/O."""
    prefixes = {os.path.abspath(active).casefold(),
                os.path.abspath(active.parent.resolve() / active.name).casefold()}
    def guarded(original):
        def call(path, *args, **kwargs):
            if not isinstance(path, int):
                value = os.path.abspath(os.fsdecode(path)).casefold()
                if any(value == prefix or value.startswith(prefix + os.sep) for prefix in prefixes):
                    raise AssertionError(f'Active writer path was probed by {original.__name__}: {path}')
            return original(path, *args, **kwargs)
        return call
    with ExitStack() as stack:
        for name in ('stat', 'open', 'resolve', 'is_symlink', 'is_file', 'is_dir'):
            stack.enter_context(patch.object(Path, name, guarded(getattr(Path, name))))
        for name in ('lstat', 'scandir'):
            stack.enter_context(patch.object(os, name, guarded(getattr(os, name))))
        yield


class CharacterAssetManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / management.CONFIG
        self.registry = self.root / management.REGISTRY
        self.folder = 'assets/library/characters/kangaroo/animations/prime-v001'
        self.candidate = 'assets/library/characters/kangaroo/animations/prime-v002'
        self.source = self.make(self.folder + '/source-sheet.png', b'original unchanged raster fixture')
        self.frame = self.make(self.folder + '/frames/neutral.png', b'lossless frame fixture')
        self.registration = self.make(self.folder + '/registration.json', json.dumps({
            'source_sheet': self.folder + '/source-sheet.png',
            'frames': [{'id': 'neutral', 'path': self.folder + '/frames/neutral.png'}]}).encode())
        self.make(self.candidate + '/presentation-candidate.png', b'unselected parallel candidate')
        self.document = {'schema_version': 1, 'batches': [{
            'root': self.folder, 'character_id': 'kangaroo', 'state': 'episode_selected',
            'owner': 'finished-production', 'scope': 'prime episode only',
            'registration_paths': [self.folder + '/registration.json'],
            'quality_reviews': [{'path': self.folder + '/registration.json', 'style_status': 'needs_revision'}]}],
            'reservations': []}
        self.write_config()

    def make(self, path, data):
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return destination

    def write_config(self):
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_bytes(management.canonical_json(self.document))

    def test_unknown_parallel_candidate_is_unclassified_not_adopted(self):
        before = self.source.read_bytes()
        snapshot = management.inspect(self.root, self.config)
        records = {b['root']: b for b in snapshot['batches']}
        self.assertEqual(records[self.folder]['state'], 'episode_selected')
        self.assertEqual(records[self.candidate]['state'], 'unclassified')
        self.assertFalse(records[self.candidate]['explicitly_classified'])
        role = records[self.candidate]['files'][0]['roles'][0]['role']
        self.assertEqual(role, 'generation_candidate')
        self.assertEqual(records[self.folder]['quality_reviews'][0]['style_status'], 'needs_revision')
        self.assertEqual(self.source.read_bytes(), before)
        self.assertFalse(self.registry.exists())

    def test_gimmick_category_is_preserved_in_the_shared_registry(self):
        self.document['batches'][0]['category'] = 'gimmick'
        self.write_config()
        snapshot = management.inspect(self.root, self.config)
        rows = {row['root']: row for row in snapshot['batches']}
        self.assertEqual(rows[self.folder]['category'], 'gimmick')
        self.assertEqual(rows[self.candidate]['category'], 'character')
        markup = management.render_index(self.root, snapshot, self.document,
                                         management.CONFIG, management.REGISTRY).decode()
        self.assertIn('背景ギミック', markup)
        self.document['batches'][0]['category'] = 'unknown'
        self.write_config()
        with self.assertRaisesRegex(ValueError, 'Unknown asset category'):
            management.inspect(self.root, self.config)

    def test_registered_roles_and_exact_hashes_are_preserved(self):
        result = management.refresh(self.root, self.config, self.registry, 'missing')
        self.assertEqual(result['status'], 'pass')
        record = json.loads(self.registry.read_text())['batches'][0]
        paths = {f['path']: f for f in record['files']}
        self.assertEqual(paths[self.folder + '/source-sheet.png']['roles'][0]['role'], 'source_sheet')
        self.assertEqual(paths[self.folder + '/frames/neutral.png']['roles'][0]['role'], 'registered_frame')
        self.assertEqual(paths[self.folder + '/source-sheet.png']['sha256'], management.current_hash(self.source))
        self.assertEqual(management.check(self.root, self.config, self.registry)['status'], 'pass')
        self.make(self.folder + '/frames/neutral.png', b'different frame')
        with self.assertRaisesRegex(ValueError, 'stale'):
            management.check(self.root, self.config, self.registry)

    def test_active_writer_tree_is_pending_and_not_hashed(self):
        self.document['batches'].append({'root': self.candidate, 'state': 'candidate', 'owner': 'parallel-chat'})
        self.document['reservations'].append({'id': 'prime-v2-live', 'root': self.candidate,
                                              'owner': 'parallel-chat', 'status': 'active'})
        self.write_config()
        original = management.file_record
        def guarded(root, path):
            if management.contains(self.candidate, management.relative(root, path)):
                self.fail('Active writer file was read or hashed')
            return original(root, path)
        with patch.object(management, 'file_record', side_effect=guarded):
            result = management.inspect(self.root, self.config)
        live = next(b for b in result['batches'] if b['root'] == self.candidate)
        self.assertEqual(live['inventory_status'], 'pending-active-writer')
        self.assertEqual(live['files'], [])
        self.assertEqual(live['active_reservations'][0]['owner'], 'parallel-chat')

    def test_case_alias_references_and_reverse_reservation_are_opaque_before_probing(self):
        alias = self.candidate.replace('prime-v002', 'PRIME-v002')
        private = alias + '/unfinished.json'
        self.make(self.candidate + '/unfinished.json', b'{incomplete private output')
        item = self.document['batches'][0]
        for field in ('registration_paths', 'selection_evidence', 'quality_reviews'):
            item[field] = [private]
        item['canonical_reference'] = private
        item['file_roles'] = {private: 'identity_reference'}
        self.registration.write_text(json.dumps({'canonical_neutral': {'path': private}}))
        self.document['batches'].append({'root': self.candidate, 'state': 'candidate'})
        for reservation in (self.candidate, alias):
            with self.subTest(reservation=reservation):
                self.document['reservations'] = [{'id': 'live-case', 'owner': 'parallel',
                                                  'root': reservation, 'status': 'active'}]
                self.write_config()
                with reject_writer_probes(self.root / self.candidate):
                    result = management.inspect(self.root, self.config)
                    self.assertEqual(management.walk_files(self.root, self.root / alias,
                                                           [reservation]), [])
                finished = next(row for row in result['batches'] if row['root'] == self.folder)
                for field in ('registration_paths', 'selection_evidence', 'quality_reviews'):
                    self.assertEqual(finished[field], [])
                    self.assertEqual(finished[field + '_pending'], [private])
                self.assertEqual(finished['canonical_reference_pending'], private)
                active = next(row for row in result['batches'] if row['root'] == self.candidate)
                self.assertEqual(active['files'], [])
                self.assertEqual(active['inventory_status'], 'pending-active-writer')

    def test_case_alias_cannot_hide_frozen_inventory_or_avoid_reservation_collision(self):
        inventory = self.root / 'catalogs/character-library-files-v1.json'
        inventory.write_text(json.dumps({'files': [{'path': self.folder + '/source-sheet.png'}]}))
        alias = self.folder.replace('prime-v001', 'PRIME-v001')
        with reject_writer_probes(self.root / self.folder):
            with self.assertRaisesRegex(ValueError, 'frozen inventoried files'):
                management.reserve(self.root, self.config, alias, 'wrong-worker', 'hidden')
        management.reserve(self.root, self.config, self.candidate, 'worker-a', 'owner-a')
        alias = self.candidate.replace('prime-v002', 'PRIME-v002')
        with reject_writer_probes(self.root / self.candidate):
            with self.assertRaisesRegex(ValueError, 'collision'):
                management.reserve(self.root, self.config, alias + '/nested', 'worker-b', 'owner-b')

    def test_non_writer_path_cannot_follow_a_symlink_outside_the_project(self):
        with tempfile.TemporaryDirectory() as outside:
            alias = self.root / self.folder / 'external'
            alias.symlink_to(Path(outside), target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'must not contain a symlink'):
                management.project_path(self.root, self.folder + '/external/source.png')

    def test_new_reservation_cannot_claim_an_external_symlink(self):
        before = self.config.read_bytes()
        with tempfile.TemporaryDirectory() as outside:
            alias = self.root / self.candidate / 'external'
            alias.symlink_to(Path(outside), target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'must not contain a symlink'):
                management.reserve(self.root, self.config, self.candidate + '/external', 'writer', 'bad-alias')
        self.assertEqual(self.config.read_bytes(), before)

    def test_non_writer_symlink_to_writer_rejected_without_probing_its_target(self):
        alias = self.root / self.folder / 'linked.png'
        alias.symlink_to(self.root / self.candidate / 'private.png')
        folder_alias = self.root / 'linked-directory'
        folder_alias.symlink_to(self.root / self.candidate, target_is_directory=True)
        with reject_writer_probes(self.root / self.candidate):
            with self.assertRaisesRegex(ValueError, 'Symlink is not an owned source'):
                management.walk_files(self.root, self.root / self.folder, [self.candidate])
            with self.assertRaisesRegex(ValueError, 'must not contain a symlink'):
                management.walk_files(self.root, folder_alias, [self.candidate])

    def test_source_and_directory_changes_during_scan_abort_publication(self):
        original = management.snapshot
        calls = 0
        def mutating(*args):
            nonlocal calls
            result = original(*args)
            calls += 1
            if calls == 1:
                self.make(self.folder + '/new-generated.png', b'new parallel source')
            return result
        with patch.object(management, 'snapshot', side_effect=mutating):
            with self.assertRaisesRegex(ValueError, 'Source changed during scan'):
                management.refresh(self.root, self.config, self.registry)
        self.assertFalse(self.registry.exists())

    def test_read_scans_hold_the_config_lock_before_discovery_until_completion(self):
        management.refresh(self.root, self.config, self.registry)
        original = management.walk_files
        attempted = []
        def racing_walk(*args):
            attempted.append(True)
            with self.assertRaisesRegex(ValueError, 'writer lock exists'):
                management.reserve(self.root, self.config, self.candidate, 'parallel', 'racing-claim')
            return original(*args)
        operations = [lambda: management.inspect(self.root, self.config),
                      lambda: management.build_snapshot(self.root, self.config),
                      lambda: management.prepare_publication(self.root, self.config),
                      lambda: management.check(self.root, self.config, self.registry),
                      lambda: management.refresh(self.root, self.config, self.registry)]
        with patch.object(management, 'walk_files', side_effect=racing_walk):
            for operation in operations:
                before = len(attempted)
                self.assertIsNotNone(operation())
                self.assertGreater(len(attempted), before)
        self.assertEqual(json.loads(self.config.read_text())['reservations'], [])
        self.assertEqual(list(self.config.parent.glob('*.lock')), [])

    def test_reserve_and_release_lock_the_config_before_reading_and_validation(self):
        original = management.read_config
        attempted = []
        def racing_read(*args, **kwargs):
            attempted.append(True)
            with self.assertRaisesRegex(ValueError, 'writer lock exists'):
                management.reserve(self.root, self.config, self.candidate, 'parallel', 'racing-claim')
            return original(*args, **kwargs)
        with patch.object(management, 'read_config', side_effect=racing_read):
            management.reserve(self.root, self.config, self.candidate, 'owner', 'owner-claim')
            management.release(self.root, self.config, 'owner-claim', 'owner')
        self.assertEqual(len(attempted), 2)
        self.assertEqual([r['status'] for r in json.loads(self.config.read_text())['reservations']], ['released'])

    def test_existing_config_lock_is_not_stolen_by_readers_or_writers(self):
        path = self.config.with_suffix('.json.lock')
        path.write_text('existing-owner')
        before = self.config.read_bytes()
        operations = [lambda: management.inspect(self.root, self.config),
                      lambda: management.build_snapshot(self.root, self.config),
                      lambda: management.prepare_publication(self.root, self.config),
                      lambda: management.check(self.root, self.config, self.registry),
                      lambda: management.refresh(self.root, self.config, self.registry),
                      lambda: management.reserve(self.root, self.config, self.candidate, 'new', 'new'),
                      lambda: management.release(self.root, self.config, 'none', 'none')]
        with patch.object(management, 'file_record', side_effect=AssertionError('Source read while locked')):
            for operation in operations:
                with self.assertRaisesRegex(ValueError, 'writer lock exists'):
                    operation()
                self.assertEqual(path.read_text(), 'existing-owner')
        self.assertEqual(self.config.read_bytes(), before)

    def test_config_and_registry_concurrent_edits_are_not_overwritten(self):
        original = management._build_snapshot_locked
        def config_change(*args):
            result = original(*args)
            self.document['notes'] = 'parallel change must survive'
            self.write_config()
            return result
        with patch.object(management, '_build_snapshot_locked', side_effect=config_change):
            with self.assertRaisesRegex(ValueError, 'Concurrent management config edit'):
                management.refresh(self.root, self.config, self.registry)
        self.assertEqual(json.loads(self.config.read_text())['notes'], 'parallel change must survive')
        self.assertFalse(self.registry.exists())
        def registry_change(*args):
            result = original(*args)
            self.registry.write_text('another manager published')
            return result
        with patch.object(management, '_build_snapshot_locked', side_effect=registry_change):
            with self.assertRaisesRegex(ValueError, 'Concurrent management edit'):
                management.refresh(self.root, self.config, self.registry)
        self.assertEqual(self.registry.read_text(), 'another manager published')

    def test_reservation_collision_owner_release_and_no_automatic_expiry(self):
        management.reserve(self.root, self.config, self.candidate, 'chat-A', 'a')
        with self.assertRaisesRegex(ValueError, 'collision'):
            management.reserve(self.root, self.config, self.candidate + '/nested', 'chat-B', 'b')
        with self.assertRaisesRegex(ValueError, 'matching active reservation owner'):
            management.release(self.root, self.config, 'a', 'chat-B')
        management.release(self.root, self.config, 'a', 'chat-A')
        management.reserve(self.root, self.config, self.candidate, 'chat-B', 'b')
        states = [r['status'] for r in json.loads(self.config.read_text())['reservations']]
        self.assertEqual(states, ['released', 'active'])

    def test_wrong_expected_hash_and_existing_writer_lock_abort(self):
        with self.assertRaisesRegex(ValueError, 'Expected registry hash differs'):
            management.refresh(self.root, self.config, self.registry, '0'*64)
        lock = self.registry.with_suffix('.json.lock')
        lock.write_text('someone-else')
        with self.assertRaisesRegex(ValueError, 'writer lock exists'):
            management.refresh(self.root, self.config, self.registry)
        self.assertEqual(lock.read_text(), 'someone-else')
        self.assertFalse(self.registry.exists())

    def test_evidence_hash_mismatch_and_path_escape_rejected(self):
        self.document['batches'][0]['registration_paths'] = [{'path': self.folder + '/registration.json',
                                                             'sha256': '0'*64}]
        self.write_config()
        with self.assertRaisesRegex(ValueError, 'Declared evidence changed'):
            management.inspect(self.root, self.config)
        with self.assertRaisesRegex(ValueError, 'leaves project'):
            management.project_path(self.root, '../../elsewhere')

    def test_loose_image_beside_versioned_children_is_not_dropped_or_duplicated(self):
        loose = self.make('assets/library/characters/kangaroo/animations/loose.png', b'loose new image')
        result = management.inspect(self.root, self.config)
        paths = [f['path'] for b in result['batches'] for f in b['files']]
        self.assertIn(management.relative(self.root, loose), paths)
        self.assertEqual(len(paths), len(set(paths)))
        broad = next(b for b in result['batches'] if b['root'].endswith('/animations'))
        self.assertEqual(broad['state'], 'unclassified')
        self.assertIn(self.folder, broad['excluded_child_batch_roots'])

    def test_explicit_unique_batch_does_not_create_an_empty_unclassified_parent(self):
        batch = 'assets/library/characters/kangaroo/generation-batches/task-a-f83c'
        self.document['batches'].append({'root': batch, 'state': 'candidate', 'owner': 'chat-a'})
        self.write_config()
        image = self.make(batch + '/source/original.png', b'unique task source')
        result = management.inspect(self.root, self.config)
        roots = {item['root'] for item in result['batches']}
        self.assertEqual(roots, {self.folder, self.candidate, batch})
        self.assertEqual(result['totals']['unclassified_batches'], 1)  # Existing prime-v002 only.
        recorded = [entry['path'] for item in result['batches'] for entry in item['files']]
        self.assertEqual(recorded.count(management.relative(self.root, image)), 1)

    def test_frozen_inventory_cannot_be_hidden_with_a_live_reservation(self):
        inventory = self.root / 'catalogs/character-library-files-v1.json'
        inventory.write_text(json.dumps({'files': [{'path': self.folder + '/source-sheet.png'}]}))
        with self.assertRaisesRegex(ValueError, 'frozen inventoried files'):
            management.reserve(self.root, self.config, self.folder, 'wrong-worker', 'frozen-claim')
        self.document['reservations'] = [{'id': 'bad-manual-claim', 'root': self.folder,
                                          'owner': 'wrong-worker', 'status': 'active'}]
        self.write_config()
        with self.assertRaisesRegex(ValueError, 'frozen inventoried files'):
            management.inspect(self.root, self.config)
        # Owner release restores visibility rather than requiring a manual edit.
        management.release(self.root, self.config, 'bad-manual-claim', 'wrong-worker')
        self.assertEqual(management.inspect(self.root, self.config)['active_reservations'], [])

    def test_registry_publish_cannot_overwrite_config_other_catalog_or_source_art(self):
        config_bytes = self.config.read_bytes()
        with self.assertRaisesRegex(ValueError, 'must not overwrite its management config'):
            management.refresh(self.root, self.config, self.config)
        self.assertEqual(self.config.read_bytes(), config_bytes)
        other = self.make('catalogs/library-v1.json', b'{"schema_version":1,"production_sets":{}}')
        original = other.read_bytes()
        with self.assertRaisesRegex(ValueError, 'not this management registry'):
            management.refresh(self.root, self.config, other)
        self.assertEqual(other.read_bytes(), original)
        with self.assertRaisesRegex(ValueError, 'limited to JSON metadata under catalogs'):
            management.refresh(self.root, self.config, self.source)

    def test_refresh_and_check_keep_the_fixed_human_index_current(self):
        before = management.refresh(self.root, self.config, self.registry)
        page = self.root / management.HUMAN_INDEX
        self.assertEqual(before['index'], management.HUMAN_INDEX)
        self.assertEqual(before['index_sha256'], management.current_hash(page))
        self.assertIn('2バッチ', page.read_text())
        management.reserve(self.root, self.config, self.candidate, 'chat-b', 'live-b')
        management.refresh(self.root, self.config, self.registry)
        self.assertIn('生成中1バッチ', page.read_text())
        self.assertIn('生成中・確定保留', page.read_text())
        self.assertEqual(management.check(self.root, self.config, self.registry)['status'], 'pass')
        page.write_text('manually stale human index')
        with self.assertRaisesRegex(ValueError, 'Human asset index is missing or stale'):
            management.check(self.root, self.config, self.registry)
        management.refresh(self.root, self.config, self.registry)
        self.assertIn('生成中1バッチ', page.read_text())
        self.assertEqual(management.check(self.root, self.config, self.registry)['status'], 'pass')

    def test_batch_quality_status_takes_precedence_over_character_assessment(self):
        review = self.document['batches'][0]['quality_reviews'][0]
        review.update(status='acceptable_with_notes', character_assessment='OTHER SHEET NEEDS REVISION')
        self.write_config()
        management.refresh(self.root, self.config, self.registry)
        text = (self.root / management.HUMAN_INDEX).read_text()
        self.assertIn('概ね良好・軽微差', text)
        self.assertNotIn('OTHER SHEET NEEDS REVISION', text)

    def test_concurrent_human_index_edit_is_not_overwritten(self):
        original = management._build_snapshot_locked
        page = self.root / management.HUMAN_INDEX
        def concurrent(*args):
            result = original(*args)
            page.write_text('another publisher changed the index')
            return result
        with patch.object(management, '_build_snapshot_locked', side_effect=concurrent):
            with self.assertRaisesRegex(ValueError, 'Concurrent management edit'):
                management.refresh(self.root, self.config, self.registry)
        self.assertEqual(page.read_text(), 'another publisher changed the index')
        self.assertFalse(self.registry.exists())

    def test_reservation_cannot_change_config_during_publication(self):
        original_replace = management.os.replace
        attempted = []
        def reserve_during_replace(source, destination):
            if Path(destination) == management.human_index_path(self.root):
                attempted.append(True)
                with self.assertRaisesRegex(ValueError, 'writer lock exists'):
                    management.reserve(self.root, self.config, self.candidate, 'chat-b', 'racing-claim')
            return original_replace(source, destination)
        with patch.object(management.os, 'replace', side_effect=reserve_during_replace):
            management.refresh(self.root, self.config, self.registry)
        self.assertEqual(attempted, [True])
        self.assertEqual(management.check(self.root, self.config, self.registry)['status'], 'pass')
        management.reserve(self.root, self.config, self.candidate, 'chat-b', 'after-publication')

    def test_human_index_symlink_cannot_redirect_publication_to_source_art(self):
        page = self.root / management.HUMAN_INDEX
        original = self.source.read_bytes()
        page.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, 'must not contain a symlink'):
            management.refresh(self.root, self.config, self.registry)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(self.registry.exists())
        page.unlink()
        parent_alias_root = self.root / 'alias-project'
        parent_alias_root.mkdir()
        (parent_alias_root / 'assets').symlink_to(self.root / 'assets', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'must not contain a symlink'):
            management.human_index_path(parent_alias_root)


if __name__ == '__main__':
    unittest.main()
