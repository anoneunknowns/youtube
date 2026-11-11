"""Verify an encoded delivery video without changing its media or render inputs."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

if __package__:
    from .video_pipeline import PipelineError, read_json
else:
    from video_pipeline import PipelineError, read_json


FPS = 30
RATE = 48_000
MIN_DURATION = 480
MAX_DURATION = 540
REPORT_NAME = "technical-qa.json"


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for data in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def finite_float(value, label):
    if isinstance(value, bool):
        raise PipelineError(f"{label} must be finite")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise PipelineError(f"{label} is missing or invalid") from error
    if not math.isfinite(result):
        raise PipelineError(f"{label} must be finite")
    return result


def safe_rate(value):
    try:
        return Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def run_logged(command, stdout_path, stderr_path):
    started = time.monotonic()
    with stdout_path.open("xb") as output, stderr_path.open("xb") as errors:
        completed = subprocess.run(command, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=errors, check=False)
    return {"exit_code": completed.returncode, "elapsed_s": time.monotonic() - started,
            "command": command, "stdout": str(stdout_path), "stderr": str(stderr_path)}


def parse_loudness(path):
    log = path.read_text(encoding="utf-8", errors="replace")
    for candidate in reversed(re.findall(r"\{[^{}]*\}", log, re.DOTALL)):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "input_i" in value:
            return value
    raise PipelineError("No loudnorm input measurements were reported")


def last_decoded_frame(path):
    frames = re.findall(r"^frame=(\d+)\s*$", path.read_text(encoding="utf-8", errors="replace"), re.MULTILINE)
    if not frames:
        raise PipelineError("Decoder progress did not report a video frame count")
    return int(frames[-1])


def verify_video(video, output_dir, timeline_path=None, ffmpeg=None, ffprobe=None,
                 *, duration_bounds=(MIN_DURATION, MAX_DURATION)):
    if not isinstance(duration_bounds, (tuple, list)) or len(duration_bounds) != 2:
        raise PipelineError("Duration bounds must contain a minimum and exclusive maximum")
    if any(isinstance(value, bool) for value in duration_bounds):
        raise PipelineError("Duration bounds must be finite numbers")
    minimum = finite_float(duration_bounds[0], "minimum duration")
    maximum = finite_float(duration_bounds[1], "maximum duration")
    if not 0 < minimum < maximum:
        raise PipelineError("Duration bounds must be positive and increasing")
    video = Path(video).resolve()
    output_dir = Path(output_dir).resolve()
    if not video.is_file():
        raise PipelineError(f"Video file does not exist: {video}")
    original_stat = video.stat()
    if original_stat.st_size == 0:
        raise PipelineError("Video is empty or the render has not completed")
    report_path = output_dir / REPORT_NAME
    names = (
        REPORT_NAME, "technical-ffprobe.json", "technical-ffprobe.log",
        "technical-decode.progress.txt", "technical-decode.log",
        "technical-loudness.stdout.txt", "technical-loudness.log",
    )
    if any((output_dir / name).exists() for name in names):
        raise PipelineError("Refusing to overwrite an existing QA report or its logs; choose a new output directory")
    ffmpeg = ffmpeg or shutil.which("ffmpeg")
    ffprobe = ffprobe or shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise PipelineError("Registered FFmpeg and ffprobe executables are required")
    timeline = read_json(timeline_path) if timeline_path else None
    timeline_duration = None
    if timeline is not None:
        timeline_duration = finite_float(timeline.get("duration_s"), "timeline.duration_s")
        if timeline_duration <= 0:
            raise PipelineError("timeline.duration_s must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    commands = {
        "ffprobe": [str(ffprobe), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)],
        "decode": [str(ffmpeg), "-nostdin", "-hide_banner", "-v", "error", "-xerror",
                   "-i", str(video), "-map", "0:v", "-map", "0:a", "-progress", "pipe:1",
                   "-nostats", "-f", "null", os.devnull],
        "loudness": [str(ffmpeg), "-nostdin", "-hide_banner", "-i", str(video), "-map", "0:a:0",
                     "-vn", "-af", "loudnorm=I=-16:TP=-1:LRA=7:print_format=json", "-f", "null", os.devnull],
    }
    log_paths = {
        "ffprobe": (output_dir / "technical-ffprobe.json", output_dir / "technical-ffprobe.log"),
        "decode": (output_dir / "technical-decode.progress.txt", output_dir / "technical-decode.log"),
        "loudness": (output_dir / "technical-loudness.stdout.txt", output_dir / "technical-loudness.log"),
    }
    with ThreadPoolExecutor(max_workers=4) as executor:
        tasks = {name: executor.submit(run_logged, command, *log_paths[name])
                 for name, command in commands.items()}
        hash_task = executor.submit(sha256_file, video)
        process_results = {name: task.result() for name, task in tasks.items()}
        digest = hash_task.result()

    errors = []
    probe = {}
    try:
        probe = read_json(log_paths["ffprobe"][0])
    except PipelineError as error:
        errors.append(str(error))
    streams = probe.get("streams", [])
    if not isinstance(streams, list):
        streams = []
    videos = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "audio"]
    visual = videos[0] if videos else {}
    audio = audios[0] if audios else {}
    measurements = {"decode_exit_code": process_results["decode"]["exit_code"],
                    "loudness_exit_code": process_results["loudness"]["exit_code"]}
    format_info = probe.get("format")
    if not isinstance(format_info, dict):
        format_info = {}
    duration = None
    try:
        duration = finite_float(format_info.get("duration"), "ffprobe format duration")
        measurements["duration_s"] = duration
    except PipelineError as error:
        errors.append(str(error))
    decoded_frames = None
    try:
        decoded_frames = last_decoded_frame(log_paths["decode"][0])
        measurements["decoded_video_frames"] = decoded_frames
    except PipelineError as error:
        errors.append(str(error))
    integrated = true_peak = None
    try:
        raw_loudness = parse_loudness(log_paths["loudness"][1])
        integrated = finite_float(raw_loudness.get("input_i"), "loudnorm input_i")
        true_peak = finite_float(raw_loudness.get("input_tp"), "loudnorm input_tp")
        measurements.update(integrated_lufs=integrated, true_peak_dbtp=true_peak,
                            lra_lu=finite_float(raw_loudness.get("input_lra"), "loudnorm input_lra"),
                            loudnorm_raw=raw_loudness,
                            analysis_input_fields="input_i/input_tp measure final encoded AAC, not normalized filter output")
    except PipelineError as error:
        errors.append(str(error))
    declared_frames = None
    try:
        if visual.get("nb_frames") is not None:
            declared_frames = int(visual["nb_frames"])
            measurements["declared_video_frames"] = declared_frames
    except (ValueError, TypeError):
        errors.append("ffprobe did not provide a valid video nb_frames value")
    checks = {
        "ffprobe_exit_zero": process_results["ffprobe"]["exit_code"] == 0,
        "exactly_one_video_and_one_audio": len(videos) == 1 and len(audios) == 1,
        f"duration_{minimum:g}_inclusive_{maximum:g}_exclusive": duration is not None and minimum <= duration < maximum,
        "dimensions_1920x1080": visual.get("width") == 1920 and visual.get("height") == 1080,
        "fps_30": safe_rate(visual.get("r_frame_rate")) == FPS and safe_rate(visual.get("avg_frame_rate")) == FPS,
        "progressive": visual.get("field_order") == "progressive",
        "codec_h264": visual.get("codec_name") == "h264",
        "pixel_format_yuv420p": visual.get("pix_fmt") == "yuv420p",
        "bt709_tags": all(visual.get(key) == "bt709" for key in ("color_space", "color_transfer", "color_primaries")),
        "limited_range": visual.get("color_range") == "tv",
        "audio_aac_48khz_stereo": (audio.get("codec_name") == "aac" and str(audio.get("sample_rate")) == str(RATE)
                                    and audio.get("channels") == 2 and audio.get("channel_layout") == "stereo"),
        "integrated_loudness_within_one_lu": integrated is not None and abs(integrated + 16) <= 1,
        "true_peak_at_or_below_minus_one_with_0_05db_tolerance": true_peak is not None and true_peak <= -0.95,
        "full_decode_exit_zero": process_results["decode"]["exit_code"] == 0,
        "loudness_measurement_exit_zero": process_results["loudness"]["exit_code"] == 0,
        "decoded_frames_match_declared_frames": (decoded_frames is not None and declared_frames is not None
                                                and decoded_frames == declared_frames),
    }
    timeline_info = None
    if timeline is not None:
        expected_frames = math.ceil(timeline_duration * FPS - 1e-9)
        timeline_info = {"path": str(Path(timeline_path).resolve()), "sha256": sha256_file(timeline_path),
                         "duration_s": timeline_duration, "fps": FPS, "expected_video_frames": expected_frames}
        checks["timeline_frame_count"] = decoded_frames == expected_frames
        checks["timeline_container_duration_within_one_frame"] = (
            duration is not None and abs(duration - timeline_duration) <= 1 / FPS + 1e-6)
        try:
            visual_duration = finite_float(visual.get("duration"), "video stream duration")
            audio_duration = finite_float(audio.get("duration"), "audio stream duration")
            measurements.update(video_stream_duration_s=visual_duration, audio_stream_duration_s=audio_duration)
            checks["timeline_video_duration"] = abs(visual_duration - expected_frames / FPS) <= 1e-5
            checks["timeline_audio_duration_within_one_aac_frame"] = abs(audio_duration - timeline_duration) <= 1024 / RATE + 1e-6
        except PipelineError as error:
            errors.append(str(error))
            checks["timeline_video_duration"] = checks["timeline_audio_duration_within_one_aac_frame"] = False
    final_stat = video.stat()
    checks["artifact_unchanged_during_verification"] = (
        original_stat.st_size == final_stat.st_size and original_stat.st_mtime_ns == final_stat.st_mtime_ns)
    report = {
        "schema_version": 1, "status": "pass" if all(checks.values()) and not errors else "fail",
        "artifact": str(video), "sha256": digest, "bytes": original_stat.st_size,
        "checked_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "checks": checks,
        "acceptance": {"duration_s": f"{minimum:g} <= duration < {maximum:g}", "dimensions": [1920, 1080], "fps": FPS,
                       "video_codec": "h264", "pixel_format": "yuv420p", "color_tags": "bt709/tv",
                       "audio_codec": "aac", "sample_rate": RATE, "channels": 2,
                       "integrated_lufs": -16, "integrated_lufs_tolerance": 1,
                       "true_peak_dbtp": -1, "true_peak_tolerance_db": 0.05},
        "measurements": measurements, "timeline": timeline_info, "errors": errors,
        "logs": {"decode": str(log_paths["decode"][1]), "decode_progress": str(log_paths["decode"][0]),
                 "loudness": str(log_paths["loudness"][1]), "ffprobe": str(log_paths["ffprobe"][0]),
                 "ffprobe_stderr": str(log_paths["ffprobe"][1])},
        "commands": commands, "process_results": process_results, "ffprobe": probe,
    }
    with report_path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(report, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeline", type=Path)
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg"))
    parser.add_argument("--ffprobe", default=shutil.which("ffprobe"))
    arguments = parser.parse_args(argv)
    try:
        report = verify_video(arguments.video, arguments.output_dir, arguments.timeline,
                              arguments.ffmpeg, arguments.ffprobe)
        print(json.dumps({"status": report["status"], "report": str(arguments.output_dir.resolve() / REPORT_NAME),
                          "failed_checks": [name for name, passed in report["checks"].items() if not passed],
                          "measurements": report["measurements"]}, ensure_ascii=False, allow_nan=False))
        return 0 if report["status"] == "pass" else 1
    except (PipelineError, OSError, subprocess.SubprocessError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
