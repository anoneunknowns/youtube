"""Read Catalan video pixels again with a different observation method.

No episode renderer or prior Catalan verifier is imported. Main number strings
are recognized from segmented glyphs without providing the expected numeral to
the recognizer. English readings are classified from a number-word image
vocabulary and inverted to integers. All31 progress cells are inspected by
position; stable unit diagrams are measured as real connected components.
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
import subprocess

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat
try:
    from verify_catalan_video_v004 import glyph_check as independent_label_glyph_check
except ModuleNotFoundError:
    from tools.verify_catalan_video_v004 import glyph_check as independent_label_glyph_check

ROOT=Path(__file__).resolve().parents[1]
FONT=ROOT/'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
DEFAULT_VIDEO=ROOT/'output/catalan-counting-001-v007/paspla-studio-catalan-numbers-c0-to-c30-1080p.mp4'
DEFAULT_TIMELINE=ROOT/'design/catalan-counting-v1/production-qa/recheck-20261112-01/audio/replacement-five-v001/adopted-v002/timeline.json'
VIDEO_SHA=None
FPS=30;NUMBER=(260,405,1660,505);READING=(270,724,1650,804);CARD=(235,245,1685,705)
BASE_DIR=ROOT/'design/catalan-counting-v1/production-qa/recheck-20261112-01/video'
SMALL='zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
TENS=['','','twenty','thirty','forty','fifty','sixty','seventy','eighty','ninety']
SCALE_WORDS={'thousand':1000,'million':10**6,'billion':10**9,'trillion':10**12,'quadrillion':10**15}


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def at(t):return math.ceil(t*FPS-1e-7)
def clamp(x):return min(1,max(0,x))
def ease(x):x=clamp(x);return x*x*(3-2*x)


@lru_cache(maxsize=128)
def face(size):return ImageFont.truetype(str(FONT),size)


def inverse_words(text):
    values={s:i for i,s in enumerate(SMALL)};values.update({s:i*10 for i,s in enumerate(TENS) if s})
    total=group=0;last_scale=10**18
    for token in text.replace('-',' ').split():
        if token in values:group+=values[token]
        elif token=='hundred':require(1<=group<=9,'Invalid hundred group '+text);group*=100
        elif token in SCALE_WORDS:
            scale=SCALE_WORDS[token];require(scale<last_scale and 0<group<1000,'Invalid scale order '+text)
            total+=group*scale;group=0;last_scale=scale
        else:raise ValueError('Unknown number word '+token)
    return total+group


def cardinal_below100(n):
    if n<20:return SMALL[n]
    return TENS[n//10]+('-'+SMALL[n%10] if n%10 else '')


def canonical_cardinal(n):
    if n<100:return cardinal_below100(n)
    if n<1000:return SMALL[n//100]+' hundred'+(' '+canonical_cardinal(n%100) if n%100 else '')
    for word,scale in sorted(SCALE_WORDS.items(),key=lambda p:p[1],reverse=True):
        if n>=scale:return canonical_cardinal(n//scale)+' '+word+(' '+canonical_cardinal(n%scale) if n%scale else '')
    raise ValueError(n)


VOCAB=tuple(sorted(set([cardinal_below100(n) for n in range(100)]+['hundred']+list(SCALE_WORDS))))


def independent_values():
    states={0:1};walks=[1]
    for step in range(1,61):
        future=Counter()
        for h,n in states.items():
            future[h+1]+=n
            if h:future[h-1]+=n
        states=future
        if step%2==0:walks.append(states.get(0,0))
    binomial=[math.comb(2*n,n)//(n+1) for n in range(31)]
    require(walks==binomial,'Ballot-walk DP and binomial numbers disagree')
    return walks


def binary(crop,cut=184):return crop.convert('L').point(lambda x:255 if x<cut else 0)


def runs(values):
    out=[];start=None
    for i,on in enumerate(values):
        if on and start is None:start=i
        if not on and start is not None:out.append((start,i));start=None
    if start is not None:out.append((start,len(values)))
    return out


def split_columns(mask):
    projection=mask.resize((mask.width,1),Image.Resampling.BOX)
    return runs([v>0 for v in projection.get_flattened_data()])


def intersection_score(a,b):
    u=ImageChops.lighter(a,b).histogram()[255]
    return ImageChops.darker(a,b).histogram()[255]/u if u else 1


@lru_cache(maxsize=20000)
def template(text,size):
    f=face(size);b=f.getbbox(text);m=Image.new('L',(b[2]-b[0]+40,b[3]-b[1]+40))
    ImageDraw.Draw(m).text((20-b[0],20-b[1]),text,font=f,fill=255)
    m=m.point(lambda x:255 if x>=128 else 0);return m.crop(m.getbbox())


def shape_score(a,b):
    if abs(a.width-b.width)>2 or abs(a.height-b.height)>2:return 0.
    w=max(a.width,b.width)+6;h=max(a.height,b.height)+6
    aa=Image.new('L',(w,h));aa.paste(a,((w-a.width)//2,(h-a.height)//2))
    scores=[]
    for dx in (-1,0,1):
        for dy in (-1,0,1):
            bb=Image.new('L',(w,h));bb.paste(b,((w-b.width)//2+dx,(h-b.height)//2+dy));scores.append(intersection_score(aa,bb))
    return max(scores)


CLASSIFICATION_CACHE={}
NUMBER_CACHE={}
ENGLISH_CACHE={}
PROGRESS_CACHE={}
SYMBOL_CACHE={}
MATH_SYMBOLS=tuple('0123456789,Cn()=−×÷+·PAIRS')+tuple('PAIRS'[i:j] for i in range(5) for j in range(i+2,6))


def classify(piece,candidates,sizes):
    key=(hashlib.blake2s(piece.tobytes(),digest_size=12).digest(),piece.size,tuple(sizes),candidates)
    if key in CLASSIFICATION_CACHE:return CLASSIFICATION_CACHE[key]
    scores=[]
    for size in sizes:
        for text in candidates:
            ref=template(text,size)
            if abs(piece.width-ref.width)<=2 and abs(piece.height-ref.height)<=2:
                scores.append((shape_score(piece,ref),text,size))
    require(scores,'No glyph/word candidate fits observed dimensions '+str(piece.size))
    scores.sort(reverse=True);best=scores[0]
    different=[s for s in scores[1:] if s[1]!=best[1]]
    margin=best[0]-(different[0][0] if different else 0)
    word=len(candidates)>11
    require(best[0]>=(.83 if word else .86) and margin>=(.05 if word else .025),f'Ambiguous actual glyph/word {best} next={different[:2]}')
    result={'text':best[1],'font_size_px':best[2],'iou':best[0],'other_character_margin':margin}
    CLASSIFICATION_CACHE[key]=result
    return result


def read_number(image,box=NUMBER,sizes=(69,82,102,112)):
    crop=image.crop(box);mask=binary(crop);b=mask.getbbox()
    cache_key=(hashlib.blake2s(mask.tobytes(),digest_size=12).digest(),box,tuple(sizes))
    if cache_key in NUMBER_CACHE:return NUMBER_CACHE[cache_key]
    require(b is not None,'Missing main numeric foreground')
    group=mask.crop(b);columns=split_columns(group)
    require(columns,'No actual numeral components')
    if group.height<=25:
        require(len(columns)==3,'Unexpected low main numeric glyphs')
        result={'text':'…','visible_box_xyxy':[b[0]+box[0],b[1]+box[1],b[2]+box[0],b[3]+box[1]],'glyphs':[]}
        NUMBER_CACHE[cache_key]=result;return result
    out=[];glyphs=[]
    for left,right in columns:
        p=group.crop((left,0,right,group.height));pb=p.getbbox();p=p.crop(pb)
        result=classify(p,tuple('0123456789,'),tuple(sizes));out.append(result['text'])
        glyphs.append({**result,'visible_box_xyxy':[box[0]+b[0]+left+pb[0],box[1]+b[1]+pb[1],box[0]+b[0]+left+pb[2],box[1]+b[1]+pb[3]]})
    text=''.join(out);require(re.fullmatch(r'\d{1,3}(?:,\d{3})*|\d+',text) is not None,'Invalid observed numeral punctuation '+text)
    result={'text':text,'value':int(text.replace(',','')),'visible_box_xyxy':[b[0]+box[0],b[1]+box[1],b[2]+box[0],b[3]+box[1]],'glyphs':glyphs}
    NUMBER_CACHE[cache_key]=result;return result


def read_english(image):
    mask=binary(image.crop(READING),180);key=hashlib.blake2s(mask.tobytes(),digest_size=12).digest()
    if key in ENGLISH_CACHE:return ENGLISH_CACHE[key]
    rows=runs([v>0 for v in mask.resize((1,mask.height),Image.Resampling.BOX).get_flattened_data()])
    words=[];records=[]
    for top,bottom in rows:
        row=mask.crop((0,top,mask.width,bottom));col=split_columns(row)
        groups=[]
        for left,right in col:
            if not groups or left-groups[-1][1]>=7:groups.append([left,right])
            else:groups[-1][1]=right
        for left,right in groups:
            part=row.crop((left,0,right,row.height));part=part.crop(part.getbbox())
            observed=classify(part,VOCAB,(30,));words.append(observed['text']);records.append(observed)
    require(words,'English result reading missing')
    text=' '.join(words)
    result={'text':text,'value':inverse_words(text),'words':records};ENGLISH_CACHE[key]=result;return result


def read_symbols(image,box,size,foreground_luma=111,candidates=MATH_SYMBOLS):
    crop=image.crop(box);grey=crop.convert('L');corners=sorted(grey.getpixel(p) for p in [(0,0),(grey.width-1,0),(0,grey.height-1),(grey.width-1,grey.height-1)])
    cut=((corners[1]+corners[2])/2+foreground_luma)/2
    mask=binary(crop,cut);b=mask.getbbox();require(b is not None,'Symbolic mathematical foreground missing')
    key=(hashlib.blake2s(mask.tobytes(),digest_size=12).digest(),box,size,candidates)
    if key in SYMBOL_CACHE:return SYMBOL_CACHE[key]
    part=mask.crop(b);letters=[];records=[]
    for l,r in split_columns(part):
        p=part.crop((l,0,r,part.height));pb=p.getbbox();p=p.crop(pb)
        try:result=classify(p,candidates,(size,))
        except ValueError as e:raise ValueError(f'Observed symbol chunk size{size}, field{box}, raster{p.size}: {e}') from e
        letters.append(result['text']);records.append({**result,'visible_box_xyxy':[box[0]+b[0]+l+pb[0],box[1]+b[1]+pb[1],box[0]+b[0]+l+pb[2],box[1]+b[1]+pb[3]]})
    result={'text':''.join(letters),'glyphs':records,'visible_box_xyxy':[b[0]+box[0],b[1]+box[1],b[2]+box[0],b[3]+box[1]]}
    SYMBOL_CACHE[key]=result;return result


def verify_literal(image,box,size,literal,foreground_luma=111,candidates=MATH_SYMBOLS):
    read=read_symbols(image,box,size,foreground_luma,candidates)
    require(read['text']==literal.replace(' ',''),f'Observed algebra/index differs: {read["text"]} != {literal}')
    return read


def whole_word_row(image,box,size,vocabulary):
    crop=image.crop(box);grey=crop.convert('L');corners=sorted(grey.getpixel(p) for p in [(0,0),(grey.width-1,0),(0,grey.height-1),(grey.width-1,grey.height-1)])
    mask=binary(crop,((corners[1]+corners[2])/2+111)/2);b=mask.getbbox();require(b,'Visible label row missing')
    part=mask.crop(b);col=split_columns(part);groups=[]
    for left,right in col:
        if not groups or left-groups[-1][1]>=7:groups.append([left,right])
        else:groups[-1][1]=right
    out=[]
    for left,right in groups:
        p=part.crop((left,0,right,part.height));pb=p.getbbox();p=p.crop(pb)
        result=classify(p,tuple(vocabulary),(size,));result={**result,'visible_box_xyxy':[box[0]+b[0]+left+pb[0],box[1]+b[1]+pb[1],box[0]+b[0]+left+pb[2],box[1]+b[1]+pb[3]]};out.append(result)
    return out


def observed_count_algebra(image,n,stage,time_s,timing):
    if stage=='relay':return []
    v=timing.values[n];prev=timing.values[n-1];factor=4*n-2;divisor=n+1;op=timing.counts[n]['operator_timing'];wide=n>=16
    out=[verify_literal(image,(265,158,1655,216),44,'C(n)=C(n−1)×(4n−2)÷(n+1)')]
    if stage=='result':
        out += [verify_literal(image,(270,268,1650,342),50 if wide else 64,f'{prev:,}×{factor}÷{divisor}'),
                verify_literal(image,(550,591,1370,653),35,f'C({n})·{n}'+('PAIR' if n==1 else 'PAIRS'),foreground_luma=77)]
    else:
        divide=time_s>=op['divided_start_s']
        expression=f'{prev*factor:,}÷{divisor}' if divide else f'{prev:,}×{factor}'
        out += [verify_literal(image,(270,268,1650,342),56 if wide and divide else 59 if wide else 76,expression,foreground_luma=149 if divide else 77),
                verify_literal(image,(252,354,580,395),23,f'4×{n}−2={factor}'),verify_literal(image,(1345,354,1667,395),23,f'{n}+1={divisor}')]
    return out


def actual_panel_inset(image):
    pixels=image.load();xs=[x for x in range(90,1831) if pixels[x,600][0]>245 and pixels[x,600][1]>235 and pixels[x,600][2]>220]
    require(xs,'Expanded pane not visible')
    left,right=min(xs)-2,max(xs)+3
    require(abs(left-(1920-right))<=1,'Pane horizontal expansion is asymmetric')
    return {'left':left,'right':right,'width':right-left,'measurement':'actual cream fill and border transition in decoded row600'}


def fade_observation(image,f,clear_rgb):
    ref=Image.new('RGB',image.size,clear_rgb);diff=ImageChops.difference(image,ref)
    regions={'whole':(0,0,1920,1080),'title':(350,25,1570,135),'lesson':(230,150,1690,812),
             'actor':(800,690,1120,1050),'progress':(100,962,730,1050)}
    return {'frame':f,'contrast':{name:ImageStat.Stat(diff.crop(box).convert('L')).mean[0] for name,box in regions.items()},
            'maximum_rgb_delta':max(maximum for minimum,maximum in diff.getextrema())}


def relay_geometry(rows,destinations,timing):
    observations=[]
    for n in range(1,31):
        require(n in destinations,'No independently observed next-expression operand center')
        target=destinations[n];bounds=target['bbox'];dxgoal=(bounds[0]+bounds[2])/2;dygoal=(bounds[1]+bounds[3])/2
        for row in [r for r in rows if r['n']==n]:
            f=row['frame'];b=row['visible_box_xyxy'];cx=(b[0]+b[2])/2;cy=(b[1]+b[3])/2
            start=timing.counts[n]['cycle_start_s'];end=timing.by[f'E{n:03}']['start_s'];u=ease((f/FPS-start)/(end-start))
            dx=cx-(960+(dxgoal-960)*u);dy=cy-(455+(dygoal-455)*u)
            require(abs(dx)<=1 and abs(dy)<=1,f'Observed relay trajectory axis error n{n} frame{f}: {dx},{dy}')
            margins={'left':b[0]-CARD[0],'right':CARD[2]-b[2],'top':b[1]-CARD[1],'bottom':CARD[3]-b[3]}
            require(min(margins.values())>0,'Moving predecessor touches/crosses actual usable region')
            observations.append({'frame':f,'n':n,'visible_box_xyxy':b,'actual_center_px':[cx,cy],
                                 'independently_observed_destination_center_px':[dxgoal,dygoal],
                                 'delta_x_px':dx,'delta_y_px':dy,'tolerance_px':1,'margins_px':margins})
    return {'passed':True,'frames':len(observations),'all30_transfers':True,'max_abs_dx':max(abs(r['delta_x_px']) for r in observations),
            'max_abs_dy':max(abs(r['delta_y_px']) for r in observations),'records':observations,
            'scope':'Actual moving numeral bounds versus mathematical trajectory ending at the independently observed next-expression predecessor glyph, never font origin/canvas extent. Explanatory-scene cuts return to calculator before transfer.'}


def new_scene_semantics(image,event,f,timing,revision):
    cue=event['id'];u=clamp((f/FPS-event['start_s'])/(event['end_s']-event['start_s']));out={'cue':cue,'frame':f,'fraction':u}
    if cue in ('T000a','T000b','T000c') and revision!='v002':
        out['general_formula']=verify_literal(image,(260,217,1660,298),47,'C(n)=C(n−1)×(4n−2)÷(n+1)',77)
        for box,text,size in [((272,369,608,415),'LASTVALUE',27),((712,369,1208,415),'WHOLEPRODUCT',27),((1312,369,1648,415),'NEXTVALUE',27)]:
            words=whole_word_row(image,box,size,('LAST','VALUE','WHOLE','PRODUCT','NEXT'))
            require(''.join(w['text'] for w in words)==text,'Value-window title semantic role differs')
        out['values']=[verify_literal(image,(275,452,605,513),43,'C(n−1)',119),
                       verify_literal(image,(715,452,1205,513),30,'C(n−1)×(4n−2)',119),
                       verify_literal(image,(1315,452,1645,513),48,'C(n)',119)]
        out['operations']=[verify_literal(image,(450,566,870,605),27,'×(4n−2)',119),verify_literal(image,(1050,566,1470,605),27,'÷(n+1)',149)]
        if revision in ('v004','v005','v006','v007'):
            markers=[]
            for box in [(620,438,700,466),(1220,438,1300,466)]:
                crop=image.crop(box);count=sum(1 for r,g,b in crop.get_flattened_data() if r>180 and 130<g<195 and b<125 and r-g>35 and g-b>45)
                markers.append(count)
            # T000a uses independent phoneme boundaries from the unchanged
            # speech source, not a fraction of the whole utterance or a value
            # supplied by the renderer. At +5.7s the voice still says minus
            # two: the divider must not be active until Then at +6.62s.
            if revision in ('v006','v007') and cue=='T000a':
                offset=f/FPS-event['start_s']
                active=-1 if offset<3.30 else 0 if offset<6.62 else 1
                expected_card=active+1
            else:
                split=4.26/(event['end_s']-event['start_s']) if cue=='T000b' else .65 if cue=='T000a' else .5
                active=1 if u>=split else 0
                expected_card=active+1
            if active<0:require(max(markers)<=3,'An operation moves before multiply is spoken')
            else:require(markers[active]>=20 and markers[1-active]<=3,'Both operations move together or wrong operation is active')
            if revision in ('v006','v007'):
                colors=[image.getpixel((x,430)) for x in [440,960,1480]]
                highlighted=[i for i,(r,g,b) in enumerate(colors) if r>225 and 205<g<237 and 165<b<210 and r-g>10 and g-b>25]
                require(highlighted==[expected_card],'Value-window highlight advances before its spoken role')
                out.update(actual_window_sample_rgb=colors,actual_highlighted_card=highlighted[0],
                           expected_window_role=['previous value','whole product','next value'][expected_card])
            out['actual_gold_marker_pixels']=markers;out['active_operation']='none' if active<0 else 'divide' if active else 'multiply'
        out['semantic_roles']='left previous value -> exact whole product in middle -> next Catalan value after division; no future numeric value exposed'
    elif cue=='T015a':
        value=read_number(image,(260,350,1660,470),(112,));require(value['value']==timing.values[15],'Wrong retained C15 during expansion')
        pane=actual_panel_inset(image);out['pane']=pane
        if revision!='v002':
            expected=round(230-110*ease(u/.65));require(abs(pane['left']-expected)<=1,'Actual pane does not follow declared expansion')
    elif cue=='T020a':
        value=read_number(image,(260,350,1660,470),(82,));require(value['value']==timing.values[20],'Wrong C20 in place-group explanation')
        out['value']=value['text']
        if revision!='v002':
            words=whole_word_row(image,(550,550,1370,605),21,('BILLION','MILLION','THOUSAND','ONES'))
            require([w['text'] for w in words]==['BILLION','MILLION','THOUSAND','ONES'],'Place names are missing or reordered')
            groups=[];part=[]
            for glyph in value['glyphs']:
                if glyph['text']==',':groups.append(part);part=[]
                else:part.append(glyph)
            groups.append(part);checks=[]
            for group,word in zip(groups,words):
                left=min(g['visible_box_xyxy'][0] for g in group);right=max(g['visible_box_xyxy'][2] for g in group)
                b=word['visible_box_xyxy'];dx=(b[0]+b[2]-left-right)/2;dy=(b[1]+b[3])/2-577.5
                require(abs(dx)<=1 and abs(dy)<=1,'Place-name/group glyph alignment differs on one or both axes')
                checks.append({'actual_digits':''.join(g['text'] for g in group),'actual_name':word['text'],'digit_box_x':[left,right],
                               'label_box':b,'delta_x_px':dx,'delta_y_px':dy,'tolerance_px':1})
            out['place_groups']=checks
    return out


def grammar_labels(image,cue,active):
    """Read the three independently proofread visible English labels."""
    if active==(1,'result'):
        row=verify_literal(image,(550,591,1370,653),35,'C(1)·1PAIR',foreground_luma=77)
        return {'label':'one-pair-result','actual_text':row['text'],'glyphs':row['glyphs'],'visible_box_xyxy':row['visible_box_xyxy']}
    if active is None and cue in ('T001b','O01'):
        text='NUM-NUM NUMBERS  ·  '+('1 PAIR' if cue=='T001b' else 'ALL 31 VALUES  ·  KEEP BOTH ONES')
        row=independent_label_glyph_check(image,(380,99,1540,122),text,20,'#7a6c5e',divisor=1,multi=False,alignment=True)
        return {'label':'one-pair-path-heading' if cue=='T001b' else 'all31-history-heading','expected_correct_English':text,'actual_glyph_match_and_both_axes':row}
    return None


def components(mask,min_pixels=1):
    data=mask.tobytes();width=mask.width;pending={i for i,v in enumerate(data) if v}
    groups=[]
    while pending:
        seed=pending.pop();todo=[seed];pixels=[seed]
        while todo:
            at=todo.pop();x=at%width;y=at//width
            for nx,ny in [(x-1,y),(x+1,y),(x,y-1),(x,y+1)]:
                if 0<=nx<width and 0<=ny<mask.height:
                    n=ny*width+nx
                    if n in pending:pending.remove(n);todo.append(n);pixels.append(n)
        if len(pixels)>=min_pixels:
            xs=[p%width for p in pixels];ys=[p//width for p in pixels]
            groups.append({'area_px':len(pixels),'bbox':[min(xs),min(ys),max(xs)+1,max(ys)+1],
                           'centroid_px':[sum(xs)/len(xs),sum(ys)/len(ys)]})
    return sorted(groups,key=lambda r:(r['centroid_px'][1],r['centroid_px'][0]))


def separated_units(image,kind='main',expected_count=70,expected_rows=None,expected_columns=None):
    if kind=='main':box=(330,534,1590,668);cut=195;minimum=25;maximum=55
    else:box=(350,270,1570,615);cut=210;minimum=100;maximum=155
    parts_all=components(binary(image.crop(box),cut));parts=[p for p in parts_all if p['area_px']>=minimum]
    require(len(parts)==expected_count,f'{kind} actual full-size components {len(parts)} != {expected_count}')
    require(all(minimum<=p['area_px']<=maximum for p in parts),'Unit has partial/tiny/merged visible area')
    require(sum(p['area_px'] for p in parts_all if p['area_px']<minimum)<=2,'Tiny foreground replaces a whole unit')
    rows={}
    for p in parts:rows.setdefault(round(p['centroid_px'][1]),[]).append(p)
    if expected_rows is not None:require(len(rows)==expected_rows and all(len(r)==expected_columns for r in rows.values()),'Actual equal-share row partition differs')
    return {'actual_full_components':len(parts),'minimum_area_px':min([p['area_px'] for p in parts] or [0]),
            'maximum_area_px':max([p['area_px'] for p in parts] or [0]),'actual_row_counts':{y:len(v) for y,v in sorted(rows.items())}}


def progress_cells(image,completed):
    # Observe all31 cells in their screen positions, including pending cells.
    stripe=(110,1018,720,1040);crop=image.crop(stripe);key=(hashlib.blake2s(crop.tobytes(),digest_size=12).digest(),completed)
    if key in PROGRESS_CACHE:return PROGRESS_CACHE[key]
    blobs=components(binary(crop,223),min_pixels=20)
    require(len(blobs)==31,f'Actual progress cell count {len(blobs)} !=31')
    blobs.sort(key=lambda r:r['centroid_px'][0]);states=[]
    for i,b in enumerate(blobs):
        x,y=b['centroid_px'];gx=round(stripe[0]+x);gy=round(stripe[1]+y)
        pixel=image.getpixel((gx,gy));on=pixel[1]-pixel[0]>25 and pixel[2]-pixel[0]>25
        require(on==(i<completed),f'Progress prefix position wrong cell{i}: RGB{pixel}, completed={completed}')
        require(abs(gx-(130+19*i))<=1 and abs(gy-1030)<=1,'Progress cell position shifted')
        require(45<=b['area_px']<=85,'Progress dot area differs')
        states.append(bool(on))
    result={'completed':completed,'actual_prefix_states':states,'cells':blobs};PROGRESS_CACHE[key]=result;return result


class Timing:
    def __init__(self,plan):
        self.plan=plan;self.events=sorted(plan['events'],key=lambda e:e['start_s']);self.by={e['id']:e for e in self.events}
        self.counts=plan['counts'];self.values=independent_values();self.ends=[self.by[f'N{n:03}']['end_s'] for n in range(31)]
        self.intervals=[]
        for n in range(1,31):
            e=self.by[f'E{n:03}'];v=self.by[f'N{n:03}'];row=self.counts[n]
            next_events=[q['start_s'] for q in self.events if q['start_s']>=v['end_s'] and q['id'].startswith(('T','O'))]
            stop=min(next_events) if next_events else plan['duration_s']
            if n<30:stop=min(stop,self.counts[n+1]['cycle_start_s'])
            self.intervals.append((row['cycle_start_s'],stop,n))
        self.starts=[r[0] for r in self.intervals];self.frames=plan['frame_count']
    def active(self,f):
        t=f/FPS;i=bisect_right(self.starts,t)-1
        if i<0 or t>=self.intervals[i][1]:return None
        n=self.intervals[i][2];e=self.by[f'E{n:03}'];row=self.counts[n];op=row['operator_timing']
        if t<e['start_s']:stage='relay'
        elif t<op['multiply_commit_s']:stage='pending'
        elif t<row['result_display_start_s']:stage='product'
        else:stage='result'
        return n,stage


def decode(video,log,indices=None):
    filters=[]
    if indices is not None:
        def combine(v):
            if len(v)==1:return v[0]
            m=len(v)//2;return '('+combine(v[:m])+'+'+combine(v[m:])+')'
        filters.append('select='+combine([f'eq(n\\,{f})' for f in indices]))
    filters.append('format=rgb24')
    cmd=[str(ROOT/'.venv/bin/ffmpeg'),'-nostdin','-v','error','-xerror','-i',str(video),'-an','-vf',','.join(filters),'-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24','pipe:1']
    with Path(log).open('xb') as err,subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=err) as proc:
        iterator=indices if indices is not None else range(10000000)
        for f in iterator:
            raw=proc.stdout.read(1920*1080*3)
            if not raw and indices is None:break
            require(len(raw)==1920*1080*3,'Native decode short frame '+str(f))
            yield f,Image.frombytes('RGB',(1920,1080),raw)
        require(not proc.stdout.read(1) and proc.wait()==0,'Extra selected frames or failed decode')


def recheck(video,timeline,out,probe_only=False,expected_sha=VIDEO_SHA,revision='v007'):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);plan=json.loads(Path(timeline).read_text());t=Timing(plan)
    require(sha(video)==expected_sha,'Wrong explicitly bound input video')
    receipts={'video':{'path':str(video),'sha256':sha(video)},'timeline':{'path':str(timeline),'sha256':sha(timeline)},'checker':{'path':str(Path(__file__)),'sha256':sha(__file__)},'font':{'path':str(FONT),'sha256':sha(FONT)}}
    write(out/'inputs.json',receipts)
    indices=None
    if probe_only:
        selected=[at(e['start_s']+.2) for e in t.events if e['id'].startswith('N')]
        for n in range(1,31):
            row=t.counts[n];op=row['operator_timing']
            selected += [at(t.by[f'E{n:03}']['start_s']+.1),at(op['multiply_commit_s']+.03),at(op['divided_start_s']+.1)]
        for cue in ['I04','T000a','T000b','T000c','T015a','T020a']:
            e=t.by[cue]
            selected += [at(e['start_s']+u*(e['end_s']-e['start_s'])) for u in (.05,.25,.5,.9)]
        for n in [1,16,30]:selected += [at(t.counts[n]['cycle_start_s']+.55*u) for u in (.05,.5,.95)]
        indices=sorted(set(selected))
    counts=Counter();relays=[];runs_observed=[];last=None;start=None;first_results={};minimum=1;word_minimum=1;word_margin_minimum=1;frames=0;semantic_rows=[];unit_rows=[];pane_rows=[];destinations={};fades=[];clear_rgb=None;last_image=None;grammar_rows=[]
    with gzip.open(out/'native-observations.jsonl.gz','wt') as log:
        for f,image in decode(video,out/'native-decode.log',indices):
            frames+=1
            if clear_rgb is None:
                clear_rgb=image.getpixel((0,0));require(max(b-a for a,b in image.getextrema())<=1,'Initial whole frame does not clear uniformly')
            if f<=18 or f>=t.frames-24:fades.append(fade_observation(image,f,clear_rgb))
            if f==t.frames-1:
                require(fades[-1]['maximum_rgb_delta']<=3,'Final whole frame retains visible foreground');last_image=image.copy()
            if f<18 or f>=t.frames-24:continue
            p=progress_cells(image,bisect_right(t.ends,f/FPS));counts['progress_frames']+=1
            active=t.active(f);record={'frame':f,'progress':p['completed']}
            current_event=t.events[max(0,bisect_right([e['start_s'] for e in t.events],f/FPS)-1)];cue=current_event['id']
            grammar=grammar_labels(image,cue,active)
            if grammar:
                grammar_rows.append({'frame':f,'cue':cue,**grammar});counts['grammar_label_frames']+=1
            if cue in ('I04','I05','N000'):
                seed=verify_literal(image,(440,320,1480,428),96,'C(0)=1',119)
                counts['seed_frames']+=1;counts['independently_read_algebra_components']+=len(seed['glyphs'])
            if active is None and cue in ('T000a','T000b','T000c','T015a','T020a'):
                try:semantic_rows.append(new_scene_semantics(image,current_event,f,t,revision))
                except ValueError as error:
                    image.save(out/f'failed-frame-{f:05}.png');write(out/'failure-context.json',{'frame':f,'cue':cue,'active':active,'reason':str(error)});raise
                counts['semantic_scene_frames']+=1
            if cue=='T004a' and current_event['start_s']<=f/FPS<current_event['end_s']:
                u=clamp((f/FPS-current_event['start_s'])/(current_event['end_s']-current_event['start_s']))
                if .245<u<.28:unit_rows.append({'frame':f,'mode':'replay-source',**separated_units(image,'replay',70,14,5)})
                elif u>=.68:unit_rows.append({'frame':f,'mode':'replay-five-equal-shares',**separated_units(image,'replay',70,5,14)})
            if active:
                n,stage=active;expected=t.values[n] if stage=='result' else t.values[n-1]*(4*n-2) if stage=='product' else None
                if stage=='relay':
                    observed=read_number(image,CARD,tuple(range(59,113)));require(observed.get('value')==t.values[n-1] and observed['text']==f'{t.values[n-1]:,}','Wrong moving predecessor '+str(f))
                    relays.append({'frame':f,'n':n,**observed});counts['relay_frames']+=1
                else:
                    observed=read_number(image);require(observed['text']=='…' if stage=='pending' else observed.get('value')==expected,f'Actual numeric value wrong f{f}: {observed["text"]} expected {expected}')
                    if expected is not None:require(observed['text']==f'{expected:,}','Observed digit grouping/punctuation differs '+str(f))
                    algebra=observed_count_algebra(image,n,stage,f/FPS,t)
                    counts['independently_read_algebra_components']+=sum(len(r['glyphs']) for r in algebra)
                    if n not in destinations and stage!='result' and f/FPS<t.counts[n]['operator_timing']['divided_start_s']:
                        prefix=[]
                        for g in algebra[1]['glyphs']:
                            if g['text']=='×':break
                            prefix.append(g)
                        require(prefix,'No actual predecessor operand glyphs')
                        boxes=[g['visible_box_xyxy'] for g in prefix]
                        destinations[n]={'frame':f,'bbox':[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)],'observed_digits':''.join(g['text'] for g in prefix)}
                    if stage=='result':
                        english=read_english(image);require(english['value']==expected,f'Actual English reading value mismatch f{f}: {english["text"]}')
                        require(english['text']==canonical_cardinal(expected),'Observed English word sequence is not the approved natural cardinal '+str(f))
                        word_minimum=min([word_minimum]+[w['iou'] for w in english['words']]);word_margin_minimum=min([word_margin_minimum]+[w['other_character_margin'] for w in english['words']])
                        counts['english_frames']+=1;counts['recognized_words']+=len(english['words']);first_results.setdefault(n,f)
                        record['english']=english['text']
                    counts['numeric_frames']+=1
                    if n<=4:
                        op=t.counts[n]['operator_timing'];prev=t.values[n-1];factor=4*n-2;total=prev*factor
                        if op['multiply_commit_s']<=f/FPS<op['divided_start_s']:
                            unit_rows.append({'frame':f,'mode':'count-product','n':n,**separated_units(image,'main',total,factor,prev)})
                        elif op['equals_start_s']<=f/FPS<t.counts[n]['result_display_start_s']:
                            unit_rows.append({'frame':f,'mode':'count-equal-shares','n':n,**separated_units(image,'main',total,n+1,t.values[n])})
                    if revision!='v002' and n>=16:
                        pane=actual_panel_inset(image);require(abs(pane['left']-120)<=1,'Wide pane does not remain expanded')
                        pane_rows.append({'frame':f,'n':n,**pane})
                b=observed['visible_box_xyxy'];require(CARD[0]<=b[0] and b[2]<=CARD[2] and CARD[1]<=b[1] and b[3]<=CARD[3],'Actual numeral is clipped/outside card')
                current=(n,stage,observed['text']);record.update(n=n,stage=stage,observed=observed['text'])
                if current!=last:
                    if last is not None:runs_observed.append({'start_frame':start,'end_frame_exclusive':f,'state':last})
                    last=current;start=f
                counts['recognized_numeric_characters']+=len(observed['glyphs']);counts['recognized_decimal_digits']+=sum(g['text'].isdigit() for g in observed['glyphs']);minimum=min([minimum]+[g['iou'] for g in observed['glyphs']])
            log.write(json.dumps(record,ensure_ascii=False)+'\n')
            if f%900==0:print('native actual-pixel recheck',f,'/',t.frames,flush=True)
    if not probe_only:
        require(frames==t.frames,'Did not decode every frame')
        for n,f in first_results.items():require(f==at(t.counts[n]['result_display_start_s']),'Observed result update timing differs '+str(n))
        geometry=relay_geometry(relays,destinations,t);write(out/'relay-geometry.json',geometry)
        for region in ['title','lesson','actor','progress','whole']:
            beginning=[r['contrast'][region] for r in fades if r['frame']<=18]
            ending=[r['contrast'][region] for r in fades if r['frame']>=t.frames-24]
            require(all(a<=b+1 for a,b in zip(beginning,beginning[1:])) and all(a+1>=b for a,b in zip(ending,ending[1:])),f'Whole-region fade reverses unexpectedly: {region}')
        bad=last_image.copy();ImageDraw.Draw(bad).ellipse((396,996,404,1004),fill='#408d93')
        control=fade_observation(bad,t.frames-1,clear_rgb);require(control['maximum_rgb_delta']>3,'Residual-footer negative control not detected')
        bad.save(out/'negative-final-footer-residue.png')
        write(out/'fade-observations.json',{'passed':True,'decoded_clear_rgb':clear_rgb,'records':fades,'endpoint_rgb_quantization_tolerance':3,
                                          'negative_footer_residue_rejected':True,'negative_maximum_rgb_delta':control['maximum_rgb_delta']})
    if last is not None:runs_observed.append({'start_frame':start,'end_frame_exclusive':t.frames,'state':last})
    write(out/'observed-number-runs.json',runs_observed);write(out/'relay-observations.json',relays)
    write(out/'semantic-scenes.json',semantic_rows);write(out/'actual-unit-components.json',unit_rows);write(out/'wide-pane-observations.json',pane_rows);write(out/'grammar-labels.json',{'passed':True,'records':grammar_rows})
    report={'passed':True,'inputs':receipts,'all_native_frames_decoded':frames,'probe_only':probe_only,'counts':dict(counts),
            'minimum_independently_classified_glyph_iou':minimum,'actual_first_result_frames':first_results,
            'minimum_classified_word_iou':word_minimum,'minimum_word_class_margin':word_margin_minimum,
            'frame_scope':'All native frames decoded; opacity-complete18439frames classified. Initial18/final24fade frames are measured separately.',
            'recognition':'Each observed digit and English word chosen without providing the expected numeral/string to classifier; mathematical value compared only afterward',
            'revision':revision,'separated_unit_frames':len(unit_rows),'scene_semantics_frames':len(semantic_rows),'wide_pane_frames':len(pane_rows),
            'scope':'Core numeric/product/result + general equations/coefficient/index symbols + English number words + all31 progress cells; all moving predecessor numerals; separate point components/area; corrected scene semantics'}
    write(out/'recheck.json',report);return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--video',type=Path,default=DEFAULT_VIDEO);p.add_argument('--timeline',type=Path,default=DEFAULT_TIMELINE)
    p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--probe-only',action='store_true');p.add_argument('--expected-sha256',required=True)
    p.add_argument('--revision',choices=['v002','v003','v004','v005','v006','v007'],default='v007');a=p.parse_args()
    print(json.dumps(recheck(a.video,a.timeline,a.out_dir,a.probe_only,a.expected_sha256,a.revision),ensure_ascii=False))


if __name__=='__main__':main()
