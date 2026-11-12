"""Prepare the requested title style in a fresh publishing-text delivery."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'output/thue-morse-counting-001-v003/delivery-description-v001'
VIDEO = ROOT/'output/thue-morse-counting-001-v003/delivery-v001/paspla-studio-thue-morse-sequence-0-to-255-1080p.mp4'
TITLE = 'Count Along the Thue–Morse Sequence from Position 0 to 255 | Num-Num Numbers'
NAMES = ('youtube-title.txt', 'youtube-description.txt', 'upload-details.txt',
         'chapters.txt', 'english-captions.srt', 'subtitles.srt', 'english-captions.vtt')


def ref(path):
    path = Path(path)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path':str(path.resolve().relative_to(ROOT)), 'sha256':digest,
            'bytes':path.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    dest = args.out_dir.resolve()
    if not dest.is_relative_to(ROOT) or dest.exists():
        raise ValueError('Choose a fresh project-local delivery directory')
    source_manifest = ref(SOURCE/'delivery-manifest.json')
    if source_manifest['sha256'] != '36e275bc28e32b69adda03c7acb543f12a2ffbabd13d3eb7284fd91d06f23072':
        raise ValueError('The adopted description delivery changed')
    source = json.loads((SOURCE/'delivery-manifest.json').read_text())
    before = {name:ref(SOURCE/name) for name in NAMES}
    accepted = {item['path']:item for item in source['files']}
    for item in before.values():
        assert accepted[item['path']]['sha256'] == item['sha256'], item['path']
    video = ref(VIDEO)
    if video['sha256'] != 'b2beedd5e393ccdad1801815c65c6609b3aa30c609045d8558993fba7aee2a0c':
        raise ValueError('The completed v003 video changed')
    assert source['index_range'] == [0,255] and source['terms'] == 256
    assert source['possible_values'] == [0,1]
    description = (SOURCE/'youtube-description.txt').read_bytes()
    old_title = (SOURCE/'youtube-title.txt').read_text().rstrip('\n')
    assert (SOURCE/'upload-details.txt').read_bytes() == old_title.encode()+b'\n\n'+description
    dest.mkdir(parents=True)
    for name in NAMES:
        shutil.copyfile(SOURCE/name, dest/name)
    (dest/'youtube-title.txt').write_text(TITLE+'\n', encoding='utf-8')
    (dest/'upload-details.txt').write_bytes(TITLE.encode()+b'\n\n'+description)
    changed = ('youtube-title.txt','upload-details.txt')
    for name in NAMES:
        assert ref(SOURCE/name) == before[name], name
        if name not in changed:
            assert (dest/name).read_bytes() == (SOURCE/name).read_bytes(), name
    assert (dest/'youtube-title.txt').read_text() == TITLE+'\n'
    assert (dest/'upload-details.txt').read_bytes() == TITLE.encode()+b'\n\n'+description
    manifest = {
        'schema_version':1, 'kind':'thue-morse-title-style-delivery-revision',
        'status':'pass', 'passed':True, 'title':TITLE,
        'requested_style_example':'Count in Hexadecimal from 0 to 7F | Num-Num Numbers',
        'range_semantics':'0 to255 identifies positions; the sequence values remain0 or1.',
        'changes':list(changed), 'unchanged_delivery_files':[n for n in NAMES if n not in changed],
        'source_video':video, 'source_delivery_manifest':source_manifest,
        'source_delivery_files':before, 'implementation':ref(__file__),
        'files':[ref(dest/name) for name in NAMES],
        'index_range':[0,255], 'terms':256, 'possible_values':[0,1],
        'copy_review':'Independent English/math review supports Count Along and explicit Position range; no implication of values rising to255.',
        'prior_delivery_and_media_preserved':True, 'media_reencoded':False, 'uploaded':False}
    with (dest/'delivery-manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'passed':True, 'title':TITLE, 'delivery':str(dest)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
