import array, hashlib, json, wave
from pathlib import Path
ROOT=Path('D:/codex_projects/youtube');OUT=ROOT/'design/odd-counting-v1/production-qa/v002-recheck-20261111/audio';WORK=Path('D:/temp/odd-recheck-20261111/audio')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
m=json.loads((OUT/'fresh-aac-manifest.json').read_text());rows=[];destination=WORK/'controls';destination.mkdir(exist_ok=False)
with wave.open(str(WORK/'fresh-decoded-aac.wav'),'rb') as stream:
    rate=stream.getframerate()
    for row in m['numbers']:
        if row['id'] not in ('N005','N109'):continue
        start,stop=[round(v*rate) for v in row['video_event_window_s']];stream.setpos(start);values=array.array('h',stream.readframes(stop-start))[::2]
        path=destination/(row['id']+'-EXACT.wav')
        with wave.open(str(path),'wb') as target:target.setparams((1,2,rate,0,'NONE','not compressed'));target.writeframes(values.tobytes())
        rows.append({'id':row['id']+'-EXACT','spoken_text':row['spoken_text'],'path':str(path),'sha256':sha(path),'duration_s':len(values)/rate,'video_event_window_s':row['video_event_window_s']})
with (OUT/'exact-event-manifest.json').open('x',encoding='utf-8') as stream:json.dump({'schema_version':1,'measurement_status':'measured','numbers':[],'dialogue':rows,'origin':m['origin']},stream,indent=2);stream.write('\n')
source=(ROOT/'output/odd-counting-001-v002/audio-review-tools/N109_diagnostic_grid.py').read_text(encoding='utf-8')
source=source.replace("ROOT/'output/odd-counting-001-v002/audio-final-qa'", "ROOT/'design/odd-counting-v1/production-qa/v002-recheck-20261111/audio'")
source=source.replace("final-aac-manifest.json", "fresh-aac-manifest.json")
source=source.replace("manifest['dialogue'] if", "manifest['numbers']+manifest['dialogue'] if")
source=source.replace("OUT/'exact-event-controls-v002/N109-EXACT.wav'", "Path('D:/temp/odd-recheck-20261111/audio/controls/N109-EXACT.wav')")
source=source.replace("destination=OUT/'N109-diagnostic-grid'", "destination=Path('D:/temp/odd-recheck-20261111/audio/N109-diagnostic-grid')")
(OUT/'recheck_n109_diagnostic_grid.py').write_text(source,encoding='utf-8',newline='\n')
print({'controls':len(rows)})
