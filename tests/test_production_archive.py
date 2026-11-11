"""Verify archive closure, relocation, corruption guards and Git ignore behavior."""
from __future__ import annotations

from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('production_archive', REPO / 'tools/update_production_archive.py')
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)


class ProductionArchiveTests(unittest.TestCase):
    def setUp(self):
        preferred = Path('D:/temp')
        self.temp = tempfile.TemporaryDirectory(prefix='youtube-archive-tests-', dir=preferred if preferred.is_dir() else None)
        self.root = Path(self.temp.name).resolve() / 'clone with spaces'
        self.root.mkdir()
        self.write('.gitignore', 'node_modules/\noutput/\n.env\n.env.*\n!.env.example\n')
        self.write('output/current/video.mp4', b'current movie')
        self.write('output/current/master.wav', b'current master')
        self.write('output/old/master.wav', b'unneeded archived master')
        self.write('output/old/speech/I01.wav', b'required adopted speech')
        self.write('output/current/timeline.json', {
            'speech_measurements': {'path': 'D:/codex_projects/youtube/output/current/speech/measurements.json'},
            'old_asr_location': 'D:/temp/discarded-take/initial-asr.json',
        })
        self.write('output/current/speech/measurements.json', {'dialogue': {'path': 'output/old/speech/I01.wav'}})
        self.write('design/production-run-old.json', {'files': [self.entry('output/old/master.wav')]})
        self.record = {
            'files': [self.entry('output/current/video.mp4'), self.entry('output/current/timeline.json'),
                      self.entry('design/production-run-old.json')]
        }
        self.write('design/production-run-current.json', self.record)
        self.write('catalogs/library-v1.json', {
            'active_production_set_ids': ['current'],
            'production_sets': {'current': {'production_record': 'design/production-run-current.json',
                                           'output': 'output/current/video.mp4', 'timeline': 'output/current/timeline.json'}},
        })
        self.policy = {
            'schema_version': 1, 'source_repository_prefixes': ['D:/codex_projects/youtube'],
            'functional_json_names': ['timeline.json', 'measurements.json', 'speech-acceptance.json'],
            'current_delivery_filenames': ['master.wav'], 'additional_required_files': [],
        }
        self.write('reproducibility/archive-policy.json', self.policy)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            path.write_bytes(data)
        elif isinstance(data, str):
            path.write_text(data, encoding='utf-8')
        else:
            path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def entry(self, name):
        return {'path': name, 'sha256': archive.sha256(self.root / name)}

    def paths(self, manifest):
        return {entry['path'] for entry in manifest['files']}

    def require_additional_file(self):
        self.write('output/current/new-evidence.txt', 'new adopted evidence')
        self.policy['additional_required_files'] = [
            {'path': 'output/current/new-evidence.txt', 'reason': 'New required evidence.'}]
        self.write(archive.POLICY, self.policy)

    def assert_publication_cleanup(self):
        self.assertEqual(list(self.root.rglob('*.tmp-*')), [])
        self.assertEqual(list(self.root.rglob('*.lock')), [])

    def test_runtime_old_speech_is_kept_without_unneeded_old_master(self):
        result = archive.build_manifest(self.root)
        self.assertIn('output/old/speech/I01.wav', self.paths(result))
        self.assertIn('output/current/master.wav', self.paths(result))
        self.assertNotIn('output/old/master.wav', self.paths(result))
        self.assertEqual(result['totals']['files'], 5)
        self.assertEqual(result['informational_external_references'][0]['path'], 'D:/temp/discarded-take/initial-asr.json')

    def test_old_absolute_root_maps_to_a_relocated_checkout(self):
        result = archive.build_manifest(self.root)
        self.assertIn('output/current/speech/measurements.json', self.paths(result))
        self.assertTrue(all(not Path(entry['path']).is_absolute() for entry in result['files']))

    def test_dictionary_inventory_is_supported(self):
        self.record['files'] = {entry['path']: entry['sha256'] for entry in self.record['files']}
        self.write('design/production-run-current.json', self.record)
        self.assertIn('output/current/video.mp4', self.paths(archive.build_manifest(self.root)))

    def test_missing_runtime_source_is_an_error_before_writing(self):
        self.write('output/current/speech/measurements.json', {'path': 'output/old/speech/missing.wav'})
        original = (self.root / '.gitignore').read_bytes()
        with self.assertRaisesRegex(archive.ArchiveError, 'Missing required project inputs'):
            archive.run(self.root, write=True)
        self.assertEqual((self.root / '.gitignore').read_bytes(), original)
        self.assertFalse((self.root / archive.MANIFEST).exists())

    def test_corrupt_record_bound_output_is_rejected(self):
        self.write('output/current/video.mp4', b'changed movie')
        with self.assertRaisesRegex(archive.ArchiveError, 'differs from the completed production inventory'):
            archive.build_manifest(self.root)

    def test_explicit_legacy_visual_reference_is_kept(self):
        self.write('output/baseline/frame.png', b'reference pixels')
        self.policy['additional_required_files'] = [{'path': 'output/baseline/frame.png', 'reason': 'Fixed visual comparator input.'}]
        self.write('reproducibility/archive-policy.json', self.policy)
        result = archive.build_manifest(self.root)
        entry = next(row for row in result['files'] if row['path'] == 'output/baseline/frame.png')
        self.assertEqual(entry['reasons'], ['Fixed visual comparator input.'])

    def test_write_and_check_are_idempotent_and_check_does_not_write(self):
        first = archive.run(self.root, write=True)
        self.assertEqual(set(first['updated_files']), {'.gitignore', archive.MANIFEST.as_posix()})
        paths = [self.root / '.gitignore', self.root / archive.MANIFEST]
        before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
        self.assertEqual(archive.run(self.root, write=False)['updated_files'], [])
        self.assertEqual(archive.run(self.root, write=True)['updated_files'], [])
        self.assertEqual(before, [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths])

    def test_check_rejects_stale_manifest_without_mutation(self):
        archive.run(self.root, write=True)
        path = self.root / archive.MANIFEST
        value = json.loads(path.read_text(encoding='utf-8'))
        value['totals']['bytes'] += 1
        self.write(archive.MANIFEST, value)
        before = path.read_bytes()
        with self.assertRaisesRegex(archive.ArchiveError, 'Archive metadata is stale'):
            archive.run(self.root, write=False)
        self.assertEqual(path.read_bytes(), before)

    def test_parent_traversal_is_rejected(self):
        self.write('output/current/timeline.json', {'source_path': 'output/../../../outside.wav'})
        with self.assertRaisesRegex(archive.ArchiveError, 'Unsafe project-relative input'):
            archive.build_manifest(self.root)

    def test_control_changes_during_scan_fail_without_overwriting_the_edit(self):
        archive.run(self.root, write=True)
        original_build = archive._build_manifest
        controls = [archive.CATALOG, archive.POLICY, archive.MANIFEST,
                    Path('.gitignore'), archive.MANAGEMENT]
        for relative in controls:
            with self.subTest(control=str(relative)):
                path = self.root / relative
                old_value = path.read_bytes() if path.exists() else None
                targets = {name: (self.root / name).read_bytes()
                           for name in [archive.MANIFEST, Path('.gitignore')]}
                edited = b'{"schema_version":1,"batches":[],"reservations":[]}\n' if old_value is None else old_value + b'\n'

                def changing_build(root, **kwargs):
                    result = original_build(root, **kwargs)
                    path.write_bytes(edited)
                    return result

                with patch.object(archive, '_build_manifest', side_effect=changing_build):
                    with self.assertRaisesRegex(archive.ArchiveError, 'Concurrent archive control edit'):
                        archive.run(self.root, write=True)
                self.assertEqual(path.read_bytes(), edited)
                for name, before in targets.items():
                    if name != relative:
                        self.assertEqual((self.root / name).read_bytes(), before)
                if old_value is None:
                    path.unlink()
                else:
                    path.write_bytes(old_value)
                self.assert_publication_cleanup()

    def test_existing_shared_locks_are_not_stolen(self):
        for relative in [archive.MANAGEMENT, archive.CATALOG, archive.POLICY,
                         archive.MANIFEST, Path('.gitignore')]:
            with self.subTest(control=str(relative)):
                path = self.root / relative
                lock = path.with_suffix(path.suffix + '.lock')
                lock.parent.mkdir(parents=True, exist_ok=True)
                lock.write_text('another writer token')
                with patch.object(archive, '_build_manifest') as build:
                    with self.assertRaisesRegex(archive.ArchiveError, 'writer lock exists'):
                        archive.run(self.root, write=True)
                    build.assert_not_called()
                self.assertEqual(lock.read_text(), 'another writer token')
                lock.unlink()
                self.assert_publication_cleanup()

    def test_second_writer_cannot_start_while_first_writer_is_scanning(self):
        original_build = archive._build_manifest

        def scanning(root, **kwargs):
            with self.assertRaisesRegex(archive.ArchiveError, 'writer lock exists'):
                archive.run(root, write=True)
            return original_build(root, **kwargs)

        with patch.object(archive, '_build_manifest', side_effect=scanning):
            self.assertEqual(archive.run(self.root, write=True)['status'], 'pass')
        self.assert_publication_cleanup()

    def test_check_respects_the_shared_reservation_lock_without_needing_other_writer_locks(self):
        archive.run(self.root, write=True)
        config = self.root / archive.MANAGEMENT
        lock = config.with_suffix(config.suffix + '.lock')
        with archive.writer_lock(lock):
            with patch.object(archive, '_build_manifest') as build:
                with self.assertRaisesRegex(archive.ArchiveError, 'writer lock exists'):
                    archive.run(self.root, write=False)
                build.assert_not_called()
        for relative in [archive.CATALOG, archive.POLICY, archive.MANIFEST, Path('.gitignore')]:
            with self.subTest(other_writer_lock=str(relative)):
                path = self.root / relative
                with archive.writer_lock(path.with_suffix(path.suffix + '.lock')):
                    self.assertEqual(archive.run(self.root, write=False)['status'], 'pass')
        self.assert_publication_cleanup()

    def test_check_holds_reservation_lock_for_the_entire_scan(self):
        archive.run(self.root, write=True)
        original_build = archive._build_manifest
        config = self.root / archive.MANAGEMENT

        def scanning(root, **kwargs):
            with self.assertRaisesRegex(archive.ArchiveError, 'writer lock exists'):
                with archive.writer_lock(config.with_suffix(config.suffix + '.lock')):
                    self.fail('Reservation writer entered during an archive check')
            return original_build(root, **kwargs)

        with patch.object(archive, '_build_manifest', side_effect=scanning):
            self.assertEqual(archive.run(self.root, write=False)['status'], 'pass')
        self.assert_publication_cleanup()

    def test_direct_build_api_respects_and_holds_the_same_reservation_lock(self):
        config = self.root / archive.MANAGEMENT
        lock = config.with_suffix(config.suffix + '.lock')
        with archive.writer_lock(lock):
            with patch.object(archive, '_build_manifest') as scan:
                with self.assertRaisesRegex(archive.ArchiveError, 'writer lock exists'):
                    archive.build_manifest(self.root)
                scan.assert_not_called()
        original_scan = archive._build_manifest

        def scanning(root, **kwargs):
            with self.assertRaisesRegex(archive.ArchiveError, 'writer lock exists'):
                with archive.writer_lock(lock):
                    self.fail('Reservation writer entered during direct archive scan')
            return original_scan(root, **kwargs)

        with patch.object(archive, '_build_manifest', side_effect=scanning):
            self.assertIn('output/current/video.mp4', self.paths(archive.build_manifest(self.root)))
        self.assert_publication_cleanup()

    def test_both_payloads_are_staged_before_replacing_either_and_stage_failure_preserves_both(self):
        archive.run(self.root, write=True)
        before = {name: (self.root / name).read_bytes()
                  for name in [archive.MANIFEST, Path('.gitignore')]}
        self.require_additional_file()
        original_fsync = archive.os.fsync
        calls = 0

        def fail_second_stage(descriptor):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('synthetic second stage failure')
            return original_fsync(descriptor)

        with patch.object(archive.os, 'fsync', side_effect=fail_second_stage):
            with self.assertRaisesRegex(OSError, 'second stage failure'):
                archive.run(self.root, write=True)
        self.assertEqual(calls, 2)
        for name, data in before.items():
            self.assertEqual((self.root / name).read_bytes(), data)
        self.assert_publication_cleanup()

    def test_ignore_edit_during_staging_is_preserved_and_prevents_publication(self):
        archive.run(self.root, write=True)
        before_manifest = (self.root / archive.MANIFEST).read_bytes()
        before_ignore = (self.root / '.gitignore').read_bytes()
        self.require_additional_file()
        original_fsync = archive.os.fsync
        changed = False

        def concurrent_edit(descriptor):
            nonlocal changed
            result = original_fsync(descriptor)
            if not changed:
                changed = True
                (self.root / '.gitignore').write_bytes(before_ignore + b'# concurrent owner edit\n')
            return result

        with patch.object(archive.os, 'fsync', side_effect=concurrent_edit):
            with self.assertRaisesRegex(archive.ArchiveError, 'Concurrent archive control edit'):
                archive.run(self.root, write=True)
        self.assertEqual((self.root / archive.MANIFEST).read_bytes(), before_manifest)
        self.assertEqual((self.root / '.gitignore').read_bytes(), before_ignore + b'# concurrent owner edit\n')
        self.assert_publication_cleanup()

    def test_ignore_edit_between_individual_replacements_is_not_lost(self):
        archive.run(self.root, write=True)
        old_ignore = (self.root / '.gitignore').read_bytes()
        self.require_additional_file()
        original_replace = archive.os.replace

        def concurrent_edit(source, destination):
            result = original_replace(source, destination)
            if destination == self.root / archive.MANIFEST:
                (self.root / '.gitignore').write_bytes(old_ignore + b'# concurrent owner edit\n')
            return result

        with patch.object(archive.os, 'replace', side_effect=concurrent_edit):
            with self.assertRaisesRegex(archive.ArchiveError, 'publication interrupted after individual atomic replacement'):
                archive.run(self.root, write=True)
        self.assertEqual((self.root / '.gitignore').read_bytes(), old_ignore + b'# concurrent owner edit\n')
        current = json.loads((self.root / archive.MANIFEST).read_text())
        self.assertIn('output/current/new-evidence.txt', self.paths(current))
        self.assert_publication_cleanup()
        archive.run(self.root, write=True)
        self.assertEqual(archive.run(self.root, write=False)['status'], 'pass')
        self.assertIn('# concurrent owner edit', (self.root / '.gitignore').read_text())

    def test_second_replace_failure_is_explicit_and_keeps_complete_recoverable_files(self):
        archive.run(self.root, write=True)
        old_ignore = (self.root / '.gitignore').read_bytes()
        self.require_additional_file()
        original_replace = archive.os.replace

        def fail_ignore(source, destination):
            if destination == self.root / '.gitignore':
                raise OSError('synthetic replacement failure')
            return original_replace(source, destination)

        with patch.object(archive.os, 'replace', side_effect=fail_ignore):
            with self.assertRaisesRegex(archive.ArchiveError, 'publication interrupted after individual atomic replacement'):
                archive.run(self.root, write=True)
        current = json.loads((self.root / archive.MANIFEST).read_text())
        self.assertIn('output/current/new-evidence.txt', self.paths(current))
        self.assertEqual((self.root / '.gitignore').read_bytes(), old_ignore)
        self.assert_publication_cleanup()
        archive.run(self.root, write=True)
        self.assertEqual(archive.run(self.root, write=False)['status'], 'pass')

    def test_first_replace_failure_preserves_both_previous_outputs(self):
        archive.run(self.root, write=True)
        before = {name: (self.root / name).read_bytes()
                  for name in [archive.MANIFEST, Path('.gitignore')]}
        self.require_additional_file()
        with patch.object(archive.os, 'replace', side_effect=OSError('synthetic first replacement failure')):
            with self.assertRaisesRegex(OSError, 'first replacement failure'):
                archive.run(self.root, write=True)
        for name, data in before.items():
            self.assertEqual((self.root / name).read_bytes(), data)
        self.assert_publication_cleanup()

    def test_active_runtime_reference_is_rejected_before_any_probe_or_read(self):
        reserved = self.root / 'assets/library/characters/cat/generation-batches/live'
        self.write(archive.MANAGEMENT, {'schema_version': 1, 'batches': [], 'reservations': [
            {'id': 'live', 'status': 'active', 'owner': 'other-ai',
             'root': reserved.relative_to(self.root).as_posix()}]})
        self.write('output/current/timeline.json', {'source': reserved.relative_to(self.root).as_posix() + '/original.png'})
        original_stat = Path.stat
        original_open = Path.open

        def guarded_stat(path, *args, **kwargs):
            self.assertFalse(path.is_relative_to(reserved), 'Active source metadata was probed')
            return original_stat(path, *args, **kwargs)

        def guarded_open(path, *args, **kwargs):
            self.assertFalse(path.is_relative_to(reserved), 'Active source was opened')
            return original_open(path, *args, **kwargs)

        self.record['files'] = [entry for entry in self.record['files']
                                if entry['path'] != 'output/current/timeline.json']
        self.write('design/production-run-current.json', self.record)
        with patch.object(Path, 'stat', guarded_stat), patch.object(Path, 'open', guarded_open):
            with self.assertRaisesRegex(archive.ArchiveError, 'Active generation source must not be read'):
                archive.run(self.root, write=True)
        self.assertFalse((self.root / archive.MANIFEST).exists())
        self.assert_publication_cleanup()

    def test_active_case_alias_is_rejected_before_stat_open_or_other_path_probes(self):
        reserved = self.root / 'assets/library/characters/cat/generation-batches/live'
        name = reserved.relative_to(self.root).as_posix()
        self.write(name + '/timeline.json', {'private_generation': 'must stay opaque'})
        self.write(archive.MANAGEMENT, {'schema_version': 1, 'batches': [], 'reservations': [
            {'id': 'live', 'status': 'active', 'owner': 'other-ai', 'root': name}]})
        self.record['files'] = [entry for entry in self.record['files']
                                if entry['path'] != 'output/current/timeline.json']
        self.write('design/production-run-current.json', self.record)
        originals = {method: getattr(Path, method) for method in ['stat', 'open', 'is_file', 'is_dir', 'is_symlink']}

        def protect(method):
            def guarded(path, *args, **kwargs):
                value = str(path).replace('\\', '/').casefold()
                prefix = str(reserved).replace('\\', '/').casefold()
                self.assertFalse(value == prefix or value.startswith(prefix + '/'),
                                 f'Active case alias reached Path.{method}: {path}')
                return originals[method](path, *args, **kwargs)
            return guarded

        for spelling in ['LIVE', 'LiVe']:
            with self.subTest(spelling=spelling):
                alias = name.rsplit('/', 1)[0] + '/' + spelling + '/timeline.json'
                self.write('output/current/timeline.json', {'source': alias})
                with ExitStack() as stack:
                    for method in originals:
                        stack.enter_context(patch.object(Path, method, protect(method)))
                    with self.assertRaisesRegex(archive.ArchiveError, 'Active generation source must not be read'):
                        archive.run(self.root, write=False)
                self.assert_publication_cleanup()

    def test_transitive_json_change_immediately_after_read_fails_check_and_write(self):
        archive.run(self.root, write=True)
        self.write('output/old/speech/I02.wav', b'new adopted speech candidate')
        path = self.root / 'output/current/speech/measurements.json'
        old_value = path.read_bytes()
        outputs = {name: (self.root / name).read_bytes()
                   for name in [archive.MANIFEST, Path('.gitignore')]}
        original_read = archive.read_json
        for write in [False, True]:
            with self.subTest(write=write):
                path.write_bytes(old_value)
                changed = False

                def changing_read(candidate):
                    nonlocal changed
                    value = original_read(candidate)
                    if candidate == path and not changed:
                        changed = True
                        self.write(path.relative_to(self.root), {'dialogue': {'path': 'output/old/speech/I02.wav'}})
                    return value

                with patch.object(archive, 'read_json', side_effect=changing_read):
                    with self.assertRaisesRegex(archive.ArchiveError, 'dependency JSON changed during scan'):
                        archive.run(self.root, write=write)
                self.assertTrue(changed)
                self.assertIn('I02.wav', path.read_text())
                for name, content in outputs.items():
                    self.assertEqual((self.root / name).read_bytes(), content)
                self.assert_publication_cleanup()

    def test_transitive_json_change_after_its_entry_was_hashed_fails_final_scan_guard(self):
        archive.run(self.root, write=True)
        self.write('output/old/speech/I02.wav', b'new adopted speech candidate')
        path = self.root / 'output/current/speech/measurements.json'
        before = (self.root / archive.MANIFEST).read_bytes()
        original_hash = archive.sha256
        changed = False

        def changing_hash(candidate):
            nonlocal changed
            value = original_hash(candidate)
            if candidate == self.root / 'output/old/speech/I01.wav' and not changed:
                changed = True
                self.write(path.relative_to(self.root), {'dialogue': {'path': 'output/old/speech/I02.wav'}})
            return value

        with patch.object(archive, 'sha256', side_effect=changing_hash):
            with self.assertRaisesRegex(archive.ArchiveError, 'dependency JSON changed during scan'):
                archive.run(self.root, write=True)
        self.assertTrue(changed)
        self.assertEqual((self.root / archive.MANIFEST).read_bytes(), before)
        self.assert_publication_cleanup()

    def test_transitive_json_change_during_staging_prevents_both_publications(self):
        archive.run(self.root, write=True)
        self.require_additional_file()
        self.write('output/old/speech/I02.wav', b'new adopted speech candidate')
        outputs = {name: (self.root / name).read_bytes()
                   for name in [archive.MANIFEST, Path('.gitignore')]}
        original_fsync = archive.os.fsync
        changed = False

        def changing_fsync(descriptor):
            nonlocal changed
            value = original_fsync(descriptor)
            if not changed:
                changed = True
                self.write('output/current/speech/measurements.json', {'dialogue': {'path': 'output/old/speech/I02.wav'}})
            return value

        with patch.object(archive.os, 'fsync', side_effect=changing_fsync):
            with self.assertRaisesRegex(archive.ArchiveError, 'dependency JSON changed before publication'):
                archive.run(self.root, write=True)
        self.assertTrue(changed)
        for name, content in outputs.items():
            self.assertEqual((self.root / name).read_bytes(), content)
        self.assert_publication_cleanup()

    def test_unreferenced_active_generation_is_opaque_and_does_not_block_archive(self):
        reserved = self.root / 'assets/library/characters/cat/generation-batches/live'
        self.write(archive.MANAGEMENT, {'schema_version': 1, 'batches': [], 'reservations': [
            {'id': 'live', 'status': 'active', 'owner': 'other-ai',
             'root': reserved.relative_to(self.root).as_posix()}]})
        original_stat = Path.stat

        def guarded_stat(path, *args, **kwargs):
            self.assertFalse(path.is_relative_to(reserved), 'Unreferenced active root was probed')
            return original_stat(path, *args, **kwargs)

        with patch.object(Path, 'stat', guarded_stat):
            self.assertEqual(archive.run(self.root, write=True)['status'], 'pass')
        self.assert_publication_cleanup()

    def test_new_reservation_during_scan_stops_before_the_reserved_source_is_probed(self):
        reserved = self.root / 'assets/library/characters/cat/generation-batches/new-live'
        name = reserved.relative_to(self.root).as_posix()
        self.write(name + '/original.png', b'fixture candidate pixels')
        self.write('output/current/timeline.json', {'source': name + '/original.png'})
        self.record['files'] = [entry for entry in self.record['files']
                                if entry['path'] != 'output/current/timeline.json']
        self.record['files'].append(self.entry('output/current/timeline.json'))
        self.write('design/production-run-current.json', self.record)
        original_read = archive.read_json
        original_stat = Path.stat
        reservation_started = False

        def changing_read(path):
            nonlocal reservation_started
            value = original_read(path)
            if path == self.root / 'output/current/timeline.json':
                self.write(archive.MANAGEMENT, {'schema_version': 1, 'batches': [], 'reservations': [
                    {'id': 'new-live', 'status': 'active', 'owner': 'other-ai',
                     'root': name}]})
                reservation_started = True
            return value

        def guarded_stat(path, *args, **kwargs):
            if reservation_started:
                self.assertFalse(path.is_relative_to(reserved), 'Source probed after reservation control changed')
            return original_stat(path, *args, **kwargs)

        with patch.object(archive, 'read_json', side_effect=changing_read), patch.object(Path, 'stat', guarded_stat):
            with self.assertRaisesRegex(archive.ArchiveError, 'management config changed during archive scan'):
                archive.run(self.root, write=True)
        self.assertTrue(reservation_started)
        self.assertFalse((self.root / archive.MANIFEST).exists())
        self.assert_publication_cleanup()

    def test_destination_symlink_is_rejected_without_changing_target(self):
        target = self.root / 'output/old/master.wav'
        before = target.read_bytes()
        destination = self.root / archive.MANIFEST
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            destination.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest('Symlink creation is not available')
        with self.assertRaisesRegex(archive.ArchiveError, 'must not contain a symlink'):
            archive.run(self.root, write=True)
        self.assertEqual(target.read_bytes(), before)
        self.assertTrue(destination.is_symlink())
        self.assert_publication_cleanup()

    @unittest.skipUnless(shutil.which('git'), 'Git is required to verify ignore semantics')
    def test_git_allows_exact_files_and_keeps_other_outputs_and_secrets_ignored(self):
        archive.run(self.root, write=True)
        subprocess.run(['git', 'init', '--quiet'], cwd=self.root, check=True, capture_output=True)
        self.write('output/current/extra-cache.wav', b'local cache')
        self.write('node_modules/local.js', 'dependency')
        self.write('.env', 'not a real secret')
        self.write('.env.example', 'example placeholder')
        wanted = ['output/current/video.mp4', 'output/old/speech/I01.wav', '.env.example']
        ignored = ['output/old/master.wav', 'output/current/extra-cache.wav', 'node_modules/local.js', '.env']
        for name in wanted:
            result = subprocess.run(['git', 'check-ignore', '--no-index', name], cwd=self.root, capture_output=True)
            self.assertEqual(result.returncode, 1, name)
        for name in ignored:
            result = subprocess.run(['git', 'check-ignore', '--no-index', name], cwd=self.root, capture_output=True)
            self.assertEqual(result.returncode, 0, name)


if __name__ == '__main__':
    unittest.main()
