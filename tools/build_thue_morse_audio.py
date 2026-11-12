"""Build sample-measured Thue-Morse cue timing and immutable linear speech master.

No speech retiming. A draft is explicitly unaccepted; --gate is required to mix.
Unique source measurements cover two inherited numeral clips and 27 new lines.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import wave

from build_fibonacci_episode import mix_truepeak_scalars

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/thue-morse-counting-v1'
RATE, FPS = 24000, 30
EXPLAIN = {3: 'rules', 15: 'complement', 31: 'substitution', 127: 'binary-parity'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local(path):
    p = Path(path).resolve()
    return p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else str(p)


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def make_plan(manifest_path, gate_path=None):
    manifest_path = Path(manifest_path).resolve()
    m = read(manifest_path)
    authored = read(DESIGN / 'script/speech-script.json')['cues']
    truth = read(DESIGN / 'math/sequence.json')['states']
    rows = {r['id']: r for r in m['numbers'] + m['dialogue']}
    assert len(rows) == 29 and len(authored) == 283 and len(truth) == 256
    if gate_path:
        gate = read(gate_path)
        assert gate['accepted'] and not gate['unresolved']
        assert gate['source_manifest_sha256'] == sha(manifest_path)
        approvals = {r['id']: r for r in gate['results']}
    sources = {}
    for ident, row in rows.items():
        p = (manifest_path.parent / row['path']).resolve()
        assert sha(p) == row['sha256'], ident
        with wave.open(str(p)) as w:
            assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (RATE, 1, 2)
            samples = w.getnframes()
        assert abs(samples / RATE - row['duration_s']) < 1/RATE
        if gate_path:
            a = approvals[ident]
            assert a['accepted'] and not a['failures'] and a['source_sha256'] == row['sha256']
        sources[ident] = {**row, 'path': local(p), 'source_path': local(p),
                          'source_sha256': row['sha256'], 'sample_frames_24k': samples,
                          'duration_s': samples / RATE}
    cursor = 0
    events = []
    for i, cue in enumerate(authored):
        ident = cue['cue_id']
        is_count = cue['kind'] == 'count'
        count_index = int(cue['position_k']) if is_count else None
        value = int(cue['value']) if is_count else None
        if is_count:
            assert truth[count_index]['value'] == value
            src = sources['V' + str(value)]
            gap = 1.2 if count_index == 0 else 2.0
        else:
            src = sources[ident]
            if cue['kind'] == 'intro':
                gap = .6 if ident == 'I001' else .45
            elif cue['kind'] == 'explanation':
                gap = .55 if ident.endswith('a') else .4
            elif cue['kind'] in ('outro', 'ending'):
                gap = 1.0 if ident == 'O001' else .6
            else:
                raise ValueError(('unrecognized cue kind', cue))
        cursor += round(gap * RATE)
        start, end = cursor, cursor + src['sample_frames_24k']
        text = cue['english']
        if is_count:
            assert text.lower().rstrip('.') == src['spoken_text'].lower().rstrip('.')
        else:
            assert text == src['spoken_text']
        event = {**src, 'id': ident, 'cue_id': ident, 'source_id': src['id'],
                 'text': text, 'subtitle_text': text, 'spoken_text': text,
                 'kind': cue['kind'], 'role': 'number' if is_count else 'dialogue',
                 'index': count_index, 'count_index': count_index, 'position_k': count_index,
                 'value': value, 'number': value, 'term_id': cue.get('term_id') or None,
                 'start_s': start/RATE, 'end_s': end/RATE,
                 'start_sample_24k': start, 'end_sample_24k': end,
                 'voice_start_frame': round(start/RATE*FPS),
                 'voice_end_frame': math.ceil(end/RATE*FPS-1e-9),
                 'gap_before_s': gap, 'visual_action': cue['visual_action'],
                 'completion_update': cue['completion_update']}
        if is_count:
            event.update(result_display_s=(start-round(.12*RATE))/RATE,
                         result_display_frame=math.ceil((start/RATE-.12)*FPS-1e-9),
                         progress_commit_s=end/RATE,
                         progress_commit_frame=math.ceil(end/RATE*FPS-1e-9),
                         completed_terms_before=count_index,
                         completed_terms_after=count_index+1, progress_delta=1)
        else:
            event.update(progress_delta=0)
        events.append(event)
        cursor = end
    duration_frames = math.ceil((cursor/RATE+2.)*FPS-1e-9)
    duration = duration_frames/FPS
    by_id = {e['id']: e for e in events}
    states = []
    for k, t in enumerate(truth):
        e = by_id[f'C{k:03}']
        prev = by_id.get(f'C{k-1:03}')
        if k == 0:
            op_start = e['start_s']-.85
        elif k-1 in EXPLAIN:
            op_start = max(x['end_s'] for x in events if x['id'].startswith(f'X{k-1:03}'))
        else:
            op_start = prev['end_s']
        s = {**t, 'count_index': k, 'index': k, 'value': t['value'], 'cue_id': e['id'],
             'cycle_start_s': op_start, 'operation_start_s': op_start,
             'operation_end_s': e['result_display_s'],
             'result_start_s': e['result_display_s'], 'result_display_s': e['result_display_s'],
             'result_voice_start_s': e['start_s'], 'result_voice_end_s': e['end_s'],
             'result_end_s': e['end_s'], 'progress_commit_s': e['end_s'],
             'result_display_frame': e['result_display_frame'],
             'progress_commit_frame': e['progress_commit_frame'],
             'operation_start_frame': math.ceil(op_start*FPS-1e-9),
             'completed_terms_before': k, 'completed_terms_after': k+1,
             'start_s': op_start, 'display_mode': 'learning-strip' if k<16 else ('paired-children' if k<32 else 'growing-loom')}
        states.append(s)
    for a,b in zip(states,states[1:]):
        a['end_s']=a['cycle_end_s']=b['start_s']
    states[-1]['end_s']=states[-1]['cycle_end_s']=by_id['O001']['start_s']-.5
    teaching = []
    for k, kind in EXPLAIN.items():
        lines = [e for e in events if e['id'].startswith(f'X{k:03}')]
        teaching.append({'id': f'X{k:03}', 'scene_id': 'TEACH-'+kind.upper(), 'kind': kind,
                         'after_index': k, 'current_index': k, 'completed_terms': k+1,
                         'start_s': by_id[f'C{k:03}']['end_s']+.25,
                         'speech_start_s': lines[0]['start_s'], 'end_s': lines[-1]['end_s'],
                         'first_cue': lines[0]['id'], 'last_cue': lines[-1]['id'],
                         'cue_ids': [x['id'] for x in lines], 'replay_adds_terms': False})
    scenes = [{'id':'S01-OPENING','scene_id':'S01-OPENING','kind':'opening', 'start_s':0.,
               'end_s':states[0]['start_s'],'current_index':None,'completed_terms':0}]
    start_k = 0
    for j, t in enumerate(teaching):
        sid = f'S{2+j*2:02}-COUNT-{start_k}-{t["after_index"]}'
        scenes.append({'id':sid,'scene_id':sid,'kind':'count', 'start_s':states[start_k]['start_s'],
                       'end_s':t['start_s'],'first_index':start_k,'last_index':t['after_index'],
                       'current_index':start_k})
        sid = f'S{3+j*2:02}-'+t['kind'].upper()
        scenes.append({**t,'id':sid,'scene_id':sid,'kind':'explanation','teaching_kind':t['kind']})
        start_k = t['after_index']+1
    scenes.append({'id':'S10-COUNT-128-255','scene_id':'S10-COUNT-128-255','kind':'count',
                   'start_s':states[128]['start_s'],'end_s':states[-1]['end_s'],
                   'first_index':128,'last_index':255,'current_index':128})
    scenes.append({'id':'S11-FINALE','scene_id':'S11-FINALE','kind':'finale',
                   'start_s':states[-1]['end_s'],'end_s':duration,
                   'current_index':255,'completed_terms':256})
    for event in events:
        scene = next((s for s in scenes if s['start_s'] <= event['start_s'] < s['end_s']),scenes[-1])
        event['scene_id']=scene['scene_id']
    plan = {'schema_version':1, 'kind':'thue-morse-measured-production-timeline',
            'production_ready':bool(gate_path),'speech_accepted':bool(gate_path),
            'fps':FPS,'frame_size':[1920,1080],'size':[1920,1080],
            'sample_rate':RATE,'duration_s':duration,'duration_frames':duration_frames,
            'duration_samples_24k':round(duration*RATE),'voice_sum_s':sum(e['duration_s'] for e in events),
            'events':events,'cues':events,'voice_events':events,
            'states':states,'counted_states':states,'teaching':teaching,'scenes':scenes,'visual_segments':scenes,
            'opening':scenes[0],'finale':scenes[-1],
            'speech_manifest':{'path':local(manifest_path),'sha256':sha(manifest_path)},
            'speech_acceptance':{'path':local(gate_path),'sha256':sha(gate_path)} if gate_path else None,
            'source_script':{'path':local(DESIGN/'script/speech-script.json'),'sha256':sha(DESIGN/'script/speech-script.json')},
            'truth':{'path':local(DESIGN/'math/sequence.json'),'sha256':sha(DESIGN/'math/sequence.json')},
            'voice_profile':m['voice'],'bgm':False,'sound_effects':[],
            'timing_policy':'Exact24k PCM samples; usual result end to next result voice start2s, four explanation boundaries replace2s; no stretching. Result display .12s before voice, progress at voice end.',
            'source_file_reuse':'Two unique accepted numeral WAVs are reused128 times each;27 unique newly generated explanation/intro/outro WAVs.'}
    plan['validation'] = validate(plan)
    return plan


def validate(plan):
    events = plan['voice_events']; by = {e['id']:e for e in events}; states=plan['states']
    assert len(events)==283 and len(by)==283 and len(states)==256
    assert sum(e['progress_delta'] for e in events)==256
    assert plan['duration_s']>=480 and plan['duration_frames']/FPS==plan['duration_s']
    normal = 0
    for k,s in enumerate(states):
        e=by[f'C{k:03}'];assert s['value']==(k.bit_count()%2)
        assert abs(e['start_s']-s['result_display_s']-.12)<1e-8
        assert s['progress_commit_frame']==math.ceil(e['end_s']*FPS-1e-9)
        if k<255 and k not in EXPLAIN:
            assert abs(by[f'C{k+1:03}']['start_s']-e['end_s']-2)<1e-8
            normal+=1
        if k:
            assert s['parent_index']==k//2 and s['parent_value']==states[k//2]['value']
    assert normal==251
    for a,b in zip(events,events[1:]):assert a['end_sample_24k']<=b['start_sample_24k']
    for a,b in zip(plan['scenes'],plan['scenes'][1:]):assert abs(a['end_s']-b['start_s'])<1e-8
    return {'passed':True,'events':283,'counted_terms':256,'explanation_cues':19,
            'normal_two_second_boundaries':251,'explanation_boundaries_after_index':list(EXPLAIN),
            'zeros':sum(s['value']==0 for s in states),'ones':sum(s['value']==1 for s in states),
            'duration_s':plan['duration_s'],'duration_frames':plan['duration_frames']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--gate',type=Path)
    p.add_argument('--draft',type=Path)
    p.add_argument('--out',type=Path)
    p.add_argument('--ffmpeg',default=str(ROOT/'.venv/bin/ffmpeg'))
    a=p.parse_args();plan=make_plan(a.manifest,a.gate)
    if a.draft:
        save(a.draft,plan);print(json.dumps(plan['validation']));return
    assert a.out and a.gate, 'Accepted gate and fresh --out required'
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    assert not any((out/n).exists() for n in ['timeline.json','master.wav','build-record.json'])
    audio=mix_truepeak_scalars(plan,out,a.ffmpeg,-19)
    plan['master']=plan['audio']=plan['master_audio']=audio
    save(out/'timeline.json',plan)
    save(out/'build-record.json',{'kind':'thue-morse-accepted-audio-build',
          'timeline_sha256':sha(out/'timeline.json'),'validation':validate(plan),
          'speech_manifest':plan['speech_manifest'],'speech_acceptance':plan['speech_acceptance'],
          'master':audio,'builder':{'path':local(Path(__file__)),'sha256':sha(__file__)}})
    print(json.dumps({'out':local(out),'duration_s':plan['duration_s'],'frames':plan['duration_frames'],'accepted':True}))


if __name__=='__main__':
    main()
