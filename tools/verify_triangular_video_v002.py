"""Independent triangular-number v002 delivery verification.

Revision gates: grammatically singular n=1 row, plural n>=2 rows, and
visible left-facing notice-053 guide poses. The immutable v001 verifier is kept.

No triangular producer, renderer, formatter or motion adapter is imported.
Arithmetic comes from binomial coefficients and row sums. Observations are
decoded MP4 pixels, separately rasterized font glyphs, connected components,
decoded AAC waveforms and delivered subtitle text. An absent check never passes.
"""
from __future__ import annotations

import argparse
from array import array
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import wave

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat, ImageOps

if __package__:
    from .component_alignment import raster_centering_report
    from . import verify_video as technical
    from .verify_prime_video import decoded_frames
else:
    from component_alignment import raster_centering_report
    import verify_video as technical
    from verify_prime_video import decoded_frames

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/triangular-counting-v1'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
BACKDROP = DESIGN / 'generation-batches/triangular-20261112-01a1cd42/source/cave-clean-plate.png'
FPS, RATE, SIZE = 30, 48000, (1920, 1080)
INK, MUTED, AMBER, EDGE, TEAL = '#544b42', '#766f60', '#edbc62', '#a66c32', '#478b88'
FORMULA_BOX = (363, 153, 1557, 233)
RESULT_BOX = (600, 265, 1320, 380)
READING_BOX = (300, 389, 1620, 430)
ARRAY_BOX = (490, 447, 1430, 883)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def path_of(path):
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def sample(at):
    return round(at * RATE)


def frame_at(at):
    return math.ceil(at * FPS - 1e-7)


def truth_values(last=60):
    values = tuple(math.comb(n + 1, 2) for n in range(last + 1))
    require(values[0] == 0 and all(v == sum(range(n + 1)) for n, v in enumerate(values)),
            'Independent binomial/row-sum truth disagrees')
    require(all(values[n] - values[n-1] == n for n in range(1, last+1)),
            'Independent triangular differences disagree')
    return values


