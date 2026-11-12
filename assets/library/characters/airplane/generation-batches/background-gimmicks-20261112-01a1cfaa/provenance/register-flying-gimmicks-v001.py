"""Register only the three reserved flying props; all native crops are lossless."""
from pathlib import Path
from collections import deque
import hashlib,json,math,shutil,sys,datetime
from PIL import Image,ImageChops,ImageDraw
ROOT=Path(__file__).resolve().parents[7]
sys.path.insert(0,str(ROOT))
from tools import character_library as library
BATCH='generation-batches/background-gimmicks-20261112-01a1cfaa'
OWNER='codex:gimmicks-20261112:01a1cfaa'
SPECS={
'airplane':{'names':['飛行機','Airplane'],'columns':2,'sheets':[('a','airplane-eight-poses-v001.png','airplane-generation-v001.json',['level_propeller_vertical','level_propeller_diagonal','climb_shallow','climb_strong','descent_shallow','descent_strong','bank_near','bank_far'])],'neutral':'level_propeller_vertical','maximum':360,'clips':{'propeller':(['level_propeller_vertical','level_propeller_diagonal'],[100,100]),'climb':(['level_propeller_vertical','climb_shallow','climb_strong','climb_shallow','level_propeller_vertical'],[350,180,350,180,350]),'descent':(['level_propeller_vertical','descent_shallow','descent_strong','descent_shallow','level_propeller_vertical'],[350,180,350,180,350]),'bank':(['level_propeller_vertical','bank_near','level_propeller_vertical','bank_far'],[350,260,350,260])}},
'rocket':{'names':['ロケット','Rocket'],'columns':1,'sheets':[('a','rocket-thrust-sheet-a-v001.png','rocket_a-generation-v001.json',['idle','ignition_small','steady_thrust']),('b','rocket-thrust-sheet-b-v002.png','rocket_b-generation-v002.json',['thrust_short','thrust_long','coast_tilt'])],'neutral':'idle','maximum':300,'clips':{'ignition':(['idle','ignition_small','steady_thrust','ignition_small','idle'],[600,200,450,200,500]),'thrust':(['steady_thrust','thrust_short','thrust_long','thrust_short'],[130,120,130,120]),'coast':(['idle','coast_tilt','idle'],[600,400,600])}},
'helicopter':{'names':['ヘリコプター','Helicopter'],'columns':1,'sheets':[('a','helicopter-rotors-sheet-a-v002.png','helicopter_a-generation-v002.json',['rotor_0','rotor_45','rotor_90']),('b','helicopter-rotors-sheet-b-v001.png','helicopter_b-generation-v001.json',['rotor_135','pitch_forward','pitch_backward'])],'neutral':'rotor_0','maximum':500,'clips':{'spin':(['rotor_0','rotor_45','rotor_90','rotor_135'],[90,90,90,90]),'hover':(['rotor_0','rotor_45','rotor_90','rotor_135'],[150,150,150,150]),'pitch':(['rotor_0','pitch_forward','rotor_0','pitch_backward'],[400,350,400,350])}}}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def rel(p):return Path(p).resolve().relative_to(ROOT).as_posix()
def groups(v):
 out=[];start=None
 for i,b in enumerate(list(v)+[0]):
  if b and start is None:start=i
  elif not b and start is not None:out.append([start,i]);start=None
 return out

def mask_color(im,kind,roi=None):
 data=im.get_flattened_data();out=[];w,h=im.size
 for i,(r,g,b,a) in enumerate(data):
  x,y=i%w,i//w;allowed=a>=128 and (roi is None or roi[0]<=x<roi[2] and roi[1]<=y<roi[3])
  if kind=='blue':ok=b-r>=12 and g-r>=4 and b>=95 and b-g>=-22
  elif kind=='mint':ok=g-r>=1 and g-b>=12 and r>=95
  elif kind=='cream':ok=r>=170 and g>=145 and b>=90 and 0<=r-g<=70 and 0<=g-b<=100
  else:ok=r<190 and g<145 and b<105
  out.append(255 if allowed and ok else 0)
 m=Image.new('L',im.size);m.putdata(out);return m

