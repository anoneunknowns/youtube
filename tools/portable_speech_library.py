"""Verify adopted speech and export a new local gate without editing historical evidence.

Old workspace paths describe where a past review ran. Only the exact known
workspace prefix is remapped; checksums, accepted decisions and PCM stay intact.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path, PureWindowsPath
import wave

ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = PureWindowsPath('D:/codex_projects/youtube')


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def resolve_reference(value, root=None):
    root = Path(root) if root is not None else ROOT
    windows = PureWindowsPath(value)
    if windows.is_absolute():
        try:
            relative = windows.relative_to(LEGACY_ROOT)
        except ValueError:
            return Path(value)
        candidate = root.joinpath(*relative.parts).resolve()
        if not candidate.is_relative_to(root.resolve()):
            raise ValueError('Archived speech path escapes this checkout')
        return candidate
    path = Path(value)
    if path.is_absolute():
        return path
    candidate = (root / path).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError('Relative speech reference escapes this checkout')
    return candidate


def export_library(library, destination):
    library = resolve_reference(str(library)).resolve()
    manifest_path, gate_path = library / 'measurements.json', library / 'speech-acceptance.json'
    manifest, gate = read(manifest_path), read(gate_path)
    if (gate.get('kind') != 'hash-bound-speech-acceptance' or gate.get('accepted') is not True
            or gate.get('summary', {}).get('unresolved') != 0
            or gate['inputs']['manifest']['sha256'] != digest(manifest_path)):
        raise ValueError('The source library has no current accepted source-bound gate')
    derived = copy.deepcopy(gate)
    references = {}
    for reference in [value for value in derived['inputs'].values() if value is not None]:
        path = resolve_reference(reference['path'])
        if digest(path) != reference['sha256']:
            raise ValueError(f'Speech gate input changed: {path}')
        reference['path'] = str(path.resolve())
        references[str(path)] = reference['sha256']
    accepted = {}
    for result in derived['results']:
        if result.get('accepted') is not True:
            raise ValueError('The adopted gate contains a rejected source')
        for reference in result.get('pronunciation_evidence', []):
            path = resolve_reference(reference['path'])
            if str(path) not in references:
                if digest(path) != reference['sha256']:
                    raise ValueError(f'Pronunciation proof changed: {path}')
                references[str(path)] = reference['sha256']
            elif references[str(path)] != reference['sha256']:
                raise ValueError('Conflicting proof checksums')
            reference['path'] = str(path.resolve())
        accepted[(result['role'], result.get('number'), result['expected_text'])] = result
    sources = []
    for role, rows in [('number', manifest['numbers']), ('dialogue', manifest['dialogue'])]:
        for row in rows:
            result = accepted[(role, row.get('number'), row['spoken_text'])]
            path = library / row['path']
            checksum = digest(path)
            if checksum != row['sha256'] or checksum != result['sha256']:
                raise ValueError(f'Adopted clip changed: {path}')
            with wave.open(str(path), 'rb') as stream:
                frames, rate = stream.getnframes(), stream.getframerate()
                if (stream.getnchannels(), stream.getsampwidth(), rate) != (1, 2, 24000):
                    raise ValueError(f'Unexpected adopted PCM format: {path}')
                if abs(frames / rate - row['duration_s']) > 1e-8:
                    raise ValueError(f'Wrong adopted source duration: {path}')
            sources.append({'role': role, 'number': row.get('number'), 'spoken_text': row['spoken_text'],
                            'path': path.relative_to(ROOT).as_posix(), 'sha256': checksum,
                            'duration_s': row['duration_s'], 'sample_frames': frames})
    destination = Path(destination).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=False)
    for name, value in [('acceptance.json', derived), ('sources.json', sources)]:
        with (destination / name).open('x', encoding='utf-8') as output:
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.write('\n')
    receipt = {'status': 'pass', 'kind': 'local-path-adaptation-of-existing-speech-acceptance',
               'source_manifest': str(manifest_path), 'source_manifest_sha256': digest(manifest_path),
               'original_gate': str(gate_path), 'original_gate_sha256': digest(gate_path),
               'local_gate': str(destination / 'acceptance.json'), 'local_gate_sha256': digest(destination / 'acceptance.json'),
               'sources_verified': len(sources), 'evidence_files_verified': len(references),
               'new_speech_generated': False, 'new_pronunciation_approval': False,
               'note': 'Only the gate reference paths were adapted to this checkout. Original gate, proof files and audio bytes are unchanged.'}
    with (destination / 'reuse-receipt.json').open('x', encoding='utf-8') as output:
        json.dump(receipt, output, ensure_ascii=False, indent=2)
        output.write('\n')
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', default='assets/library/audio/speech/kokoro-af-heart/v002', type=Path)
    parser.add_argument('--out-dir', required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(export_library(args.library, args.out_dir), indent=2))


if __name__ == '__main__':
    main()
