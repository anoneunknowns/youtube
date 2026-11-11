"""Prespecified source/delivery x rate/padding controls, no production edits."""
import array,hashlib,json,math,subprocess,sys,wave
from pathlib import Path
ROOT=Path('D:/codex_projects/youtube');OUT=ROOT/'design/odd-counting-v1/production-qa/v002-recheck-20261111/audio'
sys.path.insert(0,str(ROOT/'tools'))
from verify_terminal_tails import fft,frame_metrics
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(name,x):
    with (OUT/name).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
mp=OUT/'fresh-aac-manifest.json';manifest=json.loads(mp.read_text(encoding='utf-8'));delivery=next(r for r in manifest['numbers']+manifest['dialogue'] if r['id']=='N109')
sm=ROOT/'output/odd-counting-001-v002/speech/measurements.json';source=next(r for r in json.loads(sm.read_text(encoding='utf-8'))['numbers'] if r['id']=='N109')
actual=Path('D:/temp/odd-recheck-20261111/audio/controls/N109-EXACT.wav');inputs={'source':Path(source['path']),'actual-aac':actual};destination=Path('D:/temp/odd-recheck-20261111/audio/N109-diagnostic-grid');destination.mkdir(exist_ok=False)
rows=[];floats={}
for label,path in inputs.items():
    for rate in (24000,48000):
        raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-ac','1','-ar',str(rate),'-f','s16le','pipe:1']);data=array.array('h',raw)
        for padding in (0,.08):
            name=f'{label}-{rate}-pad{round(padding*1000):03d}';target=destination/(name+'.wav');guard=round(padding*rate)
            signal=array.array('h',[0])*guard+data+array.array('h',[0])*guard
            with wave.open(str(target),'wb') as w:w.setparams((1,2,rate,0,'NONE','not compressed'));w.writeframes(signal.tobytes())
            rows.append({'id':name,'spoken_text':'one hundred nine','path':str(target),'sha256':sha(target),'duration_s':len(signal)/rate,'sample_frames':len(signal),
                         'diagnostic_source':label,'analysis_sample_rate_hz':rate,'exterior_silence_each_side_s':padding})
    raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-ac','1','-ar','16000','-f','f32le','pipe:1']);floats[label]=array.array('f',raw)
save('N109-diagnostic-grid-manifest.json',{'schema_version':1,'measurement_status':'measured','numbers':[],'dialogue':rows,
   'origin':{'video':manifest['origin']['video'],'source':{'path':source['path'],'sha256':source['sha256']},'actual_exact_event':{'path':str(actual),'sha256':sha(actual)},
             'method':'Prespecified2x2x2 grid: frozen adopted source and actual v002 AAC exact-event, analysis-only24k/48k PCM resampling, zero/80ms exterior silence. No audio-content trimming, gain matching, replacing production or selecting only favorable outcomes.'}})
a,b=floats['source'],floats['actual-aac'];n=min(len(a),len(b));begin=round(.8*16000);end=n;a=a[begin:end];b=b[begin:end]
ea=sum(x*x for x in a);eb=sum(x*x for x in b);dot=sum(x*y for x,y in zip(a,b));corr=dot/math.sqrt(ea*eb);gain=dot/ea
win=lambda x:[v*(.5-.5*math.cos(2*math.pi*i/(len(x)-1))) for i,v in enumerate(x)]
fa,_=fft(win(a));fb,_=fft(win(b));pa=[abs(z)**2 for z in fa];pb=[abs(z)**2 for z in fb];spec=sum(x*y for x,y in zip(pa,pb))/math.sqrt(sum(x*x for x in pa)*sum(y*y for y in pb))
frames=[]
for tick in range(80,112):
    c=round(tick*.01*16000);half=160;fr={'event_relative_time_s':tick*.01}
    for label,values in floats.items():
        if c+half<=len(values):fr[label]=frame_metrics(values[max(0,c-half):c+half],16000)
    frames.append(fr)
save('N109-local-terminal-waveform.json',{'schema_version':1,'kind':'isolated-acoustic-analysis','video':manifest['origin']['video'],
  'source_manifest_sha256':sha(mp),'source':{'path':source['path'],'sha256':source['sha256']},'actual_exact_event':{'path':str(actual),'sha256':sha(actual)},
  'method':'Original source and actual final AAC exact event independently resampled16k f32. Compare event-relative .8s through common end at zero lag, best uniform gain for residual only; Hamming-window normalized power-spectrum cosine. Frame metrics are fresh paired20ms windows/10ms hop. No recognition used for signal decisions.',
  'interval_s':[.8,(begin+n-begin)/16000],'local_correlation_zero_lag':corr,'best_uniform_gain':gain,'normalized_power_spectrum_cosine':spec,
  'normalized_residual_rms':math.sqrt(sum((y-gain*x)**2 for x,y in zip(a,b))/eb),'frames':frames})
print(json.dumps({'diagnostic_inputs':len(rows),'local_terminal_correlation':corr,'spectrum_cosine':spec}))
