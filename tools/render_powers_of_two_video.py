"""Render the measured Powers of Two episode and retain per-frame QA inputs.

All 64 operations have moving duplicate groups. No interpolated integer, whole
actor dissolve, per-pose fitting or free-running audio clock is used.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import asdict, dataclass
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import textwrap

from PIL import Image, ImageChops, ImageDraw, ImageOps

try:
    import render_powers_of_two_mockups as m
    from component_alignment import raster_centering_report
except ModuleNotFoundError:
    from tools import render_powers_of_two_mockups as m
    from tools.component_alignment import raster_centering_report

ROOT=m.ROOT
FPS=30
SIZE=(1920,1080)
DEFAULT_OUT=ROOT/'output/powers-of-two-counting-001-v001'
VIDEO_NAME='paspla-studio-powers-of-two-1-to-18446744073709551616-1080p.mp4'
INK,MUTED,TEAL,CREAM=m.INK,m.MUTED,m.TEAL,m.CREAM
FIELDS={
    'power':[720,180,1200,300],
    'pending':[350,122,1570,166],
    'operation':[300,330,1620,414],
    'input-value':[300,340,1620,424],
    'original-copy-value':[300,330,1620,394],
    'second-copy-value':[300,438,1620,502],
    'original-copy-label':[300,292,1620,324],
    'second-copy-label':[300,506,1620,540],
    'gate':[850,534,1070,604],
    'equals':[900,610,1020,648],
    'answer':[240,650,1680,764],
    'english':[260,778,1660,886],
    'old-paper-units':[350,440,830,620],
    'new-paper-units':[1090,440,1570,620],
    'progress':[300,1008,820,1044],
}


def local(path):
    return str(Path(path).resolve().relative_to(ROOT))


def resolve(path):
    p=Path(path)
    return p if p.is_absolute() else ROOT/p


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def receipt(path):
    return dict(path=local(path),sha256=sha(path))


def clamp(x):
    return min(1,max(0,x))


def ease(x):
    x=clamp(x)
    return x*x*(3-2*x)


def lerp(a,b,p):
    return a+(b-a)*p


def shifted(box,dx=0,dy=0):
    return [box[0]+dx,box[1]+dy,box[2]+dx,box[3]+dy]


class Canvas:
    def __init__(self,plate,name):
        self.image=plate.copy()
        self.draw=ImageDraw.Draw(self.image)
        self.name=name
        self.records=[]
        self.layers={}
        self.data={}

    def center(self,layer,box,ident,opacity=1,**metadata):
        if opacity<1/255:
            self.data.setdefault('intentional_absences',[]).append(ident)
            return None
        if opacity<1:
            layer=layer.copy()
            layer.putalpha(layer.getchannel('A').point(lambda a:round(a*opacity)))
        threshold=max(1,round(128*opacity))
        b=m.bbox(layer,threshold)
        if b is None:
            raise ValueError(f'Empty component {ident}')
        xy=(round((box[0]+box[2]-b[0]-b[2])/2),round((box[1]+box[3]-b[1]-b[3])/2))
        row=raster_centering_report(layer,box,origin_xy=xy,name=f'{self.name}/{ident}',tolerance_px=.5,alpha_threshold=threshold)
        row.update(component_id=ident,horizontal='center',vertical='center',opacity=opacity,**metadata)
        if not row['passed']:
            raise ValueError(row)
        self.records.append(row)
        self.layers[ident]=(layer,xy,threshold)
        self.image.alpha_composite(layer,xy)
        return xy

    def text(self,text,box,size,ident,color=INK,opacity=1):
        return self.center(m.text_layer(text,size,color),box,ident,opacity,text=text,font_size_px=size,color=color)

    def lines(self,lines,box,size,ident,color=MUTED):
        return self.center(m.multiline_layer(lines,size,color),box,ident,text='\n'.join(lines),lines=lines,font_size_px=size,color=color,line_spacing_px=12,group='whole multiline visible glyph group')

    def power(self,n,box=FIELDS['power'],size=74,ident='power'):
        base=m.text_layer('2',size,INK)
        exp_size=round(size*.53)
        power=m.text_layer(str(n),exp_size,TEAL)
        bb,pb=m.bbox(base),m.bbox(power)
        layer=Image.new('RGBA',(500,size*2+100))
        base_xy=(30-bb[0],50-bb[1])
        power_xy=(30+bb[2]-bb[0]+9-pb[0],20-pb[1])
        layer.alpha_composite(base,base_xy);layer.alpha_composite(power,power_xy)
        origin=self.center(layer,box,ident,text=f'2^{n}',base_font_size_px=size,exponent_font_size_px=exp_size,base_color=INK,exponent_color=TEAL,base_visible_top_local_px=50,exponent_visible_top_local_px=20,glyph_gap_px=9)
        for key,text,piece,xy,font_size,color in [('base','2',base,base_xy,size,INK),('exponent',str(n),power,power_xy,exp_size,TEAL)]:
            b=m.bbox(piece)
            visible=[b[0]+xy[0]+origin[0],b[1]+xy[1]+origin[1],b[2]+xy[0]+origin[0],b[3]+xy[1]+origin[1]]
            self.records.append(dict(component_id=f'{ident}/{key}',text=text,font_size_px=font_size,color=color,visible_box_xyxy=visible,measurement_origin_px=[xy[0]+origin[0],xy[1]+origin[1]],horizontal='registered relative glyph gap',vertical='registered visible top offset',parent_component=ident,drawn_as_part_of_parent=True,passed=True,contained=True,delta_x_px=0,delta_y_px=0))

    def panel(self,box,outline='#c4ad85',fill=CREAM):
        self.draw.rounded_rectangle(tuple(round(x) for x in box),18,fill=fill,outline=outline,width=2)

    def clearance(self):
        # Body / teaching numerals / reading must never collide. The two equal
        # copy layers may contact while they separate from the same source.
        contacts=[]
        keys=list(self.layers)
        for i,a in enumerate(keys):
            for b in keys[i+1:]:
                if {a,b}<={'original-copy-value','second-copy-value'} or {a,b}<={'old-paper-units','new-paper-units'}:
                    continue
                la,oa,ta=self.layers[a];lb,ob,tb=self.layers[b]
                ba=m.bbox(la,ta);bb=m.bbox(lb,tb)
                aa=[ba[0]+oa[0],ba[1]+oa[1],ba[2]+oa[0],ba[3]+oa[1]]
                ab=[bb[0]+ob[0],bb[1]+ob[1],bb[2]+ob[0],bb[3]+ob[1]]
                x0,y0=max(aa[0],ab[0]),max(aa[1],ab[1]);x1,y1=min(aa[2],ab[2]),min(aa[3],ab[3])
                if x0>=x1 or y0>=y1:
                    continue
                am=la.getchannel('A').point(lambda x:255 if x>=ta else 0).crop((x0-oa[0],y0-oa[1],x1-oa[0],y1-oa[1]))
                bm=lb.getchannel('A').point(lambda x:255 if x>=tb else 0).crop((x0-ob[0],y0-ob[1],x1-ob[0],y1-ob[1]))
                if ImageChops.multiply(am,bm).getbbox():
                    contacts.append([a,b])
        if contacts:
            raise ValueError(f'Foreground collisions {self.name}: {contacts}')
        self.data['unintended_foreground_contacts']=contacts


class Actor:
    def __init__(self,registration=None):
        lib=json.loads((ROOT/'catalogs/character-library-v1.json').read_text())
        neutral=next(c for c in lib['characters'] if c['id']=='fairy-pitta')['neutral']
        self.rows={'neutral':neutral}
        self.registration_paths=[]
        for path in [m.REG,resolve(registration) if registration else None]:
            if path and path.exists():
                data=json.loads(path.read_text());rows=data.get('poses',data.get('frames',{}))
                rows=rows if isinstance(rows,dict) else {r['id']:r for r in rows}
                for ident,row in rows.items():
                    if row.get('animation_composite'):
                        selected={**row,**row['animation_composite'],'raw_source_path':row['path'],'raw_source_sha256':row['sha256'],'selection':'explicit canonical-body animation composite'}
                    elif ident=='watch_up':
                        selected={**neutral,'id':ident,'selection':'explicit canonical neutral alias; generated raw gaze not selected','raw_source_path':row['path']}
                    else:
                        selected=row
                    self.rows[ident]=selected
                self.registration_paths.append(receipt(path))
        self.images={}
        for ident,row in self.rows.items():
            path=resolve(row['path'])
            if sha(path)!=row['sha256']:
                raise ValueError(f'Actor source changed: {ident}')
            if not row.get('reference_height_px') or not row.get('anchor_px'):
                raise ValueError(f'Actor needs scale/support {ident}')
            self.images[ident]=Image.open(path).convert('RGBA')

    def choose(self,*ids):
        return next((x for x in ids if x in self.rows),'neutral')

    @lru_cache(maxsize=128)
    def sprite(self,pose,height):
        row=self.rows[pose];im=self.images[pose];scale=height/row['reference_height_px']
        if row.get('render_mode')=='canonical_plus_overlay':
            # The overlay is already a registered RGBA layer. It carries only
            # the newly drawn wing/eyes; the adopted head, body and feet remain
            # the exact canonical pixels. No silhouette/face dissolve.
            canonical=self.rows['neutral'];body=self.images['neutral']
            cs=height/canonical['reference_height_px']
            body=body.resize((round(body.width*cs),round(body.height*cs)),Image.Resampling.LANCZOS)
            overlay=im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.LANCZOS)
            c_anchor=canonical['anchor_px'];o_anchor=row['anchor_px']
            offset=row.get('overlay_offset_canonical_px',[0,0])
            xy=(round(c_anchor[0]*cs-o_anchor[0]*scale+offset[0]*cs),round(c_anchor[1]*cs-o_anchor[1]*scale+offset[1]*cs))
            # Union canvas retains every outboard feather instead of cropping
            # overlays to the canonical neutral's transparent source boundary.
            minx,miny=min(0,xy[0]),min(0,xy[1]);maxx,maxy=max(body.width,xy[0]+overlay.width),max(body.height,xy[1]+overlay.height)
            joined=Image.new('RGBA',(maxx-minx,maxy-miny));joined.alpha_composite(body,(-minx,-miny));joined.alpha_composite(overlay,(xy[0]-minx,xy[1]-miny))
            synthetic={**row,'anchor_px':[c_anchor[0]*cs-minx,c_anchor[1]*cs-miny],'reference_height_px':height,'rendered_from_canonical_plus_overlay':True,'registered_overlay_scale':scale,'canonical_source':canonical['path'],'canonical_scale':cs}
            # Returned synthetic image is already in output pixels. A 1:1
            # support transform prevents per-pose fitting after composition.
            return joined,synthetic,1
        return im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.LANCZOS),row,scale

    def draw(self,c,pose,height,foot):
        image,row,scale=self.sprite(pose,height)
        anchor=row['anchor_px']
        xy=(round(foot[0]-anchor[0]*scale),round(foot[1]-anchor[1]*scale))
        b=m.bbox(image,8)
        bounds=[b[0]+xy[0],b[1]+xy[1],b[2]+xy[0],b[3]+xy[1]]
        actual=[xy[0]+anchor[0]*scale,xy[1]+anchor[1]*scale]
        dx,dy=actual[0]-foot[0],actual[1]-foot[1]
        passed=abs(dx)<=.5 and abs(dy)<=.5 and 20<=bounds[0] and 20<=bounds[1] and bounds[2]<=1900 and bounds[3]<=1060
        rec=dict(component_id='character',pose=pose,path=row['path'],sha256=row['sha256'],horizontal='anatomical-foot-x',vertical='anatomical-foot-y',target_anchor_px=list(foot),actual_anchor_px=actual,delta_x_px=dx,delta_y_px=dy,tolerance_px=.5,visible_box_xyxy=bounds,reference_height_px=row['reference_height_px'],display_body_height_px=height,scale=scale,anchor_px=anchor,passed=passed,contained=passed,full_actor_crossfade=False,per_pose_bbox_fit=False,canonical_plus_overlay=row.get('rendered_from_canonical_plus_overlay',False),canonical_body_fixed=row.get('canonical_body_fixed',False),canonical_source=row.get('canonical_source'),registered_overlay_scale=row.get('registered_overlay_scale'),selection=row.get('selection'))
        if not passed:
            raise ValueError(rec)
        c.records.append(rec);c.layers['character']=(image,xy,8)
        c.image.alpha_composite(image,xy)
        c.data['actor']=rec


@dataclass(frozen=True)
class Frame:
    mode:str
    n:int
    stage:str='hold'
    tick:int=60
    pose:str='neutral'
    completed:int=0
    lesson_tick:int=0
    fade:int=0


def prepared_plan(path):
    plan=json.loads(Path(path).read_text())
    plan['voice_events']=plan.get('voice_events',plan.get('events'))
    if len(plan['counted_states'])!=65 or len([e for e in plan['voice_events'] if e['id'].startswith('N')])!=65:
        raise ValueError('65 measured result states/events required')
    for n,row in enumerate(plan['counted_states']):
        if int(row['value'])!=2**n or row['index']!=n:
            raise ValueError('Timeline mathematical state mismatch')
        row['result_frame']=math.ceil(row['result_start_s']*FPS)
        row['operation_frame']=math.ceil(row['operation_start_s']*FPS) if n else row['result_frame']
    return plan


class Episode:
    def __init__(self,timeline,registration=None,background=None):
        self.timeline_path=Path(timeline)
        self.plan=prepared_plan(timeline)
        self.events=self.plan['voice_events'];self.by={e['id']:e for e in self.events}
        self.counts=self.plan['counted_states'];self.ends=[r['voice_end_s'] for r in self.counts]
        self.background_path=resolve(background) if background else m.BG
        self.background=ImageOps.fit(Image.open(self.background_path).convert('RGBA'),SIZE,Image.Resampling.LANCZOS)
        self.actor=Actor(registration)
        self.segments=self.make_segments();self.starts=[s['start_frame'] for s in self.segments]
        self.motion=self.make_motion()
        self.reports={}
        self.sources=[receipt(self.timeline_path),receipt(self.background_path),receipt(__file__),receipt(m.__file__),receipt(m.FONT)]+self.actor.registration_paths+[receipt(resolve(row['path'])) for row in self.actor.rows.values()]

    def make_segments(self):
        segments=[dict(mode='intro',n=0,start_frame=0,cue='I001')]
        for n,row in enumerate(self.counts):
            segments.append(dict(mode='count',n=n,start_frame=row['operation_frame'],cue=f'N{n:03d}'))
            teaching=self.by.get(f'X{n:03d}')
            if teaching:
                segments.append(dict(mode='teaching',n=n,start_frame=math.ceil(teaching['start_s']*FPS),cue=teaching['id']))
        segments.append(dict(mode='outro',n=64,start_frame=math.ceil(self.by['O001']['start_s']*FPS),cue='O001'))
        segments.sort(key=lambda x:x['start_frame'])
        for i,s in enumerate(segments):
            s['end_frame']=segments[i+1]['start_frame'] if i+1<len(segments) else self.plan['duration_frames']
        return segments

    def make_motion(self):
        a=self.actor;rows=[]
        def add(ident,cue,edge,offset,poses,lengths,reason):
            event=self.by.get(cue)
            if not event:
                return
            start=math.ceil((event[edge]+offset)*FPS);cursor=start;keys=[]
            for pose,length in zip(poses,lengths):
                keys.append(dict(at_frame=cursor,pose=pose,hold_frames=length));cursor+=length
            rows.append(dict(id=ident,source_cue=cue,source_edge=edge,offset_s=offset,start_frame=start,end_frame=cursor,keyframes=keys,reason=reason,full_actor_crossfade=False))
        wave=[a.choose('gesture_rest','wave_prepare','cue_half'),a.choose('gesture_low','wave_half','cue_half'),a.choose('gesture_mid','wave_up','cue_up'),a.choose('gesture_high','wave_out','cue_up'),a.choose('gesture_mid','wave_in','cue_up'),a.choose('gesture_high','wave_out','cue_up'),a.choose('gesture_mid','wave_half','cue_half'),a.choose('gesture_low','wave_prepare','settle'),a.choose('gesture_rest','settle'),'neutral']
        for cue,name in [('I001','welcome'),('O002','farewell')]:
            add(name,cue,'start_s',.12,wave,[5,6,6,7,7,7,6,5,6,6],'Raise a wing, two short waves, lower and return to the adopted neutral.')
        guide=['neutral',a.choose('gesture_rest','cue_prepare','cue_half'),a.choose('gesture_low','cue_half'),a.choose('gesture_mid','cue_half'),a.choose('gesture_high','cue_up'),a.choose('gesture_mid','cue_half'),a.choose('gesture_low','cue_prepare','settle'),a.choose('gesture_rest','settle'),'neutral']
        for n in [0,3,40]:
            add(f'guide-{n:03d}',f'X{n:03d}','start_s',.2,guide,[6,5,6,7,24,7,6,5,6],'Indicate the actual exponent or rule and return through intermediate wing positions.')
        wonder=['neutral',a.choose('gesture_rest','settle'),a.choose('gesture_low','cue_half'),a.choose('open_half','wonder_half','cue_half'),a.choose('open_full','wonder_open'),a.choose('open_half','wonder_half','cue_half'),a.choose('gesture_low','cue_half'),a.choose('gesture_rest','settle'),'neutral']
        for n in [5,10,30,60]:
            add(f'wonder-{n:03d}',f'X{n:03d}','start_s',.15,wonder,[6,5,6,8,25,9,7,6,6],'Open both wings at this authored milestone and settle without changing the reading cadence.')
        look=[a.choose('gesture_rest','neutral'),a.choose('gesture_low','cue_half'),a.choose('gesture_mid','cue_half'),a.choose('gesture_low','cue_half'),a.choose('gesture_rest','neutral'),'neutral']
        for n in [7,16,25,36,48,57]:
            add(f'small-cue-{n:03d}',f'N{n:03d}','end_s',.03,look,[5,7,12,8,6,5],'A small wing cue accompanies the next equal copy, then returns to the exact neutral; no body oscillation or unselected gaze sprite.')
        rest=[a.choose('rest_half','rest_prepare','settle'),a.choose('rest_low','perch_rest','rest','settle'),a.choose('rest_half','rest_prepare','settle'),a.choose('gesture_rest','settle'),'neutral']
        for n in [20,44,53]:
            available=round((self.by[f'N{n:03d}']['end_s']-self.by[f'N{n:03d}']['start_s']-.8)*FPS)
            hold=max(30,min(180,available-35))
            add(f'quiet-rest-{n:03d}',f'N{n:03d}','start_s',.3,rest,[9,hold,10,8,8],'Quiet lowered stance during a long spoken value; use common physical scale and grounded feet, then stand and return.')
        blink=['neutral',a.choose('blink_closed','neutral'),'neutral']
        for n in [2,12,23,35,46,58]:
            add(f'blink-{n:03d}',f'N{n:03d}','start_s',.45,blink,[6,3,6],'A brief blink during a stable spoken number; no body wobble loop.')
        return sorted(rows,key=lambda r:r['start_frame'])

    def pose_at(self,f):
        active=[r for r in self.motion if r['start_frame']<=f<r['end_frame']]
        if not active:
            return 'neutral'
        row=active[-1]
        return next(k['pose'] for k in reversed(row['keyframes']) if k['at_frame']<=f)

    def state(self,f):
        t=f/FPS
        i=bisect_right(self.starts,f)-1;s=self.segments[max(0,i)]
        n=s['n'];mode=s['mode'];row=self.counts[n]
        completed=bisect_right(self.ends,t)
        stage='hold';tick=60;lesson=0
        if mode=='count' and n and f<row['result_frame']:
            stage='operation';tick=round(clamp((f-row['operation_frame'])/(row['result_frame']-row['operation_frame']))*60)
        if mode=='teaching':
            event=self.by[s['cue']]
            lesson=round(clamp((t-event['start_s'])/(event['end_s']-event['start_s']))*60)
        if mode in ['intro','outro']:
            lesson=round(clamp((f-s['start_frame'])/max(1,s['end_frame']-s['start_frame']))*60)
        fade=0
        if mode=='intro' and f<18:
            fade=round((1-f/18)*255)
        if mode=='outro' and f>self.plan['duration_frames']-18:
            fade=round((f-(self.plan['duration_frames']-18))/18*255)
        return Frame(mode,n,stage,tick,self.pose_at(f),completed,lesson,fade)

    def character_placement(self,state):
        if state.mode=='intro':
            return 320,(960,1050)
        if state.mode=='outro':
            return 300,(960,1050)
        if state.mode=='teaching' and state.n in [0,3,5]:
            return 320,(1400,1035)
        if state.n<=5:
            return 230,(1430,1048)
        if state.n<=10:
            return 180,(960,1052)
        return 150,(1440,1050)

    def progress(self,c,state):
        c.text(f'Counted: {state.completed} / 65',FIELDS['progress'],24,'progress',MUTED)

    def count(self,c,state):
        n=state.n;value=1<<n;prev=value//2 if n else None;p=state.tick/60
        displayed_n=n if state.stage=='hold' or p>=.68 or n==0 else n-1
        c.power(displayed_n)
        if n==0:
            c.text('= 1',(690,342,1230,438),80,'seed-equation')
            c.center(m.diamonds(1,84),(710,466,1210,608),'old-paper-units')
            c.text('No doubling yet. Start with one.',(400,650,1520,718),38,'seed-explanation',TEAL)
            c.text('one',FIELDS['english'],25,'english',MUTED)
            c.data.update(value=str(value),displayed_exponent=0,exact_old_unit_count=1,exact_new_unit_count=0,answer_text=None,seed=True)
            return
        pending=state.stage=='operation'
        if not c.data.get('suppress_pending_label'):
            c.text('Making the next power' if pending else f'Doublings: {n}',FIELDS['pending'],25,'pending-label',MUTED)
        if n<=5:
            c.text(f'{prev:,} × 2'+('' if pending else f' = {value:,}'),FIELDS['operation'],62,'operation')
            size=44 if n<=4 else 28
            c.center(m.diamonds(prev,size,8),FIELDS['old-paper-units'],'old-paper-units')
            new_p=ease(clamp((p-.16)/.55)) if pending else 1
            if new_p>0:
                # A duplicate travels from the identical source, through the
                # mathematical ×2 shutter, into the second group.
                dx=lerp(-740,0,new_p)
                c.center(m.diamonds(prev,size,8,TEAL,True),shifted(FIELDS['new-paper-units'],dx,-55*math.sin(math.pi*new_p)),'new-paper-units',min(1,new_p*4))
            c.text('same group',(350,626,830,660),24,'original-copy-label',MUTED)
            c.text('one more copy',(1090,626,1570,660),24,'second-copy-label',TEAL)
            opening=new_p
            w=round(70*(1-opening))+3
            c.draw.rectangle((956-w,448,956,578),fill='#dac8a7',outline='#ad8d62',width=2)
            c.draw.rectangle((964,448,964+w,578),fill='#eddec0',outline='#ad8d62',width=2)
            c.text('× 2',(866,572,1054,632),48,'gate',TEAL)
            c.data.update(exact_old_unit_count=prev,exact_new_unit_count=prev if new_p*4>=1/255 else 0,copy_progress=new_p)
        elif pending:
            # Both labels use the same integer, laid out on two full-width rows.
            # Their horizontal lengths never force a smaller font on a value.
            lift=ease(clamp(p/.24))
            original_box=shifted(FIELDS['answer'],0,lerp(0,-345,lift))
            original_size=round(lerp(80,46,lift))
            c.text(f'{prev:,}',original_box,original_size,'original-copy-value')
            cp=ease(clamp((p-.24)/.46))
            if cp>0:
                copy_box=shifted(FIELDS['second-copy-value'],0,lerp(-108,0,cp))
                c.text(f'{prev:,}',copy_box,46,'second-copy-value',TEAL,min(1,cp*4))
            if lift>=1:
                c.text('ORIGINAL GROUP',FIELDS['original-copy-label'],22,'original-copy-label',MUTED)
            if cp>=1:
                c.text('EQUAL COPY',FIELDS['second-copy-label'],22,'second-copy-label',TEAL)
            if lift>=1:
                c.text('× 2',FIELDS['gate'],52,'gate',TEAL)
            c.data.update(copy_progress=cp,symbolic_group_values=[str(prev),str(prev)] if cp>0 else [str(prev)],individual_units_shown=False)
        else:
            c.text('previous value',(520,302,1400,334),24,'input-label',MUTED)
            c.text(f'{prev:,}',FIELDS['input-value'],62,'input-value')
            c.panel((830,478,1090,576),outline='#b89d70',fill='#f2e7d0')
            c.text('× 2',(850,492,1070,562),52,'gate',TEAL)
            c.text('=',FIELDS['equals'],38,'equals',MUTED)
            c.data.update(symbolic_group_values=[str(prev)],individual_units_shown=False)
        question_visible=not pending or n<=5 or p>=.24
        if question_visible:
            c.text('?' if pending else f'{value:,}',FIELDS['answer'],80,'answer',TEAL)
        lines=['Copy the whole amount.'] if pending else textwrap.wrap(m.number_words(value),68,break_long_words=False,break_on_hyphens=False)
        c.lines(lines,FIELDS['english'],25,'english',MUTED)
        c.data.update(value=str(value),previous_value=str(prev),displayed_exponent=displayed_n,answer_text=('?' if question_visible else None) if pending else f'{value:,}',result_atomic=True,prior_result_lift=(pending and n>=6 and p<.24))

    def teaching(self,c,state):
        n=state.n
        if n==3:
            c.power(3,(330,218,900,478),240,'detail-power')
            c.lines(['The raised 3 counts','three doubling steps.'],(980,248,1550,414),34,'detail-explanation',TEAL)
            positions=[400,700,1000,1300]
            highlight=min(3,state.lesson_tick//15)
            for k,(v,x) in enumerate(zip([1,2,4,8],positions)):
                c.text(str(v),(x-70,564,x+70,656),74,f'detail-value-{k}',TEAL if k<=highlight else INK)
            arrow=Image.new('RGBA',(186,48));d=ImageDraw.Draw(arrow)
            d.line((20,24,158,24),fill=MUTED,width=4);d.polygon([(145,13),(166,24),(145,35)],fill=MUTED)
            for k in range(3):
                x=(positions[k]+positions[k+1])//2
                c.center(arrow,(x-94,584,x+94,632),f'detail-arrow-{k+1}')
                c.text('× 2',(x-75,512,x+75,556),32,f'detail-label-{k+1}',TEAL)
            c.text('3 doublings from 1',(330,722,1170,790),44,'detail-step-count',TEAL)
            c.data.update(replay=True,result_value='8',exact_doubling_arrows=3)
        elif n==5:
            c.power(5)
            c.text('32 individual paper shapes',(350,330,1570,390),42,'group-transition-title')
            c.center(m.diamonds(32,34,8),(330,422,1070,684),'group-transition-shapes')
            c.panel((1160,450,1560,660),outline=TEAL)
            c.text('32',(1200,470,1520,574),80,'group-transition-value',TEAL)
            c.text('units in this group',(1190,580,1530,630),25,'group-transition-units',TEAL)
            c.lines(['Next, a labeled group stands','for the whole amount.'],(350,738,1160,836),32,'group-transition-explanation',MUTED)
            c.data.update(replay=True,result_value='32',exact_unit_count=32,symbolic_group_value='32',not_next_result=True)
        elif n==0:
            self.count(c,Frame('count',0,pose=state.pose,completed=state.completed))
        else:
            c.data['suppress_pending_label']=True
            self.count(c,Frame('count',n,pose=state.pose,completed=state.completed))
            labels={10:'FIRST PAST ONE THOUSAND',20:'FIRST PAST ONE MILLION',30:'FIRST PAST ONE BILLION',40:'FIRST PAST ONE TRILLION',60:'FIRST PAST ONE QUINTILLION'}
            c.text(labels[n],(340,120,1580,160),30,'milestone-title',TEAL)
            c.data['replay']=True

    def intro(self,c,state):
        c.text('POWERS OF 2',(400,128,1520,208),54,'intro-title')
        c.text('Start with one.',(400,248,1520,310),43,'intro-start')
        c.power('n',(650,350,1270,520),130,'intro-power')
        c.text('Copy the whole group. Double it.',(340,570,1580,636),40,'intro-rule',TEAL)
        c.text('1   2   4   8   16   32   …',(330,676,1590,730),43,'intro-sequence')

    def outro(self,c,state):
        c.text('POWERS OF 2',(400,128,1520,208),54,'outro-title')
        c.text('Next value = previous value × 2',(340,278,1580,350),46,'outro-recurrence')
        c.power('n',(690,390,1230,526),94,'outro-power')
        c.text('1   2   4   8   16   32   …',(340,580,1580,642),46,'outro-sequence',TEAL)
        c.text('65 terms • 64 doublings • starting at 1',(340,684,1580,734),30,'outro-count',MUTED)

    @lru_cache(maxsize=8)
    def image(self,state):
        c=Canvas(self.background,json.dumps(asdict(state),sort_keys=True))
        {'count':self.count,'teaching':self.teaching,'intro':self.intro,'outro':self.outro}[state.mode](c,state)
        height,foot=self.character_placement(state)
        self.actor.draw(c,state.pose,height,foot)
        if state.mode!='intro' and state.mode!='outro':
            self.progress(c,state)
        c.clearance()
        im=c.image.convert('RGB')
        if state.fade:
            im=Image.blend(im,Image.new('RGB',SIZE,CREAM),state.fade/255)
        key=json.dumps(asdict(state),sort_keys=True,separators=(',',':'))
        report=dict(key=key,state_key=key,state=asdict(state),components=c.records,data=c.data,source_alignment_passed=all(r['passed'] for r in c.records),whole_frame_fade=bool(state.fade))
        self.reports[state]=report
        return im.tobytes(),report

    def export_plan(self,directory):
        directory.mkdir(parents=True,exist_ok=True)
        spec=dict(schema_version=1,size_px=list(SIZE),fps=FPS,font=receipt(m.FONT),colors=dict(ink=INK,muted=MUTED,accent=TEAL),fields=FIELDS,main_result_font_px=80,english_font_px=25,english_wrap_characters=68,english_line_spacing_px=12,power=dict(base_font_px=74,exponent_font_px=39,base_visible_top_local_px=50,exponent_visible_top_local_px=20,glyph_gap_px=9),operation_phases=dict(prior_lift=[0,.24],prior_lift_type='same previous result80px at result center707 lifts to original group center362 while shrinking to46px; question appears after lift',copy_separation=[.24,.70],power_increment=.68,result='atomic at counted_state.result_frame, never a digit interpolation'),rounding='ceil each timeline transition timestamp*30; frame sample time frame/30',background=receipt(self.background_path),actor_registrations=self.actor.registration_paths)
        (directory/'visual-spec.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n')
        (directory/'character-motion.json').write_text(json.dumps(dict(schema_version=1,windows=self.motion,default_pose='neutral',scene_placements={f'{mode}-{n}':{'height':self.character_placement(Frame(mode,n))[0],'foot':self.character_placement(Frame(mode,n))[1]} for mode,n in [('intro',0),('count',3),('teaching',3),('count',6),('count',64),('outro',64)]}),ensure_ascii=False,indent=2)+'\n')
        (directory/'visual-segments.json').write_text(json.dumps(self.segments,ensure_ascii=False,indent=2)+'\n')


def write_report_rows(path,reports):
    with gzip.open(path,'wt',encoding='utf8') as stream:
        for r in reports:
            stream.write(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n')


def prepare_qa(ep,out):
    out.mkdir(parents=True,exist_ok=True)
    samples=[]
    for n in range(65):
        for tick in ([60] if n==0 else [0,1,12,24,36,42,54,59,60]):
            state=Frame('count',n,'hold' if tick==60 else 'operation',tick,'neutral',n+int(tick==60))
            raw,report=ep.image(state);samples.append(report)
            if n in [0,3,4,5,6,10,11,40,60,63,64] and tick in [0,36,60]:
                Image.frombytes('RGB',SIZE,raw).save(out/f'n{n:02d}-tick{tick:02d}.png')
    for n in [0,3,5,10,20,30,40,60]:
        state=Frame('teaching',n,pose=ep.actor.choose('gesture_high','cue_up'),completed=n+1,lesson_tick=30)
        raw,report=ep.image(state);samples.append(report)
        Image.frombytes('RGB',SIZE,raw).save(out/f'teaching-{n:02d}.png')
    write_report_rows(out/'layout-probes.jsonl.gz',samples)
    summary=dict(status='pass',scope='all65 static states and eight operation probes each; teaching modes; source-raster only',states=len(samples),components=sum(len(r['components']) for r in samples),max_abs_dx_px=max(abs(c['delta_x_px']) for r in samples for c in r['components']),max_abs_dy_px=max(abs(c['delta_y_px']) for r in samples for c in r['components']),all_passed=all(r['source_alignment_passed'] for r in samples),timeline=receipt(ep.timeline_path),renderer=receipt(__file__))
    (out/'source-layout-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


def encoder(path):
    ffmpeg=shutil.which('ffmpeg') or str(ROOT/'.venv/bin/ffmpeg')
    return subprocess.Popen([ffmpeg,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','-','-an','-vf','scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-color_range','tv','-movflags','+faststart',str(path)],stdin=subprocess.PIPE)


def preview(ep,out):
    out.mkdir(parents=True,exist_ok=True)
    # Discontinuous excerpts are labelled as a silent motion review, not a
    # shortened episode or a substitute for measured narration.
    states=[]
    for f in range(120):
        states.append(Frame('intro',0,pose=ep.pose_at(math.ceil(ep.by['I001']['start_s']*30)+f),lesson_tick=round(f/2)))
    for n in [3,6,40,64]:
        for f in range(120):
            tick=min(60,round(f/56*60))
            pose=ep.actor.choose('gesture_low','cue_half') if f<30 else ep.actor.choose('gesture_high','cue_up') if f<56 else ep.actor.choose('gesture_rest','settle')
            states.append(Frame('count',n,'operation' if f<56 else 'hold',tick,pose,n+int(f>=56)))
    for f in range(90):
        states.append(Frame('teaching',3,pose=ep.actor.choose('gesture_high','cue_up'),completed=4,lesson_tick=round(f/90*60)))
    path=out/'powers-of-two-motion-preview-1080p.mp4';process=encoder(path);reports=[]
    with gzip.open(out/'preview-frame-states.jsonl.gz','wt',encoding='utf8') as frames:
        for f,state in enumerate(states):
            raw,report=ep.image(state);process.stdin.write(raw)
            frames.write(json.dumps(dict(frame=f,time_s=f/30,state=asdict(state)))+'\n')
            if f%30==0:
                Image.frombytes('RGB',SIZE,raw).save(out/f'frame-{f:04d}.png')
            reports.append(report)
    process.stdin.close()
    if process.wait()!=0:
        raise RuntimeError('Preview encode failed')
    write_report_rows(out/'preview-reports.jsonl.gz',reports)
    (out/'preview-manifest.json').write_text(json.dumps(dict(status='rendered_for_review',scope='silent motion excerpts; not final episode cadence or final speech synchronization',path=local(path),sha256=sha(path),frames=len(states),duration_s=len(states)/30,renderer=receipt(__file__)),indent=2)+'\n')
    return path


def actor_preview(ep,out):
    out.mkdir(parents=True,exist_ok=True)
    a=ep.actor
    sequences=[('Raise, wave twice, return',['neutral',a.choose('gesture_rest'),a.choose('gesture_low'),a.choose('gesture_mid'),a.choose('gesture_high'),a.choose('gesture_mid'),a.choose('gesture_high'),a.choose('gesture_mid'),a.choose('gesture_low'),a.choose('gesture_rest'),'neutral'],[12,6,7,8,8,8,8,8,7,6,12]),('Notice, open a wing, settle',['neutral',a.choose('gesture_low'),a.choose('open_half','wonder_open'),a.choose('open_full','wonder_open'),a.choose('open_half','wonder_open'),a.choose('gesture_low'),a.choose('gesture_rest'),'neutral'],[12,8,9,20,9,8,8,12]),('Watch, blink, relax and stand',['neutral',a.choose('watch_up'),a.choose('blink_closed'),a.choose('watch_up'),'neutral',a.choose('rest_half','settle'),a.choose('rest_low','settle'),a.choose('rest_half','settle'),'neutral'],[12,15,3,10,10,12,45,12,12])]
    path=out/'actor-motion-review-320px-1080p.mp4';process=encoder(path);reports=[];frame=0
    for title,poses,lengths in sequences:
        for pose,length in zip(poses,lengths):
            c=Canvas(ep.background,f'actor-review-{frame:04d}')
            c.text('CHARACTER MOTION REVIEW',(350,150,1570,216),44,'review-title')
            c.text(title,(300,300,1620,356),34,'action-title',TEAL)
            c.text('Common body reference: 320 px • fixed anatomical foot support',(270,430,1650,480),26,'review-scale',MUTED)
            ep.actor.draw(c,pose,320,(960,1035));c.clearance()
            raw=c.image.convert('RGB').tobytes()
            for _ in range(length):
                process.stdin.write(raw);frame+=1
            reports.append(dict(start_frame=frame-length,end_frame=frame,pose=pose,components=c.records,data=c.data))
            c.image.convert('RGB').save(out/f'actor-{frame-length:04d}-{pose}.png')
    process.stdin.close()
    if process.wait()!=0:
        raise RuntimeError('Actor review encode failed')
    (out/'actor-motion-review.json').write_text(json.dumps(dict(status='for_root_review',video=receipt(path),frame_count=frame,duration_s=frame/30,common_body_height_px=320,reports=reports),ensure_ascii=False,indent=2)+'\n')
    return path


def render(ep,out,audio):
    out.mkdir(parents=True,exist_ok=True)
    final=out/VIDEO_NAME
    if final.exists():
        raise FileExistsError(final)
    for source in ep.sources:
        if sha(resolve(source['path']))!=source['sha256']:
            raise ValueError(f'Frozen visual input changed before render: {source["path"]}')
    silent=out/'silent-picture.mp4';process=encoder(silent)
    frames_path=out/'visual-frame-states.jsonl.gz'
    reports={}
    with gzip.open(frames_path,'wt',encoding='utf8') as frames:
        for f in range(ep.plan['duration_frames']):
            state=ep.state(f);raw,report=ep.image(state);process.stdin.write(raw)
            key=json.dumps(asdict(state),sort_keys=True,separators=(',',':'))
            reports[key]=report
            frames.write(json.dumps(dict(frame=f,time_s=f/30,state_key=key,state=asdict(state)),separators=(',',':'))+'\n')
            if f%900==0:
                print(json.dumps(dict(rendered_frame=f,total_frames=ep.plan['duration_frames'])),flush=True)
    process.stdin.close()
    if process.wait()!=0:
        raise RuntimeError('Full picture encode failed')
    ffmpeg=shutil.which('ffmpeg') or str(ROOT/'.venv/bin/ffmpeg')
    subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y','-i',str(silent),'-i',str(audio),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t',str(ep.plan['duration_frames']/30),'-movflags','+faststart',str(final)],check=True)
    write_report_rows(out/'distinct-state-reports.jsonl.gz',reports.values())
    for source in ep.sources:
        if sha(resolve(source['path']))!=source['sha256']:
            raise ValueError(f'Frozen visual input changed during render: {source["path"]}')
    manifest=dict(status='rendered_pending_independent_final_qa',completed=False,video=receipt(final),silent_picture=receipt(silent),audio=receipt(audio),timeline=receipt(ep.timeline_path),renderer=receipt(__file__),source_mockup_helpers=receipt(m.__file__),frozen_sources=ep.sources,frame_count=ep.plan['duration_frames'],duration_s=ep.plan['duration_frames']/30,distinct_visual_states=len(reports),all_source_alignment_passed=all(r['source_alignment_passed'] for r in reports.values()),frame_states=receipt(frames_path),state_reports=receipt(out/'distinct-state-reports.jsonl.gz'))
    (out/'render-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return final


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--timeline',type=Path,default=DEFAULT_OUT/'audio-build/timeline.json')
    ap.add_argument('--actor-registration',type=Path)
    ap.add_argument('--background',type=Path)
    ap.add_argument('--out-dir',type=Path,default=DEFAULT_OUT)
    ap.add_argument('--audio',type=Path)
    ap.add_argument('--preview',action='store_true')
    ap.add_argument('--render',action='store_true')
    ap.add_argument('--qa-only',action='store_true')
    ap.add_argument('--actor-preview-only',action='store_true')
    args=ap.parse_args()
    ep=Episode(args.timeline,args.actor_registration,args.background)
    ep.export_plan(args.out_dir/'visual-plan')
    if args.actor_preview_only:
        print(actor_preview(ep,args.out_dir/'motion-preview'))
        return
    summary=prepare_qa(ep,args.out_dir/'visual-plan/source-qa')
    print(json.dumps(summary),flush=True)
    if args.preview:
        print(actor_preview(ep,args.out_dir/'motion-preview'))
        print(preview(ep,args.out_dir/'motion-preview'))
    if args.render:
        if not args.audio:
            raise ValueError('--render requires an explicit accepted --audio master')
        print(render(ep,args.out_dir/'video',args.audio))


if __name__=='__main__':
    main()
