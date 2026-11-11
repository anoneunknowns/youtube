"""Validate reusable video metadata and plan timing without generating media.

Speech measurements must describe audible speech after trimming edge silence.
The planner neither synthesizes speech nor changes playback speed.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any


MAX_COUNT = 10_000
MAX_JSON_BYTES = 16 * 1024 * 1024
EPSILON = 1e-8
OUTER_AUDIO_FIELDS = (
    "sfx_id", "relative_start_s", "sfx_duration_s",
    "ordinary_next_speech_not_before_s",
)


class PipelineError(ValueError):
    """A user-actionable metadata or scheduling error."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PipelineError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise PipelineError(f"{label} must be an array")
    if len(value) > MAX_COUNT:
        raise PipelineError(f"{label} exceeds {MAX_COUNT} entries")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PipelineError(f"{label} must be a nonempty string")
    return value


def _integer(value: Any, label: str, minimum: int = 1,
             maximum: int = MAX_COUNT) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise PipelineError(f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PipelineError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise PipelineError(f"{label} must be a finite number") from error
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        qualifier = "positive finite" if positive else "nonnegative finite"
        raise PipelineError(f"{label} must be a {qualifier} number")
    return result


def _schema(document: dict[str, Any], label: str) -> None:
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        raise PipelineError(f"{label}.schema_version must be 1")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PipelineError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise PipelineError(f"non-finite JSON value: {value}")


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise PipelineError(f"non-finite JSON number: {value}")
    return result


def read_json(path: str | Path) -> dict[str, Any]:
    """Read a bounded UTF-8 JSON object; duplicate keys are rejected."""
    path = Path(path)
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise PipelineError(f"JSON input exceeds {MAX_JSON_BYTES} bytes: {path}")
        document = json.loads(raw.decode("utf-8-sig"),
                              object_pairs_hook=_unique_object,
                              parse_constant=_invalid_constant,
                              parse_float=_finite_float)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise PipelineError(f"cannot read JSON {path}: {error}") from error
    return _object(document, str(path))


def english_number(number: int) -> str:
    """Return the project's US-English integer spelling, without 'and'."""
    _integer(number, "number")
    small = ("zero", "one", "two", "three", "four", "five", "six", "seven",
             "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
             "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")
    tens = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
            "eighty", "ninety")
    if number < 20:
        return small[number]
    if number < 100:
        return tens[number // 10] + ("-" + small[number % 10] if number % 10 else "")
    if number < 1000:
        return small[number // 100] + " hundred" + (
            " " + english_number(number % 100) if number % 100 else "")
    return english_number(number // 1000) + " thousand" + (
        " " + english_number(number % 1000) if number % 1000 else "")


def _normalized_words(value: str) -> str:
    return " ".join(value.lower().replace("-", " ").split())


def _check_intervals(events: list[dict[str, Any]], label: str) -> None:
    ordered = sorted(events, key=lambda event: (event["start_s"], event["end_s"]))
    for previous, current in zip(ordered, ordered[1:]):
        if current["start_s"] < previous["end_s"] - EPSILON:
            raise PipelineError(
                f"{label}: audio overlap between {previous.get('id', previous.get('spoken_text'))!r} "
                f"and {current.get('id', current.get('spoken_text'))!r}")


def _validate_block(block: Any, label: str,
                    palette: dict[str, float]) -> dict[str, Any]:
    block = _object(block, label)
    duration = _number(block.get("duration_s"), f"{label}.duration_s", positive=True)
    reserved = []
    for index, raw_event in enumerate(_array(block.get("events"), f"{label}.events")):
        event_label = f"{label}.events[{index}]"
        event = _object(raw_event, event_label)
        kind = event.get("kind")
        if kind == "speech":
            _text(event.get("spoken_text"), f"{event_label}.spoken_text")
            window = _array(event.get("window_s"), f"{event_label}.window_s")
            if len(window) != 2:
                raise PipelineError(f"{event_label}.window_s must contain start and end")
            start = _number(window[0], f"{event_label}.window_s[0]")
            end = _number(window[1], f"{event_label}.window_s[1]")
        elif kind == "sfx":
            identifier = _text(event.get("id"), f"{event_label}.id")
            if identifier not in palette:
                raise PipelineError(f"{event_label}: unknown SFX {identifier}")
            start = _number(event.get("start_s"), f"{event_label}.start_s")
            end = _number(event.get("end_s"), f"{event_label}.end_s")
            if not math.isclose(end - start, palette[identifier], abs_tol=EPSILON):
                raise PipelineError(f"{event_label}: SFX duration must include its full palette tail")
        else:
            raise PipelineError(f"{event_label}.kind must be speech or sfx")
        if end <= start or end > duration + EPSILON:
            raise PipelineError(f"{event_label}: event window is outside its block")
        reserved.append({**event, "start_s": start, "end_s": end})
    _check_intervals(reserved, label)
    return block


@dataclass(frozen=True)
class ValidatedDesign:
    episode: dict[str, Any]
    cue_sheet: dict[str, Any]
    episode_id: str
    count_end: int
    source_count_end: int
    provisional: bool
    target_s: float
    minimum_s: float
    maximum_s: float
    minimum_display_s: float
    ordinary_gap_s: float
    pre_sfx_gap_s: float
    post_sfx_gap_s: float
    palette: dict[str, float]
    count_lines: dict[int, str]
    cues: dict[int, dict[str, Any]]


def validate_design(episode: Any, cue_sheet: Any) -> ValidatedDesign:
    """Validate design metadata; a missing voice ID is allowed at this stage."""
    episode = _object(episode, "episode")
    cue_sheet = _object(cue_sheet, "cue_sheet")
    _schema(episode, "episode")
    _schema(cue_sheet, "cue_sheet")
    episode_id = _text(episode.get("episode_id"), "episode.episode_id")
    if _integer(episode.get("count_start"), "episode.count_start") != 1:
        raise PipelineError("episode.count_start must be 1")
    end = _integer(episode.get("count_end"), "episode.count_end")
    if end % 50:
        raise PipelineError("episode.count_end must be a multiple of 50")
    provisional = episode.get("final_count_provisional")
    if type(provisional) is not bool:
        raise PipelineError("episode.final_count_provisional must be boolean")
    candidates = _array(episode.get("count_end_candidates"), "episode.count_end_candidates")
    seen_candidates = set()
    for candidate in candidates:
        if _integer(candidate, "episode.count_end_candidates entry") % 50:
            raise PipelineError("count_end_candidates must be multiples of 50")
        if candidate in seen_candidates:
            raise PipelineError(f"duplicate count_end_candidate: {candidate}")
        seen_candidates.add(candidate)
    if end not in seen_candidates:
        raise PipelineError("episode.count_end must be one of count_end_candidates")
    duration = _object(episode.get("duration"), "episode.duration")
    target = _number(duration.get("target_s"), "episode.duration.target_s", positive=True)
    minimum = _number(duration.get("min_inclusive_s"), "episode.duration.min_inclusive_s")
    maximum = _number(duration.get("max_exclusive_s"), "episode.duration.max_exclusive_s", positive=True)
    if not minimum <= target < maximum:
        raise PipelineError("episode duration must satisfy min_inclusive_s <= target_s < max_exclusive_s")
    timing = _object(episode.get("timing"), "episode.timing")
    timing_values = [_number(timing.get(key), f"episode.timing.{key}", positive=key == "minimum_display_s")
                     for key in ("minimum_display_s", "ordinary_gap_s", "pre_sfx_gap_s", "post_sfx_gap_s")]
    cue_timing = _object(cue_sheet.get("timing"), "cue_sheet.timing")
    gap_range = _array(cue_timing.get("ordinary_gap_adjustment_range_s"),
                       "cue_sheet.timing.ordinary_gap_adjustment_range_s")
    if len(gap_range) != 2:
        raise PipelineError("ordinary_gap_adjustment_range_s must contain minimum and maximum")
    gap_minimum = _number(gap_range[0], "ordinary gap minimum")
    gap_maximum = _number(gap_range[1], "ordinary gap maximum")
    if not gap_minimum <= timing_values[1] <= gap_maximum:
        raise PipelineError("ordinary_gap_s is outside the cue sheet's adjustment range; "
                            "minimum-display holding is applied separately")
    voice = _object(episode.get("voice"), "episode.voice")
    if voice.get("language") != "en-US" or cue_sheet.get("language") != "en-US":
        raise PipelineError("this counting planner currently requires en-US voice and cue language")

    source_end = _integer(cue_sheet.get("provisional_count"), "cue_sheet.provisional_count")
    if source_end % 50 or end > source_end:
        raise PipelineError("cue source must cover count_end and end at a multiple of 50")
    count_lines: dict[int, str] = {}
    for index, raw_line in enumerate(_array(cue_sheet.get("count_lines"), "cue_sheet.count_lines")):
        line = _object(raw_line, f"count_lines[{index}]")
        number = _integer(line.get("number"), f"count_lines[{index}].number")
        text = _text(line.get("spoken_text"), f"count_lines[{index}].spoken_text")
        if number in count_lines:
            raise PipelineError(f"duplicate count_lines number: {number}")
        if _normalized_words(text) != _normalized_words(english_number(number)):
            raise PipelineError(f"count_lines number {number} has incorrect US-English spoken_text")
        count_lines[number] = text
    if list(count_lines) != list(range(1, source_end + 1)):
        raise PipelineError("count_lines must be ordered, complete, and cover 1 through provisional_count")

    palette: dict[str, float] = {}
    for index, raw_sound in enumerate(_array(cue_sheet.get("palette"), "cue_sheet.palette")):
        sound = _object(raw_sound, f"palette[{index}]")
        identifier = _text(sound.get("id"), f"palette[{index}].id")
        if identifier in palette:
            raise PipelineError(f"duplicate palette ID: {identifier}")
        palette[identifier] = _number(sound.get("duration_s"), f"palette[{index}].duration_s", positive=True)

    intro = _validate_block(cue_sheet.get("intro"), "intro", palette)
    first_count = _number(intro.get("first_count_at_s"), "intro.first_count_at_s")
    if not math.isclose(first_count, intro["duration_s"], abs_tol=EPSILON):
        raise PipelineError("intro.first_count_at_s must equal intro.duration_s")

    cues: dict[int, dict[str, Any]] = {}
    cue_ids = set()
    for index, raw_cue in enumerate(_array(cue_sheet.get("cues"), "cue_sheet.cues")):
        label = f"cues[{index}]"
        cue = _object(raw_cue, label)
        number = _integer(cue.get("count"), f"{label}.count")
        identifier = _text(cue.get("cue_id"), f"{label}.cue_id")
        if number in cues or identifier in cue_ids:
            raise PipelineError(f"duplicate cue number or ID: {number} / {identifier}")
        cue_ids.add(identifier)
        if number not in count_lines or cue.get("spoken_text") != count_lines[number]:
            raise PipelineError(f"{label}: spoken_text does not match count_lines")
        if cue.get("anchor") != f"spoken_end({number})":
            raise PipelineError(f"{label}: anchor must refer to this number's spoken_end")
        block = cue.get("pause_block")
        if block is not None:
            if any(cue.get(key) is not None for key in OUTER_AUDIO_FIELDS):
                raise PipelineError(f"{label}: pause_block requires null outer audio fields")
            _validate_block(block, f"{label}.pause_block", palette)
            resume = block.get("resume_number")
            expected_resume = None if number == source_end else number + 1
            if resume != expected_resume or isinstance(resume, bool):
                raise PipelineError(f"{label}: incorrect resume_number")
        else:
            sfx_id = _text(cue.get("sfx_id"), f"{label}.sfx_id")
            if sfx_id not in palette:
                raise PipelineError(f"{label}: unknown SFX {sfx_id!r}")
            start = _number(cue.get("relative_start_s"), f"{label}.relative_start_s")
            length = _number(cue.get("sfx_duration_s"), f"{label}.sfx_duration_s", positive=True)
            next_time = _number(cue.get("ordinary_next_speech_not_before_s"), f"{label}.ordinary_next_speech_not_before_s")
            if not math.isclose(length, palette[sfx_id], abs_tol=EPSILON):
                raise PipelineError(f"{label}: SFX duration differs from palette")
            if next_time < start + length + timing_values[3] - EPSILON:
                raise PipelineError(f"{label}: next speech would overlap the SFX safety gap")
        cues[number] = cue
    if list(cues) != list(range(10, source_end + 1, 10)):
        raise PipelineError("cues must be ordered, complete, and occur every 10 numbers")
    if cues[source_end].get("pause_block") is None:
        raise PipelineError("source final cue must supply a FINISH pause_block")
    return ValidatedDesign(episode, cue_sheet, episode_id, end, source_end,
                           provisional, target, minimum, maximum, *timing_values,
                           palette, count_lines, cues)


def _duration_measurement(row: dict[str, Any], label: str) -> float:
    duration = None
    if "duration_s" in row:
        duration = _number(row["duration_s"], f"{label}.duration_s", positive=True)
    if "start_s" in row or "end_s" in row:
        start = _number(row.get("start_s"), f"{label}.start_s")
        end = _number(row.get("end_s"), f"{label}.end_s")
        if end <= start:
            raise PipelineError(f"{label}: end_s must be greater than start_s")
        measured = end - start
        if duration is not None and not math.isclose(duration, measured, abs_tol=EPSILON):
            raise PipelineError(f"{label}: duration_s disagrees with start_s/end_s")
        duration = measured
    if duration is None:
        raise PipelineError(f"{label}: missing measured duration_s or start_s/end_s")
    return duration


def _measurements(manifest: Any) -> tuple[dict[int, float], dict[str, float]]:
    manifest = _object(manifest, "speech_manifest")
    _schema(manifest, "speech_manifest")
    if manifest.get("measurement_status") != "measured":
        raise PipelineError("speech_manifest requires measurement_status='measured'; estimated timings are not speech measurements")
    numbers: dict[int, float] = {}
    dialogue: dict[str, float] = {}
    for field, destination in (("numbers", numbers), ("dialogue", dialogue)):
        for index, raw_row in enumerate(_array(manifest.get(field), f"speech_manifest.{field}")):
            label = f"speech_manifest.{field}[{index}]"
            row = _object(raw_row, label)
            key = (_integer(row.get("number"), f"{label}.number") if field == "numbers"
                   else _text(row.get("spoken_text"), f"{label}.spoken_text"))
            if key in destination:
                raise PipelineError(f"duplicate {field} measurement: {key}")
            destination[key] = _duration_measurement(row, label)
    return numbers, dialogue


def _selected_cues(design: ValidatedDesign) -> dict[int, dict[str, Any]]:
    selected = {number: deepcopy(cue) for number, cue in design.cues.items()
                if number <= design.count_end}
    final = selected[design.count_end]
    template = design.cues[design.source_count_end]
    final["pause_block"] = deepcopy(template["pause_block"])
    final["pause_block"]["resume_number"] = None
    final["playback_mode"] = "pause_block_events_only"
    final["bloom_count"] = design.count_end // 50
    for key in OUTER_AUDIO_FIELDS:
        final[key] = None
    return selected


def _canonical_json_sha256(document: dict[str, Any]) -> str:
    """Fingerprint parsed JSON independently of input formatting and key order."""
    try:
        encoded = json.dumps(document, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise PipelineError(f"input cannot be fingerprinted as finite JSON: {error}") from error
    return hashlib.sha256(encoded).hexdigest()


def prepare_audio(episode: Any, cue_sheet: Any) -> dict[str, Any]:
    """Describe text and sound requirements without measurements or generation."""
    design = validate_design(episode, cue_sheet)
    selected = _selected_cues(design)
    voice = design.episode["voice"]
    for key in ("provider", "voice_id"):
        if voice.get(key) is not None:
            _text(voice[key], f"episode.voice.{key}")
    mix = _object(design.cue_sheet.get("mix"), "cue_sheet.mix")
    bgm = mix.get("bgm")
    if type(bgm) is not bool:
        raise PipelineError("cue_sheet.mix.bgm must be boolean")

    dialogue_usage: dict[str, list[dict[str, Any]]] = {}
    sfx_usage: dict[str, list[dict[str, Any]]] = {}

    def add_sfx(identifier: str, start: float, end: float,
                source: str, anchor: str, number: int | None) -> None:
        sfx_usage.setdefault(identifier, []).append({
            "source": source, "anchor": anchor, "number": number,
            "relative_start_s": round(float(start), 9),
            "relative_end_s": round(float(end), 9),
            "duration_s": round(float(end - start), 9),
        })

    def describe_block(block: dict[str, Any], source: str,
                       anchor: str, number: int | None) -> None:
        for event in block["events"]:
            if event["kind"] == "speech":
                start, end = event["window_s"]
                dialogue_usage.setdefault(event["spoken_text"], []).append({
                    "source": source, "anchor": anchor, "number": number,
                    "window_s": [start, end],
                    "max_duration_s": round(float(end - start), 9),
                })
            else:
                add_sfx(event["id"], event["start_s"], event["end_s"],
                        source, anchor, number)

    describe_block(design.cue_sheet["intro"], "intro", "video_start", None)
    for number, cue in selected.items():
        anchor = f"spoken_end({number})"
        if cue.get("pause_block") is not None:
            describe_block(cue["pause_block"], cue["cue_id"], anchor, number)
        else:
            start = max(design.pre_sfx_gap_s, cue["relative_start_s"])
            add_sfx(cue["sfx_id"], start, start + cue["sfx_duration_s"],
                    cue["cue_id"], anchor, number)

    dialogue = [{
        "spoken_text": text,
        "usage_count": len(occurrences),
        "max_duration_s": min(item["max_duration_s"] for item in occurrences),
        "occurrences": occurrences,
    } for text, occurrences in dialogue_usage.items()]
    sounds = []
    for sound in design.cue_sheet["palette"]:
        identifier = sound["id"]
        if identifier not in sfx_usage:
            continue
        sounds.append({
            "id": identifier,
            "name": sound.get("name"),
            "description": sound.get("description"),
            "design_duration_s": sound["duration_s"],
            "duration_includes_tails": True,
            "usage_count": len(sfx_usage[identifier]),
            "occurrences": sfx_usage[identifier],
        })

    return {
        "schema_version": 1,
        "kind": "audio-preparation-plan-only",
        "status": "unmeasured-text-and-cue-plan",
        "measurement_status": "unmeasured-preparation-plan",
        "production_ready": False,
        "audio_generated": False,
        "episode_id": design.episode_id,
        "count_start": 1,
        "count_end": design.count_end,
        "final_count_provisional": design.provisional,
        "bgm": bgm,
        "voice": {
            "language": voice["language"],
            "provider": voice.get("provider"),
            "voice_id": voice.get("voice_id"),
            "selection_status": ("unselected" if voice.get("provider") is None or voice.get("voice_id") is None
                                 else "configured-unverified"),
        },
        "commercial_rights_verified_by_this_tool": False,
        "provider_quota_checked_by_this_tool": False,
        "duration_basis": "Dialogue limits concern audible speech after trimming edge silence. "
                          "SFX lengths are design requirements including fades and tails, not measurements.",
        "dialogue_limit_rule": "max_duration_s is the minimum of all usage-window lengths for the same clip.",
        "input_hashes": {
            "algorithm": "SHA-256",
            "method": "canonical-json-v1",
            "canonicalization": "Python json.dumps(sort_keys=True, ensure_ascii=False, "
                                "separators=(',', ':'), allow_nan=False), UTF-8, no BOM or trailing newline; "
                                "not an RFC 8785 canonicalization claim.",
            "episode_sha256": _canonical_json_sha256(design.episode),
            "cue_sheet_sha256": _canonical_json_sha256(design.cue_sheet),
        },
        "summary": {
            "count_line_count": design.count_end,
            "dialogue_unique_count": len(dialogue),
            "dialogue_usage_count": sum(item["usage_count"] for item in dialogue),
            "sfx_unique_count": len(sounds),
            "sfx_usage_count": sum(item["usage_count"] for item in sounds),
        },
        "count_lines": [{"number": number, "spoken_text": design.count_lines[number]}
                        for number in range(1, design.count_end + 1)],
        "dialogue": dialogue,
        "sfx_palette": sounds,
    }


def build_plan(episode: Any, cue_sheet: Any, speech_manifest: Any) -> dict[str, Any]:
    """Schedule measured speech and SFX; return metadata, never media."""
    design = validate_design(episode, cue_sheet)
    numbers, dialogue = _measurements(speech_manifest)
    missing = sorted(set(range(1, design.count_end + 1)) - numbers.keys())
    if missing:
        raise PipelineError(f"missing measured number durations: {', '.join(map(str, missing))}")
    selected = _selected_cues(design)
    blocks = [design.cue_sheet["intro"]] + [cue["pause_block"] for cue in selected.values()
                                           if cue.get("pause_block") is not None]
    required_dialogue = {event["spoken_text"] for block in blocks for event in block["events"]
                         if event["kind"] == "speech"}
    missing_dialogue = sorted(required_dialogue - dialogue.keys())
    if missing_dialogue:
        raise PipelineError(f"missing measured dialogue durations: {missing_dialogue}")
    events: list[dict[str, Any]] = []

    def play_block(block: dict[str, Any], offset: float, source: str) -> None:
        for event in block["events"]:
            if event["kind"] == "speech":
                text = event["spoken_text"]
                start, ceiling = event["window_s"]
                duration = dialogue[text]
                if duration > ceiling - start + EPSILON:
                    raise PipelineError(f"{source}: measured dialogue exceeds its speech window: {text!r}")
                events.append({"kind": "speech", "role": "dialogue", "spoken_text": text,
                               "start_s": offset + start, "end_s": offset + start + duration,
                               "source": source})
            else:
                events.append({"kind": "sfx", "id": event["id"],
                               "start_s": offset + event["start_s"],
                               "end_s": offset + event["end_s"], "source": source})

    intro = design.cue_sheet["intro"]
    play_block(intro, 0, "intro")
    cursor = float(intro["duration_s"])
    non_counting_duration = cursor
    displays = []
    groups = []
    for number in range(1, design.count_end + 1):
        start = cursor
        end = start + numbers[number]
        events.append({"kind": "speech", "role": "number", "number": number,
                       "spoken_text": design.count_lines[number], "start_s": start,
                       "end_s": end, "source": f"count:{number}"})
        cue = selected.get(number)
        if cue is not None and cue.get("pause_block") is not None:
            block = cue["pause_block"]
            play_block(block, end, cue["cue_id"])
            cursor = end + block["duration_s"]
            non_counting_duration += block["duration_s"]
        elif cue is not None:
            sfx_start = end + max(design.pre_sfx_gap_s, cue["relative_start_s"])
            sfx_end = sfx_start + cue["sfx_duration_s"]
            events.append({"kind": "sfx", "id": cue["sfx_id"], "start_s": sfx_start,
                           "end_s": sfx_end, "source": cue["cue_id"]})
            cursor = max(sfx_end + design.post_sfx_gap_s,
                         end + cue["ordinary_next_speech_not_before_s"],
                         start + design.minimum_display_s)
        else:
            # Minimum display holding may exceed the ordinary gap's adjustment
            # range. It is real counted time, never additional silent padding.
            cursor = max(end + design.ordinary_gap_s, start + design.minimum_display_s)
        displays.append({"number": number, "start_s": start, "end_s": cursor})
        if cue is not None:
            groups.append({"cue_id": cue["cue_id"], "count": number, "anchor_s": end,
                           "role": "finale" if number == design.count_end else (
                               "pause" if cue.get("pause_block") is not None else "ordinary"),
                           "bloom_count": number // 50, "held_number": number,
                           "duration_s": cursor - end})
    _check_intervals(events, "timeline")
    if not design.minimum_s <= cursor < design.maximum_s:
        raise PipelineError(f"planned duration {cursor:.3f}s is outside "
                            f"[{design.minimum_s:g}, {design.maximum_s:g}); "
                            "revise the episode or pacing without stretching measured speech")

    events.sort(key=lambda event: (event["start_s"], event["end_s"]))
    result = {
        "schema_version": 1,
        "status": "metadata-plan-only",
        "episode_id": design.episode_id,
        "count_start": 1,
        "count_end": design.count_end,
        "final_count_provisional": design.provisional,
        "production_ready": False,
        "media_generated": False,
        "measurement_status": "measured",
        "duration_s": cursor,
        "counting_duration_s": cursor - non_counting_duration,
        "non_counting_duration_s": non_counting_duration,
        "target_duration_s": design.target_s,
        "target_deviation_s": cursor - design.target_s,
        "allowed_duration_s": {"min_inclusive": design.minimum_s, "max_exclusive": design.maximum_s},
        "unused_numbers": sorted(set(numbers) - set(range(1, design.count_end + 1))),
        "unused_dialogue": sorted(set(dialogue) - required_dialogue),
        "number_displays": displays,
        "cue_groups": groups,
        "events": events,
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "plan", "prepare-audio"):
        command_parser = subcommands.add_parser(command)
        command_parser.add_argument("--episode", required=True, type=Path)
        command_parser.add_argument("--cues", required=True, type=Path)
        if command == "plan":
            command_parser.add_argument("--speech-manifest", type=Path)
        if command != "validate":
            command_parser.add_argument("--out", required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        episode = read_json(arguments.episode)
        cues = read_json(arguments.cues)
        design = validate_design(episode, cues)
        if arguments.command == "validate":
            print(json.dumps({"valid": True, "production_ready": False,
                              "episode_id": design.episode_id, "count_end": design.count_end,
                              "final_count_provisional": design.provisional,
                              "note": "Design validation only; measured speech and media remain separate."},
                             ensure_ascii=False))
        else:
            if arguments.command == "plan":
                if arguments.speech_manifest is None:
                    raise PipelineError("plan requires --speech-manifest with measured audible speech durations; no media will be generated")
                result = build_plan(episode, cues, read_json(arguments.speech_manifest))
            else:
                result = prepare_audio(episode, cues)
            arguments.out.parent.mkdir(parents=True, exist_ok=True)
            with arguments.out.open("x", encoding="utf-8", newline="\n") as output:
                json.dump(result, output, ensure_ascii=False, indent=2, allow_nan=False)
                output.write("\n")
            report = {"production_ready": False, "out": str(arguments.out)}
            if arguments.command == "plan":
                report.update(planned=True, duration_s=result["duration_s"])
            else:
                report.update(prepared_audio=True, audio_generated=False, summary=result["summary"])
            print(json.dumps(report,
                             ensure_ascii=False))
        return 0
    except (PipelineError, OSError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
