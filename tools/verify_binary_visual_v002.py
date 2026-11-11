"""Check binary focus and the bear-held decimal sign in the slower second cut.

One FFmpeg pass selects all 770 bit midpoints and compares cropped boards,
digit ink and focus rings. Another checks decimal sign ink and foreground paw
grips. A final pass retains full representative frames for visual review.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import subprocess
import time

from PIL import Image, ImageChops, ImageDraw, ImageStat

try:
    from render_binary_video_v002 import DecimalSignScene as BinaryScene, BinaryTimeline, CREAM, INK, FPS, file_hash, font
    from render_binary_video_v002 import SIGN_BBOX, SIGN_VALUE_ROI, SIGN_VALUE_CENTER, SIGN_VALUE_FONT_SIZE
    from render_binary_video_v002 import SIGN_GRIP_BBOXES, sign_geometry
    from render_counting_video import find_ffmpeg
except ModuleNotFoundError:
    from tools.render_binary_video_v002 import DecimalSignScene as BinaryScene, BinaryTimeline, CREAM, INK, FPS, file_hash, font
    from tools.render_binary_video_v002 import SIGN_BBOX, SIGN_VALUE_ROI, SIGN_VALUE_CENTER, SIGN_VALUE_FONT_SIZE
    from tools.render_binary_video_v002 import SIGN_GRIP_BBOXES, sign_geometry
    from tools.render_counting_video import find_ffmpeg

BOARD = (610, 228, 1850, 808)
BOARD_SIZE = (1240, 580)
SIGN_REGION = (108, 640, 510, 820)


def ink_mask(image):
    """Select dark warm numeric ink; ignore pale sign material and codec halos."""
    red, green, blue = image.convert('RGB').split()
    mask = red.point(lambda value:255 if value<140 else 0)
    mask = ImageChops.multiply(mask,green.point(lambda value:255 if value<125 else 0))
    return ImageChops.multiply(mask,blue.point(lambda value:255 if value<110 else 0))


def independent_decimal_mask(value):
    """Compute the decimal typography directly from value, without renderer state."""
    roi=SIGN_VALUE_ROI
    image=Image.new('RGB',(roi[2]-roi[0],roi[3]-roi[1]),'white')
    draw=ImageDraw.Draw(image)
    face=font(SIGN_VALUE_FONT_SIZE)
    text=str(value)
    box=draw.textbbox((0,0),text,font=face)
    center=(SIGN_VALUE_CENTER[0]-roi[0],SIGN_VALUE_CENTER[1]-roi[1])
    xy=(center[0]-(box[0]+box[2])/2,center[1]-(box[1]+box[3])/2)
    draw.text(xy,text,font=face,fill=INK)
    return ink_mask(image)


def binary_mask_iou(first,second):
    overlap=ImageStat.Stat(ImageChops.multiply(first,second)).sum[0]
    union=ImageStat.Stat(ImageChops.lighter(first,second)).sum[0]
    return overlap/union if union else 0


def normalized_glyph(mask):
    box=mask.getbbox()
    if not box:
        return Image.new('L',(90,100),0)
    glyph=mask.crop(box)
    if glyph.width>90 or glyph.height>100:
        raise ValueError('Decimal glyph exceeds its independent recognition canvas')
    canvas=Image.new('L',(90,100),0)
    canvas.paste(glyph,((90-glyph.width)//2,(100-glyph.height)//2))
    return canvas


def recognize_decimal(mask,digit_templates):
    """Segment actual ink, then classify each numeral without expected text."""
    columns=mask.getprojection()[0]
    runs=[]
    start=None
    for index,active in enumerate([*columns,0]):
        if active and start is None:
            start=index
        elif not active and start is not None:
            if index-start>=3:
                runs.append((start,index))
            start=None
    result=[]
    confidence=[]
    for left,right in runs:
        glyph=normalized_glyph(mask.crop((left,0,right,mask.height)))
        scores={digit:binary_mask_iou(glyph,template) for digit,template in digit_templates.items()}
        best=max(scores,key=scores.get)
        result.append(best)
        confidence.append(scores[best])
    return ''.join(result),min(confidence,default=0)


def verify_decimal_sign_frames(video,token_by_index,scene,ffmpeg,output_dir):
    """Verify 770 decoded decimal labels independently of binary-board rendering."""
    templates={value:independent_decimal_mask(value) for value in range(128)}
    digit_templates={str(value):normalized_glyph(templates[value]) for value in range(10)}
    comparisons=[]
    failures=[]
    seen=set()
    for ordinal,(index,region) in enumerate(decoded_frames(video,token_by_index,ffmpeg,output_dir/'decode-signs.log',SIGN_REGION),1):
        token=token_by_index[index]
        value=token['decimal_value']
        def local(box):
            return (box[0]-SIGN_REGION[0],box[1]-SIGN_REGION[1],box[2]-SIGN_REGION[0],box[3]-SIGN_REGION[1])
        decoded=region.crop(local(SIGN_VALUE_ROI))
        observed=ink_mask(decoded)
        box=observed.getbbox()
        reference=templates[value]
        iou=binary_mask_iou(observed,reference)
        recognized,recognition_confidence=recognize_decimal(observed,digit_templates)
        if box:
            width,height=observed.size
            margins=[box[0],box[1],width-box[2],height-box[3]]
            ink_height=box[3]-box[1]
            reference_box=reference.getbbox()
            center_error=max(abs((box[0]+box[2]-reference_box[0]-reference_box[2])/2),
                             abs((box[1]+box[3]-reference_box[1]-reference_box[3])/2))
        else:
            margins=[0,0,0,0];ink_height=0;center_error=999
        state=scene.state(index/FPS)
        geometry=sign_geometry(scene.pose(index/FPS,state))
        grip_errors=[]
        expected_region=scene.frame(index/FPS).crop(SIGN_REGION)
        for grip in geometry['grip_paw_bboxes']:
            grip_errors.append(mae(region.crop(local(grip)),expected_region.crop(local(grip))))
        grip_geometry_valid=(geometry['style']=='held' and len(geometry['grip_paw_bboxes'])==2
                             and geometry['face_clearance_px']>=5)
        passed=(iou>=.90 and ink_height>=72 and min(margins)>=5 and center_error<=1.5
                and recognized==str(value) and recognition_confidence>=.88
                and grip_geometry_valid and max(grip_errors,default=999)<=7)
        row={'id':token['id'],'frame_index':index,'frame_time_s':index/FPS,
             'decimal_value':value,'independent_decimal_text':str(value),
             'recognized_decimal_text':recognized,'minimum_digit_recognition_iou':round(recognition_confidence,6),
             'glyph_mask_iou':round(iou,6),'visible_ink_height_px':ink_height,
             'roi_margins_px':margins,'visible_ink_center_error_px':center_error,
             'holding_style':geometry['style'],'grip_paw_count':len(grip_errors),
             'grip_roi_mae':[round(error,5) for error in grip_errors],
             'face_clearance_px':geometry['face_clearance_px'],'passed':passed}
        comparisons.append(row)
        if not passed:
            failures.append(row)
            decoded.save(output_dir/f'failed-sign-{token["id"]}.png')
        if value in (0,45,127) and value not in seen:
            decoded.save(output_dir/f'decimal-sign-{value:03}.png')
        seen.add(value)
        if ordinal%100==0:
            print(f'Decoded decimal-sign QA {ordinal}/770',flush=True)
    return {'passed':not failures,'all_128_decimal_values_checked':sorted(seen)==list(range(128)),
            'all_770_synchronized_sign_frames_checked':len(comparisons)==770,
            'independent_numeric_glyph_mask_comparison':True,
            'independent_segmented_decimal_digit_recognition':True,
            'sign_bbox':list(SIGN_BBOX),'decimal_roi':list(SIGN_VALUE_ROI),
            'foreground_grip_bboxes':[list(box) for box in SIGN_GRIP_BBOXES],
            'font_size_px':SIGN_VALUE_FONT_SIZE,
            'all_spoken_counts_have_two_visible_foreground_grips':all(row['grip_paw_count']==2 for row in comparisons),
            'maximum_grip_roi_mae':max(max(row['grip_roi_mae']) for row in comparisons),
            'minimum_face_clearance_px':min(row['face_clearance_px'] for row in comparisons),
            'minimum_observed_glyph_mask_iou':min(row['glyph_mask_iou'] for row in comparisons),
            'minimum_observed_single_digit_recognition_iou':min(row['minimum_digit_recognition_iou'] for row in comparisons),
            'minimum_visible_ink_height_px':min(row['visible_ink_height_px'] for row in comparisons),
            'maximum_visible_ink_center_error_px':max(row['visible_ink_center_error_px'] for row in comparisons),
            'thresholds':{'glyph_mask_iou':.90,'ink_height_px':72,'roi_margin_px':5,'center_error_px':1.5},
            'comparisons':comparisons,'failures':failures}


def read_exact(stream, length):
    data = bytearray(length)
    view = memoryview(data)
    position = 0
    while position < length:
        count = stream.readinto(view[position:])
        if not count:
            raise ValueError(f'Decoder ended after {position}/{length} bytes')
        position += count
    return data


def mae(first, second):
    return sum(ImageStat.Stat(ImageChops.difference(first, second)).mean)/3


def teal_count(image):
    red, green, blue = image.split()
    tests = (red.point(lambda v:255 if v<=100 else 0),
             green.point(lambda v:255 if v>=90 else 0),
             blue.point(lambda v:255 if v>=100 else 0),
             ImageChops.subtract(green, red).point(lambda v:255 if v>=35 else 0),
             ImageChops.subtract(blue, red).point(lambda v:255 if v>=35 else 0))
    result = tests[0]
    for test in tests[1:]:
        result = ImageChops.multiply(result, test)
    return round(ImageStat.Stat(result).sum[0]/255)


def slot_boxes(slot):
    width=(1160-14*6)/7
    x=650+slot*(width+14)-BOARD[0]
    y=330-BOARD[1]
    digit=(round(x+14),round(y+20),round(x+width-14),round(y+172))
    cell=(round(x-11),round(y-11),round(x+width+11),round(y+245))
    return digit, cell


def observed_slots_and_focus(board):
    """Classify cell backgrounds independently from the expected raster image."""
    palette={None:(246,240,231),'0':(221,213,239),'1':(255,209,93)}
    values=[]
    focused=[]
    width=(1160-14*6)/7
    for slot in range(7):
        center=round(650+slot*(width+14)+width/2-BOARD[0])
        patch=board.crop((center-12,349-BOARD[1],center+12,361-BOARD[1]))
        mean=ImageStat.Stat(patch).mean
        values.append(min(palette,key=lambda bit:sum((mean[channel]-palette[bit][channel])**2 for channel in range(3))))
        # At the center of the top edge, the ring cannot leak from a neighbor.
        outline=board.crop((center-20,319-BOARD[1],center+20,330-BOARD[1]))
        if teal_count(outline)>=100:
            focused.append(slot)
    return values,focused


def decoded_frames(video, indices, ffmpeg, log_path, crop=None):
    indices=sorted(set(indices))
    def balanced_sum(terms):
        if len(terms)==1:
            return terms[0]
        midpoint=len(terms)//2
        return '('+balanced_sum(terms[:midpoint])+'+'+balanced_sum(terms[midpoint:])+')'
    # AVExpr has a recursion limit; a linear chain of 770 additions overflows it.
    expression=balanced_sum([f'eq(n\\,{index})' for index in indices])
    filters=[f'select={expression}']
    size=(1920,1080)
    if crop:
        x,y,right,bottom=crop
        size=(right-x,bottom-y)
        filters.append(f'crop={size[0]}:{size[1]}:{x}:{y}')
    filters.append('scale=in_range=limited:out_range=full:in_color_matrix=bt709')
    command=[ffmpeg,'-hide_banner','-v','error','-i',str(video),'-vf',','.join(filters),
             '-fps_mode','passthrough','-an','-f','rawvideo','-pix_fmt','rgb24','pipe:1']
    with log_path.open('w',encoding='utf-8') as log:
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=log)
        assert process.stdout is not None
        try:
            for index in indices:
                buffer=read_exact(process.stdout,size[0]*size[1]*3)
                yield index, Image.frombytes('RGB',size,bytes(buffer))
            extra=process.stdout.read(1)
            if extra:
                raise ValueError('Decoder emitted unrequested extra frames')
            code=process.wait()
            if code:
                raise ValueError(f'FFmpeg decoding failed ({code}); see {log_path}')
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
                process.wait()


def verify(video, timeline_path, output_dir, report_path, ffmpeg):
    started=time.perf_counter()
    receipt_path=video.with_suffix('.render.json')
    receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
    if receipt['timeline_sha256'] != file_hash(timeline_path):
        raise ValueError('Renderer receipt refers to a different timeline')
    if receipt['renderer_sha256'] != file_hash(Path(__file__).with_name('render_binary_video_v002.py')):
        raise ValueError('Renderer source changed since the encoded movie')
    if receipt['base_binary_renderer_sha256'] != file_hash(Path(__file__).with_name('render_binary_video.py')):
        raise ValueError('Base renderer changed since the encoded movie')
    if receipt['shared_encoder_and_bear_sha256'] != file_hash(Path(__file__).with_name('render_counting_video.py')):
        raise ValueError('Shared character/encoder implementation changed since render')
    root=Path(__file__).resolve().parents[1]
    for source in receipt['source_assets']:
        if file_hash(root/source['path']) != source['sha256']:
            raise ValueError(f'Rendered source artwork changed: {source["path"]}')
    timeline=BinaryTimeline(json.loads(timeline_path.read_text(encoding='utf-8')))
    scene=BinaryScene(timeline)
    output_dir.mkdir(parents=True,exist_ok=False)
    if report_path.exists():
        raise ValueError(f'Refusing to overwrite QA report: {report_path}')
    tokens=[]
    for row in timeline.counts:
        for token in row['bit_events']:
            midpoint=(token['start_s']+token['end_s'])/2
            index=round(midpoint*FPS)
            stamp=index/FPS
            if not token['start_s']<=stamp<token['end_s']:
                raise ValueError('Spoken bit has no safely interior video frame')
            tokens.append((index,token))
    if len(tokens)!=770 or len({index for index,_ in tokens})!=770:
        raise ValueError('Expected 770 distinct spoken-bit midpoint frames')
    token_by_index=dict(tokens)
    comparisons=[]
    failures=[]
    for ordinal,(index,decoded) in enumerate(decoded_frames(video,token_by_index,ffmpeg,output_dir/'decode-boards.log',BOARD),1):
        token=token_by_index[index]
        seconds=index/FPS
        state=scene.state(seconds)
        if state['number'] != token['decimal_value'] or state['focus'] != token['bit_index']:
            raise ValueError(f'Timeline source state differs at token {token["id"]}')
        expected=scene.frame(seconds).crop(BOARD)
        board_error=mae(decoded,expected)
        digit_errors=[]
        focus_counts=[]
        ring_errors=[]
        for slot in range(7):
            digit_box,cell_box=slot_boxes(slot)
            digit_errors.append(mae(decoded.crop(digit_box),expected.crop(digit_box)))
            observed=teal_count(decoded.crop(cell_box))
            reference=teal_count(expected.crop(cell_box))
            focus_counts.append(observed)
            ring_errors.append(abs(observed-reference))
        slot_states,focused_slots=observed_slots_and_focus(decoded)
        independent_bits=format(token['decimal_value'],'b')
        expected_slots=[None]*(7-len(independent_bits))+list(independent_bits)
        row={'id':token['id'],'decimal_value':token['decimal_value'],'display_binary':token['display_binary'],
             'token':token['token'],'bit_index':token['bit_index'],'slot_index':token['slot_index'],
             'frame_index':index,'frame_time_s':seconds,'board_mae':round(board_error,5),
             'digit_roi_mae':[round(error,5) for error in digit_errors],
             'focus_teal_pixel_counts':focus_counts,'focus_teal_pixel_count_delta':ring_errors,
             'observed_cell_states':slot_states,'expected_cell_states':expected_slots,
             'observed_focused_slots':focused_slots}
        # Board-wide error alone could hide one wrong bit. Check each independent
        # glyph region as well as the high-contrast spoken-focus outline.
        passed=(board_error<=4 and max(digit_errors)<=7 and max(ring_errors)<=900
                and focus_counts[token['slot_index']]>=1800 and slot_states==expected_slots
                and focused_slots==[token['slot_index']])
        row['passed']=passed
        comparisons.append(row)
        if not passed:
            failures.append(row)
            decoded.save(output_dir/f'failed-{token["id"]}.png')
        if ordinal%100==0:
            print(f'Decoded binary visual QA {ordinal}/770',flush=True)
    sign_report=verify_decimal_sign_frames(video,token_by_index,scene,ffmpeg,output_dir)
    # Retain representative full frames from the actual compressed MP4.
    samples=scene.sample_times()
    sample_by_index={min(math.ceil(timeline.duration*FPS)-1,round(seconds*FPS)):(label,seconds) for label,seconds in samples}
    sheet=Image.new('RGB',(1920,math.ceil(len(sample_by_index)/3)*402),CREAM)
    draw=ImageDraw.Draw(sheet)
    retained=[]
    for ordinal,(index,frame) in enumerate(decoded_frames(video,sample_by_index,ffmpeg,output_dir/'decode-samples.log')):
        label,_=sample_by_index[index]
        path=output_dir/f'{ordinal+1:02d}-{label}.png'
        frame.save(path)
        x,y=ordinal%3*640,ordinal//3*402
        sheet.paste(frame.resize((640,360),Image.Resampling.LANCZOS),(x,y))
        draw.text((x+10,y+367),f'{label} / decoded {index/FPS:.3f}s',font=font(20),fill=INK)
        retained.append({'label':label,'frame_index':index,'time_s':index/FPS,'path':str(path), 'sha256':file_hash(path)})
    sheet_path=output_dir/'decoded-contact-sheet.png'
    sheet.save(sheet_path)
    counts=Counter(row['decimal_value'] for row in comparisons)
    report={'schema_version':1,'kind':'binary-encoded-visual-qa-v002','passed':not failures and sign_report['passed'],
            'video':str(video),'video_sha256':file_hash(video),'timeline':str(timeline_path),
            'timeline_sha256':file_hash(timeline_path),'renderer_receipt_sha256':file_hash(receipt_path),
            'verifier_sha256':file_hash(__file__),'all_128_states_sampled':list(sorted(counts))==list(range(128)),
            'all_770_spoken_bits_checked':len(comparisons)==770,'independent_per_slot_digit_rois':True,
            'independent_cell_state_classification':True,'independent_top_edge_focus_classification':True,
            'exact_focused_slot_checked':True,'maximum_board_mae':max(row['board_mae'] for row in comparisons),
            'maximum_digit_roi_mae':max(max(row['digit_roi_mae']) for row in comparisons),
            'maximum_teal_count_delta':max(max(row['focus_teal_pixel_count_delta']) for row in comparisons),
            'thresholds':{'board_mae':4,'per_slot_digit_roi_mae':7,'teal_ring_count_delta':900,'focused_slot_min_teal_pixels':1800},
            'midpoint_frame_selection_error_max_s':1/(2*FPS),'comparisons':comparisons,'failures':failures,
            'decimal_sign':sign_report,
            'retained_decoded_frames':retained,'contact_sheet':str(sheet_path),
            'limitations':'Compares encoded frames to separately validated renderer/time-state output. It does not independently recognize spoken pronunciation or approve all unsampled animation frames.',
            'elapsed_s':round(time.perf_counter()-started,3)}
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('passed','all_128_states_sampled','all_770_spoken_bits_checked','maximum_board_mae','maximum_digit_roi_mae','maximum_teal_count_delta','elapsed_s')},indent=2),flush=True)
    if failures or not sign_report['passed']:
        raise ValueError(f'{len(failures)} binary checks and {len(sign_report["failures"])} sign checks failed; see {report_path}')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video',type=Path,required=True)
    parser.add_argument('--timeline',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--ffmpeg')
    args=parser.parse_args()
    verify(args.video,args.timeline,args.output_dir,args.out,find_ffmpeg(args.ffmpeg))


if __name__=='__main__':
    main()
