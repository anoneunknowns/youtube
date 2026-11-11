"""Extract finished AAC utterances for new, isolated recognition.

No source audio is changed. The decoder honors AAC priming, and cuts use the
measured timeline's sample grid. A new output directory is always required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[1]
RATE = 24000


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def extract(video, timeline, destination, ffmpeg='ffmpeg', channel='left'):
    video, timeline, destination = Path(video).resolve(), Path(timeline).resolve(), Path(destination).resolve()
    plan = json.loads(timeline.read_text())
    events = plan['voice_events']
    if len(events) != 104 or len({row['id'] for row in events}) != 104:
        raise ValueError('Expected all104 distinct Fibonacci voice events')
    for left, right in zip(events, events[1:]):
        if left['end_s'] > right['start_s']:
            raise ValueError('Overlapping or unordered voice events')
    destination.mkdir(parents=True, exist_ok=False)
    decoded = destination / f'final-aac-{channel}-24k.wav'
    subprocess.run([ffmpeg, '-v', 'error', '-nostdin', '-i', str(video), '-map', '0:a:0',
                    '-af', 'pan=mono|c0=c0' if channel == 'left' else 'pan=mono|c0=c1',
                    '-ar', str(RATE), '-c:a', 'pcm_s16le', str(decoded)], check=True)
    with wave.open(str(decoded), 'rb') as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) != (1, 2, RATE):
            raise ValueError('Unexpected decoded PCM format')
        pcm = stream.readframes(stream.getnframes())
        frames = stream.getnframes()
    if frames < round(events[-1]['end_s'] * RATE):
        raise ValueError('AAC ended before the final utterance')
    numbers, dialogue = [], []
    clips = destination / 'clips'
    clips.mkdir()
    previous = 0
    for row in events:
        start = row.get('start_sample_24k', round(row['start_s'] * RATE))
        end = row.get('end_sample_24k', round(row['end_s'] * RATE))
        if not isinstance(start, int) or not isinstance(end, int) or not previous <= start < end <= frames:
            raise ValueError(f'Invalid utterance interval:{row["id"]}')
        previous = end
        cut = clips / f'{row["id"]}.wav'
        with wave.open(str(cut), 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(RATE)
            stream.writeframes(pcm[start*2:end*2])
        original_kind = row.get('kind', '')
        is_result = row['id'].startswith('N')
        record = {'id': row['id'], 'path': cut.relative_to(destination).as_posix(),
                  'sha256': digest(cut), 'duration_s': (end-start)/RATE,
                  'sample_frames_24k': end-start, 'spoken_text': row['text'], 'text': row['text'],
                  'kind': original_kind, 'index': row.get('index'),
                  'production_start_s': start/RATE, 'production_end_s': end/RATE,
                  'cut_from': 'finished-AAC-decoded-PCM', 'channel': channel}
        if is_result:
            value = row.get('value', row.get('decimal_value', row.get('number')))
            if value is None:
                n = int(row['id'][1:])
                values = [0, 1]
                for _ in range(39):
                    values.append(values[-2]+values[-1])
                value = values[n]
            record['number'] = value
            record['value'] = value
            numbers.append(record)
        else:
            dialogue.append(record)
    if len(numbers) != 41 or len(dialogue) != 63:
        raise ValueError('Expected41result utterances and63other utterances')
    manifest = {'schema_version': 1, 'measurement_status': 'measured',
                'kind': 'finished-fibonacci-AAC-isolated-clips',
                'source_video': {'path': str(video), 'sha256': digest(video)},
                'source_timeline': {'path': str(timeline), 'sha256': digest(timeline)},
                'decoded_audio': {'path': decoded.name, 'sha256': digest(decoded),
                                  'sample_rate_hz': RATE, 'channels': 1, 'sample_frames': frames},
                'channel': channel, 'numbers': numbers, 'dialogue': dialogue,
                'method': 'Decode finishedAAC with priming honored; select one original stereo channel and resample24k; exact measured sample cuts. No denoise, speech repair, time stretch or lexical context.',
                'pronunciation_approved': False}
    (destination/'measurements.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'clips': len(events), 'channel': channel, 'manifest': str(destination/'measurements.json')}))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--channel', choices=('left', 'right'), default='left')
    args = parser.parse_args()
    extract(args.video, args.timeline, args.out_dir, args.ffmpeg, args.channel)
