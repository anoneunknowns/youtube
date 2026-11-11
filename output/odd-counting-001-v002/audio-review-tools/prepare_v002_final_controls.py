"""No-padding control from the same final decoded AAC, for a new CTC label warning."""
import array
import hashlib
import json
from pathlib import Path
import wave

ROOT=Path('D:/codex_projects/youtube');OUT=ROOT/'output/odd-counting-001-v002/audio-final-qa'
WORK=Path('D:/temp/odd-audio-production/final-aac-v002')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
mp=OUT/'final-aac-manifest.json';manifest=json.loads(mp.read_text(encoding='utf-8'))
clips=OUT/'exact-event-controls';clips.mkdir(exist_ok=False)
rows=[]
with wave.open(str(WORK/'decoded-final-aac-stereo.wav'),'rb') as w:
    rate=w.getframerate()
    for row in manifest['dialogue']:
        if row['id']!='N005':continue
        a,b=[round(t*rate) for t in row['video_event_window_s']]
        w.setpos(a);raw=array.array('h',w.readframes(b-a));data=raw[::2]
        path=clips/(row['id']+'-EXACT.wav')
        with wave.open(str(path),'wb') as target:
            target.setparams((1,2,rate,0,'NONE','not compressed'));target.writeframes(data.tobytes())
        rows.append({'id':row['id']+'-EXACT','number':row['number'],'spoken_text':row['spoken_text'],
                     'path':str(path),'sha256':sha(path),'sample_frames':len(data),'duration_s':len(data)/rate,
                     'video_event_window_s':row['video_event_window_s'],'diagnostic_question':'Does removing only exterior silence change the unexpected terminal z label?','audio_altered':False})
out={'schema_version':1,'measurement_status':'measured','numbers':[],'dialogue':rows,
     'origin':{'video':manifest['origin']['video'],'full_manifest':{'path':str(mp),'sha256':sha(mp)},
               'method':'Same actual final AAC decode, exact planned event bounds without exterior80ms silence. Left channel remains unchanged; no gain, stretch or reference audio.'}}
with (OUT/'exact-event-control-manifest.json').open('x',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({'controls':len(rows)}))
