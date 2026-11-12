"""Render the measured Collatz episode and a pixel-measured visual contract.

The art is immutable. Number values are discrete exact integers: no digit morphs,
rolling counters, full-character dissolves, or accelerated Collatz steps.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import OrderedDict
from functools import lru_cache
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    from .component_alignment import raster_centering_report
except ImportError:
    from component_alignment import raster_centering_report

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/collatz-counting-v1'
OUT = ROOT / 'output/collatz-counting-001-v001'
PROD = DESIGN / 'production-v001'
BG = DESIGN / 'generation-batches/collatz-preproduction-20261112-01a1cd57/source/waterworks-clean-plate.png'
FONT = ROOT / 'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
SIZE, FPS = (1920, 1080), 30
INK, TEAL, CLAY, PALE, BLUE = '#344f54', '#267b80', '#ad6143', '#fffaf0', '#537ca0'
MAIN_BOX = (600, 263, 1320, 444)
READING_BOX = (240, 470, 1680, 525)
INDEX_BOX = (300, 166, 1620, 211)
EQUATION_BOX = (350, 699, 1570, 777)
VIDEO_NAME = 'paspla-studio-collatz-sequence-7-and-27-1080p.mp4'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative(path):
    return str(Path(path).resolve().relative_to(ROOT))


def resolve(path):
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def receipt(path):
    p = Path(path)
    return {'path': relative(p), 'sha256': digest(p), 'bytes': p.stat().st_size}


def write(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def ffbin(name):
    p = ROOT / '.venv/bin' / name
    return str(p) if p.is_file() else shutil.which(name)


@lru_cache(maxsize=40)
def font(size):
    return ImageFont.truetype(str(FONT), size)


@lru_cache(maxsize=1800)
def glyphs(text, size, color):
    b = font(size).getbbox(text)
    im = Image.new('RGBA', (b[2] - b[0] + 48, b[3] - b[1] + 48))
    ImageDraw.Draw(im).text((24 - b[0], 24 - b[1]), text, font=font(size), fill=color)
    return im


def visible(im, threshold=128):
    return im.getchannel('A').point(lambda x: 255 if x >= threshold else 0).getbbox()


def words(n):
    one = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
    ten = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']
    if n < 20: return one[n]
    if n < 100: return ten[n // 10] + ('-' + one[n % 10] if n % 10 else '')
    if n < 1000: return one[n // 100] + ' hundred' + (' ' + words(n % 100) if n % 100 else '')
    return words(n // 1000) + ' thousand' + (' ' + words(n % 1000) if n % 1000 else '')


def smooth(p):
    p = max(0, min(1, p))
    return p * p * (3 - 2 * p)


class Canvas:
    def __init__(self, background, scene, semantics=None):
        self.image = background.copy()
        self.draw = ImageDraw.Draw(self.image)
        self.scene = scene
        self.records, self.foreground = [], {}
        self.data = dict(semantics or {})

    def panel(self, box, fill=PALE, edge='#c2d4cb', radius=28):
        self.draw.rounded_rectangle(box, radius=radius, fill=fill, outline=edge, width=2)

    def text(self, text, box, size=36, color=INK, ident='text', role='label', **semantic):
        layer = glyphs(str(text), size, color)
        b = visible(layer)
        if not b: raise ValueError(f'Empty text: {ident}')
        xy = (round((box[0]+box[2]-b[0]-b[2])/2), round((box[1]+box[3]-b[1]-b[3])/2))
        r = raster_centering_report(layer, box, origin_xy=xy, name=f'{self.scene}/{ident}', tolerance_px=.5)
        r.update(component_id=ident, text=str(text), font_size_px=size, color=color,
                 horizontal='center', vertical='center', numeric_role=role, **semantic)
        if not r['passed']: raise ValueError(r)
        self.records.append(r)
        self.foreground[ident] = (layer, xy, 128)
        self.image.alpha_composite(layer, xy)

    def lines(self, lines, box, size=34, color=INK, ident='lines', role='label', **semantic):
        layers = [glyphs(x, size, color) for x in lines]
        bounds = [visible(im) for im in layers]
        w = max(b[2]-b[0] for b in bounds)
        h = sum(b[3]-b[1] for b in bounds)+(len(lines)-1)*14
        layer = Image.new('RGBA', (w+48, h+48))
        y = 24
        for im,b in zip(layers,bounds):
            layer.alpha_composite(im,(round(24+(w-b[2]+b[0])/2)-b[0],y-b[1]))
            y += b[3]-b[1]+14
        b = visible(layer)
        xy = (round((box[0]+box[2]-b[0]-b[2])/2),round((box[1]+box[3]-b[1]-b[3])/2))
        r = raster_centering_report(layer,box,origin_xy=xy,name=f'{self.scene}/{ident}',tolerance_px=.5)
        r.update(component_id=ident,text='\n'.join(lines),font_size_px=size,color=color,
                 horizontal='center',vertical='center',numeric_role=role,multiline=True,**semantic)
        if not r['passed']: raise ValueError(r)
        self.records.append(r);self.foreground[ident]=(layer,xy,128)
        self.image.alpha_composite(layer,xy)

    def header(self, title='COLLATZ SEQUENCE', subtitle='THE NUMBER WATERWORKS'):
        self.text(title,(270,70,1650,144),47,ident='heading')
        self.text(subtitle,INDEX_BOX,25,TEAL,'index',role='index' if subtitle.startswith('START ') else 'label')

    def mirror(self, value, x, y=638, radius=125, active=False, ident='mirror', role='copy', **semantic):
        self.draw.ellipse((x-radius-6,y-radius*.54-6,x+radius+6,y+radius*.54+6),
                          fill='#fff5df',outline=TEAL if active else '#9bbfbb',width=4 if active else 2)
        self.draw.ellipse((x-radius,y-radius*.54,x+radius,y+radius*.54),fill='#e0f2ea')
        if value is not None:
            self.text(f'{value:,}',(x-radius+14,y-radius*.54+10,x+radius-14,y+radius*.54-10),
                      50,TEAL,ident,role=role,value=value,**semantic)

    def assert_clearance(self):
        # Foreground glyphs and the actual actor never share ink. Parent panels
        # and mirror housings are intentionally absent from this check.
        values = list(self.foreground.items())
        for i,(a,(ia,xa,ta)) in enumerate(values):
            ba=visible(ia,ta);aa=(ba[0]+xa[0],ba[1]+xa[1],ba[2]+xa[0],ba[3]+xa[1])
            for b,(ib,xb,tb) in values[i+1:]:
                bb=visible(ib,tb);ab=(bb[0]+xb[0],bb[1]+xb[1],bb[2]+xb[0],bb[3]+xb[1])
                if max(aa[0],ab[0])<min(aa[2],ab[2]) and max(aa[1],ab[1])<min(aa[3],ab[3]):
                    raise ValueError(f'Visible foreground bounds overlap: {a} / {b}: {aa} / {ab}')
        self.data['foreground_clearance_passed']=True


class Episode:
    def __init__(self,timeline,background=None,animation=None):
        self.timeline_path=Path(timeline)
        self.plan=json.loads(self.timeline_path.read_text())
        self.events=self.plan.get('voice_events',self.plan.get('events',[]))
        if len(self.events)<143: raise ValueError('All143 original count/narration events required')
        self.by_id={e['id']:e for e in self.events}
        self.counts=[e for e in self.events if e.get('kind')=='count' or e['id'].startswith(('C7_','C27_'))]
        if len(self.counts)!=129: raise ValueError('Need129 count utterances')
        self.starts=[self.result_time(e) for e in self.counts]
        self.ends=[e['end_s'] for e in self.counts]
        self.event_starts=[e['start_s'] for e in self.events]
        self.duration_s=self.plan.get('duration_s',self.plan.get('duration'))
        self.duration_frames=self.plan.get('duration_frames',math.ceil(self.duration_s*FPS))
        self.master_path=resolve(self.plan.get('master_path',self.plan.get('audio_path','output/collatz-counting-001-v001/audio-build/master.wav')))
        self.background_path=resolve(background) if background else BG
        self.background=ImageOps.fit(Image.open(self.background_path).convert('RGBA'),SIZE,Image.Resampling.LANCZOS)
        self.teaching=[e for e in self.events if e['id'].startswith('T27_')]
        self.animation_path=resolve(animation) if animation else ROOT/'tools/collatz_animation.py'
        self.animation=None
        if self.animation_path.exists():
            spec=importlib.util.spec_from_file_location('collatz_episode_animation',self.animation_path)
            self.animation=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.animation)
        self.cache=OrderedDict();self.reports={};self.frame_rows=[]
        self.motion=self.make_motion()
        self.motion_starts=[r['start_s'] for r in self.motion]

    @staticmethod
    def result_time(e):
        return e.get('result_start_s',e['start_s']-.12)

    @staticmethod
    def seed(e):
        return 7 if e['id'].startswith('C7_') else 27

    def make_motion(self):
        windows=[]
        def add(start,end,state,cue,reason):
            if end>start:windows.append(dict(start_s=start,end_s=end,state=state,cue=cue,reason=reason))
        for ident,state in [('I01','greet'),('I03','even'),('I04','odd'),('I05','think'),('B01','cheer'),
                            ('T27_001','odd'),('T27_036','surprise'),('T27_077','surprise'),
                            ('T27_103','nod'),('O01','cheer'),('O02','think'),('O03','goodbye')]:
            e=self.by_id[ident];start=e['start_s']+.15
            if ident=='I01':start=max(.1,e['start_s']-.35)
            add(start,min(e['end_s']+.35,start+3.8),state,ident,'narration-related gesture with preparation and return')
        for c in self.counts:
            seed=self.seed(c);i=c['index']
            if (seed==7 and i in [0,1,4,8,12]) or (seed==27 and i in [0,5,13,21,29,44,58,69,87,96,107]):
                nxt=self.by_id.get(f'C{seed}_{i+1:03d}')
                if nxt:
                    start=c['end_s']+.25;end=min(start+1.25,nxt['start_s']-.25)
                    add(start,end,'odd' if c['value']%2 else 'even',c['id'],'selected operation, not a repeated gesture on every value')
            if seed==27 and i in [48,89]:
                # A quiet complete stretch during a longer number; no hopping.
                start=c['start_s']+.1
                add(start,min(c['end_s']+.1,start+2.5),'stretch',c['id'],'quiet posture change with stable foot support')
        return sorted(windows,key=lambda r:r['start_s'])

    def state(self,frame):
        t=frame/FPS
        k=bisect_right(self.starts,t)-1
        completed=bisect_right(self.ends,t)
        e=self.events[max(0,bisect_right(self.event_starts,t)-1)]
        ident=e['id']
        if t>=e['end_s']+.2 and not ident.startswith(('C7_','C27_')):
            # A narration scene persists through its short authored tail.
            pass
        mode='count' if k>=0 else 'intro'
        op_n=None;op_index=None;phase=-1;replay=False
        if ident.startswith('I') and k<0:
            mode=ident
            if ident in ['I03','I04']:
                op_n=8 if ident=='I03' else 5;phase=max(0,min(1,(t-e['start_s'])/max(.1,e['end_s']-e['start_s'])))
        elif ident=='B01' and (k<17 or t<self.starts[17]):mode='bridge'
        elif ident.startswith('T27_') and t<e['end_s']+.22:
            mode=ident;replay=True
            if ident in ['T27_001','T27_036']:
                op_index=0 if ident=='T27_001' else 35
                op_n=self.by_id[f'C27_{op_index:03d}']['value']
                phase=max(0,min(1,(t-e['start_s'])/max(.1,e['end_s']-e['start_s'])))
        elif ident.startswith('O'):
            mode=ident
        if mode=='count' and k>=0 and k+1<len(self.counts):
            cur,nxt=self.counts[k:k+2]
            if self.seed(cur)==self.seed(nxt):
                begin=nxt.get('operation_start_s',cur['end_s']+.22)
                end=self.result_time(nxt)
                if begin<=t<end:
                    op_n=cur['value'];op_index=cur['index']
                    phase=max(0,min(1,(t-begin)/max(.01,end-begin)))
        # Fine motion is quantized to30 positions over each short operation.
        tick=round(phase*30) if phase>=0 else -1
        motion=next((m for m in reversed(self.motion) if m['start_s']<=t<m['end_s']),None)
        actor=motion['state'] if motion else 'neutral'
        actor_phase=round((t-motion['start_s'])/(motion['end_s']-motion['start_s'])*60) if motion else round((t%5)/5*60)
        fade=round(255*(1-t/.6)) if t<.6 else round(255*(t-(self.duration_s-.8))/.8) if t>self.duration_s-.8 else 0
        fade=max(0,min(255,fade))
        return dict(mode=mode,k=k,completed=completed,op_n=op_n,op_index=op_index,
                    phase_tick=tick,replay=replay,actor=actor,actor_tick=actor_phase,
                    active_cue=ident,fade=fade)

    def current(self,c,e):
        seed=self.seed(e);index=e['index'];value=e['value'];total=17 if seed==7 else 112
        c.header(subtitle=f'START {seed} · STEP {index} · TERM {index+1} OF {total}')
        c.draw.ellipse((570,239,1350,460),fill=PALE,outline='#8bb7b2',width=4)
        c.text(f'{value:,}',MAIN_BOX,164,INK,'main',role='main',seed=seed,index=index,value=value)
        c.text(words(value),READING_BOX,35,TEAL,'reading',role='reading',seed=seed,index=index,value=value)
        c.data.update(seed=seed,index=index,value=value,total_terms=total)

    def operation(self,c,n,p,seed,index,replay=False):
        odd=n%2==1;out=3*n+1 if odd else n//2
        label=('REPLAY · ALREADY COUNTED' if replay else 'NEXT: ODD · THREE COPIES, THEN +1') if odd else 'NEXT: EVEN · TWO EQUAL HALVES'
        if seed is None:label='RULE DEMO · '+('ODD: ×3, THEN +1' if odd else 'EVEN: ÷2')
        if odd and .42<=p<.9:
            label=('REPLAY · ' if replay else 'RULE DEMO · ' if seed is None else '')+'CALCULATION ONLY · '+('MULTIPLY BY THREE' if p<.7 else 'THEN ADD ONE')
        c.text(label,(350,529,1570,561),25,CLAY if odd else TEAL,'operation-label')
        c.panel((315,585,1605,789),fill='#fff9ed')
        if odd:
            if p<.22:
                c.mirror(n,960,ident='copy-1',role='copy',seed=seed,index=index)
                for x in [620,1300]:
                    radius=round(125*smooth(p/.22))
                    c.draw.ellipse((x-radius,638-radius*.54,x+radius,638+radius*.54),outline='#aecdc6',width=2)
            else:
                for j,x in enumerate([620,960,1300]):c.mirror(n,x,ident=f'copy-{j}',role='copy',seed=seed,index=index)
            if p<.42:
                expression=f'{n:,} × 3 = ?';stage='multiply-pending'
            elif p<.70:
                expression=f'{n:,} × 3 = {3*n:,}';stage='intermediate'
            elif p<.9:
                expression=f'{3*n:,} + 1 = ?';stage='plus-one-pending'
            else:
                expression=f'{3*n:,} + 1 = {out:,}';stage='next-ready'
            if .42<=p<.9:
                x=1635;y=round(580+smooth((p-.42)/.48)*125)
                c.draw.ellipse((x-43,y-43,x+43,y+43),fill='#d8eee9',outline=TEAL,width=2)
                c.text('+1',(x-34,y-27,x+34,y+27),29,CLAY,'one-droplet')
            c.text(expression,EQUATION_BOX,52,CLAY,'equation',role='equation',seed=seed,index=index,
                   input_value=n,next_value=out,intermediate=3*n,calculation_stage=stage,replay=replay)
            c.data['intermediate_is_counted']=False
        else:
            spread=smooth(min(1,p/.5))
            if spread<.94:
                for x in [round(960-210*spread),round(960+210*spread)]:
                    c.draw.ellipse((x-131,564,x+131,712),fill='#e0f2ea',outline='#9bbfbb',width=2)
            else:
                for j,x in enumerate([750,1170]):c.mirror(out,x,active=j==0,ident=f'half-{j}',role='half',seed=seed,index=index,input_value=n)
            expression=f'{n:,} ÷ 2 = {out:,}' if p>=.8 else f'{n:,} ÷ 2 = ?'
            c.text(expression,EQUATION_BOX,52,TEAL,'equation',role='equation',seed=seed,index=index,
                   input_value=n,next_value=out,calculation_stage='next-ready' if p>=.8 else 'divide-pending',replay=replay)
        c.data.update(operation_input=n,operation_result=out,operation_phase=p,operation_replay=replay)

    def incoming(self,c,e):
        seed=self.seed(e);i=e['index'];n=e['value']
        c.text('HOW THIS TERM WAS MADE' if i else 'A NEW JOURNEY STARTS HERE',
               (350,542,1570,579),25,TEAL,'operation-label')
        c.panel((365,592,1555,785),fill='#fff9ed')
        if i:
            prev=self.by_id[f'C{seed}_{i-1:03d}']['value']
            expression=f'{prev:,} × 3 + 1 = {n:,}' if prev%2 else f'{prev:,} ÷ 2 = {n:,}'
            c.text(expression,(400,619,1520,738),56,CLAY if prev%2 else TEAL,'equation',role='incoming-equation',
                   seed=seed,index=i,input_value=prev,value=n)
        else:
            c.lines([f'START WITH {n}', 'STOP WHEN WE FIRST REACH 1'],(400,615,1520,752),37,TEAL,'start-instructions')

    def footer(self,c,s):
        if s['k']<0:return
        e=self.counts[s['k']];seed=self.seed(e)
        completed=[x for x in self.counts[:s['completed']] if self.seed(x)==seed]
        recent=completed[-3:]
        c.text('RECENT TERMS',(255,834,745,875),23,TEAL,'recent-label')
        c.text(' → '.join(f"{x['value']:,}" for x in recent) if recent else 'READY',
               (250,889,750,952),29,INK,'recent-terms',role='recent',seed=seed,indices=[x['index'] for x in recent])
        c.text('TERMS COMPLETED',(1175,834,1665,875),23,TEAL,'progress-label')
        total=17 if seed==7 else 112
        c.text(f'{len(completed)} / {total}',(1170,889,1670,952),37,INK,'progress',role='progress',seed=seed,completed=len(completed),total=total)

    def intro(self,c,s):
        ident=s['mode']
        c.header('COLLATZ SEQUENCE','ONE NUMBER. TWO RULES. A SURPRISING JOURNEY.')
        if ident in ['I03','I04']:
            n=s['op_n'];p=s['phase_tick']/30
            c.draw.ellipse((600,235,1320,450),fill=PALE,outline='#8bb7b2',width=4)
            c.text(f'{n}',MAIN_BOX,164,INK,'demo-input',role='demo-input',value=n)
            c.text('RULE DEMO · NOT A COUNTED JOURNEY',READING_BOX,30,BLUE,'demo-label')
            self.operation(c,n,p,None,None)
        elif ident=='I02':
            c.panel((340,257,1580,733))
            c.text('1, 2, 3, 4, 5, …',(410,309,1510,450),102,TEAL,'positive-integers')
            c.lines(['Start with a positive whole number.', 'Each rule makes the next number.'],
                     (400,503,1520,688),39,INK,'domain-description')
        elif ident=='I05':
            c.panel((340,257,1580,760))
            for j,x in enumerate([620,960,1300]):c.mirror(5,x,y=378,ident=f'value-copy-{j}',role='demo-copy')
            c.lines(['THREE COPIES OF THE VALUE', '5 + 5 + 5 = 15', 'Numbers, not amounts of water.'],
                     (405,497,1515,716),38,INK,'value-not-water')
        else:
            c.draw.ellipse((600,250,1320,578),fill=PALE,outline='#8bb7b2',width=4)
            c.text('7' if ident=='I06' else 'n',(640,276,1280,498),164,TEAL,'start-symbol')
            c.text('START HERE',(710,510,1210,555),28,TEAL,'start-label')
            c.panel((300,637,800,741));c.text('EVEN: n ÷ 2',(330,658,770,721),42,TEAL,'even-rule')
            c.panel((1120,637,1620,741));c.text('ODD: 3 × n + 1',(1140,658,1600,721),37,CLAY,'odd-rule')

    def narration(self,c,s,e):
        mode=s['mode']
        if mode=='bridge':
            c.header('A NEW START. THE SAME TWO RULES.','FIRST JOURNEY FINISHED · NEXT JOURNEY BEGINS AT 27')
            c.panel((340,265,1580,755))
            c.text('7 → 1',(450,300,1470,432),108,TEAL,'first-trip')
            c.text('17 TERMS · 16 STEPS',(450,453,1470,512),34,TEAL,'first-trip-total')
            c.text('NEW START: 27',(450,567,1470,695),75,CLAY,'new-start')
            c.data['reset_not_a_collatz_transition']=True
        elif mode in ['T27_001','T27_036']:
            self.operation(c,s['op_n'],s['phase_tick']/30,27,s['op_index'],True)
        elif mode=='T27_077':
            c.text('HIGHEST VALUE OF THIS JOURNEY',(330,545,1590,592),32,CLAY,'peak-label')
            self.route(c,77)
        elif mode=='T27_103':
            c.panel((265,572,1655,787))
            c.text('SAME VALUE. SAME RULE. SAME ENDING.',(300,594,1620,637),28,TEAL,'same-rule')
            c.text('40 → 20 → 10 → 5 → 16 → 8 → 4 → 2 → 1',
                   (310,669,1610,752),42,INK,'familiar-ending')
        elif mode.startswith('O'):
            c.header('TWO JOURNEYS. THE SAME TWO RULES.','7: 16 STEPS · 27: 111 STEPS · BOTH STOP AT 1')
            c.draw.ellipse((600,239,1320,460),fill=PALE,outline='#8bb7b2',width=4)
            c.text('1',MAIN_BOX,164,INK,'main',role='main',seed=27,index=111,value=1)
            c.text('one',READING_BOX,35,TEAL,'reading',role='reading',seed=27,index=111,value=1)
            c.panel((330,577,1590,786))
            if mode=='O01':
                c.lines(['WE STOP AT 1.', 'IF WE CONTINUE: 1 → 4 → 2 → 1'],(375,609,1545,752),39,TEAL,'stop-and-loop')
            elif mode=='O02':
                c.lines(['Will every positive integer reach 1?', 'THE COLLATZ CONJECTURE · STILL UNPROVED'],
                         (365,609,1555,752),35,INK,'unproved-conjecture')
            else:
                self.route(c,111)

    def route(self,c,last):
        c.panel((330,600,1590,789))
        values=[self.by_id[f'C27_{i:03d}']['value'] for i in range(last+1)]
        points=[(390+i/111*1140,748-math.log2(n)/math.log2(9232)*103) for i,n in enumerate(values)]
        c.draw.line(points,fill=TEAL,width=3)
        for i,(x,y) in enumerate(points):
            r=5 if i in [0,77,last] else 2
            c.draw.ellipse((x-r,y-r,x+r,y+r),fill=CLAY if i==77 else TEAL)
        c.text('27',(344,710,396,750),21,TEAL,'route-start')
        if last==111:c.text('1',(1528,713,1570,753),21,TEAL,'route-end')
        c.text('HEIGHT: log₂(value) · HORIZONTAL: COLLATZ STEP',
               (400,604,1520,626),18,BLUE,'route-scale')
        c.data['route']={'values':values,'last_index':last,'x_scale':'linear0..111','y_scale':'log2(value)',
                         'future_terms_drawn':False,'plot_box':[390,645,1530,748]}

    def canvas(self,s):
        mode=s['mode'];c=Canvas(self.background,mode,s)
        if mode.startswith('I') or mode=='intro':
            self.intro(c,s)
        elif mode=='bridge' or mode.startswith('O'):
            self.narration(c,s,None)
        else:
            e=self.counts[max(0,s['k'])];self.current(c,e)
            if mode.startswith('T27_'):self.narration(c,s,e)
            elif s['op_n'] is not None:
                self.operation(c,s['op_n'],s['phase_tick']/30,self.seed(e),s['op_index'])
            else:self.incoming(c,e)
        if mode!='bridge' and not mode.startswith('I') and mode!='intro':self.footer(c,s)
        if self.animation:
            rec=self.animation.draw_character(c.image,s['actor'],s['actor_tick']/60,height=260,foot=(960,1030))
            c.data['character']=rec
            # Isolate the actual rendered actor for clearance without using its
            # transparent canvas as a centering target.
            bbox=rec.get('visible_bbox',rec.get('visible_box_xyxy'))
            if bbox:
                c.records.append({'component_id':'character','visible_box_xyxy':bbox,'not_centering_target':True,
                                  'horizontal':'anatomical foot x','vertical':'ground support y','passed':True,**rec})
                for r in c.records[:-1]:
                    b=r.get('visible_box_xyxy')
                    if b and max(b[0],bbox[0])<min(b[2],bbox[2]) and max(b[1],bbox[1])<min(b[3],bbox[3]):
                        raise ValueError(f'Actor overlaps readable foreground: {r["component_id"]}')
        else:
            # Only a draft preflight may omit the animation module. Final render
            # refuses to run without the registered production actor.
            c.data['character_missing_in_draft']=True
        c.assert_clearance()
        if s['fade']:
            c.image=Image.blend(c.image,Image.new('RGBA',SIZE,PALE),s['fade']/255)
        c.data['declared_fade_alpha']=s['fade']
        return c

    def image(self,frame,with_report=False):
        s=self.state(frame);key=json.dumps(s,sort_keys=True,separators=(',',':'))
        if key in self.cache:
            im,rec=self.cache.pop(key);self.cache[key]=(im,rec)
        else:
            c=self.canvas(s);rec={'state':s,'components':c.records,'scene_data':c.data}
            im=c.image.convert('RGB');self.cache[key]=(im,rec)
            if len(self.cache)>20:self.cache.popitem(last=False)
        ident=hashlib.sha256(key.encode()).hexdigest()[:18]
        self.reports.setdefault(ident,rec)
        return (im,rec,ident) if with_report else im

    def component_metadata(self,frame):
        _,report,_=self.image(frame,True)
        return report

    def write_contract(self,out_dir):
        p=Path(out_dir);p.mkdir(parents=True,exist_ok=True)
        spec={'kind':'collatz-production-visual-contract','fps':FPS,'resolution_px':list(SIZE),
              'font':receipt(FONT),'background':receipt(self.background_path),'timeline':receipt(self.timeline_path),
              'main':{'content_box':MAIN_BOX,'font_size_px':164,'color':INK},
              'reading':{'content_box':READING_BOX,'font_size_px':35,'color':TEAL},
              'index':{'content_box':INDEX_BOX,'font_size_px':25,'color':TEAL},
              'operation_equation':{'content_box':EQUATION_BOX,'font_size_px':52,'odd_color':CLAY,'even_color':TEAL},
              'mirrors':{'y':638,'radius':125,'odd_x':[620,960,1300],'even_x':[750,1170],
                         'value_font_size_px':50,'color':TEAL,'glyphs_appear_only_after_separation':True},
              'count_commit':'first frame with frame/30 >= event.result_start_s = voice.start_s-.12',
              'incoming_equation':'previous input transforms to the current value; no equation for a new seed',
              'normal_operation':'current.end+.22 through next.result_start; explanation boundaries start at narration.end+.22',
              'odd_stages':[[0,.22,'one source plus separating empty mirrors'],[.22,.42,'three same-value copies; multiplication pending'],
                            [.42,.7,'3*n intermediate, not a counted term'],[.7,.9,'+1 pending'],[.9,1,'3*n+1 result ready']],
              'even_stages':[[0,.5,'empty bowls separate'],[.5,.8,'two equal half-value mirrors'],[.8,1,'division result ready']],
              'replay':'current counted main and index remain unchanged; previous arithmetic explicitly labelled already counted',
              'actor':{'module':receipt(self.animation_path) if self.animation_path.exists() else None,'body_height_px':260,'foot_px':[960,1030],
                       'windows':self.motion,'no_full_actor_crossfade':True},
              'bookends':{'opening_fade_s':.6,'closing_fade_s':.8},
              'qa_scope':'Native glyph masks and foot placement. Independent final-video decoded verification is separate.'}
        write(p/'visual-contract.json',spec)
        write(p/'character-motion.json',{'fps':FPS,'windows':self.motion,'actor':spec['actor']})

    def preflight(self,out_dir,every_frame=True):
        out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
        frames=range(self.duration_frames) if every_frame else self.sample_frames()
        rows=[]
        for frame in frames:
            _,report,ident=self.image(frame,True)
            rows.append({'frame':frame,'state_id':ident,'mode':report['state']['mode'],'count_index':report['state']['k'],
                         'fade':report['state']['fade'],'actor':report['state']['actor']})
        rs=[r for x in self.reports.values() for r in x['components'] if not r.get('not_centering_target')]
        report={'kind':'collatz-native-raster-layout','timeline':receipt(self.timeline_path),'renderer':receipt(Path(__file__)),
                'frames_checked':len(rows),'all_frames':every_frame,'distinct_states':len(self.reports),
                'component_observations':len(rs),'all_passed':all(r['passed'] for r in rs),
                'max_abs_dx_px':max(abs(r['delta_x_px']) for r in rs),'max_abs_dy_px':max(abs(r['delta_y_px']) for r in rs),
                'clearance_all_pass':all(x['scene_data']['foreground_clearance_passed'] for x in self.reports.values()),
                'actor_module_present':self.animation is not None,'is_decoded_video_qa':False}
        (out/'native-states.json.gz').write_bytes(gzip.compress(json.dumps(self.reports,ensure_ascii=False,separators=(',',':')).encode()))
        (out/'frame-plan.json.gz').write_bytes(gzip.compress(json.dumps(rows,separators=(',',':')).encode()))
        write(out/'native-layout-verification.json',report)
        self.write_contract(PROD)
        return report

    def sample_frames(self):
        fs={0,self.duration_frames-1}
        for e in self.events:
            fs.update([max(0,math.floor(e['start_s']*FPS)-1),round((e['start_s']+e['end_s'])/2*FPS),min(self.duration_frames-1,math.ceil(e['end_s']*FPS))])
        for e in self.counts:
            begin=e.get('operation_start_s')
            if begin is not None:
                end=self.result_time(e)
                fs.update(round((begin+(end-begin)*x)*FPS) for x in [0,.2,.4,.6,.8,.95])
        return sorted(x for x in fs if 0<=x<self.duration_frames)


def preview(ep,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    ids=['I01','I02','I03','I04','I05','C7_000','C7_001','C7_005','B01','C27_000','T27_001',
         'C27_035','T27_036','C27_076','C27_077','T27_077','T27_103','C27_111','O01','O02','O03']
    results=[]
    for ident in ids:
        e=ep.by_id[ident];frame=round((e['start_s']+min(.8,(e['end_s']-e['start_s'])/2))*FPS)
        im,rec,state_id=ep.image(frame,True);path=out/f'{ident}-{frame:06d}.png';im.save(path)
        results.append({'cue':ident,'frame':frame,'state_id':state_id,**receipt(path)})
    write(out/'preview-manifest.json',results)
    # A compact full-frame contact sheet is a navigation aid, not native QA.
    sheet=Image.new('RGB',(1920,math.ceil(len(results)/3)*392),PALE);d=ImageDraw.Draw(sheet)
    for i,r in enumerate(results):
        x,y=i%3*640,i//3*392
        im=Image.open(resolve(r['path'])).resize((640,360),Image.Resampling.LANCZOS);sheet.paste(im,(x,y))
        d.text((x+12,y+365),r['cue'],font=font(20),fill=INK)
    sheet.save(out/'contact-sheet.jpg',quality=94)
    return results


def render(ep,out,limit_frames=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if ep.animation is None:raise ValueError('Final render requires registered production character animation')
    if not ep.master_path.is_file():raise ValueError('Measured audio master missing')
    count=min(ep.duration_frames,limit_frames) if limit_frames else ep.duration_frames
    path=out/VIDEO_NAME
    if path.exists():raise FileExistsError('Use a new render directory to preserve prior media')
    cmd=[ffbin('ffmpeg'),'-v','error','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','-',
         '-i',str(ep.master_path),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','fast','-crf','18',
         '-pix_fmt','yuv420p','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709',
         '-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t',f'{count/FPS:.9f}','-movflags','+faststart',str(path)]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
    try:
        for frame in range(count):
            im,rep,ident=ep.image(frame,True)
            proc.stdin.write(im.tobytes())
            ep.frame_rows.append({'frame':frame,'state_id':ident,'mode':rep['state']['mode'],'fade':rep['state']['fade']})
            if frame%900==0:print(json.dumps({'frame':frame,'total':count,'time_s':frame/FPS}),flush=True)
        proc.stdin.close()
        code=proc.wait()
        if code:raise RuntimeError(f'ffmpeg failed:{code}')
    except BaseException:
        proc.terminate();raise
    qa=out/'native-qa';qa.mkdir(exist_ok=True)
    rs=[r for rep in ep.reports.values() for r in rep['components'] if not r.get('not_centering_target')]
    (qa/'native-states.json.gz').write_bytes(gzip.compress(json.dumps(ep.reports,ensure_ascii=False,separators=(',',':')).encode()))
    (qa/'frame-plan.json.gz').write_bytes(gzip.compress(json.dumps(ep.frame_rows,separators=(',',':')).encode()))
    summary={'kind':'collatz-render-native-layout','rendered_frames':count,'distinct_states':len(ep.reports),'component_observations':len(rs),
             'all_passed':all(r['passed'] for r in rs),'max_abs_dx_px':max(abs(r['delta_x_px']) for r in rs),
             'max_abs_dy_px':max(abs(r['delta_y_px']) for r in rs),'is_decoded_video_qa':False}
    write(qa/'native-layout-verification.json',summary)
    ep.write_contract(PROD)
    write(out/'render-manifest.json',{'video':receipt(path),'timeline':receipt(ep.timeline_path),'master':receipt(ep.master_path),
                                    'renderer':receipt(Path(__file__)),'background':receipt(ep.background_path),
                                    'animation_module':receipt(ep.animation_path),'frame_count':count,'fps':FPS,'native_layout':summary,
                                    'final_video_qa_complete':False})
    return str(path)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['preview','preflight','render'])
    p.add_argument('--timeline',required=True);p.add_argument('--out-dir',required=True)
    p.add_argument('--background');p.add_argument('--animation');p.add_argument('--sample-only',action='store_true')
    p.add_argument('--limit-frames',type=int)
    args=p.parse_args();ep=Episode(args.timeline,args.background,args.animation)
    if args.action=='preview':r=preview(ep,args.out_dir)
    elif args.action=='preflight':r=ep.preflight(args.out_dir,not args.sample_only)
    else:r=render(ep,args.out_dir,args.limit_frames)
    print(json.dumps(r,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
