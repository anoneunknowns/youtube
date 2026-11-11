"""Behavioral checks for coherent arm acting and truthful completed-prime progress."""
from copy import deepcopy
import json
import math
from pathlib import Path
import unittest

from PIL import Image,ImageChops,ImageDraw

from tools import kangaroo_animation_v003 as a
from tools import render_prime_video_v003 as r

ROOT=Path(__file__).resolve().parents[1]


class GuideScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=json.loads((ROOT/'output/prime-counting-001-v002/timeline.json').read_text())

    def test_adds_purposeful_variety_without_changing_any_timing(self):
        before=deepcopy(self.plan);schedule=a.Schedule(self.plan)
        self.assertEqual(before,self.plan)
        names={x.name for x in schedule.actions}
        self.assertTrue({'factor-presentation','composite-presentation','two-factor-presentation','bridge-presentation','middle-rest','quarter-clap','three-quarter-clap'}<=names)
        self.assertEqual(len([x for x in schedule.actions if 'hop' in x.name]),2)
        self.assertEqual(schedule.total_frames,20590)

    def test_rest_has_both_transition_directions_and_no_new_wait(self):
        action=next(x for x in a.Schedule(self.plan).actions if x.name=='middle-rest')
        self.assertEqual(len(action.frames),360)
        poses=[x.pose for x in action.frames]
        self.assertLess(poses.index('half_seated'),poses.index('seated_neutral'))
        self.assertLess(poses.index('seated_stretch_half'),poses.index('seated_stretch'))
        self.assertGreater(poses.index('stand_half'),poses.index('seated_stretch'))
        self.assertEqual(poses[-1],'neutral')

    def test_clap_approaches_and_releases_through_middle_drawing(self):
        frames=a.clap();poses=[frame.pose for i,frame in enumerate(frames) if i==0 or frame.pose!=frames[i-1].pose]
        self.assertEqual(poses,['neutral','clap_open','clap_near','clap_touch','clap_near','clap_open','clap_near','clap_touch','clap_near','clap_open','settle','neutral'])
        self.assertLessEqual(len(frames)/30,1.4)

    def test_recurring_blink_cannot_pop_the_sitting_character_to_standing(self):
        schedule=a.Schedule(self.plan);rest=next(x for x in schedule.actions if x.name=='middle-rest')
        for action in schedule.actions:
            if action.name.startswith('blink-'):
                self.assertFalse(action.start_frame<rest.end_frame and rest.start_frame<action.end_frame)

    def test_meaningful_counting_gaps_stay_below_ninety_seconds(self):
        schedule=a.Schedule(self.plan)
        actions=[x for x in schedule.actions if not x.name.startswith('blink-')]
        gaps=[(b.start_frame-a.end_frame)/30 for a,b in zip(actions,actions[1:])]
        self.assertLessEqual(max(gaps),90)
        goodbye=next(x for x in actions if x.name=='goodbye-wave')
        self.assertGreaterEqual(len(goodbye.frames)/30,2.8)


class ProgressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=json.loads((ROOT/'output/prime-counting-001-v002/timeline.json').read_text());cls.progress=r.ProgressMosaic(cls.plan)

    def test_one_tile_only_after_each_actual_count_voice_finishes(self):
        count_events=[x for x in self.plan['voice_events'] if x['kind']=='count']
        self.assertEqual(self.progress.count(0),0)
        for ordinal,event in enumerate(count_events,1):
            first_frame=math.ceil(event['end_s']*30-1e-9)
            self.assertEqual(self.progress.count(first_frame-1),ordinal-1)
            self.assertEqual(self.progress.count(first_frame),ordinal)
        self.assertEqual(self.progress.count(20589),168)

    def test_native_tile_pixels_count_and_both_axes_center(self):
        for n in (0,1,13,14,15,84,167,168):
            layer,report=self.progress.layer(n)
            self.assertTrue(report['passed'])
            active=(45,115,107,255)
            occupied=0
            for i in range(168):
                x=1549+(i%14)*16+6;y=333+(i//14)*15+5
                occupied+=layer.getpixel((x,y))==active
            self.assertEqual(occupied,n)
            self.assertIsNone(layer.getchannel('A').crop((0,0,1370,1080)).getbbox())


class LocalArmRigTests(unittest.TestCase):
    def test_local_rgba_replacement_erases_old_arm_without_moving_head_pouch_or_tail(self):
        neutral=Image.new('RGBA',(80,100));d=ImageDraw.Draw(neutral)
        d.rectangle((20,10,50,85),fill=(220,170,110,255));d.rectangle((12,45,24,65),fill=(90,50,20,255))
        source=neutral.copy();ImageDraw.Draw(source).rectangle((12,45,19,65),fill=(0,0,0,0));ImageDraw.Draw(source).rectangle((5,35,25,44),fill=(90,50,20,255))
        actor=a.Artwork.__new__(a.Artwork);actor.raw_images={'neutral':neutral,'present_open':source}
        actor.images={'neutral':neutral.copy(),'present_open':source.copy()};actor.scales={'neutral':1,'present_open':1}
        actor.render_anchors={'neutral':[40,85],'present_open':[40,85]};actor.face_rig_reports={};actor.arm_rig_reports={}
        actor.registration={'arm_overlays':{'present_open':{'source_to_base':{'scale':1,'translate_xy':[0,0]},'replace_polygon_xy':[[2,32],[27,32],[27,68],[2,68]],'feather_px':0}}}
        actor.apply_face_overlays();result=actor.images['present_open']
        self.assertEqual(result.getpixel((15,55))[3],0)
        self.assertIsNone(ImageChops.difference(result.crop((0,0,80,30)),neutral.crop((0,0,80,30))).convert('RGB').getbbox())
        self.assertEqual(result.crop((0,70,80,100)).tobytes(),neutral.crop((0,70,80,100)).tobytes())
        self.assertEqual(actor.render_anchors['present_open'],actor.render_anchors['neutral'])


class _TestActor:
    root=(1625,1014)
    scales={'neutral':1}
    def draw(self,image,state):ImageDraw.Draw(image).ellipse((1500,550,1820,1014),fill='#ddaa77')
    def bounds(self,state):return(1500,550,1821,1015)
    def support(self,state):return {'horizontal_passed':True,'vertical_passed':True}


class TeachingCanvasTests(unittest.TestCase):
    def test_new_progress_and_actor_leave_all_original_learning_pixels_unchanged(self):
        plan=json.loads((ROOT/'output/prime-counting-001-v002/timeline.json').read_text())
        original=r.source.Scene(plan)
        scene=r.Scene.__new__(r.Scene);scene.plan=plan;scene.base=r.source.Scene(plan)
        scene.base.character=r.pipeline.AbsentCharacter();scene.character=_TestActor()
        scene.progress=r.ProgressMosaic(plan);scene.cream=Image.new('RGBA',(1920,1080),r.source.m.CREAM);scene.actor_reports={}
        for mode,value,alpha,cream,completed in [('opening',None,255,0,0),('definition',None,255,0,0),
            ('comparison',None,128,0,0),('rotation',None,128,0,0),('one',None,255,0,0),
            ('nine',None,255,0,4),('bridge',None,255,0,25),('count',2,255,0,0),
            ('count',101,255,0,25),('count',997,255,0,167),('finale',997,255,100,168)]:
            with self.subTest(mode=mode,value=value):
                before,_=original.image(r.source.Frame(mode,value,alpha,cream))
                after,_=scene.image(r.Frame(mode,value,alpha,cream,'neutral',0,completed))
                self.assertIsNone(ImageChops.difference(before.crop((0,0,1370,1080)),after.crop((0,0,1370,1080))).getbbox())


if __name__=='__main__':unittest.main()
