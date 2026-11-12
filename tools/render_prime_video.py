"""Render the accepted prime lesson at 1080p30 using repeatable still holds and exact speech timing."""
from __future__ import annotations
import argparse
from bisect import bisect_right
from dataclasses import dataclass,asdict
from functools import lru_cache
from itertools import groupby
import json
import math
from pathlib import Path
import subprocess
import time

from PIL import Image,ImageDraw,ImageOps
try:
    import render_prime_mockups as m
    from build_prime_episode import read,save_new,digest,local,validate,VIDEO_NAME,ROOT
except ModuleNotFoundError:
    from tools import render_prime_mockups as m
    from tools.build_prime_episode import read,save_new,digest,local,validate,VIDEO_NAME,ROOT

FPS=30

@dataclass(frozen=True)
class Frame:
    mode:str
    value:int|None=None
    diagram_alpha:int=255
    cream:int=0

class ProductionCanvas(m.Canvas):
    def __init__(self,background,name,diagram_alpha):
        super().__init__(background,name);self.diagram_alpha=diagram_alpha
    def tiles(self,*args,**kwargs):
        kwargs['opacity']=kwargs.get('opacity',1)*self.diagram_alpha/255
        return super().tiles(*args,**kwargs)


def definition(c):
    m.exhibit(c)
    c.centered('WHAT IS A PRIME?',(145,284,1285,341),48,m.TEAL,'definition-heading')
    c.centered('GREATER THAN 1',(150,401,1280,483),62,m.INK,'definition-greater')
    c.centered('EXACTLY TWO POSITIVE FACTORS',(120,553,1310,613),43,m.TEAL,'definition-two')
    c.centered('1 AND ITSELF',(150,672,1280,758),68,m.INK,'definition-factors')
    c.centered('A factor divides evenly, with no remainder.',(125,822,1305,878),34,m.MUTED,'definition-factor-meaning')
    c.centered('EXAMPLE: 5 has factors 1 and 5.',(150,923,1280,967),32,m.TEAL,'definition-example')

class Scene:
    def __init__(self,plan):
        self.plan=plan;self.duration=plan['duration_s'];self.frame_count=plan['duration_frames'];self.segments=plan['visual_segments'];self.starts=[s['start_s'] for s in self.segments]
        if plan['fps']!=30 or self.frame_count!=math.ceil(self.duration*30-1e-8):raise ValueError('Timeline not on correct30fps grid')
        self.validation=validate(plan)
        with Image.open(m.BACKGROUND) as src:self.background=ImageOps.fit(src.convert('RGBA'),m.SIZE,Image.Resampling.LANCZOS)
        self.character=m.Kangaroo();self.cream=Image.new('RGBA',m.SIZE,m.CREAM)

    def state(self,index):
        if not 0<=index<self.frame_count:raise IndexError(index)
        t=index/FPS+1e-9;seg=self.segments[bisect_right(self.starts,t)-1]
        opacity=1
        fi=seg.get('diagram_fade_in_s',0);fo=seg.get('diagram_fade_out_s',0)
        if fi:opacity=min(opacity,(t-seg['start_s'])/fi)
        if fo:opacity=min(opacity,(seg['end_s']-t)/fo)
        cream=0
        if t<.8:cream=round(255*(1-t/.8))
        elif t>=self.duration-2:
            last=(self.frame_count-1)/FPS;cream=round(255*(t-self.duration+2)/(last-self.duration+2))
        return Frame(seg['mode'],seg.get('value'),max(0,min(255,round(opacity*255))),max(0,min(255,cream)))

    def image(self,state):
        name=f'{state.mode}-{state.value}-{state.diagram_alpha}-{state.cream}'
        c=ProductionCanvas(self.background,name,state.diagram_alpha)
        self.character.draw(c.image)
        teaching=state.mode in ('definition','comparison','rotation','one','nine','bridge')
        m.header(c,'TEACHING EXAMPLE · THE MOSAIC MUSEUM' if teaching else 'THE SUNLIT MOSAIC MUSEUM')
        if state.mode=='definition':definition(c)
        elif state.mode=='opening':m.opening(c)
        elif state.mode=='count':m.count(c,state.value)
        elif state.mode=='comparison':m.comparison(c)
        elif state.mode=='rotation':m.rotation(c)
        elif state.mode=='one':m.one(c)
        elif state.mode=='nine':m.nine(c)
        elif state.mode=='bridge':m.bridge(c)
        elif state.mode=='finale':m.finale(c)
        else:raise ValueError(state)
        image=Image.blend(c.image,self.cream,state.cream/255) if state.cream else c.image
        return image.convert('RGB'),{'state':asdict(state),'components':c.records,'diagrams':c.diagrams,'intended_alignment_tolerance_px':.5,'underlying_layout_passed':all(r['passed'] for r in c.records),'whole_frame_fade':bool(state.cream)}


