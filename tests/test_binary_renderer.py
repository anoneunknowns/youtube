"""Binary-specific renderer contracts that the decimal renderer cannot cover."""
from copy import deepcopy
import unittest

from tools.render_binary_video import BinaryTimeline


def binary_plan():
    events=[]
    cursor=32.0
    for value in range(128):
        bits=format(value,'b')
        start=cursor
        tokens=[]
        for index,bit in enumerate(bits):
            token={'type':'digit_voice','id':f'bit-{value}-{index}',
                   'decimal_value':value,'bit_index':index,'slot_index':7-len(bits)+index,
                   'token':'one' if bit=='1' else 'zero','start_s':cursor+.12,'end_s':cursor+.62}
            events.append(token)
            tokens.append(token)
            cursor+=.68
        events.append({'type':'count','number':value,'decimal_value':value,
                       'display_binary':bits,'start_s':start,'end_s':cursor+.2,'bit_events':tokens})
        cursor+=.2
    return {'duration_s':cursor+15,'fps':30,'events':events}


class BinaryRendererTests(unittest.TestCase):
    def test_zero_and_every_binary_state_are_accepted(self):
        timeline=BinaryTimeline(binary_plan())
        self.assertIsNone(timeline.count_at(0))
        self.assertEqual(timeline.count_at(32)['display_binary'],'0')
        self.assertEqual(timeline.count_at(timeline.starts[-1])['display_binary'],'1111111')

    def test_word_focus_changes_at_actual_audio_boundaries(self):
        timeline=BinaryTimeline(binary_plan())
        row=timeline.counts[2]
        first,second=row['bit_events']
        self.assertIsNone(timeline.focus_at(row,row['start_s']))
        self.assertEqual(timeline.focus_at(row,first['start_s']),0)
        self.assertIsNone(timeline.focus_at(row,first['end_s']))
        self.assertEqual(timeline.focus_at(row,second['start_s']),1)

    def test_rejects_decimal_value_or_word_slot_mismatch(self):
        plan=binary_plan()
        bad=deepcopy(plan)
        next(e for e in bad['events'] if e['type']=='count' and e['number']==2)['display_binary']='11'
        with self.assertRaises(ValueError):
            BinaryTimeline(bad)
        bad=deepcopy(plan)
        row=next(e for e in bad['events'] if e['type']=='count' and e['number']==2)
        row['bit_events'][0]['slot_index']=0
        with self.assertRaises(ValueError):
            BinaryTimeline(bad)

    def test_rejects_missing_zero_and_out_of_bounds_event(self):
        bad=binary_plan()
        bad['events']=[e for e in bad['events'] if not(e['type']=='count' and e['number']==0)]
        with self.assertRaises(ValueError):
            BinaryTimeline(bad)
        bad=binary_plan()
        bad['duration_s']=40
        with self.assertRaises(ValueError):
            BinaryTimeline(bad)


if __name__=='__main__':
    unittest.main()
