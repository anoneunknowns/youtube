"""Export measured English captions, chapters and upload copy for Four Ways to Count."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path

if __package__:
    from .export_octal_delivery import SERIES_URL, format_srt
else:
    from export_octal_delivery import SERIES_URL, format_srt

TITLE = 'Four Ways to Count to 127 | Binary, Decimal, Octal & Hexadecimal | Num-Num Numbers'


def count_readings(timeline):
    readings = {}
    for event in sorted(timeline['events'], key=lambda row:row['start_s']):
        if event.get('phase') == 'count' and 'decimal_value' in event and event['type'] != 'sfx':
            if event['decimal_value'] in readings:
                raise ValueError('Each decimal count must have exactly one complete utterance')
            readings[event['decimal_value']] = event
    if list(readings) != list(range(128)):
        raise ValueError('Count speech must cover each value 0–127')
    for value,event in readings.items():
        expected = timeline['numeric_sources'][str(value)]['spoken_text']
        if event.get('text', event.get('token')) != expected:
            raise ValueError(f'Wrong decimal narration for {value}')
    return readings


def caption_rows(timeline):
    events = list(count_readings(timeline).values())
    events += [event for event in timeline['events'] if event['type'] == 'dialogue' or event['id'] == 'I04-TEN']
    rows = []
    for event in events:
        text = event.get('text',event.get('token','')).strip()
        if not text:
            raise ValueError(f'Missing text at {event["id"]}')
        if event.get('phase') == 'count':
            text = text[0].upper()+text[1:]+'.'
        rows.append((event['start_s'],event['end_s'],text))
    rows.sort()
    previous=0
    for start,end,text in rows:
        if not previous<=start<end<=timeline['duration_s'] or '\n' in text or round(start*1000)>=round(end*1000):
            raise ValueError('Invalid or overlapping caption')
        previous=end
    expected = 128 + len(timeline['intro']['dialogue']) + len(timeline['pauses']) + len(timeline['finale']['dialogue'])
    if len(rows)!=expected:
        raise ValueError('Missing or extra caption cue')
    return rows


def chapter_lines(timeline):
    pauses={p['after_decimal_value']:p for p in timeline['pauses']}
    marks=[(0,'One Value, Four Number Systems'),(timeline['counted_states'][0]['estimated_display_start_s'],'Start Counting in Decimal'),
           (pauses[8]['estimated_start_s'],'Eight: A New Octal Place'),(pauses[16]['estimated_start_s'],'Sixteen: A New Hexadecimal Place'),
           (pauses[64]['estimated_start_s'],'Sixty-Four: Binary and Octal Grow'),(timeline['finale']['estimated_start_s'],'Four Ways to Write 127')]
    marks=[(math.floor(t),text) for t,text in marks]
    if any(b-a<10 for a,b in zip([m[0] for m in marks],[m[0] for m in marks][1:]+[timeline['duration_s']])):
        raise ValueError('Each chapter must be at least ten seconds')
    return [f'{t//60:02}:{t%60:02} {text}' for t,text in marks]


def export_metadata(timeline,output_dir,video_filename):
    rows=caption_rows(timeline)
    chapters='\n'.join(chapter_lines(timeline))+'\n'
    description=('Count from zero to 127 in four number systems at once: binary, decimal, octal, and hexadecimal.\n'
                 'Listen to the decimal number while every row shows the same value in a different base. '
                 'Little Bird joins us by the seaside lighthouse as we watch new places appear at eight, sixteen, and sixty-four.\n\n'
                 f'{chapters}\nNum-Num Numbers — Paspla Studio\n{SERIES_URL}\n')
    upload=f'Title\n{TITLE}\n\nDescription\n{description}\nFiles\nVideo: {video_filename}\nCaptions: english-captions.srt (English)\n'
    output_dir.mkdir(parents=True,exist_ok=True)
    for name,text in {'english-captions.srt':format_srt(rows),'chapters.txt':chapters,'upload-details.txt':upload}.items():
        (output_dir/name).write_text(text,encoding='utf-8',newline='\n')
    return {'subtitle_count':len(rows),'counted_values':128,'files':['english-captions.srt','chapters.txt','upload-details.txt']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--timeline',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--video-filename',required=True)
    args=p.parse_args()
    print(json.dumps(export_metadata(json.loads(args.timeline.read_text(encoding='utf-8-sig')),args.output_dir,args.video_filename)))


if __name__=='__main__':main()
