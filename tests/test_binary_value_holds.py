"""Check completed-value sampling boundaries and reject shorter pauses."""
from copy import deepcopy
import unittest

from tools.verify_binary_value_holds import first_frame_at_or_after,hold_samples


def fixture():
    counts=[]
    cursor=32.0
    for value in range(128):
        start=cursor
        cursor+=.12
        bits=[]
        for index,_ in enumerate(format(value,'b')):
            bits.append({'start_s':cursor,'end_s':cursor+.5})
            cursor+=.5
            if index<len(format(value,'b'))-1:cursor+=.9
        counts.append({'type':'count','decimal_value':value,'start_s':start,
                       'voice_end_s':cursor,'bit_events':bits})
        cursor+=1.88 if value<127 else .28
        if value in (7,63):cursor+=3
        if value==31:cursor+=8
    return {'events':counts,'duration_s':cursor+15}


class ValueHoldTests(unittest.TestCase):
    def test_last_old_and_first_new_are_opposite_sides_of_commit(self):
        for seconds in (32.0,32.000001,17.333333333333332,17.333333333333336):
            index=first_frame_at_or_after(seconds)
            self.assertLess((index-1)/30,seconds)
            self.assertGreaterEqual(index/30,seconds)

    def test_all_gaps_and_representative_sampling_are_covered(self):
        transitions,samples=hold_samples(fixture())
        self.assertEqual(len(transitions),127)
        self.assertEqual(len(samples),44)
        self.assertEqual(len({row['frame_index'] for row in samples}),44)
        self.assertTrue(any(row['from_decimal']==14 and row['to_decimal']==15 for row in samples))
        self.assertEqual(sum(not row['special_teaching_or_stretch_pause'] for row in transitions),124)

    def test_shorter_between_value_or_within_value_pause_is_rejected(self):
        original=fixture()
        between=deepcopy(original)
        between['events'][1]['bit_events'][0]['start_s']-=.1
        with self.assertRaisesRegex(ValueError,'Completed-value voice gap'):
            hold_samples(between)
        within=deepcopy(original)
        within['events'][6]['bit_events'][1]['start_s']-=.1
        with self.assertRaisesRegex(ValueError,'within-value'):
            hold_samples(within)


if __name__=='__main__':unittest.main()
