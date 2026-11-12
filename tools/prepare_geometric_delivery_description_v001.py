"""Prepare the requested description format, preserving the approved delivery."""
from datetime import datetime, timezone
from pathlib import Path
import json
import shutil

from prepare_geometric_delivery_title_v001 import ROOT, TITLE, NAMES, ref

SOURCE = ROOT / 'output/geometric-sequence-counting-001-v002/delivery-title-v001'
DEST = SOURCE.parent / 'delivery-description-v001'
DESIGN = ROOT / 'design/geometric-sequence-counting-v1/description-revision-v001'
DESCRIPTION = '''Count in a geometric sequence with our pink rabbit guide.

Starting with 2, follow all 41 terms up to 24,315,330,918,113,857,602, multiplying the previous value by 3 to make each new term. Watch three equal groups make the next term, and see how a result becomes the input for the next step. Put a term number into the formula, compare multipliers of 2 and 3, and explore a separate sequence that gets smaller by half. Pause along the way to follow how the values are generated.

Num-Num Numbers — Paspla Studio
https://pasplastudio.com/num-num-numbers/

━━━━━━━━━━━━━━━━━━

'''


def main():
    if DEST.exists() or DESIGN.exists():
        raise FileExistsError('Preserve earlier delivery and metadata records')
    previous_record_path = ROOT / 'design/geometric-sequence-counting-v1/title-revision-v001/record.json'
    previous = json.loads(previous_record_path.read_text())
    source_manifest = ref(SOURCE / 'delivery-manifest.json')
    assert source_manifest == previous['new_delivery_manifest']
    assert source_manifest['sha256'] == 'b42c08486b0a5a2170e6981eb21c8c714128c33256ebc23aba76ccfdb68a886b'
    video = ref(ROOT / previous['source_video']['path'])
    assert video == previous['source_video']
    timeline = json.loads((ROOT / json.loads((SOURCE / 'delivery-manifest.json').read_text())['source_timeline']['path']).read_text())
    states = timeline['counted_states']
    assert len(states) == 41 and states[0]['value'] == '2'
    assert states[-1]['value'] == str(2 * 3 ** 40) == '24315330918113857602'
    before = {name: ref(SOURCE / name) for name in NAMES}
    assert (SOURCE / 'youtube-title.txt').read_text() == TITLE + '\n'
    assert len(DESCRIPTION.strip().split('\n\n')) == 4
    assert DESCRIPTION.endswith('━━━━━━━━━━━━━━━━━━\n\n')
    DEST.mkdir(parents=True)
    DESIGN.mkdir(parents=True)
    for name in NAMES:
        shutil.copyfile(SOURCE / name, DEST / name)
    (DEST / 'youtube-description.txt').write_text(DESCRIPTION)
    (DEST / 'upload-details.txt').write_text(TITLE + '\n\n' + DESCRIPTION)
    changed = ('youtube-description.txt', 'upload-details.txt')
    for name in NAMES:
        assert ref(SOURCE / name) == before[name]
        if name not in changed:
            assert (DEST / name).read_bytes() == (SOURCE / name).read_bytes()
    assert (DEST / 'upload-details.txt').read_text() == TITLE + '\n\n' + DESCRIPTION
    manifest = {
        'schema_version': 1, 'kind': 'geometric-description-style-delivery-revision',
        'passed': True, 'title': TITLE, 'description': DESCRIPTION,
        'changes': list(changed), 'unchanged_delivery_files': [n for n in NAMES if n not in changed],
        'source_video': video, 'source_delivery_manifest': source_manifest,
        'source_delivery_files': before, 'implementation': ref(__file__),
        'implementation_dependency': ref(ROOT / 'tools/prepare_geometric_delivery_title_v001.py'),
        'files': [ref(DEST / name) for name in NAMES],
        'content_range': ['2', '24315330918113857602'], 'terms': 41,
        'copy_review': 'Independent read-only review of natural English and mathematical/visual facts; '
                       'the opening explicitly treats2 as the starting term and each later multiplication as a new term.',
        'website_link': 'Exact user-specified URL; no website-content claims.',
        'old_deliveries_preserved': True, 'media_reencoded': False, 'uploaded': False}
    manifest_path = DEST / 'delivery-manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    revision = {
        'schema_version': 1, 'kind': 'geometric-current-delivery-description-revision',
        'status': 'verified-description-metadata', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'title': TITLE, 'description': DESCRIPTION, 'source_production': previous['source_production'],
        'source_video': video, 'source_title_revision': ref(previous_record_path),
        'new_delivery_manifest': ref(manifest_path),
        'scope': 'Description and matching upload-details body only; original film/QA and current title preserved.',
        'verification': {'passed': True, 'changed_files': list(changed),
                         'unchanged_delivery_file_count': len(NAMES) - len(changed),
                         'source_delivery_unchanged': True, 'title_unchanged': True,
                         'range_matches_timeline': True, 'media_unchanged': True,
                         'new_media_QA_claimed': False},
        'implementation': ref(__file__),
        'files': [ref(DEST / name) for name in NAMES] + [ref(manifest_path)], 'uploaded': False}
    (DESIGN / 'record.json').write_text(json.dumps(revision, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': True, 'delivery': str(DEST),
                      'record': ref(DESIGN / 'record.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
