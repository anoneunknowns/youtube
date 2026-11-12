"""Build Lucas timing, linear speech master and deliveries from accepted PCM.

Every cue retains the approved gap_before_s. --draft-plan writes a visibly
unadopted timing JSON only, so a renderer can be developed during speech review.
Final builds require a current, individual, hash-bound speech acceptance gate.
"""
from __future__ import annotations

import argparse
from array import array
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import wave

try:
    from .build_prime_episode import digest, local, resolve, save_new, srt_time, chapter
    from .build_fibonacci_episode import mix_truepeak_scalars
except ImportError:
    from build_prime_episode import digest, local, resolve, save_new, srt_time, chapter
    from build_fibonacci_episode import mix_truepeak_scalars

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT/'design/lucas-counting-v1'
SPEECH = ROOT/'output/lucas-counting-001-v001/speech'
OUT = ROOT/'output/lucas-counting-001-v001/audio-build'
RATE, FPS = 24000, 30
VIDEO_NAME = 'paspla-studio-lucas-numbers-L0-to-L40-1080p.mp4'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def samples(seconds):
    return round(seconds*RATE)


def sources(manifest_path, gate_path=None):
    manifest = read(manifest_path)
    profile = manifest['voice']
    if manifest.get('measurement_status') != 'measured':
        raise ValueError('PCM-measured sources required')
    if (profile['model_id'],profile['voice_id'],profile['dtype'],profile['generation_speed']) != (
            'onnx-community/Kokoro-82M-v1.0-ONNX','af_heart','fp32',.98):
        raise ValueError('Established voice/model/dtype/speed changed')
    authored = read(DESIGN/'script/speech-script.json')['cues']
    truth = read(DESIGN/'math/lucas-truth.json')['rows']
    expected = {c['id']: c for c in authored}
    gate = read(gate_path) if gate_path else None
    approvals = {r['id']: r for r in gate['results']} if gate else {}
    if gate and (not gate.get('accepted') or gate.get('unresolved')
                 or gate.get('source_manifest_sha256') != digest(manifest_path)):
        raise ValueError('Current accepted gate with no unresolved warnings required')
    if gate:
        def check_evidence(node):
            if isinstance(node,dict):
                if isinstance(node.get('path'),str) and isinstance(node.get('sha256'),str):
                    p = resolve(node['path'])
                    if not p.is_file():
                        p = gate_path.parent/node['path']
                    if not p.is_file() or digest(p) != node['sha256']:
                        raise ValueError(f'Acceptance evidence changed: {p}')
                for child in node.values():
                    check_evidence(child)
            elif isinstance(node,list):
                for child in node:
                    check_evidence(child)
        check_evidence(gate.get('inputs',{}))
    result = {}
    for row in manifest['numbers']+manifest['dialogue']:
        ident = row['id']
        if ident not in expected or ident in result or row['spoken_text'] != expected[ident]['text']:
            raise ValueError(f'Unexpected/duplicate/changed cue: {ident}')
        path = Path(row['path'])
        if not path.is_absolute():
            path = manifest_path.parent/path
        if not path.is_file() or digest(path) != row['sha256']:
            raise ValueError(f'Source hash mismatch: {ident}')
        with wave.open(str(path)) as wav:
            if (wav.getframerate(),wav.getnchannels(),wav.getsampwidth()) != (RATE,1,2):
                raise ValueError('24kHz mono PCM16 source required')
            frames = wav.getnframes()
            pcm = array('h',wav.readframes(frames))
        active = [i for i,v in enumerate(pcm) if abs(v)>=104]
        if not active:
            raise ValueError(f'Empty speech activity: {ident}')
        active_start,active_end = active[0],active[-1]+1
        if abs(frames/RATE-row['duration_s']) > 1/RATE:
            raise ValueError(f'Mismeasured cue: {ident}')
        c = expected[ident]
        if c['kind'] == 'count' and row['number'] != truth[c['n']]['value']:
            raise ValueError(f'Value/index confusion: {ident}')
        if gate:
            approval = approvals.get(ident,{})
            if not approval.get('accepted') or approval.get('failures') or approval.get('source_sha256') != row['sha256']:
                raise ValueError(f'Individual cue not approved: {ident}')
        result[ident] = {**row,'path':local(path),'source_path':local(path),
                         'source_sha256':row['sha256'],'sample_frames_24k':frames,
                         'duration_s':frames/RATE,'source_duration_s':frames/RATE,
                         'source_active_start_sample_24k':active_start,
                         'source_active_end_sample_24k':active_end,
                         'speech_sample_frames_24k':active_end-active_start,
                         'source_head_margin_s':active_start/RATE,
                         'source_tail_margin_s':(frames-active_end)/RATE,
                         'speech_boundary_method':'first/last PCM16 sample with abs(sample)>=104 (~-50dBFS); retained generation trim threshold, no ASR word timestamps'}
    if set(result) != set(expected) or len(result) != 104:
        raise ValueError('All104 approved authored cues required')
    return authored,truth,result


