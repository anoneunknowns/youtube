"""Bind isolated ASR, CTC and waveform evidence to per-source review decisions.

Works with any measured schema1 numbers/dialogue manifest, including decoded
AAC clips. Without --decisions it writes an unresolved review worksheet. Approval
requires a separate explicit decision for every exact source hash. A recognizer
match or a phoneme similarity threshold never grants approval by itself.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import wave

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def local(path):
    p = Path(path).resolve()
    return p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else str(p)


def normalize_phones(text):
    return (text.replace('ˈ', '').replace('ˌ', '').replace(' ', '')
            .replace('ᵻ', 'ɪ').replace('ɐ', 'ə').replace('ɚ', 'əɹ')
            .replace('ː', '').replace('ɔɹ', 'oɹ'))


def review(manifest_path, asr_path, phonemes_path, acoustics_path, decisions_path=None):
    manifest, asr, ctc, acoustics = map(read, (manifest_path, asr_path, phonemes_path, acoustics_path))
    binding = sha(manifest_path)
    if manifest.get('measurement_status') != 'measured' or manifest.get('schema_version') != 1:
        raise ValueError('Measured schema1 manifest required')
    for report in (asr, ctc, acoustics):
        if report.get('source_manifest_sha256') != binding:
            raise ValueError('Evidence is not bound to this manifest')
    entries = manifest['numbers'] + manifest['dialogue']
    by_asr, by_ctc = ({r['id']: r for r in report['results']} for report in (asr, ctc))
    by_acoustic = {r['id']: r for r in acoustics['onset_waveform']['results']}
    by_tail = {r['id']: r for r in acoustics['terminal_results']}
    decision_document = read(decisions_path) if decisions_path else {}
    decisions = {r['id']: r for r in decision_document.get('results', [])}
    if any(len(mapping) != len(entries) for mapping in (by_asr, by_ctc, by_acoustic, by_tail)):
        raise ValueError('Independent evidence must cover every unique utterance ID')
    results = []
    for row in entries:
        ident = row['id']
        source = Path(row['path'])
        if not source.is_absolute():
            source = manifest_path.parent / source
        if sha(source) != row['sha256']:
            raise ValueError(f'Changed source {ident}')
        with wave.open(str(source)) as wav:
            if abs(wav.getnframes() / wav.getframerate() - row['duration_s']) > 1 / wav.getframerate():
                raise ValueError(f'Mismeasured WAV {ident}')
        ar, cr, ac, tail = (mapping[ident] for mapping in (by_asr, by_ctc, by_acoustic, by_tail))
        for evidence in (ar, cr, ac, tail):
            if evidence['source_sha256'] != row['sha256']:
                raise ValueError(f'Wrong source hash on independent evidence {ident}')
        if ar['expected_text'] != row['spoken_text'] or cr['expected_text'] != row['spoken_text']:
            raise ValueError(f'Expected text mismatch {ident}')
        expected, recognized = map(normalize_phones, (cr['expected_espeak'], cr['recognized_phonemes']))
        sequence = SequenceMatcher(None, expected, recognized, autojunk=False)
        differences = [{'operation': tag, 'expected': expected[a:b], 'recognized': recognized[c:d]}
                       for tag, a, b, c, d in sequence.get_opcodes() if tag != 'equal']
        flags = []
        if ar['status'] != 'asr-match':
            flags.append('isolated-lexical-ASR-warning')
        if differences:
            flags.append('CTC-phone-differences-to-review')
        if ac['voiced_prefix_warning']:
            flags.append('initial-fricative-screen-warning')
        if tail.get('suspicious'):
            flags.append('terminal-voiced-tail-screen-warning')
        decision = decisions.get(ident, {})
        accepted = (decision.get('accepted') is True and decision.get('source_sha256') == row['sha256']
                    and bool(decision.get('notes')) and not ac['clipped_samples'])
        result = {'id': ident, 'index': row.get('index'), 'number': row.get('number'),
                  'expected_text': row['spoken_text'], 'source_path': local(source),
                  'source_sha256': row['sha256'], 'duration_s': row['duration_s'],
                  'asr_status': ar['status'], 'asr_transcript': ar['recognized_text'],
                  'expected_espeak': cr['expected_espeak'], 'recognized_phonemes': cr['recognized_phonemes'],
                  'phoneme_comparison_not_acceptance_score': sequence.ratio(),
                  'phoneme_differences': differences, 'flags_reviewed': flags,
                  'waveform': {k: ac[k] for k in ('peak_pcm16', 'clipped_samples', 'first_sample', 'last_sample',
                                                 'head_margin_at_minus50db_s', 'tail_margin_at_minus50db_s')},
                  'terminal_target': tail['target_voiceless_terminal'],
                  'accepted': accepted, 'decision': decision.get('decision', 'unresolved'),
                  'notes': decision.get('notes', []), 'human_listening_claim': False,
                  'failures': [] if accepted else ['Explicit hash-bound individual review required']}
        results.append(result)
    unresolved = [r['id'] for r in results if not r['accepted']]
    finished_aac = ('source_video_sha256' in manifest
                    or 'aac' in manifest.get('kind', '').lower()
                    or any('aac' in r.get('cut_from', '').lower() for r in entries))
    inputs = {name: {'path': local(path), 'sha256': sha(path)} for name, path in
              (('manifest', manifest_path), ('isolated_asr', asr_path), ('isolated_phonemes', phonemes_path),
               ('acoustics', acoustics_path))}
    if decisions_path:
        inputs['individual_decisions'] = {'path': local(decisions_path), 'sha256': sha(decisions_path)}
        for i, ref in enumerate(decision_document.get('supporting_evidence', [])):
            path = Path(ref['path'])
            if not path.is_absolute():
                path = ROOT / path
            if sha(path) != ref['sha256']:
                raise ValueError('Supporting review evidence changed')
            inputs[f'supporting_evidence_{i:02}'] = {'path': local(path), 'sha256': sha(path)}
    return {'schema_version': 1, 'kind': 'hash-bound-fibonacci-speech-review',
            'accepted': not unresolved, 'accepted_at_utc': datetime.now(timezone.utc).isoformat() if not unresolved else None,
            'source_manifest_sha256': binding, 'inputs': inputs,
            'scope': ('Finished AAC extracted utterances and their fresh lexical/phoneme/signal evidence. Original-to-final waveform/channel comparison is a separate independent verifier result. No whole-video human listening or perfect-articulation claim.'
                      if finished_aac else 'Selected isolated source WAVs and their fresh lexical/phoneme/signal evidence. No final master/AAC, whole-video listening or perfect-articulation claim.'),
            'policy': {'isolated_ASR_match_alone_approves_pronunciation': False,
                       'phone_similarity_threshold_approves_pronunciation': False,
                       'individual_hash_bound_decision_required': True,
                       'changed_source_requires_fresh_evidence': True},
            'summary': {'clips': len(results), 'numbers': len(manifest['numbers']),
                        'dialogue': len(manifest['dialogue']), 'accepted': len(results) - len(unresolved),
                        'unresolved': len(unresolved),
                        'isolated_asr_warnings_reviewed': sum(r['asr_status'] != 'asr-match' and r['accepted'] for r in results)},
            'unresolved': unresolved, 'results': results,
            'limitations': 'ASR and CTC are fallible; decisions distinguish lexical transcription and ordinary phonetic variation from material speech defects. Automated and agent review evidence does not assert human listening.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest', 'asr', 'phonemes', 'acoustics', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--decisions', type=Path)
    parser.add_argument('--gate', type=Path, help='Also write this accepted gate; unresolved sources are refused')
    args = parser.parse_args()
    for path in (args.out, args.gate):
        if path and path.exists():
            raise FileExistsError(f'Refusing to replace evidence {path}')
    report = review(args.manifest.resolve(), args.asr.resolve(), args.phonemes.resolve(),
                    args.acoustics.resolve(), args.decisions.resolve() if args.decisions else None)
    for target in (args.out, args.gate):
        if target:
            if target == args.gate and not report['accepted']:
                raise ValueError('Unresolved sources cannot be adopted')
            with target.open('x') as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
    print(json.dumps(report['summary']))


if __name__ == '__main__':
    main()
