"""Regression checks for the hash-bound speech acceptance gate; no TTS or FFmpeg."""

from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
import wave

from tools.build_audio_mix import file_hash, main, verify_speech_acceptance
from tools.video_pipeline import PipelineError


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SpeechAcceptanceTests(unittest.TestCase):
    def setUp(self):
        temporary_root = PROJECT_ROOT / "output"
        temporary_root.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="speech-gate-test-", dir=temporary_root)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.clip = self.root / "six.wav"
        with wave.open(str(self.clip), "wb") as audio:
            audio.setparams((1, 2, 24_000, 0, "NONE", "not compressed"))
            audio.writeframes(b"\0\0" * 240)
        self.manifest = self.root / "measurements.json"
        self.write_json(self.manifest, {
            "schema_version": 1,
            "measurement_status": "measured",
            "numbers": [{"number": 6, "spoken_text": "six", "path": str(self.clip),
                         "sha256": file_hash(self.clip), "duration_s": 0.01}],
            "dialogue": [],
        })
        self.asr = self.root / "isolated-asr.json"
        self.pronunciation = self.root / "pronunciation-review.json"
        self.prior_manifest = self.root / "prior-measurements.json"
        self.evidence = self.root / "phoneme-evidence.json"
        for path, kind in ((self.asr, "isolated-asr"),
                           (self.pronunciation, "speech-pronunciation-review"),
                           (self.prior_manifest, "prior-measurements"),
                           (self.evidence, "isolated-phoneme-asr")):
            self.write_json(path, {"kind": kind, "fixture": True})
        self.report = {
            "schema_version": 1,
            "kind": "hash-bound-speech-acceptance",
            "accepted": True,
            "inputs": {
                "manifest": self.record(self.manifest),
                "isolated_asr": self.record(self.asr),
                "pronunciation": self.record(self.pronunciation),
                "prior_manifest": self.record(self.prior_manifest),
            },
            "summary": {"clips": 1, "numbers": 1, "dialogue": 0,
                        "accepted": 1, "unresolved": 0},
            "unresolved": [],
            "replacements": [],
            "results": [{
                "role": "number", "number": 6, "spoken_text": "six",
                "path": str(self.clip), "sha256": file_hash(self.clip),
                "accepted": True, "failures": [],
                "isolated_asr_status": "asr-match", "pronunciation_decision": "pass",
                "pronunciation_evidence": [{
                    **self.record(self.evidence), "kind": "isolated-phoneme-asr",
                    "summary": "Synthetic test fixture for evidence hash verification only.",
                }],
            }],
        }
        self.acceptance = self.root / "speech-acceptance.json"
        self.save_report()

    @staticmethod
    def write_json(path, data):
        path.write_text(json.dumps(data), encoding="utf-8")

    @staticmethod
    def record(path):
        return {"path": str(path.resolve()), "sha256": file_hash(path)}

    def save_report(self):
        self.write_json(self.acceptance, self.report)

    def test_missing_gate_is_rejected(self):
        with self.assertRaisesRegex(PipelineError, "requires --speech-acceptance"):
            verify_speech_acceptance(None, self.manifest)

    def test_mix_cli_requires_gate(self):
        with redirect_stderr(io.StringIO()) as errors:
            with self.assertRaises(SystemExit) as stopped:
                main(["mix", "--timeline", "timeline.json", "--speech-manifest", "speech.json",
                      "--sfx-dir", "sfx", "--out", "master.wav", "--work-dir", "work"])
        self.assertEqual(stopped.exception.code, 2)
        self.assertIn("--speech-acceptance", errors.getvalue())

    def test_unaccepted_report_is_rejected(self):
        self.report["accepted"] = False
        self.save_report()
        with self.assertRaisesRegex(PipelineError, "missing, unresolved, or for a different manifest"):
            verify_speech_acceptance(self.acceptance, self.manifest)

    def test_unresolved_report_is_rejected(self):
        self.report["summary"]["unresolved"] = 1
        self.save_report()
        with self.assertRaisesRegex(PipelineError, "missing, unresolved, or for a different manifest"):
            verify_speech_acceptance(self.acceptance, self.manifest)

    def test_different_manifest_is_rejected(self):
        other_manifest = self.root / "different-measurements.json"
        self.write_json(other_manifest, {"numbers": [], "dialogue": []})
        with self.assertRaisesRegex(PipelineError, "different manifest"):
            verify_speech_acceptance(self.acceptance, other_manifest)

    def test_changed_review_inputs_are_rejected(self):
        for path in (self.manifest, self.asr, self.pronunciation, self.prior_manifest):
            with self.subTest(input=path.name):
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                try:
                    with self.assertRaises(PipelineError):
                        verify_speech_acceptance(self.acceptance, self.manifest)
                finally:
                    path.write_bytes(original)

    def test_changed_evidence_is_rejected(self):
        self.evidence.write_text("changed after review", encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "pronunciation evidence changed"):
            verify_speech_acceptance(self.acceptance, self.manifest)

    def test_unaccepted_clip_is_rejected(self):
        self.report["results"][0]["accepted"] = False
        self.save_report()
        with self.assertRaisesRegex(PipelineError, "unaccepted clip"):
            verify_speech_acceptance(self.acceptance, self.manifest)

    def test_valid_report_returns_hash_bound_receipt(self):
        self.assertEqual(verify_speech_acceptance(self.acceptance, self.manifest), {
            "path": str(self.acceptance.resolve()), "sha256": file_hash(self.acceptance),
        })
        self.report["inputs"]["prior_manifest"] = None
        self.save_report()
        self.assertEqual(verify_speech_acceptance(self.acceptance, self.manifest)["sha256"],
                         file_hash(self.acceptance))


if __name__ == "__main__":
    unittest.main()