def stage(scene,folder):
    folder.mkdir(parents=True,exist_ok=False);cache={};runs=[];reports=[];lines=['ffconcat version1.0'];end=0
    # The concat parser requires this exact header spelling.
    lines[0]='ffconcat version 1.0'
    for state,group in groupby(scene.state(i) for i in range(scene.frame_count)):
        if state not in cache:
            name=f'frame-{len(cache):04d}.png';im,report=scene.image(state);im.save(folder/name,compress_level=1);cache[state]=name
            report.update(file=name,sha256=digest(folder/name));reports.append(report)
            if len(cache)%50==0:print(json.dumps({'staged_images':len(cache),'at_frame':end}),flush=True)
        name=cache[state];start=end;end+=sum(1 for _ in group);us=round(end*1e6/FPS)-round(start*1e6/FPS)
        lines.extend((f"file '{name}'",f'option framerate {FPS}',f'duration {us/1e6:.6f}'))
        runs.append({'start_frame':start,'end_frame':end,'frame_count':end-start,'start_s':start/FPS,'end_s':end/FPS,'file':name,**asdict(state)})
    if end!=scene.frame_count:raise ValueError('Frame plan incomplete')
    lines.extend((f"file '{name}'",f'option framerate {FPS}'))
    index=folder/'frames.ffconcat';index.write_text('\n'.join(lines)+'\n',encoding='ascii')
    return index,runs,reports


def encode(index,audio,output,frames,ffmpeg,preset,crf):
    filters=f'scale=in_range=full:out_range=limited:out_color_matrix=bt709,setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709,fps={FPS},trim=end_frame={frames}'
    command=[ffmpeg,'-hide_banner','-loglevel','warning','-stats','-stats_period','10','-nostdin','-n','-f','concat','-safe','0','-i',str(index),'-i',str(audio),'-map','0:v:0','-map','1:a:0','-vf',filters,'-c:v','libx264','-preset',preset,'-crf',str(crf),'-pix_fmt','yuv420p','-color_range','tv','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-movflags','+faststart',str(output)]
    with output.with_suffix('.ffmpeg.log').open('x') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    return command


