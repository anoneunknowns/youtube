"""Fresh acoustic evidence from the actual AAC-derived, guard-retaining clips."""
import array
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import wave

ROOT=Path('D:/codex_projects/youtube');OUT=ROOT/'output/odd-counting-001-v002/audio-final-qa'
sys.path.insert(0,str(ROOT/'tools'))
from verify_terminal_tails import frame_metrics
spec=importlib.util.spec_from_file_location('lpc_diagnostic',ROOT/'output/even-counting-001-v001/speech/acoustic_formants.py')
lpc=importlib.util.module_from_spec(spec);spec.loader.exec_module(lpc)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(name,data):
    with (OUT/name).open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
mp=OUT/'final-aac-manifest.json';manifest=json.loads(mp.read_text(encoding='utf-8'))
rows=manifest['dialogue'];entries={r['id']:r for r in rows};signals={};edges=[]
for row in rows:
    assert sha(row['path'])==row['sha256']
    with wave.open(row['path'],'rb') as w:
        rate=w.getframerate();data=array.array('h',w.readframes(w.getnframes()))
    values=[v/32768 for v in data];signals[row['id']]=(values,rate)
    active=[i for i,v in enumerate(data) if abs(v)>104]
    assert active,row['id']
    first=round(row['event_offset_in_clip_s']*rate)
    last=first+round((row['video_event_window_s'][1]-row['video_event_window_s'][0])*rate)
    edges.append({'id':row['id'],'source_sha256':row['sha256'],'head_margin_s':active[0]/rate,
                  'tail_margin_s':(len(data)-active[-1]-1)/rate,
                  'first20ms_peak_pcm16':max(map(abs,data[:round(rate*.02)]),default=0),
                  'last20ms_peak_pcm16':max(map(abs,data[-round(rate*.02):]),default=0),
                  'nominal_event_start_step_pcm16':abs(data[first]-data[first-1]),
                  'nominal_event_end_step_pcm16':abs(data[last]-data[last-1]),
                  'clipped_samples':sum(abs(v)>=32767 for v in data)})
save('edge-signal-review.json',{'schema_version':1,'kind':'isolated-acoustic-analysis','source_manifest_sha256':sha(mp),
    'method':'Unaltered actual AAC left48k with80ms exterior guards. Activity threshold104/32768 about-50dBFS; first/last20ms peaks and nominal event boundary adjacent-sample steps. Cut/click screen, not semantic approval.',
    'summary':{'clips':len(edges),'min_head_margin_s':min(r['head_margin_s'] for r in edges),'min_tail_margin_s':min(r['tail_margin_s'] for r in edges),
      'max_first20ms_peak_pcm16':max(r['first20ms_peak_pcm16'] for r in edges),'max_last20ms_peak_pcm16':max(r['last20ms_peak_pcm16'] for r in edges),
      'max_nominal_boundary_step_pcm16':max(max(r['nominal_event_start_step_pcm16'],r['nominal_event_end_step_pcm16']) for r in edges),
      'clipped_samples':sum(r['clipped_samples'] for r in edges)},'results':edges})
heads=('three','thirteen','thirty','four','five','fifteen','forty','fifty','six','seven','sixty','seventy','from','thanks')
screen=[]
for row in rows:
    if not row['spoken_text'].lower().startswith(heads):continue
    values,rate=signals[row['id']];frames=[]
    for tick in range(37):
        center=round(tick*.01*rate);half=round(.01*rate)
        if center+half>len(values):break
        frames.append({'time_s':tick*.01,**frame_metrics(values[max(0,center-half):center+half],rate)})
    voiced=[r for r in frames if r['rms_dbfs']>-45 and r['low_ratio_under_1khz']>=.6 and r['periodicity']>=.6]
    fric=[r for r in frames if r['rms_dbfs']>-45 and r['high_ratio_2khz_up']>=.35 and r['periodicity']<.4]
    weak=[r for r in frames if r['rms_dbfs']>-65 and r['high_ratio_2khz_up']>=.35 and r['periodicity']<.4]
    first=fric[0]['time_s'] if fric else None;weakfirst=weak[0]['time_s'] if weak else None
    before=[r for r in voiced if first is not None and r['time_s']<first]
    screen.append({'id':row['id'],'source_sha256':row['sha256'],'frames':frames,'first_strong_frication_s':first,'first_weak_frication_s':weakfirst,
                   'voiced_prefix_s':len(before)*.01,'voiced_prefix_times_s':[r['time_s'] for r in before],
                   'prefix_max_rms_dbfs':max((r['rms_dbfs'] for r in before),default=None)})
flags=[{k:r[k] for k in ('id','voiced_prefix_s','voiced_prefix_times_s','prefix_max_rms_dbfs')} for r in screen if r['voiced_prefix_s']>=.03]
save('initial-fricative-screen.json',{'schema_version':1,'kind':'isolated-acoustic-analysis','source_manifest_sha256':sha(mp),
   'method':'Actual AAC-derived left48k.20ms windows/10ms hop first360ms, including80ms exterior guards. Strong voiced RMS>-45 lowband>=.6 periodicity>=.6 before first aperiodic frication RMS>-45 highband>=.35 periodicity<.4. Weak frication threshold-65 also recorded. Flags require individual review.',
   'screened':len(screen),'candidates':flags,'results':screen})
formants=[]
for identity,start,end in [('I04',1.17,1.44),('I05',2.29,2.56),('N001',.08,.26),('N151',1.0,1.24),('N161',1.04,1.27),('N171',1.12,1.3)]:
    row=entries[identity];offset=row['event_offset_in_clip_s']
    raw=subprocess.check_output(['ffmpeg','-v','error','-i',row['path'],'-ar','12000','-f','f32le','pipe:1'])
    values=array.array('f',raw);frames=[]
    for center in range(round((start+offset)*12000),round((end+offset)*12000)+1,120):
        fs=lpc.formants(values[max(0,center-240):center+240],12000)
        frames.append({'clip_time_s':center/12000,'event_relative_time_s':center/12000-offset,'formants_hz_bw':[[round(x,1),round(y,1)] for x,y in fs]})
    formants.append({'id':identity,'source_sha256':row['sha256'],'frames':frames})
save('targeted-formants.json',{'schema_version':1,'kind':'isolated-acoustic-analysis','source_manifest_sha256':sha(mp),
   'method':'Actual AAC-derived clips resampled12k;40ms Hamming/10ms hop,LPC14,0.97preemphasis,bandwidth<450Hz. New measurements of delivery, not inherited source approval. Diagnostic only.','results':formants})
boundaries=[]
for identity,start,end in [('N065',.02,.13),('N173',.6,.72),('I05',1.8,1.98),('N159',.43,.68),('N163',.43,.66)]:
    row=entries[identity];offset=row['event_offset_in_clip_s'];values,rate=signals[identity];frames=[]
    for tick in range(round(start*100),round(end*100)+1):
        center=round((tick*.01+offset)*rate);half=round(.01*rate)
        frames.append({'event_relative_time_s':tick*.01,**frame_metrics(values[max(0,center-half):center+half],rate)})
    boundaries.append({'id':identity,'source_sha256':row['sha256'],'frames':frames})
save('targeted-boundaries.json',{'schema_version':1,'kind':'isolated-acoustic-analysis','source_manifest_sha256':sha(mp),
   'method':'Fresh actual AAC-derived20ms frames/10ms hop, event-relative positions compensate80ms extraction guards. No expected lexical prompting.','results':boundaries})
print(json.dumps({'fricative_screened':len(screen),'candidates':flags,'edges_clips':len(edges)}))
