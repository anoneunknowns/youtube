"""Prepare the requested title style in a fresh delivery, preserving v002."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'output/triangular-counting-001-v002'
TITLE = 'Count Triangular Numbers from 0 to 1,830 | Num-Num Numbers'
OLD_TITLE = 'Triangular Numbers: Watch the Formula Work | 0 to 1,830 | Num-Num Numbers'
VIDEO = SOURCE / 'paspla-studio-triangular-numbers-0-to-1830-1080p-bt709.mp4'
NAMES = ('youtube-title.txt', 'upload-details.txt', 'youtube-description.txt',
         'chapters.txt', 'subtitles.srt', 'english-captions.srt', 'triangular-numbers-en.srt')


def ref(path):
    path = Path(path)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path.resolve().relative_to(ROOT)),
            'sha256': digest, 'bytes': path.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    dest = args.out_dir.resolve()
    if not dest.is_relative_to(ROOT):
        raise ValueError('Use a project-local delivery directory')
    if dest.exists():
        raise FileExistsError('Preserve previous deliveries; choose a fresh destination')
    video = ref(VIDEO)
    if video['sha256'] != 'db48a46013d770c87ec85e4d2733827a3f6dfd3882fa453a968692e0672a9e92':
        raise ValueError('The approved v002 media changed')
    before = {name: ref(SOURCE / name) for name in NAMES}
    if (SOURCE / 'youtube-title.txt').read_text().strip() != OLD_TITLE:
        raise ValueError('Unexpected source title revision')
    description = (SOURCE / 'youtube-description.txt').read_bytes()
    if (SOURCE / 'upload-details.txt').read_bytes() != OLD_TITLE.encode() + b'\n\n' + description:
        raise ValueError('Unexpected upload-details structure')
    timeline = json.loads((SOURCE / 'timeline.json').read_text())
    states = timeline['counted_states']
    if (len(states), states[0]['value'], states[-1]['value']) != (61, 0, 1830):
        raise ValueError('The requested title does not match the adopted range')
    dest.mkdir(parents=True)
    for name in NAMES:
        shutil.copyfile(SOURCE / name, dest / name)
    (dest / 'youtube-title.txt').write_text(TITLE + '\n')
    (dest / 'upload-details.txt').write_bytes(TITLE.encode() + b'\n\n' + description)
    for name in NAMES:
        if name not in ('youtube-title.txt', 'upload-details.txt'):
            assert (dest / name).read_bytes() == (SOURCE / name).read_bytes(), name
        assert ref(SOURCE / name) == before[name], name
    assert (dest / 'youtube-title.txt').read_text() == TITLE + '\n'
    assert (dest / 'upload-details.txt').read_bytes() == TITLE.encode() + b'\n\n' + description
    manifest = {
        'schema_version': 1, 'kind': 'triangular-title-style-delivery-revision',
        'passed': True, 'title': TITLE,
        'requested_style_example': 'Count in Hexadecimal from 0 to 7F | Num-Num Numbers',
        'changes': ['YouTube title', 'upload-details title line'],
        'unchanged_delivery_files': list(NAMES[2:]),
        'source_video': video, 'source_timeline': ref(SOURCE / 'timeline.json'),
        'source_production_record': ref(ROOT / 'design/triangular-counting-v1/production-run-v002.json'),
        'source_delivery_files': before,
        'implementation': ref(__file__),
        'files': [ref(dest / name) for name in NAMES],
        'range': [0, 1830], 'terms': 61,
        'prior_delivery_preserved': True, 'media_reencoded': False, 'uploaded': False,
    }
    with (dest / 'delivery-manifest.json').open('x') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': True, 'title': TITLE, 'delivery': str(dest)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
