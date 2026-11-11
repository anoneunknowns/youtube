import hashlib
import json
import re
import shutil
import wave
from pathlib import Path

OUT = Path('D:/codex_projects/youtube/output/odd-counting-001-v002/speech')
def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(name):
    return json.loads((OUT/name).read_text(encoding='utf-8'))
def write(name, value):
    with (OUT/name).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')
def ref(name, summary, kind='isolated-acoustic-analysis'):
    return {'kind':kind,'path':str(OUT/name),'sha256':sha(OUT/name),'summary':summary}
def normipa(s):
    return re.sub(r'[ˈˌ\s]','',s).replace('ᵻ','ɪ').replace('oːɹ','ɔːɹ')
small = ['zero','one','two','three','four','five','six','seven','eight','nine','ten','eleven','twelve','thirteen','fourteen','fifteen','sixteen','seventeen','eighteen','nineteen']
tens = ['', '', 'twenty','thirty','forty','fifty','sixty','seventy','eighty','ninety']
def words(n):
    if n < 20: return small[n]
    if n < 100: return tens[n//10] + ('-'+small[n%10] if n%10 else '')
    return small[n//100]+' hundred'+(' '+words(n%100) if n%100 else '')
def normtext(s):
    s=re.sub(r'\d+',lambda m: words(int(m.group())),s.lower())
    s=s.replace("let's", 'let us').replace('leftover','left over')
    return re.sub(r'[^a-z]+',' ',s).strip()

initial=OUT/'initial-measurements-v001.json'
manifest=read(initial.name)
clips=manifest['numbers']+manifest['dialogue']
assert len(clips)==163 and [r['number'] for r in manifest['numbers']]==list(range(1,300,2))
for r in clips:
    assert sha(r['path'])==r['sha256'],r['id']
    with wave.open(r['path'],'rb') as w:
        assert w.getnframes()==r['sample_frames']
        assert w.getframerate()==24000 and w.getnchannels()==1 and w.getsampwidth()==2
        assert abs(r['duration_s']-w.getnframes()/24000)<1e-12
final=OUT/'measurements.json'
if final.exists():
    assert sha(final)==sha(initial),'Existing current manifest cannot be changed'
else:
    shutil.copyfile(initial,final)
mh=sha(final)

raw=read('isolated-asr-raw-v001.json')
phon=read('isolated-phonemes-v001.json')
assert phon['source_manifest_sha256']==mh
assert sha(OUT/'isolated-input-v001.json')==raw['source_manifest_sha256']
assert len(raw['results'])==163 and len(phon['results'])==163
pr={r['id']:r for r in phon['results']}
onset=read('initial-fricative-screen-v002.json')
assert onset['source_manifest_sha256']==mh and not onset['candidates']
onset_ids={r['id'] for r in onset['results']}
assert len(onset_ids)==34
tail=read('terminal-tail-review-v001.json')
assert tail['source_manifest_sha256']==mh and tail['summary']['suspicious_candidates']==0 and tail['summary']['not_resolved_release']==0
edge=read('source-edge-review-v001.json')
assert edge['source_manifest_sha256']==mh and edge['summary']['clipped_samples']==0 and edge['summary']['max_edge_sample_abs']==0

notes={}
def setnote(ids,text):
    for i in ids.split():
        assert i not in notes
        notes[i]=text
setnote('N065','CTC splits initial /s/ across a blank. Fresh 20ms signal frames show a single continuous aperiodic frication (0.02–0.11s) followed by the first voiced vowel at 0.12s, with no intervening voiced vowel or repeated syllable.')
setnote('N081 N087 N185','The intervocalic alveolar tap in eighty is labelled t/r/d by CTC. The surrounding eɪ-i sequence and the following unit word are present. This is a tap-label ambiguity, not an inserted lexical r or a missing numeric syllable.')
setnote('N089','CTC marks the final vowel of eighty as long iː instead of i. The eighty-nine phoneme sequence is otherwise complete; vowel-length label variation is acceptable.')
setnote('N091 N093 N095 N097 N191 N193 N197 N199','CTC labels the nasal-adjacent intervocalic stop of ninety as d rather than t. This American English voicing/tap realization preserves the ninety syllables and the following unit, without an extra vowel or number change.')
setnote('N121','CTC labels the intervocalic twenty stop as a tap. This is ordinary American English connected articulation; the full twenty-one sequence is preserved.')
setnote('N123 N127 N129','CTC merges the /nt/ sequence of twenty into /n/. A reduced or unreleased alveolar stop in this nasal-stop sequence is acceptable American articulation; twenty and the correct following unit retain their vowel and consonant identities.')
setnote('N133 N143 N195','The unstressed second vowel of hundred is labelled schwa rather than ɪ. Reduced-vowel variation is acceptable; the complete hundred consonant sequence and following two-digit number are present.')
setnote('N139 N149 N189','CTC recognizes the expected American intervocalic alveolar tap rather than the dictionary t label. The number sequence is complete and there is no additional syllable.')
setnote('N151 N161 N171','CTC labels the vowel nucleus of the final one as a rather than ʌ (posterior 0.41–0.52). The w-vowel-n sequence is complete. These broad low/central vowel labels do not indicate an extra utterance or a different number; fresh LPC trajectories for N151/N171 show continuous voiced vowel nuclei rather than any inserted word.')
setnote('N159 N163','The unaccented vowel in hundred is absorbed into the r/d transition by CTC. Fresh signal frames show voiced low-frequency r/reduced-vowel energy at 0.46–0.55s followed by the final stop and next fricative. The entire word hundred is present; no numeric component is omitted.')
setnote('N173','CTC splits the medial s across a blank, and does not mark final three vowel length. Fresh frames show continuous unvoiced frication at 0.60–0.70s, then the first voiced vowel at 0.71s. There is no repeated syllable; the final θ-r-i sequence is complete.')
setnote('I02','The start-at word boundary has a voiced alveolar tap and a reduced at vowel. Both syllabic nuclei and the following one-and-add-two sequence remain present; the independent lexical recognition agrees with the full sentence.')
setnote('I03','CTC recognizes full-form hæz for has instead of the reduced hɐz dictionary form. This is a valid pronunciation of has and the sentence is complete.')
setnote('I04','The low-confidence CTC vowel label in pairs (eɪ posterior 0.215) lacks a separate r. Fresh LPC trajectories show F3 falling about 2.93kHz at 1.17s to 2.09kHz at 1.33s and converging toward F2, supporting the expected r-colored vowel. The final z is present. No actionable missing-r defect remains.')
setnote('I05','The pairs vowel label is low-confidence (eɪ posterior 0.243). Fresh LPC shows F3 falling about 3.05kHz at 2.29s to 2.04–2.15kHz at 2.44–2.45s, supporting r-coloring before z. At when-we, a single short labial-nasal transition (CTC m at 1.88s) precedes w/i; the continuous nasal-to-glide signal has no intervening extra vowel or word.')
setnote('I06','CTC coalesces our plus the following vowel to one r-colored transition and recognizes the start-at tap. These are connected-speech boundary variations; both clauses and final one are complete.')
setnote('I07','CTC labels reduced we\'ll as wɪl and the ninety stop as d. These ordinary American English reductions preserve every lexical component and the terminal ninety-nine.')
setnote('T101 F02','CTC recognizes an unstressed hundred vowel and a voiced/tap realization of the ninety stop. The complete expected phrase and the target numeric values are present with no missing or extra number.')
setnote('F03','Unstressed for is reduced to fɜː and final me is labelled short i. These are ordinary reduction/length-label differences; every word of the closing line is present.')
setnote('F04','Unstressed for is reduced to fɚ, a valid American pronunciation. Bye-for-now remains complete.')
notes['I07']="Fresh CTC labels reduced we'll as wɪl, all as ɑːl rather than ɔːl (valid US cot/caught-type vowel variation), and ninety t as d. Every lexical component including two-hundred-ninety-nine remains present."
setnote('N219 N259','Fresh CTC absorbs the unstressed hundred vowel into the r/d transition. Original source signal has strong continuous voiced r/reduced-vowel energy at0.40–0.48s (N219) or0.38–0.46s (N259), followed by the final stop. The word hundred remains complete; no numeric component is missing.')
setnote('N223','Fresh CTC merges the nasal-stop nt of twenty into n and shortens the final three vowel-length label. Reduced/unreleased t in this American sequence and length marking do not omit twenty or alter the following three; all number syllables are present.')
setnote('N227 N277','Fresh CTC recognizes an American alveolar tap in twenty/seventy. This is ordinary intervocalic articulation and the whole numeric sequence is preserved.')
setnote('N229','Fresh CTC labels the unstressed hundred vowel as schwa and merges twenty nt into n. These reductions preserve all number syllables and the complete unit nine; no inserted syllable is established.')
setnote('N233','Fresh CTC labels the unstressed hundred vowel as schwa and shortens the final three vowel-length label. The full expected consonant/vowel sequence and all numeric components remain present.')
setnote('N239 N249 N289','Fresh CTC recognizes the American intervocalic alveolar tap rather than dictionary t in thirty/forty/eighty. The complete number and following nine remain intact.')
setnote('N241 N251','Fresh CTC labels the final one nucleus a rather than ʌ at moderate/low probability. The complete w-vowel-n sequence is present. Fresh LPC trajectories show one continuous voiced nucleus and a following nasal transition, with no extra word or cut; the broad vowel label does not change the numeric value.')
setnote('N263','Fresh CTC shortens the vowel-length label of final three from iː to i. The full θ-r-i sequence and all preceding number syllables are present.')
setnote('N273','Fresh CTC labels the unstressed second hundred vowel schwa rather than ɪ. This accepted reduced-vowel variation preserves the entire number sequence.')
setnote('N279','Fresh CTC splits the short stop/tap in seventy into adjacent t/ɾ labels (posterior.500/.405). Source signal has one closure/release at0.86–0.90s followed by the sole i nucleus beginning0.92s, with no interposed vowel or extra syllable. This is short-consonant segmentation ambiguity, not an additional word.')
setnote('N281','Fresh CTC recognizes a reduced schwa in hundred and labels the short eighty tap as r. The complete vowel/consonant order and following one remain present; there is no extra lexical r or numeric component.')
setnote('N291 N295 N297','Fresh CTC labels the nasal-adjacent stop in ninety as d. This voiced/tap American realization preserves all numeric syllables and the correct final unit.')
setnote('N293','Fresh CTC labels the unstressed hundred vowel schwa, ninety stop d, and shortens final three vowel length. These ordinary reduced-vowel, tap and length-label variants preserve all numeric components.')
setnote('N299','Fresh CTC labels the unstressed hundred vowel schwa and ninety stop d. The full two-hundred-ninety-nine sequence is present without an omitted or additional number.')
differences={r['id'] for r in phon['results'] if normipa(r['expected_espeak'])!=normipa(r['recognized_phonemes'])}
assert differences==set(notes),(differences-set(notes),set(notes)-differences)

asrrows=[]
reviews=[]
for r in clips:
    role='number' if r.get('number') is not None else 'dialogue'
    matches=[a for a in raw['results'] if a['source_sha256']==r['sha256'] and a['expected_text']==r['spoken_text']]
    assert len(matches)==1,r['id']
    a=matches[0]
    assert normtext(a['recognized_text'])==normtext(r['spoken_text']),(r['id'],a['recognized_text'])
    p=pr[r['id']]
    assert p['source_sha256']==r['sha256'] and p['expected_text']==r['spoken_text']
    identity={'role':role,'id':r['id'],'number':r.get('number'),'expected_text':r['spoken_text'],'source_sha256':r['sha256']}
    ar={**a,**identity,'original_inference_role':a['role'],'raw_status':a['status'],
        'semantic_text_match':True,'semantic_match_method':'Case/punctuation/hyphen spacing, digits expanded as English cardinal words, let\'s→let us and leftover→left over; no phonemes inferred from expected text.'}
    if role=='number':
        m=re.fullmatch(r'\s*(\d+)\.?\s*',a['recognized_text'])
        assert m and int(m.group(1))==r['number']
        ar['interpreted_number']=int(m.group(1))
    asrrows.append(ar)
    summary=notes.get(r['id'],'Unprompted phoneme CTC matches the expected isolated sequence after removing dictionary stress/spacing and equivalent unstressed-vowel/r-colored-o normalization. No extra lexical vowel or truncated terminal sequence is indicated.')
    evidence=[ref('isolated-phonemes-v001.json',f'{r["id"]}: {summary}','isolated-phoneme-asr'),
              ref('source-edge-review-v001.json',f'{r["id"]}: fresh source PCM format/frame/hash check; no clipped samples, zero edge samples and at least 15ms active-edge guards.'),
              ref('terminal-tail-review-v001.json',f'{r["id"]}: terminal class checked against its expected final sound; whole-manifest terminal screening had zero suspicious candidates. Non-target voiced endings are checked by isolated CTC, not an unvoiced-tail heuristic.')]
    if r['id'] in onset_ids:
        evidence.append(ref('initial-fricative-screen-v002.json',f'{r["id"]}: fresh onset frame screen found no strong voiced-prefix run before the expected initial unvoiced frication.'))
    if r['id'] in ('N065','N173','N159','N163','I05'):
        evidence.append(ref('targeted-boundaries-v001.json',f'{r["id"]}: {notes[r["id"]]}'))
    if r['id'] in ('I04','I05','N151','N171'):
        evidence.append(ref('targeted-formants-v001.json',f'{r["id"]}: {notes[r["id"]]}'))
    if r.get('number',0)>199:
        evidence.append(ref('extended-number-acoustics-v001.json',f'{r["id"]}: freshly generated two-hundred onset includes complete initial t-u-h CTC tokens; immutable-source head frames and targeted ambiguous transitions/vowels are measured in this report.'))
    reviews.append({**identity,'decision':'pass','review_type':'Fresh isolated ASR + independent CTC with explicit per-difference review and targeted source acoustics; no human-listening claim.',
                    'phoneme_difference':r['id'] in differences,'resolution':summary,'evidence':evidence})

write('isolated-asr.json',{'schema_version':1,'kind':'independent-local-asr-review','source_manifest':str(final),'source_manifest_sha256':mh,
      'raw_inference_report':{'path':str(OUT/'isolated-asr-raw-v001.json'),'sha256':sha(OUT/'isolated-asr-raw-v001.json')},
      'original_input_manifest':{'path':str(OUT/'isolated-input-v001.json'),'sha256':sha(OUT/'isolated-input-v001.json')},
      'derivation':'No new inference. Original unchanged WAV SHA and expected text are checked one-to-one; number rows are restored from dialogue representation because the legacy numeric CLI requires contiguous 1..max. Raw recognized text and warning status are preserved. Only the deterministic text/numeric comparison is added.',
      'model':raw['model'],'method':raw['method'],
      'summary':{'clips':163,'numbers':150,'dialogue':13,'semantic_text_matches':163,'raw_literal_matches':raw['summary']['asr_matches'],'raw_warnings_preserved':raw['summary']['warnings']},'results':asrrows})
write('pronunciation-review.json',{'schema_version':1,'kind':'speech-pronunciation-review','source_manifest_sha256':mh,
      'scope':'Automatic isolated evidence plus individual analytical review of phoneme differences; no assertion of full human listening. Independent CTC is unprompted; expected dictionary labels were computed after recognition. Numeric/text recognition alone does not clear pronunciation.',
      'summary':{'clips':163,'phoneme_normalized_matches':163-len(differences),'phoneme_differences_individually_resolved':len(differences),'initial_unvoiced_fricative_cases_freshly_screened':34,'unresolved':0,'source_replacements':0},
      'results':reviews})
windows={'I01':(.8,4.3),'I02':(5,8.5),'I03':(9.2,12),'I04':(13,18.5),'I05':(19.2,23.7),'I06':(25,29.4),'I07':(30.2,35),'T009':(.7,6.5),'T101':(.5,7),'F01':(1,2.3),'F02':(2.8,7.8),'F03':(8.2,10.5),'F04':(10.8,11.8)}
wr=[]
for r in manifest['dialogue']:
    start,end=windows[r['id']]
    assert start+r['duration_s']<=end
    wr.append({'id':r['id'],'source_sha256':r['sha256'],'window_start_s':start,'window_end_s':end,'duration_s':r['duration_s'],'remaining_margin_s':end-start-r['duration_s'],'fits':True})
write('dialogue-window-fit-v001.json',{'schema_version':1,'kind':'speech-editorial-window-fit','source_manifest_sha256':mh,'results':wr})
print(json.dumps({'manifest_sha256':mh,'numbers':150,'dialogue':13,'numeric_duration_s':sum(r['duration_s'] for r in manifest['numbers']),'phoneme_differences_reviewed':len(differences),'unresolved':0}))
