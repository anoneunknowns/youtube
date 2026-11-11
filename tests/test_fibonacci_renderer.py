"""Arithmetic, result commit and moving-memory contracts of the video renderer."""
import copy
import unittest

from tools import render_fibonacci_video as r


class FibonacciRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = r.smoke_plan()
        cls.scene = r.Scene(cls.plan)

    def test_decimal_columns_reconstruct_real_sums(self):
        expected = {
            (8, 13): [(11, 1, 1), (2, 2, 0)],
            (89, 144): [(13, 3, 1), (13, 3, 1), (2, 2, 0)],
            (987, 1597): [(14, 4, 1), (18, 8, 1), (15, 5, 1), (2, 2, 0)],
        }
        for inputs, columns in expected.items():
            with self.subTest(inputs=inputs):
                steps = r.carry_steps(*inputs)
                self.assertEqual([(s['total'], s['digit'], s['carry_out']) for s in steps], columns)
                self.assertEqual(sum(s['digit'] * 10 ** i for i, s in enumerate(steps)), sum(inputs))

    def test_carry_input_rejects_negative_and_non_integer(self):
        for a, b in ((-1, 2), (1.5, 2), (2, -3)):
            with self.subTest(inputs=(a, b)), self.assertRaises(ValueError):
                r.carry_steps(a, b)

    def test_duplicate_one_terms_have_separate_indices(self):
        self.assertEqual([s['value'] for s in self.plan['counted_states'][:4]], [0, 1, 1, 2])
        self.assertEqual([s['index'] for s in self.plan['counted_states'][:4]], [0, 1, 2, 3])

    def test_result_and_reading_commit_at_same_frame(self):
        for n in (2, 8, 21, 40):
            boundary = self.plan['counted_states'][n]['display_start_s']
            before = self.scene.state(r.frame_at(boundary)-1)
            after = self.scene.state(r.frame_at(boundary))
            self.assertNotEqual(before.stage, 'result')
            self.assertEqual(after.stage, 'result')
            _, pending = self.scene.image(before)
            _, committed = self.scene.image(after)
            pending_names = [x['name'].split('/')[-1] for x in pending['components']]
            committed_names = [x['name'].split('/')[-1] for x in committed['components']]
            self.assertNotIn('main-result', pending_names)
            self.assertNotIn('result-reading', pending_names)
            self.assertIn('main-result', committed_names)
            self.assertIn('result-reading', committed_names)

    def test_completed_handoff_holds_current_result_until_next_formula(self):
        n = 8
        row = self.plan['counted_states'][n]
        state = self.scene.state(r.frame_at(row['transfer_end_s']+.25))
        self.assertEqual((state.n, state.stage, state.transfer_tick), (n, 'transfer', 30))
        _, report = self.scene.image(state)
        self.assertEqual(report['scene_data']['result'], 21)
        moved = {x['name'].split('/')[-1]: x['text'] for x in report['components'] if 'text' in x}
        self.assertEqual(moved['transferred-0'], '13')
        self.assertEqual(moved['transferred-1'], '21')
        self.assertEqual(moved['main-result'], '21')

    def test_handoff_endpoints_land_in_next_input_windows(self):
        for n in (2, 20, 21, 39):
            for tick in (0, 15, 30):
                _, report = self.scene.image(r.Frame('count', n, 'transfer', tick))
                labels = [x for x in report['components'] if '/transferred-' in x['name'] and '/transferred-index' not in x['name']]
                self.assertEqual(len(labels), 2)
                self.assertTrue(all(x['passed'] for x in labels))
                if tick == 30:
                    self.assertEqual([x['target_center_px'][0] for x in labels], [274, 714])

    def test_unprocessed_replay_columns_remain_unknown(self):
        _, report = self.scene.image(r.Frame('replay', 13, carry_column=0, carry_stage='write'))
        result = {x['name'].split('/')[-1]: x['text'] for x in report['components'] if '/column-c-' in x['name']}
        self.assertEqual(result, {'column-c-0': '?', 'column-c-1': '?', 'column-c-2': '3'})
        self.assertEqual(report['scene_data']['completed_columns_from_right'], 1)

    def test_carries_do_not_collide_when_incoming_is_consumed(self):
        for n in (8, 13, 18):
            for column in range(len(r.carry_steps(*r.m.VALUES[n-2:n]))):
                for tick in (0, 15, 30):
                    _, report = self.scene.image(r.Frame('replay', n, carry_column=column, carry_stage='move', carry_tick=tick))
                    self.assertTrue(report['foreground_groups_do_not_overlap'])

    def test_zero_carry_ends_column_without_a_move_instruction(self):
        for n, column in ((8, 1), (13, 2), (18, 3)):
            _, report = self.scene.image(r.Frame('replay', n, carry_column=column, carry_stage='move', carry_tick=30))
            action = next(x['text'] for x in report['components'] if x['name'].endswith('/carry-action'))
            self.assertEqual(action, 'COLUMN COMPLETE')
            detail = next(x['text'] for x in report['components'] if x['name'].endswith('/carry-step-detail'))
            self.assertIn('No further carry.', detail)

    def test_operator_emphasis_stays_outside_the_glyph_field(self):
        a, _ = self.scene.image(r.Frame('count', 8, 'input-a'))
        b, _ = self.scene.image(r.Frame('count', 8, 'input-b'))
        flow, _ = self.scene.image(r.Frame('count', 8, 'flow'))
        self.assertEqual(a.crop((454, 367, 534, 466)).tobytes(), b.crop((454, 367, 534, 466)).tobytes())
        self.assertEqual(a.crop((894, 367, 974, 466)).tobytes(), flow.crop((894, 367, 974, 466)).tobytes())

    def test_single_one_is_described_as_a_place_not_plural_ones(self):
        _, report = self.scene.image(r.Frame('replay', 8, carry_column=0, carry_stage='write'))
        detail = next(x['text'] for x in report['components'] if x['name'].endswith('/carry-step-detail'))
        self.assertEqual(detail, 'Write 1 in the\nones place.\nCarry 1 ten.')

    def test_wide_number_mode_changes_once_at_index21(self):
        for n, expected in ((20, 88), (21, 47), (40, 47)):
            _, report = self.scene.image(r.Frame('count', n))
            self.assertEqual(report['scene_data']['equation_font_px'], expected)

    def test_long_result_reading_keeps_fixed_size_and_two_lines(self):
        _, report = self.scene.image(r.Frame('count', 40))
        reading = next(x for x in report['components'] if x['name'].endswith('/result-reading'))
        self.assertEqual(reading['font_size_px'], 32)
        self.assertLessEqual(reading['text'].count('\n'), 1)
        self.assertTrue(reading['passed'])
        self.assertLessEqual(abs(reading['delta_x_px']), .5)
        self.assertLessEqual(abs(reading['delta_y_px']), .5)

    def test_history_preserves_all41_including_both_ones(self):
        _, report = self.scene.image(r.Frame('finale', 40, legend='history'))
        self.assertEqual(report['scene_data']['history_values'][:3], [0, 1, 1])
        self.assertEqual(len(report['scene_data']['history_values']), 41)
        values = [x for x in report['components'] if '/history-value-' in x['name']]
        self.assertEqual(len(values), 41)

    def test_bad_result_and_bad_display_lead_are_rejected(self):
        bad = copy.deepcopy(self.plan)
        bad['counted_states'][3]['value'] = 999
        with self.assertRaises(ValueError):
            r.Scene(bad)
        bad = copy.deepcopy(self.plan)
        bad['counted_states'][3]['display_start_s'] += .1
        with self.assertRaises(ValueError):
            r.Scene(bad)

    def test_frame_bounds_are_checked(self):
        for index in (-1, self.scene.frame_count):
            with self.assertRaises(IndexError):
                self.scene.state(index)

    def test_fade_ends_in_exact_cream(self):
        state = self.scene.state(self.scene.frame_count-1)
        self.assertEqual(state.cream, 255)
        image, _ = self.scene.image(state)
        self.assertEqual(image.getextrema(), ((255, 255), (250, 250), (240, 240)))


if __name__ == '__main__':
    unittest.main()
