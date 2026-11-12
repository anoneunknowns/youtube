"""Lucas production renderer: measured cues, integer additions, visible value flow.

The immutable clean plate and registered actor are separate from native exact
arithmetic. Preview plans are accepted only by preview commands, never render.
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
from PIL import Image, ImageChops, ImageDraw, ImageFont

try:
    from component_alignment import raster_centering_report
except ImportError:
    from tools.component_alignment import raster_centering_report

ROOT=Path(__file__).resolve().parents[1]
DES=ROOT/'design/lucas-counting-v1'
PROD=DES/'production-v001/renderer'
OUT=ROOT/'output/lucas-counting-001-v001/render'
BG=DES/'generation-batches/lucas-preproduction-20261112-01a1ce1d/source/clocktower-clean-plate.png'
FONT=ROOT/'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
SIZE,FPS=(1920,1080),30
INK,MUTED,TEAL,CORAL,GOLD,CREAM,EDGE='#604934','#7e7364','#327e84','#ce795f','#c79949','#fffaf0','#d9ccb5'
SUB=str.maketrans('0123456789','₀₁₂₃₄₅₆₇₈₉')
INPUTS=[(300,248,820,435),(1100,248,1620,435)]
INPUT_VALUE=[(324,325,796,413),(1124,325,1596,413)]
RESULT=(465,603,1455,730)
READING=(385,802,1535,899)
PROGRESS=(55,47,305,114)
VIDEO_NAME='paspla-studio-lucas-numbers-L0-to-L40-1080p.mp4'

def local(p):return str(Path(p).resolve().relative_to(ROOT))
def resolve(p):return Path(p) if Path(p).is_absolute() else ROOT/p
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def receipt(p):return {'path':local(p),'sha256':sha(p),'bytes':Path(p).stat().st_size}
def write(p,d):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def clamp(p):return min(1.,max(0.,p))
def smooth(p):p=clamp(p);return p*p*(3-2*p)
def lerp(a,b,p):return a+(b-a)*p
def label(n):return 'L'+str(n).translate(SUB)
def phase(t,a,b):return clamp((t-a)/max(.001,b-a))
def ffbin(n):p=ROOT/'.venv/bin'/n;return str(p) if p.exists() else shutil.which(n)
@lru_cache(maxsize=128)
def font(n):return ImageFont.truetype(str(FONT),n)
def visible(im,threshold=128):return im.getchannel('A').point(lambda v:255 if v>=threshold else 0).getbbox()
@lru_cache(maxsize=2600)
def glyph(s,n,color=INK):
    b=font(n).getbbox(str(s));im=Image.new('RGBA',(b[2]-b[0]+48,b[3]-b[1]+48));ImageDraw.Draw(im).text((24-b[0],24-b[1]),str(s),font=font(n),fill=color);return im
@lru_cache(maxsize=180)
def multi(lines,n,color=INK):
    pieces=[glyph(s,n,color) for s in lines];bs=[visible(p) for p in pieces];w=max(b[2]-b[0] for b in bs);h=sum(b[3]-b[1] for b in bs)+12*(len(lines)-1)
    im=Image.new('RGBA',(w+48,h+48));y=24
    for p,b in zip(pieces,bs):im.alpha_composite(p,(24+round((w-b[2]+b[0])/2)-b[0],y-b[1]));y+=b[3]-b[1]+12
    return im
def wrap(s,n,width=1120):
    rows=[];part=''
    for w in s.split():
        trial=(part+' '+w).strip()
        if part and font(n).getlength(trial)>width:rows.append(part);part=w
        else:part=trial
    if part:rows.append(part)
    return tuple(rows)

class Canvas:
    def __init__(self,plate,name):
        self.im=plate.copy();self.d=ImageDraw.Draw(self.im);self.name=name;self.records=[];self.foreground={};self.ink_snapshots={};self.data={};self.absent=[]
    def panel(self,b,fill=CREAM,radius=30,outline=EDGE,width=2):self.d.rounded_rectangle(b,radius,fill=fill,outline=outline,width=width)
    def center(self,layer,b,ident,role='label',**semantic):
        bb=visible(layer)
        if bb is None:raise ValueError('Empty '+ident)
        xy=(round((b[0]+b[2]-bb[0]-bb[2])/2),round((b[1]+b[3]-bb[1]-bb[3])/2))
        r=raster_centering_report(layer,b,origin_xy=xy,name=self.name+'/'+ident,tolerance_px=.5)
        r.update(component_id=ident,horizontal='center',vertical='center',role=role,**semantic)
        if not r['passed']:raise ValueError(r)
        self.records.append(r);self.foreground[ident]=(layer,xy,128);self.im.alpha_composite(layer,xy)
        self.ink_snapshots[ident]=self.im.crop((xy[0],xy[1],xy[0]+layer.width,xy[1]+layer.height)).convert('RGB')
    def text(self,s,b,size=36,color=INK,ident='text',role='label',**semantic):self.center(glyph(str(s),size,color),b,ident,role,text=str(s),font_size_px=size,color=color,**semantic)
    def lines(self,rows,b,size=32,color=MUTED,ident='reading',role='label',**semantic):self.center(multi(tuple(rows),size,color),b,ident,role,text='\n'.join(rows),font_size_px=size,color=color,multiline_group=True,**semantic)
    def arrow(self,a,b,color=GOLD,width=5):
        self.d.line([a,b],fill=color,width=width);angle=math.atan2(b[1]-a[1],b[0]-a[0]);r=14;self.d.polygon([b,(b[0]-r*math.cos(angle-.5),b[1]-r*math.sin(angle-.5)),(b[0]-r*math.cos(angle+.5),b[1]-r*math.sin(angle+.5))],fill=color)
    def clearance(self):
        rs=self.records
        for i,a in enumerate(rs):
            if a.get('allow_overlap'):continue
            aa=a['visible_box_xyxy']
            for b in rs[i+1:]:
                if b.get('allow_overlap'):continue
                bb=b['visible_box_xyxy']
                if max(aa[0],bb[0])<min(aa[2],bb[2]) and max(aa[1],bb[1])<min(aa[3],bb[3]):raise ValueError(('glyph overlap',self.name,a['component_id'],b['component_id'],aa,bb))
        circles=self.data.get('unit_shape_circles',[])
        for i,(x,y,r) in enumerate(circles):
            if not (24<=x-r<x+r<=1896 and 24<=y-r<y+r<=1056):raise ValueError(('unit clipped',x,y,r))
            for rec in rs:
                b=rec['visible_box_xyxy']
                if max(x-r,b[0])<min(x+r,b[2]) and max(y-r,b[1])<min(y+r,b[3]):raise ValueError(('unit/glyph contact',self.name,i,rec['component_id'],[x,y,r],b))
            for xx,yy,rr in circles[i+1:]:
                if math.hypot(x-xx,y-yy)+1e-6<r+rr+8:raise ValueError(('unit counters touch',self.name,[x,y,r],[xx,yy,rr]))
        self.data['glyph_clearance_passed']=True
    def preserve_glyph_ink(self):
        """Catch late path, frame, decoration or panel paint over actual ink.

        Parent/route shapes never join the glyph mask. Alpha128 visible glyph
        pixels retain the RGB observed immediately after that glyph was drawn.
        This is separate from centering, which cannot detect an overpaint.
        """
        for ident,(layer,xy,_) in self.foreground.items():
            solid=layer.getchannel('A').point(lambda v:255 if v>=128 else 0)
            expected=self.ink_snapshots[ident];actual=self.im.crop((xy[0],xy[1],xy[0]+layer.width,xy[1]+layer.height)).convert('RGB')
            diff=ImageChops.difference(expected,actual);bands=diff.split();delta=ImageChops.lighter(ImageChops.lighter(bands[0],bands[1]),bands[2]);changed=ImageChops.multiply(delta.point(lambda v:255 if v else 0),solid);box=changed.getbbox()
            if box is not None:raise ValueError(('foreground ink overpaint',self.name,ident,[box[0]+xy[0],box[1]+xy[1],box[2]+xy[0],box[3]+xy[1]]))
        self.data['glyph_ink_preserved_after_all_paths_panels_and_decorations']=True
        self.data['ink_integrity_method']='actual final composition RGB equals immediate post-glyph RGB at original glyph alpha>=128; independent of centering/bounds'

class NeutralPlaceholder:
    def __init__(self):
        self.row=next(c for c in json.load(open(ROOT/'catalogs/character-library-v1.json'))['characters'] if c['id']=='meerkat')['neutral'];self.source=Image.open(ROOT/self.row['path']).convert('RGBA')
    @lru_cache(maxsize=20)
    def scaled(self,height):
        s=height/self.row['reference_height_px'];return self.source.resize((round(self.source.width*s),round(self.source.height*s)),Image.Resampling.LANCZOS),s
    def draw(self,im,time_s,scene,height=280,foot=(250,1030)):
        layer,s=self.scaled(height);a=self.row['anchor_px'];xy=(round(foot[0]-a[0]*s),round(foot[1]-a[1]*s));bb=visible(layer,8);im.alpha_composite(layer,xy)
        return {'pose':'neutral-placeholder','placeholder':True,'source':{'path':self.row['path'],'sha256':self.row['sha256']},'visible_box':[bb[0]+xy[0],bb[1]+xy[1],bb[2]+xy[0],bb[3]+xy[1]],'foot_delta_x_px':xy[0]+a[0]*s-foot[0],'foot_delta_y_px':xy[1]+a[1]*s-foot[1],'height':height,'foot':foot}

def load_plan(path,allow_planned=False):
    raw=json.loads(resolve(path).read_text());events=raw.get('events',raw.get('voice_events',raw.get('cues',[])))
    planned=events and 'start_s' not in events[0]
    if planned and not allow_planned:raise ValueError('Measured speech timeline required')
    if planned:events=[{**e,'start_s':e['plan_start_s'],'end_s':e['plan_end_s']} for e in events]
    if len(events)!=104 or len({e['id'] for e in events})!=104:raise ValueError('All104 cue IDs required')
    by={e['id']:e for e in events};truth=json.load(open(DES/'math/lucas-truth.json'))['rows'];supplied={r.get('n',r.get('index')):r for r in raw.get('counted_states',[])};states=[]
    for n,row in enumerate(truth):
        cue=by[f'N{n:03d}'];formula=by.get(f'E{n:03d}');later=[e for e in events if e.get('n',e.get('index'))==n and e['id'].startswith('X')];last=max([cue['end_s']]+[e['end_s'] for e in later]);transfer=next((e for e in later if e['id'] in ['X002b','X020b','X029b']),None)
        trstart=transfer['start_s']+.35 if transfer else last+.25;trend=trstart+1.4
        st={**row,'voice_start_s':cue['start_s'],'voice_end_s':cue['end_s'],'progress_commit_s':cue['end_s'],'result_start_s':cue['start_s']-.12,'formula_start_s':formula['start_s'] if formula else None,'formula_end_s':formula['end_s'] if formula else None,'transfer_start_s':trstart if 2<=n<40 else None,'transfer_end_s':trend if 2<=n<40 else None,'transfer_event_id':transfer['id'] if transfer else None,'cycle_start_s':formula['start_s'] if formula else cue['start_s']-.12,'cycle_end_s':by[f'E{n+1:03d}']['start_s'] if 1<=n<40 else by['O01']['start_s'] if n==40 else by['N001']['start_s']-.12}
        st.update(supplied.get(n,{}));st['n']=n
        if n>=2 and st['a']+st['b']!=st['value']:raise ValueError('Wrong input sum')
        states.append(st)
    duration=raw.get('duration_s',raw.get('estimated_duration_s',events[-1]['end_s']+1.2));raw.update(events=events,counted_states=states,duration_s=duration,duration_frames=math.ceil(duration*FPS),fps=FPS,preview_plan_only=planned)
    return raw

class Episode:
    def __init__(self,timeline,allow_planned=False,placeholder=False):
        self.timeline_path=resolve(timeline);self.plan=load_plan(self.timeline_path,allow_planned);self.events=self.plan['events'];self.by={e['id']:e for e in self.events};self.rows=self.plan['counted_states'];self.starts=[e['start_s'] for e in self.events];self.ends=[r['progress_commit_s'] for r in self.rows]
        self.background=Image.open(BG).convert('RGBA').resize(SIZE,Image.Resampling.LANCZOS);self.cache=OrderedDict();self.actor_path=ROOT/'tools/lucas_animation.py'
        if not placeholder and self.actor_path.exists():
            spec=importlib.util.spec_from_file_location('lucas_episode_actor',self.actor_path);module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module);self.actor=module.LucasActor(self.plan);self.placeholder=False
        else:self.actor=NeutralPlaceholder();self.placeholder=True
        self.frozen=[receipt(self.timeline_path),receipt(BG),receipt(FONT),receipt(DES/'math/lucas-truth.json'),receipt(Path(__file__))]+([receipt(self.actor_path)] if not self.placeholder else [])
    def event(self,t):return self.events[max(0,bisect_right(self.starts,t)-1)]
    def state(self,t):
        e=self.event(t);ident=e['id'];n=e.get('n',e.get('index'));progress=bisect_right(self.ends,t);p=phase(t,e['start_s'],e['end_s'])
        s={'mode':'count','n':n,'cue_id':ident,'stage':'result','tick':round(p*90),'progress':progress}
        if ident.startswith('I'):s.update(mode='intro' if ident!='I04' else 'seeds',stage=ident)
        elif ident.startswith('O'):s.update(mode='history',stage=ident,n=40)
        elif n is not None and n<2:s.update(mode='seeds',stage=ident)
        elif n is not None:
            row=self.rows[n];a,b=row.get('transfer_start_s'),row.get('transfer_end_s')
            if a is not None and t>=a:
                if t<b:s.update(mode='transfer',stage='handoff',tick=round(smooth(phase(t,a,b))*90))
                else:s.update(mode='count',n=n+1,stage='ready',tick=0)
            elif ident.startswith('X'):
                modes={'X002a':'units','X005a':'ten','X005b':'value-tags','X010a':'carry-ones','X010b':'carry-tens','X010c':'carry-result','X020a':'midpoint','X020b':'midpoint','X029a':'millions','X029b':'millions','X038':'last-inputs','X039':'hundred-million'}
                s.update(mode=modes.get(ident,'count'),stage=ident)
            elif t<row['result_start_s']:
                f=self.by[f'E{n:03d}'];ht=f.get('highlight_timing',{});a0=ht.get('a_start_s',f['start_s']);pl=ht.get('plus_start_s',lerp(f['start_s'],f['end_s'],.3));b0=ht.get('b_start_s',lerp(f['start_s'],f['end_s'],.45));eq=ht.get('equals_start_s',lerp(f['start_s'],f['end_s'],.85))
                stage='older' if t<pl else 'plus' if t<b0 else 'newer' if t<eq else 'equals';aa,bb={'older':(a0,pl),'plus':(pl,b0),'newer':(b0,eq),'equals':(eq,row['result_start_s'])}[stage]
                s.update(stage=stage,tick=round(phase(t,aa,bb)*90),highlight_method=ht.get('method','preview proportional estimate'))
        if s['mode']=='count' and s['stage']=='result':s['tick']=0
        return s
    def header(self,c,s,subtitle=None,rule=True):
        c.panel((365,25,1555,126));c.text('LUCAS NUMBERS',(395,39,1525,84),43,ident='title')
        if subtitle is None:subtitle=f'BUILDING {label(s["n"])}  ·  TERM {s["n"]+1} / 41'
        c.text('NUM-NUM NUMBERS  ·  '+subtitle,(395,99,1525,119),18,MUTED,'subtitle')
        c.panel((40,35,320,125));c.lines(('COMPLETED',f'{s["progress"]} / 41'),PROGRESS,22,MUTED,'completed-progress','progress',completed_terms=s['progress'])
        if rule:
            c.panel((280,141,1640,213),fill='#fff9e9',radius=22);c.text('L₀ = 2     L₁ = 1     L(n) = L(n − 2) + L(n − 1)   (n ≥ 2)',(300,151,1620,205),33,MUTED,'general-rule')
    def input_node(self,c,n,value,k,role,size):
        b=INPUTS[k];color=TEAL if k==0 else CORAL;c.panel(b,radius=64)
        c.text(role,(b[0]+20,b[1]+19,b[0]+155,b[1]+53),21,color,'input-role-'+str(k))
        c.text(label(n),(b[0]+180,b[1]+16,b[2]-180,b[1]+52),25,color,'input-index-'+str(k),'index',n=n)
        if value is not None:c.text(f'{value:,}',INPUT_VALUE[k],size,color,'input-value-'+str(k),'input',value=value,n=n)
    def wheel(self,c):
        c.d.arc((315,225,1605,930),190,350,fill='#cbbd9e',width=3);c.arrow((720,430),(930,480),TEAL);c.arrow((1200,430),(990,480),CORAL);c.arrow((960,538),(960,568),GOLD);c.d.ellipse((912,446,1008,538),fill=CREAM,outline=GOLD,width=3);c.text('+',(928,464,992,515),52,INK,'addition-operator')
    def normal(self,c,s,reading=True):
        row=self.rows[s['n']];n=s['n'];wide=n>=20;self.header(c,s);self.wheel(c);self.input_node(c,n-2,row['a'],0,'OLDER',60 if wide else 86);self.input_node(c,n-1,row['b'],1,'NEWER',60 if wide else 86)
        c.panel((430,578,1490,755),outline=GOLD);c.text('=  '+label(n),(1050,540,1390,576),29,MUTED,'result-index','index',n=n)
        committed=s['stage'] not in ['older','plus','newer','equals','ready'];result=row['a']+row['b']
        if result!=row['value']:raise ValueError('Live integer addition disagrees with truth')
        if committed:
            c.text(f'{result:,}',RESULT,109 if wide else 126,TEAL,'result-value','result',value=result,n=n)
            if reading:c.lines(wrap(row['english'],32),READING,32,MUTED,'english-reading','reading',value=result,n=n)
        else:c.text('?',RESULT,109 if wide else 126,TEAL,'uncommitted-output','unknown')
        c.data.update(arithmetic={'a':row['a'],'b':row['b'],'computed':result,'truth':row['value'],'committed':committed},display_mode='large' if wide else 'small')
        if s['stage'] in ['older','plus','newer','equals']:self.emphasis(c,s)
    def emphasis(self,c,s):
        stage=s['stage'];p=s['tick']/90;overlay=Image.new('RGBA',SIZE);d=ImageDraw.Draw(overlay)
        if stage=='older':d.rounded_rectangle((294,242,826,441),70,outline=TEAL,width=9)
        elif stage=='newer':d.rounded_rectangle((1094,242,1626,441),70,outline=CORAL,width=9)
        elif stage=='plus':d.ellipse((903,437,1017,547),outline=GOLD,width=8)
        else:
            r=next(r['visible_box_xyxy'] for r in c.records if r['component_id']=='result-index');d.rounded_rectangle((r[0]-12,r[1]-9,r[2]+12,r[3]+9),12,outline=GOLD,width=5)
        # An opaque stroke travels along the input connector, never as a counted dot.
        if stage in ['older','plus','newer']:
            a,b,color=((720,430),(930,480),TEAL) if stage in ['older','plus'] else ((1200,430),(990,480),CORAL);z0=max(0,p-.23);z1=min(1,p+.1);d.line([(lerp(a[0],b[0],z0),lerp(a[1],b[1],z0)),(lerp(a[0],b[0],z1),lerp(a[1],b[1],z1))],fill=color,width=10)
        elif stage=='equals':d.line([(960,538),(960,lerp(538,568,p))],fill=GOLD,width=9)
        a=overlay.getchannel('A')
        for r in c.records:
            if a.crop(tuple(map(int,r['visible_box_xyxy']))).getbbox():raise ValueError(('emphasis glyph contact',stage,r['component_id']))
        c.im.alpha_composite(overlay);c.data['emphasis']={'stage':stage,'phase':p,'glyph_contact':False,'connector_tracer_is_not_a_counted_object':True}
    def transfer(self,c,s):
        n=s['n'];row=self.rows[n];p=s['tick']/90;source=86 if n<20 else 60;target=86 if n+1<20 else 60;size=round(lerp(source,target,p))
        for k in [0,1]:
            c.panel(INPUTS[k],radius=64)
        c.panel((430,578,1490,755),outline=GOLD);c.arrow((1495,665),(1535,665),CORAL,3)
        trajectories=[(row['b'],n-1,(1360,369),(560,369),-40),(row['value'],n,(1660,665),(1360,369),0)]
        # All connectors precede ALL number/index foreground layers. In v001,
        # the second connector could overpaint the first short moving value.
        for _,_,a,b,arc in trajectories:
            points=[(lerp(a[0],b[0],z/60),lerp(a[1],b[1],z/60)+arc*math.sin(math.pi*z/60)) for z in range(61)];c.d.line(points,fill=GOLD,width=3)
        moving=[]
        for k,(value,idx,a,b,arc) in enumerate(trajectories):
            x=lerp(a[0],b[0],p);y=lerp(a[1],b[1],p)+arc*math.sin(math.pi*p);color=TEAL if k==0 else CORAL;layer=glyph(f'{value:,}',size,color);bb=visible(layer);c.panel((x-(bb[2]-bb[0])/2-10,y-(bb[3]-bb[1])/2-10,x+(bb[2]-bb[0])/2+10,y+(bb[3]-bb[1])/2+10),radius=12)
            moving.append((k,value,idx,x,y,color,layer))
        # Both moving-card backgrounds are also below every glyph. Fixed next
        # role labels sit above the slots, outside the complete card envelope.
        self.header(c,s,'KEEP THE NEWER VALUE  ·  KEEP THE RESULT')
        for k in [0,1]:
            b=INPUTS[k];c.text('NEXT OLDER' if k==0 else 'NEXT NEWER',(b[0]+16,217,b[0]+174,241),17,TEAL if k==0 else CORAL,'next-role-'+str(k))
        c.text(f'{row["value"]:,}',RESULT,109 if n>=20 else 126,TEAL,'held-result','result',value=row['value'],n=n);c.text('COPY',(1560,719,1760,748),20,CORAL,'copy-dock')
        for k,value,idx,x,y,color,layer in moving:
            c.center(layer,(x-250,y-65,x+250,y+65),'transferred-value-'+str(k),'moving-copy',text=f'{value:,}',value=value,n=idx,font_size_px=size,color=color,phase=p,planned_center_xy=[x,y],source_index=idx,destination_input=k)
            c.text(label(idx),(x-130,y-101,x+130,y-73),25,color,'transferred-index-'+str(k),'index',n=idx,phase=p)
        c.text(f'{row["value"]:,} stays visible until the next equation.',(410,795,1510,843),29,MUTED,'held-result-note')
        c.text(f'The earlier {row["a"]:,} retires to history.',(430,900,1490,940),27,MUTED,'retired-value-note')
        c.data.update(transfer={'source_n':n,'retired_value':row['a'],'moving_values':[row['b'],row['value']],'moving_indices':[n-1,n],'destination_n':n+1,'phase':p,'font_px':size,'from_font_px':source,'to_font_px':target,'copy_dock':True,'held_result':row['value'],'integer_values_unchanged':True,'next_pair_sum':row['b']+row['value']})
    def intro(self,c,s):
        self.header(c,s,'THE CLOCK TOWER OF TWO MEMORIES',rule=False)
        c.text('Two memories. One adding rule.',(300,169,1620,231),46,ident='intro-hook')
        c.d.ellipse((505,265,1415,705),fill='#f7efd8',outline=EDGE,width=4)
        for k,x in enumerate([590,1070]):
            c.panel((x,305,x+260,459));c.text('OLDER' if k==0 else 'NEWER',(x+20,330,x+240,370),25,TEAL if k==0 else CORAL,'intro-input-'+str(k))
        c.arrow((825,475),(935,545),TEAL);c.arrow((1095,475),(985,545),CORAL);c.text('+',(905,500,1015,581),70,ident='intro-plus')
        c.text('L(n) = L(n − 2) + L(n − 1)',(575,610,1345,660),36,MUTED,'intro-rule')
        if s['cue_id']=='I02':
            k=0 if s['tick']<45 else 1;x=[590,1070][k];c.d.rounded_rectangle((x-5,300,x+265,464),30,outline=TEAL if k==0 else CORAL,width=7)
        if s['cue_id']=='I03':
            c.d.line([(650,687),(1270,687)],fill=GOLD,width=6)
        c.data['initial_values_not_yet_displayed']=True
    def seeds(self,c,s,t):
        self.header(c,s,'STARTING VALUES',False);c.text('Start with two. Then one.',(320,177,1600,246),54,ident='seed-title')
        shown=[]
        for x,n,v,color in [(395,0,2,TEAL),(1125,1,1,CORAL)]:
            c.panel((x,315,x+400,625),radius=70);c.text(label(n),(x+40,342,x+360,400),40,color,'seed-index-'+str(n),'index',n=n)
            if t>=self.rows[n]['result_start_s']:
                c.text(str(v),(x+40,431,x+360,586),152,color,'seed-value-'+str(n),'seed',n=n,value=v);shown.append(v)
            else:c.absent.append({'component_id':'seed-value-'+str(n),'reason':'not yet committed'})
        if len(shown)==2:c.arrow((845,470),(1075,470),GOLD,7)
        if s['cue_id']=='X000':
            c.text('position label',(390,680,800,723),30,MUTED,'zero-index-note');c.d.line([(580,410),(450,410),(450,650),(610,650)],fill=GOLD,width=3)
        if s['cue_id'] in ['X001a','X001b']:
            c.text('The first step gets smaller.',(410,696,1510,753),43,MUTED,'initial-decrease');c.text('These two values are given, before any addition.',(370,792,1550,836),31,MUTED,'given-seeds')
        c.data.update(seed_values_visible=shown,seed_values_given=True,initial_additions=0)
    def units(self,c,s):
        self.normal(c,{**s,'stage':'result'},reading=False);p=min(1,s['tick']/60);starts=[(510,488),(590,488),(1360,488)];ends=[(870,845),(960,845),(1050,845)]
        c.panel((460,780,1460,914))
        centers=[]
        for i,(a,b) in enumerate(zip(starts,ends)):
            # Route around the result panel, not across its frame or numeral.
            route=[a,[(330,520),(390,520),(1550,520)][i],[(330,810),(390,870),(1550,810)][i],b]
            seg=0 if p<.2 else 1 if p<.65 else 2;aa,bb=route[seg:seg+2];q=smooth(phase(p,[0,.2,.65][seg],[.2,.65,1][seg]));x=lerp(aa[0],bb[0],q);y=lerp(aa[1],bb[1],q)
            c.d.ellipse((x-26,y-26,x+26,y+26),fill=TEAL if i<2 else CREAM,outline=INK if i<2 else CORAL,width=4);centers.append([x,y])
            panel=(430,578,1490,755)
            if max(x-26,panel[0])<min(x+26,panel[2]) and max(y-26,panel[1])<min(y+26,panel[3]):raise ValueError(('Unit intersects held result panel',p,i,x,y))
        for i,a in enumerate(centers):
            for b in centers[i+1:]:
                if math.hypot(a[0]-b[0],a[1]-b[1])<60:raise ValueError(('Three unit counters touch',p,a,b))
        c.text('REPLAY  ·  2 filled + 1 outlined = 3 counters',(480,929,1440,974),30,MUTED,'unit-caption')
        c.data.update(exact_units={'filled':2,'outlined':1,'total':3,'centers':centers,'unit_radius':26,'minimum_required_center_distance_px':60,'routing':'outside held result panel; two left lanes and one right lane','no_particles':True},unit_shape_circles=[[*p,26] for p in centers],replay=True)
    def ten(self,c,s):
        self.header(c,s,'REPLAY  ·  ONE GROUP OF TEN',False);c.text('4 + 7 = 11',(400,164,1520,237),65,TEAL,'ten-equation')
        p=s['tick']/90;arrange=smooth(p/.5);drop=smooth((p-.48)/.4)
        c.panel((400,300,1520,620));c.panel((600,650,920,915));c.panel((1000,650,1320,915));c.text('4 filled + 7 outlined',(560,313,1360,350),24,MUTED,'eleven-unit-partition');c.text('TENS',(620,924,900,950),22,MUTED,'tens-label');c.text('ONES',(1020,924,1300,950),22,MUTED,'ones-label')
        centers=[]
        for i in range(11):
            # Affine movement preserves row/column order and separation. A
            # regrouping must not make two actual counters disappear in overlap.
            st=(560+(i%5)*72,390+(i//5)*80) if i<10 else (1160,470)
            target=(660+(i%5)*48,440+(i//5)*60) if i<10 else (1160,470)
            x=lerp(st[0],target[0],arrange);y=lerp(st[1],target[1],arrange)+drop*285;c.d.ellipse((x-17,y-17,x+17,y+17),fill=TEAL if i<4 else CREAM,outline=TEAL if i<4 else CORAL,width=3);centers.append([x,y])
        if p>.5:c.d.rounded_rectangle((625,415+drop*285,890,525+drop*285),18,outline=GOLD,width=4)
        if p>.88:
            c.text('1',(670,824,850,900),68,TEAL,'tens-digit','place-digit',value=1,place='tens');c.text('1',(1070,824,1250,900),68,TEAL,'ones-digit','place-digit',value=1,place='ones')
        c.text('10 ones make 1 ten.  1 one remains.',(420,952,1500,996),29,MUTED,'ten-meaning')
        for i,a in enumerate(centers):
            for b in centers[i+1:]:
                if math.hypot(a[0]-b[0],a[1]-b[1])<36:raise ValueError(('Eleven unit counters overlap',p,a,b))
        c.data.update(replay=True,exact_units={'total':11,'filled':4,'outlined':7,'grouped_ten_units':10 if p>.5 else 0,'ungrouped_units':1 if p>.5 else 11,'centers':centers,'minimum_counter_center_separation_px':48,'individual_counter_radius_px':17},unit_shape_circles=[[*p,17] for p in centers],place_result_visible=p>.88)
    def carry(self,c,s):
        self.header(c,s,'REPLAY  ·  FOLLOW THE CARRY',False);c.text('47 + 76 = 123',(420,166,1500,239),65,TEAL,'replay-equation')
        c.panel((280,280,1120,850));c.panel((1170,318,1675,785));xs=[520,720,920];p=s['tick']/90;mode=s['mode']
        for j,name in enumerate(['hundreds','tens','ones']):c.text(name,(xs[j]-90,301,xs[j]+90,340),22,MUTED,'place-'+name)
        for ri,(number,y) in enumerate([('47',435),('76',550)]):
            for ci,ch in enumerate(number.rjust(3)):
                if ch!=' ':c.text(ch,(xs[ci]-73,y,xs[ci]+73,y+84),79,INK,f'carry-addend-{ri}-{ci}','place-digit',value=int(ch),row=ri,place=2-ci)
        c.text('+',(345,552,425,629),75,INK,'vertical-plus');c.d.line((435,681,1010,681),fill=INK,width=4)
        show_ones=mode!='carry-ones' or p>.93;show_tens=mode=='carry-result' or mode=='carry-tens' and p>.93;show_hundreds=mode=='carry-result'
        for ci,show in enumerate([show_hundreds,show_tens,show_ones]):
            if show:c.text(str([1,2,3][ci]),(xs[ci]-73,715,xs[ci]+73,799),79,TEAL,'carry-result-'+str(ci),'place-digit',value=[1,2,3][ci],place=2-ci)
        moving=None;unit_count=0;circles=[]
        if mode in ['carry-ones','carry-tens']:
            unit_count=13 if mode=='carry-ones' else 12;color=CORAL if mode=='carry-ones' else GOLD
            q=smooth((p-.62)/.3);end=(720,386) if mode=='carry-ones' else (520,386);gx=lerp(1384,end[0],q);gy=lerp(467,end[1],q)-35*math.sin(math.pi*q)
            c.text('13 ONES' if mode=='carry-ones' else '12 TENS',(1200,340,1645,380),30,color,'carry-group-label')
            for k in range(unit_count):
                x=1230+(k%5)*77;y=435+(k//5)*64;r=15
                if k<10 and q>0:
                    if q>.75:continue
                    x=gx+(x-1384)*(1-q);y=gy+(y-467)*(1-q);r=15*(1-q)
                c.d.ellipse((x-r,y-r,x+r,y+r),fill=color if k<(7 if mode=='carry-ones' else 4) else CREAM,outline=color,width=2 if r<10 else 3)
                circles.append([x,y,r])
            if q==0:c.d.rounded_rectangle((1200,401,1570,545),18,outline=GOLD,width=3)
            c.lines(('10 ones = 1 ten','3 ones remain') if mode=='carry-ones' else ('4 + 7 + 1 = 12 tens','10 tens = 1 hundred','2 tens remain'),(1200,636,1645,761),25 if mode=='carry-tens' else 27,MUTED,'carry-unit-meaning')
            if q>.75:
                x,y=gx,gy;c.panel((x-35,y-28,x+35,y+28),radius=12,outline=color,width=3);c.text('1',(x-27,y-22,x+27,y+22),36,color,'moving-carry','carry',value=1,source_units=10,place='tens' if mode=='carry-ones' else 'hundreds',phase=q);moving={'value':1,'place':'tens' if mode=='carry-ones' else 'hundreds','phase':q,'center':[x,y]}
            c.data['carry_quantity_conservation']={'source_unit_value':1 if mode=='carry-ones' else 10,'source_total':unit_count,'moving_group_units':10,'ungrouped_units':unit_count-10,'moving_group_encoded_as_one_higher_place':q>.75,'no_double_counted_source_group':True,'phase':q,'minimum_counter_gap_px':8,'ten_carry_consumed_into_twelve_tens':mode=='carry-tens'}
        else:
            c.text('1',(470,365,570,407),36,CORAL,'final-carry-hundred','carry',value=1,place='hundreds');c.lines(('1 hundred','2 tens','3 ones'),(1200,405,1645,691),40,MUTED,'carry-final-meaning')
        c.text('REPLAY: the term counter does not advance.',(430,885,1490,926),28,MUTED,'replay-no-progress')
        c.data.update(replay=True,unit_shape_circles=circles,carry={'mode':mode,'phase':p,'unit_count':unit_count,'moving':moving,'ones_visible':show_ones,'tens_visible':show_tens,'hundreds_visible':show_hundreds,'correct_sum':123,'tens_carry_consumed':mode!='carry-ones'})
    def explanation(self,c,s):
        mode=s['mode'];self.normal(c,{**s,'stage':'result'},reading=False)
        if mode=='value-tags':
            c.text('VALUE TAGS',(490,800,1430,851),40,GOLD,'value-tag-heading');c.text('One window shows a whole number value.',(440,889,1480,934),30,MUTED,'value-tag-meaning')
        elif mode=='millions':
            parts=f'{self.rows[s["n"]]["value"]:,}'.split(',')
            if len(parts)!=3:raise ValueError('Million explanation requires three digit groups')
            for i,(word,value) in enumerate(zip(['millions','thousands','ones'],parts)):
                x=510+i*300;c.panel((x,790,x+280,925),radius=18,outline=GOLD if s['tick']//30==i else EDGE);c.text(word,(x+10,801,x+270,836),23,MUTED,'group-label-'+str(i));c.text(value,(x+12,853,x+268,908),43,TEAL,'three-digit-group-'+str(i),'decimal-group',value=int(value),group_index=i)
            c.data['decimal_grouping']={'parts':parts,'is_place_value_aid_not_new_terms':True,'threshold_not_counted':1000000}
        elif mode=='hundred-million':c.lines(('First Lucas value above 100,000,000.','One more addition.'),(430,802,1490,905),31,MUTED,'first-hundred-million')
        elif mode=='last-inputs':
            # This narration is before the next addition: show exactly its two
            # inputs, while withholding L39. Never pre-count a threshold/result.
            c.absent.append({'component_id':'next-result','reason':'next addition has not started'})
            c.text('Keep these two for the next addition.',(430,810,1490,865),32,MUTED,'last-pair-note')
        else:c.text('The same adding rule. Longer number values.',(430,810,1490,865),32,MUTED,'midpoint-note')
        c.data['replay']=mode not in ['last-inputs','hundred-million']
    def ending(self,c,s):
        compact=s['stage'] in ['O03','O04'];self.header(c,s,'ALL 41 TERMS  ·  39 ADDITIONS',False)
        c.panel((158,144 if compact else 160,1762,621 if compact else 853))
        for i,row in enumerate(self.rows):
            col=i%7;r=i//7;x=178+224*col;y=(157+r*74) if compact else (177+r*110);h=66 if compact else 99;c.panel((x,y,x+216,y+h),fill='#f9f2e4',radius=13)
            c.text(label(i),(x+12,y+5,x+204,y+(23 if compact else 31)),14 if compact else 18,MUTED,f'history-index-{i:02}','index',n=i)
            c.text(row['display'],(x+10,y+(30 if compact else 44),x+206,y+(59 if compact else 85)),25 if compact else 26,TEAL if i in [0,1,39,40] else INK,f'history-value-{i:02}','history-value',n=i,value=row['value'])
        if s['stage']=='O03':
            c.panel((415,665,1535,928));c.text('SEPARATE EXAMPLE  ·  SAME ADDING RULE',(445,683,1505,727),28,MUTED,'comparison-title')
            c.text('LUCAS',(450,760,760,805),30,TEAL,'lucas-comparison-name');c.text('2 → 1 → 3 → 4',(850,760,1480,805),37,TEAL,'lucas-comparison-values','separate-comparison',values=[2,1,3,4])
            c.text('FIBONACCI',(450,843,760,888),30,CORAL,'fibonacci-comparison-name');c.text('0 → 1 → 1 → 2',(850,843,1480,888),37,CORAL,'fibonacci-comparison-values','separate-example',values=[0,1,1,2])
            c.data['comparison']={'lucas':[2,1,3,4],'fibonacci':[0,1,1,2],'main_progress_unchanged':41,'zero_is_separate_example_only':True}
        else:c.text('L(n) = L(n − 2) + L(n − 1)   (n ≥ 2)',(420,640 if compact else 872,1500,690 if compact else 916),31,MUTED,'closing-rule')
        c.data.update(history_values=[r['value'] for r in self.rows],history_indices=list(range(41)),unused_last_cell_not_drawn=True,history_mode='compact' if compact else 'full')
    def actor_geometry(self,s):
        mode=s['mode'];n=s.get('n')
        if mode=='intro':return 340,(960,1045)
        if mode=='history':
            if s['stage']=='O03':return 210,(250,1040)
            if s['stage']=='O04':return 340,(960,1045)
            return 125,(960,1050)
        if mode.startswith('carry-'):return 215,(1720,1040)
        if mode=='ten':return 235,(1740,1040)
        if mode=='units':return 240,(190,1030)
        if mode=='transfer':return (260,(1700,1030)) if n is not None and n>=20 else (280,(250,1030))
        if mode=='seeds':return 280,(250,1040)
        return (260,(1700,1030)) if n is not None and n>=20 else (280,(250,1030))
    def math_canvas(self,s):
        key=json.dumps(s,sort_keys=True)
        if key in self.cache:
            c=self.cache.pop(key);self.cache[key]=c;return c
        c=Canvas(self.background,key);mode=s['mode']
        if mode=='intro':self.intro(c,s)
        elif mode=='seeds':self.seeds(c,s,s.get('time_s',self.by[s['cue_id']]['start_s']))
        elif mode=='transfer':self.transfer(c,s)
        elif mode=='units':self.units(c,s)
        elif mode=='ten':self.ten(c,s)
        elif mode.startswith('carry-'):self.carry(c,s)
        elif mode=='history':self.ending(c,s)
        elif mode=='count':self.normal(c,s)
        else:self.explanation(c,s)
        c.clearance();c.preserve_glyph_ink();self.cache[key]=c
        if len(self.cache)>48:self.cache.popitem(last=False)
        return c
    def image(self,t,include_masks=False):
        s=self.state(t)
        if s['mode']=='seeds':s['time_s']=round(t,6)
        c=self.math_canvas(s);im=c.im.copy();height,foot=self.actor_geometry(s);actor=self.actor.draw(im,t,s,height=height,foot=foot);ab=actor.get('visible_box_xyxy',actor.get('visible_box'))
        if ab:
            for r in c.records:
                box=r['visible_box_xyxy']
                if max(ab[0],box[0])<min(ab[2],box[2]) and max(ab[1],box[1])<min(ab[3],box[3]):raise ValueError(('actor obscures glyph',t,s,r['component_id'],ab,box))
            for x,y,r in c.data.get('unit_shape_circles',[]):
                if max(ab[0],x-r)<min(ab[2],x+r) and max(ab[1],y-r)<min(ab[3],y+r):raise ValueError(('actor/unit contact',t,s,ab,[x,y,r]))
        fade=min(1,t/.4,(self.plan['duration_s']-t)/.8)
        if fade<1:im=Image.blend(Image.new('RGBA',SIZE,CREAM),im,max(0,fade))
        report={'time_s':t,'state':s,'components':c.records,'scene_data':c.data,'actor':actor,'native_layout_tolerance_px':.5,'whole_frame_opacity':max(0,min(1,fade)),'all_components_passed':all(r['passed'] for r in c.records),'intentional_absences':c.absent}
        return im.convert('RGB'),report,c.foreground if include_masks else None

def representative_times(ep):
    times={0,.2,.4,ep.plan['duration_s']-.8,ep.plan['duration_s']-1/FPS}
    for row in ep.rows:
        for k in ['formula_start_s','result_start_s','voice_start_s','voice_end_s','progress_commit_s','transfer_start_s','transfer_end_s']:
            z=row.get(k)
            if z is not None:
                for d in [-1/FPS,0,1/FPS]:times.add(max(0,min(ep.plan['duration_s']-1/FPS,z+d)))
        if row.get('transfer_start_s') is not None:times.add((row['transfer_start_s']+row['transfer_end_s'])/2)
    for e in ep.events:
        if e['id'].startswith(('X','I','O')):
            for p in [.02,.35,.7,.98]:times.add(lerp(e['start_s'],e['end_s'],p))
        if e['id'].startswith('E'):
            h=e.get('highlight_timing',{})
            for k in ['a_start_s','plus_start_s','b_start_s','equals_start_s']:
                if k in h:times.add(h[k]+1/FPS)
    return sorted(times)

def save_frames(ep,out,times=None):
    out.mkdir(parents=True,exist_ok=False);times=times or representative_times(ep);records=[]
    maskdir=out/'masks';maskdir.mkdir()
    for i,t in enumerate(times):
        im,report,fg=ep.image(t,True);name=f'{i:04}-{t:.6f}-{report["state"]["cue_id"]}.png';im.save(out/name);report['image']=name
        # Compact native foreground crops retain uncut alpha and global origins.
        if i%20==0 or report['state']['cue_id'] in ['N040','X010a','X010b','X010c']:
            masks=[]
            for ident,(layer,xy,threshold) in fg.items():
                p=maskdir/f'{i:04}-{ident}.png';layer.save(p);masks.append({'component_id':ident,'path':p.name,'origin_xy':xy,'threshold':threshold})
            report['masks']=masks
        records.append(report)
    with gzip.open(out/'frame-reports.jsonl.gz','wt') as f:
        for r in records:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    write(out/'manifest.json',{'scope':'native production renderer representative frames, not completed MP4 QA','placeholder_actor':ep.placeholder,'preview_plan_only':ep.plan['preview_plan_only'],'frame_count':len(records),'all_passed':all(r['all_components_passed'] for r in records),'frames':[{'path':r['image'],'time_s':r['time_s'],'state':r['state']} for r in records],'frozen_sources':ep.frozen})
    return records

def encode(ep,out,ranges=None,silent=False):
    out.mkdir(parents=True,exist_ok=False);full=ranges is None;ranges=ranges or [(0,ep.plan['duration_s'])];indices=[]
    for a,b in ranges:indices.extend(range(max(0,round(a*FPS)),min(ep.plan['duration_frames'],math.ceil(b*FPS))))
    path=out/VIDEO_NAME if full else out/'lucas-motion-preview.mp4';cmd=[ffbin('ffmpeg'),'-y','-v','error','-f','rawvideo','-pixel_format','rgb24','-video_size','1920x1080','-framerate',str(FPS),'-i','-']
    if not silent:
        if not full:raise ValueError('Audio compilation must be separately measured; preview is silent')
        master=ep.plan.get('master_path',ep.plan.get('audio_path','output/lucas-counting-001-v001/audio-build/master.wav'));cmd+=['-i',str(resolve(master))]
    cmd+=['-map','0:v:0','-c:v','libx264','-crf','18','-preset','medium','-pix_fmt','yuv420p','-r',str(FPS),'-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv','-bsf:v','h264_metadata=video_full_range_flag=0:colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1']
    if not silent:cmd+=['-map','1:a:0','-c:a','aac','-b:a','192k','-ar','48000','-ac','2']
    else:cmd+=['-an']
    cmd+=['-movflags','+faststart','-t',f'{len(indices)/FPS:.9f}',str(path)];proc=subprocess.Popen(cmd,stdin=subprocess.PIPE);unique={}
    with gzip.open(out/'frame-state.jsonl.gz','wt') as f:
        for output_frame,index in enumerate(indices):
            t=index/FPS;im,r,_=ep.image(t);proc.stdin.write(im.tobytes());state_key=json.dumps(r['state'],sort_keys=True);key=hashlib.sha256(state_key.encode()).hexdigest()[:18];unique.setdefault(key,{'state':r['state'],'components':r['components'],'scene_data':r['scene_data']})
            f.write(json.dumps({'frame':output_frame,'source_frame':index,'time_s':t,'state_key':key,'state':r['state'],'actor':r['actor'],'opacity':r['whole_frame_opacity']},ensure_ascii=False)+'\n')
            if output_frame%900==0:print(f'{output_frame}/{len(indices)} frames',flush=True)
    proc.stdin.close()
    if proc.wait():raise RuntimeError('Encoding failed')
    with gzip.open(out/'native-state-components.json.gz','wt') as f:json.dump(unique,f,ensure_ascii=False)
    write(out/'render-manifest.json',{'video':receipt(path),'fps':FPS,'frames':len(indices),'duration_s':len(indices)/FPS,'source_ranges_s':ranges,'full_episode':full,'silent':silent,'preview_plan_only':ep.plan['preview_plan_only'],'placeholder_actor':ep.placeholder,'frozen_sources':ep.frozen,'actor_receipt':ep.actor.receipt() if hasattr(ep.actor,'receipt') else {'placeholder':True},'command':cmd,'header_semantics':'TERM n+1 /41 is the presented term ordinal; COMPLETED updates only at N cue ends.'})
    return path

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['frames','preview','render']);p.add_argument('--timeline',type=Path,default=ROOT/'output/lucas-counting-001-v001/audio-build/timeline.json');p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--allow-planned',action='store_true');p.add_argument('--neutral-placeholder',action='store_true');p.add_argument('--times',help='comma-separated frame times');p.add_argument('--ranges',help='preview-only comma-separated start:end ranges');args=p.parse_args();ep=Episode(args.timeline,args.allow_planned,args.neutral_placeholder)
    if args.command=='render':
        if ep.plan['preview_plan_only'] or ep.placeholder:raise ValueError('Final rendering requires measured audio timeline and registered production actor')
        if not ep.plan.get('production_audio_accepted'):raise ValueError('Production audio must be accepted before full render')
        print(encode(ep,args.out_dir,silent=False))
    elif args.command=='frames':save_frames(ep,args.out_dir,[float(v) for v in args.times.split(',')] if args.times else None)
    else:
        by=ep.by;ranges=[]
        if args.ranges:ranges=[tuple(map(float,r.split(':'))) for r in args.ranges.split(',')]
        else:
            for first,last in [('E002','X002b'),('E005','X005b'),('X010a','X010c'),('E020','X020b'),('E039','N040'),('O03','O04')]:ranges.append((by[first]['start_s'],min(by[last]['end_s']+.25,ep.plan['duration_s'])))
        print(encode(ep,args.out_dir,ranges=ranges,silent=True))

if __name__=='__main__':main()
