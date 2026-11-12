"""Bind the corrected D016 audio and fresh complete-picture QA to revision v002.

Previous accepted/rejected media and diagnostic reports remain immutable.
This does not render, encode, register or change source assets.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/geometric-sequence-counting-v1'
QA = DESIGN / 'production-qa/v002'
OUT = ROOT / 'output/geometric-sequence-counting-001-v002'
AUDIO = OUT / 'audio-build'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def receipt(path):
    path = Path(path).resolve()
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path),
            'bytes': path.stat().st_size}


def bound(row):
    path = (ROOT / row['path']).resolve()
    assert path.is_relative_to(ROOT) and sha(path) == row['sha256'], row
    return path


def evidence(name):
    path = QA / name / 'verification.json'
    data = read(path)
    assert data['passed'] is True, path
    return data, receipt(path)


def save_identical_or_new(path, data):
    payload = json.dumps(data, indent=2) + '\n'
    if path.exists():
        assert path.read_text() == payload, path
    else:
        with path.open('x') as stream:
            stream.write(payload)


def main():
    dest = QA / 'final-verification.json'
    assert not dest.exists()
    video = OUT / 'delivery-v001/paspla-studio-geometric-sequence-2-times-3-1080p.mp4'
    picture = OUT / 'render-v001/silent-picture.mp4'
    timeline = AUDIO / 'timeline-v004.json'
    gate_path = AUDIO / 'speech-acceptance-final.json'
    accepted_path = AUDIO / 'encoded-aac-v002-256k/acceptance.json'
    plan = read(timeline)
    assert plan['duration_frames'] == 20456 and len(plan['voice_events']) == 110
    technical, tr = evidence('final-technical-001')
    sound, sr = evidence('final-audio-001')
    copied, cr = evidence('final-aac-copy-001')
    teaching, ter = evidence('final-teaching-001')
    caption, car = evidence('caption-neighbor-001')
    actor, ar = evidence('actor-alpha250-001')
    creative, cer = evidence('creative-review')
    base_path = QA / 'full-picture-001/verification.json'
    base = read(base_path)
    assert base['passed'] is False
    assert bound(base['video']) == picture.resolve()
    for data, key in [(technical, 'video'), (sound, 'video'), (copied, 'final_movie'),
                      (teaching, 'video'), (caption, 'final_video')]:
        assert bound(data[key]) == video.resolve()
    assert bound(creative['inputs']['video']) == video.resolve()
    assert bound(caption['base_report']) == base_path.resolve()
    assert bound(caption['source_picture']) == picture.resolve()
    old = {(r['frame'], r['component_id']): r for r in base['visual']['failures']}
    corrected = {(r['frame'], r['component_id']): r
                 for r in caption['corrected_native_observations']}
    assert old.keys() == corrected.keys() == {(417, 'return-caption'), (418, 'return-caption')}
    resolved = []
    for key, initial in old.items():
        new = corrected[key]
        assert new['passed'] and new['alignment']['passed']
        assert initial['content_box_xyxy'] == new['content_box_xyxy']
        assert initial['alignment']['tolerance_px'] == new['alignment']['tolerance_px'] == 1
        resolved.append({'frame': key[0], 'component_id': key[1], 'initial': receipt(base_path),
                         'correction': car, 'delta_x_px': new['alignment']['delta_x_px'],
                         'delta_y_px': new['alignment']['delta_y_px'],
                         'reason': 'Adjacent teal moving6 contaminated the muted-caption guard; '
                                   'same box/tolerance remeasured with color separation.',
                         'content_box_changed': False, 'tolerance_changed': False, 'passed': True})
    assert not caption['accepted_complete_picture_evidence']['remaining_failures']
    ydir = QA / 'final-yuv-identity-001'
    paths = [ydir / 'source-picture.framemd5', ydir / 'final-picture.framemd5']
    rows = [[line for line in p.read_text().splitlines() if line and not line.startswith('#')]
            for p in paths]
    assert rows[0] == rows[1] and len(rows[0]) == plan['duration_frames']
    yuv = {'kind': 'independent-geometric-v002-yuv-clock-copy-identity', 'passed': True,
           'source_picture': receipt(picture), 'final_video': receipt(video),
           'decoded_frames': len(rows[0]), 'source_hashes': receipt(paths[0]),
           'final_hashes': receipt(paths[1]),
           'scope': 'Fresh full decode; all YUV420p hashes, DTS, PTS, duration and sizes match.'}
    save_identical_or_new(ydir / 'verification.json', yuv)
    yr = receipt(ydir / 'verification.json')
    producer_path = OUT / 'finalization-v001/finalization.json'
    producer = read(producer_path)
    assert producer['status'] == 'pass' and all(producer['checks'].values())
    assert bound(producer['video']) == video.resolve()
    source = read(gate_path)
    aac = read(accepted_path)
    assert source['accepted'] and not source['unresolved']
    assert aac['accepted'] and not aac['unresolved'] and aac['aac_ready_for_stream_copy_mux']
    accepted_aac = bound(aac['accepted_aac'])
    old_plan = read(ROOT / 'output/geometric-sequence-counting-001-v001/audio-build/revision-v003/timeline.json')
    old_events = {e['id']: e for e in old_plan['voice_events']}
    changed = [e['id'] for e in plan['voice_events']
               if e['source_sha256'] != old_events[e['id']]['source_sha256']]
    assert changed == ['D016']
    negative_path = AUDIO / 'D016-negative-control.json'
    negative = read(negative_path)
    assert negative['passed']
    source_d016 = next(r for r in source['results'] if r['id'] == 'D016')
    phones = source_d016['recognized_phonemes'].split()
    assert any(phones[i:i + 4] == ['s', 'ɪ', 'k', 's'] for i in range(len(phones) - 3))
    assert not any(phones[i:i + 4] == ['s', 'ɛ', 'k', 's'] for i in range(len(phones) - 3))
    assert actor['mask']['pixels'] > 60000 and actor['unique_final_native_sources'] == 287
    diagnostic_path = QA / 'root-correction-001/unchanged-master-regions-difference-v002.json'
    diagnostic = read(diagnostic_path)
    assert diagnostic['passed'] and diagnostic['maximum_peak_difference_dbfs'] < -120
    verifier = ROOT / 'tools/verify_geometric_video.py'
    assert base['verifier_sha256'] == technical['verifier_sha256'] == sound['verifier_sha256'] == sha(verifier)
    archive = QA / 'verifier-source-v002.py'
    if archive.exists():
        assert sha(archive) == sha(verifier)
    else:
        shutil.copyfile(verifier, archive)
    inputs = {k: receipt(p) for k, p in [
        ('video', video), ('timeline', timeline), ('master', AUDIO / 'master.wav'),
        ('speech_manifest', AUDIO / 'measurements.json'), ('speech_acceptance', gate_path),
        ('accepted_aac', accepted_aac), ('encoded_audio_acceptance', accepted_path)]}
    numbers = base['visual']
    audio = sound['audio']
    correlations = [r[k]['correlation'] for r in audio['voice_cues'] for k in ('left', 'right')]
    result = {
        'kind': 'independent-geometric-corrected-media-v002-aggregate', 'status': 'pass',
        'passed': True, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'inputs': inputs, 'unresolved_material_findings': [], 'required_fixes': [],
        'correction': {'cue_ids': changed, 'method': 'Only the list-context Six in D016 was replaced; '
                        '109 exact source WAVs retain adoption. All dependent clocks were regenerated.',
                       'focused_regression': receipt(negative_path),
                       'old_accepted_gate_D016_is_not_a_new_pronunciation_approval': True},
        'technical': {'passed': True, 'evidence': tr, 'frames': plan['duration_frames'],
                      'duration_s': plan['duration_s'], 'measurements': technical['technical']['measurements']},
        'math': {'passed': True, 'evidence': [tr, ter], **technical['schedule']['math'],
                 'general_semantic_frames': len(teaching['general_frame_semantics'])},
        'timing': {'passed': True, 'evidence': [tr, sr, ter], 'voice_events': 110,
                   'word_reveal_observations': len(teaching['word_reveal_observations']),
                   'ordinary_result_end_to_next_operand_s': 2, 'operand_to_result_s': .16,
                   'result_display_lead_s': .12, 'progress': 'commit after result reading ends'},
        'audio': {'passed': True, 'evidence': [sr, cr, receipt(accepted_path)],
                  'source_to_master_cues': len(audio['source_to_master_cues']),
                  'final_left_right_cues': len(audio['voice_cues']),
                  'minimum_correlation': min(correlations), 'silence_intervals': len(audio['silence_intervals']),
                  'new_encoded_recognition': 'New256k AAC: ASR220 and CTC220 across110 cues×2 channels, '
                                             'isolated corrected Six on both channels and two additional base.en checks.',
                  'master_rebuild_quantization': receipt(diagnostic_path),
                  'master_bytes_identical_to_old_version_claimed': False},
        'visual': {'passed': True, 'complete_picture': receipt(base_path),
                   'resolved_measurements': resolved, 'unresolved_measurements': [],
                   'YUV_identity': yr, 'finalization': receipt(producer_path),
                   'decoded_frames': numbers['decoded_frames'],
                   'half_resolution_glyph_observations': numbers['all_frame_half_glyph_observations'],
                   'native_sample_frames': numbers['native_sample_frames'],
                   'native_components': numbers['native_component_observations'],
                   'native_digits': numbers['native_digits'],
                   'actor_alpha250': ar, 'teaching': ter,
                   'scope': 'All-frame critical glyph/state checks at half resolution, native event/transition '
                            'samples and individual digits; both axes and clipping at original tolerances.'},
        'captions': {'passed': True, 'evidence': sr, **sound['subtitles']},
        'creative': {'passed': True, 'evidence': cer, 'separate_from_technical': True},
        'reproducibility': {'verifier_snapshot': receipt(archive), 'aggregate_verifier': receipt(__file__),
                            'old_media_and_failed_diagnostics_preserved': True},
        'scope_limits': ['Automated full decode, signal/recognition tests, native stills and continuous-frame '
                         'contacts are distinguished from human uninterrupted full playback/listening.',
                         '109 prior source decisions are inherited only for exact WAV hashes; the new '
                         'encoded AAC has a new full recognition/signal gate.',
                         'Exact PCM24 equality with the previous master is not a requirement or claim: '
                         'old two-stage gain quantization and new single-stage total gain differ by at most '
                         'the measured tiny quantization residual. All new output checks stand independently.']}
    with dest.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print(json.dumps({'status': 'pass', 'report': receipt(dest), 'resolved_measurements': len(resolved)}))


if __name__ == '__main__':
    main()
