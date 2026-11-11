from array import array
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,math
from pathlib import Path
import subprocess

ROOT=Path('D:/codex_projects/youtube')
OUT=ROOT/'output/four-base-counting-001-v002-to-200'
WORK=Path(__file__).parent
FFMPEG='D:/dev/FFmpeg/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe'
plan=json.loads((OUT/'timeline.json').read_text(encoding='utf-8'))
event=next(e for e in plan['events'] if e['id']=='N164')
help_result=subprocess.run([FFMPEG,'-hide_banner','-h','encoder=aac'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=True)
(WORK/'aac-encoder-help.txt').write_bytes(help_result.stdout)

def candidate(pns):
    target=WORK/f'diagnostic-pns-{pns}.m4a'
    encode=[FFMPEG,'-hide_banner','-nostdin','-v','error','-xerror','-n','-i',str(OUT/'master.wav'),'-af','volume=0.8dB:precision=double','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-aac_pns',str(pns),str(target)]
    done=subprocess.run(encode,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (WORK/f'pns-{pns}-encode.stderr.txt').write_bytes(done.stderr)
    if done.returncode or done.stderr:raise RuntimeError(done.stderr.decode())
    raw=WORK/f'diagnostic-pns-{pns}.s16le'
    decode=[FFMPEG,'-hide_banner','-nostdin','-v','error','-xerror','-n','-i',str(target),'-ar','48000','-ac','2','-c:a','pcm_s16le','-f','s16le',str(raw)]
    done=subprocess.run(decode,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (WORK/f'pns-{pns}-decode.stderr.txt').write_bytes(done.stderr)
    if done.returncode or done.stderr:raise RuntimeError(done.stderr.decode())
    return {'pns':pns,'encode':encode,'decode':decode,'path':str(raw),'file_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}

with ThreadPoolExecutor(max_workers=2) as pool:
    cases=list(pool.map(candidate,[1,0]))
def load(path):
    a=array('h')
    with Path(path).open('rb') as f:a.fromfile(f,Path(path).stat().st_size//2)
    return a

original=load(WORK/'aac-stereo.s16le')
begin,end=round(event['start_s']*48000)*2,round(event['end_s']*48000)*2
orig_event=original[begin:end]
left,right=orig_event[::2],orig_event[1::2]
diff=[a-b for a,b in zip(left,right)]
peak_index=max(range(len(diff)),key=lambda i:abs(diff[i]))
printed=[]
for entry in cases:
    raw=load(entry['path'])
    frames=min(len(raw),len(original))//2
    ls,rs=raw[::2],raw[1::2]
    event_l,event_r=raw[begin:end:2],raw[begin+1:end:2]
    ll=sum(x*x for x in event_l);rr=sum(x*x for x in event_r);lr=sum(x*y for x,y in zip(event_l,event_r))
    source_length=len(original)
    entry.update(decoded_frames=len(raw)//2,
      master_frames=source_length//2,
      whole_channel_max_difference_pcm16=max(abs(a-b) for a,b in zip(ls,rs)),
      n164_channel_max_difference_pcm16=max(abs(a-b) for a,b in zip(event_l,event_r)),
      n164_channel_correlation=lr/math.sqrt(ll*rr),
      original_prefix_exact_samples=sum(a==b for a,b in zip(raw[:source_length],original)),
      original_samples_compared=min(len(raw),source_length),
      original_prefix_max_difference=max(abs(a-b) for a,b in zip(raw[:source_length],original)),
      extra_padding_frames=max(0,(len(raw)-source_length)//2),
    )
    printed.append({k:v for k,v in entry.items() if k not in ['encode','decode']})

# Localize large differences; the question is whether there is a time shift or a brief high-frequency coding component.
bins=[]
for offset in range(0,len(diff),240):
    chunk=diff[offset:offset+240]
    rms=math.sqrt(sum(x*x for x in chunk)/len(chunk))
    bins.append({'relative_start_s':offset/48000,'side_rms_pcm16':rms/2,'difference_peak_pcm16':max(map(abs,chunk))})
report={'status':'diagnostic-complete','hypothesis':'AAC perceptual noise substitution is enabled by default and can make separately decoded channels differ for a dual-mono source.',
    'encoder_help_pns_lines':[line for line in help_result.stdout.decode().splitlines() if 'aac_pns' in line],
    'original_event':event,'n164_max_diff_relative_s':peak_index/48000,'n164_max_diff_absolute_s':event['start_s']+peak_index/48000,
    'n164_diff_samples_above_1000':sum(abs(x)>1000 for x in diff),'n164_diff_samples_above_10000':sum(abs(x)>10000 for x in diff),
    'n164_duration_s':len(diff)/48000,'largest_5ms_difference_bins':sorted(bins,key=lambda r:r['side_rms_pcm16'],reverse=True)[:10],
    'candidates':cases,
    'original_media_modified':False}
(WORK/'aac-pns-causal-diagnostic.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'pns_help':report['encoder_help_pns_lines'],'peak_relative_s':report['n164_max_diff_relative_s'],'above1000':report['n164_diff_samples_above_1000'],'above10000':report['n164_diff_samples_above_10000'],'cases':printed}))
