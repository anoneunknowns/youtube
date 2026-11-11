"""Behavioral checks for event-relative, local Fibonacci acting revision."""
import copy
import json
from pathlib import Path
import unittest

from tools import render_fibonacci_video_v002 as r


class FibonacciActingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = json.loads((r.ROOT/'output/fibonacci-counting-001-v002/timeline.json').read_text())
        cls.scene = r.Scene(cls.plan)

    def test_old_renderer_remains_frozen(self):
        self.assertEqual(r.previous.digest(Path(r.previous.__file__)), r.OLD_RENDERER_SHA256)

    def test_every_math_and_voice_cue_is_from_measured_base(self):
        base = json.loads(r.checked(self.plan['source_timeline']).read_text())
        for key in r.UNCHANGED_FIELDS:
            self.assertEqual(self.plan[key], base[key], key)

    def test_motion_refuses_changed_measured_content(self):
        bad = copy.deepcopy(self.plan)
        bad['counted_states'][31]['display_start_s'] += .01
        with self.assertRaisesRegex(ValueError, 'measured audio/content'):
            r.Scene(bad)

    def test_waves_have_two_out_and_back_excursions_and_return(self):
        for window in self.scene.motion['windows']:
            if window['kind'] != 'wave':
                continue
            names = [key['pose_id'] for key in window['keyframes']]
            self.assertEqual(names, ['neutral', 'wave_prepare', 'wave_in', 'wave_out',
                'wave_in', 'wave_out', 'wave_in', 'wave_prepare', 'neutral'])
            self.assertEqual(window['wave_cycles'], 2)
            self.assertEqual(window['end_frame']-window['start_frame'], 54)

    def test_schedule_follows_cues_after_duration_changes(self):
        base = json.loads(r.checked(self.plan['source_timeline']).read_text())
        changed = copy.deepcopy(base)
        for event in changed['voice_events']:
            if event['id'] in ('N031', 'O01', 'O04'):
                event['start_s'] += .4
                event['end_s'] += .4
        changed['duration_s'] += .4
        changed['duration_frames'] += 12
        motion = r.make_motion(changed, self.plan['source_timeline'], self.scene.motion['registry'])
        before = {w['id']: w for w in self.scene.motion['windows']}
        for window in motion['windows']:
            expected_delta = 0 if window['id'] == 'opening-wave' else 12
            self.assertEqual(window['start_frame']-before[window['id']]['start_frame'], expected_delta)

    def test_one_notice_stays_in_existing_two_second_gap(self):
        notices = [w for w in self.scene.motion['windows'] if w['kind'] == 'notice']
        self.assertEqual(len(notices), 1)
        end = self.scene.voice['N031']['end_s']
        self.assertGreaterEqual(notices[0]['start_s'], end)
        self.assertLessEqual(notices[0]['end_s'], end+2)

    def test_keyframe_boundary_has_one_held_pose_without_dissolve(self):
        for window in self.scene.motion['windows']:
            for key in window['keyframes']:
                start = key['at_frame']
                self.assertEqual(key['interpolation'], 'hold')
                for frame in (start, start+key['hold_frames']-1):
                    self.assertEqual(self.scene.state(frame).pose, key['pose_id'])
        self.assertFalse(self.scene.motion['full_actor_crossfade'])

    def test_finale_closed_eyes_return_open(self):
        longest, run = 0, 0
        for index in range(self.scene.frame_count):
            pose = self.scene.state(index).pose
            closed = self.scene.motion['poses'][pose]['eyes_closed']
            run = run+1 if closed else 0
            longest = max(longest, run)
        self.assertEqual(longest, 36)
        self.assertEqual(self.scene.state(self.scene.frame_count-1).pose, 'neutral')

    def test_direct_sources_and_registered_feet(self):
        reg = json.loads(r.checked(self.scene.motion['registry']).read_text())
        self.assertFalse(reg['creative_composites_used'])
        for frame in reg['frames']:
            self.assertEqual(r.previous.digest(r.resolve(frame['path'])), frame['source_sha256'])
            self.assertEqual(frame['crop_from_source_xyxy'], [0, 0, *frame['size_px']])
            self.scene.character.sprite(frame['id'])
            rec = self.scene.character.receipts[frame['id']]
            self.assertEqual(rec['foot_anchor_px'], [1655, 990])
            self.assertEqual(rec['body_height_px'], 400)

    def test_actor_extrema_preserve_lesson_clearance(self):
        for window in self.scene.motion['windows']:
            for key in window['keyframes']:
                image, receipt = self.scene.image(self.scene.state(key['at_frame']))
                self.assertEqual(image.size, (1920, 1080))
                self.assertTrue(receipt['underlying_layout_passed'])
                self.assertTrue(receipt['foreground_groups_do_not_overlap'])

    def test_wav_cannot_be_reencoded_in_copy_only_revision(self):
        with self.assertRaisesRegex(ValueError, 'WAV re-encoding'):
            r.encode('unused', 'master.wav', 'unused.mp4', 10, 'unused')


if __name__ == '__main__':
    unittest.main()
