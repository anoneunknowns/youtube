import hashlib,json,wave
from pathlib import Path

work=Path(__file__).parent
out=Path('D:/codex_projects/youtube/output/four-base-counting-001-v002-to-200')
plan=json.loads((out/'timeline.json').read_text(encoding='utf-8'))
event=next(e for e in plan['events'] if e['id']=='N164')
start,end=round(event['start_s']*48000),round(event['end_s']*48000)
records=[]
for name,source in [('N164-final-pns-on.wav','aac-stereo.s16le'),('N164-diagnostic-pns-off.wav','diagnostic-pns-0.s16le'),('N164-reference-master.wav','master-gained-stereo.s16le')]:
    with (work/source).open('rb') as stream:
        stream.seek(start*4)
        pcm=stream.read((end-start)*4)
    with wave.open(str(work/name),'wb') as stream:
        stream.setparams((2,2,48000,0,'NONE','not compressed'))
        stream.writeframes(pcm)
    records.append({'path':name,'sha256':hashlib.sha256((work/name).read_bytes()).hexdigest(),'bytes':(work/name).stat().st_size,'frames':end-start,'source_raw':source})
(work/'N164-diagnostic-clips.json').write_text(json.dumps({'method':'Sample-exact cuts of the already-decoded full streams; no second lossy encode.','event':event,'clips':records},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
path=work/'independent-audio-audit-resolved.json'
report=json.loads(path.read_text(encoding='utf-8'))
report['audible_event_boundary_checks']=216
report['speech_utterances']=215
report['raw_asr_numeric_spelling_warnings_only']=2
report['diagnostic_clips']='N164-diagnostic-clips.json'
path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(records))
