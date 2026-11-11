"""Fibonacci reproduction must preserve the accepted master without double gain."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from tools import portable_production as portable


class FibonacciPortableTests(unittest.TestCase):
    def test_fibonacci_uses_its_own_measured_renderer(self):
        plan = {'duration_s': 600}
        fake = SimpleNamespace(Scene=lambda actual: actual)
        with patch.object(portable, 'module', return_value=fake) as imported:
            _, scene = portable.make_scene('fibonacci', {}, plan, None)
        imported.assert_called_once_with('render_fibonacci_video')
        self.assertIs(scene, plan)

    def test_preview_uses_exact_requested_frame(self):
        image = object()
        scene = SimpleNamespace(duration=10, frame_count=300, state=lambda index: index,
                                image=lambda state: (image, {'frame': state}))
        self.assertIs(portable.scene_image('fibonacci', scene, .12), image)
        with self.assertRaises(ValueError):
            portable.scene_image('fibonacci', scene, 10)

    def test_fibonacci_revision_uses_its_measured_motion_renderer(self):
        for name in ('render_fibonacci_video_v002', 'render_fibonacci_video_v003'):
            with self.subTest(renderer=name):
                plan = {'duration_s': 600, 'renderer_implementation': f'tools/{name}.py'}
                fake = SimpleNamespace(Scene=lambda actual: actual)
                with patch.object(portable, 'module', return_value=fake) as imported:
                    _, scene = portable.make_scene('fibonacci', {}, plan, None)
                imported.assert_called_once_with(name)
                self.assertIs(scene, plan)

    def test_unknown_fibonacci_renderer_is_rejected(self):
        with patch.object(portable, 'module') as imported:
            with self.assertRaisesRegex(ValueError, 'Unknown adopted Fibonacci'):
                portable.make_scene('fibonacci', {}, {'renderer_implementation': 'unexpected.py'}, None)
        imported.assert_not_called()

    def test_actor_revision_cannot_change_measured_voice_or_base(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            base = {name: [] for name in ('events', 'voice_events', 'counted_states', 'visual_segments', 'scenes')}
            base.update(duration_s=1, duration_frames=30, master_audio={'sha256': 'accepted'}, timing={})
            base_path = folder / 'base.json'
            base_path.write_text(json.dumps(base))
            source = {'path': str(base_path), 'sha256': portable.sha256(base_path)}
            motion_path = folder / 'character-motion.json'
            motion_path.write_text(json.dumps({'source_timeline': source}))
            plan = dict(base, source_timeline=source,
                        character_motion={'path': str(motion_path), 'sha256': portable.sha256(motion_path)})
            self.assertEqual(portable.fibonacci_motion_source(plan), motion_path)
            changed = dict(plan, voice_events=[{'id': 'N024', 'start_s': .1}])
            with self.assertRaisesRegex(ValueError, 'voice_events'):
                portable.fibonacci_motion_source(changed)
            motion_path.write_text(json.dumps({'source_timeline': dict(source, sha256='wrong')}))
            plan['character_motion']['sha256'] = portable.sha256(motion_path)
            with self.assertRaisesRegex(ValueError, 'different measured base'):
                portable.fibonacci_motion_source(plan)

    def test_encoded_audio_cannot_cross_master_or_base(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            master, aac, gate_path = (folder / name for name in ('master.wav', 'accepted.m4a', 'gate.json'))
            master.write_bytes(b'accepted master')
            aac.write_bytes(b'accepted AAC')
            base = {'path': 'base.json', 'sha256': 'base-hash'}
            gate = {'passed': True, 'source_timeline': base,
                    'master': {'path': str(master), 'sha256': portable.sha256(master)},
                    'encoded_aac': {'path': str(aac), 'sha256': portable.sha256(aac)}}
            gate_path.write_text(json.dumps(gate))
            plan = {'master_audio': gate['master'], 'source_timeline': base,
                    'encoded_audio_acceptance': {'path': str(gate_path), 'sha256': portable.sha256(gate_path)}}
            self.assertEqual(portable.fibonacci_aac_source(plan, master), aac)
            plan['source_timeline'] = dict(base, sha256='other-base')
            with self.assertRaisesRegex(ValueError, 'different master or measured base'):
                portable.fibonacci_aac_source(plan, master)
            plan['source_timeline'] = base
            master.write_bytes(b'changed master')
            with self.assertRaisesRegex(ValueError, 'checksum differs'):
                portable.fibonacci_aac_source(plan, master)

    def test_accepted_master_is_not_amplified_again(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            timeline = folder/'timeline.json'
            timeline.write_text('{}')
            audio = folder/'master.wav'
            audio.write_bytes(b'accepted48k24bitstereo')
            calls = []

            def encode(index, source, output, frames, ffmpeg, preset, crf):
                calls.append((source, frames))
                output.write_bytes(b'encoded-test-fixture')

            renderer = SimpleNamespace(stage=lambda scene, destination: (destination/'frames.ffconcat', [1], [1]),
                                       encode=encode)
            args = argparse.Namespace(command='render', production='fibonacci', timeline=str(timeline),
                                      audio=str(audio), motion_manifest=None, out_dir=str(folder/'delivery'),
                                      work_dir=str(folder), ffmpeg='ffmpeg', crf=18, preset='veryfast')
            row = {'output': 'output/fibonacci-counting-001-v001/fibonacci.mp4',
                   'render_implementation': 'tools/render_fibonacci_video.py'}
            scene = SimpleNamespace(duration=1, frame_count=30)
            with patch.object(portable, 'production', return_value=('fibonacci-test', 'fibonacci', row)), \
                 patch.object(portable, 'check_inputs', return_value=({}, renderer, scene, 104)), \
                 patch.object(portable, 'executable', return_value='ffmpeg'):
                receipt = portable.render_or_preview(args)
            self.assertEqual(calls, [(audio, 30)])
            self.assertEqual(receipt['audio_mux_gain_db'], 0)
            self.assertEqual(audio.read_bytes(), b'accepted48k24bitstereo')

    def test_revision_verification_requires_motion_pass(self):
        for revision, motion_pass in [('render_fibonacci_video', True),
                                      ('render_fibonacci_video_v002', True),
                                      ('render_fibonacci_video_v002', False),
                                      ('render_fibonacci_video_v003', True),
                                      ('render_fibonacci_video_v003', False)]:
            with self.subTest(revision=revision, motion_pass=motion_pass), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                timeline, audio, video = (folder / name for name in ('timeline.json', 'master.wav', 'movie.mp4'))
                timeline.write_text(json.dumps({'renderer_implementation': revision}))
                audio.write_bytes(b'master')
                video.write_bytes(b'movie')
                commands = []

                def run(command, **kwargs):
                    commands.append(command)
                    evidence = Path(command[command.index('--out-dir') + 1])
                    evidence.mkdir()
                    is_motion = 'verify_fibonacci_motion_v' in command[2]
                    (evidence / 'verification.json').write_text(json.dumps({'passed': motion_pass if is_motion else True}))

                args = argparse.Namespace(production='fibonacci', video=str(video), out_dir=str(folder / 'qa'),
                                          ffmpeg=None, ffprobe=None, delivery_dir=None)
                with patch.object(portable, 'production', return_value=('fibonacci-test', 'fibonacci', {})), \
                     patch.object(portable, 'inputs', return_value=(timeline, audio, None)), \
                     patch.object(portable, 'executable', side_effect=lambda name, explicit: name), \
                     patch.object(portable.subprocess, 'run', side_effect=run):
                    if revision != 'render_fibonacci_video' and not motion_pass:
                        with self.assertRaisesRegex(ValueError, 'character motion'):
                            portable.verify(args)
                        self.assertFalse((folder / 'qa/portable-verification.json').exists())
                    else:
                        result = portable.verify(args)
                        self.assertEqual(result['status'], 'pass')
                        self.assertEqual('motion_evidence' in result, revision != 'render_fibonacci_video')
                self.assertEqual(len(commands), 2 if revision != 'render_fibonacci_video' else 1)
                expected_video = 'verify_fibonacci_video_v003.py' if revision.endswith('v003') else 'verify_fibonacci_video.py'
                self.assertEqual(Path(commands[0][2]).name, expected_video)

    def test_custom_revision_receipt_identifies_the_renderer_actually_used(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            timeline, master, aac, implementation = (folder / name for name in
                ('timeline.json', 'master.wav', 'accepted.m4a', 'render_fibonacci_video_v003.py'))
            plan = {'renderer_implementation': 'tools/render_fibonacci_video_v003.py'}
            timeline.write_text(json.dumps(plan))
            master.write_bytes(b'measured master')
            aac.write_bytes(b'accepted AAC')
            implementation.write_bytes(b'exact revision renderer fixture')
            used = []

            def encode(index, source, output, frames, ffmpeg, preset, crf):
                used.append(source)
                output.write_bytes(b'new picture plus copied AAC')

            renderer = SimpleNamespace(stage=lambda scene, destination: (destination/'frames.ffconcat', [1], [1]),
                                       encode=encode, aac_hash=lambda source, ffmpeg: 'same-adts-payload')
            args = argparse.Namespace(command='render', production='fibonacci', timeline=str(timeline),
                                      audio=str(master), motion_manifest=None, out_dir=str(folder/'delivery'),
                                      work_dir=str(folder), ffmpeg='ffmpeg', crf=18, preset='veryfast')
            row = {'output': 'output/fibonacci-counting-001-v002/fibonacci.mp4',
                   'render_implementation': 'tools/render_fibonacci_video_v002.py'}
            original_path = portable.project_path
            resolve = lambda value: implementation if value == plan['renderer_implementation'] else original_path(value)
            with patch.object(portable, 'production', return_value=('fibonacci-test', 'fibonacci', row)), \
                 patch.object(portable, 'check_inputs', return_value=(plan, renderer, SimpleNamespace(frame_count=30), 104)), \
                 patch.object(portable, 'executable', return_value='ffmpeg'), \
                 patch.object(portable, 'project_path', side_effect=resolve), \
                 patch.object(portable, 'fibonacci_aac_source', return_value=aac):
                result = portable.render_or_preview(args)
            self.assertEqual(used, [aac])
            self.assertEqual(result['renderer'], plan['renderer_implementation'])
            self.assertEqual(result['renderer_sha256'], portable.sha256(implementation))
            self.assertTrue(result['encoded_audio_bitstream_identical'])


if __name__ == '__main__':
    unittest.main()
