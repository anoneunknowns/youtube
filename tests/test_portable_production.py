"""Compatibility and no-overwrite checks for the portable adapter."""
import argparse
from contextlib import chdir
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


portable = load('portable_production')
library = load('portable_speech_library')


class PortableCompatibility(unittest.TestCase):
    def test_legacy_references_use_checkout_even_when_legacy_drive_exists(self):
        with tempfile.TemporaryDirectory() as folder:
            expected = Path(folder) / 'assets/speech.json'
            actual = library.resolve_reference('D:\\codex_projects\\youtube\\assets\\speech.json', root=folder)
            self.assertEqual(actual, expected.resolve())

    def test_legacy_reference_cannot_escape_checkout(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                library.resolve_reference('D:/codex_projects/youtube/../../secret.txt', root=folder)

    def test_relative_reference_cannot_escape_checkout(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'escapes this checkout'):
                library.resolve_reference('assets/../../../outside-proof.json', root=folder)
            self.assertEqual(library.resolve_reference('assets/proof.json', root=folder),
                             (Path(folder) / 'assets/proof.json').resolve())

    def test_existing_output_is_never_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            sentinel = Path(folder) / 'user-file.txt'
            sentinel.write_text('preserve me', encoding='utf-8')
            with self.assertRaises(FileExistsError):
                portable.new_directory(folder)
            self.assertEqual(sentinel.read_text(), 'preserve me')

    def test_explicit_work_root_does_not_need_d_drive(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'work with spaces'
            self.assertEqual(portable.work_directory(path), path.resolve())
            self.assertTrue(path.is_dir())

    @unittest.skipIf(os.name == 'nt', 'POSIX path interpretation')
    def test_relative_d_drive_directory_does_not_override_posix_system_temp(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            decoy = root / 'D:/temp'
            decoy.mkdir(parents=True)
            system_temp = root / 'system-temp'
            with chdir(root), patch.dict(os.environ, {'YOUTUBE_WORK_DIR': ''}), \
                    patch.object(portable.tempfile, 'gettempdir', return_value=str(system_temp)):
                actual = portable.work_directory()
            self.assertEqual(actual.resolve(), (system_temp / 'youtube-production').resolve())
            self.assertNotEqual(actual.resolve(), decoy.resolve())

    def test_lfs_pointer_is_rejected_before_rendering(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'art.png'
            path.write_text('version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 1234\n')
            with self.assertRaisesRegex(ValueError, 'Git LFS pointer'):
                portable.require_file(path)

    def test_staged_recipe_delivery_gains_match_adopted_render_records(self):
        expected = {'octal': .8, 'hexadecimal': 0, 'four-base': .8}
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            timeline = work / 'timeline.json'
            audio = work / 'master.wav'
            timeline.write_text('{}')
            audio.write_bytes(b'preserved-input')
            calls = []
            def encode(index, source, output, count, ffmpeg, crf, preset, gain):
                calls.append((source, gain, count))
                output.write_bytes(b'test-encoded-artifact')
            shared = SimpleNamespace(stage_frames=lambda scene, directory: (directory / 'index', 1, 1), encode=encode)
            for kind, gain in expected.items():
                _, _, recipe = portable.production(kind)
                args = argparse.Namespace(command='render', production=kind, timeline=str(timeline), audio=str(audio),
                                          motion_manifest=None, out_dir=str(work / kind), work_dir=str(work),
                                          ffmpeg='ffmpeg', crf=18, preset='veryfast')
                scene = SimpleNamespace(duration=500, frame_count=15000)
                with patch.object(portable, 'check_inputs', return_value=({}, None, scene, 0)), \
                     patch.object(portable, 'module', return_value=shared), \
                     patch.object(portable, 'executable', return_value='ffmpeg'):
                    result = portable.render_or_preview(args)
                self.assertEqual(calls[-1], (audio, gain, 15000))
                self.assertEqual(result['audio_mux_gain_db'], gain)
                if kind != 'four-base':
                    record = portable.read(ROOT / recipe['production_record'])
                    options = record['render_options']
                    self.assertEqual(float(options[options.index('--audio-gain-db') + 1]), gain)
            self.assertEqual(audio.read_bytes(), b'preserved-input')

    def test_octal_adapter_uses_common_baseline(self):
        fake = SimpleNamespace(Scene=lambda plan, layout: (plan, layout))
        with patch.object(portable, 'module', return_value=fake):
            _, scene = portable.make_scene('octal', {}, {'id': 1}, None)
        self.assertEqual(scene, ({'id': 1}, 'common-baseline'))

    def test_even_adapter_passes_measured_scene_contract_without_base_adaptation(self):
        plan = {'scenes': [{'scene': 'count', 'decimal_value': 200}], 'duration_s': 369.339125}
        fake = SimpleNamespace(Scene=lambda actual: actual)
        with patch.object(portable, 'module', return_value=fake) as imported:
            _, scene = portable.make_scene('even', {}, plan, None)
        imported.assert_called_once_with('render_even_video')
        self.assertIs(scene, plan)

    def test_new_even_alias_is_available_only_after_catalog_adoption(self):
        old_id = portable.ALIASES['four-base']
        even_id = portable.ALIASES['even']
        catalog = {'active_production_set_ids': [old_id], 'production_sets': {}}
        with patch.object(portable, 'read', return_value=catalog):
            self.assertEqual(portable.adopted_aliases(), {'four-base': old_id})
            with self.assertRaisesRegex(ValueError, 'adopted production'):
                portable.production('even')
            catalog['active_production_set_ids'].append(even_id)
            catalog['production_sets'][even_id] = {'duration_s': 369.339125}
            self.assertEqual(portable.production('even'),
                             (even_id, 'even', catalog['production_sets'][even_id]))
            self.assertEqual(portable.adopted_aliases()['even'], even_id)

    def test_even_revision_selects_its_versioned_renderer(self):
        plan = {'renderer_implementation': 'tools/render_even_video_v002.py'}
        fake = SimpleNamespace(Scene=lambda actual: actual)
        with patch.object(portable, 'module', return_value=fake) as imported:
            _, scene = portable.make_scene('even', {}, plan, None)
        imported.assert_called_once_with('render_even_video_v002')
        self.assertIs(scene, plan)

    def test_even_renderer_does_not_dispatch_arbitrary_modules(self):
        with self.assertRaisesRegex(ValueError, 'Unknown adopted even-number renderer'):
            portable.make_scene('even', {}, {'renderer_implementation': 'tools/unrelated.py'}, None)

    def test_odd_adapter_passes_measured_scene_contract_without_base_adaptation(self):
        plan = {'renderer_implementation': 'tools/render_odd_video.py',
                'scenes': [{'scene': 'count', 'decimal_value': 199}], 'duration_s': 372.4}
        fake = SimpleNamespace(Scene=lambda actual: actual)
        with patch.object(portable, 'module', return_value=fake) as imported:
            _, scene = portable.make_scene('odd', {}, plan, None)
        imported.assert_called_once_with('render_odd_video')
        self.assertIs(scene, plan)
        with self.assertRaisesRegex(ValueError, 'Unknown adopted odd-number renderer'):
            portable.make_scene('odd', {}, {'renderer_implementation': 'tools/unrelated.py'}, None)

    def test_odd_alias_is_available_only_after_catalog_adoption(self):
        even_id, odd_id = portable.ALIASES['even'], portable.ALIASES['odd']
        catalog = {'active_production_set_ids': [even_id], 'production_sets': {}}
        with patch.object(portable, 'read', return_value=catalog):
            self.assertEqual(portable.adopted_aliases(), {'even': even_id})
            with self.assertRaisesRegex(ValueError, 'adopted production'):
                portable.production('odd')
            catalog['active_production_set_ids'].append(odd_id)
            catalog['production_sets'][odd_id] = {'duration_s': 372.4}
            self.assertEqual(portable.production('odd'),
                             (odd_id, 'odd', catalog['production_sets'][odd_id]))
            self.assertEqual(portable.adopted_aliases()['odd'], odd_id)

    def test_odd_input_checks_bind_voice_events_to_their_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            checkout = Path(folder)
            record, timeline = checkout / 'record.json', checkout / 'timeline.json'
            master, speech = checkout / 'master.wav', checkout / 'N001.wav'
            record.write_text('{"files": []}')
            master.write_bytes(b'master')
            speech.write_bytes(b'changed-source')
            timeline.write_text(json.dumps({'voice_events': [
                {'source_path': 'N001.wav', 'source_sha256': hashlib.sha256(b'accepted-source').hexdigest()}]}))
            with patch.object(portable, 'ROOT', checkout), patch.object(portable, 'make_scene') as create_scene:
                with self.assertRaisesRegex(ValueError, 'checksum differs'):
                    portable.check_inputs('odd', {'production_record': 'record.json'}, timeline, master, None, custom=True)
            create_scene.assert_not_called()

    def test_even_render_uses_timeline_delivery_gain(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            timeline, audio = work / 'timeline.json', work / 'master.wav'
            timeline.write_text('{}')
            audio.write_bytes(b'preserved-master')
            calls = []
            def encode(index, source, output, count, ffmpeg, crf, preset, gain):
                calls.append((source, gain, count))
                output.write_bytes(b'even-encoded-artifact')
            shared = SimpleNamespace(stage_frames=lambda scene, directory: (directory / 'index', 1, 1), encode=encode)
            row = {'output': 'output/even-counting-001-v001/even.mp4',
                   'render_implementation': 'tools/render_even_video.py'}
            args = argparse.Namespace(command='render', production='even', timeline=str(timeline), audio=str(audio),
                                      motion_manifest=None, out_dir=str(work / 'render'), work_dir=str(work),
                                      ffmpeg='ffmpeg', crf=18, preset='veryfast')
            scene = SimpleNamespace(duration=369.339125, frame_count=11081)
            with patch.object(portable, 'production', return_value=(portable.ALIASES['even'], 'even', row)), \
                 patch.object(portable, 'check_inputs', return_value=({'delivery_gain_db': .65}, None, scene, 0)), \
                 patch.object(portable, 'module', return_value=shared), \
                 patch.object(portable, 'executable', return_value='ffmpeg'):
                result = portable.render_or_preview(args)
            self.assertEqual(calls, [(audio, .65, 11081)])
            self.assertEqual(result['audio_mux_gain_db'], .65)
            self.assertEqual(audio.read_bytes(), b'preserved-master')

    def test_even_verification_calls_complete_verifier_once_with_master(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            timeline, audio, video = work / 'timeline.json', work / 'master.wav', work / 'even.mp4'
            timeline.write_text('{"duration_s": 369.339125}')
            audio.write_bytes(b'master')
            video.write_bytes(b'video')
            destination = work / 'qa'
            row = {'output': 'output/even-counting-001-v001/even.mp4'}
            args = argparse.Namespace(production='even', timeline=str(timeline), audio=str(audio),
                                      motion_manifest=None, video=str(video), out_dir=str(destination),
                                      delivery_dir=work, work_dir=str(work), ffmpeg='ffmpeg', ffprobe='ffprobe')
            def run(command, **kwargs):
                self.assertIn('verify_even_video.py', ' '.join(command))
                self.assertEqual(command[command.index('--master') + 1], str(audio))
                self.assertEqual(command[command.index('--delivery-dir') + 1], str(work))
                (destination / 'even-final-qa.json').write_text('{"status": "pass", "checks": {}}')
            with patch.object(portable, 'production', return_value=(portable.ALIASES['even'], 'even', row)), \
                 patch.object(portable, 'module') as imported, \
                 patch.object(portable.subprocess, 'run', side_effect=run) as launched, \
                 patch.object(portable, 'executable', side_effect=lambda name, explicit: name):
                result = portable.verify(args)
            launched.assert_called_once()
            imported.assert_not_called()  # Avoid a duplicate generic technical run and its old duration gate.
            self.assertEqual(result['status'], 'pass')
            self.assertTrue((destination / 'portable-verification.json').is_file())

    def test_odd_render_uses_timeline_delivery_gain(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            timeline, audio = work / 'timeline.json', work / 'master.wav'
            timeline.write_text('{}')
            audio.write_bytes(b'preserved-master')
            calls = []
            def encode(index, source, output, count, ffmpeg, crf, preset, gain):
                calls.append((source, gain, count))
                output.write_bytes(b'odd-encoded-artifact')
            shared = SimpleNamespace(stage_frames=lambda scene, directory: (directory / 'index', 1, 1), encode=encode)
            row = {'output': 'output/odd-counting-001-v001/odd.mp4',
                   'render_implementation': 'tools/render_odd_video.py'}
            args = argparse.Namespace(command='render', production='odd', timeline=str(timeline), audio=str(audio),
                                      motion_manifest=None, out_dir=str(work / 'render'), work_dir=str(work),
                                      ffmpeg='ffmpeg', crf=18, preset='veryfast')
            scene = SimpleNamespace(duration=372.4, frame_count=11172)
            with patch.object(portable, 'production', return_value=(portable.ALIASES['odd'], 'odd', row)), \
                 patch.object(portable, 'check_inputs', return_value=({'delivery_gain_db': .45}, None, scene, 0)), \
                 patch.object(portable, 'module', return_value=shared), \
                 patch.object(portable, 'executable', return_value='ffmpeg'):
                result = portable.render_or_preview(args)
            self.assertEqual(calls, [(audio, .45, 11172)])
            self.assertEqual(result['audio_mux_gain_db'], .45)
            self.assertEqual(audio.read_bytes(), b'preserved-master')

    def test_odd_verification_calls_complete_verifier_once_with_master(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            timeline, audio, video = work / 'timeline.json', work / 'master.wav', work / 'odd.mp4'
            timeline.write_text(json.dumps({'duration_s': 540, 'count_start': 1, 'count_end': 299,
                                            'count_step': 2, 'voice_events': [{}] * 163,
                                            'verifier_implementation': 'tools/verify_odd_video.py'}))
            audio.write_bytes(b'master')
            video.write_bytes(b'video')
            destination = work / 'qa'
            row = {'output': 'output/odd-counting-001-v001/odd.mp4'}
            args = argparse.Namespace(production='odd', timeline=str(timeline), audio=str(audio),
                                      motion_manifest=None, video=str(video), out_dir=str(destination),
                                      delivery_dir=work, work_dir=str(work), ffmpeg='ffmpeg', ffprobe='ffprobe')
            def run(command, **kwargs):
                self.assertIn('verify_odd_video.py', ' '.join(command))
                self.assertEqual(command[command.index('--master') + 1], str(audio))
                self.assertEqual(command[command.index('--delivery-dir') + 1], str(work))
                self.assertEqual(command[command.index('--work-dir') + 1], str(work.resolve()))
                (destination / 'odd-final-qa.json').write_text('{"status": "pass", "checks": {}}')
            with patch.object(portable, 'production', return_value=(portable.ALIASES['odd'], 'odd', row)), \
                 patch.object(portable, 'module') as imported, \
                 patch.object(portable.subprocess, 'run', side_effect=run) as launched, \
                 patch.object(portable, 'executable', side_effect=lambda name, explicit: name):
                result = portable.verify(args)
            launched.assert_called_once()
            imported.assert_not_called()
            self.assertEqual(result['evidence'], 'odd-final-qa.json')
            self.assertIn('all 150 odd values', result['checks_performed'][1])
            self.assertIn('all 163 voices', result['checks_performed'][2])
            self.assertTrue((destination / 'portable-verification.json').is_file())

    def test_historical_record_list_and_dict_checksums_are_both_supported(self):
        checksum = 'a' * 64
        expected = {'output/example/master.wav': checksum}
        self.assertEqual(portable.record_hashes([{'path': 'output/example/master.wav', 'sha256': checksum}]), expected)
        self.assertEqual(portable.record_hashes(expected), expected)

    def test_adopted_master_change_is_rejected_without_running_doctor(self):
        with tempfile.TemporaryDirectory() as folder:
            checkout = Path(folder)
            (checkout / 'reproducibility').mkdir()
            record = checkout / 'record.json'
            record.write_text('{"files": []}')
            source = checkout / 'output/example'
            source.mkdir(parents=True)
            timeline, master = source / 'timeline.json', source / 'master.wav'
            timeline.write_text('{}')
            original = b'adopted master content'
            master.write_bytes(original)
            archived = [{'path': p.relative_to(checkout).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                        for p in [timeline, master]]
            (checkout / 'reproducibility/production-inputs.json').write_text(json.dumps({'files': archived}))
            master.write_bytes(b'X' + original[1:])  # Same byte count; duration alone cannot catch this.
            with patch.object(portable, 'ROOT', checkout):
                with self.assertRaisesRegex(ValueError, 'checksum differs'):
                    portable.check_inputs('decimal', {'production_record': 'record.json'}, timeline, master, None)


if __name__ == '__main__':
    unittest.main()
