"""Fresh final-MP4 target controls with silence-only 80ms guards."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[3]
QA = Path(__file__).resolve().parent
OUT = QA.parent
VIDEO = OUT / 'paspla-studio-fibonacci-numbers-0-to-102334155-1080p.mp4'
TIMELINE = OUT / 'timeline.json'
FFMPEG = ROOT / '.venv/bin/ffmpeg'
events = json.loads(TIMELINE.read_text())['voice_events']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def one(channel):
    dest = QA / ('guarded-' + channel)
    dest.mkdir(exist_ok=False)
    full = dest / 'decoded-48k.wav'
    subprocess.run([str(FFMPEG), '-v', 'error', '-nostdin', '-i', str(VIDEO),
                    '-map', '0:a:0', '-af', 'pan=mono|c0=c0' if channel == 'left' else 'pan=mono|c0=c1',
                    '-ar', '48000', '-c:a', 'pcm_s16le', str(full)], check=True)
    with wave.open(str(full)) as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (48000, 1, 2)
        pcm = wav.readframes(wav.getnframes())
    numbers = []
    for i, row in enumerate(events):
        if row['id'] not in ('N003', 'N006', 'N024'):
            continue
        before = min(.08, max(0, row['start_s'] - events[i-1]['end_s']) / 2) if i else .08
        after = min(.08, max(0, events[i+1]['start_s'] - row['end_s']) / 2)
        start, end = round((row['start_s']-before)*48000), round((row['end_s']+after)*48000)
        path = dest / (row['id'] + '.wav')
        with wave.open(str(path), 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(48000)
            wav.writeframes(pcm[start*2:end*2])
        numbers.append({'id': row['id'], 'index': row['index'], 'number': {'N003': 2, 'N006': 8, 'N024': 46368}[row['id']],
                        'path': path.name, 'sha256': sha(path), 'spoken_text': row['text'],
                        'duration_s': (end-start)/48000, 'speech_offset_s': row['start_s']-start/48000,
                        'guard_before_s': before, 'guard_after_s': after,
                        'excerpt_start_s': start/48000, 'excerpt_end_s': end/48000,
                        'cut_from': 'finished-AAC-decoded-PCM', 'channel': channel})
    manifest = {'schema_version': 1, 'measurement_status': 'measured',
                'kind': 'final-fibonacci-AAC-silence-guarded-target-control',
                'source_video': {'path': VIDEO.relative_to(ROOT).as_posix(), 'sha256': sha(VIDEO)},
                'source_timeline': {'path': TIMELINE.relative_to(ROOT).as_posix(), 'sha256': sha(TIMELINE)},
                'channel': channel, 'numbers': numbers, 'dialogue': [],
                'method': 'Decode finished AAC at48k; add at most80ms of actual neighboring silence, clamped to half of each gap. No neighboring spoken word, text prompt or speech alteration.'}
    path = dest / 'measurements.json'
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    for name, tool in [('phonemes', 'portable_verify_phonemes.mjs'), ('asr', 'verify_fibonacci_speech.mjs')]:
        with (dest / (name + '.log')).open('x') as log:
            subprocess.run(['node', str(ROOT/'tools'/tool), '--manifest', str(path), '--out', str(dest/(name+'.json')),
                            '--cache', str(ROOT/'.model-cache'), '--ffmpeg', str(FFMPEG)],
                           cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    return channel


with ThreadPoolExecutor(max_workers=2) as pool:
    for channel in pool.map(one, ('left', 'right')):
        print('Fresh silence-guarded final-AAC controls complete: ' + channel)
