import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path('D:/codex_projects/youtube')
sys.path.insert(0, str(ROOT / 'tools'))
from verify_four_base_audio_v002 import validate_schedule

timeline = ROOT / 'output/four-base-counting-001-v002-to-200/timeline.json'
original = json.loads(timeline.read_text(encoding='utf-8'))
_, summary = validate_schedule(original)
cases = []

def reject(name, mutation):
    plan = copy.deepcopy(original)
    mutation(plan)
    try:
        validate_schedule(plan)
    except (AssertionError, ValueError, KeyError) as error:
        cases.append({'case': name, 'incorrect_schedule_rejected': True,
                      'error': str(error) or type(error).__name__})
    else:
        raise AssertionError(f'Incorrect schedule accepted: {name}')

def wrong_source(plan):
    replacement = plan['numeric_sources']['199']
    event = next(e for e in plan['events'] if e['id'] == 'N200')
    state = plan['counted_states'][-1]
    event['text'] = state['spoken_text'] = replacement['spoken_text']
    event['source_path'] = state['source_path'] = replacement['path']
    event['source_sha256'] = state['source_sha256'] = replacement['sha256']
    plan['numeric_sources']['200'] = replacement.copy()

reject('200 key mapped consistently to 199 wording/source', wrong_source)
reject('duration below requested eight minutes', lambda p: p.update(duration_s=479.99))
reject('missing terminal counted state 200', lambda p: p['counted_states'].pop())
reject('incorrect canonical hexadecimal endpoint', lambda p: p['counted_states'][-1]['representations'].update(hexadecimal='C7'))
reject('noncanonical leading-zero binary endpoint', lambda p: p['counted_states'][-1]['representations'].update(binary='011001000'))
reject('missing numeric source 200', lambda p: p['numeric_sources'].pop('200'))
reject('display continuity differs by one sample', lambda p: p['counted_states'][100].update(estimated_display_end_s=p['counted_states'][100]['estimated_display_end_s']+1/48000))
reject('final hold shortened by one sample', lambda p: p['counted_states'][-1].update(estimated_display_end_s=p['counted_states'][-1]['estimated_display_end_s']-1/48000))
report = {'status': 'PASS', 'baseline_validates': True, 'schedule_summary': summary,
          'timeline_sha256': hashlib.sha256(timeline.read_bytes()).hexdigest(),
          'validator_sha256': hashlib.sha256((ROOT / 'tools/verify_four_base_audio_v002.py').read_bytes()).hexdigest(),
          'incorrect_schedule_cases_rejected': len(cases), 'cases': cases,
          'production_inputs_modified': False}
path = ROOT / 'output/four-base-counting-001-v002-to-200/qa-v002/audio/schedule-guard-regression.json'
path.parent.mkdir(parents=True, exist_ok=True)
with path.open('x', encoding='utf-8') as stream:
    json.dump(report, stream, indent=2)
    stream.write('\n')
print(json.dumps({'status': 'PASS', 'incorrect_schedules_rejected': len(cases), 'report': str(path)}))
