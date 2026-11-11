"""Verify the explicitly requested slower binary revision without relaxing v001."""
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
    from .verify_binary_production_v002 import validate_policy as validate_baseline_policy
else:
    import verify_binary_production as base
    from verify_binary_production_v002 import validate_policy as validate_baseline_policy

ROOT = Path(__file__).resolve().parents[1]
BOUNDS = (480, 960)
PACING = {'pre_speech_s': .12, 'post_speech_s': .28, 'within_number_gap_s': .60}
POLICY = {'minimum_s': 480, 'maximum_exclusive_s': 960, 'reason': 'user-requested-longer-between-digit-pauses'}


def validate_policy(timeline):
    if timeline.get('revision_id') != 'binary-counting-v003' or timeline.get('duration_policy') != POLICY:
        raise base.BinaryValidationError('Longer duration requires the explicit v003 slower-pacing policy')
    pacing = timeline.get('pacing', {})
    if pacing.get('playback_speed_changed') is not False:
        raise base.BinaryValidationError('Slower counting must preserve the original voice playback speed')
    for key, expected in PACING.items():
        if abs(base.finite(pacing.get(key), f'pacing.{key}') - expected) > 1 / 48000:
            raise base.BinaryValidationError(f'Incorrect declared slower pacing: {key}')
    return BOUNDS


def unchanged_speech(timeline, baseline):
    def speech_events(plan):
        events = [event for event in plan['events'] if event['type'] in ('digit_voice', 'dialogue')]
        result = {event['id']: event for event in events}
        if len(events) != len(result):
            raise base.BinaryValidationError('Speech ids must remain unique')
        return result
    old, new = speech_events(baseline), speech_events(timeline)
    if new.keys() != old.keys():
        raise base.BinaryValidationError('Revision must retain all baseline speech events')
    for identifier, event in new.items():
        original = old[identifier]
        for key in ('type', 'speech_id', 'source_sha256', 'token', 'display_binary', 'bit_index', 'slot_index', 'text', 'phase'):
            if event.get(key) != original.get(key):
                raise base.BinaryValidationError(f'Speech content or source changed: {identifier}/{key}')
        if abs((event['end_s'] - event['start_s']) - (original['end_s'] - original['start_s'])) > 1 / 48000:
            raise base.BinaryValidationError(f'Voice playback duration changed: {identifier}')


def validate_revision(timeline, speech, baseline):
    bounds = validate_policy(timeline)
    report = base.validate_timeline(timeline, speech, duration_bounds=bounds)
    validate_baseline_policy(baseline)
    base.validate_timeline(baseline, speech, duration_bounds=(480, 600))
    unchanged_speech(timeline, baseline)
    if timeline.get('speech_manifest_sha256') != baseline.get('speech_manifest_sha256'):
        raise base.BinaryValidationError('Revision must reuse the accepted baseline speech manifest')
    counts = sorted((event for event in timeline['events'] if event['type'] == 'count'), key=lambda event: event['start_s'])
    old_counts = sorted((event for event in baseline['events'] if event['type'] == 'count'), key=lambda event: event['start_s'])
    pauses = {event['after_decimal_value']: event for event in timeline['events'] if event['type'] == 'pause'}
    finale = next(event for event in timeline['events'] if event['type'] == 'finale')
    old_pauses = {event['after_decimal_value']: event for event in baseline['events'] if event['type'] == 'pause'}
    old_finale = next(event for event in baseline['events'] if event['type'] == 'finale')
    gaps = []
    postholds = []
    for number, row in enumerate(counts):
        bits = row['bit_events']
        if abs(bits[0]['start_s'] - row['start_s'] - PACING['pre_speech_s']) > 1 / 48000:
            raise base.BinaryValidationError(f'Incorrect pre-speech hold at {number}')
        for first, second in zip(bits, bits[1:]):
            gap = second['start_s'] - first['end_s']
            if abs(gap - PACING['within_number_gap_s']) > 1 / 48000:
                raise base.BinaryValidationError(f'Actual spoken digit gap was not slowed: {number}')
            gaps.append(gap)
        boundary = (pauses[number]['start_s'] if number in pauses else
                    counts[number+1]['start_s'] if number < 127 else finale['start_s'])
        hold = boundary - row['voice_end_s']
        if abs(hold - PACING['post_speech_s']) > 1 / 48000:
            raise base.BinaryValidationError(f'Incorrect post-speech hold at {number}')
        postholds.append(hold)
    if len(gaps) != 642:
        raise base.BinaryValidationError('Expected all642 within-number gaps')
    if abs(counts[0]['start_s'] - old_counts[0]['start_s']) > 1 / 48000:
        raise base.BinaryValidationError('Intro timing must stay unchanged')
    for number, pause in pauses.items():
        if abs((pause['end_s']-pause['start_s']) - (old_pauses[number]['end_s']-old_pauses[number]['start_s'])) > 1 / 48000:
            raise base.BinaryValidationError('Teaching and stretch pauses must stay unchanged')
    if abs((finale['end_s']-finale['start_s']) - (old_finale['end_s']-old_finale['start_s'])) > 1 / 48000:
        raise base.BinaryValidationError('Finale timing must stay unchanged')
    old_pacing = baseline['pacing']
    expected_increase = 642 * (PACING['within_number_gap_s']-old_pacing['within_number_gap_s']) + 128 * (PACING['post_speech_s']-old_pacing['post_speech_s'])
    observed_increase = timeline['duration_s'] - baseline['duration_s']
    if abs(observed_increase-expected_increase) > .001:
        raise base.BinaryValidationError('Total revision duration does not match the actual added pauses')
    report.update({'revision_id': timeline['revision_id'], 'duration_policy': timeline['duration_policy'],
                   'pacing_change': {'unchanged_speech_events': 786, 'digit_gaps_checked': len(gaps),
                                     'postholds_checked': len(postholds), 'within_number_gap_s': .60,
                                     'post_speech_s': .28, 'added_duration_s': observed_increase,
                                     'speech_playback_speed_changed': False}})
    return report


