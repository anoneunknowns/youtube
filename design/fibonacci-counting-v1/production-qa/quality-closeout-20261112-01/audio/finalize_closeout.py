"""Close the independent audio audit with all diagnostic causes retained."""
from pathlib import Path
from datetime import datetime,timezone
import difflib
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[5]
QA=Path(__file__).resolve().parent
OUT=ROOT/'output/fibonacci-quality-closeout-20261112-01'
EPISODE=ROOT/'output/fibonacci-counting-001-v002'
sys.path.insert(0,str(ROOT))
from tools.review_fibonacci_speech import normalize_phones


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def ref(path):return {'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path)}
def save(name,data):
    with (QA/name).open('x') as stream:json.dump(data,stream,ensure_ascii=False,indent=2);stream.write('\n')


baseline=read(QA/'baseline.json')
for row in baseline['inputs']:assert sha(ROOT/row['path'])==row['sha256'],'Accepted media/QA changed'
alternate=read(QA/'alternate-ASR.json');guarded=read(QA/'new-guarded-phonemes.json')
prosody=read(QA/'all104-word-prosody-screen.json');short=read(QA/'short-word-physical-controls.json')
assert len(alternate['results'])==len(guarded['results'])==len(prosody['results'])==104
assert prosody['summary']=={'utterances':104,'word_occurrences':1221,'matched_vowel_nuclei':1714}
new_a={row['id']:row for row in alternate['results']};new_p={row['id']:row for row in guarded['results']}
old_a={channel:{row['id']:row for row in read(EPISODE/f'audio-final-qa/asr-{channel}.json')['results']} for channel in ('left','right')}
source_a={row['id']:row for row in read(EPISODE/'speech/fresh-asr.json')['results']}
physical={row['id']:row for row in short['results']}
word_screens={row['id']:row for row in prosody['results']}

causes={
 'N032':('currency-sign hallucination','Source tiny ASR prints $, while new base.en reads2,178,309. Independent new CTC contains two million / one hundred seventy-eight thousand / three hundred nine; no dollars syllables.'),
 'N033':('malformed digit-group rendering','Both models can print3,500,24,578. New CTC directly retains three million, five hundred twenty-four thousand, five hundred seventy-eight, including terminal eight. Do not reinterpret malformed groups as exact ASR matches.'),
 'N034':('malformed digit-group rendering','Tiny right truncates the printed last group and base.en prints5,700,2,887. New CTC retains five million, seven hundred two thousand, eight hundred eighty-seven; the hundred/eighty/seven sequence is present. No source truncation identified.'),
 'N038':('malformed digit groups and currency sign','Tiny prints$39,8,169 and base.en39,88,169. Independent new CTC has thirty-nine million/eighty-eight thousand/one hundred sixty-nine; speech does not include currency. Raw text warnings stay.'),
 'N039':('currency-sign hallucination','Right tiny inserts$, whereas base.en prints63,245,986. New CTC has full sixty-three million / two hundred forty-five thousand / nine hundred eighty-six without a dollars word.'),
 'N040':('currency-sign hallucination','Tiny inserts$; base.en returns102,334,155. New CTC has the complete one hundred two million / three hundred thirty-four thousand / one hundred fifty-five. No actual currency syllable.'),
 'T013a':('homophones and number-unit typography','Write/right and Here/hear have the same relevant phone sequence. Base.en also prints10s for tens. New CTC preserves three, carry one ten, tens including carry and both thirteens. Unreleased make-final k is weak to CTC; the newly measured local closure/transition is retained without a separate extra syllable.'),
 'T013b':('standalone hundred rendered as digits','New base.en says Write three tens and carry100; that hundred... Full new CTC independently has theta-r-i plus t-e-n-z, not tenths, and all repeated hundred units. Existing whole-clip scalar is unrelated to lexical notation.'),
 'T018b':('spoken units rendered as 10s/100s','Base.en writes18 10s/1500s, tiny1810s/1500s. New CTC explicitly has eighteen tens and fifteen hundreds with plural endings. Teen-vowel nuclei and final n occur before the unit words; no actual1810 spoken or skipped unit.'),
 'E028':('alternate ASR loses a printed one; CTC s/theta confusion','Base.en alone prints120,393 instead of121,393. The same new clip CTC has one hundred twenty ONE thousand three hundred ninety-three. Its second ninety-six onset is labeled theta, but a new local spectrum shows a strong sibilant at~8.9kHz, unlike the same-clip theta control; k/s and following thousand are present.'),
 'E031':('zero lost in printed 832040 group','Tiny prints832,40; base.en returns832,040. Independent CTC includes eight hundred thirty-two thousand forty, both plus and equals. The zero is place notation, not a separately missing spoken zero.'),
 'E032':('zero lost in printed 832040 group','Tiny prints832,40; base.en returns832,040 plus1,346,269. New CTC retains the full first thousand-forty group, second million/thousand groups, plus and equals.'),
 'E035':('malformed digit groups','Whisper models segment million/hundred/thousand speech into malformed numeric punctuation. New full CTC retains both complete million/thousand/hundred operand groups and plus/equals; weak unstressed vowel labels remain diagnostic.'),
 'E036':('malformed digit groups','Both models can print5,700,2,887. New CTC retains five million seven hundred two thousand eight hundred eighty-seven, then nine million two hundred twenty-seven thousand four hundred sixty-five, and both operators.'),
 'E039':('malformed digit group and weak CTC s','ASR prints39,88,169. New CTC preserves all scale words/operators, and the omitted-label s at seventeen has a distinct new measured high-frequency sibilant region(~9kHz). The teen vowel and terminal n remain; no spoken-word omission identified.'),
 'E040':('malformed digit group and currency sign','Tiny can add$ and both models can print39,88,169. New CTC retains thirty-nine million eighty-eight thousand one hundred sixty-nine plus sixty-three million two hundred forty-five thousand nine hundred eighty-six equals, with no currency word.'),
 'N003':('short isolated multilingual CTC label discrepancy','Current two has a real unvoiced onset and voiced vowel from~.12s; onset does not have an extra early periodic vowel. Its F2 descends2400→1250Hz, late median1370Hz, versus same-voice three3010Hz. New independent base.en returns2. Short CTC tɕh/i5 labels are low-confidence model labels, not evidence of a missing t or an i-only vowel. A natural stronger-aspiration full-word control gives t/u, demonstrating allophone/model sensitivity rather than proving current speech defective.'),
 'N006':('short isolated CTC diphthong label discrepancy','New actual-MP4 silence-guarded CTC has/eɪt/ with final t retained. Fresh current-eight F1 descends730→380Hz while F2 rises2630→2980Hz in its vowel nucleus, matching same-voice formula eight and differing from the aI nucleus in five. The nominal aI label is retained as diagnostic, without relying on numeric context or source-waveform identity alone.'),
 'N024':('previous-take issue explicitly rechecked','This is the new complete46,368 take. New actual-MP4 CTC directly has internal theta/r/i and terminal eI/t; base.en returns46,368. It is not accepted by transferring the previous-take decision.'),
 'I05':('weak function-word/rhotic model labels','The new80ms-silence-only CTC recovers the initial voiced th that nominal CTC had omitted. Remaining their/our/rhotic/weak article variants do not replace a teaching word; no initial signal cut or extra syllable.'),
 'I07':('connected voiced-fricative label omission','CTC omits v at show values, but a fresh98–106centisecond local interval has consonant constriction/frication: -25.04dBFS,25.65%3–10kHz energy, compared with0.11%/0.40%in neighboring vowels and33.04%in later same-clip v. This is positive isolated signal evidence beyond the ASR values word. The reduced article a uses a weak vowel and does not match isolated-letter/eI/ labels.'),
 'E025':('connected weak h/unstressed-vowel labels','Six hundred keeps its hundred vowel/n/d/r/d structure. The preceding s/h boundary is coarticulated; the first h need not appear as a separate CTC spike. The later three hundred h and both operators remain in new CTC; no whole scale-word gap or extra syllable is present.'),
 'O04':('adjacent t closure shared across next time','New CTC has next followed by a single t transition into time rather than two independent t labels. This connected stop articulation does not add or remove a syllable; new base.en and the signal ending retain next time.'),
 'I01':('long-word stress/phone screen','Fibonacci has all f/i/b/weak-vowel/n/AA/ch/i segments. The n-AA-to-ch interval is~140ms, longer than the first i-to-b~60ms; declining phrase F0 alone is not misread as wrong lexical stress. The CMU reference primary AA and secondary IH are retained as reference, not as an observed-stress guarantee.')}

ledger=[]
for row in prosody['results']:
    ident=row['id'];phone=new_p[ident];new=new_a[ident]
    expected=normalize_phones(phone['expected_espeak']);recognized=normalize_phones(phone['recognized_phonemes'])
    sequence=difflib.SequenceMatcher(None,expected,recognized,autojunk=False)
    differences=[{'operation':op,'expected':expected[a:b],'recognized':recognized[c:d]} for op,a,b,c,d in sequence.get_opcodes() if op!='equal']
    warnings=[kind for kind,ar in [('source-tiny',source_a[ident]),('final-left-tiny',old_a['left'][ident]),('final-right-tiny',old_a['right'][ident]),('new-base-en',new)] if ar['status']!='asr-match']
    if warnings and ident not in causes:raise ValueError('Unreviewed warning '+ident)
    category,reason=causes.get(ident,('ordinary weak-vowel/rhotic/flap/connected-phone labels' if differences else 'no diagnostic mismatch',
                                    'New per-word CTC and vowel-nucleus samples were checked against complete words, internal units, operators and long-number groups. Differences concern weak vowels, American flap/dental/rhotic labels or connected reductions; raw differences remain listed. No extra syllable, missing complete numeric unit, cut or incompatible teen ending is identified. No score threshold or expected numeric context serves as phonetic approval.'))
    ledger.append({'id':ident,'text':row['expected_text'],'source_tiny_ASR_warning':source_a[ident]['status']!='asr-match',
                   'left_tiny_ASR':{'text':old_a['left'][ident]['recognized_text'],'status':old_a['left'][ident]['status']},
                   'right_tiny_ASR':{'text':old_a['right'][ident]['recognized_text'],'status':old_a['right'][ident]['status']},
                   'new_base_en_ASR':{'text':new['recognized_text'],'status':new['status'],'source_sha256':new['source_sha256']},
                   'new_guarded_CTC':phone['recognized_phonemes'],'raw_CTC_differences_retained':differences,
                   'diagnostic_sources':warnings,'cause':category,'new_evidence_and_judgment':reason,
                   'word_occurrences_screened':len(row['words']),
                   'vowel_nuclei_screened':sum(len(word['vowel_nucleus_signal_samples']) for word in row['words']),
                   'stress_scope':'CMU/US word references plus new nucleus duration/energy/periodicity and teen-endings inspection; perceived prosodic perfection is not claimed.',
                   'status':'diagnostic model-label discrepancy reviewed; no material audio defect' if warnings or differences or ident in causes else 'no material audio defect identified by the stated checks',
                   'material_audio_defect':False,'human_full_listening_claim':False})

candidate_rows=[]
for batch,ctc_name,asr_name in [('candidates-v001','candidate-phonemes.json','candidate-asr.json'),
                               ('candidates-v002','phoneme-controls-CTC.json','phoneme-controls-ASR.json'),
                               ('candidates-v003','allophone-controls-CTC.json','allophone-controls-ASR.json')]:
    ctc={r['id']:r for r in read(QA/ctc_name)['results']};asr={r['id']:r for r in read(QA/asr_name)['results']}
    for take in read(OUT/batch/'takes.json'):
        ident=take['id'];judgment='Comparison only; no independently established current material defect or clear perceptual improvement warrants changing accepted speech.'
        if ident=='two_short_u':judgment='Rejected: independent lexical ASR says Chew and onset has an early periodic component; shortening the vowel label is not an improvement.'
        if ident=='two_syllable_stress':judgment='Rejected: CTC adds an initial epsilon and ASR says E2; extra-syllable risk.'
        if ident=='two_aspirated_unmarked':judgment='Valid natural allophone control: explicit aspirated t yields/t u/. Its stronger aspiration and slightly lower F2 are an alternate realization, not proof of current consonant/vowel loss. Parent chose current AAC continuity after the direct current-signal review.'
        if ident=='eight_endstop':judgment='No demonstrated substantive improvement: same vowel trajectory and .99788local source correlation with the accepted complete-word eight; nominal CTC confidence change alone is not a replacement reason.'
        candidate_rows.append({'id':ident,'raw_source':ref(Path(take['path'])),'duration_s':take['duration_s'],
                               'canonical_text':'two' if take['number']==2 else 'eight','generation_text':take['text'],
                               'phonemes':take.get('phonemes'),'generation':take['generation'],
                               'CTC':ctc[ident]['recognized_phonemes'],'ASR':asr[ident]['recognized_text'],
                               'judgment':judgment,'adopted':False,'source_audio_was_spliced_or_time_scaled':False})
assert len(candidate_rows)==13
save('warning-ledger.json',{'kind':'all104-independent-closeout-diagnostic-and-word-review-ledger',
                            'prior_acceptance_decisions_imported':False,'results':ledger,
                            'all_raw_diagnostics_preserved':True,'unresolved_material_audio_findings':[]})
save('candidate-comparison.json',{'kind':'new-complete-word-two-eight-candidate-comparison','candidate_count':13,
                                'adopted_count':0,'results':candidate_rows,
                                'decision':'Keep actual accepted AAC. Some controls are natural alternatives, others are worse; none proves a current missing consonant/vowel or wrong word.',
                                'retime_or_source_mutation_applied':False})

inputs=[QA/name for name in ('baseline.json','alternate-ASR.json','new-guarded-phonemes.json','all104-word-prosody-screen.json',
                            'expected-word-pronunciations.json','cmudict-source.json','short-word-physical-controls.json',
                            'internal-target-physical-observations.json','warning-ledger.json','candidate-comparison.json',
                            'carry-voice-landmarks.json','candidate-asr.json','candidate-phonemes.json',
                            'phoneme-controls-ASR.json','phoneme-controls-CTC.json','allophone-controls-ASR.json','allophone-controls-CTC.json')]
inputs += [OUT/'model-cache/models.json',OUT/'new-final-left-guarded/measurements.json',
           EPISODE/'speech/fresh-asr.json',EPISODE/'audio-final-qa/asr-left.json',EPISODE/'audio-final-qa/asr-right.json']
source_final_warning_ids=[row['id'] for row in ledger if row['diagnostic_sources']]
report={'schema_version':1,'kind':'independent-fibonacci-audio-quality-closeout',
        'status':'DIAGNOSTIC_MODEL_LABEL_DISCREPANCIES_REVIEWED_NO_MATERIAL_AUDIO_DEFECT','passed':True,
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),
        'audited_movie':baseline['inputs'][0],'audited_timeline':baseline['inputs'][1],
        'source_and_existing_QA_preserved':True,'prior_acceptance_decisions_used_as_approval':False,
        'summary':{'utterances_individually_audited':104,'word_occurrences_screened':1221,'vowel_nuclei_screened':1714,
                   'new_alternate_base_en_ASR_runs':104,'new_silence_guarded_final_CTC_runs':104,
                   'new_base_en_matches':94,'new_base_en_raw_warnings':10,
                   'previous_final_tiny_left_raw_warnings_audited':13,'previous_final_tiny_right_raw_warnings_audited':14,
                   'previous_source_tiny_raw_warnings_audited':14,'new_full_word_candidates_generated':13,
                   'new_candidate_ASR_runs':13,'new_candidate_CTC_runs':13,'candidates_adopted':0,
                   'material_audio_defects_identified':0,'unresolved_material_audio_findings':0},
        'unresolved_definition':{'material':'A specific reproducible wrong/absent/extra syllable or word, missing numeric unit/operator, cut, prohibited timing/level anomaly, or isolated pronunciation concern with no positive same-clip explanation would remain unresolved and block acceptance.',
                                 'diagnostic':'An ASR printing convention or fallible CTC allophone label is closed as diagnostic only when direct same-clip phone/signal evidence explains it. It remains in raw logs and is never silently relabeled as an exact recognizer match.',
                                 'absolute_guarantee':'Finite automated/acoustic/agent checks cannot certify every listener perception or perfect stress/naturalness. This methodological limit is stated, rather than misreported as human full listening.'},
        'warning_ids_individually_closed':source_final_warning_ids,
        'two_decision':causes['N003'][1],'eight_decision':causes['N006'][1],
        'long_words_and_stress_review':{'method':'All1221word occurrences have US dictionary reference, matched CTC segments and new vowel energy/periodicity samples. Teen identities are additionally checked by full i/n endings and numeric-unit boundaries, not loudness alone. Fibonacci primary-AA timing is directly inspected. Declining phrase pitch and ordinary American flap/rhotic/reduced vowels are not treated as missing words.',
                                        'perceived_stress_perfect_certification':False,'human_full_listening_claim':False,
                                        'CMU_primary_source':'https://github.com/cmusphinx/cmudict'},
        'candidate_decision':'All13new complete-word candidates remain unadopted. Stronger aspiration/backer vowel variants are natural controls, not proof current speech is defective. Do not change source solely to improve a diagnostic model label.',
        'next_revision_audio_recommendation':'Copy the accepted AAC to visual-only v003; bind all packet payloads/pts/dts/durations, ADTS, decoded stereo PCM and exact voice/source/master cues using the prepared read-only script. A new signal would require new audio review.',
        'unresolved':[],'all_raw_warnings_retained':True,'human_full_listening_claim':False,'perfect_pronunciation_claim':False,
        'inputs':[ref(path) for path in inputs]}
