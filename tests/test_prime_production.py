"""Timing regressions for the sparse prime lesson and teaching transitions."""
import json
import math
from pathlib import Path
import unittest
from tools.build_prime_episode import make_plan,validate,VALUES,RATE

ROOT=Path(__file__).resolve().parents[1]

class PrimeProductionTests(unittest.TestCase):
    def setUp(self):
        self.authored=json.loads((ROOT/'design/prime-counting-v1/narration.json').read_text())
        self.sources={r['id']:{'id':r['id'],'text':r['text'],'spoken_text':r['text'],'sample_frames_24k':RATE,'duration_s':1,'source_path':'fixture.wav','source_sha256':'fixture'} for r in self.authored}
        self.plan=make_plan(self.authored,self.sources)

    def test_all168_primes_once_and_no_composites(self):
        values=[r['decimal_value'] for r in self.plan['counted_states']]
        self.assertEqual(len(values),168);self.assertEqual(values,list(VALUES))
        self.assertEqual(values[0],2);self.assertEqual(values[-1],997)
        self.assertNotIn(1,values);self.assertNotIn(9,values);self.assertNotIn(99,values)

    def test_exact_measured_duration_and_pace(self):
        self.assertAlmostEqual(self.plan['duration_s'],168+474.4)
        events=[r for r in self.plan['voice_events'] if r['kind']=='count']
        for l,r in zip(events,events[1:]):
            self.assertAlmostEqual(r['start_s']-l['end_s'],18 if l['decimal_value'] in (2,7,97) else 2)
        for r in self.plan['counted_states']:self.assertAlmostEqual(r['voice_start_s']-r['start_s'],.12)

    def test_visual_segments_cover_all_time_without_overlap(self):
        cursor=0
        for row in self.plan['visual_segments']:
            self.assertAlmostEqual(row['start_s'],cursor);self.assertGreater(row['end_s'],cursor);cursor=row['end_s']
        self.assertAlmostEqual(cursor,self.plan['duration_s'])
        self.assertEqual([r['mode'] for r in self.plan['visual_segments'] if r['phase']=='teaching'],['nine','bridge'])

    def test_overlong_dialogue_expands_window_without_speech_retiming(self):
        self.sources['I02']['sample_frames_24k']=15*RATE;self.sources['I02']['duration_s']=15
        plan=make_plan(self.authored,self.sources)
        self.assertGreater(plan['intro']['end_s'],70)
        ev=next(r for r in plan['voice_events'] if r['id']=='I02')
        self.assertAlmostEqual(ev['end_s']-ev['start_s'],15)
        self.assertTrue(plan['measured_window_adjustments'])

    def test_end_frame_covers_last_audio_sample(self):
        self.assertGreaterEqual(self.plan['duration_frames']/30,self.plan['duration_s'])
        self.assertLess(self.plan['duration_frames']/30-self.plan['duration_s'],1/30)

    def test_invalid_continuous_count_sequence_rejected(self):
        self.plan['voice_events'][10]['decimal_value']=9
        # Modify an actual count row, independent of chronological dialogue positions.
        next(r for r in self.plan['voice_events'] if r['kind']=='count')['decimal_value']=1
        with self.assertRaises(ValueError):validate(self.plan)

if __name__=='__main__':unittest.main()
