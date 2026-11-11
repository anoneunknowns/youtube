"""New all-word/nucleus prosody screen; no perceptual-stress certification."""
from pathlib import Path
import array
import difflib
import hashlib
import json
import math
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[5]
QA = Path(__file__).resolve().parent
OUT = ROOT/'output/fibonacci-quality-closeout-20261112-01'
sys.path.insert(0, str(ROOT))
from tools.review_fibonacci_speech import normalize_phones


def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


expected = {row['word']:row['ipa'] for row in read(QA/'expected-word-pronunciations.json')['results']}
dictionary = {}
for line in (QA/'cmudict.dict').read_text().splitlines():
    word, _, pronunciation = line.partition(' ')
    dictionary.setdefault(re.sub(r'\(\d+\)$','',word), []).append(pronunciation)
manifest_path = OUT/'new-final-left-guarded/measurements.json'
manifest = read(manifest_path)
measurements = {row['id']:row for row in manifest['numbers']+manifest['dialogue']}
phones = read(QA/'new-guarded-phonemes.json')
vowels = {'aɪ','eɪ','aʊ','oʊ','iː','ɪ','ə','ʌ','uː','ɜː','ɔːɹ','ɔː','æ','ɛ','ɑː','i','ʊ','əɹ','ɚ','ᵻ','ɐ','oːɹ'}


def nucleus(samples, center):
    start = max(0, round((center-.02)*8000)); window = samples[start:start+320]
    mean = sum(window)/len(window); x = [sample-mean for sample in window]
    energy = sum(sample*sample for sample in x)
    correlations = []
    for lag in range(20, 101):
        first, second = x[:-lag], x[lag:]
        denominator = math.sqrt(sum(a*a for a in first)*sum(a*a for a in second))
        correlations.append((sum(a*b for a,b in zip(first,second))/max(1e-30,denominator),lag))
    best = max(correlations)
    candidates = [value for i,value in enumerate(correlations[1:-1],1)
                  if value[0] >= correlations[i-1][0] and value[0] >= correlations[i+1][0]
                  and value[0] >= max(.65, best[0]*.9)]
    selected = min(candidates,key=lambda value:value[1]) if candidates else None
    return {'center_s':center,'window_s':.04,'rms_dbfs':20*math.log10(max(1e-12,math.sqrt(energy/len(x)))),
            'F0_hz_if_periodic':8000/selected[1] if selected else None,
            'periodicity_peak':best[0], 'diagnostic_only':True}


results=[]
for row in phones['results']:
    ident=row['id']; measured=measurements[ident]
    words=re.findall(r"[a-z]+(?:'[a-z]+)?",row['expected_text'].lower())
    spans=[]; expected_joined=''
    for word in words:
        normalized=normalize_phones(expected[word]);begin=len(expected_joined);expected_joined+=normalized
        spans.append((word,begin,len(expected_joined)))
    recognized='';tokenchars=[]
    for index, token in enumerate(row['tokens']):
        normalized=normalize_phones(token['token']);recognized+=normalized;tokenchars.extend([index]*len(normalized))
    sequence=difflib.SequenceMatcher(None,expected_joined,recognized,autojunk=False)
    charmap={}
    for operation,a,b,c,d in sequence.get_opcodes():
        if operation=='equal':
            for first,second in zip(range(a,b),range(c,d)):charmap[first]=tokenchars[second]
    pcm=subprocess.check_output([str(ROOT/'.venv/bin/ffmpeg'),'-v','error','-i',str(manifest_path.parent/measured['path']),'-ac','1','-ar','8000','-f','f64le','pipe:1'])
    samples=array.array('d',pcm);word_rows=[]
    for word,begin,end in spans:
        indices=sorted({charmap[index] for index in range(begin,end) if index in charmap})
        matched=[row['tokens'][index] for index in indices]
        nuclei=[{**token,'signal':nucleus(samples,(token['start_s']+token['end_s'])/2)}
                for token in matched if token['token'] in vowels]
        reference=dictionary.get(word,[])
        word_rows.append({'word':word,'dictionary_US_IPA_reference':expected[word],
                          'CMU_US_reference':reference,'CMU_stress_patterns_reference_only':[[part[-1] for part in variant.split() if part[-1:].isdigit()] for variant in reference],
                          'approximate_CTC_start_s':matched[0]['start_s'] if matched else None,
                          'approximate_CTC_end_s':matched[-1]['end_s'] if matched else None,
                          'observed_matching_phone_tokens':matched,'vowel_nucleus_signal_samples':nuclei,
                          'missing_alignment_does_not_prove_missing_word':not bool(indices)})
    results.append({'id':ident,'expected_text':row['expected_text'],'source_sha256':row['source_sha256'],
                    'recognized_phonemes':row['recognized_phonemes'],'words':word_rows,
                    'stress_screen_scope':'Reference stress patterns and new observed vowel energy/periodicity/phone-time evidence inspected for teen/ty contrast, long words, scales and operators. These proxies are not a human perceived-stress or naturalness verdict.'})
    print('screened',ident,flush=True)
report={'kind':'new-all104-word-phone-nucleus-and-stress-reference-screen',
        'source_manifest_sha256':sha(manifest_path),'source_CTC_sha256':sha(QA/'new-guarded-phonemes.json'),
        'CMU_dictionary':read(QA/'cmudict-source.json'),
        'method':'eSpeak word phone labels and CMU stress references are aligned only after no-prompt independent CTC inference. Approximate matched vowel nuclei receive new40ms8kHz energy and normalized80–400Hz autocorrelation measurements. Word-stress interpretation is qualified and cannot be reduced to maximum loudness/F0; no universal quality threshold or phonetic approval is applied.',
        'summary':{'utterances':len(results),'word_occurrences':sum(len(row['words']) for row in results),
                   'matched_vowel_nuclei':sum(len(word['vowel_nucleus_signal_samples']) for row in results for word in row['words'])},
        'human_listening_claim':False,'stress_or_naturalness_perfect_certification':False,'results':results}
with (QA/'all104-word-prosody-screen.json').open('x') as stream:
    json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(report['summary'])
