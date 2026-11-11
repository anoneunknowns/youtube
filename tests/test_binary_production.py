"""Exercise incorrect token order, source media and overlap rejection."""
from copy import deepcopy
import hashlib
import json
import random
from pathlib import Path
import tempfile
import unittest
import wave

from tools.verify_binary_production import BinaryValidationError, load_speech, validate_timeline, waveform_correlation
from tools.prepare_binary_episode import INTRO_LINES, FINALE_LINES


def fixture():
    speech = {
        f"binary-{word}": {"spoken_text": word, "actual_duration_s": .5, "sample_rate": 24000, "sha256": "a" * 64}
        for word in ("zero", "one")
    }
    events = []

    def dialogue(text, start, phase, identifier):
        speech[identifier] = {"spoken_text": text, "actual_duration_s": .5, "sample_rate": 24000, "sha256": "a" * 64}
        events.append({"type": "dialogue", "id": identifier, "speech_id": identifier, "text": text,
                       "start_s": start, "end_s": start + .5, "phase": phase})

    for index, (text, start, _) in enumerate(INTRO_LINES):
        dialogue(text, start, "intro", f"intro-{index}")
    cursor = 32.0
    for number in range(128):
        bits = format(number, "b")
        start = cursor
        cursor += .12
        tokens = []
        for index, bit in enumerate(bits):
            token = "one" if bit == "1" else "zero"
            event = {"type": "digit_voice", "id": f"bit-{number:03}-{index}", "speech_id": f"binary-{token}",
                     "decimal_value": number, "display_binary": bits, "bit_index": index,
                     "slot_index": 7 - len(bits) + index, "token": token,
                     "start_s": cursor, "end_s": cursor + .5}
            events.append(event)
            tokens.append(deepcopy(event))
            cursor += .5
            if index < len(bits) - 1:
                cursor += .055
        voice_end = cursor
        cursor += .18
        events.append({"type": "count", "number": number, "decimal_value": number, "display_binary": bits,
                       "display_slots": [None] * (7 - len(bits)) + [int(bit) for bit in bits],
                       "start_s": start, "end_s": cursor, "voice_end_s": voice_end, "bit_events": tokens})
        if number in (2, 4, 8, 16, 32, 64):
            events.append({"type": "sfx", "id": "SE_PLACE", "before_decimal_value": number,
                           "start_s": start + .01, "end_s": start + .09})
        if number in (7, 31, 63):
            end = cursor + (8 if number == 31 else 3)
            if number == 31:
                dialogue("Let's stretch.", cursor + .2, "stretch", "stretch")
                dialogue("Ready? Let's keep going!", cursor + 5.7, "stretch", "ready")
            else:
                dialogue("A new place is ready.", cursor + .35, "place", f"place-{number}")
            events.append({"type": "pause", "kind": "stretch" if number == 31 else "new-place-comparison",
                           "after_decimal_value": number, "start_s": cursor, "end_s": end})
            cursor = end
    events.append({"type": "finale", "start_s": cursor, "end_s": cursor + 15})
    events.append({"type": "sfx", "id": "SE_FINISH", "start_s": cursor + .08, "end_s": cursor + 1.08})
    for index, (text, start, _) in enumerate(FINALE_LINES):
        dialogue(text, cursor + start, "outro", f"outro-{index}")
    return {"duration_s": cursor + 15, "fps": 30, "events": events}, speech


