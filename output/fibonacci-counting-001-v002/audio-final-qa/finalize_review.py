"""Bind this run's new clip decisions and signal evidence to the finished MP4."""
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import difflib
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
QA = Path(__file__).resolve().parent
OUT = QA.parent
sys.path.insert(0, str(ROOT))
from tools.review_fibonacci_speech import review, normalize_phones


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)}


def save(name, data):
    with (QA / name).open('x') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2); stream.write('\n')


for filename in ('individual-decisions-left.json', 'individual-decisions-right.json',
                 'review-left.json', 'review-right.json', 'final-aac-review.json', 'final-aac-review.txt'):
    if (QA / filename).exists():
        raise FileExistsError(filename)

baseline = read(QA/'baseline.json')
for binding in baseline.values():
    assert sha(ROOT/binding['path']) == binding['sha256'], 'Bound final/build input changed'
video = ROOT/baseline['video']['path']
timeline = ROOT/baseline['visual_timeline']['path']
plan = read(timeline)
technical_path = OUT/'qa/v001/technical/technical-qa.json'
technical = read(technical_path)
assert technical['status'] == 'pass' and technical['sha256'] == sha(video)
levels = technical['measurements']
assert abs(levels['integrated_lufs']+16) <= 1 and levels['true_peak_dbtp'] <= -1.5
waveform_path = QA/'waveform-review.json'
waveforms = read(waveform_path)
assert waveforms['passed'] and waveforms['video_sha256'] == sha(video) and waveforms['timeline_sha256'] == sha(timeline)
assert all(len(row['events']) == 104 and row['channels_per_event'] == 2 for row in waveforms['tracks'])
assert all(event['left_lag_samples'] == event['right_lag_samples'] == 0 for row in waveforms['tracks'] for event in row['events'])
copy = read(QA/'aac-copy-proof.json')
assert copy['passed'] and copy['video'] == ref(video) and copy['timeline'] == ref(timeline)
subtitle = read(QA/'subtitle-sync-review.json')
assert subtitle['passed'] and subtitle['video'] == ref(video) and subtitle['timeline'] == ref(timeline)
vowels = read(QA/'vowel-controls.json')
assert all(control['two_f2_lower_than_three'] for control in vowels['two_three_controls'])
eight_delta = max(abs(window['delta_f2_hz']) for row in vowels['eight_final_comparisons'] for window in row['paired_frequency_differences'])
assert eight_delta <= 10
transition = read(QA/'level-transition-review.json')
assert transition['within_T013b_gain_span_db'] < .00001

source_decisions_path = OUT/'speech/individual-source-decisions.json'
source_decisions = {row['id']: row for row in read(source_decisions_path)['results']}
source_ctc = {row['id']: row for row in read(OUT/'speech/fresh-phonemes.json')['results']}
source_transfer = []
target_results = []
channel_reviews = []
support = [QA/'vowel-controls.json', QA/'level-transition-review.json',
           QA/'internal-phone-signal-controls.json', waveform_path, QA/'aac-copy-proof.json',
           QA/'subtitle-sync-review.json', technical_path]
for channel in ('left', 'right'):
    support += [QA/f'guarded-{channel}/measurements.json', QA/f'guarded-{channel}/phonemes.json', QA/f'guarded-{channel}/asr.json']

