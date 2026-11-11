"""Finite v003 adapter over the unchanged v002 independent actor verifier."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json,shutil
from pathlib import Path
if __package__:from . import verify_fibonacci_motion_v002 as old
else:import verify_fibonacci_motion_v002 as old

def validate_base_binding(top,motion,motion_path):
    old.require(top.get('renderer_implementation')=='tools/render_fibonacci_video_v003.py','Unexpected v003 renderer implementation')
    # The actor implementation and its base/motion DAG are unchanged. Only the
    # explicitly allowlisted renderer name differs from the strict v002 gate.
    projected=dict(top,renderer_implementation='tools/render_fibonacci_video_v002.py')
    base,report=old.validate_base_binding(projected,motion,motion_path)
    report['actual_finite_renderer_implementation']='tools/render_fibonacci_video_v003.py'
    report['actor_contract']='Unchanged registered-art/motion behavior; v003 changes only F20 teaching-value font interpolation.'
    return base,report

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('video','timeline','out-dir'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--motion-plan',type=Path);p.add_argument('--ffmpeg',default=shutil.which('ffmpeg'));p.add_argument('--ffprobe',default=shutil.which('ffprobe'))
    args=p.parse_args(argv);args.out_dir.mkdir(parents=True,exist_ok=False)
    path=args.motion_plan or args.video.parent/'character-motion.json'
    r={'schema_version':1,'kind':'independent-fibonacci-motion-v003-verification','passed':False,
       'checked_at_utc':datetime.now(timezone.utc).isoformat(),'verifier_sha256':old.sha(Path(__file__)),
       'preserved_motion_verifier':{'path':'tools/verify_fibonacci_motion_v002.py','sha256':old.sha(Path(old.__file__))}}
    try:
        old.require(args.ffmpeg and args.ffprobe,'FFmpeg/ffprobe required')
        r.update(video_sha256=old.sha(args.video),timeline_sha256=old.sha(args.timeline),motion_plan_sha256=old.sha(path))
        top=json.loads(args.timeline.read_text());motion=json.loads(path.read_text())
        _,r['base_binding']=validate_base_binding(top,motion,path)
        poses,r['registered_sources']=old.registered_entries(motion)
        windows,r['window_contract']=old.validate_windows(top,motion,poses)
        layers={};geometry=[]
        for ident,row in poses.items():
            layers[ident],result=old.project_pose(row);geometry.append(result)
        r['geometry']={'passed':all(x['passed'] for x in geometry),'poses':geometry,'alpha_threshold':8,'protected_teacher_regions':list(old.PROTECTED)}
        old.require(r['geometry']['passed'],'Registered actor would clip or obscure teaching content')
        r['decoded_motion']=old.decoded_motion_checks(args.video,top,windows,poses,layers,args.ffmpeg,args.out_dir)
        old.require(r['decoded_motion']['passed'],'Decoded v003 actor motion failed')
        old.require(old.sha(args.video)==r['video_sha256'],'Video changed during verification');r['passed']=True
    except Exception as error:r['error']=str(error);raise
    finally:(args.out_dir/'verification.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':r['passed'],'report':str(args.out_dir/'verification.json')}))

if __name__=='__main__':main()
