import array,hashlib,importlib.util,json,math,statistics,subprocess,sys,wave
from pathlib import Path
ROOT=Path('D:/codex_projects/youtube');OUT=ROOT/'output/odd-counting-001-v002/speech'
sys.path.insert(0,str(ROOT/'tools'))
from verify_terminal_tails import frame_metrics
spec=importlib.util.spec_from_file_location('lpc_diagnostic',ROOT/'output/even-counting-001-v001/speech/acoustic_formants.py')
lpc=importlib.util.module_from_spec(spec);spec.loader.exec_module(lpc)
manifest=json.loads((OUT/'initial-measurements-v001.json').read_text(encoding='utf-8'))
entries={r['id']:r for r in manifest['numbers']+manifest['dialogue']}
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(name,data):
    with (OUT/name).open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
signals={};edges=[]
for row in entries.values():
    with wave.open(str(row['path']),'rb') as f:
        rate=f.getframerate();raw=array.array('h',f.readframes(f.getnframes()))
    vals=[v/32768 for v in raw];signals[row['id']]=(vals,rate)
    active=[i for i,v in enumerate(raw) if abs(v)>104]
    edges.append({'id':row['id'],'source_sha256':row['sha256'],
                  'first_activity_s':active[0]/rate,'last_activity_s':active[-1]/rate,
                  'head_margin_s':active[0]/rate,'tail_margin_s':(len(raw)-active[-1]-1)/rate,
                  'edge_first_sample':raw[0],'edge_last_sample':raw[-1],
                  'max_abs_pcm16':max(map(abs,raw)), 'clipped_samples':sum(abs(v)>=32767 for v in raw)})
save('source-edge-review-v001.json',{'kind':'isolated-acoustic-analysis','source_manifest_sha256':sha(OUT/'initial-measurements-v001.json'),
 'method':'Each original monoPCM16/24k source read unchanged. Active threshold104/32768 about-50dBFS, first/last sample and clipping. Screening, not lexical approval.',
 'summary':{'clips':len(edges),'clipped_samples':sum(r['clipped_samples'] for r in edges),
  'minimum_active_head_margin_s':min(r['head_margin_s'] for r in edges),
  'minimum_active_tail_margin_s':min(r['tail_margin_s'] for r in edges),
  'max_edge_sample_abs':max(max(abs(r['edge_first_sample']),abs(r['edge_last_sample'])) for r in edges)},'results':edges})
formants=[]
for identity,start,end in [('I04',1.17,1.44),('I05',2.29,2.56),('N001',.08,.26),('N151',1.0,1.24),('N171',1.12,1.3)]:
    row=entries[identity]
    raw=subprocess.check_output(['ffmpeg','-v','error','-i',row['path'],'-ar','12000','-f','f32le','pipe:1'])
    vals=array.array('f',raw);frames=[]
    for center in range(round(start*12000),round(end*12000)+1,120):
        fs=lpc.formants(vals[max(0,center-240):center+240],12000)
        frames.append({'time_s':center/12000,'formants_hz_bw':[[round(x,1),round(y,1)] for x,y in fs]})
    formants.append({'id':identity,'source_sha256':row['sha256'],'region_s':[start,end],'frames':frames})
save('targeted-formants-v001.json',{'kind':'isolated-acoustic-analysis','method':'Fresh original source PCM resampled12k,40ms Hamming/10ms hop,LPC14/0.97preemphasis,bandwidth<450Hz. Diagnostic formants only; no hard articulation guarantee.','results':formants})
metrics=[]
for identity,start,end in [('N065',.02,.13),('N173',.6,.72),('I05',1.80,1.98),('N159',.43,.68),('N163',.43,.66)]:
    vals,rate=signals[identity];frames=[]
    for tick in range(round(start*100),round(end*100)+1):
        center=round(tick*.01*rate);half=round(.01*rate)
        frames.append({'time_s':tick*.01,**frame_metrics(vals[max(0,center-half):center+half],rate)})
    metrics.append({'id':identity,'source_sha256':entries[identity]['sha256'],'frames':frames})
save('targeted-boundaries-v001.json',{'kind':'isolated-acoustic-analysis','method':'Fresh unchanged source20ms windows/10ms hop. Inspect aperiodic s-label segmentation, nasal/glide transition and unstressed hundred region. No contextual-ASR approval.','results':metrics})
for r in formants:
    print(r['id'],[(f['time_s'],f['formants_hz_bw'][:4]) for f in r['frames'][::4]])
for r in metrics:
    print(r['id'],[(f['time_s'],round(f['rms_dbfs'],1),round(f['periodicity'],2),round(f['high_ratio_2khz_up'],2)) for f in r['frames']])