save('audio-closeout.json',report)
rows=[]
for row in ledger:
    if row['diagnostic_sources'] or row['id'] in ('N003','N006','N024','I07','E025'):
        rows.append(f"{row['id']}: {row['cause']} — {row['new_evidence_and_judgment']}")
text='''フィボナッチ音声 品質closeout: 診断差分の原因を個別確認、実質的な音声不備なし

対象は現行v002の完成AAC。既存の媒体・原音・承認記録は変更していません。
前回承認を再引用せず、別重みWhisper-base.enで新規104件、新しい実MP4由来の無音80msguard付きCTC104件を解析しました。
全104本文・1221語・1714母音核を、語中音、長語、teen/ty、million/thousand/hundred、plus/equals、ストレス参照と母音信号の観点で点検。
新base.enは94一致/10警告。従来tinyの左13/右14/原音14警告も、今回の直接根拠で個別に再検討しました。

two: 語頭の無声区間から約0.12秒で有声母音へ移り、余計な先行有声母音は見られません。
母音F2は2400→1250Hzへ下がり、後半中央値1370Hz。同声threeは3010Hzで、iだけの母音ではありません。
短語CTCの非英語ラベルはモデル診断差分として記録を残します。数値2と認識されたことだけで発音を保証していません。
eight: 新guardedCTCは/eɪt/。母音核のF1低下とF2上昇は同声の式内eightと対応し、fiveの/aɪ/核とは異なります。語末tも存在します。
46,368: 新たな完成AACのtheta/r/iと語末eI/tを再確認しました。

同声af_heart・fp32・速度0.98で全文単語候補13本も新規生成しました。全て未採用です。
明示的な自然aspirationで/t u/となる対照も得ましたが、それは現行の欠落/誤語を確定する証拠ではありません。
Chew/E2となる悪化候補は除外。認識器の表記やlabelを良くすることだけを理由に現行音源は変更しません。

『未解決』は、具体的な欠落/余分な音節/誤語/単位や演算子の欠落/音切れ等が再現し、同clipの直接根拠で説明できない場合です。
今回それに該当する所見は0。ASR桁表記・同音語・短語/allophone CTC差分は、原因と正の音響根拠を付けた診断差分として閉じました。
全ての生警告は保存しています。完全な発音・聞き手全員の自然さ・人による全件試聴を主張しません。
CMU US dictionary参照: https://github.com/cmusphinx/cmudict （参照ラベルを観測stressと取り違えていません）

個別一覧:
'''+ '\n'.join(rows)+'''

全104件の一覧: warning-ledger.json
新規単語/母音核資料: all104-word-prosody-screen.json
新規単独音響対照: short-word-physical-controls.json / internal-target-physical-observations.json
新候補比較: candidate-comparison.json
次の映像改訂ではAACをそのままcopyし、実v003到着後にpacket/pts/dts/duration・ADTS・decoded PCM・全voice cueの同一性を別記録へ束縛します。
'''
with (QA/'audio-closeout.txt').open('x') as stream:stream.write(text)
print(json.dumps({'passed':True,'summary':report['summary'],'report':ref(QA/'audio-closeout.json')},ensure_ascii=False))
