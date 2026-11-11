"""Metadata-only regression checks for timing, endpoint reuse, and invalid input."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools.video_pipeline import (
    PipelineError, build_plan, english_number, main, prepare_audio, read_json, validate_design,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CUE_PATH = PROJECT_ROOT / "design/counting-video-v1/cue-sheet-v2.json"
TEMP_ROOT = Path("D:/temp") if Path("D:/temp").is_dir() else None


def episode(count_end=300):
    return {
        "schema_version": 1,
        "episode_id": "test-counting",
        "count_start": 1,
        "count_end": count_end,
        "final_count_provisional": True,
        "count_end_candidates": [300, 250],
        "duration": {"target_s": 510, "min_inclusive_s": 480, "max_exclusive_s": 540},
        "timing": {"minimum_display_s": 0.8, "ordinary_gap_s": 0.15,
                   "pre_sfx_gap_s": 0.1, "post_sfx_gap_s": 0.15},
        "voice": {"language": "en-US", "provider": None, "voice_id": None},
        "render": {"width": 1920, "height": 1080, "fps": 30},
        "media_generation_allowed": False,
    }


def measured_manifest(cues, number_duration=1.3):
    blocks = [cues["intro"]] + [cue["pause_block"] for cue in cues["cues"]
                               if cue.get("pause_block") is not None]
    dialogue = {}
    for block in blocks:
        for event in block["events"]:
            if event["kind"] == "speech":
                start, end = event["window_s"]
                dialogue[event["spoken_text"]] = (end - start) * 0.7
    return {
        "schema_version": 1,
        "measurement_status": "measured",
        "numbers": [{"number": number, "duration_s": number_duration}
                    for number in range(1, 301)],
        "dialogue": [{"spoken_text": text, "duration_s": duration}
                     for text, duration in dialogue.items()],
    }


class PlanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_cues = read_json(CUE_PATH)

    def setUp(self):
        self.cues = deepcopy(self.source_cues)
        self.episode = episode()
        self.manifest = measured_manifest(self.cues)

    def test_design_allows_unselected_voice_and_additional_metadata(self):
        self.episode["custom_series_note"] = "future episode metadata"
        design = validate_design(self.episode, self.cues)
        self.assertEqual(design.count_end, 300)
        self.assertTrue(design.provisional)

    def test_300_plan_counts_once_and_keeps_special_audio_exclusive(self):
        plan = build_plan(self.episode, self.cues, self.manifest)
        spoken_numbers = [event["number"] for event in plan["events"]
                          if event.get("role") == "number"]
        self.assertEqual(spoken_numbers, list(range(1, 301)))
        self.assertEqual(len(plan["cue_groups"]), 30)
        self.assertEqual(len([event for event in plan["events"]
                              if event.get("id") == "SE_FINISH"]), 1)
        self.assertFalse(plan["media_generated"])
        self.assertFalse(plan["production_ready"])
        self.assertTrue(plan["final_count_provisional"])
        self.assertEqual(plan["non_counting_duration_s"], 60)
        self.assertAlmostEqual(plan["duration_s"], 509.52)
        self.assertAlmostEqual(plan["counting_duration_s"], 449.52)
        for left, right in zip(plan["events"], plan["events"][1:]):
            self.assertLessEqual(left["end_s"], right["start_s"] + 1e-8)

    def test_250_reuses_300_measurements_and_replaces_final_bloom(self):
        self.episode["count_end"] = 250
        self.manifest = measured_manifest(self.cues, number_duration=1.6)
        self.manifest["dialogue"].append({"spoken_text": "Unused future line.", "duration_s": 1})
        plan = build_plan(self.episode, self.cues, self.manifest)
        self.assertEqual(plan["unused_numbers"], list(range(251, 301)))
        self.assertEqual(plan["unused_dialogue"], ["Unused future line."])
        self.assertEqual(len(plan["number_displays"]), 250)
        self.assertEqual(len(plan["cue_groups"]), 25)
        self.assertEqual(plan["cue_groups"][-1]["role"], "finale")
        self.assertEqual(plan["cue_groups"][-1]["held_number"], 250)
        self.assertEqual(plan["cue_groups"][-1]["bloom_count"], 5)
        final_sounds = [event["id"] for event in plan["events"]
                        if event["source"] == "CUE_250" and event["kind"] == "sfx"]
        self.assertIn("SE_FINISH", final_sounds)
        self.assertNotIn("SE_BLOOM", final_sounds)
        self.assertTrue(all(event.get("number", 0) <= 250 for event in plan["events"]))
        self.assertEqual(self.cues["cues"][24]["sfx_id"], "SE_BLOOM")

    def test_short_numbers_hold_for_minimum_display_as_counted_time(self):
        baseline = build_plan(self.episode, self.cues, self.manifest)
        self.manifest["numbers"][0]["duration_s"] = 0.2
        plan = build_plan(self.episode, self.cues, self.manifest)
        display = plan["number_displays"][0]
        self.assertAlmostEqual(display["end_s"] - display["start_s"], 0.8)
        self.assertAlmostEqual(baseline["duration_s"] - plan["duration_s"], 0.65)
        self.assertAlmostEqual(plan["duration_s"] - plan["counting_duration_s"], 60)

    def test_ordinary_gap_cannot_be_used_for_arbitrary_silent_padding(self):
        self.episode["timing"]["ordinary_gap_s"] = 2
        with self.assertRaisesRegex(PipelineError, "adjustment range"):
            validate_design(self.episode, self.cues)

    def test_start_end_measurements_are_supported_without_using_padding(self):
        self.manifest["numbers"][0] = {"number": 1, "start_s": 4.0, "end_s": 5.3}
        plan = build_plan(self.episode, self.cues, self.manifest)
        first = next(event for event in plan["events"] if event.get("number") == 1)
        self.assertAlmostEqual(first["end_s"] - first["start_s"], 1.3)

    def test_conflicting_duration_and_endpoints_are_rejected(self):
        self.manifest["numbers"][0].update(start_s=0, end_s=2)
        with self.assertRaisesRegex(PipelineError, "disagrees"):
            build_plan(self.episode, self.cues, self.manifest)

    def test_missing_number_measurement_is_explicit(self):
        self.manifest["numbers"].pop(198)
        with self.assertRaisesRegex(PipelineError, "missing measured number durations: 199"):
            build_plan(self.episode, self.cues, self.manifest)

    def test_missing_dialogue_measurement_is_explicit(self):
        self.manifest["dialogue"] = []
        with self.assertRaisesRegex(PipelineError, "missing measured dialogue"):
            build_plan(self.episode, self.cues, self.manifest)

    def test_estimated_measurements_are_not_accepted(self):
        self.manifest["measurement_status"] = "estimated"
        with self.assertRaisesRegex(PipelineError, "measurement_status='measured'"):
            build_plan(self.episode, self.cues, self.manifest)

    def test_duplicate_number_and_dialogue_measurements_are_rejected(self):
        for field in ("numbers", "dialogue"):
            with self.subTest(field=field):
                manifest = deepcopy(self.manifest)
                manifest[field].append(deepcopy(manifest[field][0]))
                with self.assertRaisesRegex(PipelineError, "duplicate"):
                    build_plan(self.episode, self.cues, manifest)

    def test_invalid_unused_measurements_are_still_rejected(self):
        self.episode["count_end"] = 250
        for invalid in (float("nan"), float("inf"), -1, 0, True, "1.5"):
            with self.subTest(invalid=invalid):
                manifest = measured_manifest(self.cues, number_duration=1.6)
                manifest["numbers"][-1]["duration_s"] = invalid
                with self.assertRaises(PipelineError):
                    build_plan(self.episode, self.cues, manifest)

    def test_number_type_and_range_are_not_coerced(self):
        for invalid in (True, 1.0, "1", 0, 10_001):
            with self.subTest(invalid=invalid):
                manifest = deepcopy(self.manifest)
                manifest["numbers"][0]["number"] = invalid
                with self.assertRaises(PipelineError):
                    build_plan(self.episode, self.cues, manifest)

    def test_speech_that_exceeds_its_window_is_not_trimmed(self):
        intro_voice = next(event for event in self.cues["intro"]["events"]
                           if event["kind"] == "speech")
        measurement = next(row for row in self.manifest["dialogue"]
                           if row["spoken_text"] == intro_voice["spoken_text"])
        measurement["duration_s"] = intro_voice["window_s"][1] - intro_voice["window_s"][0] + 0.01
        with self.assertRaisesRegex(PipelineError, "exceeds its speech window"):
            build_plan(self.episode, self.cues, self.manifest)

    def test_pause_block_rejects_duplicate_outer_audio(self):
        special = next(cue for cue in self.cues["cues"] if cue["count"] == 100)
        special["sfx_id"] = "SE_CELEBRATE"
        with self.assertRaisesRegex(PipelineError, "null outer audio"):
            validate_design(self.episode, self.cues)

    def test_overlapping_reserved_dialogue_and_sfx_is_rejected(self):
        self.cues["intro"]["events"].append({
            "kind": "sfx", "id": "SE_WIND", "start_s": 1.1, "end_s": 1.5,
        })
        with self.assertRaisesRegex(PipelineError, "overlap"):
            validate_design(self.episode, self.cues)

    def test_missing_and_duplicate_tens_cues_are_rejected(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                cues = deepcopy(self.cues)
                if duplicate:
                    cues["cues"].append(deepcopy(cues["cues"][0]))
                else:
                    cues["cues"].pop(0)
                with self.assertRaises(PipelineError):
                    validate_design(self.episode, cues)

    def test_bad_us_english_number_is_rejected(self):
        self.cues["count_lines"][12]["spoken_text"] = "thirty"
        with self.assertRaisesRegex(PipelineError, "incorrect US-English"):
            validate_design(self.episode, self.cues)

    def test_unknown_sfx_and_missing_safety_gap_are_rejected(self):
        for field, invalid in (("sfx_id", "NO_SUCH_SOUND"),
                               ("sfx_id", []),
                               ("ordinary_next_speech_not_before_s", 0.1)):
            with self.subTest(field=field, invalid=invalid):
                cues = deepcopy(self.cues)
                cues["cues"][0][field] = invalid
                with self.assertRaises(PipelineError):
                    validate_design(self.episode, cues)

    def test_too_short_plan_is_rejected(self):
        manifest = measured_manifest(self.cues, number_duration=1)
        with self.assertRaisesRegex(PipelineError, "outside"):
            build_plan(self.episode, self.cues, manifest)

    def test_duration_upper_bound_is_exclusive_and_lower_bound_inclusive(self):
        duration = build_plan(self.episode, self.cues, self.manifest)["duration_s"]
        self.episode["duration"] = {"target_s": duration, "min_inclusive_s": duration,
                                    "max_exclusive_s": duration + 1}
        self.assertEqual(build_plan(self.episode, self.cues, self.manifest)["duration_s"], duration)
        self.episode["duration"] = {"target_s": duration - 1, "min_inclusive_s": duration - 2,
                                    "max_exclusive_s": duration}
        with self.assertRaisesRegex(PipelineError, "outside"):
            build_plan(self.episode, self.cues, self.manifest)

    def test_integer_spelling_covers_critical_transitions(self):
        expected = {13: "thirteen", 30: "thirty", 40: "forty", 100: "one hundred",
                    101: "one hundred one", 250: "two hundred fifty", 300: "three hundred",
                    1000: "one thousand", 10_000: "ten thousand"}
        for number, words in expected.items():
            with self.subTest(number=number):
                self.assertEqual(english_number(number), words)


class JsonAndCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="video-pipeline-tests-", dir=TEMP_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_json(self, filename, value):
        path = self.root / filename
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_duplicate_json_keys_nonfinite_values_and_wrong_root_are_rejected(self):
        for index, text in enumerate(('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}',
                                      '{"a":1e999}', '[]')):
            with self.subTest(text=text):
                path = self.root / f"bad-{index}.json"
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(PipelineError):
                    read_json(path)

    def test_cli_without_measurements_is_clear_and_does_not_create_output(self):
        episode_path = self.write_json("episode.json", episode())
        output = self.root / "not-created" / "plan.json"
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = main(["plan", "--episode", str(episode_path), "--cues", str(CUE_PATH),
                           "--out", str(output)])
        self.assertEqual(result, 2)
        self.assertIn("measured audible speech durations", stderr.getvalue())
        self.assertFalse(output.parent.exists())

    def test_cli_validate_reports_design_only(self):
        episode_path = self.write_json("episode.json", episode())
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = main(["validate", "--episode", str(episode_path), "--cues", str(CUE_PATH)])
        self.assertEqual(result, 0)
        report = json.loads(stdout.getvalue())
        self.assertTrue(report["valid"])
        self.assertFalse(report["production_ready"])

    def test_cli_prepare_audio_needs_no_measurements_and_never_overwrites(self):
        episode_path = self.write_json("episode.json", episode())
        output = self.root / "audio-preparation.json"
        arguments = ["prepare-audio", "--episode", str(episode_path),
                     "--cues", str(CUE_PATH), "--out", str(output)]
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(main(arguments), 0)
        report = json.loads(stdout.getvalue())
        self.assertFalse(report["audio_generated"])
        document = read_json(output)
        self.assertEqual(document["kind"], "audio-preparation-plan-only")
        self.assertEqual(document["summary"]["count_line_count"], 300)
        original = output.read_bytes()
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(arguments), 2)
        self.assertEqual(output.read_bytes(), original)
        self.assertEqual(sorted(path.name for path in self.root.iterdir()),
                         ["audio-preparation.json", "episode.json"])

    def test_cli_writes_metadata_and_refuses_to_overwrite_existing_file(self):
        cues = read_json(CUE_PATH)
        episode_path = self.write_json("episode.json", episode())
        manifest_path = self.write_json("speech.json", measured_manifest(cues))
        output = self.root / "plans" / "plan.json"
        arguments = ["plan", "--episode", str(episode_path), "--cues", str(CUE_PATH),
                     "--speech-manifest", str(manifest_path), "--out", str(output)]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(arguments), 0)
        original = output.read_bytes()
        self.assertFalse(read_json(output)["media_generated"])
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(arguments), 2)
        self.assertEqual(output.read_bytes(), original)


class AudioPreparationTests(unittest.TestCase):
    def setUp(self):
        self.cues = read_json(CUE_PATH)
        self.episode = episode()

    def test_300_preparation_captures_all_required_text_and_sounds(self):
        document = prepare_audio(self.episode, self.cues)
        self.assertEqual(document["summary"], {
            "count_line_count": 300,
            "dialogue_unique_count": 11,
            "dialogue_usage_count": 12,
            "sfx_unique_count": 10,
            "sfx_usage_count": 33,
        })
        self.assertEqual([line["number"] for line in document["count_lines"]], list(range(1, 301)))
        self.assertFalse(document["bgm"])
        self.assertFalse(document["production_ready"])
        self.assertFalse(document["audio_generated"])
        self.assertFalse(document["commercial_rights_verified_by_this_tool"])
        self.assertFalse(document["provider_quota_checked_by_this_tool"])
        self.assertIsNone(document["voice"]["voice_id"])
        self.assertEqual(document["voice"]["language"], "en-US")
        self.assertEqual(document["voice"]["selection_status"], "unselected")
        for sound in document["sfx_palette"]:
            self.assertTrue(sound["duration_includes_tails"])
            self.assertEqual(sound["usage_count"], len(sound["occurrences"]))
            for usage in sound["occurrences"]:
                self.assertAlmostEqual(usage["duration_s"], sound["design_duration_s"])
                self.assertAlmostEqual(usage["relative_end_s"] - usage["relative_start_s"],
                                       sound["design_duration_s"])
        wind = next(sound for sound in document["sfx_palette"] if sound["id"] == "SE_WIND")
        self.assertEqual(wind["usage_count"], 6)
        self.assertEqual(wind["occurrences"][0]["anchor"], "spoken_end(20)")
        self.assertTrue(all(usage["anchor"] != "video_start" for usage in wind["occurrences"]))
        bird = next(sound for sound in document["sfx_palette"] if sound["id"] == "SE_BIRD")
        self.assertEqual(bird["occurrences"][0]["anchor"], "spoken_end(10)")
        self.assertAlmostEqual(bird["occurrences"][0]["relative_start_s"], 0.1)

    def test_reused_dialogue_uses_the_tightest_of_all_windows(self):
        document = prepare_audio(self.episode, self.cues)
        repeated = [line for line in document["dialogue"] if line["usage_count"] > 1]
        self.assertEqual(len(repeated), 1)
        line = repeated[0]
        self.assertEqual(line["usage_count"], 2)
        self.assertEqual({usage["source"] for usage in line["occurrences"]}, {"CUE_100", "CUE_300"})
        self.assertAlmostEqual(line["max_duration_s"], 1.5)
        self.assertEqual(line["max_duration_s"],
                         min(usage["max_duration_s"] for usage in line["occurrences"]))

    def test_250_preparation_uses_finale_at_250_and_omits_later_numbers(self):
        self.episode["count_end"] = 250
        document = prepare_audio(self.episode, self.cues)
        self.assertEqual(document["summary"]["count_line_count"], 250)
        self.assertEqual(document["summary"]["sfx_usage_count"], 28)
        self.assertEqual(document["summary"]["dialogue_usage_count"], 12)
        self.assertEqual(document["count_lines"][-1]["number"], 250)
        self.assertTrue(document["final_count_provisional"])
        finish = next(sound for sound in document["sfx_palette"] if sound["id"] == "SE_FINISH")
        self.assertEqual(finish["usage_count"], 1)
        self.assertEqual(finish["occurrences"][0]["anchor"], "spoken_end(250)")
        self.assertEqual(finish["occurrences"][0]["source"], "CUE_250")
        bloom = next(sound for sound in document["sfx_palette"] if sound["id"] == "SE_BLOOM")
        self.assertEqual([usage["number"] for usage in bloom["occurrences"]], [50, 150])
        for sound in document["sfx_palette"]:
            self.assertTrue(all(usage["number"] is None or usage["number"] <= 250
                                for usage in sound["occurrences"]))

    def test_preparation_is_not_a_measured_speech_manifest(self):
        document = prepare_audio(self.episode, self.cues)
        with self.assertRaisesRegex(PipelineError, "measurement_status='measured'"):
            build_plan(self.episode, self.cues, document)

    def test_input_fingerprints_ignore_key_order_but_track_design_changes(self):
        original = prepare_audio(self.episode, self.cues)["input_hashes"]
        reordered = dict(reversed(list(self.episode.items())))
        self.assertEqual(prepare_audio(reordered, self.cues)["input_hashes"], original)
        self.episode["voice"]["voice_id"] = "pending-test-choice"
        changed_episode = prepare_audio(self.episode, self.cues)["input_hashes"]
        self.assertNotEqual(changed_episode["episode_sha256"], original["episode_sha256"])
        self.assertEqual(changed_episode["cue_sheet_sha256"], original["cue_sheet_sha256"])
        self.cues["intro"]["visual_note"] += " Updated reference."
        self.assertNotEqual(prepare_audio(self.episode, self.cues)["input_hashes"]["cue_sheet_sha256"],
                            original["cue_sheet_sha256"])
        self.assertEqual(original["algorithm"], "SHA-256")
        self.assertEqual(original["method"], "canonical-json-v1")
        self.assertEqual(len(original["episode_sha256"]), 64)

    def test_preparation_validates_design_before_describing_audio(self):
        self.cues["cues"][0]["sfx_id"] = "UNKNOWN_SOUND"
        with self.assertRaisesRegex(PipelineError, "unknown SFX"):
            prepare_audio(self.episode, self.cues)

    def test_bgm_is_copied_as_boolean_without_generating_music(self):
        self.cues["mix"]["bgm"] = True
        document = prepare_audio(self.episode, self.cues)
        self.assertTrue(document["bgm"])
        self.assertFalse(document["audio_generated"])
        self.cues["mix"]["bgm"] = "false"
        with self.assertRaisesRegex(PipelineError, "bgm must be boolean"):
            prepare_audio(self.episode, self.cues)


if __name__ == "__main__":
    unittest.main()
