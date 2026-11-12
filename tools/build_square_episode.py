"""Build the square-number episode from hash-bound individually reviewed speech.

The 24kHz PCM frame counts determine the schedule. Speech is never stretched;
the approved planning gaps remain unchanged. A draft plan is clearly unadopted.
"""
from __future__ import annotations

import argparse
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
DESIGN = ROOT / 'design/square-counting-v1'
SPEECH = ROOT / 'output/square-counting-001-v001/speech'
OUT = ROOT / 'output/square-counting-001-v001/audio-build'
RATE, FPS = 24000, 30
CHECKPOINTS = (0, 4, 10, 32)
VIDEO_NAME = 'paspla-studio-square-numbers-0-to-10000-1080p.mp4'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def samples(seconds):
    return round(seconds * RATE)


def authored_rows():
    rows = read(DESIGN / 'timing-plan.json')['events']
    if len(rows) != 215 or len({r['id'] for r in rows}) != 215:
        raise ValueError('The approved plan requires215 unique utterances')
    return rows


def measured_sources(manifest_path, gate_path=None):
    manifest = read(manifest_path)
    if manifest.get('measurement_status') != 'measured':
        raise ValueError('A PCM-measured manifest is required')
    voice = manifest['voice']
    if (voice.get('voice_id'), voice.get('generation_speed'), voice.get('dtype'), voice.get('model_id')) != (
            'af_heart', .98, 'fp32', 'onnx-community/Kokoro-82M-v1.0-ONNX'):
        raise ValueError('Established voice/model/speed policy changed')
    expected = {r['id']: r for r in authored_rows()}
    gate = read(gate_path) if gate_path else None
    approvals = {r['id']: r for r in gate.get('results', [])} if gate else {}
    if gate:
        if (gate.get('accepted') is not True or gate.get('unresolved')
                or gate.get('source_manifest_sha256') != digest(manifest_path)):
            raise ValueError('Accepted gate must bind this exact manifest with no unresolved sources')
        checked = set()

        def proof(node):
            if isinstance(node, dict):
                if isinstance(node.get('path'), str) and isinstance(node.get('sha256'), str):
                    p = resolve(node['path'])
                    if not p.is_file():
                        p = resolve(node['path'], Path(gate_path).parent)
                    key = str(p), node['sha256']
                    if key not in checked:
                        if not p.is_file() or digest(p) != node['sha256']:
                            raise ValueError(f'Changed acceptance evidence: {p}')
                        checked.add(key)
                for value in node.values():
                    proof(value)
            elif isinstance(node, list):
                for value in node:
                    proof(value)
        proof(gate.get('inputs', {}))
    result = {}
    for row in manifest['numbers'] + manifest['dialogue']:
        ident = row['id']
        if ident not in expected or ident in result or row['spoken_text'] != expected[ident]['text']:
            raise ValueError(f'Unexpected/duplicate/changed speech: {ident}')
        path = resolve(row['path'], Path(manifest_path).parent)
        if not path.is_file() or digest(path) != row['sha256']:
            raise ValueError(f'Source checksum mismatch: {ident}')
        with wave.open(str(path)) as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (RATE, 1, 2):
                raise ValueError(f'Expected24kHz mono16 source: {ident}')
            frames = wav.getnframes()
        if abs(frames / RATE - row['duration_s']) > 1 / RATE:
            raise ValueError(f'Mismeasured source: {ident}')
        if gate:
            a = approvals.get(ident, {})
            if a.get('accepted') is not True or a.get('source_sha256') != row['sha256'] or a.get('failures'):
                raise ValueError(f'Individual source not approved: {ident}')
        result[ident] = {**row, 'text': row['spoken_text'], 'path': local(path),
                         'source_path': local(path), 'source_sha256': row['sha256'],
                         'sample_frames_24k': frames, 'duration_s': frames / RATE}
    if set(result) != set(expected) or len(manifest['numbers']) != 101:
        raise ValueError('All101 results and114 dialogue/formula sources are required')
    return result