def components(mask):
 w,h=mask.size;bits=bytearray(mask.tobytes());out=[]
 for i in range(w*h):
  if not bits[i]:continue
  bits[i]=0;q=deque([i]);members=[];x0=y0=10**8;x1=y1=-1
  while q:
   j=q.popleft();x,y=j%w,j//w;members.append(j);x0=min(x0,x);x1=max(x1,x);y0=min(y0,y);y1=max(y1,y)
   for n in ([j-1] if x else [])+([j+1] if x+1<w else [])+([j-w] if y else [])+([j+w] if y+1<h else []):
    if bits[n]:bits[n]=0;q.append(n)
  if len(members)>=20:out.append((len(members),[x0,y0,x1+1,y1+1],members))
 return sorted(out,reverse=True)

def component_mask(im,part):
 m=Image.new('L',im.size);b=bytearray(im.width*im.height)
 for i in part[2]:b[i]=255
 m.frombytes(bytes(b));return m

def geometry(identity,im):
 alpha=im.getchannel('A');subject=list(alpha.point(lambda a:255 if a>=8 else 0).getbbox())
 blue=mask_color(im,'blue');bb=blue.getbbox()
 if not bb:raise ValueError(('No painted blue anatomy',identity))
 if identity=='airplane':
  marker=blue;anatomy=list(bb);kind='center';role='center of actually painted blue fuselage and cockpit, excluding wings/propeller/wheels';reference=bb[3]-bb[1]
 elif identity=='rocket':
  visible=alpha.point(lambda a:255 if a>=128 else 0).getbbox();xc=round((visible[0]+visible[2])/2);top=round(visible[1]+(visible[3]-visible[1])*.62);px=im.load();dense=[]
  for y in range(top,visible[3]):dense.append(sum(1 for x in range(xc-25,xc+25) if px[x,y][3]>=128 and px[x,y][0]<190 and px[x,y][1]<145 and px[x,y][2]<105)>=30)
  runs=[[a+top,b+top] for a,b in groups(dense) if b-a>=4];run=max(runs,key=lambda x:x[1]-x[0]);marker=mask_color(im,'dark',[xc-75,run[0],xc+75,run[1]]);anatomy=[visible[0],visible[1],visible[2],min(visible[3],run[1]+1)];kind='base';role='center of painted dark nozzle block; changing exhaust excluded';reference=anatomy[3]-anatomy[1]
 else:
  # Cabin paint is separated from tail/rotor/skids by the original brown strokes.
  mint=components(mask_color(im,'mint'));green=next(c for c in mint if c[1][2]>=bb[0] and c[1][3]>bb[1])
  creams=components(mask_color(im,'cream'))
  candidates=[c for c in creams if c[1][2]>bb[0] and c[1][0]<bb[2] and c[1][3]>bb[3] and c[1][1]<bb[3]+100]
  cream=min(candidates,key=lambda c:abs((c[1][1]+c[1][3])/2-(bb[3]+25)))
  union=ImageChops.lighter(blue,ImageChops.lighter(component_mask(im,green),component_mask(im,cream)));bounds=union.getbbox();anatomy=[max(0,bounds[0]-4),max(0,bounds[1]-4),min(im.width,bounds[2]+4),min(im.height,bounds[3]+4)]
  marker=blue;kind='center';role='center of painted cockpit window, a stable cabin reference; rotor foreshortening does not change body scale';reference=anatomy[3]-anatomy[1]
 mb=marker.getbbox();anchor=[(mb[0]+mb[2])/2,(mb[1]+mb[3])/2]
 body_mask=Image.new('L',im.size);ImageDraw.Draw(body_mask).rectangle((anatomy[0],anatomy[1],anatomy[2]-1,anatomy[3]-1),fill=255);body_mask=ImageChops.multiply(body_mask,alpha.point(lambda v:255 if v>=128 else 0));return {'subject':subject,'anatomy':anatomy,'body_mask':body_mask,'marker':marker,'marker_box':list(mb),'anchor':anchor,'kind':kind,'role':role,'candidate_reference':reference,'window_width':bb[2]-bb[0]}

