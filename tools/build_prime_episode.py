"""Build the prime lesson from hash-bound adopted speech; never retime speech."""
from __future__ import annotations
import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import wave

ROOT=Path(__file__).resolve().parents[1]
DESIGN=ROOT/'design/prime-counting-v1'
OUT=ROOT/'output/prime-counting-001-v001'
RATE=24000
FPS=30
VALUES=tuple(n for n in range(2,1000) if all(n%d for d in range(2,math.isqrt(n)+1)))
VIDEO_NAME='paspla-studio-prime-numbers-2-to-997-1080p.mp4'


def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def save_new(path,data):
    with Path(path).open('x',encoding='utf-8',newline='\n') as f:json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')

def resolve(path,base=ROOT):
    p=Path(path);return p if p.is_absolute() else base/p

def local(path):
    p=Path(path).resolve()
    return p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else str(p)

def samples(s):return round(s*RATE)

def accepted_sources(manifest_path,gate_path):
    measured,gate=read(manifest_path),read(gate_path)
    if measured.get('measurement_status')!='measured' or gate.get('accepted') is not True or gate.get('unresolved') or gate.get('summary',{}).get('unresolved',0):raise ValueError('Fully accepted measured speech required')
    binding=gate.get('inputs',{}).get('manifest',{})
    if binding.get('sha256')!=digest(manifest_path):raise ValueError('Speech gate is not bound to current measurements')
    checked=set()
    def verify_references(node):
        if isinstance(node,dict):
            if isinstance(node.get('path'),str) and isinstance(node.get('sha256'),str):
                source=resolve(node['path'])
                if not source.is_file():source=resolve(node['path'],gate_path.parent)
                key=(str(source.resolve()),node['sha256'])
                if key not in checked:
                    if not source.is_file() or digest(source)!=node['sha256']:raise ValueError(f'Acceptance evidence changed: {source}')
                    checked.add(key)
            for value in node.values():verify_references(value)
        elif isinstance(node,list):
            for value in node:verify_references(value)
    verify_references(gate)
    authored=read(DESIGN/'narration.json');expected={r['id']:r for r in authored}
    numbers=measured.get('numbers',[]);dialogue=measured.get('dialogue',[])
    if len(numbers)!=168 or sorted(r['number'] for r in numbers)!=list(VALUES) or len(dialogue)!=20:raise ValueError('Expected168 primes and20dialogue clips')
    result={}
    approvals=gate.get('results',[])
    for role,rows in [('number',numbers),('dialogue',dialogue)]:
        for row in rows:
            ident=row.get('id',f'N{row["number"]:03d}' if role=='number' else '')
            if ident in result or ident not in expected:raise ValueError(f'Unexpected or repeated clip {ident}')
            text=row.get('spoken_text',row.get('text'))
            if text!=expected[ident]['text']:raise ValueError(f'Authored text mismatch {ident}')
            path=resolve(row['path'],manifest_path.parent)
            if not path.exists():path=resolve(row['path'])
            if digest(path)!=row['sha256']:raise ValueError(f'Source changed {ident}')
            with wave.open(str(path),'rb') as w:
                if w.getnchannels()!=1 or w.getframerate()!=RATE or w.getsampwidth()!=2:raise ValueError(f'Expected24kmono16bit source {ident}')
                frames=w.getnframes()
            duration=frames/RATE
            if abs(duration-row['duration_s'])>1/RATE:raise ValueError(f'Incorrect measured duration {ident}')
            if approvals:
                found=[a for a in approvals if a.get('id')==ident or (role=='number' and a.get('number')==row['number'] and a.get('role')=='number')]
                if len(found)!=1 or found[0].get('accepted') is not True or found[0].get('failures'):raise ValueError(f'Missing individual approval {ident}')
                a=found[0]
                if a.get('sha256',a.get('source_sha256'))!=row['sha256']:raise ValueError(f'Individual source gate mismatch {ident}')
            result[ident]={**row,'id':ident,'text':text,'spoken_text':text,'path':local(path),'source_path':local(path),'sha256':row['sha256'],'source_sha256':row['sha256'],'sample_frames_24k':frames,'duration_s':duration}
    if set(result)!=set(expected):raise ValueError('Speech does not cover all188 authored IDs')
    return authored,result


