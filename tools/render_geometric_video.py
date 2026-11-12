"""Render the measured geometric sequence, with exact integers and frame QA.

The planning art is immutable. Every revealed result, spoken cue and progress
commit is bound to the accepted audio clock, not to a wall-clock animation.
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
import textwrap

from PIL import Image, ImageDraw, ImageChops
import render_geometric_mockups as m
import render_geometric_formula_study as gf
from component_alignment import raster_centering_report

ROOT=m.ROOT; D=m.D; SIZE=(1920,1080); FPS=30
OUT=ROOT/'output/geometric-sequence-counting-001-v001'
VIDEO_NAME='paspla-studio-geometric-sequence-2-times-3-1080p.mp4'
INK,TEAL,MUTED,CORAL=m.INK,m.TEAL,m.MUTED,m.CORAL
CREAM='#fff8ea'
FFMPEG=str(ROOT/'.venv/bin/ffmpeg')


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def local(p):return str(Path(p).resolve().relative_to(ROOT))
def receipt(p):return {'path':local(p),'sha256':sha(p),'bytes':Path(p).stat().st_size}
def clamp(x):return max(0.,min(1.,x))
def ease(x):x=clamp(x);return x*x*(3-2*x)
def mix(a,b,p):return a+(b-a)*p
def box_at(x,y,w,h):return (x-w/2,y-h/2,x+w/2,y+h/2)
def save(p,data):Path(p).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def rich(parts):
    """Same typography as the plan, retaining the actual constituent glyphs."""
    out=Image.new('RGBA',(2500,310));x=30;details=[]
    for text,size,offset,color in parts:
        im=m.letters(text,size,color);b=m.bounds(im);y=round(105-size*.7+offset)
        out.alpha_composite(im,(x-b[0],y-b[1]))
        details.append(dict(text=text,font_size_px=size,color=color,visible_box_xyxy=[x,y,x+b[2]-b[0],y+b[3]-b[1]]))
        x+=b[2]-b[0]+6
    b=m.bounds(out);crop=(b[0]-20,b[1]-20,b[2]+20,b[3]+20)
    im=out.crop(crop)
    for p in details:p['visible_box_xyxy']=[v-crop[i%2] for i,v in enumerate(p['visible_box_xyxy'])]
    im.info['_parts']=details
    return im


def formula(index='n',exp='n−1',result=None,size=72):
    parts=[('a',size,0,INK),(str(index),round(size*.53),size*.38,TEAL),(' = 2 × 3',size,0,INK),(str(exp),round(size*.53),-size*.32,TEAL)]
    if result is not None:parts.append((' = '+str(result),size,0,INK))
    return rich(parts)


def power(base,exp,suffix='',size=70):
    parts=[(str(base),size,0,INK),(str(exp),round(size*.55),-size*.32,TEAL)]
    if suffix:parts.append((suffix,size,0,INK))
    return rich(parts)


ORIGINAL_COMPOSE=gf.compose
def tracked_compose(parts):
    im,slots=ORIGINAL_COMPOSE(parts);details=[];primitives=[]
    for ident,text,size,offset,color,visible in parts:
        if visible:details.append(dict(component_id=ident,text=text,font_size_px=size,color=color,visible_box_xyxy=list(slots[ident])))
        else:
            b=slots[ident];draw_box=[b[0],b[1]+2,b[2],b[3]-2]
            primitives.append(dict(component_id=ident,kind='rounded_rectangle',draw_box_xyxy=draw_box,
                                   visible_box_xyxy=[draw_box[0],draw_box[1],draw_box[2]+1,draw_box[3]+1],radius=4,outline=TEAL,width=2))
    im.info['_parts']=details
    im.info['_primitives']=primitives
    return im,slots


class Canvas(m.Canvas):
    def __init__(self,ident):
        super().__init__(ident);self.layers={};self.data={}

    def put(self,layer,box,ident,opacity=1,**extra):
        if opacity<=0:return
        alpha_threshold=max(1,round(128*opacity))
        if opacity<1:
            original=layer;layer=layer.copy();layer.putalpha(layer.getchannel('A').point(lambda a:round(a*opacity)))
            layer.info.update(original.info)
        b=m.bounds(layer,alpha_threshold)
        xy=(round((box[0]+box[2]-b[0]-b[2])/2),round((box[1]+box[3]-b[1]-b[3])/2))
        row=raster_centering_report(layer,box,origin_xy=xy,name=f'{self.ident}/{ident}',tolerance_px=.5,alpha_threshold=alpha_threshold)
        row.update(component_id=ident,horizontal='center',vertical='center',opacity=opacity,**extra)
        if not row['passed']:raise ValueError(row)
        if '_parts' in layer.info:
            row['parts']=[dict(p,visible_box_xyxy=[v+xy[i%2] for i,v in enumerate(p['visible_box_xyxy'])]) for p in layer.info['_parts']]
            row['is_compound']=True
        if layer.info.get('_primitives'):
            row['primitives']=[dict(p,draw_box_xyxy=[v+xy[i%2] for i,v in enumerate(p['draw_box_xyxy'])],
                                    visible_box_xyxy=[v+xy[i%2] for i,v in enumerate(p['visible_box_xyxy'])]) for p in layer.info['_primitives']]
        self.records.append(row);self.layers[ident]=(layer,xy)
        self.image.alpha_composite(layer,xy)
        return xy

    def text(self,s,box,size=40,color=INK,ident='text',opacity=1):
        # Product expressions use numeric slots, not implementation captions.
        if ident=='progress-rule' and getattr(self,'general_tick',0)>=216:
            s='2 → 6 → 18 → 54  •  three ×3 steps'
        return self.put(m.letters(s,size,color),box,ident,opacity,text=s,font_size_px=size,color=color)

    def lines(self,lines,box,size=30,color=INK,ident='lines'):
        return self.put(m.group_lines(lines,size,color),box,ident,text='\n'.join(lines),font_size_px=size,color=color,line_gap_px=14)

    def header(self,s,sub=''):
        if s=='GENERAL TERM AT WORK':sub='Term 4 replay  •  the main count stays at four'
        self.text(s,(160,64,1760,140),48,ident='heading')
        if sub:self.text(sub,(150,155,1770,205),27,MUTED,'subheading')

    def progress(self,n):
        self.text(f'{n} / 41 completed',(40,1010,340,1055),22,MUTED,'main-progress-counter')


gf.Canvas=Canvas;gf.compose=tracked_compose;gf.power=power


class Actor:
    """Adapter; previews can use canonical stills until the acting handoff."""
    def __init__(self,allow_still=False):
        self.used={};self.frames={};self.directory=None
        try:
            import geometric_rabbit_animation as art
            self.art=art.Artwork();self.fallback=None
        except ImportError:
            if not allow_still:raise
            self.art=None;self.fallback=m.Rabbit()
        self.motion={'state':'neutral','phase':0.,'gaze':'forward'}

    def draw(self,c,pose='neutral',height=280,foot=(1720,1045)):
        if self.art is None:
            self.fallback.draw(c,'neutral',height,foot);return
        state=self.motion['state'];phase=self.motion['phase'];gaze=self.motion['gaze']
        if gaze!='forward':
            gaze='upper_left' if foot[0]>=1200 else 'upper_right' if foot[0]<=600 else 'up'
        meta=self.art.draw(c.image,state=state,phase=phase,height=height,foot=foot,gaze=gaze,scene_mode=c.ident)
        if not isinstance(meta,dict):raise TypeError('Actor.draw must return per-frame source/anchor metadata')
        meta=dict(meta);meta.setdefault('component_id','rabbit');meta.update(state=state,phase=phase,gaze=gaze,body_height_px=height,foot_px=list(foot))
        c.records.append(meta)


class Episode:
    def __init__(self,timeline,allow_draft=False,allow_still=False):
        self.timeline_path=Path(timeline);self.plan=json.loads(self.timeline_path.read_text())
        if not allow_draft and not self.plan.get('speech_accepted'):raise ValueError('Accepted speech is required for final rendering')
        self.events=self.plan['events'];self.starts=[round(e['start_s']*FPS) for e in self.events]
        self.result=[e for e in self.events if e['kind']=='result'];self.commits=[e['progress_commit_frame'] for e in self.result]
        self.byid={e['id']:e for e in self.events};self.terms=json.loads((D/'math/sequence.json').read_text())['terms']
        self.actor=Actor(allow_still);self.motion=self.make_motion();self.frame_cache={};self.state_reports={}
        self.number_words={};self.word_alignment={}
        align=self.timeline_path.parent/'number-list-alignment.json'
        self.alignment_path=align
        if align.exists():self.word_alignment=json.loads(align.read_text())
        self.allow_draft=allow_draft
        required=['D008','D009','D010','D014','D016','D021','D023']
        if not allow_draft:
            if not all(k in self.word_alignment for k in required):raise ValueError('Measured lexical anchors are required for final rendering')
            for cue in required:
                evidence=self.word_alignment['cues'][cue];event=self.byid[cue]
                assert evidence['source_sha256']==event['source_sha256']
                assert abs(evidence['cue_absolute_start_s']-event['start_s'])<1/24000

    def make_motion(self):
        acts=[]
        def add(cue,state,offset,length,gaze):
            e=self.byid[cue];a=e['start_s']+offset;b=min(a+length,e['end_s']+.25)
            if b-a>=.7:acts.append(dict(start_s=a,end_s=b,state=state,gaze=gaze,cue=cue))
        add('D001','wave',.05,1.8,'forward');add('D002','wonder',.5,1.8,'up')
        for n in [2,3,4,8,12,16,24,28,32,36,40]:
            e=self.byid[f'E{n:03d}'];start=max(e['start_s'],e['end_s']-1.0)
            acts.append(dict(start_s=start,end_s=start+1.5,state='operate',gaze='up',cue=e['id']))
        for cue,state,gaze in [('D004','present','up'),('D005','operate','up'),('D006','wonder','up'),
                               ('D007','wonder','up'),('D009','wonder','up'),('D010','wonder','up'),
                               ('D012','present','right'),('D015','present','right'),('D017','think','up'),
                               ('D020','present','up'),('D022','operate','up'),('D023','wonder','up'),
                               ('D026','wonder','up'),('D029','wave','forward')]:add(cue,state,.1,1.6,gaze)
        return acts

    def actor_motion(self,t,cue,mode):
        for a in self.motion:
            if a['start_s']<=t<a['end_s']:
                return {'state':a['state'],'phase':round((t-a['start_s'])/(a['end_s']-a['start_s'])*32)/32,'gaze':a['gaze']}
        # No whole-body idle loop. A brief blink and purposeful eye movement
        # retain the planted body, calm speech and ordinary numerical timing.
        blink_age=(t-3.4)%6.7
        if 0<=blink_age<.2:return {'state':'blink','phase':round(blink_age/.2*16)/16,'gaze':'up' if mode not in {'intro','outro'} else 'forward'}
        return {'state':'neutral','phase':0.,'gaze':'up' if mode not in {'intro','outro'} else 'forward'}

    def state(self,f):
        t=f/FPS;i=max(0,bisect_right(self.starts,f)-1);e=self.events[i]
        following=self.events[i+1] if i+1<len(self.events) else None
        if following and following['kind']=='result' and f>=following['result_display_frame']:
            i+=1;e=following;following=self.events[i+1] if i+1<len(self.events) else None
        completed=bisect_right(self.commits,f)
        cue=e['id'];n=e.get('term_n') or e.get('current_index',0);kind=e['kind'];tick=0;revealed=None;split_tick=None
        if kind=='dialogue':
            num=int(cue[1:]);mode='intro' if num<=3 else 'transition' if num<=6 else 'general' if num<=11 else 'compare' if num<=18 else 'half' if num<=25 else 'outro'
            p=clamp((t-e['start_s'])/(e['end_s']-e['start_s']))
            tick=round(p*90)
            if mode=='general':
                ranges={'D007':(0,1.5),'D008':(1.5,3.),'D009':(3.,5.35),'D010':(5.35,7.2),'D011':(7.2,7.97)}
                a,b=ranges[cue];tick=round(mix(a,b,p)*30)
                tau=max(0,t-e['start_s'])
                if cue in self.word_alignment:
                    anchors=self.word_alignment[cue]
                    if cue=='D008':
                        answer=max(.3,anchors[-1]-.12)
                        if tau<answer:gtime=mix(1.5,2.4,clamp(tau/answer))
                        elif tau<answer+.15:gtime=mix(2.4,2.6,(tau-answer)/.15)
                        else:gtime=mix(2.6,2.966,clamp((tau-answer-.15)/.25))
                    elif cue=='D009':
                        answer=max(.8,anchors[-1]-.12)
                        gtime=mix(3.,4.65,clamp(tau/answer)) if tau<answer else mix(4.65,5.32,clamp((tau-answer)/max(.2,e['duration_s']-answer)))
                    else:
                        input_time=max(.25,anchors[1]-.12);answer=max(input_time+.2,anchors[-1]-.12)
                        if tau<input_time:gtime=mix(5.35,6.1,clamp(tau/input_time))
                        elif tau<answer:gtime=mix(6.1,6.59,clamp((tau-input_time)/(answer-input_time)))
                        else:gtime=mix(6.6,7.2,clamp((tau-answer)/max(.2,e['duration_s']-answer)))
                    tick=round(gtime*30)
            if cue in {'D014','D016','D021'} and cue in self.word_alignment:
                reveal_frames=[round((e['start_s']+a-.12)*30) for a in self.word_alignment[cue]]
                revealed=max(1,bisect_right(reveal_frames,f))
            if cue in {'D022','D023'}:
                answer=self.word_alignment.get('D023',[0,.96])[-1]-.12 if cue=='D023' else 1.1
                split_tick=round(clamp((t-e['start_s'])/max(.2,answer))*30)
            stage=cue
        else:
            mode='seed' if n==1 else 'exact' if n<=3 else 'loop' if n<=32 else 'wide'
            result=self.byid[f'N{n:03d}'];stage='result' if f>=result['result_display_frame'] else 'forming'
            if kind=='operand':
                duration=e['end_s']-e['start_s'];move_start=e['start_s']+max(.05,duration-1.55)
                tick=round(clamp((t-move_start)/max(.6,min(1.25,duration-.1)))*60)
            if kind=='result' and following and following['kind']=='operand' and t>=e['end_s']+.30:
                mode='feedback';stage='return';n=following['term_n'];tick=round(clamp((t-e['end_s']-.30)/1.3)*60)
        fade_in=round(255*(1-clamp(f/17))) if f<18 else 0
        fade_out=round(255*clamp((f-(self.plan['duration_frames']-36))/35)) if f>=self.plan['duration_frames']-36 else 0
        actor=self.actor_motion(t,cue,mode)
        return dict(mode=mode,cue=cue,n=n,stage=stage,tick=tick,revealed=revealed,split_tick=split_tick,completed=completed,fade=max(fade_in,fade_out),actor=actor)

    def shell(self,state,title,subtitle):
        c=Canvas(state['mode']);c.header(title,subtitle);return c

    def draw_actor(self,c,s,height=260,foot=(1720,1045)):
        self.actor.motion=s['actor'];self.actor.draw(c,height=height,foot=foot)

    def intro(self,s):
        c=self.shell(s,'GEOMETRIC SEQUENCES','The Glass Gallery of Ratios')
        c.put(formula(size=92),(350,264,1570,416),'general-formula')
        c.text('FIRST TERM',(410,468,830,514),29,MUTED,'first-label');c.text('2',(410,538,830,666),112,TEAL,'first-value')
        c.text('COMMON RATIO',(1090,468,1510,514),29,MUTED,'ratio-label');c.text('×3',(1090,538,1510,666),100,CORAL,'ratio-value')
        c.text('One starting value. One repeating multiplier.',(280,699,1640,760),34,MUTED,'intro-caption')
        self.draw_actor(c,s,300,(960,1050));return c

    def seed(self,s):
        c=self.shell(s,'START WITH TWO','Term 1  •  zero multiplications so far')
        c.put(formula('1','0','2',80),(350,254,1570,370),'seed-formula')
        c.put(m.beads(2,TEAL,82,2),(710,421,1210,571),'seed-units',exact_unit_count=2)
        c.text('2',(650,616,1270,766),138,TEAL,'result')
        c.text('The zero exponent keeps the starting value.',(350,805,1570,865),33,MUTED,'zero-exponent')
        self.draw_actor(c,s,280,(1470,1040));return c

    def exact(self,s):
        n=s['n'];v=2*3**(n-1);prev=v//3;p=ease(s['tick']/60);ready=s['stage']=='result'
        c=self.shell(s,'THE SAME MULTIPLIER, EVERY TIME',f'Term {n}  •  three equal groups')
        c.text(str(prev),(330,238,690,330),82,INK,'operand-value');c.text('×3',(760,238,1060,330),82,INK,'operator')
        c.text('=',(1120,238,1260,330),82,INK,'equals');c.text(str(v) if ready else '?',(1350,238,1670,330),82,TEAL,'equation-result')
        for j,x in enumerate((510,960,1410)):
            c.panel((x-175,388,x+175,650),fill=['#fff1e8','#edf5ee','#f4edf7'][j])
            c.text(f'GROUP {j+1}',(x-150,402,x+150,450),27,MUTED,f'group-{j+1}-label')
        for j,x in enumerate((510,960,1410)):
            if ready or p>0 or j==0:
                xx=mix(960,x,p if not ready else 1);yy=mix(495,540,p if not ready else 1)
                c.put(m.beads(prev,m.COLORS[j],30,3),box_at(xx,yy,280,140),f'group-{j+1}-units',exact_unit_count=prev,group=j+1)
        c.text('1 bead = 1',(720,670,1200,714),28,MUTED,'unit-legend')
        c.text(str(v) if ready else '?',(680,740,1240,880),124,TEAL,'result')
        if ready:c.text(f'{v} beads in total',(650,892,1270,944),29,MUTED,'total-description')
        self.draw_actor(c,s,260,(1650,1040));c.data.update(exact_unit_count=v if ready or p>=1 else None,groups_complete=ready or p>=1)
        return c

    def loop(self,s):
        n=s['n'];v=2*3**(n-1);prev=v//3;ready=s['stage']=='result';p=1 if ready else ease(s['tick']/60)
        c=self.shell(s,'THE RESULT BECOMES THE NEXT INPUT',f'Term {n}  •  VALUE GROUPS  •  keep the multiplier fixed at three')
        c.panel((320,260,800,402),fill='#fff7eb');c.text('PREVIOUS VALUE',(350,270,770,312),25,MUTED,'previous-label')
        c.text(f'{prev:,}',(340,327,780,385),36,INK,'operand-value')
        c.draw.ellipse((870,245,1050,425),fill='#edf5ee',outline=TEAL,width=3);c.text('×3',(880,276,1040,394),68,TEAL,'fixed-multiplier')
        c.arrow((810,335),(855,335))
        for j,x in enumerate((510,960,1410)):
            c.panel((x-195,475,x+195,615),fill=['#fff1e8','#edf5ee','#f4edf7'][j])
            if p>=1:c.text(f'GROUP {j+1}',(x-170,485,x+170,525),25,MUTED,f'group-{j+1}-label')
            c.arrow((960,432),(x,463),m.COLORS[j],5)
        label_bounds=m.bounds(m.letters(f'{prev:,}',31,INK));side_gate=min(1,(label_bounds[2]-label_bounds[0]+24)/450)
        for j,x in enumerate((510,960,1410)):
            if j==1 or p>=side_gate:
                xx=mix(960,x,p);yy=mix(445,568,p)
                c.text(f'{prev:,}',box_at(xx,yy,354,54),31,INK,f'group-{j+1}-value')
        c.draw.line([(510,625),(510,649),(1410,649),(1410,625)],fill=TEAL,width=5);c.arrow((960,625),(960,664))
        c.text(f'{v:,}' if ready else '?',(270,680,1650,810),82,TEAL,'result')
        if ready:c.lines(textwrap.wrap(self.terms[n-1]['english'],70),(370,815,1500,942),26,INK,'english-reading')
        c.draw.line([(290,745),(233,745),(233,335),(304,335)],fill=TEAL,width=5);c.arrow((267,335),(304,335))
        c.text('Reuse the whole result. Keep ×3.',(400,955,1500,1007),28,MUTED,'feedback-label')
        self.draw_actor(c,s,220,(1720,1045));c.data.update(groups_complete=p>=1,group_values=[str(prev)]*3,main_result=str(v) if ready else None)
        return c

    def wide(self,s):
        n=s['n'];v=2*3**(n-1);prev=v//3;ready=s['stage']=='result';p=1 if ready else ease(s['tick']/60)
        c=self.shell(s,'GEOMETRIC SEQUENCES',f'Term {n}  •  a = 2  •  r = 3')
        c.text(f'{prev:,}',(180,235,1380,325),55,INK,'operand-value');c.text('×3 =',(1400,235,1760,325),55,INK,'operator')
        c.text(f'{v:,}' if ready else '?',(130,368,1790,504),82,TEAL,'result')
        if ready:
            c.lines(textwrap.wrap(self.terms[n-1]['english'],88),(150,540,1770,724),28,INK,'english-reading')
            c.text(f'Three equal value groups of {prev:,}',(170,735,1750,775),29,MUTED,'symbolic-groups')
            c.text('VALUE DIAGRAM  •  not a picture of every unit',(350,785,1570,823),23,MUTED,'diagram-legend')
        else:
            for j,x in enumerate((460,960,1460)):
                c.panel((x-218,545,x+218,712),fill=['#fff1e8','#edf5ee','#f4edf7'][j])
                if p>=1:c.text(f'GROUP {j+1}',(x-200,555,x+200,600),25,MUTED,f'group-{j+1}-label')
            label_bounds=m.bounds(m.letters(f'{prev:,}',24,INK));side_gate=min(1,(label_bounds[2]-label_bounds[0]+24)/500)
            for j,x in enumerate((460,960,1460)):
                if j==1 or p>=side_gate:
                    c.text(f'{prev:,}',box_at(mix(960,x,p),mix(500,650,p),400,60),24,INK,f'group-{j+1}-value')
            c.text('Three equal value groups',(400,752,1520,810),31,MUTED,'forming-description')
        self.draw_actor(c,s,220,(960,1060));c.data.update(groups_complete=p>=1,group_values=[str(prev)]*3,main_result=str(v) if ready else None)
        return c

    def feedback(self,s):
        n=s['n'];v=2*3**(n-2);p=ease(s['tick']/60);old=n-1
        source=(960,691,138) if old==1 else (960,810,124) if old<=3 else (960,745,82) if old<=32 else (960,436,82)
        target=(510,284,82) if n<=3 else (560,356,36) if n<=32 else (780,280,55)
        c=self.shell(s,'KEEP THE SAME RATIO',f'The completed result becomes the input for term {n}')
        c.panel(box_at(target[0],target[1],500 if n<=32 else 1300,145),fill='#fff7eb')
        if n<=32:c.text('×3',(1120,260,1430,380),80,TEAL,'fixed-multiplier')
        else:c.text('×3',(1450,235,1740,325),55,TEAL,'fixed-multiplier')
        # An isolated whole numeral travels on a cleared field. Its scale is
        # continuous; the prior groups and prior input are already removed.
        x=mix(source[0],target[0],p)-260*math.sin(math.pi*p)
        y=mix(source[1],target[1],p)
        size=round(mix(source[2],target[2],p))
        c.text(f'{v:,}',box_at(x,y,1740,180),size,TEAL if p<1 else INK,'returning-value')
        c.text('The result becomes the next input.',(350,840,1570,910),36,MUTED,'return-caption')
        self.draw_actor(c,s,220,(1720,1045));c.data.update(return_value=str(v),return_phase=s['tick']/60,result_revealed=False)
        return c

    def transition(self,s):
        c=self.shell(s,'FROM BEADS TO GROUP VALUES','The labeled drawing is a model of an amount')
        p=s['tick']/90;cue=s['cue']
        if cue=='D004':
            c.put(m.beads(18,TEAL,37,6),(420,310,1500,670),'eighteen-units',exact_unit_count=18)
            c.text('18 beads',(600,720,1320,820),80,TEAL,'eighteen-label')
        elif cue=='D005':
            c.panel((610,300,1310,720),fill='#edf5ee')
            if p<.65:
                c.put(m.beads(18,TEAL,round(37*(1-.7*ease(p/.65))),6),(660,350,1260,585),'gathered-eighteen-units',exact_unit_count=18)
                c.text('VALUE: 18',(650,617,1270,685),48,TEAL,'group-amount')
            else:
                c.text('VALUE',(650,350,1270,420),34,MUTED,'value-label');c.text('18',(650,460,1270,640),124,TEAL,'group-amount')
            c.text('One group stands for the whole amount.',(320,770,1600,835),34,MUTED,'group-model-caption')
        else:
            for j,x in enumerate((510,960,1410)):
                c.panel((x-175,350,x+175,640),fill=['#fff1e8','#edf5ee','#f4edf7'][j])
                c.text(f'GROUP {j+1}',(x-150,370,x+150,425),27,MUTED,f'group-{j+1}-label');c.text('18',(x-150,465,x+150,600),96,INK,f'group-{j+1}-value')
            c.text('18 × 3 = ?',(420,715,1500,830),80,TEAL,'pending-equation')
        self.draw_actor(c,s,260,(1620,1040));c.data.update(main_progress_held=3,diagram_mode='group_values' if cue!='D004' else 'exact_units')
        return c

    def general(self,s):
        self.actor.motion=s['actor']
        Canvas.general_tick=s['tick']
        c=gf.render_frame(s['tick'],self.actor)
        c.general_tick=s['tick']
        # The source study's last line is replaced after composing, keeping
        # all mathematical layers in native 1080p and the prior study intact.
        if s['cue']=='D011':
            layer,xy=c.layers['progress-rule'];b=m.bounds(layer)
            # Redraw the whole scene with the intended caption override via
            # a class-level per-render option, rather than painting over text.
            c.data['three_steps_explanation']='2 → 6 → 18 → 54; exactly three times-three steps'
        c.data.update(c.notes);return c

    def list_visible(self,cue,p,values):
        # If measured lexical alignments exist, callers replace this planning
        # preview fallback with accepted word starts before final rendering.
        return min(len(values),1+int(p*len(values)))

    def compare(self,s):
        cue=s['cue'];p=s['tick']/90
        if cue=='D018':return self.restore(s,10)
        c=self.shell(s,'CHANGE THE MULTIPLIER','COMPARISON  •  main sequence paused at term 10')
        top=4 if cue in {'D015','D016','D017'} else (s['revealed'] or self.list_visible(cue,p,[2,4,8,16])) if cue=='D014' else 1
        bottom=4 if cue=='D017' else (s['revealed'] or self.list_visible(cue,p,[2,6,18,54])) if cue=='D016' else 1
        for y,r,vals,count in [(370,2,[2,4,8,16],top),(645,3,[2,6,18,54],bottom)]:
            c.text(f'r = {r}',(170,y-50,440,y+35),60,TEAL if r==2 else CORAL,f'ratio-{r}')
            for j,v in enumerate(vals[:count]):
                x=640+j*315;c.text(str(v),(x-115,y-65,x+115,y+65),88,INK,f'comparison-r{r}-n{j+1}')
                if j<count-1:c.arrow((x+127,y),(x+185,y),TEAL if r==2 else CORAL)
            c.text(f'×{r} at every step',(610,y+88,1650,y+144),31,MUTED,f'r{r}-caption')
        self.draw_actor(c,s,250,(1720,1045));c.data.update(comparison_only=True,main_progress_held=10,comparison_visible=[top,bottom]);return c

    def half(self,s):
        cue=s['cue'];p=s['tick']/90
        if cue in {'D024','D025'}:return self.restore(s,20)
        c=self.shell(s,'A GEOMETRIC SEQUENCE CAN SHRINK','ANOTHER EXAMPLE  •  first term 16  •  r = 1/2')
        values=['16','8','4','2','1','1/2']
        count=(s['revealed'] or self.list_visible(cue,p,values)) if cue=='D021' else 6 if cue in {'D022','D023'} else 1
        c.text('   →   '.join(values[:count]),(180,245,1740,365),62,INK,'halving-path')
        if cue in {'D019','D020','D021'}:
            current=16 if count==1 else 8 if count==2 else 4 if count==3 else 2 if count==4 else 1
            # Sixteen equal-area cells keep a fixed unit size through every
            # step; inactive cells retain their outline for the same whole.
            for k in range(16):
                x=640+(k%8)*84;y=465+(k//8)*84
                c.draw.rounded_rectangle((x,y,x+62,y+62),radius=9,fill=TEAL if k<current else '#e3e3d4',outline=INK,width=2)
                if count==6 and k==0:c.draw.rectangle((x+31,y+2,x+60,y+60),fill='#e3e3d4')
            c.text('Each small square is one whole unit.',(370,720,1550,783),31,MUTED,'unit-rule')
            c.data['unit_geometry']=dict(kind='16_fixed_squares',columns=8,rows=2,top_left=[640,465],step_px=84,side_px=62,active_wholes=current if count<6 else 0,active_half=count==6,exact_amount=values[count-1])
        else:
            for x,half in [(710,False),(1210,True)]:
                c.draw.ellipse((x-100,465,x+100,665),fill='#e2e4d4',outline=INK,width=3)
                if half:
                    split=(s.get('split_tick') or 0)/30
                    c.draw.ellipse((x-100,465,x+100,665),fill=TEAL,outline=INK,width=3)
                    a=tuple(int(TEAL.lstrip('#')[i:i+2],16) for i in (0,2,4));b=(226,228,212)
                    color=tuple(round(mix(a[i],b[i],ease(split))) for i in range(3))
                    c.draw.pieslice((x-100,465,x+100,665),90,270,fill=color,outline=INK,width=3)
                else:c.draw.ellipse((x-100,465,x+100,665),fill=TEAL,outline=INK,width=3)
                c.text(('1/2 of a whole' if s['split_tick']==30 else 'Keep one half') if half else '1 whole',(x-220,700,x+220,755),34,INK,f'whole-{half}')
            c.arrow((850,565),(1060,565));c.text('× 1/2',(845,445,1065,500),38,TEAL,'half-operator')
            c.data['unit_geometry']=dict(kind='full_and_half_circles',centers=[[710,565],[1210,565]],radius_px=100,reference_whole_area='pi*100^2',retained_fraction='1/2',half_orientation='right',split_phase=(s.get('split_tick') or 0)/30)
        c.text('The unit stays the same.',(320,828,1400,886),34,MUTED,'halving-caption')
        self.draw_actor(c,s,260,(1570,1040));c.data.update(comparison_only=True,main_progress_held=20,halving_visible=count);return c

    def restore(self,s,n):
        c=self.shell(s,'BACK TO OUR TIMES-THREE SEQUENCE',f'Main sequence held at term {n}')
        c.put(formula(str(n),str(n-1),size=72),(370,275,1550,420),'restored-formula')
        c.text(f'{2*3**(n-1):,}',(160,490,1760,645),104,TEAL,'held-main-value')
        c.text('The next result continues this sequence.',(320,740,1600,810),35,MUTED,'resume-caption')
        self.draw_actor(c,s,260,(1570,1040));c.data.update(main_progress_held=n,main_value=str(2*3**(n-1)));return c

    def outro(self,s):
        c=self.shell(s,'THE SAME RATIO CONNECTS EVERY STEP','41 terms  •  40 multiplications by three')
        c.text('2   →   6   →   18   →   54   →   …',(200,260,1720,360),66,INK,'recap-path')
        c.text('24,315,330,918,113,857,602',(130,425,1790,555),78,TEAL,'last-value')
        c.put(formula('41','40',size=68),(430,635,1490,740),'recap-formula')
        self.draw_actor(c,s,280,(960,1050));return c

    def image(self,s):
        key=json.dumps(s,sort_keys=True,separators=(',',':'))
        if key in self.frame_cache:return self.frame_cache[key],self.state_reports[key]
        c=getattr(self,s['mode'])(s)
        if s['mode']!='general':c.progress(s['completed'])
        # A support-point registration is never treated as center alignment.
        char=next((r for r in c.records if r.get('component_id')=='rabbit'),None)
        if char and 'visible_box_xyxy' in char:
            a=char['visible_box_xyxy'];collisions=[]
            for row in c.records:
                if row is char or 'visible_box_xyxy' not in row:continue
                b=row['visible_box_xyxy']
                if max(a[0],b[0])<min(a[2],b[2]) and max(a[1],b[1])<min(a[3],b[3]):collisions.append(row['component_id'])
            if collisions:raise ValueError(('Actor/teaching overlap',s,collisions))
        if s['fade']:
            wash=Image.new('RGBA',SIZE,CREAM);wash.putalpha(s['fade']);c.image.alpha_composite(wash)
        raw=c.image.convert('RGB').tobytes()
        report=dict(state_key=key,state=s,components=c.records,data=c.data,notes=c.notes,source_alignment_passed=all(r.get('passed',True) for r in c.records))
        self.state_reports[key]=report
        # Numeric speech is mostly held while read. Bound the raster cache so
        # native video frames do not accumulate in gigabytes of RAM.
        if len(self.frame_cache)>24:self.frame_cache.clear()
        self.frame_cache[key]=raw
        return raw,report


def encoder(path,frames):
    return subprocess.Popen([FFMPEG,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','-',
          '-an','-vf','scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p','-c:v','libx264','-preset','fast','-crf','18',
          '-force_key_frames',f'{(frames-1)/30:.9f}','-pix_fmt','yuv420p','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-color_range','tv',
          '-bsf:v','h264_metadata=video_full_range_flag=0:colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1',
          '-movflags','+write_colr+faststart',str(path)],stdin=subprocess.PIPE)


def render(ep,out,audio=None,preview=False,encoded_aac=None):
    out.mkdir(parents=True,exist_ok=False)
    if preview:
        frames=[]
        for cue in ['D001','E002','N003','D005','D008','D009','D010','D014','D021','E025','N025','E041','N041','D029']:
            e=ep.byid[cue];a=max(0,round(e['start_s']*30)-3);b=min(ep.plan['duration_frames'],round(e['end_s']*30)+6)
            frames.extend(range(a,b))
    else:frames=range(ep.plan['duration_frames'])
    silent=out/('motion-preview.mp4' if preview else 'silent-picture.mp4');p=encoder(silent,len(frames))
    frames_path=out/'frame-states.jsonl.gz'
    with gzip.open(frames_path,'wt',encoding='utf8') as stream:
        for index,f in enumerate(frames):
            s=ep.state(f);raw,report=ep.image(s);p.stdin.write(raw)
            stream.write(json.dumps(dict(frame=index,episode_frame=f,time_s=f/30,state_key=report['state_key'],**s),ensure_ascii=False,separators=(',',':'))+'\n')
            if index%900==0:print(json.dumps({'rendered_frames':index,'total_frames':len(frames)}),flush=True)
    p.stdin.close()
    if p.wait()!=0:raise RuntimeError('Video encode failed')
    with gzip.open(out/'distinct-reports.jsonl.gz','wt',encoding='utf8') as stream:
        for row in ep.state_reports.values():stream.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
    final=silent
    if audio or encoded_aac:
        final=out/VIDEO_NAME
        command=[FFMPEG,'-hide_banner','-v','warning','-y','-i',str(silent),'-i',str(encoded_aac or audio),'-map','0:v:0','-map','1:a:0','-c:v','copy']
        if encoded_aac:command+=['-c:a','copy']
        else:command+=['-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t',str(len(frames)/30)]
        command+=['-bsf:v','h264_metadata=video_full_range_flag=0:colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1',
                  '-color_primaries:v','bt709','-color_trc:v','bt709','-colorspace:v','bt709','-color_range:v','tv',
                  '-video_track_timescale','15360','-movflags','+write_colr+faststart',str(final)]
        subprocess.run(command,check=True)
    spec=dict(size=list(SIZE),fps=30,font=receipt(m.FONT),background=receipt(m.BG),colors=dict(ink=INK,teal=TEAL,muted=MUTED,coral=CORAL,cream=CREAM),
              typography='actual visible glyph bounds; multiline gap 14px; compound parts have exact glyph bounds',
              actor='geometric_rabbit_animation.Artwork; per-frame source metadata',actor_module=receipt(ROOT/'tools/geometric_rabbit_animation.py'),
              actor_recipe=ep.actor.art.receipt() if ep.actor.art else None,timeline=receipt(ep.timeline_path),lexical_anchors=receipt(ep.alignment_path),
              renderer=receipt(__file__),planning_helpers=receipt(m.__file__),general_helpers=receipt(gf.__file__))
    save(out/'visual-spec.json',spec)
    save(out/'render-manifest.json',dict(status='rendered_pending_final_qa',preview=preview,video=receipt(final),silent_picture=receipt(silent),
         timeline=receipt(ep.timeline_path),frame_count=len(frames),duration_s=len(frames)/30,distinct_states=len(ep.state_reports),
         source_alignment_passed=all(x['source_alignment_passed'] for x in ep.state_reports.values()),frame_states=receipt(frames_path),
         state_reports=receipt(out/'distinct-reports.jsonl.gz'),encoded_aac=receipt(encoded_aac) if encoded_aac else None,sources=spec))
    return final


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--timeline',type=Path,required=True);p.add_argument('--audio',type=Path)
    p.add_argument('--encoded-aac',type=Path)
    p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--preview',action='store_true');p.add_argument('--allow-draft',action='store_true');p.add_argument('--allow-still',action='store_true')
    a=p.parse_args();ep=Episode(a.timeline,a.allow_draft,a.allow_still);video=render(ep,a.out_dir,a.audio,a.preview,a.encoded_aac)
    print(json.dumps({'video':str(video),'duration_frames':ep.plan['duration_frames'],'distinct_states':len(ep.state_reports)}))


if __name__=='__main__':main()
