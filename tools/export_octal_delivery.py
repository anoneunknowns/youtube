"""Export English captions, chapters and upload text from the measured octal timeline."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path

if __package__:
    from .export_delivery_metadata import timestamp
else:
    from export_delivery_metadata import timestamp


DIGIT_WORDS = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven')
TITLE = 'Count in Octal from 0 to 177 | Num-Num Numbers'
SERIES_URL = 'https://pasplastudio.com/num-num-numbers/'


def count_readings(timeline):
    """Return the measured count events by decimal value in speech order."""
    readings = defaultdict(list)
    for event in sorted(timeline['events'], key=lambda row: row['start_s']):
        if event['type'] == 'digit_voice' and event['phase'] == 'count':
            readings[event['decimal_value']].append(event)
    if list(readings) != list(range(128)):
        raise ValueError('Measured speech must count each value from 0 through 127 in order')
    for value, events in readings.items():
        digits = format(value, 'o')
        expected = [(DIGIT_WORDS[int(digit)], slot)
                    for slot, digit in enumerate(digits, 3 - len(digits))]
        actual = [(event['token'], event['slot_index']) for event in events]
        if actual != expected:
            raise ValueError(f'Incorrect speech for octal {digits}: {actual!r}')
    return readings


def caption_rows(timeline):
    rows = []
    for events in count_readings(timeline).values():
        text = ' '.join(event['token'] for event in events).capitalize() + '.'
        rows.append((events[0]['start_s'], events[-1]['end_s'], text))

    example_ids = {'I04A', 'I04-ONE', 'I04-TWO', 'I04B'}
    example_events = []
    dialogue_ids = []
    for event in timeline['events']:
        if event['id'] in example_ids:
            if event['phase'] != 'intro':
                raise ValueError(f"Example event is outside the intro: {event['id']}")
            example_events.append(event)
        elif event['type'] == 'dialogue':
            dialogue_ids.append(event['id'])
            rows.append((event['start_s'], event['end_s'], event['text']))
    if len(example_events) != len(example_ids) or {event['id'] for event in example_events} != example_ids:
        raise ValueError('The intro example requires four distinct measured events')
    if set(dialogue_ids) != {
        'I01', 'I02', 'I03', 'I05', 'I06', 'I07', 'I08',
        'P07', 'S31A', 'S31B', 'P63', 'F03', 'F05', 'F07', 'F09',
    } or len(dialogue_ids) != 15:
        raise ValueError('Measured dialogue does not contain each scripted cue exactly once')
    example = next(row for row in timeline['intro']['dialogue'] if row['id'] == 'I04')
    rows.append((min(event['start_s'] for event in example_events),
                 max(event['end_s'] for event in example_events), example['text']))

    rows.sort()
    previous_end = 0.0
    duration = timeline['duration_s']
    for start, end, text in rows:
        if not all(math.isfinite(value) for value in (start, end)) or not previous_end <= start < end <= duration:
            raise ValueError(f'Invalid or overlapping caption timing for {text!r}')
        if not text.strip() or '\n' in text or round(start * 1000) >= round(end * 1000):
            raise ValueError(f'Invalid caption for {text!r}')
        previous_end = end
    return rows


def chapter_lines(timeline):
    states = {row['decimal_value']: row for row in timeline['counted_states']}
    pauses = {row['after_decimal_value']: row for row in timeline['pauses']}
    marks = [
        (0, 'How to Count in Base Eight'),
        (states[0]['estimated_display_start_s'], 'Start Counting at Zero'),
        (pauses[7]['estimated_start_s'], 'From 7 to 10 in Base Eight'),
        (pauses[31]['estimated_start_s'], 'Stretch Break'),
        (pauses[63]['estimated_start_s'], 'From 77 to 100 in Base Eight'),
        (timeline['finale']['estimated_start_s'], 'We Reached 177 in Base Eight!'),
    ]
    marks = [(math.floor(at), label) for at, label in marks]
    boundaries = [at for at, _ in marks] + [timeline['duration_s']]
    if any(end - start < 10 for start, end in zip(boundaries, boundaries[1:])):
        raise ValueError('The episode chapters must be at least ten seconds apart')
    return [f'{at // 60:02}:{at % 60:02} {label}' for at, label in marks]


def format_srt(rows):
    return '\n'.join(
        f'{index}\n{timestamp(start)} --> {timestamp(end)}\n{text}\n'
        for index, (start, end, text) in enumerate(rows, 1)
    ) + '\n'


def export_metadata(timeline, output_dir, video_filename):
    rows = caption_rows(timeline)
    chapters = '\n'.join(chapter_lines(timeline)) + '\n'
    subtitles = format_srt(rows)
    description = (
        'Count in octal, or base eight, with our pink rabbit under the northern lights.\n'
        'Follow the digits from octal 0 to 177 as the rabbit\'s sign shows the same values '
        'in decimal, from 0 to 127. Read each digit aloud, see what happens after 7 and 77, '
        'and take a short stretch break along the way.\n\n'
        f'{chapters}\nNum-Num Numbers — Paspla Studio\n{SERIES_URL}\n'
    )
    upload = (f'Title\n{TITLE}\n\nDescription\n{description}\nFiles\n'
              f'Video: {video_filename}\nCaptions: english-captions.srt (English)\n')
    files = {'english-captions.srt': subtitles, 'chapters.txt': chapters, 'upload-details.txt': upload}
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, contents in files.items():
        (output_dir / name).write_text(contents, encoding='utf-8', newline='\n')
    return {'subtitle_count': len(rows), 'counted_values': 128, 'files': list(files)}


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
