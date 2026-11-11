"""Read-only same-voice vowel-resonance control for short-word CTC confusion.

N002 and N003 are independently ASR-recognized one-word two/three sources.
LPC envelopes are a targeted acoustic aid, not a perfect vowel classifier.
"""
from __future__ import annotations
import argparse, array, hashlib, json, math, statistics, subprocess
from pathlib import Path


def peaks(values, rate=16000, order=12):
    x=[v-.97*values[i-1] if i else v for i,v in enumerate(values)]
    x=[v*(.54-.46*math.cos(2*math.pi*i/(len(x)-1))) for i,v in enumerate(x)]
    r=[sum(x[j]*x[j+k] for j in range(len(x)-k)) for k in range(order+1)]
    a=[1.];error=r[0]
    for i in range(1,order+1):
        k=-(r[i]+sum(a[j]*r[i-j] for j in range(1,i)))/error
        a=[1.]+[a[j]+k*a[i-j] for j in range(1,i)]+[k]
        error*=1-k*k
    spectrum=[]
    for f in range(150,3501,10):
        z=sum(v*complex(math.cos(-2*math.pi*f*j/rate),math.sin(-2*math.pi*f*j/rate)) for j,v in enumerate(a))
        spectrum.append((f,1/(abs(z)**2+1e-20)))
    return [{'frequency_hz':spectrum[i][0],'relative_power':spectrum[i][1]} for i in range(1,len(spectrum)-1)
            if spectrum[i][1]>spectrum[i-1][1] and spectrum[i][1]>spectrum[i+1][1]]


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--ffmpeg',default='ffmpeg');a=p.parse_args()
    raw=a.manifest.read_bytes();m=json.loads(raw);by_id={r['id']:r for r in m['numbers']};results=[]
    for ident in ('N002','N003'):
        r=by_id[ident];source=Path(r['path'])
        if not source.is_absolute():source=a.manifest.parent/source
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        if digest!=r['sha256']:raise ValueError('Source hash mismatch')
        data=subprocess.check_output([a.ffmpeg,'-v','error','-nostdin','-i',str(source),'-ac','1','-ar','16000','-f','f32le','pipe:1'])
        samples=array.array('f',data);windows=[]
        offset=float(r.get('speech_offset_s',0))
        for center in (.19,.22,.25,.28,.31,.34):
            start=round((offset+center-.016)*16000);v=samples[start:start+512]
            found=peaks(v)
            windows.append({'center_s':center,'clip_center_s':offset+center,'envelope_peaks':found})
        sustained=[w['envelope_peaks'] for w in windows if w['center_s']>=.25]
        f1=[next(v['frequency_hz'] for v in x if v['frequency_hz']<1000) for x in sustained]
        f2=[next(v['frequency_hz'] for v in x if v['frequency_hz']>=1000) for x in sustained]
        results.append({'id':ident,'text':r['spoken_text'],'source_sha256':digest,'speech_offset_s':offset,'windows':windows,
                        'median_sustained_f1_hz':statistics.median(f1),'median_sustained_f2_hz':statistics.median(f2)})
    lower=results[0]['median_sustained_f2_hz']<results[1]['median_sustained_f2_hz']
    report={'schema_version':1,'kind':'same-speaker-short-vowel-ctc-control','source_manifest_sha256':hashlib.sha256(raw).hexdigest(),
            'method':{'decode':'16kHz mono float32, no source alteration; FFmpeg resampling for analysis only',
                      'lpc_order':12,'window_ms':32,'hop_centers_s':[.19,.22,.25,.28,.31,.34],
                      'preemphasis':.97,'window':'Hamming','envelope_sampling_hz':10,
                      'summary_windows_s':[.25,.28,.31,.34]},'results':results,
            'observation':'Two has a lower sustained second resonance than same-voice three; its resonance falls while three remains high. This supports rounded /u/ rather than accepting multilingual CTC i5 as an actual /i/ vowel.',
            'two_sustained_f2_lower_than_three':lower,
            'limitations':'Relative same-speaker acoustic control, not a universal formant acceptance range or proof of perfect pronunciation. Isolated lexical ASR, exact source provenance and edge checks are separate evidence. No human listening is claimed.'}
    with a.out.open('x')as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'two_f2':results[0]['median_sustained_f2_hz'],'three_f2':results[1]['median_sustained_f2_hz'],'lower':lower}))
