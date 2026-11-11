"""Screen measured speech for voiced tails after voiceless final consonants.

This is an acoustic review aid, not a pronunciation acceptance gate. It never
edits audio, synthesizes speech, or approves a clip for production. Existing
phonemizer/Node performs text-only en-US G2P; all signal work is Python stdlib.
"""

from __future__ import annotations

import argparse
import array
import cmath
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import wave


TARGETS = frozenset({"s", "k", "t", "f", "θ", "ʃ", "p"})
METHOD = {
    "window_ms": 32, "hop_ms": 10, "analyzed_final_s": 0.42,
    "terminal_noise_search_final_s": 0.30, "end_guard_s": 0.015,
    "voiced_min_frames": 3, "voiced_run_must_reach_final_s": 0.18,
    "voiced_rule": "RMS >= -40 dBFS, under-1kHz power >= 0.60, normalized periodicity >= 0.50",
    "s_noise_rule": "4kHz-up power >= 0.55, centroid >= 3500Hz, periodicity < 0.35, RMS > -45dBFS",
    "sh_noise_rule": "2kHz-up power >= 0.55, centroid >= 2000Hz, periodicity < 0.35, RMS > -45dBFS",
    "other_noise_rule": "2kHz-up power >= 0.35, centroid >= 1700Hz, periodicity < 0.35, RMS > -45dBFS",
    "periodicity": "Maximum normalized autocorrelation, 100-400 Hz; computed only for low-band power >= 0.5 and RMS >= -48dBFS",
    "important_limit": "Heuristic screening only. Stop releases, creaky voice and recording conditions can cause false results. Absence of this pattern is not pronunciation approval. Review phoneme ASR and listen separately.",
}


