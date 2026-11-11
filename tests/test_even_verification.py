"""Inject sequence, wording, timing and caption faults into delivery QA."""
from copy import deepcopy
import math
import tempfile
from pathlib import Path
import unittest

from PIL import Image, ImageDraw

from tools.verify_even_video import caption_checks, check_block_arrangement, english_number, validate_schedule


def fixture():
    events = []
    def voice(identifier, text, start, end, phase, value=None):
        event = {'id': identifier, 'text': text, 'phase': phase,
                 'type': 'number_voice' if phase == 'count' else 'dialogue',
                 'start_s': start, 'end_s': end,
                 'start_sample_24k': round(start * 24000), 'end_sample_24k': round(end * 24000)}
        if value is not None:
            event['decimal_value'] = value
        events.append(event)
    for index, identifier in enumerate(('I01', 'I02', 'I03', 'I04', 'I05', 'I06', 'I06B', 'I07')):
        voice(identifier, 'Intro.', .8 + index * 4, 1 + index * 4, 'intro')
    scenes = [{'scene': 'intro', 'start_s': 0, 'end_s': 36}]
    cursor = 36
    for value in range(0, 201, 2):
        begin, stop = cursor + .12, cursor + .32
        end = stop + (9.88 if value in (20, 100) else 1.88) if value < 200 else stop + .28
        state = {'scene': 'count', 'decimal_value': value, 'start_s': cursor, 'end_s': end,
                 'voice_start_s': begin, 'voice_end_s': stop}
        voice(f'N{value:03}', english_number(value), begin, stop, 'count', value)
        if value in (20, 100):
            state['teaching'] = {'id': f'T{value:03}', 'start_s': stop + .4, 'end_s': stop + 8.4}
            voice(f'T{value:03}', 'Teaching.', stop + 1, stop + 1.2, 'teaching')
        scenes.append(state)
        cursor = end
    for index, offset in enumerate((1, 2.8, 8.2, 10.8), 1):
        voice(f'F{index:02}', 'Finale.', cursor + offset, cursor + offset + .2, 'finale')
    scenes.append({'scene': 'finale', 'start_s': cursor, 'end_s': cursor + 14})
    events.sort(key=lambda event: event['start_s'])
    duration = cursor + 14
    return {'fps': 30, 'duration_s': duration, 'duration_frames': math.ceil(duration * 30 - 1e-7),
            'scenes': scenes, 'events': events, 'voice_events': events}


class EvenVerificationTests(unittest.TestCase):
    def setUp(self):
        self.plan = fixture()

    def test_canonical_us_cardinals(self):
        for value, text in ((0, 'zero'), (18, 'eighteen'), (40, 'forty'), (98, 'ninety-eight'),
                            (100, 'one hundred'), (102, 'one hundred two'),
                            (178, 'one hundred seventy-eight'), (200, 'two hundred')):
            self.assertEqual(english_number(value), text)

    def test_valid_complete_schedule(self):
        events, report = validate_schedule(self.plan)
        self.assertEqual(len(events), 115)
        self.assertEqual(report['ordinary_two_second_gaps'], 98)
        self.assertEqual(report['teaching_ten_second_gaps'], 2)

    def test_missing_or_duplicated_value_rejected(self):
        for replacement in (19, 22):
            plan = deepcopy(self.plan)
            plan['scenes'][11]['decimal_value'] = replacement
            with self.assertRaisesRegex(ValueError, 'every even value'):
                validate_schedule(plan)

    def test_digit_reading_and_extra_and_rejected(self):
        for text in ('one zero two', 'one hundred and two'):
            plan = deepcopy(self.plan)
            next(event for event in plan['voice_events'] if event['id'] == 'N102')['text'] = text
            with self.assertRaisesRegex(ValueError, 'Incorrect cardinal'):
                validate_schedule(plan)

    def test_wrong_gap_rejected_even_when_scene_voice_agree(self):
        plan = deepcopy(self.plan)
        event = next(event for event in plan['voice_events'] if event['id'] == 'N022')
        state = next(scene for scene in plan['scenes'] if scene.get('decimal_value') == 22)
        event['start_s'] += .1
        event['start_sample_24k'] += 2400
        state['start_s'] += .1
        state['voice_start_s'] += .1
        # Keep scene continuity so the violated count pause is the fault.
        plan['scenes'][11]['end_s'] += .1
        with self.assertRaisesRegex(ValueError, 'Incorrect gap'):
            validate_schedule(plan)

    def test_teaching_cannot_overlap_the_next_count(self):
        plan = deepcopy(self.plan)
        state = next(scene for scene in plan['scenes'] if scene.get('decimal_value') == 20)
        state['teaching']['end_s'] += 2
        with self.assertRaisesRegex(ValueError, 'eight seconds'):
            validate_schedule(plan)

    def test_missing_caption_rejected(self):
        with tempfile.TemporaryDirectory(dir='D:/temp' if Path('D:/temp').exists() else None) as directory:
            path = Path(directory)
            (path / 'english-captions.srt').write_text('1\n00:00:00,800 --> 00:00:01,000\nIntro.\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '115 caption'):
                caption_checks(self.plan, path)

    def test_missing_or_misplaced_block_rejected_from_pixels(self):
        image = Image.new('RGB', (1920, 1080), '#fff8e8')
        draw = ImageDraw.Draw(image)
        for y in (756, 815):
            for x in range(364, 1103, 82):
                draw.rectangle((x - 10, y - 10, x + 10, y + 10), fill='#eabf82')
        self.assertEqual(check_block_arrangement(image, 20)['vertical_pairs'], 10)
        draw.rectangle((354, 746, 374, 766), fill='#fff8e8')
        with self.assertRaisesRegex(ValueError, '19 blocks'):
            check_block_arrangement(image, 20)
        draw.rectangle((394, 746, 414, 766), fill='#eabf82')
        with self.assertRaisesRegex(ValueError, 'vertical pair'):
            check_block_arrangement(image, 20)


if __name__ == '__main__':
    unittest.main()
