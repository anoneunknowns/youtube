"""Check every encoded binary spoken digit against its exact source-time frame.

One FFmpeg decoding pass selects all 770 bit midpoints and compares cropped
boards, digit ink and focus rings. A second pass retains full representative
frames for visual review. This verifies encoding and timing, not pronunciation.
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
    from render_binary_video import BinaryScene, BinaryTimeline, CREAM, INK, FPS, file_hash, font
    from render_counting_video import find_ffmpeg
except ModuleNotFoundError:
    from tools.render_binary_video import BinaryScene, BinaryTimeline, CREAM, INK, FPS, file_hash, font
    from tools.render_counting_video import find_ffmpeg

BOARD = (610, 228, 1850, 808)
BOARD_SIZE = (1240, 580)


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
    if receipt['renderer_sha256'] != file_hash(Path(__file__).with_name('render_binary_video.py')):
        raise ValueError('Renderer source changed since the encoded movie')
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
    report={'schema_version':1,'kind':'binary-encoded-visual-qa','passed':not failures,
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
            'retained_decoded_frames':retained,'contact_sheet':str(sheet_path),
            'limitations':'Compares encoded frames to separately validated renderer/time-state output. It does not independently recognize spoken pronunciation or approve all unsampled animation frames.',
            'elapsed_s':round(time.perf_counter()-started,3)}
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('passed','all_128_states_sampled','all_770_spoken_bits_checked','maximum_board_mae','maximum_digit_roi_mae','maximum_teal_count_delta','elapsed_s')},indent=2),flush=True)
    if failures:
        raise ValueError(f'{len(failures)} encoded binary visual checks failed; see {report_path}')


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
