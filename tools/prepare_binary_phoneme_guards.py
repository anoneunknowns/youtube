"""Make recognizer-only silence guards to diagnose initial stop CTC omissions.

Production audio is never changed. Each derived WAV records its exact source
hash and sample-for-sample copy relationship after a 200 ms silence prefix.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import wave


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    args.out.mkdir(parents=True, exist_ok=False)
    takes, origins = [], []
    for row in manifest['dialogue']:
        if row['id'] not in {'I02', 'I06', 'I07'}:
            continue
        source = (args.manifest.resolve().parent / row['path']).resolve()
        if sha(source) != row['sha256']:
            raise ValueError('Original audio checksum mismatch')
        with wave.open(str(source), 'rb') as stream:
            if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) != (1, 2, 24000):
                raise ValueError('Unexpected source WAV format')
            raw = stream.readframes(stream.getnframes())
        derived = args.out.resolve() / (row['id'] + '-guard.wav')
        with wave.open(str(derived), 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(24000)
            stream.writeframes(bytes(4800 * 2) + raw + bytes(4800 * 2))
        takes.append(dict(id=row['id'] + '-guard', text=row['spoken_text'], path=str(derived),
                          sha256=sha(derived)))
        origins.append(dict(id=row['id'], original_path=str(source), original_sha256=row['sha256'],
                            derived_path=str(derived), derived_sha256=sha(derived),
                            unchanged_source_pcm=True, prefix_samples=4800, suffix_samples=4800,
                            production_audio_changed=False))
    (args.out / 'takes.json').write_text(json.dumps(takes, indent=2) + '\n', encoding='utf-8')
    (args.out / 'source-mapping.json').write_text(json.dumps(dict(schema_version=1,
        purpose='CTC recognizer boundary sensitivity diagnostic only', records=origins), indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(prepared=len(takes), out=str(args.out))))


if __name__ == '__main__':
    main()
