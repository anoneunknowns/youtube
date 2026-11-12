"""Copy accepted AAC while binding a revised audio timeline to v003 picture.

No encoding is performed. Uses the preserved v001 helper's existing preparation.
`remux` requires an immutable-compatible final timeline, the approved AAC's exact
SHA and a hash-bound acceptance report. Use a new target directory; no previous
MP4, old QA or catalog is modified by this script.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path('/Users/support/codex/youtube')
EPISODE = ROOT / 'output/powers-of-two-counting-001-v001'
DEFAULT_SOURCE = EPISODE / 'video/v003-fade-corrected/paspla-studio-powers-of-two-1-to-18446744073709551616-1080p.mp4'
EXPECTED_SOURCE_SHA = '987c324fb1245474fade766f9a8fae656f69905899dd10e4c14a8c6984fc395f'
DEFAULT_TIMELINE = EPISODE / 'audio-build/codec-v002/timeline.json'
DEFAULT_PROOF = EPISODE / 'recheck-20261112-v001/video/remux-v004-preparation'
DEFAULT_OUTPUT = EPISODE / 'video/v004-audio-reencoded'
DEFAULT_REVISION_RECORD = EPISODE / 'recheck-20261112-v001/video/helper-revisions/v002-final-revision.json'
FFMPEG = ROOT / '.venv/bin/ffmpeg'
FFPROBE = ROOT / '.venv/bin/ffprobe'
FRAME_COUNT = 16954


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def receipt(path):
    path = Path(path).resolve()
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha(path)}


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def resolve(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def capture(command, destination):
    with Path(destination).open('xb') as stream:
        subprocess.run([str(c) for c in command], stdout=stream, check=True)


def probe(path, destination):
    capture([FFPROBE, '-v', 'error', '-show_streams', '-show_format',
             '-show_data_hash', 'sha256', '-of', 'json', path], destination)
    return json.loads(Path(destination).read_text())


def packets(path, selection, destination):
    capture([FFPROBE, '-v', 'error', '-select_streams', selection,
             '-show_packets', '-show_entries',
             'packet=pts,dts,duration,size,flags,data_hash',
             '-show_data_hash', 'sha256', '-of', 'json', path], destination)
    rows = json.loads(Path(destination).read_text())['packets']
    require(rows and all(all(k in r for k in ('pts', 'dts', 'duration', 'size', 'flags', 'data_hash')) for r in rows),
            f'Missing packet identity/timing fields in {path}')
    return rows


def frames(path, destination):
    capture([FFMPEG, '-nostdin', '-v', 'error', '-xerror', '-i', path,
             '-map', '0:v:0', '-an', '-fps_mode', 'passthrough',
             '-pix_fmt', 'yuv420p', '-f', 'framemd5', 'pipe:1'], destination)
    return frame_rows(destination)


def frame_rows(path):
    return [line.strip() for line in Path(path).read_text().splitlines()
            if line.strip() and not line.startswith('#')]


def stream(document, kind):
    found = [s for s in document['streams'] if s['codec_type'] == kind]
    require(len(found) == 1, f'Expected one {kind} stream')
    return found[0]


def video_contract(vs, rows):
    require(vs['codec_name'] == 'h264' and (vs['width'], vs['height']) == (1920, 1080), 'Video format changed')
    require(vs['pix_fmt'] == 'yuv420p' and vs['avg_frame_rate'] == '30/1' and vs['r_frame_rate'] == '30/1', 'Video pixel/fps contract changed')
    require(vs['nb_frames'] == str(FRAME_COUNT) and len(rows) == FRAME_COUNT, 'Video packet/frame count differs')
    require(vs['start_pts'] == 0 and vs['color_range'] == 'tv', 'Video origin/range changed')
    require(all(vs[k] == 'bt709' for k in ('color_space', 'color_transfer', 'color_primaries')), 'BT709 tags differ')
    require(Fraction(vs['time_base']) * vs['duration_ts'] == Fraction(FRAME_COUNT, 30), 'Video duration ticks differ')
    require(Fraction(vs['time_base']) * max(int(p['pts']) + int(p['duration']) for p in rows) == Fraction(FRAME_COUNT, 30),
            'Video packet presentation endpoint differs')


def audio_contract(au, plan):
    require(au['codec_name'] == 'aac' and au['profile'] == 'LC' and au['sample_rate'] == '48000'
            and au['channels'] == 2 and au['channel_layout'] == 'stereo', 'Accepted AAC must be48kHz stereo AAC-LC')
    require(au['start_pts'] == 0, 'Audio stream origin changed')
    expected_samples = round(plan['duration_s'] * 48000)
    actual = Fraction(au['time_base']) * au['duration_ts'] * 48000
    require(abs(actual - expected_samples) <= 1, 'Accepted AAC end differs from measured timeline by more than1sample')
    return {'start_sample_48k': 0, 'expected_end_sample_48k': expected_samples,
            'actual_end_sample_48k': str(actual), 'audio_end_s': str(actual / 48000),
            'video_end_s': str(Fraction(FRAME_COUNT, 30)),
            'video_minus_audio_end_s': str(Fraction(FRAME_COUNT, 30) - actual / 48000)}


def pcm_digest(path):
    command = [FFMPEG, '-nostdin', '-v', 'error', '-xerror', '-i', path,
               '-map', '0:a:0', '-vn', '-ar', '48000', '-ac', '2', '-c:a',
               'pcm_s24le', '-f', 's24le', 'pipe:1']
    h = hashlib.sha256()
    size = 0
    with subprocess.Popen([str(c) for c in command], stdout=subprocess.PIPE) as process:
        while block := process.stdout.read(2**20):
            h.update(block)
            size += len(block)
        require(process.wait() == 0, 'Audio decode failed')
    require(size % 6 == 0, 'Decoded stereo24bit PCM has incomplete sample frame')
    return {'sha256': h.hexdigest(), 'bytes': size, 'sample_frames_48k_stereo24': size // 6}


def immutable_timeline_contract(plan):
    """Audio master/codec metadata may change; teaching/source/time may not."""
    keys = ('schema_version', 'episode_id', 'revision_id', 'speech_adopted',
            'fps', 'width', 'height', 'duration_s', 'duration_frames',
            'count_index_start', 'count_index_end', 'count_start', 'count_end',
            'counted_values', 'doubling_operations', 'voice_event_count',
            'source_sample_rate_hz', 'master_sample_rate_hz', 'master_channels',
            'voice_sum_s', 'counted_states', 'visual_segments', 'scenes',
            'teaching', 'intro', 'finale', 'timing', 'bgm', 'sound_effects',
            'source_script', 'renderer_implementation', 'integer_policy',
            'speech_manifest', 'speech_acceptance', 'phoneme_alignment')
    require(all(k in plan for k in keys), 'Timeline omits a required immutable field')
    contract = {k: plan[k] for k in keys}
    allowed_n029_gain_fields = {'mix_gain_db', 'aac_codec_calibration_gain_db',
                               'codec_derived_master_scalar_db'}
    for collection in ('voice_events', 'events'):
        events = plan[collection]
        require(len(events) == 78 and len({e['id'] for e in events}) == 78,
                f'Timeline has wrong cue coverage: {collection}')
        contract[collection] = [
            {k: value for k, value in event.items()
             if not (event['id'] == 'N029' and k in allowed_n029_gain_fields)}
            for event in events]
    return contract


def timeline_compatibility(old, new):
    previous, final = immutable_timeline_contract(old), immutable_timeline_contract(new)
    if previous != final:
        changed = [key for key in previous if previous[key] != final[key]]
        raise ValueError('New timeline changed immutable voice/math/seconds/frames/visual contract: ' + ', '.join(changed))
    gain_changes = []
    for collection in ('voice_events', 'events'):
        before = next(e for e in old[collection] if e['id'] == 'N029')
        after = next(e for e in new[collection] if e['id'] == 'N029')
        for key in ('mix_gain_db', 'aac_codec_calibration_gain_db', 'codec_derived_master_scalar_db'):
            if before.get(key) != after.get(key):
                gain_changes.append({'collection': collection, 'id': 'N029', 'field': key,
                                     'before': before.get(key), 'after': after.get(key)})
    changed_metadata = [k for k in sorted(set(old) | set(new))
                        if k not in previous and old.get(k) != new.get(k)]
    return {'passed': True, 'immutable_contract_sha256': hashlib.sha256(
                json.dumps(previous, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            'immutable_top_level_fields': list(previous), 'permitted_N029_gain_changes': gain_changes,
            'changed_audio_or_revision_metadata_fields': changed_metadata,
            'scope': 'Allsourcevoice identities/hashes/text and event fields match; onlyN029mix/AACscalar gain fields may differ. Mathematical/count state, visualsegments, teaching, seconds/samples/frames/fades and remaining cue gains match exactly. Master/AAC/codec and revision metadata are excluded from this picture-inheritance contract and bound separately.'}


def validate_helper_revision(prepared, record_path):
    require(receipt(resolve(prepared['helper']['path'])) == prepared['helper'], 'Prepared original helper changed')
    record = json.loads(record_path.read_text())
    require(record['previous_helper'] == prepared['helper'], 'Revision does not derive from the prepared original helper')
    require(receipt(resolve(record['previous_helper_snapshot']['path'])) == record['previous_helper_snapshot'],
            'Previous helper snapshot changed')
    require(record['previous_helper_snapshot']['sha256'] == prepared['helper']['sha256'],
            'Previous helper snapshot does not preserve prepared bytes')
    require(receipt(__file__) == record['current_helper'], 'New helper differs from revision record')
    return receipt(record_path)


def prepare(args):
    source, proof, timeline = args.source.resolve(), args.proof_dir.resolve(), args.timeline.resolve()
    require(sha(source) == EXPECTED_SOURCE_SHA, 'Current v003 source differs from the independently reviewed MP4')
    plan = json.loads(timeline.read_text())
    require(plan['duration_frames'] == FRAME_COUNT and plan['fps'] == 30, 'Timeline frame contract differs')
    proof.mkdir(parents=True, exist_ok=False)
    document = probe(source, proof / 'source-probe.json')
    rows = packets(source, 'v:0', proof / 'source-video-packets.json')
    video_contract(stream(document, 'video'), rows)
    ends = audio_contract(stream(document, 'audio'), plan)
    decoded = frames(source, proof / 'source-video.framemd5')
    require(len(decoded) == FRAME_COUNT, 'Source full decode frame count differs')
    result = {'schema_version': 1, 'kind': 'prepared-v003-picture-identity-for-audio-only-v004',
              'created_at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'prepared-no-remux-performed',
              'source': receipt(source), 'timeline': receipt(timeline), 'helper': receipt(__file__),
              'source_probe': receipt(proof / 'source-probe.json'),
              'source_video_packets': receipt(proof / 'source-video-packets.json'),
              'source_decoded_frames': receipt(proof / 'source-video.framemd5'),
              'video_packet_count': len(rows), 'decoded_frame_count': len(decoded),
              'ends': ends, 'aac_acceptance_required_before_remux': True}
    save(proof / 'preparation.json', result)
    print(json.dumps({'status': result['status'], 'proof': str(proof / 'preparation.json'),
                      'video_packets': len(rows), 'decoded_frames': len(decoded)}), flush=True)


def remux(args):
    prepared_path = args.proof_dir.resolve() / 'preparation.json'
    prepared = json.loads(prepared_path.read_text())
    source = resolve(prepared['source']['path'])
    require(receipt(source) == prepared['source'] and sha(source) == EXPECTED_SOURCE_SHA, 'Prepared source changed')
    revision = validate_helper_revision(prepared, args.helper_revision_record.resolve())
    previous_timeline = resolve(prepared['timeline']['path'])
    require(receipt(previous_timeline) == prepared['timeline'], 'Prepared timeline changed')
    timeline = args.final_timeline.resolve()
    plan = json.loads(timeline.read_text())
    compatibility = timeline_compatibility(json.loads(previous_timeline.read_text()), plan)
    master = plan['master_audio']
    require(receipt(resolve(master['path']))['sha256'] == master['sha256'], 'Final timeline master audio hash differs')
    for field in ('source_probe', 'source_video_packets', 'source_decoded_frames'):
        path = resolve(prepared[field]['path'])
        require(receipt(path) == prepared[field], f'Preparation evidence changed: {field}')
    aac = args.accepted_aac.resolve()
    require(sha(aac) == args.accepted_aac_sha256, 'Explicitly accepted AAC SHA differs')
    acceptance = args.acceptance_report.resolve()
    require(sha(acceptance) == args.acceptance_report_sha256, 'Explicit acceptance-report SHA differs')
    out = args.out_dir.resolve()
    require(out == DEFAULT_OUTPUT.resolve(), 'This revision may write media only to video/v004-audio-reencoded')
    out.mkdir(parents=True, exist_ok=False)
    qa = args.final_proof_dir.resolve()
    qa.mkdir(parents=True, exist_ok=False)
    save(qa / 'timeline-compatibility.json', {'previous_timeline': prepared['timeline'],
         'final_timeline': receipt(timeline), **compatibility})
    accepted_probe = probe(aac, qa / 'accepted-aac-probe.json')
    accepted_ends = audio_contract(stream(accepted_probe, 'audio'), plan)
    candidate = out / source.name
    command = [FFMPEG, '-hide_banner', '-v', 'warning', '-nostdin', '-n',
               '-i', source, '-i', aac, '-map', '0:v:0', '-map', '1:a:0',
               '-c:v', 'copy', '-c:a', 'copy', '-map_metadata', '0',
               '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace',
               'bt709', '-color_range', 'tv', '-movflags', '+write_colr+faststart', candidate]
    save(qa / 'remux-command.json', [str(c) for c in command])
    with (qa / 'remux.log').open('xb') as log:
        subprocess.run([str(c) for c in command], stdout=log, stderr=log, check=True)
    before = json.loads(resolve(prepared['source_video_packets']['path']).read_text())['packets']
    after = packets(candidate, 'v:0', qa / 'final-video-packets.json')
    require(before == after, 'H264 packet payload/hash/PTS/DTS/duration/size/flags changed')
    source_audio = packets(aac, 'a:0', qa / 'accepted-aac-packets.json')
    final_audio = packets(candidate, 'a:0', qa / 'final-audio-packets.json')
    require(source_audio == final_audio, 'Accepted AAC packet hash/timing/flags changed during remux')
    old_frames = frame_rows(resolve(prepared['source_decoded_frames']['path']))
    new_frames = frames(candidate, qa / 'final-video.framemd5')
    require(old_frames == new_frames and len(new_frames) == FRAME_COUNT, 'Native decoded YUV pixels/timestamps/frame count changed')
    old_probe = json.loads(resolve(prepared['source_probe']['path']).read_text())
    final_probe = probe(candidate, qa / 'final-probe.json')
    old_vs, final_vs = stream(old_probe, 'video'), stream(final_probe, 'video')
    video_contract(final_vs, after)
    for key in ('extradata_hash', 'time_base', 'start_pts', 'duration_ts', 'nb_frames',
                'codec_name', 'profile', 'width', 'height', 'pix_fmt', 'r_frame_rate',
                'avg_frame_rate', 'color_space', 'color_primaries', 'color_transfer', 'color_range'):
        require(old_vs.get(key) == final_vs.get(key), f'Video stream property changed: {key}')
    final_ends = audio_contract(stream(final_probe, 'audio'), plan)
    require(accepted_ends == final_ends == prepared['ends'], 'Audio/video endpoints changed')
    accepted_pcm, final_pcm = pcm_digest(aac), pcm_digest(candidate)
    require(accepted_pcm == final_pcm, 'Accepted AAC decoded PCM differs after remux')
    require(receipt(source) == prepared['source'] and sha(aac) == args.accepted_aac_sha256, 'An immutable input changed while remuxing')
    result = {'schema_version': 1, 'kind': 'exact-H264-and-decoded-pixel-visual-inheritance',
              'created_at_utc': datetime.now(timezone.utc).isoformat(), 'passed': True,
              'status': 'audio-only-remux-identity-proven-pending-final-audio-qa',
              'original_video': prepared['source'], 'corrected_video': receipt(candidate),
              'original_video_sha256': prepared['source']['sha256'], 'corrected_video_sha256': sha(candidate),
              'preparation': receipt(prepared_path), 'previous_timeline': prepared['timeline'],
              'timeline': receipt(timeline), 'master_audio': receipt(resolve(master['path'])),
              'identical_immutable_voice_math_timing_visual_contract': True,
              'timeline_compatibility': receipt(qa / 'timeline-compatibility.json'),
              'previous_helper': prepared['helper'], 'helper_revision': revision,
              'accepted_aac': receipt(aac), 'accepted_aac_review': receipt(acceptance), 'helper': receipt(__file__),
              'h264_packet_bytes_and_pts_dts_duration_flags_identical': True, 'packet_count': len(after),
              'all_decoded_YUV420p_frame_MD5_and_timestamps_identical': True, 'decoded_frame_count': len(new_frames),
              'H264_SPS_PPS_extradata_identical': True, 'H264_extradata_sha256': final_vs.get('extradata_hash'),
              'video_stream_properties_including_BT709_identical': True, 'accepted_AAC_packet_bytes_and_timing_identical': True,
              'accepted_AAC_packet_count': len(final_audio), 'accepted_AAC_decoded_PCM_identical': True,
              'accepted_decoded_PCM': accepted_pcm, 'ends': final_ends,
              'source_video_reencoded': False, 'source_audio_reencoded': False,
              'proofs': [receipt(qa / name) for name in ('final-video-packets.json', 'accepted-aac-packets.json',
                         'final-audio-packets.json', 'final-video.framemd5', 'final-probe.json', 'remux-command.json')],
              'scope': 'AllH264packetSHA256+PTS/DTS/duration/size/flags; all16954nativeYUV420pframeMD5+timestamps; SPS/PPS; BT709/ends; approvedAACpacket and decodedPCM identity. Establishes exact picture inheritance from fresh-v003 visual QA. Does not independently accept new audio pronunciation, loudness or codec-error absence.'}
    save(qa / 'verification.json', result)
    save(out / 'render-manifest-v004.json', result)
    print(json.dumps({'status': result['status'], 'video': result['corrected_video'],
                      'verification': str(qa / 'verification.json'), 'packets': len(after),
                      'decoded_frames': len(new_frames)}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    mux = sub.add_parser('remux', help='Invoke only after explicit acceptance of this exact AAC/hash')
    mux.add_argument('--proof-dir', type=Path, default=DEFAULT_PROOF)
    mux.add_argument('--final-timeline', type=Path, required=True)
    mux.add_argument('--helper-revision-record', type=Path, default=DEFAULT_REVISION_RECORD)
    mux.add_argument('--accepted-aac', type=Path, required=True)
    mux.add_argument('--accepted-aac-sha256', required=True)
    mux.add_argument('--acceptance-report', type=Path, required=True)
    mux.add_argument('--acceptance-report-sha256', required=True)
    mux.add_argument('--out-dir', type=Path, default=DEFAULT_OUTPUT)
    mux.add_argument('--final-proof-dir', type=Path, default=EPISODE/'recheck-20261112-v001/video/remux-v004-final')
    args = parser.parse_args()
    remux(args)


if __name__ == '__main__':
    main()