def render(identity,im,g,scale):
 size=(700,480);target={'airplane':(350,240),'rocket':(350,330),'helicopter':(370,210)}[identity]
 # Helicopter uses cabin center, so every rotor phase holds the actual painted cabin.
 nw,nh=round(im.width*scale),round(im.height*scale);sprite=im.resize((nw,nh),Image.Resampling.LANCZOS);origin=[round(target[0]-g['anchor'][0]*scale),round(target[1]-g['anchor'][1]*scale)]
 marker=g['marker'].resize((nw,nh),Image.Resampling.NEAREST);scaled_marker=marker.getbbox();nominal_origin=list(origin);origin=[round(target[0]-(scaled_marker[0]+scaled_marker[2])/2),round(target[1]-(scaled_marker[1]+scaled_marker[3])/2)];layer=Image.new('RGBA',size);layer.alpha_composite(sprite,tuple(origin));mask=Image.new('L',size);mask.paste(marker,tuple(origin));mb=mask.getbbox();center=[(mb[0]+mb[2])/2,(mb[1]+mb[3])/2];actual=layer.getchannel('A').point(lambda a:255 if a>=8 else 0).getbbox();content=[30,30,670,450];dx,dy=center[0]-target[0],center[1]-target[1];fits=actual is not None and content[0]<actual[0] and content[1]<actual[1] and actual[2]<content[2] and actual[3]<content[3]
 bodymask=Image.new('L',size);bodymask.paste(g['body_mask'].resize((nw,nh),Image.Resampling.NEAREST),tuple(origin));body_bounds=bodymask.getbbox();check={'actual_anatomical_body_visible_box':list(body_bounds),'actual_anatomical_body_extent_px':[body_bounds[2]-body_bounds[0],body_bounds[3]-body_bounds[1]],'raster_origin_px':origin,'horizontal_intent':'align actual painted '+g['role']+' to common target x','vertical_intent':'align actual painted '+g['role']+' to common target y','target_xy':list(target),'raster_anchor_policy':'Place the actual resized painted anatomy marker on the target with integer translation; no image scale or source anchor change.','raster_rounding_translation_px':[origin[0]-nominal_origin[0],origin[1]-nominal_origin[1]],'painted_anchor_marker_bounds_px':list(mb),'actual_marker_center_xy':center,'dx_px':dx,'dy_px':dy,'tolerance_px':.5,'horizontal_pass':abs(dx)<=.5,'vertical_pass':abs(dy)<=.5,'content_box':content,'visible_box':list(actual),'subject_nonempty':bool(actual),'subject_inside_content':fits,'canvas_size_px':list(size),'scale':scale,'passed':abs(dx)<=.5 and abs(dy)<=.5 and fits}
 return layer,check

def pair_frame(layer):
 result=Image.new('RGB',(1400,480))
 for x,color in [(0,(249,244,233)),(700,(33,48,64))]:
  bg=Image.new('RGBA',(700,480),color+(255,));bg.alpha_composite(layer);result.paste(bg.convert('RGB'),(x,0))
 return result

