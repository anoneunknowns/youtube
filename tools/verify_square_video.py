"""Independent verification of square-number finished media.

This verifier never imports the square producer, renderer or motion adapter.
Truth is obtained from odd-number sums, strict inverse cardinal parsing and
separately rasterized glyphs; observations come from the actual decoded MP4.
"""
from __future__ import annotations

import argparse
from array import array
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import gzip
import json
import math
from pathlib import Path
import re
import shutil
from statistics import median
import subprocess
import tempfile
import wave

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat, ImageFilter, ImageOps

if __package__:
    from . import verify_video as technical
    from .component_alignment import raster_centering_report, centering_report
else:
    import verify_video as technical
    from component_alignment import raster_centering_report, centering_report

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/square-counting-v1'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
FPS, RATE, SIZE = 30, 48000, (1920, 1080)
INK, TEAL, BLUE, GOLD = '#29475b', '#237e83', '#4c88b4', '#cb8450'
GRID = (720,402,1200,882)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def path_of(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def sample(at):
    return round(at*RATE)


def frame_at(at):
    return math.ceil(at*FPS-1e-7)


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')


def squares():
    """Independent identity 1+3+...+(2n-1), including its empty sum."""
    result=[0]
    for odd in range(1,200,2):
        result.append(result[-1]+odd)
    require(len(result)==101 and result[-1]==10000 and sum(result)==338350,
            'Odd-sum truth invariant differs')
    require(all(math.isqrt(v)==n for n,v in enumerate(result)), 'Integer-root independent check failed')
    return tuple(result)


def parse_cardinal(text):
    """Inverse parser, no producer cardinal formatting code is used."""
    names='zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
    small=dict(zip(names,range(20)))
    tens=dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(),range(20,100,10)))
    tokens=text.lower().replace('-',' ').split()
    def group(words):
        if not words:return 0
        if 'hundred' in words:
            if len(words)<2 or words[1]!='hundred' or words.count('hundred')!=1 or not 1<=small.get(words[0],-1)<=9:return None
            tail=group(words[2:])
            return 100*small[words[0]]+tail if tail is not None and tail<100 else None
        if len(words)==1:return small.get(words[0],tens.get(words[0]))
        if len(words)==2 and words[0] in tens and 1<=small.get(words[1],-1)<=9:return tens[words[0]]+small[words[1]]
        return None
    if tokens.count('thousand')==1:
        k=tokens.index('thousand');a,b=group(tokens[:k]),group(tokens[k+1:])
        return a*1000+b if a is not None and 1<=a<=10 and b is not None and b<1000 else None
    return group(tokens)


def checked_design():
    truth=squares();rows=json.loads((DESIGN/'count-lines.json').read_text())
    require(len(rows)==101,'Count correspondence must have101 terms')
    for n,row in enumerate(rows):
        require(row['index']==row['n']==n and row['ordinal']==n+1, f'Authored index wrong n{n}')
        require(row['value']==truth[n] and row['display_value']==f'{truth[n]:,}', f'Authored square wrong n{n}')
        require(row['factor_a']==row['factor_b']==row['a']==row['b']==n, f'Inputs not the same n{n}')
        require(parse_cardinal(row['text'])==truth[n], f'Incorrect result cardinal n{n}')
        require(parse_cardinal(row['a_text'])==parse_cardinal(row['b_text'])==n, f'Incorrect input cardinal n{n}')
        require(row['equation_text']==f'{n} × {n} = {truth[n]:,}' and row['symbolic_equation_text']==f'{n}² = {n} × {n} = {truth[n]:,}',f'Authored formula differs n{n}')
        require(row['formula_prefix_text']==f'{row["a_text"]} times {row["b_text"]} equals',f'Formula narration differs n{n}')
        require(row['formula_narration_id']==f'E{n:03}' and row['count_narration_id']==f'N{n:03}', f'Authored cue IDs differ n{n}')
    authored=json.loads((DESIGN/'timing-plan.json').read_text())['events']
    require(len(authored)==len({r['id'] for r in authored})==215,'Expected215 unique authored utterances')
    return truth,rows,{r['id']:r for r in authored}


def validate_schedule(plan):
    truth,rows,authored=checked_design()
    require(plan['fps']==30 and plan['duration_frames']==frame_at(plan['duration_s']), 'Frame grid differs')
    require(480<=plan['duration_s']<1800,'Long-form square film must be at least8minutes')
    events=sorted(plan.get('voice_events',plan.get('events',[])),key=lambda r:r['start_s'])
    require(len(events)==len({r['id'] for r in events})==215 and {r['id'] for r in events}==set(authored),'Actual speech cue set differs')
    cursor=0
    for row in events:
        require(row['text']==authored[row['id']]['text'], f'Speech text changed {row["id"]}')
        start,end=sample(row['start_s']),sample(row['end_s'])
        require(cursor<=start<end<=sample(plan['duration_s']),f'Invalid/overlapping cue {row["id"]}')
        require(start%2==end%2==0,f'Cue not on24k source grid {row["id"]}')
        cursor=end
    by_id={r['id']:r for r in events}
    states=plan.get('counted_states',plan.get('count_states',[]))
    require(len(states)==101,'Need101 counted states')
    ordinary,checkpoints=0,0
    for n,state in enumerate(states):
        prefix,result=by_id[f'E{n:03}'],by_id[f'N{n:03}']
        require(state.get('index',state.get('n'))==n and state['value']==truth[n],f'Counted state wrong n{n}')
        require(state.get('operands',[state.get('a'),state.get('b')])==[n,n],f'Wrong inputs n{n}')
        require(parse_cardinal(result['text'])==truth[n],f'Actual result cardinal wrong n{n}')
        require(prefix['text']==rows[n]['formula_prefix_text'],f'Actual expression wrong n{n}')
        require(sample(result['start_s']-prefix['end_s'])==sample(.16),f'Expression/result gap wrong n{n}')
        committed=state.get('result_start_s',state.get('display_start_s'))
        require(sample(result['start_s']-committed)==sample(.12),f'Result display lead wrong n{n}')
        for key,event,endpoint in [('formula_start_s',prefix,'start_s'),('formula_end_s',prefix,'end_s'),('voice_start_s',result,'start_s'),('voice_end_s',result,'end_s')]:
            require(sample(state[key])==sample(event[endpoint]),f'State/audio disagree n{n}/{key}')
        if n<100:
            nex=by_id[f'E{n+1:03}']
            if n in (0,4,10,32):
                explanation=by_id[f'T{n:03}']
                require(sample(explanation['start_s']-result['end_s'])==sample(.4),f'Checkpoint entrance gap n{n}')
                require(sample(nex['start_s']-explanation['end_s'])==sample(2),f'Checkpoint settling gap n{n}')
                checkpoints+=1
            else:
                require(sample(nex['start_s']-result['end_s'])==sample(2),f'Ordinary N-end→next-E-start gap n{n}')
                ordinary+=1
    require(ordinary==96 and checkpoints==4,'Ordinary/checkpoint boundary coverage differs')
    spoken=sum(r['end_s']-r['start_s'] for r in events)
    require(abs(plan['duration_s']-spoken-223.16)<=1/FPS+1/RATE,'Adopted speech plus fixed editing duration differs')
    segments=plan.get('visual_segments',[])
    if segments:
        require(segments[0]['start_s']==0 and abs(segments[-1]['end_s']-plan['duration_s'])<1e-6,'Visual segments miss endpoints')
        for left,right in zip(segments,segments[1:]):
            require(abs(left['end_s']-right['start_s'])<1e-6,'Visual segments have a hole or overlap')
    return events,states,segments,{'passed':True,'independent_truth':'Odd-number accumulation, integer-root check and strict inverse English parser','terms':101,'expressions':101,'voice_events':215,'ordinary_two_second_boundaries':ordinary,'checkpoint_boundaries':checkpoints,'source_speech_duration_s':spoken,'fixed_editing_duration_s':223.16}


def pcm16(data):
    values=array('h');values.frombytes(data)
    if __import__('sys').byteorder!='little':values.byteswap()
    return values


def correlation(reference,observed,guard=8,stride=16):
    ref=reference[::stride];energy=sum(v*v for v in ref);best=(-1,0,0)
    for lag in range(-guard,guard+1):
        obs=observed[guard+lag:guard+lag+len(reference):stride]
        if len(obs)!=len(ref):continue
        actual_energy=sum(v*v for v in obs)
        if not actual_energy or not energy:continue
        corr=sum(a*b for a,b in zip(ref,obs))/math.sqrt(energy*actual_energy)
        if corr>best[0]:best=(corr,lag,10*math.log10(actual_energy/energy))
    return best


