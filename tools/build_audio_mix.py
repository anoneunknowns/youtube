"""Create original garden SFX and mix a measured timeline; never call a TTS API."""

from __future__ import annotations

import argparse
from array import array
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import uuid
import wave

if __package__:
    from .video_pipeline import PipelineError, english_number, read_json
else:
    from video_pipeline import PipelineError, english_number, read_json


RATE = 48_000
CHANNELS = 2
SAMPLE_WIDTH = 2
CHUNK_FRAMES = 24_000
SEED = 26_111_001
SOUND_IDS = (
    "SE_BIRD", "SE_WIND", "SE_RAINBOW", "SE_PLANE", "SE_BLOOM",
    "SE_LEAF", "SE_CELEBRATE", "SE_READY", "SE_FINISH", "SE_SPARKLE",
)


def number(value, label, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PipelineError(f"{label} must be a finite number")
    value = float(value)
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise PipelineError(f"{label} must be {'positive ' if positive else ''}finite")
    return value


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_new(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(document, output, indent=2, ensure_ascii=False, allow_nan=False)
        output.write("\n")


def _note(samples, start, duration, frequency, end_frequency=None, amplitude=1.0,
          decay=1.5, harmonics=0.10):
    start_frame = round(start * RATE)
    frames = min(round(duration * RATE), len(samples) - start_frame)
    if frames <= 0:
        return
    end_frequency = frequency if end_frequency is None else end_frequency
    for frame in range(frames):
        elapsed = frame / RATE
        position = frame / max(1, frames - 1)
        attack = min(1.0, elapsed / 0.018)
        release = min(1.0, (frames - 1 - frame) / (RATE * min(0.08, duration * 0.35)))
        envelope = math.sin(attack * math.pi / 2) ** 2 * release ** 2 * math.exp(-decay * position)
        phase = 2 * math.pi * (frequency * elapsed +
                               (end_frequency - frequency) * elapsed * elapsed / (2 * duration))
        samples[start_frame + frame] += amplitude * envelope * (
            math.sin(phase) + harmonics * math.sin(2 * phase))


def synthesize_sound(identifier, duration):
    frames = round(duration * RATE)
    if not 0 < frames <= RATE * 5:
        raise PipelineError("SFX design duration must be between one sample and five seconds")
    samples = [0.0] * frames
    rng = random.Random(SEED + SOUND_IDS.index(identifier))
    if identifier == "SE_BIRD":
        _note(samples, 0.025, 0.105, 1450, 2050, decay=0.9, harmonics=0.04)
        _note(samples, 0.16, 0.135, 1720, 2220, amplitude=0.85, decay=0.9, harmonics=0.04)
    elif identifier in ("SE_WIND", "SE_LEAF", "SE_PLANE"):
        fast = slow = 0.0
        for frame in range(frames):
            elapsed = frame / RATE
            position = frame / max(1, frames - 1)
            noise = rng.uniform(-1, 1)
            fast += 0.15 * (noise - fast)
            slow += 0.018 * (noise - slow)
            envelope = math.sin(math.pi * position) ** 2
            if identifier == "SE_WIND":
                sample = (fast - slow) * 0.9
            elif identifier == "SE_LEAF":
                flutter = 0.55 + 0.45 * math.sin(2 * math.pi * 9 * elapsed) ** 2
                sample = (fast - slow) * flutter
            else:
                flutter = 0.8 + 0.2 * math.sin(2 * math.pi * 11 * elapsed)
                phase = 2 * math.pi * (220 * elapsed - 45 * elapsed * elapsed / duration)
                sample = 0.15 * math.sin(phase) * flutter + 0.22 * (fast - slow)
            samples[frame] = sample * envelope
    elif identifier == "SE_RAINBOW":
        _note(samples, 0.025, 0.22, 523.25, decay=1.3, harmonics=0.08)
        _note(samples, 0.265, 0.245, 659.25, amplitude=0.85, decay=1.5, harmonics=0.08)
    elif identifier == "SE_BLOOM":
        _note(samples, 0.018, 0.41, 554.37, decay=4.0, harmonics=0.12)
    elif identifier == "SE_CELEBRATE":
        for start, frequency in ((0.02, 349.23), (0.22, 440.0), (0.42, 523.25)):
            _note(samples, start, 0.21, frequency, decay=1.5, harmonics=0.06)
    elif identifier == "SE_READY":
        _note(samples, 0.015, 0.27, 659.25, decay=2.7, harmonics=0.05)
    elif identifier == "SE_FINISH":
        for start, duration_note, frequency in ((0.02, 0.24, 523.25),
                                               (0.30, 0.24, 440.0),
                                               (0.58, 0.38, 349.23)):
            _note(samples, start, duration_note, frequency, decay=1.6, harmonics=0.06)
    elif identifier == "SE_SPARKLE":
        _note(samples, 0.02, 0.15, 698.46, decay=2.6, harmonics=0.025)
        _note(samples, 0.18, 0.15, 1046.5, amplitude=0.65, decay=2.6, harmonics=0.025)
    peak = max(abs(sample) for sample in samples)
    if peak == 0:
        raise PipelineError(f"{identifier} synthesized silence")
    pcm = array("h")
    for frame, sample in enumerate(samples):
        # This final envelope applies to every sound, including generated noise.
        edge = min(1, frame / (RATE * 0.008), (frames - 1 - frame) / (RATE * 0.025))
        value = round(sample / peak * 0.50 * 32767 * max(0, edge))
        pcm.extend((value, value))
    if sys.byteorder != "little":
        pcm.byteswap()
    return pcm.tobytes()


def pcm_stats(path):
    energy = 0
    peak = sample_count = frames = 0
    with wave.open(str(path), "rb") as source:
        if (source.getframerate(), source.getnchannels(), source.getsampwidth(), source.getcomptype()) != (
                RATE, CHANNELS, SAMPLE_WIDTH, "NONE"):
            raise PipelineError(f"not canonical 48kHz stereo 16-bit PCM: {path}")
        while raw := source.readframes(CHUNK_FRAMES):
            values = array("h")
            values.frombytes(raw)
            if sys.byteorder != "little":
                values.byteswap()
            energy += sum(sample * sample for sample in values)
            peak = max(peak, max((abs(sample) for sample in values), default=0))
            sample_count += len(values)
        frames = source.getnframes()
    if sample_count != frames * CHANNELS:
        raise PipelineError(f"truncated PCM file: {path}")
    return {"frames": frames, "duration_s": frames / RATE, "energy": energy,
            "sample_count": sample_count, "peak": peak,
            "rms": math.sqrt(energy / max(1, sample_count)) / 32768}


def generate_sfx(cue_path, out_dir):
    cues = read_json(cue_path)
    palette = cues.get("palette")
    if not isinstance(palette, list) or len(palette) != len(SOUND_IDS):
        raise PipelineError("expected the garden palette of exactly ten sound effects")
    if any(not isinstance(sound, dict) for sound in palette):
        raise PipelineError("every SFX palette entry must be an object")
    if {sound.get("id") for sound in palette} != set(SOUND_IDS):
        raise PipelineError("unexpected or duplicate garden SFX identifiers")
    out_dir = Path(out_dir)
    targets = [out_dir / f"{identifier}.wav" for identifier in SOUND_IDS]
    targets.extend((out_dir / "generation-spec.json", out_dir / "rights-record.txt"))
    if any(path.exists() for path in targets):
        raise PipelineError("refusing to replace an existing SFX library version")
    out_dir.mkdir(parents=True, exist_ok=True)
    assets = []
    for sound in palette:
        identifier = sound["id"]
        duration = number(sound.get("duration_s"), f"{identifier}.duration_s", positive=True)
        data = synthesize_sound(identifier, duration)
        path = out_dir / f"{identifier}.wav"
        with path.open("xb") as target:
            with wave.open(target, "wb") as output:
                output.setparams((CHANNELS, SAMPLE_WIDTH, RATE, 0, "NONE", "not compressed"))
                output.writeframes(data)
        stats = pcm_stats(path)
        if abs(stats["duration_s"] - duration) > 0.5 / RATE:
            raise PipelineError(f"duration mismatch after SFX generation: {identifier}")
        assets.append({"id": identifier, "name": sound.get("name"),
                       "design_description": sound.get("description"), "path": path.name,
                       "duration_s": stats["duration_s"], "frames": stats["frames"],
                       "sha256": file_hash(path), "peak_dbfs": 20 * math.log10(stats["peak"] / 32768),
                       "rms_dbfs": 20 * math.log10(stats["rms"])})
    receipt = {
        "schema_version": 1, "kind": "original-procedural-sfx-library", "version": "v001",
        "sample_rate": RATE, "channels": CHANNELS, "pcm_bits": 16,
        "random_seed": SEED, "durations_include_fades_and_tails": True,
        "source_cue_sha256": file_hash(cue_path), "generator_sha256": file_hash(__file__),
        "method": "Original sine/chirp/decaying harmonic tones and seeded filtered noise; "
                  "8ms global attack and 25ms global release, plus note-level envelopes.",
        "third_party_recordings": False, "trained_audio_models": False,
        "rights": "Original procedural material created for this repository; no third-party "
                  "recordings or melodies were copied. Public redistribution license is not specified.",
        "assets": assets,
    }
    write_json_new(out_dir / "generation-spec.json", receipt)
    with (out_dir / "rights-record.txt").open("x", encoding="utf-8", newline="\n") as output:
        output.write("Garden SFX v001\n\nOriginal procedural sound effects created for Paspla Studio.\n"
                     "Generated from project-authored sine/chirp envelopes and seeded filtered noise.\n"
                     "No third-party recordings, voice models, songs, or sound libraries were used.\n"
                     "Preserve generation-spec.json, generator source, source palette, and file hashes.\n"
                     "This record does not grant a public redistribution license for the project assets.\n")
    return receipt


def run_ffmpeg(executable, arguments):
    result = subprocess.run([executable, "-hide_banner", "-nostdin", *arguments],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            check=False)
    if result.returncode:
        raise PipelineError(f"FFmpeg failed ({result.returncode}): {result.stderr[-3500:]}")
    return result.stderr


def loudnorm_metrics(log):
    for match in reversed(re.findall(r"\{[^{}]*\}", log, re.DOTALL)):
        try:
            metrics = json.loads(match)
        except json.JSONDecodeError:
            continue
        if "input_i" in metrics:
            for key in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset"):
                if not math.isfinite(float(metrics[key])):
                    raise PipelineError(f"non-finite loudness measurement: {key}")
            return metrics
    raise PipelineError("FFmpeg did not report loudnorm measurements")


def canonical_clip(path, work_dir, ffmpeg):
    path = Path(path).resolve()
    if not path.is_file():
        raise PipelineError(f"audio clip is missing: {path}")
    try:
        stats = pcm_stats(path)
        return path, stats
    except (PipelineError, wave.Error):
        digest = file_hash(path)
        converted = work_dir / f"clip-{digest}.wav"
        if not converted.exists():
            run_ffmpeg(ffmpeg, ["-v", "error", "-n", "-i", str(path), "-vn", "-ar", str(RATE),
                               "-ac", str(CHANNELS), "-c:a", "pcm_s16le", str(converted)])
        return converted, pcm_stats(converted)


def _speech_rows(manifest, manifest_path):
    if manifest.get("schema_version") != 1 or manifest.get("measurement_status") != "measured":
        raise PipelineError("mix requires a measured schema_version 1 speech manifest")
    rows = {}
    for field in ("numbers", "dialogue"):
        if not isinstance(manifest.get(field), list):
            raise PipelineError(f"speech manifest {field} must be an array")
        for row in manifest[field]:
            if not isinstance(row, dict):
                raise PipelineError("speech measurement must be an object")
            if field == "numbers":
                key_value = row.get("number")
                if type(key_value) is not int or not 1 <= key_value <= 10_000:
                    raise PipelineError("speech number must be an integer from 1 to 10000")
                key = ("number", key_value)
                if row.get("spoken_text", english_number(key_value)) != english_number(key_value):
                    raise PipelineError(f"speech number text mismatch: {key_value}")
            else:
                key_value = row.get("spoken_text")
                if not isinstance(key_value, str) or not key_value.strip():
                    raise PipelineError("dialogue spoken_text must be nonempty")
                key = ("dialogue", key_value)
            if key in rows:
                raise PipelineError(f"duplicate speech measurement: {key}")
            duration = number(row.get("duration_s"), f"{key}.duration_s", positive=True)
            path_value = row.get("path")
            if not isinstance(path_value, str) or not path_value.strip():
                raise PipelineError(f"speech clip path is missing: {key}")
            path = Path(path_value)
            if not path.is_absolute():
                path = Path(manifest_path).parent / path
            rows[key] = {"duration_s": duration, "path": path.resolve(), "sha256": row.get("sha256")}
    return rows


def _timeline_events(timeline, rows, sfx_dir):
    duration = number(timeline.get("duration_s"), "timeline.duration_s", positive=True)
    total_frames = round(duration * RATE)
    if total_frames * CHANNELS * SAMPLE_WIDTH + 44 >= 2 ** 32:
        raise PipelineError("timeline is too long for the PCM RIFF working file")
    if not isinstance(timeline.get("events"), list):
        raise PipelineError("timeline.events must be an array")
    events = []
    for raw in timeline["events"]:
        if not isinstance(raw, dict):
            raise PipelineError("timeline event must be an object")
        start = number(raw.get("start_s"), "event.start_s")
        end = number(raw.get("end_s"), "event.end_s", positive=True)
        if end <= start or end > duration + 1 / RATE:
            raise PipelineError("event is outside the timeline")
        kind = raw.get("kind")
        if kind == "speech":
            role = raw.get("role")
            if role == "number":
                value = raw.get("number")
                if type(value) is not int:
                    raise PipelineError("timeline number must be an integer")
                key = ("number", value)
                if raw.get("spoken_text") != english_number(value):
                    raise PipelineError(f"timeline number text mismatch: {value}")
            elif role == "dialogue":
                text = raw.get("spoken_text")
                if not isinstance(text, str) or not text.strip():
                    raise PipelineError("timeline dialogue spoken_text must be nonempty")
                key = ("dialogue", text)
            else:
                raise PipelineError("speech role must be number or dialogue")
            if key not in rows:
                raise PipelineError(f"no measured speech clip for timeline event: {key}")
            row = rows[key]
            if abs(end - start - row["duration_s"]) > 1 / RATE:
                raise PipelineError(f"timeline duration disagrees with speech measurement: {key}")
            path = row["path"]
        elif kind == "sfx":
            identifier = raw.get("id")
            if identifier not in SOUND_IDS:
                raise PipelineError(f"unknown timeline SFX: {identifier!r}")
            key = ("sfx", identifier)
            path = Path(sfx_dir) / f"{identifier}.wav"
        else:
            raise PipelineError("timeline event kind must be speech or sfx; BGM is not supported")
        event = {"key": key, "path": path, "start_s": start, "end_s": end,
                 "start_frame": round(start * RATE), "end_frame": round(end * RATE),
                 "kind": kind, "source": raw.get("source")}
        events.append(event)
    events.sort(key=lambda item: (item["start_frame"], item["end_frame"]))
    for previous, current in zip(events, events[1:]):
        if current["start_frame"] < previous["end_frame"]:
            raise PipelineError(f"audio overlap: {previous['key']} / {current['key']}")
    count_end = timeline.get("count_end")
    numbered = [event["key"][1] for event in events if event["key"][0] == "number"]
    if type(count_end) is not int or not 1 <= count_end <= 10_000 or numbered != list(range(1, count_end + 1)):
        raise PipelineError("timeline must contain every number from 1 through count_end exactly once in order")
    return total_frames, events


def _silence(output, frames):
    while frames:
        chunk = min(frames, CHUNK_FRAMES)
        output.writeframesraw(b"\0" * (chunk * CHANNELS * SAMPLE_WIDTH))
        frames -= chunk


def _write_clip(output, path, frames, gain):
    with wave.open(str(path), "rb") as source:
        remaining = frames
        while remaining:
            count = min(remaining, CHUNK_FRAMES)
            raw = source.readframes(count)
            actual_frames = len(raw) // (CHANNELS * SAMPLE_WIDTH)
            if abs(gain - 1) > 1e-12 and raw:
                values = array("h")
                values.frombytes(raw)
                if sys.byteorder != "little":
                    values.byteswap()
                for index, sample in enumerate(values):
                    value = round(sample * gain)
                    if not -32768 <= value <= 32767:
                        raise PipelineError("gain would clip a PCM sample")
                    values[index] = value
                if sys.byteorder != "little":
                    values.byteswap()
                raw = values.tobytes()
            output.writeframesraw(raw)
            remaining -= actual_frames
            if actual_frames < count:
                # Only the last rounding sample may need silence after resampling.
                if remaining > 1:
                    raise PipelineError("clip became shorter while mixing")
                _silence(output, remaining)
                remaining = 0


def verify_speech_acceptance(acceptance_path, speech_path):
    """Fail closed if reviewed speech or its evidence changed after acceptance."""
    if acceptance_path is None:
        raise PipelineError("mix requires --speech-acceptance from the independent speech review gate")
    acceptance = read_json(acceptance_path)
    if (acceptance.get("kind") != "hash-bound-speech-acceptance"
            or acceptance.get("accepted") is not True
            or acceptance.get("summary", {}).get("unresolved") != 0
            or acceptance.get("inputs", {}).get("manifest", {}).get("sha256") != file_hash(speech_path)):
        raise PipelineError("speech acceptance is missing, unresolved, or for a different manifest")
    for record in acceptance["inputs"].values():
        if record is not None and file_hash(Path(record["path"])) != record["sha256"]:
            raise PipelineError("speech acceptance input changed after review")
    verified = set()
    for result in acceptance.get("results", []):
        if result.get("accepted") is not True:
            raise PipelineError("speech acceptance contains an unaccepted clip")
        for evidence in result.get("pronunciation_evidence", []):
            identity = (evidence["path"], evidence["sha256"])
            if identity not in verified:
                if file_hash(Path(evidence["path"])) != evidence["sha256"]:
                    raise PipelineError("speech pronunciation evidence changed after review")
                verified.add(identity)
    return {"path": str(Path(acceptance_path).resolve()), "sha256": file_hash(acceptance_path)}


def build_mix(timeline_path, speech_path, sfx_dir, out_path, work_base, ffmpeg, sfx_gain_db=-12,
              acceptance_path=None):
    if not math.isfinite(sfx_gain_db) or not -30 <= sfx_gain_db <= -6:
        raise PipelineError("sfx gain must be between -30 and -6 dB relative to active voice RMS")
    timeline = read_json(timeline_path)
    manifest = read_json(speech_path)
    acceptance_receipt = verify_speech_acceptance(acceptance_path, speech_path)
    rows = _speech_rows(manifest, speech_path)
    total_frames, events = _timeline_events(timeline, rows, sfx_dir)
    sfx_receipt = read_json(Path(sfx_dir) / "generation-spec.json")
    registered_sounds = sfx_receipt.get("assets")
    if not isinstance(registered_sounds, list):
        raise PipelineError("SFX library has no registered assets")
    sfx_hashes = {}
    for sound in registered_sounds:
        if not isinstance(sound, dict) or sound.get("id") not in SOUND_IDS:
            raise PipelineError("invalid registered SFX asset")
        if sound["id"] in sfx_hashes:
            raise PipelineError("duplicate registered SFX asset")
        sfx_hashes[sound["id"]] = sound.get("sha256")
    out_path = Path(out_path).resolve()
    receipt_path = out_path.with_suffix(".mix.json")
    if out_path.exists() or receipt_path.exists():
        raise PipelineError("refusing to replace an existing master or mix receipt")
    if not ffmpeg:
        raise PipelineError("FFmpeg is required for resampling and two-pass loudness normalization")
    work_dir = Path(work_base).resolve() / f"audio-mix-{uuid.uuid4().hex}"
    work_dir.mkdir(parents=True, exist_ok=False)
    canonical = {}
    usage = Counter(event["key"] for event in events)
    for event in events:
        key = event["key"]
        if key not in canonical:
            source_hash = file_hash(event["path"])
            if key[0] != "sfx" and rows[key]["sha256"] not in (None, source_hash):
                raise PipelineError(f"speech file checksum mismatch: {key}")
            if key[0] == "sfx" and sfx_hashes.get(key[1]) != source_hash:
                raise PipelineError(f"SFX library checksum mismatch: {key}")
            path, stats = canonical_clip(event["path"], work_dir, ffmpeg)
            canonical[key] = {"path": path, "stats": stats, "source_sha256": source_hash}
        stats = canonical[key]["stats"]
        if abs(stats["duration_s"] - (event["end_s"] - event["start_s"])) > 2 / RATE:
            raise PipelineError(f"actual WAV duration disagrees with timeline: {key}")
    voice_energy = sum(item["stats"]["energy"] * usage[key] for key, item in canonical.items()
                       if key[0] != "sfx")
    voice_samples = sum(item["stats"]["sample_count"] * usage[key] for key, item in canonical.items()
                        if key[0] != "sfx")
    if voice_energy <= 0 or voice_samples <= 0:
        raise PipelineError("measured speech contains no audible signal")
    voice_rms = math.sqrt(voice_energy / voice_samples) / 32768
    gains = {}
    for key, clip in canonical.items():
        gain = 1.0
        if key[0] == "sfx":
            rms = clip["stats"]["rms"]
            if rms <= 0:
                raise PipelineError(f"SFX contains silence: {key}")
            gain = min(voice_rms * 10 ** (sfx_gain_db / 20) / rms,
                       0.95 * 32767 / clip["stats"]["peak"])
        gains[key] = gain
    premaster = work_dir / "premaster-48k-stereo.wav"
    with wave.open(str(premaster), "wb") as output:
        output.setparams((CHANNELS, SAMPLE_WIDTH, RATE, 0, "NONE", "not compressed"))
        cursor = 0
        for event in events:
            _silence(output, event["start_frame"] - cursor)
            _write_clip(output, canonical[event["key"]]["path"],
                        event["end_frame"] - event["start_frame"], gains[event["key"]])
            cursor = event["end_frame"]
        _silence(output, total_frames - cursor)
    measurement = loudnorm_metrics(run_ffmpeg(ffmpeg, ["-v", "info", "-i", str(premaster),
        "-af", "loudnorm=I=-16:TP=-1:LRA=7:print_format=json", "-f", "null", os.devnull]))
    filter_string = (
        "loudnorm=I=-16:TP=-1:LRA=7:linear=true:print_format=json:"
        f"measured_I={measurement['input_i']}:measured_TP={measurement['input_tp']}:"
        f"measured_LRA={measurement['input_lra']}:measured_thresh={measurement['input_thresh']}:"
        f"offset={measurement['target_offset']}"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = loudnorm_metrics(run_ffmpeg(ffmpeg, ["-v", "info", "-n", "-i", str(premaster),
        "-af", filter_string, "-ar", str(RATE), "-ac", str(CHANNELS), "-c:a", "pcm_s24le",
        str(out_path)]))
    with wave.open(str(out_path), "rb") as master:
        if (master.getframerate(), master.getnchannels(), master.getsampwidth()) != (RATE, CHANNELS, 3):
            raise PipelineError("master audio format is incorrect")
        if abs(master.getnframes() - total_frames) > 1:
            raise PipelineError("master duration changed during normalization")
    if abs(float(normalized["output_i"]) + 16) > 1 or float(normalized["output_tp"]) > -0.9:
        raise PipelineError(f"master missed loudness targets: {normalized}")
    receipt = {
        "schema_version": 1, "kind": "rendered-audio-master", "bgm": False,
        "duration_s": total_frames / RATE, "sample_rate": RATE, "channels": CHANNELS,
        "pcm_bits": 24, "audio_event_count": len(events),
        "timeline_sha256": file_hash(timeline_path), "speech_manifest_sha256": file_hash(speech_path),
        "speech_acceptance": acceptance_receipt,
        "master_sha256": file_hash(out_path), "master_path": str(out_path),
        "work_dir": str(work_dir), "normalization": {"method": "FFmpeg loudnorm two-pass",
            "target_i_lufs": -16, "target_tp_dbtp": -1, "first_pass": measurement,
            "second_pass": normalized},
        "sfx_gain_relative_to_active_voice_rms_db": sfx_gain_db,
        "active_voice_rms_dbfs": 20 * math.log10(voice_rms),
        "clips": [{"role": key[0], "identifier": key[1], "uses": usage[key],
                   "source_sha256": clip["source_sha256"],
                   "gain_db": 20 * math.log10(gains[key]),
                   "duration_s": clip["stats"]["duration_s"]}
                  for key, clip in canonical.items()],
    }
    write_json_new(receipt_path, receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate-sfx")
    generate.add_argument("--cues", required=True, type=Path)
    generate.add_argument("--out-dir", required=True, type=Path)
    mix = commands.add_parser("mix")
    for name in ("timeline", "speech-manifest", "sfx-dir", "out", "work-dir"):
        mix.add_argument(f"--{name}", required=True, type=Path)
    mix.add_argument("--ffmpeg", default=shutil.which("ffmpeg"))
    mix.add_argument("--sfx-gain-db", type=float, default=-12)
    mix.add_argument("--speech-acceptance", required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "generate-sfx":
            result = generate_sfx(arguments.cues, arguments.out_dir)
            report = {"generated_sfx": len(result["assets"]), "out_dir": str(arguments.out_dir)}
        else:
            result = build_mix(arguments.timeline, arguments.speech_manifest, arguments.sfx_dir,
                               arguments.out, arguments.work_dir, arguments.ffmpeg, arguments.sfx_gain_db,
                               arguments.speech_acceptance)
            report = {"master": result["master_path"], "duration_s": result["duration_s"],
                      "loudness": result["normalization"]["second_pass"]}
        print(json.dumps(report, ensure_ascii=False, allow_nan=False))
        return 0
    except (PipelineError, OSError, wave.Error, ValueError, OverflowError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
