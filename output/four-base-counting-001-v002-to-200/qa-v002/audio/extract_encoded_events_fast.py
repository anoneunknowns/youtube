"""Decode the final AAC once, then split exact measured event intervals for ASR."""
import argparse
import array
import hashlib
import json
from pathlib import Path
import subprocess
import wave


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', required=True, type=Path)
    parser.add_argument('--timeline', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--decoded-audio', type=Path)
    parser.add_argument('--ffmpeg', default='D:/dev/FFmpeg/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe')
    args = parser.parse_args()
    plan = json.loads(args.timeline.read_text(encoding='utf-8'))
    args.output_dir.mkdir(parents=True, exist_ok=False)
    clip_dir = args.output_dir / 'encoded-events'
    clip_dir.mkdir()
    decoded = args.decoded_audio or (args.output_dir / 'aac-decoded-full.wav')
    decoded.parent.mkdir(parents=True, exist_ok=True)
    command = [args.ffmpeg, '-v', 'error', '-xerror', '-nostdin', '-n', '-i', str(args.video),
               '-map', '0:a:0', '-ar', '48000', '-ac', '1', '-c:a', 'pcm_s16le', str(decoded)]
    process = subprocess.run(command, capture_output=True, text=True, check=True)
    assert not process.stderr.strip(), process.stderr
    manifest = {'schema_version': 1, 'measurement_status': 'measured',
                'source_video': str(args.video.resolve()), 'source_video_sha256': digest(args.video),
                'source_timeline': str(args.timeline.resolve()), 'source_timeline_sha256': digest(args.timeline),
                'numbers': [], 'dialogue': []}
    index = []
    peaks = []
    with wave.open(str(decoded), 'rb') as source:
        assert source.getnchannels() == 1 and source.getsampwidth() == 2 and source.getframerate() == 48000
        assert abs(source.getnframes() - round(plan['duration_s'] * 48000)) <= 2048
        decoded_frames = source.getnframes()
        for event in plan['events']:
            if event['type'] == 'sfx':
                continue
            start = round(event['start_s'] * 48000)
            end = round(event['end_s'] * 48000)
            assert 0 <= start < end <= source.getnframes()
            source.setpos(start)
            pcm = source.readframes(end - start)
            assert len(pcm) == (end - start) * 2
            path = clip_dir / (event['id'] + '.wav')
            assert not path.exists()
            with wave.open(str(path), 'wb') as target:
                target.setnchannels(1)
                target.setsampwidth(2)
                target.setframerate(48000)
                target.writeframes(pcm)
            row = {'id': event['id'], 'path': str(path.resolve()), 'spoken_text': event['text'],
                   'duration_s': (end - start) / 48000, 'sha256': digest(path)}
            if event['type'] == 'number_voice' and event['phase'] == 'count' and event['decimal_value'] > 0:
                row['number'] = event['decimal_value']
                manifest['numbers'].append(row)
            else:
                manifest['dialogue'].append(row)
            index.append({**row, 'type': event['type'], 'phase': event['phase'],
                          'decimal_value': event.get('decimal_value'), 'start_s': start / 48000, 'end_s': end / 48000})
            samples = array.array('h', pcm)
            peak = max(map(abs, samples))
            assert peak > 0
            peaks.append({'id': event['id'], 'samples': len(samples), 'peak_pcm16': peak,
                          'clipped_samples': sum(abs(value) >= 32767 for value in samples)})
    clipping = {'passed': all(row['clipped_samples'] == 0 for row in peaks), 'events': len(peaks),
                'clipped_samples': sum(row['clipped_samples'] for row in peaks),
                'maximum_peak_pcm16': max(row['peak_pcm16'] for row in peaks),
                'all_event_clips_nonempty': True, 'clips': peaks}
    assert clipping['passed']
    extraction = {'status': 'PASS', 'ffmpeg_command': command, 'ffmpeg_stderr': process.stderr,
                  'source_video_sha256': manifest['source_video_sha256'],
                  'source_timeline_sha256': manifest['source_timeline_sha256'],
                  'decoded_audio_frames': decoded_frames, 'decoded_audio_sha256': digest(decoded),
                  'decoded_audio_path': str(decoded.resolve()),
                  'extracted_speech_events': len(index), 'expected_text_used_as_recognition_prompt': False,
                  'extractor_sha256': digest(Path(__file__))}
    for name, value in (('encoded-events-manifest.json', manifest), ('encoded-events-index.json', index),
                        ('encoded-event-clipping.json', clipping), ('extraction.json', extraction)):
        with (args.output_dir / name).open('x', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
    print(json.dumps({'status': 'PASS', 'extracted_events': len(index), 'numbers': len(manifest['numbers']),
                      'dialogue': len(manifest['dialogue']), 'clipped_samples': clipping['clipped_samples'],
                      'output_dir': str(args.output_dir)}))


if __name__ == '__main__':
    main()