def operator_times(event, phonemes):
    tokens = phonemes.get(event['id'], {}).get('tokens', [])
    chars = [(ch, t) for t in tokens for ch in t['token'].replace('ː', '').replace('ᵻ', 'ɪ')]
    times = equals = None
    sequence = ''.join(c for c, _ in chars)
    tm = re.search(r'taɪm[zs]', sequence)
    eq = re.search(r'kwəl+z', sequence)
    if tm:
        times = chars[tm.start()][1]['start_s'], chars[tm.end()-1][1]['end_s']
    if eq:
        i = eq.start()
        start = i-1 if i and chars[i-1][0] in ('i', 'ɪ', 'e') else i
        equals = chars[start][1]['start_s']
    if times and equals is not None and 0 <= times[0] < times[1] < equals < event['duration_s']:
        return {'method': 'independent CTC times/equals token sequences; approximate20ms timestamps',
                'a_start_s': event['start_s'], 'times_start_s': event['start_s'] + times[0],
                'b_start_s': event['start_s'] + times[1], 'equals_start_s': event['start_s'] + equals,
                'source_sha256': event['source_sha256']}
    left, right = event['text'].removesuffix(' equals').split(' times ')
    a, b = len(left.replace('-', ' ').split()), len(right.replace('-', ' ').split())
    total = a + b + 2
    return {'method': 'word-count proportional visual estimate within PCM-measured cue; not measured word alignment',
            'a_start_s': event['start_s'], 'times_start_s': event['start_s'] + event['duration_s'] * a / total,
            'b_start_s': event['start_s'] + event['duration_s'] * (a + 1) / total,
            'equals_start_s': event['start_s'] + event['duration_s'] * (a + b + 1) / total,
            'source_sha256': event['source_sha256']}


