"""Render the richer museum guide and one-tile-per-completed-prime wall mosaic.

The accepted teaching canvas, words, timing and encoded AAC packets are reused.
Only the right-hand actor and existing framed wall exhibit change.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, asdict
from functools import lru_cache
import json
import math
from pathlib import Path
import shutil
import subprocess
import time

from PIL import Image, ImageDraw

try:
    import render_prime_video as source
    import render_prime_video_v002 as pipeline
    import kangaroo_animation_v003 as animation
    from build_prime_episode import read,save_new,digest,local,ROOT,VIDEO_NAME
    from component_alignment import raster_centering_report
except ModuleNotFoundError:
    from tools import render_prime_video as source
    from tools import render_prime_video_v002 as pipeline
    from tools import kangaroo_animation_v003 as animation
    from tools.build_prime_episode import read,save_new,digest,local,ROOT,VIDEO_NAME
    from tools.component_alignment import raster_centering_report

FPS=30
OLD=ROOT/'output/prime-counting-001-v002'
OUT=ROOT/'output/prime-counting-001-v003'
stage=pipeline.stage
encode=pipeline.encode
aac_hash=pipeline.aac_hash

PROGRESS_MOSAIC={
    'kind':'one-tile-per-completed-prime-wall-exhibit',
    'panel_inner_xyxy':[1523,320,1795,522],
    'grid_xyxy':[1549,333,1769,509],
    'columns':14,'rows':12,'capacity':168,
    'tile_size_px':[12,11],'gap_px':4,
    'panel_color':'#f8edd7','active_color':'#2d736b','inactive_color':'#f4e9d4',
    'inactive_outline_color':'#d6c4a5',
    'tile_corner_radius_px':1,
    'box_convention':'All xyxy bounds are half-open; raster rectangles stop at right-1,bottom-1.',
    'state_rule':'Number of count-voice end_s timestamps <= current video frame time; row-major fill; zero during introduction;168 after the last prime.',
    'location':'Only the interior of the original right-wall mosaic gold frame; original frame, window and x<1370 teaching canvas retained.',
}


@dataclass(frozen=True)
class Frame:
    mode:str
    value:int|None=None
    diagram_alpha:int=255
    cream:int=0
    pose:str='neutral'
    actor_y:int=0
    completed_primes:int=0


class ProgressMosaic:
    def __init__(self,plan):
        self.voice_ends=sorted(row['end_s'] for row in plan['voice_events'] if row['kind']=='count')
        if len(self.voice_ends)!=168:
            raise ValueError('The wall mosaic must have exactly168 prime voices')
        declared=plan.get('progress_mosaic')
        if declared is not None and declared!=PROGRESS_MOSAIC:
            raise ValueError('Progress geometry differs from the reviewed version')
        self.metadata=deepcopy(PROGRESS_MOSAIC)

    def count(self,index):
        return bisect_right(self.voice_ends,index/FPS+1e-9)

    @lru_cache(maxsize=169)
    def layer(self,count):
        if not 0<=count<=168:
            raise ValueError('Invalid completed-prime progress')
        canvas=Image.new('RGBA',(1920,1080));draw=ImageDraw.Draw(canvas)
        left,top,right,bottom=self.metadata['panel_inner_xyxy']
        draw.rectangle((left,top,right-1,bottom-1),fill=self.metadata['panel_color'])
        grid=Image.new('RGBA',canvas.size);tiles=ImageDraw.Draw(grid)
        gx,gy,_,_=self.metadata['grid_xyxy'];tw,th=self.metadata['tile_size_px'];gap=self.metadata['gap_px']
        for i in range(168):
            x=gx+(i%14)*(tw+gap);y=gy+(i//14)*(th+gap)
            tiles.rounded_rectangle((x,y,x+tw-1,y+th-1),radius=1,
                fill=self.metadata['active_color'] if i<count else self.metadata['inactive_color'],
                outline=self.metadata['active_color'] if i<count else self.metadata['inactive_outline_color'],width=1)
        report=raster_centering_report(grid,self.metadata['panel_inner_xyxy'],name='wall-progress/full-168-cell-grid',tolerance_px=.5)
        if not report['passed']:
            raise ValueError('Wall mosaic is not centered on both axes')
        canvas.alpha_composite(grid)
        return canvas,report

    def draw(self,image,count):
        layer,report=self.layer(count);image.alpha_composite(layer)
        return {**report,'completed_primes':count,'visible_active_tiles':count,'capacity':168}


class Scene(pipeline.Scene):
    def __init__(self,plan,registration=None):
        self.plan=plan;self.base=source.Scene(plan);self.base.character=pipeline.AbsentCharacter()
        self.duration=self.base.duration;self.frame_count=self.base.frame_count
        self.segments=self.base.segments;self.starts=self.base.starts
        receipt=plan.get('kangaroo_animation',{}).get('registration',{})
        registration=registration or receipt.get('path') or animation.DEFAULT_REGISTRATION
        if receipt.get('sha256') and digest(animation.resolve(registration))!=receipt['sha256']:
            raise ValueError('Guide registration differs from measured timeline')
        self.character=animation.Artwork(registration);self.schedule=animation.Schedule(plan,self.character.frames.keys())
        self.progress=ProgressMosaic(plan);self.cream=Image.new('RGBA',source.m.SIZE,source.m.CREAM)
        self.validation=self.base.validation;self.actor_reports={}

    def state(self,index):
        old=self.base.state(index);actor=self.schedule.state(index)
        return Frame(old.mode,old.value,old.diagram_alpha,old.cream,actor.pose,actor.offset_y,self.progress.count(index))

    def image(self,state):
        background,base_report=self.learning_layer(state.mode,state.value,state.diagram_alpha)
        image=background.copy();progress_report=self.progress.draw(image,state.completed_primes)
        actor=animation.ActorState(state.pose,state.actor_y);self.character.draw(image,actor)
        if state.cream:image=Image.blend(image,self.cream,state.cream/255)
        key=(state.pose,state.actor_y)
        actor_report=self.actor_reports.setdefault(key,{'pose':state.pose,'offset_y_px':state.actor_y,
            'visible_bounds_px':self.character.bounds(actor),'foot_root_px':list(self.character.root),
            'source_group_scale':self.character.scales[state.pose],'grounded':state.actor_y==0,
            'support':self.character.support(actor)})
        return image.convert('RGB'),{**base_report,'state':asdict(state),'actor':actor_report,'wall_progress':progress_report}


def prepare_revision(source_timeline,out,registration,source_movie):
    plan=pipeline.prepare_revision(source_timeline,out,registration,source_movie)
    plan['revision_id']='prime-counting-v003';plan['renderer_implementation']='tools/render_prime_video_v003.py'
    plan['progress_mosaic']=deepcopy(PROGRESS_MOSAIC)
    plan['kangaroo_animation']['body_height_px']=animation.BODY_HEIGHT
    plan['kangaroo_animation']['foot_root_px']=list(animation.FOOT_ROOT)
    return plan


def acting_summary(scene):
    poses=Counter(scene.schedule.state(i).pose for i in range(scene.frame_count))
    meaningful=[a for a in scene.schedule.actions if not a.name.startswith('blink-')]
    states={state for action in scene.schedule.actions for state in action.frames}
    reports=[{'pose':state.pose,'offset_y_px':state.offset_y,'bounds':scene.character.bounds(state),
        'support':scene.character.support(state)} for state in sorted(states,key=lambda s:(s.pose,s.offset_y))]
    return {'registered_pose_keys':len(scene.character.frames),'actions':len(scene.schedule.actions),
        'blink_actions':sum(a.name.startswith('blink-') for a in scene.schedule.actions),
        'pose_seconds':{pose:frames/FPS for pose,frames in sorted(poses.items())},
        'meaningful_actor_seconds':sum(frames/FPS for pose,frames in poses.items() if pose not in ('neutral','blink_half','blink_closed')),
        'longest_without_nonblink_action_s':max((b.start_frame-a.end_frame)/FPS for a,b in zip(meaningful,meaningful[1:])),
        'all_actor_states_inside_corridor':True,'measured_actor_states':reports,
        'wall_mosaic_alignment':scene.progress.layer(0)[1]}


def preview(scene,out,ffmpeg):
    actions={a.name:a for a in scene.schedule.actions}
    def start(name):return actions[name].start_frame/FPS
    shots=[('Opening wave',1.0,2.3),('Museum presentation',start('factor-presentation')-.1,2.1),
        ('Milestone applause',start('quarter-clap')-.1,1.5),('Sit, stretch, rest and stand',start('middle-rest')-.1,12.4),
        ('Halfway hop',start('halfway-hop')-.1,1.6),('Closing wave',start('goodbye-wave')-.1,3.1)]
    full=out/'animation-preview.mp4';native=out/'animation-actor-preview.mp4'
    def command(path,size):return [ffmpeg,'-nostdin','-v','error','-n','-f','rawvideo','-pixel_format','rgb24','-video_size',size,'-framerate','30','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(path)]
    thumbs=[]
    with subprocess.Popen(command(full,'960x540'),stdin=subprocess.PIPE) as p,subprocess.Popen(command(native,'550x680'),stdin=subprocess.PIPE) as q:
        for label,at,duration in shots:
            for step in range(round(duration*FPS)):
                frame_index=round(at*FPS)+step;image,_=scene.image(scene.state(frame_index))
                small=image.resize((960,540),Image.Resampling.LANCZOS);p.stdin.write(small.tobytes())
                q.stdin.write(image.crop((1370,400,1920,1080)).tobytes())
                if step in (0,round(duration*FPS)//2):thumbs.append((label,small.copy(),frame_index/FPS))
        p.stdin.close();q.stdin.close()
        if p.wait() or q.wait():raise ValueError('Guide preview encode failed')
    sheet=Image.new('RGB',(1920,math.ceil(len(thumbs)/2)*580),source.m.CREAM);labels=ImageDraw.Draw(sheet)
    for i,(label,img,at) in enumerate(thumbs):
        x,y=i%2*960,i//2*580;sheet.paste(img,(x,y));labels.text((x+12,y+546),f'{label} / {at:.3f}s',font=source.m.font(21),fill=source.m.INK)
    sheet.save(out/'animation-preview-contact-sheet.jpg',quality=92)
    groups=[('standing',['neutral','wave_raise','wave_high','wave_left','wave_right','settle','think_raise','think','aha']),
        ('present-and-clap',['neutral','present_prepare','present_open','present_point','clap_open','clap_near','clap_touch','neutral']),
        ('rest',['neutral','half_seated','seated_neutral','seated_stretch_half','seated_stretch','stand_half','neutral']),
        ('hop',['neutral','posture_neutral','crouch_half','crouch_down','takeoff','hop_air','land','neutral'])]
    sheets=[]
    for name,poses in groups:
        board=Image.new('RGB',(1650,math.ceil(len(poses)/3)*720),source.m.CREAM);draw=ImageDraw.Draw(board)
        underlying=scene.state(round(start('quarter-clap')*FPS))
        for i,pose in enumerate(poses):
            state=Frame(underlying.mode,underlying.value,underlying.diagram_alpha,0,pose,-60 if pose=='hop_air' else 0,underlying.completed_primes)
            image,_=scene.image(state);x,y=i%3*550,i//3*720;board.paste(image.crop((1370,400,1920,1080)),(x,y))
            draw.text((x+12,y+686),pose,font=source.m.font(21),fill=source.m.INK)
        path=out/f'animation-{name}-keyposes-native.png';board.save(path);sheets.append({'path':local(path),'sha256':digest(path),'poses':poses})
    return {'path':local(full),'sha256':digest(full),'fps':30,'silent':True,
        'native_size_actor_preview':{'path':local(native),'sha256':digest(native),'body_height_px':animation.BODY_HEIGHT,'crop':[1370,400,1920,1080]},
        'native_size_keypose_contact_sheets':sheets,
        'clips':[{'name':name,'source_start_s':at,'duration_s':duration} for name,at,duration in shots]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-timeline',type=Path,default=OLD/'timeline.json')
    parser.add_argument('--registration',type=Path,default=animation.DEFAULT_REGISTRATION)
    parser.add_argument('--audio-source',type=Path,default=OLD/VIDEO_NAME)
    parser.add_argument('--out-dir',type=Path,default=OUT)
    parser.add_argument('--ffmpeg',default='ffmpeg');parser.add_argument('--ffprobe',default='ffprobe')
    parser.add_argument('--preset',default='veryfast');parser.add_argument('--crf',type=int,default=18)
    parser.add_argument('--preview-only',action='store_true');parser.add_argument('--skip-preview',action='store_true')
    args=parser.parse_args();out=args.out_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    for filename in ['timeline.json','kangaroo-motion.json','render-record.json',VIDEO_NAME]:
        if (out/filename).exists():raise FileExistsError('Choose a new v003 output folder; existing artifacts are preserved')
    registration=args.registration.resolve();timeline=out/'timeline.json';motion_file=out/'kangaroo-motion.json'
    plan=prepare_revision(args.source_timeline.resolve(),out,registration,args.audio_source.resolve());scene=Scene(plan,registration)
    for action in scene.schedule.actions:
        for state in set(action.frames):scene.character.bounds(state)
    motion={**scene.schedule.receipt(),'artwork':scene.character.receipt(),'progress_mosaic':PROGRESS_MOSAIC,
        'source_timeline':{'path':local(args.source_timeline),'sha256':digest(args.source_timeline)}}
    save_new(motion_file,motion);plan['kangaroo_animation']['schedule']['sha256']=digest(motion_file);save_new(timeline,plan)
    preview_record=None if args.skip_preview else preview(scene,out,args.ffmpeg)
    if args.preview_only:
        save_new(out/'preview-record.json',{'kind':'prime-v003-museum-guide-preview','timeline_sha256':digest(timeline),
            'motion_sha256':digest(motion_file),'artwork':scene.character.receipt(),'preview':preview_record})
        print(json.dumps({'preview':preview_record,'actions':len(scene.schedule.actions)}),flush=True);return
    pipeline.copy_deliveries(out)
    runtime=acting_summary(scene);save_new(out/'animation-runtime-checks.json',runtime)
    begin=time.perf_counter();index,runs,reports=stage(scene,out/'.work/frames-v003')
    save_new(out/'frame-plan.json',{'schema_version':1,'fps':30,'duration_frames':scene.frame_count,
        'timeline_sha256':digest(timeline),'image_directory':local(index.parent),'runs':runs,'distinct_images':len(reports),'images':reports})
    movie=out/VIDEO_NAME;command=encode(index,args.audio_source.resolve(),movie,scene.frame_count,args.ffmpeg,args.preset,args.crf)
    old_audio,new_audio=aac_hash(args.audio_source.resolve(),args.ffmpeg),aac_hash(movie,args.ffmpeg)
    if old_audio!=new_audio:raise ValueError('Accepted AAC packets changed')
    probe=json.loads(subprocess.check_output([args.ffprobe,'-v','error','-show_streams','-show_format','-of','json',str(movie)],text=True))
    record={'schema_version':1,'kind':'prime-museum-guide-v003-render','source_timeline':{'path':local(args.source_timeline),'sha256':digest(args.source_timeline)},
        'timeline':local(timeline),'timeline_sha256':digest(timeline),'motion':local(motion_file),'motion_sha256':digest(motion_file),
        'renderer':local(Path(__file__)),'renderer_sha256':digest(Path(__file__)),'animation_tool_sha256':digest(Path(animation.__file__)),
        'artwork':scene.character.receipt(),'source_character':scene.character.receipt(),'progress_mosaic':PROGRESS_MOSAIC,
        'acting_summary':runtime,
        'frames':scene.frame_count,'duration_s':scene.frame_count/FPS,'distinct_images':len(reports),'holds':len(runs),
        'native_layout_checks_passed':all(r['underlying_layout_passed'] for r in reports),'actor_bounds_passed':True,
        'original_speech_timing_preserved':True,'original_audio_adts_sha256':old_audio,'output_audio_adts_sha256':new_audio,
        'encoded_audio_bitstream_identical':True,'audio_codec_copy':True,'preview':preview_record,'encode_command':command,
        'output':local(movie),'output_sha256':digest(movie),'probe':probe,'elapsed_s':time.perf_counter()-begin}
    save_new(out/'render-record.json',record);print(json.dumps({'output':local(movie),'frames':scene.frame_count,
        'distinct_images':len(reports),'holds':len(runs),'audio_identical':True,'elapsed_s':record['elapsed_s']}),flush=True)


if __name__=='__main__':main()
