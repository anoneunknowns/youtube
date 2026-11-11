"""Negative controls for the seed/fade gap and F20 size-transition revision."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from PIL import Image,ImageDraw,ImageFont
from tools import verify_fibonacci_intro_seed as seed
from tools import verify_fibonacci_video_v003 as v3
from tools import verify_fibonacci_motion_v003 as actor
from tests import test_fibonacci_motion_v002 as old_motion_tests

def draw_centered(image,text,size,field,color,dx=0,dy=0):
    font=ImageFont.truetype(str(seed.independent.FONT),size);box=font.getbbox(text)
    x=round((field[0]+field[2]-box[0]-box[2])/2)+dx
    y=round((field[1]+field[3]-box[1]-box[3])/2)+dy
    ImageDraw.Draw(image).text((x,y),text,font=font,fill=color)

def spawned_override_probe():
    original=seed.independent.count_labels
    with v3.v003_labels():inside=seed.independent.count_labels is v3.count_labels
    return inside,seed.independent.count_labels is original

class SeedNegativeControls(unittest.TestCase):
    def row(self,term=False):
        return dict(id='seed-term-0' if term else 'seed-value-0',text='F0 · FIRST TERM' if term else '0',
                    size=27 if term else 130,field=(100,100,500,400),observation=(80,80,520,420),
                    color=seed.independent.BLUE,fill=seed.independent.PALE)
    def picture(self,row,text=None,dx=0,dy=0):
        image=Image.new('RGB',seed.independent.SIZE,seed.independent.PALE)
        draw_centered(image,text or row['text'],row['size'],row['field'],row['color'],dx,dy);return image
    def test_wrong_zero_one_and_wrong_F_index_rejected(self):
        for term,wrong in [(False,'1'),(True,'F1 · FIRST TERM'),(True,'F0 · SECOND TERM')]:
            row=self.row(term)
            self.assertTrue(seed.inspect(self.picture(row),[row],1)[0]['passed'])
            self.assertFalse(seed.inspect(self.picture(row,wrong),[row],1)[0]['passed'])
    def test_each_axis_is_independently_required(self):
        row=self.row()
        for dx,dy in [(5,0),(0,5),(-5,5)]:
            report=seed.inspect(self.picture(row,dx=dx,dy=dy),[row],1)[0]
            self.assertFalse(report['passed'])
    def test_empty_and_clipped_observation_are_rejected(self):
        row=self.row();blank=Image.new('RGB',seed.independent.SIZE,seed.independent.PALE)
        with self.assertRaisesRegex(ValueError,'empty component'):seed.inspect(blank,[row],1)
        image=self.picture(row);row['observation']=(300,80,520,420)
        report=seed.inspect(image,[row],1)[0]
        self.assertFalse(report['passed']);self.assertTrue(report['touches_measurement_edge'])
    def test_end_flash_does_not_pass_as_a_fade(self):
        plan={'duration_frames':90,'duration_s':3.}
        dark=Image.new('RGB',seed.independent.SIZE,'#344659');cream=Image.new('RGB',seed.independent.SIZE,seed.CREAM)
        def frames(video,ffmpeg,log,divisor,selected):
            for n in selected:yield n,(cream if n==89 else dark)
        with tempfile.TemporaryDirectory() as folder,patch.object(seed.independent.media,'decoded_frames',frames):
            report=seed.fade_checks('unused',plan,'unused',Path(folder))
            self.assertFalse(report['passed']);self.assertTrue(report['endpoint_uniform_and_cream'])

class TransferRevisionControls(unittest.TestCase):
    def test_only_F20_moving_numerals_shrink(self):
        for n in (19,20,21):
            original=v3.ORIGINAL_COUNT_LABELS(n,'transfer',.5);updated=v3.count_labels(n,'transfer',.5)
            for a,b in zip(original,updated):
                if n==20 and a['name'] in ('transferred-0','transferred-1'):
                    self.assertEqual(b['size'],68)
                    self.assertEqual({k:v for k,v in a.items() if k!='size'},{k:v for k,v in b.items() if k!='size'})
                else:self.assertEqual(a,b)
    def test_quantized_smooth_progress_has_no_second_easing(self):
        state={'transfer_start_s':10.,'transfer_end_s':11.2}
        p=v3.independent_progress(state,10.3)
        self.assertEqual(p,5/30);self.assertEqual(v3.transition_size(20,p),81)
        self.assertEqual(v3.transition_size(20,0),88);self.assertEqual(v3.transition_size(20,1),47)
        sizes=[v3.transition_size(20,i/30) for i in range(31)]
        self.assertTrue(all(a>=b for a,b in zip(sizes,sizes[1:])))
    def test_held_old_font_fails_finished_glyph_match(self):
        state={'index':20,'transfer_start_s':0.,'transfer_end_s':1.2}
        rows=v3.count_labels(20,'transfer',1);image=seed.independent.transfer_windows_background().copy()
        for row in rows:
            if not row['name'].startswith('transferred-'):continue
            if row['name'] in ('transferred-0','transferred-1'):
                field=row['field'];ImageDraw.Draw(image).rectangle(field,fill=seed.independent.PALE)
                draw_centered(image,row['text'],88,field,row['color'])
            else:draw_centered(image,row['text'],row['size'],row['field'],row['color'])
        report=v3.check_transfer_frame(image,state,36)
        observed=next(c for c in report['components'] if c['name'].endswith('/transferred-0'))
        self.assertFalse(observed['passed']);self.assertEqual(observed['font_size_px'],47)
    def test_new_label_context_does_not_modify_historical_module(self):
        original=seed.independent.count_labels
        with v3.v003_labels():self.assertIs(seed.independent.count_labels,v3.count_labels)
        self.assertIs(seed.independent.count_labels,original)
    def test_spawned_worker_override_cannot_leak_into_parent(self):
        original=seed.independent.count_labels
        with ProcessPoolExecutor(max_workers=1,mp_context=multiprocessing.get_context('spawn')) as pool:
            self.assertEqual(pool.submit(spawned_override_probe).result(),(True,True))
        self.assertIs(seed.independent.count_labels,original)

class FiniteActorAdapterControls(unittest.TestCase):
    def test_only_named_v003_is_allowed(self):
        helper=old_motion_tests.BaseBindingControls()
        with tempfile.TemporaryDirectory() as folder:
            top,motion,path=helper.bound_plan(folder)
            top['renderer_implementation']='tools/render_fibonacci_video_v003.py'
            _,report=actor.validate_base_binding(top,motion,path);self.assertTrue(report['passed'])
            for name in ('tools/render_fibonacci_video.py','tools/render_fibonacci_video_v002.py','unknown.py'):
                top['renderer_implementation']=name
                with self.assertRaisesRegex(ValueError,'Unexpected'):actor.validate_base_binding(top,motion,path)

if __name__=='__main__':unittest.main()
