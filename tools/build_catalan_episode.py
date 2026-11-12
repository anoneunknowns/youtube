"""Build Catalan delivery from accepted 24k PCM speech and measured CTC tokens.

Preproduction inputs are read-only. No voiced clip is stretched, repaired or
silently substituted. All large integer values remain decimal strings in JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import wave

try:
    from .build_prime_episode import digest, local, resolve, save_new, srt_time, chapter, probe_loudness
    from .build_fibonacci_episode import mix_truepeak_scalars
except ImportError:
    from build_prime_episode import digest, local, resolve, save_new, srt_time, chapter, probe_loudness
    from build_fibonacci_episode import mix_truepeak_scalars

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT/'design/catalan-counting-v1'
OUT = ROOT/'output/catalan-counting-001-v001'
RATE, FPS = 24000, 30


def read(path):
    return json.loads(Path(path).read_text())


def prepare_manifest(speech, destination, takes_paths):
    authored = read(DESIGN/'narration.json')
    takes = {}
    for file in takes_paths:
        for row in read(file):
            takes[row['id']] = row
    if set(takes) != {r['id'] for r in authored}:
        raise ValueError('All86 authored utterances must have explicit selected sources')
    numbers, dialogue = [], []
    count_rows = {r['index']: r for r in read(DESIGN/'count-lines.json')}
    for cue in authored:
        row = takes[cue['id']]
        if row.get('text', row.get('spoken_text')) != cue['text']:
            raise ValueError(f'Authored text mismatch {cue["id"]}')
        source = resolve(row['path'])
        if digest(source) != row['sha256']:
            raise ValueError(f'Source changed {cue["id"]}')
        with wave.open(str(source)) as w:
            if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, RATE):
                raise ValueError('Expected24kmono16')
            frames = w.getnframes()
        record = {**row, 'id': cue['id'], 'kind': cue['kind'], 'index': cue.get('index'),
                  'text': cue['text'], 'spoken_text': cue['text'],
                  'path': local(source), 'duration_s': frames/RATE,
                  'sample_frames_24k': frames, 'measurement_status': 'measured'}
        # Use root-relative paths in an explicit source-location field and a
        # manifest-relative path for generic speech-analysis tools.
        record['source_path'] = local(source)
        record['path'] = str(Path(__import__('os').path.relpath(source, destination.parent)))
        if cue['id'].startswith('N'):
            record['number'] = count_rows[cue['index']]['value']
            record['value'] = count_rows[cue['index']]['value']
            numbers.append(record)
        else:
            dialogue.append(record)
    manifest = dict(schema_version=1, measurement_status='measured',
                    kind='catalan-selected-source-measurements',
                    adoption_status='unreviewed selection; accepted gate required before mix',
                    source_script={'path':local(DESIGN/'narration.json'),'sha256':digest(DESIGN/'narration.json')},
                    voice={'provider':'local-kokoro','model_id':'onnx-community/Kokoro-82M-v1.0-ONNX',
                           'voice_id':'af_heart','generation_speed':.98,'dtype':'fp32',
                           'library':'kokoro-js@1.2.1','sample_rate':RATE,'channels':1},
                    integer_encoding='decimal-string', numbers=numbers, dialogue=dialogue,
                    selection_inputs=[{'path':local(p),'sha256':digest(p)} for p in takes_paths])
    save_new(destination, manifest)
    return manifest


def accepted_sources(manifest_path, gate_path):
    manifest, gate = read(manifest_path), read(gate_path)
    if not gate.get('accepted') or gate.get('unresolved') or gate['source_manifest_sha256'] != digest(manifest_path):
        raise ValueError('A complete, current accepted speech gate is required')
    required_voice={'model_id':'onnx-community/Kokoro-82M-v1.0-ONNX','voice_id':'af_heart',
                    'generation_speed':.98,'dtype':'fp32','sample_rate':RATE,'channels':1}
    if any(manifest['voice'].get(k)!=v for k,v in required_voice.items()):
        raise ValueError('Voice policy mismatch')
    checked = set()
    def verify(node):
        if isinstance(node, dict):
            if isinstance(node.get('path'), str) and isinstance(node.get('sha256'), str):
                path = resolve(node['path'])
                if not path.exists():
                    path = resolve(node['path'], gate_path.parent)
                key = (str(path), node['sha256'])
                if key not in checked and (not path.is_file() or digest(path) != node['sha256']):
                    raise ValueError(f'Acceptance evidence changed: {path}')
                checked.add(key)
            for value in node.values():
                verify(value)
        elif isinstance(node, list):
            for value in node:
                verify(value)
    verify(gate.get('inputs', {}))
    approvals = {r['id']:r for r in gate['results']}
    authored = read(DESIGN/'narration.json')
    by_id = {r['id']:r for r in authored}
    sources = {}
    for row in manifest['numbers']+manifest['dialogue']:
        ident = row['id']
        source = resolve(row['path'], manifest_path.parent)
        approval = approvals[ident]
        if (row['spoken_text'] != by_id[ident]['text'] or digest(source) != row['sha256']
                or not approval['accepted'] or approval.get('failures')
                or approval['source_sha256'] != row['sha256']):
            raise ValueError(f'Unapproved or changed utterance {ident}')
        with wave.open(str(source)) as w:
            frames = w.getnframes()
            if (w.getnchannels(),w.getsampwidth(),w.getframerate()) != (1,2,RATE):
                raise ValueError('Expected24kmono16')
        if abs(frames/RATE-row['duration_s']) > 1/RATE:
            raise ValueError('Source duration mismatch')
        sources[ident] = {**row,'path':local(source),'source_path':local(source),
                          'source_sha256':row['sha256'],'sample_frames_24k':frames,'duration_s':frames/RATE}
    if len(sources) != 86 or set(sources) != set(by_id):
        raise ValueError('Incorrect authored speech coverage')
    return authored, sources


def operator_times(event, ctc):
    if ctc['source_sha256'] != event['source_sha256']:
        raise ValueError('CTC is bound to a different source')
    sequence = []
    for token in ctc['tokens']:
        clean = token['token'].replace('ː','').replace('ˈ','').replace('ˌ','').replace('ᵻ','ɪ').replace('ɐ','ə')
        if clean.startswith('<'):
            continue
        for ch in clean:
            if ch.strip() and ch != '|':
                sequence.append((ch,token))
    text = ''.join(x[0] for x in sequence)
    # Explicit acoustic variants: /z/ can devoice before an initial /s/ in
    # "times six/seventy"; intervocalic /d/ may flap; CTC blank frames may
    # split one sustained /l/. All boundaries still come from actual tokens.
    patterns = {'times':r't(?:aɪ|ɑɪ|ai)m[zs]',
                'divided':r'd[ɪəi]v(?:aɪ|ɑɪ|ai)[dɾ][ɪəi]d',
                'equals':r'[iɪeɛə]?kw[əɪ]l+z'}
    selected, after = {}, 0
    for label, pattern in patterns.items():
        candidates = [m for m in re.finditer(pattern,text) if m.start() >= after]
        if not candidates:
            raise ValueError(f'Measured CTC operator not found {event["id"]}/{label}: {text}')
        match = candidates[0]
        a,b = sequence[match.start()][1], sequence[match.end()-1][1]
        selected[label] = {'recognized_sequence':match.group(), 'relative_start_s':a['start_s'],
                           'relative_end_s':b['end_s'], 'start_s':event['start_s']+a['start_s'],
                           'end_s':event['start_s']+b['end_s'],
                           'minimum_token_probability':min(x[1]['probability'] for x in sequence[match.start():match.end()])}
        after = match.end()
    if not selected['times']['end_s'] < selected['divided']['start_s'] < selected['equals']['start_s'] < event['end_s']:
        raise ValueError('CTC operator ordering invalid')
    return dict(method='independent CTC actual operator-token sequences; approximate20ms grid; no proportional fallback',
                source_sha256=event['source_sha256'], operators=selected,
                times_start_s=selected['times']['start_s'],
                divided_start_s=selected['divided']['start_s'], equals_start_s=selected['equals']['start_s'],
                multiply_commit_s=selected['divided']['start_s']-.10)


def make_plan(authored, sources, phonemes):
    events=[];cursor=round(.8*RATE)
    counts = read(DESIGN/'count-lines.json')
    for cue in authored:
        src=sources[cue['id']];end=cursor+src['sample_frames_24k']
        row={**src,'text':cue['text'],'id':cue['id'],'kind':cue['kind'],'index':cue.get('index'),
             'start_sample_24k':cursor,'end_sample_24k':end,'start_s':cursor/RATE,'end_s':end/RATE,
             'translation_ja':cue['japanese'],'visual_cue':cue['visual_cue']}
        if cue['id'].startswith('N'):
            row['value']=counts[cue['index']]['value'];row['decimal_value']=row['value']
        events.append(row);cursor=end+round(cue['following_pause_seconds']*RATE)
    cursor += round(1.2*RATE)
    duration=cursor/RATE;by_id={e['id']:e for e in events}
    ctc={e['id']:e for e in phonemes['results']}
    states=[];changes=[]
    def change(t,mode,n=None,**params):
        changes.append((t,mode,n,params))
    change(0,'intro',None,voice_event_id='I01')
    for e in events:
        if e['id'].startswith('I'):
            mode='intro' if e['id'] in ('I01','I06') else ('seed' if e['id'] in ('I04','I05') else 'intro')
            change(max(0,e['start_s']-.12),mode,0 if mode=='seed' else None,voice_event_id=e['id'])
    change(by_id['N000']['start_s']-.12,'seed',0)
    for ident in ('T000a','T000b','T000c'):
        e=by_id[ident];change(e['start_s']-.12,'coefficient',0,voice_event_id=ident,stage=ident)
    finale_start=by_id['O01']['start_s']-.12
    for n,c in enumerate(counts):
        e=by_id[f'N{n:03}'];prefix=by_id.get(f'E{n:03}')
        cycle_start=prefix['start_s']-.55 if prefix else e['start_s']-.12
        cycle_end=by_id[f'E{n+1:03}']['start_s']-.55 if n<30 else finale_start
        state={**c,'cycle_start_s':cycle_start,'cycle_end_s':cycle_end,
               'formula_start_s':prefix['start_s'] if prefix else None,
               'formula_end_s':prefix['end_s'] if prefix else None,
               'result_display_start_s':e['start_s']-.12,'display_start_s':e['start_s']-.12,
               'voice_start_s':e['start_s'],'voice_end_s':e['end_s'],
               'voice_event_id':e['id'],'formula_event_id':prefix['id'] if prefix else None}
        if prefix:
            timing=operator_times(prefix,ctc[prefix['id']]);prefix['operator_timing']=timing;state['operator_timing']=timing
            state.update(transfer_start_s=cycle_start,transfer_end_s=prefix['start_s'])
            change(cycle_start,'multiply',n,stage='relay',transfer_start_s=cycle_start,transfer_end_s=prefix['start_s'])
            change(prefix['start_s'],'multiply',n,stage='input',operator_timing=timing)
            change(timing['times_start_s'],'multiply',n,stage='times',operator_timing=timing)
            change(timing['multiply_commit_s'],'multiply',n,stage='product',operator_timing=timing)
            change(timing['divided_start_s'],'divide',n,stage='divide',operator_timing=timing)
        change(e['start_s']-.12,'result' if n else 'seed',n,stage='result')
        states.append(state)
    for e in events:
        if not e['id'].startswith('T') or e['id'].startswith('T000'):
            continue
        n=e['index'];mode='result';stage=e['id']
        if n in (1,2):mode='five_paths'
        elif n==3:mode='five_paths' if e['id']=='T003a' else 'first_return'
        elif n==4:mode='equal_groups' if e['id']=='T004a' else 'recurrence'
        elif n in (15,20):mode='result'
        change(e['start_s']-.12,mode,n,stage=stage,replay=True,voice_event_id=e['id'],progress_increment=0)
    change(finale_start,'ending',30,stage='recap',history_indices=list(range(31)))
    change(by_id['O02']['start_s']-.12,'ending',30,stage='wave',voice_event_id='O02')
    changes.sort(key=lambda r:r[0]);visual=[]
    for i,(start,mode,n,params) in enumerate(changes):
        finish=changes[i+1][0] if i+1<len(changes) else duration
        if finish>start:
            visual.append({'mode':mode,'index':n,'start_s':start,'end_s':finish,'params':params})
    plan=dict(schema_version=1,kind='measured-catalan-counting-timeline',episode_id='catalan-counting-001',
              revision_id='catalan-counting-v001',status='measured-accepted-speech',
              fps=FPS,width=1920,height=1080,duration_s=duration,duration_frames=math.ceil(duration*FPS-1e-8),
              frame_count=math.ceil(duration*FPS-1e-8),source_sample_rate_hz=RATE,master_sample_rate_hz=48000,
              master_channels=2,voice_event_count=len(events),events=events,voice_events=events,
              counts=states,counted_states=states,visual_segments=visual,scenes=visual,
              count_index_start=0,count_index_end=30,counted_values=31,integer_encoding='decimal-string',
              voice_sum_s=sum(e['duration_s'] for e in events),
              intro={'start_s':0,'end_s':states[0]['cycle_start_s'],'fade_in_s':.8},
              finale={'start_s':finale_start,'end_s':duration,'fade_last_s':1.8},
              timing={'result_display_lead_s':.12,'formula_prefix_to_result_gap_s':.16,
                      'ordinary_result_end_to_next_formula_start_s':2,'transfer_s':.55,
                      'operator_policy':'actual independently decoded CTC sequences only'},
              bgm=False,sound_effects=[],source_script={'path':local(DESIGN/'narration.json'),'sha256':digest(DESIGN/'narration.json')})
    validate(plan);return plan


def validate(plan):
    events=plan['events'];by={e['id']:e for e in events}
    if len(events)!=86 or len(by)!=86 or len(plan['counts'])!=31:
        raise ValueError('Coverage mismatch')
    for left,right in zip(events,events[1:]):
        if right['start_s']<left['end_s']:
            raise ValueError('Overlapping speech')
        if left['kind']=='formula-prefix' and abs(right['start_s']-left['end_s']-.16)>1e-8:
            raise ValueError('E-to-N gap changed')
        if left['kind'] in ('seed','result') and right['kind']=='formula-prefix' and abs(right['start_s']-left['end_s']-2)>1e-8:
            raise ValueError('Normal2second gap changed')
    for n,state in enumerate(plan['counts']):
        if state['index']!=n or abs(state['voice_start_s']-state['result_display_start_s']-.12)>1e-8:
            raise ValueError('Value order or lead mismatch')
        if int(state['value'])!=math.comb(2*n,n)//(n+1):
            raise ValueError('Independent Catalan value mismatch')
        if n:
            if (state['multiplier']!=4*n-2 or state['divisor']!=n+1
                    or int(state['previous_value'])!=int(plan['counts'][n-1]['value'])
                    or int(state['integer_product'])!=int(state['previous_value'])*state['multiplier']
                    or int(state['integer_product'])%state['divisor']
                    or int(state['integer_product'])//state['divisor']!=int(state['value'])):
                raise ValueError('Arithmetic mismatch')
            timing=state['operator_timing']
            if not (state['formula_start_s']<timing['times_start_s']<timing['multiply_commit_s']
                    <timing['divided_start_s']<timing['equals_start_s']<state['formula_end_s']
                    <state['result_display_start_s']<state['voice_start_s']):
                raise ValueError('Measured operator/display ordering mismatch')
    previous=0
    for segment in plan['visual_segments']:
        if abs(segment['start_s']-previous)>1e-8 or segment['end_s']<=previous:
            raise ValueError('Noncontiguous visual timeline')
        previous=segment['end_s']
    if abs(previous-plan['duration_s'])>1e-8 or plan['duration_s']<480:
        raise ValueError('Incomplete timeline or duration below8minutes')
    return {'passed':True,'events':86,'counts':31,'formula_operators_measured':90,'duration_s':plan['duration_s']}


def deliveries(plan,out):
    captions='\n'.join(f'{i}\n{srt_time(e["start_s"])} --> {srt_time(e["end_s"])}\n{e["text"]}\n' for i,e in enumerate(plan['events'],1))
    for name in ('subtitles.srt','english-captions.srt'):
        (out/name).write_text(captions)
    by={e['id']:e for e in plan['events']}
    marks=[(0,'Welcome to the Ribbon Plaza'),(by['N000']['start_s'],'One empty path'),
           (by['T003a']['start_s'],'Five paths and the first return'),(by['T004a']['start_s'],'Multiply first, then share equally'),
           (by['E016']['start_s'],'Bigger numbers, the same exact rule'),(by['E026']['start_s'],'From trillions to quadrillions'),
           (plan['finale']['start_s'],'All31 Catalan numbers')]
    stamps=[int(t) for t,_ in marks]
    if any(b-a<10 for a,b in zip(stamps,stamps[1:])) or plan['duration_s']-stamps[-1]<10:
        raise ValueError('Chapter spacing below10seconds')
    chapters='\n'.join(f'{chapter(t)} {title}' for t,title in marks)+'\n'
    title='Catalan Numbers: Watch the Formula Work | C0 to C30 | Num-Num Numbers'
    description=('Watch Catalan numbers grow with Tora at the Wind Ribbon Plaza!\n\n'
                 'We count all31 indexed values from C0=1 to C30=3,814,986,502,092,304, keeping both initial ones. '
                 'Ribbon paths show balanced up/down steps that never fall below the starting line. The first-return decomposition explains how smaller choices combine.\n\n'
                 'For n>=1, Cn=C(n-1)×(4n−2)÷(n+1). Every calculation multiplies first, displays the exact integer product, and divides exactly. '
                 'The numerical windows show values; symbolic ribbons do not stand for that many physical objects. '
                 'Natural American English uses the short scale: billion=10^9, trillion=10^12, quadrillion=10^15.\n\n'
                 'No background music or sound effects.\n\nCHAPTERS\n'+chapters+
                 '\nPaspla Studio — Num-Num Numbers\n#CatalanNumbers #LearnNumbers #MathForKids\n')
    for name,text in [('chapters.txt',chapters),('youtube-title.txt',title+'\n'),('youtube-description.txt',description),('upload-details.txt',title+'\n\n'+description)]:
        (out/name).write_text(text)


def calibrated_master(plan,out,ffmpeg,resume=False):
    """Retain the series attempt, then use the final-codec headroom if needed.

    A -2.04dBTP trial gives this all-speech lesson -17.05LUFS. The accepted
    final-codec ceiling is -1.5dBTP; a new -1.85dBTP PCM trial uses part of
    that headroom without any compression, time stretch or source editing.
    Its AAC must independently meet the final ceiling before adoption.
    """
    initial=out/'.work/linear-truepeak-v001'
    if not resume:
        try:
            return mix_truepeak_scalars(plan,out,ffmpeg,balance_rms_dbfs=-19)
        except ValueError as error:
            if not str(error).startswith('Constant-scalar truepeak calibration failed:'):
                raise
    report=read(initial/'level-report.json')
    if report['passed']:
        raise ValueError('No rejected initial master trial exists')
    source_measurements={r['id']:r for r in report['source_measurements']}
    if set(source_measurements)!={e['id'] for e in plan['events']}:
        raise ValueError('Initial source-measurement coverage changed')
    for e in plan['events']:
        r=source_measurements[e['id']]
        if r['source_sha256']!=e['source_sha256'] or digest(resolve(r['base_48k_path']))!=r['base_48k_sha256']:
            raise ValueError('Initial mix evidence/source binding changed')
        e.update(source_peak_dbfs=r['source_peak_dbfs'],source_rms_dbfs=r['source_rms_dbfs'],
                 mix_gain_db=r['final_source_gain_db'],
                 per_source_truepeak_calibration_db=r['additional_constant_gain_db'],aac_codec_calibration_gain_db=0)
    raw=initial/'master-linear-truepeak-balanced.wav'
    with wave.open(str(raw)) as w:
        if (w.getnchannels(),w.getframerate(),w.getsampwidth(),w.getnframes())!=(2,48000,3,round(plan['duration_s']*48000)):
            raise ValueError('Initial linear master has a different format/duration')
    work=out/'.work/linear-truepeak-v002';work.mkdir(parents=True,exist_ok=False)
    before=probe_loudness(ffmpeg,raw)
    gain=min(-16-float(before['input_i']),-1.85-float(before['input_tp']))
    candidate=work/'master-level-test.wav'
    subprocess.run([ffmpeg,'-v','error','-i',str(raw),'-af',f'volume={gain:.12f}dB:precision=double','-c:a','pcm_s24le',str(candidate)],check=True)
    after=probe_loudness(ffmpeg,candidate)
    passed=abs(float(after['input_i'])+16)<=1 and float(after['input_tp'])<=-1.8
    trial={'kind':'constant-linear-master-new-headroom-trial','passed':passed,
           'reason':'Initial -2.04dBTP trial gave -17.05LUFS and failed the +/-1LU target. New -1.85dBTP trial uses part of the final AAC -1.5dBTP headroom. First failure remains unchanged.',
           'first_attempt':{'path':local(initial/'level-report.json'),'sha256':digest(initial/'level-report.json')},
           'source_linear_master':{'path':local(raw),'sha256':digest(raw)},'common_gain_db':gain,
           'before':before,'after':after,'final_AAC_acceptance_pending':True,
           'source_measurements':list(source_measurements.values()),
           'policy':'One constant source gain per whole utterance and one common scalar. No source changes, limiting, compression, denoise, time stretch or timing changes.'}
    save_new(work/'level-report.json',trial)
    if not passed:
        candidate.rename(work/'master-level-rejected.wav')
        raise ValueError('New linear master trial did not meet measured criteria')
    master=out/'master.wav';candidate.rename(master)
    return {'path':local(master),'sha256':digest(master),'sample_rate_hz':48000,'channels':2,
            'sample_width_bits':24,'duration_s':plan['duration_s'],'common_gain_db':gain,'source_gain_db':gain,
            'source_gains':[{'id':e['id'],'source_sha256':e['source_sha256'],'gain_db':e['mix_gain_db']} for e in plan['events']],
            'before':before,'after':after,'master_level_attempt':local(work/'level-report.json'),
            'method':trial['policy'],'final_AAC_acceptance_pending':True}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepare-manifest',type=Path)
    p.add_argument('--takes',type=Path,action='append')
    p.add_argument('--speech-manifest',type=Path,default=OUT/'speech/measurements.json')
    p.add_argument('--speech-gate',type=Path,default=OUT/'speech/speech-acceptance.json')
    p.add_argument('--phonemes',type=Path,default=OUT/'speech/isolated-phonemes.json')
    p.add_argument('--out-dir',type=Path,default=OUT)
    p.add_argument('--ffmpeg',default=str(ROOT/'.venv/bin/ffmpeg'))
    p.add_argument('--plan-only',action='store_true')
    p.add_argument('--resume-master-attempt',action='store_true',help='Resume an explicitly retained failed first level trial after checking its source hashes')
    args=p.parse_args()
    if args.prepare_manifest:
        if not args.takes:raise ValueError('--takes required')
        m=prepare_manifest(args.prepare_manifest.parent,args.prepare_manifest,args.takes)
        print(json.dumps({'numbers':len(m['numbers']),'dialogue':len(m['dialogue'])}));return
    out=args.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    for name in ('timeline.json','master.wav','subtitles.srt','build-record.json'):
        if (out/name).exists():raise FileExistsError(f'Refusing to replace {out/name}')
    authored,sources=accepted_sources(args.speech_manifest.resolve(),args.speech_gate.resolve())
    phonemes=read(args.phonemes)
    if phonemes['source_manifest_sha256']!=digest(args.speech_manifest):raise ValueError('CTC evidence not current')
    plan=make_plan(authored,sources,phonemes)
    plan['speech_manifest']={'path':local(args.speech_manifest),'sha256':digest(args.speech_manifest)}
    plan['speech_acceptance']={'path':local(args.speech_gate),'sha256':digest(args.speech_gate)}
    plan['phonemes']={'path':local(args.phonemes),'sha256':digest(args.phonemes)}
    if not args.plan_only:plan['master_audio']=calibrated_master(plan,out,args.ffmpeg,args.resume_master_attempt)
    save_new(out/'timeline.json',plan);deliveries(plan,out)
    save_new(out/'build-record.json',{'kind':'catalan-measured-build','timeline_sha256':digest(out/'timeline.json'),
              'validation':validate(plan),'master':plan.get('master_audio'),'source_script':plan['source_script'],
              'speech_manifest':plan['speech_manifest'],'speech_acceptance':plan['speech_acceptance'],'phonemes':plan['phonemes']})
    print(json.dumps({'duration_s':plan['duration_s'],'frames':plan['duration_frames'],'events':len(plan['events'])}))


if __name__=='__main__':main()
