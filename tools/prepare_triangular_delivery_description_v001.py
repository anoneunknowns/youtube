"""Prepare the requested description style in a fresh delivery directory."""
from pathlib import Path
import argparse
import json
import shutil

try:
    from prepare_triangular_delivery_title_v001 import ROOT, TITLE, VIDEO, NAMES, ref
except ModuleNotFoundError:
    from tools.prepare_triangular_delivery_title_v001 import ROOT, TITLE, VIDEO, NAMES, ref

SOURCE = ROOT / 'output/triangular-counting-001-v002/delivery-title-v001'
DESCRIPTION = '''Count triangular numbers with our meerkat guide.

Follow the numbers from 0 to 1,830 as rows of glowing dots build a growing triangle. Watch two matching triangles form a rectangle, then see how choosing one of the two equal groups brings n × (n + 1) ÷ 2 to life. Each new row adds the next whole number. Pause along the way to compare the row number with the total and follow all 61 triangular numbers.

Num-Num Numbers — Paspla Studio
https://pasplastudio.com/num-num-numbers/

━━━━━━━━━━━━━━━━━━

'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    dest = args.out_dir.resolve()
    if not dest.is_relative_to(ROOT) or dest.exists():
        raise ValueError('Use a fresh project-local delivery directory')
    source_manifest = ref(SOURCE / 'delivery-manifest.json')
    if source_manifest['sha256'] != 'c2a68efd3df69a93687d62b152d89c3ebb92a5b3871f2c05db14aa6821645747':
        raise ValueError('The accepted title delivery changed')
    video = ref(VIDEO)
    if video['sha256'] != 'db48a46013d770c87ec85e4d2733827a3f6dfd3882fa453a968692e0672a9e92':
        raise ValueError('The approved media changed')
    before = {name: ref(SOURCE / name) for name in NAMES}
    if (SOURCE / 'youtube-title.txt').read_text() != TITLE + '\n':
        raise ValueError('Unexpected title')
    dest.mkdir(parents=True)
    for name in NAMES:
        shutil.copyfile(SOURCE / name, dest / name)
    (dest / 'youtube-description.txt').write_text(DESCRIPTION)
    (dest / 'upload-details.txt').write_text(TITLE + '\n\n' + DESCRIPTION)
    changed = ('youtube-description.txt', 'upload-details.txt')
    for name in NAMES:
        if name not in changed:
            assert (dest / name).read_bytes() == (SOURCE / name).read_bytes(), name
        assert ref(SOURCE / name) == before[name], name
    assert (dest / 'youtube-description.txt').read_text() == DESCRIPTION
    assert (dest / 'upload-details.txt').read_text() == TITLE + '\n\n' + DESCRIPTION
    assert DESCRIPTION.endswith('━━━━━━━━━━━━━━━━━━\n\n')
    manifest = {
        'schema_version': 1, 'kind': 'triangular-description-style-delivery-revision',
        'passed': True, 'title': TITLE, 'description': DESCRIPTION,
        'changes': list(changed),
        'unchanged_delivery_files': [n for n in NAMES if n not in changed],
        'source_video': video, 'source_delivery_manifest': source_manifest,
        'source_delivery_files': before,
        'implementation': ref(__file__),
        'implementation_dependency': ref(ROOT / 'tools/prepare_triangular_delivery_title_v001.py'),
        'files': [ref(dest / name) for name in NAMES],
        'content_range': [0, 1830], 'terms': 61,
        'copy_review': 'Natural English and mathematical/visual facts independently reviewed by math_plan.',
        'website_link': 'User-specified URL retained exactly; no website-content claims.',
        'old_deliveries_preserved': True, 'media_reencoded': False, 'uploaded': False,
    }
    with (dest / 'delivery-manifest.json').open('x') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': True, 'delivery': str(dest)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
