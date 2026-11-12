"""Apply the requested Count ... from ... to ... title to a fresh delivery."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import shutil

from prepare_lucas_delivery_description_v001 import ROOT, NAMES, ref

SOURCE = ROOT / 'output/lucas-counting-001-v001/delivery-description-v001'
TITLE = 'Count Lucas Numbers from 2 to 228,826,127 | Num-Num Numbers'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    dest = args.out_dir.resolve()
    if not dest.is_relative_to(ROOT) or dest.exists():
        raise ValueError('Choose a fresh project-local delivery directory')
    manifest_path = SOURCE / 'delivery-manifest.json'
    source_manifest = ref(manifest_path)
    assert source_manifest['sha256'] == '5cbfd1d8fe2926b51305c1ceb6652c6c6befc077586c6d6fc22b17a9863dbd7b'
    source = json.loads(manifest_path.read_text())
    before = {name: ref(SOURCE / name) for name in NAMES}
    inventory = {row['path']: row for row in source['files']}
    assert all(row == inventory[row['path']] for row in before.values())
    video = ref(ROOT / source['source_video']['path'])
    assert video == source['source_video']
    record = json.loads((ROOT / source['source_production']['path']).read_text())
    timeline_path = ROOT / record['timeline']['path']
    assert ref(timeline_path) == record['timeline']
    states = json.loads(timeline_path.read_text())['counted_states']
    assert (len(states), states[0]['value'], states[-1]['value']) == (41, 2, 228826127)
    description = (SOURCE / 'youtube-description.txt').read_bytes()
    old_title = (SOURCE / 'youtube-title.txt').read_text().strip()
    assert (SOURCE / 'upload-details.txt').read_bytes() == old_title.encode()+b'\n\n'+description
    dest.mkdir(parents=True)
    for name in NAMES:
        shutil.copyfile(SOURCE / name, dest / name)
    (dest / 'youtube-title.txt').write_text(TITLE+'\n')
    (dest / 'upload-details.txt').write_bytes(TITLE.encode()+b'\n\n'+description)
    for name in NAMES:
        assert ref(SOURCE / name) == before[name]
        if name not in ('youtube-title.txt', 'upload-details.txt'):
            assert (dest / name).read_bytes() == (SOURCE / name).read_bytes()
    assert (dest / 'youtube-title.txt').read_text() == TITLE+'\n'
    assert (dest / 'upload-details.txt').read_bytes() == TITLE.encode()+b'\n\n'+description
    assert ref(ROOT / source['source_video']['path']) == video
    result = {
        'schema_version': 1, 'kind': 'lucas-title-style-delivery-revision',
        'passed': True, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'title': TITLE, 'title_characters': len(TITLE),
        'requested_style_example': 'Count in Hexadecimal from 0 to 7F | Num-Num Numbers',
        'changes': ['youtube-title.txt', 'upload-details.txt title line'],
        'unchanged_delivery_files': [n for n in NAMES if n not in ('youtube-title.txt', 'upload-details.txt')],
        'source_video': video, 'source_timeline': ref(timeline_path),
        'source_production': source['source_production'],
        'source_metadata_record': ref(ROOT / 'design/lucas-counting-v1/description-revision-v001/record.json'),
        'source_delivery_manifest': source_manifest, 'source_delivery_files': before,
        'implementation': ref(__file__),
        'implementation_dependency': ref(ROOT / 'tools/prepare_lucas_delivery_description_v001.py'),
        'files': [ref(dest / name) for name in NAMES],
        'range': [2, 228826127], 'terms': 41, 'initial_values': [2, 1],
        'copy_review': 'Independently reviewed natural English and correct endpoints; opening2to1 is explicit in the retained description and film.',
        'prior_delivery_preserved': True, 'media_reencoded': False,
        'new_media_QA_claimed': False, 'uploaded': False}
    with (dest / 'delivery-manifest.json').open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': True, 'title': TITLE, 'delivery': str(dest)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
