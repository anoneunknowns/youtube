"""Copy an accepted corrected AAC onto the immutable Powers-of-Two picture.

Never rewrite the first MP4, timeline, PCM or render manifest. Preparation can
run while the sound engineer calibrates a new derived PCM/AAC revision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
FFMPEG=shutil.which('ffmpeg') or str(ROOT/'.venv/bin/ffmpeg')
FFPROBE=shutil.which('ffprobe') or str(ROOT/'.venv/bin/ffprobe')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve(path):
    path=Path(path)
    return path if path.is_absolute() else ROOT/path


def receipt(path):
    path=Path(path).resolve()
    return dict(path=str(path.relative_to(ROOT)),sha256=digest(path))


def save(path,value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')


def packets(path,stream):
    result=subprocess.check_output([FFPROBE,'-v','error','-select_streams',stream,'-show_packets','-show_entries','packet=pts,dts,duration,size,data_hash','-show_data_hash','sha256','-of','json',str(path)],text=True)
    rows=json.loads(result)['packets']
    if not rows or any('data_hash' not in r for r in rows):
        raise ValueError('Encoded packet hash missing')
    return rows


def probe(path):
    return json.loads(subprocess.check_output([FFPROBE,'-v','error','-show_streams','-show_format','-show_data_hash','sha256','-of','json',str(path)],text=True))


def frames(path,destination):
    subprocess.run([FFMPEG,'-v','error','-nostdin','-n','-i',str(path),'-map','0:v:0','-an','-f','framemd5',str(destination)],check=True)
    return [line.strip() for line in destination.read_text().splitlines() if line.strip() and not line.startswith('#')]


def pcm(path):
    command=[FFMPEG,'-v','error','-nostdin','-i',str(path),'-map','0:a:0','-vn','-ar','48000','-ac','2','-c:a','pcm_s24le','-f','s24le','pipe:1']
    process=subprocess.Popen(command,stdout=subprocess.PIPE);h=hashlib.sha256();length=0
    while data:=process.stdout.read(2**20):
        h.update(data);length+=len(data)
    if process.wait():
        raise RuntimeError('AAC PCM decode failed')
    return dict(sha256=h.hexdigest(),bytes=length,sample_frames_48k_stereo24=length//6)


def contract(plan):
    keys=('fps','width','height','duration_s','duration_frames','counted_states','visual_segments','intro','finale')
    event_keys=('id','kind','phase','index','insert_after','value','text','start_s','end_s','duration_s','start_sample_24k','end_sample_24k','source_path','source_sha256')
    return {**{key:plan.get(key) for key in keys},'voice_events':[{key:e.get(key) for key in event_keys} for e in plan['voice_events']]}


def prepare(manifest,proof):
    record=json.loads(manifest.read_text());original=resolve(record['video']['path'])
    if digest(original)!=record['video']['sha256']:
        raise ValueError('First MP4 changed')
    proof.mkdir(parents=True,exist_ok=False)
    original_packets=packets(original,'v:0')
    save(proof/'original-video-packets.json',original_packets)
    decoded=frames(original,proof/'original-video.framemd5')
    if len(decoded)!=record['frame_count']:
        raise ValueError('First MP4 frame count failed')
    value=dict(status='prepared',original=receipt(original),previous_render=receipt(manifest),video_packet_count=len(original_packets),decoded_frames=len(decoded),original_probe=probe(original))
    save(proof/'preparation.json',value)
    print(json.dumps({k:value[k] for k in ['status','video_packet_count','decoded_frames']}),flush=True)


def remux(manifest,proof,timeline,aac,aac_sha,correction,out):
    before=json.loads(manifest.read_text());prepared=json.loads((proof/'preparation.json').read_text())
    original=resolve(before['video']['path']);old_timeline=resolve(before['timeline']['path'])
    if receipt(original)!=prepared['original'] or receipt(manifest)!=prepared['previous_render']:
        raise ValueError('Immutable first render or its manifest changed')
    if digest(aac)!=aac_sha:
        raise ValueError('Accepted AAC checksum differs')
    if digest(old_timeline)!=before['timeline']['sha256']:
        raise ValueError('Immutable first-render audio timeline changed')
    old_plan,new_plan=json.loads(old_timeline.read_text()),json.loads(timeline.read_text())
    if contract(old_plan)!=contract(new_plan):
        raise ValueError('Audio correction moved a visual, utterance or timing contract')
    master=new_plan.get('master_audio')
    if master and digest(resolve(master['path']))!=master['sha256']:
        raise ValueError('Corrected PCM source checksum differs')
    out.mkdir(parents=True,exist_ok=False)
    candidate=out/original.name
    command=[FFMPEG,'-hide_banner','-v','warning','-nostdin','-n','-i',str(original),'-i',str(aac),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','copy','-map_metadata','0','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv','-movflags','+write_colr+faststart',str(candidate)]
    with (out/'remux.log').open('x') as stream:
        subprocess.run(command,stdout=stream,stderr=stream,check=True)
    old_packets=json.loads((proof/'original-video-packets.json').read_text())
    new_packets=packets(candidate,'v:0');save(out/'corrected-video-packets.json',new_packets)
    if old_packets!=new_packets:
        raise ValueError('H264 payload/PTS/DTS/durations changed')
    source_audio_packets=packets(aac,'a:0');new_audio_packets=packets(candidate,'a:0')
    save(out/'accepted-aac-packets.json',source_audio_packets);save(out/'corrected-aac-packets.json',new_audio_packets)
    if source_audio_packets!=new_audio_packets:
        raise ValueError('Accepted AAC packets/PTS/DTS/durations changed')
    old_frames=[line.strip() for line in (proof/'original-video.framemd5').read_text().splitlines() if line.strip() and not line.startswith('#')]
    new_frames=frames(candidate,out/'corrected-video.framemd5')
    if old_frames!=new_frames or len(new_frames)!=before['frame_count']:
        raise ValueError('Decoded picture identity failed')
    accepted_pcm,final_pcm=pcm(aac),pcm(candidate)
    if accepted_pcm!=final_pcm:
        raise ValueError('Copied AAC decoded differently')
    result_probe=probe(candidate);vs=next(s for s in result_probe['streams'] if s['codec_type']=='video');au=next(s for s in result_probe['streams'] if s['codec_type']=='audio')
    original_vs=next(s for s in prepared['original_probe']['streams'] if s['codec_type']=='video')
    if vs.get('extradata_hash')!=original_vs.get('extradata_hash'):
        raise ValueError('H264 SPS/PPS extradata changed during container tagging')
    if not (vs['nb_frames']==str(before['frame_count']) and vs['avg_frame_rate']=='30/1' and (vs['width'],vs['height'])==(1920,1080) and all(vs.get(k)=='bt709' for k in ['color_space','color_transfer','color_primaries']) and vs.get('color_range')=='tv' and au['codec_name']=='aac' and au['sample_rate']=='48000' and au['channels']==2):
        raise ValueError('Delivery stream properties changed')
    record=dict(schema_version=1,status='audio_corrected_pending_final_independent_acceptance',completed=False,kind='powers-of-two-audio-and-container-color-copy-remux',video=receipt(candidate),previous_render_manifest=receipt(manifest),original_video=receipt(original),previous_timeline=receipt(old_timeline),timeline=receipt(timeline),accepted_aac=receipt(aac),source_bound_audio_correction=receipt(correction),preparation=receipt(proof/'preparation.json'),frame_count=before['frame_count'],duration_s=before['duration_s'],visual_frame_states=before['frame_states'],distinct_visual_state_reports=before['state_reports'],identical_visual_and_utterance_contract=True,identical_H264_payloads_pts_dts_durations=True,identical_H264_packet_count=len(new_packets),identical_H264_SPS_PPS_extradata=True,H264_extradata_hash=vs.get('extradata_hash'),container_only_color_correction={'range':'tv','space':'bt709','primaries':'bt709','transfer':'bt709','mp4_colr_written':True,'video_reencoded':False,'bitstream_filter_applied':False},identical_decoded_frame_md5=True,identical_decoded_frame_count=len(new_frames),accepted_AAC_copied_without_reencoding=True,identical_accepted_AAC_payloads_pts_dts_durations=True,identical_AAC_packet_count=len(new_audio_packets),accepted_and_muxed_decoded_PCM_identical=True,accepted_decoded_pcm=accepted_pcm,probe=result_probe,command=command,helper=receipt(__file__))
    save(out/'render-manifest-v002.json',record)
    print(json.dumps(dict(status='copy_remux_passed',video=receipt(candidate),video_packets=len(new_packets),video_frames=len(new_frames),audio_packets=len(new_audio_packets))),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','remux']);p.add_argument('--previous-manifest',type=Path,required=True);p.add_argument('--proof-dir',type=Path,required=True);p.add_argument('--timeline',type=Path);p.add_argument('--accepted-aac',type=Path);p.add_argument('--accepted-aac-sha256');p.add_argument('--audio-correction',type=Path);p.add_argument('--out-dir',type=Path);a=p.parse_args()
    if a.action=='prepare':
        prepare(a.previous_manifest,a.proof_dir)
    else:
        if not all([a.timeline,a.accepted_aac,a.accepted_aac_sha256,a.audio_correction,a.out_dir]):
            p.error('remux requires timeline, accepted AAC/hash, correction and new out-dir')
        remux(a.previous_manifest,a.proof_dir,a.timeline,a.accepted_aac,a.accepted_aac_sha256,a.audio_correction,a.out_dir)


if __name__=='__main__':
    main()
