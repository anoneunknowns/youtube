"""New local signal observations for the remaining internal CTC differences."""
from pathlib import Path
import array
import cmath
import hashlib
import json
import math
import wave

ROOT=Path(__file__).resolve().parents[5]
QA=Path(__file__).resolve().parent
OUT=ROOT/'output/fibonacci-quality-closeout-20261112-01'
mp=OUT/'new-final-left-guarded/measurements.json'
manifest=json.loads(mp.read_text());by={r['id']:r for r in manifest['numbers']+manifest['dialogue']}


def fft(x):
    if len(x)==1:return x
    a,b=fft(x[::2]),fft(x[1::2]);c=[cmath.exp(-2j*math.pi*i/len(x))*v for i,v in enumerate(b)]
    return [v+w for v,w in zip(a,c)]+[v-w for v,w in zip(a,c)]


def feature(path,start,end):
    with wave.open(str(path)) as stream:
        rate=stream.getframerate();stream.setpos(round(start*rate));samples=array.array('h',stream.readframes(round((end-start)*rate)))
    x=[v/32768 for v in samples];size=1<<(len(x)-1).bit_length()
    windowed=[v*(.5-.5*math.cos(2*math.pi*i/(len(x)-1))) for i,v in enumerate(x)]
    spectrum=fft(windowed+[0]*(size-len(x)));powers=[(i*rate/size,abs(v)**2) for i,v in enumerate(spectrum[:size//2+1])]
    band=[(f,p) for f,p in powers if 200<=f<=10000];total=sum(p for f,p in band)
    return {'rms_dbfs':20*math.log10(max(1e-12,math.sqrt(sum(v*v for v in x)/len(x)))),
            'centroid_200_to10000_hz':sum(f*p for f,p in band)/total,
            'energy_ratio_3000_to10000':sum(p for f,p in band if f>=3000)/total,
            'zero_crossing_fraction':sum((a>=0)!=(b>=0) for a,b in zip(x,x[1:]))/(len(x)-1)}


targets=[('I07','show-values boundary',.98,1.06),('I07','show vowel control',.88,.96),
         ('I07','values ae vowel control',1.10,1.18),('I07','later value v control',5.70,5.76),
         ('E025','six-hundred s/h connection',1.24,1.32),('E025','hundred vowel control',1.32,1.38),
         ('T013a','make final k before thirteen',.71,.78),
         ('E028','six onset s despite final CTC theta',4.48,4.54),
         ('E028','within-utterance thousand theta control',1.10,1.16),
         ('E039','seventeen onset s despite CTC omission',3.49,3.55),
         ('N024','three theta direct target',1.40,1.46)]
results=[]
for ident,role,start,end in targets:
    row=by[ident];path=mp.parent/row['path'];offset=row['speech_offset_s']
    results.append({'id':ident,'role':role,'nominal_local_start_s':start,'nominal_local_end_s':end,
                    'guard_offset_s':offset,'clip_sha256':row['sha256'],'features':feature(path,start+offset,end+offset)})
report={'kind':'new-local-internal-phone-difference-physical-observations',
        'manifest_sha256':hashlib.sha256(mp.read_bytes()).hexdigest(),'results':results,
        'method':'New fixed local windows of actual final AAC at48k, offset by measured silence guard.20Hz–10k spectral/envelope observations are diagnostic; a phoneme cannot be proven from a single spectral centroid. No surrounding numerical meaning enters these physical measurements.',
        'human_listening_claim':False}
with (QA/'internal-target-physical-observations.json').open('x') as stream:
    json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
print([(row['id'],row['role'],row['features']) for row in results])
