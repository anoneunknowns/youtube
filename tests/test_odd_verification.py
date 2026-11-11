"""Exercise odd QA with missing values, incorrect parity, timing and diagram faults."""

from copy import deepcopy
import math
from pathlib import Path
import tempfile
import unittest
import wave

from PIL import Image, ImageDraw

from tools.verify_odd_video import (
    INK, MUTED, SIZE, TEAL, _draw_centered, caption_checks, check_ticket_pairs,
    english_number, expected_value_at, field_scores, instruction_scores,
    metadata_checks, numberline_values, pcm_contract_checks, shared, teaching_surface, validate_schedule,
)


def fixture(count_end=199, number_duration=None):
    if number_duration is None:
        number_duration = 1.0 if count_end == 299 else .2
    events = []
    def voice(identifier, text, start, end, phase, value=None):
        event = {'id': identifier, 'text': text, 'phase': phase,
                 'type': 'number_voice' if phase == 'count' else 'dialogue',
                 'start_s': start, 'end_s': end,
                 'start_sample_24k': round(start * 24000), 'end_sample_24k': round(end * 24000)}
        if value is not None:
            event['decimal_value'] = value
        events.append(event)
    for index in range(1, 8):
        voice(f'I{index:02}', 'Intro.', .8 + (index - 1) * 4, 1 + (index - 1) * 4, 'intro')
    scenes = [{'scene': 'intro', 'start_s': 0, 'end_s': 36}]
    cursor = 36
    for value in range(1, count_end + 1, 2):
        start, stop = cursor + .12, cursor + .12 + number_duration
        end = stop + (.28 if value == count_end else 9.88 if value in (9, 101) else 1.88)
        row = {'scene': 'count', 'decimal_value': value, 'start_s': cursor, 'end_s': end,
               'voice_start_s': start, 'voice_end_s': stop}
        voice(f'N{value:03}', english_number(value), start, stop, 'count', value)
        if value in (9, 101):
            row['teaching'] = {'id': f'T{value:03}', 'start_s': stop + .4, 'end_s': stop + 8.4}
            voice(f'T{value:03}', 'Teaching.', stop + 1, stop + 1.2, 'teaching')
        scenes.append(row)
        cursor = end
    for index, offset in enumerate((1, 2.8, 8.2, 10.8), 1):
        voice(f'F{index:02}', 'Finale.', cursor + offset, cursor + offset + .2, 'finale')
    scenes.append({'scene': 'finale', 'start_s': cursor, 'end_s': cursor + 14})
    events.sort(key=lambda row: row['start_s'])
    result = {'fps': 30, 'duration_s': cursor + 14, 'duration_frames': math.ceil((cursor + 14) * 30 - 1e-7),
              'scenes': scenes, 'events': events, 'voice_events': events}
    if count_end == 299:
        result.update(revision_id='odd-counting-v002', count_start=1, count_end=299, count_step=2,
                      pacing_policy={'ordinary_gap_s': 2, 'teaching_gap_s': 10, 'minimum_duration_s': 480})
    return result


