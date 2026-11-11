"""Verify 900ms digit pauses and two-second pauses between complete values."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import wave

if __package__:
    from . import verify_binary_production as base
    from . import verify_binary_production_v004 as previous
else:
    import verify_binary_production as base
    import verify_binary_production_v004 as previous

ROOT = Path(__file__).resolve().parents[1]
BOUNDS = (480, 1440)
PACING = {'pre_speech_s': .12, 'post_speech_s': 1.88,
          'final_post_speech_s': .28, 'within_number_gap_s': .90,
          'between_number_voice_gap_s': 2.0}
POLICY = {'minimum_s': 480, 'maximum_exclusive_s': 1440,
          'reason': 'user-requested-two-second-between-number-pause'}


def validate_policy(timeline):
    if timeline.get('revision_id') != 'binary-counting-v005' or timeline.get('duration_policy') != POLICY:
        raise base.BinaryValidationError('Longer duration requires the explicit v005 number-pause policy')
    pacing = timeline.get('pacing', {})
    if pacing.get('playback_speed_changed') is not False:
        raise base.BinaryValidationError('Number pauses must preserve voice playback speed')
    for key, expected in PACING.items():
        if abs(base.finite(pacing.get(key), f'pacing.{key}') - expected) > 1 / 48000:
            raise base.BinaryValidationError(f'Incorrect declared number pacing: {key}')
    return BOUNDS


def number_transition_windows(timeline):
    counts = sorted((event for event in timeline['events'] if event['type'] == 'count'),
                    key=lambda event: event['start_s'])
    if [event['decimal_value'] for event in counts] != list(range(128)):
        raise base.BinaryValidationError('Number transitions require all 128 values')
    pauses = {event['after_decimal_value']: event for event in timeline['events'] if event['type'] == 'pause'}
    if sorted(pauses) != [7, 31, 63]:
        raise base.BinaryValidationError('Only the three existing teaching pauses may extend transitions')
    windows = []
    for number, (first, second) in enumerate(zip(counts, counts[1:])):
        extra = pauses[number]['end_s'] - pauses[number]['start_s'] if number in pauses else 0
        start, end = first['voice_end_s'], second['bit_events'][0]['start_s']
        if abs(end - start - (2 + extra)) > 1 / 48000:
            raise base.BinaryValidationError(f'Complete-number pause is not two seconds plus teaching: {number}')
        windows.append({'after_decimal_value': number, 'next_decimal_value': number + 1,
                        'from_id': first['bit_events'][-1]['id'], 'to_id': second['bit_events'][0]['id'],
                        'start_s': start, 'end_s': end, 'duration_s': end - start,
                        'kind': 'teaching' if number in pauses else 'ordinary',
                        'teaching_extra_s': extra})
    return windows


def number_silence_segments(timeline, transitions):
    """Exclude only registered chimes and the existing teaching dialogue."""
    audio = [event for event in timeline['events'] if event['type'] in ('dialogue', 'sfx')]
    segments, exclusions = [], []
    for transition in transitions:
        start, end = transition['start_s'], transition['end_s']
        inside = sorted((event for event in audio if event['start_s'] < end and event['end_s'] > start),
                        key=lambda event: event['start_s'])
        cursor = start
        for event in inside:
            if event['start_s'] < start - 1 / 48000 or event['end_s'] > end + 1 / 48000:
                raise base.BinaryValidationError('An excluded clip crosses a number-pause boundary')
            if event['type'] == 'sfx':
                if (event['id'] != 'SE_PLACE' or event.get('before_decimal_value') != transition['next_decimal_value']
                        or abs(event['end_s'] - event['start_s'] - .08) > 1 / 48000):
                    raise base.BinaryValidationError('Only the registered 80ms place chime may interrupt a number pause')
            elif transition['kind'] != 'teaching' or event.get('phase') not in ('place', 'stretch'):
                raise base.BinaryValidationError('Ordinary number pauses cannot contain narration')
            if event['start_s'] < cursor - 1 / 48000:
                raise base.BinaryValidationError('Excluded boundary clips overlap')
            if event['start_s'] > cursor + 1 / 48000:
                segments.append({'after_decimal_value': transition['after_decimal_value'],
                                 'start_s': cursor, 'end_s': event['start_s']})
            exclusions.append(dict(event, after_decimal_value=transition['after_decimal_value']))
            cursor = event['end_s']
        if end > cursor + 1 / 48000:
            segments.append({'after_decimal_value': transition['after_decimal_value'], 'start_s': cursor, 'end_s': end})
    return segments, exclusions


def validate_revision(timeline, speech, baseline):
    report = base.validate_timeline(timeline, speech, duration_bounds=validate_policy(timeline))
    previous.validate_policy(baseline)
    base.validate_timeline(baseline, speech, duration_bounds=previous.BOUNDS)
    previous.unchanged_speech(timeline, baseline)
    if timeline.get('speech_manifest_sha256') != baseline.get('speech_manifest_sha256'):
        raise base.BinaryValidationError('The accepted speech manifest must remain unchanged')
    counts = sorted((event for event in timeline['events'] if event['type'] == 'count'), key=lambda event: event['start_s'])
    old_counts = sorted((event for event in baseline['events'] if event['type'] == 'count'), key=lambda event: event['start_s'])
    pauses = {event['after_decimal_value']: event for event in timeline['events'] if event['type'] == 'pause'}
    old_pauses = {event['after_decimal_value']: event for event in baseline['events'] if event['type'] == 'pause'}
    finale = next(event for event in timeline['events'] if event['type'] == 'finale')
    old_finale = next(event for event in baseline['events'] if event['type'] == 'finale')
    for number, count in enumerate(counts):
        if abs(count['bit_events'][0]['start_s'] - count['start_s'] - .12) > 1 / 48000:
            raise base.BinaryValidationError('The pre-speech display settle must remain 120ms')
        boundary = (pauses[number]['start_s'] if number in pauses else
                    counts[number + 1]['start_s'] if number < 127 else finale['start_s'])
        expected = .28 if number == 127 else 1.88
        if abs(boundary - count['voice_end_s'] - expected) > 1 / 48000:
            raise base.BinaryValidationError(f'Incorrect complete-number posthold: {number}')
    if len(previous.digit_gap_windows(timeline)) != 642:
        raise base.BinaryValidationError('All 642 internal 900ms digit gaps must remain')
    if abs(counts[0]['start_s'] - old_counts[0]['start_s']) > 1 / 48000:
        raise base.BinaryValidationError('Intro timing must remain unchanged')
    for number, pause in pauses.items():
        if abs((pause['end_s'] - pause['start_s']) - (old_pauses[number]['end_s'] - old_pauses[number]['start_s'])) > 1 / 48000:
            raise base.BinaryValidationError('Existing teaching/stretch pause lengths must remain unchanged')
    if abs((finale['end_s'] - finale['start_s']) - (old_finale['end_s'] - old_finale['start_s'])) > 1 / 48000:
        raise base.BinaryValidationError('Finale timing must remain unchanged')
    if abs(timeline['duration_s'] - baseline['duration_s'] - 127 * 1.6) > .001:
        raise base.BinaryValidationError('Added duration must be 1.6s for each of 127 number transitions')
    transitions = number_transition_windows(timeline)
    segments, exclusions = number_silence_segments(timeline, transitions)
    ordinary = [row for row in transitions if row['kind'] == 'ordinary']
    teaching = [row for row in transitions if row['kind'] == 'teaching']
    if len(ordinary) != 124 or [round(row['duration_s'], 6) for row in teaching] != [5, 10, 5]:
        raise base.BinaryValidationError('Expected 124 two-second transitions and the preserved 5/10/5-second teaching transitions')
    report.update({'revision_id': timeline['revision_id'], 'duration_policy': timeline['duration_policy'],
                   'pacing_change': {'unchanged_speech_events': 786, 'digit_gaps_checked': 642,
                                     'within_number_gap_s': .9, 'between_number_transitions_checked': 127,
                                     'ordinary_two_second_transitions': 124,
                                     'teaching_transition_durations_s': [5, 10, 5],
                                     'added_duration_s': timeline['duration_s'] - baseline['duration_s'],
                                     'speech_playback_speed_changed': False},
                   'number_transition_schedule': {'passed': True, 'transitions': transitions,
                                                  'silent_segment_count': len(segments),
                                                  'registered_clip_exclusions': len(exclusions)}})
    return report


def inspect_number_silence(reader, segments, guard, peak_limit):
    results = []
    for segment in segments:
        start = round((segment['start_s'] + guard) * 48000)
        end = round((segment['end_s'] - guard) * 48000)
        if end <= start:
            results.append(dict(segment, verified_silence_s=0, reason='codec-boundary-guards'))
            continue
        reader.setpos(start)
        samples = base._pcm_values(reader.readframes(end - start))
        if len(samples) != end - start:
            raise base.BinaryValidationError('Decoded audio ends within a number pause')
        peak = max(abs(sample) for sample in samples)
        if peak > peak_limit:
            raise base.BinaryValidationError(f'Unexpected sound between complete values after {segment["after_decimal_value"]}: peak={peak}')
        results.append(dict(segment, verified_silence_s=len(samples) / 48000,
                            interior_peak_pcm16=peak,
                            interior_rms_pcm16=math.sqrt(sum(sample * sample for sample in samples) / len(samples))))
    return results


def verify_number_pause_audio(timeline, source):
    source = Path(source).resolve()
    transitions = number_transition_windows(timeline)
    segments, exclusions = number_silence_segments(timeline, transitions)
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise base.BinaryValidationError('FFmpeg is required for number-pause waveform checks')
    lossy = source.suffix.lower() in ('.mp4', '.aac', '.m4a')
    guard, peak_limit = (.03, 3) if lossy else (.002, 1)
    temp = Path('D:/temp')
    chime_results = []
    with tempfile.TemporaryDirectory(prefix='binary-number-pauses-', dir=temp if temp.is_dir() else None) as folder:
        work = Path(folder)
        decoded = work / 'decoded.wav'
        subprocess.run([ffmpeg, '-nostdin', '-hide_banner', '-v', 'error', '-n', '-i', str(source),
                        '-map', '0:a:0', '-ar', '48000', '-ac', '1', '-c:a', 'pcm_s16le', str(decoded)],
                       capture_output=True, check=True)
        chimes = [event for event in exclusions if event['type'] == 'sfx']
        reference = None
        if chimes:
            sfx = ROOT / 'assets/library/audio/sfx/binary/v001'
            registration = json.loads((sfx / 'generation-spec.json').read_text(encoding='utf-8'))
            row = next(row for row in registration['assets'] if row['id'] == 'SE_PLACE')
            chime = sfx / row['path']
            if base.sha256_file(chime) != row['sha256']:
                raise base.BinaryValidationError('Registered place chime checksum changed')
            output = work / 'chime.wav'
            subprocess.run([ffmpeg, '-nostdin', '-hide_banner', '-v', 'error', '-n', '-i', str(chime),
                            '-ar', '48000', '-ac', '1', '-c:a', 'pcm_s16le', str(output)], capture_output=True, check=True)
            with wave.open(str(output), 'rb') as reader:
                reference = base._pcm_values(reader.readframes(reader.getnframes()))
        with wave.open(str(decoded), 'rb') as reader:
            results = inspect_number_silence(reader, segments, guard, peak_limit)
            for event in chimes:
                reader.setpos(round(event['start_s'] * 48000) - 8)
                observed = base._pcm_values(reader.readframes(len(reference) + 16))
                correlation, lag = base.waveform_correlation(reference, observed)
                if correlation < .95:
                    raise base.BinaryValidationError('Excluded number-pause sound does not match the registered chime')
                chime_results.append({'before_decimal_value': event['before_decimal_value'],
                                      'correlation': correlation, 'best_lag_samples': lag})
    verified = [row for row in results if row.get('verified_silence_s', 0) > 0]
    if {row['after_decimal_value'] for row in verified} != set(range(127)):
        raise base.BinaryValidationError('Actual silence was not verified at every number boundary')
    return {'passed': True, 'path': str(source), 'sha256': base.sha256_file(source),
            'number_transitions_checked': 127, 'ordinary_two_second_transitions_checked': 124,
            'minimum_scheduled_transition_s': min(row['duration_s'] for row in transitions),
            'boundary_guard_s': guard, 'peak_limit_pcm16': peak_limit,
            'maximum_observed_silent_interior_peak_pcm16': max(row['interior_peak_pcm16'] for row in verified),
            'registered_chimes_checked': len(chime_results), 'chime_waveform_results': chime_results,
            'teaching_transition_durations_s': [5, 10, 5], 'transitions': transitions,
            'silent_segments': results, 'excluded_registered_clips': exclusions,
            'scope': 'All 127 complete-value boundaries. Existing teaching narration and checksum-registered chimes are excluded from silence checks; their waveforms are checked independently.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--speech-manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--master-audio', type=Path)
    parser.add_argument('--video', type=Path)
    parser.add_argument('--captions', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.out.exists():
            raise base.BinaryValidationError('Refusing to overwrite an existing QA report')
        timeline = json.loads(args.timeline.read_text(encoding='utf-8-sig'))
        baseline, baseline_path = previous.read_bound_baseline(timeline)
        _, speech = base.load_speech(args.speech_manifest)
        if timeline.get('speech_manifest_sha256') != base.sha256_file(args.speech_manifest):
            raise base.BinaryValidationError('Timeline is bound to a different speech manifest')
        report = validate_revision(timeline, speech, baseline)
        report.update({'schema_version': 1, 'kind': 'binary-production-v005-qa',
                       'checked_at': datetime.now(timezone.utc).isoformat(),
                       'timeline': {'path': str(args.timeline.resolve()), 'sha256': base.sha256_file(args.timeline)},
                       'speech_manifest': {'path': str(args.speech_manifest.resolve()), 'sha256': base.sha256_file(args.speech_manifest)},
                       'baseline_timeline': {'path': str(baseline_path), 'sha256': base.sha256_file(baseline_path)}})
        if args.master_audio:
            report['master_audio_waveform'] = base.verify_rendered_audio(timeline, speech, args.master_audio)
            report['master_inter_digit_silence'] = previous.verify_gap_silence(timeline, args.master_audio)
            report['master_between_number_pauses'] = verify_number_pause_audio(timeline, args.master_audio)
        if args.captions:
            report['captions'] = base.verify_captions(timeline, args.captions)
        if args.video:
            ffprobe = shutil.which('ffprobe')
            if not ffprobe:
                raise base.BinaryValidationError('ffprobe is required for encoded-number-pause checks')
            completed = subprocess.run([ffprobe, '-v', 'error', '-show_entries',
                                        'format=duration:stream=width,height,r_frame_rate,codec_type',
                                        '-of', 'json', str(args.video)], capture_output=True, text=True, check=True)
            metadata = json.loads(completed.stdout)
            duration = float(metadata['format']['duration'])
            if abs(duration - timeline['duration_s']) > .08:
                raise base.BinaryValidationError('Encoded duration differs from the measured number-pause timeline')
            streams = [stream for stream in metadata['streams'] if stream['codec_type'] == 'video']
            if len(streams) != 1 or (streams[0].get('width'), streams[0].get('height'), streams[0].get('r_frame_rate')) != (1920, 1080, '30/1'):
                raise base.BinaryValidationError('Expected one 1080p30 encoded stream')
            report['video'] = {'path': str(args.video.resolve()), 'sha256': base.sha256_file(args.video),
                               'duration_s': duration}
            report['encoded_audio_waveform'] = base.verify_rendered_audio(timeline, speech, args.video)
            report['encoded_inter_digit_silence'] = previous.verify_gap_silence(timeline, args.video)
            report['encoded_between_number_pauses'] = verify_number_pause_audio(timeline, args.video)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        print(json.dumps({'passed': True, 'report': str(args.out), 'states': 128,
                          'digit_voices': 770, 'number_transitions': 127, 'duration_s': report['duration_s']}))
        return 0
    except (base.BinaryValidationError, OSError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f'Binary number-pause QA failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
