"""Replace the final closed GOP with the planned 36-frame inclusive fade.

The frozen original renderer and all previous movies remain unchanged. The
prefix is copied, the final closed GOP is rendered from the same source art,
and the accepted AAC is copied without another encode.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import gzip
import json
import math
from pathlib import Path
import subprocess

from PIL import Image

try:
    import render_powers_of_two_video as base
    import remux_powers_of_two_audio as proof
except ModuleNotFoundError:
    from tools import render_powers_of_two_video as base
    from tools import remux_powers_of_two_audio as proof

ROOT=base.ROOT
FPS=30
FADE_FRAMES=36


class Episode(base.Episode):
    def state(self,f):
        state=super().state(f)
        if state.mode=='outro':
            start=self.plan['duration_frames']-FADE_FRAMES
            alpha=round(255*(f-start)/(FADE_FRAMES-1)) if f>=start else 0
            return replace(state,fade=alpha)
        return state


def key(state):
    return json.dumps(state,sort_keys=True,separators=(',',':'))


def frame_lines(path):
    return [line.strip() for line in path.read_text().splitlines() if line.strip() and not line.startswith('#')]


def tail_encoder(path,frame_count,launch=True):
    # A final I-frame makes the fully opaque cream endpoint independent of
    # previous text-shaped prediction residue. The source RGB frame is uniform.
    args=[proof.FFMPEG,'-hide_banner','-loglevel','error','-nostdin','-n','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','30','-i','-','-an','-vf','scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p','-c:v','libx264','-preset','fast','-crf','18','-force_key_frames',str((frame_count-1)/30),'-pix_fmt','yuv420p','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-color_range','tv','-movflags','+write_colr+faststart',str(path)]
    return (subprocess.Popen(args,stdin=subprocess.PIPE) if launch else None),args


def save_gzip(path,rows):
    with gzip.open(path,'wt',encoding='utf8') as stream:
        for row in rows:
            stream.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--previous-manifest',type=Path,required=True)
    ap.add_argument('--source-render-manifest',type=Path,required=True)
    ap.add_argument('--timeline',type=Path,required=True)
    ap.add_argument('--actor-registration',type=Path,required=True)
    ap.add_argument('--accepted-aac',type=Path,required=True)
    ap.add_argument('--accepted-aac-sha256',required=True)
    ap.add_argument('--out-dir',type=Path,required=True)
    ap.add_argument('--verify-existing',action='store_true',help='Verify the already muxed revision without changing any media or saved source PNG.')
    a=ap.parse_args()
    previous=json.loads(a.previous_manifest.read_text())
    first=json.loads(a.source_render_manifest.read_text())
    original=base.resolve(previous['video']['path'])
    if base.sha(original)!=previous['video']['sha256']:
        raise ValueError('Previous corrected movie changed')
    if base.sha(a.accepted_aac)!=a.accepted_aac_sha256:
        raise ValueError('Accepted AAC changed')
    for source in first['frozen_sources']:
        if base.sha(base.resolve(source['path']))!=source['sha256']:
            raise ValueError(f'Frozen source changed: {source["path"]}')
    ep=Episode(a.timeline,a.actor_registration)
    if ep.plan['duration_frames']!=16954 or ep.plan.get('finale',{}).get('fade_last_s')!=1.2:
        raise ValueError('Expected the accepted16954-frame plan with1.2-second final fade')
    old_plan=json.loads(base.resolve(first['timeline']['path']).read_text())
    if proof.contract(old_plan)!=proof.contract(ep.plan):
        # prepared_plan adds two derived frame keys without changing source
        # timeline contents, so compare the saved corrected plan directly.
        if proof.contract(old_plan)!=proof.contract(json.loads(a.timeline.read_text())):
            raise ValueError('The corrected timeline changed the visual/voice contract')
    full_packets=json.loads(subprocess.check_output([proof.FFPROBE,'-v','error','-select_streams','v:0','-show_packets','-show_entries','packet=pts,pts_time,dts,duration,size,data_hash,flags','-show_data_hash','sha256','-of','json',str(original)],text=True))['packets']
    fade_start=ep.plan['duration_frames']-FADE_FRAMES
    boundary=max(round(float(p['pts_time'])*FPS) for p in full_packets if 'K' in p.get('flags','') and round(float(p['pts_time'])*FPS)<=fade_start)
    if boundary!=16750:
        raise ValueError(f'Unexpected closed-GOP splice frame {boundary}')
    if not a.verify_existing:
        a.out_dir.mkdir(parents=True,exist_ok=False)
    work=a.out_dir/'proof'
    if not a.verify_existing:
        work.mkdir()
    prefix=work/'unchanged-prefix.mp4'
    if not a.verify_existing:
        subprocess.run([proof.FFMPEG,'-hide_banner','-v','warning','-nostdin','-n','-i',str(original),'-map','0:v:0','-an','-c:v','copy','-frames:v',str(boundary),'-movflags','+write_colr+faststart',str(prefix)],check=True)
    old_packets=proof.packets(original,'v:0');prefix_packets=proof.packets(prefix,'v:0')
    if prefix_packets!=old_packets[:boundary]:
        raise ValueError('The copied prefix packet/timestamp contract changed')
    new_tail=work/'regenerated-tail.mp4';tail_count=ep.plan['duration_frames']-boundary
    process,encode_command=tail_encoder(new_tail,tail_count,launch=not a.verify_existing)
    tail_reports={}
    tail_semantics=[]
    for f in range(boundary,ep.plan['duration_frames']):
        state=ep.state(f);raw,report=ep.image(state)
        if f==ep.plan['duration_frames']-1:
            image=Image.frombytes('RGB',base.SIZE,raw)
            if image.getextrema()!=tuple((v,v) for v in image.getpixel((0,0))):
                raise ValueError('Last raw frame is not uniform opaque cream')
            if state.fade!=255:
                raise ValueError('Final raw opacity is not255')
            if a.verify_existing:
                if Image.open(work/'final-raw-cream.png').convert('RGB').tobytes()!=raw:
                    raise ValueError('Saved final raw frame differs from the deterministic source')
            else:
                image.save(work/'final-raw-cream.png')
        if process:
            process.stdin.write(raw)
        tail_reports[report['key']]=report
        tail_semantics.append(dict(frame=f,state=asdict(state),state_key=report['key']))
        if f>=fade_start:
            snapshot=work/f'fade-source-{f:05d}.png'
            if a.verify_existing:
                if Image.open(snapshot).convert('RGB').tobytes()!=raw:
                    raise ValueError(f'Saved fade source differs at {f}')
            else:
                Image.frombytes('RGB',base.SIZE,raw).save(snapshot)
    if process:
        process.stdin.close()
        if process.wait()!=0:
            raise RuntimeError('Tail encode failed')
    prefix_probe=proof.probe(prefix);tail_probe=proof.probe(new_tail)
    prefix_v=next(s for s in prefix_probe['streams'] if s['codec_type']=='video');tail_v=next(s for s in tail_probe['streams'] if s['codec_type']=='video')
    if prefix_v.get('extradata_hash')!=tail_v.get('extradata_hash'):
        raise ValueError('Regenerated tail has incompatible H264 SPS/PPS extradata')
    listing=work/'picture.ffconcat'
    if not a.verify_existing:
        listing.write_text("ffconcat version 1.0\n"+f"file '{prefix.resolve()}'\nduration {boundary/FPS:.15f}\nfile '{new_tail.resolve()}'\n")
    final=a.out_dir/original.name
    mux_command=[proof.FFMPEG,'-hide_banner','-v','warning','-nostdin','-n','-f','concat','-safe','0','-auto_convert','0','-i',str(listing),'-i',str(a.accepted_aac),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','copy','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv','-movflags','+write_colr+faststart',str(final)]
    existing_media_receipt=None
    if a.verify_existing:
        existing_media_receipt=base.receipt(final)
        failed=json.loads((work/'first-verification-attempt.json').read_text())
        if existing_media_receipt!=failed['video']:
            raise ValueError('Already muxed media changed after its first verification')
    else:
        with (work/'mux.log').open('x') as stream:
            subprocess.run(mux_command,stdout=stream,stderr=stream,check=True)
    final_packets=proof.packets(final,'v:0')
    if final_packets[:boundary]!=old_packets[:boundary] or len(final_packets)!=ep.plan['duration_frames']:
        raise ValueError('Spliced prefix packets or total frame count changed')
    old_presentation=sorted((int(p['pts']),int(p['duration'])) for p in old_packets)
    new_presentation=sorted((int(p['pts']),int(p['duration'])) for p in final_packets)
    if old_presentation!=new_presentation or [p['dts'] for p in old_packets]!=[p['dts'] for p in final_packets]:
        raise ValueError('Video presentation grid or decode clock changed')
    aac_packets=proof.packets(a.accepted_aac,'a:0');final_audio_packets=proof.packets(final,'a:0')
    if aac_packets!=final_audio_packets:
        raise ValueError('Accepted AAC packets changed')
    # Reuse the independently proven v002 full decoded frame inventory, then
    # decode every frame in the new movie and compare the unchanged prefix.
    parent_md5=original.parent/'corrected-video.framemd5'
    old_hashes=frame_lines(parent_md5);new_hashes=proof.frames(final,work/'final-video.framemd5')
    if len(new_hashes)!=ep.plan['duration_frames'] or old_hashes[:boundary]!=new_hashes[:boundary]:
        raise ValueError('Decoded unchanged-prefix identity failed')
    accepted_pcm,final_pcm=proof.pcm(a.accepted_aac),proof.pcm(final)
    if accepted_pcm!=final_pcm:
        raise ValueError('Accepted AAC decoded PCM changed')
    old_frames=base.resolve(first['frame_states']['path']);all_states=[];actual_changed=[]
    for line in gzip.open(old_frames,'rt'):
        old=json.loads(line);f=old['frame'];new=asdict(ep.state(f));old_state=old['state']
        if {k:v for k,v in new.items() if k!='fade'}!={k:v for k,v in old_state.items() if k!='fade'}:
            raise ValueError(f'Non-fade state changed at {f}')
        if new!=old_state:
            actual_changed.append(f)
        all_states.append(dict(frame=f,time_s=f/FPS,state_key=key(new),state=new))
    if any(f<fade_start for f in actual_changed):
        raise ValueError('Fade revision altered an earlier state')
    save_gzip(a.out_dir/'visual-frame-states.jsonl.gz',all_states)
    old_reports=base.resolve(first['state_reports']['path']);reports={}
    for line in gzip.open(old_reports,'rt'):
        row=json.loads(line);reports[row['key']]=row
    reports.update(tail_reports)
    used_keys={r['state_key'] for r in all_states}
    save_gzip(a.out_dir/'distinct-state-reports.jsonl.gz',[reports[k] for k in sorted(used_keys)])
    save_gzip(work/'regenerated-tail-state-reports.jsonl.gz',tail_reports.values())
    final_probe=proof.probe(final);v=next(s for s in final_probe['streams'] if s['codec_type']=='video')
    if not (v['nb_frames']=='16954' and v['avg_frame_rate']=='30/1' and v['color_range']=='tv' and all(v.get(k)=='bt709' for k in ['color_space','color_transfer','color_primaries'])):
        raise ValueError('Final stream format/tags failed')
    if existing_media_receipt and base.receipt(final)!=existing_media_receipt:
        raise ValueError('Existing MP4 was unexpectedly rewritten during proof')
    record=dict(schema_version=1,status='fade_corrected_pending_independent_final_acceptance',completed=False,video=base.receipt(final),parent_render_manifest=base.receipt(a.previous_manifest),original_source_render=base.receipt(a.source_render_manifest),timeline=base.receipt(a.timeline),renderer_revision=base.receipt(__file__),picture_generation_source_snapshot=base.receipt(work/'renderer-generation-before-proof-correction.py') if a.verify_existing else base.receipt(__file__),proof_resumed_without_rewriting_media=a.verify_existing,frozen_base_renderer=base.receipt(base.__file__),accepted_aac=base.receipt(a.accepted_aac),frame_count=16954,duration_s=16954/30,splice_start_frame=boundary,unchanged_prefix_frames=boundary,regenerated_tail_frames=tail_count,fade_window=dict(start_frame=fade_start,end_frame_inclusive=16953,frame_count=36,coefficient='round(255*j/35), j=0..35',first=0,last=255,actual_changed_state_frames=actual_changed),unchanged_prefix_packet_payloads_pts_dts_durations=True,unchanged_prefix_decoded_frame_md5=True,all_presentation_pts_durations_unchanged=True,all_packet_decode_clock_dts_unchanged=True,regenerated_tail_b_frame_decode_order_may_differ=True,accepted_AAC_all_packets_pts_dts_durations_identical=True,accepted_AAC_decoded_PCM_identical=True,accepted_AAC_copied_without_reencoding=True,accepted_decoded_pcm=accepted_pcm,parent_decoded_frames=base.receipt(parent_md5),new_decoded_frames=base.receipt(work/'final-video.framemd5'),frame_states=base.receipt(a.out_dir/'visual-frame-states.jsonl.gz'),state_reports=base.receipt(a.out_dir/'distinct-state-reports.jsonl.gz'),regenerated_tail_reports=base.receipt(work/'regenerated-tail-state-reports.jsonl.gz'),all_tail_source_layouts_passed=all(r['source_alignment_passed'] for r in tail_reports.values()),all36_tail_fade_raw_frames_saved=True,final_raw_uniform_cream=True,encode_tail_command=encode_command,mux_command=mux_command,probe=final_probe)
    proof.save(a.out_dir/'render-manifest-v003.json',record)
    print(json.dumps(dict(status='splice_and_fade_source_proof_passed',video=record['video'],unchanged_prefix_frames=boundary,regenerated_tail_frames=tail_count,fade_frames=36,audio_packets=len(aac_packets))),flush=True)


if __name__=='__main__':
    main()
