"""New all-utterance, both-channel source/master/final-AAC signal checks."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
QA = Path(__file__).resolve().parent
OUT = QA.parent
sys.path.insert(0, str(ROOT))
from tools.verify_prime_video import audio_checks

video = OUT / 'paspla-studio-fibonacci-numbers-0-to-102334155-1080p.mp4'
timeline = OUT / 'timeline.json'
plan = json.loads(timeline.read_text())
master = ROOT / plan['master_audio']['path']
with tempfile.TemporaryDirectory(prefix='new-stereo-waveforms-', dir=QA) as work:
    result = audio_checks(plan, plan['voice_events'], video, master, str(ROOT/'.venv/bin/ffmpeg'), Path(work))
result['kind'] = 'fresh-fibonacci-v002-stereo-source-master-final-AAC-waveform-review'
result['scope'] = 'New full signal decodes: all104 original-source utterances versus both master and actual finished-AAC stereo channels, zero-lag/correlation and guarded silent interiors. Separate ASR/CTC/pronunciation review; no human listening claim.'
result['video_sha256'] = hashlib.sha256(video.read_bytes()).hexdigest()
result['timeline_sha256'] = hashlib.sha256(timeline.read_bytes()).hexdigest()
result['checked_at_utc'] = datetime.now(timezone.utc).isoformat()
with (QA/'waveform-review.json').open('x') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
print([(row['kind'], row['minimum_correlation'], row['silence_intervals_checked'], row['maximum_silent_interior_peak_pcm16']) for row in result['tracks']])
