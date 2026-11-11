"""Signal-pattern and source-integrity checks for the terminal screening aid."""

import array
import hashlib
import math
from pathlib import Path
import tempfile
import unittest
import wave

from tools.verify_terminal_tails import TailReviewError, analyze_samples, main, read_clip


class TerminalTailTests(unittest.TestCase):
    rate = 16_000

    def tone(self, frequency, duration, amplitude=0.1):
        return [amplitude * math.sin(2 * math.pi * frequency * index / self.rate)
                for index in range(round(duration * self.rate))]

    def test_sustained_voiced_tail_after_fricative_is_a_candidate(self):
        samples = (self.tone(220, 0.12) + self.tone(6000, 0.09)
                   + self.tone(190, 0.09) + [0.0] * 480)
        result = analyze_samples(samples, self.rate, "s")
        self.assertTrue(result["suspicious"])
        self.assertGreaterEqual(result["voiced_runs"][0]["approx_duration_s"], 0.03)
        self.assertGreater(result["voiced_runs"][0]["start_s"], result["last_terminal_noise_s"])

    def test_retained_fricative_and_silence_do_not_flag(self):
        samples = self.tone(220, 0.13) + self.tone(6000, 0.12) + [0.0] * 480
        result = analyze_samples(samples, self.rate, "s")
        self.assertFalse(result["suspicious"])
        self.assertIsNotNone(result["last_terminal_noise_s"])
        self.assertIn("not_a_listening_approval", result["status"])

    def test_voiced_clip_with_no_terminal_release_is_unresolved(self):
        result = analyze_samples(self.tone(190, 0.30), self.rate, "t")
        self.assertIsNone(result["last_terminal_noise_s"])
        self.assertIn("not_resolved", result["status"])
        self.assertFalse(result["suspicious"])

    def test_short_or_silent_clips_do_not_become_pronunciation_approvals(self):
        for samples in ([0.0] * 100, [0.0] * 8000):
            result = analyze_samples(samples, self.rate, "s")
            self.assertFalse(result["suspicious"])
            self.assertIsNone(result["last_terminal_noise_s"])
            self.assertIn("not_a_listening_approval", result["status"])

    def test_unsupported_phoneme_or_rate_is_rejected(self):
        for terminal, rate in (("n", self.rate), ("s", 8000)):
            with self.assertRaises(TailReviewError):
                analyze_samples([0.0] * 800, rate, terminal)

    def test_hash_and_duration_are_checked_before_analysis(self):
        with tempfile.TemporaryDirectory(dir="D:/temp") as folder:
            path = Path(folder) / "test.wav"
            values = array.array("h", [round(value * 32767) for value in self.tone(190, 0.10)])
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(self.rate)
                output.writeframes(values.tobytes())
            row = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "duration_s": 0.10}
            samples, rate = read_clip(row)
            self.assertEqual(rate, self.rate)
            self.assertEqual(len(samples), 1600)
            with self.assertRaisesRegex(TailReviewError, "SHA256"):
                read_clip({**row, "sha256": "0" * 64})
            for duration in (0.11, True, float("nan")):
                with self.assertRaisesRegex(TailReviewError, "duration"):
                    read_clip({**row, "duration_s": duration})

    def test_existing_output_is_never_replaced(self):
        with tempfile.TemporaryDirectory(dir="D:/temp") as folder:
            output = Path(folder) / "report.json"
            output.write_text("original", encoding="utf-8")
            with self.assertRaisesRegex(TailReviewError, "already exists"):
                main(["--manifest", "does-not-exist.json", "--out", str(output)])
            self.assertEqual(output.read_text(encoding="utf-8"), "original")


if __name__ == "__main__":
    unittest.main()
