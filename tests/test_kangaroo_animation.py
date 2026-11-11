"""Acting requirements: real key drawings, silent-gap blinking and fixed lesson pixels."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from PIL import Image, ImageChops, ImageDraw
from tools import kangaroo_animation as a
from tools import render_prime_video as old
from tools import render_prime_video_v002 as revised

ROOT=Path(__file__).resolve().parents[1]


class AnimationScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=json.loads((ROOT/'output/prime-counting-001-v001/timeline.json').read_text())

    def test_schedule_does_not_change_speech_or_lesson_timing(self):
        before=deepcopy(self.plan)
        schedule=a.Schedule(self.plan,(*a.REQUIRED_POSES,'takeoff'))
        self.assertEqual(self.plan,before)
        self.assertEqual(schedule.total_frames,20590)
        self.assertGreaterEqual(sum(x.name.startswith('blink-') for x in schedule.actions),80)

    def test_blinks_use_three_phases_and_never_intersect_voices(self):
        schedule=a.Schedule(self.plan)
        for action in schedule.actions:
            if not action.name.startswith('blink-'):continue
            self.assertEqual([x.pose for x in action.frames],['blink_half']*2+['blink_closed']*3+['blink_half']*2)
            for voice in self.plan['voice_events']:
                self.assertFalse(action.start_frame/30<voice['end_s'] and voice['start_s']<action.end_frame/30)

    def test_wave_has_four_distinct_arm_drawings_and_returns_to_neutral(self):
        poses={frame.pose for frame in a.wave()}
        self.assertTrue({'wave_raise','wave_high','wave_left','wave_right'}.issubset(poses))
        self.assertEqual(a.wave()[-1],a.ActorState())

    def test_hop_is_crouch_takeoff_air_land_not_only_translation(self):
        frames=a.hop(True);poses=[frame.pose for frame in frames]
        self.assertLess(poses.index('crouch_half'),poses.index('crouch_down'))
        self.assertLess(poses.index('takeoff'),poses.index('hop_air'))
        self.assertLess(poses.index('hop_air'),poses.index('land'))
        self.assertEqual(min(frame.offset_y for frame in frames),-60)
        self.assertEqual(frames[-1],a.ActorState())

    def test_count_milestone_actions_fit_existing_silent_gaps(self):
        schedule=a.Schedule(self.plan,(*a.REQUIRED_POSES,'takeoff'))
        names={'early-thinking','halfway-hop','later-smile','late-discovery'}
        for action in schedule.actions:
            if action.name not in names:continue
            for voice in self.plan['voice_events']:
                self.assertFalse(action.start_frame/30<voice['end_s'] and voice['start_s']<action.end_frame/30)

    def test_all_actions_finish_before_global_fade(self):
        schedule=a.Schedule(self.plan)
        self.assertLess(max(x.end_frame for x in schedule.actions),int((self.plan['duration_s']-2)*30))
        self.assertEqual(schedule.state(self.plan['duration_frames']-1),a.ActorState())

    def test_actual_rounded_source_anchors_stay_within_half_pixel_on_each_axis(self):
        actor=a.Artwork.__new__(a.Artwork)
        actor.root=(1625,982)
        actor.render_anchors={'neutral':[108.5,299.25],'hop_air':[202.75,370.5]}
        actor.scales={'neutral':430/277,'hop_air':430/443.829545}
        for state in (a.ActorState(),a.ActorState('hop_air',-60)):
            report=actor.support(state)
            self.assertTrue(report['horizontal_passed'])
            self.assertTrue(report['vertical_passed'])
            self.assertLessEqual(abs(report['anchor_rounding_error_px'][0]),.5)
            self.assertLessEqual(abs(report['anchor_rounding_error_px'][1]),.5)
        self.assertEqual(actor.support(a.ActorState('hop_air',-60))['intended_foot_anchor_px'],[1625,922])


class _TestActor:
    root=(1625,982)
    scales={'neutral':1}
    def draw(self,image,state):
        from PIL import ImageDraw
        ImageDraw.Draw(image).ellipse((1500,550,1800,982),fill='#e1aa6b')
    def bounds(self,state):return(1500,550,1801,983)
    def support(self,state):return {'horizontal_passed':True,'vertical_passed':True}


class FaceRigTests(unittest.TestCase):
    def test_eye_patch_cannot_expand_neutral_outline_or_move_body_pixels(self):
        neutral=Image.new('RGBA',(80,100))
        ImageDraw.Draw(neutral).ellipse((20,10,60,55),fill=(220,170,110,254))
        ImageDraw.Draw(neutral).rectangle((30,50,55,95),fill=(200,150,90,254))
        # The measured generated patch deliberately extends beyond the head.
        source=Image.new('RGBA',neutral.size,(230,180,120,254))
        actor=a.Artwork.__new__(a.Artwork)
        actor.raw_images={'neutral':neutral,'blink_half':source}
        actor.images={'neutral':neutral.copy(),'blink_half':source.copy()}
        actor.render_anchors={'neutral':[40,95],'blink_half':[39,94]}
        actor.scales={'neutral':1,'blink_half':1}
        actor.face_rig_reports={}
        actor.registration={'face_overlays':{'blink_half':{'base_pose':'neutral','patches':[{
            'source_box_xyxy':[10,20,60,40],'target_box_xyxy':[10,20,60,40],
            'feather_px':2,'clip_to_base_alpha':True,'base_alpha_inset_px':2}]}}}
        actor.apply_face_overlays()
        result=actor.images['blink_half']
        self.assertEqual(result.getchannel('A').getbbox(),neutral.getchannel('A').getbbox())
        self.assertIsNone(ImageChops.difference(result.crop((0,50,80,100)),neutral.crop((0,50,80,100))).getbbox())
        self.assertEqual(actor.render_anchors['blink_half'],actor.render_anchors['neutral'])
        self.assertIsNotNone(ImageChops.difference(result,neutral).getbbox())


class UnchangedTeachingPixelsTests(unittest.TestCase):
    def test_compositing_leaves_all_learning_fields_exactly_unchanged(self):
        plan=json.loads((ROOT/'output/prime-counting-001-v001/timeline.json').read_text())
        original=old.Scene(plan)
        scene=revised.Scene.__new__(revised.Scene)
        scene.plan=plan;scene.base=old.Scene(plan);scene.base.character=revised.AbsentCharacter()
        scene.character=_TestActor();scene.cream=original.cream;scene.actor_reports={}
        for mode,value,alpha,cream in [('opening',None,255,0),('definition',None,255,0),
            ('comparison',None,128,0),('rotation',None,128,0),('one',None,200,0),
            ('nine',None,128,0),('bridge',None,128,0),('count',2,255,0),
            ('count',101,255,0),('count',773,255,0),('count',997,255,0),('finale',997,255,100)]:
            with self.subTest(mode=mode,value=value,alpha=alpha,cream=cream):
                before,_=original.image(old.Frame(mode,value,alpha,cream))
                after,_=scene.image(revised.Frame(mode,value,alpha,cream))
                self.assertIsNone(ImageChops.difference(before.crop((0,0,1370,1080)),after.crop((0,0,1370,1080))).getbbox())


if __name__=='__main__':unittest.main()
