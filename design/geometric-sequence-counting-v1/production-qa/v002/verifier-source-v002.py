"""Independent final-media checks for the geometric sequence episode.

No geometric builder, renderer or actor module is imported. Integer truth,
inverse English parsing and glyph masks are independently produced here.
The render manifest supplies the authored placement contract, never pixel truth.
"""
from __future__ import annotations

import argparse
from array import array
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import wave

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat, ImageFilter

if __package__:
    from .component_alignment import raster_centering_report
    from . import verify_video as technical
else:
    from component_alignment import raster_centering_report
    import verify_video as technical

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/geometric-sequence-counting-v1'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
BG = DESIGN / 'generation-batches/geometric-preproduction-20261112-01a1cdca/source/glass-salt-plain.png'
SIZE, FPS, RATE = (1920,1080), 30, 48000
INK, TEAL, MUTED, CORAL = '#573c36','#367f7b','#8c7166','#b86458'
CURRENT_SCENE = None
ACTOR_SOURCE_OBSERVATIONS = {}
ACTOR_BASELINES = {}
SMALL = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
TENS = dict(zip(range(20,100,10),'twenty thirty forty fifty sixty seventy eighty ninety'.split()))
SCALES = [(10**18,'quintillion'),(10**15,'quadrillion'),(10**12,'trillion'),(10**9,'billion'),(10**6,'million'),(1000,'thousand')]


def require(ok,message):
    if not ok: raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as source: return hashlib.file_digest(source,'sha256').hexdigest()


def path_of(path):
    p=Path(path);return p if p.is_absolute() else ROOT/p


