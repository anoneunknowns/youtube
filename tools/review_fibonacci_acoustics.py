"""Read-only waveform, onset and terminal-tail evidence keyed by utterance ID.

Fibonacci includes zero and two distinct one entries, so the legacy classifier's
positive/unique-number restriction does not apply. Expected phonemes here come
from the independently recognized CTC report's text-only G2P labels.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

try:
    from .review_prime_acoustics import review as onset_review
    from .verify_terminal_tails import read_clip, analyze_samples, TARGETS, METHOD
except ImportError:
    from review_prime_acoustics import review as onset_review
    from verify_terminal_tails import read_clip, analyze_samples, TARGETS, METHOD


def review(manifest_path, phonemes_path):
    manifest = json.loads(manifest_path.read_text())
    ctc = json.loads(phonemes_path.read_text())
    by_id = {r['id']: r for r in ctc['results']}
    onset = onset_review(manifest_path, phonemes_path)
    results = []
    for row in manifest['numbers'] + manifest['dialogue']:
        path = Path(row['path'])
        if not path.is_absolute():
            path = manifest_path.parent / path
        labels = by_id[row['id']]['expected_espeak']
        terminal = ''.join(c for c in labels if c.isalpha())[-1]
        values, rate = read_clip({**row, 'path': str(path)})
        entry = {'id': row['id'], 'source_sha256': row['sha256'],
                 'expected_espeak': labels, 'terminal_phoneme': terminal,
                 'target_voiceless_terminal': terminal in TARGETS}
        if terminal in TARGETS:
            entry.update(analyze_samples(values, rate, terminal))
        results.append(entry)
    return {'schema_version': 1, 'kind': 'fibonacci-source-onset-waveform-and-terminal-screen',
            'source_manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            'source_phonemes_sha256': hashlib.sha256(phonemes_path.read_bytes()).hexdigest(),
            'onset_waveform': onset, 'terminal_method': METHOD, 'terminal_results': results,
            'summary': {**onset['summary'],
                        'terminal_targets': sum(r['target_voiceless_terminal'] for r in results),
                        'terminal_suspicious': sum(r.get('suspicious', False) for r in results)},
            'terminal_warning_ids': [r['id'] for r in results if r.get('suspicious')],
            'pronunciation_approved': False,
            'limitations': 'Heuristic signal evidence requires individual ASR/CTC review; no source modification or full listening is claimed.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--phonemes', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError('Use a new evidence filename')
    report = review(args.manifest.resolve(), args.phonemes.resolve())
    with args.out.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(report['summary']))


if __name__ == '__main__':
    main()
