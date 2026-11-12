"""Triangular v002: singular row label and visible N053 forepaw reaction.

V001 sources/media are immutable inputs. Approved AAC is copied, never encoded.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import asdict,dataclass
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

from PIL import Image,ImageChops,ImageDraw,ImageOps

try:
    import render_triangular_mockups as m
    import triangular_animation_v002 as animation
except ModuleNotFoundError:
    from tools import render_triangular_mockups as m
    from tools import triangular_animation_v002 as animation

ROOT=m.ROOT;DESIGN=m.DESIGN;FPS=30;SIZE=(1920,1080)
VIDEO_NAME='paspla-studio-triangular-numbers-0-to-1830-1080p-bt709.mp4'
REVISION=DESIGN/'revision-v002'
AAC_SOURCE=ROOT/'output/triangular-counting-001-v001/paspla-studio-triangular-numbers-0-to-1830-1080p-bt709.mp4'
APPROVED_AAC_SOURCE_SHA256='c78e6f2fce80f26901cdb1c90d8bdefc60c9ac40d54da9097895f60bd791be86'
APPROVED_TIMELINE_SHA256='c0533218beaa2c8d180b98f4e0fa91d09dbe3ed3e40dba8c6ada5a216b3075a4'
FORMULA_BOX=(363,153,1557,233);RESULT_BOX=(600,265,1320,380);READING_BOX=(300,389,1620,430)
PROGRESS_BOX=(170,1005,735,1045)


def resolve(path):return animation.resolve(path)
def local(path):return animation.local(path)
def sha(path):return animation.sha(path)
def receipt(path):return {'path':local(path),'sha256':sha(path)}
def clamp(x):return max(0,min(1,x))
def smooth(x):x=clamp(x);return x*x*(3-2*x)
def tick(x):return round(clamp(x)*60)
def ffbin(name):
    p=ROOT/'.venv/bin'/name
    return str(p) if p.exists() else shutil.which(name)


class Canvas(m.Canvas):
    def clearance(self):
        contacts=[]
        for i,a in enumerate(self.records):
            for b in self.records[i+1:]:
                aa,bb=a['visible_box_xyxy'],b['visible_box_xyxy']
                if max(aa[0],bb[0])>=min(aa[2],bb[2]) or max(aa[1],bb[1])>=min(aa[3],bb[3]):continue
                la,oa=self.layers[a['component_id']];lb,ob=self.layers[b['component_id']]
                region=(max(aa[0],bb[0]),max(aa[1],bb[1]),min(aa[2],bb[2]),min(aa[3],bb[3]))
                masks=[]
                for layer,origin in ((la,oa),(lb,ob)):
                    masks.append(layer.getchannel('A').point(lambda z:255 if z>=128 else 0).crop(
                        (region[0]-origin[0],region[1]-origin[1],region[2]-origin[0],region[3]-origin[1])))
                if ImageChops.multiply(*masks).getbbox():
                    raise ValueError(f'Foreground collision: {self.scene}: {a["component_id"]}/{b["component_id"]}')
        self.data['foreground_clearance_pass']=True


@dataclass(frozen=True)
class Frame:
    mode:str
    n:int
    phase:str
    build:int
    angle:int
    merge:int
    remove:int
    zoom:int
    highlight:str
    completed:int
    cue:str
    lesson:int
    pose:str
    fade:int=0


def prepare(path):
    p=json.loads(Path(path).read_text())
    if 'voice_events' not in p:
        events=[]
        for r in p['cues']:
            events.append({**r,'text':r['text_en'],'start_s':r['slot_start_s'],'end_s':r['slot_end_s'],
                           'duration_s':r['slot_end_s']-r['slot_start_s']})
        p={**p,'voice_events':events,'duration_s':events[-1]['end_s']+1.2,'preview_plan_only':True}
    p.setdefault('duration_frames',math.ceil(p['duration_s']*FPS));p.setdefault('fps',FPS)
    if p['fps']!=FPS:raise ValueError('Triangular video requires 30fps timeline')
    events=p['voice_events'];by={e['id']:e for e in events}
    if len(events)!=131:raise ValueError('The complete 131-cue triangular script is required')
    if 'counted_states' not in p:
        p['counted_states']=[]
        for n in range(61):
            v=by[f'N{n:03d}'];e=by.get(f'E{n:03d}')
            p['counted_states'].append({'n':n,'index':n,'value':n*(n+1)//2,'voice_start_s':v['start_s'],
                'voice_end_s':v['end_s'],'result_start_s':v['start_s']-.12,
                'cycle_start_s':e['start_s'] if e else v['start_s']-.12,
                'formula_start_s':e['start_s'] if e else None,'formula_end_s':e['end_s'] if e else None})
    return p


class Episode:
    def __init__(self,timeline,registry=None,background=None):
        self.timeline_path=Path(timeline);self.plan=prepare(timeline)
        self.events=self.plan['voice_events'];self.by={e['id']:e for e in self.events}
        self.starts=[e['start_s'] for e in self.events]
        self.counts=self.plan['counted_states'];self.ends=[r['voice_end_s'] for r in self.counts]
        self.background_path=resolve(background) if background else m.BG
        self.background=ImageOps.fit(Image.open(self.background_path).convert('RGBA'),SIZE,Image.Resampling.LANCZOS)
        self.art=animation.Artwork(registry);self.schedule=animation.Schedule(self.plan,self.art)
        self.segments=[{'mode':'intro','n':0,'cue':'I01','start_frame':0}]
        for n in range(61):
            count=self.counts[n]
            self.segments.append({'mode':'count','n':n,'cue':f'N{n:03d}' if n==0 else f'E{n:03d}',
                                  'start_frame':math.ceil(count['cycle_start_s']*FPS)})
            ex=[e for e in self.events if e['id'].startswith(f'X{n:03d}')]
            if ex:self.segments.append({'mode':'replay','n':n,'cue':ex[0]['id'],
                'start_frame':math.ceil((ex[0]['start_s']-.12)*FPS)})
        outro_start=self.plan.get('finale',{}).get('start_s',self.by['O01']['start_s']-.12)
        self.segments.append({'mode':'outro','n':60,'cue':'O01','start_frame':math.ceil(outro_start*FPS)})
        self.segments.sort(key=lambda r:r['start_frame']);self.segment_starts=[r['start_frame'] for r in self.segments]
        for i,r in enumerate(self.segments):r['end_frame']=self.segments[i+1]['start_frame'] if i+1<len(self.segments) else self.plan['duration_frames']
        self.cuts=[r['start_frame'] for i,r in enumerate(self.segments) if i and self.scale_key(r)!=self.scale_key(self.segments[i-1])
                   and not (r['mode']=='count' and r['n']==0)]
        self.reports={};self.frame_rows=[]

    def scale_key(self,segment):
        mode,n=segment['mode'],segment['n']
        if mode!='count':return (mode,n if mode=='replay' else 0)
        return ('count','large' if n>=45 else 'dense' if n>10 else 'small')

    def operation(self,n,t):
        e=self.by[f'E{n:03d}'];s,eend=e['start_s'],e['end_s'];d=eend-s
        h=self.counts[n].get('highlight_timing') or e.get('highlight_timing') or {}
        times=h.get('times_start_s',s+d*.22);b=h.get('b_start_s',s+d*.39)
        divided=h.get('divided_start_s',s+d*.67);eq=h.get('equals_start_s',s+d*.89)
        if not (s<=times<=b<=divided<=eq<=eend+.05):raise ValueError(f'Operator timings invalid {n}: {h}')
        rotate_end=b+(divided-b)*.58
        commit=self.counts[n]['result_start_s']
        if t>=commit:return ('result',60,60,60,60,60,'result')
        if t<times:return ('build',tick((t-s)/max(.01,times-s)),0,0,0,0,'first')
        if t<b:return ('copy',60,0,0,0,0,'times')
        if t<rotate_end:return ('rotate',60,tick((t-b)/max(.01,rotate_end-b)),0,0,0,'second')
        if t<divided:return ('pair',60,60,tick((t-rotate_end)/max(.01,divided-rotate_end)),0,0,'second')
        if t<eq:return ('half',60,60,60,tick((t-divided)/max(.01,eq-divided)),0,'divide')
        return ('settle',60,60,60,60,tick((t-eq)/max(.01,commit-eq)),'equals')

    def state(self,frame):
        t=frame/FPS;segment=self.segments[max(0,bisect_right(self.segment_starts,frame)-1)]
        mode,n,cue=segment['mode'],segment['n'],segment['cue']
        active=self.events[max(0,bisect_right(self.starts,t)-1)]
        phase='result';build=angle=merge=remove=zoom=60;highlight='result';lesson=0
        if mode=='count' and n:
            phase,build,angle,merge,remove,zoom,highlight=self.operation(n,t)
            cue=f'N{n:03d}' if t>=self.by[f'N{n:03d}']['start_s'] else f'E{n:03d}'
        elif mode=='intro':
            cue=active['id'] if active['id'].startswith('I') else 'I03'
            phase='intro';e=self.by[cue];lesson=tick((t-e['start_s'])/max(.01,e['duration_s']))
        elif mode=='replay':
            phase='replay'
            if n==4:
                ea,eb=self.by['X004a'],self.by['X004b']
                if t<eb['start_s']:
                    cue='X004a';u=clamp((t-ea['start_s'])/max(.01,ea['duration_s']))
                    if u<.38:phase='build';build=tick(u/.38);angle=merge=remove=zoom=0
                    elif u<.76:phase='rotate';build=60;angle=tick((u-.38)/.38);merge=remove=zoom=0
                    else:phase='pair';build=angle=60;merge=tick((u-.76)/.24);remove=zoom=0
                else:
                    cue='X004b';u=clamp((t-eb['start_s'])/max(.01,eb['duration_s']))
                    if u<.28:phase='pair';build=angle=merge=60;remove=zoom=0
                    elif u<.78:phase='half';build=angle=merge=60;remove=tick((u-.28)/.50);zoom=0
                    else:phase='result';build=angle=merge=remove=zoom=60
            e=self.by[cue];lesson=tick((t-e['start_s'])/max(.01,e['duration_s']))
        elif mode=='outro':
            lesson=tick((t-self.by['O01']['start_s'])/self.by['O01']['duration_s'])
        fade_frames=max(2,round(self.plan.get('finale',{}).get('fade_last_s',1.2)*FPS))
        fade=round((1-clamp(frame/18))*255) if frame<18 else round(clamp((frame-(self.plan['duration_frames']-fade_frames))/(fade_frames-1))*255)
        for cut in self.cuts:
            if abs(frame-cut)<=4:fade=max(fade,round((1-abs(frame-cut)/4)*255))
        pose=self.schedule.pose(frame,mode,phase,n)
        return Frame(mode,n,phase,build,angle,merge,remove,zoom,highlight,bisect_right(self.ends,t),cue,lesson,pose,fade)

    def formula(self,c,n,committed,highlight,text=None):
        c.panel((340,139,1580,250))
        full=text or f'{n} × {n+1} ÷ 2 = '+(f'{n*(n+1)//2:,}' if committed else '?')
        if text:c.text(full,FORMULA_BOX,65,m.INK,'working-equation')
        else:
            pieces=[str(n),' × ',str(n+1),' ÷ 2',' = ',f'{n*(n+1)//2:,}' if committed else '?']
            active={'first':0,'times':1,'second':2,'divide':3,'equals':4,'result':5}.get(highlight)
            layer=m.colored_text_layer([(s,m.EDGE if i==active and i!=3 else m.TEAL if i==active else m.INK) for i,s in enumerate(pieces)],65)
            c.center(layer,FORMULA_BOX,'working-equation');c.records[-1].update(text=full,font_size_px=65,highlight=highlight)
        c.data.update(n=n,value=n*(n+1)//2,equation=full,result_committed=committed)

    def result(self,c,n,committed=True):
        c.text(f'{n*(n+1)//2:,}' if committed else '?',RESULT_BOX,108,m.INK,'result')
        c.text(m.words(n*(n+1)//2) if committed else 'watch the formula work',READING_BOX,31,m.MUTED,'result-reading')

    def point_group(self,c,points,radius,group,ident,new_row=None):
        if not points:
            c.data.setdefault('intentional_empty_groups',[]).append(ident);return
        xmin=min(p[0] for p in points);xmax=max(p[0] for p in points)
        ymin=min(p[1] for p in points);ymax=max(p[1] for p in points)
        ox,oy=math.floor(xmin-radius)-20,math.floor(ymin-radius)-20
        layer=Image.new('RGBA',(math.ceil(xmax+radius)-ox+21,math.ceil(ymax+radius)-oy+21));draw=ImageDraw.Draw(layer)
        for i,(x,y) in enumerate(points):
            q=(round(x-radius-ox),round(y-radius-oy),round(x+radius-ox),round(y+radius-oy))
            if group=='A':
                fill=m.TEAL if new_row is not None and i>=new_row else m.AMBER
                draw.ellipse(q,fill=fill,outline=m.EDGE if fill==m.AMBER else '#2c6667',width=max(1,round(radius*.12)))
                if radius>=10:draw.ellipse((x-radius*.47-ox,y-radius*.55-oy,x-radius*.06-ox,y-radius*.15-oy),fill='#fff3c9')
            else:draw.ellipse(q,fill='#e1f4ee',outline=m.TEAL,width=max(1,round(radius*.23)))
        target=((xmin+xmax)/2+.5,(ymin+ymax)/2+.5)
        c.fixed(layer,(ox,oy),ident,target,kind='mathematical point group trajectory')
        c.records[-1].update(point_count=len(points),point_radius_px=radius,copy=group)

    def geometry(self,c,s,force_new_row=False,override_n=None,scale_progress=None,new_row_fraction=None):
        n=s.n if override_n is None else override_n
        if not n:
            c.draw.rounded_rectangle((690,496,1230,738),radius=28,outline='#bca989',width=3)
            c.text('NO ROWS · NO DOTS',(720,575,1200,654),37,m.MUTED,'zero-label')
            c.data['diagram']={'n':0,'A':0,'B':0,'intentional_empty':True};return
        large=n>=45 and s.mode=='count'
        final_h=435 if large else 340 if n>10 else 295
        final_cy=665 if large else 620
        op_cy=700 if large else 620
        op_h=min(final_h,380 if large else 260)
        z=smooth(s.zoom/60) if scale_progress is None else scale_progress
        cy=op_cy+(final_cy-op_cy)*z
        height=op_h+(final_h-op_h)*z
        pitch=min(62,height/max(1,n-.36));radius=min(17,pitch*.32)
        x0=960-(n-1)*pitch/2;y0=cy-(n-1)*pitch/2
        rows=n if s.build==60 else max(0,math.ceil(n*s.build/60))
        new_boundary=n*(n-1)//2 if force_new_row else None
        new_visible=n if new_row_fraction is None else math.ceil(n*clamp(new_row_fraction))
        aa=[(x0+col*pitch,y0+row*pitch) for row in range(rows) for col in range(row+1)
            if row<n-1 or col<new_visible]
        if new_row_fraction is not None:rows=n if new_visible else n-1
        self.point_group(c,aa,radius,'A','points-A',new_boundary)
        has_b=s.phase in ('copy','rotate','pair','half')
        bb=[];angle=math.pi*smooth(s.angle/60)
        shift=450*(1-smooth(s.merge/60)) if s.phase in ('copy','rotate','pair') else 480*smooth(s.remove/60)
        if has_b and not (s.phase=='half' and s.remove>=60):
            px=n*pitch/2;py=(n-1)*pitch/2
            for row in range(n):
                for col in range(row+1):
                    x=col*pitch-px;y=row*pitch-py
                    bb.append((x0+px+x*math.cos(angle)-y*math.sin(angle)+shift,
                               y0+py+x*math.sin(angle)+y*math.cos(angle)))
            self.point_group(c,bb,radius,'B','points-B')
        c.text(f'n = {n} '+('row' if n==1 else 'rows'),(180,606,650,650),30,m.EDGE,'row-label')
        c.text(f'rectangle width: n + 1 = {n+1}',(150,674,690,718),25,m.TEAL,'column-label')
        c.text('A: filled dots',(170,871,700,904),25,m.EDGE,'legend-A')
        if has_b:c.text('B: matching ring dots',(170,919,700,952),25,m.TEAL,'legend-B')
        elif n>10:c.text('ALL DOTS SHOWN',(170,919,700,952),24,m.MUTED,'density-note')
        c.data['diagram']={'n':n,'A':len(aa),'B':len(bb),'expected_full_A':n*(n+1)//2,
            'expected_full_B':n*(n+1)//2,'visible_rows':rows,'pitch_px':pitch,'radius_px':radius,
            'base_origin_px':[x0,y0],'row_count':n,'column_count':n+1,'center_y_px':cy,
            'rotation_radians':angle,'B_translation_x_px':shift,'zoom':z,'all_points_drawn':True,
            'representation':'one actual dot per unit; B is a rigid 180-degree copy',
            'individual_dot_counting_expected':n<=10,'new_row_boundary':new_boundary,
            'new_row_visible_points':new_visible if new_row_fraction is not None else None}

    @lru_cache(maxsize=12)
    def image(self,s):
        ident=hashlib.sha256(json.dumps(asdict(s),sort_keys=True).encode()).hexdigest()[:20]
        c=Canvas(self.background,ident)
        m.header(c,'REPLAY · NO NEW TERM' if s.mode=='replay' else 'NUM-NUM NUMBERS · THE LIGHT-PEBBLE GROTTO')
        if s.mode=='intro':self.intro(c,s);foot,height=(960,1044),356
        elif s.mode=='outro':self.outro(c,s);foot,height=(960,1044),231
        elif s.mode=='replay':
            self.replay(c,s);foot,height=((960,1050),150) if s.n==45 else ((960,1044),215)
        else:
            show=s.phase=='result';self.formula(c,s.n,show,s.highlight);self.result(c,s.n,show);self.geometry(c,s)
            foot,height=((1780,1046),164) if s.n>=45 else ((960,1044),215 if s.n>10 else 235)
        c.text(f'Counted: {s.completed} / 61',PROGRESS_BOX,26,m.MUTED,'completed-progress')
        self.art.draw(c,s.pose,foot,height)
        c.clearance()
        c.data.update(completed=s.completed,progress_rule='number of N cues whose end_s <= frame/30',state=asdict(s))
        image=c.image
        if s.fade:image=Image.blend(image,Image.new('RGBA',SIZE,m.CREAM),s.fade/255)
        self.reports[ident]={'state':asdict(s),'components':c.records,'data':c.data,
                             'foreground_clearance_pass':True,'whole_frame_fade':bool(s.fade)}
        return image.convert('RGB'),ident

    def intro(self,c,s):
        c.text('A new row. A bigger triangle.',(220,156,1700,226),52,m.INK,'intro-line')
        c.text('Tₙ = n × (n + 1) ÷ 2',(340,266,1580,346),66,m.INK,'general-formula')
        # A four-row example supports the introduction without exposing 1,830.
        n=4;p=50;r=16;x0=885;y0=404
        pts=[(x0+j*p,y0+i*p) for i in range(n) for j in range(i+1)]
        self.point_group(c,pts,r,'A','intro-triangle')
        line={'I01':'0, 1, 3, 6, 10, 15, …','I02':'n tells the rows · Tₙ tells the total',
              'I03':'two matching triangles → one rectangle → one equal half'}[s.cue]
        c.text(line,(250,610,1670,664),34 if s.cue=='I03' else 40,m.TEAL,'intro-subject')
        c.data.update(no_endpoint_revealed=True,intro_cue=s.cue)

    def replay(self,c,s):
        n=s.n
        if n==4:
            self.formula(c,n,True,'divide' if s.phase=='half' else 'second');self.result(c,n,True);self.geometry(c,s)
        elif n in (5,45):
            before=n*(n-1)//2;value=n*(n+1)//2
            self.formula(c,n,True,'result',text=f'{before:,} + {n} = {value:,}');self.result(c,n)
            # Retain old rows; reveal the entire new row in its own explanatory beat.
            q=Frame(s.mode,n,'result',60,60,60,60,60,s.highlight,s.completed,s.cue,s.lesson,s.pose,s.fade)
            self.geometry(c,q,force_new_row=True,new_row_fraction=(s.lesson-10)/15)
            if n==45:c.text('1,000 is the mark we crossed',(450,840,1470,883),31,m.TEAL,'threshold-note')
        else:
            self.formula(c,n,True,'result');self.result(c,n);self.geometry(c,s)
            note='Every dot still counts as one.' if n==10 else 'Three digits. The same rule.'
            c.text(note,(1190,907,1790,954),26,m.TEAL,'replay-note')
        c.data.update(replay=True,count_advanced=False)

    def outro(self,c,s):
        c.text('Tₙ = 1 + 2 + … + n = n × (n + 1) ÷ 2',(170,155,1750,229),52,m.INK,'ending-formula')
        c.text('Sum for n >= 1; T₀ = 0',(350,243,1570,270),22,m.MUTED,'sum-domain')
        c.panel((260,279,1660,700))
        values=[f'{n*(n+1)//2:,}' for n in range(61)]
        for row in range(7):c.text('   '.join(values[row*9:row*9+9]),(290,300+row*54,1630,342+row*54),29,m.INK,f'history-row-{row}')
        c.text('Each new row makes the next number.',(240,731,1680,784),39,m.TEAL,'ending-line')
        c.data.update(all_61_values=[n*(n+1)//2 for n in range(61)],term_count=61,rows=60)

    def write_contract(self,out):
        out=Path(out);out.mkdir(parents=True,exist_ok=True)
        contract={'kind':'triangular-production-layout-v002','fps':FPS,'resolution_px':list(SIZE),
            'timeline':receipt(self.timeline_path),'background':receipt(self.background_path),'renderer':receipt(Path(__file__)),
            'animation':receipt(Path(animation.__file__)),'art':self.art.receipt(),'font':receipt(m.FONT),
            'formula':{'content_box':FORMULA_BOX,'font_px':65},'result':{'content_box':RESULT_BOX,'font_px':108},
            'reading':{'content_box':READING_BOX,'font_px':31},'progress':{'content_box':PROGRESS_BOX,'font_px':26},
            'dot_model':{'A':'r=0..n-1,c=0..r','B':'rotate same A by pi around (n*p/2,(n-1)*p/2), then translate into rectangle',
                'count_one':1830,'count_double':3660,'radius':'min(17,0.32*pitch)',
                'operation_height':'min(final_height,380 if n>=45 else260)',
                'final_height':'435 if count n>=45;340 if n>10;295 otherwise',
                'pitch':'min(62,height/max(1,n-.36))','center':'large operation(960,700), uniform settle to final(960,665); other modes(960,620)',
                'A_origin':'(960-(n-1)*pitch/2, center_y-(n-1)*pitch/2)',
                'B_start_shift_x':450,'B_removal_end_shift_x':480,'A_color':m.AMBER,'A_outline':m.EDGE,
                'B_fill':'#e1f4ee','B_outline':m.TEAL,'rendering':'one actual circle per unit, integer raster boundary rounding',
                'small_unit_counting':'n<=10','large':'all dots, labels support reading; operation dots smaller then uniform readability zoom'},
            'timing':{'build':'E.start to times_start','copy':'times_start to b_start',
                'rotate':'b_start to b_start+.58*(divided_start-b_start)',
                'pair':'rotation end to divided_start','half':'divided_start to equals_start',
                'readability_zoom':'equals_start to N.start-.12, after B removed',
                'result_commit':'N.start-.12','result_hold':'stable formula, main value, reading and A through N.end',
                'easing':'smoothstep on each motion; 61 ticks including both endpoints','progress':'N.end only'},
            'segments':self.segments,'scene_scale_cuts':self.cuts,'actor_schedule':self.schedule.receipt(),
            'subscript_n':'MPLUS lacks U+2099; smaller literal n at .64 font scale with .39*size lower baseline; group measured together',
            'fades':{'intro_frames':18,'end_frames':max(2,round(self.plan.get('finale',{}).get('fade_last_s',1.2)*FPS)),
                'scene_cut_half_width_frames':4,'actor_crossfades':False,
                'seed_cut':'hard cut at N000.start-.12; no fade may hide the committed zero'}}
        (out/'layout-spec.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n')
        (out/'motion.json').write_text(json.dumps(self.schedule.receipt(),ensure_ascii=False,indent=2)+'\n')


def preview(ep,out_dir):
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True);samples=[]
    for cue in ('I01','I02','N000','E004','N004','X004a','X004b','X005','N014','X045','E060','N060','O01'):
        e=ep.by[cue];t=e['start_s']+min(.6,e['duration_s']/2);frame=round(t*FPS)
        im,ident=ep.image(ep.state(frame));path=out/f'{cue}-{frame:06d}.png';im.save(path)
        samples.append({'cue':cue,'time_s':frame/FPS,'state_id':ident,**receipt(path)})
    sheet=Image.new('RGB',(1920,math.ceil(len(samples)/3)*385),'#f2ecdf');d=ImageDraw.Draw(sheet)
    for i,r in enumerate(samples):
        x,y=(i%3)*640,(i//3)*385
        sheet.paste(Image.open(resolve(r['path'])).resize((624,351),Image.Resampling.LANCZOS),(x+8,y+8))
        d.text((x+14,y+359),r['cue'],font=m.font(18),fill=m.INK)
    sheet.save(out/'preview-contact-sheet.png')
    (out/'preview-manifest.json').write_text(json.dumps({'production_video':False,'timeline':receipt(ep.timeline_path),'samples':samples},ensure_ascii=False,indent=2)+'\n')
    return samples


def native_preflight(ep,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    for frame in range(ep.plan['duration_frames']):
        ep.image(ep.state(frame))
        if frame%(FPS*60)==0:print(json.dumps({'native_checked_frame':frame,'total_frames':ep.plan['duration_frames']}),flush=True)
    observations=[c for r in ep.reports.values() for c in r['components']]
    report={'kind':'triangular-v002-all-native-frame-preflight','status':'pass','timeline':receipt(ep.timeline_path),
        'frame_count':ep.plan['duration_frames'],'distinct_states':len(ep.reports),'component_observations':len(observations),
        'all_components_pass':all(c['passed'] for c in observations),
        'max_abs_dx_px':max(abs(c['delta_x_px']) for c in observations),
        'max_abs_dy_px':max(abs(c['delta_y_px']) for c in observations),
        'foreground_collisions':0,'scope':'all uncompressed raster states; independent completed MP4 inspection remains separate',
        'renderer':receipt(Path(__file__)),'animation':receipt(Path(animation.__file__))}
    (directory/'native-layout-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report


def motion_preview(ep,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    ranges=[('opening',max(0,round((ep.by['I01']['start_s']+.05)*FPS)),72),
            ('four-row-proof',round(ep.by['X004a']['start_s']*FPS),round((ep.by['X004b']['end_s']-ep.by['X004a']['start_s'])*FPS)),
            ('neck',round((ep.by['N027']['end_s']+.02)*FPS),57),
            ('blink',round((ep.by['N024']['end_s']+.20)*FPS),30),
            ('largest',round(ep.by['E060']['start_s']*FPS),round((ep.by['N060']['end_s']-ep.by['E060']['start_s'])*FPS)),
            ('closing',round((ep.by['O01']['end_s']-2.35)*FPS),72)]
    target=out/'acting-and-equation-review.mp4';total=sum(z[2] for z in ranges)
    with (out/'motion-preview-ffmpeg.log').open('wb') as log:
        proc=subprocess.Popen([ffbin('ffmpeg'),'-y','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','-',
            '-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(target)],
            stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
        try:
            for label,start,length in ranges:
                for frame in range(start,start+length):proc.stdin.write(ep.image(ep.state(frame))[0].tobytes())
        finally:proc.stdin.close()
        if proc.wait():raise RuntimeError('Motion preview encode failed')
    (out/'motion-preview-manifest.json').write_text(json.dumps({'video':receipt(target),'production_video':False,
        'audio_present':False,'duration_s':total/FPS,'timeline':receipt(ep.timeline_path),
        'extracts':[{'id':k,'source_start_frame':s,'frames':n} for k,s,n in ranges]},ensure_ascii=False,indent=2)+'\n')
    master=ep.plan.get('master_audio')
    if master:
        audio=resolve(master['path'] if isinstance(master,dict) else master)
        filters=[]
        for i,(_,start,length) in enumerate(ranges):
            filters.append(f'[1:a]atrim=start={start/FPS:.9f}:end={(start+length)/FPS:.9f},asetpts=PTS-STARTPTS[a{i}]')
        filters.append(''.join(f'[a{i}]' for i in range(len(ranges)))+f'concat=n={len(ranges)}:v=0:a=1[a]')
        voiced=out/'acting-and-equation-review-with-audio.mp4'
        subprocess.run([ffbin('ffmpeg'),'-v','error','-y','-i',str(target),'-i',str(audio),
            '-filter_complex',';'.join(filters),'-map','0:v:0','-map','[a]','-c:v','copy',
            '-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t',f'{total/FPS:.9f}',
            '-movflags','+faststart',str(voiced)],check=True)
        (out/'motion-preview-with-audio.json').write_text(json.dumps({'video':receipt(voiced),'production_video':False,
            'master':receipt(audio),'source_timeline':receipt(ep.timeline_path),
            'silent_preview_manifest':receipt(out/'motion-preview-manifest.json'),
            'extracts':[{'id':k,'source_start_frame':s,'source_end_frame_exclusive':s+n,
                         'output_start_frame':sum(r[2] for r in ranges[:i]),'frames':n}
                        for i,(k,s,n) in enumerate(ranges)],
            'timing':'unaltered frame-aligned source slices; no speed change','duration_s':total/FPS},indent=2)+'\n')
    return receipt(target)


def encode(ep,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);target=out/VIDEO_NAME
    if target.exists():raise FileExistsError(f'Preserve existing video; use a new render directory: {target}')
    if sha(ep.timeline_path)!=APPROVED_TIMELINE_SHA256:
        raise ValueError('Inherited AAC is bound to the approved immutable timeline; source timeline changed')
    if sha(AAC_SOURCE)!=APPROVED_AAC_SOURCE_SHA256:
        raise ValueError('Approved AAC copy source does not match its frozen media SHA256')
    master=ep.plan.get('master_audio')
    if not master or not ep.plan.get('speech_adopted'):raise ValueError('Adopted measured speech and master_audio required')
    if not ep.art.registration.get('production_ready'):raise ValueError('Use reviewed runtime production character registration')
    path=resolve(master['path'] if isinstance(master,dict) else master)
    if isinstance(master,dict) and sha(path)!=master['sha256']:raise ValueError('Master audio hash mismatch')
    duration=ep.plan['duration_frames']/FPS
    if duration<480:raise ValueError('The adopted episode must be at least eight minutes')
    command=[ffbin('ffmpeg'),'-y','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','-',
        '-i',str(AAC_SOURCE),'-map','0:v:0','-map','1:a:0','-frames:v',str(ep.plan['duration_frames']),
        '-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-profile:v','high',
        '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv',
        '-bsf:v','h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1',
        '-c:a','copy',
        '-t',f'{duration:.9f}','-movflags','+faststart',str(target)]
    rows=[];last=None;raw=None;ident=None
    with (out/'render-ffmpeg.log').open('wb') as log:
        proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
        try:
            for frame in range(ep.plan['duration_frames']):
                state=ep.state(frame)
                if state!=last:
                    im,ident=ep.image(state);raw=im.tobytes();last=state
                proc.stdin.write(raw)
                rows.append({'frame':frame,'time_s':frame/FPS,'state_id':ident,**asdict(state)})
                if frame%(FPS*30)==0:print(json.dumps({'rendered_frame':frame,'total_frames':ep.plan['duration_frames']}),flush=True)
        finally:proc.stdin.close()
        if proc.wait():raise RuntimeError('Production encoding failed')
    ep.frame_rows=rows
    (out/'frame-plan.json').write_text(json.dumps({'fps':FPS,'duration_frames':len(rows),'frames':rows},ensure_ascii=False,indent=2)+'\n')
    (out/'native-states.json').write_text(json.dumps({'states':ep.reports,'sources':[receipt(ep.timeline_path),receipt(ep.background_path),ep.art.receipt()]},ensure_ascii=False,indent=2)+'\n')
    result={'video':receipt(target),'timeline':receipt(ep.timeline_path),'master_audio_reference':receipt(path),'audio_copy_source':receipt(AAC_SOURCE),'audio_reencoded':False,'frame_count':len(rows),
        'duration_s':len(rows)/FPS,'native_states':len(ep.reports),'independent_decoded_video_qa':'pending'}
    (out/'render-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def srt_time(t):
    ms=round(t*1000);s,ms=divmod(ms,1000);minute,s=divmod(s,60);h,minute=divmod(minute,60)
    return f'{h:02}:{minute:02}:{s:02},{ms:03}'


def export_delivery(ep,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    srt='\n\n'.join(f'{i}\n{srt_time(e["start_s"])} --> {srt_time(e["end_s"])}\n{e.get("subtitle_text",e["text"])}' for i,e in enumerate(ep.events,1))+'\n'
    (out/'triangular-numbers-en.srt').write_text(srt)
    chapter_rows=[('00:00','Triangular numbers'),(None,'Zero and the first triangles','N000'),
        (None,'Two matching triangles','X004a'),(None,'A new row','X005'),(None,'More rows, same rule','X010'),
        (None,'Three digits','X014'),(None,'Past one thousand','X045'),(None,'Sixty rows and all 61 terms','E060')]
    chapters=[]
    for row in chapter_rows:
        if row[0] is not None:stamp=row[0]
        else:
            sec=int(ep.by[row[2]]['start_s']);stamp=f'{sec//60:02}:{sec%60:02}'
        chapters.append(stamp+' '+row[1])
    (out/'chapters.txt').write_text('\n'.join(chapters)+'\n')
    starts=[]
    for line in chapters:
        stamp=line.split(' ',1)[0];minute,second=map(int,stamp.split(':'));starts.append(minute*60+second)
    gaps=[b-a for a,b in zip(starts,starts[1:])]+[ep.plan['duration_frames']/FPS-starts[-1]]
    if any(g<10 for g in gaps):raise ValueError(f'YouTube chapters shorter than ten seconds: {gaps}')
    description='Count Triangular Numbers | 0 to 1,830 | Num-Num Numbers\n\n'+\
        'Watch rows of dots form triangles. Two matching triangles make an n by (n + 1) rectangle; choosing one equal half gives T(n) = n × (n + 1) ÷ 2.\n\n'+\
        'All 61 terms from T0 = 0 through T60 = 1,830 are counted in natural American English. Every displayed dot represents one.\n\n'+\
        '\n'.join(chapters)+'\n\nNo background music or sound effects.\n'
    (out/'youtube-description.txt').write_text(description)
    # The speech builder owns the adopted cue text and the standard delivery
    # names. Preserve those exact files when bound to its measured timeline.
    copies=[]
    for name in ('english-captions.srt','subtitles.srt','chapters.txt','youtube-description.txt','youtube-title.txt','upload-details.txt'):
        source=ep.timeline_path.parent/name
        target=out/name
        if source.exists() and source.resolve()!=target.resolve():
            shutil.copyfile(source,target);copies.append({'from':receipt(source),'to':receipt(target)})
    if not (out/'english-captions.srt').exists():(out/'english-captions.srt').write_text(srt)
    if not (out/'subtitles.srt').exists():(out/'subtitles.srt').write_text(srt)
    if not (out/'youtube-title.txt').exists():(out/'youtube-title.txt').write_text('Triangular Numbers: Watch the Formula Work | 0 to 1,830 | Num-Num Numbers\n')
    if not (out/'upload-details.txt').exists():
        (out/'upload-details.txt').write_text((out/'youtube-title.txt').read_text()+'\n'+(out/'youtube-description.txt').read_text())
    adopted_chapters=(out/'chapters.txt').read_text().strip().splitlines();starts=[]
    for line in adopted_chapters:
        minute,second=map(int,line.split(' ',1)[0].split(':'));starts.append(minute*60+second)
    adopted_gaps=[b-a for a,b in zip(starts,starts[1:])]+[ep.plan['duration_frames']/FPS-starts[-1]]
    if starts[0]!=0 or any(g<10 for g in adopted_gaps):raise ValueError(f'Invalid adopted chapter lengths: {adopted_gaps}')
    (out/'delivery-manifest.json').write_text(json.dumps({'source_timeline':receipt(ep.timeline_path),
        'files':[receipt(out/name) for name in ('triangular-numbers-en.srt','english-captions.srt','subtitles.srt','chapters.txt','youtube-description.txt','youtube-title.txt','upload-details.txt')],
        'copied_adopted_inputs':copies,'chapter_durations_s':adopted_gaps,
        'cue_count':131,'terms':61,'range':[0,1830],'uploaded':False},ensure_ascii=False,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--timeline',type=Path,required=True)
    p.add_argument('--registry',type=Path);p.add_argument('--background',type=Path)
    p.add_argument('--out-dir',type=Path,default=ROOT/'output/triangular-counting-001-v002')
    p.add_argument('--preview-only',action='store_true');p.add_argument('--motion-preview',action='store_true')
    p.add_argument('--export-only',action='store_true')
    p.add_argument('--check-all-frames',action='store_true')
    args=p.parse_args();ep=Episode(args.timeline,args.registry,args.background)
    ep.write_contract(args.out_dir)
    if args.export_only:export_delivery(ep,args.out_dir);return
    preview(ep,args.out_dir/'preview')
    if args.check_all_frames:print(json.dumps(native_preflight(ep,REVISION/'qa/native'),ensure_ascii=False))
    if args.motion_preview:print(json.dumps(motion_preview(ep,args.out_dir/'preview'),ensure_ascii=False))
    if not args.preview_only:
        print(json.dumps(encode(ep,args.out_dir),ensure_ascii=False))


if __name__=='__main__':main()
