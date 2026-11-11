"""Build measured binary timing, original chimes, audio and matching delivery files."""
from __future__ import annotations

import argparse
from array import array
from collections import Counter
import json
import math
import os
from pathlib import Path
import shutil
import sys
import uuid
import wave

if __package__:
    from . import build_audio_mix as audio
    from .prepare_binary_episode import INTRO_LINES, FINALE_LINES, make_count_rows
else:
    import build_audio_mix as audio
    from prepare_binary_episode import INTRO_LINES, FINALE_LINES, make_count_rows

ROOT = Path(__file__).resolve().parents[1]
RATE = 48000


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def stamp(seconds):
    return round(seconds * RATE) / RATE


def speech_rows(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    manifest = read(manifest_path)
    if manifest.get('measurement_status') != 'measured':
        raise ValueError('Only actually measured speech may enter production')
    rows = {}
    for row in manifest['numbers'] + manifest['dialogue']:
        identifier = row.get('id') or row.get('speech_id')
        if not identifier:
            identifier = f"binary-{row['spoken_text']}" if 'number' in row else row['spoken_text']
        if identifier in rows:
            raise ValueError(f'Duplicate speech id: {identifier}')
        path = Path(row['path'])
        if not path.is_absolute():
            path = manifest_path.parent / path
        if audio.file_hash(path) != row['sha256']:
            raise ValueError(f'Speech checksum mismatch: {identifier}')
        with wave.open(str(path), 'rb') as clip:
            measured = clip.getnframes() / clip.getframerate()
            if clip.getsampwidth() != 2 or clip.getnchannels() != 1 or clip.getframerate() != 24000:
                raise ValueError(f'Unexpected speech format: {identifier}')
        if abs(measured - row['duration_s']) > 1 / 24000:
            raise ValueError(f'Speech duration mismatch: {identifier}')
        rows[identifier] = dict(row, id=identifier, absolute_path=path.resolve(), duration_s=measured)
    return manifest, rows


def plan(manifest_path):
    manifest, clips = speech_rows(manifest_path)
    by_text = {row['spoken_text']: row for row in clips.values()}
    digits = {token: by_text[token] for token in ('zero', 'one')}
    events = []

    def dialogue(text, start, phase, identifier):
        clip = by_text[text]
        end = stamp(start + clip['duration_s'])
        events.append(dict(type='dialogue', id=identifier, speech_id=clip['id'], text=text,
                           spoken_text=text, start_s=stamp(start), end_s=end, phase=phase,
                           source_sha256=clip['sha256']))
        return end

    intro_end = 0
    for ordinal, (text, nominal_start, _) in enumerate(INTRO_LINES, 1):
        intro_end = dialogue(text, max(nominal_start, intro_end + .2), 'intro', f'I{ordinal:02}')
    count_start = stamp(max(32, intro_end + .8))
    pre, post, gap = .12, .18, .055
    voiced_total = 448 * digits['one']['duration_s'] + 322 * digits['zero']['duration_s']
    base_duration = count_start + voiced_total + 642 * gap + 128 * (pre + post) + 14 + 15
    if base_duration >= 539:
        gap = .04
        over = count_start + voiced_total + 642 * gap + 128 * (pre + post) + 29 - 538
        post = max(.10, post - max(0, over) / 128)
    if base_duration < 481:
        post += (481 - base_duration) / 128
    if post > .55:
        raise ValueError('Measured speech is too short; review the count pacing before rendering')
    cursor = count_start
    counts = []
    checkpoints = read(ROOT / 'design/binary-counting-v1/cue-sheet.json')['checkpoints']
    checkpoint_map = {row['after_decimal_value']: row for row in checkpoints}
    for row in make_count_rows():
        value = row['decimal_value']
        start = stamp(cursor)
        cursor = stamp(start + pre)
        bits = []
        for bit_index, token in enumerate(row['spoken_tokens']):
            clip = digits[token]
            end = stamp(cursor + clip['duration_s'])
            bit = dict(type='digit_voice', id=f'bit-{value:03}-{bit_index}', speech_id=clip['id'],
                       decimal_value=value, display_binary=row['display_binary'], bit_index=bit_index,
                       slot_index=7-len(row['spoken_tokens'])+bit_index, token=token,
                       spoken_text=token, start_s=cursor, end_s=end, source_sha256=clip['sha256'])
            bits.append(bit)
            events.append(bit)
            cursor = stamp(end + (gap if bit_index < len(row['spoken_tokens']) - 1 else 0))
        voice_end = cursor
        cursor = stamp(cursor + post)
        state = dict(type='count', number=value, sequence_index=value, decimal_value=value,
                     display_binary=row['display_binary'], display_slots=row['display_slots'],
                     spoken_tokens=row['spoken_tokens'], spoken_text=' '.join(row['spoken_tokens']) + '.',
                     start_s=start, end_s=cursor, voice_end_s=voice_end, bit_events=bits)
        if value in (2, 4, 8, 16, 32, 64):
            events.append(dict(type='sfx', id='SE_PLACE', start_s=stamp(start+.01),
                               end_s=stamp(start+.09), before_decimal_value=value))
        if value in (7, 31, 63):
            pause_start = cursor
            kind = 'stretch' if value == 31 else 'new-place-comparison'
            if value == 31:
                stretch_end = dialogue("Let's stretch.", pause_start+.2, 'stretch', 'STRETCH')
                ready_start = max(pause_start+5.7, stretch_end+.3)
                ready_end = dialogue("Ready? Let's keep going!", ready_start, 'stretch', 'READY')
                cursor = stamp(max(pause_start+8, ready_end+.5))
            else:
                end = dialogue('A new place is ready.', pause_start+.35, 'place', f'PLACE-{value}')
                cursor = stamp(max(pause_start+3, end+.35))
            events.append(dict(type='pause', kind=kind, after_decimal_value=value,
                               start_s=pause_start, end_s=cursor, held_binary=row['display_binary']))
            state['end_s'] = cursor
        if value in checkpoint_map:
            cp = checkpoint_map[value]
            events.append(dict(type='checkpoint', visual=cp['visual'], after_decimal_value=value,
                               start_s=voice_end, end_s=stamp(voice_end+(cp.get('effect_duration_s') or 1.2))))
        counts.append(state)
        events.append(state)
    finale_start = cursor
    for index, (text, nominal_start, _) in enumerate(FINALE_LINES):
        start = finale_start + nominal_start
        if index:
            start = max(start, outro_end+.25)
        outro_end = dialogue(text, start, 'outro', f'F{index+1:02}')
    duration = stamp(max(finale_start+15, outro_end+2.3))
    counts[-1]['end_s'] = duration
    events.append(dict(type='sfx', id='SE_FINISH', start_s=stamp(finale_start+.08), end_s=stamp(finale_start+1.08)))
    events.append(dict(type='finale', start_s=finale_start, end_s=duration))
    for previous, current in zip(counts, counts[1:]):
        if previous['display_binary'].endswith('1'):
            start = stamp(max(previous['voice_end_s']+.015, current['start_s']-.45))
            events.append(dict(type='carry', from_decimal=previous['number'], to_decimal=current['number'],
                               from_binary=previous['display_binary'], to_binary=current['display_binary'],
                               start_s=start, end_s=stamp(current['start_s']+.10)))
    events.sort(key=lambda event: (event['start_s'], event['type']))
    if not 480 <= duration < 540:
        raise ValueError(f'Measured duration {duration:.3f}s is outside the required 8–9 minute band')
    return dict(schema_version=1, kind='measured-binary-counting-production-timeline',
                episode_id='binary-counting-001', fps=30, width=1920, height=1080,
                measurement_status='measured', production_ready=True, count_start=0, count_end=127,
                duration_s=duration, intro_duration_s=count_start, finale_start_s=finale_start,
                fade_out_start_s=duration-2, events=events,
                speech_manifest=str(Path(manifest_path).resolve()), speech_manifest_sha256=audio.file_hash(manifest_path),
                pacing=dict(pre_speech_s=pre, post_speech_s=post, within_number_gap_s=gap,
                            playback_speed_changed=False, all_durations_measured=True),
                totals=dict(states=128, bit_words=770, one_words=448, zero_words=322),
                audio_policy=dict(bgm=False, opening_silence_s=.8, sfx_relative_voice_rms_db=-18),
                source_preproduction='design/binary-counting-v1/README.txt')


def generate_sfx(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    frames = round(.08 * RATE)
    data = array('h')
    amplitude = 32767 * 10 ** (-24 / 20)
    for index in range(frames):
        envelope = min(1, index/(.008*RATE), (frames-1-index)/(.008*RATE))
        sample = round(amplitude * max(0, envelope) * math.sin(2*math.pi*880*index/RATE))
        data.extend((sample, sample))
    if sys.byteorder != 'little':
        data.byteswap()
    with wave.open(str(out/'SE_PLACE.wav'), 'wb') as stream:
        stream.setparams((2, 2, RATE, 0, 'NONE', 'not compressed'))
        stream.writeframes(data.tobytes())
    source = ROOT/'assets/library/audio/sfx/garden/v001/SE_FINISH.wav'
    if audio.file_hash(source) != '8613212125bb249eadc6b6672d7aeed67af7095ff9660b4de0a3c177d8c291d1':
        raise ValueError('Existing finale chime changed')
    shutil.copyfile(source, out/'SE_FINISH.wav')
    assets = []
    for identifier in ('SE_PLACE', 'SE_FINISH'):
        path = out/f'{identifier}.wav'
        with wave.open(str(path), 'rb') as stream:
            duration = stream.getnframes()/stream.getframerate()
        assets.append(dict(id=identifier, path=path.name, duration_s=duration, sha256=audio.file_hash(path)))
    write_new(out/'generation-spec.json', dict(schema_version=1, kind='original-binary-sfx-library',
              sample_rate=RATE, channels=2, pcm_bits=16, assets=assets,
              method='Original 880Hz sine, 8ms attack/release, no noise or reverb; accepted garden finale chime reused.',
              generator_sha256=audio.file_hash(__file__), third_party_recordings=False))


def mix(timeline_path, manifest_path, acceptance_path, sfx_dir, output, work_base):
    timeline = read(timeline_path)
    _, rows = speech_rows(manifest_path)
    acceptance_receipt = audio.verify_speech_acceptance(acceptance_path, manifest_path)
    accepted = read(acceptance_path)
    accepted_hashes = {row.get('sha256') for row in accepted.get('results', []) if row.get('accepted') is True}
    if any(row['sha256'] not in accepted_hashes for row in rows.values()):
        raise ValueError('Acceptance does not cover every current speech clip')
    output = Path(output).resolve()
    receipt_path = output.with_suffix('.mix.json')
    if output.exists() or receipt_path.exists():
        raise ValueError('Refusing to overwrite a master')
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise ValueError('Registered FFmpeg is required')
    work = Path(work_base)/f'binary-audio-{uuid.uuid4().hex}'
    work.mkdir(parents=True, exist_ok=False)
    sounds = {r['id']: r for r in read(Path(sfx_dir)/'generation-spec.json')['assets']}
    audio_events = [event for event in timeline['events'] if event['type'] in ('digit_voice', 'dialogue', 'sfx')]
    canonical, usage = {}, Counter()
    for event in audio_events:
        sound = event['type'] == 'sfx'
        key = ('sfx' if sound else 'speech', event['id'] if sound else event['speech_id'])
        row = sounds[key[1]] if sound else rows[key[1]]
        path = Path(sfx_dir)/row['path'] if sound else row['absolute_path']
        if audio.file_hash(path) != row['sha256']:
            raise ValueError(f'Audio checksum mismatch: {key}')
        event['_mix_key'] = key
        if key not in canonical:
            converted, stats = audio.canonical_clip(path, work, ffmpeg)
            canonical[key] = dict(path=converted, stats=stats, source_sha256=row['sha256'])
        if abs(canonical[key]['stats']['duration_s']-(event['end_s']-event['start_s'])) > 2/RATE:
            raise ValueError(f'Measured audio mismatch: {key}')
        usage[key] += 1
    audio_events.sort(key=lambda row: row['start_s'])
    for previous, current in zip(audio_events, audio_events[1:]):
        if round(current['start_s']*RATE) < round(previous['end_s']*RATE):
            raise ValueError(f'Audio overlap: {previous["id"]}, {current["id"]}')
    energy = sum(clip['stats']['energy']*usage[key] for key, clip in canonical.items() if key[0]=='speech')
    samples = sum(clip['stats']['sample_count']*usage[key] for key, clip in canonical.items() if key[0]=='speech')
    voice_rms = math.sqrt(energy/samples)/32768
    gains = {}
    for key, clip in canonical.items():
        stats = clip['stats']
        gains[key] = min(voice_rms*10**(-18/20)/stats['rms'], .95*32767/stats['peak']) if key[0]=='sfx' else 1
    premaster = work/'premaster.wav'
    total_frames = round(timeline['duration_s']*RATE)
    with wave.open(str(premaster), 'wb') as stream:
        stream.setparams((2, 2, RATE, 0, 'NONE', 'not compressed'))
        cursor = 0
        for event in audio_events:
            start, end = round(event['start_s']*RATE), round(event['end_s']*RATE)
            audio._silence(stream, start-cursor)
            audio._write_clip(stream, canonical[event['_mix_key']]['path'], end-start, gains[event['_mix_key']])
            cursor = end
        audio._silence(stream, total_frames-cursor)
    first = audio.loudnorm_metrics(audio.run_ffmpeg(ffmpeg, ['-v','info','-i',str(premaster),
              '-af','loudnorm=I=-16:TP=-1.5:LRA=7:print_format=json','-f','null',os.devnull]))
    filter_string = ('loudnorm=I=-16:TP=-1.5:LRA=7:linear=true:print_format=json:'
                     f"measured_I={first['input_i']}:measured_TP={first['input_tp']}:"
                     f"measured_LRA={first['input_lra']}:measured_thresh={first['input_thresh']}:offset={first['target_offset']}")
    second = audio.loudnorm_metrics(audio.run_ffmpeg(ffmpeg, ['-v','info','-n','-i',str(premaster),
               '-af',filter_string,'-ar',str(RATE),'-ac','2','-c:a','pcm_s24le',str(output)]))
    if abs(float(second['output_i'])+16)>1 or float(second['output_tp'])>-.95:
        raise ValueError(f'Master failed loudness targets: {second}')
    with wave.open(str(output), 'rb') as stream:
        if (stream.getnframes(), stream.getframerate(), stream.getnchannels(), stream.getsampwidth()) != (total_frames,RATE,2,3):
            raise ValueError('Master format or sample count mismatch')
    receipt = dict(schema_version=1, kind='binary-rendered-audio-master', duration_s=total_frames/RATE,
                   master_path=str(output), master_sha256=audio.file_hash(output),
                   timeline_sha256=audio.file_hash(timeline_path), speech_manifest_sha256=audio.file_hash(manifest_path),
                   speech_acceptance=acceptance_receipt, audio_event_count=len(audio_events), bgm=False,
                   sfx_gain_relative_to_active_voice_rms_db=-18,
                   normalization=dict(first_pass=first, second_pass=second, target_lufs=-16, target_tp_dbtp=-1.5),
                   clips=[dict(id=key[1],role=key[0],uses=usage[key],source_sha256=clip['source_sha256'],
                               gain_db=20*math.log10(gains[key])) for key,clip in canonical.items()])
    write_new(receipt_path, receipt)
    return receipt


def srt_time(seconds):
    milliseconds = round(seconds*1000)
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}'


def export(timeline_path, out, video_filename):
    timeline = read(timeline_path)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    entries = []
    for event in timeline['events']:
        if event['type']=='dialogue':
            entries.append((event['start_s'], event['end_s'], event['text']))
        elif event['type']=='count':
            entries.append((event['bit_events'][0]['start_s'], event['voice_end_s'], event['spoken_text'].capitalize()))
    entries.sort()
    lines = []
    for index,(start,end,text) in enumerate(entries,1):
        lines.extend([str(index),f'{srt_time(start)} --> {srt_time(end)}',text,''])
    with (out/'english-captions.srt').open('x',encoding='utf-8',newline='\n') as stream:
        stream.write('\n'.join(lines)+'\n')
    counts = {event['number']:event for event in timeline['events'] if event['type']=='count'}
    chapters = [(0,'How to count in binary')]
    for value in (0,8,16,32,64):
        chapters.append((int(counts[value]['start_s']),f"Count from {format(value,'b')} (binary)"))
    chapters.append((int(timeline['finale_start_s']),'We reached 1111111!'))
    chapter_text = '\n'.join(f'{s//60:02}:{s%60:02} {text}' for s,text in chapters)+'\n'
    (out/'chapters.txt').write_text(chapter_text,encoding='utf-8')
    title = 'Count in Binary from 0 to 1111111 | Num-Num Numbers | Paspla Studio'
    description = ('Learn to read binary numbers one digit at a time with our red-beret bear.\n'
                   'We count from binary 0 to 1111111 (decimal 0 to 127), using zero and one.\n'
                   'Follow each highlighted digit, watch new places appear, and take a little stretch break.\n\n'
                   +chapter_text+'\nNum-Num Numbers — Paspla Studio\nhttps://pasplastudio.com/num-num-numbers/\n')
    (out/'upload-details.txt').write_text(f'Title\n{title}\n\nDescription\n{description}\nFiles\nVideo: {video_filename}\nCaptions: english-captions.srt (English)\n',encoding='utf-8')
    write_new(out/'word-timings.json',dict(timeline_sha256=audio.file_hash(timeline_path),
              tokens=[event for event in timeline['events'] if event['type']=='digit_voice']))
    return dict(subtitle_count=len(entries),binary_counts=128,bit_tokens=770)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    p = commands.add_parser('plan'); p.add_argument('--speech-manifest',required=True,type=Path); p.add_argument('--out',required=True,type=Path)
    p = commands.add_parser('sfx'); p.add_argument('--out',required=True,type=Path)
    p = commands.add_parser('mix'); p.add_argument('--timeline',required=True,type=Path); p.add_argument('--speech-manifest',required=True,type=Path)
    p.add_argument('--speech-acceptance',required=True,type=Path); p.add_argument('--sfx-dir',required=True,type=Path); p.add_argument('--out',required=True,type=Path)
    p.add_argument('--work-dir',default='D:/temp',type=Path)
    p = commands.add_parser('export'); p.add_argument('--timeline',required=True,type=Path); p.add_argument('--out',required=True,type=Path); p.add_argument('--video-filename',required=True)
    args = parser.parse_args()
    if args.command=='plan':
        result = plan(args.speech_manifest); write_new(args.out,result)
        print(json.dumps({key:result[key] for key in ('duration_s','intro_duration_s','totals','pacing')}))
    elif args.command=='sfx':
        generate_sfx(args.out); print(str(args.out))
    elif args.command=='mix':
        print(json.dumps(mix(args.timeline,args.speech_manifest,args.speech_acceptance,args.sfx_dir,args.out,args.work_dir)))
    else:
        print(json.dumps(export(args.timeline,args.out,args.video_filename)))


if __name__=='__main__':
    main()
