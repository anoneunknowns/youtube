"""Create hash-bound binary speech acoustic evidence and explicit review receipts.

This helper writes evidence only; pass/reject decisions are supplied from review
of the independent recognizers, never inferred merely from an ASR match.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import unicodedata

from verify_terminal_tails import METHOD, TARGETS, analyze_samples, read_clip


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--phonemes', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    phonemes = json.loads(args.phonemes.read_text(encoding='utf-8'))
    manifest_hash = digest(manifest_path)
    if phonemes['source_manifest_sha256'] != manifest_hash:
        raise ValueError('Phoneme review belongs to another manifest')
    rows = [dict(row, role=role) for role, group in [('number', 'numbers'), ('dialogue', 'dialogue')]
            for row in manifest[group]]
    by_hash = {row['source_sha256']: row for row in phonemes['results']}
    results, classification = [], []
    for row in rows:
        entry = dict(row, path=str((manifest_path.parent / row['path']).resolve()))
        samples, rate = read_clip(entry)
        recognized = by_hash[row['sha256']]
        if recognized['expected_text'] != row['spoken_text']:
            raise ValueError('Phoneme text mismatch')
        letters = [c for c in recognized['expected_espeak'] if unicodedata.category(c).startswith('L')]
        terminal = letters[-1]
        classified = dict(role=row['role'], number=row.get('number'), id=row['id'],
                          spoken_text=row['spoken_text'], sha256=row['sha256'],
                          terminal_phoneme=terminal, target_voiceless_terminal=terminal in TARGETS)
        classification.append(classified)
        if terminal in TARGETS:
            results.append(dict(classified, **analyze_samples(samples, rate, terminal)))
    candidates = [dict((k, v) for k, v in row.items() if k != 'frame_measurements')
                  for row in results if row['suspicious']]
    report = dict(schema_version=1, kind='read-only-terminal-tail-signal-review',
                  source_manifest=str(manifest_path), source_manifest_sha256=manifest_hash,
                  source_audio_modified=False, screening_only=True, pronunciation_approved=False,
                  method=METHOD, classification_source=dict(path=str(args.phonemes.resolve()),
                  sha256=digest(args.phonemes), method='en-US eSpeak labels computed after independent phoneme recognition'),
                  summary=dict(classified_clips=len(rows), analyzed_voiceless_targets=len(results),
                               suspicious_candidates=len(candidates)), classification=classification,
                  candidates=candidates, results=results)
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(report['summary']))


if __name__ == '__main__':
    main()
