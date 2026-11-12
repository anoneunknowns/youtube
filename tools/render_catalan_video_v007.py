"""Catalan episode: measured speech, exact arithmetic and moving ribbon paths.

The retained preproduction files are immutable inputs. Static plates and glyphs
are cached; animated points, traced paths, operand transfers and registered
character acting are composed per frame. Planning previews never adopt audio.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import asdict, dataclass
from functools import lru_cache
import gzip
import hashlib
import importlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import time

from PIL import Image, ImageDraw, ImageFont

try:
    from component_alignment import raster_centering_report
except ModuleNotFoundError:
    from tools.component_alignment import raster_centering_report

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/catalan-counting-v1'
BG = DESIGN / 'generation-batches/catalan-20261112-01a1cd57/source/ribbon-courtyard-clean-plate.png'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
SIZE, FPS = (1920, 1080), 30
VIDEO_NAME = 'paspla-studio-catalan-numbers-c0-to-c30-1080p.mp4'
INK, MUTED, TEAL, CORAL, GOLD = '#604934', '#7a6c5e', '#408d93', '#d87d61', '#dca449'
CREAM, EDGE = '#fffaf0', '#d9c9ae'
EXPRESSION_BOX = (270, 268, 1650, 342)
NUMBER_BOX = (260, 405, 1660, 505)
READING_BOX = (270, 724, 1650, 804)
PROGRESS_BOX = (110, 968, 720, 1044)
INTRO_WORD_TIMING = DESIGN / 'timing-revisions/intro-word-timing-v001.json'


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def resolve(path):
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def receipt(path):
    p = Path(path).resolve()
    try:
        name = str(p.relative_to(ROOT))
    except ValueError:
        name = str(p)
    return {'path': name, 'sha256': sha(p)}


def ffbin(name):
    p = ROOT / '.venv/bin' / name
    return str(p) if p.exists() else shutil.which(name)


def clamp(x): return min(1., max(0., x))
def smooth(x):
    x = clamp(x)
    return x*x*(3-2*x)


@lru_cache(maxsize=128)
def font(size): return ImageFont.truetype(str(FONT), size)


def visible(layer):
    return layer.getchannel('A').point(lambda a: 255 if a >= 128 else 0).getbbox()


@lru_cache(maxsize=2048)
def text_layer(text, size, color=INK):
    b = font(size).getbbox(text)
    layer = Image.new('RGBA', (b[2]-b[0]+40, b[3]-b[1]+40))
    ImageDraw.Draw(layer).text((20-b[0], 20-b[1]), text, font=font(size), fill=color)
    return layer


def wrap(text, size=30, width=1360):
    lines, part = [], ''
    for word in text.split():
        trial = (part+' '+word).strip()
        if part and font(size).getlength(trial) > width:
            lines.append(part); part = word
        else:
            part = trial
    if part: lines.append(part)
    return lines


@lru_cache(maxsize=128)
def multiline(text, size=30, width=1360, color=MUTED):
    pieces = [text_layer(s, size, color) for s in wrap(text, size, width)]
    bs = [visible(p) for p in pieces]
    w = max(b[2]-b[0] for b in bs)
    h = sum(b[3]-b[1] for b in bs) + 10*(len(bs)-1)
    out = Image.new('RGBA', (w+40, h+40)); y = 20
    for piece, b in zip(pieces, bs):
        out.alpha_composite(piece, (20+round((w-b[2]+b[0])/2)-b[0], y-b[1]))
        y += b[3]-b[1]+10
    return out


class Canvas:
    def __init__(self, image, name):
        self.image = image.copy(); self.draw = ImageDraw.Draw(self.image)
        self.name, self.records = name, []

    def panel(self, box, fill=CREAM, radius=27):
        self.draw.rounded_rectangle(box, radius, fill=fill, outline=EDGE, width=2)

    def center(self, layer, box, ident):
        b = visible(layer)
        if b is None: raise ValueError('Empty '+ident)
        xy = (round((box[0]+box[2]-b[0]-b[2])/2), round((box[1]+box[3]-b[1]-b[3])/2))
        rec = raster_centering_report(layer, box, origin_xy=xy, name=ident, tolerance_px=.5)
        if not rec['passed']: raise ValueError(rec)
        rec.update(component_id=ident, horizontal='center', vertical='center')
        self.records.append(rec); self.image.alpha_composite(layer, xy)
        return rec

    def text(self, text, box, size=36, color=INK, ident='text'):
        rec = self.center(text_layer(text, size, color), box, ident)
        rec.update(text=text, font_size_px=size)
        return rec


def add_header(c, subtitle):
    c.panel((350, 25, 1570, 135))
    c.text('CATALAN NUMBERS', (380, 40, 1540, 89), 42, ident='title')
    c.text('NUM-NUM NUMBERS  ·  '+subtitle, (380, 99, 1540, 122), 20, MUTED, 'subtitle')


@lru_cache(maxsize=64)
def operand_center(previous,factor,size):
    expression=f'{previous:,} × {factor}';prefix=f'{previous:,}'
    full=text_layer(expression,size);b=visible(full)
    origin=(round((EXPRESSION_BOX[0]+EXPRESSION_BOX[2]-b[0]-b[2])/2),
            round((EXPRESSION_BOX[1]+EXPRESSION_BOX[3]-b[1]-b[3])/2))
    metric=font(size).getbbox(expression);part=Image.new('RGBA',full.size)
    ImageDraw.Draw(part).text((20-metric[0],20-metric[1]),prefix,font=font(size),fill=INK)
    pb=visible(part)
    return (origin[0]+(pb[0]+pb[2])/2,origin[1]+(pb[1]+pb[3])/2)


def centered_path(c, word, box, ident, progress=1, highlight=False, unit=None):
    heights = [0]
    for s in word: heights.append(heights[-1]+(1 if s == 'U' else -1))
    if min(heights) < 0 or heights[-1] != 0: raise ValueError('Invalid teaching path '+word)
    natural_h = max(1, max(heights))
    if unit is None:
        unit = min((box[2]-box[0]-60)/max(1,len(word)), (box[3]-box[1]-45)/natural_h)
    width = len(word)*unit
    left = (box[0]+box[2]-width)/2
    top = (box[1]+box[3]-natural_h*unit)/2
    baseline = top+natural_h*unit
    points = [(left+i*unit,baseline-v*unit) for i,v in enumerate(heights)]
    c.draw.line((left,baseline,left+width,baseline), fill='#b9b0a0', width=3)
    first = next((i for i,v in enumerate(heights[1:],1) if v == 0),len(word))
    extent = len(word)*clamp(progress)
    for k in range(min(len(word), math.ceil(extent))):
        frac = min(1, extent-k)
        if frac <= 0: continue
        a,b = points[k],points[k+1]
        end = (a[0]+(b[0]-a[0])*frac,a[1]+(b[1]-a[1])*frac)
        color = (GOLD if k in (0,first-1) else TEAL if k<first else CORAL) if highlight else TEAL
        c.draw.line((a,end), fill=color, width=9)
        if k == math.ceil(extent)-1:
            c.draw.ellipse((end[0]-7,end[1]-7,end[0]+7,end[1]+7), fill=GOLD)
    if not word: c.draw.ellipse((left-4,baseline-4,left+4,baseline+4),fill=INK)
    for i,(x,y) in enumerate(points):
        if i <= extent: c.draw.ellipse((x-3,y-3,x+3,y+3),fill=INK)
    tip_index=min(len(word)-1,max(0,int(extent))) if word else 0
    if word:
        fraction=clamp(extent-tip_index);a,b=points[tip_index],points[tip_index+1]
        tip=(a[0]+(b[0]-a[0])*fraction,a[1]+(b[1]-a[1])*fraction)
    else:tip=points[0]
    return {'id':ident,'word':word,'first_return_step':first,'progress':clamp(progress),'points':points,'tip':tip,
            'horizontal':'path group center','vertical':'path group center','content_box':box}


def planning_plan():
    authored = json.loads((DESIGN/'narration.json').read_text())
    events = [{**e,'start_s':e['planning_window_seconds'][0], 'end_s':e['planning_window_seconds'][1],
               'duration_s':e['planning_window_seconds'][1]-e['planning_window_seconds'][0]} for e in authored]
    by = {e['id']:e for e in events}; counts = []
    for n in range(31):
        v=by[f'N{n:03}'];e=by.get(f'E{n:03}')
        d=e['duration_s'] if e else 0
        counts.append({'index':n,'value':str(math.comb(2*n,n)//(n+1)),
                       'cycle_start_s':e['start_s']-.55 if e else v['start_s']-.12,
                       'formula_start_s':e['start_s'] if e else None,
                       'result_display_start_s':v['start_s']-.12,
                       'voice_start_s':v['start_s'],'voice_end_s':v['end_s'],
                       'operator_timing':{'times_start_s':e['start_s']+d*.45,
                           'divided_start_s':e['start_s']+d*.70,
                           'equals_start_s':e['start_s']+d*.92,
                           'multiply_commit_s':e['start_s']+d*.70-.10} if e else {}})
    duration=events[-1]['end_s']+1.8
    return {'events':events,'counts':counts,'duration_s':duration,'frame_count':math.ceil(duration*FPS),
            'fps':FPS,'preview_plan_only':True,'timing_status':'unmeasured planning preview only'}


@dataclass(frozen=True)
class State:
    mode: str
    n: int
    stage: str
    cue: str
    completed: int
    progress: float
    local_s: float
    scene_start_s: float
    scene_end_s: float


class Episode:
    def __init__(self, timeline=None, background=None, allow_preview_character=False, character_registration=None):
        self.timeline_path=Path(timeline) if timeline else None
        self.plan=json.loads(Path(timeline).read_text()) if timeline else planning_plan()
        self.events=sorted(self.plan.get('events',self.plan.get('voice_events',[])),key=lambda e:e['start_s'])
        self.by={e['id']:e for e in self.events};self.starts=[e['start_s'] for e in self.events]
        if len(self.by)!=86:raise ValueError('All86 authored speech cues are required')
        self.intro_word_timing=json.loads(INTRO_WORD_TIMING.read_text())
        if self.by['T000a']['source_sha256']!=self.intro_word_timing['source_audio']['sha256']:
            raise ValueError('Intro word timing belongs to a different voice source')
        for dep in self.intro_word_timing['evidence']:
            if sha(resolve(dep['path']))!=dep['sha256']:raise ValueError('Intro word evidence changed')
        self.counts=self.plan.get('counts',self.plan.get('counted_states',[]))
        self.counts=sorted(self.counts,key=lambda r:r['index'])
        if len(self.counts)!=31:raise ValueError('All31 counted states are required')
        self.rows=json.loads((DESIGN/'math/count-values.json').read_text())['rows']
        for n,row in enumerate(self.rows):
            if int(row['value'])!=math.comb(2*n,n)//(n+1):raise ValueError('Design math changed')
            if str(self.counts[n]['value'])!=row['value']:raise ValueError('Timeline math changed')
        self.duration=float(self.plan['duration_s']);self.frame_count=int(self.plan.get('frame_count',self.plan.get('duration_frames',math.ceil(self.duration*FPS))))
        if int(self.plan.get('fps',FPS))!=FPS:raise ValueError('1080p30 timeline required')
        self.ends=[c['voice_end_s'] for c in self.counts]
        self.bg_path=resolve(background) if background else BG
        self.background=Image.open(self.bg_path).convert('RGBA').resize(SIZE,Image.Resampling.LANCZOS)
        self.preview_character=allow_preview_character
        try:
            self.animation=importlib.import_module('catalan_animation_v003' if not __package__ else 'tools.catalan_animation_v003')
            actor_plan={**self.plan,'voice_events':self.events}
            self.actor_configuration=self.animation.configure_animation(actor_plan,registration_path=character_registration)
        except (ModuleNotFoundError, FileNotFoundError):
            if not allow_preview_character:raise
            self.animation=None
        if self.animation is None:
            self.preview_module=importlib.import_module('render_catalan_mockups' if not __package__ else 'tools.render_catalan_mockups')
            self.preview_art=self.preview_module.Tora()
            self.actor_configuration=None
        self.bound_inputs=[receipt(self.bg_path),receipt(FONT),receipt(Path(__file__)),
                           receipt(DESIGN/'math/count-values.json'),receipt(DESIGN/'narration.json')]
        if self.timeline_path:self.bound_inputs.append(receipt(self.timeline_path))
        self.bound_inputs += [receipt(INTRO_WORD_TIMING)] + self.intro_word_timing['evidence']
        if self.animation:
            self.bound_inputs.append(receipt(Path(self.animation.__file__)))
            self.bound_inputs.append(self.actor_configuration['artwork']['registration'])
        self.native_records={};self.motion_examples={};self.frame_rows=[]

    def event_at(self,t):
        return self.events[max(0,bisect_right(self.starts,t)-1)]

    def state(self,frame):
        t=frame/FPS;event=self.event_at(t);cue=event['id'];n=int(event.get('index',0) or 0)
        start,end=event['start_s'],event['end_s'];u=clamp((t-start)/max(.001,end-start))
        complete=bisect_right(self.ends,t)
        # Operands move only after the preceding result/lesson has finished.
        for k in range(1,31):
            e=self.by[f'E{k:03}'];v=self.by[f'N{k:03}'];cs=self.counts[k]
            cycle=cs.get('cycle_start_s',e['start_s']-.55)
            next_lesson=next((x for x in self.events if x['start_s']>=v['end_s'] and x['id'].startswith(('T','O'))),None)
            stop=next_lesson['start_s'] if next_lesson else self.duration
            if k<30:stop=min(stop,self.counts[k+1].get('cycle_start_s',self.by[f'E{k+1:03}']['start_s']-.55))
            if cycle<=t<stop:
                op=cs.get('operator_timing',e.get('operator_timing',{}));d=e['end_s']-e['start_s']
                ts=op.get('times_start_s',e['start_s']+d*.45)
                ds=op.get('divided_start_s',e['start_s']+d*.70)
                eq=op.get('equals_start_s',e['start_s']+d*.92)
                mc=op.get('multiply_commit_s',ds-.10)
                commit=cs.get('result_display_start_s',cs.get('result_start_s',v['start_s']-.12))
                if t<e['start_s']:stage='relay';p=smooth((t-cycle)/max(.001,e['start_s']-cycle))
                elif t<ts:stage='input';p=clamp((t-e['start_s'])/max(.001,ts-e['start_s']))
                elif t<mc:stage='multiply';p=clamp((t-ts)/max(.001,mc-ts))
                elif t<ds:stage='product';p=1
                elif t<commit:stage='divide';p=clamp((t-ds)/max(.001,eq-ds))
                else:stage='result';p=1
                return State('count',k,stage,f'N{k:03}' if t>=v['start_s'] else f'E{k:03}',complete,round(p,5),t-e['start_s'],cycle,stop)
        if cue.startswith('I'):
            mode='seed' if cue in ('I04','I05') else 'intro'
        elif cue=='N000':mode='seed';n=0
        elif cue.startswith('T000'):mode='coefficient'
        elif cue=='T001a':mode='two_ones';n=1
        elif cue in ('T001b','T002a'):mode='path_example';n=1 if cue=='T001b' else 2
        elif cue.startswith('T003'):mode='five_paths' if cue=='T003a' else 'first_return';n=3
        elif cue=='T004a':mode='equal_groups';n=4
        elif cue=='T004b':mode='recurrence';n=4
        elif cue in ('O01','O02'):mode='history' if cue=='O01' else 'ending';n=30
        elif cue.startswith('T'):mode='milestone'
        else:mode='seed'
        if mode=='milestone' and cue=='T015a':n=15
        return State(mode,n,'lesson',cue,complete,round(u,5),t-start,start,end)

    @lru_cache(maxsize=24)
    def plate(self,n,stage):
        row=self.rows[n];wide=n>=16;c=Canvas(self.background,f'{n}/{stage}')
        add_header(c,f'PAIR COUNT  n = {n}')
        c.text('C(n) = C(n − 1) × (4n − 2) ÷ (n + 1)',(265,158,1655,216),44,MUTED,'general-equation')
        c.panel((120,240,1800,710) if wide else (230,240,1690,710))
        expression_box=(150,268,1770,342) if wide else EXPRESSION_BOX
        number_box=(150,405,1770,505) if wide else NUMBER_BOX
        prev=int(row['previous_value']);factor=row['numerator_factor'];divisor=row['divisor'];product=int(row['multiplication_product'])
        if stage=='result':
            c.text(f'{prev:,} × {factor} ÷ {divisor}',expression_box,50 if wide else 64,MUTED,'result-formula-input')
            c.text('=',(900,353,1020,395),44,MUTED,'equals')
            c.text(row['display_value'],number_box,82 if wide else 112,TEAL,'committed-result')
            c.text(f'C({n})  ·  {n} {"PAIR" if n==1 else "PAIRS"}',(550,591,1370,653),35,INK,'result-index')
            c.panel((130,716,1790,812) if wide else (240,716,1680,812),radius=18)
            rec=c.center(multiline(row['text'],30,1360),(160,724,1760,804) if wide else READING_BOX,'result-reading')
            rec.update(text=row['text'],font_size_px=30,group='whole multiline glyph group')
        else:
            if stage=='divide':expression=f'{product:,} ÷ {divisor}'
            else:expression=f'{prev:,} × {factor}'
            c.text(expression,expression_box,56 if wide and stage=='divide' else 59 if wide else 76,
                   CORAL if stage=='divide' else INK,'operation-input')
            c.text('DIVIDE INTO EQUAL SHARES' if stage=='divide' else 'MULTIPLY FIRST',
                   (590,354,1330,391),24,CORAL if stage=='divide' else TEAL,'operation-label')
            c.text(f'4 × {n} − 2 = {factor}',(252,354,580,395),23,MUTED,'coefficient-factor')
            c.text(f'{n} + 1 = {divisor}',(1345,354,1667,395),23,MUTED,'coefficient-divisor')
            committed=stage in ('product','divide')
            c.text(f'{product:,}' if committed else '…',number_box,69 if wide else 102,TEAL,'intermediate-product')
            c.text('WHOLE PRODUCT' if committed else 'CALCULATING THE WHOLE PRODUCT',
                   (480,500,1440,531),22,MUTED,'intermediate-label')
            if n>4:
                c.text('VALUE WINDOWS  ·  RIBBONS SHOW THE CALCULATION',(330,665,1590,696),20,MUTED,'symbolic-note')
        self.native_records[f'count-{n}-{stage}']=c.records
        return c.image, c.records

    def progress(self,c,completed):
        c.panel((100,962,730,1050),radius=15)
        layer=Image.new('RGBA',(600,94));d=ImageDraw.Draw(layer)
        line=text_layer(f'{completed} / 31 VALUES',24,MUTED);b=visible(line)
        layer.alpha_composite(line,(round((600-b[2]+b[0])/2)-b[0],4-b[1]))
        for k in range(31):
            x=14+k*19;d.ellipse((x-4,51,x+4,59),fill=TEAL if k<completed else '#cfbda3')
        c.center(layer,PROGRESS_BOX,'completed-values')

    def exact_points(self,c,n,stage,p):
        row=self.rows[n];previous=int(row['previous_value']);factor=row['numerator_factor'];total=previous*factor
        divisor=row['divisor'];value=int(row['value'])
        if total>70:raise ValueError('Large values must use symbolic flow')
        count=total if stage in ('product','divide') else previous*min(factor,math.floor(factor*clamp(p))) if stage=='multiply' else 0
        for k in range(count):
            a=(960+(k%previous-(previous-1)/2)*28,602+(k//previous-(factor-1)/2)*8)
            b=(960+(k%value-(value-1)/2)*70,602+(k//value-(divisor-1)/2)*24)
            u=smooth(p) if stage=='divide' else 0
            x=a[0]+(b[0]-a[0])*u;y=a[1]+(b[1]-a[1])*u
            c.draw.ellipse((x-3,y-3,x+3,y+3),fill=TEAL if stage=='divide' else CORAL)
        if stage in ('multiply','product'):
            label=f'{factor} groups of {previous}'
        else:label=f'{divisor} equal shares'
        c.text(label,(460,669,1460,696),20,MUTED,'exact-unit-meaning')
        return {'actual_units':count,'whole_product':total,'groups':divisor if stage=='divide' else factor,
                'point_motion_progress':p if stage=='divide' else 0}

    def symbolic_flow(self,c,n,stage,p):
        row=self.rows[n];factor=row['numerator_factor'];divisor=row['divisor']
        boxes=[(450,552,700,636),(835,552,1085,636),(1220,552,1470,636)]
        labels=[f'× {factor}','WHOLE',f'÷ {divisor}']
        active=2 if stage=='divide' else 1 if stage=='product' else 0
        for i,(box,label) in enumerate(zip(boxes,labels)):
            c.panel(box,fill='#f2dfb8' if i==active else '#f8f0df',radius=17)
            c.text(label,(box[0]+12,box[1]+13,box[2]-12,box[3]-13),30 if i!=1 else 25,
                   CORAL if stage=='divide' and i==active else TEAL if i==active else MUTED,f'flow-port-{i}')
        c.draw.line((712,594,822,594),fill=EDGE,width=4);c.draw.line((1097,594,1207,594),fill=EDGE,width=4)
        if stage in ('multiply','divide'):
            x=(712 if stage=='multiply' else 1097)+110*smooth(p)
            c.draw.ellipse((x-9,585,x+9,603),fill=GOLD)
        return {'symbolic':True,'decorative_marker_is_not_counted_units':True,'operator_highlight':stage}

    def count_scene(self,state):
        n,stage,p=state.n,state.stage,state.progress
        base_stage='multiply' if stage in ('relay','input','multiply') else stage
        image,records=self.plate(n,base_stage)
        c=Canvas(image,f'count-{n}-{stage}');c.records=list(records);data={}
        if stage=='relay':
            # Mask the next operand until its retained predecessor reaches it.
            c.draw.rectangle((235,245,1685,705),fill=CREAM)
            c.records=[r for r in c.records if r['component_id'] in ('title','subtitle','general-equation')]
            wide=n>=16
            # Explicit parentheses avoid individual-value font fitting.
            start_size=82 if n-1>=16 else 112;end_size=59 if wide else 76
            size=round(start_size+(end_size-start_size)*p)
            goal=operand_center(int(self.rows[n-1]['value']),self.rows[n]['numerator_factor'],end_size)
            cx=960+(goal[0]-960)*p;cy=455+(goal[1]-455)*p
            half_width=min(cx-280,1640-cx)
            c.text(self.rows[n-1]['display_value'],(cx-half_width,cy-62,cx+half_width,cy+62),size,TEAL,'transferred-previous')
            data={'transfer_progress':p,'previous_value':self.rows[n-1]['value'],'font_transition':[start_size,end_size]}
        elif stage!='result':
            if n<=4:data=self.exact_points(c,n,stage,p)
            else:data=self.symbolic_flow(c,n,stage,p)
            # The spoken operator lights independently of the diagram.
            if stage in ('multiply','divide','product'):
                color=CORAL if stage=='divide' else TEAL
                c.draw.rounded_rectangle((590,349,1330,396),13,outline=color,width=3)
        data.update(index=n,stage=stage,value=self.rows[n]['value'],product=self.rows[n]['multiplication_product'])
        return c,data

    def replay_points(self,c,u):
        # Each of the70 retained units has one identity and a continuous path.
        move=smooth((u-.28)/.40);amount=5*min(14,math.floor(14*clamp(u/.24)))
        for k in range(amount):
            a=(960+(k%5-2)*55,428+(k//5-6.5)*22)
            b=(960+(k%14-6.5)*80,428+(k//14-2)*48)
            # Antisymmetric arcs preserve the whole group's center.
            arc=math.sin(math.pi*move)*30*(1 if k%2 else -1)
            x=a[0]+(b[0]-a[0])*move;y=a[1]+(b[1]-a[1])*move+arc
            color=TEAL if u>=.68 and k//14==min(4,int((u-.68)/.32*5)) else CORAL if u<.68 else '#c9ac7e'
            c.draw.ellipse((x-6,y-6,x+6,y+6),fill=color)
        c.text('5 × 14 = '+('70' if u>=.24 else '…'),(450,200,1470,265),54,TEAL,'replay-product')
        c.text('14 groups of 5' if u<.28 else '70 units move into 5 equal shares' if u<.68 else '70 ÷ 5 = 14 in each share',
               (300,638,1620,698),35,MUTED,'replay-share-label')
        return {'unit_count':amount,'units_after_build':70,'continuous_identity_count':70,
                'rearrangement_progress':move,'source_groups':14,'source_group_size':5,'destination_groups':5,'destination_group_size':14,
                'actual_counted_units':True}

    def lesson_scene(self,state):
        mode,n,cue,u=state.mode,state.n,state.cue,state.progress
        c=Canvas(self.background,mode+'/'+cue);data={};add_header(c,{
            'intro':'RIBBON COURTYARD','seed':'ZERO PAIRS  ·  ONE EMPTY PATH','coefficient':'THE EXACT EQUATION',
            'two_ones':'SAME VALUE  ·  DIFFERENT PLACES','path_example':f'{n} {"PAIR" if n==1 else "PAIRS"}',
            'five_paths':'ALL FIVE PATHS  ·  REPLAY C(3)','first_return':'FIRST RETURN  ·  REPLAY C(3)',
            'equal_groups':'EXACT INTEGER SHARES  ·  REPLAY C(4)','recurrence':'TWO RULES  ·  SAME SEQUENCE',
            'milestone':f'REPLAY C({n})  ·  COUNTING WAYS','history':'ALL 31 VALUES  ·  KEEP BOTH ONES',
            'ending':'THANKS FOR COUNTING CATALAN NUMBERS'}.get(mode,mode.upper()))
        if mode=='intro':
            if cue=='I01':
                c.text('How many paths can a ribbon make?',(240,177,1680,245),48,ident='intro-question')
                for i,word in enumerate(['UDUDUD','UUDUDD','UUUDDD']):
                    path=centered_path(c,word,(250+i*470,315,670+i*470,525),f'intro-{i}',clamp(u*3-i))
                    if i==min(2,int(u*3)):data['gaze_target']=path['tip']
                c.text('UP  ·  DOWN  ·  BACK TO THE LINE',(350,585,1570,636),31,MUTED,'intro-rule')
            elif cue in ('I02','I03'):
                c.panel((300,175,1620,650));word='UUDDUD' if cue=='I02' else 'UD'
                data['path']=centered_path(c,word,(420,220,1500,530),'rule-path',clamp(u*1.2),highlight=cue=='I03')
                c.text('Never below the line' if cue=='I02' else '1 UP + 1 DOWN = 1 PAIR',
                       (350,565,1570,625),38,MUTED,'path-rule')
            else:
                c.text('FROM C(0) TO C(30)',(300,190,1620,270),65,TEAL,'route')
                c.text('31 places  ·  each has its own value',(260,330,1660,400),43,MUTED,'route-count')
                for i,word in enumerate(['UD','UUDD','UUUDDD']):centered_path(c,word,(300+i*450,470,690+i*450,650),f'route-path-{i}',clamp(u*1.5))
        elif mode=='seed':
            c.panel((400,195,1520,650));c.text('0 PAIRS',(600,226,1320,283),43,MUTED,'seed-index')
            c.text('C(0) = 1',(440,320,1480,428),96,TEAL,'seed-value')
            c.draw.ellipse((954,483,966,495),fill=INK)
            c.text('one empty path',(500,546,1420,605),43,MUTED,'empty-path')
        elif mode=='coefficient':
            c.panel((220,190,1700,680))
            c.text('C(n) = C(n − 1) × (4n − 2) ÷ (n + 1)',(260,217,1660,298),47,INK,'rule-formula')
            if cue=='T000a':
                multiply_at=self.intro_word_timing['multiply_start_offset_s']
                divide_at=self.intro_word_timing['then_start_offset_s']
                divide_started=state.local_s>=divide_at
                step=1 if divide_started else 0 if state.local_s>=multiply_at else None
                flow_progress=(clamp((state.local_s-divide_at)/(state.scene_end_s-state.scene_start_s-divide_at))
                               if divide_started else clamp((state.local_s-multiply_at)/(divide_at-multiply_at)))
                active=2 if divide_started else 1 if step==0 else 0
            else:
                split=4.26/max(.001,state.scene_end_s-state.scene_start_s) if cue=='T000b' else .5
                divide_started=u>=split
                step=1 if divide_started else 0
                flow_progress=clamp((u-split)/(1-split)) if divide_started else clamp(u/split)
                active=2 if divide_started else 1
            cards=[((260,350,620,550),'LAST VALUE','C(n − 1)',43),
                   ((700,350,1220,550),'WHOLE PRODUCT','C(n − 1) × (4n − 2)',30),
                   ((1300,350,1660,550),'NEXT VALUE','C(n)',48)]
            for i,(box,title,label,size) in enumerate(cards):
                x,y,right,bottom=box
                c.panel(box,fill='#f2dfb8' if i==active else CREAM)
                c.text(title,(x+12,369,right-12,415),27,MUTED,f'rule-title-{i}')
                c.text(label,(x+15,452,right-15,513),size,TEAL,f'rule-input-{i}')
            for i,(left,right,label,color) in enumerate([(630,690,'× (4n − 2)',TEAL),(1230,1290,'÷ (n + 1)',CORAL)]):
                y=452;c.draw.line((left,y,right-8,y),fill=color,width=5)
                c.draw.polygon([(right-8,y-9),(right,y),(right-8,y+9)],fill=color)
                cx=(left+right)/2
                c.text(label,(cx-210,566,cx+210,605),27,color,f'rule-operation-{i}')
                # Only the currently explained operation transports a highlight.
                # The divider never starts while the product is being introduced.
                if i==step:
                    px=left+(right-left-12)*flow_progress
                    c.draw.ellipse((px-5,y-5,px+5,y+5),fill=GOLD)
            c.text('VALUE WINDOWS  ·  EXACT INTEGERS',(320,624,1600,660),26,MUTED,'rule-note')
            data.update(value_window_roles=['previous value','whole multiplication product','next Catalan value'],
                        operation_order=['multiply','divide'],active_operation='divide' if step==1 else 'multiply' if step==0 else None,
                        operation_progress=flow_progress,
                        gaze_target=([(440,470),(960,470),(1480,470)][active] if cue=='T000a'
                                     else (1480,470) if cue=='T000b' and divide_started else (960,470)))
        elif mode=='two_ones':
            for i,(idx,word,label) in enumerate([(0,'','0 PAIRS'),(1,'UD','1 PAIR')]):
                x=350+i*650;c.panel((x,190,x+570,625));c.text(f'C({idx}) = 1',(x+20,218,x+550,320),78,TEAL,'one-'+str(idx))
                centered_path(c,word,(x+50,370,x+520,490),'one-path-'+str(idx),clamp(u*2-i*.3))
                c.text(label,(x+20,545,x+550,595),31,MUTED,'one-index-'+str(idx))
            data['two_initial_ones_preserved']=True
        elif mode=='path_example':
            words=['UD'] if n==1 else ['UUDD','UDUD']
            for i,word in enumerate(words):
                box=(420,210,1500,540) if n==1 else (260+i*760,210,900+i*760,540)
                c.panel((box[0]-20,box[1]-15,box[2]+20,620));centered_path(c,word,box,f'example-{i}',clamp(u*len(words)-i))
                c.text(f'{i+1} WAY' if n==1 else f'PATH {i+1}',(box[0],558,box[2],605),34,MUTED,'example-label-'+str(i))
            data['paths']=words
        elif mode=='five_paths':
            words=['UUUDDD','UUDUDD','UUDDUD','UDUUDD','UDUDUD']
            for i,word in enumerate(words):
                x=245+(i%3)*490;y=175+(i//3)*235;c.panel((x,y,x+450,y+215))
                centered_path(c,word,(x+25,y+20,x+425,y+157),f'all-five-{i}',clamp(u*6-i),True)
                c.text(str(i+1),(x+25,y+168,x+425,y+202),27,MUTED,'path-id-'+str(i))
            c.text('C(3) = 5',(1260,444,1660,585),68,TEAL,'five-total')
            c.text('ALL FIVE  ·  EACH APPEARS ONCE',(380,680,1540,725),31,MUTED,'five-complete')
            data['paths']=words
        elif mode=='first_return':
            if cue=='T003b':
                path=centered_path(c,'UUDDUD',(410,170,1510,415),'first-return',1,True)
                # Preserve each segment's identity as A descends to its own
                # baseline and B moves alongside it. They are ordered copies.
                rise=smooth(u)
                c.panel((370,457,940,687));c.panel((980,457,1550,687))
                for letter,source,target,color in [
                    ('A',path['points'][1:4],[(575,604),(655,524),(735,604)],TEAL),
                    ('B',path['points'][4:7],[(1185,604),(1265,524),(1345,604)],CORAL)]:
                    points=[(a[0]+(b[0]-a[0])*rise,a[1]+(b[1]-a[1])*rise) for a,b in zip(source,target)]
                    c.draw.line(points,fill=color,width=9)
                    if rise>.8:c.draw.line((target[0],target[-1]),fill='#b9b0a0',width=3)
                data['gaze_target']=(655,550) if u<.5 else (1265,550)
                c.text('INSIDE A  ·  1 PAIR',(400,641,910,676),24,TEAL,'inside-name')
                c.text('AFTER B  ·  1 PAIR',(1010,641,1520,676),24,CORAL,'after-name')
                data['decomposition']='U A D B'
            else:
                groups=[['UDUUDD','UDUDUD'],['UUDDUD'],['UUUDDD','UUDUDD']]
                active=0 if cue=='T003c' else 1 if cue=='T003d' and u<.48 else 2 if cue=='T003d' else -1
                for k,words in enumerate(groups):
                    x=250+k*480;c.panel((x,180,x+460,590),fill='#f2dfb8' if k==active else CREAM)
                    c.text(f'{k} INSIDE  ·  {2-k} AFTER',(x+15,197,x+445,242),25,MUTED,'group-pairs-'+str(k))
                    for i,word in enumerate(words):centered_path(c,word,(x+35,265+i*127,x+425,371+i*127),f'group-{k}-{i}',clamp(u*2),True)
                    c.text(['1 × 2 = 2','1 × 1 = 1','2 × 1 = 2'][k],(x+15,527,x+445,572),39,TEAL,'group-product-'+str(k))
                c.text('C(3) = 2 + 1 + 2 = 5',(280,647,1640,721),57,TEAL,'convolution-total')
                data.update(groups=groups,products=[2,1,2],sum=5,ordered=True)
                data['gaze_target']=(480+480*max(0,active),355)
        elif mode=='equal_groups':
            c.panel((260,175,1660,724));data.update(self.replay_points(c,u))
        elif mode=='recurrence':
            c.panel((250,195,1670,685))
            c.text('C(3) = 2 + 1 + 2 = 5',(290,240,1630,320),60,TEAL,'path-rule')
            c.text('C(4) = 5 × 14 ÷ 5 = 14',(290,390,1630,480),57,CORAL,'arithmetic-rule')
            c.text('SAME CATALAN SEQUENCE',(300,568,1620,641),45,INK,'same-sequence')
        elif mode=='milestone':
            expansion=smooth(u/.65) if cue=='T015a' else 1 if n>=16 else 0
            inset=round(230-110*expansion)
            c.panel((inset,190,1920-inset,705));row=self.rows[n]
            c.text(f'C({n})',(560,220,1360,286),51,INK,'milestone-index')
            value_box=(inset+30,350,1890-inset,470)
            c.text(row['display_value'],value_box,82 if n>=16 else 112,TEAL,'milestone-value')
            if cue=='T020a':
                value=row['display_value'];size=82;layer=text_layer(value,size,TEAL);b=visible(layer)
                origin=(round((value_box[0]+value_box[2]-b[0]-b[2])/2),round((value_box[1]+value_box[3]-b[1]-b[3])/2))
                metric=font(size).getbbox(value);prefix='';groups=[]
                for i,(group,name) in enumerate(zip(value.split(','),['BILLION','MILLION','THOUSAND','ONES'])):
                    part=Image.new('RGBA',layer.size)
                    ImageDraw.Draw(part).text((20-metric[0]+font(size).getlength(prefix),20-metric[1]),group,font=font(size),fill=TEAL)
                    pb=visible(part);glyph_box=[origin[0]+pb[0],origin[1]+pb[1],origin[0]+pb[2],origin[1]+pb[3]]
                    cx=(glyph_box[0]+glyph_box[2])/2
                    c.draw.line((glyph_box[0],494,glyph_box[2]-1,494),fill=GOLD,width=3)
                    c.text(name,(cx-66,550,cx+66,605),21,MUTED,'place-name-'+str(i))
                    groups.append({'digits':group,'name':name,'digit_visible_box_xyxy':glyph_box,'label_center_x':cx})
                    prefix+=group+','
                data['place_groups']=groups
            else:c.text('COUNTING WAYS  ·  EXACT INTEGER VALUES',(300,555,1620,615),31,MUTED,'milestone-message')
            if cue=='T015a':
                c.text('MORE ROOM FOR LONG VALUES',(300,642,1620,685),27,MUTED,'wide-transition')
                data.update(expansion_progress=expansion,value_window_box=[inset,190,1920-inset,705],usable_value_box=value_box)
        elif mode=='history':
            c.panel((195,161,1725,785))
            for i,row in enumerate(self.rows):
                col=i//11;r=i%11;x=210+col*505;y=180+r*53
                c.text(f'C({i}) = {row["display_value"]}',(x+5,y,x+490,y+40),26,TEAL if i in (0,1,30) else INK,'history-'+str(i))
            data.update(history_values=[r['value'] for r in self.rows],two_initial_ones_preserved=True)
        elif mode=='ending':
            c.text('C(30)',(600,188,1320,267),61,INK,'ending-index')
            c.text(self.rows[30]['display_value'],(260,350,1660,480),82,TEAL,'ending-value')
            c.text('THANK YOU FOR COUNTING WITH ME!',(250,592,1670,657),43,MUTED,'ending-message')
        return c,data

    def frame(self,frame):
        state=self.state(frame);t=frame/FPS
        c,data=self.count_scene(state) if state.mode=='count' else self.lesson_scene(state)
        self.progress(c,state.completed)
        if state.mode=='count':height=210 if state.n>=16 else 220
        else:height=340 if state.mode=='intro' and state.cue=='I01' else 210 if state.mode in ('history','five_paths','first_return') else 280
        foot=(960,1032)
        if self.animation:
            target=data.get('gaze_target',data.get('path',{}).get('tip',(960,440)))
            character=self.animation.draw_character(c.image,t,state.mode,scene_start_s=state.scene_start_s,
                scene_end_s=state.scene_end_s,cue={'id':state.cue,'stage':state.stage,'n':state.n,'kind':state.mode,'ordinal':state.n+1},
                body_height=height,foot=foot,target=target)
        else:
            # Explicitly limited development preview; final rendering rejects it.
            try:
                old=self.preview_module.Canvas('preview',c.image);self.preview_art.draw(old,'watch_up',height,foot);c.image=old.im
                character={'preview_only':True,'pose':'retained preproduction watch_up'}
            except Exception:
                character={'preview_only':True,'absent':True}
        fade=1-clamp(frame/18) if frame<18 else clamp((frame-(self.frame_count-24))/23)
        if fade:c.image=Image.blend(c.image,Image.new('RGBA',SIZE,CREAM),fade)
        for r in c.records:
            key=json.dumps({k:r[k] for k in ('component_id','content_box_xyxy','visible_box_xyxy')},sort_keys=True)
            self.native_records[key]=r
        report={'frame':frame,'time_s':t,'state':asdict(state),'mathematics':data,'character':character,
                'fade':fade,'native_alignment_pass':all(r['passed'] for r in c.records)}
        return c.image.convert('RGB'),report


def write_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def preview(episode,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False);reports=[];samples=[]
    for e in episode.events:
        if e['id'].startswith('E'):
            n=int(e['id'][1:]);cs=episode.counts[n];op=cs.get('operator_timing',{})
            for tag,t in [('input',e['start_s']+.1),('product',op.get('multiply_commit_s',e['end_s']-.8)+.04),
                          ('divide',op.get('divided_start_s',e['end_s']-.6)+.1),('result',episode.by[f'N{n:03}']['start_s']+.12)]:
                samples.append((e['id']+'-'+tag,t))
        else:samples.append((e['id'],e['start_s']+(e['end_s']-e['start_s'])*.65))
    for name,t in samples:
        im,rep=episode.frame(min(episode.frame_count-1,max(0,round(t*FPS))))
        im.save(directory/(name+'.png'));reports.append(rep)
    records=[r for v in episode.native_records.values() for r in (v if isinstance(v,list) else [v])]
    write_json(directory/'preview.json',{'planning_only':bool(episode.plan.get('preview_plan_only')),'frames':reports,
                                       'native_components':records,'all_native_alignment_passed':all(r['passed'] for r in records)})
    print(json.dumps({'preview_frames':len(reports),'all_native_alignment_passed':all(r['passed'] for r in records)}))


def encode(episode,directory,audio=None,start_s=0,duration_s=None,no_audio=False,accepted_aac=None):
    if episode.plan.get('preview_plan_only') and not no_audio:raise ValueError('Planning timing cannot produce an adopted episode')
    if not no_audio and episode.animation is None:raise ValueError('Production character runtime required')
    aac_gate=None
    if accepted_aac:
        track=resolve(accepted_aac);gate_path=track.with_name('encoded-aac-acceptance.json')
        aac_gate=json.loads(gate_path.read_text())
        if not (aac_gate.get('accepted') and aac_gate.get('passed') and aac_gate['encoded_AAC']['sha256']==sha(track)):
            raise ValueError('Accepted AAC gate does not accept this exact track')
        if not episode.timeline_path or aac_gate['timeline']['sha256']!=sha(episode.timeline_path):
            raise ValueError('Accepted AAC gate is not bound to this exact timeline')
        if sha(track)!=episode.intro_word_timing['accepted_aac']['sha256']:
            raise ValueError('Intro speech timing requires its exact reviewed AAC')
        episode.bound_inputs += [receipt(track),receipt(gate_path)]
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    start=round(start_s*FPS);last=episode.frame_count if duration_s is None else min(episode.frame_count,start+round(duration_s*FPS))
    silent=directory/'mathematics-silent.mp4';final=directory/VIDEO_NAME
    if silent.exists() or (not no_audio and final.exists()):raise FileExistsError('Use a new render directory')
    cmd=[ffbin('ffmpeg'),'-nostdin','-v','error','-n','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','-',
         '-an','-vf','scale=in_range=pc:out_range=tv:out_color_matrix=bt709',
         '-c:v','libx264','-preset','fast','-crf','17','-pix_fmt','yuv420p','-color_primaries','bt709','-color_trc','bt709',
         '-colorspace','bt709','-color_range','tv','-bsf:v','h264_metadata=video_full_range_flag=0:colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1',
         '-movflags','+faststart+write_colr',str(silent)]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE);started=time.monotonic()
    with gzip.open(directory/'frame-observations.jsonl.gz','wt') as log:
        try:
            for f in range(start,last):
                image,report=episode.frame(f);proc.stdin.write(image.tobytes());log.write(json.dumps(report,ensure_ascii=False)+'\n')
                if f%300==0:print(f'frame {f}/{last}  elapsed {time.monotonic()-started:.1f}s',flush=True)
        finally:proc.stdin.close()
    if proc.wait():raise RuntimeError('Video encoder failed')
    output=silent
    if not no_audio:
        master=episode.plan.get('audio_master_path') or episode.plan.get('master_path') or episode.plan.get('audio_master') or episode.plan.get('master_audio')
        if isinstance(master,dict):master=master.get('path')
        source=resolve(audio) if audio else resolve(master or '')
        if not source.is_file():raise FileNotFoundError('Measured PCM master required: '+str(source))
        if accepted_aac:
            if start_s or duration_s is not None:raise ValueError('Accepted AAC copy is for the complete episode only')
            source=resolve(accepted_aac)
            subprocess.run([ffbin('ffmpeg'),'-nostdin','-v','error','-n','-i',str(silent),'-i',str(source),'-map','0:v:0','-map','1:a:0',
                            '-c:v','copy','-c:a','copy','-bsf:v','h264_metadata=video_full_range_flag=0:colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1',
                            '-color_primaries:v','bt709','-color_trc:v','bt709','-colorspace:v','bt709','-color_range:v','tv',
                            '-video_track_timescale','15360','-movflags','+faststart+write_colr',str(final)],check=True)
        else:
            subprocess.run([ffbin('ffmpeg'),'-nostdin','-v','error','-n','-i',str(silent),'-ss',str(start_s),'-i',str(source),'-map','0:v:0','-map','1:a:0',
                            '-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t',str((last-start)/FPS),'-movflags','+faststart',str(final)],check=True)
        output=final
    records=[r for v in episode.native_records.values() for r in (v if isinstance(v,list) else [v])]
    for dep in episode.bound_inputs:
        if sha(resolve(dep['path']))!=dep['sha256']:raise ValueError('A frozen render input changed: '+dep['path'])
    write_json(directory/'render.json',{'video':receipt(output),'timeline':receipt(episode.timeline_path) if episode.timeline_path else None,
               'renderer':receipt(Path(__file__)),'background':receipt(episode.bg_path),'font':receipt(FONT),
               'resolution_px':SIZE,'fps':FPS,'start_frame':start,'end_frame_exclusive':last,'frame_count':last-start,
               'duration_s':(last-start)/FPS,'planning_preview_only':bool(episode.plan.get('preview_plan_only')),
               'native_alignment_passed':all(r['passed'] for r in records),'native_components':records,
               'mathematics_animation':'exact integer multiply then divide; continuous identified units for small examples; symbolic value windows for large values',
               'accepted_aac_copied':bool(accepted_aac),'audio_source':receipt(source) if not no_audio else None,
               'frozen_inputs':episode.bound_inputs,'actor_configuration':episode.actor_configuration,
               'accepted_aac_gate':receipt(resolve(accepted_aac).with_name('encoded-aac-acceptance.json')) if accepted_aac else None,
               'final_media_qa_pending':True})
    print(output)
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--timeline',type=Path);p.add_argument('--background',type=Path)
    p.add_argument('--character-registration',type=Path)
    p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--audio',type=Path)
    p.add_argument('--accepted-aac',type=Path)
    p.add_argument('--preview-only',action='store_true');p.add_argument('--planning-preview',action='store_true')
    p.add_argument('--no-audio',action='store_true');p.add_argument('--start-s',type=float,default=0)
    p.add_argument('--duration-s',type=float)
    args=p.parse_args()
    if not args.timeline and not args.planning_preview:p.error('--timeline required; --planning-preview is development only')
    e=Episode(args.timeline,args.background,allow_preview_character=args.planning_preview,character_registration=args.character_registration)
    if args.preview_only:preview(e,args.out_dir)
    else:encode(e,args.out_dir,args.audio,args.start_s,args.duration_s,args.no_audio,args.accepted_aac)


if __name__=='__main__':main()
