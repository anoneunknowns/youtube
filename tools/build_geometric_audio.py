"""Measure, schedule and mix geometric sequence speech without retiming sources."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import wave
from build_prime_episode import local, digest, save_new, srt_time, chapter
from build_fibonacci_episode import mix_truepeak_scalars,probe_loudness
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
DESIGN=ROOT/'design/geometric-sequence-counting-v1'
RATE,FPS=24000,30


def read(p):return json.loads(Path(p).read_text())


def script():
    rows=read(DESIGN/'math/speech-script.json')
    assert len(rows)==110 and len({r['id'] for r in rows})==110
    assert sum(r['progress_delta'] for r in rows)==41
    return rows


def measurements(candidates,target):
    expected={r['id']:r for r in script()};takes=read(candidates/'takes.json')
    assert {r['id'] for r in takes}==set(expected)
    numbers,dialogue=[],[]
    for take in takes:
        cue=expected[take['id']];p=Path(take['path']).resolve()
        assert cue['text']==take['text'] and digest(p)==take['sha256']
        with wave.open(str(p)) as w:
            assert (w.getframerate(),w.getnchannels(),w.getsampwidth())==(RATE,1,2)
            frames=w.getnframes()
        row={**take,'path':str(p.relative_to(target.parent)),'spoken_text':cue['text'],
             'kind':cue['kind'],'term_n':cue['term_n'],'index':cue['term_n'],
             'duration_s':frames/RATE,'sample_frames_24k':frames}
        if cue['kind']=='result':
            row.update(number=cue['value'],value=cue['value']);numbers.append(row)
        else:dialogue.append(row)
    result={'schema_version':1,'measurement_status':'measured','adoption_status':'unreviewed-new-candidates',
            'voice':{'provider':'local-kokoro','model_id':'onnx-community/Kokoro-82M-v1.0-ONNX',
                     'library':'kokoro-js@1.2.1','voice_id':'af_heart','dtype':'fp32',
                     'generation_speed':.98,'sample_rate':RATE,'channels':1},
            'source_script':{'path':local(DESIGN/'math/speech-script.json'),'sha256':digest(DESIGN/'math/speech-script.json')},
            'candidate_takes':{'path':local(candidates/'takes.json'),'sha256':digest(candidates/'takes.json')},
            'measurement_method':'Exact PCM frames / 24000. No time stretch.', 'numbers':numbers,'dialogue':dialogue}
    save_new(target,result);return result


def sources(manifest,gate=None):
    m=read(manifest);expected={r['id']:r for r in script()};result={}
    assert m['measurement_status']=='measured'
    approvals={}
    if gate:
        g=read(gate)
        assert g['accepted'] and not g['unresolved'] and g['source_manifest_sha256']==digest(manifest)
        approvals={r['id']:r for r in g['results']}
        def evidence(node):
            if isinstance(node,dict):
                if isinstance(node.get('path'),str) and isinstance(node.get('sha256'),str):
                    p=Path(node['path']);p=p if p.is_absolute() else ROOT/p
                    assert p.is_file() and digest(p)==node['sha256'],str(p)
                for v in node.values():evidence(v)
            elif isinstance(node,list):
                for v in node:evidence(v)
        evidence(g.get('inputs',{}))
    for row in m['numbers']+m['dialogue']:
        ident=row['id'];p=(manifest.parent/row['path']).resolve()
        assert ident in expected and ident not in result and expected[ident]['text']==row['spoken_text']
        assert digest(p)==row['sha256']
        with wave.open(str(p)) as w:
            assert (w.getframerate(),w.getnchannels(),w.getsampwidth())==(RATE,1,2)
            frames=w.getnframes()
        assert abs(row['duration_s']-frames/RATE)<1/RATE
        if gate:
            a=approvals[ident]
            assert a['accepted'] and not a['failures'] and a['source_sha256']==row['sha256']
        result[ident]={**row,'path':local(p),'source_path':local(p),'source_sha256':row['sha256'],
                       'sample_frames_24k':frames,'duration_s':frames/RATE}
    assert set(result)==set(expected)
    return result


def make_plan(source,accepted=False):
    rows=script();cursor=0;events=[]
    for row in rows:
        s=source[row['id']];cursor+=round(row['gap_before_s']*RATE)
        start,end=cursor,cursor+s['sample_frames_24k']
        event={**s,**{k:row[k] for k in ['id','scene_id','kind','term_n','current_index','completed_terms_before',
               'completed_terms_after','comparison_id','progress_delta','value','text','subtitle_text','visible_action','gap_before_s']},
               'phase':row['kind'],'role':'number' if row['kind']=='result' else 'dialogue',
               'index':row['term_n'],'n':row['term_n'],'spoken_text':row['text'],
               'start_s':start/RATE,'end_s':end/RATE,'start_sample_24k':start,'end_sample_24k':end,
               'voice_start_frame':round(start/RATE*FPS),'voice_end_frame':math.ceil(end/RATE*FPS-1e-9)}
        if row['kind']=='result':
            event.update(result_display_s=(start-round(.12*RATE))/RATE,
                         result_display_frame=round((start/RATE-.12)*FPS),progress_commit_s=end/RATE,
                         progress_commit_frame=math.ceil(end/RATE*FPS-1e-9))
        events.append(event);cursor=end
    duration=(cursor+round(1.2*RATE))/RATE
    frames=math.ceil(duration*FPS-1e-9)
    # Pad the common audio tail to the final video frame; do not retime speech.
    duration=frames/FPS
    by_id={e['id']:e for e in events};seq=read(DESIGN/'math/sequence.json')['terms'];states=[]
    for n,term in enumerate(seq,1):
        count=by_id[f'N{n:03}'];stem=by_id.get(f'E{n:03}')
        nxt=by_id.get(f'E{n+1:03}')
        state={**term,'index':n,'n':n,'decimal_value':term['value'],
               'cycle_start_s':stem['start_s'] if stem else count['result_display_s'],
               'cycle_end_s':nxt['start_s'] if nxt else by_id['D026']['start_s'],
               'operation_start_s':stem['start_s'] if stem else None,
               'operation_end_s':count['result_display_s'] if stem else None,
               'operand_start_s':stem['start_s'] if stem else None,'operand_end_s':stem['end_s'] if stem else None,
               'result_start_s':count['result_display_s'],'result_voice_start_s':count['start_s'],
               'result_voice_end_s':count['end_s'],'result_end_s':count['end_s'],
               'display_start_s':count['result_display_s'],'progress_commit_s':count['end_s'],
               'progress_commit_frame':count['progress_commit_frame']}
        state.update(start_s=state['cycle_start_s'],end_s=state['cycle_end_s'],
                     operation_start_frame=round(stem['start_s']*FPS) if stem else None,
                     operation_end_frame=count['result_display_frame'] if stem else None,
                     result_display_frame=count['result_display_frame'],
                     display_mode='exact-units' if n<=3 else 'value-groups' if n<=32 else 'wide-value')
        states.append(state)
    scenes=[]
    for e in events:
        if not scenes or scenes[-1]['scene_id']!=e['scene_id']:
            scenes.append({'scene_id':e['scene_id'],'start_s':e['start_s']-e['gap_before_s'],
                           'end_s':e['end_s'],'first_cue':e['id'],'last_cue':e['id'],'current_index':e['current_index']})
        else:scenes[-1].update(end_s=e['end_s'],last_cue=e['id'])
    for a,b in zip(scenes,scenes[1:]):a['end_s']=b['start_s']
    scenes[-1]['end_s']=duration
    plan={'schema_version':1,'kind':'geometric-sequence-measured-production-timeline','production_ready':accepted,
          'speech_accepted':accepted,'fps':FPS,'frame_size':[1920,1080],'sample_rate':RATE,
          'duration_s':duration,'duration_frames':frames,'duration_samples_24k':round(duration*RATE),
          'voice_sum_s':sum(e['duration_s'] for e in events),'voice_events':events,'events':events,
          'counted_states':states,'states':states,'scenes':scenes,'visual_segments':scenes,
          'source_script':{'path':local(DESIGN/'math/speech-script.json'),'sha256':digest(DESIGN/'math/speech-script.json')},
          'integer_policy':'Exact decimal strings. 41 terms, 40 operations; no intermediate or comparison term count.',
          'bgm':False,'sound_effects':[],'voice_profile':{'voice_id':'af_heart','speed':.98,'dtype':'fp32'}}
    validate(plan);return plan


def validate(plan):
    events=plan['voice_events'];by={e['id']:e for e in events};normal=0
    assert len(events)==110 and len(by)==110 and len(plan['states'])==41
    assert sum(e['progress_delta'] for e in events)==41
    assert plan['duration_s']>=480
    for n,s in enumerate(plan['states'],1):
        assert s['n']==n and int(s['value'])==2*3**(n-1)
        a=by[f'N{n:03}'];assert abs(a['start_s']-s['result_start_s']-.12)<1e-8
        assert s['progress_commit_frame']==math.ceil(a['end_s']*FPS-1e-9)
        if n>1:
            b=by[f'E{n:03}'];assert abs(a['start_s']-b['end_s']-.16)<1e-8
        if n<41 and n not in (3,4,10,20):
            normal+=1;assert abs(by[f'E{n+1:03}']['start_s']-a['end_s']-2)<1e-8
    for a,b in zip(events,events[1:]):assert a['end_sample_24k']<=b['start_sample_24k']
    return {'passed':True,'speech_events':110,'result_events':41,'operand_events':40,'dialogue_events':29,
            'ordinary_two_second_boundaries':normal,'explanation_boundaries':[3,4,10,20],
            'duration_s':plan['duration_s'],'duration_frames':plan['duration_frames'],'voice_sum_s':plan['voice_sum_s']}


def deliveries(plan,out):
    srt='\n'.join(f'{i}\n{srt_time(e["start_s"])} --> {srt_time(e["end_s"])}\n{e["text"]}\n' for i,e in enumerate(plan['events'],1))
    for name in ('subtitles.srt','english-captions.srt'):
        with (out/name).open('x') as f:f.write(srt)
    headings={'S01-OPENING':'Welcome to the Glass Gallery of Ratios','S02-EXACT-UNITS':'Start with two; multiply by three',
              'S03-SCHEMATIC-TRANSITION':'From beads to whole value groups','S05-GENERAL-TERM':'Put a term number into the formula',
              'S07-COMPARE-RATIOS':'Change the common ratio','S09-HALF-EXAMPLE':'Geometric sequences can shrink','S11-ENDING':'The same starting number and ratio'}
    chapters='\n'.join(f'{chapter(s["start_s"])} {headings[s["scene_id"]]}' for s in plan['scenes'] if s['scene_id'] in headings)+'\n'
    title='Geometric Sequences: Watch the Formula Work | Multiply by 3 | Num-Num Numbers'
    description='Count 41 geometric-sequence terms with our pink rabbit in the Glass Gallery of Ratios. Start at 2 and multiply by 3 at every step, through 24,315,330,918,113,857,602.\n\nWatch the result become the next input. Put n=4 into a_n=2×3^(n−1), compare ratios 2 and 3, and see a separate halving sequence. The intermediate 27 and comparison examples are not new main terms. Natural American English, short scale. No background music or sound effects.\n\nCHAPTERS\n'+chapters+'\nPaspla Studio — Num-Num Numbers\n#GeometricSequence #LearnNumbers #MathForKids\n'
    for name,text in [('chapters.txt',chapters),('youtube-title.txt',title+'\n'),('youtube-description.txt',description)]:
        with (out/name).open('x') as f:f.write(text)


def adopt_measured_constant_gain_attempt(plan,out,work,ffmpeg,extra_gain_db):
    """Apply the episode's approved constant-gain PCM delivery specification.

    The shared Fibo attempt and its failed stricter (-2dBTP) receipt remain
    immutable. This new episode uses PCM TP<=-1.8 and final AAC<=-1dBTP.
    """
    report=read(work/'level-report.json');candidate=work/'master-level-rejected.wav'
    assert report['passed'] is False and abs(extra_gain_db-.20)<1e-9
    measurements={r['id']:r for r in report['source_measurements']}
    assert len(measurements)==len(plan['voice_events'])==110
    for e in plan['voice_events']:
        row=measurements[e['id']];assert row['source_sha256']==e['source_sha256']
        e.update(source_peak_dbfs=row['source_peak_dbfs'],source_rms_dbfs=row['source_rms_dbfs'],
                 mix_gain_db=row['final_source_gain_db'],per_source_truepeak_calibration_db=row['additional_constant_gain_db'],
                 aac_codec_calibration_gain_db=row.get('aac_codec_calibration_gain_db',0))
    master=out/'master.wav'
    subprocess.run([ffmpeg,'-v','error','-i',str(candidate),'-af',f'volume={extra_gain_db:.12f}dB:precision=double',
                    '-c:a','pcm_s24le',str(master)],check=True)
    after=probe_loudness(ffmpeg,master)
    assert -17<=float(after['input_i'])<=-15 and float(after['input_tp'])<=-1.8
    with wave.open(str(master)) as w:
        assert (w.getframerate(),w.getnchannels(),w.getsampwidth())==(48000,2,3)
        assert w.getnframes()==round(plan['duration_s']*48000)
    receipt={'kind':'geometric-episode-constant-delivery-gain-acceptance','accepted':True,
             'scope':'PCM master; final AAC requires independent conventional gate',
             'criteria':{'integrated_lufs':[-17,-15],'true_peak_max_dbtp':-1.8},
             'final_aac_criteria':{'integrated_lufs':[-17,-15],'true_peak_max_dbtp':-1},
             'parent_decision':'Geometric production: retain shared strict -2dBTP attempt, apply a single extra +0.20dB to meet I=-16±1 with PCM TP<=-1.8; final AAC retains established TP<=-1.',
             'source_attempt':{'path':local(candidate),'sha256':digest(candidate)},
             'source_attempt_receipt':{'path':local(work/'level-report.json'),'sha256':digest(work/'level-report.json')},
             'extra_constant_gain_db':extra_gain_db,'shared_attempt_loudness':report['after'],'after':after,
             'master':{'path':local(master),'sha256':digest(master)},
             'signal_processing':'Only constant volume scalar and PCM24 quantization. No limiting/compression/time stretch. Same channels, sample count, cue times and silent intervals.'}
    save_new(out/'pcm-level-acceptance-v002.json',receipt)
    common=report['common_gain_db']+extra_gain_db
    return {'path':local(master),'sha256':digest(master),'sample_rate_hz':48000,'channels':2,'sample_width_bits':24,
            'duration_s':plan['duration_s'],'source_gain_db':common,'common_gain_db':common,
            'per_source_balancing_applied':True,'source_gains':[{'id':e['id'],'source_sha256':e['source_sha256'],'gain_db':e['mix_gain_db']} for e in plan['voice_events']],
            'master_level_attempt':local(work/'level-report.json'),'master_level_acceptance':local(out/'pcm-level-acceptance-v002.json'),
            'before':report['before'],'after':after,'method':'Per-source constant true-peak scalars, 48k stereo PCM24, common scalar plus approved episode-wide +0.20dB. No source WAV edits or retiming.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepare-manifest',type=Path);p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--gate',type=Path);p.add_argument('--draft',type=Path);p.add_argument('--out',type=Path)
    p.add_argument('--adopt-level-attempt',type=Path)
    p.add_argument('--ffmpeg',default=str(ROOT/'.venv/bin/ffmpeg'))
    a=p.parse_args();manifest=a.manifest.resolve()
    if a.prepare_manifest:measurements(a.prepare_manifest.resolve(),manifest)
    data=sources(manifest,a.gate.resolve() if a.gate else None);plan=make_plan(data,bool(a.gate))
    plan['speech_manifest']={'path':local(manifest),'sha256':digest(manifest)}
    if a.draft:
        save_new(a.draft.resolve(),plan);print(json.dumps(validate(plan)));return
    assert a.gate and a.out,'Accepted gate and --out required for mixing'
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    for name in ('timeline.json','master.wav','build-record.json'):assert not (out/name).exists()
    level=(adopt_measured_constant_gain_attempt(plan,out,a.adopt_level_attempt.resolve(),a.ffmpeg,.20)
           if a.adopt_level_attempt else mix_truepeak_scalars(plan,out,a.ffmpeg,-19))
    plan['master']=plan['audio']=plan['master_audio']=level
    plan['speech_acceptance']={'path':local(a.gate),'sha256':digest(a.gate)}
    save_new(out/'timeline.json',plan);deliveries(plan,out)
    record={'status':'accepted-measured-speech-and-master-built','timeline':{'path':local(out/'timeline.json'),'sha256':digest(out/'timeline.json')},'master':level,'speech_manifest':plan['speech_manifest'],'speech_gate':plan['speech_acceptance'],'validation':validate(plan),'sources_retimed_or_overwritten':False,'video_rendered':False}
    save_new(out/'build-record.json',record);print(json.dumps(record['validation']))


if __name__=='__main__':main()
