"""Prepare the requested Lucas description in a fresh, verified delivery."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'output/lucas-counting-001-v001/render/full-v002'
RECORD = ROOT / 'design/lucas-counting-v1/production-run-v001.json'
NAMES = ('youtube-title.txt', 'youtube-description.txt', 'upload-details.txt',
         'chapters.txt', 'subtitles.srt', 'english-captions.srt')
DESCRIPTION = '''Count Lucas numbers with our meerkat guide inside a sunny clock tower.

Start with 2, then 1, and follow all 41 Lucas numbers through 228,826,127. Watch each new number appear as the previous two values are added, then see the latest pair move into place for the next addition. Explore small groups and place-value carrying as the numbers grow. Pause along the way to compare the inputs with the result and follow the same adding rule.

Num-Num Numbers — Paspla Studio
https://pasplastudio.com/num-num-numbers/

━━━━━━━━━━━━━━━━━━

'''


def ref(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': digest,
            'bytes': path.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', required=True, type=Path)
    args = parser.parse_args()
    dest = args.out_dir.resolve()
    if not dest.is_relative_to(ROOT) or dest.exists():
        raise ValueError('Choose an unused project-local delivery directory')
    record = json.loads(RECORD.read_text())
    video = ref(ROOT / record['video']['path'])
    assert video == record['video']
    inventory = {row['path']: row for row in record['files']}
    before = {name: ref(SOURCE / name) for name in NAMES}
    assert all(row == inventory[row['path']] for row in before.values())
    timeline = json.loads((ROOT / record['timeline']['path']).read_text())
    values = [row['value'] for row in timeline['counted_states']]
    assert len(values) == 41 and values[:2] == [2, 1] and values[-1] == 228826127
    assert all(values[n-2]+values[n-1] == values[n] for n in range(2, 41))
    assert len(DESCRIPTION.strip().split('\n\n')) == 4
    assert DESCRIPTION.endswith('━━━━━━━━━━━━━━━━━━\n\n')
    assert 'https://pasplastudio.com/num-num-numbers/\n' in DESCRIPTION
    title = (SOURCE / 'youtube-title.txt').read_text()
    dest.mkdir(parents=True)
    for name in NAMES:
        shutil.copyfile(SOURCE / name, dest / name)
    (dest / 'youtube-description.txt').write_text(DESCRIPTION)
    (dest / 'upload-details.txt').write_text(title.rstrip('\n')+'\n\n'+DESCRIPTION)
    changes = ['youtube-description.txt', 'upload-details.txt']
    for name in NAMES:
        assert ref(SOURCE / name) == before[name]
        if name not in changes:
            assert (dest / name).read_bytes() == (SOURCE / name).read_bytes()
    assert (dest / 'youtube-description.txt').read_text() == DESCRIPTION
    assert (dest / 'upload-details.txt').read_text() == title.rstrip('\n')+'\n\n'+DESCRIPTION
    assert ref(ROOT / record['video']['path']) == video
    manifest = {
        'schema_version': 1, 'kind': 'lucas-description-style-delivery-revision',
        'passed': True, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'title': title.strip(), 'description': DESCRIPTION, 'changes': changes,
        'unchanged_delivery_files': [name for name in NAMES if name not in changes],
        'source_production': ref(RECORD), 'source_video': video,
        'source_delivery_files': before, 'implementation': ref(__file__),
        'files': [ref(dest / name) for name in NAMES],
        'terms': 41, 'initial_values': [2, 1], 'last_value': 228826127,
        'copy_review': 'Independent natural-English and mathematical/visual fact review by recheck_content; no personal character name is assigned.',
        'website_link': 'Exact user-supplied URL; no website-content claims.',
        'old_deliveries_preserved': True, 'media_reencoded': False,
        'new_media_QA_claimed': False, 'uploaded': False}
    with (dest / 'delivery-manifest.json').open('x') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': True, 'delivery': str(dest),
                      'manifest': ref(dest / 'delivery-manifest.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