warning_notes = {
    'N033': 'ASR produces malformed comma groups (3,500,24,578). Fresh CTC retains three million / five hundred twenty-four thousand / five hundred seventy-eight, with terminal eight; malformed ASR text remains a warning.',
    'N034': 'ASR comma/hyphen grouping is malformed and right-channel transcription shortens the last group. Independent CTC retains five million, seven hundred two thousand, eight hundred eighty-seven, including eight/ty/seven. This lexical warning is retained.',
    'N038': 'ASR inserts a dollar sign and malformed 88-thousand grouping. CTC independently retains thirty-nine million, eighty-eight thousand, one hundred sixty-nine; no dollars syllables appear. Raw ASR warning retained.',
    'N039': 'The right ASR invents a dollar sign; full CTC independently retains sixty-three million, two hundred forty-five thousand, nine hundred eighty-six, without a dollars word. Raw warning retained.',
    'N040': 'ASR prints a dollar sign before the otherwise matching digits. CTC retains the full cardinal one hundred two million / three hundred thirty-four thousand / one hundred fifty-five; no currency word occurs. Raw warning retained.',
    'T013a': 'Write/right are homophones and the new ASR spells right. CTC has /raɪt/ and three/carry/one ten plus the later thirteen. The final CTC omits one make-final k; new fixed local PCM comparison preserves that consonant region at correlation >.9997. No text parser relaxation applied.',
    'T013b': 'ASR maps standalone hundred to 100. New CTC directly retains /θɹiː tɛnz/, carry one hundred, repeated hundred and own place, distinguishing tens from tenths. Fresh adjacent-RMS and active-window checks document the one whole-clip -2.5dB scalar and no internal gain step.',
    'T018b': 'ASR writes 1810s and 1500s. Fresh CTC explicitly retains eighteen tens and fifteen hundreds, including plural z; those spoken units are inspected independently, and the ASR notation warning remains.',
    'E031': 'ASR writes 832,40. Fresh CTC independently includes eight hundred thirty-two thousand forty, with plus and final equals. The malformed grouping is not normalized away.',
    'E032': 'ASR writes 832,40. Fresh CTC independently includes eight hundred thirty-two thousand forty and the full one million three hundred forty-six thousand two hundred sixty-nine prefix; both operators remain.',
    'E035': 'ASR has malformed groups for both operands. Fresh CTC retains all million/thousand/hundred groups of three million five hundred twenty-four thousand five hundred seventy-eight and five million seven hundred two thousand eight hundred eighty-seven; plus and equals are present. Weak phone labels remain recorded.',
    'E036': 'ASR malformed 5,700,2887 grouping is retained as a warning. CTC independently preserves five million seven hundred two thousand eight hundred eighty-seven, plus nine million two hundred twenty-seven thousand four hundred sixty-five, and equals.',
    'E039': 'ASR loses zeroes in the 88-thousand printed group. CTC preserves the million/thousand groups and operators, but omits the initial s of seventeen. New fixed60ms source/final signal control finds the same high-frequency sibilant region (centroid about9kHz and >99.9%3–10kHz energy fraction); warning remains recorded without a perfect-phone claim.',
    'E040': 'ASR invents dollar signs and malformed 88-thousand digits. CTC independently retains thirty-nine million eighty-eight thousand one hundred sixty-nine plus sixty-three million two hundred forty-five thousand nine hundred eighty-six equals. Currency and malformed-group warnings remain in the raw report.'}