def make_plan(sources, phonemes=None, adopted=True):
    authored = authored_rows()
    events = []
    cursor = samples(.6)
    for i, cue in enumerate(authored):
        src = sources[cue['id']]
        start, end = cursor, cursor + src['sample_frames_24k']
        n = cue.get('index')
        row = {**src, 'id': cue['id'], 'kind': cue['kind'], 'phase': cue['kind'],
               'role': 'number' if cue['kind'] == 'count' else 'dialogue',
               'index': n, 'n': n, 'value': cue.get('value'), 'decimal_value': cue.get('value'),
               'text': cue['text'], 'spoken_text': cue['text'], 'subtitle_text': cue['text'],
               'cue': cue.get('cue'), 'start_s': start / RATE, 'end_s': end / RATE,
               'start_sample_24k': start, 'end_sample_24k': end}
        if cue['kind'] == 'count':
            row['result_display_s'] = (start - samples(.12)) / RATE
        events.append(row)
        cursor = end
        if cue['kind'] == 'intro':
            cursor += samples(.8 if i+1 == len(authored) or authored[i+1]['kind'] != 'intro' else .3)
        elif cue['kind'] == 'formula_prefix':
            cursor += samples(.16)
        elif cue['kind'] == 'count':
            cursor += samples(.6 if n == 100 else .4 if n in CHECKPOINTS else 2)
        elif cue['kind'] == 'explanation':
            cursor += samples(.4 if n == 100 else 2)
        elif cue['kind'] == 'outro':
            cursor += samples(1.2)
        else:
            raise ValueError(cue['kind'])
    by_id = {e['id']: e for e in events}
    ctc = {r['id']: r for r in (phonemes or {}).get('results', [])}
    for e in events:
        if e['kind'] == 'formula_prefix':
            e['highlight_timing'] = operator_times(e, ctc)
    duration = cursor / RATE
    finale_start = by_id['O01']['start_s'] - .12
    states, teaching, visual = [], [], []

    def segment(mode, start, end, n=None, voice_event_id=None, scene=None, **params):
        if end <= start:
            raise ValueError('Empty or reversed visual segment')
        visual.append({'mode': mode, 'kind': mode, 'scene': scene or mode,
                       'index': n, 'n': n, 'value': n*n if n is not None else None,
                       'voice_event_id': voice_event_id, 'start_s': start, 'end_s': end, 'params': params})
    intros = [e for e in events if e['kind'] == 'intro']
    for i, e in enumerate(intros):
        start = 0 if i == 0 else e['start_s'] - .12
        end = intros[i+1]['start_s'] - .12 if i+1 < len(intros) else by_id['E000']['start_s']
        segment('intro', start, end, voice_event_id=e['id'], scene=e['id'])
    scene_names = {'T000': 'empty', 'T004': 'l-shape', 'T010': 'hundred', 'T032': 'threshold', 'T100': 'maximum'}
    for n in range(101):
        E, N = by_id[f'E{n:03}'], by_id[f'N{n:03}']
        end = by_id[f'E{n+1:03}']['start_s'] if n < 100 else finale_start
        state = {'index': n, 'n': n, 'value': n*n, 'decimal_value': n*n, 'ordinal': n+1,
                 'a': n, 'b': n, 'c': n*n, 'operands': [n,n],
                 'cycle_start_s': E['start_s'], 'cycle_end_s': end, 'start_s': E['start_s'], 'end_s': end,
                 'formula_start_s': E['start_s'], 'formula_end_s': E['end_s'],
                 'expression_start_s': E['start_s'], 'expression_end_s': E['end_s'],
                 'result_start_s': N['result_display_s'], 'result_end_s': N['end_s'],
                 'display_start_s': N['result_display_s'], 'display_end_s': end,
                 'voice_start_s': N['start_s'], 'voice_end_s': N['end_s'],
                 'voice_event_id': N['id'], 'formula_event_id': E['id'],
                 'spoken_text': N['text'], 'highlight_timing': E['highlight_timing'],
                 'progress_commit_s': N['end_s']}
        states.append(state)
        T = by_id.get(f'T{n:03}')
        if T:
            tstart = T['start_s'] - .12
            segment('count', E['start_s'], tstart, n, E['id'])
            segment('teaching', tstart, end, n, T['id'], scene_names[T['id']],
                    count_progress_held=True, look_ahead=n==4, replay=n==32,
                    preview_n=5 if n==4 else None, count_state_index=n)
            teaching.append({'index': n, 'after_index': n, 'n': n, 'value': n*n,
                             'voice_event_id': T['id'], 'scene': scene_names[T['id']],
                             'start_s': tstart, 'end_s': end, 'voice_start_s': T['start_s'],
                             'voice_end_s': T['end_s'], 'count_progress_held': True,
                             'look_ahead': n==4, 'replay': n==32})
        else:
            segment('count', E['start_s'], end, n, E['id'])
    segment('outro', finale_start, duration, 100, 'O01', 'finale')
    plan = {'schema_version': 1, 'kind': 'measured-square-counting-timeline',
            'episode_id': 'square-counting-001', 'revision_id': 'square-counting-v001',
            'status': 'measured-accepted-speech' if adopted else 'measured-unreviewed-candidate-draft-not-production',
            'speech_adopted': adopted, 'fps': FPS, 'width': 1920, 'height': 1080,
            'duration_s': duration, 'duration_frames': math.ceil(duration*FPS-1e-8),
            'count_index_start': 0, 'count_index_end': 100, 'count_start': 0, 'count_end': 10000,
            'counted_values': 101, 'voice_event_count': 215, 'source_sample_rate_hz': RATE,
            'master_sample_rate_hz': 48000, 'master_channels': 2, 'voice_events': events,
            'events': events, 'counted_states': states, 'visual_segments': visual, 'scenes': visual,
            'teaching': teaching, 'intro': {'start_s': 0, 'end_s': states[0]['start_s'], 'fade_in_s': .6},
            'finale': {'start_s': finale_start, 'end_s': duration, 'fade_last_s': 1.2},
            'timing': {'result_display_lead_s': .12, 'formula_prefix_to_result_gap_s': .16,
                       'ordinary_result_end_to_next_formula_start_s': 2,
                       'checkpoint_after_indices': list(CHECKPOINTS), 'final_explanation_index': 100,
                       'fixed_transition_sum_s': 223.16,
                       'highlight_word_boundary_policy': 'independent CTC operator tokens where detected, explicitly labelled proportional estimates otherwise'},
            'voice_sum_s': sum(e['duration_s'] for e in events), 'bgm': False, 'sound_effects': [],
            'source_script': {'path': local(DESIGN/'timing-plan.json'), 'sha256': digest(DESIGN/'timing-plan.json')},
            'renderer_implementation': 'tools/render_square_video.py', 'verifier_implementation': 'tools/verify_square_video.py'}
    validate(plan)
    return plan


