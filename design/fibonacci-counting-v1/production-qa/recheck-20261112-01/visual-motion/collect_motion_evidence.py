"""Fresh decoded-MP4 motion evidence, with no producer-renderer imports."""
from pathlib import Path
import hashlib
import json
import math
import subprocess

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT/'output/fibonacci-counting-001-v001'
VIDEO = OUT/'paspla-studio-fibonacci-numbers-0-to-102334155-1080p.mp4'
FFMPEG = str(ROOT/'.venv/bin/ffmpeg')
FONT = ROOT/'assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf'
ACTOR = (1470, 570, 1850, 1020)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ref(path):
    return {'path':str(Path(path).relative_to(ROOT)), 'sha256':sha(path)}


def frame(video, index, crop=None):
    filters = ['crop=%s:%s:%s:%s' % (crop[2]-crop[0],crop[3]-crop[1],crop[0],crop[1])] if crop else []
    command = [FFMPEG,'-v','error','-ss',f'{index/30:.9f}','-i',str(video),'-frames:v','1']
    if filters:
        command += ['-vf',','.join(filters)]
    command += ['-f','rawvideo','-pix_fmt','rgb24','pipe:1']
    size = (crop[2]-crop[0],crop[3]-crop[1]) if crop else (1920,1080)
    return Image.frombytes('RGB',size,subprocess.check_output(command))


def changed(a,b,threshold=20):
    diff = ImageChops.difference(a,b)
    channels = diff.split()
    maximum = ImageChops.lighter(channels[0],ImageChops.lighter(channels[1],channels[2]))
    mask = maximum.point(lambda v:255 if v > threshold else 0)
    return {'pixels_over_threshold':mask.histogram()[255],
            'difference_bbox':list(mask.getbbox()) if mask.getbbox() else None,
            'mean_absolute_RGB_difference':sum(ImageStat.Stat(diff).mean)/3,
            'threshold':threshold}


def eyes(image):
    # Independent feature observation from decoded blue iris pixels, restricted
    # to the face. Background windows lie above this region.
    origin=(1540,630)
    face=image.crop((1540,630,1770,810))
    pixels=[]
    for y in range(face.height):
        for x in range(face.width):
            r,g,b=face.getpixel((x,y))
            if b-r >=20 and b-g >=4 and 45<=r<=170 and g<=190:
                pixels.append((x+origin[0],y+origin[1]))
    if not pixels:
        return None
    return {'blue_pixels':len(pixels),'center_xy':[sum(p[i] for p in pixels)/len(pixels) for i in (0,1)],
            'bbox_xyxy':[min(p[0] for p in pixels),min(p[1] for p in pixels),max(p[0] for p in pixels)+1,max(p[1] for p in pixels)+1],
            'method':'Decoded RGB blue-iris mask in fixed face region; gaze changes are intentional features, not a general centering test.'}


def strip(images, labels, destination, columns=4):
    width,height=images[0].size
    sheet=Image.new('RGB',(width*columns,(height+30)*math.ceil(len(images)/columns)),'#fff8ed')
    draw=ImageDraw.Draw(sheet);font=ImageFont.truetype(str(FONT),18)
    for i,(image,label) in enumerate(zip(images,labels)):
        x=i%columns*width;y=i//columns*(height+30)
        sheet.paste(image,(x,y+30));draw.text((x+7,y+4),label,font=font,fill='#45382d')
    sheet.save(destination)


