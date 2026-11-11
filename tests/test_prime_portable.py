"""Portable prime reproduction preserves the already mastered speech level."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from tools import portable_production as portable


class PrimePortableTests(unittest.TestCase):
    def test_prime_adapter_uses_measured_scene(self):
        plan = {'duration_s': 685.95}
        fake = SimpleNamespace(Scene=lambda actual: actual)
        with patch.object(portable, 'module', return_value=fake) as imported:
            renderer, scene = portable.make_scene('prime', {}, plan, None)
        imported.assert_called_once_with('render_prime_video')
        self.assertIs(scene, plan)

    def test_animated_prime_selects_only_supported_renderer(self):
        for version in ('v002', 'v003'):
            with self.subTest(version=version):
                plan = {'renderer_implementation': f'tools/render_prime_video_{version}.py'}
                fake = SimpleNamespace(Scene=lambda actual: actual)
                with patch.object(portable, 'module', return_value=fake) as imported:
                    _, scene = portable.make_scene('prime', {}, plan, None)
                imported.assert_called_once_with(f'render_prime_video_{version}')
                self.assertIs(scene, plan)
        with patch.object(portable, 'module') as imported:
            with self.assertRaisesRegex(ValueError, 'Unknown adopted prime-number renderer'):
                portable.make_scene('prime', {}, {'renderer_implementation': 'unexpected.py'}, None)
        imported.assert_not_called()

    def copied_audio_fixture(self, folder):
        master = folder / 'master.wav'
        master.write_bytes(b'accepted PCM master fixture')
        movie = folder / 'source.mp4'
        movie.write_bytes(b'accepted AAC movie fixture')
        original = {'events': [{'id': 'N002', 'start_s': 1, 'end_s': 2}],
                    'voice_events': [{'id': 'N002', 'start_s': 1, 'end_s': 2}],
                    'duration_s': 3, 'timing': {'normal_gap_s': 2},
                    'master_audio': {'path': str(master), 'sha256': portable.sha256(master)}}
        source_timeline = folder / 'original-timeline.json'
        source_timeline.write_text(json.dumps(original))
        plan = deepcopy(original)
        plan.update(renderer_implementation='tools/render_prime_video_v002.py',
                    source_timeline={'path': str(source_timeline), 'sha256': portable.sha256(source_timeline)},
                    reused_final_aac={'path': str(movie), 'sha256': portable.sha256(movie)})
        return plan, master, movie

    def test_copied_aac_rejects_changed_pcm_and_speech_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            plan, master, movie = self.copied_audio_fixture(Path(directory))
            self.assertEqual(portable.prime_aac_source(plan, master), movie)
            changed = deepcopy(plan)
            changed['events'][0]['start_s'] = 1.1
            with self.assertRaisesRegex(ValueError, 'unchanged accepted speech: events'):
                portable.prime_aac_source(changed, master)
            master.write_bytes(b'unaccepted replacement PCM')
            with self.assertRaisesRegex(ValueError, 'Input checksum differs'):
                portable.prime_aac_source(plan, master)

    def test_animated_render_passes_verified_aac_movie_instead_of_wav(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            plan, master, movie = self.copied_audio_fixture(folder)
            timeline = folder / 'timeline.json'
            timeline.write_text(json.dumps(plan))
            calls = []
            def encode(index, source, output, frames, ffmpeg, preset, crf):
                calls.append(source)
                output.write_bytes(b'new picture with copied AAC')
            renderer = SimpleNamespace(stage=lambda scene, path: (path/'frames.ffconcat', [1], [1]),
                                       encode=encode, aac_hash=lambda source, ffmpeg: 'same AAC payload')
            row = {'output': 'output/prime-counting-001-v002/test.mp4',
                   'render_implementation': 'tools/render_prime_video_v002.py'}
            args = argparse.Namespace(command='render', production='prime', timeline=str(timeline),
                                      audio=str(master), motion_manifest=None, out_dir=str(folder/'delivery'),
                                      work_dir=str(folder), ffmpeg='ffmpeg', crf=18, preset='veryfast')
            with patch.object(portable, 'production', return_value=('prime-test', 'prime', row)), \
                 patch.object(portable, 'check_inputs', return_value=(plan, renderer, SimpleNamespace(frame_count=90), 188)), \
                 patch.object(portable, 'executable', return_value='ffmpeg'):
                result = portable.render_or_preview(args)
            self.assertEqual(calls, [movie])
            self.assertTrue(result['audio_codec_copy'])
            self.assertTrue(result['encoded_audio_bitstream_identical'])
            self.assertEqual(result['original_audio_adts_sha256'], result['output_audio_adts_sha256'])

    def test_prime_preview_returns_image_without_alignment_receipt(self):
        image = object()
        scene = SimpleNamespace(duration=10, frame_count=300,
                                state=lambda index: index,
                                image=lambda state: (image, {'frame': state}))
        self.assertIs(portable.scene_image('prime', scene, .1), image)
        with self.assertRaises(ValueError):
            portable.scene_image('prime', scene, 10)

    def test_reproduction_does_not_apply_master_gain_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            timeline = folder / 'timeline.json'
            timeline.write_text('{}')
            audio = folder / 'master.wav'
            audio.write_bytes(b'preserved accepted master')
            calls = []
            def encode(index, source, output, frames, ffmpeg, preset, crf):
                calls.append((source, frames, preset, crf))
                output.write_bytes(b'encoded fixture')
            renderer = SimpleNamespace(stage=lambda scene, path: (path / 'frames.ffconcat', [1], [1]),
                                       encode=encode)
            row = {'output': 'output/prime-counting-001-v001/test.mp4',
                   'render_implementation': 'tools/render_prime_video.py'}
            args = argparse.Namespace(command='render', production='prime', timeline=str(timeline),
                                      audio=str(audio), motion_manifest=None, out_dir=str(folder/'delivery'),
                                      work_dir=str(folder), ffmpeg='ffmpeg', crf=18, preset='veryfast')
            scene = SimpleNamespace(duration=1, frame_count=30)
            with patch.object(portable, 'production', return_value=('prime-test', 'prime', row)), \
                 patch.object(portable, 'check_inputs', return_value=({}, renderer, scene, 188)), \
                 patch.object(portable, 'executable', return_value='ffmpeg'):
                result = portable.render_or_preview(args)
            self.assertEqual(calls, [(audio, 30, 'veryfast', 18)])
            self.assertEqual(result['audio_mux_gain_db'], 0)
            self.assertEqual(audio.read_bytes(), b'preserved accepted master')


if __name__ == '__main__':
    unittest.main()
