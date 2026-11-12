"""Independent arithmetic-sequence delivery QA.

Truth comes from a fresh integer recurrence, closed form and inverse cardinal
parser. Pixel observations come from decoded MP4, never a renderer import.
The final report distinguishes mathematical, technical, pixel and artistic QA.
"""
from __future__ import annotations

import argparse
from array import array
from bisect import bisect_right
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import gzip
import json
import math
from pathlib import Path
import re
import subprocess
import wave

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps, ImageStat

if __package__:
    from .component_alignment import raster_centering_report
    from . import verify_video as technical
else:
    from component_alignment import raster_centering_report
    import verify_video as technical

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/arithmetic-sequence-counting-v1'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
BACKGROUND = DESIGN / 'generation-batches/wind-organ-hall-20261112-01a1cdca/source/wind-organ-hall.png'
SIZE, FPS, RATE = (1920, 1080), 30, 24000
INK, TEAL, GOLD, PALE, MUTED = '#364c4a', '#357e7b', '#c9823e', '#fffaf0', '#73877c'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def path_of(value):
    value = Path(value)
    return value if value.is_absolute() else ROOT / value


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def frame_at(at):
    return math.ceil(at * FPS - 1e-7)


def sample(at):
    return round(at * RATE)


def truth_values():
    recurrence = [2]
    for _ in range(100):
        recurrence.append(recurrence[-1] + 3)
    closed = [2 + 3 * (n - 1) for n in range(1, 102)]
    require(recurrence == closed, 'Recurrence and closed form disagree')
    require((closed[0], closed[33], closed[66], closed[100]) == (2, 101, 200, 302), 'Milestone truth differs')
    require(len(set(closed)) == 101 and sum(closed) == 15352, 'Count uniqueness/sum differs')
    return tuple(closed)


