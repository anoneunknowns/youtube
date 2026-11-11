"""Extend the approved four-base episode to decimal 200 without altering v001."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import json
import math
from pathlib import Path
import shutil
import tempfile

if __package__:
    from . import build_four_base_episode as previous
    from .build_octal_episode import checked_wav, event, local_path, read, write
    from .video_pipeline import english_number
else:
    import build_four_base_episode as previous
    from build_octal_episode import checked_wav, event, local_path, read, write
    from video_pipeline import english_number

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/four-base-counting-001-v002-to-200'
DESIGN = ROOT / 'design/four-base-counting-v1/count-to-200-v002'
PRIOR_RECORD = ROOT / 'design/four-base-counting-v1/production-run-v001.json'
PRIOR_TIMELINE = ROOT / 'output/four-base-counting-001-v001/timeline.json'
RATE = 24000
END_VALUE = 200
TEACHING = {8, 16, 64}


def frames(seconds):
    return round(seconds * RATE)


def seconds(count):
    return count / RATE


def source_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def checked_reference(reference, cache):
    path = source_path(reference['path'])
    key = path.resolve().as_posix()
    if key not in cache:
        cache[key] = previous.audio.file_hash(path)
    if cache[key] != reference['sha256']:
        raise ValueError(f'Changed acceptance evidence: {path}')
    return {'path': local_path(path), 'sha256': cache[key]}


def accepted_numbers(cache):
    """Validate both source gates, every referenced proof, and all 201 PCM clips."""
    sources, gates = {}, []
    library = ROOT / 'assets/library/audio/speech/kokoro-af-heart'
    for version, values in (('binary-v001', [0]), ('v002', range(1, END_VALUE + 1))):
        manifest_path = library / version / 'measurements.json'
        gate_path = manifest_path.with_name('speech-acceptance.json')
        manifest, gate = read(manifest_path), read(gate_path)
        if (gate.get('accepted') is not True or gate.get('kind') != 'hash-bound-speech-acceptance'
                or manifest['measurement_status'] != 'measured'
                or manifest['voice']['sample_rate'] != RATE or gate.get('unresolved')):
            raise ValueError(f'Unaccepted speech library: {gate_path}')
        for reference in gate['inputs'].values():
            if reference is not None:
                checked_reference(reference, cache)
        if gate['inputs']['manifest']['sha256'] != previous.audio.file_hash(manifest_path):
            raise ValueError('Speech gate is bound to another manifest')
        numbers = {row['number']: row for row in manifest['numbers']}
        reviews = {row['number']: row for row in gate['results'] if row['role'] == 'number'}
        for value in values:
            row, review = numbers[value], reviews[value]
            if (review.get('accepted') is not True or review.get('failures')
                    or review['expected_text'] != row['spoken_text']
                    or row['spoken_text'] != ('zero' if value == 0 else english_number(value))
                    or any(row[key] != review[key] for key in ('path', 'sha256', 'duration_s'))):
                raise ValueError(f'Number does not match its source gate: {value}')
            for reference in review['pronunciation_evidence']:
                checked_reference(reference, cache)
            path = manifest_path.parent / row['path']
            count = checked_wav(path, row['sha256'], row['duration_s'], RATE, 1)
            sources[value] = {
                'path': local_path(path), 'sha256': row['sha256'], 'sample_frames': count,
                'duration_s': seconds(count), 'spoken_text': row['spoken_text'],
                'voice_id': manifest['voice']['voice_id'], 'generation_speed': manifest['voice']['generation_speed'],
                'measurement_manifest': local_path(manifest_path),
                'measurement_manifest_sha256': previous.audio.file_hash(manifest_path),
                'acceptance_record': local_path(gate_path), 'acceptance_record_sha256': previous.audio.file_hash(gate_path),
                'pronunciation_decision': review['pronunciation_decision'],
                'pronunciation_evidence': copy.deepcopy(review['pronunciation_evidence']),
            }
        gates.append({'manifest': checked_reference({'path': local_path(manifest_path), 'sha256': previous.audio.file_hash(manifest_path)}, cache),
                      'acceptance': checked_reference({'path': local_path(gate_path), 'sha256': previous.audio.file_hash(gate_path)}, cache)})
    if list(sources) != list(range(END_VALUE + 1)):
        raise ValueError('Number coverage is not exactly 0 through 200')
    return sources, gates


def prior_sources(cache):
    """Reuse the ten reviewed episode lines and three gated closing lines."""
    record, old = read(PRIOR_RECORD), read(PRIOR_TIMELINE)
    for reference in record['files']:
        checked_reference(reference, cache)
    checked_reference(record['timeline'], cache)
    checked_reference(old['speech_measurements'], cache)
    speech = read(ROOT / old['speech_measurements']['path'])
    for reference in speech['review']['evidence']:
        checked_reference(reference, cache)
    adopted = {**speech['new_dialogue'], **speech['reused_dialogue']}
    dialogue = {}
    for item in old['events']:
        if item['type'] != 'dialogue':
            continue
        entry = adopted[item['id']]
        if (entry['sha256'] != item['source_sha256'] or entry['text'] != item['text']
                or entry['path'] != item['source_path']):
            raise ValueError(f'Prior adopted dialogue source differs: {item["id"]}')
        if item['id'] in speech['new_dialogue']:
            if (entry['asr_status'] != 'text-match' or not entry['independent_phoneme_transcript']
                    or previous.dialogue_key(entry['asr_transcript']) != previous.dialogue_key(item['text'])):
                raise ValueError(f'Prior dialogue has no matching review: {item["id"]}')
        else:
            checked_reference({'path': entry['acceptance_record'], 'sha256': entry['acceptance_record_sha256']}, cache)
            gate = read(ROOT / entry['acceptance_record'])
            matches = [row for row in gate['results'] if row['role'] == 'dialogue'
                       and row['sha256'] == entry['sha256'] and row['expected_text'] == item['text'] and row['accepted'] is True]
            if len(matches) != 1:
                raise ValueError(f'Reused closing line is not accepted: {item["id"]}')
            for reference in matches[0]['pronunciation_evidence']:
                checked_reference(reference, cache)
        count = checked_wav(ROOT / entry['path'], entry['sha256'], entry['duration_s'], RATE, 1)
        dialogue[item['id']] = {**copy.deepcopy(entry), 'sample_frames': count,
                                'adoption': 'Unchanged reviewed speech from completed four-base v001.'}
    if len(dialogue) != 13:
        raise ValueError('Expected thirteen unchanged dialogue sources')
    return old, dialogue, speech


def make_plan(old, numbers, dialogue, script_path):
    plan = copy.deepcopy(old)
    states, pauses, events = [], [], []
    old_pauses = {row['after_decimal_value']: row for row in old['pauses']}
    old_events = {row['id']: row for row in old['events']}
    cursor = frames(30)
    for value, source in numbers.items():
        begin, voice_start = cursor, cursor + frames(.12)
        item = event(source, f'N{value:03d}', 'number_voice', 'count', voice_start,
                     source['spoken_text'], decimal_value=value, narration_base=10)
        voice_end = item['end_sample_24k']
        cursor = voice_end + frames(.28 if value == END_VALUE else 1.88)
        if value in TEACHING:
            pause = copy.deepcopy(old_pauses[value])
            pause['estimated_start_s'], pause['estimated_end_s'] = seconds(cursor), seconds(cursor + frames(3))
            pauses.append(pause)
            cursor += frames(3)
        representations = {'binary': format(value, 'b'), 'decimal': str(value),
                           'octal': format(value, 'o'), 'hexadecimal': format(value, 'X')}
        states.append({'decimal_value': value, 'representations': representations,
                       'estimated_display_start_s': seconds(begin), 'estimated_voice_start_s': seconds(voice_start),
                       'estimated_voice_end_s': seconds(voice_end), 'estimated_display_end_s': seconds(cursor),
                       'display_start_s': seconds(begin), 'display_end_s': seconds(cursor),
                       'voice_start_s': seconds(voice_start), 'voice_end_s': seconds(voice_end),
                       'spoken_text': source['spoken_text'], 'source_path': source['path'], 'source_sha256': source['sha256'],
                       'all_rows_update_together': True, 'voice_event_id': item['id']})
        events.append(item)
    finale = copy.deepcopy(old['finale'])
    finale['estimated_start_s'] = seconds(cursor)
    sections = [('intro', 0, plan['intro']['dialogue'])]
    sections += [('pause', frames(p['estimated_start_s']), [p['dialogue']]) for p in pauses]
    sections.append(('finale', cursor, finale['dialogue']))
    for phase, origin, cues in sections:
        for cue in cues:
            source = numbers[10] if cue['id'] == 'I04-TEN' else dialogue[cue['id']]
            start, limit = (origin + frames(t) for t in cue['relative_window_s'])
            fields = {'decimal_value': 10, 'narration_base': 10} if cue['id'] == 'I04-TEN' else {}
            item = event(source, cue['id'], 'number_voice' if fields else 'dialogue', phase, start, cue['text'], **fields)
            if item['end_sample_24k'] > limit:
                raise ValueError(f'Adopted line exceeds editorial window: {cue["id"]}')
            cue.update(actual_start_s=item['start_s'], actual_end_s=item['end_s'])
            if cue['id'] == 'I04-TEN':
                cue['source'] = copy.deepcopy(source)
            events.append(item)
    sound = copy.deepcopy(old_events['SE_FINISH'])
    length = sound['end_sample_24k'] - sound['start_sample_24k']
    checked_wav(ROOT / sound['source_path'], sound['source_sha256'], seconds(length), 48000, 2)
    sound.update(start_sample_24k=cursor + frames(.08), end_sample_24k=cursor + frames(.08) + length,
                 start_s=seconds(cursor + frames(.08)), end_s=seconds(cursor + frames(.08) + length))
    events.append(sound)
    events.sort(key=lambda item: item['start_sample_24k'])
    duration = seconds(cursor + frames(12))
    plan.update(revision_id='four-base-counting-v002-to-200', count_start=0, count_end=END_VALUE,
                kind='measured-four-base-counting-timeline', status='measured-and-reviewed-speech',
                source_script=local_path(script_path), source_script_sha256=previous.audio.file_hash(script_path),
                numeric_sources=numbers, measured_number_clips=numbers, counted_states=states, pauses=pauses,
                finale=finale, events=events, duration_s=duration, duration_s_estimate=duration,
                audio_generated=True, video_generated=False,
                estimate_limit='All existing accepted speech source WAVs measured; no newly generated narration.',
                predecessor={'production_record': local_path(PRIOR_RECORD), 'sha256': previous.audio.file_hash(PRIOR_RECORD),
                             'timeline': local_path(PRIOR_TIMELINE), 'timeline_sha256': previous.audio.file_hash(PRIOR_TIMELINE)})
    plan['timing'].update(counted_values=201, count_voice_duration_s_measured_total=sum(x['sample_frames'] for x in numbers.values()) / RATE,
                          ordinary_two_second_transitions=197, teaching_five_second_transitions=3,
                          count_section_s_without_additional_checks=seconds(cursor - frames(30) - frames(9)))
    plan['sound_effects'] = [{'id': 'SE_FINISH', 'source_path': sound['source_path'], 'source_sha256': sound['source_sha256'],
                              'estimated_start_s': sound['start_s'], 'estimated_end_s': sound['end_s'], 'required': True}]
    validate(plan)
    return plan


def validate(plan):
    events = plan['events']
    if Counter(x['type'] for x in events) != {'number_voice': 202, 'dialogue': 13, 'sfx': 1}:
        raise ValueError('Incorrect full event coverage')
    if len({x['id'] for x in events}) != 216:
        raise ValueError('Duplicate audio event ID')
    if any(a['end_sample_24k'] > b['start_sample_24k'] for a, b in zip(events, events[1:])):
        raise ValueError('Audio events overlap')
    if events[0]['start_sample_24k'] != frames(.8) or events[-1]['end_sample_24k'] > frames(plan['duration_s']):
        raise ValueError('Audio lies outside episode')
    counted = [x for x in events if x['type'] == 'number_voice' and x['phase'] == 'count']
    if [x['decimal_value'] for x in counted] != list(range(201)):
        raise ValueError('Count sequence differs from 0 through 200')
    gaps = Counter()
    for value, (item, state) in enumerate(zip(counted, plan['counted_states'], strict=True)):
        if item['start_sample_24k'] != frames(state['estimated_display_start_s']) + frames(.12):
            raise ValueError(f'Display/speech synchronization differs at {value}')
        for name, base in (('binary', 2), ('decimal', 10), ('octal', 8), ('hexadecimal', 16)):
            if int(state['representations'][name], base) != value:
                raise ValueError(f'Wrong {name} value at {value}')
        if value:
            gap = item['start_sample_24k'] - counted[value - 1]['end_sample_24k']
            if gap != frames(5 if value - 1 in TEACHING else 2):
                raise ValueError(f'Wrong completed-number gap at {value}')
            gaps[gap] += 1
    if gaps != {frames(2): 197, frames(5): 3}:
        raise ValueError('Incorrect completed-number gap coverage')
    if frames(plan['finale']['estimated_start_s']) - counted[-1]['end_sample_24k'] != frames(.28):
        raise ValueError('Incorrect final-value hold')
    if not 480 <= plan['duration_s'] < 900:
        raise ValueError('Requested eight-minute minimum is not met')
    return {'counted_values': 201, 'four_base_representations': 804, 'events': 216,
            'ordinary_two_second_transitions': 197, 'teaching_five_second_transitions': 3,
            'duration_s': plan['duration_s'], 'video_frames': math.ceil(plan['duration_s'] * 30 - 1e-7)}


def write_script(design, old):
    script = design / 'script-and-scenario.txt'
    text = ('Num-Num Numbers — Four Ways to Count to 200\n'
            '第5弾v002：十進0〜200を、2・10・8・16進数で同時に表示する。\n'
            '背景はSeaside Lighthouse、既存の黄色い小鳥を280px高で表示する。\n'
            '音声は十進数の自然な英語読み。既存の採用音声を再利用し、新録・速度変更を行わない。\n'
            '導入30秒、本カウント全201値、締め12秒。通常の発話間隔2秒、8・16・64の確認後は5秒。\n'
            '200の発話終了0.28秒後に締めへ進む。終点は11001000 / 200 / 310 / C8。\n'
            '小鳥の既存3演技（冒頭の羽ばたき、48後のついばみ、96後のホップ）のみを維持する。\n'
            '128は通常カウントとして二進8桁への桁上がりを示し、新しい説明音声は追加しない。\n'
            '音楽なし。締めSE_FINISHを1回のみ。締め10〜12秒にクリーム色へフェードする。\n\n'
            '以下の英語台詞は完成v001と同一。時刻は各場面内の相対編集枠。\n')
    sections = [('INTRO', old['intro']['dialogue'])]
    sections += [(f'AFTER {p["after_decimal_value"]}', [p['dialogue']]) for p in old['pauses']]
    sections += [('FINALE', old['finale']['dialogue'])]
    for label, cues in sections:
        text += f'\n{label}\n'
        for cue in cues:
            text += f'{cue["id"]} | {cue["relative_window_s"][0]:.6f}–{cue["relative_window_s"][1]:.6f} | {cue["text"]}\n'
    with script.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)
    return script


def build(output, design, work_root):
    reserved = ('timeline.json', 'master.wav', 'audio-qa.json', 'speech')
    if any((output / name).exists() for name in reserved) or (design / 'script-and-scenario.txt').exists():
        raise FileExistsError('Choose fresh v002 output and design locations')
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise ValueError('Registered FFmpeg is required')
    cache = {}
    old, dialogue, prior_speech = prior_sources(cache)
    numbers, gates = accepted_numbers(cache)
    design.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    script = write_script(design, old)
    plan = make_plan(old, numbers, dialogue, script)
    speech_dir = output / 'speech'
    speech_dir.mkdir()
    evidence = [{'path': path, 'sha256': checksum} for path, checksum in sorted(cache.items())]
    acceptance = {'schema_version': 1, 'kind': 'hash-bound-existing-speech-reuse', 'accepted': True,
                  'numeric_sources': 201, 'reused_dialogue_sources': 13, 'new_speech_generated': False,
                  'original_production': {'path': local_path(PRIOR_RECORD), 'sha256': previous.audio.file_hash(PRIOR_RECORD)},
                  'source_gates': gates, 'checked_evidence': evidence,
                  'policy': 'Reuse unchanged source-bound reviewed narration; validate WAV hashes, durations, natural decimal text and original gates.',
                  'human_full_listening_claimed': False}
    acceptance_path = speech_dir / 'reuse-acceptance.json'
    write(acceptance_path, acceptance)
    measurements = {'schema_version': 1, 'measurement_status': 'measured', 'numeric_clips': numbers,
                    'new_dialogue': {}, 'reused_dialogue': dialogue,
                    'review': {'method': 'Current source gates and source-bound completed v001 dialogue evidence; no new synthesis.',
                              'human_listening_performed': False, 'prior_dialogue_review': prior_speech['review'],
                              'evidence': [{'kind': 'existing-speech-reuse-acceptance', 'path': local_path(acceptance_path),
                                            'sha256': previous.audio.file_hash(acceptance_path)}]}}
    measurement_path = speech_dir / 'measurements.json'
    write(measurement_path, measurements)
    plan['speech_measurements'] = {'path': local_path(measurement_path), 'sha256': previous.audio.file_hash(measurement_path)}
    timeline_path = output / 'timeline.json'
    write(timeline_path, plan)
    rows = [{'decimal_value': row['decimal_value'], **row['representations'], 'spoken_text': row['spoken_text'],
             'source': numbers[row['decimal_value']]} for row in plan['counted_states']]
    write(design / 'count-lines.json', rows)
    with (design / 'count-lines.tsv').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write('decimal_value\tbinary\tdecimal\toctal\thexadecimal\tspoken_text\n')
        for row in rows:
            stream.write('\t'.join(str(row[key]) for key in ('decimal_value', 'binary', 'decimal', 'octal', 'hexadecimal', 'spoken_text')) + '\n')
    write(design / 'measured-plan.json', plan)
    summary = validate(plan)
    write(design / 'schedule-validation.json', summary)
    print(json.dumps({'schedule_published': local_path(timeline_path), **summary}), flush=True)
    work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fourbase-v002-master-', dir=work_root) as directory:
        work = Path(directory)
        master = work / 'master.wav'
        receipt = previous.mix_balanced(plan, master, work, ffmpeg, {})
        receipt['delivery_probe'] = previous.delivery_probe(master, work, ffmpeg, output)
        receipt.update(kind='four-base-audio-master-qa', schema_version=1,
                       timeline_path=local_path(timeline_path), timeline_sha256=previous.audio.file_hash(timeline_path),
                       speech_measurements_sha256=previous.audio.file_hash(measurement_path), schedule_validation=summary)
        master.rename(output / 'master.wav')
        write(output / 'audio-qa.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=OUTPUT)
    parser.add_argument('--design-dir', type=Path, default=DESIGN)
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    receipt = build(args.out.resolve(), args.design_dir.resolve(), args.work_dir.resolve())
    print(json.dumps({'output': local_path(args.out.resolve()), 'duration_s': receipt['duration_s'],
                      'master_sha256': receipt['master_sha256'], 'loudness_lufs': receipt['loudness_lufs'],
                      'true_peak_dbtp': receipt['true_peak_dbtp'], 'delivery_probe': receipt['delivery_probe']}), flush=True)


if __name__ == '__main__':
    main()
