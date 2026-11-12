"""Build the triangular episode from hash-bound, reviewed, PCM-measured speech.

No time stretching or artificial extensions. Ordinary gaps and each utterance's
sample count determine the timeline; a draft is explicitly not production.
"""
from __future__ import annotations
import argparse,hashlib,json,math,re,wave
from pathlib import Path
try:
    from .build_prime_episode import digest,local,resolve,save_new,srt_time,chapter
    from .build_fibonacci_episode import mix_truepeak_scalars
except ImportError:
    from build_prime_episode import digest,local,resolve,save_new,srt_time,chapter
    from build_fibonacci_episode import mix_truepeak_scalars
ROOT=Path(__file__).resolve().parents[1]
DESIGN=ROOT/'design/triangular-counting-v1'
SPEECH=ROOT/'output/triangular-counting-001-v001/speech'
OUT=ROOT/'output/triangular-counting-001-v001/audio-build/v002'
RATE,FPS=24000,30
VIDEO_NAME='paspla-studio-triangular-numbers-0-to-1830-1080p.mp4'
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def samples(s):return round(s*RATE)
def authored_rows():
    p=read(DESIGN/'math/math-plan.json');rows=p['cues']
    if len(rows)!=131 or len({r['id'] for r in rows})!=131 or p['n_max']!=60:raise ValueError('Expected approved131 cues and n0..60')
    return [{**r,'text':r['text_en'],'authored_kind':r['kind'],'kind':'count' if r['kind']=='result' else r['kind'],'index':r.get('n'),'cue':r.get('visual')} for r in rows]
def measured_sources(manifest_path,gate_path=None):
    m=read(manifest_path);voice=m['voice'];expected={r['id']:r for r in authored_rows()}
    if m.get('measurement_status')!='measured' or (voice['voice_id'],voice['dtype'],voice['generation_speed'])!=('af_heart','fp32',.98):raise ValueError('Wrong measurements/voice')
    gate=read(gate_path) if gate_path else None;approvals={r['id']:r for r in gate.get('results',[])} if gate else {}
    if gate:
        if not gate.get('accepted') or gate.get('unresolved') or gate.get('source_manifest_sha256')!=digest(manifest_path):raise ValueError('Unaccepted or wrong-hash source gate')
        def evidence(node):
            if isinstance(node,dict):
                if isinstance(node.get('path'),str) and isinstance(node.get('sha256'),str):
                    p=resolve(node['path']);p=p if p.is_file() else resolve(node['path'],Path(gate_path).parent)
                    if not p.is_file() or digest(p)!=node['sha256']:raise ValueError(f'Acceptance evidence changed:{p}')
                for v in node.values():evidence(v)
            elif isinstance(node,list):
                for v in node:evidence(v)
        evidence(gate.get('inputs',{}))
    result={}
    for row in m['numbers']+m['dialogue']:
        ident=row['id'];p=resolve(row['path'],Path(manifest_path).parent)
        if ident not in expected or ident in result or row['spoken_text']!=expected[ident]['text']:raise ValueError(f'Wrong source:{ident}')
        if digest(p)!=row['sha256']:raise ValueError(f'Changed WAV:{ident}')
        with wave.open(str(p)) as w:
            if (w.getframerate(),w.getnchannels(),w.getsampwidth())!=(RATE,1,2):raise ValueError('Expected24k mono16')
            frames=w.getnframes()
        if abs(frames/RATE-row['duration_s'])>1/RATE:raise ValueError('Incorrect duration')
        if gate:
            a=approvals.get(ident,{})
            if not a.get('accepted') or a.get('failures') or a.get('source_sha256')!=row['sha256']:raise ValueError(f'Unapproved source:{ident}')
        result[ident]={**row,'text':row['spoken_text'],'path':local(p),'source_path':local(p),'source_sha256':row['sha256'],'sample_frames_24k':frames,'duration_s':frames/RATE}
    if set(result)!=set(expected) or len(m['numbers'])!=61:raise ValueError('Incomplete131-cue coverage')
    return result

