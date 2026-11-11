import array,hashlib,importlib.util,json,subprocess,sys,wave
from pathlib import Path
ROOT=Path('D:/codex_projects/youtube');OUT=ROOT/'output/odd-counting-001-v002/speech'
sys.path.insert(0,str(ROOT/'tools'))
from verify_terminal_tails import frame_metrics
spec=importlib.util.spec_from_file_location('lpc',ROOT/'output/even-counting-001-v001/speech/acoustic_formants.py')
lpc=importlib.util.module_from_spec(spec);spec.loader.exec_module(lpc)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest=json.loads((OUT/'initial-measurements-v001.json').read_text(encoding='utf-8'));entries={r['id']:r for r in manifest['numbers']+manifest['dialogue']}
phon=json.loads((OUT/'isolated-phonemes-v001.json').read_text(encoding='utf-8'));ph={r['id']:r for r in phon['results']}
signals={}
def signal(identity):
    if identity not in signals:
        r=entries[identity];assert sha(r['path'])==r['sha256']
        with wave.open(r['path'],'rb') as w:rate=w.getframerate();raw=array.array('h',w.readframes(w.getnframes()))
        signals[identity]=([v/32768 for v in raw],rate)
    return signals[identity]
heads=[]
for n in range(201,300,2):
    identity=f'N{n:03d}';p=ph[identity];assert [t['token'] for t in p['tokens'][:3]]==['t','uː','h'],identity
    values,rate=signal(identity);frames=[]
    for tick in range(17):
        center=round(tick*.01*rate);half=round(.01*rate)
        frames.append({'time_s':tick*.01,**frame_metrics(values[max(0,center-half):center+half],rate)})
    heads.append({'id':identity,'source_sha256':entries[identity]['sha256'],'first_ctc_tokens':p['tokens'][:3],'head_frames':frames})
boundaries=[]
for identity,start,end in [('N219',.36,.56),('N259',.34,.56),('N279',.82,.96)]:
    values,rate=signal(identity);frames=[]
    for tick in range(round(start*100),round(end*100)+1):
        center=round(tick*.01*rate);half=round(.01*rate)
        frames.append({'time_s':tick*.01,**frame_metrics(values[max(0,center-half):center+half],rate)})
    boundaries.append({'id':identity,'source_sha256':entries[identity]['sha256'],'frames':frames})
formants=[]
for identity,start,end in [('N241',.92,1.14),('N251',.9,1.14)]:
    row=entries[identity];raw=subprocess.check_output(['ffmpeg','-v','error','-i',row['path'],'-ar','12000','-f','f32le','pipe:1']);values=array.array('f',raw);frames=[]
    for center in range(round(start*12000),round(end*12000)+1,120):
        fs=lpc.formants(values[max(0,center-240):center+240],12000)
        frames.append({'time_s':center/12000,'formants_hz_bw':[[round(x,1),round(y,1)] for x,y in fs]})
    formants.append({'id':identity,'source_sha256':row['sha256'],'frames':frames})
report={'schema_version':1,'kind':'isolated-acoustic-analysis','source_manifest_sha256':sha(OUT/'initial-measurements-v001.json'),
  'fresh_ctc':{'path':str(OUT/'isolated-phonemes-v001.json'),'sha256':sha(OUT/'isolated-phonemes-v001.json')},
  'method':'Fresh immutable24k source signals.20ms frames10ms hop for50 new two-hundred onsets and3 flagged transitions. LPC diagnostic12k/40ms Hamming/LPC14/.97preemphasis/bandwidth<450Hz for final-one vowel labels. No context ASR or imported approval.',
  'new_two_hundred_onset_clips':50,'new_onset_ctc_prefixes_complete':50,'onsets':heads,'boundaries':boundaries,'formants':formants}
with (OUT/'extended-number-acoustics-v001.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
for r in boundaries:print(r['id'],[(f['time_s'],round(f['rms_dbfs'],1),round(f['periodicity'],2),round(f['high_ratio_2khz_up'],2)) for f in r['frames'][::2]])
for r in formants:print(r['id'],[(f['time_s'],[v[0] for v in f['formants_hz_bw'][:4]]) for f in r['frames'][::4]])
print(json.dumps({'new_onsets':len(heads),'ctc_prefix_complete':50}))
