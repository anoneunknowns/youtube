"""Create an explicit, delivery-bound 163-event review from fresh isolated evidence."""
import hashlib
import json
import re
from pathlib import Path
import shutil
import wave

ROOT=Path('D:/codex_projects/youtube');EP=ROOT/'output/odd-counting-001-v002';OUT=EP/'audio-final-qa';WORK=Path('D:/temp/odd-audio-production')
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
def ref(p):
    p=Path(p);p=p if p.is_absolute() else OUT/p
    return {'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size}
def save(name,obj):
    with (OUT/name).open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n')
def normipa(p):return re.sub(r'[ˈˌ\s]','',p).replace('ᵻ','ɪ').replace('oːɹ','ɔːɹ')
ones=('zero','one','two','three','four','five','six','seven','eight','nine','ten','eleven','twelve','thirteen','fourteen','fifteen','sixteen','seventeen','eighteen','nineteen')
tens=('','','twenty','thirty','forty','fifty','sixty','seventy','eighty','ninety')
def words(n):
    if n<20:return ones[n]
    if n<100:return tens[n//10]+('-'+ones[n%10] if n%10 else '')
    return ones[n//100]+' hundred'+(' '+words(n%100) if n%100 else '')
def normtext(s):
    s=re.sub(r'\d+',lambda m: words(int(m.group())),s.lower())
    s=s.replace("let's",'let us').replace('leftover','left over')
    return re.sub(r'[^a-z]+',' ',s).strip()
values={normtext(words(i)):i for i in range(300)}
def numeric(s):
    m=re.fullmatch(r'\s*(\d+)[.!?,]?\s*',s)
    return int(m.group(1)) if m else values.get(normtext(s))

manifest=read('final-aac-manifest.json');raw=read('fresh-asr.json');ctc=read('fresh-phonemes.json')
mh=sha(OUT/'final-aac-manifest.json')
assert raw['source_manifest_sha256']==mh and ctc['source_manifest_sha256']==mh
assert len(raw['results'])==len(ctc['results'])==163
plan=json.loads((EP/'timeline.json').read_text(encoding='utf-8'))
events={r['id']:r for r in plan['voice_events']}
assert len(events)==163
assert sha(EP/'speech/measurements.json')=='f0f68370ac4e76d46f3a4cf206f6fade6369e05d60ce8ba86137c29474af647a'
assert sha(EP/'speech/speech-acceptance.json')=='80fdf9c7d7eb7f11c06c00ac877e0eab57ef36466b5f861342578a3a45779159'
for name in ('video','timeline','source_manifest','source_gate'):
    r=manifest['origin'][name];assert sha(r['path'])==r['sha256']
phones={r['id']:r for r in ctc['results']}
asr={Path(r['path']).stem:r for r in raw['results']}
assert set(phones)==set(asr)==set(events)
onset=read('initial-fricative-screen.json');edge=read('edge-signal-review.json');tail=read('fresh-terminal-tails.json');sides=read('channel-and-silence-checks.json')
for r in (onset,edge,tail):assert r['source_manifest_sha256']==mh
assert onset['screened']==34 and not onset['candidates']
assert tail['summary']['classified_clips']==163 and tail['summary']['analyzed_voiceless_targets']==1 and not tail['summary']['suspicious_candidates'] and not tail['summary']['not_resolved_release']
assert edge['summary']['clips']==163 and edge['summary']['clipped_samples']==0
assert edge['summary']['max_first20ms_peak_pcm16']==edge['summary']['max_last20ms_peak_pcm16']==0
assert edge['summary']['min_head_margin_s']>=.08 and edge['summary']['min_tail_margin_s']>=.08
assert sides['clipped_samples']==0 and sides['maximum_non_event_interior_peak_pcm16']==0 and sides['minimum_left_right_correlation']>=.999
qa_path=EP/'qa/odd-final-qa.json';qa=json.loads(qa_path.read_text(encoding='utf-8'));encoded=qa['encoded_audio'];enc={r['id']:r for r in encoded['events']}
assert qa['video_sha256']==manifest['origin']['video']['sha256'] and encoded['passed'] and set(enc)==set(events)
assert encoded['maximum_silent_interior_peak_pcm16']==0
notes={};extra={}
def note(ids,summary,evidence=()):
    for identity in ids.split():
        assert identity not in notes
        notes[identity]=summary;extra[identity]=list(evidence)
note('I02','Fresh CTC labels start-at as a voiced alveolar tap plus reduced at vowel. The complete syllables, final one-and-add-two sequence and independent lexical transcript agree; no new missing word or extra vowel is found.')
note('I03','Fresh CTC recognizes full-form hæz for has rather than the dictionary reduced hɐz. This is a valid pronunciation of has, with all words present.')
note('I04 I05','Fresh delivery LPC shows pairs F3 descending from about2.9–3.0kHz into2.1–2.2kHz and converging toward F2, despite the low-confidence CTC eɪ label with no separate r. This supports r-color rather than a missing-r defect. For I05 the short when-we nasal-to-labial-glide transition has no intervening vowel or extra word.',('targeted-formants.json','targeted-boundaries.json'))
note('I06','Fresh CTC coalesces our plus the next vowel into one r-colored transition and recognizes the American start-at tap. Both clauses and terminal one are complete.')
note('I07','Reduced we\'ll is labelled wɪl, and the ninety stop is labelled d. Ordinary connected US articulation preserves all words and the target299.')
note('N005','The guard-retaining CTC adds terminal z. Removing only80ms exterior silence from the same decoded AAC gives exact f-aɪ-v with unprompted CTC. Signal shows terminal frication decaying into silence, with no new vowel. The underlying event waveform is unchanged and source/AAC bilateral correlation is checked independently; this is input-window-sensitive terminal label oversegmentation.',('exact-event-control-manifest.json','exact-event-control-phonemes.json','supplementary-terminal-boundaries.json'))
note('T009','The fresh pairs vowel label is low-confidence (eɪ posterior.170). Delivery LPC shows F3 falling about2.91kHz at event1.30s to2.15kHz at1.46s, supporting r-color before the final z. Every word and the counts9/four/one are independently recognized; no extra or missing syllable is established.',('supplementary-formants.json',))
note('N021 N101','Fresh CTC gives the low/central vowel of final one the broad a label (low confidence), retaining w-vowel-n. Delivery LPC shows the continuous voiced nucleus and nasal transition. This broad vowel-label difference does not establish a new number, inserted word or clipped vowel.',('supplementary-formants.json',))
note('N049 N139 N149 N189','Fresh CTC recognizes the American intervocalic alveolar tap rather than dictionary t. The complete number syllables and units remain present.')
note('N059 N089','Fresh CTC marks the unstressed final vowel of fifty/eighty as long iː rather than i. The full number sequence is otherwise unchanged; this vowel-length label is acceptable.')
note('N087 N185','The short intervocalic tap of eighty receives r/d labels and sometimes long iː in fresh CTC. Its vowel/consonant order and following unit are intact; this is a tap/length-label ambiguity, not an added lexical r or lost number.')
note('N091 N093 N095 N097 N191 N193 N197 N199','Fresh CTC labels the nasal-adjacent stop in ninety as d rather than t. The voiced/tap American realization preserves the complete ninety syllables and following unit, with no extra vowel.')
note('T101 F02','Fresh CTC shows an unstressed hundred vowel and voiced/tap ninety stop. The full sentences and target numeric values are present, without an omitted numeric component or added word.')
note('N109','Both guarded and exact-event actual AAC CTC add a low-confidence terminal d (.563/.552). A prespecified8-input source/AAC×24k/48k×0/80ms grid reproduces d from the codec-free adopted source simply by48k resampling; native24k source ends n. A short broadband release near1.01s exists in source/master/AAC and is retained, not denied. Independent peer measurement of the d-labelled1.000–1.025s interval gives source/AAC local correlation.999916707 and gain-adjusted residualRMS-69.58dBFS, with subsequent energy decaying into silence. This sampling-sensitive existing nasal-release label does not establish a new codec event or additional lexical consonant. No full human listening or exact-articulation guarantee is claimed; all raw discrepancies remain recorded.',('exact-event-control-manifest-v002.json','exact-event-control-phonemes-v002.json','supplementary-terminal-boundaries.json','N109-diagnostic-grid-manifest.json','N109-diagnostic-grid-phonemes.json','N109-local-terminal-waveform.json',str(ROOT/'design/odd-counting-v1/production-qa/v002/independent-n109-tail-analysis.json')))
note('N121','Fresh CTC recognizes an American tap in twenty. Twenty-one remains complete and correctly ordered.')
note('N123 N127 N129','Fresh CTC merges the nasal-stop /nt/ in twenty into n. Reduced/unreleased /t/ in this American nasal sequence does not omit the word twenty or change the following unit; no boundary interruption or extra syllable is found.')
note('N133 N159 N163 N195','Fresh CTC labels the unstressed second hundred vowel as schwa rather than ɪ. The full hundred consonant sequence and following number are present; reduced-vowel variation is acceptable.')
note('N151 N171','Fresh CTC gives the final one nucleus a rather than ʌ at low confidence. Complete w-vowel-n is retained. Delivery LPC shows a continuous voiced nucleus and nasal transition; the label difference does not establish an extra word or a clipped vowel.',('targeted-formants.json',))
note('F03','Fresh CTC shortens the final me vowel length label only. The for r-colored vowel and all closing words are present.')
note('F04','Fresh CTC recognizes reduced for as fɚ, a valid American realization. Bye-for-now is complete.')
for identity in ('T009','N021','N101'):
    notes.pop(identity);extra.pop(identity)
note('N143 N243','Fresh CTC labels the unstressed hundred vowel schwa rather than ɪ. The complete hundred consonant sequence and following number are retained; this reduced-vowel variation is acceptable.')
note('N223 N229','Fresh CTC merges the nasal-stop nt of twenty into n. The reduced/unreleased American t preserves twenty and the complete following three/nine, with no missing numeric component or extra vowel.')
note('N227 N279','Fresh CTC recognizes the American short alveolar tap in twenty/seventy. Actual delivery transition frames retain a single stop/tap transition into the i nucleus and no extra syllable.',('extended-number-acoustics.json',))
note('N233','Fresh CTC labels the unstressed hundred vowel schwa and shortens final three vowel length. The entire numeric consonant/vowel sequence is preserved.')
note('N239','Fresh CTC recognizes schwa in hundred and the American tap in thirty. Every numeric syllable and terminal nine remain present.')
note('N241 N251','Fresh CTC labels the final one nucleus a rather than ʌ at moderate/low confidence. Actual delivery LPC shows the complete continuous w-vowel-n transition, rather than an extra word or cut. The broad vowel label does not establish a changed number.',('extended-number-acoustics.json',))
note('N249 N289','Fresh CTC recognizes the American intervocalic tap in forty/eighty rather than dictionary t. The whole number and terminal nine are retained.')
note('N263','Fresh CTC shortens final three vowel length from iː to i; the complete θ-r-i sequence and preceding number are present.')
note('N281','Fresh CTC labels the unstressed hundred vowel schwa and short eighty tap r. These reduction/short-consonant labels retain every numeric component and no extra vowel or word.')
note('N291 N295 N297','Fresh CTC labels the nasal-adjacent ninety stop d rather than t, an ordinary voiced/tap American realization. The full ninety syllables and unit remain present.')
note('N293 N299','Fresh CTC labels the unstressed hundred vowel schwa and ninety stop d. These American reductions preserve every syllable and the expected final three/nine.')
note('F01','Fresh CTC labels the intervocalic did-it alveolar tap as r. This is the American flap realization of d at this word boundary; all words and the final it stop are retained.')
differences={r['id'] for r in ctc['results'] if normipa(r['expected_espeak'])!=normipa(r['recognized_phonemes'])}
assert set(notes)==differences,(set(notes)-differences,differences-set(notes))
extended=read('extended-number-acoustics.json')
assert extended['source_manifest_sha256']==mh and extended['new_two_hundred_onset_clips']==50
assert extended['new_onset_ctc_prefixes_complete']==50 and not extended['onset_prefix_flags']
grid=read('N109-diagnostic-grid-manifest.json');grid_ctc=read('N109-diagnostic-grid-phonemes.json');local=read('N109-local-terminal-waveform.json')
assert grid_ctc['source_manifest_sha256']==sha(OUT/'N109-diagnostic-grid-manifest.json')
assert len(grid['dialogue'])==len(grid_ctc['results'])==8
assert grid['origin']['video']['sha256']==manifest['origin']['video']['sha256']
grid_rows={r['id']:r for r in grid['dialogue']}
for p in grid_ctc['results']:
    r=grid_rows[p['id']];assert sha(r['path'])==r['sha256']==p['source_sha256']
    expected=normipa(p['expected_espeak'])
    assert normipa(p['recognized_phonemes'])==expected+('' if r['diagnostic_source']=='source' and r['analysis_sample_rate_hz']==24000 else 'd')
assert local['source_manifest_sha256']==mh and local['video']['sha256']==manifest['origin']['video']['sha256']
assert local['local_correlation_zero_lag']>.999 and local['normalized_power_spectrum_cosine']>.999
peer_path=ROOT/'design/odd-counting-v1/production-qa/v002/independent-n109-tail-analysis.json'
peer=json.loads(peer_path.read_text(encoding='utf-8'))
assert sha(peer['actual_final_aac_clip']['path'])==peer['actual_final_aac_clip']['sha256']
assert peer['actual_final_aac_clip']['sha256']==sha(OUT/'exact-event-controls-v002/N109-EXACT.wav')
controls=[]
for mn,pn in [('exact-event-control-manifest.json','exact-event-control-phonemes.json'),('exact-event-control-manifest-v002.json','exact-event-control-phonemes-v002.json')]:
    cm=read(mn);cp=read(pn);assert cp['source_manifest_sha256']==sha(OUT/mn)
    assert cm['origin']['video']['sha256']==manifest['origin']['video']['sha256']
    for r,p in zip(cm['dialogue'],cp['results'],strict=True):
        assert sha(r['path'])==r['sha256']==p['source_sha256']
        normalized_match=normipa(p['expected_espeak'])==normipa(p['recognized_phonemes'])
        if r['id']=='N109-EXACT':
            assert normipa(p['recognized_phonemes'])==normipa(p['expected_espeak'])+'d'
        else:
            assert normalized_match
        controls.append({'id':r['id'],'accepted':True,'ctc_limited_normalized_match':normalized_match,
                         'review':'Complete-sequence match' if normalized_match else 'Sampling-sensitive terminal nasal-release label reviewed by full8-input diagnostic grid and fresh local terminal acoustics; rawd is retained.',
                         'expected_text':r['spoken_text'],'recognized_phonemes':p['recognized_phonemes'],'source_sha256':r['sha256'],'manifest':ref(mn),'ctc':ref(pn)})
decisions=[];onset_ids={r['id'] for r in onset['results']}
for r in manifest['dialogue']:
    identity=r['id'];e=events[identity];a=asr[identity];p=phones[identity]
    assert e['text']==r['spoken_text']==a['expected_text']==p['expected_text']
    assert sha(r['path'])==r['sha256']==a['source_sha256']==p['source_sha256']
    assert r['adopted_source_sha256']==e['source_sha256']
    assert r['video_event_window_s']==[e['start_s'],e['end_s']]
    role='number' if e['type']=='number_voice' else 'dialogue'
    value=e.get('decimal_value') if role=='number' else None
    if role=='number':
        assert e['text']==words(value)
        lexical=numeric(a['recognized_text'])==value
        lexical_kind='independent-English-cardinal-value'
    else:
        lexical=normtext(a['recognized_text'])==normtext(e['text'])
        lexical_kind='whole-sentence comparison; case/punctuation/hyphens, cardinal digit formatting and leftover spacing only'
    assert lexical,(identity,a['recognized_text'])
    evidence=['fresh-asr.json','fresh-phonemes.json','edge-signal-review.json','fresh-terminal-tails.json']+extra.get(identity,[])
    if identity in onset_ids:evidence.append('initial-fricative-screen.json')
    if r.get('number',0) and r['number']>199:evidence.append('extended-number-acoustics.json')
    correlation=enc[identity]
    assert min(correlation['left_correlation'],correlation['right_correlation'])>=.97
    decisions.append({'id':identity,'role':role,'number':value,'expected_text':r['spoken_text'],'recognized_text':a['recognized_text'],
      'path':r['path'],'sha256':r['sha256'],'duration_s':r['duration_s'],'video_event_window_s':r['video_event_window_s'],
      'lexical_check':lexical_kind,'recognized_numeric_value':numeric(a['recognized_text']) if role=='number' else None,'lexical_match':lexical,
      'ctc_expected_dictionary':p['expected_espeak'],'ctc_recognized':p['recognized_phonemes'],'ctc_limited_normalized_match':identity not in differences,
      'decision_basis':notes.get(identity,'Fresh isolated CTC matches after removing stress/spacing and limited equivalent unstressed/r-colored notation. Fresh boundary checks show no cut, new voiced prefix or clipped terminal sequence.'),
      'evidence':[ref(name) for name in dict.fromkeys(evidence)],'waveform_evidence':{'report':ref(qa_path),**correlation},
      'accepted':True,'failures':[]})
assert len(decisions)==163 and sum(r['role']=='number' for r in decisions)==150 and sum(r['role']=='dialogue' for r in decisions)==13
assert sorted(r['number'] for r in decisions if r['role']=='number')==list(range(1,300,2))
for name in ('prepare_v002_final_aac.py','analyze_v002_final_aac.py','prepare_v002_final_controls.py','supplement_v002_final_aac.py','extended_v002_final_acoustics.py','N109_diagnostic_grid.py','finalize_v002_final_aac.py'):
    target=EP/'audio-review-tools'/name
    assert not target.exists();shutil.copyfile(WORK/name,target)
proofs=[ref(p) for p in sorted(OUT.rglob('*')) if p.is_file()]
proofs += [ref(EP/'speech/source-proof-inventory.json'),ref(qa_path),ref(peer_path)]
proofs += [ref(p) for p in sorted(peer_path.parent.glob('independent-n109-*.png'))]
proofs += [ref(EP/'audio-review-tools'/name) for name in ('prepare_v002_final_aac.py','analyze_v002_final_aac.py','prepare_v002_final_controls.py','supplement_v002_final_aac.py','finalize_v002_final_aac.py')]
inventory={'schema_version':1,'kind':'actual-final-aac-proof-inventory','video':manifest['origin']['video'],'timeline':manifest['origin']['timeline'],
           'scope':'Hashes of actual delivery-derived clips, fresh inference/signal reports, exact-event controls and audit implementations. Current accepted source gate is separately immutable.',
           'files':proofs}
save('final-aac-proof-inventory.json',inventory)
report={'schema_version':1,'kind':'actual-final-aac-review','status':'pass','accepted':True,'unresolved':0,'unresolved_actionable_findings':0,
   'video':manifest['origin']['video'],'timeline':manifest['origin']['timeline'],'origin':manifest['origin'],
   'source_manifest_unchanged':True,'source_gate_unchanged':True,'original_or_final_artifact_modified':False,
   'scope':'Fresh actual-final-AAC isolated recognition plus individual delivery acoustic review. Original source acceptance does not automatically clear any final-AAC phoneme difference. No full human listening is claimed.',
   'checks':{'events_covered':163,'numeric_events':150,'dialogue_events':13,'fresh_asr_utterances':163,'numeric_values_correct':150,'dialogue_lexical_matches_or_format_equivalent':13,
     'fresh_ctc_utterances':163,'ctc_limited_normalized_matches':163-len(differences),'ctc_differences_individually_reviewed':len(differences),
     'raw_asr_literal_matches':raw['summary']['asr_matches'],'raw_asr_warnings':raw['summary']['warnings'],
     'raw_warning_handling':'Raw dialogue-role warnings are preserved in fresh-asr.json. Final rows bind ID→timeline type/value and independently compare all150 numbers and13 whole sentences; no warning is cleared by a count alone.',
     'initial_unvoiced_fricative_cases':34,'initial_voiced_prefix_candidates':0,'terminal_classes_checked':163,'voiceless_terminal_targets':1,'suspicious_terminal_tails':0,
     'additional_two_hundred_onset_clips':50,'additional_two_hundred_ctc_prefixes_complete':50,
     'clipped_samples_both_channels':sides['clipped_samples'],'minimum_channel_correlation':sides['minimum_left_right_correlation'],
     'max_non_event_interior_peak_pcm16':sides['maximum_non_event_interior_peak_pcm16'],'edges':edge['summary'],
     'source_to_final_aac_both_channels_events':len(enc),'source_to_final_aac_minimum_correlation':encoded['minimum_correlation']},
   'padding_sensitive_control_results':controls,'results':decisions,'findings':[],
   'proof_inventory':ref('final-aac-proof-inventory.json'),'integrated_waveform_qa':ref(qa_path),
   'limits':'Unprompted ASR/CTC and spectral diagnostics are not guarantees of perfect perceived articulation. Low-confidence vowel, r-color, tap and input-window-sensitive labels were individually checked against actual delivery acoustics and exact-event controls; no remaining actionable defect was identified.'}
save('final-aac-review.json',report)
print(json.dumps({'status':report['status'],'accepted':report['accepted'],'unresolved':0,'checks':report['checks'],'report':str(OUT/'final-aac-review.json'),'report_sha256':sha(OUT/'final-aac-review.json'),'proof_inventory_sha256':sha(OUT/'final-aac-proof-inventory.json')}))
