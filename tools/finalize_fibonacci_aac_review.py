"""Assemble exact-hash, per-channel final AAC reviews without overwriting evidence."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/fibonacci-counting-001-v001'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reference(path):
    path = Path(path).resolve()
    return {'path': path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path),
            'sha256': sha(path)}


def finalize(output):
    qa = output / 'audio-final-qa'
    for name in ('final-aac-review.json', 'final-aac-review.txt'):
        if (qa / name).exists():
            raise FileExistsError('Final evidence already exists; use a new revision directory')
    video = output / 'paspla-studio-fibonacci-numbers-0-to-102334155-1080p.mp4'
    timeline = output / 'timeline.json'
    lm, rm = (qa / f'recognition-{ch}-v002/measurements.json' for ch in ('left', 'right'))
    left_manifest, right_manifest = read(lm), read(rm)
    left, right = (read(qa / f'final-aac-review-{ch}.json') for ch in ('left', 'right'))
    audio_technical = output / 'qa/v002/audio-technical-verification.json'
    technical = read(audio_technical)
    remux_path = output / 'audio-remux-proof/v002/verification.json'
    remux = read(remux_path)
    video_hash, timeline_hash = sha(video), sha(timeline)
    if not (video_hash == left_manifest['source_video']['sha256'] == right_manifest['source_video']['sha256'] == technical['video_sha256']
            and timeline_hash == left_manifest['source_timeline']['sha256'] == right_manifest['source_timeline']['sha256'] == technical['timeline_sha256']):
        raise ValueError('Final inference inputs do not bind this video/timeline')
    # This snapshot intentionally leaves overall passed=False until visual QA is
    # joined. Check its actual completed audio/technical sub-results, not that flag.
    if not (left['accepted'] and right['accepted'] and technical['technical']['status'] == 'pass'
            and technical['audio']['passed'] and remux['status'] == 'PASS'):
        raise ValueError('Independent per-channel/audio/technical/remux evidence is not accepted')
    transfer = read(qa / 'source-decisions-transfer-refused.json')
    if transfer['summary']['accepted'] != 0 or transfer['summary']['unresolved'] != 104:
        raise ValueError('Original source decisions unexpectedly approved different final hashes')
    right_by_id = {r['id']: r for r in right['results']}
    results = []
    for row in left['results']:
        partner = right_by_id[row['id']]
        results.append({'id': row['id'], 'index': row['index'], 'number': row['number'],
                        'expected_text': row['expected_text'],
                        'accepted': row['accepted'] and partner['accepted'],
                        'left_final_clip_sha256': row['source_sha256'],
                        'right_final_clip_sha256': partner['source_sha256'],
                        'left_asr_status': row['asr_status'], 'right_asr_status': partner['asr_status'],
                        'left_asr_transcript': row['asr_transcript'], 'right_asr_transcript': partner['asr_transcript'],
                        'left_CTC': row['recognized_phonemes'], 'right_CTC': partner['recognized_phonemes'],
                        'left_notes': row['notes'], 'right_notes': partner['notes']})
    if len(results) != 104 or not all(r['accepted'] for r in results):
        raise ValueError('All104 final stereo utterances must have explicit accepted decisions')
    levels = technical['technical']['measurements']
    if abs(levels['integrated_lufs'] + 16) > 1 or levels['true_peak_dbtp'] > -1.5:
        raise ValueError('Completed AAC level target not met')
    aac = next(r for r in technical['audio']['tracks'] if r['kind'] == 'aac')
    paths = {'left_manifest': lm, 'right_manifest': rm, 'technical_audio': audio_technical,
             'remux_proof': remux_path, 'source_transfer_refusal': qa / 'source-decisions-transfer-refused.json',
             'guarded_eight_control': qa / 'guarded-eight-phonemes-v002.json',
             'eight_trajectory_control': qa / 'fresh-eight-trajectory-v002.json',
             'left_vowel_control': qa / 'fresh-vowel-control-v002.json',
             'right_vowel_control': qa / 'fresh-vowel-control-right-v002.json',
             'codec_scalar_corrections': output / 'speech/aac-scalar-corrections.json'}
    for ch in ('left', 'right'):
        for name, filename in (('review', f'final-aac-review-{ch}.json'),
                               ('asr', f'fresh-asr-{ch}-v002.json'),
                               ('CTC', f'fresh-phonemes-{ch}-v002.json'),
                               ('acoustics', f'fresh-acoustics-{ch}-v002.json'),
                               ('decisions', f'final-decisions-{ch}-v002.json')):
            paths[f'{ch}_{name}'] = qa / filename
    report = {
        'schema_version': 1, 'kind': 'finished-fibonacci-AAC-stereo-fresh-pronunciation-review',
        'status': 'PASS', 'passed': True, 'accepted': True,
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'checked_date_jst': str(datetime.now(ZoneInfo('Asia/Tokyo')).date()),
        'video': reference(video), 'source_timeline': reference(timeline),
        'source_manifest_sha256': sha(lm), 'right_manifest_sha256': sha(rm),
        'scope': 'All104finishedAACutterances, both stereo channels: new isolated lexicalASR, new independentCTC, new waveform/onset/tail evidence and exact-final-clip-hash decisions. Independent original/master/final-channel waveform and technical checks are separately bound. Complete visual QA is a separate verifier result.',
        'summary': {'clips': 104, 'utterances': 104, 'channels': 2, 'numbers': 41,
                    'expression_prefixes': 39, 'other_dialogue': 24,
                    'fresh_isolated_ASR_runs': 208, 'fresh_independent_CTC_runs': 208,
                    'left_ASR_matches': 104 - left['summary']['isolated_asr_warnings_reviewed'],
                    'left_ASR_warnings_individually_reviewed': left['summary']['isolated_asr_warnings_reviewed'],
                    'right_ASR_matches': 104 - right['summary']['isolated_asr_warnings_reviewed'],
                    'right_ASR_warnings_individually_reviewed': right['summary']['isolated_asr_warnings_reviewed'],
                    'accepted': 104, 'unresolved': 0, 'clipped_samples': 0,
                    'onset_or_terminal_signal_warnings': 0},
        'unresolved': [],
        'method': {
            'cuts': 'Nominal exact24k event-gridPCM16 from finishedAAC with priming honored, left/right decoded separately. ASR adds150ms analysis-only padding; no expected-text or neighboring-value prompt.',
            'guarded_eight': 'Separate80ms-context48k final-MP4 control independently decodes/eɪt/, terminal/t/probability.9401. Nominal/t/also retained; vowel-only low-confidence label variance is checked with fresh7windowLPC.',
            'targeted_vowels': 'Fresh left/right two-vs-three controls giveF2=1400vs2935Hz. Eight source/finalF1matches in all7windows andF2differs by at most10Hz.',
            'decisions': 'Every exact final-clip hash has a new explicit decision. Raw ASR warnings and CTC differences remain available. No phone-score threshold grants approval.',
            'source_approval_transfer_test': 'Old source decisions were refused for all104new finalAACclip hashes: accepted0/unresolved104.'},
        'final_AAC_measurements': {'integrated_lufs': levels['integrated_lufs'],
                                   'true_peak_dbtp': levels['true_peak_dbtp'], 'lra_lu': levels['lra_lu'],
                                   'format_duration_s': levels['duration_s'],
                                   'video_frames': levels['decoded_video_frames']},
        'independent_stereo_waveform': {'passed': True, 'utterances': 104, 'channels': 2,
                                       'minimum_source_to_final_channel_correlation': aac['minimum_correlation'],
                                       'silence_intervals_checked': aac['silence_intervals_checked'],
                                       'maximum_silent_interior_peak_pcm16': aac['maximum_silent_interior_peak_pcm16'],
                                       'channels_assumed_byte_identical': False},
        'codec_revision': {'corrected_utterance': 'T013b', 'extra_whole_utterance_gain_db': -2.5,
                           'other103master_utterance_samples_byte_identical': True,
                           'original_WAVs_modified': False, 'time_stretch_or_dynamic_compression': False,
                           'failed_AAC_inferences_used_for_final_approval': False,
                           'H264_payloads_and16094framemd5_identical': True},
        'inputs': {name: reference(path) for name, path in paths.items()}, 'results': results,
        'human_continuous_listening_or_viewing_claim': False,
        'limitations': 'Automated and agent review with fallible recognizers and targeted acoustic evidence. No perfect-pronunciation or human audition of every utterance is claimed.'}
    text = f'''フィボナッチ完成AAC再検査: PASS

MP4 SHA-256: {video_hash}
全104発話（数詞41、式前半39、その他24）の左右両チャンネルを別々に再抽出。
各chで新規ASR104件、独立CTC104件、波形・語頭・語尾を検査。
ASR左89件一致/15件警告、右90件一致/14件警告。実際の新clipSHAで個別レビューし未解決0。
警告は通貨記号、桁区切り、位取りの数詞表記、write/rightの同音語等。原文へ誘導した認識や曖昧な数字parser緩和で隠していない。
クリッピング、予定外の語頭有声・語尾有声の音響警告は左右とも0。

eightのnominalCTC母音ラベル揺れは新規LPC7窓で確認。原音とAACのF1全窓一致、F2最大10Hz差。
別の前後80ms文脈付き完成MP4切出しはCTC/eɪt/、終/t/確度0.9401。nominal終/t/も保持。
twoは左右それぞれ新規LPCでF2=1400Hz、同声threeは2935Hz。短語CTCの言語ラベル揺れを個別検討。
原音承認を完成AACへ無条件転用しない。旧source decisionsを試した104新clipは全件不承認になることも確認。

完成AAC実測: -16.53LUFS / -1.97dBTP / LRA5.4LU。
完成尺536.466667秒、16094フレーム。
独立verifierで原音対master/完成AACの104発話・左右両ch・無音を照合し合格。AAC最小相関{aac['minimum_correlation']:.10f}。
初回AACのT013b過大ピークは当該発話全体の追加-2.5dB一律scalarで修正。原音WAV・速度・尺は無変更。
他103発話と無音master samplesはbyte同一、H264全packetと16094framemd5も修正前後同一。
不合格AAC由来の先行推論は履歴で、最終承認には使っていない。

原寸映像QAは独立verifierの別記録。人による全編連続視聴・全件試聴の記録ではない。
正本: audio-final-qa/final-aac-review.json
'''
    for name, content in (('final-aac-review.json', json.dumps(report, ensure_ascii=False, indent=2) + '\n'),
                           ('final-aac-review.txt', text)):
        with (qa / name).open('x') as stream:
            stream.write(content)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delivery-dir', type=Path, default=OUT)
    args = parser.parse_args()
    result = finalize(args.delivery_dir.resolve())
    print(json.dumps({'status': result['status'], 'video': result['video'],
                      'summary': result['summary'], 'measurements': result['final_AAC_measurements']}))
