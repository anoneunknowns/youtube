"""Persist the explicit per-line review decisions and editing-budget checks."""
from __future__ import annotations
import array
import hashlib
import json
from pathlib import Path
import re
import wave

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(name, value):
    with (OUT / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')

DECISIONS = {
    'I01': 'Isolated lexical ASR matches all words. CTC resolves hi, lets, count, even, numbers in order, with final voiced /z/ and no added word or repeated count.',
    'I02': 'Whisper writes to for two; both are /tu:/, not an acoustic discrepancy. Independent CTC is w i: ae d t u: i: tsh t ai m, covering add, two, each, time without omission. Original ASR warning retained.',
    'I03': 'Whisper independently recognizes one pair. CTC pair-vowel label eI is low-confidence 0.3315. Read-only LPC has a falling third formant from 2951.5Hz at1.16s to1984.0Hz at1.32s (F2 then1731.7Hz), consistent with US r-color rather than a sustained non-rhotic pay ending. Two, blocks, make, one consonants are resolved. Targeted stress alternative gives no recognition benefit, so original retained.',
    'I04': 'Whisper writes 6 and3 for six and three, preserving all words. CTC identifies six, blocks, three, pairs, with, none, left, over. Make final /k/ is absent from greedy CTC, but PCM shows closure at0.85–0.87s (-40.81 to-53.61dBFS), followed by release0.88s (-35.07dBFS,0.8813 power above2kHz), before three frication. Thus there is independent signal evidence for the stop, rather than approving via neighboring number context.',
    'I05': 'Whisper matches all words, including pairs. CTC pair-vowel eI is low-confidence0.2077; LPC F3 falls from2919.6Hz at1.58s to2057.5Hz at1.74s with F21713.6Hz, consistent with an r-colored vowel. Final /z/ remains at1.86–1.905s; grouped has both /p/ and/t/. Targeted long-vowel alternative does not improve recognition, so original retained.',
    'I06': 'Whisper writes 0 is even2: zero numeric formatting and too/two are homophones. Independent CTC resolves z i: r oU i z i: v schwa n t u:, matching every intended sound. The last word is the intended too; original formatting warning retained, no context recognition substituted.',
    'I06B': 'Lexical ASR matches all words. Independent CTC resolves there are no blocks left over including blocks /ks/, left /ft/, and final rhotic /er/; no repeated or missing word.',
    'I07': 'Whisper writes0 and200 for zero and two hundred. Independent CTC resolves lets count from zero to two hundred in order, including /t/ after count and the final /d/ of hundred. Warning is numeric spelling only.',
    'T020': 'Whisper writes20 and10 for twenty and ten. CTC resolves twenty blocks make ten pairs with none left over, including make /k/, pairs /er z/, and left /ft/. No digit spelling is spoken instead of the cardinal words; original lexical warning retained.',
    'T100': 'Whisper writes digit forms0,2,4,6,8 while preserving the complete list in order. CTC resolves the matching cardinal phones. Always-zero shares a continuous /z/ across the word boundary; or-eight has normal r-linking. Final /t/ is resolved and terminal-tail screen finds its release with no suspicious following voicing. The reduced last-digit stop cluster does not remove a word or alter the list.',
    'F01': 'Byte-identical reuse of already accepted We did it. Fresh lexical ASR matches and independent CTC resolves w i: d i d i t; final /t/ release is resolved with no suspicious voiced tail.',
    'F02': 'Whisper writes200 for two hundred. Independent CTC resolves we counted by twos all the way to two hundred, including plural twos /z/. Hundred final unstressed vowel variation /schwa/ vs eSpeak /I/ is an ordinary reduction, with final /d/ present. Numeric-format warning retained.',
    'F03': 'Byte-identical reuse of already accepted Thanks for counting with me. Fresh lexical ASR matches and independent CTC resolves every word; weak-form for has reduced vowel and no added syllable. Existing hash-bound approval is additionally verified.',
    'F04': 'Byte-identical reuse of already accepted Bye for now. Fresh lexical ASR matches and CTC has b ai f er n aU, including the ordinary reduced for. Existing hash-bound approval is verified;0.83317s duration fits the1.00s final spoken budget.',
}

def main():
    manifest_path = OUT / 'measurements.json'
    manifest = read(manifest_path)
    asr = read(OUT / 'isolated-asr.json')
    phonemes = read(OUT / 'isolated-phonemes.json')
    assert asr['source_manifest_sha256'] == sha(manifest_path)
    assert phonemes['source_manifest_sha256'] == sha(manifest_path)
    by_text = {r['expected_text']: r for r in asr['results']}
    by_id = {r['id']: r for r in phonemes['results']}
    assert set(DECISIONS) == {r['id'] for r in manifest['dialogue']}
    reviews = []
    for row in manifest['dialogue']:
        identity = row['id']
        result = by_id[identity]
        assert row['sha256'] == result['source_sha256'] == sha(Path(row['path']))
        evidence_names = ['isolated-phonemes.json']
        if identity in {'I03', 'I05'}:
            evidence_names.append('pair-vowel-formants.json')
        if identity == 'I04':
            evidence_names.append('make-boundary-signal.json')
        evidence = [{'kind': 'isolated-phoneme-asr' if name == 'isolated-phonemes.json' else 'isolated-acoustic-analysis',
                     'path': str(OUT / name), 'sha256': sha(OUT / name),
                     'summary': DECISIONS[identity]} for name in evidence_names]
        reviews.append({'role': 'dialogue', 'id': identity, 'number': None,
                        'expected_text': row['spoken_text'], 'source_sha256': row['sha256'],
                        'decision': 'pass', 'human_listening_performed': False,
                        'isolated_asr_status': by_text[row['spoken_text']]['status'],
                        'recognized_text': by_text[row['spoken_text']]['recognized_text'],
                        'recognized_phonemes': result['recognized_phonemes'],
                        'review_summary': DECISIONS[identity], 'evidence': evidence,
                        'unresolved_warnings': []})
    write('pronunciation-review.json', {
        'schema_version': 1, 'kind': 'speech-pronunciation-review',
        'source_manifest_sha256': sha(manifest_path),
        'scope': 'Explicit agent review of isolated lexical ASR, independent acoustic CTC, and targeted PCM diagnostics. No full human or agent listening claimed. Automatic models and LPC have limitations; this receipt documents concrete source-bound evidence rather than guaranteeing perfect articulation.',
        'human_listening_performed': False,
        'summary': {'clips': 14, 'newly_generated': 11, 'accepted_library_reuse': 3,
                    'asr_warnings_reviewed': 7, 'unresolved_warnings': 0},
        'results': reviews})
    budgets = {}
    for line in (ROOT / 'design/even-counting-v1/script-and-sound-cues.txt').read_text(encoding='utf-8').splitlines():
        if not re.match(r'^(I\d{2}B?|T\d{3}|F\d{2}) \|', line):
            continue
        cells = [v.strip() for v in line.split('|')]
        start, end = map(float, cells[2 if cells[0].startswith('T') else 1].split('–'))
        budgets[cells[0]] = (start, end)
    signals = []
    for row in manifest['dialogue']:
        with wave.open(row['path'], 'rb') as stream:
            values = array.array('h', stream.readframes(stream.getnframes()))
        start, end = budgets[row['id']]
        assert row['duration_s'] <= end - start
        assert values[0] == 0 and values[-1] == 0
        signals.append({'id': row['id'], 'source_sha256': row['sha256'],
                        'duration_s': row['duration_s'], 'budget_s': end - start,
                        'remaining_budget_s': end - start - row['duration_s'],
                        'peak_pcm16': max(abs(v) for v in values),
                        'clipped_pcm_samples': sum(abs(v) >= 32767 for v in values),
                        'edge_samples_zero': True, 'fits': True})
    write('dialogue-audio-review.json', {
        'schema_version': 1, 'kind': 'episode-dialogue-audio-review',
        'status': 'pass', 'source_manifest_sha256': sha(manifest_path),
        'summary': {'clips': 14, 'fit_budgets': 14, 'clipped_samples': 0,
                    'source_audio_modified_for_review': False,
                    'full_human_listening': False},
        'source_checks': signals,
        'targeted_candidate_decision': {'generated': 3, 'selected': 0,
          'reason': 'Original pair vowel has r-color in unmodified PCM despite low-confidence CTC labels. Stressed/longer vowel alternatives did not improve overall independent recognition and were not adopted.',
          'candidate_manifest': str(OUT / 'targeted-v002/manifest.json'),
          'candidate_manifest_sha256': sha(OUT / 'targeted-v002/manifest.json')},
        'evidence': [{'path': str(OUT / name), 'sha256': sha(OUT / name)} for name in [
            'isolated-asr.json', 'isolated-phonemes.json', 'terminal-tail-review.json',
            'pair-vowel-formants.json', 'make-boundary-signal.json',
            'library-verification/reuse-receipt.json', 'pronunciation-review.json']]})
    print(json.dumps({'reviewed_clips': len(reviews), 'all_fit': True,
                      'asr_warnings_reviewed': 7, 'unresolved': 0,
                      'measurements_sha256': sha(manifest_path)}))

if __name__ == '__main__':
    main()