def crop_sequence(video, start_frame, end_frame, box):
    width,height=box[2]-box[0],box[3]-box[1]
    count=end_frame-start_frame
    raw=subprocess.check_output([FFMPEG,'-v','error','-ss',f'{start_frame/30:.9f}','-i',str(video),
                                  '-frames:v',str(count),'-vf',f'crop={width}:{height}:{box[0]}:{box[1]}',
                                  '-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
    stride=width*height*3
    assert len(raw)==count*stride
    return [Image.frombytes('RGB',(width,height),raw[i*stride:(i+1)*stride]) for i in range(count)]


def main():
    references={name:frame(VIDEO,round(at*30),ACTOR) for name,at in
                [('neutral',5),('greet',1.5),('watch_left',25),('present_half',10.1),
                 ('present_full',10.5),('think',60),('delighted',510)]}
    command=[FFMPEG,'-v','error','-i',str(VIDEO),'-vf',
             'crop=380:450:1470:570,select=not(mod(n\\,30))','-fps_mode','passthrough',
             '-f','rawvideo','-pix_fmt','rgb24','pipe:1']
    process=subprocess.Popen(command,stdout=subprocess.PIPE)
    rows=[];index=0;size=380*450*3
    previous=None
    while True:
        raw=process.stdout.read(size)
        if not raw:
            break
        assert len(raw)==size
        image=Image.frombytes('RGB',(380,450),raw)
        distances={name:sum(ImageStat.Stat(ImageChops.difference(image,reference)).mean)/3
                   for name,reference in references.items()}
        match=min(distances,key=distances.get)
        row={'frame':index*30,'at_s':index,'closest_actual_reference':match,
             'reference_MAD':distances[match],'distances':distances,
             'fade_or_unclassified':distances[match]>12}
        if previous is not None:
            row['previous_sample_difference']=changed(image,previous)
        rows.append(row);previous=image;index+=1
    assert process.wait()==0
    # Derive same-pose intervals from observed pixels, never from scheduled poses.
    runs=[]
    for row in rows:
        pose='fade/unclassified' if row['fade_or_unclassified'] else row['closest_actual_reference']
        if not runs or runs[-1]['pose']!=pose:
            runs.append({'pose':pose,'first_observed_frame':row['frame'],'last_observed_frame':row['frame'],'samples':1})
        else:
            runs[-1]['last_observed_frame']=row['frame'];runs[-1]['samples']+=1
    boundaries=[]
    # Scheduled boundaries only choose decode windows. Every saved observation
    # and geometric measurement below is newly decoded from the actual MP4.
    plan=json.loads((OUT/'frame-plan.json').read_text());last=None
    for run in plan['runs']:
        if last is not None and run['pose']!=last:
            boundaries.append({'frame':run['start_frame'],'from':last,'to':run['pose']})
        last=run['pose']
    transition_dir=HERE/'transition-native';transition_dir.mkdir(exist_ok=False)
    observations=[]
    for transition in boundaries:
        center=transition['frame'];start=max(0,center-3);end=center+4
        images=crop_sequence(VIDEO,start,end,ACTOR)
        name=f'f{center:05d}-{transition["from"]}-to-{transition["to"]}'
        strip(images,[f'{(start+i)/30:.3f}s f{start+i}' for i in range(len(images))],transition_dir/f'{name}.png',4)
        before=frame(VIDEO,center-1);after=frame(VIDEO,center)
        measurements={'actor':changed(before.crop(ACTOR),after.crop(ACTOR)),
                      'head':changed(before.crop((1510,580,1800,820)),after.crop((1510,580,1800,820))),
                      'torso':changed(before.crop((1590,830,1720,950)),after.crop((1590,830,1720,950))),
                      'eyes_before':eyes(before),'eyes_after':eyes(after)}
        if measurements['eyes_before'] and measurements['eyes_after']:
            measurements['iris_center_delta_px']=[measurements['eyes_after']['center_xy'][i]-measurements['eyes_before']['center_xy'][i] for i in (0,1)]
        observations.append({**transition,'at_s':center/30,'decoded_contiguous_frames':[start,end-1],
                             'evidence':ref(transition_dir/f'{name}.png'),'measurements':measurements})
    # The renderer's schedules are not consulted for this stationary negative
    # control: a frozen decoded image must return zero pixel motion.
    frozen=changed(references['watch_left'],references['watch_left'])
    report={'kind':'fresh-decoded-MP4-character-motion-survey','video':ref(VIDEO),'actor_roi_xyxy':list(ACTOR),
            'survey_fps':1,'source_frame_indices_exact_multiples_of30':True,'samples':rows,'observed_reference_pose_runs':runs,
            'largest_observed_hold':max((r for r in runs if r['pose']!='fade/unclassified'),key=lambda r:r['samples']),
            'reference_method':'Closest decoded actual-frame RGB mean absolute difference; pose names guide semantic labeling, not source-render acceptance. Whole-frame fade samples excluded bydistance.',
            'transition_observations':observations,'negative_frozen_control':frozen,
            'frozen_control_detected':frozen['pixels_over_threshold']==0,
            'scope':'Fresh1fps survey and7contiguous native actor frames around every scheduled pose boundary. Not a full30fpsall-frame human viewing claim. Detailed numeric/all-frame verification is separate.'}
    (HERE/'motion-measurements.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'samples':len(rows),'transitions':len(observations),'longest_observed_hold':report['largest_observed_hold']}),flush=True)


if __name__=='__main__':
    main()
