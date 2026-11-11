"""Verify the measured octal master and the AAC audio from its final movie."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import subprocess
import tempfile
import wave

from render_counting_video import find_ffmpeg
from verify_binary_production import _pcm_values, sha256_file, waveform_correlation


ROOT = Path(__file__).resolve().parents[1]
RATE = 48000
WORDS = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven')
TEACHING_GAPS = {7: 5, 31: 10, 63: 5}
MAX_LAG = 8


def sample(seconds):
    return round(seconds * RATE)


def validate_schedule(plan):
    events = sorted(plan['events'], key=lambda event: event['start_s'])
    groups = defaultdict(list)
    intro_digits = []
    if any(event['type'] not in {'dialogue', 'digit_voice', 'sfx'} for event in events):
        raise ValueError('The audio schedule includes a non-audio event')
    if len({event['id'] for event in events}) != len(events):
        raise ValueError('The audio schedule contains duplicate clip ids')
    cursor = sample(.8)
    for event in events:
        start, end = sample(event['start_s']), sample(event['end_s'])
        if not cursor <= start < end <= sample(plan['duration_s']):
            raise ValueError(f'Invalid audio placement at {event["id"]}')
        cursor = end
        if event['type'] == 'digit_voice' and event['phase'] == 'count':
            groups[event['decimal_value']].append(event)
        if event['type'] == 'digit_voice' and event['phase'] == 'intro':
            intro_digits.append(event)

    if list(groups) != list(range(128)):
        raise ValueError('Count voices must cover each value from 0 to 127 in order')
    within, between = [], []
    for value, group in groups.items():
        octal = format(value, 'o')
        expected = [(WORDS[int(digit)], slot) for slot, digit in enumerate(octal, 3 - len(octal))]
        actual = [(event['token'], event['slot_index']) for event in group]
        if expected != actual:
            raise ValueError(f'Incorrect octal reading for {value}')
        within.extend(sample(right['start_s']) - sample(left['end_s']) for left, right in zip(group, group[1:]))
        if value:
            gap = sample(group[0]['start_s']) - sample(groups[value - 1][-1]['end_s'])
            if gap != sample(TEACHING_GAPS.get(value - 1, 2)):
                raise ValueError(f'Incorrect pause between {value - 1} and {value}')
            between.append(gap)
    if len(within) != 184 or any(gap != sample(.9) for gap in within):
        raise ValueError('All 184 inter-digit pauses must be 0.900 seconds')
    if [(event['token'], event['slot_index']) for event in intro_digits] != [('one', 1), ('two', 2)]:
        raise ValueError('The intro demonstration must read the digits of 12 octal')
    if sample(intro_digits[1]['start_s']) - sample(intro_digits[0]['end_s']) != sample(.9):
        raise ValueError('The intro demonstration digit pause must be 0.900 seconds')

    counts = Counter(event['type'] for event in events)
    if counts != {'digit_voice': 314, 'dialogue': 17, 'sfx': 3}:
        raise ValueError(f'The measured audio schedule is incomplete: {counts}')
    return events, {
        'counted_values': len(groups),
        'count_digit_voices': counts['digit_voice'] - len(intro_digits),
        'within_count_gaps_checked': len(within),
        'within_count_gap_s': .9,
        'intro_digit_gap_s': .9,
        'between_values_checked': len(between),
        'ordinary_two_second_gaps': between.count(sample(2)),
        'teaching_gaps_s': TEACHING_GAPS,
    }


def decode(ffmpeg, source, destination):
    process = subprocess.run(
        [ffmpeg, '-nostdin', '-hide_banner', '-v', 'error', '-xerror', '-n', '-i', str(source),
         '-map', '0:a:0', '-ar', str(RATE), '-ac', '1', '-c:a', 'pcm_s16le', str(destination)],
        capture_output=True,
    )
    if process.returncode:
        raise RuntimeError(f'Audio decode failed for {source}: {process.stderr.decode(errors="replace")}')


def source_references(events, ffmpeg, directory):
    clips = {}
    for event in events:
        path = ROOT / event['source_path']
        key = event['source_sha256']
        if path in clips:
            if clips[path][0] != key:
                raise ValueError(f'Conflicting checksum for {path}')
            continue
        if sha256_file(path) != key:
            raise ValueError(f'Clip checksum mismatch: {path}')
        output = directory / f'clip-{len(clips):02d}.wav'
        decode(ffmpeg, path, output)
        with wave.open(str(output), 'rb') as clip:
            clips[path] = key, _pcm_values(clip.readframes(clip.getnframes()))
    return clips


def verify_track(source, events, clips, duration, ffmpeg, directory, lossy):
    output = directory / ('aac-decoded.wav' if lossy else 'master-decoded.wav')
    decode(ffmpeg, source, output)
    guard = sample(.03 if lossy else .002)
    peak_limit = 3 if lossy else 1
    speech_threshold = .97
    sfx_threshold = .94
    clip_checks = []
    silence_peaks = []
    with wave.open(str(output), 'rb') as reader:
        if abs(reader.getnframes() - duration) > (2048 if lossy else 0):
            raise ValueError(f'Audio duration does not cover the measured timeline: {source}')
        cursor = 0
        for event in events:
            start, end = sample(event['start_s']), sample(event['end_s'])
            gap_start = cursor + (guard if cursor else 0)
            gap_frames = start - guard - gap_start
            if gap_frames > 0:
                reader.setpos(gap_start)
                silence_peaks.append(max(map(abs, _pcm_values(reader.readframes(gap_frames))), default=0))
            cursor = end

            key, reference = clips[ROOT / event['source_path']]
            if abs(len(reference) - (end - start)) > 2:
                raise ValueError(f'Actual clip length differs from the schedule: {event["id"]}')
            reader.setpos(start - MAX_LAG)
            observed = _pcm_values(reader.readframes(len(reference) + 2 * MAX_LAG))
            correlation, lag = waveform_correlation(reference, observed, MAX_LAG)
            threshold = sfx_threshold if event['type'] == 'sfx' else speech_threshold
            if correlation < threshold:
                raise ValueError(f'Actual sound differs from the source at {event["id"]}: {correlation:.5f}')
            clip_checks.append({'id': event['id'], 'type': event['type'], 'source_sha256': key,
                                'correlation': round(correlation, 9), 'best_lag_samples': lag})
        reader.setpos(cursor + guard)
        silence_peaks.append(max(map(abs, _pcm_values(reader.readframes(reader.getnframes()))), default=0))

    maximum_peak = max(silence_peaks)
    if maximum_peak > peak_limit:
        raise ValueError(f'Unexpected audio outside the scheduled clips in {source}: {maximum_peak} PCM16')
    return {
        'path': str(source),
        'sha256': sha256_file(source),
        'clips_checked': len(clip_checks),
        'speech_clips_checked': sum(row['type'] != 'sfx' for row in clip_checks),
        'sfx_clips_checked': sum(row['type'] == 'sfx' for row in clip_checks),
        'minimum_correlation': min(row['correlation'] for row in clip_checks),
        'minimum_speech_correlation': min(row['correlation'] for row in clip_checks if row['type'] != 'sfx'),
        'silence_intervals_checked': len(silence_peaks),
        'boundary_guard_s': guard / RATE,
        'maximum_silent_interior_peak_pcm16': maximum_peak,
        'clips': clip_checks,
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
    drive_temp = Path('D:/temp')
    with tempfile.TemporaryDirectory(prefix='octal-audio-qa-', dir=drive_temp if drive_temp.is_dir() else None) as work:
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
                      'master_minimum_speech_correlation': master['minimum_speech_correlation'],
                      'aac_minimum_speech_correlation': encoded['minimum_speech_correlation'],
                      'aac_maximum_silent_interior_peak_pcm16': encoded['maximum_silent_interior_peak_pcm16']}))


if __name__ == '__main__':
    main()