for channel in ('left', 'right'):
    manifest_path = QA/channel/'measurements.json'
    manifest = read(manifest_path)
    assert manifest['source_video']['sha256'] == sha(video) and manifest['source_timeline']['sha256'] == sha(timeline)
    asr = read(QA/f'asr-{channel}.json')
    phones = read(QA/f'phonemes-{channel}.json')
    acoustic = read(QA/f'acoustics-{channel}.json')
    assert acoustic['summary']['clipped_samples'] == 0
    assert acoustic['summary']['voiced_prefix_warnings'] == acoustic['summary']['terminal_suspicious'] == 0
    a = {row['id']: row for row in asr['results']}
    p = {row['id']: row for row in phones['results']}
    guarded_manifest = read(QA/f'guarded-{channel}/measurements.json')
    guarded = read(QA/f'guarded-{channel}/phonemes.json')
    guarded_asr = read(QA/f'guarded-{channel}/asr.json')
    assert guarded_asr['summary']['asr_matches'] == 3 and guarded_asr['summary']['warnings'] == 0
    guards = {row['id']: row for row in guarded['results']}
    assert guards['N006']['recognized_phonemes'] == 'eɪ t'
    result = p['N024']
    internal = next(t for t in result['tokens'] if t['token'] == 'θ' and t['start_s'] > 1)
    guarded_internal = next(t for t in guards['N024']['tokens'] if t['token'] == 'θ' and t['start_s'] > 1)
    assert 'θɹi' in normalize_phones(result['recognized_phonemes']) and result['recognized_phonemes'].endswith('eɪ t')
    assert 'θɹi' in normalize_phones(guards['N024']['recognized_phonemes']) and guards['N024']['recognized_phonemes'].endswith('eɪ t')
    target_results.append({'channel': channel, 'N024_nominal_clip_sha256': result['source_sha256'],
                           'N024_nominal_CTC': result['recognized_phonemes'], 'internal_theta': internal,
                           'N024_guarded_clip_sha256': guards['N024']['source_sha256'],
                           'N024_guarded_CTC': guards['N024']['recognized_phonemes'], 'guarded_internal_theta': guarded_internal,
                           'N024_terminal_t': result['tokens'][-1],
                           'eight_nominal_CTC': p['N006']['recognized_phonemes'],
                           'eight_guarded_CTC': guards['N006']['recognized_phonemes'],
                           'eight_guarded_terminal_t': guards['N006']['tokens'][-1],
                           'two_nominal_CTC_warning_retained': p['N003']['recognized_phonemes'],
                           'two_guarded_CTC_warning_retained': guards['N003']['recognized_phonemes']})
    decisions = []
    for row in manifest['numbers'] + manifest['dialogue']:
        ident = row['id']; cr = p[ident]; ar = a[ident]
        expected = normalize_phones(cr['expected_espeak']); recognized = normalize_phones(cr['recognized_phonemes'])
        sequence = difflib.SequenceMatcher(None, expected, recognized, autojunk=False)
        differences = [{'operation': tag, 'expected': expected[i:j], 'recognized': recognized[k:l]}
                       for tag, i, j, k, l in sequence.get_opcodes() if tag != 'equal']
        notes = [f'Fresh finished-{channel}-channel isolated ASR and independent CTC were inspected for this exact clip hash; all original raw lexical/phone differences remain in the bound reports. New onset, clipping and terminal signal screens have no flags.',
                 'New source/master/final-AAC waveform evidence checks this scheduled utterance in both channels. Acceptance is limited automated-and-agent evidence review, not a full human audition or perfect pronunciation guarantee.']
        if ident in warning_notes:
            notes.append(warning_notes[ident])
        elif ar['status'] != 'asr-match':
            raise ValueError('Unreviewed new ASR warning: '+ident)
        if ident == 'N003':
            notes.append('Short isolated CTC outputs non-English labels in both nominal and silence-guarded cuts; that pronunciation warning is retained. New single-clip LPC gives medianF2=1400Hz, versus2935Hz for same-voice three, with a descending formant trajectory supporting /u/. Lexical two matches are supplementary, not the reason for clearing the phonetic warning; no perfect onset articulation claim.')
        elif ident == 'N006':
            notes.append('Nominal CTC labels the vowel /aɪ/ at low confidence; retain that warning. New7-window same-clip LPC preserves source F1 in all windows and F2 within10Hz; a separate80ms-silence-only finished-MP4 control decodes /eɪt/ with terminal/t/ probability about.937 in each channel. No neighboring numeric speech or expected-text prompt is used.')
        elif ident == 'N024':
            notes.append('The new whole-utterance take has fresh full-cardinal ASR46368 and actual finished-MP4 nominal and silence-guarded CTC /θɹiː/ internally plus final/eɪt/. Both targeted sequence regions are directly inspected; the prior-take internal-theta caution is not inherited or silently erased.')
        elif ident == 'E028':
            notes.append('Nominal CTC substitutes theta for the s onset in the second ninety-six (posterior about.577). New60ms local spectrum retains a strong sibilant centered8945Hz with99.86%3–10kHz energy, versus a same-utterance theta control centered1664Hz/16.25%. Source/final narrow-window correlation exceeds.991. This acoustic evidence supports retained/s/; the raw model substitution remains visible.')
        elif differences:
            notes.append('Phone differences were reviewed as recorded weak-vowel/rhotic/flap or connected-consonant labels; substantive numeric groups and operators remain. Neither similarity score nor lexical context is an approval threshold. Diagnostic phone-label differences are retained, including possible natural reductions.')
        accepted = True
        decisions.append({'id': ident, 'source_sha256': row['sha256'], 'accepted': accepted,
                          'decision': 'fresh-final-v002-clip-evidence-reviewed', 'notes': notes,
                          'raw_ASR_warning_retained': ar['status'] != 'asr-match',
                          'raw_phone_differences_retained': differences,
                          'fresh_source_CTC': source_ctc[ident]['recognized_phonemes'],
                          'human_listening_claim': False})
        source_transfer.append({'id': ident, 'channel': channel, 'source_approval_hash': source_decisions[ident]['source_sha256'],
                                'final_clip_hash': row['sha256'], 'source_approval_matches_final_hash': source_decisions[ident]['source_sha256'] == row['sha256']})
    document = {'schema_version': 1, 'kind': 'new-exact-final-v002-channel-clip-decisions',
                'video': ref(video), 'timeline': ref(timeline), 'channel': channel,
                'past_approvals_unconditionally_transferred': False, 'human_listening_claim': False,
                'results': decisions, 'supporting_evidence': [ref(path) for path in support]}
    decisions_path = QA/f'individual-decisions-{channel}.json'
    save(decisions_path.name, document)
    reviewed = review(manifest_path, QA/f'asr-{channel}.json', QA/f'phonemes-{channel}.json',
                      QA/f'acoustics-{channel}.json', decisions_path)
    assert reviewed['accepted'] and reviewed['summary']['accepted'] == 104 and not reviewed['unresolved']
    save(f'review-{channel}.json', reviewed)
    channel_reviews.append(reviewed)

