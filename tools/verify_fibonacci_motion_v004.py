"""Independent v004 acting QA: spec, intact artwork and every decoded frame.

Only verification modules are imported. The production schedule API and drawing
code are deliberately absent: the separately authored acting plan is expanded
here, and accepted source PNGs establish the finite pixel dictionary. Small
gaze/blink changes are tested by relative pixel projection, so a held character
cannot pass merely because its whole-body average error is small.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import shutil

from PIL import Image, ImageChops, ImageDraw, ImageOps, ImageStat

if __package__:
    from . import verify_fibonacci_motion_v002 as independent
    from . import verify_fibonacci_video as lesson
    from .verify_fibonacci_intro_seed import fade_expected_weight
else:
    import verify_fibonacci_motion_v002 as independent
    import verify_fibonacci_video as lesson
    from verify_fibonacci_intro_seed import fade_expected_weight

ROOT = independent.ROOT
FPS = 30
NEW_POSES = ('watch_upper_left', 'watch_lower_left', 'nod_mid', 'nod_down',
             'blink_half', 'blink_closed')
FIELDS = ('path', 'sha256', 'anchor_px', 'reference_height_px', 'eyes_closed')
UNCHANGED = tuple(dict.fromkeys(independent.BASE_FIELDS +
    ('teaching', 'intro', 'finale', 'mathematics_animation', 'codec_scalar_corrections',
     'bgm', 'sound_effects', 'encoded_audio_acceptance')))
REGIONS = {'eyes': (1500, 650, 1810, 800), 'head': (1500, 565, 1835, 820),
           'torso': (1530, 805, 1780, 955), 'feet': (1510, 950, 1800, 1015),
           'tail': (1765, 735, 1855, 975)}
require, sha, local_path = independent.require, independent.sha, independent.local_path


def validate_binding(plan, motion, motion_path):
    require(plan.get('renderer_implementation') == 'tools/render_fibonacci_video_v004.py',
            'Unexpected v004 renderer')
    base_path, base = independent.document_reference(plan.get('source_timeline'), 'audio base')
    visual_path, visual = independent.document_reference(plan.get('source_visual_revision'), 'v003 lesson')
    require(visual.get('renderer_implementation') == 'tools/render_fibonacci_video_v003.py', 'Wrong visual baseline')
    for field in UNCHANGED:
        require(plan.get(field) == visual.get(field), f'Acting changed lesson/audio field {field}')
    for field in independent.BASE_FIELDS:
        require(plan.get(field) == base.get(field), f'Acting changed immutable audio field {field}')
    require(plan.get('character_motion', {}).get('sha256') == sha(motion_path), 'Top motion SHA mismatch')
    require(sha(local_path(plan['character_motion']['path'])) == sha(motion_path), 'Wrong motion path')
    require(motion.get('source_timeline') == plan['source_timeline'], 'Motion and top audio base differ')
    spec_path, spec = independent.document_reference(motion.get('source_schedule'), 'independent acting spec')
    require(spec['source_visual_timeline']['sha256'] == sha(visual_path), 'Acting spec visual source mismatch')
    require(spec['source_timeline']['sha256'] == sha(base_path), 'Acting spec audio source mismatch')
    retained_path, retained = independent.document_reference(motion.get('source_motion'), 'retained motion')
    require(visual['character_motion']['sha256'] == sha(retained_path), 'Retained motion is not baseline motion')
    require(motion['windows'] == spec['windows'], 'Production motion differs from independently authored spec')
    for field in ('default_pose', 'default_pose_by_mode', 'body_height_px', 'ground_foot_anchor_px',
                  'interpolation', 'full_actor_crossfade', 'source_art_modified_at_render', 'duration_frames', 'fps'):
        require(motion.get(field) == spec.get(field), f'Production changed acting contract {field}')
    require(motion['fps'] == FPS and motion['duration_frames'] == plan['duration_frames'], 'Motion time grid changed')
    require(motion['body_height_px'] == 400 and motion['ground_foot_anchor_px'] == [1655, 990], 'Physical scale/foot changed')
    require(motion['full_actor_crossfade'] is False and motion['source_art_modified_at_render'] is False, 'Dissolve or source editing forbidden')
    require(motion['drawing_transform'] == 'common-isotropic-family-scale-and-registered-foot-translation', 'Unknown actor transform')
    # Register the old immutable sixteen and all six direct source drawings.
    registry_path, registry = independent.document_reference(motion.get('registry'), 'new direct registry')
    independent.document_reference(motion.get('retained_registry'), 'retained direct registry')
    require(registry.get('source_pixels_modified') is False, 'Registry reports modified source pixels')
    poses = motion['poses']
    require(set(poses) == set(retained['poses']) | set(NEW_POSES) and len(poses) == 22, 'Wrong finite artwork inventory')
    for ident, row in retained['poses'].items():
        require(all(poses[ident].get(k) == row.get(k) for k in FIELDS), f'Retained artwork changed: {ident}')
    rows = registry['frames']
    if isinstance(rows, dict): rows = [dict(v, id=k) for k,v in rows.items()]
    require({row['id'] for row in rows} == set(NEW_POSES), 'New registry does not contain exactly six adopted drawings')
    for row in rows:
        ident = row['id']
        require(all(poses[ident].get(k) == row.get(k) for k in FIELDS), f'Registration differs: {ident}')
        require(row['reference_height_px'] == 1120 and row['anchor_px'] == [627, 1179], 'New family scale/foot drift')
    for ident,row in poses.items():
        require(sha(local_path(row['path'])) == row['sha256'], f'Adopted source changed: {ident}')
        require(isinstance(row['eyes_closed'], bool), f'Unknown eye state {ident}')
    return spec, poses, {'passed': True, 'source_timeline': independent.receipt(base_path),
        'source_visual_revision': independent.receipt(visual_path), 'independent_schedule': independent.receipt(spec_path),
        'new_registry': independent.receipt(registry_path), 'exact_lesson_fields': list(UNCHANGED),
        'source_pose_count': len(poses), 'hash_graph': 'immutable audio base and v003 source -> spec/motion -> top; no cyclic SHA'}


def effective_mode(plan, frame):
    at = frame/FPS
    segment = next((s for s in plan['visual_segments'] if s['start_s'] <= at < s['end_s']), plan['visual_segments'][-1])
    mode = segment['mode']
    # I08 is the ordinal/range legend at its own display lead, even while the
    # broad intro segment is called opening in the immutable audio plan.
    cue = next(e for e in plan['voice_events'] if e['id'] == 'I08')
    if mode == 'opening' and at >= cue['start_s']-.12: mode = 'legend'
    return mode


def expand_track(plan, spec):
    """Loop over exact integer intervals; no production Schedule dependency."""
    total = plan['duration_frames']
    track = [spec['default_pose_by_mode'].get(effective_mode(plan, f), spec['default_pose']) for f in range(total)]
    actions = [None]*total
    prior = 0
    events = {e['id']: e for e in plan['voice_events']}
    for w in spec['windows']:
        a,b = w['start_frame'], w['end_frame']
        require(isinstance(a,int) and isinstance(b,int) and prior <= a < b <= total, 'Overlapping/out-of-range acting window')
        require(abs(a/FPS-w['start_s']) < 1e-8 and abs(b/FPS-w['end_s']) < 1e-8, 'Window off integer frame grid')
        cue = w['source_cue']
        require(a == lesson.frame_at(events[cue['id']][cue['edge']]+cue['offset_s']), f'Cue anchor changed {w["id"]}')
        cursor = a
        for key in w['keyframes']:
            end = cursor+key['hold_frames']
            require(key['at_frame'] == cursor and abs(key['at_s']-cursor/FPS) < 1e-8 and
                    isinstance(key['hold_frames'],int) and key['hold_frames'] > 0 and end <= b, 'Held keys have gap/overlap')
            require(key['interpolation'] == 'hold', 'Actor crossfade/unknown interpolation')
            track[cursor:end] = [key['pose_id']]*(end-cursor)
            actions[cursor:end] = [w['id']]*(end-cursor)
            cursor = end
        require(cursor == b, 'Keyframes do not fill action')
        prior = b
    return track, actions


def runs(track):
    result=[]
    for i,ident in enumerate(track):
        if not result or result[-1]['pose_id'] != ident: result.append({'pose_id':ident,'start_frame':i,'end_frame':i+1})
        else: result[-1]['end_frame']=i+1
    return result


def validate_intent(plan, spec, poses, track):
    windows=spec['windows']; counts=Counter(w['kind'] for w in windows)
    require(len(windows)==118 and counts['count-attention']==39 and counts['pair-handoff-follow']==38 and
            counts['checkpoint-presentation']==6 and counts['result-acknowledgement']==15, 'Coverage omissions in acting spec')
    require(set(track) <= set(poses), 'Track references unknown drawing')
    states={s['index']:s for s in plan['counted_states']}
    for w in windows:
        ids=[k['pose_id'] for k in w['keyframes']]
        if w['kind']=='count-attention':
            n=int(w['id'].rsplit('-',1)[1]); s=states[n]
            require(ids[0]=='watch_upper_left' and 'watch_left' in ids and ids[-1]=='watch_lower_left', 'Attention is not input -> operator -> result')
            display=lesson.frame_at(s['display_start_s'])
            require(track[display]=='watch_lower_left', f'Result gaze not synchronized F{n}')
        if w['kind']=='result-acknowledgement':
            n=int(w['id'].rsplit('-',1)[1]);s=states[n]
            require(w['end_frame']-w['start_frame']==9 and ids==['nod_mid','nod_down','nod_mid','watch_lower_left'], 'Nod order/duration changed')
            require(w['start_frame']>=lesson.frame_at(s['voice_end_s']) and
                    w['end_frame']<=lesson.frame_at(s['transfer_start_s']), 'Nod collides with reading/transfer')
    retained_path,retained=independent.document_reference(spec['retained_motion'],'retained important actions')
    old={w['id']:w for w in retained['windows']}
    for ident in ('opening-wave','million-notice','completion-smile','goodbye-wave'):
        w=next(w for w in windows if w['id']==ident)
        for k,v in old[ident].items(): require(w.get(k)==v, f'Important retained action changed: {ident}/{k}')
    critical=[]
    for s in states.values():
        critical += [s['display_start_s']]
        if s.get('formula_start_s') is not None:
            a,b=s['formula_start_s'],s['formula_end_s'];critical += [a+.45*(b-a),a+.60*(b-a)]
        critical += [s[k] for k in ('transfer_start_s','transfer_end_s') if s.get(k) is not None]
    blink_runs=[r for r in runs(track) if r['pose_id']=='blink_closed']
    require(len(blink_runs)==len(spec['blink_schedule'])==14, 'Blink count differs from accepted editing plan')
    last_end=-100
    for r,declared in zip(blink_runs,sorted(spec['blink_schedule'],key=lambda x:x['start_frame'])):
        a,b=r['start_frame'],r['end_frame'];start=declared['start_frame']
        require(a==start+2 and b==a+3 and track[a-2:a]==['blink_half']*2 and track[b:b+2]==['blink_half']*2, 'Blink is not half2/closed3/half2')
        require(track[b+2]==declared['return_pose'] and declared['return_pose'] in ('watch_left','watch_upper_left'), 'Blink does not return to relaxed open-eye pose')
        require(a-2-last_end>=45, 'Eyes do not remain open for1.5s between blinks')
        require(all(not(a-2 < t*FPS+7.5 and b+2 > t*FPS-7.5) for t in critical), 'Blink masks important lesson transition')
        last_end=b+2
    closed=runs([bool(poses[p]['eyes_closed']) for p in track])
    maximum=max((r['end_frame']-r['start_frame'] for r in closed if r['pose_id']),default=0)
    require(maximum<=60, 'Closed eyes held beyond2s')
    pose_runs=runs(track)
    return {'passed':True,'windows':len(windows),'purpose_counts':dict(counts),'blink_episodes':len(blink_runs),
        'dedicated_nods':15,'all_nod_down_intervals':sum(r['pose_id']=='nod_down' for r in pose_runs),
        'pose_changes':len(pose_runs)-1,'longest_held_pose_s':max(r['end_frame']-r['start_frame'] for r in pose_runs)/FPS,
        'longest_closed_eye_s':maximum/FPS,'whole_body_bob':False,'tail_part_animation':False,
        'coverage_note':'Upper/lower broad attention targets; no claim of distinct horizontal eye positions for operand A and B, simulated breathing, or independent tail movement.'}


def squared_distance(a,b,mask=None):
    return sum(ImageStat.Stat(ImageChops.difference(a,b),mask).sum2)


class PixelDictionary:
    """All registered candidates, with source-relative projection rejection.

    For actual X and expected L, projection toward wrong H equals
    (||X-L||²-||X-H||²+||H-L||²)/(2||H-L||²). The noise common to the two
    distances cancels. A static wrong gaze yields1; a half dissolve yields.5.
    This is not a threshold on global movement rate or whole-character MAE.
    """
    def __init__(self,pictures,mask,divisor=2):
        size=(pictures[next(iter(pictures))].width//divisor,pictures[next(iter(pictures))].height//divisor)
        self.images={k:v.resize(size,Image.Resampling.BOX) for k,v in pictures.items()}
        self.mask=mask.resize(size,Image.Resampling.NEAREST)
        self.energy={(a,b):squared_distance(x,y,self.mask) for a,x in self.images.items() for b,y in self.images.items() if a!=b}

    def observe(self,image,expected):
        small=image.resize(self.images[expected].size,Image.Resampling.BOX)
        errors={k:squared_distance(small,v,self.mask) for k,v in self.images.items()}
        projections={k:(errors[expected]-error+self.energy[expected,k])/(2*self.energy[expected,k])
            for k,error in errors.items() if k!=expected and self.energy[expected,k]>=20000}
        worst=max(projections,key=lambda k:abs(projections[k]),default=None)
        return {'nearest_pose':min(errors,key=errors.get),'worst_alternative':worst,
                'maximum_abs_relative_projection':abs(projections[worst]) if worst else 0,
                'signed_projection':projections.get(worst,0),
                'passed':not worst or abs(projections[worst])<=.30}


def build_pictures(poses):
    plate=ImageOps.fit(Image.open(independent.BACKGROUND).convert('RGBA'),independent.SIZE,Image.Resampling.LANCZOS)
    shadow=Image.new('RGBA',independent.SIZE);ImageDraw.Draw(shadow).ellipse((1530,977,1815,1007),fill=(74,88,89,22))
    plate.alpha_composite(shadow)
    pictures={};layers={};geometry=[];mask=Image.new('L',(520,640))
    for ident,row in poses.items():
        layer,record=independent.project_pose(dict(row,id=ident));geometry.append(record);layers[ident]=layer
        require(record['passed'],f'Source edge, clipping or teacher clearance failure: {ident}')
        composite=plate.copy();composite.alpha_composite(layer)
        pictures[ident]=composite.convert('RGB').crop(independent.ACTOR_ROI)
        mask=ImageChops.lighter(mask,layer.getchannel('A').crop(independent.ACTOR_ROI).point(lambda x:255 if x>=8 else 0))
    return pictures,layers,mask,plate.convert('RGB').crop(independent.ACTOR_ROI),geometry


class RegisteredAlignment:
    """Measure both axes against fixed source placement, never fit the actor.

    Head, torso and planted feet are compared separately. The expected nod head
    displacement already belongs to its source drawing. A raster shifted by2px
    is rejected even if whole-character mean error happens to remain small.
    """
    def __init__(self,pictures):
        self.models={}
        for ident,picture in pictures.items():
            gray=picture.convert('L');regions={}
            for name in ('head','torso','feet'):
                b=REGIONS[name];box=(b[0]-1390,b[1]-400,b[2]-1390,b[3]-400)
                candidates={(dx,dy):gray.crop((box[0]-dx,box[1]-dy,box[2]-dx,box[3]-dy))
                    for dx in range(-2,3) for dy in range(-2,3)}
                regions[name]=(box,candidates)
            self.models[ident]=regions

    def observe(self,image,ident):
        gray=image.convert('L');result={}
        for name,(box,candidates) in self.models[ident].items():
            actual=gray.crop(box)
            errors={offset:squared_distance(actual,expected) for offset,expected in candidates.items()}
            best=min(errors,key=errors.get)
            result[name]={'delta_x_px':best[0],'delta_y_px':best[1],
                'error_at_fixed_placement':errors[0,0],'minimum_error':errors[best],
                'passed':abs(best[0])<=1 and abs(best[1])<=1}
        return {'passed':all(r['passed'] for r in result.values()),'regions':result,'tolerance_px_each_axis':1}


def score_frame(image,expected,backdrop,mask,dictionary,ident,core=True,alignment=None):
    classification=dictionary.observe(image,ident)
    errors={}
    for name,box in REGIONS.items():
        relative=(box[0]-1390,box[1]-400,box[2]-1390,box[3]-400)
        errors[name]=sum(ImageStat.Stat(ImageChops.difference(image.crop(relative),expected.crop(relative))).mean)/3
    body=independent.mae(image,expected,mask)
    loss=independent.missing_opaque_core(image,expected,backdrop) if core else {'passed':True}
    placement=alignment.observe(image,ident) if alignment else {'passed':True}
    return {'body_mae_rgb':body,'regional_mae_rgb':errors,'identity':classification,'opaque_core':loss,
            'registered_alignment':placement,
            'passed':classification['passed'] and body<=6 and max(errors.values())<=7 and loss['passed'] and placement['passed']}


def decoded_checks(video,plan,spec,poses,track,actions,ffmpeg,directory):
    pictures,layers,mask,backdrop,geometry=build_pictures(poses)
    dictionary=PixelDictionary(pictures,mask);alignment=RegisteredAlignment(pictures)
    # Source-level negative controls test exactly the finite distinctions which
    # whole-character MAE alone would miss, including tiny eye changes.
    negatives=[]
    for wrong,right in [('watch_left','watch_upper_left'),('watch_left','watch_lower_left'),
                        ('watch_upper_left','watch_lower_left'),('blink_closed','blink_half'),('nod_mid','nod_down')]:
        static=dictionary.observe(pictures[wrong],right)
        ghost=dictionary.observe(Image.blend(pictures[right],pictures[wrong],.5),right)
        negatives.append({'wrong':wrong,'expected':right,'held_rejected':not static['passed'],'half_dissolve_rejected':not ghost['passed']})
    require(all(n['held_rejected'] and n['half_dissolve_rejected'] for n in negatives),'Dictionary accepts static/ghost negative control')
    cached={};errors=[];records=[];observed=Counter();windows={w['id']:{'id':w['id'],'kind':w['kind'],'frames':0,'passed':True,'pose_ids':[]} for w in spec['windows']}
    cream=Image.new('RGB',(520,640),(255,250,240));worst_projection=0;max_body=0;max_regions=Counter()
    cache_hits=0
    for frame,image in independent.decoded_actor_frames(video,ffmpeg,directory/'actor-decode.log',plan['duration_frames']):
        ident=track[frame];expected=pictures[ident]
        fade=fade_expected_weight(frame,plan['duration_frames'],plan['duration_s'],'opening' if frame<24 else 'ending') if frame<24 or frame/FPS>=plan['duration_s']-2 else 0
        if fade:
            expected=Image.blend(expected,cream,round(fade*255)/255)
            error=sum(ImageStat.Stat(ImageChops.difference(image,expected)).mean)/3
            row={'passed':error<=3,'fade_weight':fade,'body_mae_rgb':error,'identity':{'passed':True},'regional_mae_rgb':{}}
        else:
            digest=hashlib.sha256(image.tobytes()).digest();key=(ident,digest)
            if key in cached:row=cached[key];cache_hits+=1
            else:
                row=score_frame(image,expected,backdrop,mask,dictionary,ident,alignment=alignment)
                cached[key]=row
            worst_projection=max(worst_projection,row['identity']['maximum_abs_relative_projection'])
            for name,value in row['regional_mae_rgb'].items():max_regions[name]=max(max_regions[name],value)
        max_body=max(max_body,row['body_mae_rgb']);observed[ident]+=1
        action=actions[frame]
        if action:
            w=windows[action];w['frames']+=1;w['passed'] &= row['passed']
            if not w['pose_ids'] or w['pose_ids'][-1]!=ident:w['pose_ids'].append(ident)
        records.append({'frame':frame,'expected_pose':ident,'action_id':action,**row})
        if not row['passed']:
            errors.append({'frame':frame,'pose':ident,**row})
            if len(errors)<=12:image.save(directory/f'failure-{frame:06d}-{ident}.png')
        if frame%1500==0:print(json.dumps({'event':'motion_progress','frame':frame,'failures':len(errors)}),flush=True)
    (directory/'all-frame-observations.json').write_text(json.dumps(records,separators=(',',':'))+'\n')
    require(len(records)==plan['duration_frames'],'Incomplete motion decode')
    for w in spec['windows']:
        actual=windows[w['id']];expected_ids=[r['pose_id'] for r in runs(track[w['start_frame']:w['end_frame']])]
        actual['passed'] &= actual['pose_ids']==expected_ids and actual['frames']==w['end_frame']-w['start_frame']
    return {'passed':not errors and all(w['passed'] for w in windows.values()),'decoded_frames':len(records),
        'actor_roi_xyxy':list(independent.ACTOR_ROI),'source_geometry':geometry,'pose_frame_counts':dict(observed),
        'max_body_mae_rgb':max_body,'max_regional_mae_rgb':dict(max_regions),
        'maximum_abs_relative_projection':worst_projection,'projection_limit':.30,
        'pixel_dictionary_minimum_pair_energy':20000,'template_divisor':2,'cached_identical_actor_frames':cache_hits,
        'negative_controls':negatives,'failure_count':len(errors),'failures':errors[:100],
        'windows':list(windows.values()),'observations':'all-frame-observations.json',
        'method':'Every actual RGB frame: registered intact source projection, full/body-region residuals, all22 alternative relative pixel projections, and native BT709 high-contrast missing-core clusters. Fade frames use the independently specified cream curve. No whole-body fit, position normalization, or producer-returned pose is used as observed truth.'}


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('timeline','video','out-dir'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--motion',type=Path);p.add_argument('--ffmpeg',default=shutil.which('ffmpeg'))
    p.add_argument('--spec-only',action='store_true')
    return p


def main(argv=None):
    args=parser().parse_args(argv);args.out_dir.mkdir(parents=True,exist_ok=False)
    plan=json.loads(args.timeline.read_text());motion_path=args.motion or local_path(plan['character_motion']['path'])
    motion=json.loads(motion_path.read_text());video_sha=sha(args.video) if args.video.is_file() else None
    report={'schema_version':1,'kind':'independent-fibonacci-v004-motion-verification','passed':False,
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'video':str(args.video.resolve()),
        'video_sha256':video_sha,'timeline_sha256':sha(args.timeline),'motion_sha256':sha(motion_path),'verifier_sha256':sha(__file__)}
    try:
        spec,poses,report['binding']=validate_binding(plan,motion,motion_path)
        track,actions=expand_track(plan,spec)
        report['intent']=validate_intent(plan,spec,poses,track)
        (args.out_dir/'independent-pose-track.json').write_text(json.dumps(runs(track),indent=2)+'\n')
        if not args.spec_only:
            require(args.ffmpeg and video_sha,'Finished video/ffmpeg required')
            report['decoded_motion']=decoded_checks(args.video,plan,spec,poses,track,actions,args.ffmpeg,args.out_dir)
            require(report['decoded_motion']['passed'],'Finished acting pixels failed independent comparison')
            require(sha(args.video)==video_sha,'Video changed during verification')
        report['passed']=True
    except Exception as error:report['error']=str(error);raise
    finally:
        report['scope']='Spec/source-only' if args.spec_only else 'All16104 actual frames and every118 complete action; mathematical teaching and audio checked by the separate v004 media verifier. Human continuous viewing/listening is not claimed; tail is verified as part of each intact drawing, with no independent tail animation claim.'
        (args.out_dir/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'report':str(args.out_dir/'verification.json')}))


if __name__=='__main__':main()
