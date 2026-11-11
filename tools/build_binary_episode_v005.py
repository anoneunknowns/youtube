"""Retain 900ms between bits and give consecutive complete values a two-second gap."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from copy import deepcopy
import json
from pathlib import Path

try:
    from . import build_binary_episode as base
except ImportError:
    import build_binary_episode as base

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT/'output/binary-counting-001-v004-gap900ms/timeline.json'
PRE, POST, GAP, FINAL_POST = .12, 1.88, .90, .28


def revised_plan(baseline_path=DEFAULT_BASELINE):
    baseline_path = Path(baseline_path).resolve()
    original = base.read(baseline_path)
    counts = sorted((event for event in original['events'] if event['type']=='count'), key=lambda event:event['start_s'])
    if [event['decimal_value'] for event in counts] != list(range(128)):
        raise ValueError('Baseline must contain the accepted 128 states')
    pauses = {event['after_decimal_value']:event for event in original['events'] if event['type']=='pause'}
    anchors = {}

    def anchor(old, new):
        key = round(old*48000)
        value = round(new*48000)
        if key in anchors and anchors[key] != value:
            raise ValueError(f'Conflicting retiming anchor at {old}')
        anchors[key] = value

    anchor(0,0)
    cursor = counts[0]['start_s']
    for count in counts:
        value = count['decimal_value']
        anchor(count['start_s'],cursor)
        cursor = base.stamp(cursor+PRE)
        for index,bit in enumerate(count['bit_events']):
            anchor(bit['start_s'],cursor)
            cursor = base.stamp(cursor + bit['end_s']-bit['start_s'])
            anchor(bit['end_s'],cursor)
            if index < len(count['bit_events'])-1:
                cursor = base.stamp(cursor+GAP)
        anchor(count['voice_end_s'],cursor)
        cursor = base.stamp(cursor+(FINAL_POST if value==127 else POST))
        old_post_end = base.stamp(count['voice_end_s']+original['pacing']['post_speech_s'])
        anchor(old_post_end,cursor)
        if value in pauses:
            pause = pauses[value]
            anchor(pause['start_s'],cursor)
            cursor = base.stamp(cursor+pause['end_s']-pause['start_s'])
            anchor(pause['end_s'],cursor)
    anchor(original['finale_start_s'],cursor)
    duration = base.stamp(cursor+original['duration_s']-original['finale_start_s'])
    anchor(original['duration_s'],duration)
    old_ticks = sorted(anchors)

    def retime(value):
        ticks = round(value*48000)
        if ticks in anchors:
            return anchors[ticks]/48000
        index = bisect_right(old_ticks,ticks)-1
        if not 0<=index<len(old_ticks)-1:
            raise ValueError(f'Time outside baseline: {value}')
        left,right = old_ticks[index:index+2]
        mapped = anchors[left]+(ticks-left)*(anchors[right]-anchors[left])/(right-left)
        return round(mapped)/48000

    result = deepcopy(original)
    for event in result['events']:
        for field in ('start_s','end_s','voice_end_s'):
            if field in event:
                event[field] = retime(event[field])
        for bit in event.get('bit_events',[]):
            bit['start_s'],bit['end_s'] = retime(bit['start_s']),retime(bit['end_s'])
    # Carry cues stay near the next count, rather than stretching across the
    # added rest. Background-only cues keep their original short duration.
    count_by_value={event['decimal_value']:event for event in result['events'] if event['type']=='count'}
    original_by_type={}
    for event in original['events']:
        original_by_type.setdefault(event['type'],[]).append(event)
    for event in result['events']:
        if event['type']=='carry':
            previous=count_by_value[event['from_decimal']]
            following=count_by_value[event['to_decimal']]
            event['start_s']=base.stamp(max(previous['voice_end_s']+.015,following['start_s']-.45))
            event['end_s']=base.stamp(following['start_s']+.10)
        elif event['type']=='checkpoint':
            source=next(item for item in original_by_type['checkpoint']
                        if item['after_decimal_value']==event['after_decimal_value'])
            event['end_s']=base.stamp(event['start_s']+source['end_s']-source['start_s'])
    result.update(revision_id='binary-counting-v005',
                  duration_s=duration,finale_start_s=retime(original['finale_start_s']),
                  fade_out_start_s=duration-2,
                  baseline_timeline=baseline_path.relative_to(ROOT).as_posix(),
                  baseline_timeline_sha256=base.audio.file_hash(baseline_path),
                  duration_policy=dict(minimum_s=480,maximum_exclusive_s=1440,reason='user-requested-two-second-between-number-pause'),
                  pacing=dict(pre_speech_s=PRE,post_speech_s=POST,within_number_gap_s=GAP,
                              final_post_speech_s=FINAL_POST,between_number_voice_gap_s=2.0,
                              teaching_pause_additions_s={'7':3,'31':8,'63':3},
                              playback_speed_changed=False,all_durations_measured=True),
                  visual_revision=dict(decimal_display='bear-held-sign',
                                       decimal_value_source='same count event as binary row',
                                       maximum_decimal=127, text_alignment='visible-ink-centered-groups-v003'))
    result['events'].sort(key=lambda event:(event['start_s'],event['type']))
    original_speech = {event['id']:event for event in original['events'] if event['type'] in ('digit_voice','dialogue')}
    for event in result['events']:
        if event['type'] in ('digit_voice','dialogue'):
            source=original_speech[event['id']]
            if abs((event['end_s']-event['start_s'])-(source['end_s']-source['start_s']))>1/48000:
                raise ValueError(f'Speech speed must stay unchanged: {event["id"]}')
    if not 480<=duration<1440:
        raise ValueError(f'Revised duration outside declared band: {duration}')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('plan');p.add_argument('--baseline',type=Path,default=DEFAULT_BASELINE);p.add_argument('--out',type=Path,required=True)
    p=commands.add_parser('mix');p.add_argument('--timeline',type=Path,required=True);p.add_argument('--speech-manifest',type=Path,required=True)
    p.add_argument('--speech-acceptance',type=Path,required=True);p.add_argument('--sfx-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--work-dir',type=Path,default=Path('D:/temp'))
    p=commands.add_parser('export');p.add_argument('--timeline',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--video-filename',required=True)
    args=parser.parse_args()
    if args.command=='plan':
        result=revised_plan(args.baseline);base.write_new(args.out,result)
        print(json.dumps({'duration_s':result['duration_s'],'pacing':result['pacing'],'duration_policy':result['duration_policy']}))
    elif args.command=='mix':
        print(json.dumps(base.mix(args.timeline,args.speech_manifest,args.speech_acceptance,args.sfx_dir,args.out,args.work_dir)))
    else:
        result=base.export(args.timeline,args.out,args.video_filename)
        details=args.out/'upload-details.txt'
        text=details.read_text(encoding='utf-8')
        text=text.replace('Count in Binary from 0 to 1111111 | Num-Num Numbers | Paspla Studio',
                          'Binary Counting with Clear Pauses | Num-Num Numbers | Paspla Studio')
        text=text.replace('Follow each highlighted digit, watch new places appear, and take a little stretch break.',
                          "Listen to each digit with clear pauses. The bear's sign shows the matching decimal value.\nPause for two seconds between complete numbers, with longer breaks for explanations and stretching.\nWatch new places appear and take a little stretch break.")
        details.write_text(text,encoding='utf-8',newline='\n')
        print(json.dumps(result))


if __name__=='__main__':
    main()