def operator_times(event,ctc):
    tokens=ctc.get(event['id'],{}).get('tokens',[])
    chars=[(ch,t) for t in tokens for ch in t['token'].replace('ː','').replace('ᵻ','ɪ').replace('ɚ','əɹ')]
    seq=''.join(ch for ch,t in chars)
    tm=re.search(r'taɪm[zs]+',seq);div=re.search(r'd[ɪəi]vaɪd[ɪəi]d',seq);eq=re.search(r'[iɪe]kwəl+z',seq)
    two=None
    if div and eq:
        twore=re.search(r'tu',seq[div.end():eq.start()])
        if twore:two=div.end()+twore.start()
    if tm and div and eq and two is not None:
        values=dict(a_start_s=0,times_start_s=chars[tm.start()][1]['start_s'],b_start_s=chars[tm.end()-1][1]['end_s'],divided_start_s=chars[div.start()][1]['start_s'],two_start_s=chars[two][1]['start_s'],equals_start_s=chars[eq.start()][1]['start_s'],equals_end_s=chars[eq.end()-1][1]['end_s'])
        if list(values.values())==sorted(values.values()) and values['equals_start_s']<event['duration_s']:
            return {**{k:event['start_s']+min(v,event['duration_s']) for k,v in values.items()},'method':'independent unprompted CTC times/divided/two/equals phone sequences; approximate20ms','source_sha256':event['source_sha256']}
    words=event['text'].replace('-',' ').replace(',','').split();a=words.index('times');divided=words.index('divided');total=len(words);d=event['duration_s']
    positions={'a_start_s':0,'times_start_s':a,'b_start_s':a+1,'divided_start_s':divided,'two_start_s':divided+2,'equals_start_s':total-1,'equals_end_s':total}
    return {**{k:event['start_s']+d*v/total for k,v in positions.items()},'method':'word-proportion visual estimate in measured cue; not word-level measured alignment','source_sha256':event['source_sha256']}

def make_plan(sources,phonemes=None,adopted=True):
    authored=authored_rows();cursor=samples(.8);events=[]
    for i,cue in enumerate(authored):
        src=sources[cue['id']];start=cursor;end=start+src['sample_frames_24k'];n=cue.get('index')
        e={**src,'id':cue['id'],'kind':cue['kind'],'phase':cue['kind'],'role':'number' if cue['kind']=='count' else 'dialogue','index':n,'n':n,'value':cue.get('value'),'decimal_value':cue.get('value'),'text':cue['text'],'spoken_text':cue['text'],'subtitle_text':cue['text'],'cue':cue['cue'],'start_s':start/RATE,'end_s':end/RATE,'start_sample_24k':start,'end_sample_24k':end}
        if cue['kind']=='count':e['result_display_s']=(start-samples(.12))/RATE
        events.append(e);cursor=end
        if i==len(authored)-1:cursor+=samples(1.2)
        else:
            next_kind=authored[i+1]['kind']
            gap=.16 if cue['kind']=='formula_prefix' and next_kind=='count' else 2 if next_kind=='formula_prefix' else .6
            cursor+=samples(gap)
    by_id={e['id']:e for e in events};ctc={e['id']:e for e in (phonemes or {}).get('results',[])}
    for e in events:
        if e['kind']=='formula_prefix':e['highlight_timing']=operator_times(e,ctc)
    duration=cursor/RATE;finale_start=by_id['O01']['start_s']-.12;states=[];visual=[];teachers=[]
    def segment(mode,start,end,n=None,voice_event_id=None,scene=None,**params):
        if end<=start:raise ValueError('Empty visual segment')
        visual.append({'mode':mode,'kind':mode,'scene':scene or mode,'index':n,'n':n,'value':sum(range(n+1)) if n is not None else None,'voice_event_id':voice_event_id,'start_s':start,'end_s':end,'params':params})
    intro=[e for e in events if e['kind']=='intro'];zero_start=by_id['N000']['result_display_s']
    for i,e in enumerate(intro):
        start=0 if i==0 else e['start_s']-.12;end=intro[i+1]['start_s']-.12 if i+1<len(intro) else zero_start
        segment('intro',start,end,voice_event_id=e['id'],scene=e['id'])
    for n in range(61):
        E=by_id.get(f'E{n:03}');N=by_id[f'N{n:03}'];value=sum(range(n+1));start=E['start_s'] if E else zero_start
        end=by_id[f'E{n+1:03}']['start_s'] if n<60 else finale_start
        state={'index':n,'n':n,'value':value,'decimal_value':value,'ordinal':n+1,'a':n,'b':n+1,'c':value,'operands':[n,n+1],'divisor':2,'double_value':n*(n+1),'cycle_start_s':start,'cycle_end_s':end,'start_s':start,'end_s':end,'formula_start_s':E['start_s'] if E else None,'formula_end_s':E['end_s'] if E else None,'expression_start_s':E['start_s'] if E else None,'expression_end_s':E['end_s'] if E else None,'result_start_s':N['result_display_s'],'result_end_s':N['end_s'],'display_start_s':N['result_display_s'],'display_end_s':end,'voice_start_s':N['start_s'],'voice_end_s':N['end_s'],'voice_event_id':N['id'],'formula_event_id':E['id'] if E else None,'spoken_text':N['text'],'highlight_timing':E['highlight_timing'] if E else {},'progress_commit_s':N['end_s']}
        states.append(state);X=[e for e in events if e['kind']=='explanation' and e['index']==n]
        if X:
            tstart=X[0]['start_s']-.12;scene={4:'pair-proof',5:'new-row',10:'density-change',14:'three-digits',45:'thousand-threshold'}[n]
            segment('count',start,tstart,n,E['id'] if E else N['id']);segment('teaching',tstart,end,n,X[0]['id'],scene,replay=True,count_progress_held=True,voice_event_ids=[x['id'] for x in X],count_state_index=n)
            teachers.append({'index':n,'after_index':n,'n':n,'value':value,'after_value':value,'voice_event_id':X[0]['id'],'voice_event_ids':[x['id'] for x in X],'scene':scene,'start_s':tstart,'end_s':end,'voice_start_s':X[0]['start_s'],'voice_end_s':X[-1]['end_s'],'count_progress_held':True,'replay':True})
        else:segment('count',start,end,n,E['id'] if E else N['id'])
    segment('outro',finale_start,duration,60,'O01','finale')
    plan={'schema_version':1,'kind':'measured-triangular-counting-timeline','episode_id':'triangular-counting-001','revision_id':'triangular-counting-v001','status':'measured-accepted-speech' if adopted else 'measured-unreviewed-draft-not-production','speech_adopted':adopted,'fps':FPS,'width':1920,'height':1080,'duration_s':duration,'duration_frames':math.ceil(duration*FPS-1e-8),'count_index_start':0,'count_index_end':60,'count_start':0,'count_end':1830,'counted_values':61,'voice_event_count':131,'source_sample_rate_hz':RATE,'master_sample_rate_hz':48000,'master_channels':2,'voice_events':events,'events':events,'counted_states':states,'visual_segments':visual,'scenes':visual,'teaching':teachers,'intro':{'start_s':0,'end_s':zero_start,'fade_in_s':.6},'finale':{'start_s':finale_start,'end_s':duration,'fade_last_s':1.2},'timing':{'result_display_lead_s':.12,'formula_prefix_to_result_gap_s':.16,'ordinary_result_end_to_next_formula_start_s':2,'checkpoint_after_indices':[4,5,10,14,45],'fixed_transition_sum_s':137.6,'highlight_word_boundary_policy':'independent CTC operator tokens; explicitly labelled proportional estimates otherwise'},'voice_sum_s':sum(e['duration_s'] for e in events),'bgm':False,'sound_effects':[],'source_script':{'path':local(DESIGN/'math/math-plan.json'),'sha256':digest(DESIGN/'math/math-plan.json')},'renderer_implementation':'tools/render_triangular_video.py','verifier_implementation':'tools/verify_triangular_video.py'}
    validate(plan);return plan

