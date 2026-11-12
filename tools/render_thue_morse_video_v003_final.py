"""Thue–Morse revision v003: explicit intro position and pointed arrow tips.

All mathematical display states share a zero-based index, while tile commitment
uses the end of the spoken result. Explanations replay existing terms only.
Preproduction stills and their audit records are never rewritten here.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw

try:
    import render_thue_morse_mockups as m
    from component_alignment import raster_centering_report
except ModuleNotFoundError:
    from tools import render_thue_morse_mockups as m
    from tools.component_alignment import raster_centering_report

ROOT=Path(__file__).resolve().parents[1]
DESIGN=ROOT/'design/thue-morse-counting-v1/production-v003'
FPS=30
SIZE=(1920,1080)
VIDEO_NAME='paspla-studio-thue-morse-sequence-256-terms-1080p.mp4'
INK,TEAL,CREAM,APRICOT,PALE,MUTED=m.INK,m.TEAL,m.CREAM,m.APRICOT,m.PALE,m.MUTED
FORMULA=(165,217,1755,309)
GEOMETRY={
 'size_px':list(SIZE),'fps':FPS,'colors':dict(ink=INK,teal=TEAL,cream=CREAM,apricot=APRICOT,pale=PALE,muted=MUTED),
 'active-equation':{'box':list(FORMULA),'font_size_px':63,'role':'applied recurrence at math_index; ? until result_revealed'},
 'parent-value':{'role':'value at floor(math_index/2), never automatically previous term'},
 'parent-address':{'role':'parent index, decimal'},'operation':{'role':'SAME VALUE or 1 minus parent value'},
 'result-value':{'role':'value at math_index'},'pending-result':{'role':'question mark before reveal'},
 'result-address':{'role':'decimal output index'},'progress':{'role':'number of spoken and completed terms; never current value'},
 'history-{j}':{'role':'value at absolute zero-based index j; only committed terms'},
 'loom-{j}':{'role':'value at absolute zero-based index j; row-major 16 columns; only committed terms'},
 'weave':{'columns':16,'rows':16,'left':152,'top':370,'step_x':47,'step_y':31,'cell_w':42,'cell_h':26,'font_size_px':18},
 'count_modes':{'0..31':'wide causal pipeline + recent strip','32..127':'frontal weave + vertical parent/operator','128..191':'overhead weave + vertical parent/operator; bird offscreen','192..255':'frontal weave; bird lower middle'},
 'alignment':'center horizontally and vertically using actual glyph alpha bounds; feet use support anchors',
 'source_tolerance_px':.5,'decoded_tolerance_px':1.0,
 'revision_v003':{'intro':'explicit small POSITION0 and large value0 during I003',
   'arrow_tips':'shaft terminates inside triangle near base; no tip protrusion or raster seam','shaft_joint_overlap_px':2},
 'revision_v002':{'arrowheads':'parallel to the actual line direction',
   'substitution':'zero-parent children first; retained while one-parent children are added',
   'binary_parity':'even15/four/zero and odd127/seven/one visible together during both-case narration',
   'fade_end':'last encoded picture frame is the uniform cream endpoint'},
}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rel(p):return str(Path(p).resolve().relative_to(ROOT))
def receipt(p):return {'path':rel(p),'sha256':sha(p)}
def clamp(v):return max(0.,min(1.,v))
def smooth(v):v=clamp(v);return v*v*(3-2*v)
def lerp(a,b,p):return a+(b-a)*p
def pc(k):return k.bit_count()&1


class Canvas(m.Canvas):
    def __init__(self,name,topdown=False):
        super().__init__(name,topdown)
        self.meta.update(placement_mode='production',math_index=None)
        self.panels=[]
        self.background_path=rel(m.OVERHEAD if topdown else m.BG)

    def panel(self,box,fill=PALE,outline='#dacdb6',radius=26):
        super().panel(box,fill,outline,radius)
        self.panels.append((box,fill))

    def arrow(self,start,end,color=TEAL,width=7):
        dx,dy=end[0]-start[0],end[1]-start[1]
        length=math.hypot(dx,dy)
        if length<=0:raise ValueError('Arrow requires a nonzero direction')
        ux,uy=dx/length,dy/length
        px,py=-uy,ux
        head=min(17.,length*.3);half_width=min(11.,length*.2)
        bx,by=end[0]-head*ux,end[1]-head*uy
        # Overlap the shaft inside the triangle to avoid a raster seam.
        joint=min(2.,head/3)
        self.draw.line([start,(bx+joint*ux,by+joint*uy)],fill=color,width=width)
        self.draw.polygon([end,(bx+half_width*px,by+half_width*py),
                                (bx-half_width*px,by-half_width*py)],fill=color)

    def text(self,text,box,size=40,color=INK,ident=None,**attrs):
        super().text(text,box,size,color,ident)
        fill=next((fill for panel,fill in reversed(self.panels) if panel[0]<=box[0] and panel[1]<=box[1] and panel[2]>=box[2] and panel[3]>=box[3]),None)
        self.records[-1].update(color=color,fill=fill,background_path=self.background_path,**attrs)

    def tile(self,value,box,ident,active=False,size=46):
        super().tile(value,box,ident,active,size)
        self.records[-1].update(role='binary-valued-tile',value=value,tile_box_xyxy=list(box),
                                absolute_index=int(ident.split('-')[-1]) if ident.startswith(('loom-','history-')) else None)

    def moving(self,text,x,y,size=31,color=INK,ident='moving-reference',**attrs):
        layer=m.glyph(str(text),size,color);b=m.visible(layer)
        w,h=b[2]-b[0],b[3]-b[1]
        self.center(layer,(x-w/2-8,y-h/2-8,x+w/2+8,y+h/2+8),ident)
        self.records[-1].update(text=str(text),font_size_px=size,color=color,role='moving mathematical reference; not a counted tile',**attrs)


class Episode:
    def __init__(self,timeline,allow_still=False):
        self.timeline_path=Path(timeline).resolve();self.plan=json.loads(self.timeline_path.read_text())
        self.events=self.plan.get('voice_events',self.plan.get('events',self.plan.get('cues',[])))
        self.events=[{**x,'id':x.get('id',x.get('cue_id')),'text':x.get('subtitle_text',x.get('text',''))} for x in self.events]
        self.events.sort(key=lambda x:x['start_s']);self.byid={x['id']:x for x in self.events}
        if len(self.events)!=283 or len(self.byid)!=283:raise ValueError('Exactly 283 unique voice events required')
        self.counts=[]
        supplied={x['index']:x for x in self.plan.get('counted_states',[])}
        for k in range(256):
            e=self.byid[f'C{k:03d}'];value=e.get('value')
            if int(value)!=pc(k):raise ValueError(('wrong spoken value',k,value))
            measured=supplied.get(k,{})
            self.counts.append({'index':k,'value':pc(k),'parent_index':k//2 if k else None,
              'voice_start_s':e['start_s'],'voice_end_s':e['end_s'],
              'reveal_s':measured.get('result_display_s',e.get('result_display_s',e['start_s']-.12)),
              'operation_start_s':measured.get('operation_start_s',e['start_s']-2 if k else e['start_s']-.85)})
        self.count_starts=[x['operation_start_s'] for x in self.counts]
        self.ends=[x['voice_end_s'] for x in self.counts]
        self.event_starts=[x['start_s'] for x in self.events]
        self.frames=int(self.plan.get('duration_frames',math.ceil(self.plan['duration_s']*30)))
        self.duration=self.frames/30
        if self.duration<480:raise ValueError('Episode must exceed eight minutes')
        for k in range(255):
            gap=self.counts[k+1]['voice_start_s']-self.counts[k]['voice_end_s']
            if k not in (3,15,31,127) and abs(gap-2)>1e-6:raise ValueError(('normal gap changed',k,gap))
        self.blocks=[]
        for after in (3,15,31,127):
            rows=[e for e in self.events if e['id'].startswith(f'X{after:03d}')]
            self.blocks.append({'after':after,'start':self.counts[after]['voice_end_s']+.20,
                                'end':self.counts[after+1]['operation_start_s'],'events':rows})
        self.outro_start=self.counts[-1]['voice_end_s']+.28
        m.PLATE=Image.open(m.BG).convert('RGBA').resize(SIZE,Image.Resampling.LANCZOS)
        m.TOP_PLATE=Image.open(m.OVERHEAD).convert('RGBA').resize(SIZE,Image.Resampling.LANCZOS)
        self.allow_still=allow_still
        try:
            if allow_still:raise ImportError('explicit geometry draft uses canonical still')
            import thue_morse_animation as anim
            self.anim=anim
        except ImportError:
            if not allow_still:raise
            self.anim=None
        self.actor_events=self.make_actor_schedule()
        self.raw_cache={};self.reports={};self.component_cache={}
        self.input_receipts=[receipt(p) for p in [self.timeline_path,Path(__file__),Path(m.__file__),m.FONT,m.BG,m.OVERHEAD,
            ROOT/'assets/library/characters/onagadori/sources/v002/neutral.png']]
        if self.anim:
            self.input_receipts += [receipt(p) for p in [Path(self.anim.__file__),self.anim.BATCH/'source/clean-source.png',
                self.anim.BATCH/'source/blink-source.png',self.anim.DONOR]]

    def event_at(self,t):
        i=max(0,bisect_right(self.event_starts,t)-1)
        return self.events[i]

    def make_actor_schedule(self):
        ev=[]
        def add(start,duration,state,reason):ev.append(dict(start_s=max(0,start),end_s=start+duration,state=state,reason=reason))
        intro_end=self.counts[0]['reveal_s']
        add(.6,min(3.2,max(1.,intro_end-1)), 'greet','opening greeting')
        add(max(4.,intro_end-3.8),2.4,'present','guide to working recurrence')
        # Designed responses to the source rule and the growing textile; no per-term gesture loop.
        for k,state in [(2,'source_look'),(3,'aha'),(4,'present'),(7,'result_look'),(10,'think'),(24,'relax'),(40,'present'),(56,'source_look'),(72,'stretch'),(88,'result_look'),(104,'think'),(120,'relax'),(200,'present'),(216,'source_look'),(232,'stretch'),(248,'aha')]:
            add(self.counts[k]['voice_end_s']+.22,1.35 if state not in ('stretch','relax') else 4.0,state,f'context at position {k}')
        for b in self.blocks:
            if b['after'] in (15,31):continue
            add(b['start']+.5,2.8,'present',f'explanation after {b["after"]}')
            if b['after']==127:add(b['end']-4.6,2.7,'aha','binary parity agrees with weave')
        o4=self.byid['O004'];add(o4['start_s']+.05,min(3.2,o4['end_s']-o4['start_s']+.45),'goodbye','closing greeting')
        # A completed gesture must return to canonical before another one
        # begins. Selecting a later overlapping event reset an open wing in
        # one frame; serialize the actions while preserving all speech clocks.
        ev.sort(key=lambda x:x['start_s'])
        previous_end=-1.
        for action in ev:
            requested=action['start_s'];duration=action['end_s']-requested
            action['requested_start_s']=requested
            action['start_s']=max(requested,previous_end+.18)
            action['end_s']=action['start_s']+duration
            action['serial_shift_s']=action['start_s']-requested
            previous_end=action['end_s']
        # Sparse irregular blinks, never the only acting in a long count.
        t=8.7;j=0
        while t<self.duration-2:
            if not any(x['start_s']-.4<=t<=x['end_s']+.4 for x in ev):add(t,.26,'blink','quiet irregular blink')
            t+=(7.1,9.3,6.7,10.1,8.6)[j%5];j+=1
        return sorted(ev,key=lambda x:x['start_s'])

    def state(self,f):
        t=f/30;event=self.event_at(t);completed=bisect_right(self.ends,t)
        s={'frame':f,'time_s':t,'cue_id':event['id'],'completed_count':completed,'replay':False}
        if t<self.counts[0]['operation_start_s']:
            return {**s,'scene':'intro','step':int(event['id'][1:])-1 if event['id'].startswith('I') else 3}
        if t>=self.outro_start:
            step=int(event['id'][1:])-1 if event['id'].startswith('O') else 0
            return {**s,'scene':'outro','step':step,'replay':True,'completed_count':256}
        for b in self.blocks:
            if b['start']<=t<b['end']:
                rows=b['events'];j=max(0,bisect_right([e['start_s'] for e in rows],t)-1)
                e=rows[j];p=clamp((t-e['start_s'])/max(.1,e['end_s']-e['start_s']))
                return {**s,'scene':f'explain-{b["after"]:03d}','step':j,'step_phase':round(p*32)/32,
                        'block_phase':clamp((t-b['start'])/(b['end']-b['start'])),'replay':True,'completed_count':b['after']+1}
        k=max(0,bisect_right(self.count_starts,t)-1);c=self.counts[k]
        revealed=t>=c['reveal_s'];p=1. if revealed else clamp((t-c['operation_start_s'])/max(.01,c['reveal_s']-c['operation_start_s']))
        return {**s,'scene':'count','index':k,'value':pc(k),'parent_index':k//2 if k else None,
                'result_revealed':revealed,'operation_phase':round(p*60)/60,
                'mode':'strip' if k<32 else 'overhead' if 128<=k<192 else 'weave',
                'completed_count':k+1 if t>=c['voice_end_s'] else k}

    def actor_at(self,s):
        t=s['time_s'];scene=s['scene']
        if scene.startswith('explain-') and scene in ('explain-015','explain-031'):return None
        if scene=='outro' and s['step']<3:return None
        if scene=='count' and s['mode']=='overhead':return None
        height,foot=(250,(610,1040)) if scene=='intro' else (210,(610,1040)) if scene=='outro' else (190,(1190,1040)) if scene=='explain-127' else (180,(1030,1035)) if scene=='count' and s['index']>=192 else (180,(1450,1035))
        selected=None
        for e in self.actor_events:
            if e['start_s']<=t<e['end_s']:
                if selected is None or e['state']!='blink':selected=e
        state,phase='neutral',0.
        if selected:state=selected['state'];phase=round((t-selected['start_s'])/(selected['end_s']-selected['start_s'])*120)/120
        return {'state':state,'phase':clamp(phase),'height':height,'foot':foot}

    def footer(self,c,n,replay=False):
        c.text(('Replay · ' if replay else '')+f'Terms counted: {n} / 256',(140,977,1030,1024),27,MUTED,'progress',role='progress',completed_count=n)

    def grid(self,c,n,active=None,large=False):
        if large:
            left,top,sx,sy,cw,ch,size=210,236,94,36,84,31,20
            c.panel((170,210,1750,838),'#f4ead7',radius=25)
        else:
            left,top,sx,sy,cw,ch,size=152,370,47,31,42,26,18
            c.panel((130,350,920,890),'#f4ead7',radius=22)
        for j in range(256):
            x=left+(j%16)*sx;y=top+(j//16)*sy
            if j<n:c.tile(pc(j),(x,y,x+cw,y+ch),f'loom-{j}',active=j==active,size=size)
            else:c.panel((x,y,x+cw,y+ch),'#f5efdf','#e6ddc8',6)
        if not large:c.text('16 × 16 · positions 0–255',(150,910,910,946),24,MUTED,'loom-order',role='loom-order')

    def recent(self,c,n,active=None):
        if not n:return
        a=max(0,n-16)
        for j in range(a,n):
            x=140+(j-a)*68;c.tile(pc(j),(x,835,x+58,900),f'history-{j}',active=j==active,size=36)
        c.text(f'Positions {a}–{n-1}',(140,911,1220,945),23,MUTED,'history-range',role='history-range')

    def rule_pipeline(self,c,k,revealed,n,mode='strip',replay=False):
        pv=pc(k//2);v=pc(k)
        formula='t(0) = '+('0' if revealed else '?') if k==0 else f't({k}) = '+(f't({k//2})' if k%2==0 else f'1 − t({k//2})')+' = '+(str(v) if revealed else '?')
        c.panel((130,199,1790,326));c.text(formula,FORMULA,63,INK,'active-equation',role='active-equation',math_index=k)
        if k==0:
            c.text('START WITH ZERO',(390,375,1530,439),38,TEAL,'seed-label')
            if revealed:c.tile(0,(818,479,1102,696),'result-value',True,153)
            else:c.text('?',(835,497,1085,675),130,MUTED,'pending-result')
            if revealed:c.text('ZERO',(700,720,1220,774),35,INK,'result-word')
        elif mode=='strip':
            c.text(f'PARENT · position {k//2}',(150,373,550,421),29,TEAL,'parent-address',role='parent-address',math_index=k)
            c.tile(pv,(230,465,470,665),'parent-value',False,136)
            c.arrow((495,565),(630,565))
            c.panel((660,459,1080,672),'#e8f0e7' if k%2==0 else '#f8e4c5')
            c.text('COPY' if k%2==0 else 'SWAP 0 ↔ 1',(690,477,1050,529),32,TEAL,'gate-title',role='gate-title',math_index=k)
            c.text('SAME VALUE' if k%2==0 else f'1 − {pv}',(690,562,1050,639),44,INK,'operation',role='operation',math_index=k)
            c.arrow((1110,565),(1260,565))
            c.text(f'POSITION {k}',(1265,373,1695,421),29,TEAL,'result-address',role='result-address',math_index=k)
            if revealed:c.tile(v,(1320,465,1560,665),'result-value',True,136)
            else:c.panel((1320,465,1560,665),'#f6efdf');c.text('?',(1340,480,1540,650),117,MUTED,'pending-result')
            if revealed:c.text('ONE' if v else 'ZERO',(1230,710,1650,766),35,INK,'result-word')
        else:
            c.text(f'PARENT · position {k//2}',(975,365,1390,411),28,TEAL,'parent-address',role='parent-address',math_index=k)
            c.tile(pv,(1060,435,1260,605),'parent-value',False,110)
            c.arrow((1160,620),(1160,660),TEAL,6)
            c.panel((980,680,1350,815),'#e8f0e7' if k%2==0 else '#f8e4c5')
            c.text('COPY' if k%2==0 else 'SWAP 0 ↔ 1',(1000,693,1330,737),29,TEAL,'gate-title',role='gate-title',math_index=k)
            c.text('SAME VALUE' if k%2==0 else f'1 − {pv}',(1000,751,1330,799),33,INK,'operation',role='operation',math_index=k)
            c.arrow((1370,745),(1445,627),TEAL,6)
            c.text(f'POSITION {k}',(1410,397,1770,445),28,TEAL,'result-address',role='result-address',math_index=k)
            if revealed:c.tile(v,(1470,495,1710,700),'result-value',True,136)
            else:c.panel((1470,495,1710,700),'#f6efdf');c.text('?',(1490,510,1690,680),117,MUTED,'pending-result')
            if revealed:c.text('ONE' if v else 'ZERO',(1420,751,1770,807),35,INK,'result-word')
        if mode=='strip':self.recent(c,n,k//2 if k else None)
        else:self.grid(c,n,k//2)
        self.footer(c,n,replay)
        c.meta.update(math_index=k,value=v,parent_index=k//2 if k else None,parent_value=pv if k else None,
                      result_revealed=revealed,completed_count=n,mode=mode,replay=replay)

    def intro(self,step):
        c=Canvas('intro');m.header(c,'THUE–MORSE SEQUENCE')
        c.text('Two tiny values. One growing pattern.',(180,230,1740,326),61,TEAL,'promise')
        if step==2:
            c.text('POSITION 0',(700,365,1220,420),29,TEAL,'intro-position-index-0',role='preview-position-index',math_index=0)
            c.tile(0,(810,452,1110,636),'intro-position-value-0',False,136)
            c.meta.update(preview_position=0,position_font_px=29,value_font_px=136)
        elif step>=1:c.text('t(0) = 0',(390,390,1530,494),82,INK,'seed-rule-preview',role='preview-not-counted')
        if step>=3:c.text('t(2n) = t(n)     ·     t(2n + 1) = 1 − t(n)',(190,535,1730,622),49,INK,'two-rules',role='symbolic-rules')
        c.tile(0,(680,664,800,767),'legend-zero',False,67);c.tile(1,(1120,664,1240,767),'legend-one',False,67)
        c.meta.update(completed_count=0,preview_not_counted=True)
        return c

    def explanation(self,after,step,phase):
        if after==3:
            c=Canvas('explain-003');m.header(c,sub='ONE PARENT · FOLLOW THE ACTIVE RULE')
            if step==0:
                c.text('SMALL POSITION · LARGE VALUE',(300,235,1620,315),47,TEAL,'position-value-title')
                for example,left in [(2,335),(3,1100)]:
                    right=left+485;cx=(left+right)/2
                    c.panel((left,350,right,733),'#fffaf0',radius=28)
                    c.text(f'POSITION {example}',(left+25,375,right-25,425),29,TEAL,
                           f'position-value-index-{example}',role='result-address',math_index=example)
                    c.tile(pc(example),(round(cx)-130,465,round(cx)+130,665),
                           f'position-value-result-{example}',False,136)
                    c.text(f't({example}) = {pc(example)}',(left+25,755,right-25,809),41,INK,
                           f'position-value-equation-{example}',role='fixed-math',math_index=example)
                self.recent(c,4);self.footer(c,4,True)
                c.meta.update(replay=True,completed_count=4,position_font_px=29,value_font_px=136,
                              shown_indices=[2,3])
            elif step in (1,2):
                self.rule_pipeline(c,2 if step==1 else 3,phase>=.8,4,'strip',True)
                if phase<.8:self.reference_motion(c,2 if step==1 else 3,phase/.8,'strip')
            elif step==3:
                c.text('0 ↔ 1',(550,233,1370,327),73,TEAL,'swap-example-title')
                c.text('1 − 0 = 1',(230,430,930,566),82,INK,'swap-zero-example',role='fixed-math')
                c.text('1 − 1 = 0',(990,430,1690,566),82,INK,'swap-one-example',role='fixed-math')
                self.recent(c,4);self.footer(c,4,True)
            else:
                c.text('t(2n) = t(n)',(220,235,1700,342),69,INK,'copy-rule',role='symbolic-rules')
                c.text('t(2n + 1) = 1 − t(n)',(200,382,1720,477),65,INK,'swap-rule',role='symbolic-rules')
                c.text('position 2 → value 1',(240,553,1680,626),55,TEAL,'position-value-2',role='fixed-math')
                c.text('position 3 → value 0',(240,680,1680,753),55,TEAL,'position-value-3',role='fixed-math')
                self.recent(c,4);self.footer(c,4,True)
            return c
        if after==15:
            c=Canvas('explain-015',True);m.header(c,sub='SAME ORDER · CHANGE EVERY VALUE')
            c.panel((170,205,1750,825),'#f7f0df',radius=40)
            c.text('KEEP',(210,248,1710,300),32,TEAL,'keep-label')
            # One column at a time visibly resolves to its complemented value.
            n=8 if step>=2 else 0 if step==0 else min(8,int(phase*9))
            for j in range(8):
                x=340+j*156;c.tile(pc(j),(x,338,x+110,438),f'replay-original-{j}',size=58)
                c.arrow((x+55,458),(x+55,532),APRICOT,5)
                if j<n:c.tile(1-pc(j),(x,554,x+110,654),f'replay-complement-{j}',size=58)
                else:c.panel((x,554,x+110,654),'#f7f0df');c.text('?',(x+8,563,x+102,645),58,MUTED,f'complement-pending-{j}')
            c.text('SWAP 0 ↔ 1',(380,704,1540,761),38,TEAL,'swap-label')
            if step>=2:c.text('01101001  |  10010110',(300,845,1620,910),50,INK,'joined-word',role='fixed-math')
            c.text('Append the changed copy after the original.',(340,946,1730,1000),30,MUTED,'append-rule')
            c.text('Replay · Terms counted: 16 / 256',(340,1018,1580,1058),23,MUTED,'progress',role='progress',completed_count=16)
            return c
        if after==31:
            c=Canvas('explain-031',True);m.header(c,sub='ONE PARENT · TWO CHILDREN')
            c.text('0 → 01        1 → 10',(320,220,1600,306),69,INK,'substitution-rules',role='symbolic-rules')
            # Match the spoken class. The zero-parent children remain visible
            # while the next sentence adds only the one-parent children.
            zero_parents=[j for j in range(16) if pc(j)==0]
            one_parents=[j for j in range(16) if pc(j)==1]
            if step==0:shown=set()
            elif step==1:shown=set(zero_parents[:min(8,int(phase*9))])
            elif step==2:shown=set(zero_parents+one_parents[:min(8,int(phase*9))])
            else:shown=set(range(16))
            for j in range(16):
                x=215+j*94
                emphasized=(step==1 and pc(j)==0) or (step==2 and pc(j)==1)
                c.tile(pc(j),(x+13,403,x+67,468),f'replay-parent-{j}',active=emphasized,size=34)
                c.arrow((x+40,490),(x+20,560),TEAL,4);c.arrow((x+40,490),(x+66,560),APRICOT,4)
                for child in (0,1):
                    xx=x+child*46
                    if j in shown:c.tile(pc(j)^child,(xx,585,xx+40,639),f'replay-child-{2*j+child}',size=28)
                    else:c.panel((xx,585,xx+40,639),'#f7f0df')
            c.text('t(2n) = t(n)',(210,720,930,811),49,TEAL,'copy-recurrence',role='symbolic-rules')
            c.text('t(2n + 1) = 1 − t(n)',(960,720,1740,811),43,TEAL,'swap-recurrence',role='symbolic-rules')
            c.text('Replay · 16 parents → 32 children',(220,872,1700,929),34,INK,'replay-shape',role='fixed-math')
            self.footer(c,32,True)
            c.meta.update(replay=True,completed_count=32,shown_parent_indices=sorted(shown),
                          emphasized_parent_value=0 if step==1 else 1 if step==2 else None)
            return c
        if step>=2:
            c=Canvas('explain-127');m.header(c,sub='THE POSITION IN BINARY · COUNT ITS ONES')
            for example,left in [(15,150),(127,995)]:
                right=left+775;cx=(left+right)/2;bits=format(example,'b');n=bits.count('1');v=n%2
                c.panel((left,210,right,825),'#fffaf0',radius=28)
                c.text(f'position {example} = {bits}₂',(left+25,249,right-25,349),44,INK,
                       f'binary-position-{example}',role='binary-position',math_index=example)
                start=cx-(n*76+(n-1)*14)/2
                for j in range(n):
                    x=round(start+j*90)
                    c.tile(1,(x,404,x+76,478),f'parity-{example}-one-{j}',size=43)
                c.text(f'{n} ones → '+('odd' if v else 'even'),(left+25,531,right-25,596),42,TEAL,
                       f'parity-condition-{example}',role='parity-condition',math_index=example)
                c.tile(v,(round(cx)-70,625,round(cx)+70,745),f'parity-output-{example}',True,78)
                c.text(f't({example}) = s₂({example}) mod 2 = {v}',(left+20,765,right-20,810),31,INK,
                       f'popcount-rule-{example}',role='popcount-rule',math_index=example)
            self.footer(c,128,True)
            c.meta.update(replay=True,completed_count=128,simultaneous_examples=[15,127],
                          reason='Both even and odd examples stay visible while the voice explains both.')
            return c
        c=Canvas('explain-127');m.header(c,sub='THE POSITION IN BINARY · COUNT ITS ONES')
        example=15 if step<2 else 127
        bit='1111' if example==15 else '1111111';n=len(bit);v=n%2
        c.text(f'position {example} = {bit}₂',(230,220,1690,319),70,INK,'binary-position',role='binary-position',math_index=example)
        left=(1920-(n*132-26))/2
        for j in range(n):
            x=round(left+j*132);c.tile(1,(x,386,x+106,503),f'binary-one-{j}',size=70)
        c.text(f'{n} ones → '+('odd → 1' if v else 'even → 0'),(270,563,1650,662),71,TEAL,'parity-result',role='parity-result',math_index=example)
        c.text(f't({example}) = s₂({example}) mod 2 = {v}',(280,710,1640,794),54,INK,'popcount-rule',role='popcount-rule',math_index=example)
        self.footer(c,128,True);return c

    def outro(self,step):
        if step>=3:
            c=Canvas('outro-wide');m.header(c,sub='TWO VALUES · THE PATTERN KEEPS GROWING')
            c.text('t(255) = 0',(270,246,1650,356),86,INK,'last-value',role='fixed-math')
            c.text('0, 1, 1, 0, 1, 0, 0, 1, …',(260,446,1660,528),58,TEAL,'prefix',role='fixed-math')
            c.text('… 1, 0, 0, 1, 0, 1, 1, 0',(260,581,1660,663),58,TEAL,'suffix',role='fixed-math')
            c.text('128 zeros. 128 ones.',(350,718,1570,784),43,INK,'balanced-counts',role='fixed-math')
            c.text('Terms counted: 256 / 256',(1240,962,1800,1026),25,MUTED,'progress',role='progress',completed_count=256)
            return c
        c=Canvas('outro-overhead',True);m.header(c,sub='256 TERMS · READ EACH ROW LEFT TO RIGHT')
        self.grid(c,256,255 if step!=1 else 0,True)
        text='0, 1, 1, 0 · REPLAY' if step==1 else 't(0) = 0 · t(2n) = t(n) · t(2n + 1) = 1 − t(n)' if step==2 else 't(255) = 1 − t(127) = 0'
        c.text(text,(230,859,1690,925),37 if step==2 else 47,INK,'final-rule',role='fixed-math')
        self.footer(c,256,step==1);return c

    @lru_cache(maxsize=12)
    def base(self,scene,index,revealed,completed,mode,step,phase):
        if scene=='count':
            c=Canvas('count-'+mode,mode=='overhead');m.header(c,sub='THE PEARL WEAVING ATELIER' if mode=='strip' else 'ONE SPOKEN VALUE · ONE WOVEN TILE')
            self.rule_pipeline(c,index,revealed,completed,mode)
        elif scene=='intro':c=self.intro(step)
        elif scene=='outro':c=self.outro(step)
        else:c=self.explanation(int(scene.split('-')[1]),step,phase)
        c.finish()
        return c.im,c.records,c.meta

    def reference_motion(self,c,k,p,mode):
        if k==0 or p<=.1 or p>=.96:return
        pv=pc(k//2)
        if mode=='strip':
            if p<.45:
                q=smooth((p-.1)/.35);x,y=lerp(490,625,q),565;v=pv
            elif p<.6:return
            else:
                q=smooth((p-.6)/.36);x,y=lerp(1110,1260,q),565;v=pc(k)
        else:
            if p<.45:
                q=smooth((p-.1)/.35);x,y=1160,lerp(621,661,q);v=pv
            elif p<.6:return
            else:
                q=smooth((p-.6)/.36);x,y=lerp(1375,1450,q),lerp(745,627,q);v=pc(k)
        # Occlude the route behind the transported glyph. Without this clear
        # chip, the arrow's horizontal stroke crossed 0 and made it look like θ.
        chip=(round(x)-24,round(y)-22,round(x)+24,round(y)+22)
        c.draw.rounded_rectangle(chip,radius=10,fill=CREAM,outline='#b3c6bb',width=2)
        c.moving(v,x,y,27,TEAL,'moving-reference',math_index=k,value=v,fill=CREAM,
                 reference_chip_box_xyxy=list(chip),route_occluded_under_glyph=True)

    def image(self,s,measure=False):
        scene=s['scene'];index=s.get('index',0);revealed=s.get('result_revealed',True);completed=s['completed_count'];mode=s.get('mode','strip');step=s.get('step',0)
        phase=s.get('step_phase',0.)
        # Only the explanatory column reveal needs multiple cached teaching bases.
        if scene=='explain-015':phase=round(phase*8)/8
        elif scene=='explain-031':phase=round(phase*16)/16
        elif scene=='explain-003' and step in (1,2):phase=round(phase*20)/20
        else:phase=0.
        base,records,meta=self.base(scene,index,revealed,completed,mode,step,phase)
        actor=self.actor_at(s);motion=s.get('operation_phase',1.) if scene=='count' and not revealed else 1.
        fade_start=self.duration-.45
        fade_end=(self.frames-1)/30
        fade=round(255*(1-clamp(s['time_s']/.35))) if s['time_s']<.35 else round(255*clamp((s['time_s']-fade_start)/(fade_end-fade_start))) if s['time_s']>fade_start else 0
        key=(scene,index,revealed,completed,mode,step,phase,motion,
             tuple(actor.items()) if actor else None,fade)
        key=str(key)
        if key in self.raw_cache and not measure:return self.raw_cache[key],self.reports[key]
        im=base.copy();extra=[];ar=None
        if scene=='count' and not revealed:
            c=Canvas.__new__(Canvas);c.im=im;c.draw=ImageDraw.Draw(im);c.name=f'{scene}-{index}';c.records=[]
            self.reference_motion(c,index,motion,mode);extra=c.records
        if actor:
            if self.anim:
                ar=self.anim.draw_character(im,actor['state'],actor['phase'],actor['height'],actor['foot'])
            else:
                spr=Image.open(ROOT/'assets/library/characters/onagadori/sources/v002/neutral.png').convert('RGBA');scale=actor['height']/736
                spr=spr.resize((round(spr.width*scale),round(spr.height*scale)),Image.Resampling.LANCZOS);xy=(round(actor['foot'][0]-350*scale),round(actor['foot'][1]-819*scale));im.alpha_composite(spr,xy)
                b=m.visible(spr,8);ar={'state':'neutral-draft-only','visible_box_xyxy':[b[0]+xy[0],b[1]+xy[1],b[2]+xy[0],b[3]+xy[1]]}
            box=ar.get('visible_box_xyxy',ar.get('visible_bbox_px',ar.get('visible_bbox')))
            if not box or not(15<box[0]<box[2]<1905 and 15<box[1]<box[3]<1060):raise ValueError(('actor cut',s,ar))
            for rec in records+extra:
                a=rec['visible_box_xyxy']
                if max(a[0],box[0])<min(a[2],box[2]) and max(a[1],box[1])<min(a[3],box[3]):raise ValueError(('actor obscures teaching glyph',s,rec['component_id'],box))
        if fade:
            wash=Image.new('RGBA',SIZE,CREAM);wash.putalpha(fade);im.alpha_composite(wash)
        component_key=(scene,index,revealed,completed,mode,step,phase)
        if component_key not in self.component_cache:
            self.component_cache[component_key]=[{**r,'math_index':r.get('math_index',meta.get('math_index',index if scene=='count' else None)),'scene':scene} for r in records]
        all_records=self.component_cache[component_key]+[{**r,'math_index':index,'scene':scene,'background_path':rel(m.OVERHEAD if mode=='overhead' else m.BG)} for r in extra]
        report={'state_key':key,'state':s,'components':all_records,'actor':ar,'actor_schedule_state':actor,'fade_alpha':fade,'metadata':meta,'source_alignment_passed':all(x['passed'] for x in all_records)}
        raw=im.convert('RGB').tobytes()
        if len(self.raw_cache)>20:self.raw_cache.clear()
        self.raw_cache[key]=raw
        if key not in self.reports:self.reports[key]=report
        return raw,report


def ffbin(name):return str(ROOT/'.venv/bin'/name)

def encode(path,frame_count=None):
    last_frame_key=['-force_key_frames',f'{(frame_count-1)/30:.9f}'] if frame_count else []
    return subprocess.Popen([ffbin('ffmpeg'),'-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','-',
      '-an','-vf','scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p',
      '-c:v','libx264','-preset','fast','-crf','18',*last_frame_key,'-pix_fmt','yuv420p','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-color_range','tv',
      '-bsf:v','h264_metadata=video_full_range_flag=0:colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1','-movflags','+write_colr+faststart',str(path)],stdin=subprocess.PIPE)


def export_samples(ep,out):
    out.mkdir(parents=True,exist_ok=True);rows=[];chosen=set()
    # Every count before/during/after speech and its own input/operator transition.
    for c in ep.counts:
        for t in [c['operation_start_s'],c['operation_start_s']+.5,c['operation_start_s']+1.15,c['reveal_s']-.04,c['voice_start_s']-.04,c['voice_start_s'],c['voice_end_s']-.04,c['voice_end_s']+.04]:chosen.add(max(0,min(ep.frames-1,round(t*30))))
    for e in ep.events:
        if not e['id'].startswith('C'):
            for t in [e['start_s'],(e['start_s']+e['end_s'])/2,e['end_s']]:chosen.add(max(0,min(ep.frames-1,round(t*30))))
    for f in sorted(chosen):
        s=ep.state(f);raw,report=ep.image(s,True)
        rows.append({'frame':f,'time_s':f/30,**report})
    with gzip.open(out/'component-locators.jsonl.gz','wt',encoding='utf8') as fp:
        for row in rows:fp.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
    times=[]
    for k in [0,2,3,4,9,10,15,16,31,32,64,99,100,127,128,160,191,192,224,254,255]:times.append(ep.counts[k]['voice_start_s']+.1)
    for e in ep.events:
        if e['id'].startswith(('I','X','O')):times.append((e['start_s']+e['end_s'])/2)
    images=[]
    for j,t in enumerate(times):
        f=min(ep.frames-1,round(t*30));s=ep.state(f);raw,report=ep.image(s,True)
        p=out/f'{j:02d}-{s["scene"]}-{f:05d}.png';im=Image.frombytes('RGB',SIZE,raw);im.save(p);images.append(im)
    cols=4;rows_n=math.ceil(len(images)/cols);board=Image.new('RGB',(1920,rows_n*290),'#fffaf0');draw=ImageDraw.Draw(board)
    for j,im in enumerate(images):
        x=j%cols*480;y=j//cols*290;board.paste(im.resize((480,270),Image.Resampling.LANCZOS),(x,y));draw.text((x+12,y+272),f'{j:02d}',font=m.font(14),fill=INK)
    board.save(out/'contact.jpg',quality=94)
    (out/'geometry.json').write_text(json.dumps(GEOMETRY,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'locator_frames':len(rows),'sample_images':len(images),'all_source_alignment_passed':all(x['source_alignment_passed'] for x in rows)}),flush=True)


def render(ep,out,audio=None,preview=False,encoded_aac=None):
    out.mkdir(parents=True,exist_ok=False)
    frames=list(range(ep.frames))
    if preview:
        selected=set()
        for a,b in [(0,.6),(ep.byid['I003']['start_s']-.2,ep.byid['I004']['start_s']+.2),
                    (ep.byid['X003a']['start_s']-.1,ep.byid['X003b']['start_s']+.2),
                    (ep.counts[32]['operation_start_s'],ep.counts[32]['voice_end_s']+.1),
                    (ep.byid['X031b']['start_s']-.2,ep.byid['X031d']['end_s']+.2),
                    (ep.byid['X127b']['start_s']-.2,ep.byid['X127e']['end_s']+.1),
                    (ep.duration-.8,ep.duration)]:
            selected.update(range(max(0,round(a*30)),min(ep.frames,round(b*30))))
        frames=sorted(selected)
    silent=out/'silent-picture.mp4';p=encode(silent,len(frames))
    with gzip.open(out/'frame-states.jsonl.gz','wt',encoding='utf8') as fp:
        for i,f in enumerate(frames):
            s=ep.state(f);raw,report=ep.image(s);p.stdin.write(raw)
            fp.write(json.dumps({**s,'frame':i,'episode_frame':f,'state_key':report['state_key'],'actor':report['actor_schedule_state'],'fade_alpha':report['fade_alpha']},ensure_ascii=False,separators=(',',':'))+'\n')
            if i%900==0:print(json.dumps({'rendered_frames':i,'total_frames':len(frames)}),flush=True)
    p.stdin.close()
    if p.wait()!=0:raise RuntimeError('ffmpeg encoder failed')
    with gzip.open(out/'distinct-reports.jsonl.gz','wt',encoding='utf8') as fp:
        for row in ep.reports.values():fp.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
    for source in ep.input_receipts:
        if sha(ROOT/source['path'])!=source['sha256']:raise ValueError(('input changed during render',source['path']))
    final=silent
    if (audio or encoded_aac) and not preview:
        final=out/VIDEO_NAME
        audio_options=['-c:a','copy'] if encoded_aac else ['-c:a','aac','-b:a','192k','-ar','48000','-ac','2']
        duration_options=[] if encoded_aac else ['-t',str(ep.frames/30)]
        subprocess.run([ffbin('ffmpeg'),'-v','error','-y','-i',str(silent),'-i',str(Path(encoded_aac or audio).resolve()),'-map','0:v:0','-map','1:a:0','-c:v','copy',*audio_options,*duration_options,
            '-bsf:v','h264_metadata=video_full_range_flag=0:colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1','-color_primaries:v','bt709','-color_trc:v','bt709','-colorspace:v','bt709','-color_range:v','tv','-video_track_timescale','15360','-movflags','+write_colr+faststart',str(final)],check=True)
    (out/'geometry.json').write_text(json.dumps(GEOMETRY,ensure_ascii=False,indent=2)+'\n')
    (out/'actor-schedule.json').write_text(json.dumps(ep.actor_events,ensure_ascii=False,indent=2)+'\n')
    summary={'status':'rendered_pending_final_qa','preview':preview,'video':receipt(final),'silent_picture':receipt(silent),'timeline':receipt(ep.timeline_path),'renderer':receipt(__file__),'frame_count':len(frames),'duration_s':len(frames)/30,
      'source_alignment_passed':all(x['source_alignment_passed'] for x in ep.reports.values()),'distinct_states':len(ep.reports),
      'immutable_inputs':ep.input_receipts,
      'backgrounds':[receipt(m.BG),receipt(m.OVERHEAD)],'font':receipt(m.FONT),'actor_module':receipt(ROOT/'tools/thue_morse_animation.py') if ep.anim else None,
      'frame_states':receipt(out/'frame-states.jsonl.gz'),'state_reports':receipt(out/'distinct-reports.jsonl.gz'),'accepted_aac':receipt(encoded_aac) if encoded_aac else None}
    (out/'render-manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return final


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--timeline',type=Path,required=True);ap.add_argument('--audio',type=Path);ap.add_argument('--encoded-aac',type=Path);ap.add_argument('--out-dir',type=Path,required=True);ap.add_argument('--preview',action='store_true');ap.add_argument('--samples-only',action='store_true');ap.add_argument('--allow-still',action='store_true')
    a=ap.parse_args();ep=Episode(a.timeline,a.allow_still)
    if a.samples_only:export_samples(ep,a.out_dir)
    else:print(json.dumps({'video':str(render(ep,a.out_dir,a.audio,a.preview,a.encoded_aac))}),flush=True)


if __name__=='__main__':main()