def previews(scene,out):
    folder=out/'previews';folder.mkdir(exist_ok=False);shots=[];seen=set()
    for seg in scene.segments:
        key=(seg['mode'],seg.get('value'))
        if key[0]=='count' and key[1] not in (2,3,97,101,773,997):continue
        if key in seen:continue
        seen.add(key);t=min(seg['end_s']-.1,seg['start_s']+max(.6,min(2,(seg['end_s']-seg['start_s'])/2)))
        index=min(scene.frame_count-1,math.ceil(t*FPS));state=scene.state(index);im,_=scene.image(state);name=f'{len(shots)+1:02d}-{state.mode}-{state.value or "example"}.png';im.save(folder/name);shots.append((im,name,t))
    cols=3;rows=math.ceil(len(shots)/cols);sheet=Image.new('RGB',(1920,rows*398),m.CREAM);draw=ImageDraw.Draw(sheet)
    for i,(im,name,t) in enumerate(shots):
        x=(i%cols)*640;y=(i//cols)*398;sheet.paste(im.resize((624,351),Image.Resampling.LANCZOS),(x+8,y+8));draw.text((x+15,y+369),f'{t:.2f}s  {name}',font=m.font(18),fill=m.INK,anchor='lt')
    sheet.save(out/'production-contact-sheet.jpg',quality=92)
    # The posterior is a pure count state, never an intermediate fade.
    im,_=scene.image(Frame('count',101));im.save(out/'poster.png')
    return [{'file':local(folder/n),'time_s':t} for _,n,t in shots]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--timeline',type=Path,default=ROOT/'output/prime-counting-001-v001/timeline.json');p.add_argument('--out-dir',type=Path);p.add_argument('--ffmpeg',default='ffmpeg');p.add_argument('--ffprobe',default='ffprobe');p.add_argument('--preset',default='veryfast');p.add_argument('--crf',type=int,default=18);p.add_argument('--stage-only',action='store_true');a=p.parse_args()
    timeline=a.timeline.resolve();plan=read(timeline);out=(a.out_dir or timeline.parent).resolve();out.mkdir(parents=True,exist_ok=True)
    if 'master_audio' not in plan and not a.stage_only:raise ValueError('Timeline has no accepted mixed master')
    if not a.stage_only:
        for key in ('speech_manifest','speech_acceptance'):
            receipt=plan[key];source=Path(receipt['path']);source=source if source.is_absolute() else ROOT/source
            if digest(source)!=receipt['sha256']:raise ValueError(f'Bound speech record changed: {key}')
    audio=ROOT/plan.get('master_audio',{}).get('path','')
    if not a.stage_only and digest(audio)!=plan['master_audio']['sha256']:raise ValueError('Master audio changed')
    destination=out/VIDEO_NAME
    for path in (destination,out/'render-record.json',out/'frame-plan.json'):
        if path.exists():raise FileExistsError(f'Refusing to overwrite {path}')
    begin=time.perf_counter();scene=Scene(plan);framesdir=out/'.work'/'frames-v001';index,runs,reports=stage(scene,framesdir)
    save_new(out/'frame-plan.json',{'schema_version':1,'fps':FPS,'duration_frames':scene.frame_count,'timeline_sha256':digest(timeline),'image_directory':local(framesdir),'runs':runs,'distinct_images':len(reports),'images':reports,'progress_policy':'Ordinal PRIME n OF168 during the counting run; a completed168tile mosaic at the finale. This keeps the approved number/factor layout legible; no continuously growing mosaic is implied.','transition_policy':'Instant silent-gap layout cuts; diagram-only0.4sec fades preserve labels and exact tile geometry; opening0.8sec and final2sec cream fades.'})
    preview=previews(scene,out)
    command=None
    if not a.stage_only:command=encode(index,audio,destination,scene.frame_count,a.ffmpeg,a.preset,a.crf)
    record={'schema_version':1,'kind':'prime-video-render-record','stage_only':a.stage_only,'timeline':local(timeline),'timeline_sha256':digest(timeline),'renderer':local(Path(__file__)),'renderer_sha256':digest(Path(__file__)),'mockup_adapter_sha256':digest(Path(m.__file__)),'frame_plan':local(out/'frame-plan.json'),'frame_plan_sha256':digest(out/'frame-plan.json'),'frames':scene.frame_count,'duration_s':scene.frame_count/FPS,'distinct_images':len(reports),'holds':len(runs),'native_layout_checks_passed':all(r['underlying_layout_passed'] for r in reports),'source_character':scene.character.receipt(),'sources':[{'path':local(q),'sha256':digest(q)} for q in (m.BACKGROUND,m.FONT)],'previews':preview,'encode_command':command,'elapsed_s':time.perf_counter()-begin,'output':local(destination) if destination.exists() else None,'output_sha256':digest(destination) if destination.exists() else None,'progress_policy':'Ordinal progress with final168tile mosaic, no persistent mini grid; no background/SFX/character loops.'}
    if destination.exists():
        record['probe']=json.loads(subprocess.check_output([a.ffprobe,'-v','error','-show_streams','-show_format','-of','json',str(destination)],text=True))
    save_new(out/'render-record.json',record);print(json.dumps({'output':str(destination),'frames':scene.frame_count,'distinct_images':len(reports),'layout_passed':record['native_layout_checks_passed'],'elapsed_s':record['elapsed_s']}),flush=True)

if __name__=='__main__':main()
