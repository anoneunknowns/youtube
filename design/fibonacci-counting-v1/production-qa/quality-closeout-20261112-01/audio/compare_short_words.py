"""New same-voice short-word/formant controls and whole-word alternatives."""
from pathlib import Path
import array
import hashlib
import json
import math
import statistics
import subprocess
import sys
import wave

ROOT=Path(__file__).resolve().parents[5]
QA=Path(__file__).resolve().parent
OUT=ROOT/'output/fibonacci-quality-closeout-20261112-01'
EPISODE=ROOT/'output/fibonacci-counting-001-v002'
sys.path.insert(0,str(ROOT))
from tools.review_prime_vowels import peaks


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def decode(path,rate):
    raw=subprocess.check_output([str(ROOT/'.venv/bin/ffmpeg'),'-v','error','-i',str(path),'-ac','1','-ar',str(rate),'-f','f64le','pipe:1'])
    return array.array('d',raw)


def metrics(path,centers):
    samples=decode(path,16000);rows=[]
    for center in centers:
        start=round((center-.016)*16000);data=samples[max(0,start):max(0,start)+512]
        p=peaks(data);low=next((v['frequency_hz'] for v in p if v['frequency_hz']<1000),None)
        high=next((v['frequency_hz'] for v in p if v['frequency_hz']>=1000),None)
        rows.append({'center_s':center,'F1_hz':low,'F2_hz':high})
    # Independent20ms onset frames: periodicity and raw waveform envelope only.
    samples=decode(path,8000);onset=[]
    for millisecond in range(0,161,10):
        first=round(millisecond*8);data=samples[first:first+160]
        power=sum(value*value for value in data)/max(1,len(data))
        correlations=[]
        for lag in range(20,81):
            a,b=data[:-lag],data[lag:];den=math.sqrt(sum(v*v for v in a)*sum(v*v for v in b))
            correlations.append(sum(x*y for x,y in zip(a,b))/max(1e-30,den))
        onset.append({'start_s':millisecond/1000,'rms_dbfs':20*math.log10(max(1e-12,math.sqrt(power))),
                       'zero_crossing_fraction':sum((a>=0)!=(b>=0) for a,b in zip(data,data[1:]))/max(1,len(data)-1),
                       'maximum_periodicity_100_to400Hz':max(correlations)})
    with wave.open(str(path)) as stream:
        rate=stream.getframerate();pcm=array.array('h',stream.readframes(stream.getnframes()))
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path),'duration_s':len(pcm)/rate,
            'clipped_samples':sum(abs(value)>=32767 for value in pcm),
            'vowel_windows':rows,'late_vowel_F2_median_hz':statistics.median(row['F2_hz'] for row in rows[-3:] if row['F2_hz'] is not None),
            'onset20ms_frames':onset}


manifest_path=EPISODE/'speech/measurements.json';manifest=read(manifest_path)
sources={row['id']:manifest_path.parent/row['path'] for row in manifest['numbers']+manifest['dialogue']}
results=[]
for ident,centers,role in [('N003',[.19,.22,.25,.28,.31,.34],'current isolated two'),
                         ('N004',[.25,.28,.31,.34],'same-voice front-vowel three control'),
                         ('E005',[.14,.17,.20],'same-voice two in formula; independent CTC t u'),
                         ('E004',[.64,.67,.70],'same-voice two in formula; independent CTC t u'),
                         ('N006',[.09,.12,.15,.18,.21,.24,.27],'current isolated eight'),
                         ('N005',[.14,.17,.20,.23,.26],'same-voice aI in five control'),
                         ('E008',[.06,.09,.12],'same-voice eI in formula-initial eight'),
                         ('E007',[.72,.75,.78],'same-voice eI in formula-medial eight')]:
    results.append({'id':ident,'role':role,**metrics(sources[ident],centers)})
for batch in ('candidates-v001','candidates-v002','candidates-v003'):
    for row in read(OUT/batch/'takes.json'):
        centers=[.19,.22,.25,.28,.31,.34] if row['number']==2 else [.09,.12,.15,.18,.21,.24,.27]
        results.append({'id':row['id'],'role':'new whole-word comparison candidate, not adopted','generation_text':row['text'],
                        'explicit_phonemes':row.get('phonemes'),**metrics(Path(row['path']),centers)})
report={'kind':'new-isolated-short-word-and-same-speaker-formant-onset-controls',
        'method':'Fresh16kHz32ms LPC-order12 formant estimates at fixed centers and8kHz20ms onset periodicity/ZCR/energy frames. Relative same-speaker controls; not universal vowel thresholds or a human perceived-naturalness judgement.',
        'results':results,'human_listening_claim':False,
        'new_full_word_candidates_generated':13,'candidate_adoption_granted':False}
with (QA/'short-word-physical-controls.json').open('x') as stream:
    json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
print([(row['id'],row['late_vowel_F2_median_hz']) for row in results])
