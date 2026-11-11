#!/usr/bin/env python3
"""Independently decode and check the prime film's registered character motion.

No renderer, schedule implementation, or staged movie images are imported. The
reference is reconstructed from the frozen original RGBA cells, reviewed asset
registration, declared action frames, physical support geometry and background.
Local facial/arm/leg checks prevent a small missing blink or wave from being
hidden by averaging over the much larger unchanged background.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import subprocess

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat

ROOT = Path(__file__).resolve().parents[1]
ACTOR = (1370, 400, 1896, 1056)
REGIONS = {
    'complete_actor_corridor': ACTOR,
    'eyes': (1573, 630, 1678, 684),
    'mouth': (1566, 666, 1635, 720),
    'greeting_and_thinking_arm': (1480, 695, 1650, 835),
    'legs_and_ground_support': (1490, 840, 1775, 995),
    'full_tail': (1685, 845, 1850, 995),
}
TOLERANCE = 4.0


def resolve(path):
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def read(path):
    return json.loads(resolve(path).read_text())


def local(path):
    return resolve(path).relative_to(ROOT).as_posix()


def delta(a, b):
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[:3]


def luma_delta(a, b):
    return ImageStat.Stat(ImageChops.difference(a.convert('L'), b.convert('L'))).mean[0]


def local_box(box):
    return tuple(box[i] - ACTOR[i % 2] for i in range(4))


def read_exact(stream, count):
    chunks, size = [], 0
    while size < count:
        block = stream.read(count - size)
        if not block:
            break
        chunks.append(block)
        size += len(block)
    if size == 0:
        return None
    if size != count:
        raise ValueError('Truncated raw decoded frame')
    return b''.join(chunks)


def actions(plan, motion):
    total = plan['duration_frames']
    states = [('neutral', 0)] * total
    previous = -1
    summaries, seen = [], Counter()
    for action in motion['actions']:
        start, end = action['start_frame'], action['end_frame']
        if start < previous or end - start != len(action['frames']) or not 0 <= start < end <= total:
            raise ValueError(f'Invalid/overlapping action frames: {action["id"]}')
        previous = end
        sequence = [(r['pose'], r['offset_y_px']) for r in action['frames']]
        if action['id'].startswith('blink-'):
            if sequence != [('blink_half', 0)] * 2 + [('blink_closed', 0)] * 3 + [('blink_half', 0)] * 2:
                raise ValueError('Blink does not close and reopen through half-eye states')
            if any(start / 30 < row['end_s'] and row['start_s'] < end / 30 for row in plan['voice_events']):
                raise ValueError('Recurring blink was placed over a speech event')
        if 'wave' in action['id']:
            compressed = [pose for i, (pose, _) in enumerate(sequence) if i == 0 or pose != sequence[i-1][0]]
            if compressed != ['neutral','wave_raise','wave_high','wave_left','wave_right','wave_left','wave_right','wave_high','wave_raise','settle','neutral']:
                raise ValueError('Greeting fails its declared outward/back arm cycle')
        if 'hop' in action['id']:
            poses = [pose for pose, _ in sequence]
            for pose in ('crouch_half','crouch_down','takeoff','hop_air','land','posture_neutral','neutral'):
                if pose not in poses:
                    raise ValueError(f'Hop lacks a real key posture: {pose}')
            lifts = [offset for pose, offset in sequence if pose == 'hop_air']
            expected = [-round(60 * math.sin(math.pi * (i + 1) / 10)) for i in range(9)]
            if lifts != expected:
                raise ValueError('Airborne feet do not follow the bounded rise/fall trajectory')
        states[start:end] = sequence
        seen.update(pose for pose, _ in sequence)
        summaries.append({'id': action['id'], 'start_frame': start, 'end_frame': end,
                          'unique_poses': sorted({pose for pose, _ in sequence})})
    if len(seen) < 18 or sum(row['id'].startswith('blink-') for row in summaries) < 40:
        raise ValueError('Insufficient actually scheduled pose/facial variety')
    return states, summaries, seen


class IndependentActor:
    def __init__(self, registration, ffmpeg='ffmpeg'):
        self.ffmpeg = ffmpeg
        self.registration = registration
        self.rows = {row['id']: row for row in registration['frames']}
        self.raw = {}
        self.geometry = {}
        for identity, row in self.rows.items():
            path = resolve(row['path'])
            if sha(path) != row['sha256']:
                raise ValueError(f'Registered original frame changed: {identity}')
            image = Image.open(path)
            source = Image.open(resolve(row['source_sheet'])).crop(row['source_cell_box_xyxy'])
            if image.mode != 'RGBA' or image.tobytes() != source.tobytes() or image.size != source.size:
                raise ValueError(f'Frame no longer equals its exact original source cell: {identity}')
            self.raw[identity] = image.copy()
            ref = registration['source_groups'][row['scale_group']]['reference_height_px']
            if abs(row['reference_height_px'] - ref) > 1e-6:
                raise ValueError('Detected individual pose rescaling')
            self.geometry[identity] = (430 / ref, row['anchor_px'])
        self.composited = dict(self.raw)
        self.face_checks = {}
        for identity, config in registration.get('face_overlays', {}).items():
            base_id = config['base_pose']
            base, source = self.raw[base_id].copy(), self.raw[identity]
            for patch in config['patches']:
                src, dst = patch['source_box_xyxy'], patch['target_box_xyxy']
                image = source.crop(src).resize((dst[2]-dst[0], dst[3]-dst[1]), Image.Resampling.LANCZOS)
                radius = patch['feather_px']
                mask = Image.new('L', image.size)
                inset = math.ceil(radius * 1.5)
                ImageDraw.Draw(mask).rectangle((inset,inset,image.width-inset-1,image.height-inset-1), fill=255)
                mask = mask.filter(ImageFilter.GaussianBlur(radius))
                if patch.get('clip_to_base_alpha'):
                    skin = self.raw[base_id].getchannel('A').crop(dst).point(lambda a:255 if a >= patch['base_alpha_threshold'] else 0)
                    skin = skin.filter(ImageFilter.MinFilter(2*patch['base_alpha_inset_px']+1))
                    mask = ImageChops.multiply(mask, skin)
                image.putalpha(ImageChops.multiply(image.getchannel('A'), mask))
                base.alpha_composite(image, dst[:2])
            # Source head ends at y251. Below it every RGBA body/tail pixel must
            # remain the original coherent neutral; test actual bytes directly.
            body_same = base.crop((0,252,base.width,base.height)).tobytes() == self.raw[base_id].crop((0,252,base.width,base.height)).tobytes()
            if not body_same:
                raise ValueError('Facial overlay changes the neutral body or tail')
            self.composited[identity] = base
            self.geometry[identity] = self.geometry[base_id]
            self.face_checks[identity] = {'body_and_tail_rgba_identical_to_neutral': body_same,
                                          'body_test_region_source_px': [0,252,base.width,base.height]}
        plate = resolve('assets/library/worlds/sunlit-mosaic-museum/backgrounds/v001/sunlit-mosaic-museum-background.png')
        self.background_path = plate
        self.background = ImageOps.fit(Image.open(plate).convert('RGBA'), (1920,1080), Image.Resampling.LANCZOS).crop(ACTOR)

    @lru_cache(maxsize=256)
    def image(self, pose, offset, cream):
        scale, anchor = self.geometry[pose]
        raw = self.composited[pose]
        sprite = raw.resize((round(raw.width*scale), round(raw.height*scale)), Image.Resampling.LANCZOS)
        position = (round(1625-anchor[0]*scale),round(982+offset-anchor[1]*scale))
        bbox = sprite.getchannel('A').point(lambda a:255 if a >=8 else 0).getbbox()
        visible = tuple(bbox[i]+position[i%2] for i in range(4))
        if not all((visible[0]>ACTOR[0],visible[1]>ACTOR[1],visible[2]<ACTOR[2],visible[3]<ACTOR[3])):
            raise ValueError(f'Actual scaled sprite/tail leaves clear region: {pose} {offset}: {visible}')
        layer = Image.new('RGBA', self.background.size)
        lift = max(0,-offset)
        w = 1-lift/200
        x,y = 1625-ACTOR[0],982-ACTOR[1]
        ImageDraw.Draw(layer).ellipse((x-92*w,y-9,x+135*w,y+14),fill=(77,61,44,round(24*w)))
        layer.alpha_composite(sprite,(position[0]-ACTOR[0],position[1]-ACTOR[1]))
        result = self.background.copy()
        result.alpha_composite(layer)
        if cream:
            result = Image.blend(result, Image.new('RGBA',result.size,'#fffaf0'), cream/255)
        return result.convert('RGB')

    @lru_cache(maxsize=256)
    def yuv420_reference(self, pose, offset, cream):
        """Apply only the film's declared RGB/YUV chroma sampling, no H.264.

        Local eye/outline RGB comparisons must account for unavoidable 4:2:0
        color sampling. This reference never reads the encoded movie or borrows
        its pixels, and does not relax the 4.0 per-channel acceptance threshold.
        """
        image = self.image(pose,offset,cream)
        command = [self.ffmpeg,'-nostdin','-v','error','-f','rawvideo','-pix_fmt','rgb24',
                   '-s',f'{image.width}x{image.height}','-i','pipe:0',
                   '-vf','format=yuv420p,format=rgb24','-f','rawvideo','-pix_fmt','rgb24','pipe:1']
        raw = subprocess.check_output(command,input=image.tobytes())
        if len(raw) != image.width*image.height*3:
            raise ValueError('RGB/YUV420P reference transform truncated its frame')
        return Image.frombytes('RGB',image.size,raw)


def cream_at(index, plan):
    t = index / 30 + 1e-9
    if t < .8:
        value = round(255*(1-t/.8))
    elif t >= plan['duration_s']-2:
        last = (plan['duration_frames']-1)/30
        value = round(255*(t-plan['duration_s']+2)/(last-plan['duration_s']+2))
    else:
        value = 0
    return max(0,min(255,value))


def actor_check(movie, ffmpeg, plan, states, actor, frame_indices, crop, out):
    w,h = ACTOR[2]-ACTOR[0],ACTOR[3]-ACTOR[1]
    command = [ffmpeg,'-nostdin','-v','error','-i',str(movie),'-an','-vf',f'crop={w}:{h}:{crop[0]}:{crop[1]}','-f','rawvideo','-pix_fmt','rgb24','pipe:1']
    worst = {name:{'mae_rgb':[0,0,0],'luma_mae':0,'frame':None} for name in REGIONS}
    failures, pose_frames, active_counterfactual = [], Counter(), {}
    with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE) as process, (out/'decoded-actor-frames.csv').open('w') as csvfile:
        writer = csv.writer(csvfile);writer.writerow(['decoded_frame','source_frame','pose','lift_px','cream','worst_region_mae','passed'])
        for decoded_index, source_index in enumerate(frame_indices):
            raw = read_exact(process.stdout,w*h*3)
            if raw is None:
                raise ValueError('Actor movie ended before the declared last frame')
            actual = Image.frombytes('RGB',(w,h),raw)
            pose,offset = states[source_index]
            cream = cream_at(source_index,plan)
            expected = actor.yuv420_reference(pose,offset,cream)
            frame_worst = 0
            passed = True
            for name,box in REGIONS.items():
                roi = local_box(box)
                actual_part,expected_part=actual.crop(roi),expected.crop(roi)
                errors = delta(actual_part,expected_part)
                luma = luma_delta(actual_part,expected_part)
                high = max(errors) if name=='complete_actor_corridor' else luma
                frame_worst=max(frame_worst,high)
                worst[name]['mae_rgb']=[max(a,b) for a,b in zip(worst[name]['mae_rgb'],errors)]
                if luma > worst[name]['luma_mae']:
                    worst[name].update(luma_mae=luma,frame=source_index,pose=pose)
                if high > TOLERANCE:
                    passed=False
                    if len(failures)<30:
                        failures.append({'decoded_frame':decoded_index,'source_frame':source_index,'pose':pose,'region':name,'mae_rgb':errors,'luma_mae':luma})
            pose_frames[pose]+=1
            if pose != 'neutral' and (pose,offset,cream) not in active_counterfactual:
                neutral = actor.yuv420_reference('neutral',0,cream)
                sensitivity = {name:(max(delta(expected.crop(local_box(box)),neutral.crop(local_box(box)))) if name=='complete_actor_corridor' else luma_delta(expected.crop(local_box(box)),neutral.crop(local_box(box)))) for name,box in REGIONS.items()}
                active_counterfactual[pose,offset,cream] = max(sensitivity.values())
            writer.writerow([decoded_index,source_index,pose,offset,cream,round(frame_worst,6),passed])
            if not passed and not (out/'first-actor-failure.png').exists():
                board=Image.new('RGB',(w*3,h));board.paste(actual,(0,0));board.paste(expected,(w,0));board.paste(ImageChops.difference(actual,expected),(w*2,0));board.save(out/'first-actor-failure.png')
            if (decoded_index+1)%3000==0:
                print(json.dumps({'actor_decoded_frames':decoded_index+1,'max_region_mae':max(max(row['mae_rgb']) for row in worst.values())}),flush=True)
        if process.stdout.read(1):
            raise ValueError('Actor movie has undeclared extra frames')
        process.stdout.close();stderr=process.stderr.read().decode();code=process.wait()
        if code:
            raise ValueError(f'Actor decode failed: {stderr}')
    sensitivity_min = min(active_counterfactual.values()) if active_counterfactual else None
    return {'frames_checked':len(frame_indices),'native_decode_crop_px':list(ACTOR),
            'complete_corridor_mae_tolerance_per_rgb_channel':TOLERANCE,
            'local_feature_geometry_mae_tolerance_luma':TOLERANCE,
            'local_feature_metric_rationale':'Luma tests visible feature strokes without false failures from unavoidable high-contrast YUV420P chroma ringing. Local RGB errors are also retained; complete actor RGB remains independently bounded.',
            'regions_px':{name:list(box) for name,box in REGIONS.items()},'worst_per_region':worst,
            'reference_color_sampling':'Original reconstructed RGB -> FFmpeg YUV420P -> RGB, without H.264 encoding or movie pixels; models declared unavoidable chroma sampling.',
            'failures':failures,'pose_frame_counts':dict(pose_frames),
            'static_neutral_counterfactual_minimum_detectable_region_mae':sensitivity_min,
            'all_active_states_would_reject_static_neutral':sensitivity_min is not None and sensitivity_min>TOLERANCE,
            'passed':not failures and sensitivity_min is not None and sensitivity_min>TOLERANCE}


def learning_check(old,new,ffmpeg,total,out):
    # Both films are decoded independently before their teaching regions are
    # compared. Root's native glyph QA separately checks exact mathematical text.
    graph='[0:v]crop=1370:1080:0:0,scale=342:270[v0];[1:v]crop=1370:1080:0:0,scale=342:270[v1];[v0][v1]blend=all_mode=difference,format=rgb24[v]'
    command=[ffmpeg,'-nostdin','-v','error','-i',str(old),'-i',str(new),'-filter_complex',graph,'-map','[v]','-an','-f','rawvideo','-pix_fmt','rgb24','pipe:1']
    worst,failures=[0,0,0],[]
    with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE) as process:
        for index in range(total):
            raw=read_exact(process.stdout,342*270*3)
            if raw is None:raise ValueError('Teaching-region comparison ended early')
            error=ImageStat.Stat(Image.frombytes('RGB',(342,270),raw)).mean
            worst=[max(a,b) for a,b in zip(worst,error)]
            if max(error)>TOLERANCE and len(failures)<30:failures.append({'frame':index,'mae_rgb':error})
        if process.stdout.read(1):raise ValueError('Teaching comparison contains extra frames')
        process.stdout.close();stderr=process.stderr.read().decode();code=process.wait()
        if code:raise ValueError(stderr)
    return {'frames_checked':total,'source_region_px':[0,0,1370,1080],'comparison_size_px':[342,270],
            'method':'Independent old/new decode, crop, identical FFmpeg scale, absolute RGB difference; complements separate native glyph checks.',
            'mae_tolerance_per_rgb_channel':TOLERANCE,'worst_mae_rgb':worst,'failures':failures,'passed':not failures}


def aac_packets(movie,ffprobe):
    command=[ffprobe,'-v','error','-select_streams','a:0','-show_packets','-show_entries','packet=pts_time,dts_time,duration_time,size,data_hash','-show_data_hash','sha256','-of','json',str(movie)]
    return json.loads(subprocess.check_output(command))['packets']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('movie','timeline','motion','registration','out'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--old-movie')
    parser.add_argument('--preview-record')
    parser.add_argument('--ffmpeg',default='ffmpeg');parser.add_argument('--ffprobe',default='ffprobe')
    args=parser.parse_args()
    out=resolve(args.out);out.mkdir(parents=True,exist_ok=False)
    movie=resolve(args.movie);plan=read(args.timeline);motion=read(args.motion);registration=read(args.registration)
    states,summaries,seen=actions(plan,motion)
    actor=IndependentActor(registration,args.ffmpeg)
    if args.preview_record:
        preview=read(args.preview_record)['preview']
        frame_indices=[min(plan['duration_frames']-1,round(clip['source_start_s']*30)+i) for clip in preview['clips'] for i in range(round(clip['duration_s']*30))]
        crop=(0,0)
    else:
        frame_indices=list(range(plan['duration_frames']));crop=ACTOR[:2]
        if not args.old_movie:raise ValueError('Full final verification requires the immutable v001 source movie')
    result={'kind':'independent-prime-animation-decoded-qa','source_hashes':{key:{'path':local(value),'sha256':sha(resolve(value))} for key,value in {'movie':args.movie,'timeline':args.timeline,'motion':args.motion,'registration':args.registration,'verifier':__file__}.items()},
            'scope':'Native decoded actor frames, local facial/arm/leg/tail references from original registered sources, declared timeline and separate light/dark/native visual review. No renderer import or staged movie-reference reuse.',
            'declared_actions_checked':summaries,'scheduled_pose_frame_counts':dict(seen),'face_body_pixel_checks':actor.face_checks,
            'background':{'path':local(actor.background_path),'sha256':sha(actor.background_path)}}
    result['actor']=actor_check(movie,args.ffmpeg,plan,states,actor,frame_indices,crop,out)
    if not args.preview_record:
        old=resolve(args.old_movie)
        result['source_hashes']['old_movie']={'path':local(old),'sha256':sha(old)}
        result['learning_region']=learning_check(old,movie,args.ffmpeg,plan['duration_frames'],out)
        before,after=aac_packets(old,args.ffprobe),aac_packets(movie,args.ffprobe)
        result['aac']={'source_packet_count':len(before),'final_packet_count':len(after),
                       'payload_sha256_and_pts_dts_duration_size_identical':before==after,
                       'passed':before==after}
    result['passed']=result['actor']['passed'] and all(result[key]['passed'] for key in ('learning_region','aac') if key in result)
    (out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':result['passed'],'actor_frames':len(frame_indices),'output':local(out/'verification.json')}),flush=True)
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':
    main()
