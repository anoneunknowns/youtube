"""Focused reader-contract tests for the optional two-pattern species collection."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from tests import test_character_stock_supplement as stock_fixtures
from tools import character_library as library, unified_asset_library as unified
original=library

class SpeciesCandidateTests(unittest.TestCase):
 def setUp(self):
  self.fixture=stock_fixtures.CharacterStockSupplementTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
  self.root=self.fixture.root
  for identity in ('bear-small','hamster','rabbit-flower','cream-companion','cat-patches'):self.fixture.add_stock(identity)
  self.before=original.build_index(self.root)
  extras=patch.object(library,'EXTRAS',list(original.EXTRAS));extras.start();self.addCleanup(extras.stop)
 def add_species(self,identity='pika'):
  base=f'assets/library/characters/{identity}/generation-batches/species-fixture/'
  source=base+'source/neutral.png';self.fixture.fixture.save_image(source,self.fixture.fixture.subject())
  prompt=base+'provenance/prompt.txt';(self.root/prompt).parent.mkdir(parents=True);(self.root/prompt).write_text('synthetic neutral-only fixture\n')
  review=base+'qa-review.json';self.fixture.fixture.write_json(review,{'status':'pass','scope':'unit-test fixture'})
  manifest=base+'source-manifest.json';self.fixture.fixture.write_json(manifest,{'files':[{'path':source},{'path':prompt},{'path':review}]})
  self.review=review
  self.item={'id':identity,'category':'character','style_pattern':'slightly-anthropomorphic-character','usage_role':'cast-character','taxonomy':{'scientific_name':'Ochotona hyperborea','taxon_precision':'species'},'name_ja':'ナキウサギ','name_en':'Pika','neutral':{'path':source,'sha256':library.sha(self.root/source),'source_size_px':[24,24],'image_region_px':[0,0,24,24],'body_bbox_px':[8,6,16,20],'anchor_px':[12,20],'reference_height_px':14,'anchor_kind':'anatomical-support','source_manifest':manifest,'source_manifest_sha256':library.sha(self.root/manifest)}}
  self.collection()
  return self.item
 def collection(self,status='stocked-and-assistant-reviewed'):
  self.fixture.fixture.write_json(library.SPECIES,{'schema_version':1,'status':status,'review_evidence':[{'path':self.review,'sha256':library.sha(self.root/self.review)}],'items':[self.item]})
 def test_absent_species_collection_preserves_all_current_entries(self):
  self.assertEqual(library.build_index(self.root),self.before)
  self.assertEqual(len(self.before['characters']),24)
 def test_neutral_only_addition_preserves_legacy_selection_and_emits_same_native_png(self):
  item=self.add_species();index=library.build_index(self.root)
  self.assertEqual(index['characters'][:24],self.before['characters'])
  self.assertEqual(index['characters'][-1]['supplemental_collection'],library.SPECIES)
  library.refresh(self.root);self.assertEqual(library.verify(self.root)['characters'],25)
  self.assertEqual(unified.build(self.root)['assets'],25);self.assertEqual(unified.verify(self.root)['assets'],25)
  current=self.root/'assets/library/characters/pika/current'
  self.assertEqual((current/'neutral.png').read_bytes(),(self.root/item['neutral']['path']).read_bytes())
  self.assertEqual(json.loads((current/'asset.json').read_bytes())['poses'],{})
  self.assertEqual(json.loads((current/'clips.json').read_bytes())['clips'],{})
  required=library._required_current_library_paths_locked(self.root,[])
  self.assertTrue({library.SPECIES,self.review,item['neutral']['path'],item['neutral']['source_manifest'],'assets/library/characters/pika/generation-batches/species-fixture/provenance/prompt.txt'}<=required)
 def test_species_cannot_replace_existing_identity(self):
  self.add_species('bear-small')
  with self.assertRaisesRegex(ValueError,'must not replace'):library.build_index(self.root)
 def test_unreviewed_or_changed_qa_fails_closed(self):
  self.add_species();self.collection('generating')
  with self.assertRaisesRegex(ValueError,'explicitly reviewed'):library.build_index(self.root)
  self.collection();(self.root/self.review).write_text('changed')
  with self.assertRaisesRegex(ValueError,'review evidence changed'):library.build_index(self.root)
 def test_active_writer_cannot_be_selected_and_opaque_image_rejected(self):
  self.add_species();batch=str(Path(self.item['neutral']['path']).parent.parent)
  self.fixture.fixture.write_json(library.MANAGEMENT,{'schema_version':1,'batches':[],'reservations':[{'id':'writer','owner':'other-agent','status':'active','root':batch}]})
  with self.assertRaisesRegex(ValueError,'active generation tree'):library.build_index(self.root)
  self.fixture.fixture.write_json(library.MANAGEMENT,{'schema_version':1,'batches':[],'reservations':[]})
  from PIL import Image
  Image.new('RGBA',(24,24),(100,80,60,255)).save(self.root/self.item['neutral']['path'])
  self.item['neutral']['sha256']=library.sha(self.root/self.item['neutral']['path']);self.collection()
  with self.assertRaisesRegex(ValueError,'empty, opaque or clipped'):library.build_index(self.root)
 def test_prop_metadata_survives_index_asset_and_master_without_invented_feet(self):
  item=self.add_species('bitterling')
  item.update(category='gimmick',style_pattern='bird-like-prop',usage_role='background-animal-prop',taxonomy={'scientific_name':'Rhodeus atremius atremius','taxon_precision':'subspecies'})
  item['neutral'].update(anchor_px=[12,12],anchor_kind='anatomical-body-center')
  self.collection();library.refresh(self.root);unified.build(self.root);self.assertEqual(unified.verify(self.root)['assets'],25)
  index=library.read(self.root/library.INDEX)['characters'][-1]
  asset=library.read(self.root/'assets/library/characters/bitterling/current/asset.json')
  master=library.read(self.root/unified.MASTER)['assets'][-1]
  for obj in (index,asset,master):
   self.assertEqual(obj['category'],'gimmick');self.assertEqual(obj['style_pattern'],'bird-like-prop');self.assertEqual(obj['usage_role'],'background-animal-prop');self.assertEqual(obj['taxonomy'],item['taxonomy'])
  self.assertEqual(asset['neutral']['anchor_px'],[12,12]);self.assertEqual(asset['poses'],{})
 def test_unknown_or_mismatched_style_role_is_not_adopted(self):
  item=self.add_species()
  for edit in ({'style_pattern':'natural-zoology'}, {'style_pattern':'bird-like-prop'}, {'category':'gimmick'}, {'usage_role':'unknown'}):
   original_item=dict(item);item.update(edit);self.collection()
   with self.assertRaisesRegex(ValueError,'approved style pattern'):library.build_index(self.root)
   item.clear();item.update(original_item)
if __name__=='__main__':unittest.main()