def validate(plan):
    events, states = plan['voice_events'], plan['counted_states']
    if len(events) != 215 or len({e['id'] for e in events}) != 215 or len(states) != 101:
        raise ValueError('Wrong utterance/state coverage')
    by_id = {e['id']: e for e in events}
    for n, state in enumerate(states):
        value = sum(range(1,2*n,2))
        E, N = by_id[f'E{n:03}'], by_id[f'N{n:03}']
        if state['index'] != n or state['value'] != value or state['operands'] != [n,n] or N['value'] != value:
            raise ValueError(f'Incorrect square state: {n}')
        if E['text'].split(' times ')[0] != E['text'].removesuffix(' equals').split(' times ')[1]:
            raise ValueError(f'Unequal factors in spoken formula: {n}')
        if abs(N['start_s']-E['end_s']-.16) > 1e-8 or abs(N['start_s']-state['result_start_s']-.12) > 1e-8:
            raise ValueError(f'Changed formula/result timing: {n}')
        if n < 100:
            gap = by_id[f'E{n+1:03}']['start_s']-N['end_s']
            expected = 2 if n not in CHECKPOINTS else 2.4+by_id[f'T{n:03}']['duration_s']
            if abs(gap-expected) > 1e-8:
                raise ValueError(f'Changed count boundary: {n}')
    for a,b in zip(events,events[1:]):
        if a['end_sample_24k'] > b['start_sample_24k']:
            raise ValueError('Overlapping speech')
    previous = 0
    for s in plan['visual_segments']:
        if abs(s['start_s']-previous) > 1e-7 or s['end_s'] <= s['start_s']:
            raise ValueError('Noncontiguous visual schedule')
        previous = s['end_s']
    if abs(previous-plan['duration_s']) > 1e-7 or abs(plan['duration_s']-plan['voice_sum_s']-223.16) > 1e-7:
        raise ValueError('Changed duration or planned fixed intervals')
    if plan['duration_s'] < 480:
        raise ValueError('Actual natural-speed audio is shorter than8min; revise the range before production')
    return {'passed': True, 'voice_events': 215, 'counted_states': 101,
            'ordinary_two_second_boundaries': 96, 'teaching_boundaries': 4,
            'duration_s': plan['duration_s'], 'voice_sum_s': plan['voice_sum_s'],
            'fixed_transition_sum_s': 223.16}


