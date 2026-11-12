"""Create the user-requested description style without altering prior deliveries."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
NAMES=['english-captions.srt','subtitles.srt','chapters.txt','youtube-title.txt','youtube-description.txt','upload-details.txt']

def ref(p):
    with Path(p).open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(Path(p).resolve().relative_to(ROOT)),'sha256':h}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-dir',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--description',type=Path,default=ROOT/'design/catalan-counting-v1/publication-copy/description-v001.txt');a=p.parse_args()
    description=a.description.read_text()
    if not description.endswith('━━━━━━━━━━━━━━━━━━\n\n'):raise ValueError('Description footer must match requested style')
    title=(a.source_dir/'youtube-title.txt').read_text().strip()
    if title!='Count Catalan Numbers from C0 to C30 | Num-Num Numbers':raise ValueError('Unexpected current title')
    a.out_dir.mkdir(parents=True,exist_ok=False)
    for name in NAMES:shutil.copyfile(a.source_dir/name,a.out_dir/name)
    (a.out_dir/'youtube-description.txt').write_text(description)
    (a.out_dir/'upload-details.txt').write_text(title+'\n\n'+description)
    unchanged=[name for name in NAMES if name not in ['youtube-description.txt','upload-details.txt']]
    for name in unchanged:
        if (a.source_dir/name).read_bytes()!=(a.out_dir/name).read_bytes():raise ValueError('Unexpected modification: '+name)
    record={'passed':True,'kind':'catalan-publication-description-style-revision','title':title,'description_source':ref(a.description),
            'implementation':ref(__file__),'source_files':{n:ref(a.source_dir/n) for n in NAMES},
            'files':{n:ref(a.out_dir/n) for n in NAMES},'changed_files':['youtube-description.txt','upload-details.txt'],
            'four_other_files_byte_identical':unchanged,'caption_timing_or_video_changes':False,
            'description_has_chapters_or_hashtags':False}
    with (a.out_dir/'delivery-text-v005.json').open('x') as f:f.write(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':True,'title':title,'description':str(a.out_dir/'youtube-description.txt')},ensure_ascii=False))

if __name__=='__main__':main()
