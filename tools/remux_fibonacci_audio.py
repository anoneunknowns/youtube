"""Bind corrected Fibonacci audio to the immutable rendered H.264 track.

Both encoded packet/timestamp identity and every decoded video frame are checked
before replacing the delivery alias. Previous render metadata remains archived.
An already accepted AAC file is copied, avoiding a second encoding decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

try:
    from .render_fibonacci_video import ROOT, VIDEO_NAME, digest, local
except ImportError:
    from render_fibonacci_video import ROOT, VIDEO_NAME, digest, local


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def replace_json(path, value):
    temporary = path.with_name(path.name+'.remux-new')
    save(temporary, value)
    temporary.replace(path)


def resolve(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT/path


def visual_contract(plan):
    keys = ('fps', 'width', 'height', 'duration_s', 'duration_frames',
            'counted_states', 'visual_segments', 'intro', 'finale')
    events = [{key: e.get(key) for key in ('id', 'kind', 'index', 'n', 'value',
                                         'scene_id', 'text', 'start_s', 'end_s',
                                         'start_sample_24k', 'end_sample_24k',
                                         'source_path', 'source_sha256')}
              for e in plan['voice_events']]
    return {**{key: plan[key] for key in keys}, 'voice_cue_contract': events}


def packets(path, stream, ffprobe):
    output = subprocess.check_output([
        ffprobe, '-v', 'error', '-select_streams', stream, '-show_packets',
        '-show_entries', 'packet=pts,dts,duration,size,data_hash',
        '-show_data_hash', 'sha256', '-of', 'json', str(path)], text=True)
    rows = json.loads(output)['packets']
    if not rows or any('data_hash' not in row for row in rows):
        raise ValueError(f'No encoded packet hashes for {path}')
    return rows


def md5_frames(path, destination, ffmpeg):
    subprocess.run([ffmpeg, '-v', 'error', '-nostdin', '-n', '-i', str(path),
                    '-map', '0:v:0', '-an', '-f', 'framemd5', str(destination)], check=True)
    return [line.strip() for line in destination.read_text().splitlines()
            if line.strip() and not line.startswith('#')]


def pcm_digest(path, ffmpeg):
    command = [ffmpeg, '-v', 'error', '-nostdin', '-i', str(path), '-map', '0:a:0',
               '-vn', '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s24le', '-f', 's24le', 'pipe:1']
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    result, length = hashlib.sha256(), 0
    while True:
        block = process.stdout.read(1024*1024)
        if not block:
            break
        result.update(block)
        length += len(block)
    if process.wait():
        raise RuntimeError('Audio decoding failed')
    return {'sha256': result.hexdigest(), 'bytes': length,
            'sample_frames_48k_stereo24': length//6}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--previous-dir', type=Path, required=True,
                        help='Immutable earlier MP4/timeline/frame-plan/render-record folder')
    parser.add_argument('--accepted-aac', type=Path, required=True,
                        help='An independently accepted192k-target48k stereo AAC/M4A file')
    parser.add_argument('--accepted-aac-sha256', required=True)
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument('--proof-dir', type=Path, required=True)
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg') or str(ROOT/'.venv/bin/ffmpeg'))
    parser.add_argument('--ffprobe', default=shutil.which('ffprobe') or str(ROOT/'.venv/bin/ffprobe'))
    args = parser.parse_args()
    timeline, previous, accepted = args.timeline.resolve(), args.previous_dir.resolve(), args.accepted_aac.resolve()
    out = (args.out_dir or timeline.parent).resolve()
    proof = args.proof_dir.resolve()
    proof.mkdir(parents=True, exist_ok=False)
    old_video, destination = previous/VIDEO_NAME, out/VIDEO_NAME
    before_plan, plan = read(previous/'timeline.json'), read(timeline)
    if visual_contract(before_plan) != visual_contract(plan):
        raise ValueError('Audio correction changed the visual or spoken cue contract')
    if digest(accepted) != args.accepted_aac_sha256:
        raise ValueError('Accepted AAC checksum does not match')
    master = plan['master_audio']
    if digest(resolve(master['path'])) != master['sha256']:
        raise ValueError('Corrected master checksum mismatch')
    for key in ('speech_manifest', 'speech_acceptance'):
        row = plan[key]
        if digest(resolve(row['path'])) != row['sha256']:
            raise ValueError(f'Accepted speech receipt changed: {key}')
    old_record, old_frame_plan = read(previous/'render-record.json'), read(previous/'frame-plan.json')
    if digest(old_video) != old_record['output_sha256']:
        raise ValueError('Immutable previous video changed')
    if destination.exists() and digest(destination) != digest(old_video):
        raise ValueError('Delivery alias differs from the preserved video; refusing to replace it')
    candidate = proof/'corrected-video.mp4'
    command = [args.ffmpeg, '-hide_banner', '-v', 'warning', '-nostdin', '-n',
               '-i', str(old_video), '-i', str(accepted), '-map', '0:v:0', '-map', '1:a:0',
               '-c:v', 'copy', '-c:a', 'copy', '-map_metadata', '0',
               '-movflags', '+faststart', str(candidate)]
    with (proof/'remux.log').open('x') as stream:
        subprocess.run(command, stdout=stream, stderr=stream, check=True)
    before_packets = packets(old_video, 'v:0', args.ffprobe)
    after_packets = packets(candidate, 'v:0', args.ffprobe)
    save(proof/'original-video-packets.json', before_packets)
    save(proof/'corrected-video-packets.json', after_packets)
    if before_packets != after_packets:
        raise ValueError('H264 payload or presentation/decode timestamps changed')
    old_md5 = md5_frames(old_video, proof/'original-video.framemd5', args.ffmpeg)
    new_md5 = md5_frames(candidate, proof/'corrected-video.framemd5', args.ffmpeg)
    if old_md5 != new_md5 or len(new_md5) != plan['duration_frames']:
        raise ValueError('Decoded video frame identity failed')
    accepted_pcm, final_pcm = pcm_digest(accepted, args.ffmpeg), pcm_digest(candidate, args.ffmpeg)
    if accepted_pcm != final_pcm:
        raise ValueError('Copied AAC decodes differently from its accepted original')
    probe = json.loads(subprocess.check_output([args.ffprobe, '-v', 'error', '-show_streams',
                                               '-show_format', '-of', 'json', str(candidate)], text=True))
    video_stream = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    audio_stream = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
    if not (int(video_stream['nb_frames']) == plan['duration_frames'] and
            video_stream['avg_frame_rate'] == '30/1' and
            (video_stream['width'], video_stream['height']) == (1920,1080) and
            all(video_stream.get(key) == 'bt709' for key in ('color_space','color_transfer','color_primaries')) and
            audio_stream['codec_name'] == 'aac' and audio_stream['sample_rate'] == '48000' and audio_stream['channels'] == 2):
        raise ValueError('Corrected MP4 stream properties are not the delivery contract')
    output_sha = digest(candidate)
    packet_digest = hashlib.sha256(json.dumps(before_packets, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    record = {'schema_version': 1, 'status': 'PASS', 'kind': 'fibonacci-audio-only-copy-remux-proof',
              'original_video': {'path': local(old_video), 'sha256': digest(old_video)},
              'corrected_video': {'path': local(destination), 'sha256': output_sha},
              'previous_timeline': {'path': local(previous/'timeline.json'), 'sha256': digest(previous/'timeline.json')},
              'corrected_timeline': {'path': local(timeline), 'sha256': digest(timeline)},
              'accepted_aac': {'path': local(accepted), 'sha256': digest(accepted)},
              'accepted_aac_decoded_pcm': accepted_pcm,
              'video_packet_count': len(after_packets),
              'identical_H264_packet_payloads_pts_dts_durations': True,
              'video_packet_contract_sha256': packet_digest,
              'identical_decoded_video_framemd5': True,
              'identical_video_frame_count': len(new_md5),
              'identical_visual_and_spoken_cue_contract': True,
              'accepted_AAC_copied_without_reencoding': True,
              'accepted_and_muxed_audio_decoded_pcm_identical': True,
              'unchanged_source_speech': True, 'only_constant_per_utterance_gain_calibration_upstream': True,
              'command': command, 'helper': local(Path(__file__)), 'helper_sha256': digest(Path(__file__)),
              'probe': probe}
    proof_record = proof/'verification.json'
    save(proof_record, record)
    # The old alias, its hash-bound metadata and source timeline are already
    # preserved. Install only after every video/audio identity check succeeds.
    candidate.replace(destination)
    frame_plan = {**old_frame_plan, 'timeline_sha256': digest(timeline),
                  'derived_from_immutable_frame_plan': {'path': local(previous/'frame-plan.json'), 'sha256': digest(previous/'frame-plan.json')},
                  'audio_only_remux_proof': {'path': local(proof_record), 'sha256': digest(proof_record)}}
    replace_json(out/'frame-plan.json', frame_plan)
    render_record = {**old_record, 'timeline': local(timeline), 'timeline_sha256': digest(timeline),
                     'frame_plan': local(out/'frame-plan.json'), 'frame_plan_sha256': digest(out/'frame-plan.json'),
                     'output': local(destination), 'output_sha256': output_sha,
                     'original_encode_command': old_record['encode_command'], 'encode_command': command,
                     'audio_encoder_target_bps': 192000, 'audio_was_previously_encoded_then_copied': True,
                     'previous_render_record': {'path': local(previous/'render-record.json'), 'sha256': digest(previous/'render-record.json')},
                     'audio_only_remux_proof': {'path': local(proof_record), 'sha256': digest(proof_record)},
                     'probe': probe}
    replace_json(out/'render-record.json', render_record)
    print(json.dumps({'status': 'PASS', 'output': str(destination), 'sha256': output_sha,
                      'video_packets_identical': len(after_packets), 'video_frames_identical': len(new_md5),
                      'aac_copied_and_decoded_pcm_identical': True}), flush=True)


if __name__ == '__main__':
    main()