def cardinal(number):
    small = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
    tens = dict(zip(range(20, 100, 10), 'twenty thirty forty fifty sixty seventy eighty ninety'.split()))
    if number < 20:
        return small[number]
    if number < 100:
        return tens[number//10*10] + ('-' + small[number%10] if number%10 else '')
    if number < 1000:
        return small[number//100] + ' hundred' + (' ' + cardinal(number%100) if number%100 else '')
    require(number < 1_000_000, 'Unsupported cardinal range')
    return cardinal(number//1000) + ' thousand' + (' ' + cardinal(number%1000) if number%1000 else '')


def parse_cardinal(text):
    """Strict inverse parser independent of authored English strings."""
    small = dict(zip('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split(), range(20)))
    tens = dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(), range(20, 100, 10)))
    if not isinstance(text, str) or not re.fullmatch(r'[a-z]+(?:[ -][a-z]+)*', text):
        return None
    tokens = text.replace('-', ' ').split()
    def group(words):
        if not words:
            return 0
        if 'hundred' in words:
            if len(words) < 2 or words[1] != 'hundred' or words.count('hundred') != 1 or not 1 <= small.get(words[0], -1) <= 9:
                return None
            tail = group(words[2:])
            return small[words[0]]*100 + tail if tail is not None and tail < 100 else None
        if len(words) == 1:
            return small.get(words[0], tens.get(words[0]))
        if len(words) == 2 and words[0] in tens and 1 <= small.get(words[1], -1) <= 9:
            return tens[words[0]] + small[words[1]]
        return None
    if 'thousand' in tokens:
        if tokens.count('thousand') != 1:
            return None
        k = tokens.index('thousand')
        a, b = group(tokens[:k]), group(tokens[k+1:])
        answer = a*1000+b if a and b is not None and b < 1000 else None
    else:
        answer = group(tokens)
    return answer if answer is not None and cardinal(answer).replace('-', ' ') == text.replace('-', ' ') else None


def validate_schedule(plan, last=60):
    values = truth_values(last)
    require(plan['fps'] == FPS and plan['duration_frames'] == frame_at(plan['duration_s']), 'Incorrect frame grid/duration')
    require(480 <= plan['duration_s'] < 1800, 'Long-form duration must be >=480s and <1800s')
    events = sorted(plan.get('voice_events', plan.get('events', [])), key=lambda r: r['start_s'])
    require(events and len(events) == len({e['id'] for e in events}), 'Missing or duplicate speech cues')
    authored = json.loads((DESIGN/'math/math-plan.json').read_text())
    require(authored['n_max'] == last and authored['terms'] == last+1, 'Authored range differs from verification contract')
    authored_by_id = {e['id']:e for e in authored['cues']}
    require(set(authored_by_id) == {e['id'] for e in events}, 'Actual and authored speech cue sets differ')
    cursor = 0
    for event in events:
        a, b = sample(event['start_s']), sample(event['end_s'])
        require(cursor <= a < b <= sample(plan['duration_s']), f'Invalid/overlapping cue {event["id"]}')
        require(a%2 == b%2 == 0, f'Cue left 24kHz source sample grid: {event["id"]}')
        require(event['text'] == authored_by_id[event['id']]['text_en'], f'Untracked script change {event["id"]}')
        cursor = b
    by_id = {e['id']:e for e in events}
    counts = [e for e in events if re.fullmatch(r'N\d{3}', e['id'])]
    expressions = [e for e in events if re.fullmatch(r'E\d{3}', e['id'])]
    require([e['id'] for e in counts] == [f'N{n:03}' for n in range(last+1)], 'Count cues omit/reorder an index')
    require([e['id'] for e in expressions] == [f'E{n:03}' for n in range(1,last+1)], 'Expression cues omit/reorder an index')
    states = plan.get('counted_states', plan.get('count_states', []))
    require(len(states) == last+1, 'Wrong counted-state count')
    ordinary, extended = [], []
    for n, state in enumerate(states):
        result = by_id[f'N{n:03}']
        require(state.get('n', state.get('index')) == n and state['value'] == values[n], f'Wrong index/value n{n}')
        require(parse_cardinal(result['text']) == values[n], f'Wrong result cardinal n{n}')
        commit = state.get('result_start_s', state.get('display_start_s'))
        require(sample(result['start_s']-commit) == sample(.12), f'Result lead is not .12s n{n}')
        require(sample(state['voice_start_s']) == sample(result['start_s']) and sample(state['voice_end_s']) == sample(result['end_s']), f'State and audio timing differ n{n}')
        if n:
            prefix = by_id[f'E{n:03}']
            require(prefix['text'] == f'{cardinal(n)} times {cardinal(n+1)}, divided by two, equals', f'Wrong expression words n{n}')
            require(sample(result['start_s']-prefix['end_s']) == sample(.16), f'Formula/result gap is not .16s n{n}')
            require(sample(state['formula_start_s']) == sample(prefix['start_s']) and sample(state['formula_end_s']) == sample(prefix['end_s']), f'Formula state timing differs n{n}')
            require(state.get('operands', [state.get('a'), state.get('b')]) == [n,n+1], f'Wrong formula operands n{n}')
        if n < last:
            following = by_id[f'E{n+1:03}']
            lessons = [e for e in events if result['end_s'] <= e['start_s'] < following['start_s'] and e['id'].startswith(('X','T'))]
            gap = sample(following['start_s'])-sample(result['end_s'])
            if lessons:
                require(all(e['start_s'] >= result['end_s'] and e['end_s'] <= following['start_s'] for e in lessons), f'Checkpoint overlaps count n{n}')
                extended.append({'after_n':n,'gap_s':gap/RATE,'cues':[e['id'] for e in lessons]})
            else:
                require(gap == sample(2), f'Ordinary N-end→next-E-start gap differs n{n}')
                ordinary.append(n)
    boundaries = [n for n in range(1,last+1) if len(str(values[n])) > len(str(values[n-1]))]
    if last == 60:
        require([r['after_n'] for r in extended] == [4,5,10,14,45] and len(ordinary) == 55,
                'Checkpoint/ordinary boundary coverage differs from the agreed editorial contract')
        spoken = sum(e['end_s']-e['start_s'] for e in events)
        require(abs(plan['duration_s']-spoken-137.6) <= 1/RATE,
                'Speech plus fixed editorial transitions differs from137.60s')
    for checkpoint in extended:
        lesson = [by_id[i] for i in checkpoint['cues']]
        require(sample(lesson[0]['start_s']-by_id[f'N{checkpoint["after_n"]:03}']['end_s']) == sample(.6),
                'Checkpoint first spoken entrance differs from.6s')
        for left,right in zip(lesson,lesson[1:]):
            require(sample(right['start_s']-left['end_s']) == sample(.6), 'Checkpoint sentence gap differs from.6s')
        require(sample(by_id[f'E{checkpoint["after_n"]+1:03}']['start_s']-lesson[-1]['end_s']) == sample(2),
                'Checkpoint final settling differs from2s')
    return events, states, {'passed':True, 'truth':'binomial coefficients, row sums, consecutive differences, strict inverse English cardinal parsing',
        'terms':last+1, 'expressions':last, 'endpoint':values[-1], 'value_sum':sum(values), 'voice_events':len(events),
        'ordinary_two_second_boundaries':ordinary, 'extended_boundaries':extended, 'decimal_digit_boundaries':boundaries,
        'speech_duration_s':sum(e['end_s']-e['start_s'] for e in events), 'actual_editing_duration_s':plan['duration_s']-sum(e['end_s']-e['start_s'] for e in events)}


def source_acceptance_check(plan,events):
    require(plan.get('speech_adopted') is True, 'Timeline speech has not been adopted')
    dependency=plan.get('speech_acceptance')
    require(dependency and dependency.get('path') and dependency.get('sha256'), 'Missing hash-bound speech-acceptance gate')
    path=path_of(dependency['path']);require(sha(path)==dependency['sha256'], 'Speech acceptance gate hash changed')
    gate=json.loads(path.read_text());require(gate.get('accepted') and not gate.get('unresolved'), 'Unresolved speech gate')
    decisions={r['id']:r for r in gate.get('results',[])}
    require(set(decisions)=={e['id'] for e in events}, 'Speech acceptance does not cover every cue')
    for event in events:
        row=decisions[event['id']]
        require(row.get('accepted') and not row.get('failures') and row.get('source_sha256')==event['source_sha256'], f'Unaccepted/wrong-source speech {event["id"]}')
    return {'passed':True,'path':str(path),'sha256':sha(path),'accepted_cues':len(events),
        'scope':'Hash-bound current source acceptance decisions inspected. This verifier does not rerun ASR/CTC.'}


@lru_cache(maxsize=96)
def font(size):
    return ImageFont.truetype(str(FONT), size)


@lru_cache(maxsize=1024)
def glyph_alpha(text, size):
    """Own glyph raster; visible ink, never advance or font origin as bounds."""
    face = font(size)
    tokens=re.fullmatch(r'(\d+)( × )(\d+)( ÷ 2)( = )([\d,?]+)',text)
    if tokens:
        # The working formula uses six independently highlighted typographic
        # runs. Fractional font advances are retained across those runs. A
        # single whole-line Pillow draw has slightly different ink placement.
        # Tokens and their values are parsed here from independent arithmetic.
        parts=tokens.groups();width=math.ceil(sum(face.getlength(p) for p in parts))
        out=Image.new('L',(width+80,size*2+80));draw=ImageDraw.Draw(out);x=40
        for part in parts:
            draw.text((x,30),part,font=face,fill=255);x+=face.getlength(part)
        return out
    if '\n' in text:
        lines = [glyph_alpha(s,size) for s in text.split('\n')]
        boxes = [im.point(lambda a:255 if a>=128 else 0).getbbox() for im in lines]
        width = max(b[2]-b[0] for b in boxes)
        height = sum(b[3]-b[1] for b in boxes)+12*(len(lines)-1)
        out = Image.new('L',(width+80,height+80)); y=40
        for im,b in zip(lines,boxes):
            out.paste(im.crop(b),(40+round((width-b[2]+b[0])/2),y));y+=b[3]-b[1]+12
        return out
    if 'ₙ' in text:
        # The font has no Unicode subscript n; this is the agreed typesetting.
        parts = text.split('ₙ'); small = font(round(size*.64))
        width = math.ceil(sum(face.getlength(p) for p in parts)+(len(parts)-1)*small.getlength('n'))
        out = Image.new('L',(width+80,size*2+80));draw=ImageDraw.Draw(out);x=40
        for i,part in enumerate(parts):
            draw.text((x,30),part,font=face,fill=255);x+=face.getlength(part)
            if i<len(parts)-1:
                draw.text((x,30+size*.39),'n',font=small,fill=255);x+=small.getlength('n')
        return out
    b = face.getbbox(text)
    out = Image.new('L',(b[2]-b[0]+80,b[3]-b[1]+80))
    ImageDraw.Draw(out).text((40-b[0],40-b[1]),text,font=face,fill=255)
    return out


def rgb(value):
    return tuple(bytes.fromhex(value.lstrip('#'))) if isinstance(value,str) else tuple(value)


def color_mask(image,color,tolerance=42):
    target=rgb(color)
    channels=[channel.point(lambda v,t=t:255 if abs(v-t)<=tolerance else 0) for channel,t in zip(image.split()[:3],target)]
    return ImageChops.darker(ImageChops.darker(channels[0],channels[1]),channels[2])


@lru_cache(maxsize=4)
def background(divisor=1):
    plate=ImageOps.fit(Image.open(BACKDROP).convert('RGB'),SIZE,Image.Resampling.LANCZOS)
    return plate if divisor==1 else plate.resize((SIZE[0]//divisor,SIZE[1]//divisor),Image.Resampling.BOX)


def iou(a,b):
    union=ImageChops.lighter(a,b).histogram()[255]
    return ImageChops.darker(a,b).histogram()[255]/union if union else 0.


def observed_ink(image, area, colors, fill=None, divisor=1):
    """Extract actual half-contrast glyph cores against the independent plate."""
    crop=image.crop(tuple(v//divisor for v in area)).convert('RGB')
    plate=Image.new('RGB',crop.size,fill) if fill else background(divisor).crop(tuple(v//divisor for v in area))
    changed=ImageChops.lighter(*ImageChops.difference(crop,plate).split()[:2])
    changed=ImageChops.lighter(changed,ImageChops.difference(crop,plate).split()[2]).point(lambda v:255 if v>=24 else 0)
    result=Image.new('L',crop.size)
    for color in colors:
        fg=rgb(color)
        if len(colors)==1:
            # BT709 luma remains full resolution in yuv420p. A teal glyph's
            # red channel contains substantial subsampled chroma, so using its
            # largest RGB contrast can lose genuine thin25px strokes.
            coefficients=(.2126,.7152,.0722,0)
            observed=crop.convert('L',coefficients);base=plate.convert('L',coefficients)
            foreground_level=round(sum(a*b for a,b in zip(fg,coefficients)))
        else:
            channel=max(range(3),key=lambda k:abs(ImageStat.Stat(plate).mean[k]-fg[k]))
            observed=crop.getchannel(channel);base=plate.getchannel(channel);foreground_level=fg[channel]
        # Affine integer expression: 2*observed <= background+foreground.
        midpoint=base.point(lambda v,t=foreground_level:(v+t)//2)
        if ImageStat.Stat(base).mean[0] >= foreground_level:
            half=ImageChops.subtract(observed,midpoint).point(lambda v:255 if v==0 else 0)
        else:
            half=ImageChops.subtract(midpoint,observed).point(lambda v:255 if v==0 else 0)
        half=ImageChops.darker(half,color_mask(crop,fg,105))
        result=ImageChops.lighter(result,half)
    return ImageChops.darker(result,changed)


def label(name,text,size,box,colors=(INK,),fill=None):
    return {'name':name,'text':text,'size':size,'box':tuple(box),'colors':tuple(colors),'fill':fill}


@lru_cache(maxsize=2048)
def label_geometry(text,size,box):
    alpha=glyph_alpha(text,size);b=alpha.point(lambda v:255 if v>=128 else 0).getbbox()
    require(b is not None,'Empty independent expected glyph')
    xy=(round((box[0]+box[2]-b[0]-b[2])/2),round((box[1]+box[3]-b[1]-b[3])/2))
    return alpha,xy,(b[0]+xy[0],b[1]+xy[1],b[2]+xy[0],b[3]+xy[1])


_glyph_shifts={}


@lru_cache(maxsize=4096)
def expected_label_mask(text,size,box,area,divisor,dx=0,dy=0):
    alpha,xy,_=label_geometry(text,size,box)
    out=Image.new('L',(area[2]-area[0],area[3]-area[1]));out.paste(alpha,(xy[0]-area[0]+dx,xy[1]-area[1]+dy))
    if divisor!=1:out=out.resize((out.width//divisor,out.height//divisor),Image.Resampling.BOX)
    return out.point(lambda v:255 if v>=128 else 0)


def inspect_label(image,row,frame,divisor=1,alignment=True):
    box=row['box'];alpha,xy,bounds=label_geometry(row['text'],row['size'],box)
    area=(max(0,(bounds[0]-12)//divisor*divisor),max(0,(bounds[1]-12)//divisor*divisor),
          min(SIZE[0],math.ceil((bounds[2]+12)/divisor)*divisor),min(SIZE[1],math.ceil((bounds[3]+12)/divisor)*divisor))
    actual=observed_ink(image,area,row['colors'],row['fill'],divisor)
    key=(row['text'],row['size'],box,area,divisor)
    if key not in _glyph_shifts:
        _,dx,dy=max((iou(actual,expected_label_mask(row['text'],row['size'],box,area,divisor,dx,dy)),dx,dy)
                    for dy in (-1,0,1) for dx in (-1,0,1))
        _glyph_shifts[key]=(dx,dy)
    dx,dy=_glyph_shifts[key]
    expected=expected_label_mask(row['text'],row['size'],box,area,divisor,dx,dy)
    score=iou(actual,expected);minimum=.92 if divisor==1 else .82
    result={'frame':frame,'name':row['name'],'text':row['text'],'font_size_px':row['size'],'content_box':list(box),'observation_box':list(area),
        'divisor':divisor,'glyph_iou':score,'minimum_glyph_iou':minimum,'fixed_glyph_raster_shift_px':[dx,dy],
        'passed':actual.getbbox() is not None and score>=minimum}
    if alignment and divisor==1:
        try:
            measured=raster_centering_report(actual,box,origin_xy=area[:2],name=f'{frame}/{row["name"]}',tolerance_px=1)
            result['alignment']=measured;result['passed'] &= measured['passed']
        except ValueError as exc:
            result['alignment']={'passed':False,'error':str(exc)};result['passed']=False
    # Every numeric character is checked locally. A long row cannot hide one
    # wrong digit behind a high whole-line IoU.
    if divisor==1 and 'ₙ' not in row['text'] and '\n' not in row['text']:
        face=font(row['size']);fb=face.getbbox(row['text'])
        tokenwise=bool(re.fullmatch(r'(\d+)( × )(\d+)( ÷ 2)( = )([\d,?]+)',row['text']))
        baseline=(xy[0]+40+dx,xy[1]+30+dy) if tokenwise else (xy[0]+40-fb[0]+dx,xy[1]+40-fb[1]+dy)
        checks=[]
        for k,ch in enumerate(row['text']):
            if not ch.isdigit():continue
            b=face.getbbox(ch);advance=face.getlength(row['text'][:k])
            absolute=(math.floor(baseline[0]+advance+b[0]-1),math.floor(baseline[1]+b[1]-1),math.ceil(baseline[0]+advance+b[2]+1),math.ceil(baseline[1]+b[3]+1))
            local=(absolute[0]-area[0],absolute[1]-area[1],absolute[2]-area[0],absolute[3]-area[1])
            value=iou(actual.crop(local),expected.crop(local));checks.append({'position':k,'digit':ch,'iou':value,'passed':value>=.88})
        result['digit_checks']=checks;result['passed'] &= all(r['passed'] for r in checks)
    return result


def connected_components(mask):
    """Independent 8-connected run components; no producer point list used."""
    mask=mask.convert('L');width,height=mask.size;data=mask.tobytes();parents=[];sums=[];previous=[]
    def find(i):
        while parents[i]!=i:
            parents[i]=parents[parents[i]];i=parents[i]
        return i
    for y in range(height):
        row=data[y*width:(y+1)*width];runs=[];x=0
        while x<width:
            if not row[x]:x+=1;continue
            left=x
            while x<width and row[x]:x+=1
            right=x;index=len(parents);parents.append(index)
            length=right-left;sums.append([length,(left+right-1)*length/2,y*length,left,y,right,y+1])
            for a,b,j in previous:
                if b<left:continue
                if a>right:break
                one,two=find(index),find(j)
                if one!=two:parents[two]=one
            runs.append((left,right,index))
        previous=runs
    merged={}
    for i,record in enumerate(sums):
        root=find(i)
        if root not in merged:merged[root]=record.copy()
        else:
            m=merged[root];m[0]+=record[0];m[1]+=record[1];m[2]+=record[2]
            m[3]=min(m[3],record[3]);m[4]=min(m[4],record[4]);m[5]=max(m[5],record[5]);m[6]=max(m[6],record[6])
    return [{'area':r[0],'center':[r[1]/r[0],r[2]/r[0]],'box':r[3:]} for r in merged.values()]


def inspect_points(image,n,frame,groups=('A',),box=ARRAY_BOX,centered=True,new_row=False,b_orientation='descending'):
    """Count decoded components and row occupancies, not expected draw calls."""
    crop=image.crop(box).convert('RGB');plate=background().crop(box)
    changed=ImageChops.lighter(*ImageChops.difference(crop,plate).split()[:2])
    changed=ImageChops.lighter(changed,ImageChops.difference(crop,plate).split()[2]).point(lambda v:255 if v>=22 else 0)
    masks={}
    for group,colors in [('A',(AMBER,EDGE)),('B',(TEAL,'#2c6667','#e1f4ee'))]:
        mask=Image.new('L',crop.size)
        for color in colors:
            # B is a pale filled circle with a teal perimeter. Count the
            # observed interior together with its perimeter: an outline-only
            # palette can split one4px decoded ring into several fragments.
            mask=ImageChops.lighter(mask,color_mask(crop,color,42 if color=='#e1f4ee' else 27))
        mask=ImageChops.darker(mask,changed)
        # The plate is ochre; A must differ in blue from the source plate as
        # well as matching the independent finite point palette.
        if group=='A':
            blue_delta=ImageChops.subtract(plate.getchannel('B'),crop.getchannel('B')).point(lambda v:255 if v>=18 else 0)
            mask=ImageChops.darker(mask,blue_delta)
        masks[group]=mask
    # A white highlight is cream with R>G; it must not become a B point merely
    # because it is close to B's pale fill in a broad RGB palette distance.
    green_over_red=ImageChops.subtract(crop.getchannel('G'),crop.getchannel('R')).point(lambda v:255 if v>=4 else 0)
    masks['B']=ImageChops.darker(masks['B'],green_over_red)
    if new_row:
        # A deliberately teal new row is still part of A. It is never an
        # additional B copy in row-growth mode.
        masks['A']=ImageChops.lighter(masks['A'],masks['B']);masks['B']=Image.new('L',crop.size)
    expected=math.comb(n+1,2);records=[];union=Image.new('L',crop.size)
    for group in ('A','B'):
        components=[c for c in connected_components(masks[group]) if c['area']>=2]
        target=expected if group in groups else 0
        rows=[]
        for component in sorted(components,key=lambda c:c['center'][1]):
            cy=component['center'][1]
            if not rows or abs(cy-sum(c['center'][1] for c in rows[-1])/len(rows[-1]))>2:
                rows.append([component])
            else:rows[-1].append(component)
        occupancy=[len(r) for r in rows]
        wanted=(list(range(1,n+1)) if group=='A' or b_orientation=='ascending' else list(range(n,0,-1))) if target else []
        result={'group':group,'expected_points':target,'observed_components':len(components),'row_occupancy':occupancy,'expected_row_occupancy':wanted,
            'actual_visible_box':list(masks[group].getbbox()) if masks[group].getbbox() else None,
            'passed':len(components)==target and occupancy==wanted}
        records.append(result)
        if group in groups:union=ImageChops.lighter(union,masks[group])
    result={'frame':frame,'n':n,'kind':'decoded-connected-point-components','groups':list(groups),'content_box':list(box),
            'total_expected':expected*len(groups),'records':records,'passed':all(r['passed'] for r in records)}
    if centered and expected:
        try:
            alignment=raster_centering_report(union,box,origin_xy=box[:2],name=f'{frame}/actual-dot-group',tolerance_px=1)
            result['alignment']=alignment;result['passed'] &= alignment['passed']
        except ValueError as exc:
            result['alignment']={'passed':False,'error':str(exc)};result['passed']=False
    return result


def pcm16(data):
    out=array('h');out.frombytes(data)
    if __import__('sys').byteorder!='little':out.byteswap()
    return out


def waveform(reference,observed,guard=8,stride=16):
    ref=reference[::stride];energy=sum(v*v for v in ref);best=(-1,0,0)
    for lag in range(-guard,guard+1):
        actual=observed[guard+lag:guard+lag+len(reference):stride]
        if len(actual)!=len(ref):continue
        actual_energy=sum(v*v for v in actual)
        if not energy or not actual_energy:continue
        corr=sum(a*b for a,b in zip(ref,actual))/math.sqrt(energy*actual_energy)
        if corr>best[0]:best=(corr,lag,10*math.log10(actual_energy/energy))
    return best


def audio_checks(plan,events,video,master,ffmpeg,directory):
    directory.mkdir(parents=True,exist_ok=False);references={};reports=[]
    with tempfile.TemporaryDirectory(prefix='triangular-independent-audio-') as temp:
        temp=Path(temp)
        for event in events:
            source=path_of(event['source_path']);require(sha(source)==event['source_sha256'],f'Speech source changed {event["id"]}')
            if source not in references:
                dest=temp/f'source-{len(references):03}.wav'
                # The production contract uses FFmpeg's mono→stereo rematrix,
                # whose equal-energy channel mapping attenuates each channel.
                # Resample/rematrix the immutable source before assessing the
                # explicitly declared scalar, rather than hiding a3dB error
                # with a widened gain tolerance.
                subprocess.run([str(ffmpeg),'-nostdin','-v','error','-xerror','-n','-i',str(source),'-ar',str(RATE),'-ac','2','-c:a','pcm_s16le',str(dest)],check=True)
                with wave.open(str(dest),'rb') as reader:references[source]=pcm16(reader.readframes(reader.getnframes()))[::2]
        for name,path,lossy in [('master',master,False),('final-aac',video,True)]:
            dest=temp/(name+'.wav')
            subprocess.run([str(ffmpeg),'-nostdin','-v','error','-xerror','-n','-i',str(path),'-map','0:a:0','-ar',str(RATE),'-ac','2','-c:a','pcm_s16le',str(dest)],check=True)
            measurements=[];silent=[];cursor=0;boundary=sample(.03 if lossy else .002)
            with wave.open(str(dest),'rb') as reader:
                require(abs(reader.getnframes()-sample(plan['duration_s']))<=(2048 if lossy else 1),f'{name} duration differs')
                for event in events:
                    start,end=sample(event['start_s']),sample(event['end_s']);reference=references[path_of(event['source_path'])]
                    require(abs(len(reference)-(end-start))<=2,f'Source duration differs {event["id"]}')
                    a,b=cursor+(boundary if cursor else 0),start-boundary
                    if b>a:
                        reader.setpos(a);peak=max(map(abs,pcm16(reader.readframes(b-a))),default=0)
                        silent.append({'start_s':a/RATE,'end_s':b/RATE,'peak_pcm16':peak})
                    reader.setpos(max(0,start-8));actual=pcm16(reader.readframes(len(reference)+16))
                    values=[waveform(reference,actual[channel::2]) for channel in (0,1)]
                    gain=event.get('mix_gain_db',0)+plan.get('master',{}).get('common_gain_db',plan.get('common_gain_db',0))
                    require(min(v[0] for v in values)>=.97,f'{name} speech waveform differs {event["id"]}: {values}')
                    require(all(abs(v[2]-gain)<=(.35 if lossy else .05) for v in values),f'{name} declared gain differs {event["id"]}: {values}, expected {gain}')
                    measurements.append({'id':event['id'],'left_correlation':values[0][0],'right_correlation':values[1][0],
                        'left_lag_samples':values[0][1],'right_lag_samples':values[1][1],'left_gain_db':values[0][2],'right_gain_db':values[1][2],'expected_gain_db':gain})
                    cursor=end
                if cursor+boundary<reader.getnframes():
                    reader.setpos(cursor+boundary);silent.append({'start_s':(cursor+boundary)/RATE,'end_s':reader.getnframes()/RATE,'peak_pcm16':max(map(abs,pcm16(reader.readframes(reader.getnframes()))),default=0)})
            peak=max((s['peak_pcm16'] for s in silent),default=0);require(peak<=(3 if lossy else 1),f'Unexpected {name} sound outside speech: {peak}')
            report={'passed':True,'track':name,'sha256':sha(path),'events':measurements,'silence_intervals':silent,'maximum_silent_interior_peak_pcm16':peak,
                'boundary_guard_s':boundary/RATE,'waveform_stride':16,'lag_search_samples':[-8,8],
                'reference_conversion':'Immutable24k mono source independently converted to48k stereo using FFmpeg default equal-energy rematrix; declared scalar measured relative to one resulting channel.'}
            write_json(directory/(name+'.json'),report);reports.append(report)
    return {'passed':True,'tracks':reports,'scope':f'All {len(events)} scheduled source hashes and master/final-AAC waveforms, both channels, declared gain, guarded silence. Waveform identity is not fresh ASR/CTC or human listening.'}


def subtitle_time(value):
    hour,minute,tail=value.split(':');second,ms=tail.split(',')
    return int(hour)*3600+int(minute)*60+int(second)+int(ms)/1000


def subtitle_checks(events,files):
    require(files,'Missing subtitles');records=[]
    for path in files:
        blocks=path.read_text(encoding='utf-8-sig').strip().split('\n\n')
        require(len(blocks)==len(events),f'Subtitle cue count differs {path}')
        for ordinal,(block,event) in enumerate(zip(blocks,events),1):
            lines=block.splitlines();require(lines[0]==str(ordinal),f'Subtitle ordinal differs {path}/{ordinal}')
            a,b=map(subtitle_time,lines[1].split(' --> '))
            require(abs(a-event['start_s'])<=.000501 and abs(b-event['end_s'])<=.000501,f'Subtitle time differs {event["id"]}')
            require(' '.join(lines[2:])==event.get('subtitle_text',event['text']),f'Subtitle content differs {event["id"]}')
        records.append({'path':str(path),'sha256':sha(path),'cues_checked':len(blocks)})
    return {'passed':True,'files':records}


def independent_state(plan,events,states,at):
    """Editorial scene selection from measured cues, independently of rendering."""
    by={e['id']:e for e in events}
    zero=states[0]['display_start_s']
    outro=by['O01']['start_s']-.12
    if at<zero:
        return {'mode':'intro','cue':events[max(0,bisect_right([e['start_s']-.12 for e in events],at)-1)]['id'],'n':0}
    if at>=outro:
        return {'mode':'outro','n':len(states)-1,'result':True}
    n=max(0,bisect_right([s.get('cycle_start_s',s['start_s']) for s in states],at)-1)
    result=at>=states[n].get('result_start_s',states[n]['display_start_s'])
    nxt=by.get(f'E{n+1:03}')
    explanations=[e for e in events if e.get('index',e.get('n'))==n and e['id'].startswith(('X','T'))]
    if explanations and at>=explanations[0]['start_s']-.12 and (not nxt or at<nxt['start_s']):
        cue=max((e for e in explanations if e['start_s']-.12<=at),key=lambda e:e['start_s'])
        return {'mode':'teaching','n':n,'cue':cue['id'],'result':True}
    return {'mode':'count','n':n,'result':result}


def smooth(value):
    value=max(0,min(1,value));return value*value*(3-2*value)


def ticks(value):
    return round(max(0,min(1,value))*60)


def operation_state(plan,events,states,at):
    state=independent_state(plan,events,states,at);n=state['n']
    state.update(phase='result',build=60,angle=60,merge=60,remove=60,zoom=60)
    if state['mode']=='intro':
        intros=[e for e in events if e['id'].startswith('I')]
        state['cue']=intros[max(0,bisect_right([e['start_s'] for e in intros],at)-1)]['id']
        return state
    if state['mode']=='teaching':
        by={e['id']:e for e in events};cue=state['cue'];e=by[cue]
        u=max(0,min(1,(at-e['start_s'])/(e['end_s']-e['start_s'])))
        state['lesson']=ticks(u)
        if n==4:
            if cue=='X004a':
                if u<.38:state.update(phase='build',build=ticks(u/.38),angle=0,merge=0,remove=0,zoom=0)
                elif u<.76:state.update(phase='rotate',build=60,angle=ticks((u-.38)/.38),merge=0,remove=0,zoom=0)
                else:state.update(phase='pair',build=60,angle=60,merge=ticks((u-.76)/.24),remove=0,zoom=0)
            elif u<.28:state.update(phase='pair',build=60,angle=60,merge=60,remove=0,zoom=0)
            elif u<.78:state.update(phase='half',build=60,angle=60,merge=60,remove=ticks((u-.28)/.50),zoom=0)
        return state
    if state['mode']!='count' or not n or state['result']:
        return state
    by={e['id']:e for e in events};e=by[f'E{n:03}'];start,end=e['start_s'],e['end_s'];h=e['highlight_timing']
    first=h['times_start_s'];second=h['b_start_s'];divided=h['divided_start_s'];equals=h['equals_start_s']
    rotated=second+.58*(divided-second);commit=states[n].get('result_start_s',states[n]['display_start_s'])
    if at<first:state.update(phase='build',build=ticks((at-start)/max(.01,first-start)),angle=0,merge=0,remove=0,zoom=0)
    elif at<second:state.update(phase='copy',build=60,angle=0,merge=0,remove=0,zoom=0)
    elif at<rotated:state.update(phase='rotate',build=60,angle=ticks((at-second)/max(.01,rotated-second)),merge=0,remove=0,zoom=0)
    elif at<divided:state.update(phase='pair',build=60,angle=60,merge=ticks((at-rotated)/max(.01,divided-rotated)),remove=0,zoom=0)
    elif at<equals:state.update(phase='half',build=60,angle=60,merge=60,remove=ticks((at-divided)/max(.01,equals-divided)),zoom=0)
    else:state.update(phase='settle',build=60,angle=60,merge=60,remove=60,zoom=ticks((at-equals)/max(.01,commit-equals)))
    return state


def independent_point_geometry(state):
    """Math coordinates from the agreed physical scene contract, no point list."""
    n=state['n']
    if not n:return [],None
    large=state['mode']=='count' and n>=45
    final_h=435 if large else 340 if n>10 else 295
    op_h=380 if large else min(final_h,260)
    z=smooth(state['zoom']/60)
    height=op_h+(final_h-op_h)*z
    cy=(700+(665-700)*z) if large else 620
    pitch=min(62,height/max(1,n-.36));radius=min(17,pitch*.32)
    x0=960-(n-1)*pitch/2;y0=cy-(n-1)*pitch/2
    visible=n if state['build']==60 else max(0,math.ceil(n*state['build']/60))
    new_row=state['mode']=='teaching' and n in (5,45)
    new_count=math.ceil(n*max(0,min(1,(state.get('lesson',60)-10)/15))) if new_row else n
    if new_row:visible=n if new_count else n-1
    points=[{'id':f'A-{row}-{col}','group':'A','role':'new-row' if new_row and row==n-1 else 'A',
             'row':row,'col':col,'xy':(x0+col*pitch,y0+row*pitch)} for row in range(visible) for col in range(row+1)
            if not new_row or row<n-1 or col<new_count]
    has_b=state['phase'] in ('copy','rotate','pair','half') and not(state['phase']=='half' and state['remove']>=60)
    if has_b:
        angle=math.pi*smooth(state['angle']/60)
        shift=450*(1-smooth(state['merge']/60)) if state['phase'] in ('copy','rotate','pair') else 480*smooth(state['remove']/60)
        px=n*pitch/2;py=(n-1)*pitch/2
        for row in range(n):
            for col in range(row+1):
                dx,dy=col*pitch-px,row*pitch-py
                points.append({'id':f'B-{row}-{col}','group':'B','role':'B','row':row,'col':col,
                    'xy':(x0+px+dx*math.cos(angle)-dy*math.sin(angle)+shift,y0+py+dx*math.sin(angle)+dy*math.cos(angle))})
    return points,{'pitch_px':pitch,'radius_px':radius,'A_rows':visible,'A_expected':math.comb(n,2)+new_count if new_row else math.comb(visible+1,2),
                   'B_expected':math.comb(n+1,2) if has_b else 0,'base_origin':[x0,y0],'center_y':cy,'new_row':new_row}


def inspect_dot_cells(image,state,frame,save_cells=False):
    """Observe every independent dot footprint and its redundant color role.

    Tiny decoded rings can fragment under a perimeter-only threshold. This
    checks actual RGB evidence in every complete analytic circle footprint,
    plus the A/B color relation to the independently loaded clean plate. It
    neither invents pixels with morphology nor accepts a planned count alone.
    """
    points,geometry=independent_point_geometry(state)
    if not geometry:
        return {'frame':frame,'n':0,'expected_points':0,'passed':True,'intentional_empty':True}
    plate=background();radius=geometry['radius_px'];failures=[];minimum={};counts=Counter();cells=[]
    origins={group:(math.floor(min(p['xy'][0] for p in points if p['group']==group)-radius)-20,
                    math.floor(min(p['xy'][1] for p in points if p['group']==group)-radius)-20)
             for group in {p['group'] for p in points}}
    for point in points:
        x,y=point['xy'];ox,oy=origins[point['group']]
        # Pixel-inclusive ellipses are rounded in the group's local integer
        # raster canvas. Preserve that public raster rule, including half ties.
        box=(round(x-radius-ox)+ox,round(y-radius-oy)+oy,round(x+radius-ox)+ox+1,round(y+radius-oy)+oy+1)
        require(0<box[0]<box[2]<1920 and 0<box[1]<box[3]<1080,'Mathematical dot footprint lies outside canvas')
        mask=Image.new('L',(box[2]-box[0],box[3]-box[1]));ImageDraw.Draw(mask).ellipse((0,0,mask.width-1,mask.height-1),fill=255)
        actual=image.crop(box).convert('RGB');base=plate.crop(box)
        am,bm=ImageStat.Stat(actual,mask).mean,ImageStat.Stat(base,mask).mean
        chroma=(am[1]-am[0])-(bm[1]-bm[0]);blue_drop=bm[2]-am[2]
        perimeter=Image.new('L',mask.size)
        width=max(1,round(radius*(.23 if point['role']=='B' else .12)))
        ImageDraw.Draw(perimeter).ellipse((0,0,mask.width-1,mask.height-1),outline=255,width=width)
        edge_color=rgb(EDGE if point['role']=='A' else TEAL if point['role']=='B' else '#2c6667')
        fy=sum(a*b for a,b in zip(edge_color,(.2126,.7152,.0722)))
        qualifying=total=0
        for av,bv,inside in zip(actual.get_flattened_data(),base.get_flattened_data(),perimeter.get_flattened_data()):
            if not inside:continue
            total+=1;ay=sum(a*b for a,b in zip(av,(.2126,.7152,.0722)));by=sum(a*b for a,b in zip(bv,(.2126,.7152,.0722)))
            qualifying+=by-fy>=15 and (by-ay)/(by-fy)>=.5
        coverage=qualifying/total
        if point['role']=='A':ok=blue_drop>=30 and chroma<15 and coverage>=.80
        else:ok=chroma>=25 and coverage>=.80
        item={'id':point['id'],'group':point['group'],'role':point['role'],'footprint':list(box),'coverage':coverage,
              'blue_drop':blue_drop,'green_red_delta':chroma,'passed':ok}
        counts[point['group']]+=int(ok)
        minimum[point['role']]=min(minimum.get(point['role'],1),coverage)
        if not ok:failures.append(item)
        if save_cells:cells.append(item)
    report={'frame':frame,'n':state['n'],'mode':state['mode'],'phase':state['phase'],'geometry':geometry,
        'expected_points':len(points),'A_observed_verified_points':counts['A'],'B_observed_verified_points':counts['B'],
        'minimum_role_pixel_coverage':minimum,'failed_cells':failures,'passed':not failures and counts['A']==geometry['A_expected'] and counts['B']==geometry['B_expected'],
        'method':'Every complete independent circle footprint: actual RGB color role, plus full-resolution BT709-luma half-contrast on every analytic perimeter pixel. The source plate supplies local contrast; no fixed assumption that amber must be bluer/darker than every rock pixel. No morphological pixel invention or producer-returned counts/bounds.',
        'thresholds':{'A_blue_drop_min':30,'A_green_red_delta_max':15,'perimeter_luma_contrast_min':15,'perimeter_observed_alpha_min':.5,'perimeter_coverage_min':.80,'B_green_red_delta_min':25}}
    if save_cells:report['cells']=cells
    # At row-growth replays the unrevealed new-row positions are explicitly
    # checked empty. Otherwise an accidentally early full row could pass by
    # merely containing every expected old dot.
    if geometry['new_row']:
        n=state['n'];shown=geometry['A_expected']-math.comb(n,2);x0,y0=geometry['base_origin'];pitch=geometry['pitch_px'];unexpected=[]
        for col in range(shown,n):
            x,y=x0+col*pitch,y0+(n-1)*pitch
            box=(round(x-radius),round(y-radius),round(x+radius)+1,round(y+radius)+1)
            mask=Image.new('L',(box[2]-box[0],box[3]-box[1]));ImageDraw.Draw(mask).ellipse((0,0,mask.width-1,mask.height-1),fill=255)
            a,b=ImageStat.Stat(image.crop(box).convert('RGB'),mask).mean,ImageStat.Stat(plate.crop(box),mask).mean
            delta=(a[1]-a[0])-(b[1]-b[0]);difference=max(abs(x-y) for x,y in zip(a,b))
            if delta>=15 and difference>=18:unexpected.append({'row':n-1,'col':col,'green_red_delta':delta,'difference':difference})
        report['unrevealed_new_row_positions_checked']=n-shown;report['unexpected_new_row_dots']=unexpected
        report['passed'] &= not unexpected
    return report


def row_count_label(n):
    """Independent number agreement, not the renderer's authored string."""
    require(isinstance(n,int) and n>=0, 'Row count must be a nonnegative integer')
    unit='row' if n==1 else 'rows'
    return f'n = {n} {unit}'


def scene_labels(state,values,events,at):
    n=state['n'];mode=state['mode'];rows=[]
    rows.append(label('title','TRIANGULAR NUMBERS',41,(240,37,1680,82),(INK,),'#fffaf1'))
    rows.append(label('subtitle','REPLAY · NO NEW TERM' if mode=='teaching' else 'NUM-NUM NUMBERS · THE LIGHT-PEBBLE GROTTO',18,(240,90,1680,110),(MUTED,),'#fffaf1'))
    completed=sum(e['end_s']<=at for e in events if re.fullmatch(r'N\d{3}',e['id']))
    rows.append(label('completed-progress',f'Counted: {completed} / 61',26,(170,1005,735,1045),(MUTED,)))
    if mode=='intro':
        rows.extend([label('intro-line','A new row. A bigger triangle.',52,(220,156,1700,226)),
            label('general-formula','Tₙ = n × (n + 1) ÷ 2',66,(340,266,1580,346))])
        texts={'I01':'0, 1, 3, 6, 10, 15, …','I02':'n tells the rows · Tₙ tells the total','I03':'two matching triangles → one rectangle → one equal half'}
        cue=state['cue'];rows.append(label('intro-subject',texts[cue],34 if cue=='I03' else 40,(250,610,1670,664),(TEAL,)))
        return rows
    if mode=='outro':
        rows.extend([label('ending-formula','Tₙ = 1 + 2 + … + n = n × (n + 1) ÷ 2',52,(170,155,1750,229)),
            label('sum-domain','Sum for n >= 1; T₀ = 0',22,(350,243,1570,270),(MUTED,)),
            label('ending-line','Each new row makes the next number.',39,(240,731,1680,784),(TEAL,))])
        for i in range(7):
            text='   '.join(f'{v:,}' for v in values[i*9:i*9+9])
            rows.append(label(f'history-row-{i}',text,29,(290,300+i*54,1630,342+i*54),(INK,),'#fffaf0'))
        return rows
    if mode=='teaching':
        fixed={'n':n,'result':True};primary=count_labels(fixed,values)
        if n in (5,45):primary[0]=label('working-equation',f'{values[n-1]:,} + {n} = {values[n]:,}',65,FORMULA_BOX,(INK,),'#fffaf0')
    else:primary=count_labels(state,values)
    rows.extend(primary)
    if not n:
        rows.append(label('zero-label','NO ROWS · NO DOTS',37,(720,575,1200,654),(MUTED,)))
        return rows
    rows.extend([label('row-label',row_count_label(n),30,(180,606,650,650),(EDGE,)),
        label('column-label',f'rectangle width: n + 1 = {n+1}',25,(150,674,690,718),(TEAL,)),
        label('legend-A','A: filled dots',25,(170,871,700,904),(EDGE,))])
    _,g=independent_point_geometry(state)
    if state['phase'] in ('copy','rotate','pair','half'):rows.append(label('legend-B','B: matching ring dots',25,(170,919,700,952),(TEAL,)))
    elif n>10:rows.append(label('density-note','ALL DOTS SHOWN',24,(170,919,700,952),(MUTED,)))
    if mode=='teaching' and n==45:rows.append(label('threshold-note','1,000 is the mark we crossed',31,(450,840,1470,883),(TEAL,)))
    if mode=='teaching' and n in (10,14):rows.append(label('replay-note','Every dot still counts as one.' if n==10 else 'Three digits. The same rule.',26,(1190,907,1790,954),(TEAL,)))
    return rows


def scene_cuts(plan):
    cuts=[];previous=None
    for s in plan['visual_segments']:
        mode=s['mode'];n=s.get('n',s.get('index'))
        key=('count','large' if n>=45 else 'dense' if n>10 else 'small') if mode=='count' else ('teaching',n) if mode=='teaching' else (mode,0)
        if previous is not None and previous!=key and not(mode=='count' and n==0):cuts.append(frame_at(s['start_s']))
        previous=key
    return cuts


def fade_amount(plan,frame):
    total=plan['duration_frames'];intro=max(1,round(plan.get('intro',{}).get('fade_in_s',.6)*FPS))
    tail=max(2,round(plan['finale']['fade_last_s']*FPS))
    fade=round((1-max(0,min(1,frame/intro)))*255) if frame<intro else round(max(0,min(1,(frame-(total-tail))/(tail-1)))*255)
    for cut in scene_cuts(plan):
        if abs(frame-cut)<=4:fade=max(fade,round((1-abs(frame-cut)/4)*255))
    return fade


def inspect_fade_patches(image,plan,frame,divisor=2):
    alpha=fade_amount(plan,frame)/255;target=(255,250,240);records=[]
    for area in ((30,300,130,400),(1750,320,1850,420),(30,960,130,1060)):
        box=tuple(v//divisor for v in area);actual=image.crop(box).convert('RGB');base=background(divisor).crop(box)
        expected=Image.blend(base,Image.new('RGB',base.size,target),alpha)
        error=ImageStat.Stat(ImageChops.difference(actual,expected)).mean
        records.append({'box':list(area),'rgb_mae':error,'passed':max(error)<=5})
    return {'frame':frame,'fade_8bit':round(alpha*255),'regions':records,'passed':all(r['passed'] for r in records)}


class ActorObserver:
    """Independent original-PNG projection, without the production adapter."""
    def __init__(self,video,plan):
        self.path=video.parent/'motion.json';self.motion=json.loads(self.path.read_text());self.plan=plan
        dep=self.motion['registration']['registry'];self.registry_path=path_of(dep['path'])
        require(sha(self.registry_path)==dep['sha256'],'Actor registry hash changed')
        self.registry=json.loads(self.registry_path.read_text());self.poses=self.registry['poses'];self.images={}
        for name,row in self.poses.items():
            p=path_of(row['path']);require(sha(p)==row['sha256'],f'Actor source hash changed {name}')
            self.images[name]=Image.open(p).convert('RGBA')
        self.actions=self.motion['actions'];self.starts=[a['start_frame'] for a in self.actions]
        # A declaration of four identical quiet poses previously passed. This
        # revision has an independent authored action contract, plus native
        # changed-limb pixel checks in the v002 supplemental QA.
        notice=next((a for a in self.actions if a['id']=='notice-053'),None)
        expected_notice=[(12537,12545,'guide_prepare_left'),(12545,12560,'guide_return_left'),
                         (12560,12569,'guide_prepare_left'),(12569,12577,'gaze_left')]
        require(notice is not None and (notice['start_frame'],notice['end_frame'])==(12537,12577),
                'v002 notice-053 endpoints differ from the independent contract')
        require([(k['start_frame'],k['end_frame'],k['pose']) for k in notice['keys']]==expected_notice,
                'v002 notice-053 guide poses absent, reordered, wrong-facing or retimed')
        self.notice_contract={'passed':True,'action':'notice-053','expected_keys':expected_notice,
                              'scope':'Independent key contract; actual native motion is a separate supplemental gate'}
        require(not self.motion.get('full_actor_crossfade') and not self.motion.get('timing_changed'),'Unexpected actor fade or retiming')
        for action in self.actions:
            keys=action['keys'];require(keys and keys[0]['start_frame']==action['start_frame'] and keys[-1]['end_frame']==action['end_frame'],'Action key endpoints differ')
            for a,b in zip(keys,keys[1:]):require(a['end_frame']==b['start_frame'],'Action keyframes have a gap')
        self.checked=0;self.observed=Counter();self.worst=0;self.failures=[]

    def pose_at(self,frame,state):
        mode,n,phase=state['mode'],state['n'],state['phase'];i=bisect_right(self.starts,frame)-1
        pose=None
        if i>=0 and frame<self.actions[i]['end_frame']:
            pose=next(k['pose'] for k in reversed(self.actions[i]['keys']) if frame>=k['start_frame'])
            if mode=='count' and n>=45:
                if pose+'_left' in self.poses:pose+='_left'
                elif pose in ('neutral','gaze_up','gaze_right'):pose='gaze_left'
        if pose is not None:return pose
        if mode=='count' and n>=45:return 'gaze_left'
        if mode=='count' and phase in ('copy','rotate','pair'):return 'gaze_right'
        if mode=='count' and phase in ('build','half','result'):return 'gaze_up'
        return 'neutral'

    @lru_cache(maxsize=256)
    def reference(self,pose,mode,n,divisor=1):
        if mode=='intro':foot,height=(960,1044),356
        elif mode=='outro':foot,height=(960,1044),231
        elif mode=='teaching':foot,height=((960,1050),150) if n==45 else ((960,1044),215)
        else:foot,height=((1780,1046),164) if n>=45 else ((960,1044),215 if n>10 else 235)
        row=self.poses[pose];scale=height/row['reference_height_px'];source=self.images[pose]
        sprite=source.resize((round(source.width*scale),round(source.height*scale)),Image.Resampling.LANCZOS)
        xy=tuple(round(a-b*scale) for a,b in zip(foot,row['anchor_px']))
        bounds=sprite.getchannel('A').point(lambda v:255 if v>=8 else 0).getbbox()
        absolute=(bounds[0]+xy[0],bounds[1]+xy[1],bounds[2]+xy[0],bounds[3]+xy[1])
        require(24<=absolute[0]<absolute[2]<=1896 and 24<=absolute[1]<absolute[3]<=1056,'Source actor is clipped')
        area=(max(0,(absolute[0]-8)//divisor*divisor),max(0,(absolute[1]-8)//divisor*divisor),
              min(1920,math.ceil((absolute[2]+8)/divisor)*divisor),min(1080,math.ceil((absolute[3]+10)/divisor)*divisor))
        expected=background().crop(area).convert('RGBA');shadow=Image.new('RGBA',expected.size)
        ImageDraw.Draw(shadow).ellipse((foot[0]-height*.26-area[0],foot[1]-5-area[1],foot[0]+height*.36-area[0],foot[1]+8-area[1]),fill=(70,58,42,25))
        expected.alpha_composite(shadow);expected.alpha_composite(sprite,(xy[0]-area[0],xy[1]-area[1]))
        expected=expected.convert('RGB')
        if divisor!=1:expected=expected.resize((expected.width//divisor,expected.height//divisor),Image.Resampling.BOX)
        return expected,area,{'pose':pose,'body_height_px':height,'source_reference_height_px':row['reference_height_px'],'source_anchor_px':row['anchor_px'],
            'ground_target_px':foot,'reference_visible_box':absolute,'scale':scale}

    def inspect(self,image,frame,state,divisor=2):
        pose=self.pose_at(frame,state);expected,area,info=self.reference(pose,state['mode'],state['n'],divisor)
        observed=image.crop(tuple(v//divisor for v in area)).convert('RGB');delta=ImageStat.Stat(ImageChops.difference(expected,observed)).mean
        error=max(delta);passed=error<=4
        self.checked+=1;self.observed[pose]+=1;self.worst=max(self.worst,error)
        result={'frame':frame,**info,'observation_box':list(area),'divisor':divisor,'rgb_mae':delta,'maximum_allowed_channel_mae':4,'passed':passed}
        if not passed and len(self.failures)<50:self.failures.append(result)
        return result

    def report(self):
        return {'passed':not self.failures,'checked_frames':self.checked,'observed_pose_frames':dict(self.observed),'maximum_channel_mae':self.worst,
            'notice_053_independent_contract':self.notice_contract,'failures':self.failures,'motion_path':str(self.path),'motion_sha256':sha(self.path),'registry_sha256':sha(self.registry_path),
            'scope':'Actual decoded actor region versus independently projected immutable runtime PNGs and registered anatomical support; declared action keys, no production adapter import. Artistic sufficiency is reviewed separately.'}


def count_labels(state,values):
    n=state['n'];committed=state['result'];answer=f'{values[n]:,}' if committed else '?'
    return [label('working-equation',f'{n} × {n+1} ÷ 2 = {answer}',65,FORMULA_BOX,(INK,TEAL,EDGE),'#fffaf0'),
            label('result',answer,108,RESULT_BOX),
            label('result-reading',cardinal(values[n]) if committed else 'watch the formula work',31,READING_BOX,(MUTED,))]


def final_array_box(n,mode='count'):
    # Effective teaching region, with the agreed centre unchanged. The margin
    # includes integer ellipse boundary rounding, and excludes the left-side
    # row/rectangle labels. A tight target-only crop would conceal clipping.
    return (710,445,1210,885) if n>=45 and mode=='count' else (710,440,1210,800)


def native_sample_indices(plan,events,states):
    count=plan['duration_frames'];indices={0,count-1};reasons=defaultdict(set)
    def add(at,reason):
        k=frame_at(at)
        for offset in (-1,0,1):
            j=k+offset
            if 0<=j<count:indices.add(j);reasons[j].add(reason)
    for event in events:
        for key in ('start_s','end_s'):add(event[key],event['id']+'/'+key)
        add((event['start_s']+event['end_s'])/2,event['id']+'/midpoint')
    for state in states:
        add(state.get('result_start_s',state['display_start_s']),f'n{state.get("n",state.get("index"))}/commit')
        h=state.get('highlight_timing',{})
        for key,value in h.items():
            if key.endswith('_s') and isinstance(value,(int,float)):add(value,f'n{state.get("n",state.get("index"))}/{key}')
        if h:
            first,second,divided,equals=h['times_start_s'],h['b_start_s'],h['divided_start_s'],h['equals_start_s']
            rotated=second+.58*(divided-second);commit=state.get('result_start_s',state['display_start_s'])
            for a,b,phase in [(first,second,'copy'),(second,rotated,'rotate'),(rotated,divided,'pair'),(divided,equals,'half'),(equals,commit,'settle')]:
                k=frame_at((a+b)/2)
                if 0<=k<count:indices.add(k);reasons[k].add('dot-phase-'+phase)
    for event in events:
        if event['id'].startswith('X'):
            for fraction in (0,.17,.29,.42,.6,.82,.99):
                k=frame_at(event['start_s']+(event['end_s']-event['start_s'])*fraction)
                if 0<=k<count:indices.add(k);reasons[k].add('dot-replay-'+event['id'])
    # Include every frame of the repaired gesture and its immediate edges.
    # These native observations are distinct from all-frame half-size checks.
    for k in range(12535,12579):
        if 0<=k<count:indices.add(k);reasons[k].add('notice053-native-transition')
    for at in [i/FPS for i in range(min(22,count))]+[i/FPS for i in range(max(0,count-40),count)]:
        indices.add(frame_at(at));reasons[frame_at(at)].add('fade')
    return sorted(indices),reasons


def visual_checks(video,plan,events,states,ffmpeg,directory,last=60):
    """All-frame glyph observations and native event/phase boundary sampling."""
    directory.mkdir(parents=True,exist_ok=False);values=truth_values(last)
    failures=[];per_n=Counter();checks=0;decoded=0;native=[];points=[];cell_records=[];fade_records=[];minimum_iou={};fade_skips=Counter()
    actor=ActorObserver(video,plan)
    def collect(records):
        for r in records:
            if not r['passed'] and len(failures)<100:failures.append(r)
    # Every decoded frame is inspected. Faded frames have an independent
    # measured fade curve, rather than pretending pale/empty glyphs were read.
    for frame,image in decoded_frames(video,ffmpeg,directory/'all-frame-half-decode.log',2):
        decoded+=1;at=frame/FPS;state=operation_state(plan,events,states,at)
        fade=inspect_fade_patches(image,plan,frame);fade_records.append(fade);collect([fade])
        if fade_amount(plan,frame):fade_skips[state['mode']]+=1;continue
        collect([actor.inspect(image,frame,state,2)])
        if state['mode']=='count':
            records=[inspect_label(image,row,frame,2,False) for row in count_labels(state,values)]
            checks+=len(records);per_n[state['n']]+=1;collect(records)
            for record in records:minimum_iou[record['name']]=min(minimum_iou.get(record['name'],1),record['glyph_iou'])
        if frame%900==0:print(json.dumps({'visual_half_frame':frame,'of':plan['duration_frames'],'failures_so_far':len(failures)}),flush=True)
    require(decoded==plan['duration_frames'],'Full content decode missed frames')
    require(set(per_n)==set(range(last+1)),'At least one counted index had no actual raster observations')
    write_json(directory/'all-frame-fade-patches.json',fade_records)
    write_json(directory/'all-frame-actor.json',actor.report())
    indices,reasons=native_sample_indices(plan,events,states);fade_images={};scene_checks=Counter();native_frames=0
    point_frames={frame_at((s['voice_start_s']+s['voice_end_s'])/2):n for n,s in enumerate(states)}
    for frame,image in decoded_frames(video,ffmpeg,directory/'native-event-decode.log',1,indices):
        native_frames+=1;at=frame/FPS;state=operation_state(plan,events,states,at)
        if frame<22 or frame>=plan['duration_frames']-40:fade_images[frame]=image.copy()
        if fade_amount(plan,frame):continue
        records=[inspect_label(image,row,frame) for row in scene_labels(state,values,events,at)]
        for record in records:record['sample_reasons']=sorted(reasons.get(frame,()))
        native.extend(records);collect(records);scene_checks[state['mode']]+=1
        if frame in point_frames:
            n=point_frames[frame]
            p=inspect_points(image,n,frame,box=final_array_box(n),centered=bool(n));points.append(p);collect([p])
        dot_reason=any(r.startswith(('dot-phase-','dot-replay-')) for r in reasons.get(frame,()))
        if (frame in point_frames or dot_reason) and state['mode'] in ('count','teaching'):
            result=inspect_dot_cells(image,state,frame);cell_records.append(result);collect([result])
        if state['mode']=='intro' and any('midpoint' in r for r in reasons.get(frame,())):
            p=inspect_points(image,4,frame,box=(840,380,1080,580));points.append(p);collect([p])
        if frame in point_frames or state['mode']!='count' and 'midpoint' in ' '.join(reasons.get(frame,())):
            image.save(directory/f'frame-{frame:05d}.png')
        if dot_reason and state['n'] in (4,5,45,60):image.save(directory/f'phase-{state["n"]:02d}-{state["phase"]}-{frame:05d}.png')
    require(native_frames==len(indices),'Native selected decode missed a frame')
    whole_fades=[];tail=round(plan['finale']['fade_last_s']*FPS)
    for frame,im in sorted(fade_images.items()):
        reference=fade_images.get(18) if frame<18 else fade_images.get(plan['duration_frames']-tail-1) if frame>=plan['duration_frames']-tail else None
        if reference is None:continue
        expected=Image.blend(reference,Image.new('RGB',SIZE,(255,250,240)),fade_amount(plan,frame)/255)
        fields=[]
        for box in ((150,130,1770,985),(780,790,1200,1060)):
            error=ImageStat.Stat(ImageChops.difference(im.crop(box),expected.crop(box))).mean
            fields.append({'box':list(box),'rgb_mae':error,'passed':max(error)<=3})
        record={'frame':frame,'regions':fields,'passed':all(f['passed'] for f in fields)};whole_fades.append(record);collect([record])
    write_json(directory/'native-labels.json',native);write_json(directory/'native-point-arrays.json',points)
    write_json(directory/'native-every-dot-footprints.json',cell_records);write_json(directory/'native-whole-fades.json',whole_fades)
    report={'passed':not failures,'decoded_frames':decoded,'all_count_frame_label_observations':checks,'count_frames_per_index':dict(per_n),
        'native_sample_frames_requested':len(indices),'native_glyph_observations':len(native),'native_point_observations':len(points),
        'all_frame_minimum_glyph_iou':minimum_iou,'intended_fade_frames_excluded_from_glyph_identity':dict(fade_skips),
        'native_scene_frames':dict(scene_checks),'native_dot_cell_observations':len(cell_records),
        'native_verified_dot_footprints':sum(r['expected_points'] for r in cell_records),'native_fade_regions':len(whole_fades),
        'actor':actor.report(),
        'failures':failures,'native_label_report':'native-labels.json','native_point_report':'native-point-arrays.json',
        'scope':'Every frame decoded: count glyphs and actor at half resolution outside declared fades; all-frame background fade curves. Native cue/operator/commit boundaries, every history glyph/digit, replay semantics, all-result point components/rows/both-axis bounds, and independent dot footprints across every operation/replay. Whole intro/end fades inspected against frozen actual unfaded reference frames. Artistic comparison is separately documented.'}
    require(set(scene_checks)=={'intro','count','teaching','outro'},'A required native scene mode was never observed')
    require(len([p for p in points if p.get('n') in range(last+1) and p.get('content_box')==list(final_array_box(p['n']))])>=last+1,'Missing at least one result point array')
    report['supplemental_scene_coverage_complete']=True
    write_json(directory/'verification.json',report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video',type=Path,required=True)
    parser.add_argument('--timeline',type=Path,required=True)
    parser.add_argument('--master',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    parser.add_argument('--last-index',type=int,default=60)
    parser.add_argument('--ffmpeg',default=shutil.which('ffmpeg') or str(ROOT/'.venv/bin/ffmpeg'))
    parser.add_argument('--ffprobe',default=shutil.which('ffprobe') or str(ROOT/'.venv/bin/ffprobe'))
    parser.add_argument('--phase',choices=('schedule','technical','audio','visual','all'),default='all')
    args=parser.parse_args(argv);args.out_dir.mkdir(parents=True,exist_ok=False)
    report={'schema_version':1,'kind':'independent-triangular-v002-final-media-verification','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'passed':False,'phase':args.phase,'verifier_sha256':sha(Path(__file__)),'errors':[]}
    try:
        if args.video.is_file():report['video']={'path':str(args.video),'sha256':sha(args.video)}
        if args.master.is_file():report['master']={'path':str(args.master),'sha256':sha(args.master)}
        plan=json.loads(args.timeline.read_text());report['timeline']={'path':str(args.timeline),'sha256':sha(args.timeline)}
        events,states,report['schedule']=validate_schedule(plan,args.last_index)
        if args.phase in ('technical','all'):
            report['technical']=technical.verify_video(args.video,args.out_dir/'technical',args.timeline,args.ffmpeg,args.ffprobe,duration_bounds=(480,1800))
            require(report['technical']['status']=='pass','Technical media verification failed')
            require(report['technical']['measurements']['true_peak_dbtp']<=-1.45,'Encoded AAC exceeds -1.5dBTP ceiling with .05dB measurement tolerance')
        if args.phase in ('audio','all'):
            report['speech_acceptance']=source_acceptance_check(plan,events)
            report['audio']=audio_checks(plan,events,args.video,args.master,args.ffmpeg,args.out_dir/'audio')
            report['subtitles']=subtitle_checks(events,sorted(args.video.parent.glob('*.srt')))
        if args.phase in ('visual','all'):
            report['visual']=visual_checks(args.video,plan,events,states,args.ffmpeg,args.out_dir/'visual',args.last_index)
            require(report['visual']['passed'],'Actual decoded visual verification is incomplete or failed')
        if 'video' in report:require(sha(args.video)==report['video']['sha256'],'Video changed during independent verification')
        report['passed']=True
    except Exception as exc:
        report['errors'].append(f'{type(exc).__name__}: {exc}')
    report['scope']='Independent automated and sampled observations only. No claim of human full-length continuous viewing/listening. Missing stages are not accepted.'
    write_json(args.out_dir/'verification.json',report)
    print(json.dumps({'passed':report['passed'],'report':str(args.out_dir/'verification.json'),'errors':report['errors']},ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
