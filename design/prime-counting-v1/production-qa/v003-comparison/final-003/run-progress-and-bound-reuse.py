"""Fresh decoded progress QA plus tightly hash-bound unchanged-scope evidence."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from tools import verify_prime_animation_v003 as check

out = Path(__file__).resolve().parent
if (out / 'verification.json').exists():
    raise FileExistsError('Preserve previous completed evidence')
previous_path = ROOT / 'design/prime-counting-v1/production-qa/v003-comparison/final-002/verification.json'
previous = json.loads(previous_path.read_text())
snapshot = previous_path.parent / 'verifier-source.py'
assert check.media.sha(snapshot) == previous['inputs']['verifier']['sha256']
for key in ('movie', 'timeline', 'motion', 'registration', 'old_movie', 'independent_media_helper'):
    assert check.media.sha(check.media.resolve(previous['inputs'][key]['path'])) == previous['inputs'][key]['sha256'], key
for scope in ('actor', 'learning_region', 'aac'):
    assert previous[scope]['passed'], scope

functions = {'SourceArtwork', 'actor_check', 'decision', 'schedule', 'rect'}
constants = {'ACTOR', 'REGIONS', 'CONTINUITY', 'THRESHOLD'}
def fingerprint(path):
    tree = ast.parse(path.read_text())
    nodes = [node for node in tree.body if (
        isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in functions
        or isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in constants for target in node.targets))]
    assert len(nodes) == len(functions) + len(constants)
    return hashlib.sha256(ast.dump(ast.Module(body=nodes, type_ignores=[]), include_attributes=False).encode()).hexdigest()

source = ROOT / 'tools/verify_prime_animation_v003.py'
assert fingerprint(source) == fingerprint(snapshot), 'Actor/continuity implementation changed'
shutil.copyfile(source, out / 'verifier-source.py')
plan = check.media.read(previous['inputs']['timeline']['path'])
movie = check.media.resolve(previous['inputs']['movie']['path'])
assert previous['actor']['frames_checked'] == plan['duration_frames'] == 20590
assert previous['learning_region']['frames_checked'] == plan['duration_frames']
report = {key: deepcopy(previous[key]) for key in ('scope', 'actions', 'source_rig_checks', 'actor', 'learning_region', 'aac')}
report['kind'] = 'independent-prime-v003-decoded-composite-final-qa'
report['inputs'] = deepcopy(previous['inputs'])
report['inputs']['verifier'] = {'path': check.media.local(source), 'sha256': check.media.sha(source)}
report['scope'] += ' Actor/continuity, left learning and AAC results are reused from the same exact movie/inputs after frozen-code AST identity checks; all progress and visible component centering are freshly decoded in this run.'
report['unchanged_scope_evidence_reuse'] = {'path': check.media.local(previous_path), 'sha256': check.media.sha(previous_path),
    'frozen_verifier_path': check.media.local(snapshot), 'frozen_verifier_sha256': check.media.sha(snapshot),
    'actor_functions_and_constants_ast_sha256': fingerprint(source), 'same_critical_actor_code': True,
    'movie_timeline_motion_registration_old_movie_helper_hashes_identical': True,
    'scopes': ['all20590actorframes', 'actual-neutral-to-standing-continuity', 'actual-static-neutral-negative-controls', 'all20590left-learningframes', 'AACpacketpayload-and-PTS/DTS/duration/size'],
    'reason': 'Only progress foreground segmentation changed, to distinguish similarly colored outer frame from real tile components. Actor/learning/AAC code and all media/source inputs are unchanged.'}
for name in ('actual-static-neutral-negative-controls.json', 'actual-decoded-pose-contact.jpg', 'actual-neutral-reference.png', 'decoded-actor-frames.csv'):
    old = previous_path.parent / name
    shutil.copyfile(old, out / name)
report['progress'] = check.progress_check(movie, 'ffmpeg', plan, plan['progress_mosaic'], out)
report['passed'] = all(report[key]['passed'] for key in ('actor', 'progress', 'learning_region', 'aac'))
report['checker_controls'] = {'premature_or_missing_tile': 'design/prime-counting-v1/production-qa/v003-comparison/native-review/checker-development/tile-checker-controls.json',
    'shifted_group_both_axes': 'design/prime-counting-v1/production-qa/v003-comparison/native-review/checker-development/shifted-grid-both-axes-component-filter-control.json'}
check.save(out / 'verification.json', report)
print(json.dumps({'passed': report['passed'], 'progress_frames': report['progress']['frames_checked'], 'centering': report['progress']['native_visible_slot_group_centering'], 'output': check.media.local(out / 'verification.json')}), flush=True)
if not report['passed']:
    raise SystemExit(1)
