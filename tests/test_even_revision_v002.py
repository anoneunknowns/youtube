"""Exercise changed speech lengths and the narrowly scoped v002 wrappers."""

from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
sys.path.insert(0, str(TOOLS))
import build_even_episode as base
import build_even_episode_v002 as revision
import render_even_video as base_renderer
import verify_even_video_v002 as wrapper


class EvenRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The archived v002 input is the comparison baseline. The old v001
        # timeline is not part of the portable inputs; do not reconstruct it
        # and present a newly generated plan as historical evidence.
        production = base.read(ROOT / 'design/even-counting-v1/production-run-v002.json')
        timeline = production['timeline']
        timeline_path = ROOT / timeline['path']
        if base.digest(timeline_path) != timeline['sha256']:
            raise ValueError('Changed archived even-v002 timeline fixture')
        cls.baseline = base.read(timeline_path)
        if cls.baseline['revision_id'] != 'even-counting-v002':
            raise ValueError('Expected the archived even-v002 comparison baseline')
        cls.numbers = {int(number): row for number, row in cls.baseline['numeric_sources'].items()}
        measurements = cls.baseline['speech_measurements']
        measurements_path = ROOT / measurements['path']
        if base.digest(measurements_path) != measurements['sha256']:
            raise ValueError('Changed archived even dialogue fixture')
        measured = base.read(measurements_path)
        cls.dialogue = {row['id']: row for row in measured['dialogue']}

    def revised_plan(self):
        numbers = deepcopy(self.numbers)
        numbers[22]['sample_frames'] += base.RATE // 2
        numbers[22]['duration_s'] += .5
        with patch.object(base, 'validate', revision.validate_revised):
            return base.make_plan(numbers, deepcopy(self.dialogue), base.script_cues())

    def test_changed_take_length_moves_later_states_without_changing_waits(self):
        plan = self.revised_plan()
        self.assertAlmostEqual(plan['duration_s'], self.baseline['duration_s'] + .5)
        old = {row['id']: row for row in self.baseline['voice_events']}
        new = {row['id']: row for row in plan['voice_events']}
        self.assertEqual(new['N022']['start_s'], old['N022']['start_s'])
        self.assertAlmostEqual(new['N024']['start_s'], old['N024']['start_s'] + .5)
        self.assertAlmostEqual(new['T100']['start_s'], old['T100']['start_s'] + .5)
        self.assertAlmostEqual(plan['finale']['start_s'], self.baseline['finale']['start_s'] + .5)
        self.assertAlmostEqual(plan['original_preproduction_estimate_s'],
                               self.baseline['original_preproduction_estimate_s'])
        validation = revision.validate_revised(plan)
        self.assertEqual(validation['ordinary_boundaries_2s'], 98)
        self.assertEqual(validation['teaching_boundaries_10s'], 2)

    def test_old_estimate_cannot_hide_a_changed_measured_duration(self):
        plan = self.revised_plan()
        plan['duration_s'] = self.baseline['duration_s']
        with self.assertRaisesRegex(ValueError, 'measured speech'):
            revision.validate_revised(plan)

    def test_builder_restores_original_validator_on_schedule_failure(self):
        original_validator = base.validate
        def fail_during_schedule(*_args):
            self.assertIs(base.validate, revision.validate_revised)
            raise RuntimeError('Injected scheduling failure')
        with tempfile.TemporaryDirectory(prefix='even-v002-revision-') as directory, ExitStack() as stack:
            stack.enter_context(patch.object(sys, 'argv', ['build-even-v002', '--out', directory, '--ffmpeg', 'ffmpeg']))
            stack.enter_context(patch.object(base, 'accepted_numbers', return_value=(deepcopy(self.numbers), [])))
            stack.enter_context(patch.object(revision, 'replacement_numbers', return_value={}))
            stack.enter_context(patch.object(base, 'reviewed_dialogue', return_value={}))
            stack.enter_context(patch.object(base, 'make_plan', side_effect=fail_during_schedule))
            with self.assertRaisesRegex(RuntimeError, 'Injected scheduling'):
                revision.main()
        self.assertIs(base.validate, original_validator)

    def test_verifier_restores_reference_scene_after_success_or_exception(self):
        original_scene = base_renderer.Scene
        for should_raise in (False, True):
            def run_core():
                self.assertIs(base_renderer.Scene, wrapper.Scene)
                if should_raise:
                    raise RuntimeError('Injected decoder failure')
                return 0
            with self.subTest(should_raise=should_raise), patch.object(sys, 'argv', ['verify-even-v002']), \
                    patch.object(wrapper.verifier, 'main', side_effect=run_core):
                if should_raise:
                    with self.assertRaisesRegex(RuntimeError, 'Injected decoder'):
                        wrapper.main()
                else:
                    self.assertEqual(wrapper.main(), 0)
            self.assertIs(base_renderer.Scene, original_scene)

    def test_v002_verifier_refuses_a_v001_timeline_before_dispatch(self):
        original_scene = base_renderer.Scene
        with tempfile.TemporaryDirectory(prefix='even-v002-revision-') as directory:
            path = Path(directory) / 'timeline.json'
            path.write_text(json.dumps({'revision_id': 'even-counting-v001'}), encoding='utf-8')
            with patch.object(sys, 'argv', ['verify-even-v002', '--timeline', str(path)]), \
                    patch.object(wrapper.verifier, 'main') as core:
                with self.assertRaisesRegex(ValueError, 'v002 recipe'):
                    wrapper.main()
                core.assert_not_called()
        self.assertIs(base_renderer.Scene, original_scene)

    def acceptance_fixture(self, directory):
        directory = Path(directory)
        source = deepcopy(self.numbers[22])
        source['number'] = 22
        source['path'] = str(base.source_path(source['path']).resolve())
        measured = {'numbers': [source]}
        manifest = directory / 'measurements.json'
        manifest.write_text(json.dumps(measured), encoding='utf-8')
        approval = {'role': 'number', 'number': 22, 'accepted': True, 'failures': [],
                    'expected_text': source['spoken_text'], 'path': source['path'],
                    'sha256': source['sha256'], 'duration_s': source['duration_s']}
        gate = {'accepted': True, 'unresolved': [], 'summary': {'unresolved': 0},
                'inputs': {'manifest': {'path': str(manifest), 'sha256': base.digest(manifest)}},
                'results': [approval]}
        return manifest, gate

    def test_individually_accepted_replacement_measures_actual_pcm(self):
        with tempfile.TemporaryDirectory(prefix='even-v002-revision-') as directory:
            manifest, gate = self.acceptance_fixture(directory)
            gate_path = Path(directory) / 'speech-acceptance.json'
            gate_path.write_text(json.dumps(gate), encoding='utf-8')
            result = revision.replacement_numbers(manifest, gate_path, self.numbers)
        self.assertEqual(set(result), {22})
        self.assertEqual(result[22]['sample_frames'], self.numbers[22]['sample_frames'])

    def test_global_acceptance_cannot_override_a_mismatched_individual_result(self):
        for fault in ('missing', 'duplicate', 'wrong-text', 'rejected', 'wrong-duration', 'different-path'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory(prefix='even-v002-revision-') as directory:
                manifest, gate = self.acceptance_fixture(directory)
                approval = gate['results'][0]
                if fault == 'missing':
                    gate['results'] = []
                elif fault == 'duplicate':
                    gate['results'].append(deepcopy(approval))
                elif fault == 'wrong-text':
                    approval['expected_text'] = 'twenty-four'
                elif fault == 'rejected':
                    approval['accepted'] = False
                    approval['failures'] = ['Unresolved pronunciation']
                elif fault == 'wrong-duration':
                    approval['duration_s'] += .1
                else:
                    copy = Path(directory) / 'other-identical-bytes.wav'
                    shutil.copyfile(approval['path'], copy)
                    approval['path'] = str(copy)
                gate_path = Path(directory) / 'speech-acceptance.json'
                gate_path.write_text(json.dumps(gate), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'matching individual|individual source acceptance'):
                    revision.replacement_numbers(manifest, gate_path, self.numbers)


if __name__ == '__main__':
    unittest.main()
