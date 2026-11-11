"""Bind measured octal speech, build its exact schedule and write the stereo master."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import unicodedata
import wave

if __package__:
    from . import build_audio_mix as audio
    from .prepare_octal_episode import (
        LIBRARY, ROOT, SAMPLE_RATE, accepted_digit_clips, build_timeline, count_rows, frames, seconds,
    )
else:
    import build_audio_mix as audio
    from prepare_octal_episode import (
        LIBRARY, ROOT, SAMPLE_RATE, accepted_digit_clips, build_timeline, count_rows, frames, seconds,
    )


PLAN = ROOT / 'design/octal-counting-v1/estimated-timeline.json'
OUTPUT = ROOT / 'output/octal-counting-001-v001'
REUSED_IDS = {'S31A', 'S31B', 'F03', 'F07', 'F09'}
EXAMPLE_FRAGMENTS = {'I04A': 'This says', 'I04B': 'Its value is ten.'}
RATE = audio.RATE
TARGET_LUFS = -16.0
TARGET_TRUE_PEAK = -2.0
SFX_BELOW_SPEECH_DB = -18.0


def read(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path: Path, data: dict) -> None:
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def local_path(path: Path) -> str:
    path = path.resolve()
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()


def checked_wav(path: Path, expected_hash: str, duration_s: float, rate: int, channels: int) -> int:
    if audio.file_hash(path) != expected_hash:
        raise ValueError(f'Audio checksum mismatch for {path}')
    with wave.open(str(path), 'rb') as stream:
        if (stream.getframerate(), stream.getnchannels(), stream.getsampwidth()) != (rate, channels, 2):
            raise ValueError(f'Unexpected PCM format for {path}')
        count = stream.getnframes()
        if len(stream.readframes(count)) != count * channels * 2:
            raise ValueError(f'Truncated PCM clip {path}')
    if count <= 0 or not math.isclose(duration_s, count / rate, rel_tol=0, abs_tol=1e-9):
        raise ValueError(f'Incorrect duration for {path}')
    return count


def reused_dialogue(cues: dict[str, str]) -> dict:
    manifest_path = LIBRARY / 'v002/measurements.json'
    acceptance_path = manifest_path.with_name('speech-acceptance.json')
    manifest, acceptance = read(manifest_path), read(acceptance_path)
    if (
        acceptance['accepted'] is not True
        or acceptance['kind'] != 'hash-bound-speech-acceptance'
        or audio.file_hash(manifest_path) != acceptance['inputs']['manifest']['sha256']
    ):
        raise ValueError('Reused dialogue is missing its hash-bound source acceptance')
    clips = {}
    for cue_id in sorted(REUSED_IDS):
        text = cues[cue_id]
        measured, = (row for row in manifest['dialogue'] if row['spoken_text'] == text)
        approved, = (
            row for row in acceptance['results']
            if row['role'] == 'dialogue' and row['expected_text'] == text and row['accepted'] is True
        )
        if any(measured[key] != approved[key] for key in ('path', 'spoken_text', 'sha256', 'duration_s')):
            raise ValueError(f'Dialogue acceptance mismatch for {cue_id}')
        path = manifest_path.parent / measured['path']
        count = checked_wav(path, approved['sha256'], approved['duration_s'], SAMPLE_RATE, 1)
        clips[cue_id] = {
            'text': text,
            'path': local_path(path),
            'sha256': approved['sha256'],
            'sample_frames': count,
            'duration_s': count / SAMPLE_RATE,
            'acceptance_record': local_path(acceptance_path),
            'acceptance_record_sha256': audio.file_hash(acceptance_path),
        }
    return clips


def dialogue_key(text: str) -> str:
    text = unicodedata.normalize('NFKC', text).lower().replace('’', "'").replace("let's", 'let us')
    return ' '.join(re.sub(r'[^a-z0-9 ]', ' ', text).split())


def transcription_status(cue_id: str, candidate: dict, report: dict) -> str:
    expected = dialogue_key(candidate['text'])
    heard = dialogue_key(report['recognized_text'])
    if heard == expected:
        return 'text-match'
    spoken_numbers = {'0': 'zero', '7': 'seven', '8': 'eight', '10': 'ten'}
    spelled = ' '.join(spoken_numbers.get(word, word) for word in heard.split())
    if spelled == expected:
        return 'numeric-format-equivalent'
    if cue_id == 'F05' and heard == 'we reached 1 77 in octal':
        return 'octal-digit-format-equivalent'
    raise ValueError(f'Unresolved ASR difference for {cue_id}: {report["recognized_text"]}')


def new_dialogue(
    candidates: list[dict], reports: list[Path], expected: dict, staging: Path, destination: Path,
) -> dict:
    by_hash = {}
    for report_path in reports:
        report = read(report_path)
        manifest_path = Path(report['source_manifest'])
        if (
            report['kind'] != 'independent-local-asr-review'
            or audio.file_hash(manifest_path) != report['source_manifest_sha256']
        ):
            raise ValueError(f'Unbound automated speech report {report_path}')
        by_hash.update((row['source_sha256'], row) for row in report['results'])
    if Counter(candidate['id'] for candidate in candidates) != Counter(expected.keys()):
        raise ValueError('New speech cues do not match the expected cue IDs')

    clips = {}
    for candidate in candidates:
        cue_id = candidate['id']
        text = expected[cue_id]
        original = Path(candidate['path'])
        match = by_hash.get(candidate['sha256'])
        if (
            candidate['text'] != text or match is None or match['expected_text'] != text
            or Path(match['path']).resolve() != original.resolve()
        ):
            raise ValueError(f'Automated review is not bound to dialogue {cue_id}')
        count = checked_wav(original, candidate['sha256'], candidate['duration_s'], SAMPLE_RATE, 1)
        verification = transcription_status(cue_id, candidate, match)
        path = staging / f'{cue_id}.wav'
        with original.open('rb') as source, path.open('xb') as target:
            shutil.copyfileobj(source, target)
        clips[cue_id] = {
            'text': text,
            'path': local_path(destination / path.name),
            'sha256': candidate['sha256'],
            'sample_frames': count,
            'duration_s': count / SAMPLE_RATE,
            'generation': {k: v for k, v in candidate['generation'].items() if k != 'status'},
            'trim': candidate['trim'],
            'asr_status': verification,
            'asr_transcript': match['recognized_text'],
        }
        if 'phonemes' in candidate:
            clips[cue_id]['phonemes'] = candidate['phonemes']
    return clips


def event(source: dict, cue_id: str, kind: str, phase: str, start: int, text: str, **fields) -> dict:
    end = start + source['sample_frames']
    return {
        'id': cue_id, 'type': kind, 'phase': phase, 'text': text,
        'start_s': seconds(start), 'end_s': seconds(end),
        'start_sample_24k': start, 'end_sample_24k': end,
        'source_path': source['path'], 'source_sha256': source['sha256'],
        **fields,
    }


def assemble_timeline(plan: dict, digits: dict, dialogue: dict) -> dict:
    events = []
    for state in plan['counted_states']:
        value = state['decimal_value']
        for highlight in state['digit_highlights']:
            token = highlight['token']
            item = event(
                digits[token], f'D{value:03d}-{highlight["ordinal"]+1}', 'digit_voice', 'count',
                frames(highlight['estimated_start_s']), token,
                token=token, decimal_value=value, slot_index=highlight['slot_index'],
            )
            if item['end_s'] != highlight['estimated_end_s']:
                raise ValueError(f'Count clip no longer matches estimated timing for {value}')
            events.append(item)

    sections = [('intro', 0, plan['intro']['dialogue'])]
    sections += [('pause', pause['estimated_start_s'], pause['dialogue']) for pause in plan['pauses']]
    sections += [('finale', plan['finale']['estimated_start_s'], plan['finale']['dialogue'])]
    for phase, origin, cues in sections:
        for cue in cues:
            cue_id = cue['id']
            start, limit = (frames(origin) + frames(value) for value in cue['relative_window_s'])
            if cue_id == 'I04':
                start += frames(.035)
                intro_a = event(dialogue['I04A'], 'I04A', 'dialogue', phase, start, EXAMPLE_FRAGMENTS['I04A'])
                one = event(
                    digits['one'], 'I04-ONE', 'digit_voice', phase,
                    intro_a['end_sample_24k'] + frames(.06), 'one',
                    token='one', decimal_value=10, slot_index=1, cue_id_parent='I04',
                )
                two = event(
                    digits['two'], 'I04-TWO', 'digit_voice', phase,
                    one['end_sample_24k'] + frames(.90), 'two',
                    token='two', decimal_value=10, slot_index=2, cue_id_parent='I04',
                )
                intro_b = event(
                    dialogue['I04B'], 'I04B', 'dialogue', phase,
                    two['end_sample_24k'] + frames(.14), EXAMPLE_FRAGMENTS['I04B'],
                )
                if intro_b['end_sample_24k'] > limit:
                    raise ValueError('Measured introductory example does not fit its editing window')
                plan['intro']['example_reading'] = {
                    'cue_id': 'I04', 'display_octal': '12', 'decimal_value': 10,
                    'relative_window_s': cue['relative_window_s'],
                    'digit_event_ids': ['I04-ONE', 'I04-TWO'],
                }
                events.extend((intro_a, one, two, intro_b))
            else:
                item = event(dialogue[cue_id], cue_id, 'dialogue', phase, start, cue['text'])
                if item['end_sample_24k'] > limit:
                    raise ValueError(f'Measured dialogue {cue_id} does not fit its editing window')
                events.append(item)

    for sound in plan['sfx_events']:
        cue_id = sound['id']
        path = ROOT / sound['path']
        spec = read(path.with_name('generation-spec.json'))
        record, = (row for row in spec['assets'] if row['id'] == cue_id and row['path'] == path.name)
        length = checked_wav(path, record['sha256'], record['duration_s'], RATE, 2)
        if length % (RATE // SAMPLE_RATE):
            raise ValueError(f'SFX {cue_id} cannot be represented on the timing grid')
        source = {'path': sound['path'], 'sha256': record['sha256'], 'sample_frames': length // (RATE // SAMPLE_RATE)}
        value = sound.get('before_decimal_value')
        phase, event_id = ('count', f'{cue_id}-{value:03d}') if value is not None else ('finale', cue_id)
        item = event(source, event_id, 'sfx', phase, frames(sound['estimated_start_s']), cue_id)
        if item['end_s'] != sound['estimated_end_s']:
            raise ValueError(f'SFX {cue_id} no longer fits its planned interval')
        events.append(item)

    events.sort(key=lambda item: item['start_sample_24k'])
    if len({item['id'] for item in events}) != len(events):
        raise ValueError('Duplicate measured audio event ID')
    if Counter(item['type'] for item in events) != {'digit_voice': 314, 'dialogue': 17, 'sfx': 3}:
        raise ValueError('Wrong number of measured audio events')
    total = frames(plan['duration_s_estimate'])
    if events[0]['start_sample_24k'] < 0 or events[-1]['end_sample_24k'] > total:
        raise ValueError('Audio runs outside the episode schedule')
    if any(left['end_sample_24k'] > right['start_sample_24k'] for left, right in zip(events, events[1:])):
        raise ValueError('Measured audio events overlap')
    plan.update(
        kind='measured-octal-counting-timeline', status='measured-audio',
        measurement_status='digit-dialogue-and-sfx-wavs-measured', audio_generated=True,
        duration_s=seconds(total), fps=30, master_sample_rate_hz=RATE, master_channels=2, events=events,
        intro_example_gap_s=.90,
    )
    return plan


def measure(ffmpeg: str, path: Path) -> dict:
    log = audio.run_ffmpeg(ffmpeg, [
        '-v', 'info', '-i', str(path), '-af',
        f'loudnorm=I={TARGET_LUFS}:TP={TARGET_TRUE_PEAK}:LRA=7:print_format=json', '-f', 'null', os.devnull,
    ])
    return audio.loudnorm_metrics(log)


def mix(timeline: dict, master_path: Path, work: Path, ffmpeg: str, staged_clips: dict) -> dict:
    by_hash = {}
    usage = Counter(item['source_sha256'] for item in timeline['events'])
    sfx = {item['source_sha256'] for item in timeline['events'] if item['type'] == 'sfx'}
    for item in timeline['events']:
        key = item['source_sha256']
        if key not in by_hash:
            source = staged_clips.get(key, ROOT / item['source_path'])
            if audio.file_hash(source) != key:
                raise ValueError(f'Source changed after measurement: {source}')
            by_hash[key] = audio.canonical_clip(source, work, ffmpeg)
    energy = sum(stats['energy'] * usage[key] for key, (_, stats) in by_hash.items() if key not in sfx)
    samples = sum(stats['sample_count'] * usage[key] for key, (_, stats) in by_hash.items() if key not in sfx)
    speech_rms = math.sqrt(energy / samples) / 32768
    gains = {
        key: min(speech_rms * 10 ** (SFX_BELOW_SPEECH_DB / 20) / stats['rms'], .95 * 32767 / stats['peak'])
        for key, (_, stats) in by_hash.items() if key in sfx
    }
    premaster = work / 'premaster.wav'
    multiplier = RATE // SAMPLE_RATE
    total_frames = frames(timeline['duration_s']) * multiplier
    with wave.open(str(premaster), 'wb') as stream:
        stream.setparams((2, 2, RATE, 0, 'NONE', 'not compressed'))
        cursor = 0
        for item in timeline['events']:
            start = item['start_sample_24k'] * multiplier
            end = item['end_sample_24k'] * multiplier
            key = item['source_sha256']
            path, stats = by_hash[key]
            if round(stats['duration_s'] * RATE) != end - start:
                raise ValueError(f'Resampling changed the scheduled duration for {item["id"]}')
            audio._silence(stream, start - cursor)
            audio._write_clip(stream, path, end - start, gains.get(key, 1))
            cursor = end
        audio._silence(stream, total_frames - cursor)

    before = measure(ffmpeg, premaster)
    gain = min(TARGET_LUFS - float(before['input_i']), TARGET_TRUE_PEAK - float(before['input_tp']))
    audio.run_ffmpeg(ffmpeg, [
        '-v', 'error', '-n', '-i', str(premaster), '-af', f'volume={gain:.6f}dB:precision=double',
        '-c:a', 'pcm_s24le', str(master_path),
    ])
    final = measure(ffmpeg, master_path)
    with wave.open(str(master_path), 'rb') as stream:
        if (stream.getnframes(), stream.getframerate(), stream.getnchannels(), stream.getsampwidth()) != (total_frames, RATE, 2, 3):
            raise ValueError('Master format or frame count differs from the measured timeline')
    if float(final['input_tp']) > TARGET_TRUE_PEAK + .05:
        raise ValueError(f'Master exceeds peak ceiling: {final["input_tp"]}')
    return {
        'duration_s': total_frames / RATE, 'sample_frames': total_frames,
        'master_sha256': audio.file_hash(master_path), 'loudness_lufs': float(final['input_i']),
        'true_peak_dbtp': float(final['input_tp']), 'pcm_bits': 24, 'channels': 2,
        'sample_rate_hz': RATE, 'linear_gain_db': gain, 'bgm': False,
        'target_lufs': TARGET_LUFS, 'target_true_peak_dbtp': TARGET_TRUE_PEAK,
        'sfx_gain_relative_to_speech_rms_db': {key: 20 * math.log10(value * by_hash[key][1]['rms'] / speech_rms)
                                                for key, value in gains.items()},
        'event_counts': dict(Counter(item['type'] for item in timeline['events'])),
    }


def build(output: Path, work_root: Path, candidates: list[dict], reports: list[Path]) -> dict:
    target_paths = [output / name for name in ('timeline.json', 'master.wav', 'audio-qa.json', 'speech')]
    if any(path.exists() for path in target_paths):
        raise ValueError('Choose an output location without an existing octal audio build')
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise ValueError('Registered FFmpeg is required')
    digits = accepted_digit_clips()
    plan = read(PLAN)
    if plan != build_timeline(count_rows(), digits):
        raise ValueError('Stored estimate differs from the current validated episode plan')
    cues = {cue['id']: cue['text'] for section in (plan['intro'], *plan['pauses'], plan['finale'])
            for cue in section['dialogue']}
    expected_new = {key: text for key, text in cues.items() if key not in REUSED_IDS and key != 'I04'}
    expected_new.update(EXAMPLE_FRAGMENTS)
    previous = reused_dialogue(cues)
    speech_dir = output / 'speech'
    with tempfile.TemporaryDirectory(prefix='octal-master-', dir=work_root) as work:
        work = Path(work)
        staging = work / 'speech'
        staging.mkdir()
        fresh = new_dialogue(candidates, reports, expected_new, staging, speech_dir)
        timeline = assemble_timeline(plan, digits, {**previous, **fresh})
        staged_clips = {clip['sha256']: staging / f'{cue_id}.wav' for cue_id, clip in fresh.items()}
        master = work / 'master.wav'
        receipt = mix(timeline, master, work, ffmpeg, staged_clips)
        speech_record = {
            'schema_version': 1, 'measurement_status': 'measured', 'digit_clips': digits,
            'reused_dialogue': previous, 'new_dialogue': fresh,
            'review': {
                'method': 'Offline isolated Whisper tiny.en q8 against exact source hashes, with no prompt text. '
                          'Comparison treats numeral display formatting as equivalent to the corresponding spoken words.',
                'human_listening_performed': False,
                'source_reports_sha256': [audio.file_hash(path) for path in reports],
                'statuses': dict(Counter(clip['asr_status'] for clip in fresh.values())),
            },
        }
        speech_manifest = staging / 'measurements.json'
        write(speech_manifest, speech_record)
        timeline['speech_measurements'] = {
            'path': local_path(speech_dir / speech_manifest.name), 'sha256': audio.file_hash(speech_manifest),
        }
        timeline_path = work / 'timeline.json'
        write(timeline_path, timeline)
        receipt.update(
            kind='octal-audio-master-qa', schema_version=1,
            timeline_sha256=audio.file_hash(timeline_path),
            speech_measurements_sha256=audio.file_hash(speech_manifest),
        )
        qa_path = work / 'audio-qa.json'
        write(qa_path, receipt)
        output.mkdir(parents=True, exist_ok=True)
        for path in (staging, master, qa_path, timeline_path):
            path.rename(output / path.name)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--takes', type=Path, required=True)
    parser.add_argument('--asr', type=Path, action='append', required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=OUTPUT)
    args = parser.parse_args()
    receipt = build(args.out.resolve(), args.work_dir.resolve(), read(args.takes), args.asr)
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