class BinaryProductionTests(unittest.TestCase):
    def setUp(self):
        self.timeline, self.speech = fixture()

    def test_complete_binary_schedule(self):
        report = validate_timeline(self.timeline, self.speech)
        self.assertTrue(report["passed"])
        self.assertEqual(report["counted_states"], 128)
        self.assertEqual(report["digit_word_totals"], {"zero": 322, "one": 448})

    def test_rejects_skipped_or_duplicated_state(self):
        for replacement in (3, 5):
            broken = deepcopy(self.timeline)
            next(row for row in broken["events"] if row["type"] == "count" and row["number"] == 4)["decimal_value"] = replacement
            with self.subTest(replacement=replacement), self.assertRaises(BinaryValidationError):
                validate_timeline(broken, self.speech)

    def test_rejects_wrong_bit_slot_or_nested_timing(self):
        for change in ("slot", "nested"):
            broken = deepcopy(self.timeline)
            if change == "slot":
                next(row for row in broken["events"] if row["type"] == "digit_voice")["slot_index"] = 0
            else:
                row = next(row for row in broken["events"] if row["type"] == "count")
                row["bit_events"][0]["start_s"] += .01
            with self.subTest(change=change), self.assertRaises(BinaryValidationError):
                validate_timeline(broken, self.speech)

    def test_rejects_late_clip_end_and_carry_during_voice(self):
        broken = deepcopy(self.timeline)
        next(row for row in broken["events"] if row["type"] == "digit_voice")["end_s"] += .02
        with self.assertRaises(BinaryValidationError):
            validate_timeline(broken, self.speech)
        broken = deepcopy(self.timeline)
        broken["events"].append({"type": "carry", "from_decimal": 0, "to_decimal": 1,
                                  "from_binary": "0", "to_binary": "1", "start_s": 32.2, "end_s": 32.3})
        with self.assertRaisesRegex(BinaryValidationError, "separate from speech"):
            validate_timeline(broken, self.speech)

    def test_rejects_sfx_overlapping_digit_and_wrong_text(self):
        broken = deepcopy(self.timeline)
        broken["events"].append({"type": "sfx", "id": "SE_PLACE", "start_s": 32.2, "end_s": 32.3})
        with self.assertRaisesRegex(BinaryValidationError, "Audio overlap"):
            validate_timeline(broken, self.speech)
        speech = deepcopy(self.speech)
        speech["binary-zero"]["spoken_text"] = "oh"
        with self.assertRaisesRegex(BinaryValidationError, "expected single token"):
            validate_timeline(self.timeline, speech)

    def test_rejects_invalid_duration_and_leading_zero(self):
        for value in (479.9, 540, float("nan"), True):
            broken = deepcopy(self.timeline)
            broken["duration_s"] = value
            with self.subTest(value=value), self.assertRaises(BinaryValidationError):
                validate_timeline(broken, self.speech)
        row = next(row for row in self.timeline["events"] if row["type"] == "count")
        row["display_binary"] = "0000000"
        with self.assertRaisesRegex(BinaryValidationError, "Binary display mismatch"):
            validate_timeline(self.timeline, self.speech)

    def test_rejects_missing_intro_and_chime(self):
        for missing_type in ("intro", "SE_PLACE"):
            broken = deepcopy(self.timeline)
            if missing_type == "intro":
                target = next(row for row in broken["events"] if row.get("phase") == "intro")
            else:
                target = next(row for row in broken["events"] if row.get("id") == "SE_PLACE")
            broken["events"].remove(target)
            with self.subTest(missing=missing_type), self.assertRaises(BinaryValidationError):
                validate_timeline(broken, self.speech)

    def test_rejects_closing_fade_that_cuts_speech(self):
        self.timeline["fade_out_start_s"] = self.timeline["duration_s"] - 10
        with self.assertRaisesRegex(BinaryValidationError, "Closing fade"):
            validate_timeline(self.timeline, self.speech)

    def test_checks_source_wav_samples_and_hash(self):
        with tempfile.TemporaryDirectory(prefix="binary-qa-", dir="D:/temp") as folder:
            root = Path(folder)
            clip = root / "zero.wav"
            with wave.open(str(clip), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24000)
                wav.writeframes(b"\0\0" * 12000)
            digest = hashlib.sha256(clip.read_bytes()).hexdigest()
            row = {"id": "binary-zero", "spoken_text": "zero", "duration_s": .5, "path": "zero.wav", "sha256": digest}
            manifest = {"measurement_status": "measured", "clips": [row]}
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            _, lookup = load_speech(path)
            self.assertEqual(lookup["binary-zero"]["actual_duration_s"], .5)
            row["duration_s"] = .4
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(BinaryValidationError, "duration mismatch"):
                load_speech(path)
            row["duration_s"] = .5
            row["sha256"] = "b" * 64
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(BinaryValidationError, "SHA-256 mismatch"):
                load_speech(path)

    def test_waveform_check_accepts_gain_and_rejects_other_audio(self):
        from array import array
        generator = random.Random(17)
        source = array("h", (generator.randrange(-1000, 1001) for _ in range(2400)))
        matched = array("h", [0] * 8 + [value * 2 for value in source] + [0] * 8)
        correlation, lag = waveform_correlation(source, matched)
        self.assertAlmostEqual(correlation, 1)
        self.assertEqual(lag, 0)
        unrelated = array("h", (generator.randrange(-1000, 1001) for _ in range(2416)))
        correlation, _ = waveform_correlation(source, unrelated)
        self.assertLess(correlation, .3)


if __name__ == "__main__":
    unittest.main()
