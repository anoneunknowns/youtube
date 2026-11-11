"""Verify completed-value holds and atomic binary/decimal visual commits."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import time

from PIL import Image,ImageDraw

try:
    import verify_binary_visual_v003 as visual
except ModuleNotFoundError:
    from tools import verify_binary_visual_v003 as visual

TRANSITIONS=(0,1,3,7,14,15,31,45,63,64,126)
SPECIALS=(7,31,63)


def first_frame_at_or_after(seconds,fps=30):
    """Use the renderer's actual idx/fps comparison, including float boundaries."""
    index=math.ceil(seconds*fps-1e-9)
    while index/fps<seconds:index+=1
    while index>0 and (index-1)/fps>=seconds:index-=1
    return index


def hold_samples(timeline):
    counts=sorted((event for event in timeline['events'] if event['type']=='count'),key=lambda event:event['start_s'])
    if [event['decimal_value'] for event in counts]!=list(range(128)):
        raise ValueError('Expected all128 values exactly once')
    transition_rows=[]
    for previous,current in zip(counts,counts[1:]):
        gap=current['bit_events'][0]['start_s']-previous['voice_end_s']
        special=previous['decimal_value'] in SPECIALS
        if (not special and abs(gap-2)>1/48000) or (special and gap<2-1/48000):
            raise ValueError(f'Completed-value voice gap differs at {previous["decimal_value"]}: {gap}')
        transition_rows.append({'from_decimal':previous['decimal_value'],'to_decimal':current['decimal_value'],
                                'previous_voice_end_s':previous['voice_end_s'],
                                'next_visual_commit_s':current['start_s'],
                                'next_first_voice_s':current['bit_events'][0]['start_s'],
                                'voice_gap_s':gap,'special_teaching_or_stretch_pause':special})
    gaps=[b['start_s']-a['end_s'] for count in counts for a,b in zip(count['bit_events'],count['bit_events'][1:])]
    if len(gaps)!=642 or any(abs(gap-.9)>1/48000 for gap in gaps):
        raise ValueError('The within-value0.9s pauses must be preserved')
    samples=[]
    for value in TRANSITIONS:
        previous,current=counts[value],counts[value+1]
        first_new=first_frame_at_or_after(current['start_s'])
        first_voice=first_frame_at_or_after(current['bit_events'][0]['start_s'])
        held_index=round((previous['voice_end_s']+1)*30)
        if not previous['voice_end_s']<held_index/30<current['start_s']:
            raise ValueError('The representative old-value sample is outside the silent hold')
        for label,index,expected,focus in (
            ('hold-plus-1s',held_index,value,None),
            ('last-old-frame',first_new-1,value,None),
            ('first-new-frame',first_new,value+1,None),
            ('first-new-voice',first_voice,value+1,7-len(format(value+1,'b'))),
        ):
            samples.append({'label':label,'from_decimal':value,'to_decimal':value+1,
                            'frame_index':index,'time_s':index/30,
                            'expected_decimal':expected,'expected_focus_slot':focus})
    return transition_rows,samples


def verify(video,timeline_path,output_dir,report_path,ffmpeg):
    started=time.perf_counter()
    if output_dir.exists() or report_path.exists():
        raise ValueError('Refusing to overwrite a previous hold inspection')
    timeline=json.loads(timeline_path.read_text(encoding='utf-8-sig'))
    transitions,samples=hold_samples(timeline)
    by_index={row['frame_index']:row for row in samples}
    if len(by_index)!=len(samples):raise ValueError('Representative hold frames must be distinct')
    output_dir.mkdir(parents=True,exist_ok=False)
    templates={str(value):visual.normalized_glyph(visual.independent_decimal_mask(value)) for value in range(10)}
    rows=[]
    failures=[]
    sheet=Image.new('RGB',(1920,math.ceil(len(samples)/4)*315),visual.CREAM)
    draw=ImageDraw.Draw(sheet)
    for ordinal,(index,frame) in enumerate(visual.decoded_frames(video,by_index,ffmpeg,output_dir/'decode-holds.log')):
        requested=by_index[index]
        expected=requested['expected_decimal']
        slots,focus=visual.observed_slots_and_focus(frame.crop(visual.BOARD))
        bits=format(expected,'b')
        expected_slots=[None]*(7-len(bits))+list(bits)
        expected_focus=[] if requested['expected_focus_slot'] is None else [requested['expected_focus_slot']]
        mask=visual.ink_mask(frame.crop(visual.SIGN_VALUE_ROI))
        recognized,confidence=visual.recognize_decimal(mask,templates)
        passed=slots==expected_slots and focus==expected_focus and recognized==str(expected) and confidence>=.88
        path=output_dir/f'{ordinal+1:02d}-{requested["from_decimal"]:03d}-to-{requested["to_decimal"]:03d}-{requested["label"]}.png'
        frame.save(path)
        row=dict(requested,observed_binary_slots=slots,observed_focus_slots=focus,
                 recognized_decimal=recognized,minimum_digit_recognition_iou=confidence,
                 path=str(path),sha256=visual.file_hash(path),passed=passed)
        rows.append(row)
        if not passed:failures.append(row)
        x,y=ordinal%4*480,ordinal//4*315
        sheet.paste(frame.resize((480,270),Image.Resampling.LANCZOS),(x,y))
        label=f'{requested["from_decimal"]}→{requested["to_decimal"]} {requested["label"]}'
        draw.text((x+8,y+277),label,font=visual.font(17),fill=visual.INK)
        draw.text((x+8,y+297),f'{index/30:.3f}s',font=visual.font(13),fill=visual.INK)
    sheet_path=output_dir/'value-hold-contact-sheet.png'
    sheet.save(sheet_path)
    report={'schema_version':1,'kind':'binary-completed-value-hold-qa-v005','passed':not failures,
            'video':{'path':str(video),'sha256':visual.file_hash(video)},
            'timeline':{'path':str(timeline_path),'sha256':visual.file_hash(timeline_path)},
            'implementation_sha256':visual.file_hash(__file__),
            'recognition_helper_sha256':visual.file_hash(Path(visual.__file__)),
            'all127_declared_value_gaps_checked':True,'ordinary_value_gap_s':2.0,
            'ordinary_value_gaps_checked':len([row for row in transitions if not row['special_teaching_or_stretch_pause']]),
            'longer_teaching_or_stretch_gaps_checked':3,
            'within_value_pause_s':.9,'within_value_gaps_checked':642,
            'representative_transitions_checked':list(TRANSITIONS),
            'decoded_boundary_frames_checked':len(rows),
            'visual_commit_policy':'Old binary and decimal value persist until next count.start_s; the new value is committed0.12s before its first speech. End-of-value voice-to-next-value voice gap is2.0s for ordinary transitions; teaching/stretch pauses remain longer.',
            'frame_quantization_tolerance_s':1/30,
            'minimum_decimal_digit_recognition_iou':min(row['minimum_digit_recognition_iou'] for row in rows),
            'transitions':transitions,'decoded_frames':rows,'failures':failures,
            'contact_sheet':str(sheet_path),'elapsed_s':time.perf_counter()-started}
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('passed','decoded_boundary_frames_checked','ordinary_value_gaps_checked','minimum_decimal_digit_recognition_iou','elapsed_s')}))
    if failures:raise ValueError(f'{len(failures)} completed-value hold frames failed; see{report_path}')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video',type=Path,required=True)
    parser.add_argument('--timeline',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--ffmpeg')
    args=parser.parse_args()
    verify(args.video,args.timeline,args.output_dir,args.out,visual.find_ffmpeg(args.ffmpeg))


if __name__=='__main__':main()