def save(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def sample(t):return round(t*RATE)


def first_frame(t):return math.ceil(t*FPS-1e-7)


def values():
    exact=tuple(2*pow(3,n) for n in range(41));repeated=[2]
    for _ in range(40):repeated.append(sum([repeated[-1]]*3))
    require(exact==tuple(repeated),'Power and three-group addition disagree')
    require(exact[-1]==24315330918113857602 and sum(exact)==36472996377170786402,'Integer endpoint/sum differs')
    require(all(Fraction(b,a)==3 for a,b in zip(exact,exact[1:])),'Common ratio differs')
    return exact


def cardinal(n):
    if n<20:return SMALL[n]
    if n<100:return TENS[n//10*10]+('-'+SMALL[n%10] if n%10 else '')
    if n<1000:return SMALL[n//100]+' hundred'+(' '+cardinal(n%100) if n%100 else '')
    for scale,word in SCALES:
        if n>=scale:return cardinal(n//scale)+' '+word+(' '+cardinal(n%scale) if n%scale else '')
    raise ValueError(n)


def parse_cardinal(text):
    text=text.strip().rstrip('.').lower()
    if not re.fullmatch('[a-z]+(?:[ -][a-z]+)*',text):return None
    small={s:i for i,s in enumerate(SMALL)};tens={s:i for i,s in TENS.items()};scales={w:s for s,w in SCALES}
    def group(tokens):
        if not tokens:return 0
        if 'hundred' in tokens:
            if len(tokens)<2 or tokens[1]!='hundred' or tokens.count('hundred')!=1 or not 1<=small.get(tokens[0],-1)<=9:return None
            rest=group(tokens[2:]);return small[tokens[0]]*100+rest if rest is not None and rest<100 else None
        if len(tokens)==1:return small.get(tokens[0],tens.get(tokens[0]))
        if len(tokens)==2 and tokens[0] in tens and 1<=small.get(tokens[1],-1)<=9:return tens[tokens[0]]+small[tokens[1]]
        return None
    total=0;last=10**21;pending=[]
    for word in text.replace('-',' ').split():
        if word in scales:
            scale=scales[word];part=group(pending)
            if scale>=last or part is None or not 1<=part<1000:return None
            total+=part*scale;last=scale;pending=[]
        else:pending.append(word)
    tail=group(pending)
    if tail is None:return None
    total+=tail
    return total if cardinal(total).replace('-',' ')==text.replace('-',' ') else None


def validate_design():
    truth=values();design=json.loads((DESIGN/'math/sequence.json').read_text());script=json.loads((DESIGN/'math/speech-script.json').read_text())
    require(design['term_count']==41 and design['operation_count']==40 and len(design['terms'])==41,'Wrong scope')
    for n,row in enumerate(design['terms'],1):
        value=truth[n-1]
        require(row['n']==n and row['value']==str(value) and row['display_value']==f'{value:,}',f'Wrong exact item n{n}')
        require(parse_cardinal(row['english'])==value and row['exponent']==n-1,f'Wrong words/exponent n{n}')
        require(row['previous_value']==(str(truth[n-2]) if n>1 else None),f'Wrong input n{n}')
        require(row['exact_unit_count']==(value if n<=3 else None),f'Wrong concrete/symbolic boundary n{n}')
    require(len(script)==110 and len({r['id'] for r in script})==110,'Wrong cue IDs')
    require([r['id'] for r in script if r['kind']=='result']==[f'N{n:03}' for n in range(1,42)],'Wrong result order')
    require([r['id'] for r in script if r['kind']=='operand']==[f'E{n:03}' for n in range(2,42)],'Wrong operand order')
    completed=0
    for row in script:
        require(row['completed_terms_before']==completed,f'Wrong prior progress {row["id"]}')
        expected_delta=int(row['kind']=='result');require(row['progress_delta']==expected_delta,f'Comparison/replay counted {row["id"]}')
        if row['kind']=='result':
            n=row['term_n'];require(parse_cardinal(row['text'])==truth[n-1],f'Wrong result speech {row["id"]}')
        if row['kind']=='operand':
            n=row['term_n'];require(row['text'].lower().endswith(' times three equals.'),'Wrong multiplier speech')
            require(parse_cardinal(row['text'][:-len(' times three equals.')])==truth[n-2],f'Wrong input speech {row["id"]}')
        completed+=expected_delta;require(row['completed_terms_after']==completed,f'Wrong committed progress {row["id"]}')
    require(completed==41,'Wrong final progress')
    return truth,script,{'passed':True,'terms':41,'operations':40,'cues':110,'last':str(truth[-1]),'sum':str(sum(truth)),
                         'method':'new arbitrary-precision exponentiation, repeated three-group addition, Fraction ratios, inverse English grammar'}


def validate_schedule(plan):
    truth,script,math_report=validate_design();events=plan.get('voice_events',plan.get('events'))
    require(isinstance(events,list) and len(events)==110,'Missing 110 measured events')
    require([e['id'] for e in events]==[r['id'] for r in script],'Measured order differs')
    require(plan['fps']==30 and plan['duration_frames']==first_frame(plan['duration_s']),'Wrong frame count')
    require(480<=plan['duration_s']<1800,'Wrong long-form duration')
    previous=None;ordinary=[];equation_gaps=[];progress=0
    for event,authored in zip(events,script):
        ident=event['id'];start,end=event['start_s'],event['end_s']
        require(0<=start<end<=plan['duration_s'] and (previous is None or previous['end_s']<=start+1/RATE),f'Overlapping event {ident}')
        require(event['text']==authored['text'] and event['subtitle_text']==authored['subtitle_text'],f'Untracked script change {ident}')
        require(event['kind']==authored['kind'] and event['progress_delta']==authored['progress_delta'],f'Wrong event kind/progress {ident}')
        require(event['completed_terms_before']==progress,'Wrong before progress')
        path=path_of(event['source_path']);require(path.is_file() and sha(path)==event['source_sha256'],f'Changed source {ident}')
        with wave.open(str(path),'rb') as wav:
            duration=wav.getnframes()/wav.getframerate()
            require(wav.getnchannels()==1 and wav.getsampwidth()==2 and wav.getframerate()==24000,f'Unexpected raw format {ident}')
        require(abs(duration-(end-start))<=2/RATE and abs(duration-event['duration_s'])<=2/RATE,f'Wrong measured duration {ident}')
        if previous:
            gap=start-previous['end_s'];expected=authored['gap_before_s']
            require(abs(gap-expected)<=2/RATE,f'Wrong gap {ident}: {gap} vs {expected}')
            if event['kind']=='operand':ordinary.append({'id':ident,'previous_id':previous['id'],'gap_s':gap,'ordinary_count_boundary':previous['kind']=='result'})
            if event['kind']=='result' and event['term_n']>1:
                require(previous['id']==f'E{event["term_n"]:03}' and abs(gap-.16)<=2/RATE,'Wrong stem→result boundary')
                equation_gaps.append(gap)
        if event['kind']=='result':
            n=event['term_n'];require(str(event['value'])==str(truth[n-1]),f'Wrong measured result n{n}')
            require(abs(start-event['result_display_s']-.12)<=2/RATE,f'Wrong reveal lead n{n}')
            require(event['result_display_frame']==round(event['result_display_s']*FPS),f'Wrong quantized reveal n{n}')
            require(abs(event['progress_commit_s']-end)<=1/RATE and event['progress_commit_frame']==first_frame(end),f'Early/late progress n{n}')
        if event['kind']=='operand':require(str(event['value'])==str(truth[event['term_n']-2]),f'Wrong measured operand {ident}')
        progress+=authored['progress_delta'];require(event['completed_terms_after']==progress,'Wrong after progress');previous=event
    counts=[e for e in events if e['kind']=='result'];states=plan.get('counted_states',plan.get('states'))
    require(len(states)==41,'Missing 41 visual cycles')
    for n,(state,event) in enumerate(zip(states,counts),1):
        require(state['n']==n and str(state['value'])==str(truth[n-1]),f'Wrong state n{n}')
        require(state['result_display_frame']==event['result_display_frame'],f'State reveal mismatch n{n}')
        require(state['progress_commit_frame']==event['progress_commit_frame'],f'State progress mismatch n{n}')
    require(sum(x['ordinary_count_boundary'] for x in ordinary)==36,'Wrong ordinary boundary count')
    require(len(ordinary)==40 and len(equation_gaps)==40,'Wrong operation boundary count')
    return events,states,{'passed':True,'math':math_report,'measured_events':110,'ordinary_boundaries':ordinary,'stem_result_gaps_s':equation_gaps,
                         'duration_s':plan['duration_s'],'frames':plan['duration_frames'],'scope':'Measured schedule and source bytes; not pronunciation or encoded-media acceptance'}


def source_acceptance(plan,events):
    require(plan.get('speech_accepted') is True,'Final media requires accepted source speech')
    binding=plan['speech_acceptance'];gate_path=path_of(binding['path']);require(sha(gate_path)==binding['sha256'],'Speech gate changed')
    manifest_binding=plan['speech_manifest'];manifest_path=path_of(manifest_binding['path']);require(sha(manifest_path)==manifest_binding['sha256'],'Speech manifest changed')
    gate=json.loads(gate_path.read_text());manifest=json.loads(manifest_path.read_text())
    require(gate['accepted'] and not gate['unresolved'] and gate['source_manifest_sha256']==sha(manifest_path),'Unresolved/mismatched source acceptance')
    decisions={r['id']:r for r in gate['results']};entries={r['id']:r for r in manifest['numbers']+manifest['dialogue']}
    require(set(decisions)==set(entries)=={e['id'] for e in events},'Source gate scope differs from final110 cues')
    for e in events:
        d=decisions[e['id']];r=entries[e['id']];source=Path(r['path']);source=source if source.is_absolute() else manifest_path.parent/source
        require(d['accepted'] and d['source_sha256']==r['sha256']==e['source_sha256'],'Wrong exact source accepted')
        require(source.resolve()==path_of(e['source_path']).resolve(),'Accepted source points to different WAV')
        require(r['spoken_text']==e['text'],'Accepted spoken words differ')
    return {'passed':True,'gate':{'path':str(gate_path),'sha256':sha(gate_path)},'manifest':{'path':str(manifest_path),'sha256':sha(manifest_path)},
            'accepted_exact_sources':len(entries),'scope':'Hash-bound per-source pronunciation gate coverage. Encoded AAC proof/recognition is separate.'}


@lru_cache(maxsize=80)
def font(size):return ImageFont.truetype(str(FONT),size)


@lru_cache(maxsize=2048)
def glyph_alpha(text,size,gap=14):
    if '\n' in text:
        rows=[glyph_alpha(line,size,gap) for line in text.split('\n')];bs=[im.point(lambda a:255 if a>=128 else 0).getbbox() for im in rows]
        width=max(b[2]-b[0] for b in bs);height=sum(b[3]-b[1] for b in bs)+gap*(len(bs)-1)
        out=Image.new('L',(width+80,height+80));y=40
        for im,b in zip(rows,bs):
            out.paste(im.crop(b),(40+round((width-b[2]+b[0])/2),y));y+=b[3]-b[1]+gap
        return out
    f=font(size);b=f.getbbox(text);out=Image.new('L',(b[2]-b[0]+80,b[3]-b[1]+80))
    ImageDraw.Draw(out).text((40-b[0],40-b[1]),text,font=f,fill=255);return out


@lru_cache(maxsize=4096)
def expected_geometry(text,size,box,gap=14):
    alpha=glyph_alpha(text,size,gap);b=alpha.point(lambda a:255 if a>=128 else 0).getbbox();require(b,'Empty expected glyph')
    xy=(round((box[0]+box[2]-b[0]-b[2])/2),round((box[1]+box[3]-b[1]-b[3])/2))
    return alpha,xy,(b[0]+xy[0],b[1]+xy[1],b[2]+xy[0],b[3]+xy[1])


@lru_cache(maxsize=3)
def backdrop(divisor=1):return Image.open(BG).convert('RGB').resize((1920//divisor,1080//divisor),Image.Resampling.LANCZOS)


@lru_cache(maxsize=64)
def scene_plate(mode,cue,n,stage,divisor=1):
    """Independent opaque teaching surfaces beneath the measured glyphs."""
    im=backdrop().copy();d=ImageDraw.Draw(im)
    def panel(box,fill):d.rounded_rectangle(box,radius=35,fill=fill,outline='#d5bbaa',width=2)
    def arrow(a,b,color=TEAL,width=6):
        d.line((a,b),fill=color,width=width);angle=math.atan2(b[1]-a[1],b[0]-a[0]);length=17
        d.polygon([b,(b[0]-length*math.cos(angle-.5),b[1]-length*math.sin(angle-.5)),(b[0]-length*math.cos(angle+.5),b[1]-length*math.sin(angle+.5))],fill=color)
    colors=['#fff1e8','#edf5ee','#f4edf7']
    if mode=='exact':
        for x,color in zip((510,960,1410),colors):panel((x-175,388,x+175,650),color)
    elif mode=='loop':
        panel((320,260,800,402),'#fff7eb');d.ellipse((870,245,1050,425),fill='#edf5ee',outline=TEAL,width=3)
        for x,color in zip((510,960,1410),colors):panel((x-195,475,x+195,615),color)
        arrow((810,335),(855,335))
        for x,color in zip((510,960,1410),['#e69a83','#83b8ad','#b6a1ca']):arrow((960,432),(x,463),color,5)
        d.line([(510,625),(510,649),(1410,649),(1410,625)],fill=TEAL,width=5);arrow((960,625),(960,664))
        d.line([(290,745),(233,745),(233,335),(304,335)],fill=TEAL,width=5);arrow((267,335),(304,335))
    elif mode=='wide' and stage!='result':
        for x,color in zip((460,960,1460),colors):panel((x-218,545,x+218,712),color)
    elif mode=='general':
        for box in ((540,250,1770,470),(540,510,1770,750),(145,450,475,665)):panel(box,'#fffaf0')
    elif mode=='transition':
        if cue=='D005':panel((610,300,1310,720),'#edf5ee')
        elif cue=='D006':
            for x,color in zip((510,960,1410),colors):panel((x-175,350,x+175,640),color)
    elif mode=='feedback':
        target=(510,284,500,145) if n<=3 else (560,356,500,145) if n<=32 else (780,280,1300,145)
        x,y,w,h=target;panel((x-w/2,y-h/2,x+w/2,y+h/2),'#fff7eb')
    if divisor!=1:im=im.resize((1920//divisor,1080//divisor),Image.Resampling.BOX)
    return im


def current_plate(divisor=1):
    if CURRENT_SCENE is None:return backdrop(divisor)
    s=CURRENT_SCENE
    return scene_plate(s['mode'],s['cue'],s['n'],s['stage'],divisor)


def rgb(color):return tuple(bytes.fromhex(color.lstrip('#'))) if isinstance(color,str) else tuple(color[:3])


def color_mask(image,color,tolerance=105):
    target=rgb(color);channels=[c.point(lambda v,t=t:255 if abs(v-t)<=tolerance else 0) for c,t in zip(image.split()[:3],target)]
    return ImageChops.darker(ImageChops.darker(channels[0],channels[1]),channels[2])


def observed_ink(image,area,colors,fill=None,divisor=1):
    scaled=tuple(v//divisor for v in area);crop=image.crop(scaled).convert('RGB')
    plate=Image.new('RGB',crop.size,fill) if fill else current_plate(divisor).crop(scaled)
    changed=ImageChops.difference(crop,plate).split();changed=ImageChops.lighter(ImageChops.lighter(changed[0],changed[1]),changed[2]).point(lambda v:255 if v>=24 else 0)
    result=Image.new('L',crop.size)
    for color in colors:
        fg=rgb(color);channel=max(range(3),key=lambda k:abs(ImageStat.Stat(plate).mean[k]-fg[k]))
        observed=crop.getchannel(channel);base=plate.getchannel(channel);midpoint=base.point(lambda v,t=fg[channel]:(v+t)//2)
        half=ImageChops.subtract(observed,midpoint).point(lambda v:255 if v==0 else 0) if ImageStat.Stat(base).mean[0]>=fg[channel] else ImageChops.subtract(midpoint,observed).point(lambda v:255 if v==0 else 0)
        result=ImageChops.lighter(result,ImageChops.darker(half,color_mask(crop,fg)))
    return ImageChops.darker(result,changed)


def iou(a,b):
    union=ImageChops.lighter(a,b).histogram()[255]
    return ImageChops.darker(a,b).histogram()[255]/union if union else 0


def text_contract(component):
    if not component.get('text'):return None
    size=component.get('font_size_px',component.get('size'))
    if not size:return None
    return {'name':component['component_id'],'text':component['text'],'size':int(size),
            'box':component.get('content_box_xyxy',component.get('box')),'gap':component.get('line_gap_px',14),
            'colors':[component.get('color',INK)] if component.get('color') else [INK,TEAL,MUTED,CORAL],
            'fill':component.get('fill'),'opacity':component.get('opacity',1)}


def inspect_text(image,row,frame,divisor=1,alignment=True):
    text,size,box=row['text'],row['size'],tuple(row['box']);alpha,xy,bounds=expected_geometry(text,size,box,row.get('gap',14))
    guard=6;area=(max(0,(bounds[0]-guard)//divisor*divisor),max(0,(bounds[1]-guard)//divisor*divisor),min(1920,math.ceil((bounds[2]+guard)/divisor)*divisor),min(1080,math.ceil((bounds[3]+guard)/divisor)*divisor))
    expected=Image.new('L',(area[2]-area[0],area[3]-area[1]));expected.paste(alpha,(xy[0]-area[0],xy[1]-area[1]));native=expected
    if divisor!=1:expected=expected.resize((expected.width//divisor,expected.height//divisor),Image.Resampling.BOX)
    expected=expected.point(lambda a:255 if a>=128 else 0);actual=observed_ink(image,area,row['colors'],row.get('fill'),divisor)
    score=iou(actual,expected);minimum=.92 if divisor==1 else .82;shift=(0,0)
    if score<minimum:
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                if not(dx or dy):continue
                test=ImageChops.offset(native,dx,dy)
                if divisor!=1:test=test.resize((test.width//divisor,test.height//divisor),Image.Resampling.BOX)
                test=test.point(lambda a:255 if a>=128 else 0);candidate=iou(actual,test)
                if candidate>score:score=candidate;expected=test;shift=(dx,dy)
    result={'frame':frame,'component_id':row['name'],'text':text,'size':size,'content_box_xyxy':list(box),'observation_box_xyxy':list(area),
            'divisor':divisor,'glyph_iou':score,'minimum_iou':minimum,'identity_registration_shift_native_px':list(shift),'passed':bool(actual.getbbox()) and score>=minimum}
    if divisor==1 and alignment:
        try:result['alignment']=raster_centering_report(actual,box,origin_xy=area[:2],name=f'{frame}/{row["name"]}',tolerance_px=1)
        except ValueError as exc:result['alignment']={'passed':False,'error':str(exc)}
        result['passed'] &= result['alignment']['passed']
    if divisor==1 and '\n' not in text:
        face=font(size);fb=face.getbbox(text);origin=(xy[0]+40-fb[0]+shift[0],xy[1]+40-fb[1]+shift[1]);digits=[]
        for k,ch in enumerate(text):
            if not ch.isdigit():continue
            b=face.getbbox(ch);advance=face.getlength(text[:k]);crop=(math.floor(origin[0]+advance+b[0]-1)-area[0],math.floor(origin[1]+b[1]-1)-area[1],math.ceil(origin[0]+advance+b[2]+1)-area[0],math.ceil(origin[1]+b[3]+1)-area[1])
            value=iou(actual.crop(crop),expected.crop(crop));digits.append({'position':k,'digit':ch,'iou':value,'passed':value>=.88})
        result['digits']=digits;result['passed'] &= all(x['passed'] for x in digits)
    return result


def jsonl(path):
    opener=gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt') as stream:
        for line in stream:
            if line.strip():yield json.loads(line)


def decoded_frames(video,ffmpeg,log,divisor=2,indices=None):
    width,height=1920//divisor,1080//divisor;filters=[]
    if indices is not None:
        def combine(terms):
            if len(terms)==1:return terms[0]
            middle=len(terms)//2;return f'({combine(terms[:middle])}+{combine(terms[middle:])})'
        filters.append('select='+combine([f'eq(n\\,{i})' for i in indices]))
    if divisor!=1:filters.append(f'scale={width}:{height}:flags=area:in_color_matrix=bt709')
    filters.append('format=rgb24')
    command=[str(ffmpeg),'-nostdin','-v','error','-xerror','-i',str(video),'-an','-vf',','.join(filters),'-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24','pipe:1']
    with Path(log).open('x') as errors,subprocess.Popen(command,stdout=subprocess.PIPE,stderr=errors) as process:
        for index in (indices if indices is not None else range(10000000)):
            raw=process.stdout.read(width*height*3)
            if not raw and indices is None:break
            require(len(raw)==width*height*3,f'Short decode at frame{index}')
            yield index,Image.frombytes('RGB',(width,height),raw)
        require(not process.stdout.read(1),'Extra frames after selected decode');require(process.wait()==0,'Decode failed')


def inspect_compound(image,component,frame,divisor=1,inspect_parts=True,alpha_overlap=False):
    """Measure a grouped formula, then its separately rasterized glyph parts."""
    parts=component.get('parts',[]);require(parts,'Missing formula part contract')
    boxes=[p.get('visible_box_xyxy',p.get('box')) for p in parts]
    primitive_boxes=[p.get('visible_box_xyxy',p.get('box')) for p in component.get('primitives',[])]
    all_boxes=boxes+primitive_boxes
    left=min(b[0] for b in all_boxes);top=min(b[1] for b in all_boxes);right=max(b[2] for b in all_boxes);bottom=max(b[3] for b in all_boxes)
    area=(max(0,math.floor((left-6)/divisor)*divisor),max(0,math.floor((top-6)/divisor)*divisor),min(1920,math.ceil((right+6)/divisor)*divisor),min(1080,math.ceil((bottom+6)/divisor)*divisor))
    expected=Image.new('L',(area[2]-area[0],area[3]-area[1]));colors=[];part_results=[]
    for part,box in zip(parts,boxes):
        size=part.get('font_size_px',part.get('size'));text=part['text'];alpha,xy,_=expected_geometry(text,int(size),tuple(box))
        part_mask=Image.new('L',expected.size);part_mask.paste(alpha,(xy[0]-area[0],xy[1]-area[1]));expected=(ImageChops.screen if alpha_overlap else ImageChops.lighter)(expected,part_mask)
        colors.append(part.get('color',INK))
        row={'name':component['component_id']+'/'+part.get('role',text),'text':text,'size':size,'box':box,'colors':[part.get('color',INK)],'fill':component.get('fill')}
        if divisor==1 and inspect_parts:
            # This declared box is a glyph placement rectangle, not a parent
            # content container with padding; containment belongs to the group.
            part_results.append(inspect_text(image,row,frame,1,False))
    for primitive,box in zip(component.get('primitives',[]),primitive_boxes):
        require(primitive['kind']=='rounded_rectangle','Unknown graphic primitive')
        draw_box=primitive.get('draw_box_xyxy',box)
        local_box=tuple(v-area[i%2] for i,v in enumerate(draw_box));ImageDraw.Draw(expected).rounded_rectangle(local_box,radius=primitive.get('radius',4),outline=255,width=primitive.get('width',2))
        colors.append(primitive.get('outline',TEAL))
    if divisor!=1:expected=expected.resize((expected.width//divisor,expected.height//divisor),Image.Resampling.BOX)
    expected=expected.point(lambda a:255 if a>=128 else 0);actual=observed_ink(image,area,colors,component.get('fill'),divisor)
    score=iou(actual,expected);minimum=.90 if divisor==1 else .80
    report={'frame':frame,'component_id':component['component_id'],'kind':'compound-formula','glyph_iou':score,'minimum_iou':minimum,'parts':part_results,'passed':score>=minimum and all(p['passed'] for p in part_results)}
    if divisor==1 and not component.get('contact_group'):
        try:report['alignment']=raster_centering_report(actual,component['content_box_xyxy'],origin_xy=area[:2],name=f'{frame}/{component["component_id"]}',tolerance_px=1)
        except ValueError as exc:report['alignment']={'passed':False,'error':str(exc)}
        report['passed'] &= report['alignment']['passed']
    elif divisor==1:
        # Contact groups deliberately combine components with different target
        # centers. Compare the aggregate visible pattern at its authored pixel
        # position instead of inventing a new centered content box.
        a=actual.getbbox();b=expected.getbbox()
        dx=((a[0]+a[2])-(b[0]+b[2]))/2 if a and b else None;dy=((a[1]+a[3])-(b[1]+b[3]))/2 if a and b else None
        report['contact_pattern_translation']={'dx':dx,'dy':dy,'tolerance_px':1,'passed':dx is not None and abs(dx)<=1 and abs(dy)<=1}
        report['passed'] &= report['contact_pattern_translation']['passed']
    return report


def connected_components(mask,min_pixels=12):
    work=mask.copy();areas=[]
    while (b:=work.getbbox()) is not None:
        y=b[1];x=next(x for x in range(b[0],b[2]) if work.getpixel((x,y)))
        before=work.histogram()[255];ImageDraw.floodfill(work,(x,y),0);area=before-work.histogram()[255]
        if area>=min_pixels:areas.append(area)
    return len(areas),areas


def inspect_units(image,component,expected_count,frame):
    box=component['content_box_xyxy'];guard=8
    area=(max(0,math.floor(box[0])-guard),max(0,math.floor(box[1])-guard),min(1920,math.ceil(box[2])+guard),min(1080,math.ceil(box[3])+guard))
    # The outline of a bead is warm dark brown; the pale rectangular vessel is
    # excluded by this foreground extraction rather than counted as one unit.
    mask=observed_ink(image,area,[INK],component.get('fill'))
    mask=mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    count,areas=connected_components(mask)
    try:alignment=raster_centering_report(mask,box,origin_xy=area[:2],name=f'{frame}/{component["component_id"]}',tolerance_px=1)
    except ValueError as exc:alignment={'passed':False,'error':str(exc)}
    return {'frame':frame,'component_id':component['component_id'],'expected_units':expected_count,'actual_units':count,'unit_areas_px2':areas,
            'measurement_mask_only_closure_px':3,'source_pixels_changed':False,'alignment':alignment,'passed':count==expected_count and alignment['passed']}


def independent_state(plan,events,frame):
    """Query the accepted clock by activation points, not renderer state code."""
    activation=[e['result_display_frame'] if e['kind']=='result' else round(e['start_s']*FPS) for e in events]
    index=max(0,bisect_right(activation,frame)-1);e=events[index];following=events[index+1] if index+1<len(events) else None
    completed=sum(x['progress_commit_frame']<=frame for x in events if x['kind']=='result');t=frame/FPS
    n=e.get('term_n') or e.get('current_index',0);mode=None;tick=0
    if e['kind']=='dialogue':
        ident=int(e['id'][1:]);mode='intro' if ident<=3 else 'transition' if ident<=6 else 'general' if ident<=11 else 'compare' if ident<=18 else 'half' if ident<=25 else 'outro'
        stage=e['id']
    else:
        mode='seed' if n==1 else 'exact' if n<=3 else 'loop' if n<=32 else 'wide';stage='result' if e['kind']=='result' else 'forming'
        if e['kind']=='result' and following and following['kind']=='operand' and t>=e['end_s']+.30:
            mode='feedback';stage='return';n=following['term_n']
    fade=round(255*(1-max(0,min(1,frame/17)))) if frame<18 else 0
    if frame>=plan['duration_frames']-36:fade=max(fade,round(255*max(0,min(1,(frame-(plan['duration_frames']-36))/35))))
    return {'mode':mode,'cue':e['id'],'n':n,'stage':stage,'completed':completed,'fade':fade}


def binding_errors(report,expected):
    errors=[];state=report['state'];truth=values();mode=expected['mode'];n=expected['n'];ready=expected['stage']=='result'
    for key in ('mode','cue','n','stage','completed','fade'):
        if state.get(key)!=expected[key]:errors.append(f'{key}: observed-log {state.get(key)!r} vs accepted-clock {expected[key]!r}')
    def check(component,wanted):
        if component.get('text')!=wanted:errors.append(f'{component["component_id"]}: {component.get("text")!r} vs independent {wanted!r}')
    for c in report['components']:
        name=c['component_id']
        if name=='main-progress-counter':check(c,f'{expected["completed"]} / 41 completed')
        if mode in {'seed','exact','loop','wide'}:
            value=truth[n-1];previous=truth[n-2] if n>1 else None
            if name=='result':check(c,(str(value) if mode in {'seed','exact'} else f'{value:,}') if ready or mode=='seed' else '?')
            if name=='equation-result':check(c,str(value) if ready else '?')
            if name=='operand-value':check(c,str(previous) if mode=='exact' else f'{previous:,}')
            if re.fullmatch(r'group-[123]-value',name):check(c,f'{previous:,}')
            if name=='english-reading':require(cardinal(value).replace(' ','')==c['text'].replace('\n','').replace(' ',''),'English reading differs from independent cardinal')
            if name=='fixed-multiplier':check(c,'×3')
            if name=='operator':check(c,'×3' if mode=='exact' else '×3 =')
            if c.get('exact_unit_count') is not None:
                wanted=2 if mode=='seed' else previous
                if c['exact_unit_count']!=wanted:errors.append(f'Wrong concrete quantity contract {name}')
        if mode=='feedback' and name=='returning-value':check(c,f'{truth[n-2]:,}')
        if mode=='intro':
            if name=='first-value':check(c,'2')
            if name=='ratio-value':check(c,'×3')
        if mode=='compare':
            match=re.fullmatch(r'comparison-r([23])-n([1-4])',name)
            if match:check(c,str(2*int(match[1])**(int(match[2])-1)))
            if name=='held-main-value':check(c,f'{truth[9]:,}')
        if mode=='half':
            if name=='held-main-value':check(c,f'{truth[19]:,}')
            if name=='halving-path':
                parts=c['text'].split('   →   ');wanted=['16','8','4','2','1','1/2'][:len(parts)]
                if parts!=wanted:errors.append('Incorrect halving sequence')
        if mode=='transition' and name=='pending-equation':check(c,'18 × 3 = ?')
        if mode=='outro' and name=='last-value':check(c,f'{truth[-1]:,}')
    if mode=='general':
        notes=report.get('notes',{})
        if notes.get('main_index',4)!=4 or notes.get('progress_delta',0)!=0:errors.append('General replay changes main progress')
    return errors


def measured_text_objects(report):
    """Merge overlapping equal-value copies into their observable union."""
    components=report['components'];groups=[c for c in components if re.fullmatch(r'group-[123]-value',c['component_id'])]
    if len(groups)>1 and not report.get('data',{}).get('groups_complete',True):
        boxes=[c['content_box_xyxy'] for c in groups];box=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
        merged={'component_id':'moving-equal-value-groups-union','content_box_xyxy':box,
                'parts':[{'text':c['text'],'font_size_px':c['font_size_px'],'color':c.get('color',INK),'visible_box_xyxy':c['visible_box_xyxy']} for c in groups],
                'overlapping_copies':True}
        return [c for c in components if c not in groups]+[merged]
    if report['state']['mode']!='general':return components
    eligible=[];other=[]
    for c in components:
        row=text_contract(c)
        if c.get('parts') or row:
            if c.get('parts'):
                bs=[p['visible_box_xyxy'] for p in c['parts']]+[p['visible_box_xyxy'] for p in c.get('primitives',[])]
                b=(min(x[0] for x in bs),min(x[1] for x in bs),max(x[2] for x in bs),max(x[3] for x in bs))
            else:_,_,b=expected_geometry(row['text'],row['size'],tuple(row['box']),row.get('gap',14))
            eligible.append((c,b))
        else:other.append(c)
    clusters=[]
    for item in eligible:
        c,b=item;matches=[]
        for i,cluster in enumerate(clusters):
            if any(max(b[0]-6,bb[0]-6)<min(b[2]+6,bb[2]+6) and max(b[1]-6,bb[1]-6)<min(b[3]+6,bb[3]+6) for _,bb in cluster):matches.append(i)
        if not matches:clusters.append([item])
        else:
            combined=[item]
            for i in reversed(matches):combined+=clusters.pop(i)
            clusters.append(combined)
    output=other[:]
    for cluster in clusters:
        if len(cluster)==1:output.append(cluster[0][0]);continue
        parts=[];primitives=[]
        for c,b in cluster:
            if c.get('parts'):parts.extend(c['parts']);primitives.extend(c.get('primitives',[]))
            else:parts.append({'text':c['text'],'font_size_px':c['font_size_px'],'color':c.get('color',INK),'visible_box_xyxy':b})
        boxes=[c['content_box_xyxy'] for c,_ in cluster]
        output.append({'component_id':'contact-group/'+'+'.join(c['component_id'] for c,_ in cluster),'parts':parts,'primitives':primitives,
                       'content_box_xyxy':[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)],
                       'overlapping_copies':True,'contact_group':True})
    return output


def native_indices(plan,events,frame_rows,preview=False):
    indices=set();why={}
    episode_to_video={row.get('episode_frame',i):i for i,row in enumerate(frame_rows)}
    def add(frame,reason):
        if 0<=frame<plan['duration_frames'] and frame in episode_to_video:
            actual=episode_to_video[frame];indices.add(actual);why.setdefault(actual,set()).add(reason)
    for e in events:
        for name,at in [('voice-start',round(e['start_s']*FPS)),('voice-end',first_frame(e['end_s']))]:
            for delta in (-1,0,1):add(at+delta,e['id']+'/'+name)
        add(round((e['start_s']+e['end_s'])/2*FPS),e['id']+'/midpoint')
        if e['kind']=='result':
            for name,at in [('reveal',e['result_display_frame']),('commit',e['progress_commit_frame'])]:
                for delta in (-1,0,1):add(at+delta,e['id']+'/'+name)
    actor_seen=set();previous=None
    for frame,row in enumerate(frame_rows):
        episode_frame=row.get('episode_frame',frame)
        s=row.get('state',row);actor=s.get('actor',{});pose=(s.get('mode'),actor.get('state'),actor.get('phase'),actor.get('gaze'))
        if pose not in actor_seen:
            actor_seen.add(pose);add(episode_frame,'first actor state/scale-mode')
        if s.get('n') in (2,3,4,32,33,41) and s.get('stage') in ('forming','return') and (previous is None or row['state_key']!=previous['state_key']):
            add(episode_frame,'representative entire transition ticks')
        if previous is None or s.get('mode')!=previous.get('state',previous).get('mode'):
            for delta in (-1,0,1):add(episode_frame+delta,'mode change')
        previous=row
    for frame in range(18):add(frame,'fade in')
    for frame in range(plan['duration_frames']-36,plan['duration_frames']):add(frame,'fade out')
    return sorted(indices),why


def actor_contract(state):
    mode=state['mode'];cue=state['cue']
    contracts={'intro':(300,(960,1050)),'seed':(280,(1470,1040)),'exact':(260,(1650,1040)),
               'loop':(220,(1720,1045)),'wide':(220,(960,1060)),'feedback':(220,(1720,1045)),
               'transition':(260,(1620,1040)),'general':(300,(335,1040)),'compare':(250,(1720,1045)),
               'half':(260,(1570,1040)),'outro':(280,(960,1050))}
    if cue in ('D018','D024','D025'):return 260,(1570,1040)
    return contracts[mode]


@lru_cache(maxsize=256)
def native_actor(path,file_hash,pixel_hash,height):
    path=path_of(path);require(sha(path)==file_hash,'Changed final native actor PNG')
    native=Image.open(path).convert('RGBA');require(hashlib.sha256(native.tobytes()).hexdigest()==pixel_hash,'Actor pixel digest differs')
    if str(path) not in ACTOR_SOURCE_OBSERVATIONS:
        canonical=Image.open(ROOT/'assets/library/characters/rabbit-beret/eyecatches/v001/source-sheets/identity-reference-crop.png').convert('RGBA')
        fixture=Image.new('RGBA',(800,800));fixture.alpha_composite(canonical,(210,100))
        mask=fixture.getchannel('A').point(lambda a:255 if a==255 else 0).filter(ImageFilter.MinFilter(7))
        head=Image.new('L',(800,800));ImageDraw.Draw(head).rectangle((210,100,561,479),fill=255);mask=ImageChops.darker(mask,head)
        for b in ((277,326,352,416),(390,326,465,416)):ImageDraw.Draw(mask).rectangle(b,fill=0)
        diff=ImageChops.difference(native,fixture);maximum=max(ImageStat.Stat(diff,mask).extrema[i][1] for i in range(4))
        feet_equal=native.crop((210,615,562,685)).tobytes()==fixture.crop((210,615,562,685)).tobytes()
        require(maximum==0 and feet_equal,f'Unintended native head/feet change {path}: {maximum}, {feet_equal}')
        ACTOR_SOURCE_OBSERVATIONS[str(path)]={'source_sha256':file_hash,'fixed_head_core_max_rgba_error':maximum,'fixed_feet_all_pixels_identical':feet_equal,'passed':True}
    scale=height/585;image=native.convert('RGBa').resize((round(native.width*scale),round(native.height*scale)),Image.Resampling.LANCZOS).convert('RGBA')
    return image,scale


@lru_cache(maxsize=512)
def _actor_fixture(path,file_hash,pixel_hash,height,foot,divisor):
    image,scale=native_actor(path,file_hash,pixel_hash,height)
    xy=(round(foot[0]-370*scale),round(foot[1]-680*scale));b=image.getchannel('A').point(lambda a:255 if a>=8 else 0).getbbox()
    area=(max(0,math.floor((xy[0]+b[0]-24)/divisor)*divisor),max(0,math.floor((xy[1]+b[1]-24)/divisor)*divisor),min(1920,math.ceil((xy[0]+b[2]+24)/divisor)*divisor),min(1080,math.ceil((xy[1]+b[3]+24)/divisor)*divisor))
    layer=Image.new('RGBA',(area[2]-area[0],area[3]-area[1]));layer.alpha_composite(image,(xy[0]-area[0],xy[1]-area[1]))
    expected=Image.alpha_composite(backdrop().crop(area).convert('RGBA'),layer).convert('RGB');mask=layer.getchannel('A')
    if divisor!=1:
        expected=expected.resize((expected.width//divisor,expected.height//divisor),Image.Resampling.BOX);mask=mask.resize(expected.size,Image.Resampling.BOX)
    opaque=mask.point(lambda a:255 if a>=220 else 0);halo=mask.filter(ImageFilter.MaxFilter(25 if divisor==2 else 49)).point(lambda a:255 if a>=8 else 0)
    return expected,mask,area,layer,xy,scale,opaque,halo


def actor_fixture(component,state,divisor=1):
    height,foot=actor_contract(state)
    require(component['body_height_px']==height and component['target_anchor_px']==list(foot),'Actor authored scene height/foot differs')
    require(component['native_reference_height_px']==585 and component['native_anchor_px']==[370.,680.],'Actor registration basis changed')
    image,scale=native_actor(component['native_sprite_path'],component['native_file_sha256'],component['native_pixel_sha256'],height)
    require(hashlib.sha256(image.tobytes()).hexdigest()==component['sprite_pixel_sha256'],'Declared scaled actor differs from native recipe output')
    return _actor_fixture(component['native_sprite_path'],component['native_file_sha256'],component['native_pixel_sha256'],height,tuple(foot),divisor)


def inspect_actor(image,report,frame,divisor=2):
    state=report['state'];component=next(c for c in report['components'] if c['component_id']=='rabbit')
    expected,alpha,area,layer,xy,scale,opaque,halo=actor_fixture(component,state,divisor);halo=halo.copy();actual=image.crop(tuple(v//divisor for v in area))
    exclusions=[]
    for c in report['components']:
        if c is component or not c.get('visible_box_xyxy'):continue
        b=c['visible_box_xyxy'];local=[(b[i]-area[i%2])/divisor for i in range(4)]
        if max(0,local[0])<min(actual.width,local[2]) and max(0,local[1])<min(actual.height,local[3]):
            ImageDraw.Draw(halo).rectangle((local[0]-2,local[1]-2,local[2]+2,local[3]+2),fill=0);exclusions.append(c['component_id'])
    difference=ImageChops.difference(actual,expected);foreground_error=max(ImageStat.Stat(difference,opaque).mean)
    gray=ImageChops.difference(actual.convert('L').filter(ImageFilter.GaussianBlur(.4)),expected.convert('L').filter(ImageFilter.GaussianBlur(.4)))
    bad=ImageChops.darker(gray.point(lambda v:255 if v>=24 else 0),halo);bad_count=bad.histogram()[255]
    baseline=ACTOR_BASELINES.get((component['body_height_px'],tuple(component['target_anchor_px']),component['gaze']))
    activity_error=None;activity_pixels=0
    if baseline is not None and component['state']!='neutral':
        normal,ns=native_actor(baseline['native_sprite_path'],baseline['native_file_sha256'],baseline['native_pixel_sha256'],component['body_height_px'])
        neutral=backdrop().crop(area).convert('RGBA');neutral.alpha_composite(normal,(xy[0]-area[0],xy[1]-area[1]));neutral=neutral.convert('RGB')
        if divisor!=1:neutral=neutral.resize(expected.size,Image.Resampling.BOX)
        changes=ImageChops.difference(expected,neutral).split();activity=ImageChops.lighter(ImageChops.lighter(changes[0],changes[1]),changes[2]).point(lambda v:255 if v>=16 else 0)
        activity_pixels=activity.histogram()[255]
        if activity_pixels:activity_error=ImageStat.Stat(ImageChops.difference(actual.convert('L'),expected.convert('L')),activity).mean[0]
    result={'frame':frame,'divisor':divisor,'state':component['state'],'phase':component['phase'],'gaze':component['gaze'],
            'body_height_px':component['body_height_px'],'foot':component['target_anchor_px'],'native_path':component['native_sprite_path'],
            'native_file_sha256':component['native_file_sha256'],'native_pixel_sha256':component['native_pixel_sha256'],
            'source_opaque_mean_rgb_error':foreground_error,'halo_bad_luma_pixels':bad_count,'halo_residual_threshold':24,
            'changed_gesture_pixels':activity_pixels,'changed_gesture_mean_luma_error':activity_error,
            'neighbor_teaching_exclusions':exclusions,'passed':foreground_error<=6 and bad_count<=(15 if divisor==2 else 40) and (activity_error is None or activity_error<=8),
            'scope':'Independent native PNG digest/resampling, authored scene height/foot, decoded opaque interiors plus24px halo. Not an acting-quality score.'}
    return result


def visual_checks(video,plan,events,states,ffmpeg,out,spec_path,frame_path,reports_path,preview=False):
    global CURRENT_SCENE
    out.mkdir(parents=True,exist_ok=False);require(spec_path and frame_path and reports_path,'Missing bound visual contract')
    spec=json.loads(Path(spec_path).read_text());require(spec.get('size',spec.get('size_px'))==list(SIZE) and spec['fps']==FPS,'Wrong visual spec')
    require(path_of(spec['background']['path']).resolve()==BG.resolve() and sha(BG)==spec['background']['sha256'],'Backdrop differs')
    require(sha(FONT)==spec['font']['sha256'],'Font differs')
    frames=list(jsonl(frame_path));reports={r['state_key']:r for r in jsonl(reports_path)}
    ACTOR_BASELINES.clear()
    for report in reports.values():
        for c in report['components']:
            if c['component_id']=='rabbit' and c['state']=='neutral':ACTOR_BASELINES[(c['body_height_px'],tuple(c['target_anchor_px']),c['gaze'])]=c
    require(preview or len(frames)==plan['duration_frames'],'Incomplete frame map')
    for i,row in enumerate(frames):require(row['frame']==i and (preview or row.get('episode_frame',i)==i) and row['state_key'] in reports,'Unbound/reordered frame state')
    failures=[];half_observations=0;all_semantics=0;decoded=0;excluded=[];minimum={};native=[];units=[];samples={};actor_frames=0;actor_rows=[]
    def fail(observation):
        if len(failures)<100:failures.append(observation)
    for frame,image in decoded_frames(video,ffmpeg,out/'all-frame-half-decode.log',2):
        decoded+=1;episode_frame=frames[frame].get('episode_frame',frame);expected=independent_state(plan,events,episode_frame);report=reports[frames[frame]['state_key']];CURRENT_SCENE=expected;errors=binding_errors(report,expected);all_semantics+=1
        if errors:fail({'frame':frame,'binding_errors':errors})
        actor=next((c for c in report['components'] if c['component_id']=='rabbit'),None)
        require(actor,'Missing actor component');actor_frames+=1
        if expected['fade']:excluded.append(frame);continue
        actor_row=inspect_actor(image,report,frame,2);actor_rows.append(actor_row)
        if not actor_row['passed']:fail(actor_row)
        for component in measured_text_objects(report):
            if component.get('opacity',1)<.995:continue
            row=text_contract(component)
            if row is not None:
                if not any(ch.isdigit() for ch in row['text']) and not any(x in row['name'] for x in ('english','reading','operand','result','equation')):continue
                item=inspect_text(image,row,frame,2,False)
            elif component.get('parts'):item=inspect_compound(image,component,frame,2,False,component.get('overlapping_copies',False))
            else:continue
            half_observations+=1;minimum[component['component_id']]=min(minimum.get(component['component_id'],1),item['glyph_iou'])
            if not item['passed']:fail(item)
        if frame%1500==0:print(json.dumps({'geometric_half_frame':frame,'total':plan['duration_frames'],'failures':len(failures)}),flush=True)
    require(decoded==len(frames),'All-frame decode incomplete')
    save(out/'all-frame-checkpoint.json',{'decoded_frames':decoded,'semantic_observations':all_semantics,'half_glyph_observations':half_observations,'minimum_iou':minimum,'failures':failures})
    indices,reasons=native_indices(plan,events,frames,preview);episode_to_video={row.get('episode_frame',i):i for i,row in enumerate(frames)}
    result_mids={episode_to_video[round((e['start_s']+e['end_s'])/2*FPS)]:e['term_n'] for e in events if e['kind']=='result' and round((e['start_s']+e['end_s'])/2*FPS) in episode_to_video}
    for frame,image in decoded_frames(video,ffmpeg,out/'native-samples-decode.log',1,indices):
        expected=independent_state(plan,events,frames[frame].get('episode_frame',frame));report=reports[frames[frame]['state_key']];CURRENT_SCENE=expected
        if expected['fade']:continue
        for component in measured_text_objects(report):
            if component.get('opacity',1)<.995:continue
            row=text_contract(component)
            if row:item=inspect_text(image,row,frame)
            elif component.get('parts'):item=inspect_compound(image,component,frame,1,not component.get('overlapping_copies',False),component.get('overlapping_copies',False))
            elif component.get('exact_unit_count') is not None and (report.get('data',{}).get('groups_complete',True)):
                item=inspect_units(image,component,component['exact_unit_count'],frame);units.append(item)
            else:continue
            item['reasons']=sorted(reasons.get(frame,()));native.append(item)
            if not item['passed']:fail(item)
        if frame in result_mids:
            image.save(out/f'result-n{result_mids[frame]:02d}-frame{frame:05d}.png')
            if result_mids[frame] in (2,3,41):samples[f'result-{result_mids[frame]}']=(frame,image.copy(),report)
        if expected['n']==41 and expected['stage']=='forming' and 'pending-41' not in samples:samples['pending-41']=(frame,image.copy(),report)
        if expected['mode'] in ('general','compare','half','feedback') and expected['mode'] not in samples:
            image.save(out/f'{expected["mode"]}-frame{frame:05d}.png');samples[expected['mode']]=(frame,image.copy(),report)
        actor=next(c for c in report['components'] if c['component_id']=='rabbit')
        baseline=ACTOR_BASELINES.get((actor['body_height_px'],tuple(actor['target_anchor_px']),actor['gaze']))
        if 'gesture' not in samples and actor['state'] in ('wave','operate','present','wonder') and .25<=actor['phase']<=.75 and baseline is not None:
            samples['gesture']=(frame,image.copy(),report,baseline)
    save(out/'native-observations.json',native);save(out/'unit-counts.json',units)
    with gzip.open(out/'all-frame-actor-observations.jsonl.gz','wt') as stream:
        for item in actor_rows:stream.write(json.dumps(item,ensure_ascii=False)+'\n')
    save(out/'native-actor-source-invariants.json',ACTOR_SOURCE_OBSERVATIONS)
    # Same measurement functions must reject concrete corruptions of encoded
    # frames, so whole-line similarity cannot hide a wrong twentieth digit.
    controls=[]
    frame,actual,report=samples['result-41'];component=next(c for c in report['components'] if c['component_id']=='result');row=text_contract(component)
    alpha,xy,_=expected_geometry(row['text'],row['size'],tuple(row['box']));face=font(row['size']);fb=face.getbbox(row['text']);origin=(xy[0]+40-fb[0],xy[1]+40-fb[1]);advance=face.getlength(row['text'][:-1]);db=face.getbbox(row['text'][-1]);area=(math.floor(origin[0]+advance+db[0]-2),math.floor(origin[1]+db[1]-2),math.ceil(origin[0]+advance+db[2]+2),math.ceil(origin[1]+db[3]+2))
    bad=actual.copy();bad.paste(backdrop().crop(area),area[:2]);ImageDraw.Draw(bad).text((origin[0]+advance,origin[1]),'3',font=face,fill=TEAL);item=inspect_text(bad,row,frame);controls.append({'kind':'final digit2 changed to3','rejected':not item['passed'],'observation':item});bad.save(out/'negative-wrong-final-digit.png')
    pframe,pending,preport=samples['pending-41'];pc=next(c for c in preport['components'] if c['component_id']=='result');pr=text_contract(pc);box=tuple(map(round,row['box']));bad=pending.copy();bad.paste(actual.crop(box),box[:2]);item=inspect_text(bad,pr,pframe);controls.append({'kind':'premature final result instead of pending question','rejected':not item['passed'],'observation':item})
    frame,concrete,creport=samples['result-3'];CURRENT_SCENE=creport['state'];unit=next(c for c in creport['components'] if c.get('exact_unit_count')==6)
    box=unit['content_box_xyxy'];area=(max(0,math.floor(box[0])-8),max(0,math.floor(box[1])-8),min(1920,math.ceil(box[2])+8),min(1080,math.ceil(box[3])+8))
    mask=observed_ink(concrete,area,[INK],unit.get('fill'));work=mask.copy();hole=None
    while (b:=work.getbbox()) is not None:
        y=b[1];x=next(x for x in range(b[0],b[2]) if work.getpixel((x,y)));before=work.copy();ImageDraw.floodfill(work,(x,y),0);component_mask=ImageChops.subtract(before,work)
        if component_mask.histogram()[255]>=12:hole=component_mask.getbbox();break
    require(hole,'No concrete unit for negative control');patch=(area[0]+hole[0]-2,area[1]+hole[1]-2,area[0]+hole[2]+2,area[1]+hole[3]+2)
    bad=concrete.copy();bad.paste(current_plate().crop(patch),patch[:2]);item=inspect_units(bad,unit,6,frame)
    controls.append({'kind':'remove one of six actual beads','rejected':not item['passed'],'observation':item});bad.save(out/'negative-missing-one-bead.png')
    require('gesture' in samples,'No active gesture with a matched neutral baseline')
    frame,gesture,greport,baseline=samples['gesture'];CURRENT_SCENE=greport['state'];actor=next(c for c in greport['components'] if c['component_id']=='rabbit')
    expected,alpha,area,layer,xy,scale,opaque,halo=actor_fixture(actor,greport['state'],1)
    normal,_=native_actor(baseline['native_sprite_path'],baseline['native_file_sha256'],baseline['native_pixel_sha256'],actor['body_height_px'])
    neutral=backdrop().convert('RGBA');neutral.alpha_composite(normal,xy)
    nb=normal.getchannel('A').point(lambda a:255 if a>=8 else 0).getbbox();ab=actor['visible_box_xyxy'];region=(min(ab[0],xy[0]+nb[0]),min(ab[1],xy[1]+nb[1]),max(ab[2],xy[0]+nb[2]),max(ab[3],xy[1]+nb[3]))
    frozen=gesture.copy();frozen.paste(neutral.convert('RGB').crop(region),region[:2]);item=inspect_actor(frozen,greport,frame,1)
    controls.append({'kind':'freeze active arm gesture to neutral','rejected':not item['passed'],'observation':item});frozen.save(out/'negative-frozen-arm.png')
    shifted=ImageChops.offset(layer,-14,0);outside=ImageChops.invert(opaque);head=Image.new('L',layer.size)
    ImageDraw.Draw(head).rectangle((0,0,layer.width,round(xy[1]+480*scale-area[1])),fill=255)
    shifted.putalpha(ImageChops.multiply(ImageChops.multiply(shifted.getchannel('A'),outside),head).point(lambda a:round(a*.65)))
    ghost=gesture.convert('RGBA');part=ghost.crop(area);part.alpha_composite(shifted);ghost.paste(part,area[:2]);ghost=ghost.convert('RGB');item=inspect_actor(ghost,greport,frame,1)
    controls.append({'kind':'extra partial-opacity head contour outside old opaque interior','rejected':not item['passed'],'observation':item});ghost.save(out/'negative-extra-head-contour.png')
    drift=dict(actor,target_anchor_px=[actor['target_anchor_px'][0],actor['target_anchor_px'][1]+6])
    try:actor_fixture(drift,greport['state'],1);rejected=False
    except ValueError:rejected=True
    controls.append({'kind':'internally logged foot moved6px from authored scene','rejected':rejected,'scope':'authored-coordinate fixture; not altered media'})
    require(all(c['rejected'] for c in controls),'Negative control not detected');save(out/'negative-controls.json',controls)
    return {'passed':not failures,'preview_only':preview,'complete_episode':not preview,'decoded_frames':decoded,'all_frame_semantic_observations':all_semantics,'all_frame_half_glyph_observations':half_observations,
            'native_sample_frames':len(indices),'native_component_observations':len(native),'native_digits':sum(len(x.get('digits',[])) for x in native),'native_unit_observations':len(units),
            'actor_present_frames':actor_frames,'minimum_half_iou_by_component':minimum,'excluded_normal_glyph_fade_frames':excluded,'negative_controls':controls,'failures':failures,
            'actor_identity_observations':len(actor_rows),'max_actor_opaque_rgb_error':max((x['source_opaque_mean_rgb_error'] for x in actor_rows),default=None),
            'max_actor_halo_bad_pixels':max((x['halo_bad_luma_pixels'] for x in actor_rows),default=None),
            'scope':'All frames decoded at half resolution for critical numeric/formula/English glyphs and accepted-clock state. Native event/reveal/commit/mode/representative transition and actor-state samples. Local numeric glyphs and separated bead counts. Actor motion identity/style and whole-episode listening are separate reviews.'}


def pcm16(data):
    out=array('h');out.frombytes(data)
    if sys.byteorder!='little':out.byteswap()
    return out


def waveform(reference,actual,guard=64,stride=16):
    ref=reference[::stride];energy=sum(x*x for x in ref);best=(-1,0,0)
    lags=[0]+[lag for distance in range(1,guard+1) for lag in (-distance,distance)]
    for lag in lags:
        obs=actual[guard+lag:guard+lag+len(reference):stride]
        if len(obs)!=len(ref):continue
        power=sum(x*x for x in obs)
        if power and energy:
            corr=sum(a*b for a,b in zip(ref,obs))/math.sqrt(energy*power)
            if corr>best[0]:best=corr,lag,10*math.log10(power/energy)
            if corr>=.999999:return best
    return best


def signal_stats(reference,actual):
    n=min(len(reference),len(actual));a=reference[:n];b=actual[:n]
    energy=sum(x*x for x in a);power=sum(x*x for x in b);cross=sum(x*y for x,y in zip(a,b))
    return {'samples':n,'reference_rms_dbfs':20*math.log10(math.sqrt(energy/n)/32768) if energy else -999,
            'correlation':cross/math.sqrt(energy*power) if energy and power else None,
            'gain_db':10*math.log10(power/energy) if energy and power else None}


def audio_checks(plan,events,video,master,ffmpeg,out):
    out.mkdir(parents=True,exist_ok=False);tracks={}
    for name,source in [('master',master),('final-aac',video)]:
        target=out/(name+'.wav');subprocess.run([str(ffmpeg),'-nostdin','-v','error','-xerror','-n','-i',str(source),'-map','0:a:0','-ar',str(RATE),'-ac','2','-c:a','pcm_s16le',str(target)],check=True)
        tracks[name]=target
    reports=[]
    with wave.open(str(tracks['master']),'rb') as ref,wave.open(str(tracks['final-aac']),'rb') as actual:
        require(abs(ref.getnframes()-sample(plan['duration_s']))<=2,'Wrong master length')
        require(abs(actual.getnframes()-sample(plan['duration_s']))<=2048,'Wrong AAC end')
        rows=[];silence=[];cursor=0;source_rows=[]
        for e in events:
            a,b=sample(e['start_s']),sample(e['end_s']);guard=64;ref.setpos(a);source=pcm16(ref.readframes(b-a))
            actual.setpos(max(0,a-guard));observed=pcm16(actual.readframes(b-a+2*guard));matches=[waveform(source[k::2],observed[k::2],guard) for k in (0,1)]
            require(all(m[0]>=.97 and abs(m[2])<=.35 and abs(m[1])<=48 for m in matches),f'AAC differs from master {e["id"]}: {matches}')
            windows=[]
            for channel in (0,1):
                source_channel=source[channel::2];lag=matches[channel][1]
                actual_channel=observed[channel::2][guard+lag:guard+lag+len(source_channel)]
                for name,lo,hi in [('head150ms',0,min(len(source_channel),7200)),('tail180ms',max(0,len(source_channel)-8640),len(source_channel))]:
                    item=signal_stats(source_channel[lo:hi:4],actual_channel[lo:hi:4]);item.update(channel=channel,window=name)
                    item['passed']=item['reference_rms_dbfs']<-45 or item['correlation'] is not None and item['correlation']>=.90 and abs(item['gain_db'])<=1
                    require(item['passed'],f'AAC head/tail changed {e["id"]}: {item}');windows.append(item)
            rows.append({'id':e['id'],'left':dict(zip(('correlation','lag_samples','gain_db'),matches[0])),'right':dict(zip(('correlation','lag_samples','gain_db'),matches[1])),'head_tail_windows':windows})
            # Matching an AAC to the wrong master would otherwise pass. Bind
            # every actual master cue to the exact independent source WAV too.
            raw=subprocess.check_output([str(ffmpeg),'-nostdin','-v','error','-i',str(path_of(e['source_path'])),'-ar',str(RATE),'-ac','1','-f','s16le','-'])
            original=pcm16(raw);require(abs(len(original)-(b-a))<=2,f'Resampled source length differs {e["id"]}')
            ref.setpos(max(0,a-16));master_around=pcm16(ref.readframes(len(original)+32))
            original_matches=[waveform(original,master_around[k::2],16) for k in (0,1)]
            require(all(m[0]>=.999 and abs(m[1])<=2 for m in original_matches),f'Wrong source in master {e["id"]}: {original_matches}')
            common=plan.get('master',{}).get('common_gain_db',plan.get('common_gain_db',0));mixed=e.get('mix_gain_db',0)
            mapping=plan.get('audio',{}).get('channel_mapping_gain_db',plan.get('master',{}).get('channel_mapping_gain_db'))
            expected_gain=common+mixed+(mapping if mapping is not None else 0)
            deltas=[m[2]-common-mixed for m in original_matches]
            require(all(min(abs(delta),abs(delta+10*math.log10(2)))<=.1 for delta in deltas),f'Source/master gain not authored mono-stereo mapping {e["id"]}: {deltas}')
            if mapping is not None:require(all(abs(m[2]-expected_gain)<=.1 for m in original_matches),'Wrong declared channel mapping')
            source_rows.append({'id':e['id'],'source_sha256':e['source_sha256'],'matches':original_matches,'source_mix_gain_db':mixed,'common_master_gain_db':common,'observed_channel_mapping_gain_db':deltas,'passed':True})
            lo=cursor+sample(.03) if cursor else 0;hi=a-sample(.03)
            if hi>lo:
                actual.setpos(lo);peak=max(map(abs,pcm16(actual.readframes(hi-lo))),default=0);silence.append({'start_s':lo/RATE,'end_s':hi/RATE,'peak_pcm16':peak});require(peak<=4,'Unexpected sound between voice cues')
            cursor=b
        if cursor+sample(.03)<actual.getnframes():
            actual.setpos(cursor+sample(.03));peak=max(map(abs,pcm16(actual.readframes(actual.getnframes()-actual.tell()))),default=0)
            silence.append({'start_s':(cursor+sample(.03))/RATE,'end_s':actual.getnframes()/RATE,'peak_pcm16':peak});require(peak<=4,'Unexpected tail sound')
    result={'passed':True,'method':'Every encoded AAC cue, left/right correlation/lag/gain against accepted PCM master; guarded silence peaks',
            'video_sha256':sha(video),'master_sha256':sha(master),'voice_cues':rows,'source_to_master_cues':source_rows,'silence_intervals':silence,
            'limits':'Source pronunciation and fresh ASR/CTC are separate; matching PCM cannot establish phonetic correctness.'}
    save(out/'verification.json',result);return result


def subtitle_checks(events,paths):
    wanted=[(e['text'],round(e['start_s']*1000),round(e['end_s']*1000)) for e in events];reports=[]
    def ms(s):
        h,m,tail=s.replace(',','.').split(':');return round((int(h)*3600+int(m)*60+float(tail))*1000)
    for path in paths:
        text=Path(path).read_text(encoding='utf-8-sig');blocks=re.split(r'\n\s*\n',text.strip());actual=[]
        for block in blocks:
            lines=block.splitlines();index=next((i for i,x in enumerate(lines) if '-->' in x),None)
            if index is None:continue
            a,b=lines[index].split('-->');actual.append((' '.join(lines[index+1:]),ms(a.strip()),ms(b.strip().split()[0])))
        require(len(actual)==len(wanted),f'Subtitle cue count differs {path}')
        for a,b in zip(actual,wanted):require(a[0]==b[0] and abs(a[1]-b[1])<=1 and abs(a[2]-b[2])<=1,f'Subtitle text/time differs {path}: {a} != {b}')
        reports.append({'path':str(path),'sha256':sha(path),'cues':len(actual),'passed':True})
    require(reports,'No subtitles');return {'passed':True,'files':reports}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--video',type=Path);p.add_argument('--timeline',type=Path,required=True)
    p.add_argument('--master',type=Path);p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--phase',choices=('schedule','technical','audio','visual','all'),default='all')
    p.add_argument('--visual-spec',type=Path);p.add_argument('--frame-states',type=Path);p.add_argument('--distinct-reports',type=Path)
    p.add_argument('--delivery-dir',type=Path);p.add_argument('--ffmpeg',default=str(ROOT/'.venv/bin/ffmpeg'));p.add_argument('--ffprobe',default=str(ROOT/'.venv/bin/ffprobe'))
    p.add_argument('--preview-clips',action='store_true',help='Calibrate on mapped excerpts; never accepts the whole episode')
    args=p.parse_args(argv);args.out_dir.mkdir(parents=True,exist_ok=False)
    report={'kind':'independent-geometric-final-media-verification','phase':args.phase,'passed':False,'created_at_utc':datetime.now(timezone.utc).isoformat(),'verifier_sha256':sha(__file__),'errors':[]}
    try:
        plan=json.loads(args.timeline.read_text());events,states,report['schedule']=validate_schedule(plan);report['timeline']={'path':str(args.timeline),'sha256':sha(args.timeline)}
        if args.phase!='schedule':
            require(args.video and args.video.is_file(),'No completed video');report['video']={'path':str(args.video),'sha256':sha(args.video)}
            if not args.preview_clips:report['source_acceptance']=source_acceptance(plan,events)
        if args.phase in ('technical','all'):
            report['technical']=technical.verify_video(args.video,args.out_dir/'technical',args.timeline,args.ffmpeg,args.ffprobe,duration_bounds=(480,1800))
            require(report['technical']['status']=='pass','Technical gate failed')
        if args.phase in ('audio','all'):
            require(args.master and args.master.is_file(),'No accepted master')
            report['audio']=audio_checks(plan,events,args.video,args.master,args.ffmpeg,args.out_dir/'audio')
            report['subtitles']=subtitle_checks(events,sorted((args.delivery_dir or args.video.parent).glob('*.srt')))
        if args.phase in ('visual','all'):
            report['visual']=visual_checks(args.video,plan,events,states,args.ffmpeg,args.out_dir/'visual',args.visual_spec,args.frame_states,args.distinct_reports,args.preview_clips)
            require(report['visual']['passed'],'Decoded visual checks failed')
        report['passed']=True
    except Exception as exc:report['errors'].append(f'{type(exc).__name__}: {exc}')
    report['scope']='Independent automated/sample observations only. No claim of human full-episode playback or of acceptance of unrun phases.'
    save(args.out_dir/'verification.json',report);print(json.dumps({'passed':report['passed'],'phase':args.phase,'errors':report['errors'],'report':str(args.out_dir/'verification.json')},ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
