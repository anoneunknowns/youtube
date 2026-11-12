"""Independent Catalan delivery verification from decoded pixels and integers.

No Catalan producer, renderer, formatter or animation runtime is imported.
Truth comes from binomial coefficients, an independent convolution, inverse
English cardinal parsing and separately rasterized glyphs. Audio content QA is
performed by the episode's dedicated speech audit, not inferred from pictures.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
from itertools import combinations
import shutil
import subprocess

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat, ImageMath, ImageFilter

try:
    from component_alignment import raster_centering_report
    from verify_prime_video import decoded_frames
    import verify_video as technical
except ModuleNotFoundError:
    from tools.component_alignment import raster_centering_report
    from tools.verify_prime_video import decoded_frames
    from tools import verify_video as technical

ROOT=Path(__file__).resolve().parents[1]
DESIGN=ROOT/'design/catalan-counting-v1'
FONT=ROOT/'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
FPS=30;SIZE=(1920,1080);CREAM='#fffaf0';INK='#604934';MUTED='#7a6c5e';TEAL='#408d93';CORAL='#d87d61'
EXPRESSION=(270,268,1650,342);NUMBER=(260,405,1660,505);READING=(270,724,1650,804)
BACKDROP=ROOT/'assets/library/worlds/ribbon-courtyard/backgrounds/v001/ribbon-courtyard-background.png'
BACKGROUND_FIELDS={(265,158,1655,216),(280,647,1640,721),(300,190,1620,270),(260,330,1660,400),(260,350,1660,480)}


def require(test,message):
    if not test:raise ValueError(message)


def ffbin(name):
    p=ROOT/'.venv/bin'/name
    return str(p) if p.exists() else shutil.which(name)


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def clamp(x):return min(1,max(0,x))
def smooth(x):x=clamp(x);return x*x*(3-2*x)
def frame_at(t):return math.ceil(t*FPS-1e-7)


def truths():
    direct=[math.comb(2*n,n)//(n+1) for n in range(31)];conv=[1]
    for n in range(1,31):conv.append(sum(conv[k]*conv[n-1-k] for k in range(n)))
    require(direct==conv,'Independent Catalan integer methods differ')
    require(direct[0]==direct[1]==1 and direct[-1]==3814986502092304,'Endpoint/seed invariant failed')
    return direct


ONES='zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
TENS=['','','twenty','thirty','forty','fifty','sixty','seventy','eighty','ninety']
SCALES=[(10**15,'quadrillion'),(10**12,'trillion'),(10**9,'billion'),(10**6,'million'),(1000,'thousand')]


def cardinal(n):
    if n<20:return ONES[n]
    if n<100:return TENS[n//10]+('-'+ONES[n%10] if n%10 else '')
    if n<1000:return ONES[n//100]+' hundred'+(' '+cardinal(n%100) if n%100 else '')
    for scale,word in SCALES:
        if n>=scale:return cardinal(n//scale)+' '+word+(' '+cardinal(n%scale) if n%scale else '')
    raise ValueError(n)


def inverse(text):
    small={word:n for n,word in enumerate(ONES)};small.update({word:n*10 for n,word in enumerate(TENS) if word})
    scales={word:scale for scale,word in SCALES};total=part=0;last=10**18
    for word in text.replace('-',' ').split():
        if word in small:part+=small[word]
        elif word=='hundred':part*=100
        elif word in scales:
            require(scales[word]<last and 0<part<1000,'Malformed English group '+text)
            total+=part*scales[word];part=0;last=scales[word]
        else:raise ValueError('Unknown English token '+word)
    result=total+part
    require(cardinal(result).replace('-',' ')==text.replace('-',' '),'Noncanonical cardinal '+text)
    return result


@lru_cache(maxsize=128)
def font(size):return ImageFont.truetype(str(FONT),size)


def lines(text,size,width=1360):
    out=[];current=''
    for word in text.split():
        trial=(current+' '+word).strip()
        if current and font(size).getlength(trial)>width:out.append(current);current=word
        else:current=trial
    if current:out.append(current)
    return out


def threshold(color):
    a=Image.new('RGB',(1,1),CREAM).convert('L').getpixel((0,0))
    b=Image.new('RGB',(1,1),color).convert('L').getpixel((0,0))
    return (a+b)/2


def dark(image,color,background_luma=None):
    cut=threshold(color) if background_luma is None else (background_luma+Image.new('RGB',(1,1),color).convert('L').getpixel((0,0)))/2
    return image.convert('L').point(lambda x:255 if x<cut else 0)


@lru_cache(maxsize=64)
def previous_operand_center(previous,factor,size):
    text=f'{previous:,} × {factor}';b=font(size).getbbox(text)
    full=Image.new('L',(b[2]-b[0]+80,b[3]-b[1]+80));d=ImageDraw.Draw(full)
    d.text((40-b[0],40-b[1]),text,font=font(size),fill=255)
    ink=full.point(lambda a:255 if a>=128 else 0).getbbox()
    x=round((EXPRESSION[0]+EXPRESSION[2]-ink[0]-ink[2])/2)
    y=round((EXPRESSION[1]+EXPRESSION[3]-ink[1]-ink[3])/2)
    part=Image.new('L',full.size);ImageDraw.Draw(part).text((40-b[0],40-b[1]),f'{previous:,}',font=font(size),fill=255)
    q=part.point(lambda a:255 if a>=128 else 0).getbbox()
    return x+(q[0]+q[2])/2,y+(q[1]+q[3])/2


def overlap(a,b):
    union=ImageChops.lighter(a,b).histogram()[255]
    return ImageChops.darker(a,b).histogram()[255]/union if union else 1


@lru_cache(maxsize=4096)
def reference(text,size,field,color,divisor=1,multi=False,dx=0,dy=0):
    # Independently measure actual glyph raster, never the font origin/advance.
    strings=lines(text,size) if multi else [text]
    pieces=[]
    for s in strings:
        b=font(size).getbbox(s);p=Image.new('RGBA',(b[2]-b[0]+64,b[3]-b[1]+64))
        ImageDraw.Draw(p).text((32-b[0],32-b[1]),s,font=font(size),fill=color)
        ink=p.getchannel('A').point(lambda a:255 if a>=128 else 0).getbbox();pieces.append((p,ink))
    w=max(b[2]-b[0] for p,b in pieces);h=sum(b[3]-b[1] for p,b in pieces)+10*(len(pieces)-1)
    layer=Image.new('RGBA',(w+64,h+64));y=32
    for p,b in pieces:
        layer.alpha_composite(p,(32+round((w-b[2]+b[0])/2)-b[0],y-b[1]));y+=b[3]-b[1]+10
    b=layer.getchannel('A').point(lambda a:255 if a>=128 else 0).getbbox()
    xy=(round((field[0]+field[2]-b[0]-b[2])/2),round((field[1]+field[3]-b[1]-b[3])/2))
    # Follow whole-frame downsampling grid; odd field origins retain their phase.
    origin=(math.floor(field[0]/divisor)*divisor,math.floor(field[1]/divisor)*divisor)
    right,bottom=math.floor(field[2]/divisor)*divisor,math.floor(field[3]/divisor)*divisor
    image=Image.new('RGBA',(right-origin[0],bottom-origin[1]),CREAM)
    image.alpha_composite(layer,(xy[0]-origin[0]+dx,xy[1]-origin[1]+dy))
    if divisor>1:image=image.resize((image.width//divisor,image.height//divisor),Image.Resampling.BOX)
    mask=dark(image.convert('RGB'),color)
    return mask


SELECTED_REFERENCES={}


@lru_cache(maxsize=2)
def clean_background(divisor):
    im=Image.open(BACKDROP).convert('RGB').resize(SIZE,Image.Resampling.LANCZOS)
    return im if divisor==1 else im.resize((1920//divisor,1080//divisor),Image.Resampling.BOX)


def background_foreground(crop,field,color,divisor):
    box=tuple(int(v//divisor) for v in field);base=clean_background(divisor).crop(box)
    br,bg,bb=[c.convert('F') for c in base.split()];ar,ag,ab=[c.convert('F') for c in crop.convert('RGB').split()]
    rr,gg,bl=Image.new('RGB',(1,1),color).getpixel((0,0))
    return ImageMath.lambda_eval(lambda q:(((q['br']-q['ar'])*(q['br']-rr)+(q['bg']-q['ag'])*(q['bg']-gg)+(q['bb']-q['ab'])*(q['bb']-bl)) /
        ((q['br']-rr)**2+(q['bg']-gg)**2+(q['bb']-bl)**2+1)>.5)*255,
        br=br,bg=bg,bb=bb,ar=ar,ag=ag,ab=ab).convert('L')


def glyph_check(image,field,text,size,color,divisor=1,multi=False,alignment=True):
    roi=tuple(int(x//divisor) for x in field)
    crop=image.crop(roi)
    grey=crop.convert('L');corners=sorted(grey.getpixel(p) for p in [(0,0),(grey.width-1,0),(0,grey.height-1),(grey.width-1,grey.height-1)])
    background_luma=(corners[1]+corners[2])/2
    actual=background_foreground(crop,field,color,divisor) if tuple(field) in BACKGROUND_FIELDS else dark(crop,color,background_luma)
    key=(text,size,tuple(field),color,divisor,multi)
    if key not in SELECTED_REFERENCES:
        candidates=[(overlap(actual,reference(text,size,tuple(field),color,divisor,multi,dx,dy)),dx,dy)
                    for dx in (-1,0,1) for dy in (-1,0,1)]
        _,dx,dy=max(candidates)
        SELECTED_REFERENCES[key]=(dx,dy)
    dx,dy=SELECTED_REFERENCES[key]
    expected=reference(text,size,tuple(field),color,divisor,multi,dx,dy)
    score=overlap(actual,expected)
    require(score>=.84 if divisor>1 else score>=.90,f'Glyph mismatch {text}: {score:.4f}')
    report={'text':text,'font_size_px':size,'content_box_xyxy':list(field),'mask_iou':score,'divisor':divisor}
    if alignment:
        rec=raster_centering_report(actual,tuple(v/divisor for v in field),origin_xy=(roi[0],roi[1]),
             name=text,tolerance_px=1 if divisor==1 else 1,alpha_threshold=128)
        require(rec['passed'],f'Actual decoded alignment {text}: {rec}')
        report.update(rec)
    if not multi:
        # Each numeric glyph is checked locally; a wrong middle digit cannot
        # hide in the total overlap of a long line. Alternatives are a negative
        # control using the same independently approved character cell.
        expected_bbox=expected.getbbox();b=font(size).getbbox(text)
        # Text-layer placement is derived afresh from the glyph string.
        alpha=Image.new('L',(math.ceil(font(size).getlength(text))+100,size*2+100))
        ImageDraw.Draw(alpha).text((40,30),text,font=font(size),fill=255)
        ink=alpha.point(lambda a:255 if a>=128 else 0).getbbox()
        text_origin_x=round((field[0]+field[2]-ink[0]-ink[2])/2)+40+dx
        digit_scores=[]
        for i,ch in enumerate(text):
            if not ch.isdigit():continue
            left=text_origin_x+font(size).getlength(text[:i]);right=text_origin_x+font(size).getlength(text[:i+1])
            cell=(max(0,math.floor(left/divisor)-roi[0]-1),0,min(actual.width,math.ceil(right/divisor)-roi[0]+1),actual.height)
            a=actual.crop(cell);e=expected.crop(cell);local=overlap(a,e)
            require(local>=.76 if divisor>1 else local>=.85,f'Individual digit mismatch {text} digit {i}:{ch}: {local:.4f}')
            digit_scores.append({'character_index':i,'digit':ch,'mask_iou':local})
        report['digits']=digit_scores
    return report


class Contract:
    def __init__(self,plan):
        self.plan=plan;self.values=truths();self.events=sorted(plan.get('events',plan.get('voice_events',[])),key=lambda r:r['start_s'])
        self.by={r['id']:r for r in self.events};self.starts=[r['start_s'] for r in self.events]
        self.counts=sorted(plan.get('counts',plan.get('counted_states',[])),key=lambda r:r['index'])
        self.ends=[r['voice_end_s'] for r in self.counts]
        self.frames=int(plan.get('frame_count',plan.get('duration_frames',frame_at(plan['duration_s']))))
        authored=json.loads((DESIGN/'narration.json').read_text());by_auth={r['id']:r for r in authored}
        require(len(self.events)==86 and len(self.by)==86 and set(self.by)==set(by_auth),'Missing/duplicate authored voice cue')
        require(len(self.counts)==31,'Missing counted state')
        require(480<=plan['duration_s']<1800 and self.frames==frame_at(plan['duration_s']),'Duration/frame contract failed')
        previous=0
        for e in self.events:
            require(e['text']==by_auth[e['id']]['text'],'Untracked script change '+e['id'])
            require(previous<=e['start_s']<e['end_s']<=plan['duration_s'],'Overlapping/invalid voice '+e['id']);previous=e['end_s']
        ordinary=[];lessons=[]
        for n,c in enumerate(self.counts):
            v=self.by[f'N{n:03}'];require(c['index']==n and str(c['value'])==str(self.values[n]),'Wrong count '+str(n))
            require(inverse(v['text'])==self.values[n],'Wrong spoken result '+str(n))
            commit=c.get('result_display_start_s',c.get('result_start_s'))
            require(abs(v['start_s']-commit-.12)<1/48000,'Wrong result display lead '+str(n))
            if n:
                e=self.by[f'E{n:03}'];prev=self.values[n-1];factor=4*n-2;divisor=n+1
                require(e['text'].rstrip('.')==f'{cardinal(prev)} times {cardinal(factor)}, divided by {cardinal(divisor)}, equals','Wrong formula speech '+str(n))
                require(abs(v['start_s']-e['end_s']-.16)<1/48000,'Wrong formula-result gap '+str(n))
                op=c.get('operator_timing',e.get('operator_timing',{}))
                require(e['start_s']<=op['times_start_s']<op['multiply_commit_s']<op['divided_start_s']<op['equals_start_s']<=e['end_s'],'Unordered operator CTC boundaries '+str(n))
                require(prev*factor%divisor==0 and prev*factor//divisor==self.values[n],'Noninteger/mistyped formula '+str(n))
            if n<30:
                following=self.by[f'E{n+1:03}'];between=[e for e in self.events if v['end_s']<=e['start_s']<following['start_s'] and e['id'].startswith('T')]
                if between:lessons.append({'after_n':n,'cues':[e['id'] for e in between]})
                else:require(abs(following['start_s']-v['end_s']-2)<1/48000,'Ordinary gap changed '+str(n));ordinary.append(n)
        self.schedule_report={'passed':True,'terms':31,'integer_multiply_divide_cycles':30,'spoken_events':86,'normal_two_second_boundaries':ordinary,
            'lesson_boundaries':lessons,'last_index':30,'last_value':str(self.values[-1]),'two_initial_ones_preserved':True,
            'independent_methods':['central binomial coefficient','ordered convolution','strict inverse English cardinal'],
            'operator_times':'Measured CTC absolute boundaries, validated order; speech recognizer content acceptance is a separate audit.'}

    def state(self,f):
        t=f/FPS;e=self.events[max(0,bisect_right(self.starts,t)-1)];cue=e['id'];n=int(e.get('index',0) or 0)
        for k in range(1,31):
            expr=self.by[f'E{k:03}'];v=self.by[f'N{k:03}'];c=self.counts[k]
            start=c.get('cycle_start_s',expr['start_s']-.55)
            future=[q['start_s'] for q in self.events if q['start_s']>=v['end_s'] and q['id'].startswith(('T','O'))]
            stop=min(future) if future else self.plan['duration_s']
            if k<30:stop=min(stop,self.counts[k+1].get('cycle_start_s',self.by[f'E{k+1:03}']['start_s']-.55))
            if start<=t<stop:
                op=c.get('operator_timing',expr.get('operator_timing',{}));commit=c.get('result_display_start_s',c.get('result_start_s'))
                if t<expr['start_s']:stage='relay';p=smooth((t-start)/(expr['start_s']-start))
                elif t<op['times_start_s']:stage='input';p=0
                elif t<op['multiply_commit_s']:stage='multiply';p=0
                elif t<op['divided_start_s']:stage='product';p=1
                elif t<commit:stage='divide';p=1
                else:stage='result';p=1
                return 'count',k,stage,p
        if cue=='N000' or cue in ('I04','I05'):return 'seed',0,cue,0
        if cue in ('O01','O02'):return ('history' if cue=='O01' else 'ending'),30,cue,0
        if cue.startswith('T') and cue not in ('T000a','T000b','T000c','T001a','T001b','T002a','T003a','T003b','T003c','T003d','T003e','T004a','T004b'):
            return 'milestone',n,cue,0
        return 'lesson',n,cue,0

    def fields(self,f):
        mode,n,stage,p=self.state(f);wide=n>=16;fields=[]
        if mode=='count':
            prev=self.values[n-1];value=self.values[n];factor=4*n-2;divisor=n+1;product=prev*factor
            fields.append(('general-equation','C(n) = C(n − 1) × (4n − 2) ÷ (n + 1)',44,(265,158,1655,216),MUTED,False))
            if stage=='relay':
                a=82 if n-1>=16 else 112;b=59 if wide else 76;size=round(a+(b-a)*p)
                gx,gy=previous_operand_center(prev,factor,b);cx=960+(gx-960)*p;cy=455+(gy-455)*p
                half_width=min(cx-280,1640-cx)
                fields.append(('transferred-previous',f'{prev:,}',size,(cx-half_width,cy-62,cx+half_width,cy+62),TEAL,False))
            elif stage=='result':
                fields += [('result-formula-input',f'{prev:,} × {factor} ÷ {divisor}',50 if wide else 64,EXPRESSION,MUTED,False),
                           ('committed-result',f'{value:,}',82 if wide else 112,NUMBER,TEAL,False),
                           ('result-index',f'C({n})  ·  {n} PAIRS',35,(550,591,1370,653),INK,False),
                           ('result-reading',cardinal(value),30,READING,MUTED,True)]
            else:
                expression=f'{product:,} ÷ {divisor}' if stage=='divide' else f'{prev:,} × {factor}'
                fields += [('operation-input',expression,56 if wide and stage=='divide' else 59 if wide else 76,EXPRESSION,CORAL if stage=='divide' else INK,False),
                           ('intermediate-product',f'{product:,}' if stage in ('product','divide') else '…',69 if wide else 102,NUMBER,TEAL,False),
                           ('coefficient-factor',f'4 × {n} − 2 = {factor}',23,(252,354,580,395),MUTED,False),
                           ('coefficient-divisor',f'{n} + 1 = {divisor}',23,(1345,354,1667,395),MUTED,False)]
        elif mode=='seed':fields=[('seed-value','C(0) = 1',96,(440,320,1480,428),TEAL,False)]
        elif mode=='milestone':fields=[('milestone-value',f'{self.values[n]:,}',82 if n>=16 else 112,(260,350,1660,470),TEAL,False)]
        elif mode=='history':
            for i,value in enumerate(self.values):
                col=i//11;r=i%11;x=210+col*505;y=180+r*53
                fields.append(('history-'+str(i),f'C({i}) = {value:,}',26,(x+5,y,x+490,y+40),TEAL if i in (0,1,30) else INK,False))
        elif mode=='ending':fields=[('ending-value',f'{self.values[30]:,}',82,(260,350,1660,480),TEAL,False)]
        elif mode=='lesson':
            cue=stage
            if cue=='I03':fields.append(('path-rule','1 UP + 1 DOWN = 1 PAIR',38,(350,565,1570,625),MUTED,False))
            elif cue=='I06':fields += [('route','FROM C(0) TO C(30)',65,(300,190,1620,270),TEAL,False),
                                      ('route-count','31 places  ·  each has its own value',43,(260,330,1660,400),MUTED,False)]
            elif cue.startswith('T000'):
                fields.append(('rule-formula','C(n) = C(n − 1) × (4n − 2) ÷ (n + 1)',47,(260,217,1660,298),INK,False))
                for i,(left,right,title,label,size) in enumerate([
                    (260,620,'LAST VALUE','C(n − 1)',43),
                    (700,1220,'WHOLE PRODUCT','C(n − 1) × (4n − 2)',30),
                    (1300,1660,'NEXT VALUE','C(n)',48)]):
                    fields.append(('rule-input-'+str(i),label,size,(left+15,452,right-15,513),TEAL,False))
                    fields.append(('rule-title-'+str(i),title,27,(left+12,369,right-12,415),MUTED,False))
                fields += [('rule-operation-0','× (4n − 2)',27,(450,566,870,605),TEAL,False),
                           ('rule-operation-1','÷ (n + 1)',27,(1050,566,1470,605),CORAL,False),
                           ('rule-note','VALUE WINDOWS  ·  EXACT INTEGERS',26,(320,624,1600,660),MUTED,False)]
            elif cue=='T001a':
                for i in (0,1):
                    x=350+i*650;fields += [('one-'+str(i),f'C({i}) = 1',78,(x+20,218,x+550,320),TEAL,False),
                                          ('one-index-'+str(i),'0 PAIRS' if i==0 else '1 PAIR',31,(x+20,545,x+550,595),MUTED,False)]
            elif cue in ('T001b','T002a'):
                for i in range(1 if cue=='T001b' else 2):
                    box=(420,210,1500,540) if cue=='T001b' else (260+i*760,210,900+i*760,540)
                    fields.append(('example-label-'+str(i),'1 WAY' if cue=='T001b' else f'PATH {i+1}',34,(box[0],558,box[2],605),MUTED,False))
            elif cue=='T003a':
                for i in range(5):
                    x=245+i%3*490;y=175+i//3*235;fields.append(('path-id-'+str(i),str(i+1),27,(x+25,y+168,x+425,y+202),MUTED,False))
                fields.append(('five-total','C(3) = 5',68,(1260,444,1660,585),TEAL,False))
            elif cue=='T003b':
                fields += [('inside-name','INSIDE A  ·  1 PAIR',24,(400,641,910,676),TEAL,False),
                           ('after-name','AFTER B  ·  1 PAIR',24,(1010,641,1520,676),CORAL,False)]
            elif cue in ('T003c','T003d','T003e'):
                for k,product in enumerate(['1 × 2 = 2','1 × 1 = 1','2 × 1 = 2']):
                    x=250+k*480;fields += [('group-pairs-'+str(k),f'{k} INSIDE  ·  {2-k} AFTER',25,(x+15,197,x+445,242),MUTED,False),
                                           ('group-product-'+str(k),product,39,(x+15,527,x+445,572),TEAL,False)]
                fields.append(('convolution-total','C(3) = 2 + 1 + 2 = 5',57,(280,647,1640,721),TEAL,False))
            elif cue=='T004a':
                event=self.by[cue];u=clamp((f/FPS-event['start_s'])/(event['end_s']-event['start_s']))
                fields.append(('replay-product','5 × 14 = '+('70' if u>=.24 else '…'),54,(450,200,1470,265),TEAL,False))
                label='14 groups of 5' if u<.28 else '70 units move into 5 equal shares' if u<.68 else '70 ÷ 5 = 14 in each share'
                fields.append(('replay-share-label',label,35,(300,638,1620,698),MUTED,False))
            elif cue=='T004b':fields += [('path-rule','C(3) = 2 + 1 + 2 = 5',60,(290,240,1630,320),TEAL,False),
                                        ('arithmetic-rule','C(4) = 5 × 14 ÷ 5 = 14',57,(290,390,1630,480),CORAL,False)]
        if mode=='count':
            subtitle=f'PAIR COUNT  n = {n}'
            if stage=='result':fields.append(('equals','=',44,(900,353,1020,395),MUTED,False))
            elif stage!='relay' and n>4:
                for i,(text,color) in enumerate([(f'× {4*n-2}',TEAL if stage in ('input','multiply') else MUTED),
                                                  ('WHOLE',TEAL if stage=='product' else MUTED),
                                                  (f'÷ {n+1}',CORAL if stage=='divide' else MUTED)]):
                    box=[(450,552,700,636),(835,552,1085,636),(1220,552,1470,636)][i]
                    fields.append(('flow-port-'+str(i),text,25 if i==1 else 30,(box[0]+12,box[1]+13,box[2]-12,box[3]-13),color,False))
        else:
            cue=stage
            if mode=='seed':subtitle='ZERO PAIRS  ·  ONE EMPTY PATH'
            elif mode=='milestone':subtitle=f'REPLAY C({n})  ·  COUNTING WAYS'
            elif mode=='history':subtitle='ALL31 VALUES  ·  KEEP BOTH ONES'
            elif mode=='ending':subtitle='THANKS FOR COUNTING CATALAN NUMBERS'
            elif cue.startswith('T000'):subtitle='THE EXACT EQUATION'
            elif cue=='T001a':subtitle='SAME VALUE  ·  DIFFERENT PLACES'
            elif cue in ('T001b','T002a'):subtitle=f'{1 if cue=="T001b" else 2} PAIRS'
            elif cue=='T003a':subtitle='ALL FIVE PATHS  ·  REPLAY C(3)'
            elif cue.startswith('T003'):subtitle='FIRST RETURN  ·  REPLAY C(3)'
            elif cue=='T004a':subtitle='EXACT INTEGER SHARES  ·  REPLAY C(4)'
            elif cue=='T004b':subtitle='TWO RULES  ·  SAME SEQUENCE'
            else:subtitle='RIBBON COURTYARD'
        fields.append(('subtitle','NUM-NUM NUMBERS  ·  '+subtitle,20,(380,99,1540,122),MUTED,False))
        return fields


def native_samples(c):
    out=set([0,1,9,17,18,c.frames-24,c.frames-13,c.frames-2,c.frames-1])
    for n in range(31):
        cs=c.counts[n];v=c.by[f'N{n:03}']
        for t in [cs.get('result_display_start_s',v['start_s']-.12),v['start_s'],v['end_s']]:
            f=frame_at(t);out.update(range(max(0,f-1),min(c.frames,f+2)))
        if n:
            e=c.by[f'E{n:03}'];op=cs['operator_timing']
            for t in [cs.get('cycle_start_s',e['start_s']-.55),e['start_s'],op['times_start_s'],op['multiply_commit_s'],op['divided_start_s'],op['equals_start_s']]:
                f=frame_at(t);out.update(range(max(0,f-1),min(c.frames,f+2)))
            a=frame_at(cs.get('cycle_start_s',e['start_s']-.55));b=frame_at(e['start_s'])
            out.update(range(a,b+1))
    for e in c.events:
        if not e['id'].startswith(('E','N')):
            out.update([frame_at(e['start_s']+.1),frame_at((e['start_s']+e['end_s'])/2),max(0,frame_at(e['end_s'])-1)])
    replay=c.by['T004a']
    for u in [.05,.24,.28,.45,.52,.68,.82,.95]:out.add(frame_at(replay['start_s']+u*(replay['end_s']-replay['start_s'])))
    return sorted(f for f in out if 0<=f<c.frames)


def check_progress(image,c,f,divisor):
    expected=bisect_right(c.ends,f/FPS);roi=(110//divisor,968//divisor,720//divisor,1044//divisor)
    crop=image.crop(roi);w,h=crop.size;points=[]
    # The independently known31 equally spaced dots occupy one separate row.
    # Detect components with teal contrast, not the text or parent panel.
    mask=crop.convert('RGB');pixels=mask.load();selected=[]
    for x in range(w):
        hits=0
        for y in range(h//2,h):
            r,g,b=pixels[x,y]
            if g-r>25 and b-r>25 and 60<g<180:hits+=1
        if hits:selected.append(x)
    groups=[]
    for x in selected:
        if not groups or x>groups[-1][-1]+1:groups.append([x])
        else:groups[-1].append(x)
    require(len(groups)==expected,f'Progress updated at wrong time frame{f}: {len(groups)} vs {expected}')
    text=f'{expected} / 31 VALUES';face=font(24);bb=face.getbbox(text)
    glyph=Image.new('L',(600,90));ImageDraw.Draw(glyph).text((30-bb[0],20-bb[1]),text,font=face,fill=255)
    ink=glyph.point(lambda a:255 if a>=128 else 0).getbbox();gw,gh=ink[2]-ink[0],ink[3]-ink[1]
    # Independent layout of the whole group: text above31 equally spaced
    # markers, measured together. The label's own target follows that group.
    origin_x=round((110+720-10-589)/2);origin_y=round((968+1044-4-60)/2)
    cx=origin_x+round((600-gw)/2)+gw/2;cy=origin_y+4+gh/2
    label=glyph_check(image,(cx-300,cy-20,cx+300,cy+20),text,24,MUTED,divisor,alignment=divisor==1)
    group=crop.convert('L').point(lambda v:255 if v<222 else 0)
    rec=raster_centering_report(group,tuple(v/divisor for v in (110,968,720,1044)),origin_xy=(roi[0],roi[1]),
                                name='progress whole label+31 dots',tolerance_px=1,alpha_threshold=128)
    require(rec['passed'],'Progress whole-group actual alignment differs '+str(rec))
    return {'completed':expected,'actual_teal_dots':len(groups),'label':label,'whole_group_alignment':rec}


def local_unit_presence(actual,expected,positions,box,divisor,radius):
    """Observe each isolated unit, so one missing dot cannot hide in mean IoU.

    During geometric crossings some centers are covered by another dot. Those
    are explicitly marked as overlaps; coverage there proves the raster union,
    not separately visible identities. Stable source/destination cells are all
    isolated and therefore each has its own independent presence observation.
    """
    isolated=covered=0;overlaps=[]
    for i,(x,y) in enumerate(positions):
        overlap_id=any(i!=j and (x-a)**2+(y-b)**2<=(2*radius+1)**2 for j,(a,b) in enumerate(positions))
        px=(x-box[0])/divisor;py=(y-box[1])/divisor
        cx,cy=math.floor(px),math.floor(py)
        patch=actual.crop((max(0,cx-1),max(0,cy-1),min(actual.width,cx+2),min(actual.height,cy+2)))
        hits=patch.histogram()[255]
        if not overlap_id:
            require(hits>0,f'Isolated mathematical unit {i} is missing near {(x,y)}')
            isolated+=1
        else:overlaps.append(i)
        if hits:covered+=1
    expanded=expected.filter(ImageFilter.MaxFilter(3))
    unexpected=ImageChops.subtract(actual,expanded).histogram()[255]
    require(unexpected<=max(2,len(positions)//20),f'Unexpected mathematical units/foreground outside expected cells: {unexpected}')
    return {'actual_covered_unit_centers':covered,'individually_observed_isolated_units':isolated,
            'centers_occluded_by_other_units':overlaps,'unexpected_foreground_pixels':unexpected,
            'actual_unit_count_when_all_isolated':isolated if isolated==len(positions) else None,
            'method':'Local actual decoded foreground in each isolated unit cell; raster-union coverage at geometric overlaps; reject unexpected foreground outside1px edge allowance'}


def small_unit_check(image,c,f,divisor=2):
    mode,n,stage,_=c.state(f)
    if mode!='count' or n>4 or stage in ('relay','result'):return None
    t=f/FPS;op=c.counts[n]['operator_timing'];previous=c.values[n-1];factor=4*n-2;count=previous*factor;shares=n+1;value=c.values[n]
    if stage=='multiply':p=clamp((t-op['times_start_s'])/(op['multiply_commit_s']-op['times_start_s']))
    elif stage=='divide':p=clamp((t-op['divided_start_s'])/(op['equals_start_s']-op['divided_start_s']))
    else:p=1 if stage=='product' else 0
    p=round(p,5)
    amount=count if stage in ('product','divide') else previous*min(factor,math.floor(factor*p)) if stage=='multiply' else 0
    box=(330,534,1590,668);mask=Image.new('L',(1260,134));d=ImageDraw.Draw(mask)
    positions=[]
    for k in range(amount):
        a=(960+(k%previous-(previous-1)/2)*28,602+(k//previous-(factor-1)/2)*8)
        b=(960+(k%value-(value-1)/2)*70,602+(k//value-(shares-1)/2)*24)
        u=smooth(p) if stage=='divide' else 0
        x=a[0]+(b[0]-a[0])*u;y=a[1]+(b[1]-a[1])*u
        positions.append((x,y))
        d.ellipse((x-3-box[0],y-3-box[1],x+3-box[0],y+3-box[1]),fill=255)
    roi=tuple(v//divisor for v in box)
    if divisor>1:
        mask=mask.crop((0,0,(roi[2]-roi[0])*divisor,(roi[3]-roi[1])*divisor)).resize((roi[2]-roi[0],roi[3]-roi[1]),Image.Resampling.BOX)
    expected=mask.point(lambda a:255 if a>=128 else 0)
    actual=image.crop(roi).convert('L').point(lambda a:255 if a<195 else 0)
    score=overlap(actual,expected)
    require(score>=.72,f'Main small-unit arithmetic differs n{n} {stage} f{f} {score:.3f}')
    presence=local_unit_presence(actual,expected,positions,box,divisor,3)
    return {'frame':f,'n':n,'stage':stage,'expected_units':amount,'product':count,'divisor':shares,'result':value,'actual_raster_iou':score,'presence':presence}


def replay_check(image,c,f,divisor=1):
    event=c.by['T004a'];u=clamp((f/FPS-event['start_s'])/(event['end_s']-event['start_s']))
    box=(350,270,1570,615);mask=Image.new('L',(box[2]-box[0],box[3]-box[1]));d=ImageDraw.Draw(mask)
    move=smooth((u-.28)/.40);amount=5*min(14,math.floor(14*clamp(u/.24)))
    positions=[]
    for k in range(amount):
        sx=960+(k%5-2)*55;sy=428+(k//5-6.5)*22
        tx=960+(k%14-6.5)*80;ty=428+(k//14-2)*48
        x=sx+(tx-sx)*move;y=sy+(ty-sy)*move+math.sin(math.pi*move)*30*(1 if k%2 else -1)
        positions.append((x,y))
        d.ellipse((x-6-box[0],y-6-box[1],x+6-box[0],y+6-box[1]),fill=255)
    roi=tuple(v//divisor for v in box)
    if divisor>1:
        mask=mask.crop((0,0,(roi[2]-roi[0])*divisor,(roi[3]-roi[1])*divisor))
        mask=mask.resize((roi[2]-roi[0],roi[3]-roi[1]),Image.Resampling.BOX)
    expected=mask.point(lambda a:255 if a>=128 else 0)
    actual=image.crop(roi).convert('L').point(lambda l:255 if l<210 else 0)
    score=overlap(actual,expected)
    require(score>=.80,f'Actual70-unit trajectory mismatch frame{f} u{u:.3f}: {score:.3f}')
    presence=local_unit_presence(actual,expected,positions,box,divisor,6)
    alignment={}
    if amount:
        ab,eb=actual.getbbox(),expected.getbbox()
        delta=[((ab[k]+ab[k+2])-(eb[k]+eb[k+2]))/2 for k in (0,1)]
        require(all(abs(z)<=1 for z in delta),'Point group deviates on one or both axes')
        alignment={'actual_visible_box':ab,'expected_visible_box':eb,'delta_x_px':delta[0],'delta_y_px':delta[1],
                   'tolerance_px':1,'horizontal':'independent trajectory x','vertical':'independent trajectory y'}
    return {'frame':f,'progress':u,'actual_raster_trajectory_iou':score,'units_after_build':70,'visible_intended_units':amount,
            'divisor':divisor,'alignment':alignment,
            'presence':presence,
            'source_partition':'14 groups of5','destination_partition':'5 groups of14','trajectory':'70 continuously identified units; no scene cut'}


def path_check(image,word,box):
    heights=[0]
    for ch in word:heights.append(heights[-1]+(1 if ch=='U' else -1))
    require(min(heights)>=0 and heights[-1]==0 and len(word)==6,'Incorrect independent3-pair path')
    unit=min((box[2]-box[0]-60)/6,(box[3]-box[1]-45)/max(heights))
    left=(box[0]+box[2]-6*unit)/2;baseline=(box[1]+box[3]+max(heights)*unit)/2
    points=[(left+i*unit,baseline-h*unit) for i,h in enumerate(heights)]
    mask=Image.new('L',(box[2]-box[0],box[3]-box[1]));d=ImageDraw.Draw(mask)
    for a,b in zip(points,points[1:]):d.line((a[0]-box[0],a[1]-box[1],b[0]-box[0],b[1]-box[1]),fill=255,width=9)
    # The raster includes small dark vertex centers and a golden moving tip.
    for x,y in points:d.ellipse((x-3-box[0],y-3-box[1],x+3-box[0],y+3-box[1]),fill=255)
    x,y=points[-1];d.ellipse((x-7-box[0],y-7-box[1],x+7-box[0],y+7-box[1]),fill=255)
    crop=image.crop(box);r,g,b=crop.split()
    # Grey baseline is excluded; teal, coral and gold strokes remain.
    actual=Image.new('L',crop.size);ap=actual.load();pix=crop.load()
    for y in range(crop.height):
        for x in range(crop.width):
            rr,gg,bb=pix[x,y]
            if (gg-rr>25 and bb-rr>20 and rr<125) or (rr-gg>35 and rr-bb>65 and gg<185) or (rr<125 and gg<110 and bb<95):ap[x,y]=255
    score=overlap(actual,mask)
    require(score>=.80,f'Dyck-path decoded shape differs {word}: {score:.3f}')
    return {'word':word,'actual_path_shape_iou':score,'nonnegative':True,'up_steps':3,'down_steps':3,'first_return_step':next(i for i,h in enumerate(heights[1:],1) if h==0)}


def negative_digit_control(image,c):
    text=f'{c.values[30]:,}';wrong=text[:-1]+('5' if text[-1]!='5' else '6')
    mutated=image.copy();d=ImageDraw.Draw(mutated);d.rectangle(NUMBER,fill=CREAM)
    face=font(82);bb=face.getbbox(wrong);layer=Image.new('RGBA',(bb[2]-bb[0]+64,bb[3]-bb[1]+64))
    ImageDraw.Draw(layer).text((32-bb[0],32-bb[1]),wrong,font=face,fill=TEAL)
    ink=layer.getchannel('A').point(lambda a:255 if a>=128 else 0).getbbox()
    xy=(round((NUMBER[0]+NUMBER[2]-ink[0]-ink[2])/2),round((NUMBER[1]+NUMBER[3]-ink[1]-ink[3])/2))
    mutated.paste(layer,xy,layer)
    rejected=None
    try:glyph_check(mutated,NUMBER,text,82,TEAL)
    except ValueError as e:rejected=str(e)
    require(rejected is not None,'Wrong final digit escaped the independent verifier')
    return mutated,{'passed':True,'source':'actual decoded C30 result frame','true':text,'mutation':wrong,'rejected_reason':rejected,
                    'scope':'One-digit corruption; no renderer output or saved math truth was changed'}


def visual(video,c,directory):
    directory.mkdir(parents=True,exist_ok=False);native=native_samples(c);summary=Counter();minimum=1.;digits=0;frame_total=0;motion=[];small=[];progress_rows=[]
    # First scan: all final frames. Typography at half size is reported apart
    # from the native1px alignment measurements in the second scan.
    with gzip.open(directory/'all-frame-glyph-observations.jsonl.gz','wt') as log:
        for f,image in decoded_frames(video,ffbin('ffmpeg'),directory/'all-decode.log',divisor=2):
            require(f<c.frames,'Extra video frame');frame_total+=1
            if f<18 or f>=c.frames-24:continue
            fields=c.fields(f);observations=[]
            for ident,text,size,box,color,multi in fields:
                # Every relay frame is checked natively in the second scan.
                if ident=='transferred-previous':continue
                r=glyph_check(image,box,text,size,color,2,multi,alignment=False)
                minimum=min(minimum,r['mask_iou']);digits+=len(r.get('digits',[]));summary[ident]+=1
                observations.append({'id':ident,'iou':r['mask_iou'],'digits':len(r.get('digits',[]))})
            check_progress(image,c,f,2)
            unit=small_unit_check(image,c,f,2)
            if unit:small.append(unit)
            replay=c.by['T004a']
            if replay['start_s']<=f/FPS<replay['end_s']:motion.append(replay_check(image,c,f,2))
            log.write(json.dumps({'frame':f,'state':c.state(f)[:3],'fields':observations})+'\n')
            if f%900==0:print(f'independent half-size decode {f}/{c.frames}',flush=True)
    require(frame_total==c.frames,'Wrong decoded frame count')
    native_records=[];native_digit_count=0;fade_rows=[];path_rows=[];negative=None;unit_negative=[];clear_rgb=None;sample_images=directory/'native';sample_images.mkdir()
    for f,image in decoded_frames(video,ffbin('ffmpeg'),directory/'native-decode.log',divisor=1,indices=native):
        if f<18 or f>=c.frames-24:
            # Header title is stable across all scenes; its contrast follows
            # the whole-frame fade and the final frame must be plain cream.
            if clear_rgb is None:
                clear_rgb=image.getpixel((0,0));source_rgb=Image.new('RGB',(1,1),CREAM).getpixel((0,0))
                require(all(abs(a-b)<=3 for a,b in zip(clear_rgb,source_rgb)),'Decoded cleared colour differs from BT709 quantization allowance')
                require(all(b-a<=1 for a,b in image.getextrema()),'Initial fade does not clear the whole frame')
            crop=image.crop((380,40,1540,89));contrast=ImageStat.Stat(ImageChops.difference(crop,Image.new('RGB',crop.size,clear_rgb)).convert('L')).mean[0]
            fade_rows.append({'frame':f,'title_contrast':contrast});image.save(sample_images/f'fade-{f:05}.png');continue
        records=[]
        for ident,text,size,box,color,multi in c.fields(f):
            r=glyph_check(image,box,text,size,color,1,multi);r.update(frame=f,time_s=f/FPS,id=ident,mode=c.state(f)[0],index=c.state(f)[1]);records.append(r)
            native_digit_count+=len(r.get('digits',[]))
        progress_rows.append({'frame':f,**check_progress(image,c,f,1)})
        replay=c.by['T004a']
        if replay['start_s']<=f/FPS<replay['end_s']:motion.append(replay_check(image,c,f,1))
        if not unit_negative and c.state(f)[:3]==('count',4,'product'):
            positive=small_unit_check(image,c,f,1);bad=image.copy();ImageDraw.Draw(bad).ellipse((956,594,964,602),fill=CREAM)
            reason=None
            try:small_unit_check(bad,c,f,1)
            except ValueError as e:reason=str(e)
            require(reason and 'missing' in reason,'One missing main arithmetic unit escaped detection')
            bad.save(directory/'negative-main-one-unit-missing.png')
            unit_negative.append({'frame':f,'scope':'one central unit removed in memory from actual decoded70-unit main-product frame; MP4 unchanged',
                                  'true_unit_count_observed':positive['presence']['actual_unit_count_when_all_isolated'],'rejected':True,'reason':reason})
        if len(unit_negative)==1 and replay['start_s']<=f/FPS<replay['end_s'] and (f/FPS-replay['start_s'])/(replay['end_s']-replay['start_s'])>.82:
            positive=replay_check(image,c,f,1);bad=image.copy();ImageDraw.Draw(bad).ellipse((753,421,767,435),fill=CREAM)
            reason=None
            try:replay_check(bad,c,f,1)
            except ValueError as e:reason=str(e)
            require(reason and 'missing' in reason,'One missing replay arithmetic unit escaped detection')
            bad.save(directory/'negative-replay-one-unit-missing.png')
            unit_negative.append({'frame':f,'scope':'one central unit removed in memory from actual decoded5x14 replay frame; MP4 unchanged',
                                  'true_unit_count_observed':positive['presence']['actual_unit_count_when_all_isolated'],'rejected':True,'reason':reason})
        for cue in ['T003a','T003c','T003d','T003e']:
            event=c.by[cue]
            if frame_at(event['end_s'])-1==f:
                if cue=='T003a':
                    words=['UUUDDD','UUDUDD','UUDDUD','UDUUDD','UDUDUD']
                    for i,word in enumerate(words):
                        x=245+(i%3)*490;y=175+(i//3)*235
                        path_rows.append({'cue':cue,'frame':f,**path_check(image,word,(x+25,y+20,x+425,y+157))})
                else:
                    for k,words in enumerate([['UDUUDD','UDUDUD'],['UUDDUD'],['UUUDDD','UUDUDD']]):
                        x=250+k*480
                        for i,word in enumerate(words):path_rows.append({'cue':cue,'inside_pairs':k,'after_pairs':2-k,'frame':f,
                            **path_check(image,word,(x+35,265+i*127,x+425,371+i*127))})
        if negative is None and c.state(f)[:3]==('count',30,'result'):
            mutated,negative=negative_digit_control(image,c);mutated.save(directory/'negative-c30-wrong-digit.png')
        native_records.extend(records)
        if f in set(native[::max(1,len(native)//70)]) or c.state(f)[0] in ('history','ending'):
            image.save(sample_images/f'frame-{f:05}.png')
    require(fade_rows[0]['title_contrast']<1 and fade_rows[-1]['title_contrast']<1,'Fade endpoint is not clear cream')
    require(max(r['title_contrast'] for r in fade_rows)>5,'Fade is not changing visible foreground')
    write(directory/'native-alignment.json',{'scope':'actual native decoded glyph masks; each axis<=1px; no renderer observations imported',
          'sample_frames':len(native),'component_observations':len(native_records),'digit_observations':native_digit_count,
          'all_passed':True,'max_abs_dx':max([abs(r['delta_x_px']) for r in native_records] or [0]),
          'max_abs_dy':max([abs(r['delta_y_px']) for r in native_records] or [0]),'records':native_records})
    write(directory/'fade.json',{'passed':True,'observations':fade_rows,'decoded_clear_rgb':clear_rgb,
                                'colour_quantization_allowance_per_channel':3,'scope':'actual initial/final contrast against decoded cleared colour; endpoint absence is intentional'})
    require(len(path_rows)==20,'Not all5 paths /3 first-return explanations were observed')
    require(motion and negative and len(unit_negative)==2,'Missing dynamic or negative control evidence')
    write(directory/'paths.json',{'passed':True,'observations':path_rows,'all5_paths_unique':len({r['word'] for r in path_rows})==5})
    write(directory/'unit-trajectories.json',{'passed':True,'actual_decoded_frame_observations':len(motion),'frames':motion})
    write(directory/'main-small-units.json',{'passed':True,'actual_decoded_frame_observations':len(small),'frames':small})
    write(directory/'progress.json',{'passed':True,'all_visible_frames_checked':c.frames-42,'native_observations':progress_rows,
                                    'scope':'all31 markers + numeric label in every visible scene including explanations; native whole-group and label each-axis <=1px'})
    write(directory/'negative-control.json',negative)
    write(directory/'negative-unit-controls.json',{'passed':True,'controls':unit_negative})
    return {'passed':True,'all_decoded_frames':frame_total,'half_size_field_observations':dict(summary),'half_size_digit_observations':digits,
            'minimum_half_size_glyph_iou':minimum,'native_sample_frames':len(native),'native_component_observations':len(native_records),
            'native_digit_observations':native_digit_count,'both_axes_native_tolerance_px':1,
            'all5_dyck_paths_and_ordered_groups':True,'continuous70_unit_motion_frames':len(motion),'wrong_digit_negative_control':negative,
            'not_claimed':['every-frame native character appearance','fresh speech ASR/CTC by this verifier','subjective acting sufficiency']}


def captions(plan,events,directory):
    candidates=[directory/'subtitles.srt',directory/'english-captions.srt']
    path=next((p for p in candidates if p.exists()),None)
    require(path is not None,'No delivered subtitle file')
    blocks=re.split(r'\n\s*\n',path.read_text().strip());require(len(blocks)==86,'Wrong subtitle cue count')
    for event,block in zip(events,blocks):
        parts=block.splitlines();require(' '.join(parts[2:])==event['text'],'Subtitle text differs '+event['id'])
        stamps=re.findall(r'(\d+):(\d+):(\d+),(\d+)',parts[1])
        require(len(stamps)==2,'Invalid subtitle timestamp '+event['id'])
        actual=[int(h)*3600+int(m)*60+int(s)+int(ms)/1000 for h,m,s,ms in stamps]
        require(abs(actual[0]-event['start_s'])<=.001 and abs(actual[1]-event['end_s'])<=.001,'Subtitle timing differs '+event['id'])
    return {'passed':True,'cues':86,'file':str(path),'sha256':sha(path),'timestamp_tolerance_s':.001}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--video',type=Path,required=True)
    p.add_argument('--timeline',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--delivery-dir',type=Path)
    p.add_argument('--skip-technical',action='store_true');p.add_argument('--skip-captions',action='store_true')
    a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=False)
    plan=json.loads(a.timeline.read_text());c=Contract(plan)
    write(a.out_dir/'schedule.json',c.schedule_report)
    tech=None
    if not a.skip_technical:tech=technical.verify_video(a.video,a.out_dir/'technical',a.timeline,ffbin('ffmpeg'),ffbin('ffprobe'),duration_bounds=(480,1800));require(tech.get('passed',tech.get('status')=='pass'),'Technical media check failed')
    images=visual(a.video,c,a.out_dir/'visual')
    delivery=None if a.skip_captions else captions(plan,c.events,a.delivery_dir or a.video.parent)
    report={'passed':True,'video':{'path':str(a.video),'sha256':sha(a.video)},'timeline':{'path':str(a.timeline),'sha256':sha(a.timeline)},
            'schedule':c.schedule_report,'visual':images,'technical':tech,'captions':delivery,
            'audio_content_scope':'Dedicated episode speech audit required; this verifier does not claim fresh ASR, CTC or full listening.',
            'art_and_acting_scope':'Native full-screen and continuous comparison is a separate root/acting review.'}
    write(a.out_dir/'verification.json',report);print(json.dumps({'passed':True,'frames':c.frames,'native_samples':images['native_sample_frames']}))


if __name__=='__main__':main()
