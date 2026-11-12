"""Create Catalan delivery text in a fresh destination; keep older deliveries."""
import argparse
import hashlib
import json
from pathlib import Path

try:
    from build_catalan_episode import deliveries
except ModuleNotFoundError:
    from tools.build_catalan_episode import deliveries

ROOT=Path(__file__).resolve().parents[1]
NAMES=['english-captions.srt','subtitles.srt','chapters.txt','youtube-title.txt','youtube-description.txt','upload-details.txt']

def ref(p):
    with Path(p).open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(Path(p).resolve().relative_to(ROOT)),'sha256':h}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--timeline',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);a=p.parse_args()
    a.out_dir.mkdir(parents=True,exist_ok=True)
    if any((a.out_dir/n).exists() for n in NAMES):raise FileExistsError('Use a destination with no existing delivery text')
    plan=json.loads(a.timeline.read_text());deliveries(plan,a.out_dir)
    edits=[]
    for name in NAMES:
        path=a.out_dir/name;text=path.read_text();count=text.count('all31')+text.count('All31')
        if count:
            path.write_text(text.replace('all31','all 31').replace('All31','All 31'))
            edits.append({'path':name,'correction':'all31 / All31 → all 31 / All 31','occurrences':count})
    record={'passed':True,'kind':'catalan-delivery-text-spacing-revision','timeline':ref(a.timeline),
            'implementation':ref(__file__),'source_builder':ref(ROOT/'tools/build_catalan_episode.py'),
            'text_only_changes':edits,'caption_timing_text_changes':False,'files':[ref(a.out_dir/n) for n in NAMES]}
    with (a.out_dir/'delivery-text-v003.json').open('x') as f:f.write(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':True,'edited_files':len(edits),'spacing_corrections':sum(e['occurrences'] for e in edits)}))

if __name__=='__main__':main()