def digit_gap_windows(timeline):
    """Find pauses between digits of one value, rather than between values."""
    windows = []
    for count in timeline['events']:
        if count['type'] != 'count':
            continue
        for first, second in zip(count['bit_events'], count['bit_events'][1:]):
            duration = second['start_s'] - first['end_s']
            if abs(duration - .60) > 1 / 48000:
                raise base.BinaryValidationError(f'Inter-digit pause is not 600ms: {first["id"]}')
            windows.append({'from_id': first['id'], 'to_id': second['id'],
                            'decimal_value': count['decimal_value'],
                            'start_s': first['end_s'], 'end_s': second['start_s'],
                            'duration_s': duration})
    return windows


def inspect_gap_windows(reader, windows, guard_s, peak_limit):
    """Check actual silent PCM interiors, retaining codec-boundary tolerance."""
    if reader.getframerate() != 48000 or reader.getnchannels() != 1 or reader.getsampwidth() != 2:
        raise base.BinaryValidationError('Gap analysis requires decoded 48kHz mono PCM16')
    results = []
    for window in windows:
        start = round((window['start_s'] + guard_s) * 48000)
        end = round((window['end_s'] - guard_s) * 48000)
        if end <= start:
            raise base.BinaryValidationError('Gap boundary guard consumes the entire pause')
        reader.setpos(start)
        samples = base._pcm_values(reader.readframes(end - start))
        if len(samples) != end - start:
            raise base.BinaryValidationError('Decoded audio ends inside an inter-digit gap')
        peak = max(abs(sample) for sample in samples)
        rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
        if peak > peak_limit:
            raise base.BinaryValidationError(f'Inter-digit gap contains sound: {window["from_id"]} peak={peak}')
        results.append(dict(window, silent_interior_s=(end - start) / 48000,
                            interior_peak_pcm16=peak, interior_rms_pcm16=rms))
    return results


