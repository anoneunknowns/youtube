"""Record the reviewed, source-specific findings for binary voice version 001.

The observations below were inspected against isolated ASR, phoneme sequences,
and acoustic tail evidence. This is an explicit automated-evidence review and
does not claim human listening. A changed source requires a new review.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / 'assets/library/audio/speech/kokoro-af-heart/binary-v001'
SOURCE_HASHES = {
    'binary-zero': 'a08d0e2e5c6a33aa4a12caa59dd06626c4a62a277b01ab876730bbbe917a234c',
    'binary-one': '58d4ab64f6a90c84474791bfcf868b29f875a971ab633afc3627732f7af1c389',
    'I01': '7cd80ac00ba4afad7fba3dff7dc43ad70ec3ddd193c65b940bfb081e7194641c',
    'I02': 'de20e554e27507e993c93f745d72db38136f5bd639a4319440494a167c6222cc',
    'I03': 'd1d500dce6036889a8805399043aba2b98e90f66b9c2bc482c3dfa7b7a226cf5',
    'I04': 'a26f0aaff537c7ecf0e90a9f36842c36428c340942ed7c816a43c2db67f2a4f6',
    'I05': 'a170be11ae1ea9d2e1be6fd7a1e1ddf9465a1e3b3bef1c2560c711e26bf2725a',
    'I06': '4dadf93feae86cff4be8a3b69cb90db070b775926337ee3a7f8788cb1195919a',
    'I07': 'b5737616a17605e01d80f37e2e59173469ee510edf31210ee32191eeff26242f',
    'I08': 'bdb3d1ad1773623ea98358a88fb4723167b445251e2c994aadad27ffdd59a595',
    'PLACE_READY': 'c27f97d72fa839f7dd5204cd7c7bc4a511c892437177ade0085e340ddddbe266',
    'SEVEN_PLACES': '5b9c84d0c88e7e64b7605faa8548624fbfc2a0fa6166e6e0631e88e1108c9c5b',
    'STRETCH': '70aa62eb89eed9e2a967b6d13f414cf208d14b43bc6cd8c90961d4eb42b030c9',
    'READY': '481731feee83acae7b22bb508fac9c0ff17c2b5575958a0d65e9d5f94a430716',
    'WE_DID_IT': 'f78e95f408a0f08bc7b866d11768c833188076fee0958c55d027742fed417d54',
    'THANKS': '62cb04c29b372d52949d85bce55772ae4e813ff26c118ae6895fd344edc01296',
    'BYE': '1d047d0223f29272d44e838ba325fbf9b94fe014b6b6066bda7164559689b8ab',
}
DECISIONS = {
    'binary-zero': 'Isolated Whisper transcribes 0; independent CTC gives /z i: r ou/. Initial /z/, stressed vowel and final /ou/ are present without an extra appended syllable. Rhotic American zero differs from eSpeak diphthong labels but preserves the word.',
    'binary-one': 'Exact accepted first-episode source reused. Fresh isolated Whisper gives 1 and CTC /w ah n/; word onset, vowel and final nasal are present.',
    'I01': 'Whisper matches every word. Independent phoneme sequence contains hello, number explorers and count in binary without added lexical content.',
    'I02': 'Whisper uses numeral typography for zero and one; warning retained. Independent phonemes confirm both digit words. Raw CTC misses initial /b/ at the input boundary; a recognizer-only 200 ms silence prefix restores /b ai n.../ from identical unchanged source PCM. The voiced uses realization /y u: z iz/ is the normal verb form.',
    'I03': 'Whisper matches. Independent sequence contains read each digit, left and right. Final /t/ is present and separate acoustic tail screening finds no appended voiced-vowel pattern.',
    'I04': 'Whisper writes 1 0 and 2; warning retained rather than applying decimal-number parsing. CTC explicitly contains /w ah n z i: r ou/ in sequence and the complete value-is-two clause. The short says vowel receives a close automatic vowel label; no missing or additional word is indicated.',
    'I05': 'Whisper matches and independent phonemes contain small number, shows and value in the stated order; final value vowel is retained.',
    'I06': 'Whisper matches all words. CTC contains means one, dark means zero; raw initial /b/ boundary omission is resolved by recognizer-only silence guards, which recover /b r ai t/ from identical source PCM.',
    'I07': 'Whisper matches. Independent CTC contains places are not spoken including final /n/. Raw initial /b/ boundary omission is resolved by recognizer-only silence guards recovering /b l ae ng k/ from identical source PCM.',
    'I08': 'Whisper matches the complete sentence. CTC contains example is finished and start at zero; rhotic our, cross-word lateral segmentation and American intervocalic /t/ flapping are consistent with connected speech and do not add a word.',
    'PLACE_READY': 'Whisper and independent phonemes agree on a new place is ready. The final unstressed vowel is retained.',
    'SEVEN_PLACES': 'Whisper and independent phonemes agree on seven places all ones, including plural /z/ in ones. This describes the final seven occupied places.',
    'STRETCH': 'Exact accepted first-episode dialogue reused. Fresh Whisper and phonemes confirm lets stretch including terminal affricate; acoustic tail screening has no suspicious appended voiced tail.',
    'READY': 'Exact accepted first-episode dialogue reused. Fresh Whisper and phoneme sequence confirm ready lets keep going including the final nasal.',
    'WE_DID_IT': 'Exact accepted first-episode dialogue reused. Fresh Whisper and phonemes confirm we did it; terminal /t/ retained, no suspicious appended voiced-tail pattern.',
    'THANKS': 'Exact accepted first-episode dialogue reused. Fresh Whisper matches and CTC confirms thanks, counting and with me; reduced for receives a recognizer vowel/rhoticity variation in connected speech.',
    'BYE': 'Exact accepted first-episode dialogue reused. Fresh Whisper and CTC confirm bye for now with reduced for and intact final /au/.',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    manifest_path = LIB / 'measurements.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    asr = json.loads((LIB / 'isolated-asr.json').read_text(encoding='utf-8'))
    phonemes = json.loads((LIB / 'isolated-phonemes.json').read_text(encoding='utf-8'))
    tails = json.loads((LIB / 'terminal-tail-review.json').read_text(encoding='utf-8'))
    guards = json.loads((LIB / 'guarded-phonemes.json').read_text(encoding='utf-8'))
    manifest_hash = sha(manifest_path)
    if any(report['source_manifest_sha256'] != manifest_hash for report in [asr, phonemes, tails]):
        raise ValueError('Independent evidence manifest mismatch')
    if tails['summary']['suspicious_candidates']:
        raise ValueError('Unreviewed suspicious tail')
    qa = LIB / 'qa'
    qa.mkdir(exist_ok=True)
    mapping = json.loads(Path('D:/temp/binary-ctc-guards-v001/source-mapping.json').read_text(encoding='utf-8'))
    guarded_by_id = {row['id']: row for row in guards['results']}
    for row in mapping['records']:
        expected = SOURCE_HASHES[row['id']]
        if expected != row['original_sha256'] or sha(row['original_path']) != expected:
            raise ValueError('Guard source mismatch')
        if sha(row['derived_path']) != row['derived_sha256']:
            raise ValueError('Guard derivative mismatch')
        result = guarded_by_id[row['id'] + '-guard']
        if not result['recognized_phonemes'].startswith('b ') or result['source_sha256'] != row['derived_sha256']:
            raise ValueError('Initial b guard diagnosis not reproduced')
        destination = qa / Path(row['derived_path']).name
        if destination.exists():
            raise ValueError('Refusing guard overwrite')
        shutil.copyfile(row['derived_path'], destination)
        row['retained_derived_path'] = str(destination)
    write_new(qa / 'guard-source-mapping.json', mapping)
    rows = [dict(row, role=role) for role, group in [('number', 'numbers'), ('dialogue', 'dialogue')]
            for row in manifest[group]]
    if {row['id'] for row in rows} != set(SOURCE_HASHES):
        raise ValueError('Coverage mismatch')
    notes = []
    for row in rows:
        if row['sha256'] != SOURCE_HASHES[row['id']] or sha(LIB / row['path']) != row['sha256']:
            raise ValueError('Source differs from specifically reviewed take')
        notes.append(dict(id=row['id'], source_sha256=row['sha256'], expected_text=row['spoken_text'],
                          decision='pass', reason=DECISIONS[row['id']]))
    notes_path = qa / 'pronunciation-decision-notes.json'
    write_new(notes_path, dict(schema_version=1, kind='source-specific-binary-pronunciation-decisions',
        human_listening_performed=False, remaining_identified_defects=0, decisions=notes,
        limitations='Machine-assisted review of exact source hashes. Independent recognizers have boundary, vowel-label and transcription-format limits; no complete human listening is claimed.'))
    evidence_files = [('isolated-phoneme-asr', LIB / 'isolated-phonemes.json', 'Fresh isolated phoneme sequences for all exact adopted sources; no expected-word prompt during inference.'),
        ('isolated-acoustic-analysis', LIB / 'terminal-tail-review.json', 'All WAV hashes/durations verified; three voiceless endings screened with no suspicious appended voiced tail.'),
        ('isolated-phoneme-asr', notes_path, 'Specific review decisions for each exact source, including ASR numeral typography and CTC initial-stop boundary diagnostics.')]
    results = []
    for row in rows:
        evidence = [dict(kind=kind, path=str(path), sha256=sha(path), summary=summary)
                    for kind, path, summary in evidence_files]
        if row['id'] in {'I02', 'I06', 'I07'}:
            for path, summary in [(LIB / 'guarded-phonemes.json', 'Recognizer-only silence guards recover initial /b/ without altering source PCM.'),
                                  (qa / 'guard-source-mapping.json', 'Exact original and derived hashes document sample-preserving recognizer guard silence and retained diagnostics.')]:
                evidence.append(dict(kind='isolated-phoneme-asr', path=str(path), sha256=sha(path), summary=summary))
        results.append(dict(role=row['role'], number=row.get('number'), expected_text=row['spoken_text'],
            source_sha256=row['sha256'], decision='pass', evidence=evidence,
            review_scope='Machine-assisted isolated speech review; no human-listening claim.'))
    write_new(LIB / 'pronunciation-review.json', dict(schema_version=1, kind='speech-pronunciation-review',
        source_manifest_sha256=manifest_hash, reviewer='Source-specific machine-assisted review of isolated word ASR, independent phonemes, and acoustic evidence.',
        human_listening_performed=False, summary=dict(clips_reviewed=len(rows), remaining_identified_defects=0,
            isolated_asr_formatting_warnings_retained=['I02', 'I04'], ctc_boundary_cases_resolved=['I02', 'I06', 'I07']),
        results=results))
    print(json.dumps(dict(reviewed=len(rows), remaining_identified_defects=0)))


if __name__ == '__main__':
    main()
