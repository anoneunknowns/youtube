"""Fresh v003 Fibonacci QA, preserving the historical independent verifier.

This module imports verification helpers only. It adds all native transfer
frames, the independently specified F20 88-to47px transition, and seed/fade QA.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib,json,math,multiprocessing,shutil,tempfile
from pathlib import Path

if __package__:
    from . import verify_fibonacci_video as old
    from . import verify_fibonacci_intro_seed as intro
else:
    import verify_fibonacci_video as old
    import verify_fibonacci_intro_seed as intro

ROOT=Path(__file__).resolve().parents[1]
ORIGINAL_COUNT_LABELS=old.count_labels

def transition_size(n,progress):
    old.require(0<=progress<=1,'Transfer progress outside0..1')
    return round(88-41*progress) if n==20 else (88 if n<=20 else 47)

def count_labels(n,stage='result',transfer=0):
    rows=ORIGINAL_COUNT_LABELS(n,stage,transfer)
    if n==20 and stage=='transfer':
        for row in rows:
            if row['name'] in ('transferred-0','transferred-1'):
                row['size']=transition_size(n,transfer)
    return rows

@contextmanager
def v003_labels():
    previous=old.count_labels;old.count_labels=count_labels
    try:yield
    finally:old.count_labels=previous

def independent_progress(state,at):
    raw=max(0,min(1,(at-state['transfer_start_s'])/(state['transfer_end_s']-state['transfer_start_s'])))
    return round(raw*raw*(3-2*raw)*30)/30

def check_transfer_frame(image,state,frame):
    n=state['index'];progress=independent_progress(state,frame/30)
    rows=[r for r in count_labels(n,'transfer',progress) if r['name'].startswith('transferred-')]
    components=old.inspect_labels(image,rows,frame)
    return {'frame':frame,'at_s':frame/30,'index':n,'effective_progress':progress,
            'expected_value_font_size_px':transition_size(n,progress),'components':components,
            'passed':all(r['passed'] for r in components)}

def all_transfer_checks(video,plan,ffmpeg,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    transfers=[s for s in plan['counted_states'] if s.get('transfer_start_s') is not None]
    old.require(len(transfers)==38,'Expected38 executed value/subscript handoffs')
    mapping={};groups={}
    for s in transfers:
        frames=range(old.frame_at(s['transfer_start_s']),old.frame_at(s['cycle_end_s']))
        old.require(frames,'Empty transfer interval')
        groups[s['index']]={'index':s['index'],'expected_values':list(old.fibonacci()[s['index']-1:s['index']+1]),
          'expected_F_indices':[s['index']-1,s['index']],'start_s':s['transfer_start_s'],
          'end_of_movement_s':s['transfer_end_s'],'end_of_arrival_hold_s':s['cycle_end_s'],'frames':[]}
        for frame in frames:
            old.require(frame not in mapping,'Transfer windows overlap');mapping[frame]=s
    for frame,image in old.media.decoded_frames(video,ffmpeg,directory/'transfer-native-decode.log',1,sorted(mapping)):
        record=check_transfer_frame(image,mapping[frame],frame);group=groups[record['index']];group['frames'].append(record)
        if record['index']==20 and (not record['passed'] or record['effective_progress'] in (0,.5,1)):
            # Preserve unique entrance/mid/arrival frames and all actual failures.
            if not record['passed'] or record['effective_progress'] not in group.get('saved_progress',[]):
                image.save(directory/f'F20-transfer-frame-{frame:06d}.png')
                group.setdefault('saved_progress',[]).append(record['effective_progress'])
    records=[r for group in groups.values() for r in group['frames']]
    old.require(len(records)==len(mapping),'All-transfer decode missed a frame')
    components=[c for r in records for c in r['components']]
    f20=groups[20]['frames'];sizes=[r['expected_value_font_size_px'] for r in f20]
    monotonic=all(a>=b for a,b in zip(sizes,sizes[1:])) and sizes[0]==88 and sizes[-1]==47
    for group in groups.values():group['passed']=all(r['passed'] for r in group['frames'])
    return {'kind':'independent-all-native-transfer-frames','passed':all(r['passed'] for r in records) and monotonic,
      'video_sha256':old.sha(video),'handoffs':len(groups),'native_transfer_frames':len(records),
      'native_components':len(components),'max_abs_dx_px':max(abs(c['delta_x_px']) for c in components),
      'max_abs_dy_px':max(abs(c['delta_y_px']) for c in components),'centering_tolerance_px':1,
      'F20_transition':{'start_px':88,'arrival_px':47,'monotonic_expected_sizes':monotonic,
          'actual_glyphs_match_every_expected_size':all(r['passed'] for r in f20),
          'font_size_formula':'round(88 -41 * tick/30), tick=round(smoothstep(clamp((t-start)/1.2s))*30); no second easing'},
      'content_truth':'Independent binomial Fibonacci values; exact integer/comma strings and F indices are carried unchanged. Numerals include one-digit-substitution negative candidates; small-index glyph identities use the preserved independent dictionary gate.',
      'scope':'Every frame from each movement start through its arrival hold, before the next expression. Two moving full numeral groups and their two F labels are native-raster inspected for identity, both axes, containment, nonempty ink, observation-edge contact and pairwise overlap.',
      'transfers':list(groups.values())}

def generic_visual_job(video,plan,states,segments,ffmpeg,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    # The finite override is confined to this spawned worker process. Its
    # try/final guard also prevents leakage between calls inside that worker.
    with v003_labels():result=old.visual_checks(video,plan,states,segments,ffmpeg,directory)
    (directory/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result

def transfer_visual_job(video,plan,ffmpeg,directory):
    result=all_transfer_checks(video,plan,ffmpeg,directory)
    (Path(directory)/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result

def parser():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('video','timeline','master','out-dir'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--delivery-dir',type=Path);p.add_argument('--final-aac-clips-dir',type=Path)
    p.add_argument('--extract-final-clips',action='store_true');p.add_argument('--skip-technical',action='store_true')
    p.add_argument('--ffmpeg',default=shutil.which('ffmpeg'));p.add_argument('--ffprobe',default=shutil.which('ffprobe'))
    return p

def main(argv=None):
    args=parser().parse_args(argv);old.require(args.ffmpeg and args.ffprobe,'FFmpeg/ffprobe required')
    args.out_dir.mkdir(parents=True,exist_ok=False);plan=json.loads(args.timeline.read_text())
    report={'schema_version':1,'kind':'independent-fibonacci-v003-final-verification',
      'checked_at_utc':datetime.now(timezone.utc).isoformat(),'video':str(args.video.resolve()),
      'video_sha256':old.sha(args.video),'timeline_sha256':old.sha(args.timeline),
      'verifier_sha256':old.sha(Path(__file__)),'preserved_independent_verifier':{'path':'tools/verify_fibonacci_video.py','sha256':old.sha(Path(old.__file__))},'passed':False}
    try:
        old.require(plan.get('renderer_implementation')=='tools/render_fibonacci_video_v003.py','Unexpected v003 renderer implementation')
        events,states,segments,report['schedule']=old.validate_schedule(plan)
        if not args.skip_technical:
            report['technical']=old.technical.verify_video(args.video,args.out_dir/'technical',args.timeline,args.ffmpeg,args.ffprobe,duration_bounds=(480,1800))
            old.require(report['technical']['status']=='pass','Technical media checks failed')
            old.require(report['technical']['measurements']['true_peak_dbtp']<=-1.45,'Final AAC true peak exceeds accepted delivery ceiling')
        report['captions_and_metadata']=old.captions_and_metadata(plan,events,args.delivery_dir or args.video.parent)
        with ProcessPoolExecutor(max_workers=2,mp_context=multiprocessing.get_context('spawn')) as pool:
            generic=pool.submit(generic_visual_job,args.video,plan,states,segments,args.ffmpeg,args.out_dir/'visual')
            transfers=pool.submit(transfer_visual_job,args.video,plan,args.ffmpeg,args.out_dir/'all-transfers')
            # No thread shares the legacy module's count_labels mutation. The
            # parent can inspect source/audio and intro/fades while both native
            # visual passes run in separate processes and separate directories.
            excerpts=(args.final_aac_clips_dir or args.video.parent/'audio-final-qa'/'clips') if args.extract_final_clips else None
            with tempfile.TemporaryDirectory(prefix='fibonacci-v003-audio-qa-') as work:
                report['audio']=old.media.audio_checks(plan,events,args.video,args.master,args.ffmpeg,Path(work),excerpts)
            if excerpts:print(json.dumps({'event':'final_aac_manifest_ready','path':report['audio']['recognition_excerpt_manifest']}),flush=True)
            report['intro_and_fades']=intro.run(args.video,plan,args.ffmpeg,args.out_dir/'intro-and-fades')
            report['visual']=generic.result();report['all_transfers']=transfers.result()
        old.require(all(report[k]['passed'] for k in ('visual','audio','all_transfers','intro_and_fades')),'Independent finished-media supplement failed')
        old.require(old.sha(args.video)==report['video_sha256'],'Video changed during verification')
        report['passed']=True
    except Exception as error:report['error']=str(error);raise
    finally:
        report['scope']='Fresh full decode and preserved independent math/cardinal/raster/audio checks, plus every native handoff frame and intro-seed/fade supplements. Historical QA is unchanged. No claim of human continuous viewing/listening.'
        (args.out_dir/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'report':str(args.out_dir/'verification.json')}))

if __name__=='__main__':main()
