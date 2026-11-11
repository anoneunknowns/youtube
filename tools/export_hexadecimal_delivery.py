"""Export English captions, chapters and upload copy from the measured hexadecimal timeline."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path

if __package__:
    from .export_octal_delivery import SERIES_URL, format_srt
else:
    from export_octal_delivery import SERIES_URL, format_srt


SYMBOLS = '0123456789ABCDEF'
TOKENS = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
          'A', 'B', 'C', 'D', 'E', 'F')
TITLE = 'Count in Hexadecimal from 0 to 7F | Num-Num Numbers'


def count_readings(timeline):
    readings = defaultdict(list)
    for event in sorted(timeline['events'], key=lambda row: row['start_s']):
        if event['type'] == 'digit_voice' and event['phase'] == 'count':
            readings[event['decimal_value']].append(event)
    if list(readings) != list(range(128)):
        raise ValueError('Measured speech must count each value from 0 through 127 in order')
    for value, events in readings.items():
        symbols = format(value, 'X')
        expected = [(TOKENS[int(symbol, 16)], slot)
                    for slot, symbol in enumerate(symbols, 2 - len(symbols))]
        actual = [(event['token'], event['slot_index']) for event in events]
        if actual != expected:
            raise ValueError(f'Incorrect hexadecimal reading for {symbols}: {actual!r}')
    return readings


def caption_rows(timeline):
    rows = []
    for events in count_readings(timeline).values():
        text = ' '.join(event['token'] for event in events)
        rows.append((events[0]['start_s'], events[-1]['end_s'], text[0].upper() + text[1:] + '.'))
    example_ids = {'I05A', 'I05-ONE', 'I05-A', 'I05B'}
    example, actual_dialogue = [], []
    for event in timeline['events']:
        if event['id'] in example_ids:
            if event['phase'] != 'intro':
                raise ValueError(f"Example event is outside the intro: {event['id']}")
            example.append(event)
        elif event['type'] == 'dialogue':
            actual_dialogue.append(event['id'])
            rows.append((event['start_s'], event['end_s'], event['text']))
    scripted = [cue for section in (timeline['intro'], *timeline['pauses'], timeline['finale'])
                for cue in section['dialogue']]
    expected_dialogue = {cue['id'] for cue in scripted} - {'I05'}
    if len(scripted) != 20 or len(actual_dialogue) != 19 or set(actual_dialogue) != expected_dialogue:
        raise ValueError('Measured dialogue must contain each of the twenty scripted cues once')
    if len(example) != 4 or {event['id'] for event in example} != example_ids:
        raise ValueError('The introductory example requires four distinct measured events')
    text = next(cue['text'] for cue in scripted if cue['id'] == 'I05')
    rows.append((min(event['start_s'] for event in example), max(event['end_s'] for event in example), text))
    rows.sort()
    previous_end = 0.0
    for start, end, text in rows:
        if not all(math.isfinite(value) for value in (start, end)) or not previous_end <= start < end <= timeline['duration_s']:
            raise ValueError(f'Invalid or overlapping caption timing for {text!r}')
        if not text.strip() or '\n' in text or round(start * 1000) >= round(end * 1000):
            raise ValueError(f'Invalid caption for {text!r}')
        previous_end = end
    return rows


def chapter_lines(timeline):
    pauses = {pause['after_decimal_value']: pause for pause in timeline['pauses']}
    marks = [
        (0, 'Learn Hexadecimal and the Letter Values'),
        (timeline['counted_states'][0]['estimated_display_start_s'], 'Start Counting at Zero'),
        (pauses[15]['estimated_start_s'], 'From F to 10 in Base Sixteen'),
        (pauses[63]['estimated_start_s'], 'Check the Place Values'),
        (timeline['finale']['estimated_start_s'], 'We Reached 7F in Base Sixteen!'),
    ]
    marks = [(math.floor(at), text) for at, text in marks]
    boundaries = [at for at, _ in marks] + [timeline['duration_s']]
    if any(end - start < 10 for start, end in zip(boundaries, boundaries[1:])):
        raise ValueError('Chapters must be at least ten seconds long')
    return [f'{at // 60:02}:{at % 60:02} {text}' for at, text in marks]


def export_metadata(timeline, output_dir, video_filename):
    rows = caption_rows(timeline)
    chapters = '\n'.join(chapter_lines(timeline)) + '\n'
    description = (
        'Count in hexadecimal, or base sixteen, with Tora the striped cat.\n'
        'Follow the symbols from hexadecimal 0 to 7F as the sign shows the matching decimal '
        'values from 0 to 127. Read each symbol from left to right, learn the values of A through F, '
        'and see how F becomes 10. Pause along the way to check the place values.\n\n'
        f'{chapters}\nNum-Num Numbers — Paspla Studio\n{SERIES_URL}\n'
    )
    upload = (f'Title\n{TITLE}\n\nDescription\n{description}\nFiles\n'
              f'Video: {video_filename}\nCaptions: english-captions.srt (English)\n')
    contents = {'english-captions.srt': format_srt(rows), 'chapters.txt': chapters, 'upload-details.txt': upload}
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, text in contents.items():
        (output_dir / name).write_text(text, encoding='utf-8', newline='\n')
    return {'subtitle_count': len(rows), 'counted_values': 128, 'files': list(contents)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--video-filename', required=True)
    args = parser.parse_args()
    timeline = json.loads(args.timeline.read_text(encoding='utf-8-sig'))
    print(json.dumps(export_metadata(timeline, args.output_dir, args.video_filename)))


if __name__ == '__main__':
    main()
