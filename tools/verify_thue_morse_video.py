"""Independent mathematical, clock, decoded-pixel and media QA for Thue–Morse.

No renderer is imported. Locator geometry supplies only physical locations;
mathematical values and progress are independently reconstructed from bit parity
and measured speech ends. This is separate from artistic acceptance.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from copy import deepcopy
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import wave

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

from component_alignment import raster_centering_report
import verify_video as technical

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT/'design/thue-morse-counting-v1'
FONT = ROOT/'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
SIZE, FPS, RATE = (1920,1080),30,24000


def require(value,message):
    if not value:raise ValueError(message)


def path_of(value):
    path=Path(value)
    return path if path.is_absolute() else ROOT/path


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def read(path):
    path=Path(path);raw=path.read_bytes()
    raw=gzip.decompress(raw) if path.suffix=='.gz' else raw
    if '.jsonl' in path.name:return [json.loads(line) for line in raw.splitlines() if line.strip()]
    return json.loads(raw)


def frame_at(at):return math.ceil(float(at)*FPS-1e-7)


@lru_cache(maxsize=1)
def values():
    parity=tuple(n.bit_count()&1 for n in range(256))
    substitution=[0]
    for _ in range(8):substitution=[y for x in substitution for y in (x,1-x)]
    recursive=[0]
    for n in range(1,256):recursive.append(recursive[n//2]^(n&1))
    require(tuple(substitution)==parity==tuple(recursive),'Independent truth disagreement')
    require(parity.count(0)==parity.count(1)==128 and parity[-1]==0,'Incorrect truth scope')
    return parity


def events_of(plan):
    rows=plan.get('voice_events',plan.get('events',plan.get('cues')))
    require(isinstance(rows,list),'Missing measured events')
    return [{**r,'id':r.get('id',r.get('cue_id')),'text':r.get('text',r.get('english',r.get('spoken_text'))),
             'subtitle_text':r.get('subtitle_text',r.get('text',r.get('english',r.get('spoken_text')))),
             'count_index':r.get('count_index',r.get('position_k',r.get('index')))} for r in rows]


def validate_schedule(plan,check_sources=True,allow_draft=False):
    truth=values();events=events_of(plan)
    script=read(DESIGN/'script/speech-script.json')['cues']
    require(len(events)==len(script)==283,'Expected283speech cues')
    require([e['id'] for e in events]==[r['cue_id'] for r in script],'Cue order differs from authored script')
    require(plan.get('fps')==30 and plan.get('duration_frames')==round(plan['duration_s']*30),'Wrong frame clock')
    require(plan['duration_s']>=480,'Long-form episode shorter than8minutes')
    if not allow_draft:require(plan.get('speech_accepted') is True,'Speech must be accepted for final media QA')
    completed=0;sources={};ordinary=[];extended=[]
    counts=[]
    for i,(e,s) in enumerate(zip(events,script)):
        require(e['text']==s['english'] and e['subtitle_text']==s['english'],f'Untracked script/caption change {e["id"]}')
        require(0<=e['start_s']<e['end_s']<=plan['duration_s'],f'Cue outside video {e["id"]}')
        require(i==0 or events[i-1]['end_s']<=e['start_s']+1/RATE,f'Cue overlap {e["id"]}')
        require(e.get('kind')==s['kind'],f'Wrong kind {e["id"]}')
        require(e.get('progress_delta',int(e['kind']=='count'))==int(e['kind']=='count'),f'Extra progress {e["id"]}')
        require(e.get('voice_start_frame',round(e['start_s']*FPS))==round(e['start_s']*FPS),f'Wrong nearest speech-start frame {e["id"]}')
        require(e.get('voice_end_frame',frame_at(e['end_s']))==frame_at(e['end_s']),f'Wrong speech-end coverage frame {e["id"]}')
        if e['kind']=='count':
            k=len(counts)
            require(e['id']==f'C{k:03d}' and e['count_index']==k and e['value']==truth[k],f'Wrong result {e["id"]}')
            require(e['text'].strip().rstrip('.').lower()==('one' if truth[k] else 'zero'),f'Wrong result words {e["id"]}')
            if counts:
                gap=e['start_s']-counts[-1]['end_s']
                if k-1 in (3,15,31,127):
                    require(gap>2,'Explanation replaced with ordinary gap');extended.append({'after_index':k-1,'gap_s':gap})
                else:
                    require(abs(gap-2)<=2/RATE,f'Ordinary count gap differs at{k}: {gap}');ordinary.append(gap)
            counts.append(e);completed+=1
        else:
            require(e.get('count_index') in (None,''),'Explanation claims a new count index')
        source=path_of(e.get('source_path',e.get('path','')))
        if check_sources:
            if str(source) not in sources:
                require(source.is_file(),f'Missing source {source}')
                digest=sha(source)
                with wave.open(str(source),'rb') as wav:
                    duration=wav.getnframes()/wav.getframerate();fmt=[wav.getnchannels(),wav.getsampwidth(),wav.getframerate()]
                sources[str(source)]={'sha256':digest,'duration_s':duration,'format':fmt}
            row=sources[str(source)]
            require(row['sha256']==e.get('source_sha256',e.get('sha256')),f'Source hash changed {e["id"]}')
            require(abs(row['duration_s']-(e['end_s']-e['start_s']))<=2/RATE,f'Cue length is not actual source length {e["id"]}')
            require(row['format']==[1,2,RATE],f'Unexpected source WAV format {e["id"]}')
    require(len(counts)==completed==256 and len(ordinary)==251 and len(extended)==4,'Wrong scope/gap counts')
    states=plan.get('counted_states',plan.get('states'))
    require(isinstance(states,list) and len(states)==256,'Missing all256visual states')
    for k,(state,event) in enumerate(zip(states,counts)):
        require(state['index']==k and state['value']==truth[k],f'Wrong visual result{k}')
        require(state.get('parent_index')==(k//2 if k else None),f'Wrong parent address{k}')
        require(state.get('parent_value')==(truth[k//2] if k else None),f'Wrong parent value{k}')
        require(state['operation']==('seed' if k==0 else 'complement' if k%2 else 'copy'),f'Wrong operation{k}')
        require(abs(state['result_display_s']-(event['start_s']-.12))<=2/RATE,f'Wrong reveal lead{k}')
        require(abs(state['progress_commit_s']-event['end_s'])<=1/RATE,f'Early/late progress{k}')
        require(state['result_display_frame']==frame_at(state['result_display_s']),f'Wrong reveal frame{k}')
        require(state['progress_commit_frame']==frame_at(state['progress_commit_s']),f'Wrong commit frame{k}')
        require(state.get('completed_terms_before',k)==k and state.get('completed_terms_after',k+1)==k+1,f'Wrong progress state{k}')
        require(state.get('operation_start_s',state.get('cycle_start_s'))<=state['result_display_s'],f'Operation starts after output{k}')
    scenes=plan.get('scenes',[])
    require(scenes and abs(scenes[0]['start_s'])<1e-8 and abs(scenes[-1]['end_s']-plan['duration_s'])<=1/FPS,'Scenes do not cover episode')
    for a,b in zip(scenes,scenes[1:]):require(abs(a['end_s']-b['start_s'])<=1/RATE,'Scene gap/overlap')
    for scene in scenes:
        if scene.get('kind')=='explanation':
            k=scene['after_index'];require(k in (3,15,31,127),'Unexpected explanation boundary')
            require(scene.get('completed_terms')==k+1 and scene.get('replay_adds_terms') is False,'Replay changes progress')
    return events,states,{'passed':True,'truth_methods':['binary-popcount','simultaneous-substitution','fresh-recurrence'],
             'terms':256,'operations':255,'zeros':128,'ones':128,'cues':283,'unique_source_wavs':len(sources),
             'ordinary_boundaries':251,'ordinary_gap_min_s':min(ordinary),'ordinary_gap_max_s':max(ordinary),
             'explanation_boundaries':extended,'duration_s':plan['duration_s'],'frames':plan['duration_frames'],
             'speech_accepted':plan.get('speech_accepted') is True,'source_bytes_checked':check_sources}


def schedule_controls(plan):
    variants=[]
    def trial(name,mutate):
        p=deepcopy(plan);mutate(p)
        try:validate_schedule(p,False,True);rejected=False
        except ValueError:rejected=True
        variants.append({'name':name,'rejected':rejected})
    # Each alias is a separate JSON array after serialization. Mutate canonical
    # voice_events, which is the verifier's declared source clock.
    trial('wrong-output',lambda p:p['voice_events'][next(i for i,e in enumerate(p['voice_events']) if e['id']=='C004')].update(value=0))
    trial('wrong-parent-address',lambda p:p['counted_states'][4].update(parent_index=3))
    trial('wrong-parent-value',lambda p:p['counted_states'][4].update(parent_value=0))
    trial('wrong-operation',lambda p:p['counted_states'][3].update(operation='copy'))
    trial('early-progress',lambda p:p['counted_states'][3].update(progress_commit_s=p['counted_states'][3]['result_voice_start_s']))
    trial('wrong-result-lead',lambda p:p['counted_states'][10].update(result_display_s=p['counted_states'][10]['result_voice_start_s']))
    trial('replay-increments',lambda p:next(x for x in p['scenes'] if x.get('kind')=='explanation').update(replay_adds_terms=True))
    trial('caption-wrong-value',lambda p:next(x for x in p['voice_events'] if x['id']=='C255').update(subtitle_text='One.'))
    require(all(x['rejected'] for x in variants),'A schedule negative control was not rejected')
    return {'passed':True,'controls':variants}


@lru_cache(maxsize=64)
def font(size):return ImageFont.truetype(str(FONT),size)


@lru_cache(maxsize=4096)
def glyph(text,size,gap=14):
    if '\n' in text:
        rows=[glyph(t,size,gap) for t in text.split('\n')];bounds=[m.point(lambda a:255 if a>=128 else 0).getbbox() for m in rows]
        width=max(b[2]-b[0] for b in bounds);height=sum(b[3]-b[1] for b in bounds)+gap*(len(rows)-1)
        out=Image.new('L',(width+64,height+64));y=32
        for row,b in zip(rows,bounds):out.paste(row.crop(b),(32+round((width-b[2]+b[0])/2),y));y+=b[3]-b[1]+gap
        return out
    face=font(size);b=face.getbbox(text);out=Image.new('L',(b[2]-b[0]+64,b[3]-b[1]+64))
    ImageDraw.Draw(out).text((32-b[0],32-b[1]),text,font=face,fill=255)
    return out


@lru_cache(maxsize=8192)
def expected_mask(text,size,box,area,gap=14):
    layer=glyph(text,size,gap);b=layer.point(lambda a:255 if a>=128 else 0).getbbox();require(b,'Empty expected glyph')
    xy=(round((box[0]+box[2]-b[0]-b[2])/2),round((box[1]+box[3]-b[1]-b[3])/2))
    out=Image.new('L',(area[2]-area[0],area[3]-area[1]))
    out.paste(layer,(xy[0]-area[0],xy[1]-area[1]))
    return out.point(lambda a:255 if a>=128 else 0)


def rgb(value):return tuple(bytes.fromhex(value.lstrip('#'))) if isinstance(value,str) else tuple(value)


@lru_cache(maxsize=8)
def background(path):return Image.open(path_of(path)).convert('RGB').resize(SIZE,Image.Resampling.LANCZOS)


def observed_ink(image,area,color,fill=None,background_path=None):
    crop=image.crop(area).convert('RGB')
    if fill:base=Image.new('RGB',crop.size,fill)
    elif background_path:base=background(background_path).crop(area)
    else:
        # A plain light panel can be measured without knowing its exact shade:
        # estimate only from the clear edge samples, not the glyph interior.
        edges=[crop.getpixel((x,y)) for x,y in [(0,0),(crop.width-1,0),(0,crop.height-1),(crop.width-1,crop.height-1)]]
        base=Image.new('RGB',crop.size,tuple(sorted(c[k] for c in edges)[len(edges)//2] for k in range(3)))
    weights=(.2126,.7152,.0722,0);measured=crop.convert('L',weights);ground=base.convert('L',weights)
    level=round(sum(a*b for a,b in zip(rgb(color),weights)))
    midpoint=ground.point(lambda x:(x+level+1)//2)
    if ImageStat.Stat(ground).mean[0]>=level:mask=ImageChops.subtract(measured,midpoint).point(lambda x:255 if x==0 else 0)
    else:mask=ImageChops.subtract(midpoint,measured).point(lambda x:255 if x==0 else 0)
    changed=ImageChops.difference(crop,base);difference=ImageChops.lighter(ImageChops.lighter(changed.getchannel(0),changed.getchannel(1)),changed.getchannel(2)).point(lambda x:255 if x>=24 else 0)
    observed=ImageChops.darker(mask,difference)
    if min(rgb(color))>210 and fill and sum(rgb(fill))/3<190:
        red,green,blue=crop.split()
        # Pale numerical ink and warm gold active borders have distinct hue.
        # This rejects the border by colour, without an expected glyph stencil.
        warm=ImageChops.subtract(red,blue).point(lambda x:255 if x<=40 else 0)
        observed=ImageChops.darker(observed,warm)
    return observed


def binary_tile_ink(mask):
    """Isolate a single connected0/1 glyph from disconnected border fragments.

    No expected digit or glyph mask is consulted. Border fragments may enter a
    padded ROI at rounded tile corners; the actual digit is the largest connected
    foreground object. Empty/wrong/shifted digits remain subject to the same tests.
    """
    width,height=mask.size;raw=mask.tobytes();seen=set();components=[]
    for index,value in enumerate(raw):
        if not value or index in seen:continue
        todo=[index];seen.add(index);pixels=[]
        while todo:
            i=todo.pop();pixels.append(i);x=i%width;y=i//width
            for yy in range(max(0,y-1),min(height,y+2)):
                for xx in range(max(0,x-1),min(width,x+2)):
                    j=yy*width+xx
                    if raw[j] and j not in seen:seen.add(j);todo.append(j)
        components.append(pixels)
    if not components:return mask,{'components':0,'selected_pixels':0}
    components.sort(key=len,reverse=True);data=bytearray(width*height)
    for i in components[0]:data[i]=255
    return Image.frombytes('L',mask.size,bytes(data)),{'components':len(components),'selected_pixels':len(components[0]),'discarded_fragment_pixels':sum(map(len,components[1:]))}


def iou(a,b):
    union=ImageChops.lighter(a,b).histogram()[255]
    return ImageChops.darker(a,b).histogram()[255]/union if union else 0.


def expected_text(component,sample,counts):
    """Use independent values for all mathematical/progress component roles."""
    ident=component.get('component_id',component.get('name',component.get('role','')))
    k=component.get('math_index',sample.get('index',sample.get('current_index')))
    now=sample.get('time_s',sample['frame']/FPS)
    completed=bisect_right([e['end_s'] for e in counts],now+1e-8)
    truth=values();k=int(k) if k is not None else None
    if ident in ('progress','replay-progress'):
        return ('Replay · ' if component.get('text','').startswith('Replay') else '')+f'Terms counted: {completed} / 256'
    if re.fullmatch(r'(?:history|loom)-\d+',ident):return str(truth[int(ident.split('-')[-1])])
    if ident.startswith('original-'):return str(truth[int(ident.split('-')[-1])])
    if ident.startswith('complement-pending-'):return '?'
    if ident.startswith('complement-'):return str(1-truth[int(ident.split('-')[-1])])
    if ident.startswith(('replay-original-','replay-parent-')):return str(truth[int(ident.split('-')[-1])])
    if ident.startswith('replay-complement-'):return str(1-truth[int(ident.split('-')[-1])])
    if ident.startswith('replay-child-'):return str(truth[int(ident.split('-')[-1])])
    if ident.startswith('binary-one-'):return '1'
    if ident=='legend-zero':return '0'
    if ident=='legend-one':return '1'
    fixed={'seed-rule-preview':'t(0) = 0','two-rules':'t(2n) = t(n)     ·     t(2n + 1) = 1 − t(n)',
           'copy-rule':'t(2n) = t(n)','copy-recurrence':'t(2n) = t(n)',
           'swap-rule':'t(2n + 1) = 1 − t(n)','swap-recurrence':'t(2n + 1) = 1 − t(n)',
           'swap-zero-example':'1 − 0 = 1','swap-one-example':'1 − 1 = 0',
           'position-value-2':'position 2 → value 1','position-value-3':'position 3 → value 0',
           'joined-word':'01101001  |  10010110','substitution-rules':'0 → 01        1 → 10',
           'replay-shape':'Replay · 16 parents → 32 children','loom-order':'16 × 16 · positions 0–255',
           'prefix':'0, 1, 1, 0, 1, 0, 0, 1, …','suffix':'… 1, 0, 0, 1, 0, 1, 1, 0'}
    if ident in fixed:return fixed[ident]
    if ident=='history-range':return f'Positions {max(0,completed-16)}–{completed-1}'
    if ident=='final-rule':
        step=sample.get('step',0)
        return '0, 1, 1, 0 · REPLAY' if step==1 else 't(0) = 0 · t(2n) = t(n) · t(2n + 1) = 1 − t(n)' if step==2 else 't(255) = 1 − t(127) = 0'
    if ident=='last-equation':return 't(255) = 1 − t(127) = 0'
    if ident=='last-value':return 't(255) = 0'
    if ident=='balanced-counts':return '128 zeros. 128 ones.'
    if k is not None and ident in ('binary-position','parity-result','popcount-rule'):
        bits=format(k,'b');ones=bits.count('1');value=ones%2
        if ident=='binary-position':return f'position {k} = {bits}₂'
        if ident=='parity-result':return f'{ones} ones → '+('odd → 1' if value else 'even → 0')
        return f't({k}) = s₂({k}) mod 2 = {value}'
    if ident=='moving-reference' and k is not None:
        phase=sample.get('operation_phase',sample.get('step_phase',0)/.8)
        return str(truth[k//2] if phase<.45 else truth[k])
    if k is not None and ident in ('parent-value','parent-address','operation','result-value','seed-value','result-word','result-address','active-equation','pending-result','gate-title'):
        result=truth[k];parent=k//2
        pending=not sample.get('result_revealed',sample.get('metadata',{}).get('result_revealed',True))
        if ident=='pending-result':return '?'
        if ident in ('result-value','seed-value'):return str(result)
        if ident=='parent-value':return str(truth[parent])
        if ident=='parent-address':return f'PARENT · position {parent}'
        if ident=='result-address':return f'POSITION {k}'
        if ident=='operation':return 'SAME VALUE' if k%2==0 else f'1 − {truth[parent]}'
        if ident=='gate-title':return 'COPY' if k%2==0 else 'SWAP 0 ↔ 1'
        if ident=='result-word':return 'ONE' if result else 'ZERO'
        if ident=='active-equation':
            if k==0:return 't(0) = '+('?' if pending else '0')
            return (f't({k}) = t({parent}) = ' if k%2==0 else f't({k}) = 1 − t({parent}) = ')+('?' if pending else str(result))
    return component.get('text')


def inspect_component(image,row,text,frame,background_path=None):
    box=tuple(row.get('content_box_xyxy',row.get('content_box',row.get('box'))))
    size=int(row.get('font_size_px',row.get('size')))
    b=glyph(text,size).point(lambda x:255 if x>=128 else 0).getbbox()
    # Measure in a padded independent ROI around the intended full content box,
    # capped by its clear padding so neighbouring panels/actors stay excluded.
    width=b[2]-b[0];height=b[3]-b[1];cx=(box[0]+box[2])/2;cy=(box[1]+box[3])/2
    area=(max(0,math.floor(cx-width/2)-10),max(0,math.floor(cy-height/2)-10),min(1920,math.ceil(cx+width/2)+10),min(1080,math.ceil(cy+height/2)+10))
    if row.get('tile_box_xyxy'):
        tile=row['tile_box_xyxy']
        area=(max(area[0],tile[0]+3),max(area[1],tile[1]+3),min(area[2],tile[2]-3),min(area[3],tile[3]-3))
    actual=observed_ink(image,area,row.get('color','#4e4639'),row.get('fill'),row.get('background_path',background_path))
    fragment_report=None
    if row.get('role')=='binary-valued-tile' and text in ('0','1'):
        actual,fragment_report=binary_tile_ink(actual)
    expected=expected_mask(text,size,box,area,row.get('line_gap_px',14));score=iou(actual,expected)
    report={'frame':frame,'component_id':row.get('component_id',row.get('name')),'expected_text':text,'declared_text':row.get('text'),
            'font_size_px':size,'content_box_xyxy':list(box),'observation_box_xyxy':list(area),'glyph_iou':score,'minimum_iou':.9,
            'passed':score>=.9 and actual.getbbox() is not None}
    if fragment_report is not None:report['tile_component_isolation']=fragment_report
    try:
        alignment=raster_centering_report(actual,box,origin_xy=area[:2],name=str(report['component_id']),tolerance_px=1)
        report['alignment']=alignment;report['passed'] &= alignment['passed']
    except ValueError as exc:report['alignment']={'passed':False,'error':str(exc)};report['passed']=False
    if re.search(r'\d',text) and '\n' not in text:
        face=font(size);whole=face.getbbox(text);layer=glyph(text,size);bounds=layer.point(lambda a:255 if a>=128 else 0).getbbox()
        xy=(round((box[0]+box[2]-bounds[0]-bounds[2])/2),round((box[1]+box[3]-bounds[1]-bounds[3])/2))
        origin=(xy[0]+32-whole[0],xy[1]+32-whole[1]);digits=[]
        for position,char in enumerate(text):
            if char not in '0123456789':continue
            bb=face.getbbox(char);advance=face.getlength(text[:position]);digit_box=(math.floor(origin[0]+advance+bb[0]-3),math.floor(origin[1]+bb[1]-3),math.ceil(origin[0]+advance+bb[2]+3),math.ceil(origin[1]+bb[3]+3))
            local=(digit_box[0]-area[0],digit_box[1]-area[1],digit_box[2]-area[0],digit_box[3]-area[1]);observed=actual.crop(local);scores=[]
            for alt in '0123456789':
                alternate=text[:position]+alt+text[position+1:]
                scores.append((iou(observed,expected_mask(alternate,size,box,area,row.get('line_gap_px',14)).crop(local)),alt))
            scores.sort(reverse=True);winner=scores[0]
            digits.append({'position':position,'expected':char,'observed':winner[1],'iou':winner[0],'alternative_margin':winner[0]-scores[1][0],'passed':winner[1]==char and winner[0]>=.82})
        report['digits']=digits;report['passed'] &= all(r['passed'] for r in digits)
    return report


def pixel_controls():
    box=(800,400,1100,620);row={'component_id':'control','text':'0','font_size_px':136,'box':box,'color':'#4e4639','fill':'#fff6de'}
    rows=[]
    for name,text,shift in [('correct','0',(0,0)),('wrong-value','1',(0,0)),('offset-x','0',(4,0)),('offset-y','0',(0,4)),('empty','',(0,0))]:
        image=Image.new('RGB',SIZE,'#fff6de')
        if text:
            mask=expected_mask(text,136,box,(0,0,1920,1080));colored=Image.new('RGBA',SIZE,'#4e4639');colored.putalpha(mask)
            image.paste(colored,shift,colored)
        observed=inspect_component(image,row,'0',0)
        rows.append({'name':name,'expected_pass':name=='correct','passed':observed['passed']==(name=='correct'),'observation':observed})
    require(all(r['passed'] for r in rows),'A pixel negative control was not discriminated')
    return {'passed':True,'controls':rows}


def normalize_locator(data):
    rows=data.get('samples',data.get('frames',data.get('locators',[]))) if isinstance(data,dict) else data
    require(isinstance(rows,list) and rows,'No locator samples')
    result=[]
    for row in rows:
        frame=int(row.get('frame',frame_at(row['time_s']) if 'time_s' in row else -1))
        require(frame>=0,'Missing sample frame')
        result.append({**row,**row.get('state',{}),'frame':frame,'time_s':frame/FPS,
                       'components':row.get('components',row.get('records',row.get('labels',[])))})
    unique={}
    for row in result:unique[row['frame']]=row
    return [unique[k] for k in sorted(unique)]


def selected_frames(video,ffmpeg,indices,log):
    # The select filter emits requested native frames after decoding their
    # preceding stream. Full-stream error/terminal validation is a separate gate.
    script=log.with_suffix('.filter.txt')
    def balanced(items):
        if len(items)==1:return f'eq(n\\,{items[0]})'
        middle=len(items)//2
        return '('+balanced(items[:middle])+')+('+balanced(items[middle:])+')'
    # A flat thousands-node sum exceeds FFmpeg's expression recursion budget.
    # The balanced tree keeps the exact same frame set with logarithmic depth.
    script.write_text('select='+balanced(indices))
    with log.open('wb') as errors:
        proc=subprocess.Popen([str(ffmpeg),'-hide_banner','-v','error','-xerror','-i',str(video),'-an','-vf',script.read_text(),'-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stdout=subprocess.PIPE,stderr=errors)
        size=1920*1080*3
        for frame in indices:
            raw=bytearray()
            while len(raw)<size:
                chunk=proc.stdout.read(size-len(raw))
                if not chunk:break
                raw.extend(chunk)
            require(len(raw)==size,f'Missing native sample{frame}')
            yield frame,Image.frombytes('RGB',SIZE,bytes(raw))
        require(proc.stdout.read(1)==b'','Unexpected selected frames')
        require(proc.wait()==0,'Native decoder failed')


def visual_checks(video,plan,locator_path,ffmpeg,out):
    out.mkdir(parents=True,exist_ok=True)
    locators=normalize_locator(read(locator_path));by={r['frame']:r for r in locators};events=events_of(plan);counts=[e for e in events if e['kind']=='count']
    failures=[];records=[];math_ids=set();saved=[];mins={};maxdx=maxdy=0;failure_counts={}
    for number,(frame,image) in enumerate(selected_frames(video,ffmpeg,sorted(by),out/'native-decode.log')):
        sample=by[frame];now=frame/FPS;completed=bisect_right([e['end_s'] for e in counts],now+1e-8)
        if sample.get('completed_count',sample.get('completed_terms',completed))!=completed:
            failures.append({'frame':frame,'error':'declared progress differs from measured speech clock','expected':completed,'declared':sample.get('completed_count',sample.get('completed_terms'))})
        if sample.get('fade',sample.get('fade_alpha',0)):continue
        for row in sample['components']:
            if 'text' not in row or not row.get('text') or row.get('horizontal','center')!='center' or row.get('vertical','center')!='center':continue
            text=expected_text(row,sample,counts)
            result=inspect_component(image,row,text,frame,sample.get('background_path'))
            ident=result['component_id'];math_ids.add(ident)
            mins[ident]=min(mins.get(ident,1),result['glyph_iou']);records.append(result)
            measured=result.get('alignment',{});maxdx=max(maxdx,abs(measured.get('delta_x_px',0)));maxdy=max(maxdy,abs(measured.get('delta_y_px',0)))
            if not result['passed']:
                failure_counts[ident]=failure_counts.get(ident,0)+1
                if failure_counts[ident]<=12:failures.append(result)
        if number in (0,len(locators)//2,len(locators)-1) or sample.get('save_native'):
            target=out/f'native-{frame:06d}.png';image.save(target);saved.append({'frame':frame,'path':str(target.relative_to(ROOT)),'sha256':sha(target)})
        if number%100==0:print(json.dumps({'native_frames':number+1,'of':len(locators),'observations':len(records),'flags':len(failures)}),flush=True)
    report={'passed':not failures,'video_sha256':sha(video),'locator_sha256':sha(locator_path),'native_frames':len(locators),
            'glyph_observations':len(records),'maximum_abs_dx_px':maxdx,'maximum_abs_dy_px':maxdy,'alignment_tolerance_px':1,
            'minimum_glyph_iou_by_component':mins,'failures':failures,'native_samples':saved,
            'failure_counts_by_component':failure_counts,
            'scope':'Actual decoded native frame samples from the final MP4. Values/parents/operation/progress/history are rebuilt independently; boxes/font/colors are locator geometry. No renderer import. Fades are excluded from glyph centering and require separate fade review.'}
    write(out/'visual-verification.json',report)
    (out/'glyph-observations.json.gz').write_bytes(gzip.compress(json.dumps(records,ensure_ascii=False,separators=(',',':')).encode()))
    return report


def subtitle_checks(events,path):
    blocks=Path(path).read_text().strip().split('\n\n');require(len(blocks)==len(events),'Subtitle count mismatch')
    rows=[]
    def seconds(stamp):
        h,m,s,ms=map(int,re.split('[:,]',stamp));return h*3600+m*60+s+ms/1000
    for e,block in zip(events,blocks):
        lines=block.splitlines();match=re.fullmatch(r'(\d\d:\d\d:\d\d,\d{3}) --> (\d\d:\d\d:\d\d,\d{3})',lines[1]);require(match,'Invalid subtitle clock')
        start,end=map(seconds,match.groups());text='\n'.join(lines[2:]);same=text==e['subtitle_text']
        rows.append({'id':e['id'],'start_error_ms':(start-e['start_s'])*1000,'end_error_ms':(end-e['end_s'])*1000,'text_matches':same,'passed':same and abs(start-e['start_s'])<=.001 and abs(end-e['end_s'])<=.001})
    return {'passed':all(r['passed'] for r in rows),'cues':rows,'sha256':sha(path)}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--timeline',type=Path,required=True);ap.add_argument('--video',type=Path);ap.add_argument('--locator',type=Path)
    ap.add_argument('--captions',type=Path);ap.add_argument('--master',type=Path);ap.add_argument('--out-dir',type=Path,required=True)
    ap.add_argument('--phase',choices=['schedule','visual','technical','all'],default='schedule');ap.add_argument('--allow-draft',action='store_true')
    ap.add_argument('--ffmpeg',default=str(ROOT/'.venv/bin/ffmpeg'));ap.add_argument('--ffprobe',default=str(ROOT/'.venv/bin/ffprobe'))
    args=ap.parse_args();out=path_of(args.out_dir);out.mkdir(parents=True,exist_ok=True)
    require(not (out/'verification.json').exists(),'Choose an unused QA output directory')
    timeline=path_of(args.timeline);plan=read(timeline);events,states,report=validate_schedule(plan,True,args.allow_draft)
    result={'kind':'independent-thue-morse-production-qa','timeline':{'path':str(timeline.relative_to(ROOT)),'sha256':sha(timeline)},
            'verifier_sha256':sha(Path(__file__)),'scope_phase':args.phase,'mathematics_and_schedule':report,'schedule_negative_controls':schedule_controls(plan),'pixel_negative_controls':pixel_controls(),'completed_episode_accepted':False}
    if args.captions:result['subtitles']=subtitle_checks(events,path_of(args.captions))
    if args.phase in ('visual','all'):
        require(args.video and args.locator,'--video and --locator required for visual QA')
        result['pixels']=visual_checks(path_of(args.video),plan,path_of(args.locator),args.ffmpeg,out/'visual')
    if args.phase in ('technical','all'):
        require(args.video,'--video required for encoded media QA')
        result['technical']=technical.verify_video(path_of(args.video),out/'technical',timeline,args.ffmpeg,args.ffprobe,duration_bounds=(480,1800))
    result['passed']=all(v.get('passed',v.get('status')!='fail') for v in result.values() if isinstance(v,dict))
    result['remaining_separate_gates']=['Final AAC independent lexical/phonetic recognition and source waveform/silence coverage','Native composition, detail and continuous acting comparison; human full-length viewing is not inferred from automatic decoding']
    write(out/'verification.json',result);print(json.dumps({'passed':result['passed'],'report':str(out/'verification.json')}))


if __name__=='__main__':main()