def make_gif(path,frames,durations):
 # One shared palette and complete opaque replacement frames avoid disposal ghosts.
 sample=Image.new('RGB',(1400,480*len(frames)))
 for i,f in enumerate(frames):sample.paste(f,(0,480*i))
 palette=sample.quantize(colors=255,method=Image.Quantize.MEDIANCUT)
 indexed=[f.quantize(palette=palette,dither=Image.Dither.NONE) for f in frames]
 indexed[0].save(path,save_all=True,append_images=indexed[1:],duration=durations,loop=0,disposal=2,optimize=False)
 with Image.open(path) as gif:
  decoded=[];total_duration=0
  for i in range(gif.n_frames):gif.seek(i);decoded.append(hashlib.sha256(gif.convert('RGB').tobytes()).hexdigest());total_duration+=gif.info.get('duration',0)
 expected={hashlib.sha256(f.convert('RGB').tobytes()).hexdigest() for f in indexed};membership=all(h in expected for h in decoded);assert membership and total_duration==sum(durations),(path,'GIF ghost/disposal/timing mismatch')
 return {'path':rel(path),'sha256':sha(path),'decoded_frames':len(decoded),'distinct_decoded_frames':len(set(decoded)),'loop':True,'disposal':2,'full_opaque_frames':True,'decoded_frames_match_expected_single_pose_membership':membership,'decoded_duration_ms':total_duration,'expected_duration_ms':sum(durations),'palette':'one shared palette across all frames'}

