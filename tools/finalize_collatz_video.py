"""Set explicit BT.709 VUI tags without re-encoding picture or AAC audio.

The original render stays intact. Full RGB-frame hashes and AAC packet hashes
with timestamps must match before its decoded-content QA can be inherited.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def executable(name):
    candidate=ROOT/'.venv/bin'/name
    found=str(candidate) if candidate.is_file() else shutil.which(name)
    if not found:raise FileNotFoundError(f'{name} is required on PATH')
    return found


FF=executable('ffmpeg');FP=executable('ffprobe')


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def frame_hashes(p):
    raw=subprocess.check_output([str(FF),'-v','error','-i',str(p),'-map','0:v:0','-pix_fmt','rgb24','-f','framemd5','-'])
    return [line for line in raw.decode().splitlines() if line and not line.startswith('#')]


def packets(p):
    return json.loads(subprocess.check_output([str(FP),'-v','error','-select_streams','a:0','-show_packets','-show_data_hash','sha256',
                '-show_entries','packet=pts,dts,duration,size,data_hash','-of','json',str(p)]))['packets']


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out-dir',required=True);a=p.parse_args()
    src=Path(a.source).resolve();out=Path(a.out_dir).resolve();out.mkdir(parents=True,exist_ok=False);dst=out/src.name
    command=[str(FF),'-v','error','-i',str(src),'-map','0','-c','copy','-bsf:v',
             'h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1',
             '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-movflags','+faststart',str(dst)]
    subprocess.run(command,check=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs=[pool.submit(fn,path) for fn,path in [(frame_hashes,src),(frame_hashes,dst),(packets,src),(packets,dst)]]
        old_frames,new_frames,old_aac,new_aac=[f.result() for f in jobs]
    if old_frames!=new_frames or old_aac!=new_aac:raise ValueError('Decoded pictures or AAC payload/timestamps changed')
    probe=json.loads(subprocess.check_output([str(FP),'-v','error','-show_streams','-show_format','-of','json',str(dst)]))
    v=next(s for s in probe['streams'] if s['codec_type']=='video')
    if any(v.get(k)!='bt709' for k in ['color_primaries','color_transfer','color_space']):raise ValueError('Incomplete BT.709 VUI tags')
    for name in ['english-captions.srt','subtitles.srt','chapters.txt','youtube-title.txt','youtube-description.txt','upload-details.txt']:
        shutil.copy2(src.parent/name,out/name)
    evidence={'kind':'collatz-color-metadata-finalization','source':{'path':str(src.relative_to(ROOT)),'sha256':sha(src)},
              'final':{'path':str(dst.relative_to(ROOT)),'sha256':sha(dst),'bytes':dst.stat().st_size},
              'method':'H264 VUI metadata filter and stream copy; no picture or AAC re-encoding',
              'all_rgb_frames_identical':True,'frame_count':len(new_frames),'aac_packets_and_timestamps_identical':True,'aac_packet_count':len(new_aac),
              'bt709_tags':{k:v[k] for k in ['color_primaries','color_transfer','color_space']},
              'probe':probe,'qa_inheritance':'Only content/geometry/acting/AAC recognition on the exact source can be inherited; this file verifies final technical tags and full picture/audio identity.'}
    (out/'frame-md5-comparison.json').write_text(json.dumps({'identical':True,'frames':new_frames},indent=2)+'\n')
    (out/'aac-packet-comparison.json').write_text(json.dumps({'identical':True,'packets':new_aac},indent=2)+'\n')
    (out/'color-finalization.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in evidence.items() if k not in ['probe']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