def validate(plan):
    events=plan['voice_events'];by={e['id']:e for e in events};states=plan['counted_states']
    if len(events)!=131 or len(by)!=131 or len(states)!=61:raise ValueError('Wrong cue/state coverage')
    for n,s in enumerate(states):
        N=by[f'N{n:03}'];E=by.get(f'E{n:03}')
        if s['index']!=n or s['value']!=sum(range(n+1)) or s['operands']!=[n,n+1] or N['value']!=s['value']:raise ValueError(f'Wrong state {n}')
        if abs(N['start_s']-s['result_start_s']-.12)>1e-8:raise ValueError('Changed result display lead')
        if E and abs(N['start_s']-E['end_s']-.16)>1e-8:raise ValueError('Changed equals/result gap')
        if not n and E:raise ValueError('Zero must have no E000')
        if n<60:
            X=[e for e in events if e['kind']=='explanation' and e['index']==n]
            last=X[-1] if X else N
            if abs(by[f'E{n+1:03}']['start_s']-last['end_s']-2)>1e-8:raise ValueError('Changed normal boundary')
    for a,b in zip(events,events[1:]):
        if a['end_sample_24k']>b['start_sample_24k']:raise ValueError('Overlapping speech')
    previous=0
    for s in plan['visual_segments']:
        if abs(s['start_s']-previous)>1e-7 or s['end_s']<=s['start_s']:raise ValueError('Noncontiguous scenes')
        previous=s['end_s']
    if abs(previous-plan['duration_s'])>1e-7 or abs(plan['duration_s']-plan['voice_sum_s']-137.6)>1e-7:raise ValueError('Changed fixed editing intervals')
    if plan['duration_s']<480:raise ValueError('Measured duration under8min; extend range before production')
    return {'passed':True,'voice_events':131,'counted_states':61,'expressions':60,'ordinary_two_second_boundaries':55,'teaching_boundaries':5,'duration_s':plan['duration_s'],'voice_sum_s':plan['voice_sum_s'],'fixed_transition_sum_s':137.6}

