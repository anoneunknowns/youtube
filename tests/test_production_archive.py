"""Verify archive closure, relocation, corruption guards and Git ignore behavior."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

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