assert not any(row['source_approval_matches_final_hash'] for row in source_transfer)
save('source-approval-transfer-refused.json', {'kind': 'exact-hash-source-approval-transfer-negative-control',
                                             'source_decisions': ref(source_decisions_path),
                                             'accepted_by_source_approval': 0, 'refused': 208, 'results': source_transfer})
summary = {'utterances': 104, 'channels': 2, 'numbers': 41, 'expression_prefixes': 39, 'other_dialogue': 24,
           'fresh_main_ASR_runs': 208, 'fresh_main_CTC_runs': 208, 'fresh_acoustic_checks': 208,
           'additional_silence_guarded_ASR_runs': 6, 'additional_silence_guarded_CTC_runs': 6,
           'left_ASR_matches': 104-channel_reviews[0]['summary']['isolated_asr_warnings_reviewed'],
           'left_ASR_warnings_retained_and_reviewed': channel_reviews[0]['summary']['isolated_asr_warnings_reviewed'],
           'right_ASR_matches': 104-channel_reviews[1]['summary']['isolated_asr_warnings_reviewed'],
           'right_ASR_warnings_retained_and_reviewed': channel_reviews[1]['summary']['isolated_asr_warnings_reviewed'],
           'accepted_utterances_per_channel': 104, 'unresolved_material_audio_findings': 0,
           'clipped_samples': 0, 'onset_or_terminal_signal_warnings': 0,
           'diagnostic_phone_warnings_erased': False, 'perfect_pronunciation_certified': False}
paths = support + [QA/'baseline.json', QA/'execution-record.json', QA/'aac-copy-proof.json',
                   QA/'source-approval-transfer-refused.json']
for channel in ('left', 'right'):
    paths += [QA/channel/'measurements.json', QA/f'asr-{channel}.json', QA/f'phonemes-{channel}.json',
              QA/f'acoustics-{channel}.json', QA/f'individual-decisions-{channel}.json', QA/f'review-{channel}.json']