class TailReviewError(ValueError):
    """Invalid input or a failed read-only review."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fft(values):
    """Return the nonnegative-frequency bins of a zero-padded radix-2 FFT."""
    size = 1
    while size < len(values):
        size *= 2
    data = [complex(value) for value in values] + [0j] * (size - len(values))
    reverse = 0
    for index in range(1, size):
        bit = size >> 1
        while reverse & bit:
            reverse ^= bit
            bit >>= 1
        reverse ^= bit
        if index < reverse:
            data[index], data[reverse] = data[reverse], data[index]
    block = 2
    while block <= size:
        turn = cmath.exp(-2j * math.pi / block)
        for offset in range(0, size, block):
            factor = 1 + 0j
            for index in range(block // 2):
                even = data[offset + index]
                odd = factor * data[offset + index + block // 2]
                data[offset + index] = even + odd
                data[offset + index + block // 2] = even - odd
                factor *= turn
        block *= 2
    return data[:size // 2 + 1], size


def frame_metrics(values, rate):
    energy = sum(value * value for value in values)
    rms = 10 * math.log10(energy / len(values) + 1e-30)
    spectrum, size = fft([
        value * (0.5 - 0.5 * math.cos(2 * math.pi * index / (len(values) - 1)))
        for index, value in enumerate(values)
    ])
    power = [abs(value) ** 2 for value in spectrum]
    total = sum(power) or 1e-30
    low = sum(value for index, value in enumerate(power) if index * rate / size < 1000) / total
    high2 = sum(value for index, value in enumerate(power) if index * rate / size >= 2000) / total
    high4 = sum(value for index, value in enumerate(power) if index * rate / size >= 4000) / total
    centroid = sum(index * rate / size * value for index, value in enumerate(power)) / total
    periodicity, frequency = 0.0, 0.0
    if low >= 0.5 and rms >= -48:
        for lag in range(round(rate / 400), round(rate / 100) + 1):
            left, right = values[:-lag], values[lag:]
            denominator = math.sqrt(sum(value * value for value in left)
                                    * sum(value * value for value in right)) or 1e-30
            score = sum(a * b for a, b in zip(left, right)) / denominator
            if score > periodicity:
                periodicity, frequency = score, rate / lag
    return {"rms_dbfs": rms, "low_ratio_under_1khz": low,
            "high_ratio_2khz_up": high2, "high_ratio_4khz_up": high4,
            "centroid_hz": centroid, "periodicity": periodicity, "period_hz": frequency}


def analyze_samples(samples, rate, terminal):
    if terminal not in TARGETS:
        raise TailReviewError("Expected a target voiceless terminal phoneme")
    if not isinstance(rate, int) or rate < 10_000:
        raise TailReviewError("Sample rate must be at least 10000 Hz for this spectral screen")
    duration = len(samples) / rate
    window_size = round(0.032 * rate)
    # Make an even window, including for uncommon sample rates.
    window_size += window_size % 2
    hop = round(0.010 * rate)
    metrics = []
    start = max(window_size // 2, round((duration - 0.42) * rate))
    for center in range(start, len(samples) - round(0.015 * rate), hop):
        values = samples[center - window_size // 2:center + window_size // 2]
        if len(values) != window_size:
            continue
        metric = frame_metrics(values, rate)
        if terminal == "s":
            noise = metric["high_ratio_4khz_up"] >= 0.55 and metric["centroid_hz"] >= 3500
        elif terminal == "ʃ":
            noise = metric["high_ratio_2khz_up"] >= 0.55 and metric["centroid_hz"] >= 2000
        else:
            noise = metric["high_ratio_2khz_up"] >= 0.35 and metric["centroid_hz"] >= 1700
        noise = (noise and metric["periodicity"] < 0.35 and metric["rms_dbfs"] > -45
                 and center / rate >= duration - 0.30)
        voiced = (metric["low_ratio_under_1khz"] >= 0.60 and metric["periodicity"] >= 0.50
                  and metric["rms_dbfs"] >= -40)
        metric = {key: round(value, 4) for key, value in metric.items()}
        metric.update(time_s=round(center / rate, 6), terminal_noise_candidate=bool(noise),
                      voiced_candidate=bool(voiced))
        metrics.append(metric)
    noises = [index for index, metric in enumerate(metrics) if metric["terminal_noise_candidate"]]
    last_noise = noises[-1] if noises else None
    runs, current = [], []
    if last_noise is not None:
        for metric in metrics[last_noise + 1:]:
            if metric["voiced_candidate"]:
                current.append(metric)
            elif current:
                runs.append(current)
                current = []
        if current:
            runs.append(current)
    good = [run for run in runs if len(run) >= 3 and run[-1]["time_s"] >= duration - 0.18]
    status = ("suspicious_voiced_tail_after_terminal_noise" if good else
              "no_pattern_detected_not_a_listening_approval" if noises else
              "terminal_release_not_resolved_not_a_listening_approval")
    return {
        "duration_s": duration, "status": status, "suspicious": bool(good),
        "last_terminal_noise_s": metrics[last_noise]["time_s"] if last_noise is not None else None,
        "voiced_runs": [{"start_s": run[0]["time_s"], "end_s": run[-1]["time_s"],
                         "frame_count": len(run), "approx_duration_s": round(len(run) * 0.01, 3),
                         "peak_rms_dbfs": max(metric["rms_dbfs"] for metric in run),
                         "max_periodicity": max(metric["periodicity"] for metric in run)} for run in good],
        "frame_measurements": metrics,
    }


def read_clip(entry):
    path = Path(entry["path"])
    data = path.read_bytes()
    if digest(data) != entry["sha256"]:
        raise TailReviewError(f"Audio SHA256 mismatch: {path}")
    try:
        with wave.open(io.BytesIO(data), "rb") as source:
            if source.getnchannels() != 1 or source.getsampwidth() != 2 or source.getcomptype() != "NONE":
                raise TailReviewError(f"Expected mono PCM16 WAV: {path}")
            rate = source.getframerate()
            if rate < 10_000:
                raise TailReviewError(f"Sample rate must be at least 10000 Hz: {path}")
            frames = source.getnframes()
            raw = source.readframes(frames)
    except (EOFError, wave.Error) as error:
        raise TailReviewError(f"Invalid WAV: {path}") from error
    if len(raw) != frames * 2 or not frames:
        raise TailReviewError(f"Empty or truncated WAV: {path}")
    measured = frames / rate
    expected = entry["duration_s"]
    if (isinstance(expected, bool) or not isinstance(expected, (int, float))
            or not math.isfinite(expected) or expected <= 0 or abs(measured - expected) > 1 / rate + 1e-9):
        raise TailReviewError(f"WAV duration does not match metadata: {path}")
    values = array.array("h", raw)
    if sys.byteorder != "little":
        values.byteswap()
    return [value / 32768 for value in values], rate


def classify(manifest, node="node"):
    classifier = Path(__file__).with_name("classify_terminal_phonemes.mjs")
    completed = subprocess.run([node, str(classifier), "--manifest", str(manifest)],
                               check=False, capture_output=True, text=True, encoding="utf-8")
    if completed.returncode:
        raise TailReviewError(f"Text-only G2P failed: {completed.stderr.strip()}")
    try:
        classification = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise TailReviewError("G2P returned invalid JSON") from error
    if classification.get("source_manifest_sha256") != digest(manifest.read_bytes()):
        raise TailReviewError("Manifest changed during G2P classification")
    return classification


def review(manifest, node="node"):
    manifest = Path(manifest).resolve()
    classification = classify(manifest, node)
    results = []
    for row in classification["entries"]:
        # Validate every source checksum/duration, including clips outside the target phonemes.
        samples, rate = read_clip(row)
        if not row["target_voiceless_terminal"]:
            continue
        finding = {key: row[key] for key in
                   ("role", "number", "spoken_text", "phonemes", "terminal_phoneme", "path", "sha256")}
        finding.update(analyze_samples(samples, rate, row["terminal_phoneme"]))
        results.append(finding)
    candidates = [{key: value for key, value in result.items() if key != "frame_measurements"}
                  for result in results if result["suspicious"]]
    tools = [Path(__file__), Path(__file__).with_name("classify_terminal_phonemes.mjs")]
    return {
        "schema_version": 1, "kind": "read-only-terminal-tail-signal-review",
        "source_manifest": str(manifest), "source_manifest_sha256": classification["source_manifest_sha256"],
        "source_audio_modified": False, "audio_generated": False, "screening_only": True,
        "pronunciation_approved": False, "asr_used_for_candidate_decision": False,
        "tools": [{"path": str(tool.resolve()), "sha256": digest(tool.read_bytes())} for tool in tools],
        "method": METHOD, "classification": classification,
        "summary": {"classified_clips": len(classification["entries"]),
                    "analyzed_voiceless_targets": len(results), "suspicious_candidates": len(candidates),
                    "not_resolved_release": sum(result["last_terminal_noise_s"] is None for result in results)},
        "candidates": candidates, "results": results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="Measured speech manifest; WAV paths relative to it")
    parser.add_argument("--out", required=True, type=Path, help="New JSON report; existing files are never overwritten")
    parser.add_argument("--node", default="node", help="Existing shared Node executable (default: OS PATH node)")
    arguments = parser.parse_args(argv)
    if arguments.out.exists():
        raise TailReviewError(f"Output already exists: {arguments.out}")
    report = review(arguments.manifest, arguments.node)
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    with arguments.out.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({"out": str(arguments.out.resolve()), **report["summary"], "screening_only": True}))


if __name__ == "__main__":
    try:
        main()
    except (TailReviewError, OSError, KeyError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