def operator_times(event, phoneme_row):
    tokens = phoneme_row.get('tokens',[])
    chars = [(ch,t) for t in tokens for ch in t['token'].replace('ː','').replace('ᵻ','ɪ').replace(' ','')]
    sequence = ''.join(ch for ch,_ in chars)
    plus = re.search(r'pl[ʌaəæ]s',sequence)
    equals = re.search(r'[iɪe]?kwəl+z',sequence)
    if plus and equals and plus.end() < equals.start():
        b_index = plus.end()
        while b_index < equals.start() and not chars[b_index][0].isalpha():
            b_index += 1
        origin=event['clip_start_s']
        result = {'method':'independent-CTC plus/equals token sequence; approximate20ms acoustic timing, relative to full clip placement',
                  'a_start_s':event['start_s'],
                  'plus_start_s':origin+chars[plus.start()][1]['start_s'],
                  'b_start_s':origin+chars[b_index][1]['start_s'],
                  'equals_start_s':origin+chars[equals.start()][1]['start_s'],
                  'source_sha256':event['source_sha256']}
        if result['a_start_s'] <= result['plus_start_s'] < result['b_start_s'] < result['equals_start_s'] < event['end_s']:
            return result
    a,b = event['text'].removesuffix(' equals').split(' plus ')
    wa,wb = len(a.replace('-',' ').split()),len(b.replace('-',' ').split())
    total = wa+wb+2
    return {'method':'proportional word-count visual estimate within PCM-measured cue; not word alignment',
            'a_start_s':event['start_s'],
            'plus_start_s':event['start_s']+event['duration_s']*wa/total,
            'b_start_s':event['start_s']+event['duration_s']*(wa+1)/total,
            'equals_start_s':event['start_s']+event['duration_s']*(wa+wb+1)/total,
            'source_sha256':event['source_sha256']}


