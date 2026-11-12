"""Render the arithmetic sequence from measured speech and explicit value flow.

The previous answer's actual glyph raster travels to the input column. Exactly
three addend counters enter the equation, then an atomic result appears before
its spoken number. Replays are visibly labelled and never advance progress.
Native raster measurements and the complete frame plan are retained separately
from independent checks of the encoded, decoded movie.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import asdict, dataclass
from functools import lru_cache
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

from PIL import Image, ImageChops, ImageDraw, ImageOps

try:
    import render_arithmetic_mockups as m
    from component_alignment import raster_centering_report
except ModuleNotFoundError:
    from tools import render_arithmetic_mockups as m
    from tools.component_alignment import raster_centering_report

ROOT=m.ROOT
DESIGN=ROOT/'design/arithmetic-sequence-counting-v1/production-v001/render'
OUTPUT=ROOT/'output/arithmetic-sequence-counting-001-v001'
FPS=30
SIZE=(1920,1080)
VIDEO_NAME='paspla-studio-arithmetic-sequence-2-to-302-1080p.mp4'
INPUT_BOX=(430,205,700,305)
ADDEND_BOX=(740,205,990,305)
EQUALS_BOX=(1030,205,1120,305)
EQUATION_RESULT_BOX=(1160,205,1480,305)
RESULT_BOX=(630,395,1290,560)
READING_BOX=(300,605,1620,655)
PROGRESS_BOX=(500,1033,1420,1063)
RECENT_BOX=(420,680,1500,722)
TERM_BOX=(1450,345,1740,395)
GENERAL_BOX=(300,208,1620,313)
REPLAY_RESULT_BOX=(1110,791,1530,951)
INK,TEAL,GOLD,PALE,MUTED=m.INK,m.TEAL,m.GOLD,m.PALE,m.MUTED


def resolve(path):
    path=Path(path)
    return path if path.is_absolute() else ROOT/path


def local(path):
    return str(Path(path).resolve().relative_to(ROOT))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def receipt(path):
    return {'path':local(path),'sha256':sha(path)}


def ffbin(name):
    candidate=ROOT/'.venv/bin'/name
    return str(candidate) if candidate.exists() else shutil.which(name)


def clamp(v):
    return max(0.,min(1.,v))


def smooth(v):
    v=clamp(v)
    return v*v*(3-2*v)


def tick(v,steps=60):
    return round(clamp(v)*steps)


def lerp(a,b,p):
    return a+(b-a)*p


def center(box):
    return ((box[0]+box[2])/2,(box[1]+box[3])/2)


@lru_cache(maxsize=512)
def glyphs(text,size,color=INK):
    return m.glyphs(text,size,color)


@lru_cache(maxsize=96)
def indexed(tail,size,index='n'):
    return m.indexed_formula(tail,size,index)


def indexed_operand_slot(n,size=65):
    """Leave the actual decimal n operand empty, retaining its exact width."""
    tail=f' = 2 + ({n} − 1) × 3';prefix=' = 2 + ('
    lead=glyphs('a',size);sub=glyphs(str(n),round(size*.52),TEAL);rest=glyphs(tail,size)
    bl,bs,br=[m.bbox(x) for x in (lead,sub,rest)]
    wl,ws,wr=[b[2]-b[0] for b in (bl,bs,br)]
    f=m.font(size);full=f.getbbox(tail)
    token=Image.new('RGBA',rest.size)
    ImageDraw.Draw(token).text((30-full[0]+f.getlength(prefix),30-full[1]),str(n),font=f,fill=INK)
    tb=m.bbox(token)
    emptied=rest.copy();emptied.putalpha(ImageChops.subtract(rest.getchannel('A'),token.getchannel('A')))
    h=max(bl[3]-bl[1]+20,br[3]-br[1]);im=Image.new('RGBA',(wl+ws+wr+88,h+70))
    im.alpha_composite(lead,(25-bl[0],25-bl[1]));im.alpha_composite(sub,(25+wl-bs[0],25+round(size*.55)-bs[1]))
    origin=(42+wl+ws-br[0],25-br[1]);im.alpha_composite(emptied,origin)
    return im,[tb[0]+origin[0],tb[1]+origin[1],tb[2]+origin[0],tb[3]+origin[1]]


def prepare(path):
    data=json.loads(resolve(path).read_text())
    if data.get('fps',FPS)!=FPS:
        raise ValueError('Arithmetic production requires an explicit 30fps timeline')
    events=data.get('voice_events',data.get('events'))
    if not events:
        raise ValueError('A complete event timeline is required')
    if 'start_s' not in events[0]:
        events=[{**e,'start_s':e['provisional_start_s'],'end_s':e['provisional_end_s'],
                 'kind':e.get('role'),'duration_s':e['estimated_duration_s']} for e in events]
        data={**data,'preview_plan_only':True}
    events=[{**e,'kind':e.get('kind',e.get('role')),
             'duration_s':e.get('duration_s',e['end_s']-e['start_s'])} for e in events]
    by={e['id']:e for e in events}
    if len(events)!=215 or len(by)!=215:
        raise ValueError('All 215 speech cues are required')
    for n in range(1,102):
        if by[f'N{n:03d}'].get('n')!=n:
            raise ValueError(f'Wrong term link N{n:03d}')
    counts=[]
    for n in range(1,102):
        result=by[f'N{n:03d}'];prefix=by.get(f'E{n:03d}')
        counts.append({'n':n,'value':3*n-1,'previous_value':3*n-4 if n>1 else None,
                       'addition_count':n-1,'formula_event_id':prefix['id'] if prefix else None,
                       'result_event_id':result['id'],'formula_start_s':prefix['start_s'] if prefix else None,
                       'formula_end_s':prefix['end_s'] if prefix else None,
                       'result_start_s':result.get('result_display_s',result['start_s']-.12),
                       'voice_start_s':result['start_s'],'voice_end_s':result['end_s'],
                       'progress_commit_s':result['end_s']})
    if 'counted_states' in data:
        supplied={r['n']:r for r in data['counted_states']}
        for c in counts:
            row=supplied[c['n']]
            if row['value']!=c['value']:
                raise ValueError(f'Wrong arithmetic value {row}')
            c.update(row)
    duration=data.get('duration_s',events[-1]['end_s']+1.2)
    data.update(voice_events=events,counted_states=counts,duration_s=duration,
                duration_frames=data.get('duration_frames',math.ceil(duration*FPS)),fps=FPS)
    return data


class Canvas(m.Canvas):
    """Retain true foreground layers for independent inspection by the QA agent."""
    def __init__(self,plate,scene,time=None):
        super().__init__(plate,scene,time)
        self.foreground={}
        self.contacts=[]

    def center(self,layer,box,ident,opacity=1):
        if opacity<=0:
            self.absent.append({'component_id':ident,'reason':'not yet generated'})
            return
        if opacity<1:
            layer=layer.copy()
            layer.putalpha(layer.getchannel('A').point(lambda a:round(a*opacity)))
        threshold=max(1,round(128*opacity))
        b=m.bbox(layer,threshold)
        if b is None:
            raise ValueError(f'Empty visible component {ident}')
        xy=(round((box[0]+box[2]-b[0]-b[2])/2),round((box[1]+box[3]-b[1]-b[3])/2))
        report=raster_centering_report(layer,box,origin_xy=xy,name=f'{self.scene}/{ident}',
                                       tolerance_px=.5,alpha_threshold=threshold)
        report.update(component_id=ident,scene=self.scene,horizontal='center',vertical='center',
                      resolution_px=list(SIZE),opacity=opacity)
        if not report['passed']:
            raise ValueError(report)
        v=report['visible_box_xyxy']
        if not (0<v[0]<v[2]<1920 and 0<v[1]<v[3]<1080):
            raise ValueError(f'Foreground crosses output canvas: {ident}: {v}')
        self.records.append(report)
        self.foreground[ident]=(layer,xy,threshold)
        self.image.alpha_composite(layer,xy)

    def text(self,text,box,size=38,color=INK,ident=None,opacity=1):
        self.center(glyphs(text,size,color),box,ident or text,opacity)
        if opacity>0:
            self.records[-1].update(text=text,font_size_px=size,color=color)

    def moving(self,layer,xy_center,ident,scale=1,color=None):
        if scale!=1:
            layer=layer.resize((max(1,round(layer.width*scale)),max(1,round(layer.height*scale))),Image.Resampling.LANCZOS)
        b=m.bbox(layer)
        w,h=b[2]-b[0],b[3]-b[1]
        x,y=xy_center
        box=(x-w/2-8,y-h/2-8,x+w/2+8,y+h/2+8)
        self.center(layer,box,ident)
        self.records[-1].update(placement_role='moving glyph center at declared curve point',raster_scale=scale)

    def counters(self,positions,ident='unit-counters',seed=False,radius=18,unit_count=None):
        if not positions:
            return
        minx=min(p[0] for p in positions);maxx=max(p[0] for p in positions)
        miny=min(p[1] for p in positions);maxy=max(p[1] for p in positions)
        # Raster at absolute integer counter centers, then measure the complete
        # intended group against its symmetric destination content region.
        x0,y0=math.floor(minx-radius-20),math.floor(miny-radius-20)
        x1,y1=math.ceil(maxx+radius+21),math.ceil(maxy+radius+21)
        layer=Image.new('RGBA',(x1-x0,y1-y0))
        d=ImageDraw.Draw(layer)
        for x,y in positions:
            x,y=round(x)-x0,round(y)-y0
            d.ellipse((x-radius,y-radius,x+radius,y+radius),fill=m.MINT if seed else m.SAND,
                      outline=TEAL if seed else GOLD,width=3)
        # The target comes from the planned integer raster centers and radius,
        # independently of the foreground mask that the checker measures.
        rounded=[(round(x),round(y)) for x,y in positions]
        box=(min(x for x,y in rounded)-radius-8,min(y for x,y in rounded)-radius-8,
             max(x for x,y in rounded)+radius+1+8,max(y for x,y in rounded)+radius+1+8)
        self.center(layer,box,ident)
        self.records[-1].update(unit_count=unit_count if unit_count is not None else len(positions),
                                role='counted unit particles; never decorative sparkle',
                                planned_integer_centers_px=rounded,radius_px=radius,
                                target_bounds_method='planned integer ellipse extents, independently of measured mask')

    def clearance(self):
        for i,a in enumerate(self.records):
            for b in self.records[i+1:]:
                aa,bb=a['visible_box_xyxy'],b['visible_box_xyxy']
                region=(max(aa[0],bb[0]),max(aa[1],bb[1]),min(aa[2],bb[2]),min(aa[3],bb[3]))
                if region[0]>=region[2] or region[1]>=region[3]:
                    continue
                pair={a['component_id'],b['component_id']}
                # Mathematical particle merges deliberately join seed and
                # addend pixels. They never contact a numeral glyph.
                if pair <= {'replay-seed-units','replay-addend-units'} or pair=={'replay-seed-units','moving-added-subtotal'}:
                    continue
                la,oa,ta=self.foreground[a['component_id']]
                lb,ob,tb=self.foreground[b['component_id']]
                masks=[]
                for layer,origin,threshold in ((la,oa,ta),(lb,ob,tb)):
                    masks.append(layer.getchannel('A').point(lambda v:255 if v>=threshold else 0).crop(
                        (region[0]-origin[0],region[1]-origin[1],region[2]-origin[0],region[3]-origin[1])))
                if ImageChops.multiply(*masks).getbbox():
                    if pair=={'input-term-number','moving-term-input'}:
                        allowed=self.data.get('term_input_source_box_px')
                        contact=ImageChops.multiply(*masks)
                        if allowed:
                            ImageDraw.Draw(contact).rectangle((math.floor(allowed[0]-region[0]),math.floor(allowed[1]-region[1]),
                                math.ceil(allowed[2]-region[0])-1,math.ceil(allowed[3]-region[1])-1),fill=0)
                            if not contact.getbbox():
                                self.contacts.append({'moving':'moving-term-input','same_value_source':'input-term-number',
                                                      'allowed_actual_numeric_glyph_box_px':allowed})
                                continue
                    raise ValueError(f'Visible foreground collision in {self.scene}: {pair}')
        self.data['visible_foreground_clearance_pass']=True
        self.data['permitted_same_value_source_contacts']=self.contacts


@dataclass(frozen=True)
class Frame:
    mode:str
    n:int
    phase:str
    tick:int
    completed:int
    cue:str
    actor_state:str='neutral'
    actor_phase:int=0
    fade:int=0
    lesson:int=0


class Episode:
    def __init__(self,timeline,registry=None,background=None,motion=None,actor_module=None):
        self.timeline_path=resolve(timeline);self.plan=prepare(self.timeline_path)
        self.events=self.plan['voice_events'];self.by={e['id']:e for e in self.events}
        self.starts=[e['start_s'] for e in self.events]
        self.counts=self.plan['counted_states'];self.ends=[c['progress_commit_s'] for c in self.counts]
        self.replay_landmarks=self.make_replay_landmarks()
        self.background_path=resolve(background) if background else m.BG
        original=Image.open(self.background_path).convert('RGBA')
        self.background=ImageOps.fit(original,SIZE,Image.Resampling.LANCZOS)
        self.background_usage={'source_size_px':list(original.size),'display_size_px':list(SIZE),
                               'uniform_cover_scale':max(1920/original.width,1080/original.height)}
        self.actor_module_path=resolve(actor_module) if actor_module else ROOT/'tools/arithmetic_animation.py'
        self.actor_module=None
        if self.actor_module_path.exists():
            spec=importlib.util.spec_from_file_location('arithmetic_production_actor',self.actor_module_path)
            self.actor_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.actor_module)
        self.actor_module_receipt=receipt(self.actor_module_path) if self.actor_module else None
        self.preview_actor=m.Actor()
        self.registry_path=resolve(registry) if registry else None
        self.motion_path=resolve(motion) if motion else None
        self.actor_windows=self.make_motion()
        if self.motion_path:
            supplied=json.loads(self.motion_path.read_text())
            self.actor_windows=supplied.get('windows',self.actor_windows)
        self.segments=[{'mode':'intro','n':0,'cue':'I001','start_frame':0}]
        for c in self.counts:
            n=c['n']
            start=c['formula_start_s']-.70 if n>1 else c['voice_start_s']-.32
            self.segments.append({'mode':'count','n':n,'cue':c['formula_event_id'] or c['result_event_id'],
                                  'start_frame':max(0,math.ceil(start*FPS))})
            replay=self.by.get(f'X{n:03d}')
            if replay:
                self.segments.append({'mode':'replay','n':n,'cue':replay['id'],
                                      'start_frame':math.ceil((replay['start_s']-.30)*FPS)})
        self.segments.append({'mode':'outro','n':101,'cue':'O001',
                              'start_frame':math.ceil((self.by['O001']['start_s']-.30)*FPS)})
        self.segments.sort(key=lambda s:s['start_frame'])
        self.segment_starts=[s['start_frame'] for s in self.segments]
        for i,s in enumerate(self.segments):
            s['end_frame']=self.segments[i+1]['start_frame'] if i+1<len(self.segments) else self.plan['duration_frames']
        self.cuts=[s['start_frame'] for i,s in enumerate(self.segments) if i and
                   (s['mode']!=self.segments[i-1]['mode'] or s['mode']=='replay')]
        self.reports={}
        self.sources={'timeline':receipt(self.timeline_path),'background':receipt(self.background_path),
                      'font':receipt(m.FONT),'renderer':receipt(Path(__file__)),
                      'canonical_actor':receipt(ROOT/self.preview_actor.char['neutral']['path'])}
        if self.actor_module:
            self.sources['actor_module']=receipt(self.actor_module_path)
            if hasattr(self.actor_module,'BATCH'):
                batch=Path(self.actor_module.BATCH)
                registration=batch/'registration.json'
                if registration.exists():
                    self.sources['actor_registration']=receipt(registration)
                for i,path in enumerate(sorted((batch/'frames').glob('*.png'))):
                    self.sources[f'actor_source_frame_{i}']=receipt(path)
        if self.plan.get('source_phonemes'):
            self.sources['source_phonemes']=receipt(resolve(self.plan['source_phonemes']['path']))
        self._math_cache_key=None;self._math_cache_canvas=None
        self._image_cache_key=None;self._image_cache_value=None

    def make_replay_landmarks(self):
        ref=self.plan.get('source_phonemes')
        if not ref:
            return {}
        path=resolve(ref['path'])
        if sha(path)!=ref['sha256']:
            raise ValueError('Replay CTC landmarks must use the exact timeline evidence')
        rows={r['id']:r for r in json.loads(path.read_text())['results']}
        result={}
        for n in (4,51,101):
            e=self.by[f'X{n:03d}'];r=rows[e['id']]
            if r['source_sha256']!=e['source_sha256']:
                raise ValueError(f'Replay CTC source changed: {e["id"]}')
            chars=[(c,t) for t in r['tokens'] for c in t['token'].replace('ː','') if c not in ' ˈˌ']
            seq=''.join(c for c,t in chars)
            isword=list(re.finditer('[ɪᵻiə]z',seq))[-1]
            onset=chars[isword.end()][1]['start_s']
            result[n]={'method':'independent CTC result onset after final spoken is',
                       'result_voice_start_relative_s':onset,'result_commit_relative_s':max(.5,onset-.12),
                       'source_sha256':r['source_sha256']}
            if n==4:
                zero=re.search('z[iɪ]ɹoʊ',seq)
                if zero:result[n]['zero_example_relative_s']=chars[zero.start()][1]['start_s']-.12
        e=self.by['X034'];r=rows['X034']
        chars=[(c,t) for t in r['tokens'] for c in t['token'].replace('ː','') if c not in ' ˈˌ']
        seq=''.join(c for c,t in chars)
        first=re.search('naɪndinaɪn',seq)
        second=re.search('wʌnhʌndɹ[ᵻɪ]d',seq[first.end():])
        second_start=first.end()+second.start();second_end=first.end()+second.end()
        third=re.search('wʌnhʌndɹ[ᵻɪ]dwʌn',seq[second_end:]);third_start=second_end+third.start()
        result[34]={'method':'independent CTC 99/100/101 onsets within the unit-step explanation',
                    'unit_step_commits_relative_s':[chars[k][1]['start_s']-.12 for k in (first.start(),second_start,third_start)],
                    'source_sha256':r['source_sha256']}
        return result

    def make_motion(self):
        windows=[]
        def add(ident,cue,state,edge='start_s',offset=.1,duration=1.6):
            e=self.by[cue]
            windows.append({'id':ident,'state':state,'start_frame':round((e[edge]+offset)*FPS),
                            'end_frame':round((e[edge]+offset+duration)*FPS),
                            'phase_policy':'0 to 1 across the window; artwork owns explicit outward-and-return motion',
                            'cue':cue,'changes_audio_timing':False})
        add('opening-greeting','I001','greet',duration=1.7)
        add('opening-plus-three','I003','offer',offset=.6,duration=2.3)
        add('opening-show-input','I004','present_left',offset=.4,duration=1.8)
        add('opening-term-label','I006','present_right',offset=1.0,duration=1.8)
        for n in (2,4,12,26,43,59,78,94):
            add(f'guide-three-{n:03d}',f'E{n:03d}','offer',offset=.05,duration=1.5)
        for n in (7,19,39,57,74,89):
            add(f'consider-{n:03d}',f'N{n:03d}','think',edge='end_s',offset=.05,duration=1.4)
        for n in (22,47,72,92):
            add(f'relax-{n:03d}',f'N{n:03d}','relax',edge='end_s',offset=.05,duration=1.7)
        for n in (29,63,84):
            add(f'stretch-{n:03d}',f'N{n:03d}','stretch',edge='end_s',offset=.05,duration=1.75)
        for n in (34,67,101):
            add(f'notice-carry-{n:03d}',f'N{n:03d}','surprise',edge='end_s',offset=.06,duration=.95)
        for n in (4,51,101):
            add(f'show-groups-{n:03d}',f'X{n:03d}','present_right' if n!=51 else 'present_left',
                offset=1.8,duration=2.4)
        add('carry-replay','X034','present_left',offset=1.2,duration=2.0)
        add('closing-wave','O003','goodbye',edge='end_s',offset=-.65,duration=.9)
        windows.sort(key=lambda w:w['start_frame'])
        return windows

    def actor_at(self,frame):
        # No free-running gesture loop. A quiet blink is isolated from limb
        # actions and uses the same canonical face on every return.
        active=[w for w in self.actor_windows if w['start_frame']<=frame<w['end_frame']]
        if active:
            w=active[-1]
            return w['state'],tick((frame-w['start_frame'])/max(1,w['end_frame']-w['start_frame']-1))
        blink_cycle=frame%211
        if blink_cycle<8 and frame>120:
            return 'blink',tick(blink_cycle/7)
        return 'neutral',0

    def operation(self,n,t):
        c=self.counts[n-1]
        if n==1:
            return ('result',60) if t>=c['result_start_s'] else ('seed',0)
        e=self.by[f'E{n:03d}'];start=e['start_s'];end=e['end_s'];d=end-start
        transfer_start=start-.70;transfer_end=start-.08
        h=e.get('highlight_timing',{})
        plus=h.get('plus_start_s',e.get('plus_start_s',start+d*.34))
        arrival=c['result_start_s']-.08
        if t<transfer_end:
            return 'transfer',tick(smooth((t-transfer_start)/max(.01,transfer_end-transfer_start)))
        if t<plus:
            return 'input',0
        if t<arrival:
            return 'add',tick(smooth((t-plus)/max(.01,arrival-plus)))
        if t<c['result_start_s']:
            return 'merge',tick((t-arrival)/max(.01,c['result_start_s']-arrival))
        return 'result',60

    def state(self,frame):
        t=frame/FPS
        segment=self.segments[max(0,bisect_right(self.segment_starts,frame)-1)]
        mode,n,cue=segment['mode'],segment['n'],segment['cue']
        active=self.events[max(0,bisect_right(self.starts,t)-1)]
        lesson=0
        if mode=='count':
            phase,p=self.operation(n,t)
            cue=f'N{n:03d}' if phase=='result' else f'E{n:03d}' if n>1 else 'N001'
        elif mode=='intro':
            cue=active['id'] if active['id'].startswith('I') else 'I007'
            e=self.by[cue];phase=cue;p=tick((t-e['start_s'])/max(.01,e['duration_s']))
        elif mode=='replay':
            e=self.by[cue];u=clamp((t-e['start_s'])/max(.01,e['duration_s']))
            if n==34:
                phase='carry';p=0
                commits=self.replay_landmarks.get(34,{}).get('unit_step_commits_relative_s',
                        [e['duration_s']*.5,e['duration_s']*.66,e['duration_s']*.81])
                relative=t-e['start_s'];lesson=bisect_right(commits,relative)
                if lesson<3:p=tick((relative-(commits[lesson]-.48))/.48)
            else:
                commit=self.replay_landmarks.get(n,{}).get('result_commit_relative_s',e['duration_s']*.84)
                relative=clamp((t-e['start_s'])/max(.01,commit))
                if relative<.20:phase='term-input';p=tick(relative/.20)
                elif relative<.40:phase='subtract';p=tick((relative-.20)/.20)
                elif relative<.77:phase='multiply';p=tick((relative-.40)/.37)
                elif relative<1:phase='join';p=tick((relative-.77)/.23)
                else:phase='replay-result';p=60
                if n==4 and t-e['start_s']>=self.replay_landmarks.get(4,{}).get('zero_example_relative_s',e['duration_s']*.77):
                    lesson=1
        else:
            cue=active['id'] if active['id'].startswith('O') else 'O003'
            e=self.by[cue];phase='outro';p=tick((t-e['start_s'])/max(.01,e['duration_s']))
        completed=bisect_right(self.ends,t)
        actor_state,actor_phase=self.actor_at(frame)
        fade=0
        # Composition changes happen during measured silent intervals. The
        # opaque cream cut prevents body-scale or scene-position dissolves.
        for cut in self.cuts:
            distance=abs(frame-cut)
            if distance<=3:
                fade=max(fade,round(255*(1-distance/3)))
        fade_in=self.plan.get('intro',{}).get('fade_in_s',.6)
        if fade_in and t<fade_in:
            fade=max(fade,round(255*(1-t/fade_in)))
        fade_out=self.plan.get('finale',{}).get('fade_last_s',.75)
        final_time=(self.plan['duration_frames']-1)/FPS
        if fade_out and t>final_time-fade_out:
            fade=max(fade,round(255*clamp((t-(final_time-fade_out))/fade_out)))
        return Frame(mode,n,phase,p,completed,cue,actor_state,actor_phase,fade,lesson)

    def header(self,c,subtitle='THE SAME DIFFERENCE · ADD THREE'):
        m.header(c,subtitle)

    def progress(self,c,k):
        c.text(f'Terms counted: {k} / 101',PROGRESS_BOX,22,MUTED,'progress')
        c.data['completed_count']=k

    def recent(self,c,k):
        values=[3*j-1 for j in range(max(1,k-4),k+1)]
        if values:
            text=('…   ' if k>5 else '')+'   →   '.join(map(str,values))
            c.text(text,RECENT_BOX,29,TEAL,'recent-terms')
        c.data['recent_completed_values']=values

    def equation(self,c,n,show_result=False,show_input=True):
        value=3*n-1;previous=value-3
        c.panel((345,190,1575,325))
        if show_input:
            source=glyphs(str(previous),180,INK)
            c.moving(source,center(INPUT_BOX),'equation-input',scale=80/180)
            c.records[-1].update(text=str(previous),font_size_px=80,source_font_size_px=180,
                                source_resampling='LANCZOS uniform scale 80/180')
        c.text('+ 3',ADDEND_BOX,80,TEAL,'equation-addend')
        c.text('=',EQUALS_BOX,80,INK,'equation-equals')
        if show_result:
            c.text(str(value),EQUATION_RESULT_BOX,80,GOLD,'equation-result')
        c.data.update(n=n,value=value,previous_value=previous,increment=3,
                      equation=f'{previous} + 3 = '+(str(value) if show_result else ''),
                      equation_layout='fixed operand/operator/result columns; each visible glyph group centered in its own content box',
                      result_committed=show_result)

    def count(self,c,s):
        n=s.n;value=3*n-1;p=s.tick/60
        self.header(c)
        c.text(f'TERM {n}',TERM_BOX,27,TEAL,'term-number')
        if n==1:
            c.center(indexed(' = 2',80,'1'),(370,205,1550,305),'seed-equation')
            if s.phase=='result':
                c.text('2',RESULT_BOX,180,GOLD,'generated-value')
                c.text('two',READING_BOX,35,INK,'natural-reading')
                c.counters([(925,578),(995,578)],'first-term-two-units',seed=True,radius=18)
            c.data.update(n=1,value=2,previous_value=None,result_committed=s.phase=='result',
                          seed_unit_count=2,increment_unit_count=0,addition_count=0,equation='a1 = 2')
        else:
            self.equation(c,n,s.phase=='result',s.phase!='transfer')
            c.text('ADD THREE',(650,345,1070,390),27,TEAL,'fixed-addend-label')
            if s.phase=='transfer':
                # Exact previous-answer raster, transported rather than a
                # different decorative token or a morphing numeric value.
                x0,y0=center(RESULT_BOX);x2,y2=center(INPUT_BOX)
                q=1-p
                point=(q*q*x0+2*q*p*500+p*p*x2,
                       q*q*y0+2*q*p*465+p*p*y2)
                scale=lerp(1,80/180,p)
                c.moving(glyphs(str(value-3),180,INK),point,'moving-previous-answer',scale)
                c.records[-1].update(text=str(value-3),source_font_size_px=180,
                                    source_value=value-3,source_center_px=list(center(RESULT_BOX)),
                                    destination_center_px=list(center(INPUT_BOX)))
                c.data['previous_glyph_transfer']={'source_value':value-3,'progress':p,
                    'source_center_px':list(center(RESULT_BOX)),'control_center_px':[500,465],
                    'destination_center_px':list(center(INPUT_BOX)),
                    'source_font_size_px':180,'destination_scale':80/180,'raster_scale':scale,
                    'identity':'same complete numeral raster; no digit morph'}
            if s.phase=='input':
                positions=[(810+j*55,430) for j in range(3)]
            elif s.phase=='add':
                positions=[(lerp(810+j*55,920+j*40,p),
                            lerp(430,515,p)-math.sin(math.pi*p)*42) for j in range(3)]
            elif s.phase=='merge':
                positions=[(lerp(920+j*40,960,p),lerp(515,477.5,p)) for j in range(3)]
            else:
                positions=[]
            if positions:
                c.counters(positions,'addend-three-units',radius=18,unit_count=3)
            if s.phase=='result':
                c.text(str(value),RESULT_BOX,180,GOLD,'generated-value')
                c.text(m.words(value),READING_BOX,35,INK,'natural-reading')
            else:
                c.text('The same three, every time.',READING_BOX,30,TEAL,'generation-caption')
            c.data.update(increment_unit_count=3 if positions else 0,
                          increment_units_have_merged=s.phase=='result',addition_count=n-1,
                          particles_represent='only the addend, never the full result',
                          transfer_phase=s.phase,phase_tick=s.tick)
        self.recent(c,s.completed)
        self.progress(c,s.completed)

    def intro(self,c,s):
        self.header(c,'NUM-NUM NUMBERS · THE MORNING WIND ORGAN')
        p=s.tick/60
        if s.cue in ('I001','I007'):
            c.text('A little breeze. Three more.',(300,224,1620,314),65,TEAL,'opening-promise')
            c.center(indexed(' = 2 + (n − 1) × 3',64),(320,353,1600,465),'general-rule')
            c.text('2,  5,  8,  11,  14, …',(450,531,1470,612),55,GOLD,'sequence-preview')
        elif s.cue=='I002':
            c.text('START WITH 2',(300,235,1620,325),58,TEAL,'choose-seed')
            c.counters([(640,465),(710,465)],'intro-seed-two',seed=True,radius=25)
            c.text('+ 3',(1070,390,1400,525),100,GOLD,'intro-fixed-addend')
            c.text('Choose the start. Keep the difference.',(300,574,1620,632),37,INK,'intro-rule-caption')
        elif s.cue in ('I003','I004'):
            demo=Frame('count',2,'add' if p<.8 else 'result',tick(p/.8) if p<.8 else 60,0,s.cue)
            self.equation(c,2,demo.phase=='result')
            c.text('PREVIEW',(1440,345,1740,390),27,TEAL,'preview-label')
            c.text('ADD THREE',(650,345,1070,390),27,TEAL,'fixed-addend-label')
            if demo.phase!='result':
                q=demo.tick/60
                c.counters([(lerp(810+j*55,920+j*40,q),lerp(430,515,q)-math.sin(math.pi*q)*42)
                            for j in range(3)],'intro-three-units',radius=18,unit_count=3)
            else:
                c.text('5',RESULT_BOX,180,GOLD,'preview-value')
            c.text('Input → add three → next value',(300,605,1620,655),36,TEAL,'intro-flow-caption')
        elif s.cue=='I005':
            c.text('next value = current value + 3',(300,230,1620,355),57,TEAL,'recurrence-preview')
            c.text('2   →   5   →   8   →   11',(330,435,1590,520),65,GOLD,'equal-step-preview')
            for x in (625,900,1180):
                c.text('+3',(x-60,560,x+60,615),32,TEAL,f'equal-step-{x}')
        elif s.cue=='I006':
            c.text('TERM NUMBER',(300,250,900,320),36,TEAL,'term-label')
            c.text('VALUE',(1050,250,1650,320),36,GOLD,'value-label')
            c.text('n = 4',(350,365,850,495),80,TEAL,'term-example')
            c.center(indexed(' = 11',80,'4'),(1050,365,1650,495),'value-example')
            c.text('PREVIEW · number 4 in the sequence has value 11',(300,560,1620,625),31,INK,'term-value-distinction')
        self.progress(c,0)
        c.data.update(scene_role='wide introduction',preview_not_counted=True,n=0)

    def replay(self,c,s):
        if s.n==34:
            return self.carry(c,s)
        n=s.n;value=3*n-1;groups=n-1;p=s.tick/60
        self.header(c,'REPLAY · (n − 1) GROUPS OF THREE')
        c.panel((280,190,1640,330))
        if s.phase=='term-input':
            layer,slot=indexed_operand_slot(n,65)
            c.center(layer,GENERAL_BOX,'working-general-formula')
            origin=c.records[-1]['measurement_origin_px']
            slot=[slot[0]+origin[0],slot[1]+origin[1],slot[2]+origin[0],slot[3]+origin[1]]
            c.records[-1].update(masked_operand=str(n),font_size_px=65,index=str(n),
                                  tail=f' = 2 + ({n} − 1) × 3')
            c.data['term_operand_slot_box_px']=slot
        elif s.phase=='subtract':
            tail=f' = 2 + ({n} − 1) × 3' if p<.55 else f' = 2 + {groups} × 3'
            c.center(indexed(tail,65,str(n)),GENERAL_BOX,'working-general-formula')
        else:
            tail=f' = 2 + {groups} × 3'
            if s.phase=='replay-result':
                tail+=f' = {value}'
            c.center(indexed(tail,65,str(n)),GENERAL_BOX,'working-general-formula')
        c.text(f'n = {n}',(760,350,1160,402),39,TEAL,'input-term-number')
        if s.phase=='term-input':
            # Copy the actual decimal n glyph from the input label, deliver it
            # into its reserved (n−1) operand slot, then evaluate subtraction.
            layer,label_origin,_=c.foreground['input-term-number']
            f=m.font(39);full=f.getbbox(f'n = {n}')
            mask=Image.new('RGBA',layer.size)
            ImageDraw.Draw(mask).text((30-full[0]+f.getlength('n = '),30-full[1]),str(n),font=f,fill=TEAL)
            sb=m.bbox(mask);source_box=[sb[0]+label_origin[0],sb[1]+label_origin[1],sb[2]+label_origin[0],sb[3]+label_origin[1]]
            sx,sy=center(source_box);tx,ty=center(slot)
            q=smooth(p)
            if q<.25:x,y=sx,lerp(sy,340,q/.25)
            elif q<.60:x,y=lerp(sx,tx,(q-.25)/.35),340
            else:x,y=tx,lerp(340,ty,(q-.60)/.40)
            c.data['term_input_source_box_px']=source_box
            c.moving(glyphs(str(n),39,TEAL),(x,y),'moving-term-input',lerp(1,65/39,q))
            c.records[-1].update(text=str(n),source_font_size_px=39,source_value=n,
                                  source_center_px=[sx,sy],destination_center_px=[tx,ty])
        elif s.phase=='subtract':
            c.text(f'{n} − 1 = {groups}',(760,414,1510,474),35,TEAL,'subtract-one-result')
        else:
            c.text(f'{groups} additions',(760,414,1510,474),35,TEAL,'addition-count')
        seed_positions=[(530,550),(595,550)]
        if s.phase not in ('join','replay-result'):
            c.text('START: 2',(410,633,730,677),28,TEAL,'replay-seed-label')
        if n==4:
            sources=[(x+(j-1)*48,550) for x in (850,1100,1350) for j in range(3)]
            if s.phase in ('term-input','subtract'):
                visible=0
            elif s.phase=='multiply':
                visible=min(9,max(0,math.ceil(p*9)))
            else:
                visible=9
            if s.phase in ('join','replay-result'):
                q=smooth(min(1,p/.5)) if s.phase=='join' else 1
                targets=[(755+j*62,525) for j in range(6)]+[(786+j*62,587) for j in range(5)]
                combined=seed_positions+sources
                moved=[(lerp(a[0],b[0],q),lerp(a[1],b[1],q)) for a,b in zip(combined,targets)]
                if s.phase=='join' and p>.5:
                    contraction=smooth((p-.5)/.5);rx,ry=center(REPLAY_RESULT_BOX)
                    moved=[(lerp(x,rx,contraction),lerp(y,ry,contraction)) for x,y in moved]
                seed_positions=moved[:2];particle_positions=moved[2:]
                if s.phase=='replay-result':
                    seed_positions=[];particle_positions=[]
            else:
                particle_positions=sources[:visible]
                for x in (850,1100,1350):
                    c.draw.rounded_rectangle((x-91,496,x+91,600),radius=24,fill='#fffcf4',outline='#dfcbaa',width=2)
            c.counters(seed_positions,'replay-seed-units',seed=True,radius=19)
            c.counters(particle_positions,'replay-addend-units',radius=17,unit_count=len(particle_positions))
            group_label='n − 1 groups of three' if s.phase=='term-input' else '3 groups of three' if s.phase=='subtract' else '3 groups × 3' if s.phase=='multiply' and p<.95 else '3 groups × 3 = 9'
            if s.phase not in ('join','replay-result'):
                c.text(group_label,(760,633,1490,677),31,GOLD,'replay-group-label')
            if s.phase=='replay-result':
                c.text('2 + 9 = 11',(650,490,1450,590),54,TEAL,'replay-completed-sum')
                if s.lesson:
                    c.text('First term: 2 + 0 × 3 = 2',(600,705,1610,758),31,TEAL,'first-term-zero-additions')
            c.data.update(diagram_kind='exact unit particles',seed_unit_count=2,
                          addend_unit_count=len(particle_positions),group_count=3,units_per_group=3,
                          exact_complete_unit_count=11,visible_seed_unit_count=len(seed_positions),
                          particles_consumed_into_result=s.phase=='replay-result',
                          particle_merge_progress=p if s.phase=='join' else None)
        else:
            marker_count=groups//10
            if s.phase=='join':
                q=smooth(p);rx,ry=center((770,791,1190,951) if n==51 else REPLAY_RESULT_BOX)
                if q<.4:
                    seed_positions=[(x,lerp(y,825,q/.4)) for x,y in seed_positions]
                else:
                    seed_positions=[(lerp(x,rx,(q-.4)/.6),lerp(825,ry,(q-.4)/.6)) for x,y in seed_positions]
            if s.phase!='replay-result':
                c.counters(seed_positions,'replay-seed-units',seed=True,radius=21)
            shown=0 if s.phase in ('term-input','subtract') else math.ceil(p*marker_count) if s.phase=='multiply' else marker_count
            for j in range(shown):
                row,col=divmod(j,5)
                x,y=820+col*133,530+row*86
                c.draw.rounded_rectangle((x-49,y-31,x+49,y+31),radius=19,fill=m.SAND,outline=GOLD,width=2)
                c.text('30',(x-42,y-24,x+42,y+24),29,GOLD,f'compressed-30-unit-marker-{j}')
            if s.phase!='join':
                c.text('1 marker = 10 groups × 3 = 30 units',(700,720,1560,769),27,TEAL,'compressed-marker-legend')
            if s.phase in ('join','replay-result'):
                marker_label=f'{marker_count} markers × 30 = {groups*3}'
            elif s.phase=='multiply':marker_label=f'{marker_count} markers × 30'
            elif s.phase=='subtract':marker_label=f'{groups} groups of three'
            else:marker_label='n − 1 groups of three'
            if s.phase=='join':
                q=smooth(p);rx,ry=center((770,791,1190,951) if n==51 else REPLAY_RESULT_BOX)
                c.moving(glyphs(str(groups*3),48,GOLD),(lerp(1130,rx,q),lerp(680,ry,q)),
                         'moving-added-subtotal',scale=lerp(1,.65,q))
                c.records[-1].update(text=str(groups*3),source_font_size_px=48,source_value=groups*3,
                                      destination_center_px=[rx,ry],role='computed subtotal from labelled compressed markers')
            else:
                c.text(marker_label,(700,655,1560,704),30,GOLD,'compressed-marker-total')
            c.data.update(diagram_kind='labelled compressed markers, not individual units',
                          seed_unit_count=2,marker_count=shown,complete_marker_count=marker_count,
                          groups_per_marker=10,units_per_group=3,units_per_marker=30,
                          indicated_added_units=shown*30,total_added_units=groups*3)
        if s.phase=='replay-result':
            c.text(str(value),(770,791,1190,951) if n==51 else REPLAY_RESULT_BOX,123,GOLD,'replay-generated-value')
            c.text(m.words(value),(400,971,1360,1015) if n==51 else (640,971,1710,1015),31,INK,'replay-natural-reading')
        elif s.phase!='join':
            c.multiline(['Subtract one to find','the number of groups.'],(610,820,1370,925),31,TEAL,'replay-generation-caption')
        self.progress(c,s.completed)
        c.data.update(n=n,value=value,replay=True,replay_adds_terms=False,phase=s.phase,
                      phase_tick=s.tick,addition_count=groups,general_formula=f'2 + ({n} - 1) * 3 = {value}',
                      voice_landmarks=self.replay_landmarks.get(n),zero_addition_example=bool(s.lesson))

    def carry(self,c,s):
        self.header(c,'REPLAY · THREE UNIT STEPS CROSS A HUNDRED')
        self.equation(c,34,True)
        c.text('REPLAY',(650,346,1270,395),32,TEAL,'carry-replay-label')
        stage=s.lesson
        values=[98,99,100,101]
        xs=[585,835,1085,1335]
        for j,(x,value) in enumerate(zip(xs,values)):
            color=GOLD if j==stage else MUTED
            c.text(str(value),(x-105,448,x+105,570),86,color,f'carry-intermediate-{j}')
            if j<3:
                c.text('+1',(x+100,585,x+170,632),27,TEAL,f'carry-one-step-{j}')
        positions=[]
        for j in range(stage,3):
            x,y=650+j*250,684
            if j==stage:
                p=smooth(s.tick/60)
                if p<.65:x=lerp(x,xs[j+1],p/.65)
                else:x,y=xs[j+1],lerp(684,570,(p-.65)/.35)
            positions.append((x,y))
        c.counters(positions,'carry-three-unit-steps',radius=18,unit_count=len(positions))
        c.text('98 + 2 = 100     then     100 + 1 = 101',(360,744,1560,809),38,TEAL,'carry-decomposition')
        c.text('99 and 100: intermediate values.',(650,851,1590,906),27,INK,'carry-not-new-terms')
        self.progress(c,s.completed)
        c.data.update(n=34,value=101,replay=True,replay_adds_terms=False,intermediate_values=values,
                      intermediate_stage=stage,unit_steps=3,consumed_unit_steps=stage,
                      remaining_unit_particles=len(positions),decomposition=[2,1],voice_landmarks=self.replay_landmarks.get(34))

    def outro(self,c,s):
        self.header(c,'ONE RULE · THE SEQUENCE KEEPS GOING')
        c.center(indexed(' = 2 + (n − 1) × 3',65),(300,218,1620,340),'general-rule')
        c.text('2, 5, 8, 11, 14, …',(330,425,1590,497),55,TEAL,'beginning-values')
        c.text('…, 296, 299, 302',(330,547,1590,632),65,GOLD,'ending-values')
        c.text('101 terms. The same difference: +3.',(330,667,1590,721),34,INK,'completed-count')
        self.progress(c,101)
        c.data.update(n=101,value=302,first_values=[2,5,8,11,14],last_values=[296,299,302],
                      continuation_beyond_movie=True,full_sequence_list=False)

    def actor_geometry(self,s):
        if s.mode=='intro':
            return (960,1010),350
        if s.mode=='replay':
            return ((1560,1010),260) if s.n==51 else ((395,1010),260)
        return (960,1010),280

    @lru_cache(maxsize=512)
    def actor_graphic(self,state,phase,foot,height):
        """Cache the actor's actual foreground, never its transparent canvas."""
        plate=Image.new('RGBA',SIZE)
        if self.actor_module:
            report=self.actor_module.draw_character(plate,state,phase/60,height=height,foot=foot)
            report={'state':state,'phase':phase/60,'foot_anchor_px':list(foot),
                    'display_body_height_px':height,'source_module':self.actor_module_receipt,**(report or {})}
        else:
            c=Canvas(plate,'preview-neutral')
            self.preview_actor.draw(c,'neutral',foot,height)
            plate=c.image
            report={**c.actors[-1],'preview_only_neutral_fallback':True}
        b=plate.getchannel('A').point(lambda a:255 if a>=8 else 0).getbbox()
        if not b or not (0<b[0]<b[2]<1920 and 0<b[1]<b[3]<1080):
            raise ValueError(f'Actor empty or clipped: {state} {phase} {b}')
        crop=(b[0]-4,b[1]-4,b[2]+4,b[3]+4)
        return plate.crop(crop),(crop[0],crop[1]),report

    def canvas(self,s):
        key=(s.mode,s.n,s.phase,s.tick,s.completed,s.cue,s.lesson)
        if key==self._math_cache_key:
            return self._math_cache_canvas
        c=Canvas(self.background,f'{s.mode}-{s.n:03d}-{s.phase}-{s.tick:02d}-{s.completed:03d}')
        if s.mode=='intro':self.intro(c,s)
        elif s.mode=='count':self.count(c,s)
        elif s.mode=='replay':self.replay(c,s)
        else:self.outro(c,s)
        c.clearance()
        self._math_cache_key=key;self._math_cache_canvas=c
        return c

    def draw_actor(self,image,s):
        foot,height=self.actor_geometry(s)
        sprite,origin,report=self.actor_graphic(s.actor_state,s.actor_phase,tuple(foot),height)
        image.alpha_composite(sprite,origin)
        self._last_actor_foreground=(sprite,origin,8)
        return report

    def image(self,s):
        if s==self._image_cache_key:
            return self._image_cache_value
        c=self.canvas(s)
        im=c.image.copy()
        actor=self.draw_actor(im,s)
        # Actual actor box is checked against all independent math/text masks.
        actor_box=actor.get('visible_box_xyxy',actor.get('visible_bbox_px',actor.get('visible_bbox')))
        if actor_box:
            ax0,ay0,ax1,ay1=actor_box
            for r in c.records:
                x0,y0,x1,y1=r['visible_box_xyxy']
                if max(ax0,x0)<min(ax1,x1) and max(ay0,y0)<min(ay1,y1):
                    region=(max(ax0,x0),max(ay0,y0),min(ax1,x1),min(ay1,y1))
                    foreground=c.foreground[r['component_id']]
                    masks=[]
                    for layer,origin,threshold in (self._last_actor_foreground,foreground):
                        masks.append(layer.getchannel('A').point(lambda a:255 if a>=threshold else 0).crop(
                            (region[0]-origin[0],region[1]-origin[1],region[2]-origin[0],region[3]-origin[1])))
                    if ImageChops.multiply(*masks).getbbox():
                        raise ValueError(f'Actual actor pixels cover teaching content: {s}: {r["component_id"]}')
        if s.fade:
            wash=Image.new('RGBA',SIZE,(255,250,240,s.fade));im.alpha_composite(wash)
        ident=hashlib.sha256(json.dumps(asdict(s),sort_keys=True).encode()).hexdigest()[:20]
        if ident not in self.reports:
            self.reports[ident]={'state':asdict(s),'components':c.records,'intentional_absences':c.absent,
                                 'scene_data':c.data,'actor':actor,'foreground_clearance_pass':True}
        answer=(im.convert('RGB'),ident)
        self._image_cache_key=s;self._image_cache_value=answer
        return answer

    def write_reports(self,directory,frames):
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        native=directory/'native-states.json.gz';plan=directory/'frame-plan.json.gz'
        native.write_bytes(gzip.compress(json.dumps({'states':self.reports},ensure_ascii=False,separators=(',',':')).encode()))
        plan.write_bytes(gzip.compress(json.dumps({'fps':FPS,'frames':frames},ensure_ascii=False,separators=(',',':')).encode()))
        components=[r for v in self.reports.values() for r in v['components']]
        faded_voice=[]
        for row in frames:
            if row['fade']:
                idx=max(0,bisect_right(self.starts,row['time_s'])-1)
                e=self.events[idx]
                if e['start_s']<=row['time_s']<e['end_s']:
                    faded_voice.append({'frame':row['frame'],'cue':e['id'],'fade':row['fade']})
        if faded_voice:
            raise ValueError(f'A composition/bookend fade covers speech: {faded_voice[:4]}')
        summary={'kind':'arithmetic-production-native-layout','status':'passed','source_inputs':self.sources,
                 'resolution_px':list(SIZE),'fps':FPS,'frame_count':len(frames),'distinct_state_count':len(self.reports),
                 'centered_component_observations':len(components),'max_abs_dx_px':max(abs(r['delta_x_px']) for r in components),
                 'max_abs_dy_px':max(abs(r['delta_y_px']) for r in components),
                 'all_components_pass':all(r['passed'] for r in components),'actual_glyph_raster_measurement':True,
                 'all_foreground_clearance_pass':True,'background_usage':self.background_usage,
                 'full_actor_crossfade':False,'native_states':receipt(native),'frame_plan':receipt(plan),
                 'finished_decoded_video_qa':False,
                 'fade_intersections_with_speech':faded_voice,
                 'scope':'underlying native layers and complete renderer frame plan; encoded movie has independent QA',
                 'finale_value':302,'term_count':101,'addition_count':100,'replay_n':[4,34,51,101]}
        (directory/'native-layout-verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        (directory/'visual-segments.json').write_text(json.dumps({'fps':FPS,'segments':self.segments,'cuts':self.cuts},ensure_ascii=False,indent=2)+'\n')
        (directory/'character-motion.json').write_text(json.dumps({'fps':FPS,'windows':self.actor_windows,
            'blink_policy':'one isolated eight-frame blink every211frames when outside explicit action windows',
            'artwork_owns_outward_and_return_phase':True,'full_actor_crossfade':False},ensure_ascii=False,indent=2)+'\n')
        (directory/'layout-spec.json').write_text(json.dumps({'resolution_px':list(SIZE),'fps':FPS,
            'boxes':{'input':INPUT_BOX,'addend':ADDEND_BOX,'equals':EQUALS_BOX,'equation_result':EQUATION_RESULT_BOX,
                     'result':RESULT_BOX,'reading':READING_BOX,'progress':PROGRESS_BOX,'recent':RECENT_BOX,
                     'term':TERM_BOX,'general_formula':GENERAL_BOX,'replay_result':REPLAY_RESULT_BOX},
            'font':receipt(m.FONT),'font_px':{'input':80,'input_source_raster':180,'addend':80,'equals':80,
                'equation_result':80,'result':180,'reading':35,'progress':22,'recent':29,'term':27},
            'colors':{'ink':INK,'teal':TEAL,'gold':GOLD,'muted':MUTED},
            'transfer':{'source':center(RESULT_BOX),'quadratic_control':[500,465],'destination':center(INPUT_BOX),
                        'start':'E.start−0.70','end':'E.start−0.08','progress':'smoothstep quantized60ticks',
                        'raster':'same complete value glyph, font180, uniform scale1→80/180'},
            'addend':{'count':3,'source':[[810+j*55,430] for j in range(3)],
                      'destination':[[920+j*40,515] for j in range(3)],
                      'curve':'linear x/y minus42*sin(pi*p) vertically',
                      'start':'measured plus_start or34% of E duration','arrival':'N.start−.20',
                      'merge':'last.08s before result commit, all3 into result center'},
            'progress':'count N cue whose measured end_s <= frame/FPS; no replay increment',
            'result_commit':'N.start−.12; all digits atomic and stable through reading',
            'fades':{'intro':'linear 255→0 over timeline.intro.fade_in_s (default.6s)',
                     'outro':'linear0→255 over timeline.finale.fade_last_s ending at last output frame (default.75s)',
                     'composition_cuts':'cream opacity255*(1−abs(frame−cut)/3) inside3frames of each declared cut'},
            'replay':'n4 exact11particles; n51/101 labelled30-unit markers; n34 intermediate unit steps',
            'replay_voice_landmarks':self.replay_landmarks,
            'actor_geometry':{'intro':{'height':350,'foot':[960,1010]},'count':{'height':280,'foot':[960,1010]},
                'replay4':{'height':260,'foot':[395,1010]},'replay34':{'height':260,'foot':[395,1010]},
                'replay51':{'height':260,'foot':[1560,1010]},'replay101':{'height':260,'foot':[395,1010]},
                'outro':{'height':280,'foot':[960,1010]}}},ensure_ascii=False,indent=2)+'\n')
        return summary


def frame_row(frame,s,ident):
    return {'frame':frame,'time_s':frame/FPS,'state_id':ident,**asdict(s)}


def preview(episode,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    cues=['I001','I003','I006','N001','E002','N004','X004','N034','X034','X051','N067','N101','X101','O001']
    samples=[]
    for cue in cues:
        e=episode.by[cue];t=e['start_s']+min(e['duration_s']*.6,2.4)
        frame=round(t*FPS);s=episode.state(frame);im,ident=episode.image(s)
        path=directory/f'{cue}-{frame:06d}.png';im.save(path)
        samples.append({'cue':cue,'frame':frame,'time_s':frame/FPS,'state_id':ident,**receipt(path)})
    (directory/'preview-manifest.json').write_text(json.dumps({'samples':samples,'sources':episode.sources,
        'preview_plan_only':episode.plan.get('preview_plan_only',False)},ensure_ascii=False,indent=2)+'\n')
    return samples


def encode_frames(episode,destination,picks=None,audio=True):
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():
        raise FileExistsError(f'Keep the prior render and choose a fresh path: {destination}')
    if audio and (episode.plan.get('preview_plan_only') or not episode.plan.get('speech_adopted') or not episode.actor_module):
        raise ValueError('Production render requires measured audio and registered production articulation')
    if audio:
        for item in episode.sources.values():
            if sha(resolve(item['path']))!=item['sha256']:
                raise ValueError(f'Render input changed after loading: {item["path"]}')
    frames=list(picks) if picks is not None else range(episode.plan['duration_frames'])
    duration=len(frames)/FPS
    command=[ffbin('ffmpeg'),'-hide_banner','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080',
             '-r',str(FPS),'-i','-']
    if audio:
        master=episode.plan.get('master_audio',episode.plan.get('master_path'))
        if not master:
            fallback=episode.timeline_path.parent/'master.wav'
            if not fallback.exists():raise ValueError('Measured master audio is missing')
            master=str(fallback)
        if isinstance(master,dict):
            path=resolve(master['path'])
            if sha(path)!=master['sha256']:raise ValueError('Master SHA mismatch')
        else:path=resolve(master)
        command+=['-i',str(path),'-map','0:v:0','-map','1:a:0']
    else:command+=['-an']
    command+=['-frames:v',str(len(frames)),'-vf','scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p,setsar=1',
              '-c:v','libx264','-preset','fast','-crf','18','-profile:v','high',
              '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv',
              '-x264-params','colorprim=bt709:transfer=bt709:colormatrix=bt709:range=tv']
    if audio:
        command+=['-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-af',f'apad=whole_dur={duration:.9f}']
    command+=['-t',f'{duration:.9f}','-movflags','+faststart',str(destination)]
    rows=[]
    with destination.with_suffix('.ffmpeg.log').open('wb') as log:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
        try:
            for outframe,frame in enumerate(frames):
                s=episode.state(frame);im,ident=episode.image(s)
                process.stdin.write(im.tobytes());rows.append(frame_row(frame,s,ident))
                if outframe%(FPS*30)==0:
                    print(json.dumps({'output_frame':outframe,'frames':len(frames),'source_time_s':frame/FPS}),flush=True)
        finally:
            process.stdin.close()
        if process.wait():
            raise RuntimeError(f'Encoding failed; inspect {destination.with_suffix(".ffmpeg.log")}')
    if audio:
        for item in episode.sources.values():
            if sha(resolve(item['path']))!=item['sha256']:
                raise ValueError(f'Render input changed during encoding: {item["path"]}')
    return rows


def motion_preview(episode,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    windows=[]
    for label,cue,offset,length in [('greeting','I001',.05,2),('addition','E004',-.75,4),
                                   ('general-input','X004',0,5),('general-join','X004',8,4),
                                   ('hundred-carry','E034',-.75,4),('farewell','O003',0,3)]:
        e=episode.by[cue]
        start=max(0,round((e['start_s']+offset)*FPS));end=min(episode.plan['duration_frames'],start+round(length*FPS))
        windows.append({'id':label,'start_frame':start,'end_frame':end})
    picks=[frame for w in windows for frame in range(w['start_frame'],w['end_frame'])]
    target=directory/'continuous-acting-and-equation-preview.mp4'
    rows=encode_frames(episode,target,picks,audio=False)
    episode.write_reports(directory,rows)
    (directory/'extracts.json').write_text(json.dumps({'video':receipt(target),'windows':windows,
        'source_timeline':receipt(episode.timeline_path),'retimed':False,'audio':False,
        'production_video':False},ensure_ascii=False,indent=2)+'\n')
    return receipt(target)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['preview','motion-preview','render','native'])
    parser.add_argument('--timeline',default=str(OUTPUT/'audio-build/timeline.json'))
    parser.add_argument('--background')
    parser.add_argument('--registry')
    parser.add_argument('--motion')
    parser.add_argument('--actor-module')
    parser.add_argument('--out-dir',required=True)
    args=parser.parse_args()
    episode=Episode(args.timeline,args.registry,args.background,args.motion,args.actor_module)
    out=resolve(args.out_dir)
    if args.command=='preview':
        result=preview(episode,out)
    elif args.command=='motion-preview':
        result=motion_preview(episode,out)
    elif args.command=='native':
        rows=[]
        for frame in range(episode.plan['duration_frames']):
            s=episode.state(frame);_,ident=episode.image(s);rows.append(frame_row(frame,s,ident))
        result=episode.write_reports(out,rows)
    else:
        rows=encode_frames(episode,out/VIDEO_NAME)
        result=episode.write_reports(out,rows)
        result['video']=receipt(out/VIDEO_NAME)
        (out/'render-run.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    main()