def deliveries(plan, out):
    subs = '\n'.join(f'{i}\n{srt_time(e["start_s"])} --> {srt_time(e["end_s"])}\n{e["text"]}\n'
                     for i,e in enumerate(plan['voice_events'],1))
    for name in ('subtitles.srt','english-captions.srt'):
        with (out/name).open('x',encoding='utf-8') as f:
            f.write(subs)
    states = {s['index']:s for s in plan['counted_states']}
    teachers = {s['index']:s for s in plan['teaching']}
    marks = [(0,'Welcome to the Frozen Lake'), (states[0]['start_s'],'Start with zero squared'),
             (teachers[4]['start_s'],'A row, a column, and one corner'),
             (teachers[10]['start_s'],'Ten by ten makes one hundred'),
             (teachers[32]['start_s'],'The first square above one thousand'),
             (states[100]['start_s'],'One hundred squared: ten thousand'),
             (plan['finale']['start_s'],'101 terms counted; the rule keeps going')]
    stamps = [int(t) for t,_ in marks]
    if stamps[0] != 0 or any(b-a<10 for a,b in zip(stamps,stamps[1:])) or plan['duration_s']-stamps[-1] < 10:
        raise ValueError('Published chapter markers need at least10seconds per chapter')
    chapters = '\n'.join(f'{chapter(t)} {title}' for t,title in marks)+'\n'
    title = 'Square Numbers: Watch the Formula Work | 0² to 100² | Num-Num Numbers'
    description = ('Watch square numbers take shape with our red panda guide at the frozen lake!\n\n'
                   'We use every whole number from 0 through 100 and multiply it by itself: n² = n × n. '
                   'All 101 square numbers are counted in order, from 0 to 10,000. Each expression is read, '
                   'then its result is spoken once in natural American English.\n\n'
                   'Small squares show one tile per unit. Larger labelled diagrams show dimensions, not individually counted tiles. '
                   'The final 100 blocks each stand for 100 unit squares, and the zoom key enlarges one existing block. '
                   'An L-shaped border and a 30+2 area split show how the same rule builds new values.\n\n'
                   'No background music or sound effects.\n\nCHAPTERS\n'+chapters+
                   '\nPaspla Studio — Num-Num Numbers\n#SquareNumbers #LearnNumbers #MathForKids\n')
    for name,text in [('chapters.txt',chapters),('youtube-title.txt',title+'\n'),
                      ('youtube-description.txt',description),('upload-details.txt',title+'\n\n'+description)]:
        with (out/name).open('x',encoding='utf-8') as f:
            f.write(text)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--speech-manifest',type=Path,default=SPEECH/'measurements-selected-v002.json')
    p.add_argument('--speech-gate',type=Path,default=SPEECH/'speech-acceptance.json')
    p.add_argument('--phonemes',type=Path,default=SPEECH/'phonemes-selected-v002.json')
    p.add_argument('--out-dir',type=Path,default=OUT)
    p.add_argument('--ffmpeg',default='ffmpeg')
    p.add_argument('--draft-plan',type=Path,help='Write measured candidate timings only; no adoption or master')
    p.add_argument('--balance-rms-dbfs',type=float,default=-19)
    args = p.parse_args()
    gate = None if args.draft_plan else args.speech_gate.resolve()
    sources = measured_sources(args.speech_manifest.resolve(),gate)
    phonemes = read(args.phonemes) if args.phonemes.is_file() else None
    plan = make_plan(sources,phonemes,adopted=gate is not None)
    plan['speech_manifest'] = {'path': local(args.speech_manifest),'sha256':digest(args.speech_manifest)}
    if args.draft_plan:
        save_new(args.draft_plan,plan)
        print(json.dumps(validate(plan)))
        return
    out = args.out_dir.resolve()
    out.mkdir(parents=True,exist_ok=True)
    for name in ('timeline.json','master.wav','subtitles.srt','build-record.json'):
        if (out/name).exists():
            raise FileExistsError(f'Refusing to replace {out/name}')
    levels = mix_truepeak_scalars(plan,out,args.ffmpeg,args.balance_rms_dbfs)
    plan['audio'] = plan['master'] = plan['master_audio'] = levels
    plan['speech_acceptance'] = {'path':local(args.speech_gate),'sha256':digest(args.speech_gate)}
    if args.phonemes.is_file():
        plan['phoneme_alignment'] = {'path':local(args.phonemes),'sha256':digest(args.phonemes)}
    save_new(out/'timeline.json',plan)
    deliveries(plan,out)
    record = {'kind':'square-production-audio-input-build','status':'accepted-measured-speech-and-master-built',
              'timeline':{'path':local(out/'timeline.json'),'sha256':digest(out/'timeline.json')},
              'speech_manifest':plan['speech_manifest'],'speech_gate':plan['speech_acceptance'],
              'master':levels,'validation':validate(plan),'video_rendered':False,
              'source_audio_retimed_or_overwritten':False,'video_filename':VIDEO_NAME}
    save_new(out/'build-record.json',record)
    print(json.dumps({'duration_s':plan['duration_s'],'frames':plan['duration_frames'],
                      'speech_events':215,'master':levels['after']}))


if __name__ == '__main__':
    main()