class OddVerificationTests(unittest.TestCase):
    def test_all_hundred_odds_and_boundary_counts(self):
        events, result = validate_schedule(fixture())
        self.assertEqual(len(events), 113)
        self.assertEqual(result['ordinary_two_second_gaps'], 97)
        self.assertEqual(result['teaching_ten_second_gaps'], 2)
        self.assertEqual(result['final_count_value'], 199)

    def test_long_form_covers_150_odds_and_163_voices_at_original_pacing(self):
        events, result = validate_schedule(fixture(299))
        self.assertEqual(len(events), 163)
        self.assertEqual(result['count_values'], 150)
        self.assertEqual(result['ordinary_boundaries'], 147)
        self.assertEqual(result['ordinary_gap_s'], 2)
        self.assertEqual(result['teaching_gap_s'], 10)
        self.assertEqual(result['minimum_duration_s'], 480)
        self.assertEqual(result['final_count_value'], 299)

    def test_long_form_under_eight_minutes_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duration is below'):
            validate_schedule(fixture(299, .2))

    def test_stretched_pacing_and_missing_long_form_policy_are_rejected(self):
        plan = fixture(299)
        plan['pacing_policy'].update(ordinary_gap_s=3.2, teaching_gap_s=11.2)
        with self.assertRaisesRegex(ValueError, 'must preserve two-second'):
            validate_schedule(plan)
        del plan['pacing_policy']
        with self.assertRaisesRegex(ValueError, 'explicit long-form pacing'):
            validate_schedule(plan)

    def test_shortened_range_cannot_be_used_for_v002(self):
        plan = fixture(299)
        plan['count_end'] = 199
        with self.assertRaisesRegex(ValueError, 'complete range one through 299'):
            validate_schedule(plan)

    def test_us_cardinals_at_odd_boundaries(self):
        for value, words in ((1, 'one'), (9, 'nine'), (49, 'forty-nine'),
                             (99, 'ninety-nine'), (101, 'one hundred one'),
                             (177, 'one hundred seventy-seven'), (199, 'one hundred ninety-nine')):
            self.assertEqual(english_number(value), words)
        for value, words in ((201, 'two hundred one'), (277, 'two hundred seventy-seven'),
                             (299, 'two hundred ninety-nine')):
            self.assertEqual(english_number(value), words)

    def test_wrong_even_duplicate_and_out_of_range_count_are_rejected(self):
        for bad in (0, 8, 11, 201):
            plan = fixture()
            plan['scenes'][5]['decimal_value'] = bad
            with self.assertRaisesRegex(ValueError, 'every odd integer'):
                validate_schedule(plan)

    def test_digit_reading_or_extra_hundred_and_are_rejected(self):
        for text in ('one zero one', 'one hundred and one'):
            plan = fixture()
            next(row for row in plan['voice_events'] if row['id'] == 'N101')['text'] = text
            with self.assertRaisesRegex(ValueError, 'Incorrect US cardinal'):
                validate_schedule(plan)

    def test_incorrect_teaching_wait_is_rejected(self):
        plan = fixture()
        row = next(row for row in plan['scenes'] if row.get('decimal_value') == 9)
        row['teaching']['end_s'] += .2
        with self.assertRaisesRegex(ValueError, 'eight seconds'):
            validate_schedule(plan)

    def test_context_numberline_has_even_values_but_no_invalid_endpoints(self):
        self.assertEqual(numberline_values(1), tuple(range(1, 8)))
        self.assertEqual(numberline_values(199), tuple(range(193, 200)))
        self.assertEqual(numberline_values(101), tuple(range(98, 105)))
        self.assertEqual(numberline_values(201, 299), tuple(range(198, 205)))
        self.assertEqual(numberline_values(299, 299), tuple(range(293, 300)))
        with self.assertRaisesRegex(ValueError, 'odd integer'):
            numberline_values(301, 299)
        for bad in (0, 2, 200, 201):
            with self.assertRaisesRegex(ValueError, 'odd integer'):
                numberline_values(bad)

    def test_intro_examples_are_not_a_second_count_sequence(self):
        plan = fixture()
        self.assertIsNone(expected_value_at(plan, 0))
        self.assertEqual(expected_value_at(plan, 150), 1)
        self.assertEqual(expected_value_at(plan, 390), 5)
        self.assertEqual(expected_value_at(plan, 750), 1)
        self.assertEqual(expected_value_at(plan, 1080), 1)

    def test_ticket_pairs_require_exactly_one_unpaired_ticket(self):
        for quantity in (1, 5, 9):
            image = teaching_surface(quantity)
            result = check_ticket_pairs(image, quantity)
            self.assertEqual(result['vertical_pairs'], quantity // 2)
            self.assertEqual(result['left_over'], 1)
        image = teaching_surface(9)
        ImageDraw.Draw(image).rectangle((1070, 765, 1170, 807), fill='#f9f0dd')
        with self.assertRaisesRegex(ValueError, 'exactly one amber'):
            check_ticket_pairs(image, 9)

    def test_missing_paired_ticket_is_rejected(self):
        image = teaching_surface(5)
        ImageDraw.Draw(image).rectangle((430, 744, 530, 783), fill='#f9f0dd')
        with self.assertRaisesRegex(ValueError, 'Ticket total'):
            check_ticket_pairs(image, 5)

    def test_missing_subtitle_is_rejected(self):
        with tempfile.TemporaryDirectory(dir='D:/temp') as folder:
            directory = Path(folder)
            (directory / 'english-captions.srt').write_text('1\n00:00:00,800 --> 00:00:01,000\nIntro.\n')
            with self.assertRaisesRegex(ValueError, '113 caption'):
                caption_checks(fixture(), directory)

    def test_half_faded_normal_instruction_ghost_is_detected(self):
        # The intended diagram reveals over blank. Inject the former mistake:
        # crossfading from the normal text leaves both labels on the same field.
        correct = teaching_surface(9, 128)
        _draw_centered(ImageDraw.Draw(correct), 'ONE LEFT OVER', (680, 270), 26, MUTED)
        expected = instruction_scores(correct, 'ONE LEFT OVER', 9, 128)
        self.assertEqual(expected['independent_teaching_iou'], 1)
        faulty = Image.blend(teaching_surface('normal'), teaching_surface(9), 128 / 255)
        _draw_centered(ImageDraw.Draw(faulty), 'ONE LEFT OVER', (680, 270), 26, MUTED)
        result = instruction_scores(faulty, 'ONE LEFT OVER', 9, 128)
        self.assertLess(result['independent_teaching_iou'], .88)

    def test_half_faded_header_overlap_is_detected(self):
        correct = teaching_surface(5, 128)
        _draw_centered(ImageDraw.Draw(correct), 'ONE LEFT OVER', (680, 270), 26, MUTED)
        self.assertGreater(instruction_scores(correct, 'ONE LEFT OVER', 5, 128)['header_glyph_iou'], .95)
        previous = teaching_surface(5, 128)
        _draw_centered(ImageDraw.Draw(previous), 'ODD NUMBER', (680, 270), 26, MUTED)
        faulty = Image.blend(previous, correct, .5)
        result = instruction_scores(faulty, 'ONE LEFT OVER', 5, 128)
        self.assertLess(result['header_glyph_iou'], .95)

    def test_muted_even_context_wrong_digit_is_detected(self):
        image = Image.new('RGB', SIZE, '#fffaf0')
        draw = ImageDraw.Draw(image)
        _draw_centered(draw, '101', (680, 447), 360, INK)
        _draw_centered(draw, english_number(101), (730, 635), 42, TEAL)
        for value, center in zip(range(98, 105), (250, 410, 570, 730, 890, 1050, 1210), strict=True):
            _draw_centered(draw, str(value), (center, 955), 46, TEAL if value % 2 else '#aaa596')
        self.assertGreater(min(field_scores(image, 101, 1).values()), .95)
        draw.rectangle((512, 928, 628, 984), fill='#fffaf0')
        _draw_centered(draw, '102', (570, 955), 46, '#aaa596')
        self.assertLess(field_scores(image, 101, 1)['ticket-570'], .88)

    def test_original_pcm_format_and_source_hash_are_checked(self):
        with tempfile.TemporaryDirectory(dir='D:/temp') as folder:
            directory = Path(folder)
            source, master = directory / 'source.wav', directory / 'master.wav'
            def write(path, channels, width, rate):
                with wave.open(str(path), 'wb') as stream:
                    stream.setparams((channels, width, rate, rate, 'NONE', 'not compressed'))
                    stream.writeframes(b'\0' * rate * channels * width)
            write(master, 2, 3, 48000)
            write(source, 1, 2, 24000)
            event = {'id': 'N001', 'source_path': str(source), 'source_sha256': shared.technical.sha256_file(source),
                     'start_sample_24k': 0, 'end_sample_24k': 24000}
            self.assertTrue(pcm_contract_checks([event], master, 1)['passed'])
            event['source_sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'Source hash'):
                pcm_contract_checks([event], master, 1)
            for channels, width, rate in ((2, 2, 24000), (1, 3, 24000), (1, 2, 48000)):
                write(source, channels, width, rate)
                event['source_sha256'] = shared.technical.sha256_file(source)
                with self.assertRaisesRegex(ValueError, 'mono PCM16 24 kHz'):
                    pcm_contract_checks([event], master, 1)

    def test_old_199_final_chapter_cannot_leak_into_299_delivery(self):
        plan = fixture(299)
        pauses = [row['teaching']['start_s'] for row in plan['scenes'][1:-1] if row.get('teaching')]
        seconds = [0, 36, *map(math.floor, pauses), math.floor(plan['scenes'][-1]['start_s'])]
        labels = ['What Are Odd Numbers?', 'Count by Twos from One',
                  'Nine Tickets, Four Pairs and One Left Over', 'From Ninety-Nine to One Hundred One',
                  'We Reached Two Hundred Ninety-Nine']
        chapters = '\n'.join(f'{value // 60:02}:{value % 60:02} {label}' for value, label in zip(seconds, labels, strict=True)) + '\n'
        with tempfile.TemporaryDirectory(dir='D:/temp') as folder:
            directory = Path(folder)
            (directory / 'chapters.txt').write_text(chapters)
            (directory / 'upload-details.txt').write_text(
                'Title\nCount Odd Numbers from 1 to 299 | Count by Twos | Num-Num Numbers\n\n'
                'Description\nCount odd numbers from one to two hundred ninety-nine with Red Panda.\n' + chapters +
                '\nFiles\nVideo: odd-299.mp4\nCaptions: english-captions.srt (English)\n')
            self.assertTrue(metadata_checks(plan, directory, 'odd-299.mp4')['passed'])
            (directory / 'chapters.txt').write_text(chapters.replace('Two Hundred Ninety-Nine', 'One Hundred Ninety-Nine'))
            with self.assertRaisesRegex(ValueError, 'Final chapter title'):
                metadata_checks(plan, directory, 'odd-299.mp4')


if __name__ == '__main__':
    unittest.main()