def make_plan(authored,truth,speech,phonemes=None,adopted=True):
    events,cursor = [],0
    ctc = {r['id']:r for r in (phonemes or {}).get('results',[])}
    for cue in authored:
        src = speech[cue['id']]
        start = cursor+samples(cue['gap_before_s'])
        end = start+src['speech_sample_frames_24k']
        clip_start=start-src['source_active_start_sample_24k']
        clip_end=clip_start+src['sample_frames_24k']
        n = cue['n']
        e = {**src,'id':cue['id'],'kind':cue['kind'],'phase':cue['kind'],
             'role':'number' if cue['kind']=='count' else 'dialogue',
             'index':n,'n':n,'value':truth[n]['value'] if n is not None else None,
             'decimal_value':truth[n]['value'] if n is not None else None,
             'scene_id':cue['scene'],'scene':cue['scene'],'direction_ja':cue['direction_ja'],
             'text':cue['text'],'spoken_text':cue['text'],'subtitle_text':cue['text'],
             'gap_before_s':cue['gap_before_s'],'start_s':start/RATE,'end_s':end/RATE,
             'duration_s':(end-start)/RATE,
             'start_sample_24k':start,'end_sample_24k':end,
             'clip_start_s':clip_start/RATE,'clip_end_s':clip_end/RATE,
             'clip_start_sample_24k':clip_start,'clip_end_sample_24k':clip_end,
             'boundary_semantics':'start/end are measured source activity; clip_start/end place the unchanged padded WAV'}
        if e['kind']=='count':
            e['result_display_s']=(start-samples(.12))/RATE
            e['progress_commit_s']=end/RATE
        if e['kind']=='formula_prefix':
            e['highlight_timing']=operator_times(e,ctc.get(e['id'],{}))
        events.append(e)
        cursor=end
    cursor += samples(1.2)
    duration=cursor/RATE
    by_id={e['id']:e for e in events}
    finale_start=by_id['O01']['start_s']-.12
    states,teaching=[],[]
    for row in truth:
        n=row['n'];number=by_id[f'N{n:03}'];prefix=by_id.get(f'E{n:03}')
        start=prefix['start_s'] if prefix else number['result_display_s']
        end=(by_id['N001']['result_display_s'] if n==0 else
             by_id[f'E{n+1:03}']['start_s'] if n<40 else finale_start)
        extras=[e for e in events if e['kind']=='explanation' and e['n']==n]
        transfer_start=transfer_end=transfer_event=None
        transfer_method='none'
        if 2<=n<40:
            transfer_event={2:'X002b',20:'X020b',29:'X029b',38:'X038'}.get(n)
            if transfer_event:
                anchor=by_id[transfer_event]
                transfer_start=anchor['start_s']+.35
                transfer_end=min(transfer_start+1.4,anchor['end_s']-.3)
                transfer_method='during-handoff-explanation'
            else:
                transfer_start=(extras[-1]['end_s'] if extras else number['end_s'])+.25
                transfer_end=transfer_start+1.4
                transfer_method='after-explanation-or-result'
            if not number['end_s'] <= transfer_start < transfer_end <= end:
                raise ValueError(f'Transfer outside result cycle: {n}')
        state={**row,'index':n,'decimal_value':row['value'],'c':row['value'],
               'cycle_start_s':start,'cycle_end_s':end,'start_s':start,'end_s':end,
               'formula_start_s':prefix['start_s'] if prefix else None,
               'formula_end_s':prefix['end_s'] if prefix else None,
               'highlight_timing':prefix.get('highlight_timing') if prefix else None,
               'voice_start_s':number['start_s'],'voice_end_s':number['end_s'],
               'result_start_s':number['result_display_s'],'display_start_s':number['result_display_s'],
               'display_end_s':end,'progress_commit_s':number['end_s'],
               'transfer_start_s':transfer_start,'transfer_end_s':transfer_end,
               'transfer_event_id':transfer_event,'transfer_method':transfer_method,
               'explanation_ids':[e['id'] for e in extras],
               'progress_before':n,'progress_after':n+1}
        states.append(state)
        if extras:
            teaching.append({'after_index':n,'after_value':row['value'],
                             'scene_ids':[e['scene_id'] for e in extras],
                             'event_ids':[e['id'] for e in extras],
                             'start_s':extras[0]['start_s']-.12,'end_s':extras[-1]['end_s'],
                             'progress':n+1,'increment_progress':False})
    visual=[]
    intro_end=states[0]['cycle_start_s']
    visual.append({'mode':'intro','scene':'intro','start_s':0,'end_s':intro_end,'n':None})
    for s in states:
        visual.append({'mode':'seed' if s['n']<2 else 'count-cycle','scene':'seed' if s['n']<2 else 'count-cycle',
                       'start_s':s['start_s'],'end_s':s['end_s'],'n':s['n'],'index':s['n'],'value':s['value'],
                       'params':{'result_commit_s':s['result_start_s'],'progress_commit_s':s['progress_commit_s'],
                                 'explanation_ids':s['explanation_ids'],'transfer_start_s':s['transfer_start_s'],
                                 'transfer_end_s':s['transfer_end_s']}})
    visual.append({'mode':'history','scene':'history','start_s':finale_start,'end_s':duration,'n':40})
    plan={'schema_version':1,'kind':'measured-lucas-counting-timeline','episode_id':'lucas-counting-001',
          'revision_id':'lucas-counting-v001','status':'measured-accepted-speech' if adopted else 'draft-measured-unaccepted-speech',
          'production_audio_accepted':adopted,'width':1920,'height':1080,'fps':FPS,
          'duration_s':duration,'duration_frames':math.ceil(duration*FPS-1e-8),
          'count_start':2,'count_end':228826127,'first_index':0,'last_index':40,
          'counted_values':41,'addition_count':39,'voice_event_count':104,
          'source_sample_rate_hz':RATE,'master_sample_rate_hz':48000,'master_channels':2,
          'events':events,'voice_events':events,'counted_states':states,'teaching':teaching,
          'visual_segments':visual,'scenes':visual,
          'intro':{'start_s':0,'end_s':intro_end,'fade_in_s':.6},
          'finale':{'start_s':finale_start,'end_s':duration,'fade_last_s':1.2},
          'timing':{'display_lead_s':.12,'ordinary_result_to_next_formula_gap_s':2,
                    'formula_to_result_gap_s':.16,'progress_update':'count utterance end only',
                    'event_boundary':'first/last PCM activity at abs(sample)>=104/32768 (~-50dBFS), sample exact',
                    'clip_boundary':'full original WAV placement, including retained head/tail margins; separate from speech/subtitle boundaries',
                    'limitations':'Activity threshold is a physical signal definition, not an assertion of exact linguistic word boundaries. CTC operator times have approximate20ms resolution.',
                    'source_audio_retimed':False,'approved_gap_before_s_preserved':True},
          'count_voice_sum_s':sum(e['duration_s'] for e in events if e['kind']=='count'),
          'speech_sum_s':sum(e['duration_s'] for e in events),
          'source_pcm_clip_sum_s':sum(e['source_duration_s'] for e in events),
          'fixed_gap_total_s':sum(c['gap_before_s'] for c in authored)+1.2,
          'bgm':False,'sound_effects':[],
          'source_script':{'path':local(DESIGN/'script/speech-script.json'),'sha256':digest(DESIGN/'script/speech-script.json')},
          'source_truth':{'path':local(DESIGN/'math/lucas-truth.json'),'sha256':digest(DESIGN/'math/lucas-truth.json')}}
    validate(plan)
    return plan


