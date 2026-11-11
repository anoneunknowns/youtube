"""New final-MP4 stereo recognition inputs and inference, never an approval.

Call only after the renderer closes the final MP4. All outputs remain in this
dedicated QA directory; existing cuts/reports are refused by the underlying tools.
"""
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
from tools.extract_fibonacci_final_audio import extract

VIDEO = OUT / 'paspla-studio-fibonacci-numbers-0-to-102334155-1080p.mp4'
TIMELINE = OUT / 'timeline.json'
FFMPEG = str(ROOT / '.venv/bin/ffmpeg')
started = datetime.now(timezone.utc).isoformat()


def ref(path):
    return {'path': path.relative_to(ROOT).as_posix(),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def execute(job):
    name, command = job
    with (QA / (name + '.log')).open('x') as stream:
        subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True)
    print('completed ' + name, flush=True)
    return {'name': name, 'command': command, 'log': ref(QA / (name + '.log'))}


baseline = {'video': ref(VIDEO), 'visual_timeline': ref(TIMELINE),
            'audio_source_timeline': ref(OUT / 'audio-build/timeline.json'),
            'audio_master': ref(OUT / 'audio-build/master.wav'),
            'accepted_AAC_receipt': ref(OUT / 'audio-build/aac-acceptance.json')}
with (QA / 'baseline.json').open('x') as stream:
    json.dump(baseline, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
for channel in ('left', 'right'):
    extract(VIDEO, TIMELINE, QA / channel, FFMPEG, channel)
print('newly extracted104clips per channel', flush=True)
jobs = []
for channel in ('left', 'right'):
    manifest = str(QA / channel / 'measurements.json')
    jobs.append((f'asr-{channel}', ['node', str(ROOT / 'tools/verify_fibonacci_speech.mjs'),
                 '--manifest', manifest, '--out', str(QA / f'asr-{channel}.json'),
                 '--cache', str(ROOT / '.model-cache'), '--ffmpeg', FFMPEG]))
    jobs.append((f'ctc-{channel}', ['node', str(ROOT / 'tools/portable_verify_phonemes.mjs'),
                 '--manifest', manifest, '--out', str(QA / f'phonemes-{channel}.json'),
                 '--cache', str(ROOT / '.model-cache'), '--ffmpeg', FFMPEG]))
with ThreadPoolExecutor(max_workers=4) as pool:
    runs = list(pool.map(execute, jobs))
jobs = []
for channel in ('left', 'right'):
    jobs.append((f'acoustics-{channel}', [sys.executable, str(ROOT / 'tools/review_fibonacci_acoustics.py'),
                 '--manifest', str(QA / channel / 'measurements.json'),
                 '--phonemes', str(QA / f'phonemes-{channel}.json'),
                 '--out', str(QA / f'acoustics-{channel}.json')]))
with ThreadPoolExecutor(max_workers=2) as pool:
    runs.extend(pool.map(execute, jobs))
if baseline['video'] != ref(VIDEO) or baseline['visual_timeline'] != ref(TIMELINE):
    raise ValueError('Final media changed during inference; preserve results as an attempt')
record = {'kind': 'new-fibonacci-v002-final-stereo-inference-execution',
          'started_at_utc': started, 'finished_at_utc': datetime.now(timezone.utc).isoformat(),
          'baseline': baseline, 'runs': runs, 'fresh_main_ASR_inputs': 208,
          'fresh_main_CTC_inputs': 208, 'fresh_acoustic_inputs': 208,
          'past_approvals_imported': False, 'approval_granted_by_this_runner': False,
          'human_listening_claim': False}
with (QA / 'execution-record.json').open('x') as stream:
    json.dump(record, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print('Fresh analyses ready for individual review; no automatic pronunciation approval.', flush=True)