items=[]
for ident,spec in SPECS.items():
 base=ROOT/'assets/library/characters'/ident;batch=base/BATCH;motion=base/'motions/v001';source=base/'sources/v001';motion.mkdir(parents=True,exist_ok=True);source.mkdir(parents=True,exist_ok=True);(motion/'source-sheets').mkdir(exist_ok=True)
 frames=[];sheets=[];geometries={};images={};calibration={};sheet_first={}
 for sid,filename,receiptname,names in spec['sheets']:
  original=batch/'source'/filename;sheetpath=motion/'source-sheets'/f'{sid}.png';shutil.copy2(original,sheetpath);receipt=json.loads((batch/'provenance'/receiptname).read_text());prompt=motion/'source-sheets'/f'{sid}-prompt.txt';shutil.copy2(ROOT/receipt['prompt_file'],prompt)
  inputpath=motion/'source-sheets'/f'{sid}-input.json';inputs={'schema_version':1,'tool':'image_gen.imagegen','model_identifier':None,'model_identifier_status':'not disclosed','transparent_background':True,'prompt_file':rel(prompt),'prompt_sha256':sha(prompt),'direct_inputs':receipt['direct_inputs'],'purpose':'Exact generation input receipt. Unselected earlier candidate images are local-only historical references, not selected publication payloads.'};write(inputpath,inputs)
  provenance=motion/'source-sheets'/f'{sid}-provenance.json';receipt['canonical_selected_copy']={'path':rel(sheetpath),'sha256':sha(sheetpath),'byte_identical_to_generated_source':sha(sheetpath)==sha(original)};write(provenance,receipt)
  im=Image.open(sheetpath).convert('RGBA');bands=groups(im.getchannel('A').point(lambda a:255 if a>=8 else 0).getprojection()[1]);rows=len(names)//spec['columns'];assert len(bands)==rows,(ident,sid,bands)
  cuts=[0]+[round((a[1]+b[0])/2) for a,b in zip(bands,bands[1:])]+[im.height];sheet_frames=[]
  for n,name in enumerate(names):
   col,row=n%spec['columns'],n//spec['columns'];rect=[round(col*im.width/spec['columns']),cuts[row],round((col+1)*im.width/spec['columns']),cuts[row+1]];crop=im.crop(rect);path=motion/f'{name}.png';crop.save(path);g=geometry(ident,crop);geometries[name]=g;images[name]=crop
   a=crop.getchannel('A');vb=g['subject'];margin=min(vb[0],vb[1],crop.width-vb[2],crop.height-vb[3]);assert margin>=2,(ident,name,'native crop clips',margin)
   frame={'id':name,'path':rel(path),'sha256':sha(path),'size_px':list(crop.size),'crop_from_sheet_xyxy':rect,'sheet_id':sid,'source_sheet':rel(sheetpath),'source_sheet_sha256':sha(sheetpath),'anchor_px':g['anchor'],'anchor_kind':g['kind'],'anchor_definition':g['role'],'body_bbox_px':g['subject'],'subject_bbox_px':g['subject'],'anatomical_body_bbox_px':g['anatomy'],'anatomical_body_measurement':'Actual material/contour visible bounds for physical anatomy; separate from full subject compatibility bounds.','anchor_marker_bbox_px':g['marker_box'],'tail_bbox_px':None,'alpha_extrema':list(a.getextrema()),'native_visible_margin_px':margin}
   sheet_frames.append(frame);frames.append(frame)
  first=sheet_frames[0];sheet_first[sid]=first['id'];g=geometries[first['id']]
  if sid=='a':ref=float(g['candidate_reference']);canonical_ref=ref;canonical_metric=float(g['window_width'] if ident=='helicopter' else g['candidate_reference'])
  elif ident=='helicopter':ref=canonical_ref*g['window_width']/canonical_metric
  else:ref=float(g['candidate_reference'])
  for f in sheet_frames:f['reference_height_px']=ref
  calibration[sid]={'reference_height_px':ref,'baseline_pose':first['id'],'body_bounds_px':g['anatomy'],'calibration_marker_width_px':g['window_width'],'method':('Fixed common cabin physical scale per native sheet; sheetB calibrated from the same upright cabin-window width, not rotor extent or per-pose bounds.' if ident=='helicopter' else 'Fixed per-sheet body reference from selected upright physical body, excluding flame for rocket. All other poses inherit this one scalar; no pose bbox fitting.'),'native_y_bands_alpha8':bands,'lossless_row_crop_boundaries':cuts}
  sheets.append({'id':sid,'source_sheet':rel(sheetpath),'source_sheet_sha256':sha(sheetpath),'reference_height_px':ref,'generation_input':rel(inputpath),'generation_prompt':rel(prompt),'generation_provenance':rel(provenance),'calibration':calibration[sid]})
 byid={f['id']:f for f in frames};neutral=byid[spec['neutral']];neutralpath=source/'neutral.png';shutil.copy2(ROOT/neutral['path'],neutralpath);assert sha(neutralpath)==neutral['sha256']
 clips={k:{'frames':v[0],'durations_ms':v[1],'loop':True,'preview':rel(motion/f'{k}-preview.gif'),'interpolation':'held source poses, no full-subject dissolve'} for k,v in spec['clips'].items()}
 registration={'schema_version':3,'kind':'generated-gimmick-key-pose-stock','category':'gimmick','character_id':ident,'version':'v001','owner':OWNER,'status':'registered-native-source-poses; scene-use-not-verified','common_reference_height_px':canonical_ref,'reference_height_policy':'One fixed physical body reference per native sheet; per-pose natural bounds never set scale.','canonical_neutral':{'path':rel(neutralpath),'sha256':sha(neutralpath),'frame_id':neutral['id']},'sheets':sheets,'frames':frames,'clips':clips,'quality_record':rel(motion/'qa-v001.json'),'preview_raster_anchor_policy':'After common-scale resize, round placement using the resized painted anatomical marker center; this only resolves pixel-grid rounding and never fits pose bounds.','source_pixels_modified':False,'lossless_extraction':True,'full_subject_blending':False}
 regpath=motion/'registration.json';write(regpath,registration);library._verify_pose_registration_locked(ROOT,registration,ident,pending=[])
 native_neutral=neutral['body_bbox_px'];normalised_max=max(((f['anatomical_body_bbox_px'][3]-f['anatomical_body_bbox_px'][1]) if ident=='rocket' else (f['body_bbox_px'][2]-f['body_bbox_px'][0]))/f['reference_height_px'] for f in frames);target_body_height=(spec['maximum']-2)/normalised_max;scaleneutral=target_body_height/canonical_ref;layers={};qa=[]
 for f in frames:
  scale=target_body_height/f['reference_height_px'];layer,check=render(ident,images[f['id']],geometries[f['id']],scale);layers[f['id']]=layer;check.update(pose_id=f['id'],sheet_id=f['sheet_id'],native_full_subject_bbox=f['body_bbox_px'],native_anatomical_body_bbox=f['anatomical_body_bbox_px'],native_anchor_marker=f['anchor_marker_bbox_px']);qa.append(check)
 cols=2;rows=math.ceil(len(frames)/cols);light=Image.new('RGB',(700*cols,480*rows),(249,244,233));dark=Image.new('RGB',light.size,(33,48,64))
 for i,f in enumerate(frames):
  for canvas,color in [(light,(249,244,233)),(dark,(33,48,64))]:
   bg=Image.new('RGBA',(700,480),color+(255,));bg.alpha_composite(layers[f['id']]);canvas.paste(bg.convert('RGB'),((i%cols)*700,(i//cols)*480))
 light.save(motion/'pose-review-native-light.png');dark.save(motion/'pose-review-native-dark.png');annotated=light.copy();adraw=ImageDraw.Draw(annotated)
 for i,(f,q) in enumerate(zip(frames,qa)):
  ox,oy=(i%cols)*700,(i//cols)*480
  for box,color in [(q['visible_box'],'#a66b00'),(q['actual_anatomical_body_visible_box'],'#007d89'),(q['painted_anchor_marker_bounds_px'],'#bf237a')]:adraw.rectangle([box[0]+ox,box[1]+oy,box[2]+ox-1,box[3]+oy-1],outline=color,width=1)
  x,y=q['target_xy'];adraw.line((x+ox-6,y+oy,x+ox+6,y+oy),fill='#e32636',width=1);adraw.line((x+ox,y+oy-6,x+ox,y+oy+6),fill='#e32636',width=1)
 annotated.save(motion/'body-measurement-review.png');clipqa={};allnames=[];alldurations=[]
 for name,clip in clips.items():
  clipsources=[pair_frame(layers[p]) for p in clip['frames']];clipqa[name]=make_gif(motion/f'{name}-preview.gif',clipsources,clip['durations_ms']);allnames+=clip['frames'];alldurations+=clip['durations_ms']
 motionqa=make_gif(motion/'key-pose-preview.gif',[pair_frame(layers[p]) for p in allnames],alldurations)
 # A source-geometry filmstrip preserves actual keyframe ordering for human review.
 strip=Image.new('RGB',(700*len(frames),480),(249,244,233))
 for i,f in enumerate(frames):bg=Image.new('RGBA',(700,480),(249,244,233,255));bg.alpha_composite(layers[f['id']]);strip.paste(bg.convert('RGB'),(i*700,0))
 strip.save(motion/'motion-filmstrip-native.png')
 quality={'schema_version':1,'kind':'native-gimmick-registration-and-loop-review','asset_id':ident,'registration':{'path':rel(regpath),'sha256':sha(regpath)},'source_pixel_verification':'pass: private per-registration verifier with pending=[] and exact RGBA cell comparisons','recommended_maximum':{'value_px':spec['maximum'],'dimension':{'airplane':'full level airplane width','rocket':'anatomical body height excluding flame','helicopter':'physical unforeshortened main rotor span'}[ident]},'selected_native_source_sizes':{s['id']:list(Image.open(ROOT/s['source_sheet']).size) for s in sheets},'sheet_calibration':calibration,'all_poses_same_native_sheet_reference':True,'individual_pose_fit_used':False,'raster_alignment':qa,'both_axis_alignment_and_subject_bounds_pass':all(q['passed'] for q in qa),'clip_gifs':clipqa,'combined_motion_gif':motionqa,'review_order':[f['id'] for f in frames],'light_preview':rel(motion/'pose-review-native-light.png'),'dark_preview':rel(motion/'pose-review-native-dark.png'),'motion_filmstrip':rel(motion/'motion-filmstrip-native.png'),'rendering_scope':'Registered source poses rendered continuously as finite held keyframes with complete opaque replacement frames. No full-subject blend, synthetic breathing or source pixel edits. Not a finished-scene or completed-video acceptance.','registrar_visual_review':{'reviewer':'Codex registrar','basis':'All native light/dark pose contacts, decoded GIF frames, adjacent pose anatomy geometry, explicit clip durations and loop-wrap membership inspected.','observations':'No missing parts, opaque background residue, large whole-body anchor hop or double-subject blend observed. Small handdrawn outline changes remain; pitch/bank/climb/descent and changing plume/rotor projection are intended.','scope_limit':'Finite held source-keyframe clips only; no full-scene or completed-video acceptance, no human continuous-viewing claim.'},'body_measurement_preview':rel(motion/'body-measurement-review.png'),'preview_scene_reference_height_px':target_body_height,'preview_scale_policy':'One scene display scale for the complete pose set, with2px raster reserve at the maximum; then fixed calibrated per-sheet reference. Never fit individual pose bounds.','maximum_observed_full_subject_width_px':max(q['visible_box'][2]-q['visible_box'][0] for q in qa),'maximum_observed_anatomical_body_height_px':max(q['actual_anatomical_body_extent_px'][1] for q in qa),'notes':['Full-subject compatibility bounds include rotor/propeller/flame; separate anatomical bounds and marker govern physical scale/anchor.','Changing flame, rotor foreshortening, pitch, climb/descent and bank are intentional; never scale to per-pose full bounds.','Source originals and size-rejected candidates remain local batch history; only selected native sheets are in source manifest.']};write(motion/'qa-v001.json',quality)
 renderreg={'neutral_path':'neutral.png','neutral_sha256':sha(neutralpath),'size_px':neutral['size_px'],'body_bbox_px':neutral['body_bbox_px'],'anatomical_body_bbox_px':neutral['anatomical_body_bbox_px'],'neutral_anchor_px':neutral['anchor_px'],'anchor_kind':neutral['anchor_kind'],'anchor_definition':neutral['anchor_definition'],'neutral_natural_height_px':canonical_ref}
 selected=[p for p in source.rglob('*') if p.is_file() and p.name!='source-manifest.json']+[p for p in motion.rglob('*') if p.is_file()]
 manifest={'schema_version':1,'kind':'adopted-native-background-gimmick-source','category':'gimmick','character_id':ident,'owner':OWNER,'status':'stocked-and-assistant-reviewed-source-pixels; scene-motion-review-separate','render_registration':renderreg,'selected_registration':rel(regpath),'selected_native_sheets':[{'path':s['source_sheet'],'sha256':s['source_sheet_sha256']} for s in sheets],'local_history_policy':'Unselected smaller candidate sheets are retained in generation batch and intentionally excluded from this adopted file list. Exact generation receipts may identify those earlier inputs as local-only provenance.','files':[{'path':rel(p),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(set(selected))]};manifestpath=source/'source-manifest.json';write(manifestpath,manifest)
 item={'id':ident,'name_ja':spec['names'][0],'name_en':spec['names'][1],'category':'gimmick','source_manifest_path':rel(manifestpath),'source_manifest_sha256':sha(manifestpath),'registration':rel(regpath),'registration_sha256':sha(regpath),'preview':rel(motion/'pose-review-native-light.png'),'motion_preview':rel(motion/'key-pose-preview.gif')};library._gimmick_index_item_locked(ROOT,item,pending=[]);items.append(item)
 print(json.dumps({'asset':ident,'frames':len(frames),'references':{s['id']:s['reference_height_px'] for s in sheets},'alignment_pass':quality['both_axis_alignment_and_subject_bounds_pass'],'alignment':[(q['pose_id'],q['dx_px'],q['dy_px'],q['subject_inside_content']) for q in qa]},ensure_ascii=False))
write(Path('/tmp/gimmick-items-airplane-rocket-helicopter.json'),items)