def schedule_group(cues,sources,planned_duration):
    """Keep the authored starts unless measured speech needs more room; never speed it up."""
    out=[];previous=0;shift=0;adjustments=[]
    for cue in cues:
        pstart,pend=cue['planning_window_seconds'];source=sources[cue['id']]
        start=max(samples(pstart+shift),previous+samples(.6) if out else 0)
        end=start+source['sample_frames_24k']
        if end>samples(pend+shift):
            delta=(end-samples(pend+shift))/RATE
            shift+=delta
            adjustments.append({'id':cue['id'],'reason':'measured speech requires more than provisional window','additional_s':delta})
        out.append((cue,start,end));previous=end
    duration=max(samples(planned_duration+shift),previous+samples(1.2 if cues[0]['kind']!='finale' else 2))
    return out,duration,adjustments


def make_plan(authored,sources):
    events=[];scenes=[];visual=[];adjust=[];byid={r['id']:r for r in authored}
    def add(cue,start,end):
        src=sources[cue['id']]
        row={**src,'type':'number_voice' if cue['kind']=='count' else 'dialogue','role':'number' if cue['kind']=='count' else 'dialogue','kind':cue['kind'],'phase':cue['kind'],'scene_id':cue['scene_id'],'start_sample_24k':start,'end_sample_24k':end,'start_s':start/RATE,'end_s':end/RATE,'decimal_value':cue.get('value'),'translation_ja':cue.get('translation_ja','')}
        events.append(row);return row
    intro=[r for r in authored if r['kind']=='intro'];scheduled,intro_length,adj=schedule_group(intro,sources,70)
    adjust.extend(adj);introevents={}
    for cue,start,end in scheduled:introevents[cue['id']]=add(cue,start,end)
    scenes.append({'scene':'intro','mode':'intro','start_s':0,'end_s':intro_length/RATE})
    boundaries=[(0,'opening'),(introevents['I02']['start_s']-.4,'definition'),(introevents['I04']['start_s']-.4,'comparison'),(introevents['I07']['start_s']-.4,'rotation'),(introevents['I08']['start_s']-.4,'one'),(introevents['I09']['start_s']-.4,'opening'),(intro_length/RATE,None)]
    for (start,mode),(end,_) in zip(boundaries,boundaries[1:]):visual.append({'mode':mode,'value':None,'start_s':start,'end_s':end,'diagram_fade_in_s':.4 if mode in ('comparison','rotation','one') else 0,'diagram_fade_out_s':.4 if mode in ('comparison','rotation','one') else 0,'phase':'intro'})
    cursor=intro_length;counted=[];teaching=[]
    for index,value in enumerate(VALUES):
        cue=byid[f'N{value:03d}'];voice_start=cursor+samples(.12);voice_end=voice_start+sources[cue['id']]['sample_frames_24k'];ev=add(cue,voice_start,voice_end)
        extended=[r for r in authored if r.get('after_count_value')==value]
        gap=samples(2);teacher=None
        if extended:
            group,group_duration,adj=schedule_group(extended,sources,18)
            adjust.extend(adj);gap=max(samples(18),group_duration)
            for c,s,e in group:add(c,voice_end+s,voice_end+e)
            mode={2:'count',7:'nine',97:'bridge'}[value]
            tstart=(voice_end+samples(.4))/RATE;tend=(voice_end+gap-samples(1.2))/RATE
            teacher={'after_value':value,'mode':mode,'value':value if mode=='count' else None,'start_s':tstart,'end_s':tend,'duration_s':tend-tstart,'gap_s':gap/RATE};teaching.append(teacher)
        final=index==len(VALUES)-1
        nextcursor=voice_end+samples(.28) if final else voice_end+gap-samples(.12)
        scene={'scene':'count','mode':'count','decimal_value':value,'value':value,'ordinal':index+1,'start_s':cursor/RATE,'end_s':nextcursor/RATE,'voice_start_s':voice_start/RATE,'voice_end_s':voice_end/RATE,'spoken_text':cue['text'],'voice_event_id':cue['id']}
        if teacher:scene['teaching']=teacher
        scenes.append(scene);state={**scene,'display_start_s':cursor/RATE,'display_end_s':nextcursor/RATE};counted.append(state)
        if teacher and teacher['mode']!='count':
            visual.extend([{'mode':'count','value':value,'start_s':cursor/RATE,'end_s':teacher['start_s'],'phase':'count'},{**teacher,'phase':'teaching','diagram_fade_in_s':.4,'diagram_fade_out_s':.4},{'mode':'count','value':value,'start_s':teacher['end_s'],'end_s':nextcursor/RATE,'phase':'count'}])
        else:visual.append({'mode':'count','value':value,'start_s':cursor/RATE,'end_s':nextcursor/RATE,'phase':'count','teaching_after_two':bool(teacher)})
        cursor=nextcursor
    finale_start=cursor;finalecues=[r for r in authored if r['kind']=='finale'];group,finale_length,adj=schedule_group(finalecues,sources,22);adjust.extend(adj)
    for cue,start,end in group:add(cue,finale_start+start,finale_start+end)
    duration=(finale_start+finale_length)/RATE
    scenes.append({'scene':'finale','mode':'finale','start_s':finale_start/RATE,'end_s':duration})
    visual.append({'mode':'finale','value':997,'start_s':finale_start/RATE,'end_s':duration,'phase':'finale'})
    events.sort(key=lambda r:r['start_sample_24k'])
    frame_count=math.ceil(duration*FPS-1e-8)
    plan={'schema_version':1,'kind':'measured-prime-counting-timeline','episode_id':'prime-counting-001','revision_id':'prime-counting-v001','status':'measured-accepted-speech','fps':FPS,'width':1920,'height':1080,'duration_s':duration,'duration_frames':frame_count,'count_start':2,'count_end':997,'upper_bound_exclusive':1000,'counted_values':168,'voice_event_count':188,'source_sample_rate_hz':RATE,'master_sample_rate_hz':48000,'master_channels':2,'scenes':scenes,'counted_states':counted,'visual_segments':visual,'voice_events':events,'events':events,'teaching':teaching,'intro':{'start_s':0,'end_s':intro_length/RATE,'fade_in_s':.8},'finale':{'start_s':finale_start/RATE,'end_s':duration,'fade_last_s':2},'timing':{'display_lead_s':.12,'ordinary_number_gap_s':2,'ordinary_boundaries':164,'extended_boundaries':3,'final_number_hold_s':.28},'measured_window_adjustments':adjust,'count_voice_sum_s':sum(sources[f'N{v:03d}']['duration_s'] for v in VALUES),'bgm':False,'sound_effects':[],'renderer_implementation':'tools/render_prime_video.py','verifier_implementation':'tools/verify_prime_video.py','source_script':{'path':local(DESIGN/'narration.json'),'sha256':digest(DESIGN/'narration.json')}}
    validate(plan);return plan


