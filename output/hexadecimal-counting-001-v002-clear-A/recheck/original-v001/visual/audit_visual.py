import hashlib,json,math,shutil,subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

ROOT=Path('D:/codex_projects/youtube')
OUT=Path('D:/temp/hex-visual-recheck-20261111')
BASE=ROOT/'output/hexadecimal-counting-001-v001'
VIDEO=BASE/'paspla-studio-hexadecimal-count-0-to-7F-1080p.mp4'
plan=json.loads((BASE/'timeline.json').read_text())
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',15)
samples={}
def add(label,time,group):
    frame=min(math.ceil(time*30-1e-7),16913)
    samples.setdefault(frame,[]).append((group,label))

for t in (0,.4,.8,1.5,4,6.2,8.2,10.6,11.4,14.4,17.4,20.4,23.4,26.4,29.1,34.3,35.5,36.5,41.3,46.2,48.6,51.4,55.6,57.8):
    add(f'Intro {t:.2f}s',t,'intro')
for row in plan['counted_states']:
    t=row['digit_highlights'][0]['estimated_start_s']+.05
    add(f"{row['display_hexadecimal']} / decimal {row['decimal_value']}",t,'counts')
for row in plan['carry_cues']:
    value=row['after_decimal_value']
    cut=plan['counted_states'][value+1]['estimated_display_start_s']
    for offset in (-.4,-.0334,0,.0667,.1334):
        add(f'{value:X} to {value+1:X} @ {offset:+.3f}s',cut+offset,'transitions')
pause=plan['pauses'][1]['estimated_start_s']
for offset in (0,.2,3.3,3.4,5.65,5.7,7.8,7.999,8,8.12):
    add(f'3F check +{offset:.3f}s',pause+offset,'check')
for offset in (0,1.5,4.5,7.5,11.1,12.5,13,14,14.9667):
    add(f'Finale +{offset:.3f}s',plan['finale']['estimated_start_s']+offset,'finale')

indices=sorted(samples)
terms=[f'eq(n,{index})' for index in indices]
while len(terms)>1:
    terms=[f'({terms[i]}+{terms[i+1]})' if i+1<len(terms) else terms[i] for i in range(0,len(terms),2)]
expression=terms[0]
ffmpeg=shutil.which('ffmpeg')
command=[ffmpeg,'-nostdin','-v','error','-xerror','-i',str(VIDEO),'-an','-vf',f"select='{expression}',scale=480:270:flags=area,format=rgb24",'-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24','pipe:1']
groups={name:[] for name in ('intro','counts','transitions','check','finale')}
with subprocess.Popen(command,stdout=subprocess.PIPE) as proc:
    for index in indices:
        data=proc.stdout.read(480*270*3)
        if len(data)!=480*270*3:raise ValueError(f'Incomplete frame {index}')
        img=Image.frombytes('RGB',(480,270),data)
        for group,label in samples[index]:groups[group].append((index,label,img.copy()))
    assert not proc.stdout.read(1)
    assert proc.wait()==0

for group,rows in groups.items():
    page_size=32 if group=='counts' else 12
    for start in range(0,len(rows),page_size):
        page=rows[start:start+page_size]
        width,height=(360,110) if group=='counts' else (480,292)
        columns=4 if group=='counts' else 3
        sheet=Image.new('RGB',(width*columns,height*math.ceil(len(page)/columns)),'white')
        draw=ImageDraw.Draw(sheet)
        for i,(index,label,img) in enumerate(page):
            x,y=(i%columns)*width,(i//columns)*height
            draw.text((x+4,y+2),f'{label} | f{index}',font=font,fill='black')
            if group=='counts':
                sheet.paste(img.crop((29,160,134,207)),(x+2,y+28))
                sheet.paste(img.crop((190,78,425,145)),(x+118,y+22))
                sheet.paste(img.crop((260,178,349,194)),(x+188,y+90))
            else:sheet.paste(img,(x,y+22))
        sheet.save(OUT/f'{group}-{start//page_size+1}.png')
report={'video_sha256':hashlib.file_digest(VIDEO.open('rb'),'sha256').hexdigest(),'unique_frames_decoded':len(indices),'groups':{key:[{'frame':f,'label':l} for f,l,_ in values] for key,values in groups.items()},'contact_sheets':[str(p) for p in OUT.glob('*.png')]}
(OUT/'selection.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'decoded':len(indices),'sheets':len(report['contact_sheets']),'groups':{k:len(v) for k,v in groups.items()}}))