def validate(plan):
    events=plan['voice_events'];states=plan['counted_states']
    counts=[e for e in events if e['kind']=='count'];formulae=[e for e in events if e['kind']=='formula_prefix']
    assert len(events)==104 and len({e['id'] for e in events})==104
    assert [e['n'] for e in counts]==list(range(41))
    assert [e['n'] for e in formulae]==list(range(2,41))
    assert [s['value'] for s in states[:3]]==[2,1,3]
    for s in states:
        n=s['n']
        assert s['ordinal']==n+1 and abs(s['voice_start_s']-s['result_start_s']-.12)<1e-8
        if n>=2:
            assert s['a']+s['b']==s['value']
            assert abs(s['voice_start_s']-s['formula_end_s']-.16)<1e-8
    for a,b in zip(events,events[1:]):
        assert a['end_sample_24k']<=b['start_sample_24k']
        assert abs((b['start_sample_24k']-a['end_sample_24k'])/RATE-b['gap_before_s'])<1/RATE
        assert a['clip_end_sample_24k']<=b['clip_start_sample_24k']
    for e in events:
        assert e['start_sample_24k']==e['clip_start_sample_24k']+e['source_active_start_sample_24k']
        assert e['end_sample_24k']==e['clip_start_sample_24k']+e['source_active_end_sample_24k']
    assert len([s for s in states if s['transfer_start_s'] is not None])==38
    assert plan['duration_s']>=480
    assert all(abs(a['end_s']-b['start_s'])<1e-8 for a,b in zip(plan['visual_segments'],plan['visual_segments'][1:]))
    assert abs(plan['visual_segments'][-1]['end_s']-plan['duration_s'])<1e-8
    return {'passed':True,'speech_cues':104,'counted_terms':41,'additions':39,'transfers':38,
            'duration_s':plan['duration_s'],'minimum_eight_minutes_pass':True,
            'scope':'Source-based timeline validation, not finished-video observation'}


