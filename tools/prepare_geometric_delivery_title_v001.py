"""Prepare the requested Count ... from ... to ... title in a fresh delivery."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'output/geometric-sequence-counting-001-v002/delivery-v001'
DEST = SOURCE.parent / 'delivery-title-v001'
DESIGN = ROOT / 'design/geometric-sequence-counting-v1/title-revision-v001'
TITLE = 'Count in a Geometric Sequence from 2 to 24,315,330,918,113,857,602 | Num-Num Numbers'
OLD_TITLE = 'Geometric Sequences: Watch the Formula Work | Multiply by 3 | Num-Num Numbers'
NAMES = ('youtube-title.txt', 'upload-details.txt', 'youtube-description.txt',
         'chapters.txt', 'subtitles.srt', 'english-captions.srt',
         'english-captions.vtt', 'thumbnail.jpg')


def ref(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': digest,
            'bytes': path.stat().st_size}


def main():
    if DEST.exists() or DESIGN.exists():
        raise FileExistsError('Preserve earlier deliveries and revision records')
    record_path = ROOT / 'design/geometric-sequence-counting-v1/production-run-v002.json'
    source_record = ref(record_path)
    record = json.loads(record_path.read_text())
    video_path = ROOT / record['final_video']['path']
    video = ref(video_path)
    assert video['sha256'] == record['final_video']['sha256']
    assert video['sha256'] == '479afec332c2e7371dac941857b1d583223ecefc54084cbbb1d4244007bd7062'
    timeline_path = ROOT / record['timeline']['path']
    assert ref(timeline_path)['sha256'] == record['timeline']['sha256']
    timeline = json.loads(timeline_path.read_text())
    states = timeline['counted_states']
    assert len(states) == 41 and states[0]['value'] == '2'
    assert states[-1]['value'] == '24315330918113857602'
    before = {name: ref(SOURCE / name) for name in NAMES}
    assert (SOURCE / 'youtube-title.txt').read_text().strip() == OLD_TITLE
    description = (SOURCE / 'youtube-description.txt').read_bytes()
    assert (SOURCE / 'upload-details.txt').read_bytes() == OLD_TITLE.encode() + b'\n\n' + description
    DEST.mkdir(parents=True)
    DESIGN.mkdir(parents=True)
    for name in NAMES:
        shutil.copyfile(SOURCE / name, DEST / name)
    (DEST / 'youtube-title.txt').write_text(TITLE + '\n')
    (DEST / 'upload-details.txt').write_bytes(TITLE.encode() + b'\n\n' + description)
    for name in NAMES:
        assert ref(SOURCE / name) == before[name]
        if name not in NAMES[:2]:
            assert (DEST / name).read_bytes() == (SOURCE / name).read_bytes()
    assert (DEST / 'youtube-title.txt').read_text() == TITLE + '\n'
    assert (DEST / 'upload-details.txt').read_bytes() == TITLE.encode() + b'\n\n' + description
    manifest = {
        'schema_version': 1, 'kind': 'geometric-title-style-delivery-revision',
        'passed': True, 'title': TITLE, 'title_characters': len(TITLE),
        'requested_style_example': 'Count in Hexadecimal from 0 to 7F | Num-Num Numbers',
        'changes': list(NAMES[:2]), 'source_video': video,
        'source_timeline': ref(timeline_path), 'source_production_record': source_record,
        'source_delivery_files': before, 'implementation': ref(__file__),
        'files': [ref(DEST / name) for name in NAMES],
        'range': ['2', '24315330918113857602'], 'terms': 41,
        'prior_delivery_preserved': True, 'media_reencoded': False, 'uploaded': False}
    manifest_path = DEST / 'delivery-manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    revision = {
        'schema_version': 1, 'kind': 'geometric-current-delivery-title-revision',
        'status': 'verified-title-metadata',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'title': TITLE, 'source_production': source_record, 'source_video': video,
        'scope': 'Publication title and upload-details title line. Existing film, '
                 'description body, captions, chapters, thumbnail and original QA are preserved.',
        'new_delivery_manifest': ref(manifest_path), 'implementation': ref(__file__),
        'verification': {'passed': True, 'source_delivery_unchanged': True,
                         'unchanged_delivery_file_count': len(NAMES) - 2,
                         'unchanged_delivery_files_byte_identical': True,
                         'range_matches_frozen_timeline': True, 'media_unchanged': True,
                         'new_media_QA_claimed': False},
        'files': [ref(DEST / name) for name in NAMES] + [ref(manifest_path)],
        'uploaded': False}
    (DESIGN / 'record.json').write_text(json.dumps(revision, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': True, 'title': TITLE, 'delivery': str(DEST),
                      'record': ref(DESIGN / 'record.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
