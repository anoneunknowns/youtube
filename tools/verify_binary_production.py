"""Check measured binary digit audio, display states and delivery timing."""
from __future__ import annotations

import argparse
from array import array
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import wave

if __package__:
    from .prepare_binary_episode import FINALE_LINES, INTRO_LINES
else:
    from prepare_binary_episode import FINALE_LINES, INTRO_LINES


class BinaryValidationError(ValueError):
    """The binary production contract is not satisfied."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finite(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise BinaryValidationError(f"{label} must be a finite number")
    return float(value)


def words(text) -> list[str]:
    return re.findall(r"[a-z]+(?:'[a-z]+)?", str(text).lower())


def load_speech(manifest_path: Path) -> tuple[dict, dict[str, dict]]:
    """Read actual adopted WAVs; never trust a stored duration alone."""
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if manifest.get("measurement_status") != "measured":
        raise BinaryValidationError("Speech manifest must be measured")
    rows = []
    for group in ("clips", "digits", "numbers", "dialogue"):
        value = manifest.get(group, [])
        if isinstance(value, dict):
            rows.extend(dict(row, id=key) for key, row in value.items())
        elif isinstance(value, list):
            rows.extend(value)
        else:
            raise BinaryValidationError(f"Manifest {group} must be an array or object")
    if not rows:
        raise BinaryValidationError("Speech manifest is empty")
    lookup = {}
    checked = {}
    for row in rows:
        if not isinstance(row, dict):
            raise BinaryValidationError("Speech row must be an object")
        clip_path = Path(row.get("path", ""))
        if not clip_path.is_absolute():
            clip_path = manifest_path.parent / clip_path
        clip_path = clip_path.resolve()
        if not clip_path.is_file():
            raise BinaryValidationError(f"Missing speech clip: {clip_path}")
        if clip_path not in checked:
            digest = sha256_file(clip_path)
            try:
                with wave.open(str(clip_path), "rb") as wav:
                    rate = wav.getframerate()
                    duration = wav.getnframes() / rate
                    if wav.getcomptype() != "NONE" or not wav.getnframes():
                        raise BinaryValidationError(f"Expected nonempty PCM WAV: {clip_path}")
            except wave.Error as error:
                raise BinaryValidationError(f"Invalid WAV: {clip_path}") from error
            checked[clip_path] = (digest, duration, rate)
        digest, duration, rate = checked[clip_path]
        if digest != row.get("sha256"):
            raise BinaryValidationError(f"Speech SHA-256 mismatch: {clip_path.name}")
        if abs(duration - finite(row.get("duration_s"), "clip.duration_s")) > 1 / rate:
            raise BinaryValidationError(f"Measured speech duration mismatch: {clip_path.name}")
        entry = dict(row, resolved_path=str(clip_path), actual_duration_s=duration, sample_rate=rate)
        keys = [row.get("id"), row.get("speech_id"), row.get("cue_id")]
        token = words(row.get("spoken_text", row.get("text", "")))
        if token in (["zero"], ["one"]):
            keys.extend([token[0], f"binary-{token[0]}"])
        for key in keys:
            if key is None:
                continue
            if not isinstance(key, str) or not key:
                raise BinaryValidationError("Speech id must be a nonempty string")
            if key in lookup and lookup[key]["sha256"] != digest:
                raise BinaryValidationError(f"Ambiguous speech id: {key}")
            lookup[key] = entry
    return manifest, lookup


def validate_timeline(timeline: dict, speech: dict[str, dict], *, duration_bounds=(480, 540)) -> dict:
    if not isinstance(duration_bounds, (tuple, list)) or len(duration_bounds) != 2:
        raise BinaryValidationError("Duration bounds must contain a minimum and exclusive maximum")
    minimum = finite(duration_bounds[0], "minimum duration")
    maximum = finite(duration_bounds[1], "maximum duration")
    if not 0 < minimum < maximum:
        raise BinaryValidationError("Duration bounds must be positive and increasing")
    duration = finite(timeline.get("duration_s"), "duration_s")
    if not minimum <= duration < maximum:
        raise BinaryValidationError(f"Final duration must be at least {minimum:g} and below {maximum:g} seconds")
    if timeline.get("fps", 30) != 30:
        raise BinaryValidationError("Delivery frame rate must be 30")
    events = timeline.get("events")
    if not isinstance(events, list):
        raise BinaryValidationError("timeline.events must be an array")
    by_type = {}
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise BinaryValidationError("Every event needs a type")
        start = finite(event.get("start_s"), "event.start_s")
        end = finite(event.get("end_s"), "event.end_s")
        if start < 0 or end <= start or end > duration + 1 / 48000:
            raise BinaryValidationError(f"Invalid event interval: {event.get('id', event['type'])}")
        by_type.setdefault(event["type"], []).append(event)
    for group in by_type.values():
        group.sort(key=lambda event: (event["start_s"], event["end_s"]))
    counts = by_type.get("count", [])
    if [row.get("decimal_value", row.get("number")) for row in counts] != list(range(128)):
        raise BinaryValidationError("Must display states 0 through 127 exactly once in order")
    for before, after in zip(counts, counts[1:]):
        if after["start_s"] < before["end_s"] - 1 / 48000:
            raise BinaryValidationError("Count display intervals overlap")
    digits = by_type.get("digit_voice", [])
    if len(digits) != 770:
        raise BinaryValidationError("Expected exactly 770 digit voices")
    if len({event.get("id") for event in digits}) != 770 or any(not event.get("id") for event in digits):
        raise BinaryValidationError("Digit voice ids must be unique and nonempty")
    totals = Counter(event.get("token") for event in digits)
    if totals != Counter({"one": 448, "zero": 322}):
        raise BinaryValidationError("Digit word totals must be 448 one and 322 zero")
    expected_voice_order = []
    clip_use = Counter()
    for number, row in enumerate(counts):
        bits = format(number, "b")
        if row.get("display_binary") != bits:
            raise BinaryValidationError(f"Binary display mismatch at decimal {number}")
        if row.get("number", number) != number:
            raise BinaryValidationError("Count number disagrees with decimal value")
        expected_slots = [None] * (7 - len(bits)) + [int(bit) for bit in bits]
        if "display_slots" in row and row["display_slots"] != expected_slots:
            raise BinaryValidationError(f"Wrong right-aligned display slots at {number}")
        row_digits = [event for event in digits if event.get("decimal_value") == number]
        if len(row_digits) != len(bits):
            raise BinaryValidationError(f"Wrong digit count at decimal {number}")
        if "bit_events" in row:
            nested = row["bit_events"]
            if not isinstance(nested, list) or [item.get("id") for item in nested] != [item["id"] for item in row_digits]:
                raise BinaryValidationError(f"Nested bit events disagree at decimal {number}")
            for a, b in zip(nested, row_digits):
                for key in ("speech_id", "decimal_value", "display_binary", "bit_index", "slot_index", "token", "start_s", "end_s"):
                    if a.get(key) != b.get(key):
                        raise BinaryValidationError(f"Nested digit event differs: {a.get('id')}/{key}")
        for index, (bit, digit) in enumerate(zip(bits, row_digits)):
            token = "one" if bit == "1" else "zero"
            if (digit.get("token"), digit.get("bit_index"), digit.get("slot_index"), digit.get("display_binary")) != (token, index, 7 - len(bits) + index, bits):
                raise BinaryValidationError(f"Digit/token/slot mismatch at {number}:{index}")
            if digit["start_s"] < row["start_s"] or digit["end_s"] > row["end_s"] + 1 / 48000:
                raise BinaryValidationError(f"Digit voice outside displayed state: {number}:{index}")
            speech_id = digit.get("speech_id")
            if speech_id not in speech:
                raise BinaryValidationError(f"Unmeasured speech id: {speech_id}")
            clip = speech[speech_id]
            if words(clip.get("spoken_text", clip.get("text", ""))) != [token]:
                raise BinaryValidationError(f"Digit speech is not the expected single token: {speech_id}")
            if abs(digit["end_s"] - digit["start_s"] - clip["actual_duration_s"]) > 1 / clip["sample_rate"]:
                raise BinaryValidationError(f"Digit interval differs from actual WAV: {number}:{index}")
            if digit.get("source_sha256", digit.get("sha256", clip["sha256"])) != clip["sha256"]:
                raise BinaryValidationError(f"Digit source hash mismatch: {number}:{index}")
            clip_use[speech_id] += 1
            expected_voice_order.append(digit["id"])
        if abs(finite(row.get("voice_end_s"), "count.voice_end_s") - row_digits[-1]["end_s"]) > 1 / 48000:
            raise BinaryValidationError(f"Count voice end disagrees at {number}")
    if [event["id"] for event in digits] != expected_voice_order:
        raise BinaryValidationError("Digit voices cross state boundaries or appear out of order")
    dialogue = by_type.get("dialogue", [])
    for phase, lines in (("intro", INTRO_LINES), ("outro", FINALE_LINES)):
        actual = [words(event.get("text", event.get("spoken_text", ""))) for event in dialogue if event.get("phase") == phase]
        if actual != [words(line[0]) for line in lines]:
            raise BinaryValidationError(f"{phase} dialogue is incomplete or out of order")
    if [words(event.get("text", "")) for event in dialogue if event.get("phase") == "stretch"] != [words("Let's stretch."), words("Ready? Let's keep going!")]:
        raise BinaryValidationError("Stretch and return dialogue are missing or out of order")
    if [words(event.get("text", "")) for event in dialogue if event.get("phase") == "place"] != [words("A new place is ready.")] * 2:
        raise BinaryValidationError("New-place teaching dialogue is missing")
    for event in dialogue:
        identifier = event.get("speech_id", event.get("id"))
        if identifier not in speech:
            raise BinaryValidationError(f"Unmeasured dialogue: {identifier}")
        clip = speech[identifier]
        if words(event.get("text", event.get("spoken_text", ""))) != words(clip.get("spoken_text", clip.get("text", ""))):
            raise BinaryValidationError(f"Dialogue text differs from adopted clip: {identifier}")
        if abs(event["end_s"] - event["start_s"] - clip["actual_duration_s"]) > 1 / clip["sample_rate"]:
            raise BinaryValidationError(f"Dialogue interval differs from actual WAV: {identifier}")
        if event.get("source_sha256", clip["sha256"]) != clip["sha256"]:
            raise BinaryValidationError(f"Dialogue source hash mismatch: {identifier}")
        if event.get("phase") == "intro" and event["end_s"] > counts[0]["start_s"]:
            raise BinaryValidationError("Intro narration extends into counted states")
        clip_use[identifier] += 1
    audio_events = sorted(digits + dialogue + by_type.get("sfx", []), key=lambda event: event["start_s"])
    if not audio_events or audio_events[0]["start_s"] < .8 - 1 / 48000:
        raise BinaryValidationError("Opening must contain at least 0.8 seconds of digital silence")
    for before, after in zip(audio_events, audio_events[1:]):
        if after["start_s"] < before["end_s"] - 1 / 48000:
            raise BinaryValidationError(f"Audio overlap: {before.get('id')} / {after.get('id')}")
    place_sounds = [event for event in by_type.get("sfx", []) if event.get("id") == "SE_PLACE"]
    if [event.get("before_decimal_value") for event in place_sounds] != [2, 4, 8, 16, 32, 64]:
        raise BinaryValidationError("Expected exactly six place chimes before new leading digits")
    for sound in place_sounds:
        row = counts[sound["before_decimal_value"]]
        if sound["start_s"] < row["start_s"] or sound["end_s"] > row["bit_events"][0]["start_s"]:
            raise BinaryValidationError("Place chime must finish before the first spoken digit")
    finish_sounds = [event for event in by_type.get("sfx", []) if event.get("id") == "SE_FINISH"]
    if len(finish_sounds) != 1 or len(by_type.get("sfx", [])) != 7 or finish_sounds[0]["start_s"] < counts[-1]["voice_end_s"]:
        raise BinaryValidationError("Expected one finish sound after the final count and no extra SFX")
    for carry in by_type.get("carry", []):
        number = carry.get("to_decimal")
        if type(number) is not int or not 1 <= number <= 127 or carry.get("from_decimal") != number - 1:
            raise BinaryValidationError("Carry must connect consecutive binary states")
        if carry.get("from_binary") != format(number - 1, "b") or carry.get("to_binary") != format(number, "b"):
            raise BinaryValidationError("Carry comparison has invalid binary values")
        if any(carry["start_s"] < event["end_s"] - 1 / 48000 and carry["end_s"] > event["start_s"] + 1 / 48000 for event in digits + dialogue):
            raise BinaryValidationError("Carry cue must be separate from speech")
    pauses = by_type.get("pause", [])
    pause_states = [event.get("after_decimal_value") for event in pauses]
    if sorted(pause_states) != [7, 31, 63]:
        raise BinaryValidationError("Expected teaching pauses after 7 and 63, and stretch after 31")
    for pause in pauses:
        number = pause["after_decimal_value"]
        expected_kind = "stretch" if number == 31 else "new-place-comparison"
        if pause.get("kind") != expected_kind:
            raise BinaryValidationError("Teaching pause uses the wrong scene")
        if pause["start_s"] < counts[number]["voice_end_s"] - 1 / 48000 or pause["end_s"] > counts[number + 1]["start_s"] + 1 / 48000:
            raise BinaryValidationError("Pause overlaps spoken counting or next display state")
        if pause.get("held_binary", pause.get("display_binary", format(number, "b"))) != format(number, "b"):
            raise BinaryValidationError("Pause must preserve the current correct binary state")
    finales = by_type.get("finale", [])
    if len(finales) != 1 or finales[0]["start_s"] < counts[-1]["voice_end_s"] - 1 / 48000:
        raise BinaryValidationError("Finale must follow the final counted state")
    for event in dialogue:
        phase = event.get("phase")
        if phase == "outro" and event["start_s"] < finales[0]["start_s"]:
            raise BinaryValidationError("Outro narration starts before the finale")
        if phase in ("stretch", "place"):
            candidates = [pause for pause in pauses if (pause["kind"] == "stretch") == (phase == "stretch")]
            if not any(pause["start_s"] <= event["start_s"] and event["end_s"] <= pause["end_s"] for pause in candidates):
                raise BinaryValidationError("Teaching narration is outside its matching pause")
    if "fade_out_start_s" in timeline and any(event["end_s"] > timeline["fade_out_start_s"] for event in digits + dialogue):
        raise BinaryValidationError("Closing fade begins before speech finishes")
    return {
        "passed": True,
        "duration_s": duration,
        "counted_states": len(counts),
        "digit_voices": len(digits),
        "digit_word_totals": dict(totals),
        "dialogue_events": len(dialogue),
        "sfx_events": len(by_type.get("sfx", [])),
        "carry_events": len(by_type.get("carry", [])),
        "teaching_pause_states": pause_states,
        "actual_measured_clip_uses": dict(clip_use),
        "audio_event_overlaps": 0,
        "scope": "Measured source WAVs and schedule; decoded visual correctness requires frame review.",
    }


def _pcm_values(data: bytes) -> array:
    result = array("h")
    result.frombytes(data)
    if sys.byteorder != "little":
        result.byteswap()
    return result


def waveform_correlation(reference, observed, maximum_lag: int = 8) -> tuple[float, int]:
    """Gain-invariant waveform agreement with a small sample-rounding allowance."""
    stride = 8
    expected = reference[::stride]
    energy = sum(value * value for value in expected)
    if energy <= 0:
        raise BinaryValidationError("Reference speech has no measurable audio")
    best, best_lag = -1.0, 0
    for offset in range(2 * maximum_lag + 1):
        actual = observed[offset:offset + len(reference):stride]
        if len(actual) != len(expected):
            continue
        actual_energy = sum(value * value for value in actual)
        if actual_energy <= 0:
            continue
        product = sum(a * b for a, b in zip(expected, actual))
        correlation = product / math.sqrt(energy * actual_energy)
        if correlation > best:
            best, best_lag = correlation, offset - maximum_lag
    return best, best_lag


def verify_rendered_audio(timeline: dict, speech: dict[str, dict], source: Path,
                          minimum_correlation: float = .97) -> dict:
    """Compare every scheduled speech clip with decoded master/AAC samples."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise BinaryValidationError("FFmpeg is required for actual audio correlation")
    source = Path(source).resolve()
    events = sorted((event for event in timeline["events"] if event["type"] in ("digit_voice", "dialogue")),
                    key=lambda event: event["start_s"])
    task_temp = Path("D:/temp")
    references = {}
    results = []
    with tempfile.TemporaryDirectory(prefix="binary-audio-qa-", dir=task_temp if task_temp.is_dir() else None) as folder:
        work = Path(folder)

        def decode(path, output):
            subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-n", "-i", str(path),
                            "-map", "0:a:0", "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(output)],
                           capture_output=True, check=True)

        decoded = work / "decoded.wav"
        decode(source, decoded)
        with wave.open(str(decoded), "rb") as master:
            if abs(master.getnframes() / 48000 - timeline["duration_s"]) > .08:
                raise BinaryValidationError("Decoded audio duration differs from the timeline")
            # Lossy AAC can have pre-echo at a scheduled boundary; the source
            # master and schedule establish the full 0.8-second silent window.
            opening_window = .75 if source.suffix.lower() in (".mp4", ".m4a", ".aac") else .8
            opening = _pcm_values(master.readframes(round(opening_window * 48000)))
            if opening and max(abs(value) for value in opening) > 1:
                raise BinaryValidationError("Decoded opening is not digital silence")
            for event in events:
                identifier = event.get("speech_id", event.get("id"))
                clip = speech[identifier]
                key = clip["sha256"]
                if key not in references:
                    path = work / f"reference-{len(references):03}.wav"
                    decode(clip["resolved_path"], path)
                    with wave.open(str(path), "rb") as reference:
                        references[key] = _pcm_values(reference.readframes(reference.getnframes()))
                reference = references[key]
                nominal = round(event["start_s"] * 48000)
                master.setpos(nominal - 8)
                observed = _pcm_values(master.readframes(len(reference) + 16))
                correlation, lag = waveform_correlation(reference, observed)
                if correlation < minimum_correlation:
                    raise BinaryValidationError(f"Actual speech waveform mismatch: {event['id']} ({correlation:.5f})")
                results.append({"id": event["id"], "speech_id": identifier,
                                "correlation": correlation, "best_lag_samples": lag,
                                "source_sha256": key, "start_s": event["start_s"]})
    return {"passed": True, "path": str(source), "sha256": sha256_file(source),
            "method": "Gain-invariant correlation of each decoded speech interval against canonical-resampled adopted WAV; no text prompt or decimal ASR normalization.",
            "sample_rate": 48000, "maximum_sample_alignment_adjustment": 8,
            "decoded_opening_silence_checked_s": opening_window,
            "minimum_required_correlation": minimum_correlation,
            "minimum_observed_correlation": min(row["correlation"] for row in results),
            "speech_intervals_checked": len(results),
            "digit_intervals_checked": sum(event["type"] == "digit_voice" for event in events),
            "results": results}


