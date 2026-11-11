"""Sample-driven Fibonacci timing and corruption regressions, without model runs."""
import copy
from array import array
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
import wave

from tools.build_fibonacci_episode import make_plan, validate, deliveries, mix_truepeak_scalars, VALUES, RATE, CHECKPOINTS
from tools.calibrate_fibonacci_aac import attempt as try_aac_correction

ROOT = Path(__file__).resolve().parents[1]


class FibonacciProductionTests(unittest.TestCase):
    def setUp(self):
        self.authored = json.loads((ROOT / 'design/fibonacci-counting-v1/narration.json').read_text())
        self.sources = {r['id']: {'id': r['id'], 'text': r['text'], 'spoken_text': r['text'],
                                'source_path': 'fixture.wav', 'source_sha256': 'fixture',
                                'sample_frames_24k': 6 * RATE, 'duration_s': 6}
                        for r in self.authored}
        self.plan = make_plan(self.authored, self.sources)

    def test_zero_and_two_distinct_ones_are_retained(self):
        states = self.plan['counted_states']
        self.assertEqual([s['value'] for s in states], VALUES)
        self.assertEqual([(s['index'], s['value']) for s in states[:3]], [(0, 0), (1, 1), (2, 1)])
        self.assertEqual(len(states), 41)
        self.assertEqual(states[-1]['value'], 102334155)

    def test_measured_lengths_and_fixed_transition_sum(self):
        self.assertAlmostEqual(self.plan['duration_s'], 104 * 6 + 107.04)
        for event in self.plan['voice_events']:
            self.assertAlmostEqual(event['end_s'] - event['start_s'], event['sample_frames_24k'] / RATE)

    def test_result_lead_formula_gap_and_ordinary_handoff(self):
        events = {e['id']: e for e in self.plan['voice_events']}
        for n, state in enumerate(self.plan['counted_states']):
            self.assertAlmostEqual(state['voice_start_s'] - state['result_start_s'], .12)
            if n >= 2:
                self.assertAlmostEqual(events[f'N{n:03}']['start_s'] - events[f'E{n:03}']['end_s'], .16)
            if 2 <= n < 40 and n not in CHECKPOINTS:
                self.assertAlmostEqual(events[f'E{n+1:03}']['start_s'] - state['voice_end_s'], 2)
                self.assertGreater(state['transfer_start_s'], state['voice_end_s'])
                self.assertLess(state['transfer_end_s'], state['cycle_end_s'])

    def test_checkpoint_explanations_do_not_double_count(self):
        teaching = self.plan['teaching']
        self.assertEqual([t['index'] for t in teaching], list(CHECKPOINTS))
        self.assertEqual(len([e for e in self.plan['voice_events'] if e['kind'] == 'count']), 41)
        self.assertTrue(all(len(t['voice_event_ids']) == 2 for t in teaching))
        for t in teaching:
            state = self.plan['counted_states'][t['index']]
            self.assertAlmostEqual(state['transfer_start_s'], t['end_s'])

    def test_visual_segments_cover_every_instant(self):
        cursor = 0
        for segment in self.plan['visual_segments']:
            self.assertAlmostEqual(segment['start_s'], cursor)
            self.assertGreater(segment['end_s'], cursor)
            cursor = segment['end_s']
        self.assertAlmostEqual(cursor, self.plan['duration_s'])

    def test_long_utterance_is_never_squeezed_into_planned_window(self):
        self.sources['E040']['sample_frames_24k'] = 19 * RATE + 137
        self.sources['E040']['duration_s'] = (19 * RATE + 137) / RATE
        plan = make_plan(self.authored, self.sources)
        event = next(e for e in plan['voice_events'] if e['id'] == 'E040')
        self.assertEqual(event['end_sample_24k'] - event['start_sample_24k'], 19 * RATE + 137)
        self.assertAlmostEqual(plan['duration_s'] - self.plan['duration_s'], 13 + 137 / RATE)

    def test_fractional_frame_ends_cover_audio_without_extra_frame(self):
        frames = self.plan['duration_frames']
        self.assertGreaterEqual(frames / 30, self.plan['duration_s'])
        self.assertLess(frames / 30 - self.plan['duration_s'], 1 / 30)

    def test_result_repetition_in_prefix_is_rejected(self):
        plan = copy.deepcopy(self.plan)
        next(e for e in plan['voice_events'] if e['id'] == 'E008')['text'] += ' twenty-one'
        with self.assertRaises(ValueError):
            validate(plan)

    def test_wrong_operand_or_count_value_is_rejected(self):
        plan = copy.deepcopy(self.plan)
        plan['counted_states'][13]['a'] = 88
        with self.assertRaises(ValueError):
            validate(plan)
        plan = copy.deepcopy(self.plan)
        next(e for e in plan['voice_events'] if e['id'] == 'N002')['value'] = 2
        with self.assertRaises(ValueError):
            validate(plan)

    def test_runtime_shortfall_is_reported_not_padded(self):
        for row in self.sources.values():
            row.update(sample_frames_24k=RATE, duration_s=1)
        with self.assertRaisesRegex(ValueError, 'shorter than eight minutes'):
            make_plan(self.authored, self.sources)

    def test_short_seed_section_is_merged_into_next_chapter(self):
        for ident in ('N000', 'N001'):
            self.sources[ident].update(sample_frames_24k=RATE // 2, duration_s=.5)
        plan = make_plan(self.authored, self.sources)
        with tempfile.TemporaryDirectory(prefix='fibonacci-chapters-test-') as tmp:
            deliveries(plan, Path(tmp))
            chapters = (Path(tmp) / 'chapters.txt').read_text().splitlines()
            self.assertEqual(len(chapters), 7)
            self.assertIn('Zero and one, then add the previous two', chapters[1])
            self.assertFalse(any(line.endswith('Add the previous two') for line in chapters))

    def test_sub_ten_second_published_chapter_is_rejected(self):
        plan = copy.deepcopy(self.plan)
        next(t for t in plan['teaching'] if t['index'] == 8)['start_s'] = plan['counted_states'][0]['start_s'] + 5
        with tempfile.TemporaryDirectory(prefix='fibonacci-chapters-invalid-') as tmp:
            with self.assertRaisesRegex(ValueError, '10seconds'):
                deliveries(plan, Path(tmp))

    def test_aac_scalar_cannot_apply_to_a_different_source(self):
        with tempfile.TemporaryDirectory(prefix='fibonacci-codec-hash-test-') as tmp:
            plan = {'duration_s': 1, 'voice_events': [{'id': 'fixture', 'source_sha256': 'expected'}]}
            corrections = {'results': [{'id': 'fixture', 'source_sha256': 'different', 'gain_db': -.2}]}
            with self.assertRaisesRegex(ValueError, 'does not bind this source'):
                mix_truepeak_scalars(plan, Path(tmp), 'not-executed', codec_corrections=corrections)

    @unittest.skipUnless((ROOT / '.venv/bin/ffmpeg').is_file(), 'Local FFmpeg is required for the waveform integration check')
    def test_linear_master_preserves_originals_and_delivery_contract(self):
        with tempfile.TemporaryDirectory(prefix='fibonacci-linear-audio-test-') as tmp:
            out = Path(tmp)
            events = []
            originals = {}
            for i, amplitude in enumerate((.12, .38)):
                path = out / f'source-{i}.wav'
                values = array('h', [round(amplitude * 32767 * math.sin(2 * math.pi * 997 * n / RATE))
                                     for n in range(RATE)])
                with wave.open(str(path), 'wb') as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(RATE)
                    wav.writeframes(values.tobytes())
                checksum = hashlib.sha256(path.read_bytes()).hexdigest()
                originals[path] = checksum
                events.append({'id': f'fixture-{i}', 'source_path': str(path), 'source_sha256': checksum,
                               'sample_frames_24k': RATE, 'start_sample_24k': i * RATE,
                               'end_sample_24k': (i + 1) * RATE})
            plan = {'duration_s': 2, 'voice_events': events}
            report = mix_truepeak_scalars(plan, out, str(ROOT / '.venv/bin/ffmpeg'))
            self.assertLessEqual(float(report['after']['input_tp']), -2)
            self.assertLessEqual(abs(float(report['after']['input_i']) + 16), 1)
            for path, checksum in originals.items():
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), checksum)
            for event in events:
                self.assertLessEqual(event['source_peak_dbfs'] + event['mix_gain_db'], -4.5 + 1e-9)
                self.assertLessEqual(event['per_source_truepeak_calibration_db'], 0)
            with wave.open(str(out / 'master.wav')) as wav:
                self.assertEqual((wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()),
                                 (48000, 2, 3, 96000))
                original_pcm = wav.readframes(wav.getnframes())
            plan['master_audio'] = report
            timeline = out / 'timeline.json'
            timeline.write_text(json.dumps(plan))
            corrections = out / 'codec-scalars.json'
            corrections.write_text(json.dumps({'results': [{'id': 'fixture-1',
                'source_sha256': events[1]['source_sha256'], 'gain_db': -.1}]}))
            trial = try_aac_correction(timeline, corrections, out / 'codec-trial', str(ROOT / '.venv/bin/ffmpeg'))
            self.assertTrue(trial['passed'])
            self.assertEqual(trial['byte_identical_other_utterances'], ['fixture-0'])
            with wave.open(str(out / 'codec-trial/master-corrected.wav')) as wav:
                corrected_pcm = wav.readframes(wav.getnframes())
            self.assertEqual(original_pcm[:48000 * 6], corrected_pcm[:48000 * 6])


if __name__ == '__main__':
    unittest.main()
