"""New independent closeout inputs; never changes accepted media or speech."""
from pathlib import Path
import array
import hashlib
import json
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[5]
QA = Path(__file__).resolve().parent
OUT = ROOT/'output/fibonacci-quality-closeout-20261112-01'
EPISODE = ROOT/'output/fibonacci-counting-001-v002'
VIDEO = EPISODE/'paspla-studio-fibonacci-numbers-0-to-102334155-1080p.mp4'
TIMELINE = EPISODE/'timeline.json'
plan = json.loads(TIMELINE.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2); stream.write('\n')


dest = OUT/'new-final-left-guarded'
dest.mkdir(exist_ok=False)
decoded = dest/'decoded-left-48k.wav'
subprocess.run([str(ROOT/'.venv/bin/ffmpeg'), '-v', 'error', '-nostdin', '-i', str(VIDEO),
                '-map', '0:a:0', '-af', 'pan=mono|c0=c0', '-ar', '48000', '-c:a', 'pcm_s16le', str(decoded)], check=True)
with wave.open(str(decoded)) as stream:
    frames = stream.getnframes(); pcm = stream.readframes(frames)
numbers, dialogue = [], []
for index, event in enumerate(plan['voice_events']):
    previous = plan['voice_events'][index-1]['end_s'] if index else 0
    following = plan['voice_events'][index+1]['start_s'] if index+1<len(plan['voice_events']) else frames/48000
    before = min(.08, (event['start_s']-previous)/2)
    after = min(.08, (following-event['end_s'])/2)
    start, end = round((event['start_s']-before)*48000), round((event['end_s']+after)*48000)
    path = dest/(event['id']+'.wav')
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((1, 2, 48000, end-start, 'NONE', 'not compressed')); stream.writeframes(pcm[start*2:end*2])
    row = {'id': event['id'], 'index': event['index'], 'path': path.name, 'sha256': sha(path),
           'spoken_text': event['text'], 'duration_s': (end-start)/48000,
           'speech_offset_s': event['start_s']-start/48000, 'excerpt_start_s': start/48000,
           'excerpt_end_s': end/48000, 'guard_before_s': before, 'guard_after_s': after}
    if event['id'].startswith('N'):
        n = event['index']; a,b = 0,1
        for _ in range(n): a,b=b,a+b
        row['number'] = a; numbers.append(row)
    else:
        dialogue.append(row)
save(dest/'measurements.json', {'schema_version': 1, 'measurement_status': 'measured',
                               'kind': 'new-finished-v002-AAC-closeout-silence-guarded-left104',
                               'source_video': {'path': VIDEO.relative_to(ROOT).as_posix(), 'sha256': sha(VIDEO)},
                               'source_timeline': {'path': TIMELINE.relative_to(ROOT).as_posix(), 'sha256': sha(TIMELINE)},
                               'method': 'New actual MP4 decode,80ms silence guards clamped to half speech gaps; no neighboring spoken word, no expected-text prompt.',
                               'numbers': numbers, 'dialogue': dialogue})

takes_path = OUT/'candidates-v001/takes.json'
takes = json.loads(takes_path.read_text())
candidate_rows = []
for row in takes:
    candidate_rows.append({'id': row['id'], 'number': row['number'], 'spoken_text': row['canonical_text'],
                           'path': Path(row['path']).relative_to(OUT).as_posix(), 'sha256': row['sha256'],
                           'duration_s': row['duration_s'], 'generation_text': row['text']})
save(OUT/'candidate-measurements.json', {'schema_version': 1, 'measurement_status': 'measured',
                                      'numbers': candidate_rows, 'dialogue': [],
                                      'kind': 'new-full-single-word-candidates-not-adopted',
                                      'generation': {'voice':'af_heart','speed':.98,'dtype':'fp32'},
                                      'adoption_status':'unreviewed-comparison-only'})

phones = {row['id']: row for row in json.loads((EPISODE/'audio-final-qa/phonemes-left.json').read_text())['results']}
events = {row['id']: row for row in plan['voice_events']}
landmarks = {'T008a': [('eleven',47,52),('one stays',53,59),('one ten',65,70),('moves left',71,78)],
             'T008b': [('carried ten',3,10),('joins',11,14),('two tens',40,45),('one one',48,53)],
             'T013a': [('thirteen',10,14),('write three',15,20),('carry one ten',24,33),('tens including carry',36,54)],
             'T013b': [('write three tens',0,9),('carry one hundred',13,26)],
             'T018b': [('fourteen',18,22),('eighteen tens',31,38),('fifteen hundreds',42,55)]}
result = []
for ident, sections in landmarks.items():
    for text, first, last in sections:
        tokens = phones[ident]['tokens'][first:last+1]
        result.append({'id': ident,'phrase':text,'event_start_s':events[ident]['start_s'],
                       'local_start_s':tokens[0]['start_s'],'local_end_s':tokens[-1]['end_s'],
                       'global_start_s':events[ident]['start_s']+tokens[0]['start_s'],
                       'global_end_s':events[ident]['start_s']+tokens[-1]['end_s'], 'tokens': tokens})
save(QA/'carry-voice-landmarks.json', {'kind':'independently-read-existing-fresh-CTC-phrase-landmarks',
                                     'source_phonemes_sha256':sha(EPISODE/'audio-final-qa/phonemes-left.json'),
                                     'timeline_sha256':sha(TIMELINE), 'timing_resolution_s':.02,
                                     'scope':'Existing finished-MP4 CTC evidence, independently segmented now; no new inference claimed for this mapping.', 'results':result})
print('Prepared104new guarded clips,6new full-word candidates,17carry phrase landmarks')
