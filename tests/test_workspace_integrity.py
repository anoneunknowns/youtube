"""Exercise workspace references, exact evidence exceptions and writer opacity."""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import verify_workspace as workspace
from tools import manage_character_assets as management


class WorkspaceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.art = 'assets/library/characters/example/sources/v001/neutral.png'
        self.write(self.art, b'owned original artwork fixture')
        self.write('output/current/movie.mp4', b'owned current media fixture')
        self.write_json('output/current/timeline.json', {'revision_id':'current'})
        self.write_json('assets/library/references/example/v001/manifest.json', {'reference_set_id':'reference'})
        self.management = {'schema_version':1, 'batches':[], 'reservations':[]}
        self.write_json(workspace.MANAGEMENT, self.management)
        self.catalog = {
            'schema_version':1, 'catalog_id':'fixture',
            'storage_policy':{'latest_production_only':False, 'latest_adopted_versions_only':False,
                              'retain_superseded_outputs':False,
                              'new_reusable_materials_default_location':'assets/library/<category>/<name>/<version>/'},
            'items':{'character':{'path':self.art, 'sha256':self.sha(self.art)}},
            'reference_sets':{'reference':{'items':['character'],
                'manifest':'assets/library/references/example/v001/manifest.json'}},
            'production_sets':{'current':{'items':['character'], 'visual_reference_set_id':'reference',
                'output':'output/current/movie.mp4', 'video_sha256':self.sha('output/current/movie.mp4'),
                'timeline':'output/current/timeline.json'}},
            'active_production_set_ids':['current'], 'active_reference_set_ids':['reference']}
        self.save_catalog()

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def write_json(self, relative, document):
        return self.write(relative, (json.dumps(document) + '\n').encode())

    def sha(self, relative):
        return hashlib.sha256((self.root / relative).read_bytes()).hexdigest()

    def save_catalog(self):
        self.write_json(workspace.MAIN, self.catalog)

    def codes(self, result, severity='errors'):
        return {item['code'] for item in result[severity]}

    @contextmanager
    def opaque_writer(self, relative):
        """Catch probes through either spelling, including pathlib fast paths."""
        active = str(self.root / relative).casefold()

        def guard(path):
            if isinstance(path, int):
                return
            candidate = os.path.abspath(path).casefold()
            self.assertFalse(candidate == active or candidate.startswith(active + os.sep),
                             f'Active writer path was inspected: {path}')

        def protected(original):
            def checked(path, *args, **kwargs):
                guard(path)
                return original(path, *args, **kwargs)
            return checked

        with ExitStack() as stack:
            for name in ('stat', 'lstat', 'exists', 'is_file', 'is_dir', 'is_symlink',
                         'open', 'read_bytes', 'read_text'):
                stack.enter_context(patch.object(Path, name, protected(getattr(Path, name))))
            stack.enter_context(patch.object(workspace.os, 'scandir', protected(os.scandir)))
            yield

    def missing_qa_override(self):
        original = 'output/old/source-glyph-qa.json'
        self.write_json(workspace.RENDER, {'render_review':{'source_glyph_qa':original}})
        return {'source_document':workspace.RENDER, 'source_sha256':self.sha(workspace.RENDER),
                'json_pointer':'/render_review/source_glyph_qa', 'original_path':original,
                'status':'unavailable_historical_evidence', 'replacement_path':None}

    def test_valid_fixture_is_read_only_and_cli_returns_json(self):
        before = {path.relative_to(self.root).as_posix():path.read_bytes()
                  for path in self.root.rglob('*') if path.is_file()}
        result = workspace.verify(self.root)
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['errors'], [])
        after = {path.relative_to(self.root).as_posix():path.read_bytes()
                 for path in self.root.rglob('*') if path.is_file()}
        self.assertEqual(after, before)
        tool = Path(workspace.__file__)
        completed = subprocess.run([sys.executable, '-B', str(tool), '--root', str(self.root)],
                                   capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)['status'], 'pass')

    def test_missing_active_production_id_is_an_error_and_cli_nonzero(self):
        self.catalog['active_production_set_ids'] = ['missing']
        self.save_catalog()
        self.assertIn('missing_active_id', self.codes(workspace.verify(self.root)))
        completed = subprocess.run([sys.executable, '-B', workspace.__file__, '--root', str(self.root)],
                                   capture_output=True, text=True)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout)['status'], 'fail')

    def test_item_and_source_reference_ids_must_resolve(self):
        self.catalog['production_sets']['current']['items'] = ['not-an-item']
        self.catalog['preproduction_sets'] = {'draft':{'source_reference_set_id':'not-a-reference'}}
        self.save_catalog()
        result = workspace.verify(self.root)
        self.assertTrue({'missing_item_id','missing_id'} <= self.codes(result))

    def test_adoption_retention_policy_cannot_discard_dependencies(self):
        self.catalog['storage_policy']['latest_production_only'] = True
        self.save_catalog()
        self.assertIn('retention_policy_mismatch', self.codes(workspace.verify(self.root)))

    def test_unused_old_media_must_not_be_retained_by_default(self):
        self.assertEqual(workspace.verify(self.root)['status'], 'pass')
        self.catalog['storage_policy']['retain_superseded_outputs'] = True
        self.save_catalog()
        self.assertIn('retention_policy_mismatch', self.codes(workspace.verify(self.root)))

    def test_unknown_catalog_schema_cannot_be_silently_accepted(self):
        self.catalog['schema_version'] = 2
        self.save_catalog()
        self.assertIn('unsupported_catalog_schema', self.codes(workspace.verify(self.root)))

    def test_unregistered_library_lfs_pointer_is_an_error(self):
        self.write('assets/library/worlds/example/background.png',
                   workspace.LFS_HEADER + b'oid sha256:' + b'1'*64 + b'\nsize 1234\n')
        result = workspace.verify(self.root)
        self.assertIn('lfs_pointer', self.codes(result))
        self.assertEqual(result['counts']['lfs_pointer_files'], 1)

    def test_declared_source_hash_mismatch_is_an_error(self):
        self.write(self.art, b'changed artwork')
        self.assertIn('sha256_mismatch', self.codes(workspace.verify(self.root)))

    def test_evidence_hash_binds_to_its_sibling_qa_path(self):
        review = 'output/current/alignment-review.json'
        self.write_json(review, {'status':'pass'})
        self.catalog['items']['character'].update(alignment_review=review,
            alignment_review_evidence={'sha256':'0'*64, 'bytes':(self.root/review).stat().st_size})
        self.save_catalog()
        self.assertIn('sha256_mismatch', self.codes(workspace.verify(self.root)))

    def test_template_exemption_cannot_hide_a_broken_adopted_path(self):
        self.catalog['items']['character']['path'] = 'assets/library/<character>/neutral.png'
        self.save_catalog()
        self.assertIn('invalid_reference', self.codes(workspace.verify(self.root)))

    def test_missing_current_file_fails_but_missing_old_production_is_a_note(self):
        self.catalog['production_sets']['old'] = {'items':['character'],
            'output':'output/unpreserved-old/movie.mp4'}
        self.save_catalog()
        result = workspace.verify(self.root)
        self.assertEqual(result['status'], 'pass')
        self.assertIn('historical_file_unavailable', self.codes(result, 'notes'))
        (self.root/'output/current/movie.mp4').unlink()
        self.assertIn('missing_file', self.codes(workspace.verify(self.root)))

    def test_item_id_spelling_cannot_turn_current_missing_art_into_history(self):
        self.catalog['items']['historical_hero'] = self.catalog['items'].pop('character')
        self.catalog['production_sets']['current']['items'] = ['historical_hero']
        self.catalog['reference_sets']['reference']['items'] = ['historical_hero']
        (self.root/self.art).unlink()
        self.save_catalog()
        result = workspace.verify(self.root)
        self.assertEqual(result['status'], 'fail')
        self.assertTrue(any(item['code'] == 'missing_file'
                            and item['location'].endswith('/items/historical_hero/path')
                            for item in result['errors']))

    def test_typed_successor_reference_set_id_must_resolve(self):
        self.catalog['reference_sets']['reference']['superseded_by_reference_set_id'] = 'missing-next-reference'
        self.save_catalog()
        result = workspace.verify(self.root)
        self.assertTrue(any(item['code'] == 'missing_id'
                            and item['location'].endswith('/superseded_by_reference_set_id')
                            for item in result['errors']))

    def test_duplicate_json_keys_are_rejected(self):
        self.write('catalogs/extra.json', b'{"name":1,"name":2}')
        result = workspace.verify(self.root)
        self.assertIn('invalid_json', self.codes(result))
        self.assertTrue(any('Duplicate JSON' in item['message'] for item in result['errors']))

    def test_only_known_historical_cli_capture_accepts_a_json_stream(self):
        stream = b'{"model":"one"}\n{\n "status":"pass"\n}\n'
        legacy = next(iter(workspace.HISTORICAL_JSON_STREAMS))
        self.write(legacy, stream)
        result = workspace.verify(self.root)
        self.assertEqual(result['status'], 'pass')
        self.assertIn('historical_json_stream', self.codes(result, 'notes'))
        self.write('catalogs/not-a-single-json.json', stream)
        self.assertIn('invalid_json', self.codes(workspace.verify(self.root)))

    def test_active_writer_is_opaque_even_with_bad_json_and_reference_links(self):
        relative = 'assets/library/characters/example/generation-batches/live-v001'
        active = self.root / relative
        self.write(relative + '/unfinished.json', b'{not-complete')
        (active/'identity-reference.png').symlink_to(self.root/self.art)
        self.management['reservations'] = [{'id':'live','owner':'another-ai','root':relative,'status':'active'}]
        self.write_json(workspace.MANAGEMENT, self.management)
        self.catalog['items']['pending'] = {'path':relative+'/unfinished.json'}
        self.save_catalog()
        original_stat, original_open, original_walk = Path.stat, Path.open, os.walk
        def guard(path):
            self.assertFalse(Path(path).is_relative_to(active), 'Active writer path was inspected')
        def guarded_stat(path, *args, **kwargs):
            guard(path)
            return original_stat(path, *args, **kwargs)
        def guarded_open(path, *args, **kwargs):
            guard(path)
            return original_open(path, *args, **kwargs)
        def guarded_walk(*args, **kwargs):
            for here, directories, names in original_walk(*args, **kwargs):
                guard(here)
                yield here, directories, names
        with patch.object(Path, 'stat', guarded_stat), patch.object(Path, 'open', guarded_open), \
                patch.object(workspace.os, 'walk', guarded_walk):
            result = workspace.verify(self.root)
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['excluded_active_roots'], [relative])
        self.assertTrue({'active_generation','pending_reference'} <= self.codes(result, 'notes'))

    def test_invalid_writer_config_aborts_before_scanning_sources(self):
        self.write(workspace.MANAGEMENT, b'{unfinished')
        with patch.object(workspace.Auditor, 'scan_managed_files',
                          side_effect=AssertionError('Sources scanned without trusted writer exclusions')):
            result = workspace.verify(self.root)
        self.assertEqual(result['status'], 'fail')
        self.assertIn('invalid_management_config', self.codes(result))

    def test_current_adoption_cannot_pass_with_pending_unverified_art(self):
        relative = 'assets/library/characters/example/generation-batches/live-v001'
        active = self.root / relative
        self.write(relative + '/unfinished.png', b'not-yet-a-finished-image')
        self.management['reservations'] = [{'id':'live','owner':'another-ai','root':relative,'status':'active'}]
        self.write_json(workspace.MANAGEMENT, self.management)
        self.catalog['items']['character']['path'] = relative + '/unfinished.png'
        self.save_catalog()
        original_stat, original_open = Path.stat, Path.open
        def guard(path):
            self.assertFalse(Path(path).is_relative_to(active), 'Pending art was inspected')
        def guarded_stat(path, *args, **kwargs):
            guard(path)
            return original_stat(path, *args, **kwargs)
        def guarded_open(path, *args, **kwargs):
            guard(path)
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'stat', guarded_stat), patch.object(Path, 'open', guarded_open):
            result = workspace.verify(self.root)
        self.assertEqual(result['status'], 'fail')
        self.assertIn('pending_required_input', self.codes(result))

    def test_case_alias_optional_reference_and_walk_never_probe_the_writer(self):
        parent = 'assets/library/characters/example/generation-batches/'
        for reserved, actual in [('live-v001', 'LIVE-V001'), ('LIVE-V001', 'live-v001')]:
            with self.subTest(reserved=reserved, actual=actual):
                reservation = parent + reserved
                relative = parent + actual
                self.write(relative + '/unfinished.json', b'{not-complete')
                self.management['reservations'] = [
                    {'id':'live', 'owner':'another-ai', 'root':reservation, 'status':'active'}]
                self.write_json(workspace.MANAGEMENT, self.management)
                self.catalog['items']['pending'] = {
                    'path':relative + '/unfinished.json', 'sha256':'0' * 64}
                self.save_catalog()
                with self.opaque_writer(reservation):
                    result = workspace.verify(self.root)
                self.assertEqual(result['status'], 'pass', result['errors'])
                self.assertTrue({'active_generation', 'pending_reference'} <= self.codes(result, 'notes'))
                self.assertEqual(result['excluded_active_roots'], [reservation])

    def test_case_alias_required_sha_reference_errors_without_probing_the_writer(self):
        parent = 'assets/library/characters/example/generation-batches/'
        for reserved, actual in [('live-v001', 'LIVE-V001'), ('LIVE-V001', 'live-v001')]:
            with self.subTest(reserved=reserved, actual=actual):
                reservation = parent + reserved
                relative = parent + actual
                self.write(relative + '/unfinished.png', workspace.LFS_HEADER + b'unfinished pointer')
                self.management['reservations'] = [
                    {'id':'live', 'owner':'another-ai', 'root':reservation, 'status':'active'}]
                self.write_json(workspace.MANAGEMENT, self.management)
                self.catalog['items']['character']['path'] = relative + '/unfinished.png'
                self.save_catalog()
                with self.opaque_writer(reservation):
                    result = workspace.verify(self.root)
                self.assertEqual(result['status'], 'fail')
                self.assertEqual(self.codes(result), {'pending_required_input'})

    def test_case_alias_json_and_hash_helpers_refuse_pending_sources_before_probes(self):
        reservation = 'assets/library/characters/example/generation-batches/live-v001'
        relative = reservation.replace('/live-v001', '/LIVE-V001') + '/unfinished.json'
        self.write(relative, b'{not-complete')
        auditor = workspace.Auditor(self.root)
        auditor.active = [{'root':reservation}]
        aliases = [relative, relative.replace('library/', 'library//'),
                   relative.replace('/characters/', '/./characters/'),
                   relative.replace('/generation-batches/', '/generation-batches//./')]
        for alias in aliases:
            with self.subTest(alias=alias), self.opaque_writer(reservation):
                self.assertIsNone(auditor.read_json(alias))
                with self.assertRaisesRegex(ValueError, 'Active generation input is pending'):
                    auditor.safe_path(alias)
                with self.assertRaisesRegex(ValueError, 'Active generation input is pending'):
                    auditor.digest(alias, self.root / alias)
                self.assertFalse(auditor.check_pointer(alias, self.root / alias))

    def test_direct_helpers_reject_parent_traversal_before_any_source_probe(self):
        relative = 'assets/library/characters/example/generation-batches/live-v001'
        auditor = workspace.Auditor(self.root)
        auditor.active = [{'root':relative}]
        invalid = relative + '/../live-v001/unfinished.json'
        with self.opaque_writer(relative):
            for helper in (auditor.pending, auditor.safe_path, auditor.read_json):
                with self.subTest(helper=helper.__name__), self.assertRaisesRegex(ValueError, 'project-relative path'):
                    helper(invalid)
            for helper in (auditor.digest, auditor.check_pointer):
                with self.subTest(helper=helper.__name__), self.assertRaisesRegex(ValueError, 'project-relative path'):
                    helper(invalid, self.root / invalid)

    def test_case_alias_pending_match_keeps_similarly_named_sibling_visible(self):
        relative = 'assets/library/characters/example/generation-batches/live-v001'
        sibling = relative.replace('/live-v001', '/LIVE-V001-previous') + '/bad.json'
        self.write(sibling, b'{invalid sibling must still be checked')
        self.management['reservations'] = [
            {'id':'live', 'owner':'another-ai', 'root':relative, 'status':'active'}]
        self.write_json(workspace.MANAGEMENT, self.management)
        with self.opaque_writer(relative):
            result = workspace.verify(self.root)
        self.assertTrue(any(row['code'] == 'invalid_json' and row['path'] == sibling
                            for row in result['errors']))

    def test_reservation_cannot_begin_midway_through_source_walk(self):
        original = workspace.Auditor.scan_managed_files
        attempted = []
        def concurrent(auditor):
            with self.assertRaisesRegex(ValueError, 'writer lock exists'):
                management.reserve(self.root, self.root/workspace.MANAGEMENT,
                    'assets/library/characters/example/generation-batches/next', 'another-ai', 'new-job')
            attempted.append(True)
            return original(auditor)
        with patch.object(workspace.Auditor, 'scan_managed_files', concurrent):
            result = workspace.verify(self.root)
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(attempted, [True])
        management.reserve(self.root, self.root/workspace.MANAGEMENT,
            'assets/library/characters/example/generation-batches/next', 'another-ai', 'after-check')

    def test_catalog_change_during_check_cannot_report_success(self):
        original = workspace.Auditor.scan_managed_files
        def concurrent(auditor):
            original(auditor)
            self.catalog['concurrent_note'] = 'another manager updated the catalog'
            self.save_catalog()
        with patch.object(workspace.Auditor, 'scan_managed_files', concurrent):
            result = workspace.verify(self.root)
        self.assertEqual(result['status'], 'fail')
        self.assertIn('concurrent_metadata_change', self.codes(result))

    def test_frozen_override_source_change_after_scan_cannot_report_success(self):
        row = self.missing_qa_override()
        self.catalog['metadata_availability_overrides'] = [row]
        self.save_catalog()
        original = workspace.Auditor.scan_managed_files
        def concurrent(auditor):
            original(auditor)
            self.write_json(workspace.RENDER, {'render_review':{'source_glyph_qa':row['original_path']},
                                              'uncoordinated_change':True})
        with patch.object(workspace.Auditor, 'scan_managed_files', concurrent):
            result = workspace.verify(self.root)
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(result['control_file_sha256'][workspace.RENDER], row['source_sha256'])
        self.assertTrue(any(item['code'] == 'concurrent_metadata_change'
                            and item['path'] == workspace.RENDER for item in result['errors']))

    def test_exact_unavailable_evidence_override_is_a_note(self):
        self.catalog['metadata_availability_overrides'] = [self.missing_qa_override()]
        self.save_catalog()
        result = workspace.verify(self.root)
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['counts']['unavailable_evidence_overrides'], 1)
        self.assertIn('declared_unavailable_evidence', self.codes(result, 'notes'))

    def test_unavailable_override_must_match_hash_pointer_path_and_scope(self):
        original = self.missing_qa_override()
        faults = {'source_sha256':'0'*64, 'json_pointer':'/render_review/missing_qa',
                  'original_path':'output/other/missing.json', 'replacement_path':'output/current/timeline.json',
                  'source_document':workspace.MAIN, 'status':'accepted'}
        for field, bad in faults.items():
            with self.subTest(field=field):
                self.catalog['metadata_availability_overrides'] = [{**original, field:bad}]
                self.save_catalog()
                self.assertIn('invalid_availability_override', self.codes(workspace.verify(self.root)))

    def test_unavailable_override_cannot_hide_primary_sources(self):
        missing = 'assets/library/characters/missing/source.png'
        self.write_json(workspace.RENDER, {'images':{'primary':{'path':missing}}})
        self.catalog['metadata_availability_overrides'] = [{
            'source_document':workspace.RENDER, 'source_sha256':self.sha(workspace.RENDER),
            'json_pointer':'/images/primary/path', 'original_path':missing,
            'status':'unavailable_historical_evidence', 'replacement_path':None}]
        self.save_catalog()
        result = workspace.verify(self.root)
        self.assertIn('invalid_availability_override', self.codes(result))
        self.assertIn('missing_file', self.codes(result))


if __name__ == '__main__':
    unittest.main()