def validate(plan):
    events=plan['voice_events'];counts=[e for e in events if e['kind']=='count']
    if [r['decimal_value'] for r in counts]!=list(VALUES) or len(events)!=188 or len({r['id'] for r in events})!=188:raise ValueError('Incorrect count/event coverage')
    for left,right in zip(events,events[1:]):
        if left['end_sample_24k']>right['start_sample_24k']:raise ValueError(f'Overlapping speech {left["id"]}, {right["id"]}')
    for left,right in zip(counts,counts[1:]):
        gap=right['start_s']-left['end_s'];value=left['decimal_value']
        if value not in (2,7,97) and abs(gap-2)>1e-8:raise ValueError('Normal2second pace changed')
        if value in (2,7,97) and gap<18-1e-8:raise ValueError('Extended explanation interval too short')
    for row in plan['counted_states']:
        if abs(row['voice_start_s']-row['display_start_s']-.12)>1e-8:raise ValueError('Wrong visual speech lead')
    previous=0
    for row in plan['visual_segments']:
        if abs(row['start_s']-previous)>1e-7 or row['end_s']<=row['start_s']:raise ValueError(f'Noncontiguous visual plan {row}')
        previous=row['end_s']
    if abs(previous-plan['duration_s'])>1e-7 or plan['duration_s']<480:raise ValueError('Wrong final duration')
    return {'passed':True,'counted_values':len(counts),'voice_events':len(events),'ordinary_two_second_boundaries':164,'teaching_boundaries':3,'duration_s':plan['duration_s']}


def probe_loudness(ffmpeg,path):
    p=subprocess.run([ffmpeg,'-hide_banner','-nostats','-i',str(path),'-af','loudnorm=I=-16:TP=-1.5:LRA=7:print_format=json','-f','null','-'],capture_output=True,text=True,check=True)
    found=re.findall(r'\{\s*"input_i".*?\}',p.stderr,re.S)
    if not found:raise ValueError('No loudness probe returned')
    return json.loads(found[-1])


