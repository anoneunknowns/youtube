import array,hashlib,importlib.util,json,subprocess,sys,wave
from pathlib import Path
ROOT=Path('D:/codex_projects/youtube');OUT=ROOT/'output/odd-counting-001-v002/audio-final-qa';WORK=Path('D:/temp/odd-audio-production/final-aac-v002')
sys.path.insert(0,str(ROOT/'tools'))
from verify_terminal_tails import frame_metrics
spec=importlib.util.spec_from_file_location('lpc_diagnostic',ROOT/'output/even-counting-001-v001/speech/acoustic_formants.py')
lpc=importlib.util.module_from_spec(spec);spec.loader.exec_module(lpc)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(name,obj):
    with (OUT/name).open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n')
mp=OUT/'final-aac-manifest.json';manifest=json.loads(mp.read_text(encoding='utf-8'));rows={r['id']:r for r in manifest['dialogue']}
clips=OUT/'exact-event-controls-v002';clips.mkdir(exist_ok=False)
with wave.open(str(WORK/'decoded-final-aac-stereo.wav'),'rb') as w:
    rate=w.getframerate();r=rows['N109'];a,b=[round(t*rate) for t in r['video_event_window_s']]
    w.setpos(a);data=array.array('h',w.readframes(b-a))[::2];path=clips/'N109-EXACT.wav'
    with wave.open(str(path),'wb') as target:
        target.setparams((1,2,rate,0,'NONE','not compressed'));target.writeframes(data.tobytes())
control={'id':'N109-EXACT','number':109,'spoken_text':r['spoken_text'],'path':str(path),'sha256':sha(path),'sample_frames':len(data),'duration_s':len(data)/rate,'video_event_window_s':r['video_event_window_s']}
save('exact-event-control-manifest-v002.json',{'schema_version':1,'measurement_status':'measured','numbers':[],'dialogue':[control],
     'origin':{'video':manifest['origin']['video'],'full_manifest':{'path':str(mp),'sha256':sha(mp)},'method':'Same final AAC decode, exact planned event bounds without exterior80ms silence. Left channel unchanged.'}})
formants=[]
for identity,start,end in [('T009',1.30,1.60),('N021',.38,.61),('N101',.72,1.02)]:
    row=rows[identity];offset=row['event_offset_in_clip_s'];raw=subprocess.check_output(['ffmpeg','-v','error','-i',row['path'],'-ar','12000','-f','f32le','pipe:1']);values=array.array('f',raw);frames=[]
    for center in range(round((start+offset)*12000),round((end+offset)*12000)+1,120):
        fs=lpc.formants(values[max(0,center-240):center+240],12000)
        frames.append({'clip_time_s':center/12000,'event_relative_time_s':center/12000-offset,'formants_hz_bw':[[round(x,1),round(y,1)] for x,y in fs]})
    formants.append({'id':identity,'source_sha256':row['sha256'],'frames':frames})
save('supplementary-formants.json',{'schema_version':1,'kind':'isolated-acoustic-analysis','source_manifest_sha256':sha(mp),
   'method':'Fresh actual AAC-derived12k PCM,40ms Hamming/10ms hop,LPC14/preemphasis.97/bandwidth<450Hz. Targeted new final-AAC CTC vowel/r-color labels, diagnostic only.','results':formants})
metrics=[]
for identity in ('N005','N109'):
    row=rows[identity]
    with wave.open(row['path'],'rb') as w:
        rate=w.getframerate();data=array.array('h',w.readframes(w.getnframes()))
    values=[v/32768 for v in data];frames=[]
    for tick in range(round((row['duration_s']-.35)*100),round(row['duration_s']*100)-1):
        center=round(tick*.01*rate);half=round(.01*rate)
        frames.append({'clip_time_s':tick*.01,**frame_metrics(values[max(0,center-half):center+half],rate)})
    metrics.append({'id':identity,'source_sha256':row['sha256'],'frames':frames})
save('supplementary-terminal-boundaries.json',{'schema_version':1,'kind':'isolated-acoustic-analysis','source_manifest_sha256':sha(mp),
   'method':'Actual AAC-derived unchanged left48k,20ms frames10ms hop. Inspect CTC end consonant label oversegmentation without treating recognition as acoustic truth.','results':metrics})
print(json.dumps({'exact_control':'N109','supplementary_formants':[r['id'] for r in formants]}))
