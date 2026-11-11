"""Join immutable new-encode waveform/ASR evidence without changing the raw ASR review."""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path('D:/codex_projects/youtube')
OUT = ROOT / 'output/four-base-counting-001-v002-to-200'
REVIEW = OUT / 'encoded-speech-review'
sys.path.insert(0, str(ROOT / 'tools'))
from verify_four_base_audio_v002 import cardinal_value

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(path):
    return json.loads(path.read_text(encoding='utf-8'))

audio = load(OUT / 'four-base-audio-final-qa.json')
asr = load(REVIEW / 'fresh-asr.json')
events = load(REVIEW / 'encoded-events-index.json')
index = {str(Path(row['path']).resolve()).casefold(): row for row in events}
manifest_path = REVIEW / 'encoded-events-manifest.json'
manifest = load(manifest_path)
clipping = load(REVIEW / 'encoded-event-clipping.json')
assert asr['source_manifest_sha256'] == digest(manifest_path)
assert asr['summary']['clips'] == len(index) == len(events) == 215
assert audio['passed'] and clipping['passed']
assert audio['encoded_audio']['sha256'] == manifest['source_video_sha256'] == digest(Path(manifest['source_video']))
assert audio['timeline_sha256'] == manifest['source_timeline_sha256'] == digest(Path(manifest['source_timeline']))
adjustments, unresolved, verified = [], [], []
seen = set()
for row in asr['results']:
    key = str(Path(row['path']).resolve()).casefold()
    assert key not in seen
    seen.add(key)
    event = index[key]
    assert row['source_sha256'] == event['sha256'] == digest(Path(row['path']))
    if event['type'] == 'number_voice':
        numeric_text = re.sub(r'[.!?\s]', '', row['recognized_text'])
        value = int(numeric_text) if numeric_text.isdecimal() else cardinal_value(row['recognized_text'])
        matches = value == event['decimal_value']
    else:
        matches = row['status'] == 'asr-match'
    if not matches:
        unresolved.append({'id': event['id'], **row})
    elif row['status'] != 'asr-match':
        adjustments.append({'id': event['id'], 'expected': event['spoken_text'],
                            'recognized': row['recognized_text'], 'value': event['decimal_value'],
                            'classification': 'Numeric spelling versus Arabic digits; exact same decimal value.',
                            'raw_asr_result_changed': False})
    verified.append({'id': event['id'], 'type': event['type'], 'phase': event['phase'],
                     'expected_text': event['spoken_text'], 'recognized_text': row['recognized_text'],
                     'decimal_value': event['decimal_value'], 'semantic_match': matches})
assert seen == set(index)
evidence = {}
for path in (OUT / 'four-base-audio-final-qa.json', REVIEW / 'fresh-asr.json',
             manifest_path, REVIEW / 'encoded-events-index.json', REVIEW / 'encoded-event-clipping.json',
             REVIEW / 'extraction.json', OUT / 'qa-v002/audio/schedule-guard-regression.json',
             ROOT / 'tools/verify_four_base_audio_v002.py', Path(__file__)):
    evidence[str(path)] = digest(path)
report = {'status': 'PASS' if not unresolved else 'FAIL',
          'scope': 'Fresh full audio review of the completed 0..200 v002 final MP4.',
          'source_video': manifest['source_video'], 'source_video_sha256': manifest['source_video_sha256'],
          'timeline_sha256': audio['timeline_sha256'],
          'waveform_comparison': {key: {k: v for k, v in audio[key].items() if k != 'clips'}
                                  for key in ('master', 'encoded_audio')},
          'schedule': audio['schedule'],
          'fresh_encoded_asr': {'speech_events': len(events), 'count_numbers': 201,
                                'intro_numbers': 1, 'dialogue': 13,
                                'raw_exact_text_or_numeric_matches': asr['summary']['asr_matches'],
                                'raw_warnings': asr['summary']['warnings'],
                                'numeric_representation_only_differences': len(adjustments),
                                'semantic_matches': len(verified) - len(unresolved),
                                'unresolved_mismatches': len(unresolved), 'adjustments': adjustments,
                                'raw_result_modified': False, 'expected_text_used_as_recognition_prompt': False,
                                'source': 'Fresh exact event intervals decoded from new final AAC.',
                                'elapsed_asr_s': asr['summary']['elapsed_s']},
          'clipping': {k: v for k, v in clipping.items() if k != 'clips'},
          'unresolved': unresolved,
          'limitations': ['ASR and waveform checks do not prove flawless articulation.',
                          'No human full-length listening review is claimed.'],
          'verified_speech': verified, 'evidence': evidence}
path = OUT / 'qa-v002/audio/audio-recheck-summary.json'
with path.open('x', encoding='utf-8') as stream:
    json.dump(report, stream, indent=2)
    stream.write('\n')
print(json.dumps({'status': report['status'], 'speech_events': len(events),
                  'semantic_matches': len(verified) - len(unresolved), 'unresolved': len(unresolved),
                  'representation_differences': adjustments, 'report': str(path)}))
assert not unresolved
