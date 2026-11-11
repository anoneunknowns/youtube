import array,hashlib,importlib.util,json,subprocess,sys,wave
from pathlib import Path
ROOT=Path('D:/codex_projects/youtube');OUT=ROOT/'output/odd-counting-001-v002/audio-final-qa'
sys.path.insert(0,str(ROOT/'tools'))
from verify_terminal_tails import frame_metrics
spec=importlib.util.spec_from_file_location('lpc',ROOT/'output/even-counting-001-v001/speech/acoustic_formants.py')
lpc=importlib.util.module_from_spec(spec);spec.loader.exec_module(lpc)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
mp=OUT/'final-aac-manifest.json';manifest=json.loads(mp.read_text(encoding='utf-8'));entries={r['id']:r for r in manifest['dialogue']}
ctcp=OUT/'fresh-phonemes.json';phon=json.loads(ctcp.read_text(encoding='utf-8'));phones={r['id']:r for r in phon['results']};assert phon['source_manifest_sha256']==sha(mp)
signals={}
def signal(identity):
    if identity not in signals:
        row=entries[identity];assert sha(row['path'])==row['sha256']
        with wave.open(row['path'],'rb') as w:rate=w.getframerate();raw=array.array('h',w.readframes(w.getnframes()))
        signals[identity]=([v/32768 for v in raw],rate)
    return signals[identity]
heads=[]
for n in range(201,300,2):
    identity=f'N{n:03d}';r=entries[identity];p=phones[identity];tokens=p['tokens'][:3]
    ok=len(tokens)==3 and tokens[0]['token']=='t' and tokens[1]['token'] in ('u','uː') and tokens[2]['token']=='h'
    values,rate=signal(identity);offset=r['event_offset_in_clip_s'];frames=[]
    for tick in range(17):
        center=round((tick*.01+offset)*rate);half=round(.01*rate)
        frames.append({'event_relative_time_s':tick*.01,**frame_metrics(values[max(0,center-half):center+half],rate)})
    heads.append({'id':identity,'source_sha256':r['sha256'],'first_ctc_tokens':tokens,'prefix_complete':ok,'frames':frames})
boundaries=[]
for identity,start,end in [('N219',.36,.56),('N259',.34,.56),('N279',.82,.96)]:
    row=entries[identity];values,rate=signal(identity);offset=row['event_offset_in_clip_s'];frames=[]
    for tick in range(round(start*100),round(end*100)+1):
        center=round((tick*.01+offset)*rate);half=round(.01*rate)
        frames.append({'event_relative_time_s':tick*.01,**frame_metrics(values[max(0,center-half):center+half],rate)})
    boundaries.append({'id':identity,'source_sha256':row['sha256'],'frames':frames})
formants=[]
for identity,start,end in [('N241',.92,1.14),('N251',.9,1.14)]:
    row=entries[identity];offset=row['event_offset_in_clip_s'];raw=subprocess.check_output(['ffmpeg','-v','error','-i',row['path'],'-ar','12000','-f','f32le','pipe:1']);values=array.array('f',raw);frames=[]
    for center in range(round((start+offset)*12000),round((end+offset)*12000)+1,120):
        fs=lpc.formants(values[max(0,center-240):center+240],12000)
        frames.append({'event_relative_time_s':center/12000-offset,'formants_hz_bw':[[round(x,1),round(y,1)] for x,y in fs]})
    formants.append({'id':identity,'source_sha256':row['sha256'],'frames':frames})
report={'schema_version':1,'kind':'isolated-acoustic-analysis','source_manifest_sha256':sha(mp),
   'fresh_ctc':{'path':str(ctcp),'sha256':sha(ctcp)},
   'method':'Actual delivery AAC-derived48k left channel with80ms guards preserved,20ms frames10ms hop compensating event offsets; fresh50 two-hundred heads and3 candidate transition regions. Diagnostic LPC12k/40ms Hamming/LPC14/preemphasis.97/bandwidth<450Hz for two final-one nuclei. All measurements from actual v002 delivery, not source review.',
   'new_two_hundred_onset_clips':50,'new_onset_ctc_prefixes_complete':sum(r['prefix_complete'] for r in heads),
   'onset_prefix_flags':[r['id'] for r in heads if not r['prefix_complete']],
   'onsets':heads,'boundaries':boundaries,'formants':formants}
with (OUT/'extended-number-acoustics.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({'actual_aac_new_onsets':len(heads),'prefix_complete':report['new_onset_ctc_prefixes_complete'],'flags':report['onset_prefix_flags']}))
