"""Cue-driven Lucas acting with a frozen canonical meerkat and original local arms."""
from __future__ import annotations
from bisect import bisect_right
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
REG=ROOT/'assets/library/characters/meerkat/generation-batches/lucas-production-20261112-01a1ce1d/registration.json'
FPS=30
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def resolve(p):
    p=Path(p);return p if p.is_absolute() else ROOT/p
def local(p):return resolve(p).relative_to(ROOT).as_posix()
def event_time(e,edge):
    for k in (edge+'_s',edge,edge+'_sec'):
        if k in e:return float(e[k])
    raise KeyError((e.get('id'),edge,list(e)))

class LucasActor:
    def __init__(self,timeline,registration=REG):
        self.timeline=json.loads(resolve(timeline).read_text()) if isinstance(timeline,(str,Path)) else timeline
        self.registry_path=resolve(registration);self.registry=json.loads(self.registry_path.read_text());self.poses=self.registry['poses']
        self.by={e['id']:e for e in self.timeline.get('events',self.timeline.get('voice_events',[]))}
        self.actions=[];self._verified=set()
        for name,row in self.poses.items():
            if sha(resolve(row['path']))!=row['sha256']:raise ValueError('Actor source changed: '+name)
            self._verified.add(name)
        self._build_actions();self.starts=[a['start_frame'] for a in self.actions]

    def _add(self,ident,cue,poses,lengths,reason,edge='start',offset=.2,optional=False):
        e=self.by.get(cue)
        if e is None:return
        start=math.ceil((event_time(e,edge)+offset)*FPS);cursor=start;keys=[]
        for p,seconds in zip(poses,lengths):
            if p!='rest' and p not in self.poses:raise ValueError('Unavailable actor pose '+p)
            count=max(1,round(seconds*FPS));keys.append(dict(start_frame=cursor,end_frame=cursor+count,pose=p));cursor+=count
        if any(start<a['end_frame'] and a['start_frame']<cursor for a in self.actions):
            if optional:return
            raise ValueError('Overlapping actor actions: '+ident)
        self.actions.append(dict(id=ident,cue_id=cue,start_frame=start,end_frame=cursor,keyframes=keys,reason=reason,
                                 interpolation='authored key drawings held; no full-body crossfade',foot_displacement_px=[0,0]))

    def _build_actions(self):
        gather=('rest','gather_low','gather_half','gather_full','gather_release','gather_low','rest')
        gtime=(.12,.16,.18,.40,.18,.16,.12)
        self._add('opening-greeting','I01',('rest','wave_raise','wave_half','wave_out','wave_in','wave_out','wave_in','wave_half','wave_raise','rest'),
                  (.15,.16,.18,.24,.20,.24,.20,.18,.16,.15),'A short greeting, then open eyes and a settled body.',offset=.15)
        self._add('introduce-two-inputs','I02',gather,gtime,'Open both palms to introduce two remembered values.',offset=.6)
        self._add('ready-starting-values','X001b',gather,gtime,'Welcome both fixed starting values before any sum.',offset=.6)
        self._add('acknowledge-three-units','X002a',gather,gtime,'Respond to the completed exact-unit merge; do not obscure counters.',offset=.35)
        self._add('explain-handoff','X002b',gather,gtime,'Both palms acknowledge the latest pair and return to rest.',offset=.7)
        self._add('first-carry','X005a',('rest','gather_low','gather_half','gather_low','rest'),(.12,.2,.48,.2,.12),
                  'A restrained acknowledgement of the first two-digit result.',offset=.4)
        self._add('value-tags','X005b',gather,gtime,'Signal the change from unit counters to labeled number values.',offset=.5)
        guide=('rest','guide_half','guide_extend','guide_half','rest')
        self._add('carry-column-guide','X010a',guide,(.12,.22,.48,.22,.12),'From the right-hand side, show the place-value columns once.',offset=.3)
        self._add('midpoint-looking-over-wheel','X020a',('rest','neck_prepare','neck_half','neck_full','neck_half','neck_return','rest'),
                  (.12,.20,.22,.55,.22,.20,.12),'An intentional quiet neck extension while looking over the enlarged wheel.',offset=.45)
        self._add('midpoint-role-transfer','X020b',guide,(.12,.22,.48,.22,.12),'Guide attention leftward to the transfer path, then settle.',offset=.45)
        self._add('million-discovery','X029a',('rest','gather_low','gather_half','delighted','gather_half','gather_low','rest'),
                  (.12,.16,.18,.38,.18,.16,.12),'A brief pleased expression after the million result; return with eyes open.',offset=.5)
        self._add('hundred-million','X039',guide,(.12,.2,.38,.2,.12),'Show the milestone after it has been spoken.',offset=.4)
        self._add('final-result-acknowledgement','N040',gather,gtime,'Only after the final number finishes, acknowledge the completed wheel.',edge='end',offset=.12)
        self._add('closing-greeting','O04',gather,(.16,.20,.24,.55,.24,.20,.16),'Open both palms once and return to the original settled stance.',offset=.5)
        # Short gaze and eyelid changes complement the teaching, without a periodic body loop.
        for n in (7,12,16,22,26,31,34,37):
            e=self.by.get(f'E{n:03}')
            if e is not None and event_time(e,'end')-event_time(e,'start')>2.6:
                self._add(f'quiet-blink-{n:02}',f'E{n:03}',('rest','blink_up','rest'),(.12,.1,.12),
                          'A single quiet blink during a long, stable formula reading.',offset=(event_time(e,'end')-event_time(e,'start'))*.55,optional=True)
        for n in (8,15,24,33):
            self._add(f'pair-ready-{n:02}',f'N{n:03}',('rest','gather_low','gather_half','gather_low','rest'),
                      (.10,.15,.27,.15,.1),'Briefly acknowledge a ready pair at a different point of the long count.',edge='end',offset=.1,optional=True)
        self.actions.sort(key=lambda a:a['start_frame'])

    def default_pose(self,scene,foot):
        mode=str(scene.get('mode',scene.get('scene_id',''))).lower()
        if any(k in mode for k in ('intro','opening','history','outro','comparison','closing')):return 'neutral'
        return 'gaze_left' if foot[0]>960 else ('gaze_right' if foot[0]<960 else 'gaze_up')

    def state(self,time_s,scene=None,foot=(250,1030)):
        scene=scene or {};f=max(0,round(time_s*FPS));default=self.default_pose(scene,foot);i=bisect_right(self.starts,f)-1
        if i<0 or f>=self.actions[i]['end_frame']:return dict(pose=default,action_id=None,keyframe_index=None)
        action=self.actions[i]
        for k,key in enumerate(action['keyframes']):
            if key['start_frame']<=f<key['end_frame']:
                return dict(pose=default if key['pose']=='rest' else key['pose'],action_id=action['id'],keyframe_index=k)
        raise AssertionError(action)

    @lru_cache(maxsize=150)
    def sprite(self,pose,height):
        row=self.poses[pose];im=Image.open(resolve(row['path'])).convert('RGBA');scale=height/row['reference_height_px']
        im=im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.LANCZOS)
        return im,row,scale

    def draw(self,image,time_s,scene=None,*,height=280,foot=(250,1030)):
        state=self.state(time_s,scene,foot);im,row,s=self.sprite(state['pose'],height)
        xy=tuple(round(foot[j]-row['anchor_px'][j]*s) for j in (0,1));b=im.getchannel('A').point(lambda a:255 if a>=8 else 0).getbbox()
        if b is None:raise ValueError('Empty actor drawing')
        box=[b[0]+xy[0],b[1]+xy[1],b[2]+xy[0],b[3]+xy[1]]
        if not (24<=box[0]<box[2]<=1896 and 24<=box[1]<box[3]<=1056):raise ValueError(('Actor clipping',state,box))
        actual=[xy[j]+row['anchor_px'][j]*s for j in (0,1)];delta=[actual[j]-foot[j] for j in (0,1)]
        if any(abs(x)>.5 for x in delta):raise ValueError(('Actor foot alignment',delta))
        image.alpha_composite(im,xy)
        return {**state,'visible_box_xyxy':box,'target_anchor_px':list(foot),'actual_anchor_px':actual,
                'delta_x_px':delta[0],'delta_y_px':delta[1],'tolerance_px':.5,'passed':True,
                'source_path':row['path'],'source_sha256':row['sha256'],'reference_height_px':row['reference_height_px'],
                'display_body_height_px':height,'scale':s,'source_anchor_px':row['anchor_px'],
                'whole_actor_crossfade':False,'source_pixels_modified':False,'per_pose_fit':False,
                'horizontal':'anatomical-foot-x','vertical':'ground-contact-y','not_centering_target':True}

    def receipt(self):
        return dict(registry={'path':local(self.registry_path),'sha256':sha(self.registry_path)},
                    actions=self.actions,source_scope=self.registry['scope'],production_ready=self.registry['production_ready'],
                    source_count=len(self.poses),default_gaze='toward centre based on scene-side foot position',
                    continuous_body_scaling_or_bounce=False,full_actor_crossfade=False)
