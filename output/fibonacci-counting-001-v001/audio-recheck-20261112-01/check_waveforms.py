"""Fresh read-only finished-media audio and subtitle checks for this recheck."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.verify_prime_video import audio_checks
from tools.build_prime_episode import probe_loudness, srt_time

OUT = ROOT / 'output/fibonacci-counting-001-v001'
QA = Path(__file__).resolve().parent
VIDEO = OUT / 'paspla-studio-fibonacci-numbers-0-to-102334155-1080p.mp4'
FFMPEG = str(ROOT / '.venv/bin/ffmpeg')
plan = json.loads((OUT / 'timeline.json').read_text())
script = {r['id']: r for r in json.loads((ROOT / 'design/fibonacci-counting-v1/narration.json').read_text())}

def save(name, data):
    with (QA / name).open('x') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')

with tempfile.TemporaryDirectory(prefix='waveform-work-', dir=QA) as temporary:
    result = audio_checks(plan, plan['voice_events'], VIDEO, OUT / 'master.wav', FFMPEG,
                          Path(temporary), QA / 'guarded-clips')
result['scope'] = 'Fresh decode and original-source/master/finishedAAC comparisons for all104utterances, both stereo channels, guarded silent interiors and newly extracted80ms-context48kleft clips. No human listening claim.'
result['checked_at_utc'] = datetime.now(timezone.utc).isoformat()
result['video_sha256'] = hashlib.sha256(VIDEO.read_bytes()).hexdigest()
save('waveform-review.json', result)
print('waveforms', [(r['kind'], r['minimum_correlation']) for r in result['tracks']], flush=True)
levels = probe_loudness(FFMPEG, VIDEO)
save('fresh-levels.json', {'kind':'fresh-final-AAC-loudness-and-truepeak-analysis',
                         'video_sha256':result['video_sha256'], 'probe':levels,
                         'passed':abs(float(levels['input_i'])+16)<=1 and float(levels['input_tp'])<=-1.5,
                         'method':'Read input_i/input_tp of the unmodified finishedAAC; normalized filter output is discarded.'})
print('levels', levels['input_i'], levels['input_tp'], flush=True)
caption_results = []
for name in ('english-captions.srt','subtitles.srt'):
    path=OUT/name
    blocks=path.read_text().replace('\r\n','\n').strip().split('\n\n')
    if len(blocks)!=104:
        raise ValueError('Caption count differs from104')
    cues=[]
    for index,(block,event) in enumerate(zip(blocks,plan['voice_events'],strict=True),1):
        lines=block.splitlines()
        expected=f'{srt_time(event["start_s"])} --> {srt_time(event["end_s"])}'
        passed=(len(lines)==3 and lines[0]==str(index) and lines[1]==expected
                and lines[2]==event['text']==script[event['id']]['text'])
        if not passed:
            raise ValueError(f'Caption mismatch {name}/{event["id"]}')
        cues.append({'id':event['id'],'number':index,'timing':lines[1],'text':lines[2],'passed':True})
    caption_results.append({'path':path.relative_to(ROOT).as_posix(),
                            'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                            'cues':cues,'passed':True})
save('subtitle-sync-review.json', {'kind':'fresh-caption-event-and-authoring-sync',
                                  'passed':True,'cues_per_caption_file':104,'files':caption_results,
                                  'speech_timing_basis':'Original-to-master-to-finishedAAC waveform correlation for each exact scheduled utterance; subtitle stamps are the nearest millisecond of that measured interval.'})
print('caption sync104x2PASS', flush=True)