def verify_gap_silence(timeline, source):
    """Confirm all 642 pauses remain audibly silent in the delivered audio."""
    source = Path(source).resolve()
    windows = digit_gap_windows(timeline)
    if len(windows) != 642:
        raise base.BinaryValidationError('Expected exactly 642 actual inter-digit silence windows')
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise base.BinaryValidationError('FFmpeg is required to inspect delivered pauses')
    lossy = source.suffix.lower() in ('.mp4', '.m4a', '.aac')
    guard = .030 if lossy else .002
    peak_limit = 3 if lossy else 1
    task_temp = Path('D:/temp')
    with tempfile.TemporaryDirectory(prefix='binary-gap-qa-', dir=task_temp if task_temp.is_dir() else None) as folder:
        decoded = Path(folder) / 'decoded.wav'
        subprocess.run([ffmpeg, '-nostdin', '-hide_banner', '-v', 'error', '-n', '-i', str(source),
                        '-map', '0:a:0', '-ar', '48000', '-ac', '1', '-c:a', 'pcm_s16le', str(decoded)],
                       capture_output=True, check=True)
        with wave.open(str(decoded), 'rb') as reader:
            results = inspect_gap_windows(reader, windows, guard, peak_limit)
    return {'passed': True, 'path': str(source), 'sha256': base.sha256_file(source),
            'inter_digit_pauses_checked': len(results), 'scheduled_pause_s': .60,
            'boundary_guard_s': guard, 'peak_limit_pcm16': peak_limit,
            'minimum_verified_silent_interior_s': min(row['silent_interior_s'] for row in results),
            'maximum_observed_interior_peak_pcm16': max(row['interior_peak_pcm16'] for row in results),
            'scope': 'Only within-number word gaps; playback clips and number-transition holds are checked separately. Codec boundary guards exclude AAC pre-echo, not any intended speech.',
            'results': results}


def read_bound_baseline(timeline):
    path = Path(timeline.get('baseline_timeline', ''))
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file() or base.sha256_file(path) != timeline.get('baseline_timeline_sha256'):
        raise base.BinaryValidationError('Baseline timeline is missing or changed after the revision was planned')
    return json.loads(path.read_text(encoding='utf-8-sig')), path.resolve()


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
        baseline, baseline_path = read_bound_baseline(timeline)
        _, speech = base.load_speech(args.speech_manifest)
        if timeline.get('speech_manifest_sha256') != base.sha256_file(args.speech_manifest):
            raise base.BinaryValidationError('Timeline is bound to a different speech manifest')
        report = validate_revision(timeline, speech, baseline)
        report.update({'schema_version': 1, 'kind': 'binary-production-v003-qa',
                       'checked_at': datetime.now(timezone.utc).isoformat(),
                       'timeline': {'path': str(args.timeline.resolve()), 'sha256': base.sha256_file(args.timeline)},
                       'speech_manifest': {'path': str(args.speech_manifest.resolve()), 'sha256': base.sha256_file(args.speech_manifest)},
                       'baseline_timeline': {'path': str(baseline_path), 'sha256': base.sha256_file(baseline_path)}})
        if args.master_audio:
            report['master_audio_waveform'] = base.verify_rendered_audio(timeline, speech, args.master_audio)
            report['master_inter_digit_silence'] = verify_gap_silence(timeline, args.master_audio)
        if args.captions:
            report['captions'] = base.verify_captions(timeline, args.captions)
        if args.video:
            ffprobe = shutil.which('ffprobe')
            if not ffprobe:
                raise base.BinaryValidationError('ffprobe is required for finalMP4 checks')
            completed = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration:stream=width,height,r_frame_rate,codec_type', '-of', 'json', str(args.video)], capture_output=True, text=True, check=True)
            metadata = json.loads(completed.stdout)
            duration = float(metadata['format']['duration'])
            if abs(duration-report['duration_s']) > .08:
                raise base.BinaryValidationError('Encoded duration differs from measured timeline')
            streams = [stream for stream in metadata['streams'] if stream['codec_type']=='video']
            if len(streams)!=1 or (streams[0].get('width'),streams[0].get('height'),streams[0].get('r_frame_rate')) != (1920,1080,'30/1'):
                raise base.BinaryValidationError('Expected one1080p30 video stream')
            report['video'] = {'path':str(args.video.resolve()),'sha256':base.sha256_file(args.video),'duration_s':duration}
            report['encoded_audio_waveform'] = base.verify_rendered_audio(timeline,speech,args.video)
            report['encoded_inter_digit_silence'] = verify_gap_silence(timeline,args.video)
        args.out.parent.mkdir(parents=True,exist_ok=True)
        with args.out.open('x',encoding='utf-8') as output:
            json.dump(report,output,ensure_ascii=False,indent=2)
            output.write('\n')
        print(json.dumps({'passed':True,'report':str(args.out),'states':128,'digit_voices':770,'duration_s':report['duration_s']}))
        return 0
    except (base.BinaryValidationError,OSError,json.JSONDecodeError,subprocess.CalledProcessError) as error:
        print(f'Binary revision QA failed: {error}',file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
