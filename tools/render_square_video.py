"""Render the square-number episode from measured, immutable speech cues.

The visual plan records every output frame, glyph/diagram observations for each
distinct layout, and the registered actor state. No actor dissolve, per-pose fit,
or free-running audio clock is used.
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

from PIL import Image, ImageChops, ImageDraw, ImageOps

try:
    import render_square_mockups as m
except ModuleNotFoundError:
    from tools import render_square_mockups as m

ROOT=m.ROOT
DESIGN=ROOT/'design/square-counting-v1'
MOTION=DESIGN/'production-motion'
FPS=30
SIZE=(1920,1080)
VIDEO_NAME='paspla-studio-square-numbers-0-to-10000-1080p.mp4'
FORMULA_BOX=(264,190,1656,292)
READING_BOX=(350,922,1570,977)
PROGRESS_BOX=(180,1027,1740,1061)


def local(path):
    return str(Path(path).resolve().relative_to(ROOT))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def receipt(path):
    return {'path':local(path),'sha256':digest(path)}


def resolve(path):
    path=Path(path)
    return path if path.is_absolute() else ROOT/path


def clamp(value):
    return max(0,min(1,value))


def smooth(value):
    value=clamp(value)
    return value*value*(3-2*value)


def tick(value):
    return round(smooth(value)*30)


def alpha_intersection(a,b):
    """Compare actual foreground pixels of two independently placed layers."""
    la,oa,ta=a;lb,ob,tb=b
    ba=m.visible(la,ta);bb=m.visible(lb,tb)
    ba=[ba[0]+oa[0],ba[1]+oa[1],ba[2]+oa[0],ba[3]+oa[1]]
    bb=[bb[0]+ob[0],bb[1]+ob[1],bb[2]+ob[0],bb[3]+ob[1]]
    region=(max(ba[0],bb[0]),max(ba[1],bb[1]),min(ba[2],bb[2]),min(ba[3],bb[3]))
    if region[0]>=region[2] or region[1]>=region[3]:
        return None,region
    masks=[]
    for layer,origin,threshold in (a,b):
        masks.append(layer.getchannel('A').point(lambda x:255 if x>=threshold else 0).crop(
            (region[0]-origin[0],region[1]-origin[1],region[2]-origin[0],region[3]-origin[1])))
    return ImageChops.multiply(*masks),region


class Canvas(m.Canvas):
    def clearance(self):
        allowed_inside={'zero-empty-label','schematic-mark','schematic-explanation'}
        actual_contacts=[]
        for i,a in enumerate(self.records):
            for b in self.records[i+1:]:
                ia,ib=a['component_id'],b['component_id']
                if (ia=='square-array' and ib in allowed_inside) or (ib=='square-array' and ia in allowed_inside):
                    continue
                aa,bb=a['visible_box_xyxy'],b['visible_box_xyxy']
                if max(aa[0],bb[0])>=min(aa[2],bb[2]) or max(aa[1],bb[1])>=min(aa[3],bb[3]):
                    continue
                if ia not in self.foreground or ib not in self.foreground:
                    raise ValueError(f'Missing foreground mask: {ia}, {ib}')
                intersection,region=alpha_intersection(self.foreground[ia],self.foreground[ib])
                if intersection is None or not intersection.getbbox():
                    continue
                move=ib if ib.startswith('moving-copy-') else ia if ia.startswith('moving-copy-') else None
                if move and 'working-equation' in (ia,ib):
                    index=int(move.rsplit('-',1)[1])
                    allowed=self.data['multiplication_input_boxes_px'][index]
                    ImageDraw.Draw(intersection).rectangle((math.floor(allowed[0]-region[0]),math.floor(allowed[1]-region[1]),
                                                           math.ceil(allowed[2]-region[0])-1,math.ceil(allowed[3]-region[1])-1),fill=0)
                    if not intersection.getbbox():
                        actual_contacts.append({'moving_component':move,'source_factor':index,'source_box_px':allowed,
                                                'permitted_same_value_source_contact':True})
                        continue
                raise ValueError(f'Actual foreground collision: {a["name"]} / {b["name"]}')
        self.data['foreground_groups_do_not_overlap']=True
        self.data['permitted_source_contacts']=actual_contacts


class Actor:
    def __init__(self,registry=None):
        self.registry_path=resolve(registry) if registry else None
        if self.registry_path:
            data=json.loads(self.registry_path.read_text())
            rows=data.get('poses',data.get('frames'))
            self.poses=rows if isinstance(rows,dict) else {r['id']:r for r in rows}
            common=data.get('reference_height_px',data.get('common_reference_height_px'))
            for ident,row in self.poses.items():
                row.setdefault('reference_height_px',common)
                row.setdefault('id',ident)
            self.registry=receipt(self.registry_path)
        else:
            selection=json.loads((DESIGN/'character-selection.json').read_text())
            self.poses={'neutral':selection['adopted_neutral_reference']}
            self.registry=None
        if 'neutral' not in self.poses:
            raise ValueError('Actor registration must include the exact neutral used for returns')
        self.sources=[];self.source_images={}
        for ident,row in self.poses.items():
            path=resolve(row['path'])
            if digest(path)!=row['sha256']:
                raise ValueError(f'Actor source hash mismatch: {ident}')
            if not row.get('reference_height_px') or not row.get('anchor_px'):
                raise ValueError(f'Actor needs physical scale and support: {ident}')
            self.sources.append({'id':ident,**receipt(path)})
            self.source_images[ident]=Image.open(path).convert('RGBA')

    def choose(self,*candidates):
        return next((p for p in candidates if p in self.poses),'neutral')

    @lru_cache(maxsize=128)
    def sprite(self,pose,height):
        row=self.poses[pose]
        source=self.source_images[pose]
        scale=height/row['reference_height_px']
        image=source.resize((round(source.width*scale),round(source.height*scale)),Image.Resampling.LANCZOS)
        return image,row,scale

    def draw(self,c,pose,foot,height):
        image,row,scale=self.sprite(pose,height)
        xy=tuple(round(a-b*scale) for a,b in zip(foot,row['anchor_px']))
        box=m.visible(image,8)
        bounds=[box[0]+xy[0],box[1]+xy[1],box[2]+xy[0],box[3]+xy[1]]
        if not (24<bounds[0] and 24<bounds[1] and bounds[2]<1896 and bounds[3]<1056):
            raise ValueError(f'Actor leaves screen: {pose}: {bounds}')
        shadow=Image.new('RGBA',SIZE)
        ImageDraw.Draw(shadow).ellipse((foot[0]-100,foot[1]-8,foot[0]+120,foot[1]+12),fill=(46,79,92,22))
        c.image.alpha_composite(shadow)
        c.image.alpha_composite(image,xy)
        c.foreground['character']=(image,xy,8)
        c.records.append({'name':f'{c.scene}/character','component_id':'character','visible_box_xyxy':bounds,
                          'horizontal':'anatomical foot-support x','vertical':'anatomical foot-support y',
                          'not_centering_target':True,'passed':True,'contained':True,'pose':pose})
        c.data['character']={'pose':pose,'path':row['path'],'sha256':row['sha256'],'display_body_height_px':height,
                             'source_reference_height_px':row['reference_height_px'],'source_anchor_px':row['anchor_px'],
                             'ground_foot_anchor_px':list(foot),'scale':scale,'visible_box_xyxy':bounds,
                             'full_actor_crossfade':False,'per_pose_bbox_fit':False,'source_pixels_modified_at_render':False}


@dataclass(frozen=True)
class Frame:
    mode:str
    n:int
    phase:str
    a_tick:int
    b_tick:int
    fill_tick:int
    highlight:str
    completed:int
    lesson_tick:int
    cue:str
    pose:str
    fade:int=0


def prepared_plan(path):
    plan=json.loads(Path(path).read_text())
    events=plan.get('voice_events',plan.get('events'))
    if not events or len(events)!=215:
        raise ValueError('Expected the full 215-event square script')
    plan['voice_events']=events
    plan.setdefault('fps',30)
    plan.setdefault('duration_s',max(x['end_s'] for x in events)+2)
    plan.setdefault('duration_frames',math.ceil(plan['duration_s']*30))
    if 'counted_states' not in plan:
        by={e['id']:e for e in events}
        states=[]
        for n in range(101):
            e,v=by[f'E{n:03d}'],by[f'N{n:03d}']
            states.append({'n':n,'index':n,'value':n*n,'ordinal':n+1,'formula_start_s':e['start_s'],'formula_end_s':e['end_s'],
                           'voice_start_s':v['start_s'],'voice_end_s':v['end_s'],'result_start_s':v['start_s']-.12,
                           'cycle_start_s':e['start_s'],'cycle_end_s':by[f'E{n+1:03d}']['start_s'] if n<100 else plan['duration_s'],
                           'voice_event_id':v['id'],'formula_event_id':e['id']})
        plan['counted_states']=states
    return plan


class Episode:
    def __init__(self,timeline,registry=None,background=None):
        self.timeline_path=Path(timeline)
        self.plan=prepared_plan(timeline)
        self.events=self.plan['voice_events']
        self.by_id={e['id']:e for e in self.events}
        self.starts=[e['start_s'] for e in self.events]
        self.counts=self.plan['counted_states']
        self.count_starts=[c['formula_start_s'] for c in self.counts]
        self.count_ends=[c['voice_end_s'] for c in self.counts]
        self.background_path=resolve(background) if background else m.BG
        self.background=ImageOps.fit(Image.open(self.background_path).convert('RGBA'),SIZE,Image.Resampling.LANCZOS)
        self.actor=Actor(registry)
        self.visual_segments=self.make_visual_segments()
        self.visual_starts=[s['start_frame'] for s in self.visual_segments]
        self.scene_cuts=[s['start_frame'] for i,s in enumerate(self.visual_segments) if i and self.visual_segments[i-1]['mode']!=s['mode']]
        self.motion=self.make_motion()
        self.motion_starts=[w['start_frame'] for w in self.motion]
        self.reports={}
        self.frame_rows=[]
        self.sources=[receipt(self.timeline_path),receipt(self.background_path),receipt(Path(__file__)),receipt(Path(m.__file__)),
                      receipt(m.FONT)]+self.actor.sources

    def make_visual_segments(self):
        segments=[{'mode':'intro','n':0,'cue':'I01','start_frame':0}]
        for n in range(101):
            e=self.by_id[f'E{n:03d}']
            # Full-frame dips take place in existing quiet intervals. The new
            # arrangement is fully visible before its first spoken formula.
            lead=.35 if n in (0,1,5,11,33) else 0
            segments.append({'mode':'count','n':n,'cue':e['id'],'start_frame':math.ceil((e['start_s']-lead)*FPS)})
            teaching=self.by_id.get(f'T{n:03d}')
            if teaching:
                segments.append({'mode':'teaching','n':n,'cue':teaching['id'],
                                 'start_frame':math.ceil((teaching['start_s']-.20)*FPS)})
        outro=self.by_id['O01']
        segments.append({'mode':'outro','n':100,'cue':'O01','start_frame':math.ceil((outro['start_s']-.20)*FPS)})
        segments.sort(key=lambda s:s['start_frame'])
        for i,s in enumerate(segments):
            s['end_frame']=segments[i+1]['start_frame'] if i+1<len(segments) else self.plan['duration_frames']
        return segments

    def make_motion(self):
        windows=[]
        a=self.actor
        def add(ident,cue,edge,offset,poses,lengths,reason):
            event=self.by_id.get(cue)
            if not event:
                return
            start=math.ceil((event[edge]+offset)*FPS)
            keys=[];cursor=start
            for pose,length in zip(poses,lengths):
                keys.append({'at_frame':cursor,'pose':pose,'hold_frames':length})
                cursor+=length
            windows.append({'id':ident,'source_cue':cue,'source_edge':edge,'offset_s':offset,'start_frame':start,
                            'end_frame':cursor,'keyframes':keys,'reason':reason,'interpolation':'held registered drawing',
                            'full_actor_crossfade':False})
        wave=[a.choose('wave_prepare'),a.choose('wave_half','wave_mid'),a.choose('wave_in'),a.choose('wave_out'),
              a.choose('wave_in'),a.choose('wave_out'),a.choose('wave_half','wave_mid'),a.choose('wave_prepare'),'neutral']
        add('opening-greeting','I01','start_s',.1,wave,[5,5,6,7,7,7,5,5,5],
            'Raise one forepaw, two outward-and-return gestures, then lower into the identical neutral.')
        add('closing-greeting','O01','start_s',.1,wave,[5,5,6,7,7,7,5,5,5],
            'A closing farewell with the same grounded body and an explicit neutral return.')
        # These actions fit the already-designed two-second post-result pause.
        # They never add time or change the count cadence.
        for n in (7,18,43,66,88):
            add(f'notice-{n:03d}',f'N{n:03d}','end_s',.10,
                [a.choose('gaze_front','neutral'),a.choose('gaze_up','gaze_up_left','watch_up'),a.choose('gaze_left','watch_left'),
                 a.choose('gaze_up','gaze_up_left','watch_up'),a.choose('gaze_front','neutral')],[5,10,12,10,5],
                'Follow the completed square with eyes and return; no body jump or new count.')
        for n in (25,52,78):
            add(f'shoulder-stretch-{n:03d}',f'N{n:03d}','end_s',.08,
                [a.choose('stretch_prepare'),a.choose('stretch_half'),a.choose('stretch_full_look','stretch_full'),
                 a.choose('stretch_return','stretch_half'),a.choose('stretch_prepare'),'neutral'],[5,7,12,9,7,5],
                'Open one forearm to loosen its shoulder during an existing gap; the canonical right arm, tail, torso and feet stay fixed.')
        for n in (12,35,58,82,96):
            add(f'show-dimensions-{n:03d}',f'N{n:03d}','end_s',.1,
                [a.choose('trace_prepare_look','trace_prepare'),a.choose('trace_half_look','trace_half','trace_horizontal_half'),
                 a.choose('trace_extend_look','trace_extend','trace_horizontal_full'),a.choose('trace_half_look','trace_half','trace_horizontal_half'),
                 a.choose('trace_prepare_look','trace_prepare'),'neutral'],[5,7,12,7,5,5],
                'One outward-and-return forepaw indication of the square; result reading is already complete.')
        windows.sort(key=lambda w:w['start_frame'])
        for left,right in zip(windows,windows[1:]):
            if left['end_frame']>right['start_frame']:
                raise ValueError(f'Actor windows overlap: {left["id"]}, {right["id"]}')
        for w in windows:
            if w['source_cue'].startswith('N'):
                n=int(w['source_cue'][1:])
                next_start=self.by_id[f'E{n+1:03d}']['start_s']*FPS
                if w['end_frame']>next_start:
                    raise ValueError(f'Actor leaves the ordinary gap: {w["id"]}')
        return windows

    def pose(self,frame,mode,n,phase):
        index=bisect_right(self.motion_starts,frame)-1
        if index>=0:
            w=self.motion[index]
            if frame<w['end_frame']:
                key=next(k for k in reversed(w['keyframes']) if frame>=k['at_frame'])
                return key['pose']
        if mode=='teaching':
            return self.actor.choose('trace_extend_look','trace_extend','trace_horizontal_full') if n in (4,10) else self.actor.choose('trace_up_look','trace_up','gaze_up','watch_up') if n==32 else 'neutral'
        if mode=='count' and phase in ('travel','fill'):
            return self.actor.choose('gaze_up','gaze_up_left','watch_up')
        return 'neutral'

    def state(self,frame):
        t=frame/FPS
        completed=bisect_right(self.count_ends,t)
        ei=max(0,bisect_right(self.starts,t)-1)
        event=self.events[ei]
        segment=self.visual_segments[max(0,bisect_right(self.visual_starts,frame)-1)]
        mode=segment['mode'];n=segment['n']
        cue=event['id'] if mode=='intro' else segment['cue']
        if mode=='count':
            cue=f'N{n:03d}' if t>=self.by_id[f'N{n:03d}']['start_s'] else f'E{n:03d}'
        phase='input';at=bt=ft=lt=0;highlight='first'
        if mode=='intro':
            mode='intro';phase='intro';n=0;lt=tick((t-event['start_s'])/max(.01,event['duration_s']))
        elif mode=='teaching':
            event=self.by_id[cue]
            mode='teaching';n=int(cue[1:]);phase='teaching'
            lt=tick((t-event['start_s'])/max(.01,event['duration_s']))
        elif mode=='outro':
            event=self.by_id[cue]
            mode='outro';n=100;phase='outro';lt=tick((t-event['start_s'])/max(.01,event['duration_s']))
        else:
            count=self.counts[n]
            e=self.by_id[f'E{n:03d}']
            h=e.get('highlight_timing',{})
            start,end=e['start_s'],e['end_s'];duration=end-start
            times=h.get('times_start_s',start+duration*.27)
            second=h.get('b_start_s',start+duration*.50)
            equals=h.get('equals_start_s',start+duration*.77)
            if not (start<=times<=second<=equals<=end+.05):
                raise ValueError(f'Invalid E highlight order: {e["id"]}: {h}')
            commit=count.get('result_start_s',count['voice_start_s']-.12)
            if t>=commit:
                phase='result';at=bt=ft=30;highlight='result'
            else:
                at=tick((t-start-.04)/max(.20,second-start-.04))
                bt=tick((t-second)/max(.20,equals-second+.05))
                ft=tick((t-equals)/max(.04,commit-equals))
                phase='fill' if ft else 'travel' if at or bt else 'input'
                highlight='first' if t<times else 'times' if t<second else 'second' if t<equals else 'equals'
        fade=round((1-clamp(frame/18))*255) if frame<18 else round(clamp((frame-(self.plan['duration_frames']-30))/29)*255)
        for cut in self.scene_cuts:
            if abs(frame-cut)<=5:
                fade=max(fade,round((1-abs(frame-cut)/5)*255))
        pose=self.pose(frame,mode,n,phase)
        return Frame(mode,n,phase,at,bt,ft,highlight,completed,lt,cue,pose,fade)

    @lru_cache(maxsize=8)
    def image(self,state):
        ident=hashlib.sha256(json.dumps(asdict(state),sort_keys=True).encode()).hexdigest()[:20]
        c=Canvas(self.background,ident)
        m.header(c,'NUM-NUM NUMBERS · THE FROZEN LAKE')
        if state.mode=='intro':
            self.intro(c,state)
            foot,height=(960,1007),260
        elif state.mode=='outro':
            self.outro(c,state)
            foot,height=(960,1010),260
        elif state.mode=='teaching':
            self.teaching(c,state)
            foot,height=((1530,1007),310) if state.n==4 else ((1590,1007),300) if state.n==32 else ((425,1007),320) if state.n==100 else ((1460,1007),280)
        else:
            self.count(c,state)
            foot,height=(1460,1007),280
        c.text(f'Squares counted: {state.completed} / 101',PROGRESS_BOX,24,m.MUTED,'completed-progress')
        c.data.update(completed_count=state.completed,progress_update_rule='N result speech END only',state=asdict(state))
        self.actor.draw(c,state.pose,foot,height)
        c.clearance()
        image=c.image
        if state.fade:
            image=Image.blend(image,Image.new('RGBA',SIZE,'#fffaf0'),state.fade/255)
        report={'state_id':ident,'state':asdict(state),'components':c.records,'scene_data':c.data,
                'intentional_absences':c.absent,'native_tolerance_px':.5,
                'all_centered_components_pass':all(r['passed'] for r in c.records),
                'all_foreground_clearance_pass':True,'whole_frame_fade':bool(state.fade),
                'decoded_alignment_applicable':not bool(state.fade),
                'decoded_alignment_exclusion_reason':'whole-frame scene dip or bookend fade; underlying native layout remains measured' if state.fade else None}
        self.reports[ident]=report
        return image.convert('RGB'),ident

    def formula(self,c,n,show_result,highlight):
        c.panel((240,178,1680,310),fill='#fffaf0',outline='#d8d1be')
        result=f'{n*n:,}' if show_result else '?'
        pieces=[f'{n}²',' = ',str(n),' × ',str(n),' = ',result]
        full=''.join(pieces)
        f=m.font(82);b=f.getbbox(full)
        layer=Image.new('RGBA',(b[2]-b[0]+40,b[3]-b[1]+40));d=ImageDraw.Draw(layer)
        active={'first':2,'times':3,'second':4,'equals':5,'result':6}.get(highlight)
        prefix='';factor_masks=[]
        for i,piece in enumerate(pieces):
            color=m.GOLD if i==active and i==6 else m.TEAL if i==active else m.INK
            draw_xy=(20-b[0]+f.getlength(prefix),20-b[1])
            d.text(draw_xy,piece,font=f,fill=color)
            if i in (2,4):
                # Render the same factor, at the exact same local raster
                # position. Its actual ink bearing is not the font advance
                # box's left edge (notably for the digit 1).
                token=Image.new('RGBA',layer.size)
                ImageDraw.Draw(token).text(draw_xy,piece,font=f,fill=color)
                factor_masks.append(token)
            prefix+=piece
        c.center(layer,FORMULA_BOX,'working-equation')
        rec=c.records[-1];rec.update(text=full,font_size_px=82,token_highlight=highlight)
        origin=rec['measurement_origin_px']
        boxes=[]
        for i,token in enumerate(factor_masks):
            ink=m.visible(token,128)
            if not ink:
                raise ValueError(f'Empty actual factor ink: {n}, {i}')
            boxes.append([ink[0]+origin[0],ink[1]+origin[1],ink[2]+origin[0],ink[3]+origin[1]])
            c.foreground[f'factor-source-{i}']=(token,tuple(origin),128)
        c.data.update(n=n,value=n*n,operands=[n,n],equation=full,result_committed=show_result,
                      multiplication_input_boxes_px=boxes,multiplication_input_centers_px=[[(q[0]+q[2])/2,(q[1]+q[3])/2] for q in boxes],
                      multiplication_source_measurement='individual actual operand ink masks drawn at exactly the same local position as the formula; actual layer-placement origin',
                      formula_highlight=highlight,equation_font_px=82)

    def count(self,c,s):
        n=s.n;show=s.phase=='result'
        self.formula(c,n,show,s.highlight)
        m.diagram(c,n,s.fill_tick/30,side_labels=False)
        self.measure_actual_fill(c,n,s.fill_tick/30)
        for i,p in enumerate((s.a_tick/30,s.b_tick/30)):
            if p==0 and not show:
                c.absent.append({'id':f'moving-copy-{i}','reason':'this factor has not begun its axis transfer'})
                continue
            startx,starty=c.data['multiplication_input_centers_px'][i]
            if i==0:
                x,y=(startx,starty+(351-starty)*p/.2) if p<.2 else (startx+(960-startx)*(p-.2)/.8,351)
            elif p<.30:
                x,y=startx,starty+(300-starty)*p/.30
            elif p<.70:
                x,y=startx+(632-startx)*(p-.30)/.40,300
            else:
                x,y=632,300+(641-300)*(p-.70)/.30
            color=m.TEAL if i==0 else m.BLUE
            if p==1:
                c.text(str(n),(850,331,1070,375) if i==0 else (592,606,672,676),35,color,'horizontal-side' if i==0 else 'vertical-side')
            else:
                c.text(str(n),(x-75,y-29,x+75,y+29),35,color,f'moving-copy-{i}')
        if show:
            c.text(m.words(n*n),READING_BOX,35,m.INK,'natural-reading')
        else:
            c.text('Equal width. Equal height. One square.',READING_BOX,31,m.TEAL,'generation-caption')

    def measure_actual_fill(self,c,n,progress):
        """Measure counted fill itself; the surrounding square is excluded."""
        layer,origin,_=c.foreground['square-array']
        color='#75bdc8' if n<=10 else '#9acbd4'
        diff=ImageChops.difference(layer.convert('RGB'),Image.new('RGB',layer.size,color))
        channels=diff.split()
        mask=ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),channels[2]).point(lambda z:255 if z==0 else 0)
        mask=ImageChops.multiply(mask,layer.getchannel('A').point(lambda z:255 if z>=128 else 0))
        box=mask.getbbox()
        rows=math.floor(n*progress+1e-9) if n<=10 else None
        expected_absent=n==0 or (n<=10 and rows==0) or (n>10 and progress==0)
        if expected_absent:
            if box is not None:
                raise ValueError('Unexpected lit fill before its generation stage')
            c.data['actual_fill_alignment']={'status':'intentionally absent','reason':'zero square or no row/area lit yet',
                                             'parent_outline_excluded':True,'empty_target_not_counted_as_pass':True}
            return
        if box is None:
            raise ValueError('Expected lit fill is empty')
        absolute=[box[0]+origin[0],box[1]+origin[1],box[2]+origin[0],box[3]+origin[1]]
        target_top=404 if n<=10 else 406
        dx=(absolute[0]+absolute[2])/2-960
        dy=absolute[1]-target_top
        contained=720<=absolute[0] and 402<=absolute[1] and absolute[2]<=1200 and absolute[3]<=882
        passed=abs(dx)<=.5 and abs(dy)<=.5 and contained
        check={'status':'measured','visible_box_xyxy':absolute,'content_box_xyxy':list(m.GRID_BOX),
               'horizontal':'center','vertical':'top','target_center_x':960,'target_top_y':target_top,
               'delta_x_px':dx,'delta_y_px':dy,'tolerance_px':.5,'contained':contained,'passed':passed,
               'counted_lit_rows':rows,'parent_outline_excluded':True,'extraction':'exact counted fill color AND alpha>=128'}
        if not passed:
            raise ValueError(check)
        c.data['actual_fill_alignment']=check

    def intro(self,c,s):
        c.panel((240,178,1680,310),fill='#fffaf0',outline='#d8d1be')
        c.text('n² = n × n',FORMULA_BOX,82,m.INK,'general-rule')
        c.panel((800,359,1120,679),fill='#f1fbfb',outline='#86afb9',radius=12)
        c.text('n',(880,324,1040,354),30,m.TEAL,'intro-width')
        c.text('n',(735,475,790,555),30,m.BLUE,'intro-height')
        lines={
            'I01':(['Hello!','Let’s make square numbers.'],['One matching pair.','One square.']),
            'I02':(['The same number','across …'],['… and down.','Both sides match.']),
            'I03':(['The little 2','means squared.'],['n × n','A number times itself.']),
            'I04':(['Move the numbers.','Set both sides.'],['Watch the square','take shape.']),
            'I05':(['Start with n = 0.'],['Continue to n = 100.']),
            'I06':(['One matching pair.'],['One new result.']),
            'I07':(['Ready?'],['Let’s see what it makes.'])}
        left,right=lines.get(s.cue,lines['I07'])
        c.multiline(left,(135,430,695,595),32,m.TEAL,'intro-left-prompt')
        c.multiline(right,(1225,430,1795,595),32,m.TEAL,'intro-right-prompt')
        if s.cue=='I03':
            c.text('SQUARED',(820,480,1100,555),35,m.GOLD,'intro-squared')
        else:
            c.text('SQUARE',(820,480,1100,555),35,m.MUTED,'intro-square-plane')
        c.data.update(general_formula='n² = n × n',intro_cue=s.cue,no_endpoint_result_revealed=True)

    def teaching(self,c,s):
        n=s.n
        if n==4:
            self.l_shape(c,s)
        elif n==32:
            self.area(c,s)
        else:
            self.formula(c,n,True,'result')
            m.diagram(c,n,1,block=n==100)
            if n==10:
                c.multiline(['Ten by ten: 100 unit tiles.','Bigger squares use a labelled diagram.'],(210,916,1320,998),28,m.TEAL,'teaching-caption')
            else:
                text='No unit tiles. Zero times zero is zero.' if n==0 else '100 blocks. Each block contains 100 unit squares.'
                c.text(text,READING_BOX if n==0 else (640,922,1680,977),28,m.TEAL,'teaching-caption')
        c.data.update(teaching_index=n,count_advanced=False,teaching_progress_tick=s.lesson_tick)

    def l_shape(self,c,s):
        c.panel((240,178,1680,310),fill='#fffaf0',outline='#d8d1be')
        c.text('4² + (4 + 4 + 1) = 5²',FORMULA_BOX,78,m.INK,'l-growth-equation')
        p=s.lesson_tick/30
        layer=Image.new('RGBA',(520,520));d=ImageDraw.Draw(layer)
        d.rectangle((20,20,499,499),fill='#f1fbfb',outline='#86afb9',width=2)
        old=new=corner=0
        for row in range(5):
            for col in range(5):
                is_old=row<4 and col<4
                is_corner=row==col==4
                lit=is_old or row==4 and col<4 and p>=.25 or col==4 and row<4 and p>=.52 or is_corner and p>=.78
                if not lit:
                    continue
                fill='#96c8d1' if is_old else '#f4cf90' if is_corner else '#e5aa6f'
                x,y=20+col*96,20+row*96
                d.rectangle((x+2,y+2,x+93,y+93),fill=fill)
                old+=is_old;new+=not is_old;corner+=is_corner
        c.center(layer,m.GRID_BOX,'square-array')
        c.text('LOOK AHEAD',(840,335,1080,378),26,m.GOLD,'look-ahead-mode')
        c.panel((125,421,610,651),fill='#fff7e8',radius=20)
        lines=['16 old tiles','+ 4 in a row'] if p<.52 else ['16 old tiles','+ 4 + 4'] if p<.78 else ['16 old tiles','+ 4 + 4 + 1','9 new tiles']
        c.multiline(lines,(145,442,590,630),35,m.GOLD,'l-count-explanation')
        c.text('Four in a row. Four in a column. One corner.',(190,925,1330,977),30,m.TEAL,'l-no-early-answer')
        c.data.update(old_quantity=old,new_quantity=new,corner_quantity=corner,result_25_revealed=False,
                      diagram_kind='16 retained cells; four row, four column, one corner added without overlap')

    def area(self,c,s):
        self.formula(c,32,True,'result')
        x,y,split,side=720,402,450,480
        c.draw.rectangle((x,y,x+split-1,y+split-1),fill='#92c6cf')
        c.draw.rectangle((x+split,y,x+side-1,y+split-1),fill='#e3b179')
        c.draw.rectangle((x,y+split,x+split-1,y+side-1),fill='#e3b179')
        c.draw.rectangle((x+split,y+split,x+side-1,y+side-1),fill='#f3d692')
        c.draw.rectangle((x,y,x+side-1,y+side-1),outline=m.TEAL,width=2)
        c.text('900',(x+15,y+20,x+split-15,y+split-20),78,m.INK,'area-900')
        c.draw.line((1196,627,1223,627,1243,532),fill=m.GOLD,width=3)
        c.text('60',(1248,500,1408,565),42,m.GOLD,'area-60-right')
        c.draw.line((945,877,945,902,1281,902,1281,875),fill=m.GOLD,width=3)
        c.text('60',(1225,812,1345,874),42,m.GOLD,'area-60-bottom')
        c.draw.line((1197,867,1212,867,1212,727,1230,727),fill=m.INK,width=3)
        c.text('4',(1235,695,1335,760),42,m.INK,'area-4')
        c.text('30',(735,341,1155,381),32,m.TEAL,'top-thirty')
        c.text('2',(1170,341,1200,381),30,m.GOLD,'top-two')
        c.text('30',(650,422,704,832),30,m.BLUE,'left-thirty')
        c.text('2',(650,852,704,882),30,m.GOLD,'left-two')
        c.panel((125,420,635,654),fill='#fff7e8',radius=20)
        c.multiline(['REPLAY: 31² = 961','32 = 30 + 2','900 + 60 + 60 + 4'],(145,443,615,630),30,m.GOLD,'area-decomposition-key')
        c.text('one thousand twenty-four',READING_BOX,35,m.INK,'natural-reading')
        c.data.update(area_parts=[900,60,60,4],area_sum=1024,split_side_units=[30,2],diagram_kind='exact area split')

    def outro(self,c,s):
        c.panel((240,178,1680,310),fill='#fffaf0',outline='#d8d1be')
        c.text('n² = n × n',FORMULA_BOX,82,m.INK,'general-rule')
        c.text('0, 1, 4, 9, 16, 25, 36, 49, 64, 81, 100, …',(180,369,1740,440),52,m.TEAL,'sequence-beginning')
        c.text('…, 9,604, 9,801, 10,000',(310,511,1610,595),65,m.INK,'sequence-ending')
        c.text('101 terms counted. The rule keeps going.',(280,653,1640,715),39,m.GOLD,'finale-total')
        c.data.update(first_values=[0,1,4,9,16,25,36,49,64,81,100],last_values=[9604,9801,10000],total_terms=101)

    def write_design(self):
        MOTION.mkdir(parents=True,exist_ok=True)
        (MOTION/'character-motion.json').write_text(json.dumps({'schema_version':1,'fps':FPS,'windows':self.motion,
            'registry':self.actor.registry,'full_actor_crossfade':False,'source_art_modified_at_render':False,
            'scale_policy':'same physical standing reference within each registered family; no pose-specific bbox fit',
            'scene_scale_transitions':{'kind':'opaque cream dip, never actor-to-actor dissolve','half_duration_frames':5,'cut_frames':self.scene_cuts,
                                       'visual_segments':self.visual_segments}},ensure_ascii=False,indent=2)+'\n')
        spec={'schema_version':1,'fps':FPS,'resolution_px':list(SIZE),'formula':{'content_box':FORMULA_BOX,'font_px':82,'font':local(m.FONT),
              'text':'n² = n × n = ? until N.start−0.12, then n² = n × n = decimal n*n','normal_color':m.INK,'active_color':m.TEAL,'result_active_color':m.GOLD,
              'measurement':'whole visible glyph group; per-factor glyph source boxes also recorded'},
              'reading':{'content_box':READING_BOX,'font_px':35,'color':m.INK,'visible_from':'N.start_s−0.12'},
              'progress':{'content_box':PROGRESS_BOX,'font_px':24,'text':'Squares counted: k / 101','k':'number of N events whose end_s <= frame/30'},
              'diagram':{'box':m.GRID_BOX,'small_unit_grid_n':[1,10],'empty_n':0,'schematic_n':[11,100],
                         'schematic_note':'n>10 normal count is ungridded and labelled; n100 teaching replaces it with 100 exact grouped blocks',
                         'palette':{'unlit':'#c7e2e9','lit':'#75bdc8','schematic_fill':'#9acbd4'}},
              'count_timing':{'highlight':'first factor until E.times_start; × until E.b_start; second factor until E.equals_start; = until result commit',
                              'token_a':'smoothstep((t−E.start−.04)/(E.b_start−E.start−.04)) quantized to 30 ticks',
                              'token_b':'smoothstep((t−E.b_start)/(E.equals_start−E.b_start+.05)) quantized to 30 ticks',
                              'fill':'smoothstep((t−E.equals_start)/(N.start−.12−E.equals_start)) quantized to 30 ticks',
                              'highlight_fallback':'27%,50%,77% of E duration only when measured alignment absent; source method retained in timeline',
                              'result_hold':'formula, reading and grid are unchanged from commit through N.end and normal pause'},
              'token_paths':{'font_px':35,'source':'actual factor glyph center in rendered formula',
                             'a':'down at source x to y351 in first20%; then right/left to x960,y351',
                             'b':'down at source x to y300 in first30%; horizontal to x632 by70%; down to x632,y641',
                             'source_contact_exception':'only actual same-factor glyph-mask overlap; no symbol overlap',
                             'arrival':'copy becomes side label; no duplicate side label during transit'},
              'teaching_modes':{'T004':'L shape:16 + row4 + col4 + corner1; reveal fractions .25/.52/.78; no25 text',
                                'T032':'32=30+2, geometric lengths450px+30px, areas900/60/60/4; 42px external callouts',
                                'T100':'10×10 counted blocks; one same-block magnified10×10 unit grid is a legend and adds zero to total'},
              'actor':{'registry':self.actor.registry,'count':{'foot':[1460,1007],'body_height':280},
                       'intro':{'foot':[960,1007],'body_height':260},'outro':{'foot':[960,1010],'body_height':260},
                       'T004':{'foot':[1530,1007],'body_height':310},'T032':{'foot':[1590,1007],'body_height':300},
                       'T100':{'foot':[425,1007],'body_height':320}},
              'scene_transitions':{'kind':'whole-frame dip to opaque cream','half_duration_frames':5,'cut_frames':self.scene_cuts,
                                   'visual_segments':self.visual_segments,'rule':'new composition at fully opaque cut; dip finishes before its E/T/O speech',
                                   'production_duration_or_audio_changed':False,'actor_to_actor_crossfade':False},
              'sources':self.sources,'finished_video_qa':'independent decoded-frame verifier; native layer metrics are separate evidence'}
        (MOTION/'layout-spec.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n')

    def native_all_frames(self):
        rows=[]
        for frame in range(self.plan['duration_frames']):
            state=self.state(frame)
            _,ident=self.image(state)
            rows.append({'frame':frame,'time_s':frame/FPS,'state_id':ident,'n':state.n,'mode':state.mode,'phase':state.phase,
                         'completed':state.completed,'pose':state.pose,'cue':state.cue})
        self.frame_rows=rows
        return self.write_native_report(rows)

    def write_native_report(self,rows):
        centered=[c for r in self.reports.values() for c in r['components'] if not c.get('not_centering_target')]
        qa_root=MOTION/'qa'/f'{digest(self.timeline_path)[:12]}-{self.actor.registry["sha256"][:12] if self.actor.registry else "neutral"}-{digest(Path(__file__))[:12]}'
        qa_root.mkdir(parents=True,exist_ok=True)
        states_path=qa_root/'native-states.json.gz'
        states_path.write_bytes(gzip.compress(json.dumps({'states':self.reports},ensure_ascii=False,separators=(',',':')).encode(),compresslevel=6))
        frames_path=qa_root/'frame-plan.json.gz'
        frames_path.write_bytes(gzip.compress(json.dumps({'fps':FPS,'frames':rows},ensure_ascii=False,separators=(',',':')).encode(),compresslevel=6))
        voice_fades=[{'frame':r['frame'],'cue':e['id']} for r in rows if self.reports[r['state_id']]['state']['fade']
                     for e in self.events if e['id'].startswith(('E','N')) and e['start_s']<=r['time_s']<e['end_s']]
        fills=[r['scene_data']['actual_fill_alignment'] for r in self.reports.values() if r['scene_data'].get('actual_fill_alignment',{}).get('status')=='measured']
        report={'kind':'square-production-native-layout-check','source_timeline':receipt(self.timeline_path),
                'renderer':receipt(Path(__file__)),'frame_count':len(rows),'distinct_state_count':len(self.reports),
                'centered_component_observations':len(centered),'max_abs_dx_px':max(abs(c['delta_x_px']) for c in centered),
                'max_abs_dy_px':max(abs(c['delta_y_px']) for c in centered),'all_components_pass':all(c['passed'] for c in centered),
                'all_foreground_clearance_pass':True,'independent_decoded_video_qa':False,'sources':self.sources,
                'actual_fill_observations':len(fills),'actual_fill_all_pass':all(f['passed'] for f in fills),
                'E_N_voice_fade_intersections':voice_fades,'final_frame_full_cream':self.state(self.plan['duration_frames']-1).fade==255,
                'state_records':receipt(states_path),'frame_records':receipt(frames_path),
                'record_format':'gzip-compressed complete UTF-8 JSON; lossless full state/frame records',
                'fade_scope':'native underlying layouts checked; decoded alignment excludes declared whole-frame dips and bookend fades'}
        if voice_fades:
            raise ValueError('A scene dip overlaps formula/result speech')
        (MOTION/'native-layout-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        (qa_root/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        return {k:v for k,v in report.items() if k not in ('sources',)}


def ffbin(name):
    candidate=ROOT/'.venv/bin'/name
    return str(candidate) if candidate.exists() else shutil.which(name)


def preview(episode,out_dir):
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    samples=[]
    for cue in ('I01','I03','E000','N000','E004','N004','T004','N010','T010','N032','T032','N061','N100','T100','O01'):
        e=episode.by_id[cue]
        t=e['start_s']+min(.6,e['duration_s']/2)
        frame=round(t*FPS);state=episode.state(frame);im,ident=episode.image(state)
        path=out_dir/f'{cue}-{frame:06d}.png';im.save(path)
        samples.append({'cue':cue,'time_s':frame/FPS,'state_id':ident,**receipt(path)})
    (out_dir/'preview-manifest.json').write_text(json.dumps({'production_video_generated':False,'timeline':receipt(episode.timeline_path),
        'registry':episode.actor.registry,'samples':samples},ensure_ascii=False,indent=2)+'\n')
    return samples


def motion_preview(episode,out_dir):
    """Six unretimed two-second extracts, including complete actor returns."""
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    picks=[]
    for prefix in ('opening-greeting','show-dimensions','shoulder-stretch','notice'):
        window=next(w for w in episode.motion if w['id'].startswith(prefix))
        picks.append((window['id'],max(0,window['start_frame']-3)))
    picks.append(('teaching-L',round((episode.by_id['T004']['start_s']+2.2)*FPS)))
    closing=next(w for w in episode.motion if w['id']=='closing-greeting')
    picks.append(('closing-greeting',closing['start_frame']-3))
    destination=out_dir/'acting-and-math-review.mp4'
    with (out_dir/'acting-preview-ffmpeg.log').open('wb') as log:
        proc=subprocess.Popen([ffbin('ffmpeg'),'-y','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','-',
                               '-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(destination)],
                              stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
        for label,start in picks:
            for k in range(60):
                im,_=episode.image(episode.state(start+k))
                proc.stdin.write(im.tobytes())
        proc.stdin.close()
        if proc.wait():
            raise RuntimeError('Actor preview encode failed')
    (out_dir/'acting-preview-manifest.json').write_text(json.dumps({'video':receipt(destination),'duration_s':12,
        'production_video':False,'audio_present':False,'registry':episode.actor.registry,'source_timeline':receipt(episode.timeline_path),
        'extracts':[{'id':label,'source_start_frame':start,'source_end_frame_exclusive':start+60,'output_start_frame':i*60} for i,(label,start) in enumerate(picks)]},ensure_ascii=False,indent=2)+'\n')
    return receipt(destination)


def encode(episode,out_dir):
    out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    destination=out_dir/VIDEO_NAME
    if destination.exists():
        raise FileExistsError(f'Preserve the existing render and choose a fresh output directory: {destination}')
    audio=episode.plan.get('master_audio')
    if not audio:
        raise ValueError('Measured master_audio is required for the production render')
    if not episode.actor.registry:
        raise ValueError('Registered production acting is required; neutral fallback is preview-only')
    audio_path=resolve(audio['path'] if isinstance(audio,dict) else audio)
    if isinstance(audio,dict) and digest(audio_path)!=audio['sha256']:
        raise ValueError('Master audio hash mismatch')
    duration=episode.plan['duration_frames']/FPS
    command=[ffbin('ffmpeg'),'-y','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r',str(FPS),'-i','-',
             '-i',str(audio_path),'-map','0:v:0','-map','1:a:0','-frames:v',str(episode.plan['duration_frames']),
             '-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-profile:v','high',
             '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv',
             '-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-af',f'apad=whole_dur={duration:.9f}',
             '-t',f'{duration:.9f}','-movflags','+faststart',str(destination)]
    frame_rows=[]
    with (out_dir/'render-ffmpeg.log').open('wb') as log:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
        last_state=None;raw=None
        try:
            for frame in range(episode.plan['duration_frames']):
                state=episode.state(frame)
                if state!=last_state:
                    im,ident=episode.image(state);raw=im.tobytes();last_state=state
                process.stdin.write(raw)
                frame_rows.append({'frame':frame,'time_s':frame/FPS,'state_id':ident,'n':state.n,'mode':state.mode,
                                   'phase':state.phase,'completed':state.completed,'pose':state.pose,'cue':state.cue})
                if frame%(FPS*30)==0:
                    print(json.dumps({'rendered_frame':frame,'total_frames':episode.plan['duration_frames'],'time_s':frame/FPS}),flush=True)
        finally:
            process.stdin.close()
        if process.wait():
            raise RuntimeError('Production encoding failed; inspect render-ffmpeg.log')
    episode.frame_rows=frame_rows
    native=episode.write_native_report(frame_rows)
    (out_dir/'frame-plan.json').write_text(json.dumps({'fps':FPS,'duration_frames':len(frame_rows),'frames':frame_rows},ensure_ascii=False,separators=(',',':'))+'\n')
    (out_dir/'native-layout-verification.json').write_text(json.dumps(native,ensure_ascii=False,indent=2)+'\n')
    for source in episode.sources:
        if digest(resolve(source['path']))!=source['sha256']:
            raise ValueError(f'Source changed during production encode: {source["path"]}')
    result={'video':receipt(destination),'source_timeline':receipt(episode.timeline_path),'master_audio':receipt(audio_path),
            'frame_count':len(frame_rows),'duration_s':len(frame_rows)/FPS,'registry':episode.actor.registry,
            'native_distinct_states':len(episode.reports),'independent_final_decode_qa':'pending separate verifier'}
    (out_dir/'render-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--timeline',type=Path,required=True)
    p.add_argument('--registry',type=Path)
    p.add_argument('--background',type=Path)
    p.add_argument('--out-dir',type=Path,default=ROOT/'output/square-counting-001-v001')
    p.add_argument('--preview-only',action='store_true')
    p.add_argument('--check-all-frames',action='store_true')
    p.add_argument('--motion-preview',action='store_true')
    args=p.parse_args()
    episode=Episode(args.timeline,args.registry,args.background)
    episode.write_design()
    preview(episode,args.out_dir/'preview')
    if args.motion_preview:
        print(json.dumps(motion_preview(episode,args.out_dir/'preview'),ensure_ascii=False))
    if args.check_all_frames:
        print(json.dumps(episode.native_all_frames(),ensure_ascii=False,indent=2))
    if not args.preview_only:
        print(json.dumps(encode(episode,args.out_dir),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
