import hashlib,json,re,shutil,statistics
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path('D:/codex_projects/youtube');OUT=ROOT/'design/odd-counting-v1/production-qa/v002-recheck-20261111/audio';WORK=Path('D:/temp/odd-recheck-20261111/audio')
def read(name):return json.loads((OUT/name).read_text(encoding='utf-8-sig'))
def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def ref(path):
    path=Path(path);return {'path':str(path),'sha256':sha(path),'bytes':path.stat().st_size}
def save(name,value):
    with (OUT/name).open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')
def words(n):
    small=('zero','one','two','three','four','five','six','seven','eight','nine','ten','eleven','twelve','thirteen','fourteen','fifteen','sixteen','seventeen','eighteen','nineteen')
    tens=('','','twenty','thirty','forty','fifty','sixty','seventy','eighty','ninety')
    if n<20:return small[n]
    if n<100:return tens[n//10]+('-'+small[n%10] if n%10 else '')
    return small[n//100]+' hundred'+(' '+words(n%100) if n%100 else '')
def normtext(text):
    text=re.sub(r'\d+',lambda m:words(int(m[0])),text.lower()).replace("let's",'let us').replace('leftover','left over')
    return re.sub('[^a-z]+',' ',text).strip()
def normipa(text):return re.sub(r'[\sˈˌ]','',text).replace('ᵻ','ɪ')
m=read('fresh-aac-manifest.json');ctc=read('fresh-ctc.json');asr=read('fresh-asr.json');signal=read('fresh-signal-checks.json');edge=read('edge-signal-review.json');onset=read('initial-fricative-screen.json');tail=read('fresh-terminal-tails.json');extended=read('extended-number-acoustics.json');consistency=read('event-consistency.json');control=read('fresh-control-ctc.json')
rows={r['id']:r for r in m['numbers']+m['dialogue']};phones={r['id']:r for r in ctc['results']};recognized={Path(r['path']).stem:r for r in asr['results']}
assert set(rows)==set(phones)==set(recognized) and len(rows)==163
assert ctc['source_manifest_sha256']==asr['source_manifest_sha256']==sha(OUT/'fresh-aac-manifest.json')
for key in ('video','timeline','master'):
    assert sha(m['origin'][key]['path'])==m['origin'][key]['sha256']
asr_checks=[]
for identity,row in rows.items():
    a=recognized[identity];p=phones[identity]
    assert a['source_sha256']==p['source_sha256']==row['sha256']==sha(row['path'])
    expect=words(row['number']) if row['event_type']=='number_voice' else row['spoken_text']
    assert expect==p['expected_text']==row['spoken_text']
    same=normtext(a['recognized_text'])==normtext(expect)
    assert same,(identity,expect,a['recognized_text'])
    asr_checks.append({'id':identity,'expected_text':expect,'recognized_text':a['recognized_text'],'accepted':same,
        'normalization':'Numeric digit expansion, case/punctuation, let us equivalence and leftover spacing only.'})

# Every limited-normalization mismatch receives a specific read-only review. No CTC phones are silently deleted.
notes={}
def note(ids,why,evidence=()):
    for identity in ids.split():notes[identity]={'reason':why,'fresh_supporting_reports':list(evidence)}
note('N005','Guarded CTC adds terminal z; the new exact-event control from the same AAC ends f-aI-v. No production sample changed. This is exterior-padding-sensitive segmentation, not an ASR-only clearance.',('fresh-control-ctc.json','exact-event-manifest.json','fresh-terminal-tails.json'))
note('N049 N139 N189 N249 N289','A single intervocalic American alveolar tap is labelled rather than dictionary t. Numeric components and following unit are complete; no additional nucleus or interruption is established.')
note('N059 N089','Final unstressed fifty/eighty vowel gets i-long rather than short i. The phoneme sequence and terminal nine are otherwise complete.')
note('N087 N185','Intervocalic eighty tap is labelled r/d and N087 has i-length variation. Each token occupies a single 25ms CTC step between vowel nuclei; a new word or extra syllable is not supported. This is a contextual allophone/label interpretation, not an exact-articulation guarantee.')
note('N091 N093 N095 N097 N191 N193 N197 N199 N291 N295 N297','Nasal-adjacent ninety stop is voiced/tapped and labelled d rather than dictionary t. Entire ninety and unit sequences remain; no extra vowel is emitted.')
note('N109','Both fresh guarded and exact-event AAC CTC label a terminal d. The new 8-input source/AAC x24k/48k x0/80ms grid reproduces d from codec-free source with48k conversion. A brief existing nasal release is present in source and AAC; local .8s-to-end correlation is0.999907866 and power-spectrum cosine0.999990802. No new codec event or new syllable is established. Raw d labels are retained; no claim of absent release or perfect perceptual articulation.',('fresh-control-ctc.json','N109-diagnostic-grid-manifest.json','N109-local-terminal-waveform.json'))
note('N121 N227 N279','Twenty/seventy intervocalic stop is a single short alveolar tap. All numerical syllables remain, with no extra vowel or boundary break.',('extended-number-acoustics.json',))
note('N123 N127 N129 N223 N229','Twenty nt sequence is nasal-reduced/unreleased and CTC merges the t into n. Twenty vowel and complete unit are retained; no missing numerical component or interruption is supported.')
note('N133 N143 N159 N163 N243','Unstressed second hundred vowel is schwa rather than dictionary ih. The consonant sequence and following component are complete.')
note('N149','Forty includes American tap plus o-r versus open-o-r broad vowel label. The complete forty and nine sequences remain.')
note('N151 N171 N241 N251','Final one nucleus is broadly labelled a rather than wedge; complete w-vowel-n is present. New delivery LPC supports a continuous vowel-to-nasal transition, with no clipped or added syllable.',('targeted-formants.json','extended-number-acoustics.json'))
note('N195 N293 N299','Hundred reduced vowel and ninety voiced/tap labels differ from dictionary, while full ordered word and terminal unit sequences remain.')
note('N233','Hundred schwa and shortened terminal three vowel are present; full consonant/vowel sequence remains.')
note('N239','Hundred schwa and thirty alveolar tap are present. Every numerical syllable and terminal nine are retained.')
note('N263','Terminal three vowel is short i rather than i-long. Complete theta-r-i and preceding number remain.')
note('N281','Hundred unstressed vowel reduces and eighty tap receives r label. A single short transition into i is present, not an extra syllable.')
note('I02','Start-at has an American tap and reduced at vowel. Complete start/at/one and add-two words remain.')
note('I03','Unstressed has is labelled with full ae vowel; sentence words and no-partner meaning remain.')
note('I04','Pairs receives p-eI-z without explicit rhotic token. New LPC shows the third formant descending from2938Hz at1.17s to2096Hz at1.33s while F2 approaches1846Hz, supporting r-color. Raw label difference retained; lexical ASR alone is not approval.',('targeted-formants.json',))
note('I05','Pairs receives p-eI-z, and n-to-w lip closure has a low-confidence25ms m label with no additional nucleus. New LPC in pairs descends from3050Hz at2.29s to2040-2147Hz at2.44-2.49s, supporting r-color. Fresh transition frame data are preserved.',('targeted-formants.json','targeted-boundaries.json'))
note('I06','Our/example boundary rhotic coalesces and start-at/lets-start stop sequence coarticulates. Whole sentence ASR and complete vowel/word order remain, with no extra syllable.')
note('I07','We will contraction vowel is unstressed, and ninety stop is voiced/tapped. Full sentence and299 target components are present.')
note('T101 F02','Ninety American voiced/tap and unstressed hundred labels differ; the complete sentences,99→101 and299 targets remain.')
note('F01','Did-it d is a short American flap labelled r, with did/it vowels and final stop retained.')
note('F03','Only terminal me vowel length differs. Complete closing words remain.')
note('F04','For is reduced f-er, a normal American unstressed form. Bye-for-now is complete.')
differences={key for key,p in phones.items() if normipa(p['expected_espeak'])!=normipa(p['recognized_phonemes'])}
assert set(notes)==differences,(set(notes)-differences,differences-set(notes))
per_phone=[]
for identity,p in phones.items():
    per_phone.append({'id':identity,'source_sha256':p['source_sha256'],'expected_ipa':p['expected_espeak'],'raw_recognized_ipa':p['recognized_phonemes'],
        'limited_normalized_match':identity not in differences,'review':notes.get(identity,{'reason':'Full sequence match under declared stress/space and reduced-vowel symbol normalization.'}),
        'accepted':True,'confidence_is_not_perceptual_guarantee':True})
assert not onset['candidates'] and tail['summary']['suspicious_candidates']==0 and extended['new_onset_ctc_prefixes_complete']==50
assert signal['summary']['clipped_samples']==0 and signal['summary']['max_silence_peak_pcm16']==0
assert signal['summary']['min_master_channel_correlation']>.995
assert edge['summary']['max_first20ms_peak_pcm16']==edge['summary']['max_last20ms_peak_pcm16']==0
boundary=consistency['boundary_199_201'];rms_delta=boundary[1]['rms_dbfs']-boundary[0]['rms_dbfs']
suffix_deltas=[r['rms_delta_db'] for r in consistency['same_suffix_pairs']]
save('individual-recognition-review.json',{'source_manifest':ref(OUT/'fresh-aac-manifest.json'),'asr':ref(OUT/'fresh-asr.json'),'ctc':ref(OUT/'fresh-ctc.json'),
    'normalization_scope':'Stress/space removal and IPA reduced-i symbol equivalence only. All58 other discrepancies explicitly retained and individually reviewed.',
    'asr_results':asr_checks,'phoneme_results':per_phone,'limited_matches':163-len(differences),'individually_reviewed_differences':len(differences)})
for name in ('prepare_controls.py','event_consistency.py','finish_report.py'):
    shutil.copyfile(WORK/name,OUT/name)
evidence=[ref(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name not in ('report.json','report.txt')]
result={'schema_version':1,'kind':'new-user-requested-final-aac-recheck','status':'pass','accepted':True,'unresolved':[],'issues':[],
    'checked_at_utc':datetime.now(timezone.utc).isoformat(),'video':m['origin']['video'],'timeline':m['origin']['timeline'],'master':m['origin']['master'],
    'scope':'New final-MP4 decode, fresh isolated ASR and CTC for all163 utterances;150 independently worded odd values,13 complete dialogue, guarded/exact controls, waveform/edge/onset/tail and consistency checks. Old review acceptance was not reused as the current verdict.',
    'checks':{'fresh_asr':163,'numeric_values_correct':150,'whole_dialogue_matches_or_format_equivalent':13,'raw_asr_warnings':5,'raw_warning_causes':'digits vs spoken numerals and leftover spacing',
        'fresh_ctc':163,'limited_ctc_matches':163-len(differences),'individually_reviewed_ctc_differences':len(differences),'fricative_onsets':34,'fricative_prefix_candidates':0,
        'new_two_hundred_onsets':50,'new_two_hundred_prefix_complete':50,'terminal_classes':163,'terminal_tail_candidates':0,
        **signal['summary'],'start_end_edges':edge['summary'],'same_suffix_group_median_rms_delta_db':consistency['summary']['201to299']['median_rms_dbfs']-consistency['summary']['101to199']['median_rms_dbfs'],
        '199_to201_rms_delta_db':rms_delta},
    'consistency_interpretation':'No loudness discontinuity at199→201: RMS delta about-0.0017dB. New200s versus100s median RMS differs about+0.0012dB. Phrase durations are content-dependent; all event source durations and2s count gaps are fixed by the reviewed timeline, not time-stretched. Full-range RMS varies across naturally different phonemes and source crest-factor limits; no clipping or group gain switch is established.',
    'specific_raw_warnings':['N005 guarded z vs exact-event f-aI-v','N109 terminal d retained and tested in source/rate/padding grid','I04/I05 pairs raw p-eI-z retained with fresh rhotic LPC evidence'],
    'full_human_listening_claimed':False,'limits':'CTC/LPC and acoustic screens support review; they do not guarantee exact articulation or replace full human listening. Temporary extracted WAVs are reproducible from bound MP4 and event/extraction windows.',
    'prior_mp4_or_source_modified':False,'evidence':evidence}
save('report.json',result)
with (OUT/'report.txt').open('x',encoding='utf-8') as stream:
    stream.write('奇数v002 完成AAC 新規再チェック: PASS\n\n1〜299の150数詞、13台詞、全163発話を完成MP4から新たに復号してASR/CTCで検査。\n数値150/150一致、台詞13/13は数字表記とleftover分かち書きのみを正規化して一致。\nCTC105件は限定正規化一致、58差分は生の結果を保持して個別評価。\n語頭34+50件、語尾163分類、左右クリップ・164無音区間・音声端点に不備候補なし。\n199→201のRMS差-0.0017dB、100番台と200番台の中央値差+0.0012dBで群間音量段差なし。\nN005/N109の同AAC exact/controlとsource/rate/padding比較、pairsの新規LPC証拠を保存。\n自動解析と個別の音響評価を含み、人が全件を試聴したという記録ではない。\n原動画・原音・既存検査は変更していない。根拠とSHAはreport.jsonを参照。\n')
print(json.dumps({'status':'pass','asr':163,'ctc':163,'differences':len(differences),'report_sha256':sha(OUT/'report.json')}))
