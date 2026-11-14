"""Synthetic fixtures for accepted video key-pose registration and reader integration."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
from tools import character_library as library
from tools import unified_asset_library as unified


class YouTubeStockTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='youtube-stock-');self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.items=[]
  for key,value in [('NAMES',{}),('EXTRAS',[library.MANAGEMENT,library.INDEX,library.STOCK,library.MOTIONS,library.STYLE]),('OPTIONAL_EXTRAS',[]),('SCOPES',['assets/library/characters','assets/library/collections'])]:
   p=patch.object(library,key,value);p.start();self.addCleanup(p.stop)
  self.write(library.MANAGEMENT,{'schema_version':1,'batches':[],'reservations':[]})
  for p,v in [(library.STOCK,{'items':[]}),(library.MOTIONS,{'items':[]}),(library.STYLE,{'records':[]})]:self.write(p,v)
  self.species=[]
  for identity,prop in [('pika',False),('bitterling',True)]:
   base=f'assets/library/characters/{identity}/generation-batches/species-fixture/'
   image=Image.new('RGBA',(24,24));ImageDraw.Draw(image).rectangle((8,6,15,19),fill='orange')
   path=base+'neutral.png';self.image(path,image)
   qa=base+'qa.json';self.write(qa,{'status':'pass','scope':'synthetic unit fixture'})
   sm=base+'source-manifest.json';self.write(sm,{'files':[{'path':path},{'path':qa}]})
   neutral={'path':path,'sha256':self.sha(path),'source_size_px':[24,24],'image_region_px':[0,0,24,24],'body_bbox_px':[8,6,16,20],'anchor_px':[12,12] if prop else [12,20],'reference_height_px':14,'anchor_kind':'anatomical-body-center' if prop else 'drawn-ground-contact','anchor_measurement':'synthetic fixture','vertical_motion_policy':'no-invented-feet' if prop else 'grounded-support','source_manifest':sm,'source_manifest_sha256':self.sha(sm)}
   self.species.append({'id':identity,'name_ja':identity,'name_en':identity,'category':'gimmick' if prop else 'character','style_pattern':'bird-like-prop' if prop else 'slightly-anthropomorphic-character','usage_role':'background-animal-prop' if prop else 'cast-character','taxonomy':{'scientific_name':'Fixture test species'},'neutral':neutral})
  self.species_review='assets/library/collections/animal-species-stock/v001/qa.json';self.write(self.species_review,{'status':'pass','scope':'synthetic'})
  self.write(library.SPECIES,{'schema_version':1,'status':'stocked-and-assistant-reviewed','items':self.species,'review_evidence':[{'path':self.species_review,'sha256':self.sha(self.species_review)}]})
  self.before=library.build_index(self.root)
  self.review='assets/library/collections/youtube-basic-stock/v001/qa.json';self.write(self.review,{'status':'pass','scope':'synthetic coverage; no art quality claim'})
 def write(self,path,data):library.write(self.root/path,data)
 def image(self,path,image):p=self.root/path;p.parent.mkdir(parents=True,exist_ok=True);image.save(p)
 def sha(self,path):return library.sha(self.root/path)
 def collection(self,status='stocked-and-assistant-reviewed'):
  self.write(library.YOUTUBE,{'schema_version':1,'status':status,'items':self.items,'review_evidence':[{'path':self.review,'sha256':self.sha(self.review)}]})
 def add_video(self,identity='pika'):
  parent=next(x for x in self.before['characters'] if x['id']==identity);neutral=parent['neutral'];base=f'assets/library/characters/{identity}/generation-batches/youtube-fixture/'
  names=['blink','greet','present_left','present_right','think','aha','cheer','species_a','species_b']
  sheet=Image.new('RGBA',(72,72));frames=[]
  for i,name in enumerate(names):
   cell=Image.new('RGBA',(24,24));ImageDraw.Draw(cell).rectangle((8,6,15,19),fill=(50+i*17,80,170,255));sheet.paste(cell,((i%3)*24,(i//3)*24));path=base+'poses/'+name+'.png';self.image(path,cell)
   frames.append({'id':name,'index':i,'path':path,'sha256':self.sha(path),'size_px':[24,24],'sheet_id':'basic','source_sheet':base+'source/basic.png','crop_from_sheet_xyxy':[(i%3)*24,(i//3)*24,(i%3+1)*24,(i//3+1)*24],'body_bbox_px':[8,6,16,20],'anchor_px':copy.deepcopy(neutral['anchor_px']),'anchor_kind':neutral['anchor_kind'],'tail_bbox_px':None,'reference_height_px':14})
  self.image(base+'source/basic.png',sheet);checksum=self.sha(base+'source/basic.png')
  for f in frames:f['source_sheet_sha256']=checksum
  alias=copy.deepcopy(neutral);alias.update(id='neutral',index=0,size_px=neutral['source_size_px'],sheet_id='canonical-neutral',source_sheet=neutral['path'],source_sheet_sha256=neutral['sha256'],crop_from_sheet_xyxy=[0,0,*neutral['source_size_px']],tail_bbox_px=None)
  registration={'schema_version':1,'kind':'video-character-native-pose-registration','character_id':identity,'version':'v001','status':'stocked-and-assistant-reviewed','registration_candidate_only':False,'current_adoption':True,'canonical_neutral':copy.deepcopy(neutral),'sheets':[{'id':'canonical-neutral','source_sheet':neutral['path'],'source_sheet_sha256':neutral['sha256'],'reference_height_px':14},{'id':'basic','source_sheet':base+'source/basic.png','source_sheet_sha256':checksum,'reference_height_px':14}],'frames':[alias,*frames],'clips':{name:{'frames':frames,'durations_ms':[400]*len(frames),'loop':False} for name,frames in {'idle_blink':['neutral','blink','neutral'],'greeting':['neutral','greet','neutral'],'presentation_left':['neutral','present_left','neutral'],'presentation_right':['neutral','present_right','neutral'],'thinking_discovery':['neutral','think','aha','neutral'],'celebration':['neutral','cheer','neutral'],'species_motion':['neutral','species_a','species_b','neutral']}.items()},'scale_policy':'One calibration per source sheet; no per-pose bbox fitting.'}
  rp=base+'registration.json';self.write(rp,registration)
  item={'id':identity,'neutral_reference':{k:neutral[k] for k in ('path','sha256')},'pose_sets':[{'namespace':'video','registration':rp,'registration_sha256':self.sha(rp)}]};self.items.append(item);self.collection();return item
 def edit(self,item,change):
  ref=item['pose_sets'][0];reg=library.read(self.root/ref['registration']);change(reg);self.write(ref['registration'],reg);ref['registration_sha256']=self.sha(ref['registration']);self.collection()
 def test_absent_collection_is_exact_noop(self):self.assertEqual(library.build_index(self.root),self.before)
 def test_cast_and_prop_add_video_without_changing_identity_neutral_or_prior_provenance(self):
  for identity in ['pika','bitterling']:self.add_video(identity)
  after=library.build_index(self.root)
  for old,new in zip(self.before['characters'],after['characters']):
   stripped=copy.deepcopy(new);self.assertEqual(len(stripped.pop('pose_sets')),1);self.assertEqual(stripped,old)
   self.assertEqual(set(new['pose_sets'][0]['poses']),library.VIDEO_POSES)
  self.assertIn(library.YOUTUBE,{x['path'] for x in after['source_collections']})
 def test_current_png_clip_loader_and_closure_use_same_namespace(self):
  for identity in ['pika','bitterling']:self.add_video(identity)
  library.write(self.root/library.INDEX,library.build_index(self.root));unified.build(self.root);library.refresh(self.root)
  self.assertEqual(library.verify(self.root)['characters'],2);self.assertEqual(unified.verify(self.root)['assets'],2)
  for old in self.before['characters']:
   current=self.root/f'assets/library/characters/{old["id"]}/current';asset=library.read(current/'asset.json');clips=library.read(current/'clips.json')
   self.assertEqual((current/'neutral.png').read_bytes(),(current/'poses/video/neutral.png').read_bytes())
   self.assertEqual((current/'neutral.png').read_bytes(),(self.root/old['neutral']['path']).read_bytes())
   self.assertEqual(len(asset['poses']),10);self.assertEqual(len(clips['clips']),7)
   self.assertEqual(asset['category'],old['category']);self.assertEqual(asset['neutral']['anchor_px'],old['neutral']['anchor_px'])
   image,anchor,ref=library.load_pose(self.root,old['id'],'video/present_right');self.assertEqual(ref,14);self.assertEqual(anchor,old['neutral']['anchor_px'])
  required=library._required_current_library_paths_locked(self.root,[]);self.assertTrue({library.YOUTUBE,self.review}<=required)
 def test_new_identity_or_canonical_replacement_is_forbidden(self):
  item=self.add_video();item['id']='unknown';self.collection()
  with self.assertRaisesRegex(ValueError,'existing identity'):library.build_index(self.root)
  item['id']='pika';item['neutral']=copy.deepcopy(self.species[0]['neutral']);self.collection()
  with self.assertRaisesRegex(ValueError,'existing identity'):library.build_index(self.root)
 def test_missing_one_direction_or_wrong_namespace_is_rejected(self):
  item=self.add_video();self.edit(item,lambda x:x['frames'].__setitem__(slice(None),[f for f in x['frames'] if f['id']!='present_right']));self.edit(item,lambda x:x['clips'].pop('presentation_right'))
  with self.assertRaisesRegex(ValueError,'all nine'):library.build_index(self.root)
  item['pose_sets'][0]['namespace']='app';self.collection()
  with self.assertRaisesRegex(ValueError,'one video namespace'):library.build_index(self.root)
 def test_same_png_with_changed_canonical_anchor_semantics_is_rejected(self):
  item=self.add_video('bitterling');self.edit(item,lambda x:x['frames'][0].update(anchor_kind='invented-feet'))
  with self.assertRaisesRegex(ValueError,'canonical geometry'):library.build_index(self.root)
 def test_individual_bbox_fitting_and_pixel_repaint_are_rejected(self):
  item=self.add_video();self.edit(item,lambda x:x['frames'][1].update(reference_height_px=13))
  with self.assertRaisesRegex(ValueError,'scale changed'):library.build_index(self.root)
  self.edit(item,lambda x:x['frames'][1].update(reference_height_px=14));reg=library.read(self.root/item['pose_sets'][0]['registration']);path=reg['frames'][1]['path'];image=Image.open(self.root/path).copy();image.putpixel((8,6),(0,255,0,255));self.image(path,image)
  self.edit(item,lambda x:x['frames'][1].update(sha256=self.sha(path)))
  with self.assertRaisesRegex(ValueError,'pixels changed'):library.build_index(self.root)
 def test_unreviewed_registration_and_collection_or_changed_qa_are_rejected(self):
  item=self.add_video();self.edit(item,lambda x:x.update(status='candidate'))
  with self.assertRaisesRegex(ValueError,'must be reviewed'):library.build_index(self.root)
  self.edit(item,lambda x:x.update(status='stocked-and-assistant-reviewed'));self.collection('generating')
  with self.assertRaisesRegex(ValueError,'explicitly reviewed'):library.build_index(self.root)
  self.collection();self.write(self.review,{'status':'changed'})
  with self.assertRaisesRegex(ValueError,'review evidence changed'):library.build_index(self.root)
 def test_adoption_flags_must_be_explicit_booleans(self):
  item=self.add_video()
  for key,correct in [('registration_candidate_only',False),('current_adoption',True)]:
   for bad in [None,not correct,0 if correct else 1]:
    self.edit(item,lambda x:x.update({key:bad}))
    with self.assertRaisesRegex(ValueError,'must be reviewed'):library.build_index(self.root)
   self.edit(item,lambda x:x.update({key:correct}))
   self.edit(item,lambda x:x.pop(key))
   with self.assertRaisesRegex(ValueError,'must be reviewed'):library.build_index(self.root)
   self.edit(item,lambda x:x.update({key:correct}))
 def test_active_generation_root_cannot_be_adopted(self):
  item=self.add_video();self.write(library.MANAGEMENT,{'schema_version':1,'batches':[],'reservations':[{'id':'writer','owner':'other','status':'active','root':str(Path(item['pose_sets'][0]['registration']).parent)}]})
  with self.assertRaisesRegex(ValueError,'active generation tree'):library.build_index(self.root)

 def test_missing_clip_or_swapped_direction_recipe_is_rejected(self):
  item=self.add_video();self.edit(item,lambda x:x['clips'].pop('presentation_right'))
  with self.assertRaisesRegex(ValueError,'all seven'):library.build_index(self.root)
  self.edit(item,lambda x:x['clips'].update(presentation_right={'frames':['neutral','present_left','neutral'],'durations_ms':[400,400,400],'loop':False}))
  with self.assertRaisesRegex(ValueError,'named roles'):library.build_index(self.root)
 def test_loop_flag_must_be_explicit_boolean(self):
  item=self.add_video()
  for bad in [None,0,1,'false']:
   self.edit(item,lambda x:x['clips']['idle_blink'].update(loop=bad))
   with self.assertRaisesRegex(ValueError,'boolean loop'):library.build_index(self.root)
  self.edit(item,lambda x:x['clips']['idle_blink'].pop('loop'))
  with self.assertRaisesRegex(ValueError,'boolean loop'):library.build_index(self.root)
  self.edit(item,lambda x:x['clips']['idle_blink'].update(loop=False));library.build_index(self.root)

 def test_clip_timing_requires_one_positive_integer_duration_per_frame(self):
  item=self.add_video();self.edit(item,lambda x:x['clips']['idle_blink'].update(durations_ms=[900,True,900]))
  with self.assertRaisesRegex(ValueError,'positive millisecond'):library.build_index(self.root)
  self.edit(item,lambda x:x['clips']['idle_blink'].update(durations_ms=[900,160]))
  with self.assertRaisesRegex(ValueError,'positive millisecond'):library.build_index(self.root)


if __name__ == '__main__':
 unittest.main(verbosity=2)