def mix(plan,out,ffmpeg,balance_rms_dbfs=-20.5):
    work=out/'.work';work.mkdir(exist_ok=True)
    def write_linear_mix(path,balance):
        total=samples(plan['duration_s'])*2;data=bytearray(total*2*3)
        for row in plan['voice_events']:
            src=resolve(row['source_path']);gain_db=0.0
            if balance:
                with wave.open(str(src),'rb') as w:pcm=array('h',w.readframes(w.getnframes()))
                peak=max(abs(v) for v in pcm)/32768
                rms=math.sqrt(sum(v*v for v in pcm)/len(pcm))/32768
                peak_db=20*math.log10(max(1e-12,peak));rms_db=20*math.log10(max(1e-12,rms))
                gain_db=min(max(0,balance_rms_dbfs-rms_db),-4.5-peak_db)
                row['source_peak_dbfs']=peak_db;row['source_rms_dbfs']=rms_db
            row['mix_gain_db']=gain_db
            cmd=[ffmpeg,'-v','error','-i',str(src)]
            if gain_db:cmd+=['-af',f'volume={gain_db:.9f}dB:precision=double']
            cmd+=['-ar','48000','-ac','2','-c:a','pcm_s24le','-f','s24le','pipe:1']
            converted=subprocess.check_output(cmd)
            expected=row['sample_frames_24k']*2*2*3
            if len(converted)!=expected:raise ValueError(f'Resampled source length mismatch {row["id"]}')
            pos=row['start_sample_24k']*2*2*3;data[pos:pos+len(converted)]=converted
        with wave.open(str(path),'wb') as w:w.setnchannels(2);w.setsampwidth(3);w.setframerate(48000);w.writeframes(data)
    raw=work/'master-unscaled.wav';write_linear_mix(raw,False)
    original=probe_loudness(ffmpeg,raw);before=original
    gain=min(-16-float(before['input_i']),-2.0-float(before['input_tp']))
    balanced=abs(float(before['input_i'])+gain+16)>1
    if balanced:
        raw=work/'master-linear-balanced.wav';write_linear_mix(raw,True);before=probe_loudness(ffmpeg,raw)
        gain=min(-16-float(before['input_i']),-2.0-float(before['input_tp']))
    candidate=work/'master-level-test.wav'
    subprocess.run([ffmpeg,'-v','error','-y','-i',str(raw),'-af',f'volume={gain:.9f}dB:precision=double','-c:a','pcm_s24le',str(candidate)],check=True)
    after=probe_loudness(ffmpeg,candidate)
    passed=float(after['input_tp'])<=-2 and abs(float(after['input_i'])+16)<=1
    trial=len(list(work.glob('master-level-report-v*.json')))+1
    report={'kind':'linear-master-level-attempt','attempt':trial,'passed':passed,'balance_rms_target_dbfs':balance_rms_dbfs,'source_peak_cap_dbfs':-4.5,'per_source_balancing_applied':balanced,'original_probe':original,'balanced_probe':before,'common_gain_db':gain,'after':after,'source_gains':[{'id':r['id'],'source_sha256':r['source_sha256'],'gain_db':r['mix_gain_db']} for r in plan['voice_events']]}
    save_new(work/f'master-level-report-v{trial:03d}.json',report)
    if not passed:
        candidate.rename(work/f'master-level-rejected-v{trial:03d}.wav')
        raise ValueError(f'Unacceptable master level {after}')
    master=out/'master.wav';candidate.rename(master)
    return {'source_gain_db':gain,'common_gain_db':gain,'per_source_balancing_applied':balanced,'per_source_policy':f'gain_db=min(max(0,{balance_rms_dbfs:g}-rms_dbfs),-4.5-peak_dbfs), a measured calibration of the established series linear mix policy' if balanced else 'none; one common linear gain was sufficient','per_source_rms_target_dbfs':balance_rms_dbfs,'source_gains':report['source_gains'],'master_level_attempt':local(work/f'master-level-report-v{trial:03d}.json'),'original_unbalanced_probe':original,'before':before,'after':after,'path':local(master),'sha256':digest(master),'sample_rate_hz':48000,'channels':2,'sample_width_bits':24,'duration_s':plan['duration_s'],'method':'Nonoverlapping accepted speech resampled24kmono to48kstereo; optional one uniform linear gain per source under the established RMS/peak policy, followed by one measured common delivery gain. No limiting, compression, time stretch or source-file changes; silent gaps preserved. Exact per-source gains are recorded on voice_events.'}


