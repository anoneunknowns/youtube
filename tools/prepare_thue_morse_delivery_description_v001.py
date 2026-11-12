"""Prepare the requested description style without changing completed media."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'output/thue-morse-counting-001-v003/delivery-v001'
PRODUCTION = ROOT/'design/thue-morse-counting-v1/production-run-v003.json'
VIDEO = SOURCE/'paspla-studio-thue-morse-sequence-0-to-255-1080p.mp4'
NAMES = ('youtube-title.txt', 'youtube-description.txt', 'upload-details.txt',
         'chapters.txt', 'english-captions.srt', 'subtitles.srt', 'english-captions.vtt')
DESCRIPTION = '''Explore the Thue–Morse sequence with our Onagadori rooster.

Follow the first 256 values, from positions 0 to 255, as zeros and ones weave a growing pattern. Watch the formula choose each new value, see how copying and swapping create the sequence, and count the ones in a position written in binary to discover another way to find its value. Pause along the way to explore the pattern.

Num-Num Numbers — Paspla Studio
https://pasplastudio.com/num-num-numbers/

━━━━━━━━━━━━━━━━━━

'''


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
    production_ref = ref(PRODUCTION)
    if production_ref['sha256'] != '839a981c0ee43fc50486c9845995b2cb45e76083c3ea03e2289ad7c0c08a602c':
        raise ValueError('The completed v003 production record changed')
    production = json.loads(PRODUCTION.read_text())
    inventory = {item['path']:item for item in production['files']}
    video_ref = ref(VIDEO)
    if video_ref['sha256'] != 'b2beedd5e393ccdad1801815c65c6609b3aa30c609045d8558993fba7aee2a0c':
        raise ValueError('The completed v003 movie changed')
    before = {name:ref(SOURCE/name) for name in NAMES}
    for item in before.values():
        if inventory[item['path']]['sha256'] != item['sha256']:
            raise ValueError('A source delivery file changed: '+item['path'])
    title = (SOURCE/'youtube-title.txt').read_text().rstrip('\n')
    if (SOURCE/'upload-details.txt').read_text() != title+'\n\n'+(SOURCE/'youtube-description.txt').read_text():
        raise ValueError('Unexpected source publishing-text structure')
    timeline = json.loads((ROOT/production['timeline']['path']).read_text())
    states = timeline['counted_states']
    if len(states) != 256 or [s['index'] for s in states] != list(range(256)):
        raise ValueError('The description range differs from the movie')
    if any(s['value'] != (s['index'].bit_count() % 2) for s in states):
        raise ValueError('The description theme differs from the counted values')
    dest.mkdir(parents=True)
    for name in NAMES:
        shutil.copyfile(SOURCE/name, dest/name)
    (dest/'youtube-description.txt').write_text(DESCRIPTION, encoding='utf-8')
    (dest/'upload-details.txt').write_text(title+'\n\n'+DESCRIPTION, encoding='utf-8')
    changed = ('youtube-description.txt','upload-details.txt')
    for name in NAMES:
        assert ref(SOURCE/name) == before[name], name
        if name not in changed:
            assert (dest/name).read_bytes() == (SOURCE/name).read_bytes(), name
    assert (dest/'upload-details.txt').read_text() == title+'\n\n'+DESCRIPTION
    assert DESCRIPTION.endswith('━━━━━━━━━━━━━━━━━━\n\n')
    assert 'CHAPTERS' not in DESCRIPTION and '#' not in DESCRIPTION
    manifest = {
        'schema_version':1, 'kind':'thue-morse-description-style-delivery-revision',
        'status':'pass', 'passed':True, 'title':title, 'description':DESCRIPTION,
        'changes':list(changed), 'unchanged_delivery_files':[n for n in NAMES if n not in changed],
        'source_video':video_ref, 'source_production_record':production_ref,
        'source_delivery_manifest':ref(SOURCE/'delivery-export.json'),
        'source_delivery_files':before, 'implementation':ref(__file__),
        'files':[ref(dest/name) for name in NAMES],
        'index_range':[0,255], 'terms':256, 'possible_values':[0,1],
        'copy_review':'Independent English and mathematical review; identifies Onagadori as the rooster breed and distinguishes positions from values.',
        'website_link':'The user-provided URL is reproduced exactly; no claim about website contents.',
        'chapters':'Retained in a separate unchanged file, omitted from the requested description style.',
        'prior_deliveries_and_media_preserved':True, 'media_reencoded':False, 'uploaded':False}
    with (dest/'delivery-manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'passed':True, 'delivery':str(dest)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