def deliveries(plan,out):
    subs=[]
    for i,e in enumerate(plan['voice_events'],1):
        subs.append(f'{i}\n{srt_time(e["start_s"])} --> {srt_time(e["end_s"])}\n{e["text"]}\n')
    for name in ('subtitles.srt','english-captions.srt'):
        (out/name).write_text('\n'.join(subs),encoding='utf-8')
    by_id={e['id']:e for e in plan['events']};states=plan['counted_states']
    marks=[(0,'Welcome to the sunny clock tower'),
           (states[0]['display_start_s'],'Two starting values: 2, then 1'),
           (states[2]['start_s'],'The formula begins: 2 + 1 = 3'),
           (by_id['X005a']['start_s'],'Eleven and the first carry'),
           (by_id['X010a']['start_s'],'47 + 76: carrying by place'),
           (by_id['X020a']['start_s'],'Longer numbers, the same rule'),
           (by_id['X029a']['start_s'],'Into the millions'),
           (by_id['X039']['start_s'],'The first term above 100 million'),
           (plan['finale']['start_s'],'All 41 Lucas terms')]
    stamps=[int(t) for t,_ in marks]
    if stamps[0]!=0 or any(b-a<10 for a,b in zip(stamps,stamps[1:])) or plan['duration_s']-stamps[-1]<10:
        raise ValueError('Published chapter timestamps must give at least10seconds each')
    chapters='\n'.join(f'{chapter(t)} {title}' for t,title in marks)+'\n'
    title='Lucas Numbers: Watch the Formula Work | 2 to 228,826,127 | Num-Num Numbers'
    description=("Watch Lucas numbers come to life with our meerkat guide inside a sunny clock tower!\n\n"
                 "We start at L0 = 2, then L1 = 1. For n >= 2, Ln = L(n-2) + L(n-1): the two latest values make the next value. We count all 41 indexed terms through L40 = 228,826,127, the first term above 200 million. L39 = 141,422,324 is the first term above 100 million. Two starting values and 39 additions make 41 terms.\n\n"
                 "Each formula combines the two latest values; its new result then joins the next input pair. Close views show exact small quantities and place-value carrying. For large numbers, labeled windows show values instead of millions of individual counters. The final history keeps every term in sequence order, including the opening decrease from 2 to 1.\n\n"
                 "Natural American English reads each expression prefix and its result. No background music or sound effects.\n\nCHAPTERS\n"
                 +chapters+'\nPaspla Studio — Num-Num Numbers\n#LucasNumbers #LearnNumbers #MathForKids\n')
    for name,text in [('chapters.txt',chapters),('youtube-title.txt',title+'\n'),
                      ('youtube-description.txt',description),('upload-details.txt',title+'\n\n'+description)]:
        (out/name).write_text(text,encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--speech-manifest',type=Path,default=SPEECH/'measurements-selected-v003.json')
    p.add_argument('--speech-gate',type=Path,default=SPEECH/'speech-acceptance.json')
    p.add_argument('--phonemes',type=Path,default=SPEECH/'isolated-phonemes-selected-v003.json')
    p.add_argument('--out-dir',type=Path,default=OUT)
    p.add_argument('--ffmpeg',default='ffmpeg')
    p.add_argument('--draft-plan',action='store_true')
    p.add_argument('--codec-corrections',type=Path)
    a=p.parse_args();out=a.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    name='timeline-draft.json' if a.draft_plan else 'timeline.json'
    if (out/name).exists() or (not a.draft_plan and (out/'master.wav').exists()):
        raise FileExistsError('Use a new output folder to preserve existing inputs/evidence')
    authored,truth,selected=sources(a.speech_manifest.resolve(),None if a.draft_plan else a.speech_gate.resolve())
    phonemes=read(a.phonemes) if a.phonemes.exists() else None
    if not a.draft_plan and phonemes is None:
        raise ValueError('Final build requires fresh independent CTC evidence')
    if phonemes:
        if phonemes.get('source_manifest_sha256') != digest(a.speech_manifest):
            raise ValueError('CTC evidence belongs to a different source manifest')
        ctc_by={r['id']:r for r in phonemes['results']}
        if set(ctc_by)!=set(selected) or any(ctc_by[k]['source_sha256']!=r['source_sha256'] for k,r in selected.items()):
            raise ValueError('CTC coverage/source hashes changed')
    plan=make_plan(authored,truth,selected,phonemes,not a.draft_plan)
    plan['speech_manifest']={'path':local(a.speech_manifest),'sha256':digest(a.speech_manifest)}
    if not a.draft_plan:
        plan['speech_acceptance']={'path':local(a.speech_gate),'sha256':digest(a.speech_gate)}
        if a.phonemes.exists():
            plan['phonemes']={'path':local(a.phonemes),'sha256':digest(a.phonemes)}
        corrections=read(a.codec_corrections) if a.codec_corrections else None
        clip_plan=copy.deepcopy(plan)
        for event in clip_plan['voice_events']:
            event['start_sample_24k']=event['clip_start_sample_24k']
            event['end_sample_24k']=event['clip_end_sample_24k']
        master=mix_truepeak_scalars(clip_plan,out,a.ffmpeg,-19,corrections)
        for event,mixed in zip(plan['voice_events'],clip_plan['voice_events']):
            for key in ('source_peak_dbfs','source_rms_dbfs','mix_gain_db','per_source_truepeak_calibration_db','aac_codec_calibration_gain_db'):
                if key in mixed:
                    event[key]=mixed[key]
        master['source_placement_boundary']='clip_start_sample_24k, distinct from speech start_sample_24k'
        plan.update(master=master,master_audio=master,audio=master)
    save_new(out/name,plan)
    if not a.draft_plan:
        deliveries(plan,out)
        save_new(out/'build-record.json',{'kind':'lucas-measured-audio-input-build',
                 'status':'individual-accepted-speech-and-linear-master-built',
                 'timeline':{'path':local(out/name),'sha256':digest(out/name)},'master':plan['master_audio'],
                 'source_manifest':plan['speech_manifest'],'speech_acceptance':plan['speech_acceptance'],
                 'validation':validate(plan),'video_rendered':False,'video_filename':VIDEO_NAME,
                 'speech_stretched_or_originals_overwritten':False})
    print(json.dumps({'duration_s':plan['duration_s'],'frames':plan['duration_frames'],
                      'events':len(plan['events']),'draft':a.draft_plan,'out':str(out/name)},ensure_ascii=False))


if __name__=='__main__':
    main()