def srt_time(s):
    n=round(s*1000);return f'{n//3600000:02d}:{n//60000%60:02d}:{n//1000%60:02d},{n%1000:03d}'

def chapter(s):
    n=int(s);return f'{n//3600}:{n//60%60:02d}:{n%60:02d}' if n>=3600 else f'{n//60:02d}:{n%60:02d}'

def deliveries(plan,out):
    subs=[]
    for i,e in enumerate(plan['voice_events'],1):subs.append(f'{i}\n{srt_time(e["start_s"])} --> {srt_time(e["end_s"])}\n{e["text"]}\n')
    (out/'subtitles.srt').write_text('\n'.join(subs),encoding='utf-8')
    (out/'english-captions.srt').write_text('\n'.join(subs),encoding='utf-8')
    count_by={r['decimal_value']:r for r in plan['counted_states']}
    marks=[(0,'Welcome to the Mosaic Museum'),(count_by[2]['start_s'],'Start counting primes'),(next(t['start_s'] for t in plan['teaching'] if t['after_value']==7),'Why nine is not prime'),(next(t['start_s'] for t in plan['teaching'] if t['after_value']==97),'From 97 to 101'),(count_by[101]['start_s'],'Three-digit primes'),(plan['finale']['start_s'],'All 168 primes below 1000')]
    chapters='\n'.join(f'{chapter(t)} {title}' for t,title in marks)+'\n';(out/'chapters.txt').write_text(chapters,encoding='utf-8')
    title='Prime Numbers 2 to 997 | Count All 168 Primes Below 1000 | Num-Num Numbers'
    (out/'youtube-title.txt').write_text(title+'\n',encoding='utf-8')
    desc="""Count every prime number below 1,000 with our kangaroo guide at the Sunlit Mosaic Museum!\n\nWe count 168 prime numbers from 2 to 997 in natural American English, with a calm pace and large, clear numbers. Tile exhibits introduce factors, show why 1 and 9 are not prime, and explain why 2 is the only even prime. Near 100, we look at why the next prime after 97 is 101.\n\nA prime is a whole number greater than 1 with exactly two positive factors: 1 and itself. One tile in the finished mosaic stands for one prime we counted.\n\nNo background music or sound effects.\n\nCHAPTERS\n"""+chapters+"\nPaspla Studio — Num-Num Numbers\n#PrimeNumbers #LearnNumbers #CountAlong\n"
    (out/'youtube-description.txt').write_text(desc,encoding='utf-8')
    (out/'upload-details.txt').write_text(title+'\n\n'+desc,encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--speech-manifest',type=Path,default=OUT/'speech/measurements.json');p.add_argument('--speech-gate',type=Path,default=OUT/'speech/speech-acceptance.json');p.add_argument('--out-dir',type=Path,default=OUT);p.add_argument('--ffmpeg',default='ffmpeg');p.add_argument('--plan-only',action='store_true');p.add_argument('--balance-rms-dbfs',type=float,default=-20.5);a=p.parse_args()
    if not -28<=a.balance_rms_dbfs<=-15:raise ValueError('Balance RMS target outside expected speech range')
    out=a.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    for name in ('timeline.json','master.wav','subtitles.srt'):
        if (out/name).exists():raise FileExistsError(f'Refusing to overwrite {out/name}')
    authored,sources=accepted_sources(a.speech_manifest.resolve(),a.speech_gate.resolve());plan=make_plan(authored,sources)
    plan['speech_manifest']={'path':local(a.speech_manifest),'sha256':digest(a.speech_manifest)};plan['speech_acceptance']={'path':local(a.speech_gate),'sha256':digest(a.speech_gate)}
    if not a.plan_only:plan['master_audio']=mix(plan,out,a.ffmpeg,a.balance_rms_dbfs)
    save_new(out/'timeline.json',plan);deliveries(plan,out)
    save_new(out/'build-record.json',{'kind':'prime-measured-build','timeline_sha256':digest(out/'timeline.json'),'validation':validate(plan),'master':plan.get('master_audio'),'script_sha256':digest(DESIGN/'narration.json'),'speech_manifest_sha256':digest(a.speech_manifest),'speech_gate_sha256':digest(a.speech_gate)})
    print(json.dumps({'duration_s':plan['duration_s'],'frames':plan['duration_frames'],'events':len(plan['voice_events']),'adjustments':plan['measured_window_adjustments'],'output':str(out)}),flush=True)

if __name__=='__main__':main()