def audio_checks(plan,events,video,master,ffmpeg,directory,include_final_aac=True):
    """Inspect both tracks/channels; waveform identity does not claim fresh ASR."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    refs={};outcomes=[]
    with tempfile.TemporaryDirectory(prefix='square-audio-independent-') as temp:
        temp=Path(temp)
        for row in events:
            source=path_of(row['source_path']);require(sha(source)==row['source_sha256'],f'Source hash changed {row["id"]}')
            if source not in refs:
                dest=temp/f'source-{len(refs):03}.wav'
                subprocess.run([str(ffmpeg),'-nostdin','-v','error','-xerror','-n','-i',str(source),'-ar',str(RATE),'-ac','2','-c:a','pcm_s16le',str(dest)],check=True)
                # Match the declared FFmpeg mono→stereo routing before testing
                # per-source/common gains: equal-power upmix is −3.0103dB/ch.
                # This is an explicit channel matrix, not a relaxed gain gate.
                with wave.open(str(dest),'rb') as w:refs[source]=pcm16(w.readframes(w.getnframes()))[::2]
        tracks=[('master',master,False)]+([('final-aac',video,True)] if include_final_aac else [])
        for label,source,lossy in tracks:
            dest=temp/(label+'.wav')
            subprocess.run([str(ffmpeg),'-nostdin','-v','error','-xerror','-n','-i',str(source),'-map','0:a:0','-ar',str(RATE),'-ac','2','-c:a','pcm_s16le',str(dest)],check=True)
            checks=[];silent=[];cursor=0;boundary=sample(.03 if lossy else .002)
            with wave.open(str(dest),'rb') as w:
                require(abs(w.getnframes()-sample(plan['duration_s']))<=(2048 if lossy else 1),'Audio end differs from timeline')
                for row in events:
                    start,end=sample(row['start_s']),sample(row['end_s']);reference=refs[path_of(row['source_path'])]
                    require(abs(len(reference)-(end-start))<=2,f'Source PCM duration differs {row["id"]}')
                    a,b=cursor+(boundary if cursor else 0),start-boundary
                    if b>a:
                        w.setpos(a);peak=max(map(abs,pcm16(w.readframes(b-a))),default=0)
                        silent.append({'start_s':a/RATE,'end_s':b/RATE,'peak_pcm16':peak})
                    w.setpos(max(0,start-8));actual=pcm16(w.readframes(len(reference)+16))
                    values=[correlation(reference,actual[ch::2]) for ch in (0,1)]
                    require(min(v[0] for v in values)>=.97,f'{label} waveform differs {row["id"]}: {values}')
                    total_gain=row.get('mix_gain_db',0)+plan.get('master',{}).get('common_gain_db',plan.get('common_gain_db',0))
                    # Explicit adopted gain is tested separately from correlation.
                    gain_ok=all(abs(v[2]-total_gain)<=(.35 if lossy else .05) for v in values)
                    require(gain_ok,f'{label} declared gain differs {row["id"]}: observed {values}, expected {total_gain}')
                    checks.append({'id':row['id'],'source_sha256':row['source_sha256'],'left_correlation':values[0][0],'right_correlation':values[1][0],'left_lag_samples':values[0][1],'right_lag_samples':values[1][1],'left_gain_db':values[0][2],'right_gain_db':values[1][2],'expected_gain_db':total_gain,'stereo_gain_difference_db':abs(values[0][2]-values[1][2])})
                    cursor=end
                if cursor+boundary<w.getnframes():
                    w.setpos(cursor+boundary);silent.append({'start_s':(cursor+boundary)/RATE,'end_s':w.getnframes()/RATE,'peak_pcm16':max(map(abs,pcm16(w.readframes(w.getnframes()))),default=0)})
            maximum=max((r['peak_pcm16'] for r in silent),default=0)
            require(maximum<=(3 if lossy else 1),f'Unexpected sound in {label} guarded silent intervals: {maximum}')
            report={'passed':True,'track':label,'sha256':sha(source),'events':checks,'silence_intervals':silent,'maximum_silent_interior_peak_pcm16':maximum,'boundary_guard_s':boundary/RATE,'minimum_waveform_correlation':min(min(r['left_correlation'],r['right_correlation']) for r in checks),'waveform_stride':16,'lag_search_samples':[-8,8],'source_reference_channel_mapping':'FFmpeg48k stereo upmix, left channel; mono→stereo equal-power attenuation −3.0103dB/ch is applied before declared gains','maximum_left_right_gain_difference_db':max(r['stereo_gain_difference_db'] for r in checks)}
            write_json(directory/(label+'.json'),report);outcomes.append(report)
    return {'passed':True,'tracks':outcomes,'scope':'All215 scheduled source hashes and waveforms against '+('master and actual decoded final AAC' if include_final_aac else 'master only; final AAC not inspected')+', two channels, declared gains and guarded silent intervals. Fresh ASR/CTC is referenced separately; no human continuous listening claim.'}


def srt_time(text):
    hh,mm,tail=text.split(':');ss,ms=tail.split(',')
    return int(hh)*3600+int(mm)*60+int(ss)+int(ms)/1000


def captions_and_metadata(plan,events,directory):
    paths=list(Path(directory).glob('*.srt'))
    require(paths,'No SRT subtitles delivered')
    records=[]
    for path in paths:
        blocks=path.read_text(encoding='utf-8-sig').strip().split('\n\n')
        require(len(blocks)==len(events),f'Subtitle count differs {path}')
        for ordinal,(block,event) in enumerate(zip(blocks,events),1):
            lines=block.splitlines();require(lines[0]==str(ordinal),f'SRT ordinal differs {path}/{ordinal}')
            start,end=map(srt_time,lines[1].split(' --> '))
            require(abs(start-event['start_s'])<=.000501 and abs(end-event['end_s'])<=.000501,f'SRT cue timing differs {event["id"]}')
            require(' '.join(lines[2:])==event.get('subtitle_text',event['text']),f'SRT cue content differs {event["id"]}')
        records.append({'path':str(path),'sha256':sha(path),'cues_checked':len(blocks)})
    directory=Path(directory);by={e['id']:e for e in events}
    raw=(directory/'chapters.txt').read_text().strip().splitlines()
    anchors=[(0,0),(by['E000']['start_s'],by['N000']['end_s']),(by['T004']['start_s'],by['T004']['end_s']),
             (by['T010']['start_s'],by['T010']['end_s']),(by['N032']['start_s'],by['T032']['end_s']),
             (by['E100']['start_s'],by['T100']['end_s']),(by['O01']['start_s'],by['O01']['end_s'])]
    require(len(raw)==7,'Expected7 chapter entries');times=[]
    for line,(lo,hi) in zip(raw,anchors):
        stamp,_=line.split(' ',1);mm,ss=stamp.split(':');at=int(mm)*60+int(ss)
        require(math.floor(lo)<=at<=hi,'Chapter timestamp outside its intended scene: '+line);times.append(at)
    require(times==sorted(set(times)) and times[0]==0 and times[-1]<plan['duration_s'],'Chapter order/end differs')
    title=(directory/'youtube-title.txt').read_text().strip();description=(directory/'youtube-description.txt').read_text()
    require('Square Numbers' in title and '0² to 100²' in title,'Title theme/range differs')
    require(all(text in description for text in ('101 square numbers','from 0 to 10,000','one existing block')),'Description mathematical meaning differs')
    require('\n'.join(raw) in description,'Description chapter list differs')
    require((directory/'upload-details.txt').read_text().strip()==title+'\n\n'+description.strip(),'Combined upload metadata differs')
    metadata={'chapters':raw,'chapter_times_s':times,'chapter_timestamp_quantization':'whole-second floor of a timestamp within its intended mathematical scene','title':title,'description_claims_checked':['0..100 inputs','101 terms','0..10000 results','labelled schematic versus exact unit grid','same-block zoom adds no units'],'files':[{'path':str(directory/name),'sha256':sha(directory/name)} for name in ('chapters.txt','youtube-title.txt','youtube-description.txt','upload-details.txt')]}
    return {'passed':True,'subtitle_files':records,'metadata':metadata,'metadata_scope':'All215 SRT texts/times,7 chapters, title/description and combined upload details checked against adopted measured timeline and independent square truth.'}


@lru_cache(maxsize=96)
def font(size):
    return ImageFont.truetype(str(FONT),size)


@lru_cache(maxsize=2048)
def glyph_alpha(text,size):
    if '\n' in text:
        lines=[glyph_alpha(line,size) for line in text.split('\n')]
        bounds=[im.point(lambda x:255 if x>=128 else 0).getbbox() for im in lines]
        width=max(b[2]-b[0] for b in bounds);height=sum(b[3]-b[1] for b in bounds)+14*(len(lines)-1)
        layer=Image.new('L',(width+80,height+80));y=40
        for im,b in zip(lines,bounds):
            layer.paste(im.crop(b),(40+round((width-b[2]+b[0])/2),y));y+=b[3]-b[1]+14
        return layer
    face=font(size);b=face.getbbox(text)
    layer=Image.new('L',(b[2]-b[0]+80,b[3]-b[1]+80))
    ImageDraw.Draw(layer).text((40-b[0],40-b[1]),text,font=face,fill=255)
    return layer


def rgb(hexadecimal):
    return tuple(bytes.fromhex(hexadecimal.lstrip('#')))


def color_mask(image,color,tolerance=52):
    color=rgb(color) if isinstance(color,str) else color
    masks=[c.point(lambda x,target=t:255 if abs(x-target)<=tolerance else 0) for c,t in zip(image.split()[:3],color)]
    return ImageChops.darker(ImageChops.darker(masks[0],masks[1]),masks[2])


def iou(a,b):
    union=ImageChops.lighter(a,b).histogram()[255]
    return ImageChops.darker(a,b).histogram()[255]/union if union else 0


def observed_ink(image,colors=(INK,TEAL,BLUE,GOLD),fill='#fffaf0'):
    """Half-contrast glyph cores, independent of producer component masks."""
    bg=rgb(fill);result=Image.new('L',image.size)
    for color in colors:
        fg=rgb(color);channel=max(range(3),key=lambda k:abs(bg[k]-fg[k]))
        limit=(bg[channel]+fg[channel])/2
        mask=image.getchannel(channel).point(lambda value:255 if value<limit else 0)
        mask=ImageChops.darker(mask,color_mask(image,fg,78))
        result=ImageChops.lighter(result,mask)
    return result


@lru_cache(maxsize=1)
def count_underlay():
    """Independent background only; no producer geometry or foreground mask."""
    source=DESIGN/'generation-batches/lake-square-20261112-a/source/frozen-lake-clean-plate.png'
    plate=ImageOps.fit(Image.open(source).convert('RGB'),SIZE,Image.Resampling.LANCZOS)
    ImageDraw.Draw(plate).rounded_rectangle((240,178,1680,310),radius=28,fill='#fffaf0',outline='#d8d1be',width=2)
    return plate


def observed_ink_on_background(image,background,colors,alpha_equivalent=128):
    """Half contrast against the actual clean-plate pixel under a moving token.

    A constant ice average biases the35px glyph when it crosses the cream
    formula panel. This retains the same half-alpha criterion and1px bounds.
    """
    result=Image.new('L',image.size)
    luminance=lambda im:im.convert('L',(.2126,.7152,.0722,0))
    for color in colors:
        fg=rgb(color);fg_y=sum(w*c for w,c in zip((.2126,.7152,.0722),fg))
        threshold=luminance(background).point(lambda b:round(b+(fg_y-b)*alpha_equivalent/255))
        mask=ImageChops.subtract(threshold,luminance(image)).point(lambda x:255 if x>0 else 0)
        # The separated-token ROI contains no other ink. A78RGB palette gate
        # would discard legitimate half-alpha teal edge pixels (red contrast
        # can exceed200), recreating the single-channel extraction bias.
        result=ImageChops.lighter(result,mask)
    return result


def label_record(name,text,size,box,colors=(INK,),fill='#fffaf0'):
    return {'name':name,'text':text,'size':size,'box':tuple(box),'colors':tuple(colors),'fill':fill}


@lru_cache(maxsize=4096)
def reference_ink(text,size,box,observation,divisor=1,dx=0,dy=0):
    alpha=glyph_alpha(text,size);b=alpha.point(lambda v:255 if v>=128 else 0).getbbox()
    layer=Image.new('L',(observation[2]-observation[0],observation[3]-observation[1]))
    x=round((box[0]+box[2]-b[0]-b[2])/2)-observation[0]+dx
    y=round((box[1]+box[3]-b[1]-b[3])/2)-observation[1]+dy
    layer.paste(alpha,(x,y))
    if divisor!=1:layer=layer.resize((layer.width//divisor,layer.height//divisor),Image.Resampling.BOX)
    return layer.point(lambda v:255 if v>=128 else 0)


def inspect_label(image,row,frame,divisor=1,alignment=True):
    box=row['box'];margin=12
    # Observation is larger than the target. Empty/edge-touching components
    # cannot pass merely because a tight target crop hid their missing pixels.
    alpha=glyph_alpha(row['text'],row['size']);ink=alpha.point(lambda v:255 if v>=128 else 0).getbbox()
    origin=(round((box[0]+box[2]-ink[0]-ink[2])/2),round((box[1]+box[3]-ink[1]-ink[3])/2))
    expected_bounds=(ink[0]+origin[0],ink[1]+origin[1],ink[2]+origin[0],ink[3]+origin[1])
    observation=(max(0,(expected_bounds[0]-margin)//divisor*divisor),max(0,(expected_bounds[1]-margin)//divisor*divisor),
                 min(1920,math.ceil((expected_bounds[2]+margin)/divisor)*divisor),min(1080,math.ceil((expected_bounds[3]+margin)/divisor)*divisor))
    actual_crop=image.crop(tuple(v//divisor for v in observation))
    if row.get('background_kind')=='count-underlay':
        background=count_underlay().crop(observation)
        if divisor!=1:background=background.resize(actual_crop.size,Image.Resampling.BOX)
        actual=observed_ink_on_background(actual_crop,background,row['colors'])
    else:actual=observed_ink(actual_crop,row['colors'],row['fill'])
    candidates=[(iou(actual,reference_ink(row['text'],row['size'],box,observation,divisor,dx,dy)),dx,dy)
                for dy in (-1,0,1) for dx in (-1,0,1)]
    score,dx,dy=max(candidates)
    bounds=actual.getbbox();threshold=.92 if divisor==1 else .84
    record={'name':row['name'],'frame':frame,'text':row['text'],'font_size_px':row['size'],'content_box':list(box),'observation_box':list(observation),'independent_glyph_iou':score,'minimum_glyph_iou':threshold,'divisor':divisor,'glyph_candidate_shift_px':[dx,dy],'actual_nonempty':bool(bounds),'passed':bool(bounds) and score>=threshold}
    if divisor==1 and alignment and bounds:
        if row.get('background_kind')=='count-underlay':
            variants=[observed_ink_on_background(actual_crop,background,row['colors'],a).getbbox() for a in (96,112,128,144,160)]
            stable=all(variants) and all(max(b[k] for b in variants)-min(b[k] for b in variants)<=1 for k in range(4))
            boxes=[[b[k]+observation[k%2] for k in range(4)] for b in variants] if all(variants) else []
            centers=[[(b[0]+b[2])/2,(b[1]+b[3])/2] for b in boxes]
            estimate=[median(c[k] for c in centers) for k in range(2)] if centers else [math.inf,math.inf]
            target=[(box[0]+box[2])/2,(box[1]+box[3])/2]
            deltas=[estimate[k]-target[k] for k in range(2)]
            contained=bool(boxes) and all(centering_report(box,b,tolerance_px=1)['contained'] for b in boxes)
            touches=any(b and (b[0]==0 or b[1]==0 or b[2]==actual.width or b[3]==actual.height) for b in variants)
            failures=[]
            if abs(deltas[0])>1:failures.append('horizontal_center_estimate_mismatch')
            if abs(deltas[1])>1:failures.append('vertical_center_estimate_mismatch')
            if not contained:failures.append('foreground_outside_content_box')
            if not stable:failures.append('alpha_boundary_uncertainty_exceeds_one_pixel')
            if touches:failures.append('foreground_touches_measurement_edge')
            alignment_result={'name':f'{frame}/{row["name"]}','measurement':'coordinatewise-median-of-five-actual-foreground-centers','content_box_xyxy':list(box),'target_center_px':target,'estimated_visible_center_px':estimate,'delta_x_px':deltas[0],'delta_y_px':deltas[1],'tolerance_px':1,'horizontal_centered':abs(deltas[0])<=1,'vertical_centered':abs(deltas[1])<=1,'contained':contained,'measurement_origin_px':list(observation[:2]),'touches_measurement_edge':touches,'alpha_equivalents':[96,112,128,144,160],'actual_visible_boxes_per_alpha':boxes,'actual_centers_per_alpha':centers,'edge_spreads_px':[max(b[k] for b in boxes)-min(b[k] for b in boxes) for k in range(4)] if boxes else None,'each_edge_spread_at_most_one_pixel':stable,'nominal128_actual_bounds':list(bounds),'failures':failures,'passed':not failures,'estimator_scope':'All five actual bounds remain recorded. Estimated center is not a single observed bbox, not median edges and not the threshold nearest the expected target.'}
        else:alignment_result=raster_centering_report(actual,box,origin_xy=observation[:2],name=f'{frame}/{row["name"]}',tolerance_px=1)
        record.update(alignment_result,horizontal='center',vertical='center',resolution_px=list(SIZE))
        record['passed']=alignment_result['passed'] and score>=threshold
    return record


def mask_union(image,colors,tolerance=24):
    mask=Image.new('L',image.size)
    for color in colors:mask=ImageChops.lighter(mask,color_mask(image,color,tolerance))
    return mask


def component_filter(mask,minimum_pixels=32):
    """Run-length4-connected components; remove tiny isolated palette noise."""
    raw=mask.tobytes();width,height=mask.size;parents=[];runs=[];previous=[]
    def root(k):
        while parents[k]!=k:parents[k]=parents[parents[k]];k=parents[k]
        return k
    for y in range(height):
        current=[]
        for match in re.finditer(b'\xff+',raw[y*width:(y+1)*width]):
            a,b=match.span();overlaps={root(k) for x,z,k in previous if a<z and x<b}
            if overlaps:
                k=min(overlaps)
                for other in overlaps:parents[other]=k
            else:k=len(parents);parents.append(k)
            current.append((a,b,k));runs.append((y,a,b,k))
        previous=current
    counts=Counter()
    for _,a,b,k in runs:counts[root(k)]+=b-a
    clean=bytearray(raw)
    for y,a,b,k in runs:
        if counts[root(k)]<minimum_pixels:clean[y*width+a:y*width+b]=b'\0'*(b-a)
    return Image.frombytes('L',mask.size,bytes(clean)),sum(n>=minimum_pixels for n in counts.values())


def palette_distance(image,color):
    target=Image.new('RGB',image.size,color);parts=ImageChops.difference(image,target).split()
    return ImageChops.add(ImageChops.add(parts[0],parts[1]),parts[2])


def nearest_fill_mask(image,colors,backgrounds=('#f1fbfb','#86afb9')):
    """Actual pixel classification by closer palette, not the enclosing frame.

    Encoded chroma may move an exact fill by more than9RGB at a tile edge.
    The midpoint to the actual surrounding/outline colors preserves the0.5
    foreground criterion without expanding the1px coordinate tolerance.
    """
    result=Image.new('L',image.size)
    for color in colors:
        distance=palette_distance(image,color);mask=color_mask(image,color,30)
        for bg in backgrounds:
            closer=ImageChops.subtract(palette_distance(image,bg),distance).point(lambda x:255 if x>0 else 0)
            mask=ImageChops.darker(mask,closer)
        result=ImageChops.lighter(result,mask)
    return result


def inspect_grid(image,n,frame,progress=1,block=False,lshape=False,divisor=1):
    """Verify unit/block fill pixels, never a parent-frame rectangle as proxy."""
    area=tuple(v//divisor for v in GRID);crop=image.crop(area)
    colors=['#75bdc8','#c7e2e9'] if not lshape else ['#96c8d1','#e5aa6f','#f4cf90']
    # The blue-gray parent outline is only17RGB from the blue unit fill;
    # use its actual color separation so the outline cannot proxy cell bounds.
    actual=mask_union(crop,colors,9)
    # Ignore only isolated1px lake texture that happens to share the palette
    # outside the rounded plane. Axis-aligned tile interiors are unchanged.
    # Explicit zero padding prevents PIL's edge replication from turning a
    # two-pixel corner speck into a connected fill at the observation edge.
    actual=ImageOps.expand(actual,5,0).filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5)).crop((5,5,crop.width+5,crop.height+5))
    actual,observed_components=component_filter(actual)
    # Reclassify chroma-smeared interior cell edges within2px of a strict core.
    # The group envelope may grow by at most1px from its observed core bbox;
    # this cannot add the unrelated parent corner or move a measured group.
    classified=nearest_fill_mask(crop,colors)
    core_bounds=actual.getbbox();recovery=Image.new('L',actual.size)
    if core_bounds:
        envelope=Image.new('L',actual.size)
        ImageDraw.Draw(envelope).rectangle((core_bounds[0]-1,core_bounds[1]-1,core_bounds[2],core_bounds[3]),fill=255)
        recovery=ImageChops.darker(envelope,ImageChops.darker(classified,actual.filter(ImageFilter.MaxFilter(5))))
    actual=ImageChops.lighter(actual,recovery)
    expected=Image.new('L',(480,480));ed=ImageDraw.Draw(expected)
    count=10 if block else n;cells=[]
    if n and (n<=10 or block):
        for row in range(count):
            for col in range(count):
                rect=(round(col*480/count)+2,round(row*480/count)+2,round((col+1)*480/count)-3,round((row+1)*480/count)-3)
                if lshape:
                    lit=(row<count-1 and col<count-1 or row==count-1 and col<count-1 and progress>=.25
                         or col==count-1 and row<count-1 and progress>=.52 or row==col==count-1 and progress>=.78)
                    if not lit:continue
                ed.rectangle(rect,fill=255)
                # The labelled source block has a3px gold magnifier outline.
                # Its central fill still must be the same counted parent block.
                trim=7 if block and row==0 and col==9 else 2
                inner=(max(0,math.ceil((rect[0]+trim)/divisor)),max(0,math.ceil((rect[1]+trim)/divisor)),
                       min(crop.width,math.floor((rect[2]-trim+1)/divisor)),min(crop.height,math.floor((rect[3]-trim+1)/divisor)))
                c=crop.crop(inner)
                role='old' if lshape and row<count-1 and col<count-1 else 'corner' if lshape and row==count-1 and col==count-1 else 'new' if lshape else 'lit' if row<math.floor(count*progress+1e-9) else 'unlit'
                color={'old':'#96c8d1','corner':'#f4cf90','new':'#e5aa6f','lit':'#75bdc8','unlit':'#c7e2e9'}[role]
                mask=color_mask(c,color,28);coverage=mask.histogram()[255]/(c.width*c.height) if c.width*c.height else 0
                cells.append({'row':row,'column':col,'role':role,'units':100 if block else 1,'actual_color_coverage':coverage,'passed':coverage>=.98})
    if divisor!=1:expected=expected.resize(actual.size,Image.Resampling.BOX).point(lambda x:255 if x>=128 else 0)
    score=iou(actual,expected) if n else 1 if actual.getbbox() is None else 0
    outside=ImageChops.subtract(actual,expected.filter(ImageFilter.MaxFilter(3))).getbbox()
    missing=ImageChops.subtract(expected.filter(ImageFilter.MinFilter(3)),actual).getbbox()
    # Subpixel codec edges and the intentional block magnifier may interrupt
    # a tiny part of a filled cell. Every cell is independently centered below;
    # a high shape IoU therefore cannot excuse a translated array or cell.
    shape_pass=score>=.96 or not outside and not missing
    cell_alignments=[]
    if divisor==1:
        for cell in cells:
            row,col=cell['row'],cell['column'];x0,y0=round(col*480/count),round(row*480/count)
            x1,y1=round((col+1)*480/count),round((row+1)*480/count)
            cm=actual.crop((x0,y0,x1,y1))
            target=(GRID[0]+x0,GRID[1]+y0,GRID[0]+x1,GRID[1]+y1)
            ca=raster_centering_report(cm,target,origin_xy=target[:2],name=f'{frame}/cell-{row}-{col}',tolerance_px=1) if cm.getbbox() else {'passed':False,'failure':'empty-actual-cell'}
            cell_alignments.append(ca)
    result={'frame':frame,'n':n,'kind':'grouped-blocks' if block else 'L-shape' if lshape else 'exact-unit-cells','divisor':divisor,'expected_cell_count':len(cells),'observed_connected_cell_count':observed_components,'observed_verified_cell_count':sum(c['passed'] for c in cells),'total_units':sum(c['units'] for c in cells),'fill_shape_iou':score,'minimum_fill_shape_iou':.96,'alternative_strict_shape_gate':'Every boundary pixel within1 native pixel plus all per-cell cores>=98%; same1px decoded geometry tolerance','outside_one_pixel_shape':list(outside) if outside else None,'missing_more_than_one_pixel_inside_shape':list(missing) if missing else None,'component_minimum_pixels':32,'cells':cells,'passed':observed_components==len(cells) and shape_pass and all(c['passed'] for c in cells)}
    if n and divisor==1 and not lshape or n and divisor==1 and progress>=.78:
        align=raster_centering_report(actual,GRID,origin_xy=GRID[:2],name=f'{frame}/actual-unit-fill',tolerance_px=1)
        result['alignment']=align;result['passed'] &= align['passed']
    if lshape:
        result['role_counts']=dict(Counter(c['role'] for c in cells))
        expected_roles={'old':16}
        if progress>=.25:expected_roles['new']=4
        if progress>=.52:expected_roles['new']=8
        if progress>=.78:expected_roles['corner']=1
        result['passed'] &= result['role_counts']==expected_roles
    result['cell_alignments']=cell_alignments
    result['passed'] &= all(c['passed'] for c in cell_alignments)
    return result


def label_geometry(row):
    alpha=glyph_alpha(row['text'],row['size']);ink=alpha.point(lambda v:255 if v>=128 else 0).getbbox();box=row['box']
    origin=(round((box[0]+box[2]-ink[0]-ink[2])/2),round((box[1]+box[3]-ink[1]-ink[3])/2))
    bounds=(ink[0]+origin[0],ink[1]+origin[1],ink[2]+origin[0],ink[3]+origin[1])
    fb=font(row['size']).getbbox(row['text']) if '\n' not in row['text'] else (0,0,0,0)
    baseline=(origin[0]+40-fb[0],origin[1]+40-fb[1])
    return alpha,origin,bounds,baseline


def inspect_compound(image,rows,frame,divisor=1):
    """Formula and its same-value copies as a union, including source contact.

    Separate padded observation islands exclude unrelated ruler/background
    strokes. Every visible mathematical character is also locally inspected.
    This does not discard contact pixels to make a formula-only test pass.
    """
    geometry=[label_geometry(r) for r in rows]
    left=min(g[2][0] for g in geometry)-12;top=min(g[2][1] for g in geometry)-12
    right=max(g[2][2] for g in geometry)+12;bottom=max(g[2][3] for g in geometry)+12
    area=(max(0,left//divisor*divisor),max(0,top//divisor*divisor),min(1920,math.ceil(right/divisor)*divisor),min(1080,math.ceil(bottom/divisor)*divisor))
    expected=Image.new('L',(area[2]-area[0],area[3]-area[1]));observations=Image.new('L',expected.size);od=ImageDraw.Draw(observations)
    for alpha,origin,bounds,_ in geometry:
        piece=Image.new('L',expected.size);piece.paste(alpha,(origin[0]-area[0],origin[1]-area[1]));expected=ImageChops.lighter(expected,piece)
        od.rectangle((bounds[0]-area[0]-12,bounds[1]-area[1]-12,bounds[2]-area[0]+11,bounds[3]-area[1]+11),fill=255)
    if divisor!=1:
        expected=expected.resize((expected.width//divisor,expected.height//divisor),Image.Resampling.BOX)
        observations=observations.resize(expected.size,Image.Resampling.BOX)
    expected=expected.point(lambda x:255 if x>=128 else 0)
    crop=image.crop(tuple(v//divisor for v in area));actual=observed_ink(crop,(INK,TEAL,BLUE,GOLD),'#fffaf0');actual=ImageChops.darker(actual,observations)
    eb,ab=expected.getbbox(),actual.getbbox();score=iou(actual,expected);limit=.91 if divisor==1 else .81
    dx=((ab[0]+ab[2]-eb[0]-eb[2])*divisor/2) if ab and eb else None
    dy=((ab[1]+ab[3]-eb[1]-eb[3])*divisor/2) if ab and eb else None
    passed=bool(ab and eb) and score>=limit and (divisor!=1 or abs(dx)<=1 and abs(dy)<=1)
    chars=[]
    for row,(_,_,_,baseline) in zip(rows,geometry):
        if row['name'] not in ('working-equation','general-rule','l-growth-equation') and not row['name'].startswith(('moving-copy','horizontal-side','vertical-side')):continue
        face=font(row['size'])
        for k,ch in enumerate(row['text']):
            if ch.isspace():continue
            b=face.getbbox(ch);start=face.getlength(row['text'][:k])
            box=(math.floor(baseline[0]+start+b[0]-2),math.floor(baseline[1]+b[1]-2),math.ceil(baseline[0]+start+b[2]+2),math.ceil(baseline[1]+b[3]+2))
            local=tuple((v-area[i%2])//divisor for i,v in enumerate(box))
            a,e=actual.crop(local),expected.crop(local);cs=iou(a,e);ok=cs>=(.86 if divisor==1 else .70)
            chars.append({'label':row['name'],'position':k,'character':ch,'box':list(box),'iou':cs,'passed':ok});passed &= ok
    return {'name':'formula-and-axis-inputs','frame':frame,'resolution_divisor':divisor,'expected_formula':rows[0]['text'],'observation_box':list(area),'independent_union_glyph_iou':score,'minimum_union_iou':limit,'delta_x_px':dx,'delta_y_px':dy,'tolerance_px':1 if divisor==1 else None,'actual_visible_box':list(ab) if ab else None,'expected_visible_box':list(eb) if eb else None,'character_checks':chars,'passed':passed,'source_contact_policy':'Same-value glyph contact is checked as actual union, not masked out.'}


def smooth_tick(raw):
    q=max(0,min(1,raw));return round((3*q*q-2*q*q*q)*30)


def independent_state(plan,events,states,at):
    """Apply the agreed editorial timing contract to measured audio cues."""
    by={e['id']:e for e in events};ends=[s['voice_end_s'] for s in states]
    completed=sum(end<=at for end in ends)
    event=events[max(0,bisect_right([e['start_s'] for e in events],at)-1)]
    segments=scene_contract(events,plan['duration_frames'])
    segment=segments[max(0,bisect_right([s['start_frame'] for s in segments],round(at*FPS))-1)]
    if segment['mode']=='intro':return {'mode':'intro','cue':event['id'],'n':0,'completed':completed}
    if segment['mode']=='teaching':
        event=by[segment['cue']]
        return {'mode':'teaching','cue':event['id'],'n':int(event['id'][1:]),'completed':completed,'lesson_tick':smooth_tick((at-event['start_s'])/event['duration_s'])}
    if segment['mode']=='outro':return {'mode':'outro','cue':'O01','n':100,'completed':completed}
    n=segment['n'];s=states[n];e=by[f'E{n:03}'];h=e.get('highlight_timing',{})
    start,end=e['start_s'],e['end_s'];duration=end-start
    times=h.get('times_start_s',start+.27*duration);second=h.get('b_start_s',start+.50*duration);equals=h.get('equals_start_s',start+.77*duration)
    commit=s.get('result_start_s',s['voice_start_s']-.12);result=at>=commit
    a=30 if result else smooth_tick((at-start-.04)/max(.20,second-start-.04))
    b=30 if result else smooth_tick((at-second)/max(.20,equals-second+.05))
    fill=30 if result else smooth_tick((at-equals)/max(.04,commit-equals))
    return {'mode':'count','cue':event['id'],'n':n,'completed':completed,'result':result,'a_tick':a,'b_tick':b,'fill_tick':fill,'highlight':'result' if result else 'first' if at<times else 'times' if at<second else 'second' if at<equals else 'equals'}


_scene_contract_cache={}


def scene_contract(events,duration_frames):
    key=(id(events),duration_frames)
    if key in _scene_contract_cache:return _scene_contract_cache[key]
    by={e['id']:e for e in events};segments=[{'mode':'intro','cue':'I01','n':0,'start_frame':0}]
    for n in range(101):
        lead=.35 if n in (0,1,5,11,33) else 0
        segments.append({'mode':'count','cue':f'E{n:03}','n':n,'start_frame':frame_at(by[f'E{n:03}']['start_s']-lead)})
        if f'T{n:03}' in by:segments.append({'mode':'teaching','cue':f'T{n:03}','n':n,'start_frame':frame_at(by[f'T{n:03}']['start_s']-.20)})
    segments.append({'mode':'outro','cue':'O01','n':100,'start_frame':frame_at(by['O01']['start_s']-.20)})
    segments.sort(key=lambda s:s['start_frame'])
    for k,s in enumerate(segments):s['end_frame']=segments[k+1]['start_frame'] if k+1<len(segments) else duration_frames
    _scene_contract_cache[key]=segments;return segments


def fade_level(frame,duration_frames,cuts):
    level=round(max(0,1-frame/18)*255) if frame<18 else round(max(0,min(1,(frame-duration_frames+30)/29))*255)
    return max([level]+[round((1-abs(frame-cut)/5)*255) for cut in cuts if abs(frame-cut)<=5])


def export_final_aac_clips(plan,events,video,ffmpeg,out_dir):
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=False)
    manifest={'schema_version':1,'kind':'square-final-aac-event-excerpts','measurement_status':'measured','numbers':[],'dialogue':[],'source_video_sha256':sha(video),'excerpt_format':{'sample_rate_hz':RATE,'channels':1,'sample_width_bits':16},'scope':'Actual final AAC decoded left channel, up to80ms context before/after each cue, bounded before neighboring speech. Fresh ASR/CTC inputs; not newly adopted source WAVs.'}
    with tempfile.TemporaryDirectory(prefix='square-final-aac-') as tmp:
        target=Path(tmp)/'final.wav'
        subprocess.run([str(ffmpeg),'-nostdin','-v','error','-xerror','-i',str(video),'-map','0:a:0','-ar',str(RATE),'-ac','2','-c:a','pcm_s16le',str(target)],check=True)
        with wave.open(str(target),'rb') as track:
            for k,event in enumerate(events):
                previous=events[k-1]['end_s'] if k else 0;following=events[k+1]['start_s'] if k+1<len(events) else plan['duration_s']
                a=sample(event['start_s']-min(.08,max(0,(event['start_s']-previous)/2)))
                b=sample(event['end_s']+min(.08,max(0,(following-event['end_s'])/2)))
                track.setpos(a);data=array('h',pcm16(track.readframes(b-a))[::2]);destination=out_dir/(event['id']+'.wav')
                with wave.open(str(destination),'wb') as clip:clip.setparams((1,2,RATE,len(data),'NONE','not compressed'));clip.writeframes(data.tobytes())
                row={'id':event['id'],'kind':'final-aac-count' if event['id'].startswith('N') else 'final-aac-dialogue','path':destination.name,'spoken_text':event['text'],'text':event['text'],'duration_s':len(data)/RATE,'clip_duration_s':len(data)/RATE,'sha256':sha(destination),'speech_offset_s':event['start_s']-a/RATE,'nominal_event_duration_s':event['duration_s'],'event_start_s':event['start_s'],'event_end_s':event['end_s'],'excerpt_start_s':a/RATE,'excerpt_end_s':b/RATE,'guard_before_s':event['start_s']-a/RATE,'guard_after_s':b/RATE-event['end_s'],'number':event.get('value'),'index':event.get('index')}
                manifest['numbers' if event['id'].startswith('N') else 'dialogue'].append(row)
    write_json(out_dir/'measurements.json',manifest)
    exported=json.loads(json.dumps(manifest))
    for row in exported['numbers']+exported['dialogue']:row['path']=str((out_dir/row['path']).resolve().relative_to(ROOT))
    write_json(out_dir/'final-aac-manifest.json',exported)
    return {'manifest':str(out_dir/'final-aac-manifest.json'),'events':len(events),'source_video_sha256':manifest['source_video_sha256']}


def count_labels(state,truth,words):
    n=state['n'];result=state['result'];formula=f'{n}² = {n} × {n} = '+(f'{truth[n]:,}' if result else '?')
    main=label_record('working-equation',formula,82,(264,190,1656,292),(INK,TEAL,GOLD))
    rows=[main];alpha,origin,_,baseline=label_geometry(main);face=font(82);fb=face.getbbox(formula)
    starts=[]
    for prefix in (f'{n}² = ',f'{n}² = {n} × '):
        factor=Image.new('L',alpha.size)
        ImageDraw.Draw(factor).text((40-fb[0]+face.getlength(prefix),40-fb[1]),str(n),font=face,fill=255)
        ink=factor.point(lambda v:255 if v>=128 else 0).getbbox()
        starts.append((origin[0]+(ink[0]+ink[2])/2,origin[1]+(ink[1]+ink[3])/2))
    for k,tick in enumerate((state['a_tick'],state['b_tick'])):
        if not tick:continue
        p=tick/30;sx,sy=starts[k]
        if k==0:x,y=(sx,sy+(351-sy)*p/.2) if p<.2 else (sx+(960-sx)*(p-.2)/.8,351)
        elif p<.3:x,y=sx,sy+(300-sy)*p/.3
        elif p<.7:x,y=sx+(632-sx)*(p-.3)/.4,300
        else:x,y=632,300+(641-300)*(p-.7)/.3
        box=((850,331,1070,375) if k==0 else (592,606,672,676)) if tick==30 else (x-75,y-29,x+75,y+29)
        name=('horizontal-side' if k==0 else 'vertical-side') if tick==30 else f'moving-copy-{k}'
        row=label_record(name,str(n),35,box,(TEAL if k==0 else BLUE,),fill='#edf6f8')
        if tick!=30:row['background_kind']='count-underlay'
        rows.append(row)
    reading=label_record('natural-reading',words[n],35,(350,922,1570,977),(INK,),fill='#edf6f8') if result else label_record('generation-caption','Equal width. Equal height. One square.',31,(350,922,1570,977),(TEAL,),fill='#edf6f8')
    return rows,reading


def shared_labels(state):
    return [label_record('episode-title','SQUARE NUMBERS',48,(100,49,1820,107),(INK,),fill='#f5faf7'),
            label_record('episode-subtitle','NUM-NUM NUMBERS · THE FROZEN LAKE',22,(100,113,1820,143),(TEAL,),fill='#f5faf7'),
            label_record('completed-progress',f'Squares counted: {state["completed"]} / 101',24,(180,1027,1740,1061),('#6b8190',),fill='#edf6f8')]


def lesson_labels(state,truth,words):
    mode,n=state['mode'],state['n'];labels=[];compound=[]
    if mode in ('intro','outro'):
        compound=[label_record('general-rule','n² = n × n',82,(264,190,1656,292))]
    if mode=='intro':
        prompts={
            'I01':(['Hello!','Let’s make square numbers.'],['One matching pair.','One square.']),
            'I02':(['The same number','across …'],['… and down.','Both sides match.']),
            'I03':(['The little 2','means squared.'],['n × n','A number times itself.']),
            'I04':(['Move the numbers.','Set both sides.'],['Watch the square','take shape.']),
            'I05':(['Start with n = 0.'],['Continue to n = 100.']),
            'I06':(['One matching pair.'],['One new result.']),
            'I07':(['Ready?'],['Let’s see what it makes.'])}
        left,right=prompts.get(state['cue'],prompts['I07'])
        labels.extend([label_record('intro-left-prompt','\n'.join(left),32,(135,430,695,595),(TEAL,),fill='#edf6f8'),
                       label_record('intro-right-prompt','\n'.join(right),32,(1225,430,1795,595),(TEAL,),fill='#edf6f8'),
                       label_record('intro-width','n',30,(880,324,1040,354),(TEAL,),fill='#edf6f8'),
                       label_record('intro-height','n',30,(735,475,790,555),(BLUE,),fill='#edf6f8'),
                       label_record('intro-plane','SQUARED' if state['cue']=='I03' else 'SQUARE',35,(820,480,1100,555),(GOLD if state['cue']=='I03' else '#6b8190',),fill='#f1fbfb')])
    elif mode=='outro':
        beginning=', '.join(str(v) for v in truth[:11])+', …';ending='…, '+', '.join(f'{v:,}' for v in truth[-3:])
        labels.extend([label_record('sequence-beginning',beginning,52,(180,369,1740,440),(TEAL,),fill='#edf6f8'),
                       label_record('sequence-ending',ending,65,(310,511,1610,595),(INK,),fill='#edf6f8'),
                       label_record('finale-total','101 terms counted. The rule keeps going.',39,(280,653,1640,715),(GOLD,),fill='#edf6f8')])
    elif n==4:
        p=state['lesson_tick']/30
        compound=[label_record('l-growth-equation','4² + (4 + 4 + 1) = 5²',78,(264,190,1656,292))]
        lines=['16 old tiles','+ 4 in a row'] if p<.52 else ['16 old tiles','+ 4 + 4'] if p<.78 else ['16 old tiles','+ 4 + 4 + 1','9 new tiles']
        labels.extend([label_record('look-ahead-mode','LOOK AHEAD',26,(840,335,1080,378),(GOLD,),fill='#edf6f8'),
                       label_record('l-count-explanation','\n'.join(lines),35,(145,442,590,630),(GOLD,),fill='#fff7e8'),
                       label_record('l-no-early-answer','Four in a row. Four in a column. One corner.',30,(190,925,1330,977),(TEAL,),fill='#edf6f8')])
    else:
        compound=[label_record('working-equation',f'{n}² = {n} × {n} = {truth[n]:,}',82,(264,190,1656,292),(INK,TEAL,GOLD))]
        if n==32:
            labels.extend([label_record('area-900','900',78,(735,422,1155,832),(INK,),fill='#92c6cf'),
                           label_record('area-60-right','60',42,(1248,500,1408,565),(GOLD,),fill='#edf6f8'),
                           label_record('area-60-bottom','60',42,(1225,812,1345,874),(GOLD,),fill='#edf6f8'),
                           label_record('area-4','4',42,(1235,695,1335,760),(INK,),fill='#edf6f8'),
                           label_record('top-thirty','30',32,(735,341,1155,381),(TEAL,),fill='#edf6f8'),
                           label_record('top-two','2',30,(1170,341,1200,381),(GOLD,),fill='#edf6f8'),
                           label_record('left-thirty','30',30,(650,422,704,832),(BLUE,),fill='#edf6f8'),
                           label_record('left-two','2',30,(650,852,704,882),(GOLD,),fill='#edf6f8'),
                           label_record('area-decomposition-key','REPLAY: 31² = 961\n32 = 30 + 2\n900 + 60 + 60 + 4',30,(145,443,615,630),(GOLD,),fill='#fff7e8'),
                           label_record('natural-reading',words[n],35,(350,922,1570,977),(INK,),fill='#edf6f8')])
        else:
            labels.extend([label_record('horizontal-side',str(n),35,(850,331,1070,375),(TEAL,),fill='#edf6f8'),label_record('vertical-side',str(n),35,(592,606,672,676),(BLUE,),fill='#edf6f8')])
            if n==0:
                labels.extend([label_record('zero-empty-label','NO UNIT TILES',40,(730,600,1190,664),('#6b8190',),fill='#f1fbfb'),label_record('teaching-caption','No unit tiles. Zero times zero is zero.',28,(350,922,1570,977),(TEAL,),fill='#edf6f8')])
            elif n==10:
                labels.append(label_record('teaching-caption','Ten by ten: 100 unit tiles.\nBigger squares use a labelled diagram.',28,(210,916,1320,998),(TEAL,),fill='#edf6f8'))
            elif n==100:
                labels.extend([label_record('teaching-caption','100 blocks. Each block contains 100 unit squares.',28,(640,922,1680,977),(TEAL,),fill='#edf6f8'),
                               label_record('block-key-title','1 BLOCK = 100 UNITS',29,(1265,427,1760,477),(TEAL,),fill='#f8fbf6'),
                               label_record('block-key-subtitle','10 × 10 unit squares',28,(1270,495,1755,540),(INK,),fill='#f8fbf6'),
                               label_record('block-key-no-addition','ZOOM KEY · THE SAME BLOCK',22,(1260,840,1765,875),('#6b8190',),fill='#f8fbf6')])
    return compound,labels


def inspect_schematic(image,n,frame,progress=1,divisor=1):
    crop=image.crop(tuple(v//divisor for v in GRID));mask=nearest_fill_mask(crop,['#9acbd4'])
    # Dark labels intentionally sit inside the schematic; they are checked as
    # separate glyph groups, while the actual colored extent measures the face.
    mask=ImageOps.expand(mask,5,0).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3)).crop((5,5,crop.width+5,crop.height+5));mask,_=component_filter(mask);b=mask.getbbox()
    if not progress:return {'frame':frame,'n':n,'intentional_empty_fill':True,'passed':b is None}
    expected_bottom=min(round(480*progress),475)+1
    if expected_bottom<=4:return {'frame':frame,'n':n,'intentional_near_empty_fill':True,'passed':True,'scope':'Sub4px growth excluded from extent measurement, not from glyph checking'}
    target=(724,406,1196,402+expected_bottom);absolute=[b[0]*divisor+720,b[1]*divisor+402,b[2]*divisor+720,b[3]*divisor+402] if b else None
    errors=[abs(a-e) for a,e in zip(absolute,target)] if absolute else [999]*4
    return {'frame':frame,'n':n,'actual_visible_box':absolute,'target_visible_box':list(target),'horizontal':'center','vertical':'top; intended downward growth','edge_deltas_abs_px':errors,'tolerance_px':1 if divisor==1 else 2,'passed':all(v<=(1 if divisor==1 else 2) for v in errors)}


def inspect_block_key(image,frame):
    field=(1385,570,1635,820);actual=nearest_fill_mask(image.crop(field),['#75bdc8'],('#f8fbf6',));expected=Image.new('L',(250,250));d=ImageDraw.Draw(expected);cells=[]
    for row in range(10):
        for col in range(10):
            x,y=16+col*22,16+row*22;d.rectangle((x,y,x+19,y+19),fill=255)
            color=image.getpixel((field[0]+x+10,field[1]+y+10));cells.append(max(abs(c-t) for c,t in zip(color,rgb('#75bdc8')))<=10)
    align=raster_centering_report(actual,field,origin_xy=field[:2],name=f'{frame}/same-block-100-unit-key',tolerance_px=1)
    score=iou(actual,expected)
    return {'frame':frame,'expected_unit_cells':100,'actual_verified_centers':sum(cells),'adds_to_counted_total':False,'fill_iou':score,'alignment':align,'passed':sum(cells)==100 and score>=.95 and align['passed']}


def inspect_area(image,frame):
    crop=image.crop(GRID);results=[]
    specifications=[('30×30',900,'#92c6cf',[(2,2,449,449)]),('two30×2bands',120,'#e3b179',[(450,2,477,449),(2,450,449,477)]),('2×2',4,'#f3d692',[(450,450,477,477)])]
    for name,value,color,rects in specifications:
        actual=color_mask(crop,color,9);expected=Image.new('L',(480,480));d=ImageDraw.Draw(expected)
        for rect in rects:d.rectangle(rect,fill=255)
        score=iou(actual,expected)
        # The independently verified900 label intentionally covers a few fill
        # pixels. Other parts contain callout connector strokes along the edge.
        passed=score>=(.95 if value==900 else .96)
        results.append({'part':name,'area_units':value,'rectangles_in_plane':rects,'actual_fill_iou':score,'passed':passed})
    return {'frame':frame,'side_lengths_units':[30,2],'pixel_lengths':[450,30],'exact_ratio':15,'parts':results,'area_sum':1024,'passed':all(r['passed'] for r in results)}


def native_indices(plan,events,states,cuts):
    indices={0,plan['duration_frames']-1}
    for event in events:
        for t in (event['start_s']-1/FPS,event['start_s'],(event['start_s']+event['end_s'])/2,event['end_s']-1/FPS,event['end_s'],event['end_s']+1/FPS):
            indices.add(frame_at(t))
        if event['id'].startswith('T'):
            for p in (0,.20,.30,.50,.60,.78,.90,1):indices.add(frame_at(event['start_s']+event['duration_s']*p))
    for state in states:
        # Every native frame of both moving copies and face generation.
        indices.update(range(frame_at(state['formula_start_s'])-1,frame_at(state.get('result_start_s',state['voice_start_s']-.12))+2))
    for cut in cuts:indices.update(range(cut-6,cut+7))
    indices.update(range(19));indices.update(range(plan['duration_frames']-31,plan['duration_frames']))
    return sorted(i for i in indices if 0<=i<plan['duration_frames'])


def negative_picture_controls(image,state,frame,truth,words):
    rows,reading=count_labels(state,truth,words);correct=inspect_compound(image,rows,frame)
    changed=[dict(r) for r in rows];changed[0]['text']=changed[0]['text'].rsplit(' = ',1)[0]+' = '+f'{truth[state["n"]]+1:,}'
    wrong=inspect_compound(image,changed,frame)
    shifted=dict(rows[0]);shifted['box']=tuple(v+(4 if i in (1,3) else 0) for i,v in enumerate(shifted['box']))
    off_axis=inspect_label(image,shifted,frame)
    wrong_grid=inspect_grid(image,state['n']+1,frame)
    side=next(r for r in rows if r['name']=='horizontal-side');side=dict(side);side['box']=tuple(v+(7 if i in (0,2) else 0) for i,v in enumerate(side['box']))
    wrong_side=inspect_label(image,side,frame)
    return {'frame':frame,'actual_correct_control_passed':correct['passed'],'wrong_square_answer_rejected':not wrong['passed'],'four_pixel_vertical_shift_rejected':not off_axis['passed'],'wrong_unit_array_quantity_rejected':not wrong_grid['passed'],'seven_pixel_axis_token_shift_rejected':not wrong_side['passed'],'passed':correct['passed'] and not any(r['passed'] for r in (wrong,off_axis,wrong_grid,wrong_side)),'scope':'Actual encoded n4 frame under correct and intentionally wrong expectations; source media is unchanged. Mathematical character identity, both axes and exact unit quantities must reject the negative alternatives.'}


def visual_checks(video,plan,states,segments,ffmpeg,directory,layout_spec=None):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    (directory/'native').mkdir();truth,rows,_=checked_design();words=[r['text'] for r in rows]
    events=plan.get('voice_events',plan['events']);scene=scene_contract(events,plan['duration_frames'])
    cuts=[s['start_frame'] for k,s in enumerate(scene) if k and scene[k-1]['mode']!=s['mode']]
    if layout_spec:
        spec=json.loads(Path(layout_spec).read_text());require(spec['scene_transitions']['cut_frames']==cuts,'Producer cut schedule differs from independently derived quiet-interval contract')
        require(spec['formula']['content_box']==[264,190,1656,292] and spec['diagram']['box']==list(GRID),'Layout differs from independently encoded acceptance fields')
    errors=[];error_count=0;counts=Counter();minimum={};progress_seen=set();terms_seen=set();fade_records=[];natives=[];maximum_dx=maximum_dy=0
    def record_error(frame,kind,detail):
        nonlocal error_count
        error_count+=1
        if len(errors)<160:errors.append({'frame':frame,'at_s':frame/FPS,'kind':kind,'detail':detail})
    def note_group(report):
        nonlocal maximum_dx,maximum_dy
        key=report.get('name',report.get('kind','diagram'));counts[key]+=1
        for axis in ('x','y'):
            delta=report.get('delta_'+axis+'_px')
            if delta is not None:
                if axis=='x':maximum_dx=max(maximum_dx,abs(delta))
                else:maximum_dy=max(maximum_dy,abs(delta))
        metric=report.get('independent_glyph_iou',report.get('independent_union_glyph_iou'))
        if metric is not None:minimum[key]=min(minimum.get(key,1),metric)
        if not report['passed']:record_error(report.get('frame',-1),key,report)
    # All output frames are decoded, not sampled by the producer frame plan.
    decoded=0
    for frame,image in decoded_frames(video,ffmpeg,directory/'all-frame-half-decode.log',2):
        decoded+=1;at=frame/FPS;state=independent_state(plan,events,states,at);fade=fade_level(frame,plan['duration_frames'],cuts)
        if fade:
            diff=ImageChops.difference(image,Image.new('RGB',image.size,'#fffaf0'))
            fade_records.append({'frame':frame,'planned_alpha':fade,'distance_mean':sum(ImageStat.Stat(diff).mean),'maximum_rgb_error':max(max(c.getextrema()) for c in diff.split())})
            if fade==255 and fade_records[-1]['maximum_rgb_error']>5:record_error(frame,'opaque-cream-cut',fade_records[-1])
            continue
        progress_seen.add(state['completed']);note_group(inspect_label(image,shared_labels(state)[-1],frame,2,False))
        if state['mode']=='count':
            terms_seen.add(state['n']);labels,reading=count_labels(state,truth,words)
            note_group(inspect_compound(image,labels,frame,2));note_group(inspect_label(image,reading,frame,2,False))
        if frame%3000==0:print(json.dumps({'qa_half_decoded_frame':frame,'duration_frames':plan['duration_frames']}),flush=True)
    require(decoded==plan['duration_frames'],'Actual full decode frame count differs')
    require(terms_seen==set(range(101)),'All-frame decode did not observe all101 generated terms')
    require(progress_seen==set(range(102)),'Actual progress display does not cover all0..101 states')
    selected=native_indices(plan,events,states,cuts);by_id={e['id']:e for e in events}
    result_mid={frame_at((by_id[f'N{n:03}']['start_s']+by_id[f'N{n:03}']['end_s'])/2):n for n in range(101)}
    lesson_mid={frame_at((e['start_s']+e['end_s'])/2):e['id'] for e in events if e['id'].startswith(('I','T','O'))}
    contact=[];native_components=0;digits=0;negative=None
    with gzip.open(directory/'native-records.jsonl.gz','wt',encoding='utf-8') as details:
        for frame,image in decoded_frames(video,ffmpeg,directory/'native-decode.log',1,selected):
            state=independent_state(plan,events,states,frame/FPS);fade=fade_level(frame,plan['duration_frames'],cuts)
            row={'frame':frame,'at_s':frame/FPS,'state':state,'components':[],'diagrams':[],'whole_frame_fade':fade}
            if not fade:
                standard=shared_labels(state)
                if state['mode']=='count':compound,reading=count_labels(state,truth,words);standard.append(reading)
                else:compound,additional=lesson_labels(state,truth,words);standard.extend(additional)
                c=inspect_compound(image,compound,frame);row['components'].append(c);note_group(c);digits+=len(c['character_checks'])
                # Once a copy clears the source, measure its own two-axis ink
                # too. At source contact, the union above preserves all pixels.
                geometries=[label_geometry(r) for r in compound]
                for k,label in enumerate(compound):
                    bounds=geometries[k][2]
                    touching=any(k!=j and max(bounds[0]-12,g[2][0])<min(bounds[2]+12,g[2][2]) and max(bounds[1]-12,g[2][1])<min(bounds[3]+12,g[2][3]) for j,g in enumerate(geometries))
                    if not touching:standard.append(label)
                    else:row.setdefault('compound_contact_measurements',[]).append(label['name'])
                for label in standard:
                    r=inspect_label(image,label,frame);row['components'].append(r);note_group(r)
                n=state['n'];diagram=None
                if state['mode']=='count':
                    progress=state['fill_tick']/30
                    diagram=inspect_grid(image,n,frame,progress) if n<=10 else inspect_schematic(image,n,frame,progress)
                    if n==0:standard_zero=label_record('zero-empty-label','NO UNIT TILES',40,(730,600,1190,664),('#6b8190',),fill='#f1fbfb');zr=inspect_label(image,standard_zero,frame);row['components'].append(zr);note_group(zr)
                    if n>10:
                        for label in [label_record('schematic-mark','SCHEMATIC',35,(740,558,1180,608),(TEAL,),fill='#f1fbfb'),label_record('schematic-explanation','dimensions in units',28,(738,627,1182,674),(INK,),fill='#f1fbfb')]:
                            r=inspect_label(image,label,frame);row['components'].append(r);note_group(r)
                elif state['mode']=='teaching':
                    if n==4:diagram=inspect_grid(image,5,frame,state['lesson_tick']/30,lshape=True)
                    elif n==32:diagram=inspect_area(image,frame)
                    else:diagram=inspect_grid(image,n,frame,block=n==100)
                    if n==100:
                        key=inspect_block_key(image,frame);row['diagrams'].append(key)
                        if not key['passed']:record_error(frame,'block-key',key)
                if diagram:
                    row['diagrams'].append(diagram)
                    if not diagram['passed']:record_error(frame,'diagram',diagram)
                native_components+=len(row['components'])
            row['passed']=all(r['passed'] for r in row['components']+row['diagrams'])
            if result_mid.get(frame)==4:
                negative=negative_picture_controls(image,state,frame,truth,words)
            if frame in result_mid or frame in lesson_mid or (not row['passed'] and len(natives)<20):
                path=directory/'native'/f'frame-{frame:06}.png';image.save(path);natives.append(str(path))
                if frame in lesson_mid or result_mid.get(frame) in (0,1,4,10,11,31,32,61,94,99,100):contact.append((frame,state,image.resize((480,270),Image.Resampling.LANCZOS)))
            details.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
    contact_im=Image.new('RGB',(1440,math.ceil(len(contact)/3)*300),'#fffaf0');d=ImageDraw.Draw(contact_im)
    for k,(frame,state,im) in enumerate(contact):
        x,y=k%3*480,k//3*300;contact_im.paste(im,(x,y));d.text((x+6,y+276),f'{frame/30:.3f}s {state["mode"]} n{state["n"]}',fill=INK)
    contact_im.save(directory/'actual-film-contact.jpg',quality=94)
    # All dips must occur outside formula/result speech and hit full opacity;
    # E/N visibility is checked independently at every boundary above.
    overlapping=[r for r in fade_records if any(e['id'].startswith(('E','N')) and e['start_s']<=r['frame']/FPS<e['end_s'] for e in events)]
    require(not overlapping,'Whole-frame fade intersects formula/result speech')
    for cut in [0,*cuts,plan['duration_frames']-1]:
        opaque=next((r for r in fade_records if r['frame']==cut),None)
        require(opaque and opaque['planned_alpha']==255 and opaque['maximum_rgb_error']<=5,f'Fade endpoint not clean cream frame{cut}')
    fade_report={'passed':not overlapping,'whole_frame_fade_observations':fade_records,'cut_frames':cuts,'speech_fade_overlap_count':len(overlapping),'minimum_or_maximum_tolerance_rgb':5}
    write_json(directory/'fade-verification.json',fade_report)
    require(negative and negative['passed'],'Picture QA did not reject negative controls');write_json(directory/'negative-controls.json',negative)
    report={'passed':error_count==0,'video_sha256':sha(video),'verifier_sha256':sha(Path(__file__)),'all_decoded_frames':decoded,'all_frame_analysis_resolution':[960,540],'all101_terms_observed':sorted(terms_seen),'all102_progress_states_observed':sorted(progress_seen),'component_observations':dict(counts),'minimum_glyph_iou':minimum,'native_frames':len(selected),'native_component_observations':native_components,'native_mathematical_characters':digits,'max_abs_dx_px':maximum_dx,'max_abs_dy_px':maximum_dy,'native_tolerance_px':1,'native_record_path':str(directory/'native-records.jsonl.gz'),'native_images':natives,'negative_controls':negative,'scene_transitions':fade_report,'error_count':error_count,'errors':errors,'scope':'Every decoded frame math/reading/progress at half resolution; all E generation frames and all215 cue boundaries plus101 results and teaching/intro/outro representatives at native resolution. Independent source-contact union, individual settled/copy two-axis ink, diagrams and numeric characters. Human continuous watching/listening is not claimed.'}
    write_json(directory/'verification.json',report)
    return report


def decoded_frames(video,ffmpeg,log,divisor=2,indices=None):
    w,h=SIZE[0]//divisor,SIZE[1]//divisor;filters=[]
    if indices is not None:
        # Compact inclusive runs keep the filter parser shallow for native transitions.
        runs=[]
        for n in indices:
            if runs and runs[-1][1]+1==n:runs[-1][1]=n
            else:runs.append([n,n])
        def combine(terms):
            if len(terms)==1:return terms[0]
            k=len(terms)//2;return '('+combine(terms[:k])+'+'+combine(terms[k:])+')'
        filters.append('select='+combine([f'between(n\\,{a}\\,{b})' for a,b in runs]))
    if divisor!=1:filters.append(f'scale={w}:{h}:flags=area:in_color_matrix=bt709')
    filters.append('format=rgb24')
    cmd=[str(ffmpeg),'-nostdin','-v','error','-xerror','-i',str(video),'-an','-vf',','.join(filters),'-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24','pipe:1']
    with Path(log).open('xb') as errors,subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=errors) as proc:
        for index in indices if indices is not None else range(10000000):
            raw=proc.stdout.read(w*h*3)
            if not raw and indices is None:break
            require(len(raw)==w*h*3,f'Unexpected decoded EOF frame{index}')
            yield index,Image.frombytes('RGB',(w,h),raw)
        require(not proc.stdout.read(1),'Unexpected extra selected frames')
        require(proc.wait()==0,'Actual MP4 frame decode failed')


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('video','timeline','master','out-dir'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--delivery-dir',type=Path)
    p.add_argument('--layout-spec',type=Path)
    p.add_argument('--ffmpeg',default=str(ROOT/'.venv/bin/ffmpeg') if (ROOT/'.venv/bin/ffmpeg').exists() else shutil.which('ffmpeg'))
    p.add_argument('--ffprobe',default=str(ROOT/'.venv/bin/ffprobe') if (ROOT/'.venv/bin/ffprobe').exists() else shutil.which('ffprobe'))
    p.add_argument('--skip-technical',action='store_true')
    return p


def main(argv=None):
    args=parser().parse_args(argv);require(args.ffmpeg and args.ffprobe,'FFmpeg/ffprobe required')
    args.out_dir.mkdir(parents=True,exist_ok=False);plan=json.loads(args.timeline.read_text())
    report={'schema_version':1,'kind':'independent-square-finished-video-QA','checked_at_utc':datetime.now(timezone.utc).isoformat(),'video':str(args.video.resolve()),'video_sha256':sha(args.video),'timeline_sha256':sha(args.timeline),'verifier_sha256':sha(Path(__file__)),'passed':False}
    try:
        events,states,segments,report['schedule']=validate_schedule(plan)
        if not args.skip_technical:
            report['technical']=technical.verify_video(args.video,args.out_dir/'technical',args.timeline,args.ffmpeg,args.ffprobe,duration_bounds=(480,1800))
            require(report['technical']['status']=='pass','Finished media technical checks failed')
            require(report['technical']['measurements']['true_peak_dbtp']<=-1.45,'Encoded final AAC true peak above accepted ceiling')
        report['captions']=captions_and_metadata(plan,events,args.delivery_dir or args.video.parent)
        report['audio']=audio_checks(plan,events,args.video,args.master,args.ffmpeg,args.out_dir/'audio')
        report['visual']=visual_checks(args.video,plan,states,segments,args.ffmpeg,args.out_dir/'visual',args.layout_spec)
        require(report['visual']['passed'],'Independent actual-picture verification failed')
        require(sha(args.video)==report['video_sha256'],'Media changed during final QA')
        report['passed']=True
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        report['scope']='Fresh source/hash/schedule/math/caption checks and actual encoded-media analysis. Human full-film watching/listening is not claimed. Static-mock QA and old accepted film records are unchanged.'
        write_json(args.out_dir/'verification.json',report)
    print(json.dumps({'passed':report['passed'],'report':str(args.out_dir/'verification.json')}))


if __name__=='__main__':
    main()
