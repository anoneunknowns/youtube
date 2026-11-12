"""Independent final-media verification for Powers of2.

No Powers of2 builder, renderer, formatter or motion adapter is imported.
Truth is independently derived with Python integers, inverse cardinal parsing,
separately rasterized glyphs and actual decoded video/audio observations.
"""
from __future__ import annotations

import argparse
from array import array
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import wave

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat, ImageFilter

if __package__:
    from .component_alignment import raster_centering_report
    from . import verify_video as technical
    from .verify_prime_video import decoded_frames
else:
    from component_alignment import raster_centering_report
    import verify_video as technical
    from verify_prime_video import decoded_frames

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT/'design/powers-of-two-counting-v1'
FONT = ROOT/'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
BACKDROP = DESIGN/'generation-batches/powers-of-two-20261112-01a1cd56/source/theatre-clean-plate.png'
FPS, RATE, SIZE = 30, 48000, (1920,1080)
INK, TEAL, MUTED = '#51453f', '#317e79', '#807267'
CHECKPOINTS = (0,3,5,10,20,30,40,60)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def path_of(value):
    value=Path(value)
    return value if value.is_absolute() else ROOT/value


def write_json(path, value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def visual_timeline_signature(plan):
    content={k:plan[k] for k in ('fps','width','height','duration_s','duration_frames','counted_states','teaching','intro','finale')}
    content['voices']=[{k:e.get(k) for k in ('id','text','index','value','start_s','end_s')} for e in plan['voice_events']]
    return hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def sample(at):
    return round(at*RATE)


def frame_at(at):
    return math.ceil(at*FPS-1e-7)


def values():
    powers=tuple(pow(2,n) for n in range(65))
    repeated=[1]
    for _ in range(64): repeated.append(repeated[-1]+repeated[-1])
    require(powers==tuple(repeated),'Integer exponentiation and repeated addition differ')
    require(powers[-1]==18446744073709551616 and sum(powers)==36893488147419103231,
            'Independent integer invariants differ')
    return powers


SMALL='zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
TENS=dict(zip(range(20,100,10),'twenty thirty forty fifty sixty seventy eighty ninety'.split()))
SCALES=((10**18,'quintillion'),(10**15,'quadrillion'),(10**12,'trillion'),(10**9,'billion'),(10**6,'million'),(1000,'thousand'))


def cardinal(n):
    require(isinstance(n,int) and 0<=n<10**21,'Unsupported exact integer cardinal')
    if n<20:return SMALL[n]
    if n<100:return TENS[n//10*10]+('-'+SMALL[n%10] if n%10 else '')
    if n<1000:return SMALL[n//100]+' hundred'+(' '+cardinal(n%100) if n%100 else '')
    for scale,word in SCALES:
        if n>=scale:return cardinal(n//scale)+' '+word+(' '+cardinal(n%scale) if n%scale else '')
    raise AssertionError(n)


def parse_cardinal(text):
    """Strict short-scale inverse; no floats, no text-to-Number conversion."""
    if not isinstance(text,str) or not re.fullmatch('[a-z]+(?:[ -][a-z]+)*',text):return None
    words=text.replace('-',' ').split();small={s:i for i,s in enumerate(SMALL)}
    tens={s:i for i,s in TENS.items()};scales={w:s for s,w in SCALES}
    def group(tokens):
        if not tokens:return 0
        if 'hundred' in tokens:
            if len(tokens)<2 or tokens[1]!='hundred' or tokens.count('hundred')!=1 or not 1<=small.get(tokens[0],-1)<=9:return None
            rest=group(tokens[2:])
            return small[tokens[0]]*100+rest if rest is not None and rest<100 else None
        if len(tokens)==1:return small.get(tokens[0],tens.get(tokens[0]))
        if len(tokens)==2 and tokens[0] in tens and 1<=small.get(tokens[1],-1)<=9:return tens[tokens[0]]+small[tokens[1]]
        return None
    total=0;last_scale=10**21;pending=[]
    for word in words:
        if word in scales:
            scale=scales[word];part=group(pending)
            if scale>=last_scale or part is None or not 1<=part<1000:return None
            total+=part*scale;pending=[];last_scale=scale
        else:pending.append(word)
    tail=group(pending)
    if tail is None:return None
    total+=tail
    return total if cardinal(total).replace('-',' ')==text.replace('-',' ') else None


def checked_design(path=DESIGN/'sequence.json'):
    design=json.loads(Path(path).read_text());truth=values()
    require(design['domain']['index_start']==0 and design['domain']['index_end']==64,'Design range differs')
    require(design['term_count']==65 and design['operation_count']==64,'Wrong term/operation count')
    require(len(design['terms'])==65,'Wrong design term length')
    for n,row in enumerate(design['terms']):
        require(row['index']==n and row['ordinal']==n+1 and row['id']==f'N{n:03}',f'Wrong item identity n{n}')
        require(isinstance(row['value'],str) and row['value']==str(truth[n]),f'Wrong/unexact value n{n}')
        require(row['display_value']==f'{truth[n]:,}',f'Wrong formatted value n{n}')
        require(parse_cardinal(row['english'])==truth[n] and parse_cardinal(row['spoken_text'])==truth[n],f'Wrong cardinal n{n}')
        require(row['previous_value']==(str(truth[n-1]) if n else None),f'Wrong recurrence input n{n}')
        require(row['is_seed']==(n==0),f'Zero exponent seed exception differs n{n}')
        require(row['completed_terms_after_voice']==n+1,f'Progress ordinal differs n{n}')
    require(truth[9]<1000<truth[10] and truth[19]<10**6<truth[20] and truth[59]<10**18<truth[60], 'Threshold explanation indices differ')
    narration=design['narration'];require(len(narration)==78 and len({e['id'] for e in narration})==78,'Narration cue IDs differ')
    return design,truth,{e['id']:e for e in narration}


def validate_schedule(plan,design_path=DESIGN/'sequence.json'):
    design,truth,authored=checked_design(design_path)
    require(plan['fps']==30 and plan['duration_frames']==frame_at(plan['duration_s']),'Incorrect frame grid')
    require(480<=plan['duration_s']<1800,'Long-form duration must be at least8minutes')
    events=sorted(plan.get('voice_events',plan.get('events',[])),key=lambda e:e['start_s'])
    require(len(events)==78 and {e['id'] for e in events}==set(authored),'Measured cue set differs')
    cursor=0
    for event in events:
        start,end=sample(event['start_s']),sample(event['end_s'])
        require(cursor<=start<end<=sample(plan['duration_s']),f'Overlapping/invalid cue {event["id"]}')
        require(start%2==end%2==0,f'Cue is off24kHz source grid {event["id"]}')
        require(event['text']==authored[event['id']]['text'],f'Untracked script change {event["id"]}')
        cursor=end
    counts=[e for e in events if re.fullmatch('N[0-9]{3}',e['id'])]
    require([e['id'] for e in counts]==[f'N{n:03}' for n in range(65)],'Count omitted/reordered')
    states=plan['counted_states'];require(len(states)==65,'Missing count states')
    ordinary=[];extended=[]
    by={e['id']:e for e in events}
    for n,(state,event) in enumerate(zip(states,counts)):
        require(state['index']==n and str(state['value'])==str(truth[n]),f'Wrong state n{n}')
        require(str(event.get('value',truth[n]))==str(truth[n]) and parse_cardinal(event['text'])==truth[n],f'Wrong speech n{n}')
        require(sample(event['start_s']-state['result_start_s'])==sample(.12),f'Wrong result lead n{n}')
        for key in ('voice_start_s','voice_end_s'):
            require(sample(state[key])==sample(event['start_s' if key=='voice_start_s' else 'end_s']),f'Wrong measured state {key} n{n}')
        require(sample(state['progress_commit_s'])==sample(event['end_s']),f'Premature/late progress n{n}')
        if n:
            require(str(state['previous_value'])==str(truth[n-1]),f'Wrong previous input n{n}')
            require(state['operation_start_s']<state['operation_end_s']<=state['result_start_s']+1/RATE,f'Operation overlaps result n{n}')
        if n<64:
            following=counts[n+1]
            if n in CHECKPOINTS:
                lesson=by[f'X{n:03}']
                require(sample(lesson['start_s']-event['end_s'])==sample(.3),f'Explanation entrance differs n{n}')
                require(sample(following['start_s']-lesson['end_s'])==sample(2),f'Explanation settle differs n{n}')
                extended.append(n)
            else:
                require(sample(following['start_s']-event['end_s'])==sample(2),f'Normal2s count gap differs n{n}')
                ordinary.append(n)
    require(len(ordinary)==56 and tuple(extended)==CHECKPOINTS,'Boundary coverage differs')
    return events,states,{'passed':True,'independent_truth':'integer exponentiation, repeated addition, geometric-series sum, strict inverse English short-scale parsing',
        'terms':65,'operations':64,'zero_exponent_seed_value':'1','endpoint':str(truth[-1]),'sum':str(sum(truth)),
        'normal_two_second_boundaries':ordinary,'explanation_boundaries':extended,
        'digit_rollovers':[n for n in range(1,65) if len(str(truth[n]))>len(str(truth[n-1]))],
        'max_decimal_digits':20,'voice_events':len(events),'speech_duration_s':sum(e['end_s']-e['start_s'] for e in events)}


def source_acceptance(plan,events):
    require(plan.get('speech_adopted') is True,'Speech not adopted')
    dependency=plan.get('speech_acceptance');require(dependency and dependency.get('path') and dependency.get('sha256'),'No hash-bound speech gate')
    path=path_of(dependency['path']);require(sha(path)==dependency['sha256'],'Speech gate changed')
    gate=json.loads(path.read_text());require(gate.get('accepted') and not gate.get('unresolved'),'Unresolved speech acceptance')
    rows={r['id']:r for r in gate['results']};require(set(rows)=={e['id'] for e in events},'Speech gate omits cues')
    for event in events:
        row=rows[event['id']]
        require(row.get('accepted') and not row.get('failures') and row.get('source_sha256')==event['source_sha256'],f'Unaccepted/wrong source {event["id"]}')
    return {'passed':True,'path':str(path),'sha256':sha(path),'cues':len(rows),'scope':'Existing hash-bound acceptance decisions inspected. No new ASR/CTC run by this verifier.'}


def pcm16(data):
    out=array('h');out.frombytes(data)
    if sys.byteorder!='little':out.byteswap()
    return out


def waveform(reference,actual,guard=8,stride=16):
    ref=reference[::stride];energy=sum(x*x for x in ref);best=(-1,0,0)
    for lag in range(-guard,guard+1):
        observed=actual[guard+lag:guard+lag+len(reference):stride]
        if len(observed)!=len(ref):continue
        power=sum(x*x for x in observed)
        if energy and power:
            correlation=sum(a*b for a,b in zip(ref,observed))/math.sqrt(energy*power)
            if correlation>best[0]:best=correlation,lag,10*math.log10(power/energy)
    return best


def audio_checks(plan,events,video,master,ffmpeg,directory):
    directory.mkdir(parents=True,exist_ok=False);reports=[];references={}
    with tempfile.TemporaryDirectory(prefix='powers2-independent-audio-') as temp:
        temp=Path(temp)
        for event in events:
            source=path_of(event['source_path']);require(sha(source)==event['source_sha256'],f'Source changed {event["id"]}')
            if source not in references:
                dest=temp/f'source-{len(references):03}.wav'
                subprocess.run([str(ffmpeg),'-nostdin','-v','error','-xerror','-n','-i',str(source),'-ar',str(RATE),'-ac','1','-c:a','pcm_s16le',str(dest)],check=True)
                with wave.open(str(dest),'rb') as w:references[source]=pcm16(w.readframes(w.getnframes()))
        for name,path,lossy in [('master',master,False),('final-aac',video,True)]:
            dest=temp/(name+'.wav')
            subprocess.run([str(ffmpeg),'-nostdin','-v','error','-xerror','-n','-i',str(path),'-map','0:a:0','-ar',str(RATE),'-ac','2','-c:a','pcm_s16le',str(dest)],check=True)
            rows=[];silence=[];cursor=0;guard=sample(.03 if lossy else .002)
            with wave.open(str(dest),'rb') as track:
                require(abs(track.getnframes()-sample(plan['duration_s']))<=(2048 if lossy else 2),f'{name} duration differs')
                for event in events:
                    start,end=sample(event['start_s']),sample(event['end_s']);reference=references[path_of(event['source_path'])]
                    require(abs(len(reference)-(end-start))<=2,f'Source/time length differs {event["id"]}')
                    a,b=cursor+(guard if cursor else 0),start-guard
                    if b>a:
                        track.setpos(a);peak=max(map(abs,pcm16(track.readframes(b-a))),default=0)
                        silence.append({'start_s':a/RATE,'end_s':b/RATE,'peak_pcm16':peak})
                    track.setpos(max(0,start-8));observed=pcm16(track.readframes(len(reference)+16))
                    matches=[waveform(reference,observed[channel::2]) for channel in (0,1)]
                    mapping=plan.get('audio',{}).get('channel_mapping_gain_db',-10*math.log10(2))
                    gain=event.get('mix_gain_db',0)+plan.get('master',{}).get('common_gain_db',plan.get('common_gain_db',0))+mapping
                    require(min(m[0] for m in matches)>=.97,f'{name} waveform differs {event["id"]}: {matches}')
                    require(all(abs(m[2]-gain)<=(.35 if lossy else .05) for m in matches),f'{name} gain differs {event["id"]}: {matches}, expected{gain}')
                    rows.append({'id':event['id'],'source_sha256':event['source_sha256'],'left_correlation':matches[0][0],'right_correlation':matches[1][0],
                        'left_lag_samples':matches[0][1],'right_lag_samples':matches[1][1],'left_gain_db':matches[0][2],'right_gain_db':matches[1][2],'expected_gain_db':gain,'mono_to_stereo_channel_mapping_gain_db':mapping})
                    cursor=end
                if cursor+guard<track.getnframes():
                    track.setpos(cursor+guard);silence.append({'start_s':(cursor+guard)/RATE,'end_s':track.getnframes()/RATE,'peak_pcm16':max(map(abs,pcm16(track.readframes(track.getnframes()))),default=0)})
            require(max((s['peak_pcm16'] for s in silence),default=0)<=(3 if lossy else 1),f'Unexpected {name} audio outside speech')
            report={'passed':True,'track':name,'sha256':sha(path),'events':rows,'silence_intervals':silence,'boundary_guard_s':guard/RATE,'lag_search_samples':[-8,8],'waveform_stride':16}
            write_json(directory/(name+'.json'),report);reports.append(report)
    return {'passed':True,'tracks':reports,'scope':'All78source hashes, source→master/finalAAC correlations in both channels, declared gains, guarded silent intervals. Waveform match does not detect source pronunciation errors.'}


def subtitle_checks(events,paths):
    require(paths,'Missing delivered SRT');records=[]
    def seconds(text):
        h,m,tail=text.split(':');s,ms=tail.split(',');return int(h)*3600+int(m)*60+int(s)+int(ms)/1000
    for path in paths:
        blocks=path.read_text(encoding='utf-8-sig').strip().split('\n\n');require(len(blocks)==len(events),'Subtitle cue count differs')
        for ordinal,(block,event) in enumerate(zip(blocks,events),1):
            lines=block.splitlines();require(lines[0]==str(ordinal),'Subtitle ordinal differs')
            start,end=map(seconds,lines[1].split(' --> '))
            require(abs(start-event['start_s'])<=.000501 and abs(end-event['end_s'])<=.000501,f'Subtitle time differs {event["id"]}')
            require(' '.join(lines[2:])==event.get('subtitle_text',event['text']),f'Subtitle text differs {event["id"]}')
        records.append({'path':str(path),'sha256':sha(path),'cues':len(events)})
    return {'passed':True,'files':records}


def native_sample_indices(plan,events,states):
    count=plan['duration_frames'];reasons=defaultdict(set)
    def add(at,why):
        k=frame_at(at)
        for offset in (-1,0,1):
            if 0<=k+offset<count:reasons[k+offset].add(why)
    for event in events:
        for key in ('start_s','end_s'):add(event[key],event['id']+'/'+key)
        add((event['start_s']+event['end_s'])/2,event['id']+'/midpoint')
    for s in states:
        for key in ('cycle_start_s','operation_start_s','operation_end_s','result_start_s','progress_commit_s'):
            if key in s and s[key] is not None:add(s[key],f'n{s["index"]}/{key}')
        if s['index']:
            a,b=s['operation_start_s'],s['operation_end_s']
            for fraction in (.25,.5,.75):add(a+(b-a)*fraction,f'n{s["index"]}/operation{fraction}')
    for k in list(range(min(32,count)))+list(range(max(0,count-62),count)):reasons[k].add('fade')
    return sorted(reasons),reasons


def independent_scene(plan,events,states,at):
    """Scene/commit/progress truth derived from measured speech boundaries."""
    by={e['id']:e for e in events}
    progress=sum(e['id'].startswith('N') and e['end_s']<=at+1e-9 for e in events)
    if at<states[0]['result_start_s']:
        return {'mode':'intro','index':None,'progress':progress,'committed':False}
    # As-rendered nonnumeric teaching/outro views cut at spoken cue onset.
    # Numeric result reveals retain the separate exact−.12s contract.
    outro=by['O001']['start_s']
    if at>=outro:
        return {'mode':'outro','index':64,'progress':progress,'committed':True}
    n=max(0,bisect_right([s['cycle_start_s'] for s in states],at+1e-9)-1)
    lesson=by.get(f'X{n:03}')
    mode='teaching' if lesson and lesson['start_s']<=at<lesson['end_s'] else 'count'
    start,end=states[n]['operation_start_s'],states[n]['operation_end_s']
    phase=None if not n else min(1,max(0,(round(at*FPS)-frame_at(start))/(frame_at(end)-frame_at(start))))
    return {'mode':mode,'index':n,'progress':progress,'committed':at>=states[n]['result_start_s']-1e-9,'operation_fraction':phase}


def delivery_checks(plan,events,directory):
    records=[]
    for name in ('chapters.txt','youtube-title.txt','youtube-description.txt','upload-details.txt'):
        path=directory/name;require(path.is_file(),f'Missing delivery file{name}')
        records.append({'path':str(path),'sha256':sha(path)})
    title=(directory/'youtube-title.txt').read_text();description=(directory/'youtube-description.txt').read_text()
    require('Powers of 2' in title and '2⁰' in title and '2⁶⁴' in title,'Title range differs')
    require('18,446,744,073,709,551,616' in description and '65' in description,'Description endpoint/count differs')
    require('32' in description and '64' in description and 'short scale' in description,'Description misses visual-mode/English-scale contract')
    lines=(directory/'chapters.txt').read_text().strip().splitlines();require(len(lines)==10,'Wrong chapter count')
    times=[]
    for line in lines:
        stamp=line.split(' ',1)[0];parts=list(map(int,stamp.split(':')))
        require(len(parts) in (2,3),'Malformed chapter stamp')
        time_value=sum(v*60**i for i,v in enumerate(reversed(parts)));times.append(time_value)
    states=plan['counted_states'];expected=[0,states[0]['result_start_s'],states[6]['cycle_start_s']]+[states[n]['result_start_s'] for n in (10,20,30,40,50,60,64)]
    require(all(abs(a-b)<1.001 for a,b in zip(times,expected)),'Chapter stamps differ from measured timeline')
    require(times==sorted(set(times)) and times[-1]<plan['duration_s'],'Chapters unordered/outside duration')
    return {'passed':True,'files':records,'chapters':len(lines),'chapter_timing_tolerance_s':1.001}


@lru_cache(maxsize=48)
def font(size):
    return ImageFont.truetype(str(FONT),size)


@lru_cache(maxsize=2048)
def glyph_alpha(text,size,spacing=12):
    if '\n' in text:
        lines=[glyph_alpha(line,size,spacing) for line in text.split('\n')]
        boxes=[im.point(lambda a:255 if a>=128 else 0).getbbox() for im in lines]
        width=max(b[2]-b[0] for b in boxes);height=sum(b[3]-b[1] for b in boxes)+spacing*(len(lines)-1)
        out=Image.new('L',(width+80,height+80));y=40
        for im,b in zip(lines,boxes):
            out.paste(im.crop(b),(40+round((width-b[2]+b[0])/2),y));y+=b[3]-b[1]+spacing
        return out
    face=font(size);b=face.getbbox(text)
    out=Image.new('L',(b[2]-b[0]+80,b[3]-b[1]+80))
    ImageDraw.Draw(out).text((40-b[0],40-b[1]),text,font=face,fill=255)
    return out


def rgb(value):
    return tuple(bytes.fromhex(value.lstrip('#'))) if isinstance(value,str) else tuple(value)


def color_mask(image,color,tolerance=42):
    target=rgb(color)
    channels=[channel.point(lambda v,t=t:255 if abs(v-t)<=tolerance else 0) for channel,t in zip(image.split()[:3],target)]
    return ImageChops.darker(ImageChops.darker(channels[0],channels[1]),channels[2])


@lru_cache(maxsize=4)
def backdrop(divisor=1):
    image=Image.open(BACKDROP).convert('RGB');target=16/9
    if image.width/image.height>target:
        width=round(image.height*target);left=(image.width-width)//2;image=image.crop((left,0,left+width,image.height))
    else:
        height=round(image.width/target);top=(image.height-height)//2;image=image.crop((0,top,image.width,top+height))
    return image.resize((SIZE[0]//divisor,SIZE[1]//divisor),Image.Resampling.LANCZOS)


def iou(a,b):
    union=ImageChops.lighter(a,b).histogram()[255]
    return ImageChops.darker(a,b).histogram()[255]/union if union else 0.


def observed_ink(image,area,colors,fill=None,divisor=1):
    scaled=tuple(v//divisor for v in area);crop=image.crop(scaled).convert('RGB')
    plate=Image.new('RGB',crop.size,fill) if fill else backdrop(divisor).crop(scaled)
    difference=ImageChops.difference(crop,plate).split()
    changed=ImageChops.lighter(ImageChops.lighter(difference[0],difference[1]),difference[2]).point(lambda v:255 if v>=24 else 0)
    result=Image.new('L',crop.size)
    for color in colors:
        fg=rgb(color);channel=max(range(3),key=lambda k:abs(ImageStat.Stat(plate).mean[k]-fg[k]))
        observed=crop.getchannel(channel);base=plate.getchannel(channel);midpoint=base.point(lambda v,t=fg[channel]:(v+t)//2)
        half=ImageChops.subtract(observed,midpoint).point(lambda v:255 if v==0 else 0) if ImageStat.Stat(base).mean[0]>=fg[channel] else ImageChops.subtract(midpoint,observed).point(lambda v:255 if v==0 else 0)
        result=ImageChops.lighter(result,ImageChops.darker(half,color_mask(crop,fg,105)))
    return ImageChops.darker(result,changed)


@lru_cache(maxsize=4096)
def expected_geometry(text,size,box,spacing=12):
    alpha=glyph_alpha(text,size,spacing);b=alpha.point(lambda a:255 if a>=128 else 0).getbbox();require(b,'Empty expected glyph')
    xy=(round((box[0]+box[2]-b[0]-b[2])/2),round((box[1]+box[3]-b[1]-b[3])/2))
    return alpha,xy,(b[0]+xy[0],b[1]+xy[1],b[2]+xy[0],b[3]+xy[1])


@lru_cache(maxsize=256)
def power_geometry(exponent,size,box,exponent_size=39):
    """Independently typeset the agreed raised exponent from visible glyphs."""
    base=glyph_alpha('2',size);raised=glyph_alpha(str(exponent),exponent_size)
    bb=base.point(lambda a:255 if a>=128 else 0).getbbox();eb=raised.point(lambda a:255 if a>=128 else 0).getbbox()
    width=bb[2]-bb[0]+9+eb[2]-eb[0];height=max(50+bb[3]-bb[1],20+eb[3]-eb[1])
    alpha=Image.new('L',(width+80,height+80))
    alpha.paste(base.crop(bb),(40,90));alpha.paste(raised.crop(eb),(40+bb[2]-bb[0]+9,60))
    b=alpha.point(lambda a:255 if a>=128 else 0).getbbox()
    xy=(round((box[0]+box[2]-b[0]-b[2])/2),round((box[1]+box[3]-b[1]-b[3])/2))
    parts=[{'role':'base','text':'2','font_size':size,'box':[xy[0]+40,xy[1]+90,xy[0]+40+bb[2]-bb[0],xy[1]+90+bb[3]-bb[1]]},
           {'role':'exponent','text':str(exponent),'font_size':exponent_size,'box':[xy[0]+40+bb[2]-bb[0]+9,xy[1]+60,xy[0]+40+bb[2]-bb[0]+9+eb[2]-eb[0],xy[1]+60+eb[3]-eb[1]]}]
    return alpha,xy,(b[0]+xy[0],b[1]+xy[1],b[2]+xy[0],b[3]+xy[1]),parts


def inspect_label(image,row,frame,divisor=1,alignment=True):
    if row.get('kind')=='related-copies':return inspect_related_copies(image,row,frame,divisor,alignment)
    text,size,box=row['text'],row['size'],tuple(row['box'])
    power_parts=None
    if row.get('kind')=='power':alpha,xy,bounds,power_parts=power_geometry(row['exponent'],size,box,row.get('exponent_size',39))
    else:alpha,xy,bounds=expected_geometry(text,size,box,row.get('spacing',12))
    # Six native pixels retain a measurement guard without admitting the
    # adjacent pending label above the early-operation glyph group.
    guard=row.get('observation_guard_px',6)
    area=(max(0,(bounds[0]-guard)//divisor*divisor),max(0,(bounds[1]-guard)//divisor*divisor),min(1920,math.ceil((bounds[2]+guard)/divisor)*divisor),min(1080,math.ceil((bounds[3]+guard)/divisor)*divisor))
    expected=Image.new('L',(area[2]-area[0],area[3]-area[1]));expected.paste(alpha,(xy[0]-area[0],xy[1]-area[1]))
    native_expected=expected
    if divisor!=1:expected=expected.resize((expected.width//divisor,expected.height//divisor),Image.Resampling.BOX)
    expected=expected.point(lambda a:255 if a>=128 else 0)
    actual=observed_ink(image,area,row.get('colors',(INK,TEAL,MUTED)),row.get('fill'),divisor)
    score=iou(actual,expected);minimum=.92 if divisor==1 else .82
    matching_shift=(0,0)
    if score<minimum:
        # Nested visible-glyph group assembly can select either half-pixel
        # rounding direction. Identify the glyph within one native pixel,
        # while measuring actual placement against the content box separately.
        # This never increases the decoded1px alignment acceptance tolerance.
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                if dx==dy==0:continue
                shifted=ImageChops.offset(native_expected,dx,dy)
                if divisor!=1:shifted=shifted.resize((shifted.width//divisor,shifted.height//divisor),Image.Resampling.BOX)
                shifted=shifted.point(lambda a:255 if a>=128 else 0);candidate=iou(actual,shifted)
                if candidate>score:score=candidate;expected=shifted;matching_shift=(dx,dy)
    result={'frame':frame,'component_id':row['name'],'text':text,'font_size_px':size,'content_box':list(box),'observation_box':list(area),'divisor':divisor,'glyph_iou':score,'minimum_glyph_iou':minimum,'passed':bool(actual.getbbox()) and score>=minimum}
    result['glyph_identity_registration_translation_native_px']=list(matching_shift)
    if divisor==1 and alignment:
        try: result['alignment']=raster_centering_report(actual,box,origin_xy=area[:2],name=f'{frame}/{row["name"]}',tolerance_px=1)
        except ValueError as exc: result['alignment']={'passed':False,'error':str(exc)}
        result['passed'] &= result['alignment']['passed']
    if divisor==1 and power_parts:
        checks=[]
        for part in power_parts:
            b=part['box'];local=(b[0]+matching_shift[0]-area[0]-1,b[1]+matching_shift[1]-area[1]-1,b[2]+matching_shift[0]-area[0]+1,b[3]+matching_shift[1]-area[1]+1)
            part_iou=iou(actual.crop(local),expected.crop(local))
            face=font(part['font_size']);fb=face.getbbox(part['text']);core=glyph_alpha(part['text'],part['font_size']).point(lambda a:255 if a>=128 else 0).getbbox()
            origin=(b[0]-core[0]+40-fb[0]+matching_shift[0],b[1]-core[1]+40-fb[1]+matching_shift[1]);digits=[]
            for k,ch in enumerate(part['text']):
                if not ch.isdigit():continue
                cb=face.getbbox(ch);advance=face.getlength(part['text'][:k]);crop=(math.floor(origin[0]+advance+cb[0]-1)-area[0],math.floor(origin[1]+cb[1]-1)-area[1],math.ceil(origin[0]+advance+cb[2]+1)-area[0],math.ceil(origin[1]+cb[3]+1)-area[1]);value=iou(actual.crop(crop),expected.crop(crop))
                digits.append({'position':k,'digit':ch,'glyph_iou':value,'passed':value>=.88})
            checks.append({'role':part['role'],'text':part['text'],'box':part['box'],'glyph_iou':part_iou,'digits':digits,'passed':part_iou>=.88 and all(d['passed'] for d in digits)})
        result['power_parts']=checks;result['passed'] &= all(r['passed'] for r in checks)
    elif divisor==1 and '\n' not in text:
        face=font(size);fb=face.getbbox(text);origin=(xy[0]+40-fb[0]+matching_shift[0],xy[1]+40-fb[1]+matching_shift[1]);digits=[]
        for position,ch in enumerate(text):
            if not ch.isdigit():continue
            b=face.getbbox(ch);advance=face.getlength(text[:position])
            crop=(math.floor(origin[0]+advance+b[0]-1)-area[0],math.floor(origin[1]+b[1]-1)-area[1],math.ceil(origin[0]+advance+b[2]+1)-area[0],math.ceil(origin[1]+b[3]+1)-area[1])
            digit_iou=iou(actual.crop(crop),expected.crop(crop));digits.append({'position':position,'digit':ch,'glyph_iou':digit_iou,'passed':digit_iou>=.88})
        result['digits']=digits;result['passed'] &= all(d['passed'] for d in digits)
    return result


def inspect_related_copies(image,row,frame,divisor=1,alignment=True):
    parts=[(r,expected_geometry(r['text'],r['size'],tuple(r['box']))) for r in row['members']]
    bounds=(min(g[2][0] for _,g in parts),min(g[2][1] for _,g in parts),max(g[2][2] for _,g in parts),max(g[2][3] for _,g in parts))
    area=(max(0,(bounds[0]-6)//divisor*divisor),max(0,(bounds[1]-6)//divisor*divisor),min(1920,math.ceil((bounds[2]+6)/divisor)*divisor),min(1080,math.ceil((bounds[3]+6)/divisor)*divisor))
    alpha=Image.new('L',(area[2]-area[0],area[3]-area[1]))
    for member,(glyph,xy,_) in parts:
        layer=Image.new('L',alpha.size);layer.paste(glyph,(xy[0]-area[0],xy[1]-area[1]));alpha=ImageChops.lighter(alpha,layer)
    if divisor!=1:alpha=alpha.resize((alpha.width//divisor,alpha.height//divisor),Image.Resampling.BOX)
    expected=alpha.point(lambda a:255 if a>=128 else 0);actual=observed_ink(image,area,(INK,TEAL),divisor=divisor)
    score=iou(actual,expected);result={'frame':frame,'component_id':row['name'],'text':row['text'],'kind':'overlapping-related-glyph-group','divisor':divisor,'glyph_iou':score,'passed':score>=(.92 if divisor==1 else .82),
        'observation_box':list(area),'placement_intent':'Two identical amount strings retain their independently prescribed paths while overlapping. Measure their visible union; do not count the other copy as spurious ink in a single-copy mask.'}
    if divisor==1:
        actual_box=actual.getbbox();expected_box=expected.getbbox()
        if not actual_box or not expected_box:result['passed']=False
        else:
            dx=(actual_box[0]+actual_box[2]-expected_box[0]-expected_box[2])/2;dy=(actual_box[1]+actual_box[3]-expected_box[1]-expected_box[3])/2
            edge=actual_box[0]<=0 or actual_box[1]<=0 or actual_box[2]>=actual.width or actual_box[3]>=actual.height
            result['alignment']={'horizontal':'registered-relative-path-group','vertical':'registered-relative-path-group','expected_visible_box':[v+area[i%2] for i,v in enumerate(expected_box)],'actual_visible_box':[v+area[i%2] for i,v in enumerate(actual_box)],'delta_x_px':dx,'delta_y_px':dy,'tolerance_px':1,'touches_measurement_edge':edge,'passed':abs(dx)<=1 and abs(dy)<=1 and not edge}
            result['passed'] &= result['alignment']['passed']
        digits=[]
        for member,(glyph,xy,_) in parts:
            face=font(member['size']);fb=face.getbbox(member['text']);origin=(xy[0]+40-fb[0],xy[1]+40-fb[1])
            for k,ch in enumerate(member['text']):
                if not ch.isdigit():continue
                b=face.getbbox(ch);advance=face.getlength(member['text'][:k]);crop=(math.floor(origin[0]+advance+b[0]-1)-area[0],math.floor(origin[1]+b[1]-1)-area[1],math.ceil(origin[0]+advance+b[2]+1)-area[0],math.ceil(origin[1]+b[3]+1)-area[1])
                value=iou(actual.crop(crop),expected.crop(crop));digits.append({'copy':member['name'],'position':k,'digit':ch,'glyph_union_iou':value,'passed':value>=.88})
        result['digits']=digits;result['passed'] &= all(r['passed'] for r in digits)
    return result


def jsonl(path):
    opener=gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt') as stream:
        for line in stream:
            if line.strip():yield json.loads(line)


def motion_excerpts(video,windows,ffmpeg,directory,actor_box=None):
    """Decode continuous native-size action clips and unscaled actor filmstrips."""
    directory.mkdir(parents=True,exist_ok=False);records=[]
    for ordinal,window in enumerate(windows):
        name=window['id'];start=max(0,window['start_s']-.2);end=window['end_s']+.2
        clip=directory/f'{ordinal:02}-{name}.mp4'
        subprocess.run([str(ffmpeg),'-nostdin','-v','error','-xerror','-n','-ss',f'{start:.9f}','-i',str(video),'-t',f'{end-start:.9f}',
            '-map','0:v:0','-an','-c:v','libx264','-crf','16','-preset','fast','-pix_fmt','yuv420p','-movflags','+faststart',str(clip)],check=True)
        first,last=frame_at(start),frame_at(end)
        indices=sorted({round(first+(last-first-1)*k/7) for k in range(8)})
        box=window.get('actor_box',actor_box) or (0,0,1920,1080)
        width,height=box[2]-box[0],box[3]-box[1]
        film=Image.new('RGB',(width*4,(height+34)*2),'#fff9ea');draw=ImageDraw.Draw(film);observed=[]
        for k,(frame,image) in enumerate(decoded_frames(video,str(ffmpeg),directory/f'{ordinal:02}-{name}-decode.log',1,indices)):
            crop=image.crop(box);x=(k%4)*width;y=(k//4)*(height+34)
            film.paste(crop,(x,y));draw.text((x+8,y+height+8),f'{frame/FPS:.3f}s / frame{frame}',fill=INK)
            observed.append({'frame':frame,'time_s':frame/FPS})
        strip=directory/f'{ordinal:02}-{name}-native-filmstrip.png';film.save(strip)
        records.append({'id':name,'start_s':start,'end_s':end,'path':str(clip),'sha256':sha(clip),'filmstrip':str(strip),'filmstrip_sha256':sha(strip),
            'source_video_sha256':sha(video),'actor_crop_box':list(box),'source_pixels_per_filmstrip_pixel':1,'sampled_frames':observed})
    write_json(directory/'manifest.json',{'passed':True,'scope':'Continuous native1920x1080 video excerpts plus8native actor crops per action. Excerpts prepared for assistant review; export itself is not a motion-quality approval. Audio omitted from these motion-only copies.', 'source_video':str(video),'records':records})
    return records


def actor_preview_checks(video,manifest,ffmpeg,directory):
    """Independently reconstruct registered actor sources, inspect every frame."""
    directory.mkdir(parents=True,exist_ok=False);document=json.loads(Path(manifest).read_text())
    require(sha(video)==document['video']['sha256'],'Actor preview changed')
    reports=document['reports'];starts=[r['start_frame'] for r in reports];cache={};rows=[];failures=[];frames=[]
    area=(770,690,1160,1060)
    def fixture(actor):
        key=(actor['path'],actor['display_body_height_px'],tuple(actor['target_anchor_px']))
        if key not in cache:
            source=path_of(actor['path']);require(sha(source)==actor['sha256'],'Actor source changed')
            raw=Image.open(source).convert('RGBA');scale=actor['display_body_height_px']/actor['reference_height_px']
            raw=raw.resize((round(raw.width*scale),round(raw.height*scale)),Image.Resampling.LANCZOS)
            xy=(round(actor['target_anchor_px'][0]-actor['anchor_px'][0]*scale),round(actor['target_anchor_px'][1]-actor['anchor_px'][1]*scale))
            image=backdrop().convert('RGBA');image.alpha_composite(raw,xy)
            alpha=Image.new('L',SIZE);alpha.paste(raw.getchannel('A'),xy)
            cache[key]=(image.convert('RGB').crop(area),alpha.crop(area).point(lambda a:255 if a>=192 else 0))
        return cache[key]
    selected=set()
    for report in reports:
        for k in [report['start_frame']-1,report['start_frame'],report['end_frame']-1]:
            if 0<=k<document['frame_count']:selected.add(k)
    for index,image in decoded_frames(video,str(ffmpeg),directory/'all307-native-decode.log',1):
        report=reports[max(0,bisect_right(starts,index)-1)];actor=report['data']['actor'];expected,mask=fixture(actor)
        crop=image.crop(area);diff=ImageChops.difference(crop,expected);region=ImageStat.Stat(diff);fg=ImageStat.Stat(diff,mask)
        row={'frame':index,'pose':report['pose'],'actor_roi':list(area),'mean_rgb_error':max(region.mean),'foreground_mean_rgb_error':max(fg.mean),'passed':max(region.mean)<=2.5 and max(fg.mean)<=4}
        rows.append(row)
        if not row['passed']:failures.append(row)
        if index in selected:frames.append((index,report['pose'],crop))
    require(len(rows)==document['frame_count'],'Preview decode count differs')
    # A neutral replacement is a meaningful negative control in a wing-only
    # region; whole-body/background similarity must not conceal a frozen actor.
    opening=next(r for r in reports if r['pose']=='gesture_high')
    neutral=next(r for r in reports if r['pose']=='neutral')
    own,_=fixture(opening['data']['actor']);frozen,_=fixture(neutral['data']['actor'])
    a=ImageChops.difference(own,frozen);activity=ImageChops.lighter(ImageChops.lighter(*a.split()[:2]),a.split()[2]).point(lambda v:255 if v>=24 else 0)
    require(activity.getbbox(),'Wing activity mask empty')
    negative_error=max(ImageStat.Stat(ImageChops.difference(frozen,own),activity).mean)
    require(negative_error>20,'Frozen actor control too weak')
    width,height=area[2]-area[0],area[3]-area[1];strip=Image.new('RGB',(width*5,(height+30)*math.ceil(len(frames)/5)),'#fff9ea');draw=ImageDraw.Draw(strip)
    for ordinal,(index,pose,crop) in enumerate(frames):
        x,y=(ordinal%5)*width,(ordinal//5)*(height+30);strip.paste(crop,(x,y));draw.text((x+5,y+height+7),f'{index/FPS:.3f}s {pose}',fill=INK)
    strip.save(directory/'all-action-boundaries-native.png')
    write_json(directory/'all-frame-observations.json',rows)
    report={'schema_version':1,'passed':not failures,'source_video':str(video),'source_video_sha256':sha(video),'source_manifest_sha256':sha(manifest),
        'decoded_frames':len(rows),'registered_actor_fixtures':len(cache),'maximum_actor_rgb_mean_error':max(r['mean_rgb_error'] for r in rows),
        'maximum_foreground_rgb_mean_error':max(r['foreground_mean_rgb_error'] for r in rows),'all_source_poses_matched_without_fullbody_crossfade':not failures,
        'negative_control':{'replacement':'gesture_high→canonical neutral','changed_region_mean_rgb_error':negative_error,'rejected':negative_error>20},
        'native_boundary_filmstrip':'all-action-boundaries-native.png','failures':failures,
        'scope':'All307encodedpreviewframes decoded and compared against independently placed hash-bound registered sprites; actor crop at native320px body reference. Filmstrip exported for visual review. Does not replace final episode motion/readability QA or human full-length viewing.'}
    write_json(directory/'verification.json',report);return report


def video_track_identity(original,corrected,ffmpeg,ffprobe,directory):
    """Bind visual inheritance to every H264 packet and decoded frame hash."""
    directory.mkdir(parents=True,exist_ok=False);tracks=[]
    for name,path in [('original',original),('corrected',corrected)]:
        packet_path=directory/(name+'-video-packets.json')
        with packet_path.open('xb') as out:
            subprocess.run([str(ffprobe),'-v','error','-select_streams','v:0','-show_packets','-show_entries','packet=pts,dts,duration,size,flags,data_hash','-show_data_hash','sha256','-of','json',str(path)],stdout=out,check=True)
        packets=json.loads(packet_path.read_text())['packets']
        frame_path=directory/(name+'-decoded-framemd5.txt')
        with frame_path.open('xb') as out:
            subprocess.run([str(ffmpeg),'-nostdin','-v','error','-xerror','-i',str(path),'-map','0:v:0','-an','-f','framemd5','pipe:1'],stdout=out,check=True)
        frame_rows=[line for line in frame_path.read_text().splitlines() if line and not line.startswith('#')]
        tracks.append({'name':name,'path':str(path),'sha256':sha(path),'packets':packets,'decoded_frames':frame_rows,'packet_report_sha256':sha(packet_path),'frame_report_sha256':sha(frame_path)})
    require(tracks[0]['packets']==tracks[1]['packets'],'H264 packet bytes/timestamps differ after remux')
    require(tracks[0]['decoded_frames']==tracks[1]['decoded_frames'],'Full decoded-frame pixels/timestamps differ after remux')
    require(len(tracks[0]['packets'])==len(tracks[0]['decoded_frames'])==16954,'Unexpected final H264/frame count')
    report={'schema_version':1,'kind':'exact-H264-and-decoded-pixel-visual-inheritance','passed':True,'original_video_sha256':tracks[0]['sha256'],'corrected_video_sha256':tracks[1]['sha256'],
        'h264_packet_bytes_and_pts_dts_duration_flags_identical':True,'packet_count':len(tracks[0]['packets']),'all_decoded_YUV420p_frame_MD5_and_timestamps_identical':True,'decoded_frame_count':len(tracks[0]['decoded_frames']),
        'reports':[{k:v for k,v in t.items() if k not in ('packets','decoded_frames')} for t in tracks],
        'scope':'EveryH264packetSHA256+PTS/DTS/duration/flags and every decoded1920x1080YUVframeMD5+timestamp compared. Container color metadata and corrected AAC intentionally differ; actual video pixels and timing remain exact.'}
    write_json(directory/'verification.json',report);return report


STATIC_TEXT={
    'seed-equation':'= 1','seed-explanation':'No doubling yet. Start with one.',
    'input-label':'previous value','gate':'× 2','equals':'=',
    'detail-explanation':'The raised 3 counts\nthree doubling steps.',
    'detail-value-0':'1','detail-value-1':'2','detail-value-2':'4','detail-value-3':'8',
    'detail-label-1':'× 2','detail-label-2':'× 2','detail-label-3':'× 2','detail-step-count':'3 doublings from 1',
    'group-transition-title':'32 individual paper shapes','group-transition-value':'32','group-transition-units':'units in this group',
    'group-transition-explanation':'Next, a labeled group stands\nfor the whole amount.',
    'intro-title':'POWERS OF 2','intro-start':'Start with one.','intro-rule':'Copy the whole group. Double it.',
    'intro-sequence':'1   2   4   8   16   32   …',
    'outro-title':'POWERS OF 2','outro-recurrence':'Next value = previous value × 2',
    'outro-sequence':'1   2   4   8   16   32   …','outro-count':'65 terms • 64 doublings • starting at 1',
}


def independently_expected_labels(report,scene):
    state=report['state'];n=scene['index'];committed=scene['committed'];mode=scene['mode'];rows=[];errors=[]
    prior=2**(n-1) if n else None
    power_n=n if committed or state.get('tick',60)/60>=.68 else n-1 if n else 0
    for component in report['components']:
        ident=component['component_id'];authored=component.get('text')
        if authored is None or component.get('drawn_as_part_of_parent'):continue
        row={'name':ident,'size':component.get('font_size_px',component.get('base_font_size_px')),
             'box':component['content_box_xyxy'],'colors':(component.get('color',INK),),'opacity':component.get('opacity',1)}
        if ident in ('power','detail-power','intro-power','outro-power'):
            exponent='n' if mode in ('intro','outro') else 3 if ident=='detail-power' else power_n
            expected=f'2^{exponent}';row.update(kind='power',exponent=exponent,exponent_size=component['exponent_font_size_px'],colors=(INK,TEAL))
        elif ident=='answer':expected=f'{2**n:,}' if committed else '?'
        elif ident in ('input-value','original-copy-value','second-copy-value'):expected=f'{prior:,}'
        elif ident=='operation':expected=f'{prior:,} × 2'+(f' = {2**n:,}' if committed else '')
        elif ident=='english':
            expected='\n'.join(textwrap.wrap(cardinal(2**n),width=68,break_long_words=False,break_on_hyphens=False)) if committed else 'Copy the whole amount.'
        elif ident=='progress':expected=f'Counted: {scene["progress"]} / 65'
        elif ident=='pending-label':expected=f'Doublings: {n}' if committed else 'Making the next power'
        elif ident=='original-copy-label':expected='same group' if n<=5 else 'ORIGINAL GROUP'
        elif ident=='second-copy-label':expected='one more copy' if n<=5 else 'EQUAL COPY'
        elif ident=='milestone-title':
            expected='FIRST PAST ONE '+dict(zip((10,20,30,40,60),('THOUSAND','MILLION','BILLION','TRILLION','QUINTILLION')))[n]
        elif ident in STATIC_TEXT:expected=STATIC_TEXT[ident]
        else:
            errors.append({'component_id':ident,'reason':'Unspecified text component cannot be independently accepted','text':authored});continue
        row['text']=expected
        if authored!=expected:errors.append({'component_id':ident,'expected':expected,'reported':authored,'reason':'Renderer text differs from independent exact truth/format'})
        rows.append(row)
    if mode=='count' and n is not None:
        ids={r['name'] for r in rows}
        required={'power','english','progress'}
        if n==0:required.add('seed-equation')
        elif committed or n<=5 or state.get('tick',60)/60>=.24:required.add('answer')
        else:required.add('original-copy-value')
        if not required<=ids:errors.append({'reason':'Required text fields missing','missing':sorted(required-ids)})
    by={r['name']:r for r in rows}
    if 'original-copy-value' in by and 'second-copy-value' in by:
        a,b=by['original-copy-value'],by['second-copy-value']
        one=expected_geometry(a['text'],a['size'],tuple(a['box']))[2]
        two=expected_geometry(b['text'],b['size'],tuple(b['box']))[2]
        if max(one[0],two[0])-min(one[2],two[2])<12 and max(one[1],two[1])-min(one[3],two[3])<12:
            rows=[r for r in rows if r['name'] not in ('original-copy-value','second-copy-value')]
            rows.append({'name':'overlapping-equal-copies','kind':'related-copies','members':[a,b],'text':a['text']+' + '+b['text'],'size':a['size'],
                'box':[min(a['box'][0],b['box'][0]),min(a['box'][1],b['box'][1]),max(a['box'][2],b['box'][2]),max(a['box'][3],b['box'][3])],
                'colors':(INK,TEAL),'opacity':min(a['opacity'],b['opacity'])})
    return rows,errors


def connected_count(mask,min_area=12):
    mask=mask.copy().convert('L');count=0;boxes=[]
    while (box:=mask.getbbox()) is not None:
        y=box[1];x=next(x for x in range(box[0],box[2]) if mask.getpixel((x,y)))
        before=mask.histogram()[255];ImageDraw.floodfill(mask,(x,y),0);area=before-mask.histogram()[255]
        if area>=min_area:count+=1;boxes.append({'seed_xy':[x,y],'area':area})
    return count,boxes


def inspect_paper_group(image,component,n,frame,ident=None):
    box=tuple(component['content_box_xyxy']);guard=12
    predicted=component.get('visible_box_xyxy',box)
    area=(max(0,math.floor(predicted[0])-guard),max(0,math.floor(predicted[1])-guard),min(1920,math.ceil(predicted[2])+guard),min(1080,math.ceil(predicted[3])+guard))
    name=ident or component['component_id'];color=TEAL if name=='new-paper-units' else INK
    # Finite palette cores distinguish the original ink fill from the teal
    # outline even when the two moving groups share a broad content box.
    crop=image.crop(area);delta=ImageChops.difference(crop,backdrop().crop(area)).split()
    changed=ImageChops.lighter(ImageChops.lighter(delta[0],delta[1]),delta[2]).point(lambda v:255 if v>=24 else 0)
    if name=='new-paper-units':
        r,g,b=crop.split()
        teal_hue=ImageChops.darker(ImageChops.subtract(g,r).point(lambda v:255 if v>=5 else 0),ImageChops.subtract(b,r).point(lambda v:255 if v>=2 else 0))
        actual=ImageChops.darker(teal_hue,changed)
    else:actual=ImageChops.darker(color_mask(crop,color,24),changed)
    raw_count,_=connected_count(actual)
    # Measurement-only closure reconnects <=4px chroma/antialias breaks;
    # genuine18px inter-unit gaps remain distinct. Source pixels stay intact.
    actual=actual.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    target=1 if n==0 else 32 if name=='group-transition-shapes' else 2**(n-1)
    count,components=connected_count(actual)
    try:alignment=raster_centering_report(actual,box,origin_xy=area[:2],name=f'{frame}/{name}',tolerance_px=1)
    except ValueError as exc:alignment={'passed':False,'error':str(exc)}
    return {'frame':frame,'component_id':name,'expected_count':target,'actual_count':count,'raw_threshold_components':raw_count,'measurement_mask_closure_px':5,'source_pixels_changed':False,'component_areas':components,'alignment':alignment,'passed':count==target and alignment['passed']}


def inspect_paper_scene(image,report,n,frame):
    """Verify every exact unit against independent vector/occlusion geometry."""
    state=report['state'];components={c['component_id']:c for c in report['components']}
    if not any(k in components for k in ('old-paper-units','new-paper-units','group-transition-shapes')):return None
    if 'group-transition-shapes' in components:
        # This replay is an unobscured static array; direct component counting.
        return inspect_paper_group(image,components['group-transition-shapes'],5,frame)
    size=84 if n==0 else 44 if n<=4 else 28
    count=1 if n==0 else 2**(n-1);columns=min(8,count);rows=math.ceil(count/columns);step=size+18
    width=(columns-1)*step+size+1;height=(rows-1)*step+size+1
    p=state['tick']/60;q=0 if n==0 else min(1,max(0,(p-.16)/.55));q=q*q*(3-2*q)
    groups=[]
    for name in ('old-paper-units','new-paper-units'):
        if name not in components:continue
        box=components[name]['content_box_xyxy'];x=round((box[0]+box[2]-width)/2);y=round((box[1]+box[3]-height)/2)
        groups.append((name,x,y,1 if name=='old-paper-units' else min(1,4*q)))
    area=(min(g[1] for g in groups)-7,min(g[2] for g in groups)-7,max(g[1]+width for g in groups)+7,max(g[2]+height for g in groups)+7)
    expected=backdrop().crop(area).convert('RGBA');units=[]
    for name,x,y,opacity in groups:
        layer=Image.new('RGBA',expected.size);draw=ImageDraw.Draw(layer);color=rgb(INK if name=='old-paper-units' else TEAL)+(round(opacity*255),)
        for k in range(count):
            ux=x+(k%columns)*step-area[0];uy=y+(k//columns)*step-area[1]
            polygon=[(ux+size//2,uy),(ux+size,uy+size//2),(ux+size//2,uy+size),(ux,uy+size//2)]
            draw.polygon(polygon,fill=color if name=='old-paper-units' else None,outline=color,width=4)
            mask=Image.new('L',expected.size);ImageDraw.Draw(mask).polygon(polygon,fill=255 if name=='old-paper-units' else None,outline=255,width=4)
            units.append({'group':name,'index':k,'mask':mask,'opacity':opacity})
        expected=Image.alpha_composite(expected,layer)
    occluder=Image.new('L',expected.size)
    if n:
        w=round(70*(1-q))+3
        rects=[(956-w,448,956,578),(964,448,964+w,578)]
        for box,color in zip(rects,('#dac8a7','#eddec0')):
            local=tuple(v-area[i%2] for i,v in enumerate(box));ImageDraw.Draw(expected).rectangle(local,fill=color,outline='#ad8d62',width=2);ImageDraw.Draw(occluder).rectangle(local,fill=255)
    actual=image.crop(area).convert('RGB');expected=expected.convert('RGB');difference=ImageChops.difference(actual,expected)
    luma=ImageChops.difference(actual.convert('L'),expected.convert('L'));observations=[]
    for unit in units:
        mask=unit.pop('mask');pixels=mask.histogram()[255];hidden=ImageChops.darker(mask,occluder).histogram()[255]
        err=max(ImageStat.Stat(difference,mask).mean);gray=ImageStat.Stat(luma,mask).mean[0]
        visible=ImageChops.subtract(mask,occluder);vb=visible.getbbox();registration=None
        if vb and visible.histogram()[255]>=12 and unit['opacity']>=.25:
            probe=(max(0,vb[0]-3),max(0,vb[1]-3),min(actual.width,vb[2]+3),min(actual.height,vb[3]+3))
            observed_patch=actual.crop(probe).convert('L');expected_patch=expected.crop(probe).convert('L');local=visible.crop(probe)
            best=(float('inf'),0,0)
            for dx in (-2,-1,0,1,2):
                for dy in (-2,-1,0,1,2):
                    value=ImageStat.Stat(ImageChops.difference(ImageChops.offset(observed_patch,dx,dy),expected_patch),local).mean[0]
                    if value<best[0]-1e-9 or abs(value-best[0])<=1e-9 and dx*dx+dy*dy<best[1]*best[1]+best[2]*best[2]:best=(value,dx,dy)
            registration={'decoded_pattern_translation_x_px':-best[1],'decoded_pattern_translation_y_px':-best[2],'registration_luminance_error':best[0],'tolerance_px':1,'passed':abs(best[1])<=1 and abs(best[2])<=1}
        observations.append({**unit,'expected_stroke_pixels':pixels,'shutter_occluded_pixels':hidden,'visible_fraction':(pixels-hidden)/pixels if pixels else 0,
            'rgb_mean_error':err,'luminance_mean_error':gray,'registration':registration,'passed':(err<=10 or gray<=8) and (registration is None or registration['passed'])})
    result={'frame':frame,'component_id':'exact-paper-unit-scene','index':n,'copies_visible_in_plan':len(groups),'units_per_group':count,'unit_count_in_plan':count*len(groups),
        'q':q,'copy_opacity':min(1,4*q),'shutter_width_px':round(70*(1-q))+3 if n else None,'native_model_box':list(area),'unit_observations':observations,'passed':all(r['passed'] for r in observations),
        'measurement':'Independent exact-count polygons, source-independent placement from declared content boxes, opacity, paint order and opaque inclusive shutter rectangles. Each expected unit stroke compared against decoded native pixels; hidden portions explicitly recorded. Full CC/centering added only after separation completes.'}
    if n==0 or q>=1-1e-9:
        exact=[inspect_paper_group(image,components[name],n,frame) for name,_,_,_ in groups]
        result['fully_exposed_component_counts']=exact;result['passed'] &= all(r['passed'] for r in exact)
    return result


def report_state_check(frame_row,scene,states):
    state=frame_row['state'];errors=[]
    if state['mode']!=scene['mode']:errors.append('mode differs from speech-derived scene')
    if scene['index'] is not None and state['n']!=scene['index']:errors.append('index differs from speech-derived cycle')
    if state['completed']!=scene['progress']:errors.append('progress differs from completed speech count')
    if scene['mode']=='count':
        expected_stage='hold' if scene['committed'] else 'operation'
        if state['stage']!=expected_stage:errors.append('answer commit/pending stage differs from exact result reveal')
        if not scene['committed'] and state['tick']!=round(scene['operation_fraction']*60):errors.append('operation tick differs from exact ceil-frame-grid phase')
    return errors


CANONICAL=ROOT/'assets/library/characters/fairy-pitta/sources/v001/neutral.png'


@lru_cache(maxsize=128)
def actor_fixture(path,source_sha,body_height,reference_height,anchor,foot,divisor):
    source=path_of(path);require(sha(source)==source_sha,'Actor source hash changed')
    raw=Image.open(source).convert('RGBA');scale=body_height/reference_height
    raw=raw.resize((round(raw.width*scale),round(raw.height*scale)),Image.Resampling.LANCZOS)
    xy=(round(foot[0]-anchor[0]*scale),round(foot[1]-anchor[1]*scale))
    layer=Image.new('RGBA',SIZE);layer.alpha_composite(raw,xy)
    bbox=layer.getchannel('A').point(lambda a:255 if a>=8 else 0).getbbox();require(bbox,'Empty actor source')
    area=(max(0,(bbox[0]-8)//divisor*divisor),max(0,(bbox[1]-8)//divisor*divisor),min(1920,math.ceil((bbox[2]+8)/divisor)*divisor),min(1080,math.ceil((bbox[3]+8)/divisor)*divisor))
    image=backdrop().convert('RGBA');image.alpha_composite(layer)
    neutral=Image.open(CANONICAL).convert('RGBA');ns=body_height/637
    neutral=neutral.resize((round(neutral.width*ns),round(neutral.height*ns)),Image.Resampling.LANCZOS)
    baseline=backdrop().convert('RGBA');baseline.alpha_composite(neutral,(round(foot[0]-593*ns),round(foot[1]-969*ns)))
    if divisor!=1:
        image=image.resize((1920//divisor,1080//divisor),Image.Resampling.BOX)
        baseline=baseline.resize(image.size,Image.Resampling.BOX)
        layer=layer.resize(image.size,Image.Resampling.BOX)
    scaled=tuple(v//divisor for v in area);expected=image.convert('RGB').crop(scaled);normal=baseline.convert('RGB').crop(scaled)
    difference=ImageChops.difference(expected,normal).split()
    activity=ImageChops.lighter(ImageChops.lighter(difference[0],difference[1]),difference[2]).point(lambda v:255 if v>=24 else 0)
    foreground=layer.getchannel('A').crop(scaled).point(lambda a:255 if a>=192 else 0)
    return expected,foreground,activity,area


def inspect_actor(image,component,frame,divisor=2):
    expected,foreground,activity,area=actor_fixture(component['path'],component['sha256'],component['display_body_height_px'],component['reference_height_px'],tuple(component['anchor_px']),tuple(component['target_anchor_px']),divisor)
    actual=image.crop(tuple(v//divisor for v in area));diff=ImageChops.difference(actual,expected)
    mean=max(ImageStat.Stat(diff).mean);fg=max(ImageStat.Stat(diff,foreground).mean)
    changed=max(ImageStat.Stat(diff,activity).mean) if activity.getbbox() else None
    changed_luma=ImageStat.Stat(ImageChops.difference(actual.convert('L'),expected.convert('L')),activity).mean[0] if activity.getbbox() else None
    return {'frame':frame,'pose':component['pose'],'divisor':divisor,'source_path':component['path'],'source_sha256':component['sha256'],'mean_rgb_error':mean,'foreground_mean_rgb_error':fg,'changed_gesture_region_mean_rgb_error':changed,
        # Native watercolor grain and4:2:0 edges produce3–5RGB MAE even on
        # correctly placed sprites. This is an identity/motion screen, not a
        # style-quality threshold. Localized changed-gesture pixels prevent a
        # small wing movement from hiding inside high whole-body similarity.
        'changed_gesture_region_mean_luminance_error':changed_luma,
        'passed':mean<=6 and fg<=6 and (changed is None or changed<=10 or changed_luma<=6),'area':list(area),
        'threshold_role':'hash-bound sprite identity screen; grain/4:2:0 tolerance, not image-style acceptance'}


def visual_checks(video,plan,events,states,ffmpeg,directory,visual_spec,frame_states,distinct_reports):
    directory.mkdir(parents=True,exist_ok=False)
    require(visual_spec and frame_states and distinct_reports,'Missing final visual specification/state evidence')
    spec=json.loads(Path(visual_spec).read_text());require(spec['size_px']==[1920,1080] and spec['fps']==30,'Wrong visual size/fps')
    require(sha(path_of(spec['font']['path']))==spec['font']['sha256'] and sha(path_of(spec['background']['path']))==spec['background']['sha256'],'Visual source binding changed')
    require(path_of(spec['background']['path']).resolve()==BACKDROP.resolve(),'Verifier backdrop must explicitly match final visual spec')
    reports={r.get('key',r.get('state_key')):r for r in jsonl(distinct_reports)}
    require(None not in reports and reports,'Empty/invalid distinct-state map')
    frame_rows=list(jsonl(frame_states));require(len(frame_rows)==plan['duration_frames'],'Frame state coverage differs')
    for k,row in enumerate(frame_rows):require(row['frame']==k and row['state_key'] in reports,'Frame map incomplete/unbound')
    failures=[];checks=0;decoded=0;per_n=Counter();excluded_fade=[];semantic_checked=0;native=[];papers=[];images={};minimum_iou={};actor_rows=[]
    def capture_failure(item):
        if len(failures)<100:failures.append(item)
    for frame,image in decoded_frames(video,str(ffmpeg),directory/'all-frame-half-decode.log',2):
        decoded+=1;scene=independent_scene(plan,events,states,frame/FPS);fm=frame_rows[frame];report=reports[fm['state_key']]
        errors=report_state_check(fm,scene,states);semantic_checked+=1
        labels,binding_errors=independently_expected_labels(report,scene)
        if errors or binding_errors:capture_failure({'frame':frame,'semantic_errors':errors,'text_binding_errors':binding_errors})
        if fm['state'].get('fade',0):excluded_fade.append(frame);continue
        if scene['index'] is not None:per_n[scene['index']]+=1
        actor=next((c for c in report['components'] if c['component_id']=='character'),None)
        if actor:
            observation=inspect_actor(image,actor,frame);actor_rows.append(observation)
            if not observation['passed']:capture_failure(observation)
        for row in labels:
            if row['opacity']<.995:continue
            result=inspect_label(image,row,frame,2,False);checks+=1
            minimum_iou[row['name']]=min(minimum_iou.get(row['name'],1),result['glyph_iou'])
            if not result['passed']:capture_failure(result)
        if frame%900==0:print(json.dumps({'half_frame':frame,'of':plan['duration_frames'],'failures':len(failures)}),flush=True)
    require(decoded==plan['duration_frames'],'Full decode missed frames');require(set(per_n)==set(range(65)),'Counted value lacks decoded observations')
    write_json(directory/'half-resolution-checkpoint.json',{'decoded_frames':decoded,'glyph_observations':checks,'semantic_observations':semantic_checked,'per_n':dict(per_n),'failures':failures,'minimum_iou':minimum_iou,'actor_observations':len(actor_rows)})
    indices,reasons=native_sample_indices(plan,events,states)
    # Every actual transition into a distinct operation tick is sampled, not
    # merely the nominal start/midpoint/end. This covers moving copies/inputs.
    for k,row in enumerate(frame_rows):
        if k==0 or row['state_key']!=frame_rows[k-1]['state_key']:
            if row['state']['mode']=='count' and row['state']['stage']=='operation':
                indices.extend(j for j in (k-1,k,k+1) if 0<=j<plan['duration_frames'])
        if k and row['state']['pose']!=frame_rows[k-1]['state']['pose']:
            indices.extend(j for j in (k-1,k,k+1) if 0<=j<plan['duration_frames'])
    indices=sorted(set(indices));result_mid={frame_at((s['voice_start_s']+s['voice_end_s'])/2):s['index'] for s in states}
    # Final revision replaces one204frame closed-GOP tail; inspect its entire
    # un-faded portion natively rather than inheriting it from the prefix.
    indices=sorted(set(indices)|set(range(max(0,plan['duration_frames']-204),plan['duration_frames'])))
    for frame,image in decoded_frames(video,str(ffmpeg),directory/'native-event-decode.log',1,indices):
        scene=independent_scene(plan,events,states,frame/FPS);fm=frame_rows[frame];report=reports[fm['state_key']]
        if fm['state'].get('fade',0):continue
        labels,_=independently_expected_labels(report,scene)
        for row in labels:
            if row['opacity']<.995:continue
            result=inspect_label(image,row,frame);result['reasons']=sorted(reasons.get(frame,()))
            native.append(result)
            if not result['passed']:capture_failure(result)
        actor_component=next((c for c in report['components'] if c['component_id']=='character'),None)
        if actor_component and actor_component['pose']=='gesture_high' and 'actor-high' not in images:images['actor-high']=(frame,image.copy(),actor_component)
        if frame in result_mid or scene['mode']=='teaching' or (scene['mode']=='count' and fm['state']['stage']=='operation'):
            observed=inspect_paper_scene(image,report,scene['index'],frame)
            if observed:
                papers.append(observed)
                if not observed['passed']:capture_failure(observed)
        if frame in result_mid or scene['mode']=='teaching' and 'midpoint' in ' '.join(reasons.get(frame,())):
            image.save(directory/f'frame-{frame:05}.png')
        if scene['mode']=='count' and scene['index'] in (3,64):
            tag=f'n{scene["index"]}-'+('hold' if scene['committed'] else 'pending')
            if tag not in images and (scene['committed'] or fm['state']['tick']>=42):images[tag]=(frame,image.copy(),labels,report)
    write_json(directory/'native-labels.json',native);write_json(directory/'native-paper-groups.json',papers);write_json(directory/'all-frame-actors.json',actor_rows)
    # Image-level negative controls use actual decoded frames, without
    # modifying the video. Wrong final digit, premature final answer, removed
    # concrete copy must each fail the same production observation functions.
    negatives=[]
    hold_frame,hold,hold_labels,hold_report=images['n64-hold'];answer=next(r for r in hold_labels if r['name']=='answer')
    bad=hold.copy();alpha,xy,bounds=expected_geometry(answer['text'],answer['size'],tuple(answer['box']))
    face=font(answer['size']);fb=face.getbbox(answer['text']);origin=(xy[0]+40-fb[0],xy[1]+40-fb[1]);position=len(answer['text'])-1;db=face.getbbox(answer['text'][-1]);advance=face.getlength(answer['text'][:position])
    region=(math.floor(origin[0]+advance+db[0]-2),math.floor(origin[1]+db[1]-2),math.ceil(origin[0]+advance+db[2]+2),math.ceil(origin[1]+db[3]+2))
    bad.paste(backdrop().crop(region),region[:2]);ImageDraw.Draw(bad).text((origin[0]+advance,origin[1]),'7',font=face,fill=TEAL)
    wrong=inspect_label(bad,answer,hold_frame);negatives.append({'kind':'wrong-final-digit6→7','rejected':not wrong['passed'],'observation':wrong})
    pending_frame,pending,pending_labels,_=images['n64-pending'];pending_answer=next(r for r in pending_labels if r['name']=='answer');bad=pending.copy();box=tuple(answer['box']);bad.paste(hold.crop(box),box[:2]);early=inspect_label(bad,pending_answer,pending_frame)
    negatives.append({'kind':'premature-final-answer-in-pending-frame','rejected':not early['passed'],'observation':early})
    early_frame,concrete,_,concrete_report=images['n3-hold'];copy_comp=next(c for c in concrete_report['components'] if c['component_id']=='new-paper-units');box=tuple(map(round,copy_comp['content_box_xyxy']));bad=concrete.copy();bad.paste(backdrop().crop(box),box[:2]);missing=inspect_paper_group(bad,copy_comp,3,early_frame)
    negatives.append({'kind':'remove-new-copy4paper-units','rejected':not missing['passed'],'observation':missing})
    actor_frame,actor_image,actor=images['actor-high']
    raw=Image.open(CANONICAL).convert('RGBA');scale=actor['display_body_height_px']/637
    raw=raw.resize((round(raw.width*scale),round(raw.height*scale)),Image.Resampling.LANCZOS);neutral_scene=backdrop().convert('RGBA');neutral_scene.alpha_composite(raw,(round(actor['target_anchor_px'][0]-593*scale),round(actor['target_anchor_px'][1]-969*scale)))
    _,_,_,actor_area=actor_fixture(actor['path'],actor['sha256'],actor['display_body_height_px'],actor['reference_height_px'],tuple(actor['anchor_px']),tuple(actor['target_anchor_px']),1)
    neutral_crop=neutral_scene.convert('RGB').crop(actor_area);bad=actor_image.copy();bad.paste(neutral_crop,actor_area[:2]);frozen=inspect_actor(bad,actor,actor_frame,1)
    negatives.append({'kind':'freeze-gesture-high-to-neutral','rejected':not frozen['passed'],'observation':frozen})
    bad=actor_image.copy();bad.paste(Image.blend(actor_image.crop(actor_area),neutral_crop,.5),actor_area[:2]);ghost=inspect_actor(bad,actor,actor_frame,1)
    negatives.append({'kind':'half-opacity-double-actor-high-and-neutral','rejected':not ghost['passed'],'observation':ghost})
    require(all(r['rejected'] for r in negatives),'At least one image negative control was not detected')
    write_json(directory/'negative-controls.json',negatives)
    return {'passed':not failures,'decoded_frames':decoded,'all_frame_semantic_observations':semantic_checked,'all_frame_half_glyph_observations':checks,
        'per_counted_index_observed_frames':dict(per_n),'native_sample_frames':len(indices),'native_glyph_observations':len(native),'native_paper_group_observations':len(papers),
        'minimum_half_iou_by_component':minimum_iou,'fade_frames_excluded_from_normal_glyph_threshold':excluded_fade,'negative_controls':negatives,'failures':failures,
        'actors':{'observed_frames':len(actor_rows),'poses':dict(Counter(r['pose'] for r in actor_rows)),'max_foreground_mean_rgb_error':max((r['foreground_mean_rgb_error'] for r in actor_rows),default=None),'max_gesture_region_mean_rgb_error':max((r['changed_gesture_region_mean_rgb_error'] or 0 for r in actor_rows),default=None),'max_gesture_region_mean_luminance_error':max((r['changed_gesture_region_mean_luminance_error'] or 0 for r in actor_rows),default=None),'passed':bool(actor_rows) and all(r['passed'] for r in actor_rows)},
        'scope':'Every frame decoded at half resolution for independent exact text/format, speech-derived state and hash-bound registered actor sprite placement (including localized gesture-change region). Native frame samples cover every actual operation-state entry±1, every cue start/end±1/midpoint, result commit, all digit rollovers and all65results. Every native numeric glyph checked locally; paper components measured independently. Exported native motion excerpts/fade curves are reviewed separately; no human full-length viewing claim.'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video',type=Path,required=True)
    parser.add_argument('--timeline',type=Path,required=True)
    parser.add_argument('--master',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    parser.add_argument('--design',type=Path,default=DESIGN/'sequence.json')
    parser.add_argument('--visual-spec',type=Path)
    parser.add_argument('--frame-states',type=Path)
    parser.add_argument('--distinct-reports',type=Path)
    parser.add_argument('--delivery-dir',type=Path)
    parser.add_argument('--reuse-technical-report',type=Path)
    parser.add_argument('--reuse-audio-report',type=Path)
    parser.add_argument('--reuse-visual-report',type=Path)
    parser.add_argument('--video-inheritance-report',type=Path)
    parser.add_argument('--fade-report',type=Path)
    parser.add_argument('--ffmpeg',default=shutil.which('ffmpeg') or str(ROOT/'.venv/bin/ffmpeg'))
    parser.add_argument('--ffprobe',default=shutil.which('ffprobe') or str(ROOT/'.venv/bin/ffprobe'))
    parser.add_argument('--phase',choices=('schedule','technical','audio','visual','all'),default='all')
    args=parser.parse_args(argv);args.out_dir.mkdir(parents=True,exist_ok=False)
    report={'schema_version':1,'kind':'independent-powers-of-two-final-media-verification','created_at_utc':datetime.now(timezone.utc).isoformat(),'passed':False,'phase':args.phase,'verifier_sha256':sha(Path(__file__)),'errors':[]}
    try:
        if args.video.is_file():report['video']={'path':str(args.video),'sha256':sha(args.video)}
        plan=json.loads(args.timeline.read_text());report['timeline']={'path':str(args.timeline),'sha256':sha(args.timeline)}
        report['visual_timeline_signature']=visual_timeline_signature(plan)
        events,states,report['schedule']=validate_schedule(plan,args.design)
        if args.phase in ('technical','all'):
            if args.reuse_technical_report:
                prior=json.loads(args.reuse_technical_report.read_text());require(prior.get('passed') and prior['video']['sha256']==report['video']['sha256'] and prior['timeline']['sha256']==report['timeline']['sha256'],'Reused technical report is not accepted for the same exact inputs')
                report['technical']=prior['technical'];report['reused_technical_evidence']={'path':str(args.reuse_technical_report),'sha256':sha(args.reuse_technical_report)}
            else:report['technical']=technical.verify_video(args.video,args.out_dir/'technical',args.timeline,args.ffmpeg,args.ffprobe,duration_bounds=(480,1800))
            require(report['technical']['status']=='pass','Technical media gate failed')
            require(report['technical']['measurements']['true_peak_dbtp']<=-1.45,'AAC truepeak exceeds−1.5dBTP ceiling with.05dB measurement tolerance')
        if args.phase in ('audio','all'):
            if args.reuse_audio_report:
                prior=json.loads(args.reuse_audio_report.read_text());require(prior.get('passed') and prior['video']['sha256']==report['video']['sha256'] and prior['timeline']['sha256']==report['timeline']['sha256'],'Reused audio report is not accepted for the same exact inputs')
                for key in ('source_acceptance','audio','subtitles','delivery'):report[key]=prior[key]
                report['reused_audio_evidence']={'path':str(args.reuse_audio_report),'sha256':sha(args.reuse_audio_report)}
            else:
                report['source_acceptance']=source_acceptance(plan,events)
                report['audio']=audio_checks(plan,events,args.video,args.master,args.ffmpeg,args.out_dir/'audio')
                delivery=args.delivery_dir or next((p for p in (args.video.parent/'delivery',args.video.parent.parent/'delivery',args.video.parent) if list(p.glob('*.srt'))),args.video.parent)
                report['subtitles']=subtitle_checks(events,sorted(delivery.glob('*.srt')))
                report['delivery']=delivery_checks(plan,events,delivery)
        if args.phase in ('visual','all'):
            if args.reuse_visual_report:
                prior=json.loads(args.reuse_visual_report.read_text());require(prior.get('passed') and prior.get('visual_timeline_signature')==report['visual_timeline_signature'],'Reused visual evidence is not accepted for the same visual timeline')
                if prior['video']['sha256']!=report['video']['sha256']:
                    require(args.video_inheritance_report,'Different final MP4 requires exact visual inheritance proof')
                    proof=json.loads(args.video_inheritance_report.read_text());require(proof.get('passed') and proof['original_video_sha256']==prior['video']['sha256'] and proof['corrected_video_sha256']==report['video']['sha256'] and proof['h264_packet_bytes_and_pts_dts_duration_flags_identical'] and proof['all_decoded_YUV420p_frame_MD5_and_timestamps_identical'],'Wrong/incomplete visual inheritance proof')
                    report['video_inheritance']={'path':str(args.video_inheritance_report),'sha256':sha(args.video_inheritance_report),'evidence':proof}
                report['visual']=prior['visual'];report['reused_visual_evidence']={'path':str(args.reuse_visual_report),'sha256':sha(args.reuse_visual_report)}
            else:report['visual']=visual_checks(args.video,plan,events,states,args.ffmpeg,args.out_dir/'visual',args.visual_spec,args.frame_states,args.distinct_reports)
            require(report['visual']['passed'],'Actual decoded visual gate incomplete/failed')
            if args.fade_report:
                fade=json.loads(args.fade_report.read_text());require(fade.get('passed') and fade['video']['sha256']==report['video']['sha256'],'Fade supplement does not accept the same exact video')
                report['fade_verification']={'path':str(args.fade_report),'sha256':sha(args.fade_report),'scope':fade.get('scope'),'summary':fade.get('summary'),'passed':True}
        report['passed']=True
    except Exception as exc:
        report['errors'].append(f'{type(exc).__name__}: {exc}')
    report['scope']='Independent automated and sampled observations only. No claim of human full-length continuous viewing/listening. Unrun stages are not accepted.'
    write_json(args.out_dir/'verification.json',report)
    print(json.dumps({'passed':report['passed'],'report':str(args.out_dir/'verification.json'),'errors':report['errors']},ensure_ascii=False),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