def cardinal(value):
    small = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
    tens = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']
    if value < 20:
        return small[value]
    if value < 100:
        return tens[value // 10] + ('-' + small[value % 10] if value % 10 else '')
    require(value < 1000, 'Unsupported number')
    return small[value // 100] + ' hundred' + (' ' + cardinal(value % 100) if value % 100 else '')


def parse_cardinal(text):
    """Strict inverse grammar; expected cardinal strings are not the parser."""
    low = dict(zip('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split(), range(20)))
    tens = dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(), range(20, 100, 10)))
    require(isinstance(text, str) and re.fullmatch(r'[a-z]+(?:[ -][a-z]+)*', text), f'Invalid cardinal {text!r}')
    words = text.replace('-', ' ').split()
    hundreds = 0
    if 'hundred' in words:
        require(words.count('hundred') == 1 and words.index('hundred') == 1 and 1 <= low.get(words[0], -1) <= 9, f'Bad hundreds {text}')
        hundreds = low[words[0]] * 100
        words = words[2:]
        if not words:
            return hundreds
    if len(words) == 1 and words[0] in low:
        require(not hundreds or low[words[0]] > 0, f'Redundant zero {text}')
        return hundreds + low[words[0]]
    require(len(words) in (1, 2) and words[0] in tens, f'Bad tens {text}')
    tail = 0
    if len(words) == 2:
        require(1 <= low.get(words[1], -1) <= 9, f'Bad units {text}')
        tail = low[words[1]]
    return hundreds + tens[words[0]] + tail


def validate_schedule(plan):
    values = truth_values()
    events = plan.get('voice_events', plan.get('events', []))
    require(len(events) == 215, 'Expected exactly215voice cues')
    require(len({e['id'] for e in events}) == len(events), 'Duplicate cue ID')
    require(events == sorted(events, key=lambda e: e['start_s']), 'Voice events not chronological')
    for i, event in enumerate(events):
        require(0 <= event['start_s'] < event['end_s'] <= plan['duration_s'], f'Invalid cue bounds {event["id"]}')
        if i:
            require(event['start_s'] >= events[i-1]['end_s'], f'Overlapping voice cues {event["id"]}')
        require(abs(event['end_s'] - event['start_s'] - event['duration_s']) <= 1/RATE, f'Cue duration differs {event["id"]}')
    counts = [e for e in events if e['kind'] == 'count']
    prefixes = [e for e in events if e['kind'] == 'formula_prefix']
    require(len(counts) == 101 and len(prefixes) == 100, 'Wrong count/expression cue totals')
    states = plan['counted_states']
    require(len(states) == 101, 'Wrong counted state total')
    by_id = {e['id']: e for e in events}
    ordinary, extended = [], []
    for n, (count, state, value) in enumerate(zip(counts, states, values), 1):
        require(count['id'] == f'N{n:03}' and count['n'] == n and count['value'] == value, f'Wrong count identity n{n}')
        require(parse_cardinal(count['text'].rstrip('.').lower()) == value, f'Count text differs n{n}')
        require(state['n'] == n and state['value'] == value, f'Wrong state identity n{n}')
        require(abs(state['voice_start_s'] - count['start_s']) <= 1/RATE and abs(state['voice_end_s'] - count['end_s']) <= 1/RATE, f'State/voice timing differs n{n}')
        require(abs(state['progress_commit_s'] - count['end_s']) <= 1/RATE, f'Progress must follow completed speech n{n}')
        display = state.get('result_start_s', state.get('display_start_s'))
        require(display is not None and abs(count['start_s'] - display - .12) <= 1/RATE, f'Result display lead differs n{n}')
        if n > 1:
            expression = by_id[f'E{n:03}']
            require(expression['text'].rstrip('.').lower() == f'{cardinal(value-3)} plus three is', f'Expression words differ n{n}')
            require(abs(count['start_s'] - expression['end_s'] - .16) <= 1/RATE, f'Expression/result gap differs n{n}')
            require(state['previous_value'] == value - 3, f'Expression previous value differs n{n}')
            require(abs(state['formula_start_s'] - expression['start_s']) <= 1/RATE and abs(state['formula_end_s'] - expression['end_s']) <= 1/RATE, f'Formula state timing differs n{n}')
        if n < 101:
            following = by_id[f'E{n+1:03}']
            lessons = [e for e in events if count['end_s'] <= e['start_s'] < following['start_s'] and e['kind'] == 'explanation']
            if lessons:
                require(all(e['end_s'] <= following['start_s'] for e in lessons), f'Lesson overlaps next count n{n}')
                extended.append({'after_n': n, 'gap_s': following['start_s'] - count['end_s'], 'cues': [e['id'] for e in lessons]})
            else:
                require(abs(following['start_s'] - count['end_s'] - 2) <= 1/RATE, f'Ordinary gap is not2s n{n}')
                ordinary.append(n)
    require(len(ordinary) + len(extended) == 100, 'Missing count boundary')
    require(plan['duration_s'] >= 480, 'Episode is shorter than8minutes')
    return events, states, {'passed': True, 'independence': 'new integer recurrence, closed form, sum/uniqueness and strict inverse English grammar; no builder or renderer imported', 'counted_terms': 101, 'addition_expressions': 100, 'first_value': 2, 'last_value': 302, 'milestones': {'n34': 101, 'n67': 200}, 'sum': sum(values), 'voice_events': len(events), 'ordinary_two_second_boundaries': ordinary, 'extended_boundaries': extended, 'digit_boundaries': [n for n in range(2,102) if len(str(values[n-1])) > len(str(values[n-2]))]}


def schedule_controls(plan):
    mutations = [('wrong_last_value', lambda p: p['counted_states'][-1].update(value=305)), ('early_progress', lambda p: p['counted_states'][33].update(progress_commit_s=p['counted_states'][33]['voice_start_s'])), ('wrong_formula', lambda p: next(e for e in p['voice_events'] if e['id']=='E034').update(text='ninety-eight plus two equals'))]
    rows=[]
    for name, mutate in mutations:
        copy=deepcopy(plan);mutate(copy)
        try:
            validate_schedule(copy)
        except (ValueError, KeyError) as exc:
            rows.append({'name':name,'detected':True,'reason':str(exc)})
        else:
            rows.append({'name':name,'detected':False})
    return {'passed':all(r['detected'] for r in rows),'controls':rows}


def source_gate_checks(plan,events):
    require(plan.get('speech_adopted') is True,'Timeline speech is not adopted')
    dependency=plan.get('speech_gate') or plan.get('speech_acceptance')
    require(dependency and dependency.get('path') and dependency.get('sha256'),'No exact source acceptance dependency')
    gate_path=path_of(dependency['path']);require(sha(gate_path)==dependency['sha256'],'Source gate bytes changed')
    gate=json.loads(gate_path.read_text());require(gate.get('accepted') is True and not gate.get('unresolved'),'Unresolved source acceptance gate')
    rows={r['id']:r for r in gate.get('results',[])}
    require(set(rows)=={e['id'] for e in events},'Gate does not cover every exact cue')
    observations=[]
    for event in events:
        row=rows[event['id']];source=path_of(event['source_path'])
        require(row.get('accepted') is True and row.get('source_sha256')==event['source_sha256'] and not row.get('failures'),'Unaccepted source '+event['id'])
        require(sha(source)==event['source_sha256'],'Source bytes changed '+event['id'])
        with wave.open(str(source)) as stream:
            frames,rate,channels=stream.getnframes(),stream.getframerate(),stream.getnchannels()
        require(rate==RATE and channels==1 and frames==sample(event['duration_s']),'Cue source shape/duration differs '+event['id'])
        observations.append({'id':event['id'],'source_sha256':sha(source),'frames_24k':frames,'accepted':True})
    return {'passed':True,'gate':str(gate_path),'gate_sha256':sha(gate_path),'cues':observations,'scope':'Current hash-bound source decisions, source WAV shape and samples. Final AAC recognition is a new separate gate.'}


def split_integrity_checks(events,manifest_path):
    manifest=json.loads(Path(manifest_path).read_text());rows=manifest['numbers']+manifest['dialogue'];by_id={r['id']:r for r in rows};observations=[];quiet=[]
    def contents(path):
        with wave.open(str(path)) as stream:
            require(stream.getframerate()==RATE and stream.getnchannels()==1 and stream.getsampwidth()==2,'Unexpected source WAV shape')
            return stream.readframes(stream.getnframes())
    for row in rows:
        raw_path=path_of(row['raw_source']['path']);require(sha(raw_path)==row['raw_source']['sha256'],'Raw source changed '+row['id'])
        raw=contents(raw_path);selected=contents(path_of(row['path']));interval=row.get('raw_sample_range_24k')
        if interval:
            expected=raw[interval[0]*2:interval[1]*2]
            require(selected==expected,'Selected source is not the stated exact PCM slice '+row['id'])
            kind='byte-exact raw sample interval'
        else:
            require(selected==raw,'Whole source copy differs '+row['id']);kind='byte-identical whole source'
        if row.get('prior_gate'):
            dependency=row['prior_gate'];gate_path=path_of(dependency['path']);require(sha(gate_path)==dependency['sha256'],'Prior library gate changed')
            gate=json.loads(gate_path.read_text());require(gate.get('accepted') and not gate.get('unresolved'),'Library gate unresolved')
            require(any(r.get('accepted') and (r.get('sha256') or r.get('source_sha256'))==row['raw_source']['sha256'] for r in gate['results']),'Reused source absent from accepted prior gate')
            kind+='; hash-bound accepted series-number reuse'
        observations.append({'id':row['id'],'origin':row['origin'],'raw_source_sha256':sha(raw_path),'selected_source_sha256':sha(path_of(row['path'])),'raw_sample_range_24k':interval,'policy':kind,'passed':True})
    for n in range(2,102):
        prefix,result=by_id[f'E{n:03}'],by_id[f'N{n:03}']
        if not result.get('raw_sample_range_24k') or prefix['raw_source']!=result['raw_source']:
            continue
        a,b=prefix['raw_sample_range_24k'][1],result['raw_sample_range_24k'][0]
        require(a<=b,'Prefix/result intervals overlap')
        gap=pcm16(contents(path_of(prefix['raw_source']['path']))[a*2:b*2])
        rms=math.sqrt(sum(v*v for v in gap)/len(gap)) if gap else 0;peak=max(map(abs,gap)) if gap else 0
        require(rms<=20 and peak<=96,'Removed interior gap contains nonquiet samples n'+str(n))
        quiet.append({'n':n,'removed_gap_frames_24k':len(gap),'rms_pcm16':rms,'peak_pcm16':peak,'passed':True})
    return {'passed':True,'manifest_sha256':sha(manifest_path),'selected_cues':len(observations),'source_observations':observations,'interior_quiet_gap_observations':quiet,'scope':'Every actual selected source compared byte-for-byte with its stated raw PCM interval or accepted library original; removed intra-sentence intervals independently measured as quiet. CTC/lexical articulation is a separate gate.'}


@lru_cache(maxsize=96)
def font(size):
    return ImageFont.truetype(str(FONT),size)


@lru_cache(maxsize=2048)
def glyph_alpha(text,size):
    if '\n' in text:
        parts=[glyph_alpha(line,size) for line in text.split('\n')]
        bounds=[p.point(lambda v:255 if v>=128 else 0).getbbox() for p in parts]
        width=max(b[2]-b[0] for b in bounds);height=sum(b[3]-b[1] for b in bounds)+15*(len(parts)-1)
        layer=Image.new('L',(width+80,height+80));y=40
        for p,b in zip(parts,bounds):
            layer.paste(p.crop(b),(40+round((width-(b[2]-b[0]))/2),y));y+=b[3]-b[1]+15
        return layer
    face=font(size);b=face.getbbox(text)
    layer=Image.new('L',(b[2]-b[0]+80,b[3]-b[1]+80))
    ImageDraw.Draw(layer).text((40-b[0],40-b[1]),text,font=face,fill=255)
    return layer


def rgb(value):
    return tuple(bytes.fromhex(value.lstrip('#'))) if isinstance(value,str) else tuple(value)


def iou(a,b):
    union=ImageChops.lighter(a,b).histogram()[255]
    return ImageChops.darker(a,b).histogram()[255]/union if union else 0.


@lru_cache(maxsize=4)
def background(divisor=1):
    im=ImageOps.fit(Image.open(BACKGROUND).convert('RGB'),SIZE,Image.Resampling.LANCZOS)
    return im if divisor==1 else im.resize((SIZE[0]//divisor,SIZE[1]//divisor),Image.Resampling.BOX)


def observed_ink(image,area,color,fill=None,divisor=1,chromatic=False):
    """Extract glyph cores by contrast against a clean plate, without a glyph mask."""
    area=tuple(v//divisor for v in area);crop=image.crop(area).convert('RGB')
    base=Image.new('RGB',crop.size,fill) if fill else background(divisor).crop(area)
    weights=(.2126,.7152,.0722,0)
    measured=crop.convert('L',weights);ground=base.convert('L',weights)
    level=round(sum(a*b for a,b in zip(rgb(color),weights)))
    # An encoded half-coverage sample is rounded to an integer luma. Retain
    # the upper midpoint on a dark-on-light edge, rather than flooring it and
    # rejecting a genuine alpha128 pixel by one quantization level.
    midpoint=ground.point(lambda x:(x+level+1)//2)
    if ImageStat.Stat(ground).mean[0]>=level:
        mask=ImageChops.subtract(measured,midpoint).point(lambda x:255 if x==0 else 0)
    else:
        mask=ImageChops.subtract(midpoint,measured).point(lambda x:255 if x==0 else 0)
    changed=ImageChops.difference(crop,base)
    difference=ImageChops.lighter(ImageChops.lighter(changed.getchannel(0),changed.getchannel(1)),changed.getchannel(2)).point(lambda x:255 if x>=24 else 0)
    if not chromatic:return ImageChops.darker(mask,difference)
    # Distinguish teal, gold and neutral ink by their chromatic direction.
    # This is color-only extraction; no expected glyph stencil is applied.
    red,green,blue=crop.split();target=rgb(color)
    if target[1]-target[0]>40:
        chroma=ImageChops.subtract(green,red).point(lambda v:255 if v>=32 else 0)
    elif target[0]-target[1]>40:
        chroma=ImageChops.subtract(red,green).point(lambda v:255 if v>=30 else 0)
    else:
        teal=ImageChops.subtract(green,red).point(lambda v:0 if v>=35 else 255)
        gold=ImageChops.subtract(red,green).point(lambda v:0 if v>=30 else 255)
        chroma=ImageChops.darker(teal,gold)
    return ImageChops.darker(ImageChops.darker(mask,difference),chroma)


@lru_cache(maxsize=4096)
def label_geometry(text,size,box,source_size=0,raster_scale=1,indexed=None,masked=None):
    layer=glyph_alpha(text,size)
    if source_size:
        face=font(source_size);b=face.getbbox(text)
        layer=Image.new('L',(b[2]-b[0]+60,b[3]-b[1]+60))
        ImageDraw.Draw(layer).text((30-b[0],30-b[1]),text,font=face,fill=255)
        layer=layer.resize((max(1,round(layer.width*raster_scale)),max(1,round(layer.height*raster_scale))),Image.Resampling.LANCZOS)
    if indexed is not None:
        # The licensed font has no n-subscript; independently typeset the
        # specified a +52%-size subscript + expression with physical ink boxes.
        parts=[glyph_alpha('a',size),glyph_alpha(str(indexed),round(size*.52)),glyph_alpha(text,size)]
        bounds=[x.point(lambda v:255 if v>=128 else 0).getbbox() for x in parts]
        widths=[b[2]-b[0] for b in bounds]
        height=max(bounds[0][3]-bounds[0][1]+20,bounds[2][3]-bounds[2][1])
        layer=Image.new('L',(sum(widths)+88,height+70))
        for part,b,xy in zip(parts,bounds,[(25,25),(25+widths[0],25+round(size*.55)),(42+widths[0]+widths[1],25)]):
            layer.paste(part.crop(b),xy)
        if masked is not None:
            face=font(size);full=face.getbbox(text);token=Image.new('L',parts[2].size)
            ImageDraw.Draw(token).text((40-full[0]+face.getlength(' = 2 + ('),40-full[1]),masked,font=face,fill=255)
            remove=Image.new('L',layer.size)
            remove.paste(token,(42+widths[0]+widths[1]-bounds[2][0],25-bounds[2][1]))
            layer=ImageChops.subtract(layer,remove)
    b=layer.point(lambda x:255 if x>=128 else 0).getbbox()
    xy=(round((box[0]+box[2]-b[0]-b[2])/2),round((box[1]+box[3]-b[1]-b[3])/2))
    return layer,xy,(b[0]+xy[0],b[1]+xy[1],b[2]+xy[0],b[3]+xy[1])


@lru_cache(maxsize=8192)
def expected_label_mask(text,size,box,area,divisor=1,shift=(0,0),source_size=0,raster_scale=1,indexed=None,masked=None):
    layer,xy,_=label_geometry(text,size,box,source_size,raster_scale,indexed,masked)
    out=Image.new('L',(area[2]-area[0],area[3]-area[1]))
    out.paste(layer,(xy[0]-area[0]+shift[0],xy[1]-area[1]+shift[1]))
    if divisor!=1:
        out=out.resize((out.width//divisor,out.height//divisor),Image.Resampling.BOX)
    return out.point(lambda x:255 if x>=128 else 0)


_TEMPLATE_SHIFTS={}


def inspect_label(image,row,frame,divisor=1,alignment=True,digits=False):
    """Independent font shape/position against actual encoded foreground."""
    text,size,box=row['text'],row['size'],tuple(row['box'])
    extra=(row.get('source_size',0),row.get('raster_scale',1),row.get('indexed'),row.get('masked'))
    layer,xy,bounds=label_geometry(text,size,box,*extra)
    margin=12
    area=(max(0,(bounds[0]-margin)//divisor*divisor),max(0,(bounds[1]-margin)//divisor*divisor),min(SIZE[0],math.ceil((bounds[2]+margin)/divisor)*divisor),min(SIZE[1],math.ceil((bounds[3]+margin)/divisor)*divisor))
    actual=Image.new('L',((area[2]-area[0])//divisor,(area[3]-area[1])//divisor))
    for color in row.get('colors',(row.get('color',INK),)):
        actual=ImageChops.lighter(actual,observed_ink(image,area,color,row.get('fill'),divisor))
    key=(text,size,box,area,divisor,extra)
    if key not in _TEMPLATE_SHIFTS:
        score,dx,dy=max((iou(actual,expected_label_mask(text,size,box,area,divisor,(dx,dy),*extra)),dx,dy) for dx in (-1,0,1) for dy in (-1,0,1))
        _TEMPLATE_SHIFTS[key]=(dx,dy)
    dx,dy=_TEMPLATE_SHIFTS[key];score=iou(actual,expected_label_mask(text,size,box,area,divisor,(dx,dy),*extra))
    minimum=.91 if divisor==1 else .79
    result={'frame':frame,'component_id':row['name'],'text':text,'font_size_px':size,'content_box':list(box),'observation_box':list(area),'resolution_divisor':divisor,'glyph_iou':score,'minimum_glyph_iou':minimum,'template_shift_native_px':[dx,dy],'passed':actual.getbbox() is not None and score>=minimum}
    if alignment and divisor==1:
        try:
            measured=raster_centering_report(actual,box,origin_xy=area[:2],name=f'{frame}/{row["name"]}',tolerance_px=1)
            result['alignment']=measured;result['passed'] &= measured['passed']
        except ValueError as exc:
            result['alignment']={'passed':False,'error':str(exc)};result['passed']=False
    if digits and divisor==1 and not extra[0] and extra[2] is None and '\n' not in text:
        face=font(size);whole=face.getbbox(text);digit_rows=[]
        origin=(xy[0]+40-whole[0]+dx,xy[1]+40-whole[1]+dy)
        for index,char in enumerate(text):
            if char not in '0123456789':
                continue
            advance=face.getlength(text[:index]);b=face.getbbox(char)
            absolute=(math.floor(origin[0]+advance+b[0]-3),math.floor(origin[1]+b[1]-3),math.ceil(origin[0]+advance+b[2]+3),math.ceil(origin[1]+b[3]+3))
            local=(absolute[0]-area[0],absolute[1]-area[1],absolute[2]-area[0],absolute[3]-area[1]);observed=actual.crop(local)
            scores=[]
            for alternative in '0123456789':
                alternate_text=text[:index]+alternative+text[index+1:]
                candidate=expected_label_mask(alternate_text,size,box,area,1,(dx,dy),*extra).crop(local)
                scores.append((iou(observed,candidate),alternative))
            scores.sort(reverse=True);winner=scores[0]
            digit_rows.append({'position':index,'expected':char,'observed':winner[1],'iou':winner[0],'alternative_margin':winner[0]-scores[1][0],'passed':winner[1]==char and winner[0]>=.83})
        result['digits']=digit_rows;result['passed'] &= all(x['passed'] for x in digit_rows)
    return result


def pixel_negative_controls(directory):
    directory.mkdir(parents=True,exist_ok=True)
    row={'name':'independent-control-value','text':'302','size':180,'box':(740,363,1360,592),'color':GOLD,'fill':PALE}
    tests=[]
    for name,text,dx,dy,expected in [('correct','302',0,0,True),('wrong-last-digit','305',0,0,False),('wrong-hundreds','202',0,0,False),('x-offset','302',4,0,False),('y-offset','302',0,4,False),('empty','',0,0,False)]:
        image=Image.new('RGB',SIZE,PALE)
        if text:
            layer,xy,_=label_geometry(text,row['size'],tuple(row['box']));colored=Image.new('RGBA',layer.size,GOLD);colored.putalpha(layer);image.paste(colored,(xy[0]+dx,xy[1]+dy),colored)
        measured=inspect_label(image,row,0,digits=True)
        require(measured['passed']==expected,f'Pixel negative control misclassified {name}')
        tests.append({'name':name,'expected_pass':expected,'correctly_classified':measured['passed']==expected,'measurement':measured})
    report={'passed':all(r['correctly_classified'] for r in tests),'controls':tests};write_json(directory/'pixel-negative-controls.json',report);return report


def connected_components(mask):
    """Independent8-connected run labelling of actual pixel masks."""
    mask=mask.convert('L');width,height=mask.size;data=mask.tobytes();parents=[];runs_all=[];previous=[]
    def find(index):
        while parents[index]!=index:
            parents[index]=parents[parents[index]];index=parents[index]
        return index
    for y in range(height):
        row=data[y*width:(y+1)*width];runs=[];x=0
        while x<width:
            if not row[x]:x+=1;continue
            left=x
            while x<width and row[x]:x+=1
            right=x;index=len(parents);parents.append(index);runs_all.append((left,right,y))
            for a,b,j in previous:
                if b<left:continue
                if a>right:break
                one,two=find(index),find(j)
                if one!=two:parents[two]=one
            runs.append((left,right,index))
        previous=runs
    groups={}
    for i,(left,right,y) in enumerate(runs_all):
        key=find(i);length=right-left
        if key not in groups:groups[key]=[0,0.,0.,left,y,right,y+1]
        r=groups[key];r[0]+=length;r[1]+=(left+right-1)*length/2;r[2]+=y*length;r[3]=min(r[3],left);r[4]=min(r[4],y);r[5]=max(r[5],right);r[6]=max(r[6],y+1)
    return [{'pixels':r[0],'centroid':[r[1]/r[0],r[2]/r[0]],'bbox':r[3:]} for r in groups.values()]


def decoded_frames(video,ffmpeg,log,divisor=2,indices=None):
    arguments=[str(ffmpeg),'-hide_banner','-v','error','-nostdin','-i',str(video),'-an']
    if indices is not None:
        selected=sorted(set(indices))
        def balanced(parts):
            if len(parts)==1:return parts[0]
            middle=len(parts)//2;return '('+balanced(parts[:middle])+'+'+balanced(parts[middle:])+')'
        expression=balanced([f'eq(n\\,{k})' for k in selected])
        arguments+=['-vf',f'select={expression},scale={SIZE[0]//divisor}:{SIZE[1]//divisor}:flags=area','-fps_mode','passthrough']
    else:
        selected=None;arguments+=['-vf',f'scale={SIZE[0]//divisor}:{SIZE[1]//divisor}:flags=area']
    arguments+=['-f','rawvideo','-pix_fmt','rgb24','pipe:1']
    Path(log).parent.mkdir(parents=True,exist_ok=True)
    with Path(log).open('wb') as errors:
        process=subprocess.Popen(arguments,stdout=subprocess.PIPE,stderr=errors)
        size=(SIZE[0]//divisor,SIZE[1]//divisor);length=size[0]*size[1]*3;ordinal=0
        try:
            while True:
                raw=process.stdout.read(length)
                if not raw:break
                require(len(raw)==length,'Truncated raw decoded frame')
                require(selected is None or ordinal<len(selected),'Unexpected selected frame')
                frame=ordinal if selected is None else selected[ordinal]
                yield frame,Image.frombytes('RGB',size,raw)
                ordinal+=1
            require(process.wait()==0,'FFmpeg decode failed; inspect '+str(log))
            if selected is not None:require(ordinal==len(selected),'Missing selected decoded frames')
        finally:
            if process.poll() is None:process.kill();process.wait()


def native_sample_indices(plan,events,states):
    maximum=plan['duration_frames']-1;indices={0,maximum}
    def add_time(time):
        frame=frame_at(time)
        indices.update(k for k in (frame-1,frame,frame+1) if 0<=k<=maximum)
    for event in events:
        for time in (event['start_s']-.12,event['start_s'],event['end_s'],event['end_s']+.1):add_time(time)
        if event['kind']=='formula_prefix':
            h=event.get('highlight_timing') or {}
            for key in ('plus_start_s','three_start_s','is_start_s'):
                if key in h:add_time(h[key])
    for state in states:
        for key in ('formula_start_s','formula_end_s','result_start_s','progress_commit_s'):
            if state.get(key) is not None:add_time(state[key])
    # Entire half-second windows around both decimal-width changes, and the
    # last term, keep individual digit boundary mixing observable at native size.
    for n in (4,34,101):
        at=frame_at(states[n-1]['result_start_s']);indices.update(k for k in range(at-15,at+16) if 0<=k<=maximum)
    return sorted(indices)


INPUT_BOX=(430,205,700,305)
ADDEND_BOX=(740,205,990,305)
EQUALS_BOX=(1030,205,1120,305)
EQ_RESULT_BOX=(1160,205,1480,305)
RESULT_BOX=(630,395,1290,560)
READING_BOX=(300,605,1620,655)
PROGRESS_BOX=(500,1033,1420,1063)
RECENT_BOX=(420,680,1500,722)
TERM_BOX=(1450,345,1740,395)


def clamp(value):
    return max(0.,min(1.,value))


def smooth(value):
    value=clamp(value);return value*value*(3-2*value)


def tick(value):
    return round(clamp(value)*60)


def label(name,text,size,box,color=INK,fill=None,**options):
    return dict(name=name,text=text,size=size,box=tuple(box),color=color,fill=fill,**options)


class Oracle:
    """Editorial contract independently rebuilt from measured cue boundaries."""
    def __init__(self,plan):
        self.plan=plan;self.events=plan['voice_events'];self.states=plan['counted_states']
        self.by={e['id']:e for e in self.events};self.starts=[e['start_s'] for e in self.events]
        self.ends=[e['end_s'] for e in self.events if e['kind']=='count'];self.segments=[(0,'intro',0,'I001')]
        for n,state in enumerate(self.states,1):
            start=state['formula_start_s']-.70 if n>1 else state['voice_start_s']-.32
            self.segments.append((max(0,frame_at(start)),'count',n,f'E{n:03}' if n>1 else 'N001'))
            if f'X{n:03}' in self.by:self.segments.append((frame_at(self.by[f'X{n:03}']['start_s']-.30),'replay',n,f'X{n:03}'))
        self.segments.append((frame_at(self.by['O001']['start_s']-.30),'outro',101,'O001'));self.segments.sort()
        self.segment_starts=[r[0] for r in self.segments]
        self.cuts=[row[0] for i,row in enumerate(self.segments) if i and (row[1]!=self.segments[i-1][1] or row[1]=='replay')]
        self.landmarks={}
        if plan.get('source_phonemes'):
            dependency=plan['source_phonemes'];path=path_of(dependency['path']);require(sha(path)==dependency['sha256'],'CTC dependency changed')
            recognized={r['id']:r for r in json.loads(path.read_text())['results']}
            for n in (4,51,101):
                row=recognized[f'X{n:03}'];require(row['source_sha256']==self.by[row['id']]['source_sha256'],'Explanation CTC source differs')
                phones=[(c,t) for t in row['tokens'] for c in t['token'].replace('ː','') if c not in ' ˈˌ'];text=''.join(c for c,t in phones)
                occurrences=list(re.finditer(r'[ɪᵻiə]z',text));require(occurrences,'No independently recognized is before replay result')
                onset=phones[occurrences[-1].end()][1]['start_s'];self.landmarks[n]={'result_commit':max(.5,onset-.12),'result_onset':onset}
                if n==4:
                    zero=re.search(r'z[iɪ]ɹoʊ',text)
                    if zero:self.landmarks[n]['zero_example']=phones[zero.start()][1]['start_s']-.12
            row=recognized['X034'];phones=[(c,t) for t in row['tokens'] for c in t['token'].replace('ː','') if c not in ' ˈˌ'];text=''.join(c for c,t in phones)
            first=re.search(r'naɪndinaɪn',text);require(first,'No recognized99landmark')
            second=re.search(r'wʌnhʌndɹ[ᵻɪ]d',text[first.end():]);require(second,'No recognized100landmark')
            two_start=first.end()+second.start();two_end=first.end()+second.end();third=re.search(r'wʌnhʌndɹ[ᵻɪ]dwʌn',text[two_end:]);require(third,'No recognized101landmark')
            self.landmarks[34]={'commits':[phones[k][1]['start_s']-.12 for k in (first.start(),two_start,two_end+third.start())]}

    def state(self,frame):
        at=frame/FPS;_,mode,n,cue=self.segments[max(0,bisect_right(self.segment_starts,frame)-1)]
        active=self.events[max(0,bisect_right(self.starts,at)-1)]
        lesson=0
        if mode=='count':
            state=self.states[n-1]
            if n==1:phase,p=('result',60) if at>=state['result_start_s'] else ('seed',0)
            else:
                event=self.by[f'E{n:03}'];start,end=event['start_s'],event['end_s']
                plus=event.get('highlight_timing',{}).get('plus_start_s',start+(end-start)*.34)
                arrival=state['result_start_s']-.08
                if at<start-.08:phase,p='transfer',tick(smooth((at-(start-.70))/((start-.08)-(start-.70))))
                elif at<plus:phase,p='input',0
                elif at<arrival:phase,p='add',tick(smooth((at-plus)/max(.01,arrival-plus)))
                elif at<state['result_start_s']:phase,p='merge',tick((at-arrival)/(state['result_start_s']-arrival))
                else:phase,p='result',60
            cue=f'N{n:03}' if phase=='result' or n==1 else f'E{n:03}'
        elif mode=='intro':
            cue=active['id'] if active['id'].startswith('I') else 'I007';event=self.by[cue]
            phase,p=cue,tick((at-event['start_s'])/max(.01,event['duration_s']))
        elif mode=='replay':
            event=self.by[cue];u=clamp((at-event['start_s'])/max(.01,event['duration_s']))
            if n==34:
                commits=self.landmarks.get(34,{}).get('commits',[event['duration_s']*.5,event['duration_s']*.66,event['duration_s']*.81]);relative=at-event['start_s'];lesson=bisect_right(commits,relative);phase,p='carry',0
                if lesson<3:p=tick((relative-commits[lesson]+.48)/.48)
            else:
                commit=self.landmarks.get(n,{}).get('result_commit',event['duration_s']*.84);relative=clamp((at-event['start_s'])/max(.01,commit))
                if relative<.20:phase,p='term-input',tick(relative/.20)
                elif relative<.40:phase,p='subtract',tick((relative-.20)/.20)
                elif relative<.77:phase,p='multiply',tick((relative-.40)/.37)
                elif relative<1:phase,p='join',tick((relative-.77)/.23)
                else:phase,p='replay-result',60
                if n==4 and at-event['start_s']>=self.landmarks.get(4,{}).get('zero_example',event['duration_s']*.77):lesson=1
        else:
            cue=active['id'] if active['id'].startswith('O') else 'O003';event=self.by[cue]
            phase,p='outro',tick((at-event['start_s'])/max(.01,event['duration_s']))
        fade=0
        for cut in self.cuts:
            if abs(frame-cut)<=3:fade=max(fade,round(255*(1-abs(frame-cut)/3)))
        fade_in=self.plan['intro'].get('fade_in_s',.6)
        if at<fade_in:fade=max(fade,round(255*(1-at/fade_in)))
        fade_out=self.plan['finale'].get('fade_last_s',.75)
        end=(self.plan['duration_frames']-1)/FPS
        if at>end-fade_out:fade=max(fade,round(255*clamp((at-end+fade_out)/fade_out)))
        return {'mode':mode,'n':n,'phase':phase,'tick':p,'completed':bisect_right(self.ends,at),'cue':cue,'fade':fade,'lesson':lesson}

    def common_labels(self,s):
        subtitle='THE SAME DIFFERENCE · ADD THREE'
        if s['mode']=='intro':subtitle='NUM-NUM NUMBERS · THE MORNING WIND ORGAN'
        elif s['mode']=='outro':subtitle='ONE RULE · THE SEQUENCE KEEPS GOING'
        elif s['mode']=='replay':subtitle='REPLAY · THREE UNIT STEPS CROSS A HUNDRED' if s['n']==34 else 'REPLAY · (n − 1) GROUPS OF THREE'
        return [label('series-title','ARITHMETIC SEQUENCE',53,(250,42,1670,116)),label('scene-subtitle',subtitle,22,(220,126,1700,162),TEAL),label('progress',f'Terms counted: {s["completed"]} / 101',22,PROGRESS_BOX,MUTED)]

    def count_labels(self,s):
        n,p=s['n'],s['tick']/60;value=2+3*(n-1);rows=self.common_labels(s)
        rows.append(label('term-number',f'TERM {n}',27,TERM_BOX,TEAL))
        if n==1:
            rows.append(label('seed-equation',' = 2',80,(370,205,1550,305),indexed='1',colors=(INK,TEAL)))
        else:
            rows.extend([label('equation-addend','+ 3',80,ADDEND_BOX,TEAL,PALE),label('equation-equals','=',80,EQUALS_BOX,INK,PALE),label('fixed-addend-label','ADD THREE',27,(650,345,1070,390),TEAL)])
            if s['phase']=='transfer':
                q=1-p;x=q*q*960+2*q*p*500+p*p*565;y=q*q*477.5+2*q*p*465+p*p*255;scale=1+(80/180-1)*p
                row=label('moving-previous-answer',str(value-3),180,(0,0,1,1),source_size=180,raster_scale=scale)
                layer,_,_=label_geometry(row['text'],180,(0,0,1,1),180,scale)
                b=layer.point(lambda v:255 if v>=128 else 0).getbbox();w,h=b[2]-b[0],b[3]-b[1]
                row['box']=(x-w/2-8,y-h/2-8,x+w/2+8,y+h/2+8);rows.append(row)
            else:rows.append(label('equation-input',str(value-3),80,INPUT_BOX,INK,PALE,source_size=180,raster_scale=80/180))
            if s['phase']=='result':rows.append(label('equation-result',str(value),80,EQ_RESULT_BOX,GOLD,PALE))
        if s['phase']=='result':
            rows.extend([label('generated-value',str(value),180,RESULT_BOX,GOLD),label('natural-reading',cardinal(value),35,READING_BOX)])
        elif n>1:rows.append(label('generation-caption','The same three, every time.',30,READING_BOX,TEAL))
        k=s['completed'];recent=[2+3*(j-1) for j in range(max(1,k-4),k+1)]
        if recent:rows.append(label('recent-terms',('…   ' if k>5 else '')+'   →   '.join(map(str,recent)),29,RECENT_BOX,TEAL))
        return rows

    def labels(self,s):
        if s['mode']=='count':return self.count_labels(s)
        rows=self.common_labels(s);cue=s['cue'];p=s['tick']/60;n=s['n'];phase=s['phase']
        if s['mode']=='intro':
            if cue in ('I001','I007'):
                rows.extend([label('opening-promise','A little breeze. Three more.',65,(300,224,1620,314),TEAL),label('general-rule',' = 2 + (n − 1) × 3',64,(320,353,1600,465),indexed='n',colors=(INK,TEAL)),label('sequence-preview','2,  5,  8,  11,  14, …',55,(450,531,1470,612),GOLD)])
            elif cue=='I002':
                rows.extend([label('choose-seed','START WITH 2',58,(300,235,1620,325),TEAL),label('intro-fixed-addend','+ 3',100,(1070,390,1400,525),GOLD),label('intro-rule-caption','Choose the start. Keep the difference.',37,(300,574,1620,632))])
            elif cue in ('I003','I004'):
                rows.extend([label('equation-input','2',80,INPUT_BOX,INK,PALE,source_size=180,raster_scale=80/180),label('equation-addend','+ 3',80,ADDEND_BOX,TEAL,PALE),label('equation-equals','=',80,EQUALS_BOX,INK,PALE),label('preview-label','PREVIEW',27,(1440,345,1740,390),TEAL),label('fixed-addend-label','ADD THREE',27,(650,345,1070,390),TEAL),label('intro-flow-caption','Input → add three → next value',36,(300,605,1620,655),TEAL)])
                if p>=.8:rows.extend([label('equation-result','5',80,EQ_RESULT_BOX,GOLD,PALE),label('preview-value','5',180,RESULT_BOX,GOLD)])
            elif cue=='I005':
                rows.extend([label('recurrence-preview','next value = current value + 3',57,(300,230,1620,355),TEAL),label('equal-step-preview','2   →   5   →   8   →   11',65,(330,435,1590,520),GOLD)])
                rows.extend(label(f'equal-step-{x}','+3',32,(x-60,560,x+60,615),TEAL) for x in (625,900,1180))
            elif cue=='I006':
                rows.extend([label('term-label','TERM NUMBER',36,(300,250,900,320),TEAL),label('value-label','VALUE',36,(1050,250,1650,320),GOLD),label('term-example','n = 4',80,(350,365,850,495),TEAL),label('value-example',' = 11',80,(1050,365,1650,495),indexed='4',colors=(INK,TEAL)),label('term-value-distinction','PREVIEW · number 4 in the sequence has value 11',31,(300,560,1620,625))])
        elif s['mode']=='outro':
            rows.extend([label('general-rule',' = 2 + (n − 1) × 3',65,(300,218,1620,340),indexed='n',colors=(INK,TEAL)),label('beginning-values','2, 5, 8, 11, 14, …',55,(330,425,1590,497),TEAL),label('ending-values','…, 296, 299, 302',65,(330,547,1590,632),GOLD),label('completed-count','101 terms. The same difference: +3.',34,(330,667,1590,721))])
        elif n==34:
            rows.extend([label('equation-input','98',80,INPUT_BOX,INK,PALE,source_size=180,raster_scale=80/180),label('equation-addend','+ 3',80,ADDEND_BOX,TEAL,PALE),label('equation-equals','=',80,EQUALS_BOX,INK,PALE),label('equation-result','101',80,EQ_RESULT_BOX,GOLD,PALE),label('carry-replay-label','REPLAY',32,(650,346,1270,395),TEAL)])
            stage=s['lesson']
            for j,(x,v) in enumerate(zip((585,835,1085,1335),(98,99,100,101))):
                rows.append(label(f'carry-intermediate-{j}',str(v),86,(x-105,448,x+105,570),GOLD if j==stage else MUTED))
                if j<3:rows.append(label(f'carry-one-step-{j}','+1',27,(x+100,585,x+170,632),TEAL))
            rows.extend([label('carry-decomposition','98 + 2 = 100     then     100 + 1 = 101',38,(360,744,1560,809),TEAL),label('carry-not-new-terms','99 and 100: intermediate values.',27,(650,851,1590,906))])
        else:
            groups=n-1;value=2+groups*3;index='n' if phase=='term-input' else str(n)
            if phase=='term-input':tail=f' = 2 + ({n} − 1) × 3';index=str(n)
            elif phase=='subtract' and p<.55:tail=f' = 2 + ({n} − 1) × 3'
            else:tail=f' = 2 + {groups} × 3'
            if phase=='replay-result':tail+=f' = {value}'
            formula=label('working-general-formula',tail,65,(300,208,1620,313),INK,PALE,indexed=index,colors=(INK,TEAL))
            if phase=='term-input':formula['masked']=str(n)
            rows.extend([formula,label('input-term-number',f'n = {n}',39,(760,350,1160,402),TEAL)])
            if phase not in ('join','replay-result'):rows.append(label('replay-seed-label','START: 2',28,(410,633,730,677),TEAL))
            if phase=='term-input':
                # Source digit ink is copied from the n=... label, delivered
                # into the actual (n−1) decimal operand slot along the specified
                # three-leg path. The token uses its real raster39→65.
                full=f'n = {n}';face=font(39);source_layer,source_xy,_=label_geometry(full,39,(760,350,1160,402))
                fb=face.getbbox(full);token=Image.new('L',source_layer.size)
                ImageDraw.Draw(token).text((40-fb[0]+face.getlength('n = '),40-fb[1]),str(n),font=face,fill=255)
                sb=token.point(lambda v:255 if v>=128 else 0).getbbox();sx=(sb[0]+sb[2])/2+source_xy[0];sy=(sb[1]+sb[3])/2+source_xy[1]
                complete,formula_xy,_=label_geometry(tail,65,(300,208,1620,313),0,1,index)
                part_a=glyph_alpha('a',65);part_sub=glyph_alpha(index,round(65*.52));part_rest=glyph_alpha(tail,65)
                ba,bs,br=[x.point(lambda v:255 if v>=128 else 0).getbbox() for x in (part_a,part_sub,part_rest)];rest_x=42+ba[2]-ba[0]+bs[2]-bs[0]
                f=font(65);fb=f.getbbox(tail);token=Image.new('L',part_rest.size)
                ImageDraw.Draw(token).text((40-fb[0]+f.getlength(' = 2 + ('),40-fb[1]),str(n),font=f,fill=255)
                tb=token.point(lambda v:255 if v>=128 else 0).getbbox();tx=formula_xy[0]+rest_x+(tb[0]+tb[2])/2-br[0];ty=formula_xy[1]+25+(tb[1]+tb[3])/2-br[1]
                q=smooth(p)
                if q<.25:x,y=sx,sy+(340-sy)*q/.25
                elif q<.60:x,y=sx+(tx-sx)*(q-.25)/.35,340
                else:x,y=tx,340+(ty-340)*(q-.60)/.40
                scale=1+(65/39-1)*q;moving,_,_=label_geometry(str(n),39,(0,0,1,1),39,scale);b=moving.point(lambda v:255 if v>=128 else 0).getbbox();w,h=b[2]-b[0],b[3]-b[1]
                rows.append(label('moving-term-input',str(n),39,(x-w/2-8,y-h/2-8,x+w/2+8,y+h/2+8),TEAL,source_size=39,raster_scale=scale))
            elif phase=='subtract':rows.append(label('subtract-one-result',f'{n} − 1 = {groups}',35,(760,414,1510,474),TEAL))
            else:rows.append(label('addition-count',f'{groups} additions',35,(760,414,1510,474),TEAL))
            if n==4:
                text='n − 1 groups of three' if phase=='term-input' else '3 groups of three' if phase=='subtract' else '3 groups × 3' if phase=='multiply' and p<.95 else '3 groups × 3 = 9'
                if phase not in ('join','replay-result'):rows.append(label('replay-group-label',text,31,(760,633,1490,677),GOLD))
                if phase=='replay-result':rows.append(label('replay-completed-sum','2 + 9 = 11',54,(650,490,1450,590),TEAL))
                if phase=='replay-result' and s['lesson']:rows.append(label('first-term-zero-additions','First term: 2 + 0 × 3 = 2',31,(600,705,1610,758),TEAL))
            else:
                count=groups//10;shown=0 if phase in ('term-input','subtract') else math.ceil(p*count) if phase=='multiply' else count
                for j in range(shown):
                    row,col=divmod(j,5);x,y=820+col*133,530+row*86
                    rows.append(label(f'compressed-30-unit-marker-{j}','30',29,(x-42,y-24,x+42,y+24),GOLD,'#f3d8a8'))
                marker_text=f'{count} markers × 30 = {groups*3}' if phase in ('join','replay-result') else f'{count} markers × 30' if phase=='multiply' else f'{groups} groups of three' if phase=='subtract' else 'n − 1 groups of three'
                if phase!='join':rows.extend([label('compressed-marker-legend','1 marker = 10 groups × 3 = 30 units',27,(700,720,1560,769),TEAL),label('compressed-marker-total',marker_text,30,(700,655,1560,704),GOLD)])
                else:
                    q=smooth(p);rx,ry=(980,871) if n==51 else (1320,871);x,y=1130+(rx-1130)*q,680+(ry-680)*q;scale=1-.35*q
                    moving,_,_=label_geometry(str(groups*3),48,(0,0,1,1),48,scale);b=moving.point(lambda v:255 if v>=128 else 0).getbbox();w,h=b[2]-b[0],b[3]-b[1]
                    rows.append(label('moving-added-subtotal',str(groups*3),48,(x-w/2-8,y-h/2-8,x+w/2+8,y+h/2+8),GOLD,source_size=48,raster_scale=scale))
            if phase=='replay-result':
                rows.extend([label('replay-generated-value',str(value),123,(770,791,1190,951) if n==51 else (1110,791,1530,951),GOLD),label('replay-natural-reading',cardinal(value),31,(400,971,1360,1015) if n==51 else (640,971,1710,1015))])
            elif phase!='join':rows.append(label('replay-generation-caption','Subtract one to find\nthe number of groups.',31,(610,820,1370,925),TEAL))
        return rows

    def particles(self,s):
        n,p=s['n'],s['tick']/60;mode,phase=s['mode'],s['phase'];groups=[]
        if mode=='count':
            if n==1 and phase=='result':groups.append({'name':'first-term-two-units','positions':[(925,578),(995,578)],'radius':18,'seed':True})
            elif n>1 and phase not in ('transfer','result'):
                if phase=='input':positions=[(810+j*55,430) for j in range(3)]
                elif phase=='add':positions=[(810+j*55+(110-j*15)*p,430+85*p-math.sin(math.pi*p)*42) for j in range(3)]
                else:positions=[(920+j*40+(40-j*40)*p,515+(477.5-515)*p) for j in range(3)]
                groups.append({'name':'addend-three-units','positions':positions,'radius':18,'seed':False,'intentional_overlap':phase=='merge'})
        elif mode=='replay':
            if n==34:
                stage=s['lesson'];positions=[]
                for j in range(stage,3):
                    x,y=650+j*250,684
                    if j==stage:
                        q=smooth(p);destination=(585,835,1085,1335)[j+1]
                        if q<.65:x=x+(destination-x)*q/.65
                        else:x,y=destination,684+(570-684)*(q-.65)/.35
                    positions.append((x,y))
                groups.append({'name':'carry-three-unit-steps','positions':positions,'radius':18,'seed':False})
            elif n==4:
                seed=[(530,550),(595,550)];sources=[(x+(j-1)*48,550) for x in (850,1100,1350) for j in range(3)]
                visible=0 if phase in ('term-input','subtract') else math.ceil(p*9) if phase=='multiply' else 9
                added=sources[:visible]
                if phase in ('join','replay-result'):
                    q=smooth(min(1,p/.5)) if phase=='join' else 1;targets=[(755+j*62,525) for j in range(6)]+[(786+j*62,587) for j in range(5)]
                    moved=[(a[0]+(b[0]-a[0])*q,a[1]+(b[1]-a[1])*q) for a,b in zip(seed+sources,targets)]
                    if phase=='join' and p>.5:
                        contraction=smooth((p-.5)/.5);moved=[(x+(1320-x)*contraction,y+(871-y)*contraction) for x,y in moved]
                    seed,added=moved[:2],moved[2:]
                    if phase=='replay-result':seed=[];added=[]
                groups.extend([{'name':'replay-seed-units','positions':seed,'radius':19,'seed':True},{'name':'replay-addend-units','positions':added,'radius':17,'seed':False,'intentional_overlap':phase=='join'}])
            elif phase!='replay-result':
                positions=[(530,550),(595,550)]
                if phase=='join':
                    q=smooth(p);rx,ry=(980,871) if n==51 else (1320,871)
                    positions=[(x,y+(825-y)*q/.4) if q<.4 else (x+(rx-x)*(q-.4)/.6,825+(ry-825)*(q-.4)/.6) for x,y in positions]
                groups.append({'name':'replay-seed-units','positions':positions,'radius':21,'seed':True,'intentional_overlap':phase=='join'})
        elif mode=='intro':
            if s['cue']=='I002':groups.append({'name':'intro-seed-two','positions':[(640,465),(710,465)],'radius':25,'seed':True})
            elif s['cue'] in ('I003','I004') and p<.8:
                q=tick(p/.8)/60;positions=[(810+j*55+(110-j*15)*q,430+85*q-math.sin(math.pi*q)*42) for j in range(3)]
                groups.append({'name':'intro-three-units','positions':positions,'radius':18,'seed':False})
        return [g for g in groups if g['positions']]


def inspect_particle_group(image,row,frame,divisor=1):
    points=tuple((round(x),round(y)) for x,y in row['positions']);radius=row['radius']
    expected_bounds=(min(x for x,y in points)-radius,min(y for x,y in points)-radius,max(x for x,y in points)+radius+1,max(y for x,y in points)+radius+1)
    area=(max(0,(expected_bounds[0]-12)//divisor*divisor),max(0,(expected_bounds[1]-12)//divisor*divisor),min(SIZE[0],math.ceil((expected_bounds[2]+12)/divisor)*divisor),min(SIZE[1],math.ceil((expected_bounds[3]+12)/divisor)*divisor))
    actual=observed_ink(image,area,TEAL if row['seed'] else GOLD,divisor=divisor)
    # The intended group is its unit particles. Guarded rectangular unit ROIs
    # exclude unrelated labels between widely separated units, while retaining
    # every full circle and surrounding room. This is not an ellipse stencil.
    guarded=Image.new('L',actual.size);guards=ImageDraw.Draw(guarded)
    for x,y in points:
        guards.rectangle((math.floor((x-radius-8-area[0])/divisor),math.floor((y-radius-8-area[1])/divisor),math.ceil((x+radius+9-area[0])/divisor)-1,math.ceil((y+radius+9-area[1])/divisor)-1),fill=255)
    actual=ImageChops.darker(actual,guarded)
    expected=Image.new('L',(area[2]-area[0],area[3]-area[1]));draw=ImageDraw.Draw(expected)
    for x,y in points:draw.ellipse((x-radius-area[0],y-radius-area[1],x+radius-area[0],y+radius-area[1]),fill=0,outline=255,width=3)
    if divisor!=1:expected=expected.resize(actual.size,Image.Resampling.BOX).point(lambda v:255 if v>=128 else 0)
    score=iou(actual,expected);minimum=.75 if divisor==1 else .57
    record={'frame':frame,'name':row['name'],'resolution_divisor':divisor,'expected_primitives':len(points),'intentional_overlap':bool(row.get('intentional_overlap')),'foreground_extraction':'union of per-unit guarded rectangular ROIs, not expected ellipse stencils','ring_footprint_iou':score,'minimum_ring_iou':minimum,'passed':actual.getbbox() is not None and score>=minimum}
    if divisor==1:
        box=(expected_bounds[0]-8,expected_bounds[1]-8,expected_bounds[2]+8,expected_bounds[3]+8)
        try:record['alignment']=raster_centering_report(actual,box,origin_xy=area[:2],name=f'{frame}/{row["name"]}',tolerance_px=1);record['passed'] &= record['alignment']['passed']
        except ValueError as exc:record['alignment']={'passed':False,'error':str(exc)};record['passed']=False
        components=[c for c in connected_components(actual) if c['pixels']>=12]
        record['observed_ring_components']=len(components)
        if not row.get('intentional_overlap'):
            # A pair of different-colour seed/addend particles can intentionally
            # contact in a join; all ordinary premerge dots stay distinct.
            record['component_count_matches']=len(components)==len(points);record['passed'] &= record['component_count_matches']
    return record


def particle_bounds(group):
    radius=group['radius'];points=[(round(x),round(y)) for x,y in group['positions']]
    return (min(x for x,y in points)-radius,min(y for x,y in points)-radius,max(x for x,y in points)+radius+1,max(y for x,y in points)+radius+1)


def near_boxes(a,b,margin=12):
    return max(a[0],b[0])-margin<min(a[2],b[2])+margin and max(a[1],b[1])-margin<min(a[3],b[3])+margin


def contact_groups(rows,groups,state):
    """Declare only the mathematical contacts specified by the scene contract."""
    packets=[];rows=list(rows);groups=list(groups)
    if state['mode']=='replay' and state['phase']=='term-input':
        moving=next((r for r in rows if r['name']=='moving-term-input'),None);source=next((r for r in rows if r['name']=='input-term-number'),None)
        if moving and source:
            a=label_geometry(moving['text'],moving['size'],moving['box'],moving.get('source_size',0),moving.get('raster_scale',1))[2]
            b=label_geometry(source['text'],source['size'],source['box'])[2]
            if near_boxes(a,b):
                packets.append({'name':'term-input-copy-contact','labels':[source,moving],'groups':[],'color':TEAL,'meaning':'The same n token leaves its still-readable source label; both complete glyph groups are one temporary intended visible group.'})
                rows=[r for r in rows if r not in (source,moving)]
            else:
                formula=next((r for r in rows if r['name']=='working-general-formula'),None)
                if formula:
                    bounds=label_geometry(formula['text'],formula['size'],formula['box'],0,1,formula.get('indexed'),formula.get('masked'))[2]
                    if near_boxes(a,bounds,margin=5):
                        packets.append({'name':'term-input-formula-destination-contact','labels':[formula,moving],'groups':[],'color':TEAL,'meaning':'The correct decimal n arrives in its reserved (n−1) operand slot; the whole formula and incoming glyph form one intended visible group.'})
                        rows=[r for r in rows if r not in (formula,moving)]
    if state['mode']=='replay' and state['phase']=='join':
        if state['n']==4 and len(groups)==2 and near_boxes(particle_bounds(groups[0]),particle_bounds(groups[1])):
            packets.append({'name':'eleven-unit-joining-group','labels':[],'groups':groups,'color':GOLD,'meaning':'Two seed units and nine addend units intentionally merge into the result; precontact counts are checked separately.'});groups=[]
        elif state['n'] in (51,101):
            subtotal=next((r for r in rows if r['name']=='moving-added-subtotal'),None)
            if subtotal and groups:
                bounds=label_geometry(subtotal['text'],subtotal['size'],subtotal['box'],subtotal.get('source_size',0),subtotal.get('raster_scale',1))[2]
                if near_boxes(bounds,particle_bounds(groups[0])):
                    packets.append({'name':'seed-and-subtotal-joining-group','labels':[subtotal],'groups':groups,'color':GOLD,'meaning':'Exactly two seed units join the independently computed150/300 subtotal, before the atomic152/302 answer.'});groups=[];rows=[r for r in rows if r is not subtotal]
    return rows,groups,packets


def inspect_contact_packet(image,packet,frame,divisor=1):
    """Observe the full intended contact group, never a clipped isolated ROI.

    The actual foreground is contrast-extracted without an expected stencil.
    A separate simple compositor produces only the expected mathematical packet
    from independently calculated positions, font ink and exact unit circles.
    """
    expected_image=background().convert('RGBA');alpha=Image.new('L',SIZE)
    for group in packet['groups']:
        draw=ImageDraw.Draw(expected_image);mask_draw=ImageDraw.Draw(alpha);radius=group['radius']
        for x,y in group['positions']:
            x,y=round(x),round(y);box=(x-radius,y-radius,x+radius,y+radius)
            draw.ellipse(box,fill='#d9eee6' if group['seed'] else '#f3d8a8',outline=TEAL if group['seed'] else GOLD,width=3);mask_draw.ellipse(box,fill=255)
    for row in packet['labels']:
        shape,origin,_=label_geometry(row['text'],row['size'],row['box'],row.get('source_size',0),row.get('raster_scale',1),row.get('indexed'),row.get('masked'))
        colored=Image.new('RGBA',shape.size,row['color']);colored.putalpha(shape)
        if row.get('indexed') is not None:
            size=row['size'];lead=glyph_alpha('a',size);sub=glyph_alpha(str(row['indexed']),round(size*.52));ba,bs=[x.point(lambda v:255 if v>=128 else 0).getbbox() for x in (lead,sub)]
            index_mask=Image.new('L',shape.size);index_mask.paste(sub.crop(bs),(25+ba[2]-ba[0],25+round(size*.55)))
            colored.putalpha(ImageChops.subtract(shape,index_mask));part=Image.new('RGBA',shape.size,TEAL);part.putalpha(index_mask);colored.alpha_composite(part)
        expected_image.alpha_composite(colored,origin)
        pasted=Image.new('L',SIZE);pasted.paste(shape,origin);alpha=ImageChops.screen(alpha,pasted)
    bounds=alpha.point(lambda v:255 if v>=128 else 0).getbbox();require(bounds,'Empty expected contact group')
    area=(max(0,(bounds[0]-12)//divisor*divisor),max(0,(bounds[1]-12)//divisor*divisor),min(SIZE[0],math.ceil((bounds[2]+12)/divisor)*divisor),min(SIZE[1],math.ceil((bounds[3]+12)/divisor)*divisor))
    expected_rgb=expected_image.convert('RGB')
    if divisor!=1:expected_rgb=expected_rgb.resize((SIZE[0]//divisor,SIZE[1]//divisor),Image.Resampling.BOX)
    actual=observed_ink(image,area,packet['color'],divisor=divisor);expected=observed_ink(expected_rgb,area,packet['color'],divisor=divisor)
    score=iou(actual,expected);minimum=.88 if divisor==1 else .76
    result={'frame':frame,'name':packet['name'],'resolution_divisor':divisor,'meaning':packet['meaning'],'member_labels':[r['name'] for r in packet['labels']],'primitive_units':sum(len(g['positions']) for g in packet['groups']),'intended_contact_group':True,'foreground_iou':score,'minimum_iou':minimum,'passed':actual.getbbox() is not None and score>=minimum}
    if divisor==1:
        box=(bounds[0]-8,bounds[1]-8,bounds[2]+8,bounds[3]+8)
        try:result['alignment']=raster_centering_report(actual,box,origin_xy=area[:2],name=f'{frame}/{packet["name"]}',tolerance_px=1);result['passed'] &= result['alignment']['passed']
        except ValueError as exc:result['alignment']={'passed':False,'error':str(exc)};result['passed']=False
    return result


def fade_patches(image,s,frame,divisor=2):
    patches=[(70,300,110,340),(1800,300,1840,340),(60,900,100,940),(1820,900,1860,940)]
    alpha=s['fade']/255;rows=[];plate=background(divisor)
    for box in patches:
        small=tuple(v//divisor for v in box);observed=ImageStat.Stat(image.crop(small)).mean;source=ImageStat.Stat(plate.crop(small)).mean
        expected=[v*(1-alpha)+target*alpha for v,target in zip(source,rgb(PALE))]
        errors=[abs(a-b) for a,b in zip(observed,expected)];rows.append(max(errors))
    return {'frame':frame,'fade_alpha_255':s['fade'],'maximum_patch_channel_error':max(rows),'passed':max(rows)<=5}


def visual_checks(video,plan,frame_plan_path,ffmpeg,directory,native_stride=None):
    directory.mkdir(parents=True,exist_ok=True);oracle=Oracle(plan)
    raw=Path(frame_plan_path).read_bytes();frame_plan=json.loads(gzip.decompress(raw) if str(frame_plan_path).endswith('.gz') else raw)
    frames=frame_plan['frames'];require(frames,'Empty actual frame plan')
    rows=[];failures=[];native_records=[];minimum={};statistics=Counter();max_dx=max_dy=0.;fade_errors=[];half_flags={}
    def consume(frame,image,divisor):
        nonlocal max_dx,max_dy
        source=frames[frame]['frame'];s=oracle.state(source);declared=frames[frame]
        for key in ('mode','n','phase','tick','completed','cue','fade','lesson'):
            if declared.get(key)!=s[key]:
                failures.append({'output_frame':frame,'source_frame':source,'schedule_field':key,'expected':s[key],'declared':declared.get(key)})
        fade=fade_patches(image,s,source,divisor);statistics['fade_frame_observations']+=1
        if not fade['passed'] and len(fade_errors)<100:fade_errors.append(fade)
        if s['fade']:
            statistics[f'fade_frames_divisor_{divisor}']+=1;return
        label_rows,particle_rows,packets=contact_groups(oracle.labels(s),oracle.particles(s),s)
        for row in label_rows:
            # During the n-token delivery, that token deliberately enters the
            # vacant formula slot. The complete composed expression is checked
            # immediately after landing; the moving glyph is checked every
            # frame on its independently reconstructed path.
            if s['mode']=='replay' and s['phase']=='term-input' and row['name']=='working-general-formula':
                statistics['formula_slot_delivery_frames']+=1;continue
            result=inspect_label(image,row,source,divisor,alignment=divisor==1,digits=divisor==1)
            statistics[f'glyph_observations_divisor_{divisor}']+=1
            minimum[row['name']]=min(minimum.get(row['name'],1),result['glyph_iou'])
            if divisor==1:
                native_records.append(result)
                alignment=result.get('alignment',{})
                max_dx=max(max_dx,abs(alignment.get('delta_x_px',0)));max_dy=max(max_dy,abs(alignment.get('delta_y_px',0)))
                statistics['native_digit_observations']+=len(result.get('digits',[]))
            if not result['passed']:
                if divisor==2:half_flags.setdefault(frame,[]).append(result)
                elif len(failures)<500:failures.append(result)
        for group in particle_rows:
            result=inspect_particle_group(image,group,source,divisor);statistics[f'particle_group_observations_divisor_{divisor}']+=1
            if divisor==1:native_records.append(result)
            if not result['passed']:
                if divisor==2:half_flags.setdefault(frame,[]).append(result)
                elif len(failures)<500:failures.append(result)
        for packet in packets:
            result=inspect_contact_packet(image,packet,source,divisor);statistics[f'contact_group_observations_divisor_{divisor}']+=1
            if divisor==1:native_records.append(result)
            if not result['passed']:
                if divisor==2:half_flags.setdefault(frame,[]).append(result)
                elif len(failures)<500:failures.append(result)
        if divisor==1 and (s['n'] in (1,4,34,67,101) or s['mode']!='count'):
            if statistics['saved_native_frames']<70 and source%3==0:
                image.save(directory/f'native-{source:06}.png');statistics['saved_native_frames']+=1
    count=0
    for frame,image in decoded_frames(video,ffmpeg,directory/'all-frame-decode.log',2):
        require(frame<len(frames),'Movie has more frames than its frame plan');consume(frame,image,2);count+=1
        if count%1500==0:print(json.dumps({'visual_half_frames':count,'declared_frames':len(frames),'flags':len(failures)}),flush=True)
    require(count==len(frames),'Decoded frame count differs from actual frame plan')
    write_json(directory/'half-resolution-flags.json',{'video_sha256':sha(video),'frames':half_flags})
    native_source=set(native_sample_indices(plan,plan['voice_events'],plan['counted_states']))
    if native_stride:native_indices=[i for i in range(len(frames)) if i%native_stride==0 or frames[i]['frame'] in native_source]
    else:native_indices=[i for i,r in enumerate(frames) if r['frame'] in native_source]
    native_indices=sorted(set(native_indices)|set(half_flags))
    for i,image in decoded_frames(video,ffmpeg,directory/'native-decode.log',1,native_indices):consume(i,image,1)
    report={'passed':not failures and not fade_errors,'video_sha256':sha(video),'background':{'path':str(BACKGROUND),'sha256':sha(BACKGROUND)},'frame_plan_sha256':sha(frame_plan_path),'decoded_frames':count,'native_sample_frames':len(native_indices),'half_resolution_flag_frames_reobserved_natively':len(half_flags),'statistics':dict(statistics),'minimum_glyph_iou_by_component':minimum,'maximum_native_abs_dx_px':max_dx,'maximum_native_abs_dy_px':max_dy,'native_alignment_tolerance_px':1,'failures':failures,'fade_curve_failures':fade_errors,'scope':'Every actual decoded frame: independent arithmetic state/atomic numeric glyphs/readings/progress/recent terms, moving previous-value and n/subtotal raster, exact particle-ring footprints. Native cue/operator/commit/carry boundaries, every half-resolution warning and requested time samples: both-axis physical ink bounds and digit competition. Whole fades checked from actual static-background patch colors. Formula body during n-token delivery is observed after landing; its incoming token is checked throughout its path.','artistic_review_separate':True}
    write_json(directory/'visual-verification.json',report)
    (directory/'native-pixel-observations.json.gz').write_bytes(gzip.compress(json.dumps(native_records,ensure_ascii=False,separators=(',',':')).encode()))
    return report


def pcm16(data):
    result=array('h');result.frombytes(data);return result


def waveform(reference,observed,guard=8,stride=12):
    scores=[]
    for lag in range(-guard,guard+1):
        pairs=((reference[i],observed[i+lag]) for i in range(guard,min(len(reference),len(observed))-guard,stride))
        dot=aa=bb=error=0.
        for a,b in pairs:
            dot+=a*b;aa+=a*a;bb+=b*b;error+=(a-b)*(a-b)
        if aa and bb:
            scores.append((dot/math.sqrt(aa*bb),lag,math.sqrt(error/aa)))
    return max(scores) if scores else (0,0,1)


def decoded_audio(video,ffmpeg,channel=None):
    args=[str(ffmpeg),'-v','error','-i',str(video),'-vn']
    if channel is not None:
        args.extend(['-af',f'pan=mono|c0=c{channel}'])
    else:
        args.extend(['-ac','1'])
    args.extend(['-ar',str(RATE),'-f','s16le','pipe:1'])
    return pcm16(subprocess.run(args,capture_output=True,check=True).stdout)


def audio_checks(plan,events,video,master,ffmpeg,directory,export_clips=False):
    directory.mkdir(parents=True,exist_ok=True)
    reference=decoded_audio(master,ffmpeg)
    channels=[decoded_audio(video,ffmpeg,k) for k in (0,1)]
    rows=[]
    for event in events:
        start,end=sample(event['start_s']),sample(event['end_s'])
        data=[]
        for k,channel in enumerate(channels):
            corr,lag,relative=waveform(reference[start:end],channel[start:end])
            data.append({'channel':k,'correlation':corr,'lag_samples_24k':lag,'relative_rms_error':relative,'passed':corr>=.985 and relative<=.19})
        rows.append({'id':event['id'],'start_sample_24k':start,'end_sample_24k':end,'channels':data,'passed':all(x['passed'] for x in data)})
    guards=[];cursor=0
    for event in events+ [{'id':'END','start_s':len(reference)/RATE,'end_s':len(reference)/RATE}]:
        end=sample(event['start_s']);a=cursor+sample(.025);b=end-sample(.025)
        if b>a:
            def rms(seq):return math.sqrt(sum(x*x for x in seq)/len(seq)) if seq else 0
            master_rms=rms(reference[a:b]);observed=[rms(ch[a:b]) for ch in channels]
            guards.append({'before':event['id'],'start_s':a/RATE,'end_s':b/RATE,'master_rms_pcm16':master_rms,'aac_rms_pcm16':observed,'passed':max(observed)<=max(16,master_rms*1.3+6)})
        cursor=sample(event['end_s'])
    report={'passed':all(r['passed'] for r in rows) and all(r['passed'] for r in guards),'master_sha256':sha(master),'video_sha256':sha(video),'rate_for_comparison_hz':RATE,'final_AAC_channels_compared_separately':True,'decoded_audio_frames_per_channel':list(map(len,channels)),'master_frames':len(reference),'cue_comparisons':rows,'silence_intervals':guards,'scope':'Final decoded AAC versus measured master, every cue separately in left/right and every sufficiently long planned silent interval. This is waveform evidence, not new lexical recognition or human listening.'}
    write_json(directory/'waveform-and-silence.json',report)
    if export_clips:
        clips=directory/'final-aac-clips';clips.mkdir(exist_ok=True);manifest={'schema_version':1,'measurement_status':'measured','numbers':[],'dialogue':[],'video_sha256':sha(video),'kind':'arithmetic-final-aac-isolated-clips'}
        for event in events:
            # Small guards lie entirely inside the shorter .16s expression gap.
            a=max(0,sample(event['start_s'])-sample(.06));b=min(len(channels[0]),sample(event['end_s'])+sample(.06))
            path=clips/f'{event["id"]}.wav';mono=array('h',((int(x)+int(y))//2 for x,y in zip(channels[0][a:b],channels[1][a:b])))
            with wave.open(str(path),'wb') as stream:
                stream.setparams((1,2,RATE,len(mono),'NONE','not compressed'));stream.writeframes(mono.tobytes())
            row={'id':event['id'],'number':event.get('value') if event['kind']=='count' else None,'index':event.get('n'),'spoken_text':event['text'],'path':str(path.resolve()),'sha256':sha(path),'duration_s':len(mono)/RATE,'final_aac_range_s':[a/RATE,b/RATE]}
            manifest['numbers' if event['kind']=='count' else 'dialogue'].append(row)
        write_json(directory/'final-aac-manifest.json',manifest)
    return report


def srt_seconds(value):
    h,m,s,ms=map(int,re.split('[:,]',value));return h*3600+m*60+s+ms/1000


def subtitle_checks(events,path):
    blocks=Path(path).read_text().strip().split('\n\n');rows=[]
    require(len(blocks)==len(events),'Subtitle cue count differs')
    for event,block in zip(events,blocks):
        lines=block.splitlines();match=re.fullmatch(r'(\d\d:\d\d:\d\d,\d{3}) --> (\d\d:\d\d:\d\d,\d{3})',lines[1]);require(match is not None,'Invalid SRT time')
        start,end=map(srt_seconds,match.groups());text=' '.join(lines[2:])
        same=re.sub(r'\s+',' ',text).strip()==re.sub(r'\s+',' ',event['text']).strip()
        rows.append({'id':event['id'],'start_error_ms':(start-event['start_s'])*1000,'end_error_ms':(end-event['end_s'])*1000,'text_matches':same,'passed':same and abs(start-event['start_s'])<=.001 and abs(end-event['end_s'])<=.001})
    return {'passed':all(r['passed'] for r in rows),'srt_sha256':sha(path),'cues':rows}


def main():
    global BACKGROUND
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline',type=Path,required=True)
    parser.add_argument('--video',type=Path)
    parser.add_argument('--master',type=Path)
    parser.add_argument('--captions',type=Path)
    parser.add_argument('--out-dir',type=Path,required=True)
    parser.add_argument('--phase',choices=['schedule','audio','visual','all'],default='schedule')
    parser.add_argument('--frame-plan',type=Path)
    parser.add_argument('--native-stride',type=int)
    parser.add_argument('--background',type=Path)
    parser.add_argument('--export-aac-clips',action='store_true')
    parser.add_argument('--ffmpeg',default=str(ROOT/'.venv/bin/ffmpeg'))
    parser.add_argument('--ffprobe',default=str(ROOT/'.venv/bin/ffprobe'))
    args=parser.parse_args();args.out_dir.mkdir(parents=True,exist_ok=True)
    report_path=args.out_dir/'verification.json';require(not report_path.exists(),'Choose an unused QA output directory')
    plan=json.loads(args.timeline.read_text());events,states,mathematics=validate_schedule(plan)
    verifier_sha_at_start=sha(Path(__file__))
    report={'schema_version':1,'kind':'independent-arithmetic-delivery-qa','created_at_utc':datetime.now(timezone.utc).isoformat(),'timeline':str(args.timeline),'timeline_sha256':sha(args.timeline),'verifier_source_sha256':verifier_sha_at_start,'mathematics_and_schedule':mathematics,'schedule_negative_controls':schedule_controls(plan),'scope_phase':args.phase}
    if args.video:report['inputs']={'video':{'path':str(args.video),'sha256':sha(args.video)}}
    if args.captions:
        report['subtitles']=subtitle_checks(events,args.captions)
    if args.phase in ('audio','all'):
        require(args.video and args.master,'--video and --master required for audio')
        report['source_acceptance']=source_gate_checks(plan,events)
        report['source_split_integrity']=split_integrity_checks(events,path_of(plan['speech_manifest']['path']))
        report['audio']=audio_checks(plan,events,args.video,args.master,args.ffmpeg,args.out_dir/'audio',args.export_aac_clips)
    if args.phase in ('visual','all'):
        require(args.video,'--video is required for actual pixel QA')
        if args.background:
            BACKGROUND=args.background
        else:
            native_inputs=json.loads((args.video.parent/'native-layout-verification.json').read_text())['source_inputs']
            bg_dependency=native_inputs['background'];BACKGROUND=path_of(bg_dependency['path']);require(sha(BACKGROUND)==bg_dependency['sha256'],'Render background changed')
        background.cache_clear()
        frame_plan=args.frame_plan or args.video.parent/'frame-plan.json.gz'
        report['pixels']=visual_checks(args.video,plan,frame_plan,args.ffmpeg,args.out_dir/'visual',args.native_stride)
        report['pixel_negative_controls']=pixel_negative_controls(args.out_dir/'pixel-controls')
    if args.phase=='all':
        report['technical']=technical.verify_video(args.video,args.out_dir/'technical',args.timeline,args.ffmpeg,args.ffprobe,duration_bounds=(480,1800))
    report['passed']=all(v.get('passed',v.get('status')!='fail') for v in report.values() if isinstance(v,dict))
    report['completed_episode_accepted']=False
    report['remaining_gates']=['Actual decoded glyph/digit/particle/progress/motion QA','Final AAC new isolated ASR/CTC and warning review','Native artistic comparison and continuous-motion review']
    require(sha(Path(__file__))==verifier_sha_at_start,'Verifier code changed while this audit was running; preserve this attempt and rerun a frozen version')
    write_json(report_path,report);print(json.dumps({'passed':report['passed'],'report':str(report_path)}))


if __name__=='__main__':
    main()
