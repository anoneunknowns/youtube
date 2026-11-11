"""Supplement the historical seed-card and intentional-fade coverage gaps.

Only frozen preproduction content rectangles are used as design intentions.
Actual glyph bounds come from a larger decoded observation, never a returned
renderer bbox. No producer/renderer is imported and no existing QA is edited.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
from functools import lru_cache
import hashlib,json,math,shutil
from pathlib import Path
from PIL import Image,ImageChops,ImageStat

if __package__:
    from . import verify_fibonacci_video as independent
    from .component_alignment import raster_centering_report
else:
    import verify_fibonacci_video as independent
    from component_alignment import raster_centering_report

ROOT=Path(__file__).resolve().parents[1]
DESIGN=ROOT/'design/fibonacci-counting-v1/qa/mockup-verification.json'
CREAM=(255,250,240)
EXPECTED={'series':('Num-Num Numbers',independent.INK,None),
 'seed-heading':('START WITH TWO SEEDS',independent.TEAL,None),
 'seed-value-0':('0',independent.BLUE,independent.PALE),
 'seed-term-0':('F0 · FIRST TERM',independent.BLUE,independent.PALE),
 'seed-value-1':('1',independent.TEAL,independent.PALE),
 'seed-term-1':('F1 · SECOND TERM',independent.TEAL,independent.PALE),
 'seed-explanation':('Zero and one start the sequence.\nEvery later term comes from addition.',independent.INK,None)}

def contract():
    data=json.loads(DESIGN.read_text());shot=next(s for s in data['shots'] if s['filename']=='02-seeds.png')
    rows=[]
    for source in shot['components']:
        ident=source['name'].split('/')[-1]
        if ident not in EXPECTED:continue
        text,color,fill=EXPECTED[ident]
        independent.require(source['text']==text,'Frozen design and independently authored seed content differ')
        field=tuple(source['content_box_xyxy']);l,t,r,b=field
        # Padding is fixed before measuring the completed video. For the two
        # stacked card components, the gap between rows keeps neighboring text
        # separate while preserving every glyph plus surrounding empty space.
        if ident.startswith('seed-value'):observation=(l-15,t-20,r+15,b+14)
        elif ident.startswith('seed-term'):observation=(l-15,t-12,r+15,b+12)
        else:observation=(l-16,t-16,r+16,b+16)
        rows.append(dict(id=ident,text=text,size=source['font_size_px'],field=field,
                         observation=observation,color=color,fill=fill))
    independent.require(len(rows)==7,'Missing frozen seed-card design fields')
    return rows,{'path':str(DESIGN.relative_to(ROOT)),'sha256':independent.sha(DESIGN),
       'used_fields':'Only intended content_box/font size and authored text. Historical visible boxes, center errors and pass flags are not used.',
       'observation_policy':'Fixed expanded fields, all-glyph observation with boundary contact rejection; no target adjustment after measurement.'}

@lru_cache(maxsize=2048)
def expected_mask(text,size,field,observation,dx=0,dy=0,threshold=128):
    alpha=independent.glyph_alpha(text,size);bounds=alpha.point(lambda x:255 if x>=128 else 0).getbbox()
    out=Image.new('L',(observation[2]-observation[0],observation[3]-observation[1]))
    x=round((field[0]+field[2]-bounds[0]-bounds[2])/2)-observation[0]+dx
    y=round((field[1]+field[3]-bounds[1]-bounds[3])/2)-observation[1]+dy
    out.paste(alpha,(x,y));return out.point(lambda x:255 if x>=threshold else 0)

def identify(mask,row,text=None):
    text=row['text'] if text is None else text
    candidates=[(independent.overlap(mask,expected_mask(text,row['size'],tuple(row['field']),tuple(row['observation']),x,y)),x,y)
                for y in (-1,0,1) for x in (-1,0,1)]
    score,x,y=max(candidates)
    if score<.975:
        score=max(score,*(independent.overlap(mask,expected_mask(text,row['size'],tuple(row['field']),tuple(row['observation']),x,y,t)) for t in range(112,233,8)))
    return score

def inspect(image,rows,frame):
    results=[]
    for row in rows:
        extraction='bt709-luminance' if row['fill'] else 'rgb-vector'
        mask=independent.observed_ink(image,row['observation'],row['color'],row['fill'],1,extraction)
        result=raster_centering_report(mask,row['field'],origin_xy=row['observation'][:2],
             name=f'frame{frame}/{row["id"]}',tolerance_px=1)
        score=identify(mask,row);alternatives=[]
        if row['id'].startswith('seed-value'):
            alternatives=[str(n) for n in range(10) if str(n)!=row['text']]
        elif row['id'].startswith('seed-term'):
            ordinal='FIRST' if row['id'].endswith('0') else 'SECOND'
            alternatives=[f'F{n} · {ordinal} TERM' for n in range(41) if f'F{n} · {ordinal} TERM'!=row['text']]
            alternatives += [row['text'].replace('FIRST','SECOND') if ordinal=='FIRST' else row['text'].replace('SECOND','FIRST')]
        wrong_score,wrong=max(((identify(mask,row,text),text) for text in alternatives),default=(0,None))
        identity=score>=.94 and (not alternatives or score-wrong_score>=.005)
        result.update(expected_text=row['text'],font_size_px=row['size'],observation_box_xyxy=list(row['observation']),
            independent_glyph_iou=score,nearest_wrong_text=wrong,nearest_wrong_iou=wrong_score,
            minimum_glyph_iou=.94,correct_text_margin=score-wrong_score,minimum_identity_margin=.005,
            foreground_extraction=extraction,
            foreground_policy='Flat seed-panel glyphs use BT709 half-contrast without a hue gate. Background headings use the established independent RGB-vector inverse-composite model, avoiding low-luma-contrast photographic plate edges.',
            independent_content_identification_passed=identity)
        result['passed']=result['passed'] and identity;results.append(result)
    return results

def seed_checks(video,plan,ffmpeg,directory):
    rows,source=contract()
    spans=[s for s in plan['visual_segments'] if s['mode']=='seeds' and s.get('index') is None]
    independent.require(len(spans)==1,'Expected one uncounted introduction seed-card scene')
    span=spans[0];frames=list(range(independent.frame_at(span['start_s']),independent.frame_at(span['end_s'])))
    records=[];cache={};saved=False
    for frame,image in independent.media.decoded_frames(video,ffmpeg,directory/'intro-seed-decode.log',1,frames):
        signature=tuple(hashlib.sha256(independent.observed_ink(image,row['observation'],row['color'],row['fill'],1,'bt709-luminance' if row['fill'] else 'rgb-vector').tobytes()).digest() for row in rows)
        if signature not in cache:cache[signature]=inspect(image,rows,frame)
        components=[dict(r,name=f'frame{frame}/{rows[i]["id"]}') for i,r in enumerate(cache[signature])]
        records.append({'frame':frame,'at_s':frame/30,'components':components,'passed':all(r['passed'] for r in components)})
        if not saved and frame>=sum(frames)//len(frames):image.save(directory/'intro-seeds-native.png');saved=True
    independent.require(len(records)==len(frames),'Seed introduction decode missed a frame')
    components=[r for f in records for r in f['components']]
    return {'passed':all(r['passed'] for r in components),'source_design':source,'scene_start_s':span['start_s'],
      'scene_end_s':span['end_s'],'decoded_frames':len(records),'components_per_frame':7,
      'max_abs_dx_px':max(abs(r['delta_x_px']) for r in components),
      'max_abs_dy_px':max(abs(r['delta_y_px']) for r in components),'frames':records,
      'numerical_truth':'Initial conditions F0=0/F1=1, ordinals1/2; no recurrence is fabricated for the seeds.'}

def fade_expected_weight(frame,frames,duration,kind):
    if kind=='opening':return max(0,min(1,1-frame/30/.8))
    final_t=(frames-1)/30
    return max(0,min(1,(frame/30-duration+2)/(final_t-duration+2)))

def fade_checks(video,plan,ffmpeg,directory):
    frames=plan['duration_frames'];duration=plan['duration_s']
    opening=list(range(0,25));start=independent.frame_at(duration-2)
    ending=list(range(start-1,frames));selected=opening+ending
    decoded={i:im for i,im in independent.media.decoded_frames(video,ffmpeg,directory/'fade-decode.log',1,selected)}
    cream=Image.new('RGB',independent.SIZE,CREAM);results=[]
    for kind,indices,reference_frame in [('opening',opening,24),('ending',ending[1:],start-1)]:
        reference=decoded[reference_frame];reference_small=reference.resize((120,68),Image.Resampling.BOX)
        base=reference_small.tobytes();target=Image.new('RGB',reference_small.size,CREAM).tobytes()
        direction=[b-a for a,b in zip(base,target)];energy=sum(x*x for x in direction)
        independent.require(energy>100000,'Fade baseline is empty or already cream')
        rows=[]
        for frame in indices:
            image=decoded[frame];weight=fade_expected_weight(frame,frames,duration,kind)
            expected=Image.blend(reference,cream,round(weight*255)/255)
            mean_error=sum(ImageStat.Stat(ImageChops.difference(image,expected)).mean)/3
            raw=image.resize((120,68),Image.Resampling.BOX).tobytes()
            observed=sum((v-a)*d for v,a,d in zip(raw,base,direction))/energy
            rows.append({'frame':frame,'at_s':frame/30,'expected_cream_weight':weight,'observed_cream_weight':observed,
                         'whole_frame_mae_rgb':mean_error,'passed':mean_error<=3 and abs(observed-weight)<=.025})
        diffs=[b['observed_cream_weight']-a['observed_cream_weight'] for a,b in zip(rows,rows[1:])]
        monotonic=all(x>=-.003 for x in diffs) if kind=='ending' else all(x<=.003 for x in diffs)
        results.append({'kind':kind,'reference_frame':reference_frame,'frames':rows,'monotonic':monotonic,
                        'passed':monotonic and all(r['passed'] for r in rows)})
    last=decoded[frames-1];last_error=sum(ImageStat.Stat(ImageChops.difference(last,cream)).mean)/3
    last_range=[list(x) for x in ImageStat.Stat(last).extrema]
    endpoint=last_error<=2 and all(b-a<=3 for a,b in last_range)
    last.save(directory/'final-cream-native.png')
    return {'passed':all(r['passed'] for r in results) and endpoint,'expected_final_cream_rgb':list(CREAM),
      'last_frame_mean_absolute_error_rgb':last_error,'last_frame_rgb_extrema':last_range,
      'endpoint_uniform_and_cream':endpoint,'expected_final_frame':frames-1,'fades':results,
      'method':'Reference is an independently decoded nonfading static frame immediately adjacent to each fade. Quantized linear whole-frame cream blending is tested on every fade frame, without trusting renderer-returned fade state.'}

def run(video,plan,ffmpeg,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    result={'kind':'independent-fibonacci-intro-seed-and-fade-supplement','video_sha256':independent.sha(video),
            'verifier_sha256':independent.sha(Path(__file__)),'passed':False}
    try:
        result['intro_seeds']=seed_checks(video,plan,ffmpeg,directory)
        result['fades']=fade_checks(video,plan,ffmpeg,directory)
        result['passed']=result['intro_seeds']['passed'] and result['fades']['passed']
        return result
    finally:(directory/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--video',type=Path,required=True)
    p.add_argument('--timeline',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--ffmpeg',default=shutil.which('ffmpeg'));args=p.parse_args(argv)
    result=run(args.video,json.loads(args.timeline.read_text()),args.ffmpeg,args.out_dir)
    print(json.dumps({'passed':result['passed'],'report':str(args.out_dir/'verification.json')}))
    independent.require(result['passed'],'Intro seed/fade supplement failed')

if __name__=='__main__':main()
