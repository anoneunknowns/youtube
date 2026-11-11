"""Verify all hexadecimal speech clips and pauses in the master and final AAC."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import tempfile

from verify_octal_audio import (
    find_ffmpeg, sample, sha256_file, source_references, verify_track,
)


WORDS = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
         'A', 'B', 'C', 'D', 'E', 'F')
SPECIAL_GAPS = {15: 5, 63: 10}


def validate_schedule(plan):
    events = sorted(plan['events'], key=lambda event: event['start_s'])
    counts = defaultdict(list)
    intro = []
    cursor = sample(.8)
    for event in events:
        start, end = sample(event['start_s']), sample(event['end_s'])
        if event['type'] not in {'digit_voice', 'dialogue', 'sfx'}:
            raise ValueError('The audio schedule contains a non-audio event')
        if not cursor <= start < end <= sample(plan['duration_s']):
            raise ValueError(f'Invalid or overlapping audio event: {event["id"]}')
        cursor = end
        if event['type'] == 'digit_voice':
            if event['phase'] == 'count':
                counts[event['decimal_value']].append(event)
            elif event['phase'] == 'intro':
                intro.append(event)
    if len({event['id'] for event in events}) != len(events):
        raise ValueError('Audio event ids must be unique')
    if list(counts) != list(range(128)):
        raise ValueError('The count must cover decimal 0 through 127 in order')
    internal_gaps = []
    transition_gaps = []
    for value, clips in counts.items():
        hexadecimal = format(value, 'X')
        expected = [(WORDS[int(symbol, 16)], slot)
                    for slot, symbol in enumerate(hexadecimal, 2 - len(hexadecimal))]
        if [(clip['token'], clip['slot_index']) for clip in clips] != expected:
            raise ValueError(f'Incorrect symbols or speaking order for {hexadecimal}')
        internal_gaps.extend(sample(b['start_s']) - sample(a['end_s']) for a, b in zip(clips, clips[1:]))
        if value:
            pause = sample(clips[0]['start_s']) - sample(counts[value - 1][-1]['end_s'])
            if pause != sample(SPECIAL_GAPS.get(value - 1, 2)):
                raise ValueError(f'Incorrect completed-value pause after {value - 1:X}')
            transition_gaps.append(pause)
    if len(internal_gaps) != 112 or any(gap != sample(.9) for gap in internal_gaps):
        raise ValueError('All 112 internal symbol pauses must be 0.900 seconds')
    if [(event['token'], event['slot_index'], event['decimal_value']) for event in intro] != [
        ('one', 0, 26), ('A', 1, 26),
    ]:
        raise ValueError('The intro must read the two symbols of 1A hexadecimal')
    if sample(intro[1]['start_s']) - sample(intro[0]['end_s']) != sample(.9):
        raise ValueError('The introductory symbol pause must be 0.900 seconds')
    types = Counter(event['type'] for event in events)
    if types != {'digit_voice': 242, 'dialogue': 21, 'sfx': 2}:
        raise ValueError(f'Incomplete hexadecimal audio schedule: {types}')
    return events, {
        'counted_values': 128, 'count_symbol_voices': 240,
        'within_count_gaps_checked': 112, 'within_count_gap_s': .9, 'intro_symbol_gap_s': .9,
        'between_values_checked': len(transition_gaps),
        'ordinary_two_second_gaps': transition_gaps.count(sample(2)),
        'teaching_gaps_s': SPECIAL_GAPS,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', required=True, type=Path)
    parser.add_argument('--master', required=True, type=Path)
    parser.add_argument('--video', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--ffmpeg')
    args = parser.parse_args()
    plan = json.loads(args.timeline.read_text(encoding='utf-8-sig'))
    events, schedule = validate_schedule(plan)
    ffmpeg = find_ffmpeg(args.ffmpeg)
    duration = sample(plan['duration_s'])
    temp_root = Path('D:/temp')
    with tempfile.TemporaryDirectory(prefix='hex-audio-qa-', dir=temp_root if temp_root.is_dir() else None) as work:
        directory = Path(work)
        clips = source_references(events, ffmpeg, directory)
        master = verify_track(args.master, events, clips, duration, ffmpeg, directory, lossy=False)
        encoded = verify_track(args.video, events, clips, duration, ffmpeg, directory, lossy=True)
    report = {'passed': True, 'timeline_sha256': sha256_file(args.timeline), 'schedule': schedule,
              'master': master, 'encoded_audio': encoded}
    with args.out.open('x', encoding='utf-8') as file:
        json.dump(report, file, indent=2)
        file.write('\n')
    print(json.dumps({'passed': True, 'schedule': schedule,
                      'minimum_aac_speech_correlation': encoded['minimum_speech_correlation'],
                      'maximum_silent_interior_peak_pcm16': encoded['maximum_silent_interior_peak_pcm16']}))


if __name__ == '__main__':
    main()
