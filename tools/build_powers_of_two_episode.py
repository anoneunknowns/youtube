"""Build the Powers of 2 episode from SHA-bound accepted measured speech.

--draft-plan creates a measured, explicitly unaccepted timeline for renderer
development. Production mixing requires the independently reviewed source gate.
New-only outputs preserve every previous candidate, measurement and review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import wave

try:
    from .build_prime_episode import digest, local, resolve, save_new, srt_time, chapter
    from .build_fibonacci_episode import mix_truepeak_scalars
except ImportError:
    from build_prime_episode import digest, local, resolve, save_new, srt_time, chapter
    from build_fibonacci_episode import mix_truepeak_scalars

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/powers-of-two-counting-v1'
EPISODE = ROOT / 'output/powers-of-two-counting-001-v001'
SPEECH = EPISODE / 'speech'
RATE, FPS = 24000, 30
VIDEO_NAME = 'paspla-studio-powers-of-two-1-to-2-to-the-64th-1080p.mp4'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def frames(time):
    return round(time * FPS)


def authored():
    plan = read(DESIGN / 'sequence.json')
    if plan['term_count'] != 65 or plan['operation_count'] != 64 or len(plan['narration']) != 78:
        raise ValueError('This production recipe is the authored 65-term, 78-cue plan')
    for n, term in enumerate(plan['terms']):
        if term['index'] != n or type(term['value']) is not str or int(term['value']) != 1 << n:
            raise ValueError('Changed mathematical truth')
    return plan


def measurement_manifest(candidates, target):
    """Repackage new candidate metadata; this does not approve the candidates."""
    plan = authored()
    takes = {r['id']: r for r in read(candidates / 'takes.json')}
    if set(takes) != {r['id'] for r in plan['narration']}:
        raise ValueError('Candidate IDs must exactly cover the authored script')
    numbers, dialogue = [], []
    for cue in plan['narration']:
        take = takes[cue['id']]
        if take['text'] != cue['text']:
            raise ValueError('Changed generation text')
        source = Path(take['path']).resolve()
        if digest(source) != take['sha256']:
            raise ValueError('Changed candidate bytes')
        with wave.open(str(source)) as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (RATE, 1, 2):
                raise ValueError('Expected exact 24 kHz mono PCM16 source')
            samples = wav.getnframes()
        row = {**take, 'path': str(source.relative_to(target.parent)),
               'kind': cue['phase'], 'index': cue.get('index'), 'insert_after': cue.get('insert_after'),
               'spoken_text': cue['text'], 'sample_frames_24k': samples, 'duration_s': samples / RATE}
        if cue['phase'] == 'count':
            row.update(number=plan['terms'][cue['index']]['value'], value=plan['terms'][cue['index']]['value'])
            numbers.append(row)
        else:
            dialogue.append(row)
    result = {'schema_version': 1, 'measurement_status': 'measured',
              'adoption_status': 'unreviewed-new-candidates; not accepted until independent hash-bound gate',
              'voice': {'provider': 'local-kokoro', 'model_id': 'onnx-community/Kokoro-82M-v1.0-ONNX',
                        'library': 'kokoro-js@1.2.1', 'voice_id': 'af_heart', 'dtype': 'fp32',
                        'generation_speed': 0.98, 'sample_rate': RATE, 'channels': 1},
              'source_script': {'path': local(DESIGN / 'sequence.json'), 'sha256': digest(DESIGN / 'sequence.json')},
              'candidate_takes': {'path': local(candidates / 'takes.json'), 'sha256': digest(candidates / 'takes.json')},
              'measurement_method': 'Actual accepted-or-candidate PCM frame count divided by 24000; no speech retiming.',
              'numbers': numbers, 'dialogue': dialogue}
    save_new(target, result)
    return result


def measured_sources(manifest_path, gate_path=None):
    manifest = read(manifest_path)
    voice = manifest['voice']
    if manifest.get('measurement_status') != 'measured' or (voice['voice_id'], voice['dtype'], voice['generation_speed']) != ('af_heart', 'fp32', 0.98):
        raise ValueError('Wrong voice profile or unmeasured manifest')
    expected = {r['id']: r for r in authored()['narration']}
    gate = read(gate_path) if gate_path else None
    approvals = {r['id']: r for r in gate.get('results', [])} if gate else {}
    if gate:
        if not gate.get('accepted') or gate.get('unresolved') or gate.get('source_manifest_sha256') != digest(manifest_path):
            raise ValueError('Unaccepted or wrong-source speech gate')

        def evidence(node):
            if isinstance(node, dict):
                if isinstance(node.get('path'), str) and isinstance(node.get('sha256'), str):
                    path = resolve(node['path'])
                    if not path.is_file() or digest(path) != node['sha256']:
                        raise ValueError(f'Acceptance evidence changed: {path}')
                for value in node.values():
                    evidence(value)
            elif isinstance(node, list):
                for value in node:
                    evidence(value)

        evidence(gate.get('inputs', {}))
    result = {}
    for row in manifest['numbers'] + manifest['dialogue']:
        ident = row['id']
        source = resolve(row['path'], manifest_path.parent)
        if ident not in expected or ident in result or row['spoken_text'] != expected[ident]['text']:
            raise ValueError(f'Unexpected, duplicate or changed cue {ident}')
        if digest(source) != row['sha256']:
            raise ValueError(f'Changed source WAV {ident}')
        with wave.open(str(source)) as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (RATE, 1, 2):
                raise ValueError(f'Wrong source format {ident}')
            samples = wav.getnframes()
        if abs(samples / RATE - row['duration_s']) > 1 / RATE:
            raise ValueError(f'Incorrect source duration {ident}')
        if gate:
            approval = approvals.get(ident, {})
            if not approval.get('accepted') or approval.get('failures') or approval.get('source_sha256') != row['sha256']:
                raise ValueError(f'Unapproved exact source {ident}')
        result[ident] = {**row, 'path': local(source), 'source_path': local(source),
                         'source_sha256': row['sha256'], 'sample_frames_24k': samples,
                         'duration_s': samples / RATE, 'text': row['spoken_text']}
    if set(result) != set(expected) or len(manifest['numbers']) != 65:
        raise ValueError('All 78 utterances and 65 result numbers required')
    return result


def make_plan(sources, adopted):
    source = authored()
    rows = source['narration']
    cursor = round(0.8 * RATE)
    events = []
    for i, cue in enumerate(rows):
        row = sources[cue['id']]
        start, end = cursor, cursor + row['sample_frames_24k']
        event = {**row, 'id': cue['id'], 'phase': cue['phase'], 'kind': cue['phase'],
                 'index': cue.get('index'), 'insert_after': cue.get('insert_after'),
                 'value': cue.get('value'), 'decimal_value': cue.get('value'),
                 'text': cue['text'], 'spoken_text': cue['text'], 'subtitle_text': cue['text'],
                 'cue': cue['visual_cue_ja'], 'start_s': start / RATE, 'end_s': end / RATE,
                 'start_sample_24k': start, 'end_sample_24k': end,
                 'voice_start_frame': frames(start / RATE), 'voice_end_frame': frames(end / RATE)}
        if cue['phase'] == 'count':
            event['result_display_s'] = (start - round(0.12 * RATE)) / RATE
            event['result_display_frame'] = frames(event['result_display_s'])
            event['progress_commit_s'] = end / RATE
        events.append(event)
        cursor = end + round(cue['pause_after_s'] * RATE)
    duration = cursor / RATE
    by_id = {e['id']: e for e in events}
    states = []
    teachers = []
    finale_start = by_id['O001']['start_s'] - 0.12
    visual = []
    zero_start = by_id['N000']['result_display_s']
    visual.append({'mode': 'intro', 'start_s': 0, 'end_s': zero_start, 'index': None})
    for n, term in enumerate(source['terms']):
        result = by_id[term['id']]
        operation_start = result['start_s'] - 2 if n else None
        operation_end = result['result_display_s'] if n else None
        cycle_start = operation_start if n else zero_start
        cycle_end = by_id[f'N{n+1:03}']['start_s'] - 2 if n < 64 else finale_start
        state = {**term, 'n': n, 'decimal_value': term['value'],
                 'cycle_start_s': cycle_start, 'cycle_end_s': cycle_end,
                 'start_s': cycle_start, 'end_s': cycle_end,
                 'operation_start_s': operation_start, 'operation_end_s': operation_end,
                 'operation_start_frame': frames(operation_start) if n else None,
                 'operation_end_frame': frames(operation_end) if n else None,
                 'result_start_s': result['result_display_s'], 'result_end_s': result['end_s'],
                 'display_start_s': result['result_display_s'], 'display_end_s': cycle_end,
                 'result_start_frame': result['result_display_frame'],
                 'voice_start_s': result['start_s'], 'voice_end_s': result['end_s'],
                 'voice_event_id': term['id'], 'progress_commit_s': result['end_s'],
                 'progress_commit_frame': math.ceil(result['end_s'] * FPS - 1e-8)}
        states.append(state)
        teacher = by_id.get(f'X{n:03}')
        if teacher:
            teaching_start = teacher['start_s'] - 0.12
            visual.append({'mode': 'count', 'index': n, 'value': term['value'],
                           'start_s': cycle_start, 'end_s': teaching_start})
            visual.append({'mode': 'teaching', 'index': n, 'value': term['value'],
                           'voice_event_id': teacher['id'], 'start_s': teaching_start,
                           'end_s': cycle_end, 'replay': True})
            teachers.append({'after_index': n, 'index': n, 'value': term['value'],
                             'voice_event_id': teacher['id'], 'start_s': teaching_start,
                             'end_s': cycle_end, 'voice_start_s': teacher['start_s'],
                             'voice_end_s': teacher['end_s'], 'replay': True,
                             'count_progress_held': True})
        else:
            visual.append({'mode': 'count', 'index': n, 'value': term['value'],
                           'start_s': cycle_start, 'end_s': cycle_end})
    visual.append({'mode': 'outro', 'index': 64, 'start_s': finale_start, 'end_s': duration})
    plan = {'schema_version': 1, 'kind': 'measured-powers-of-two-timeline',
            'episode_id': 'powers-of-two-counting-001', 'revision_id': 'powers-of-two-counting-v001',
            'status': 'accepted-measured-source-speech' if adopted else 'measured-unaccepted-draft-not-production',
            'speech_adopted': adopted, 'fps': FPS, 'width': 1920, 'height': 1080,
            'duration_s': duration, 'duration_frames': math.ceil(duration * FPS - 1e-8),
            'count_index_start': 0, 'count_index_end': 64, 'count_start': '1',
            'count_end': '18446744073709551616', 'counted_values': 65, 'doubling_operations': 64,
            'voice_event_count': 78, 'source_sample_rate_hz': RATE, 'master_sample_rate_hz': 48000,
            'master_channels': 2, 'voice_sum_s': sum(e['duration_s'] for e in events),
            'voice_events': events, 'events': events, 'counted_states': states,
            'visual_segments': visual, 'scenes': visual, 'teaching': teachers,
            'intro': {'start_s': 0, 'end_s': zero_start, 'fade_in_s': 0.6},
            'finale': {'start_s': finale_start, 'end_s': duration, 'fade_last_s': 1.2},
            'timing': {**source['timing_policy'], 'status': 'measured_pcm_exact',
                       'fixed_transition_sum_s': 134.2,
                       'frame_quantization': 'Audio sample boundaries exact at24kHz; video display events nearest30fps frame; progress commit ceil so never before voice end.'},
            'bgm': False, 'sound_effects': [],
            'source_script': {'path': local(DESIGN / 'sequence.json'), 'sha256': digest(DESIGN / 'sequence.json')},
            'renderer_implementation': 'tools/render_powers_of_two_video.py',
            'integer_policy': 'All mathematical values are decimal strings; exact integer arithmetic only.'}
    validate(plan)
    return plan


def validate(plan):
    events, states = plan['voice_events'], plan['counted_states']
    by_id = {e['id']: e for e in events}
    if len(events) != 78 or len(by_id) != 78 or len(states) != 65:
        raise ValueError('Wrong event or state coverage')
    ordinary = 0
    for n, state in enumerate(states):
        result = by_id[f'N{n:03}']
        if state['index'] != n or type(state['value']) is not str or int(state['value']) != 1 << n or result['value'] != state['value']:
            raise ValueError(f'Wrong exact state {n}')
        if abs(result['start_s'] - state['result_start_s'] - 0.12) > 1e-8:
            raise ValueError('Result lead changed')
        if state['progress_commit_frame'] != math.ceil(result['end_s'] * FPS - 1e-8):
            raise ValueError('Progress must commit on or after actual speech end')
        if n:
            if int(state['previous_value']) * 2 != int(state['value']) or abs(state['operation_end_s'] - state['operation_start_s'] - 1.88) > 1e-8:
                raise ValueError('Incorrect doubling operation')
        elif state['operation_start_s'] is not None:
            raise ValueError('Seed may not perform a doubling operation')
        if n < 64:
            teacher = by_id.get(f'X{n:03}')
            if teacher:
                if abs(teacher['start_s'] - result['end_s'] - 0.3) > 1e-8 or abs(by_id[f'N{n+1:03}']['start_s'] - teacher['end_s'] - 2) > 1e-8:
                    raise ValueError('Incorrect explanatory boundary')
            else:
                ordinary += 1
                if abs(by_id[f'N{n+1:03}']['start_s'] - result['end_s'] - 2) > 1e-8:
                    raise ValueError('Incorrect ordinary2-second boundary')
    for a, b in zip(events, events[1:]):
        if a['end_sample_24k'] > b['start_sample_24k']:
            raise ValueError('Overlapping speech')
    previous = 0
    for scene in plan['visual_segments']:
        if abs(previous - scene['start_s']) > 1e-7 or scene['end_s'] <= scene['start_s']:
            raise ValueError('Noncontiguous or empty visual scene')
        previous = scene['end_s']
    if abs(previous - plan['duration_s']) > 1e-7 or abs(plan['duration_s'] - plan['voice_sum_s'] - 134.2) > 1e-7:
        raise ValueError('Incorrect measured duration or editing sum')
    if plan['duration_s'] < 480:
        raise ValueError('Measured duration below8min; coordinate range extension before production')
    return {'passed': True, 'voice_events': 78, 'counted_states': 65, 'doubling_operations': 64,
            'normal_two_second_boundaries': ordinary, 'teaching_boundaries': len(plan['teaching']),
            'duration_s': plan['duration_s'], 'voice_sum_s': plan['voice_sum_s'], 'fixed_transition_sum_s': 134.2}


def deliveries(plan, out):
    out.mkdir(parents=True, exist_ok=True)
    srt = '\n'.join(f'{i}\n{srt_time(e["start_s"])} --> {srt_time(e["end_s"])}\n{e["text"]}\n'
                    for i, e in enumerate(plan['voice_events'], 1))
    state = {s['index']: s for s in plan['counted_states']}
    marks = [(0, 'Welcome to the Paper & Shadow Doubling Theatre'),
             (state[0]['display_start_s'], 'Begin with one: two to the zero power'),
             (state[6]['cycle_start_s'], 'Labeled groups show whole amounts'),
             (state[10]['display_start_s'], 'The first power above one thousand'),
             (state[20]['display_start_s'], 'Above one million'),
             (state[30]['display_start_s'], 'Above one billion'),
             (state[40]['display_start_s'], 'Above one trillion'),
             (state[50]['display_start_s'], 'Above one quadrillion'),
             (state[60]['display_start_s'], 'Above one quintillion'),
             (state[64]['display_start_s'], 'Two to the sixty-fourth power')]
    chapters = '\n'.join(f'{chapter(t)} {title}' for t, title in marks) + '\n'
    title = 'Powers of 2: Watch the Formula Double | 2⁰ to 2⁶⁴ | Num-Num Numbers'
    description = (
        'Count all 65 powers of two from 2^0=1 through 2^64=18,446,744,073,709,551,616, '
        'with our fairy pitta guide at the Paper & Shadow Doubling Theatre.\n\n'
        'Begin with one. Every step doubles the previous amount. The little exponent records '
        'how many doubling steps we have taken. Paper diamond shapes show exact unit counts '
        'through 32; from 64 onward, labeled groups represent complete values. '
        'Every full result is spoken once in natural American English using the short scale.\n\n'
        'No background music or sound effects.\n\nCHAPTERS\n' + chapters +
        '\nPaspla Studio — Num-Num Numbers\n#PowersOfTwo #LearnNumbers #MathForKids\n')
    for name, text in [('subtitles.srt', srt), ('english-captions.srt', srt),
                       ('chapters.txt', chapters), ('youtube-title.txt', title + '\n'),
                       ('youtube-description.txt', description), ('upload-details.txt', title + '\n\n' + description)]:
        with (out / name).open('x', encoding='utf-8') as stream:
            stream.write(text)
    save_new(out / 'delivery-record.json', {
        'kind': 'measured-powers-of-two-delivery-files',
        'timeline_duration_s': plan['duration_s'], 'subtitles': 78, 'chapter_count': len(marks),
        'source_timeline_inputs': plan['source_script'],
        'files': [{'path': local(p), 'sha256': digest(p)} for p in sorted(out.iterdir()) if p.is_file()]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-manifest', type=Path, help='New candidate folder containing takes.json; writes --speech-manifest')
    parser.add_argument('--speech-manifest', type=Path, default=SPEECH / 'measurements.json')
    parser.add_argument('--speech-gate', type=Path, default=SPEECH / 'speech-acceptance.json')
    parser.add_argument('--phonemes', type=Path, default=SPEECH / 'fresh-phonemes.json')
    parser.add_argument('--out-dir', type=Path, default=EPISODE / 'audio-build')
    parser.add_argument('--delivery-dir', type=Path, default=EPISODE / 'delivery')
    parser.add_argument('--draft-plan', type=Path)
    parser.add_argument('--ffmpeg', default=str(ROOT / '.venv/bin/ffmpeg'))
    parser.add_argument('--balance-rms-dbfs', type=float, default=-19)
    args = parser.parse_args()
    manifest = args.speech_manifest.resolve()
    if args.prepare_manifest:
        measurement_manifest(args.prepare_manifest.resolve(), manifest)
    gate = None if args.draft_plan else args.speech_gate.resolve()
    sources = measured_sources(manifest, gate)
    plan = make_plan(sources, adopted=gate is not None)
    plan['speech_manifest'] = {'path': local(manifest), 'sha256': digest(manifest)}
    if args.draft_plan:
        save_new(args.draft_plan, plan)
        print(json.dumps(validate(plan)))
        return
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    for name in ('timeline.json', 'master.wav', 'build-record.json'):
        if (out / name).exists():
            raise FileExistsError(f'Refusing to overwrite {out / name}')
    levels = mix_truepeak_scalars(plan, out, args.ffmpeg, args.balance_rms_dbfs)
    plan['audio'] = plan['master'] = plan['master_audio'] = levels
    plan['speech_acceptance'] = {'path': local(gate), 'sha256': digest(gate)}
    if args.phonemes.is_file():
        plan['phoneme_alignment'] = {'path': local(args.phonemes), 'sha256': digest(args.phonemes)}
    save_new(out / 'timeline.json', plan)
    deliveries(plan, args.delivery_dir.resolve())
    save_new(out / 'build-record.json', {'kind': 'powers-of-two-production-audio-build',
        'status': 'accepted-measured-speech-and-master-built',
        'timeline': {'path': local(out / 'timeline.json'), 'sha256': digest(out / 'timeline.json')},
        'speech_manifest': plan['speech_manifest'], 'speech_gate': plan['speech_acceptance'],
        'master': levels, 'validation': validate(plan), 'video_rendered': False,
        'source_audio_retimed_or_overwritten': False, 'video_filename': VIDEO_NAME})
    print(json.dumps({'duration_s': plan['duration_s'], 'frames': plan['duration_frames'],
                      'speech_events': 78, 'master': levels['after']}))


if __name__ == '__main__':
    main()
