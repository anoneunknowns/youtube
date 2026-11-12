"""Copy an immutable square episode while explicitly repairing H.264 VUI.

Decoded YUV frame MD5s and every AAC packet's payload hash and timestamps must
remain identical. The original media, audio adoption and earlier QA are retained.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local(path):
    return str(Path(path).resolve().relative_to(ROOT))


def ref(path):
    return {'path':local(path),'sha256':sha(path)}


def binary(name):
    p=ROOT/'.venv/bin'/name
    return str(p) if p.exists() else shutil.which(name)


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def run(command,log_path):
    result=subprocess.run(command,capture_output=True,text=True)
    log_path.write_text(result.stderr)
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}), inspect {log_path}')
    return result.stdout


def probe(path,qa,label):
    command=[binary('ffprobe'),'-v','error','-show_streams','-show_format','-of','json',str(path)]
    result=json.loads(run(command,qa/f'{label}-probe.log'))
    target=qa/f'{label}-probe.json';save(target,result)
    return {'command':command,'artifact':ref(target),'data':result}


def packets(path,qa,label):
    command=[binary('ffprobe'),'-v','error','-select_streams','a:0','-show_packets','-show_data_hash','sha256',
             '-show_entries','packet=pts,dts,duration,pts_time,dts_time,duration_time,size,flags,data_hash:packet_side_data',
             '-of','json',str(path)]
    result=json.loads(run(command,qa/f'{label}-aac-packets.log'))
    target=qa/f'{label}-aac-packets.json';save(target,result)
    return {'command':command,'artifact':ref(target),'packets':result['packets']}


def frames(path,qa,label):
    target=qa/f'{label}-decoded-video.framemd5'
    command=[binary('ffmpeg'),'-nostdin','-v','error','-threads','4','-i',str(path),'-map','0:v:0','-an',
             '-pix_fmt','yuv420p','-fps_mode','passthrough','-f','framemd5',str(target)]
    run(command,qa/f'{label}-framemd5.log')
    rows=[r.strip() for r in target.read_text().splitlines() if r.strip() and not r.startswith('#')]
    return {'command':command,'artifact':ref(target),'rows':rows}


def repair(source,out_dir,qa):
    source=Path(source).resolve();out_dir=Path(out_dir).resolve();qa=Path(qa).resolve()
    if out_dir.exists() or qa.exists():
        raise FileExistsError('Use fresh output and QA directories; preserve earlier outputs')
    source_ref=ref(source)
    out_dir.mkdir(parents=True)
    qa.mkdir(parents=True)
    destination=out_dir/source.name
    command=[binary('ffmpeg'),'-nostdin','-v','info','-copyts','-start_at_zero','-i',str(source),
             '-map','0:v:0','-map','0:a:0','-c','copy',
             '-bsf:v','h264_metadata=video_full_range_flag=0:colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1',
             '-color_primaries:v','bt709','-color_trc:v','bt709','-colorspace:v','bt709','-color_range:v','tv',
             '-video_track_timescale','15360','-movflags','+faststart+write_colr',str(destination)]
    save(qa/'remux-command.json',{'command':command,'source':source_ref,'source_preserved':True,
         'operation':'H.264 VUI and MP4 colour description metadata only; video/audio stream copy'})
    run(command,qa/'remux.log')
    with ThreadPoolExecutor(max_workers=6) as executor:
        jobs={
            'old_probe':executor.submit(probe,source,qa,'old'),
            'new_probe':executor.submit(probe,destination,qa,'new'),
            'old_packets':executor.submit(packets,source,qa,'old'),
            'new_packets':executor.submit(packets,destination,qa,'new'),
            'old_frames':executor.submit(frames,source,qa,'old'),
            'new_frames':executor.submit(frames,destination,qa,'new'),
        }
        result={name:job.result() for name,job in jobs.items()}
    oldv=next(x for x in result['old_probe']['data']['streams'] if x['codec_type']=='video')
    newv=next(x for x in result['new_probe']['data']['streams'] if x['codec_type']=='video')
    tags={key:newv.get(key) for key in ('color_range','color_space','color_transfer','color_primaries')}
    tags_pass=tags=={'color_range':'tv','color_space':'bt709','color_transfer':'bt709','color_primaries':'bt709'}
    a=result['old_packets']['packets'];b=result['new_packets']['packets']
    packets_equal=a==b
    packet_diffs=[i for i,(x,y) in enumerate(zip(a,b)) if x!=y]
    fa=result['old_frames']['rows'];fb=result['new_frames']['rows']
    frames_equal=fa==fb
    frame_diffs=[i for i,(x,y) in enumerate(zip(fa,fb)) if x!=y]
    preserved=sha(source)==source_ref['sha256']
    checks={
        'all_bt709_and_tv_tags':tags_pass,
        'all_19405_decoded_frame_rows_identical':frames_equal and len(fa)==len(fb)==19405,
        'all_AAC_packet_content_hashes_and_timestamps_identical':packets_equal and len(a)==len(b),
        'width_height_fps_framecount_unchanged':all(oldv.get(k)==newv.get(k) for k in ('width','height','r_frame_rate','avg_frame_rate','nb_frames')),
        'video_duration_unchanged':oldv['duration']==newv['duration'],
        'source_bytes_preserved':preserved,
    }
    artifacts={key:{k:v for k,v in value.items() if k not in ('rows','packets','data')} for key,value in result.items()}
    report={'schema_version':1,'kind':'square-h264-colour-vui-lossless-correction','created_at_utc':datetime.now(timezone.utc).isoformat(),
            'source':source_ref,'corrected_video':ref(destination),'repair_script':ref(Path(__file__)),
            'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'new_tags':tags,
            'old_tags':{key:oldv.get(key) for key in tags},'decoded_video_frame_count':len(fb),'aac_packet_count':len(b),
            'frame_differences':frame_diffs,'packet_differences':packet_diffs,'command':command,'artifacts':artifacts,
            'inheritance_scope':'Identical decoded YUV420p frame hashes and complete AAC packet records preserve prior pixel-content, timing, mathematical, acting and audio evidence. New colour-tag verification applies to this corrected MP4.',
            'video_reencoded':False,'audio_reencoded':False,'prior_media_or_QA_overwritten':False}
    save(qa/'metadata-correction.json',report)
    save(out_dir/'metadata-correction.json',report)
    if not all(checks.values()):
        raise RuntimeError(f'Lossless correction verification failed: {checks}')
    return {k:v for k,v in report.items() if k not in ('artifacts','command')}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    parser.add_argument('--qa-dir',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(repair(args.source,args.out_dir,args.qa_dir),ensure_ascii=False,indent=2))