def verify_captions(timeline: dict, path: Path) -> dict:
    """Compare delivered SRT words and millisecond boundaries with the plan."""
    def seconds(value):
        match = re.fullmatch(r"(\d+):(\d{2}):(\d{2}),(\d{3})", value)
        if not match:
            raise BinaryValidationError("Invalid SRT timestamp")
        hours, minutes, seconds_value, milliseconds = map(int, match.groups())
        return hours * 3600 + minutes * 60 + seconds_value + milliseconds / 1000

    expected = []
    for event in timeline["events"]:
        if event["type"] == "dialogue":
            expected.append((event["start_s"], event["end_s"], words(event.get("text", event.get("spoken_text")))))
        elif event["type"] == "count":
            expected.append((event["bit_events"][0]["start_s"], event["voice_end_s"],
                             ["one" if bit == "1" else "zero" for bit in event["display_binary"]]))
    expected.sort()
    blocks = re.split(r"\n\s*\n", Path(path).read_text(encoding="utf-8-sig").strip())
    if len(blocks) != len(expected):
        raise BinaryValidationError("SRT must contain every count and dialogue exactly once")
    for index, (block, (start, end, tokens)) in enumerate(zip(blocks, expected), 1):
        lines = block.splitlines()
        if len(lines) < 3 or lines[0] != str(index):
            raise BinaryValidationError("SRT numbering is invalid")
        interval = lines[1].split(" --> ")
        if len(interval) != 2 or abs(seconds(interval[0]) - start) > .00051 or abs(seconds(interval[1]) - end) > .00051:
            raise BinaryValidationError(f"SRT timing mismatch at caption {index}")
        if words(" ".join(lines[2:])) != tokens:
            raise BinaryValidationError(f"SRT token mismatch at caption {index}")
    return {"passed": True, "path": str(Path(path).resolve()), "sha256": sha256_file(Path(path)),
            "captions_checked": len(expected), "binary_count_captions": 128,
            "timestamp_tolerance_s": .00051}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--speech-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--master-audio", type=Path)
    parser.add_argument("--captions", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.out.exists():
            raise BinaryValidationError("Refusing to overwrite an existing QA report")
        timeline = json.loads(args.timeline.read_text(encoding="utf-8-sig"))
        _, speech = load_speech(args.speech_manifest)
        if timeline.get("speech_manifest_sha256", sha256_file(args.speech_manifest)) != sha256_file(args.speech_manifest):
            raise BinaryValidationError("Timeline is bound to a different speech manifest")
        report = validate_timeline(timeline, speech)
        report.update({"schema_version": 1, "kind": "binary-production-qa", "checked_at": datetime.now(timezone.utc).isoformat(),
                       "timeline": {"path": str(args.timeline.resolve()), "sha256": sha256_file(args.timeline)},
                       "speech_manifest": {"path": str(args.speech_manifest.resolve()), "sha256": sha256_file(args.speech_manifest)}})
        if args.master_audio:
            report["master_audio_waveform"] = verify_rendered_audio(timeline, speech, args.master_audio)
        if args.captions:
            report["captions"] = verify_captions(timeline, args.captions)
        if args.video:
            ffprobe = shutil.which("ffprobe")
            if not ffprobe:
                raise BinaryValidationError("ffprobe is required for --video")
            completed = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration:stream=width,height,r_frame_rate,codec_type", "-of", "json", str(args.video)], capture_output=True, text=True, check=True)
            metadata = json.loads(completed.stdout)
            video_duration = float(metadata["format"]["duration"])
            if abs(video_duration - report["duration_s"]) > .08:
                raise BinaryValidationError("Encoded duration does not cover the scheduled audio correctly")
            streams = [stream for stream in metadata["streams"] if stream["codec_type"] == "video"]
            if len(streams) != 1 or (streams[0].get("width"), streams[0].get("height"), streams[0].get("r_frame_rate")) != (1920, 1080, "30/1"):
                raise BinaryValidationError("Expected one 1920x1080 30fps video stream")
            report["video"] = {"path": str(args.video.resolve()), "sha256": sha256_file(args.video), "duration_s": video_duration}
            report["encoded_audio_waveform"] = verify_rendered_audio(timeline, speech, args.video)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8") as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
            output.write("\n")
        print(json.dumps({"passed": True, "report": str(args.out), "states": 128, "digit_voices": 770}))
        return 0
    except (BinaryValidationError, OSError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"Binary QA failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
