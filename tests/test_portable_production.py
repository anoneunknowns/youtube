"""Compatibility and no-overwrite checks for the portable adapter."""
import argparse
import hashlib
import importlib.util
import json
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
