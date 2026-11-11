"""Check the actual final AAC payload/PCM and all subtitle event bindings."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
QA = Path(__file__).resolve().parent
OUT = QA.parent
sys.path.insert(0, str(ROOT))
from tools.build_prime_episode import srt_time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)}


def save(name, data):
    with (QA / name).open('x') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


video = OUT / 'paspla-studio-fibonacci-numbers-0-to-102334155-1080p.mp4'
timeline = OUT / 'timeline.json'
receipt = OUT / 'audio-build/aac-acceptance.json'
acceptance = json.loads(receipt.read_text())
encoded = ROOT / acceptance['encoded_aac']['path']
assert sha(encoded) == acceptance['encoded_aac']['sha256']
ffmpeg = str(ROOT / '.venv/bin/ffmpeg')


def signal(job):
    kind, path = job
    command = [ffmpeg, '-v', 'error', '-nostdin', '-i', str(path), '-map', '0:a:0']
    command += ['-c:a', 'copy', '-f', 'adts', 'pipe:1'] if kind == 'ADTS' else ['-ar', '48000', '-ac', '2', '-c:a', 'pcm_s24le', '-f', 's24le', 'pipe:1']
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    digest = hashlib.sha256(); size = 0
    while block := process.stdout.read(1024 * 1024):
        digest.update(block); size += len(block)
    error = process.stderr.read().decode()
    if process.wait():
        raise RuntimeError(error)
    return {'kind': kind, 'input': ref(path), 'sha256': digest.hexdigest(), 'bytes': size,
            'command': command, 'exit_code': 0}


with ThreadPoolExecutor(max_workers=4) as pool:
    comparisons = list(pool.map(signal, [('ADTS', encoded), ('ADTS', video), ('PCM48k24bitStereo', encoded), ('PCM48k24bitStereo', video)]))
assert comparisons[0]['sha256'] == comparisons[1]['sha256'] and comparisons[0]['bytes'] == comparisons[1]['bytes']
assert comparisons[2]['sha256'] == comparisons[3]['sha256'] and comparisons[2]['bytes'] == comparisons[3]['bytes']
save('aac-copy-proof.json', {'kind': 'new-final-MP4-to-accepted-M4A-signal-copy-proof', 'passed': True,
                            'checked_at_utc': datetime.now(timezone.utc).isoformat(),
                            'video': ref(video), 'timeline': ref(timeline), 'accepted_aac_receipt': ref(receipt),
                            'AAC_payload_identical': True, 'decoded_PCM_identical': True,
                            'method': 'Fresh ffmpeg extraction of both actual containers: compare ADTS bytes/hash and decoded48k24bitstereo PCM bytes/hash. No source inference reused to stand in for final-MP4 recognition.',
                            'results': comparisons})

plan = json.loads(timeline.read_text())
script = {row['id']: row for row in json.loads((ROOT / 'design/fibonacci-counting-v1/narration.json').read_text())}
files = []
for filename in ('english-captions.srt', 'subtitles.srt'):
    path = OUT / filename
    blocks = path.read_text().replace('\r\n', '\n').strip().split('\n\n')
    assert len(blocks) == 104
    cues = []
    for index, (block, event) in enumerate(zip(blocks, plan['voice_events'], strict=True), 1):
        lines = block.splitlines()
        expected = f'{srt_time(event["start_s"])} --> {srt_time(event["end_s"])}'
        assert len(lines) == 3 and lines[0] == str(index) and lines[1] == expected
        assert lines[2] == event['text'] == script[event['id']]['text']
        cues.append({'id': event['id'], 'timing': lines[1], 'text': lines[2], 'passed': True})
    files.append({**ref(path), 'cues': cues, 'passed': True})
save('subtitle-sync-review.json', {'kind': 'new-final-subtitle-text-and-measured-event-sync', 'passed': True,
                                  'video': ref(video), 'timeline': ref(timeline), 'files': files,
                                  'cues_per_file': 104,
                                  'method': 'Both caption files use the104canonical texts in measured event order; start/end rounded to nearest millisecond. Actual audio position is separately checked against these measured events by the independent waveform verifier.'})
print('Fresh AAC payload/decoded PCM copy proof and104x2 subtitle binding PASS')
