"""Fresh targeted vowel and level-transition measurements; no approvals imported."""
from pathlib import Path
import array
import hashlib
import json
import math
import statistics
import subprocess
import sys
import wave

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.review_prime_vowels import peaks
QA=Path(__file__).resolve().parent
OUT=QA.parent
FF=str(ROOT/'.venv/bin/ffmpeg')

def save(name,data):
 with (QA/name).open('x') as stream:
  json.dump(data,stream,ensure_ascii=False,indent=2);stream.write('\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def decode(path,rate=16000):
 raw=subprocess.check_output([FF,'-v','error','-i',str(path),'-ac','1','-ar',str(rate),'-f','f64le','pipe:1'])
 return array.array('d',raw)
def lpc(path,centers):
 values=decode(path);out=[]
 for center in centers:
  start=round((center-.016)*16000);p=peaks(values[start:start+512]);out.append({'center_s':center,'f1_hz':next(x['frequency_hz'] for x in p if x['frequency_hz']<1000),'f2_hz':next(x['frequency_hz'] for x in p if x['frequency_hz']>=1000),'peaks':p})
 return out

controls=[]
for channel in ['left','right']:
 mp=QA/channel/'measurements.json';m=json.loads(mp.read_text());by={r['id']:r for r in m['numbers']};two_three=[]
 for ident,expected_value in [('N003',2),('N004',3)]:
  row=by[ident];assert row['number']==expected_value
  windows=lpc(mp.parent/row['path'],[.19,.22,.25,.28,.31,.34]);two_three.append({'id':ident,'sha256':row['sha256'],'windows':windows,'median_f1_hz':statistics.median(w['f1_hz'] for w in windows[2:]),'median_f2_hz':statistics.median(w['f2_hz'] for w in windows[2:])})
 controls.append({'channel':channel,'manifest_sha256':sha(mp),'results':two_three,'two_f2_lower_than_three':two_three[0]['median_f2_hz']<two_three[1]['median_f2_hz']})
source_manifest=OUT/'speech/measurements.json';source=json.loads(source_manifest.read_text());eight=next(r for r in source['numbers'] if r['id']=='N006');centers=[.09,.12,.15,.18,.21,.24,.27];reference=lpc(source_manifest.parent/eight['path'],centers)
eight_comparison=[]
for channel in ['left','right']:
 mp=QA/channel/'measurements.json';row=next(r for r in json.loads(mp.read_text())['numbers'] if r['id']=='N006');windows=lpc(mp.parent/row['path'],centers);paired=[{'center_s':a['center_s'],'delta_f1_hz':b['f1_hz']-a['f1_hz'],'delta_f2_hz':b['f2_hz']-a['f2_hz']} for a,b in zip(reference,windows)]
 eight_comparison.append({'channel':channel,'final_clip_sha256':row['sha256'],'windows':windows,'paired_frequency_differences':paired})
save('vowel-controls.json',{'kind':'new-independent-targeted-LPC-measurements','method':'Analysis-only16kHzdecode,32msHamming window,preemphasis.97,LPCorder12,spectrum10Hz. Same-speaker two/three relative control and original-vs-finished eight trajectory; no lexical context used for recognition.','two_three_controls':controls,'eight_original_source_sha256':eight['sha256'],'eight_original_windows':reference,'eight_final_comparisons':eight_comparison,'limitation':'Relative signal support, not universal vowel-classification thresholds or a human listening claim.'})
print('freshLPCtwo/three',[(r['channel'],[(x['id'],x['median_f2_hz']) for x in r['results']]) for r in controls],flush=True)
print('freshLPCeight maxF2difference',max(abs(d['delta_f2_hz']) for r in eight_comparison for d in r['paired_frequency_differences']),flush=True)

plan=json.loads((OUT/'timeline.json').read_text());events=plan['voice_events'];index=next(i for i,e in enumerate(events) if e['id']=='T013b');near=events[index-1:index+2];level_rows=[]
for channel in ['left','right']:
 mp=QA/channel/'measurements.json';m=json.loads(mp.read_text());by={r['id']:r for r in m['numbers']+m['dialogue']}
 for event in near:
  row=by[event['id']]
  with wave.open(str(mp.parent/row['path'])) as w:rate=w.getframerate();v=array.array('h',w.readframes(w.getnframes()))
  rms=20*math.log10(math.sqrt(sum(x*x for x in v)/len(v))/32768);peak=20*math.log10(max(abs(x) for x in v)/32768)
  level_rows.append({'channel':channel,'id':row['id'],'rms_dbfs':rms,'sample_peak_dbfs':peak,'sha256':row['sha256'],'first_sample':v[0],'last_sample':v[-1]})
focus=events[index];original=decode(ROOT/focus['source_path'],48000)
with wave.open(str(OUT/'master.wav')) as w:
 w.setpos(focus['start_sample_24k']*2);raw=w.readframes(focus['sample_frames_24k']*2)
master=[int.from_bytes(raw[i:i+3],'little',signed=True)/8388608 for i in range(0,len(raw),6)]
assert len(original)==len(master)
window=round(.2*48000);gains=[]
for start in range(0,len(original)-window+1,window):
 x=original[start:start+window];y=master[start:start+window];energy=sum(v*v for v in x)
 if energy/window<10**(-40/10):continue
 gain=sum(a*b for a,b in zip(x,y))/energy
 gains.append({'start_s':start/48000,'end_s':(start+window)/48000,'least_squares_gain_db':20*math.log10(gain)})
differences=[]
for channel in ['left','right']:
 by={r['id']:r for r in level_rows if r['channel']==channel};differences.append({'channel':channel,'previous_to_T013b_rms_change_db':by['T013b']['rms_dbfs']-by[near[0]['id']]['rms_dbfs'],'T013b_to_next_rms_change_db':by[near[2]['id']]['rms_dbfs']-by['T013b']['rms_dbfs']})
save('level-transition-review.json',{'kind':'fresh-adjacent-utterance-level-and-whole-scalar-review','ids':[e['id'] for e in near],'finished_AAC_levels':level_rows,'differences':differences,'T013b_declared_extra_constant_scalar_db':focus.get('aac_codec_calibration_gain_db'),'source_to_master_active200ms_gain_windows':gains,'within_T013b_gain_span_db':max(r['least_squares_gain_db'] for r in gains)-min(r['least_squares_gain_db'] for r in gains),'basis':'RMS is measured over the nominal extracted utterance including its original edge guards. Source-to-master least-squares amplitude is checked in active200mswindows; quiet windows below-40dBFSare excluded. Original/encoded phonetic and signal checks are separate.','interpretation':'A small adjacent-utterance RMS difference is reported rather than forcing equal loudness. A constant whole-utterance scalar does not introduce an internal level step; source-to-master windows directly test this.'})
print('adjacentRMS',differences,'withinfocusgainspan',max(r['least_squares_gain_db'] for r in gains)-min(r['least_squares_gain_db'] for r in gains),flush=True)
