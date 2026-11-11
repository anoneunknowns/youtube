"""Measure new dialogue and byte-preserving reused lines for this episode."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
import wave

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
LIBRARY = ROOT / 'assets/library/audio/speech/kokoro-af-heart/v002'

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    jobs = read(OUT / 'all-dialogue-jobs.json')
    candidates = {row['id']: row for row in read(OUT / 'candidates-v001/takes.json')}
    old_manifest = read(LIBRARY / 'measurements.json')
    old_gate = read(OUT / 'library-verification/acceptance.json')
    assert old_gate['accepted'] and old_gate['summary']['unresolved'] == 0
    adopted = OUT / 'reused'
    adopted.mkdir(exist_ok=True)
    rows = []
    for job in jobs:
        if job['id'] in candidates:
            take = candidates[job['id']]
            source = Path(take['path'])
            provenance = {'type': 'new-local-kokoro-candidate',
                          'generation': take['generation'], 'trim': take['trim'],
                          'generation_take_record': str(source) + '.json'}
        else:
            take = next(row for row in old_manifest['dialogue'] if row['spoken_text'] == job['text'])
            approval = next(row for row in old_gate['results']
                            if row['role'] == 'dialogue' and row['expected_text'] == job['text'])
            assert approval['accepted'] and approval['sha256'] == take['sha256']
            original = LIBRARY / take['path']
            assert digest(original) == take['sha256']
            source = adopted / (job['id'] + '.wav')
            if source.exists():
                raise ValueError(f'No overwrites: {source}')
            shutil.copyfile(original, source)
            provenance = {'type': 'byte-preserving-accepted-library-reuse',
                          'source_path': str(original),
                          'source_manifest': str(LIBRARY / 'measurements.json'),
                          'source_manifest_sha256': digest(LIBRARY / 'measurements.json'),
                          'verified_local_gate': str(OUT / 'library-verification/acceptance.json'),
                          'verified_local_gate_sha256': digest(OUT / 'library-verification/acceptance.json'),
                          'historical_accepted': True}
        with wave.open(str(source), 'rb') as wav:
            assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 24000)
            frames = wav.getnframes()
        assert digest(source) == take['sha256']
        rows.append({'id': job['id'], 'text': job['text'], 'spoken_text': job['text'],
                     'path': str(source.resolve()), 'sample_frames': frames,
                     'sample_rate': 24000, 'duration_s': frames / 24000,
                     'sha256': digest(source), 'provenance': provenance})
    manifest = {'schema_version': 1, 'measurement_status': 'measured',
                'episode_id': 'even-counting-001', 'sample_rate': 24000,
                'numbers': [], 'dialogue': rows,
                'acceptance_policy': 'Measurement does not approve speech. Use the separately hash-bound speech-acceptance.json gate.'}
    with (OUT / 'measurements.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'manifest': str(OUT / 'measurements.json'),
                      'dialogue': len(rows), 'generated': len(candidates),
                      'reused': len(rows) - len(candidates),
                      'durations': {row['id']: row['duration_s'] for row in rows}}))

if __name__ == '__main__':
    main()
