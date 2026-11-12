"""Independently verify the Fibonacci v002 character motion and source bindings.

No producer or renderer is imported. Adopted RGBA files are projected using the
registered body reference and foot anchor, then compared with decoded pixels.
Motion plans bind the immutable audio-build timeline, avoiding a hash cycle.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat, ImageMath

ROOT = Path(__file__).resolve().parents[1]
SIZE = (1920,1080)
FPS = 30
BODY_HEIGHT = 400
FOOT = (1655,990)
ACTOR_ROI = (1390,400,1910,1040)
PROTECTED = ((70,60,1380,1040),(1420,60,1890,150))
BACKGROUND = ROOT/'assets/library/worlds/cloud-post-office/backgrounds/v001/cloud-post-office-background.png'
BASE_FIELDS = ('events','voice_events','counted_states','visual_segments','scenes','duration_s',
               'duration_frames','fps','width','height','count_index_start','count_index_end',
               'count_start','count_end','counted_values','voice_sum_s','source_script',
               'audio','master','master_audio','speech_manifest','speech_acceptance','timing')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def local_path(value):
    path=Path(value)
    return path if path.is_absolute() else ROOT/path


def receipt(path):
    path=Path(path)
    return {'path':str(path.resolve()),'sha256':sha(path),'bytes':path.stat().st_size}


def frame_at(at):
    return math.ceil(at*FPS-1e-7)


def document_reference(reference, label):
    require(isinstance(reference,dict) and reference.get('path') and reference.get('sha256'),f'Missing {label} path/SHA binding')
    path=local_path(reference['path'])
    require(sha(path)==reference['sha256'],f'Changed {label}: {path}')
    return path,json.loads(path.read_text())


def validate_base_binding(top, motion, motion_path):
    base_path,base=document_reference(top.get('source_timeline'),'immutable audio-build timeline')
    require(top.get('renderer_implementation')=='tools/render_fibonacci_video_v002.py','Unexpected v002 renderer implementation')
    for field in BASE_FIELDS:
        require(top.get(field)==base.get(field),f'Character motion changed base {field}')
    declared=top.get('character_motion')
    require(isinstance(declared,dict) and declared.get('sha256')==sha(motion_path),'Top timeline does not bind this exact motion plan')
    require(sha(local_path(declared['path']))==sha(motion_path),'Top timeline motion path points to different bytes')
    motion_base_path,motion_base=document_reference(motion.get('source_timeline'),'motion audio-build timeline')
    require(sha(motion_base_path)==sha(base_path) and motion_base==base,'Motion/top timelines bind different audio bases')
    require(top['fps']==FPS and top['duration_frames']==frame_at(top['duration_s']),'Invalid motion frame grid')
    require((top.get('width'),top.get('height'))==SIZE,'Character placement requires1920x1080')
    require(top['counted_states'][31]['value']==1346269 and top['counted_states'][30]['value']==832040,'Million reaction target is not the first term above one million')
    return base,{'passed':True,'source_timeline':receipt(base_path),
                 'exactly_compared_fields':list(BASE_FIELDS),
                 'hash_graph':'audio-build base -> motion -> top -> rendered video -> QA; no top hash inside motion'}


def registered_entries(motion):
    reference=motion.get('registry',motion.get('pose_registry',motion.get('registration')))
    path,registry=document_reference(reference,'character pose registry')
    raw=registry.get('frames',registry.get('poses'))
    require(isinstance(raw,(list,dict)) and raw,'Pose registry is empty')
    if isinstance(raw,dict):
        rows=[dict(value,id=key) for key,value in raw.items()]
    else:
        rows=raw
    # Explicit extra adopted rows are useful for neutral/legacy poses without
    # silently following the shared library's later active-pose selection.
    snapshots=motion.get('poses')
    if isinstance(snapshots,dict) and snapshots:
        snapshot_rows={key:dict(value,id=key) for key,value in snapshots.items()}
        for row in rows:
            require(row['id'] in snapshot_rows,f'Motion snapshot omits registered pose {row["id"]}')
            for field in ('path','sha256','anchor_px','reference_height_px','eyes_closed'):
                require(snapshot_rows[row['id']].get(field)==row.get(field),f'Motion snapshot changed registered {row["id"]}/{field}')
        rows=list(snapshot_rows.values())
    else:
        extra=motion.get('pose_sources',{})
        if isinstance(extra,dict):
            rows=list(rows)+[dict(value,id=key) for key,value in extra.items()]
    result={}
    for original in rows:
        row=dict(original)
        ident=row['id']
        require(ident not in result,f'Duplicate registered pose {ident}')
        row['reference_height_px']=row.get('reference_height_px',registry.get('common_reference_height_px'))
        require(row.get('reference_height_px',0)>0 and len(row.get('anchor_px',[]))==2,f'Missing body/foot registration {ident}')
        require(isinstance(row.get('eyes_closed'),bool),f'Missing reviewed eyes_closed metadata {ident}')
        source=local_path(row['path'])
        require(sha(source)==row['sha256'],f'Changed adopted pose {ident}')
        result[ident]=row
    return result,{'registry':receipt(path),'pose_count':len(result)}


def keyframe_time(row):
    return row.get('at_s',row.get('time_s'))


def keyframe_pose(row):
    return row.get('pose_id',row.get('pose'))


def window_kind(row):
    return str(row.get('kind',row.get('id','')))


def validate_windows(plan, motion, poses):
    windows=motion.get('windows')
    require(isinstance(windows,list) and windows,'No character motion windows')
    require(len({w['id'] for w in windows})==len(windows),'Duplicate motion window IDs')
    require(motion.get('body_height_px',BODY_HEIGHT)==BODY_HEIGHT,'Motion changed established body scale')
    require(tuple(motion.get('ground_foot_anchor_px',motion.get('foot_anchor_px',FOOT)))==FOOT,'Motion changed established foot support')
    ordered=sorted(windows,key=lambda row:row['start_s'])
    prior_end=-1
    for window in ordered:
        start,end=window['start_s'],window['end_s']
        require(0<=start<end<=plan['duration_s'],'Motion window outside video')
        require(start>=prior_end-1e-9,'Overlapping whole-character windows')
        prior_end=end
        require(window.get('start_frame',frame_at(start))==frame_at(start) and
                window.get('end_frame',frame_at(end))==frame_at(end),'Motion frame/time mismatch')
        keys=window.get('keyframes',[])
        times=[keyframe_time(k) for k in keys]
        require(len(keys)>=2 and all(isinstance(t,(int,float)) for t in times),'Motion needs timed keyframes')
        require(times==sorted(set(times)) and abs(times[0]-start)<1e-7 and times[-1]<=end,'Keyframes do not begin/advance within their window')
        if all('hold_frames' in key for key in keys):
            cursor=frame_at(start)
            for key in keys:
                require(key.get('at_frame',frame_at(keyframe_time(key)))==cursor and
                        frame_at(keyframe_time(key))==cursor and isinstance(key['hold_frames'],int) and key['hold_frames']>0,
                        'Held keyframes do not cover consecutive frames')
                cursor+=key['hold_frames']
            require(cursor==frame_at(end),'Held keys do not cover the complete motion window')
        else:
            require(abs(times[-1]-end)<1e-7,'Interpolated keys do not reach their window endpoint')
        require(all(keyframe_pose(k) in poses for k in keys),'Keyframe references an unregistered pose')
        require(all(not k.get('offset_xy') or k['offset_xy']==[0,0] for k in keys),'Unsupported per-keyframe positional offset')
        for key in keys:
            interpolation=key.get('interpolation',window.get('interpolation','hold'))
            name=interpolation.get('kind',interpolation.get('method')) if isinstance(interpolation,dict) else interpolation
            require(name in ('hold','linear','smoothstep'),'Unsupported declared interpolation')
        if 'wave' in window_kind(window):
            require(window.get('wave_cycles',0)>=1,'Wave window has no declared complete cycle')
            hashes={poses[keyframe_pose(k)]['sha256'] for k in keys}
            require(len(hashes)>=3,'A held greeting is not a wave with intermediate poses')
    by_id={event['id']:event for event in plan['voice_events']}
    opening=[w for w in windows if w['id']=='opening-wave' and 'wave' in window_kind(w)]
    goodbye=[w for w in windows if w['id']=='goodbye-wave' and 'wave' in window_kind(w)]
    million=[w for w in windows if w['id']=='million-notice']
    require(len(opening)==len(goodbye)==len(million)==1,'Required opening/goodbye waves and first-million reaction must each occur once')
    require(abs(opening[0]['start_s']-.9)<1/FPS and abs(opening[0]['end_s']-2.7)<1/FPS,'Opening wave is outside the agreed window')
    require(by_id['O04']['start_s']<=goodbye[0]['start_s']<goodbye[0]['end_s']<=by_id['O04']['end_s'],'Goodbye wave is outside its utterance')
    require(by_id['N031']['end_s']<=million[0]['start_s']<million[0]['end_s']<=by_id['E032']['start_s'],'First-million reaction is premature or intrudes into next expression')
    return ordered,{'passed':True,'windows':len(windows),'opening_wave_count':1,'goodbye_wave_count':1,'first_million_reaction_count':1}


def project_pose(row, body_height=BODY_HEIGHT, foot=FOOT):
    image=Image.open(local_path(row['path'])).convert('RGBA')
    source_bounds=image.getchannel('A').point(lambda x:255 if x>=8 else 0).getbbox()
    require(source_bounds is not None,f'Empty adopted RGBA {row["id"]}')
    scale=body_height/row['reference_height_px']
    scaled=image.resize((round(image.width*scale),round(image.height*scale)),Image.Resampling.LANCZOS)
    alpha=scaled.getchannel('A').point(lambda x:255 if x>=8 else 0)
    bounds=alpha.getbbox()
    origin=tuple(round(a-b*scale) for a,b in zip(foot,row['anchor_px']))
    projected=tuple(bounds[i]+origin[i%2] for i in range(4))
    canvas=Image.new('RGBA',SIZE)
    canvas.alpha_composite(scaled,origin)
    source_mask=alpha
    frame_mask=canvas.getchannel('A').point(lambda x:255 if x>=8 else 0)
    lost=source_mask.histogram()[255]-frame_mask.histogram()[255]
    overlap=[]
    for rectangle in PROTECTED:
        overlap.append({'protected_box_xyxy':list(rectangle),'overlap_pixels':frame_mask.crop(rectangle).histogram()[255]})
    touching_source_edge=source_bounds[0]==0 or source_bounds[1]==0 or source_bounds[2]==image.width or source_bounds[3]==image.height
    contained=0<=projected[0]<projected[2]<=SIZE[0] and 0<=projected[1]<projected[3]<=SIZE[1]
    report={'pose_id':row['id'],'source_sha256':row['sha256'],'source_visible_box_alpha8':list(source_bounds),
            'source_touches_edge_alpha8':touching_source_edge,'source_alpha_max':image.getchannel('A').getextrema()[1],
            'body_reference_height_px':row['reference_height_px'],'target_body_height_px':body_height,
            'isotropic_scale':scale,'foot_anchor_px':list(foot),'paste_origin_xy':list(origin),
            'projected_visible_box_xyxy':list(projected),'out_of_frame_visible_pixels':lost,
            'protected_regions':overlap,'eyes_closed':row['eyes_closed'],
            'passed':contained and not touching_source_edge and lost==0 and not any(r['overlap_pixels'] for r in overlap)}
    return canvas,report


def interpolate(window, at):
    keys=window['keyframes'];times=[keyframe_time(k) for k in keys]
    if at<=times[0]:return keyframe_pose(keys[0]),keyframe_pose(keys[0]),0.
    if at>=times[-1]:return keyframe_pose(keys[-1]),keyframe_pose(keys[-1]),0.
    index=bisect_right(times,at)-1
    fraction=(at-times[index])/(times[index+1]-times[index])
    specification=keys[index].get('interpolation',window.get('interpolation','hold'))
    method=specification.get('kind',specification.get('method')) if isinstance(specification,dict) else specification
    if method=='hold':fraction=0.
    elif method=='smoothstep':fraction=fraction*fraction*(3-2*fraction)
    steps=specification.get('steps') if isinstance(specification,dict) else None
    if steps:fraction=round(fraction*steps)/steps
    return keyframe_pose(keys[index]),keyframe_pose(keys[index+1]),fraction


def excursion_count(values, low=.30, high=.70):
    """Completed low-high-low excursions, with hysteresis against codec noise."""
    phase=0;cycles=0
    for value in values:
        if phase==0 and value<=low:phase=1
        elif phase==1 and value>=high:phase=2
        elif phase==2 and value<=low:cycles+=1;phase=1
    return cycles


def mae(actual, expected, mask):
    return sum(ImageStat.Stat(ImageChops.difference(actual,expected),mask).mean)/3


def missing_opaque_core(actual, expected, backdrop):
    """Find connected loss of strongly visible character ink, not AA noise.

    BT709 luma preserves spatial resolution in a4:2:0 movie. Pixels whose
    expected contrast is >=64/255 must retain at least half that contrast.
    Clipping a small paw can evade a whole-character mean-error threshold, so
    contiguous missing-core clusters are measured separately.
    """
    def luma(image):
        channels={f'c{i}':c.convert('F') for i,c in enumerate(image.split())}
        return ImageMath.lambda_eval(lambda d:d['c0']*.2126+d['c1']*.7152+d['c2']*.0722,**channels)
    a,e,b=luma(actual),luma(expected),luma(backdrop)
    mask=ImageMath.lambda_eval(lambda d:(((d['e']-d['b'])*(d['e']-d['b'])>=64*64)*
        ((d['a']-d['b'])*(d['e']-d['b'])<.5*(d['e']-d['b'])*(d['e']-d['b'])))*255,a=a,e=e,b=b).convert('L')
    width=mask.width;points={i for i,v in enumerate(mask.tobytes()) if v}
    count=len(points);largest=0
    while points:
        seed=points.pop();stack=[seed];area=1
        while stack:
            i=stack.pop();x=i%width
            neighbors=[i-width,i+width]
            if x:neighbors.append(i-1)
            if x+1<width:neighbors.append(i+1)
            for j in neighbors:
                if j in points:points.remove(j);stack.append(j);area+=1
        largest=max(largest,area)
    return {'missing_high_contrast_pixels':count,'largest_missing_connected_component_px':largest,
            'minimum_expected_luma_contrast':64,'minimum_retained_contrast_fraction':.5,
            'maximum_missing_cluster_px':16,'passed':largest<=16}


def static_pose_at(plan, at):
    segments=plan['visual_segments'];starts=[s['start_s'] for s in segments]
    segment=segments[bisect_right(starts,at+1e-9)-1]
    mode,n=segment['mode'],segment.get('index')
    if mode=='finale':return 'neutral'
    if mode=='opening':
        end=next(e['start_s']-.12 for e in plan['voice_events'] if e['id']=='I08')
        return 'watch_left' if at>=end else 'neutral'
    if mode in ('count','legend'):return 'watch_left' if mode=='legend' or (n or 0)>=2 else 'neutral'
    if mode=='rule':
        elapsed=at-segment['start_s'];length=segment['end_s']-segment['start_s']
        if elapsed<.4 or elapsed>length-.25:return 'watch_left'
        return 'present_half' if elapsed<.65 or elapsed>length-.5 else 'present_full'
    if mode=='replay':
        if n==2:return 'think'
        begin=min(s['start_s'] for s in segments if s['mode']=='replay' and s['index']==n)
        elapsed=at-begin
        if elapsed<.4:return 'watch_left'
        if elapsed<.7:return 'present_half'
        if elapsed<2.2:return 'present_full'
        if elapsed<2.5:return 'present_half'
        return 'watch_left'
    return 'neutral'


def motion_support(images):
    require(len(images)>=2,'No distinct keyframe images')
    variation=Image.new('L',images[0].size)
    for image in images[1:]:
        channels=ImageChops.difference(images[0],image).split()
        distance=ImageChops.lighter(channels[0],ImageChops.lighter(channels[1],channels[2]))
        variation=ImageChops.lighter(variation,distance)
    return variation.point(lambda x:255 if x>=12 else 0).filter(ImageFilter.MaxFilter(3))


def projection_model(low, high, mask):
    lo,hi=low.tobytes(),high.tobytes();m=mask.tobytes();width=mask.width
    indices=[(y*width+x)*3+c for y in range(0,mask.height,3) for x in range(0,width,3)
             if m[y*width+x] for c in range(3)]
    reference=[lo[i] for i in indices];direction=[hi[i]-lo[i] for i in indices]
    energy=sum(d*d for d in direction)
    require(energy>1000,'Key poses do not establish visible motion')
    return indices,reference,direction,energy


def projection(image, model):
    indices,reference,direction,energy=model;data=image.tobytes()
    return sum((data[i]-a)*d for i,a,d in zip(indices,reference,direction))/energy


def decoded_actor_frames(video, ffmpeg, log, frame_count):
    x1,y1,x2,y2=ACTOR_ROI;width,height=x2-x1,y2-y1
    command=[ffmpeg,'-nostdin','-v','error','-xerror','-i',str(video),'-an','-vf',
             f'crop={width}:{height}:{x1}:{y1},format=rgb24','-fps_mode','passthrough','-f','rawvideo','pipe:1']
    with Path(log).open('x') as errors,subprocess.Popen(command,stdout=subprocess.PIPE,stderr=errors) as process:
        for frame in range(frame_count):
            data=process.stdout.read(width*height*3)
            require(len(data)==width*height*3,f'Actor decode EOF at frame{frame}')
            yield frame,Image.frombytes('RGB',(width,height),data)
        require(not process.stdout.read(1),'Actor decode has extra frames')
        require(process.wait()==0,'Actor video decode failed')


def decoded_motion_checks(video, plan, windows, poses, layers, ffmpeg, directory):
    plate=ImageOps.fit(Image.open(BACKGROUND).convert('RGBA'),SIZE,Image.Resampling.LANCZOS)
    shadow=Image.new('RGBA',SIZE)
    ImageDraw.Draw(shadow).ellipse((1530,977,1815,1007),fill=(74,88,89,22))
    plate.alpha_composite(shadow)
    pictures={};body_mask=Image.new('L',(ACTOR_ROI[2]-ACTOR_ROI[0],ACTOR_ROI[3]-ACTOR_ROI[1]))
    for ident,layer in layers.items():
        composite=plate.copy();composite.alpha_composite(layer)
        pictures[ident]=composite.convert('RGB').crop(ACTOR_ROI)
        support=layer.getchannel('A').crop(ACTOR_ROI).point(lambda x:255 if x>=8 else 0)
        body_mask=ImageChops.lighter(body_mask,support)
    summaries={};models={}
    for window in windows:
        ids=list(dict.fromkeys(keyframe_pose(k) for k in window['keyframes']))
        images=[pictures[ident] for ident in ids];support=motion_support(images)
        require(support.histogram()[255]>=100,f'Window{window["id"]} has no visible pose change')
        if 'wave' in window_kind(window):
            require('wave_in' in ids and 'wave_out' in ids,'Wave must contain both reviewed in/out extremes')
            low,high=pictures['wave_in'],pictures['wave_out']
            projection_support=motion_support([low,high])
            basis=['wave_in','wave_out']
        else:
            low=images[0];high=max(images[1:],key=lambda image:mae(low,image,support))
            projection_support=support;basis=[ids[0],'maximally-different-reaction-pose']
        models[window['id']]={'support':support,'projection':projection_model(low,high,projection_support),
                             'expected_peak_mae':mae(low,high,support)}
        summaries[window['id']]={'id':window['id'],'kind':window_kind(window),'decoded_samples':[],
                                 'source_pose_ids':ids,'motion_support_pixels':support.histogram()[255],
                                 'projection_basis_pose_ids':basis,'projection_support_pixels':projection_support.histogram()[255],
                                 'expected_peak_mae_rgb':mae(low,high,support)}
    cached={};core_cache={};outside=[];errors=[];closed_run=longest_closed=0;unknown_run=longest_unknown=0
    backdrop=plate.convert('RGB').crop(ACTOR_ROI)
    sample_frames={}
    for window in windows:
        sample_frames[window['id']]={frame_at(window['start_s']),frame_at(window['end_s'])-1,
             frame_at(window['start_s'])-1,frame_at(window['end_s']),
             frame_at((window['start_s']+window['end_s'])/2),*(frame_at(keyframe_time(k)) for k in window['keyframes'])}
    for frame,image in decoded_actor_frames(video,ffmpeg,directory/'actor-decode.log',plan['duration_frames']):
        at=frame/FPS+1e-9
        window=next((w for w in windows if w['start_s']<=at<w['end_s']),None)
        boundary=False
        if window is None:
            window=next((w for w in windows if frame in (frame_at(w['start_s'])-1,frame_at(w['end_s']))),None)
            boundary=window is not None
        if at<.8 or at>=plan['duration_s']-2:
            continue
        if window:
            if boundary:
                first=second=window.get('return_pose_id',keyframe_pose(window['keyframes'][-1]));weight=0.
            else:
                first,second,weight=interpolate(window,at)
            expected=Image.blend(pictures[first],pictures[second],weight)
            model=models[window['id']]
            body_error=mae(image,expected,body_mask);motion_error=mae(image,expected,model['support'])
            observed=projection(image,model['projection']);predicted=projection(expected,model['projection'])
            fingerprint=hashlib.sha256(image.tobytes()).digest()
            core_key=(fingerprint,first,second,weight)
            if core_key not in core_cache:core_cache[core_key]=missing_opaque_core(image,expected,backdrop)
            core=core_cache[core_key]
            match=body_error<=6 and motion_error<=8 and abs(observed-predicted)<=.25 and core['passed']
            record={'frame':frame,'at_s':frame/FPS,'poses':[first,second],'blend_weight':weight,
                    'boundary_return_sample':boundary,
                    'body_mae_rgb':body_error,'motion_mae_rgb':motion_error,
                    'strong_ink_visibility':core,
                    'observed_projection':observed,'expected_projection':predicted,'passed':match}
            summaries[window['id']]['decoded_samples'].append(record)
            if not match:errors.append(f'Frame{frame}: registered motion does not match decoded character')
            closed=(1-weight)*poses[first]['eyes_closed']+weight*poses[second]['eyes_closed']>=.5
            uncertain=False
            if frame in sample_frames[window['id']]:
                image.save(directory/f'{window["id"]}-frame-{frame:06d}.png')
        else:
            fingerprint=hashlib.sha256(image.tobytes()).digest()
            if fingerprint not in cached:
                scores=[(mae(image,picture,body_mask),ident) for ident,picture in pictures.items()]
                score,ident=min(scores)
                open_score=min((s for s,i in scores if not poses[i]['eyes_closed']),default=1e9)
                closed_score=min((s for s,i in scores if poses[i]['eyes_closed']),default=1e9)
                cached[fingerprint]=(score,ident,closed_score+.10<open_score,abs(open_score-closed_score)<.10)
            score,ident,closed,uncertain=cached[fingerprint]
            expected_id=static_pose_at(plan,at)
            require(expected_id in pictures,f'Unregistered educational pose{expected_id}')
            expected_error=mae(image,pictures[expected_id],body_mask)
            core_key=(fingerprint,expected_id)
            if core_key not in core_cache:core_cache[core_key]=missing_opaque_core(image,pictures[expected_id],backdrop)
            core=core_cache[core_key]
            if score>6 or expected_error>6 or not core['passed']:
                errors.append(f'Frame{frame}: outside-window character differs from educational pose or loses visible ink')
            if frame%30==0:outside.append({'frame':frame,'best_pose':ident,'expected_pose':expected_id,'mae_rgb':score,
                                         'expected_pose_mae_rgb':expected_error,'strong_ink_visibility':core,
                                         'eyes_closed':closed,'uncertain':uncertain})
        closed_run=closed_run+1 if closed else 0;longest_closed=max(longest_closed,closed_run)
        unknown_run=unknown_run+1 if uncertain else 0;longest_unknown=max(longest_unknown,unknown_run)
    for window in windows:
        summary=summaries[window['id']];samples=summary['decoded_samples']
        require(samples,f'No decoded frames in required window{window["id"]}')
        observed=[r['observed_projection'] for r in samples]
        expected=[r['expected_projection'] for r in samples]
        observed_cycles=excursion_count(observed);expected_cycles=excursion_count(expected)
        variation=max(observed)-min(observed);expected_variation=max(expected)-min(expected)
        summary.update(observed_excursions=observed_cycles,expected_excursions=expected_cycles,
                       observed_projection_range=variation,expected_projection_range=expected_variation)
        moving=variation>=.45*expected_variation and variation>=.45
        if 'wave' in window_kind(window):
            moving=moving and expected_cycles>=window.get('wave_cycles',1) and observed_cycles>=window.get('wave_cycles',1)
        summary['passed']=moving and all(row['passed'] for row in samples)
        if not summary['passed']:errors.append(f'Window{window["id"]}: decoded gesture is missing, held, out of order or incomplete')
    max_closed_s=longest_closed/FPS
    if max_closed_s>2:errors.append(f'Closed eyes held for{max_closed_s:.3f}s, exceeding brief-reaction limit2s')
    if longest_unknown/FPS>2:errors.append('Unable to classify eye state for over2 continuous seconds')
    return {'passed':not errors,'decoded_frames':plan['duration_frames'],'actor_roi_xyxy':list(ACTOR_ROI),
            'all_motion_windows':list(summaries.values()),'outside_window_samples':outside,
            'longest_eyes_closed_s':max_closed_s,'closed_eye_limit_s':2,
            'longest_unclassified_eye_run_s':longest_unknown/FPS,'errors':errors,
            'limits':'Automated registered-art/pixel/movement checks; artistic identity and paw semantics also require the documented source-art and contact-sheet review.'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video',type=Path,required=True);parser.add_argument('--timeline',type=Path,required=True)
    parser.add_argument('--motion-plan',type=Path);parser.add_argument('--out-dir',type=Path,required=True)
    parser.add_argument('--ffmpeg',default=shutil.which('ffmpeg'));parser.add_argument('--ffprobe',default=shutil.which('ffprobe'))
    args=parser.parse_args(argv);args.out_dir.mkdir(parents=True,exist_ok=False)
    motion_path=args.motion_plan or args.video.parent/'character-motion.json'
    report={'schema_version':1,'kind':'independent-fibonacci-motion-v002-verification','passed':False,
            'checked_at_utc':datetime.now(timezone.utc).isoformat(),'verifier_sha256':sha(Path(__file__))}
    try:
        require(args.ffmpeg and args.ffprobe,'FFmpeg/ffprobe required')
        report.update(video_sha256=sha(args.video),timeline_sha256=sha(args.timeline),motion_plan_sha256=sha(motion_path))
        top=json.loads(args.timeline.read_text());motion=json.loads(motion_path.read_text())
        _,report['base_binding']=validate_base_binding(top,motion,motion_path)
        poses,report['registered_sources']=registered_entries(motion)
        windows,report['window_contract']=validate_windows(top,motion,poses)
        layers={};geometry=[]
        for ident,row in poses.items():
            layers[ident],result=project_pose(row);geometry.append(result)
        report['geometry']={'passed':all(r['passed'] for r in geometry),'poses':geometry,
             'alpha_threshold':8,'protected_teacher_regions':list(PROTECTED),
             'convex_interpolation_support_proof':'All keyframe layers share fixed body scale/foot support. A convex crossfade cannot create alpha support outside the union of its endpoints.'}
        require(report['geometry']['passed'],'Registered character would be empty, clipped or obscure teaching content')
        report['decoded_motion']=decoded_motion_checks(args.video,top,windows,poses,layers,args.ffmpeg,args.out_dir)
        require(report['decoded_motion']['passed'],'Decoded motion checks failed')
        require(sha(args.video)==report['video_sha256'],'Video changed during motion verification')
        report['passed']=True
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        (args.out_dir/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'report':str(args.out_dir/'verification.json')}))


if __name__=='__main__':main()
