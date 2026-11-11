"""Try hash-bound, constant per-utterance AAC peak corrections in a new folder.

Only explicitly named speech intervals receive one scalar. Every other master
sample and every silent interval is preserved byte-for-byte. No dynamic gain,
compression, limiting, speech repair or time stretching is performed. This tool
does not install or overwrite the original master, timeline or video.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import wave

try:
    from .build_prime_episode import probe_loudness
except ImportError:
    from build_prime_episode import probe_loudness

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local(path):
    path = Path(path).resolve()
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def attempt(timeline, corrections, output, ffmpeg):
    plan = json.loads(timeline.read_text())
    correction = json.loads(corrections.read_text())
    master = Path(plan['master_audio']['path'])
    if not master.is_absolute():
        master = ROOT / master
    if sha(master) != plan['master_audio']['sha256']:
        raise ValueError('Original master binding changed')
    events = {r['id']: r for r in plan['voice_events']}
    output.mkdir(parents=True, exist_ok=False)
    with wave.open(str(master)) as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (48000, 2, 3):
            raise ValueError('Expected48k24bit stereo master')
        original = wav.readframes(wav.getnframes())
    pcm = bytearray(original)

    def write(path, data):
        with wave.open(str(path), 'wb') as wav:
            wav.setnchannels(2)
            wav.setsampwidth(3)
            wav.setframerate(48000)
            wav.writeframes(data)

    applied = []
    for row in correction['results']:
        event = events[row['id']]
        if row['source_sha256'] != event['source_sha256'] or not -12 <= row['gain_db'] <= 0:
            raise ValueError('Correction must be nonpositive and bind an exact original source')
        start = event['start_sample_24k'] * 2 * 2 * 3
        end = event['end_sample_24k'] * 2 * 2 * 3
        source = output / f'{event["id"]}-prior-master.wav'
        write(source, original[start:end])
        adjusted = subprocess.check_output([ffmpeg, '-v', 'error', '-i', str(source), '-af',
                                           f'volume={row["gain_db"]:.12f}dB:precision=double',
                                           '-c:a', 'pcm_s24le', '-f', 's24le', 'pipe:1'])
        if len(adjusted) != end - start:
            raise ValueError('Whole-utterance scalar changed sample length')
        pcm[start:end] = adjusted
        applied.append({**row, 'start_sample_48k': start // 6, 'end_sample_48k': end // 6,
                        'prior_interval_sha256': hashlib.sha256(original[start:end]).hexdigest(),
                        'corrected_interval_sha256': hashlib.sha256(adjusted).hexdigest()})
    changed = {r['id'] for r in applied}
    preserved = []
    for event in plan['voice_events']:
        if event['id'] not in changed:
            start, end = event['start_sample_24k'] * 12, event['end_sample_24k'] * 12
            if original[start:end] != pcm[start:end]:
                raise ValueError('Unnamed speech samples changed')
            preserved.append(event['id'])
    candidate = output / 'master-corrected.wav'
    write(candidate, pcm)
    encoded = output / 'accepted-aac-candidate.m4a'
    command = [ffmpeg, '-v', 'error', '-i', str(candidate), '-map', '0:a:0', '-c:a', 'aac',
               '-b:a', '192k', '-ar', '48000', '-ac', '2', '-movflags', '+faststart', str(encoded)]
    subprocess.run(command, check=True)
    master_levels, aac_levels = probe_loudness(ffmpeg, candidate), probe_loudness(ffmpeg, encoded)
    passed = (float(master_levels['input_tp']) <= -2 and abs(float(master_levels['input_i']) + 16) <= 1
              and float(aac_levels['input_tp']) <= -1.5 and abs(float(aac_levels['input_i']) + 16) <= 1)
    report = {'schema_version': 1, 'kind': 'AAC-feedback-whole-utterance-scalar-calibration', 'passed': passed,
              'prior_timeline': {'path': local(timeline), 'sha256': sha(timeline)},
              'prior_master': {'path': local(master), 'sha256': sha(master)},
              'corrections': {'path': local(corrections), 'sha256': sha(corrections)},
              'applied': applied, 'byte_identical_other_utterances': preserved,
              'master': {'path': local(candidate), 'sha256': sha(candidate), 'levels': master_levels},
              'aac': {'path': local(encoded), 'sha256': sha(encoded), 'levels': aac_levels},
              'encoder_command': command, 'original_sources_modified': False,
              'timing_or_visual_cues_changed': False,
              'method': 'One extra constant scalar on each explicitly named whole speech interval; unchanged original samples elsewhere; AAC192k trial measured before any final-video mux.'}
    with (output / 'correction-report.json').open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--corrections', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    args = parser.parse_args()
    report = attempt(args.timeline.resolve(), args.corrections.resolve(), args.out_dir.resolve(), args.ffmpeg)
    print(json.dumps({'passed': report['passed'], 'master': report['master'], 'aac': report['aac']}))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