def deliveries(plan,out):
    srt='\n'.join(f'{i}\n{srt_time(e["start_s"])} --> {srt_time(e["end_s"])}\n{e["text"]}\n' for i,e in enumerate(plan['voice_events'],1))
    states={s['index']:s for s in plan['counted_states']};teaching={s['index']:s for s in plan['teaching']}
    marks=[(0,'Welcome to the Light-Pebble Grotto'),(states[0]['start_s'],'Start with zero'),(teaching[4]['start_s'],'Two triangles make a rectangle'),(teaching[10]['start_s'],'Follow the growing rows'),(teaching[45]['start_s'],'The first triangular number above one thousand'),(states[60]['start_s'],'Sixty rows: one thousand eight hundred thirty'),(plan['finale']['start_s'],'All 61 triangular numbers')]
    # Closely spaced final state/outro are one published chapter.
    marks=[(t,title) for i,(t,title) in enumerate(marks) if i!=len(marks)-1 or t-marks[i-1][0]>=10]
    chapters='\n'.join(f'{chapter(t)} {title}' for t,title in marks)+'\n'
    title='Triangular Numbers: Watch the Formula Work | 0 to 1,830 | Num-Num Numbers'
    description='Count all 61 triangular numbers from T0=0 through T60=1,830 with our meerkat guide in the Light-Pebble Grotto.\n\nTwo matching dot triangles form an n by (n+1) rectangle. Taking one of the two equal copies shows Tn=n(n+1)/2. Each new row also adds n dots. All dots are drawn; for larger triangles, follow the row labels and formula. Every result is spoken once in natural American English.\n\nNo background music or sound effects.\n\nCHAPTERS\n'+chapters+'\nPaspla Studio — Num-Num Numbers\n#TriangularNumbers #LearnNumbers #MathForKids\n'
    for name,text in [('subtitles.srt',srt),('english-captions.srt',srt),('chapters.txt',chapters),('youtube-title.txt',title+'\n'),('youtube-description.txt',description),('upload-details.txt',title+'\n\n'+description)]:
        with (out/name).open('x',encoding='utf-8') as f:f.write(text)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--speech-manifest',type=Path,default=SPEECH/'measurements-selected-v003.json');p.add_argument('--speech-gate',type=Path,default=SPEECH/'speech-acceptance-v002.json');p.add_argument('--phonemes',type=Path,default=SPEECH/'phonemes-selected-v003.json');p.add_argument('--out-dir',type=Path,default=OUT);p.add_argument('--ffmpeg',default=str(ROOT/'.venv/bin/ffmpeg'));p.add_argument('--draft-plan',type=Path);p.add_argument('--balance-rms-dbfs',type=float,default=-19);a=p.parse_args()
    gate=None if a.draft_plan else a.speech_gate.resolve();src=measured_sources(a.speech_manifest.resolve(),gate);phonemes=read(a.phonemes) if a.phonemes.is_file() else None;plan=make_plan(src,phonemes,adopted=gate is not None);plan['speech_manifest']={'path':local(a.speech_manifest),'sha256':digest(a.speech_manifest)}
    if a.draft_plan:save_new(a.draft_plan,plan);print(json.dumps(validate(plan)));return
    out=a.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    for name in ('timeline.json','master.wav','subtitles.srt','build-record.json'):
        if (out/name).exists():raise FileExistsError(f'Refusing to overwrite {out/name}')
    levels=mix_truepeak_scalars(plan,out,a.ffmpeg,a.balance_rms_dbfs);plan['audio']=plan['master']=plan['master_audio']=levels;plan['speech_acceptance']={'path':local(a.speech_gate),'sha256':digest(a.speech_gate)}
    if a.phonemes.is_file():plan['phoneme_alignment']={'path':local(a.phonemes),'sha256':digest(a.phonemes)}
    save_new(out/'timeline.json',plan);deliveries(plan,out);save_new(out/'build-record.json',{'kind':'triangular-production-audio-build','status':'accepted-measured-speech-and-master-built','timeline':{'path':local(out/'timeline.json'),'sha256':digest(out/'timeline.json')},'speech_manifest':plan['speech_manifest'],'speech_gate':plan['speech_acceptance'],'master':levels,'validation':validate(plan),'video_rendered':False,'source_audio_retimed_or_overwritten':False,'video_filename':VIDEO_NAME});print(json.dumps({'duration_s':plan['duration_s'],'frames':plan['duration_frames'],'speech_events':131,'master':levels['after']}))
if __name__=='__main__':main()
