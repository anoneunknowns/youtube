"""Fault injection for independent Fibonacci schedule and decoded glyph checks."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageChops

from tools import verify_fibonacci_video as verify

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT/'design/fibonacci-counting-v1'


def provisional_schedule():
    authored = json.loads((DESIGN/'narration.json').read_text())
    values = verify.fibonacci()
    events = []
    for row in authored:
        event = dict(row, start_s=row['planning_window_seconds'][0], end_s=row['planning_window_seconds'][1])
        if row['id'].startswith('N'):
            n = int(row['id'][1:])
            event.update(index=n, value=values[n])
        events.append(event)
    by_id = {row['id']: row for row in events}
    states = []
    for n, value in enumerate(values):
        voice = by_id[f'N{n:03}']
        state = {'index':n,'value':value,'display_start_s':voice['start_s']-.12,
                 'voice_start_s':voice['start_s'],'voice_end_s':voice['end_s']}
        if n >= 2:
            prefix = by_id[f'E{n:03}']
            state.update(a=values[n-2], b=values[n-1], formula_start_s=prefix['start_s'], formula_end_s=prefix['end_s'])
        states.append(state)
    duration = events[-1]['end_s']+2
    final_start = by_id['O01']['start_s']-.12
    segments = [{'mode':'opening','start_s':0,'end_s':states[0]['display_start_s']}]
    def add(mode,start,end,n,**params):
        if end > start:
            segments.append({'mode':mode,'start_s':start,'end_s':end,'index':n,'params':params})
    for n,state in enumerate(states):
        end = (states[n+1]['display_start_s'] if n == 0 else by_id[f'E{n+1:03}']['start_s']) if n < 40 else final_start
        if n < 2:
            add('seeds',state['display_start_s'],end,n)
            continue
        add('count',state['formula_start_s'],state['display_start_s'],n,stage='input-a')
        explanations = [e for e in events if e['id'].startswith(f'T{n:03}')]
        if explanations:
            transfer_start = explanations[-1]['end_s']+.6
            add('count',state['display_start_s'],explanations[0]['start_s']-.12,n,stage='result')
            for i,e in enumerate(explanations):
                finish = explanations[i+1]['start_s']-.12 if i+1 < len(explanations) else transfer_start
                add('replay',e['start_s']-.12,finish,n,after_index=n,voice_event_id=e['id'],show_replay_label=True)
        elif n < 40:
            transfer_start = state['voice_end_s']+.35
            add('count',state['display_start_s'],transfer_start,n,stage='result')
        else:
            add('count',state['display_start_s'],end,n,stage='result')
            continue
        state.update(transfer_start_s=transfer_start,transfer_end_s=transfer_start+1.2)
        add('count',transfer_start,end,n,stage='transfer',transfer_end_s=transfer_start+1.2,
            next_pair=[values[n-1],values[n]],next_pair_indices=[n-1,n])
    add('finale',final_start,duration,40,history_indices=list(range(41)))
    return {'fps':30,'duration_s':duration,'duration_frames':verify.frame_at(duration),
            'voice_events':events,'counted_states':states,
            'visual_segments':segments}


class IndependentContent(unittest.TestCase):
    def test_binomial_values_preserve_initial_zero_and_both_ones(self):
        values = verify.fibonacci()
        self.assertEqual(values[:4], (0,1,1,2))
        self.assertEqual(len(values), 41)
        self.assertEqual(values[-3:], (39088169,63245986,102334155))
        self.assertEqual(sum(values), 267914295)
        self.assertTrue(all(values[n-2]+values[n-1] == values[n] for n in range(2,41)))

    def test_english_inverse_parser_handles_large_and_zero_groups(self):
        for number in (0,1,13,144,1597,75025,832040,1346269,24157817,102334155):
            with self.subTest(number=number):
                self.assertEqual(verify.parse_cardinal(verify.cardinal(number)), number)
        for bad in ('one two','twenty thirteen','one hundred hundred','one hundred and one',
                    'zero thousand','one million zero','one thousand million','one million one million'):
            with self.subTest(text=bad):
                self.assertIsNone(verify.parse_cardinal(bad))

    def test_authored_all_41_values_and_39_formula_prefixes(self):
        values, authored, order = verify.checked_design()
        self.assertEqual(len(values), 41)
        self.assertEqual(len(authored), 104)
        self.assertEqual(len(order), 104)

    def test_valid_schedule_has_34_ordinary_and_six_checkpoint_boundaries(self):
        result = verify.validate_schedule(provisional_schedule())[-1]
        self.assertEqual(result['ordinary_two_second_boundaries'], 34)
        self.assertEqual(result['checkpoint_boundaries'], 6)

    def test_missing_duplicate_one_state_is_rejected(self):
        plan = provisional_schedule()
        del plan['counted_states'][2]
        with self.assertRaisesRegex(ValueError, 'omit/reorder'):
            verify.validate_schedule(plan)

    def test_one_axis_equivalent_timing_cannot_hide_wrong_visual_lead(self):
        plan = provisional_schedule()
        plan['counted_states'][20]['display_start_s'] += .04
        with self.assertRaisesRegex(ValueError, 'Visual lead'):
            verify.validate_schedule(plan)

    def test_wrong_formula_operand_is_rejected(self):
        plan = provisional_schedule()
        plan['counted_states'][13]['a'] = 88
        with self.assertRaisesRegex(ValueError, 'operands'):
            verify.validate_schedule(plan)

    def test_noncanonical_gap_is_rejected(self):
        plan = provisional_schedule()
        event = next(row for row in plan['voice_events'] if row['id'] == 'E010')
        event['start_s'] += .04
        with self.assertRaises(ValueError):
            verify.validate_schedule(plan)

    def test_handoff_does_not_retain_old_older_value(self):
        plan = provisional_schedule()
        row = next(s for s in plan['visual_segments'] if s.get('params',{}).get('stage') == 'transfer' and s['index'] == 8)
        row['params']['next_pair'] = [8,21]
        with self.assertRaisesRegex(ValueError,'wrong values or labels'):
            verify.validate_schedule(plan)

    def test_final_history_cannot_deduplicate_one(self):
        plan = provisional_schedule()
        plan['visual_segments'][-1]['params']['history_indices'].remove(2)
        with self.assertRaisesRegex(ValueError,'history'):
            verify.validate_schedule(plan)

    def test_pixel_audit_reuse_rejects_failed_prior_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'prior.json'
            report.write_text(json.dumps({'passed':False,'visual':{'passed':False}}))
            with self.assertRaisesRegex(ValueError,'failed visual audit'):
                verify.reuse_identical_video_pixels({},Path(tmp)/'new.mp4',report,'unused',Path(tmp))

    def test_pixel_audit_reuse_rejects_changed_voice_focus_timing_before_decode(self):
        prior=provisional_schedule();current=deepcopy(prior)
        current['voice_events'][0]['start_s']+=.04
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);oldvideo=folder/'old.mp4';oldvideo.write_bytes(b'immutable-source-placeholder')
            timeline=folder/'old.json';timeline.write_text(json.dumps(prior));report=folder/'prior.json'
            report.write_text(json.dumps({'passed':True,'visual':{'passed':True},'source_video':str(oldvideo),
                'source_video_sha256':verify.sha(oldvideo),'source_timeline':str(timeline),'source_timeline_sha256':verify.sha(timeline)}))
            with self.assertRaisesRegex(ValueError,'voice/focus timing'):
                verify.reuse_identical_video_pixels(current,folder/'new.mp4',report,'unused',folder)


class DecodedRasterFaults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        file = DESIGN/'mockups/05-add-and-generate.png'
        if not file.is_file() or file.read_bytes().startswith(b'version https://git-lfs'):
            raise unittest.SkipTest('Fibonacci mockup image bodies required')
        cls.image = Image.open(file).convert('RGB')

    def test_native_and_quarter_glyphs_match_independent_expected_21(self):
        for divisor in (1,4):
            image = self.image if divisor == 1 else self.image.resize((480,270),Image.Resampling.BOX)
            reports = verify.inspect_labels(image, verify.count_labels(8), 0, divisor)
            for report in reports:
                with self.subTest(divisor=divisor, component=report['name']):
                    self.assertTrue(report['passed'], report)

    def test_wrong_result_does_not_pass_by_matching_bbox(self):
        labels = deepcopy(verify.count_labels(8))
        main = next(row for row in labels if row['name'] == 'main-result')
        main['text'] = '22'
        report = next(row for row in verify.inspect_labels(self.image,labels,0) if row['name'].endswith('/main-result'))
        self.assertFalse(report['passed'])
        self.assertLess(report['independent_glyph_iou'], .9)

    def test_single_wrong_digit_in_nine_digit_result_is_rejected(self):
        image = Image.open(DESIGN/'mockups/10-final-addition.png').convert('RGB')
        main = next(row for row in verify.count_labels(40) if row['name']=='main-result')
        bad = dict(main,text='102,334,156')
        report = verify.inspect_labels(image,[bad],0)[0]
        self.assertFalse(report['passed'])
        self.assertFalse(report['numeric_identification_passed'])
        self.assertEqual(report['nearest_wrong_text'],'102,334,155')

    def test_vertical_shift_fails_with_horizontal_axis_still_centered(self):
        mask = verify.observed_ink(self.image,verify.MAIN,verify.INK)
        moved = ImageChops.offset(mask,0,4)
        report = verify.raster_centering_report(moved,verify.MAIN,origin_xy=verify.MAIN[:2],tolerance_px=1)
        self.assertTrue(report['horizontal_centered'])
        self.assertFalse(report['vertical_centered'])
        self.assertFalse(report['passed'])

    def test_revealed_answer_cannot_pass_as_unknown_input_stage(self):
        reports = verify.inspect_labels(self.image,verify.count_labels(8,'input-a'),0)
        result = next(row for row in reports if row['name'].endswith('/operand-2'))
        self.assertFalse(result['passed'])
        segment = {'mode':'count','index':8,'start_s':0,'end_s':1,'params':{'stage':'input-a'}}
        self.assertFalse(verify.unrevealed_reading_check(self.image,segment,0)['passed'])

    def test_multiline_largest_number_reading_is_checked_as_whole_group(self):
        image = Image.open(DESIGN/'mockups/10-final-addition.png').convert('RGB')
        reading = next(row for row in verify.count_labels(40) if row['name'] == 'result-reading')
        self.assertIn('\n', reading['text'])
        report = verify.inspect_labels(image,[reading],0)[0]
        self.assertTrue(report['passed'], report)

    def test_wrong_small_history_index_loses_to_independent_dictionary(self):
        image = Image.open(DESIGN/'mockups/12-all-41-terms.png').convert('RGB')
        original = verify.history_labels()[0]
        self.assertTrue(verify.inspect_labels(image,[original],0)[0]['passed'])
        for wrong in ('F6','F8','F9'):
            row = dict(original,text=wrong)
            report = verify.inspect_labels(image,[row],0)[0]
            with self.subTest(wrong=wrong):
                self.assertFalse(report['passed'])
                self.assertFalse(report['index_identification_passed'])
                self.assertEqual(report['nearest_wrong_index'],'F0')

    def test_decimal_carries_have_independently_expected_column_totals(self):
        self.assertEqual([op['total'] for op in verify.carry_operations(8)],[11,2])
        self.assertEqual([op['total'] for op in verify.carry_operations(13)],[13,13,2])
        self.assertEqual([op['total'] for op in verify.carry_operations(18)],[14,18,15,2])

    def test_visible_luma_punctuation_is_not_lost_to_chroma_desaturation(self):
        image=verify.background().copy()
        # A decoded blue edge can retain >50% luma contrast while its chroma
        # gets averaged with the pale wall. The RGB hue gate must not erase Y.
        image.putpixel((640,542),(168,161,159))
        field=(632,496,662,569)
        mask=verify.observed_ink(image,field,verify.BLUE,method='bt709-luminance')
        self.assertEqual(mask.getpixel((8,46)),255)

    def test_observation_crop_cannot_pass_with_a_cut_recurrence(self):
        row=next(r for r in verify.count_labels(8) if r['name']=='recurrence')
        row['observation']=(620,220,810,286)
        report=verify.inspect_labels(self.image,[row],0)[0]
        self.assertFalse(report['passed'])
        self.assertTrue(report['touches_measurement_edge'])


if __name__ == '__main__':
    unittest.main()