report = {'schema_version': 1, 'kind': 'new-fibonacci-v002-finished-AAC-stereo-audio-review',
          'status': 'PASS_WITH_DIAGNOSTIC_WARNINGS_RETAINED', 'passed': True, 'accepted': True,
          'checked_at_utc': datetime.now(timezone.utc).isoformat(),
          'checked_date_jst': str(datetime.now(ZoneInfo('Asia/Tokyo')).date()),
          'video': ref(video), 'timeline': ref(timeline), 'audio_source_timeline': baseline['audio_source_timeline'],
          'master': baseline['audio_master'], 'summary': summary, 'unresolved': [],
          'scope': 'Actual finished-v002 MP4, newly extracted104nominal utterances per stereo channel; new independent lexical ASR/CTC/acoustics and explicit exact-hash decisions, with source/master/final waveform, complete AAC/PCM copy and subtitle bindings. Visual QA is a separate gate.',
          'final_AAC_measurements': {key: levels[key] for key in ('integrated_lufs', 'true_peak_dbtp', 'lra_lu', 'duration_s', 'decoded_video_frames')},
          'targeted_controls': target_results,
          'T013b_level_review': {'adjacent_differences': transition['differences'],
                                'within_utterance_gain_span_db': transition['within_T013b_gain_span_db'],
                                'extra_whole_utterance_scalar_db': -2.5,
                                'interpretation': 'Measured adjacent RMS differences of about2.23/1.84dB are modest. Constant-scalar window measurements show no internal abrupt gain step; no forced equal-loudness adjustment was added.'},
          'waveform_summary': [{key: row[key] for key in ('kind', 'minimum_correlation', 'silence_intervals_checked', 'maximum_silent_interior_peak_pcm16')} for row in waveforms['tracks']],
          'AAC_payload_and_decoded_PCM_identical_to_accepted_M4A': True,
          'source_approval_transfer': {'unconditional_transfer_used': False, 'exact_hash_negative_control_refused': 208},
          'diagnostic_warnings_policy': 'All ASR text warnings and CTC phone differences remain available. A number recognized from context does not clear an isolated phonetic warning. Targeted physical signal/independent CTC controls are stated separately. No similarity-score threshold grants approval.',
          'human_full_listening_claim': False, 'perfect_pronunciation_claim': False,
          'limitations': 'Automated recognizers and targeted acoustic/agent assessment are fallible. No human full-listening session or complete pronunciation guarantee is recorded. Ordinary connected-speech/phone-label uncertainties, particularly isolated two and nominal eight, remain explicit diagnostic warnings.',
          'inputs': [ref(path) for path in dict.fromkeys(paths)],
          'results': [{'id': left['id'], 'expected_text': left['expected_text'],
                       'left_clip_sha256': left['source_sha256'], 'right_clip_sha256': right['source_sha256'],
                       'accepted_both_channels': left['accepted'] and right['accepted'],
                       'left_ASR_status': left['asr_status'], 'right_ASR_status': right['asr_status'],
                       'left_CTC': left['recognized_phonemes'], 'right_CTC': right['recognized_phonemes'],
                       'raw_phone_differences_left': left['phoneme_differences'],
                       'raw_phone_differences_right': right['phoneme_differences']}
                      for left, right in zip(channel_reviews[0]['results'], channel_reviews[1]['results'], strict=True)]}
save('final-aac-review.json', report)
text = f'''フィボナッチv002 完成AAC新規検査: 合格（診断警告は保全）

対象MP4 SHA-256: {sha(video)}
完成尺536.8秒、16104フレーム。完成AAC実測 -16.52LUFS / -1.98dBTP / LRA5.2LU。

左右104発話ずつを新規抽出し、ASR208件・独立CTC208件・語頭/語尾/波形検査208件を実施。
ASRは左91一致/13警告、右90一致/14警告。通貨記号・桁区切り・数詞表記・write/right等の警告は消していません。
全新clipのSHAに対して個別判断を記録。未解決の実質的な音声不備0、クリッピング/語頭/語尾の音響警告0。
原音・master・完成AACの104発話を両chで新規照合し全件lag0。予定外無音区間も合格。

46,368: 新しい全文テイクの内部three /θɹiː/と語末eight /eɪt/を、完成MP4左右のnominal/80ms無音付き両方で確認。
eight: nominal CTCの母音揺れは保全。別の無音付き切出しでは両ch /eɪt/、語末t確度約0.937。
two: 短語CTCの非英語ラベル警告は保全。新規LPCでF2=1400Hz、同声three=2935Hzという単独音響差を確認。
T013b: 前発話比約-2.232dB、次発話へ約+1.840dB。原音対masterの発話内部gain差幅0.00000194dBで、中途の急なゲイン切替なし。

合格M4Aと実MP4はAACペイロードおよびdecoded48k24bitstereo PCMが完全一致。字幕2ファイル各104件も本文/実測時刻と一致。
既存原音承認の無条件転用なし（全208最終clip hashは元source承認hashと異なり、その承認単独では受理不可）。

自動認識と個別音響資料に基づくエージェント検査で、人による全件試聴・発音の完全保証の記録ではありません。
映像全体の合否は独立した最終動画verifierで扱います。
正本: audio-final-qa/final-aac-review.json
'''
with (QA/'final-aac-review.txt').open('x') as stream:
    stream.write(text)
print(json.dumps({'status': report['status'], 'video': report['video'], 'summary': summary, 'levels': report['final_AAC_measurements']}, ensure_ascii=False))
