"""Check all four-base values and decimal highlights in the final encoded movie."""
from __future__ import annotations

import argparse
from collections import defaultdict
from functools import lru_cache
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageDraw

if __package__:
    from . import export_four_base_delivery as delivery
    from . import render_four_base_mockups as layout
    from .render_four_base_video import Scene
    from . import verify_octal_video as shared
else:
    import export_four_base_delivery as delivery
    import render_four_base_mockups as layout
    from render_four_base_video import Scene
    import verify_octal_video as shared


NUMERIC_BOXES = {name: (536, (box[1]+20)//4*4, 1380, (box[3]-16+3)//4*4)
                 for name, _, _, box in layout.ROWS}
QUARTER_IOU = .90
NATIVE_IOU = .95


@lru_cache(maxsize=1024)
def expected_numeric(value, row_id, active, marked, quarter):
    box = next(box for name, _, _, box in layout.ROWS if name == row_id)
    fill = '#ffead0' if active else '#fff0de' if row_id == 'decimal' else layout.CREAM
    canvas = Image.new('RGB', layout.SIZE, fill)
    layout.draw_value(ImageDraw.Draw(canvas), layout.representations(value)[row_id], box, active, {0} if marked else set())
    image = canvas.crop(NUMERIC_BOXES[row_id])
    if quarter:
        image = image.resize((image.width//4, image.height//4), Image.Resampling.BOX)
    return shared.glyph_mask(image)


@lru_cache(maxsize=4)
def expected_label(row_id):
    _, label, base, box = next(row for row in layout.ROWS if row[0] == row_id)
    canvas = Image.new('RGB',layout.SIZE,layout.CREAM)
    layout.draw_label_block(ImageDraw.Draw(canvas),label,base,box,row_id=='decimal')
    return shared.glyph_mask(canvas.crop((100,box[1]+20,476,box[3]-16)))


def teal_fraction(image):
    dark=teal=0
    for r,g,b in image.getdata():
        if .299*r+.587*g+.114*b < 137:
            dark += 1
            teal += g>r+8 and b>r+8
    return teal/dark if dark else 0


def check_count_frame(frame,value,active,marks=()):
    errors=[]
    for row_id,_,_,row_box in layout.ROWS:
        box=NUMERIC_BOXES[row_id]
        crop=frame.crop(shared.quarter_box(box))
        actual=shared.glyph_mask(crop)
        expected=expected_numeric(value,row_id,active and row_id=='decimal',row_id in marks,True)
        score=shared.mask_similarity(actual,expected)
        if score < QUARTER_IOU:
            errors.append(f'{row_id} value{layout.representations(value)[row_id]} glyphIoU{score:.4f}')
        if row_id=='decimal':
            fraction=teal_fraction(crop)
            if (active and fraction<.65) or (not active and fraction>.05):
                errors.append(f'decimal speech highlight{fraction:.3f}, expected{active}')
        # Every teaching mark is a new leading1; its left padding clears the1's ink.
        first_center=layout.LAST_SYMBOL_CENTER_X-layout.SYMBOL_STEP*(len(layout.representations(value)[row_id])-1)
        marked=shared.close_to_fill(frame,first_center-36,(row_box[1]+row_box[3])//2,(225,239,218))
        if marked!=(row_id in marks):
            errors.append(f'{row_id} new-place mark{marked}, expected{row_id in marks}')
    return errors


def samples(timeline):
    events=delivery.count_readings(timeline)
    probes=defaultdict(list)
    previous=shared.first_frame(timeline['intro']['duration_s'])
    for value,state in enumerate(timeline['counted_states']):
        expected=layout.representations(value)
        if state['representations']!=expected:
            raise ValueError(f'Incorrect mathematical display at{value}')
        start=shared.first_frame(state['estimated_display_start_s'])
        end=shared.first_frame(state['estimated_display_end_s'])
        if start!=previous or not start<end:
            raise ValueError('Discontinuous display intervals')
        previous=end
        probes[start].append((value,False,(),'state_start'))
        probes[end-1].append((value,False,(),'state_end'))
        event=events[value]
        begin,stop=shared.first_frame(event['start_s']),shared.first_frame(event['end_s'])
        if not start<begin<stop<end:
            raise ValueError('Voice is outside its display interval')
        for index,active,role in ((begin-1,False,'before_voice'),(begin,True,'voice_start'),
                                  (stop-1,True,'voice_end'),(stop,False,'after_voice')):
            probes[index].append((value,active,(),role))
    if previous!=shared.first_frame(timeline['finale']['estimated_start_s']):
        raise ValueError('Final state does not reach the finale')
    for pause in timeline['pauses']:
        if pause['duration_s']!=3:
            raise ValueError('Teaching checks must be three seconds')
        for offset in (.1,.3,1.5,2.8):
            marks=tuple(pause['focus_rows']) if .2<=offset<2.7 else ()
            probes[shared.first_frame(pause['estimated_start_s']+offset)].append((pause['after_decimal_value'],False,marks,'teaching'))
    intro=timeline['intro']['example']
    event=next(e for e in timeline['events'] if e['id']=='I04-TEN')
    for at,value,active in ((intro['display_start_s']-1/30,0,False),(intro['display_start_s'],10,False),
                            (event['start_s'],10,True),(event['end_s']-1/30,10,True),(event['end_s'],10,False),
                            (intro['display_end_s'],0,False)):
        probes[shared.first_frame(at)].append((value,active,(),'intro_example'))
    return probes


def metadata_checks(timeline,directory,video_name):
    chapters='\n'.join(delivery.chapter_lines(timeline))+'\n'
    upload=(directory/'upload-details.txt').read_text(encoding='utf-8')
    return {
        'captions_match_measured_speech':(directory/'english-captions.srt').read_text(encoding='utf-8')==delivery.format_srt(delivery.caption_rows(timeline)),
        'chapters_match_measured_sections':(directory/'chapters.txt').read_text(encoding='utf-8')==chapters,
        'upload_details_match':upload.startswith(f'Title\n{delivery.TITLE}\n') and chapters in upload and delivery.SERIES_URL in upload and f'Video: {video_name}\n' in upload,
    }


def native_checks(video,timeline,scene,ffmpeg):
    voices=delivery.count_readings(timeline)
    probes=[]
    for value in range(16):
        state=timeline['counted_states'][value]
        probes.extend([(shared.first_frame(state['estimated_display_start_s']),value,False),
                       (shared.first_frame(voices[value]['start_s']),value,True)])
    for value in (26,64,104,127):
        probes.append((shared.first_frame(voices[value]['start_s']),value,True))
    records=[]
    errors=[]
    for index,value,active in probes:
        image=shared.decoded_native_frame(video,ffmpeg,index)
        row_records=[]
        for row_id,_,_,box in layout.ROWS:
            actual=shared.glyph_mask(image.crop(NUMERIC_BOXES[row_id]))
            expected=expected_numeric(value,row_id,active and row_id=='decimal',False,False)
            score=shared.mask_similarity(actual,expected)
            bounds,reference=actual.getbbox(),expected.getbbox()
            baseline=layout.row_baseline(box)+bounds[3]-reference[3] if bounds and reference else None
            if score<NATIVE_IOU or baseline is None or abs(baseline-layout.row_baseline(box))>1:
                errors.append(f'Nativeframe{index}/{row_id} value/baseline differs')
            label=shared.mask_similarity(shared.glyph_mask(image.crop((100,box[1]+20,476,box[3]-16))),expected_label(row_id))
            if label<NATIVE_IOU:
                errors.append(f'Nativeframe{index}/{row_id} label differs')
            row_records.append({'row':row_id,'value':layout.representations(value)[row_id],
                                'glyph_iou':round(score,4),'baseline_y_px':baseline,'label_iou':round(label,4)})
        records.append({'frame':index,'decimal_value':value,'voice_active':active,'rows':row_records})
    names=[]
    for cue in timeline['intro']['base_name_cues']:
        index=shared.first_frame((cue['start_s']+cue['end_s'])/2)
        image=shared.decoded_native_frame(video,ffmpeg,index)
        observed=[]
        for row_id,_,_,box in layout.ROWS:
            if shared.close_to_color(image,750,box[1]+2,(32,91,87)):
                observed.append(row_id)
        if observed!=[cue['row']]:
            errors.append(f'Introbase focus{observed},expected{cue["row"]}')
        names.append({'frame':index,'row':cue['row'],'observed':observed})
    bird_records=[]
    checks=[shared.first_frame(voices[26]['start_s'])]
    for cue in scene.actor.cues:
        checks += [shared.first_frame(cue['start_s']),shared.first_frame((cue['start_s']+cue['end_s'])/2),shared.first_frame(cue['end_s'])-1]
        sequence=cue.get('sequence',[{'at_s':0,'pose':'neutral'}])
        for position,node in enumerate(sequence):
            end=sequence[position+1]['at_s'] if position+1<len(sequence) else cue['end_s']-cue['start_s']
            checks.append(shared.first_frame(cue['start_s']+(node['at_s']+end)/2))
    for index in sorted(set(checks)):
        image=shared.decoded_native_frame(video,ffmpeg,index)
        expected=scene.image(scene.state(index))
        region=(1450,500,1912,1000)
        score=shared.mask_similarity(shared.glyph_mask(image.crop(region)),shared.glyph_mask(expected.crop(region)))
        if score<.90:
            errors.append(f'Bird artwork/size atframe{index} differs ({score:.4f})')
        bird_records.append({'frame':index,'bird_pose':scene.state(index).bird_pose,'glyph_mask_iou':round(score,4)})
    return {'reading_probes':records,'opening_base_names':names,'bird_probes':bird_records,'errors':errors}


def visual_checks(video,timeline,ffmpeg,motion_manifest=None):
    scene=Scene(timeline,motion_manifest)
    probes=samples(timeline)
    fade_start=shared.first_frame(scene.fade_start)
    indices=sorted(set(probes)|{0,fade_start-1,scene.frame_count-1})
    expression=shared.select_expression(indices)
    filters=f'select={expression},scale=480:270:flags=area:in_color_matrix=bt709,format=rgb24'
    command=[str(ffmpeg),'-nostdin','-v','error','-xerror','-i',str(video),'-map','0:v:0','-an','-vf',filters,'-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24','pipe:1']
    errors=[]
    stats=defaultdict(int)
    decoded=0
    with subprocess.Popen(command,stdout=subprocess.PIPE) as process:
        for index in indices:
            raw=process.stdout.read(shared.BYTES_PER_FRAME)
            if len(raw)!=shared.BYTES_PER_FRAME:
                errors.append(f'Decode ended atframe{index}')
                break
            decoded+=1
            image=Image.frombytes('RGB',shared.SAMPLE_SIZE,raw)
            if index in (0,scene.frame_count-1):
                if any(not shared.close_to_fill(image,x,y,shared.CREAM_FILL) for x,y in ((500,300),(1200,700),(1675,900))):
                    errors.append(f'Cream fade endpoint differs atframe{index}')
            for value,active,marks,role in probes.get(index,()):
                stats[role]+=1
                errors.extend(f'Frame{index}/{value}/{role}: {error}' for error in check_count_frame(image,value,active,marks))
        if process.stdout.read(1):
            errors.append('Extra decoded frame')
            process.stdout.close()
        if process.wait():errors.append('Quarter decoder failed')
    native=native_checks(video,timeline,scene,ffmpeg)
    errors.extend(native['errors'])
    return {'sampled_frames':decoded,'planned_samples':len(indices),'checks_by_role':dict(stats),
            'native_layout':native,'all_samples_match':not errors,'errors':errors}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--timeline',type=Path,required=True)
    p.add_argument('--video',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--delivery-dir',type=Path)
    p.add_argument('--motion-manifest',type=Path)
    p.add_argument('--technical-report',type=Path)
    p.add_argument('--ffmpeg',default=shutil.which('ffmpeg'))
    p.add_argument('--ffprobe',default=shutil.which('ffprobe'))
    a=p.parse_args()
    timeline=json.loads(a.timeline.read_text(encoding='utf-8-sig'))
    timeline_hash=shared.sha256_file(a.timeline)
    if a.technical_report:
        technical=json.loads(a.technical_report.read_text(encoding='utf-8-sig'))
        if technical.get('status')!='pass' or technical['sha256']!=shared.sha256_file(a.video) or technical['timeline']['sha256']!=timeline_hash:
            raise ValueError('Technical report does not match the media/timeline')
        a.output_dir.mkdir(parents=True,exist_ok=True)
    else:
        technical=shared.verify_video(a.video,a.output_dir,a.timeline,a.ffmpeg,a.ffprobe,duration_bounds=(1,900))
    checks=metadata_checks(timeline,a.delivery_dir or a.video.parent,a.video.name)
    checks['exact_frame_timestamp_grid']=shared.check_video_timestamps(a.video,timeline['duration_s'],a.ffprobe)
    visual=visual_checks(a.video,timeline,a.ffmpeg,a.motion_manifest)
    checks['all_sampled_visuals_match']=visual['all_samples_match']
    checks['technical_media_passes']=technical['status']=='pass'
    report={'status':'pass' if all(checks.values()) else 'fail','checks':checks,'visual':visual,
            'timeline_sha256':timeline_hash,'video_sha256':technical['sha256'],
            'motion_manifest_sha256':shared.sha256_file(a.motion_manifest) if a.motion_manifest else None}
    destination=a.output_dir/'four-base-final-qa.json'
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(destination),'checks':checks,'visual_failures':len(visual['errors'])}))
    return 0 if report['status']=='pass' else 1


if __name__=='__main__':raise SystemExit(main())
