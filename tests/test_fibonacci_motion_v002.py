"""Independent negative controls for motion, geometry and immutable-base binding."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image,ImageDraw

from tools import verify_fibonacci_motion_v002 as verify


class GeometryControls(unittest.TestCase):
    def make_pose(self,folder,name='pose',top=10,alpha=254,anchor=(50,90)):
        image=Image.new('RGBA',(100,100))
        ImageDraw.Draw(image).rectangle((20,top,79,89),fill=(80,60,40,alpha))
        path=Path(folder)/(name+'.png');image.save(path)
        return {'id':name,'path':str(path),'sha256':verify.sha(path),
                'reference_height_px':80,'anchor_px':list(anchor),'eyes_closed':False}

    def test_alpha254_is_valid_and_padding_does_not_determine_scale(self):
        with tempfile.TemporaryDirectory() as folder:
            row=self.make_pose(folder)
            _,report=verify.project_pose(row)
            self.assertTrue(report['passed'],report)
            self.assertEqual(report['source_alpha_max'],254)
            self.assertEqual(report['isotropic_scale'],5)
            self.assertEqual(report['foot_anchor_px'],[1655,990])

    def test_shorter_pose_keeps_registered_scale_instead_of_bbox_fitting(self):
        with tempfile.TemporaryDirectory() as folder:
            _,standing=verify.project_pose(self.make_pose(folder,'standing',10))
            _,short=verify.project_pose(self.make_pose(folder,'short',30))
            self.assertEqual(standing['isotropic_scale'],short['isotropic_scale'])
            a=standing['projected_visible_box_xyxy'];b=short['projected_visible_box_xyxy']
            self.assertEqual((a[3]-a[1])-(b[3]-b[1]),100)

    def test_teacher_occlusion_fails_even_inside_video_frame(self):
        with tempfile.TemporaryDirectory() as folder:
            _,report=verify.project_pose(self.make_pose(folder,anchor=(80,90)))
            self.assertFalse(report['passed'])
            self.assertEqual(report['out_of_frame_visible_pixels'],0)
            self.assertGreater(report['protected_regions'][0]['overlap_pixels'],0)

    def test_clipped_character_is_not_accepted_as_a_smaller_bbox(self):
        with tempfile.TemporaryDirectory() as folder:
            _,report=verify.project_pose(self.make_pose(folder),foot=(1910,990))
            self.assertFalse(report['passed'])
            self.assertGreater(report['out_of_frame_visible_pixels'],0)


class ActualMovementControls(unittest.TestCase):
    def test_held_greeting_cannot_pass_as_a_complete_wave(self):
        self.assertEqual(verify.excursion_count([0]*54),0)
        self.assertEqual(verify.excursion_count([0,.1,.5,.9,1,.6,.2,0]),1)

    def test_codec_sized_noise_is_not_a_wave(self):
        self.assertEqual(verify.excursion_count([0,.04,.02,.1,.05,0]*5),0)

    def test_distinct_pose_ids_with_identical_art_do_not_establish_motion(self):
        image=Image.new('RGB',(32,32),'white')
        support=verify.motion_support([image,image.copy(),image.copy()])
        self.assertIsNone(support.getbbox())
        with self.assertRaisesRegex(ValueError,'visible motion'):
            verify.projection_model(image,image,support)

    def test_projected_motion_changes_in_decoded_pixels(self):
        low=Image.new('RGB',(32,32),'white');high=low.copy()
        ImageDraw.Draw(low).rectangle((10,20,21,30),fill='#503c28')
        ImageDraw.Draw(high).rectangle((10,2,21,12),fill='#503c28')
        support=verify.motion_support([low,high]);model=verify.projection_model(low,high,support)
        self.assertAlmostEqual(verify.projection(low,model),0)
        self.assertAlmostEqual(verify.projection(high,model),1)
        self.assertGreater(verify.mae(low,high,support),8)

    def test_clipped_paw_cannot_hide_in_a_whole_body_mean_error(self):
        background=Image.new('RGB',(32,32),'white')
        expected=background.copy();ImageDraw.Draw(expected).rectangle((8,8,23,23),fill='#503c28')
        actual=expected.copy();ImageDraw.Draw(actual).rectangle((16,8,23,23),fill='white')
        missing=verify.missing_opaque_core(actual,expected,background)
        self.assertFalse(missing['passed'])
        self.assertEqual(missing['largest_missing_connected_component_px'],128)
        self.assertTrue(verify.missing_opaque_core(expected,expected,background)['passed'])


class BaseBindingControls(unittest.TestCase):
    def bound_plan(self,folder):
        values=[0,1]
        for _ in range(39):values.append(values[-1]+values[-2])
        base={key:[] for key in verify.BASE_FIELDS}
        base.update(duration_s=600,duration_frames=18000,fps=30,width=1920,height=1080,
                    counted_states=[{'index':n,'value':v} for n,v in enumerate(values)],
                    master_audio={'path':'immutable-master.wav'},timing={'gap':2})
        base_path=Path(folder)/'base.json';base_path.write_text(json.dumps(base))
        reference={'path':str(base_path),'sha256':verify.sha(base_path)}
        motion={'source_timeline':reference};motion_path=Path(folder)/'motion.json';motion_path.write_text(json.dumps(motion))
        top=deepcopy(base);top.update(source_timeline=reference,
             renderer_implementation='tools/render_fibonacci_video_v002.py',
             character_motion={'path':str(motion_path),'sha256':verify.sha(motion_path)})
        return top,motion,motion_path

    def test_base_motion_top_hash_dag_has_no_cycle(self):
        with tempfile.TemporaryDirectory() as folder:
            top,motion,path=self.bound_plan(folder)
            _,report=verify.validate_base_binding(top,motion,path)
            self.assertTrue(report['passed'])
            self.assertNotIn('top_timeline_sha256',motion)

    def test_changed_voice_cue_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            top,motion,path=self.bound_plan(folder);top['voice_events']=[{'id':'changed'}]
            with self.assertRaisesRegex(ValueError,'voice_events'):
                verify.validate_base_binding(top,motion,path)

    def test_changed_base_time_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            top,motion,path=self.bound_plan(folder);top['duration_s']+=.04
            with self.assertRaisesRegex(ValueError,'duration_s'):
                verify.validate_base_binding(top,motion,path)

    def test_unknown_renderer_is_not_loaded(self):
        with tempfile.TemporaryDirectory() as folder:
            top,motion,path=self.bound_plan(folder);top['renderer_implementation']='tools/other.py'
            with self.assertRaisesRegex(ValueError,'Unexpected'):
                verify.validate_base_binding(top,motion,path)


class EducationalPoseControls(unittest.TestCase):
    def test_rule_exit_returns_via_half_before_watch(self):
        plan={'visual_segments':[{'mode':'rule','index':None,'start_s':10.,'end_s':20.}]}
        for at,expected in [(10.2,'watch_left'),(10.5,'present_half'),(12.,'present_full'),
                            (19.6,'present_half'),(19.8,'watch_left')]:
            with self.subTest(at=at):self.assertEqual(verify.static_pose_at(plan,at),expected)


if __name__=='__main__':unittest.main()
