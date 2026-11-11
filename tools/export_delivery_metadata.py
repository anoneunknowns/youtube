"""Export matching English subtitles and upload text from a measured timeline."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

def timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, rest = divmod(milliseconds, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    whole, fraction = divmod(rest, 1000)
    return f"{hours:02}:{minutes:02}:{whole:02},{fraction:03}"

def export_metadata(timeline: dict, output_dir: Path, channel: str, video_filename: str | None = None) -> dict:
    count_end = timeline["count_end"]
    events = sorted((row for row in timeline["events"] if row["kind"] == "speech"),
                    key=lambda row: row["start_s"])
    numbers = [row["number"] for row in events if row["role"] == "number"]
    if numbers != list(range(1, count_end + 1)):
        raise ValueError("Subtitle source must count consecutively from 1 to N exactly once")
    output_dir.mkdir(parents=True, exist_ok=True)
    srt = output_dir / "english-captions.srt"
    chapters_path = output_dir / "chapters.txt"
    details_path = output_dir / "upload-details.txt"
    for path in (srt, chapters_path, details_path):
        if path.exists():
            raise ValueError(f"Refusing to overwrite an existing delivery file: {path}")
    lines = []
    for index, row in enumerate(events, 1):
        start, end = row["start_s"], row["end_s"]
        if not all(math.isfinite(v) for v in (start, end)) or not 0 <= start < end:
            raise ValueError("Invalid subtitle timing")
        text = row["spoken_text"]
        text = text[0].upper() + text[1:]
        lines.extend([str(index), f"{timestamp(start)} --> {timestamp(end)}", text, ""])
    srt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    displays = {row["number"]: row for row in timeline["number_displays"]}
    chapters = [(0, "Let's count!")]
    for start in range(1, count_end + 1, 50):
        end = min(count_end, start + 49)
        chapters.append((int(displays[start]["start_s"]), f"Count {start} to {end}"))
    finale = next(row for row in timeline["cue_groups"] if row["role"] == "finale")
    chapters.append((int(finale["anchor_s"]), f"We reached {count_end}!"))
    chapter_lines = [f"{seconds // 60:02}:{seconds % 60:02} {text}" for seconds, text in chapters]
    chapters_path.write_text("\n".join(chapter_lines) + "\n", encoding="utf-8")
    title = f"Count from 1 to {count_end} in English | {channel}"
    video_filename = video_filename or f"{channel.lower().replace(' ', '-')}-count-1-to-{count_end}-1080p.mp4"
    description = (
        f"Count from 1 to {count_end} in English with our red-beret bear.\n"
        "Follow the big numbers and enjoy little garden surprises along the way, "
        "with a gentle stretch break.\n\n" + "\n".join(chapter_lines) +
        f"\n\n{channel}\n"
    )
    details_path.write_text(
        "Title\n" + title + "\n\nDescription\n" + description +
        "\nFiles\n"
        f"Video: {video_filename}\n"
        "Captions: english-captions.srt (English)\n"
        "Thumbnail: assets/library/branding/paspla-studio/v001/exports/thumbnail-3840x2160.jpg\n",
        encoding="utf-8")
    return {"subtitle_count": len(events), "number_count": len(numbers),
            "count_end": count_end, "subtitle_path": str(srt),
            "chapters_path": str(chapters_path), "upload_details_path": str(details_path)}

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--channel", default="Paspla Studio")
    parser.add_argument("--video-filename", help="Actual exported MP4 basename")
    args = parser.parse_args()
    with args.timeline.open(encoding="utf-8-sig") as source:
        result = export_metadata(json.load(source), args.output_dir, args.channel, args.video_filename)
    print(json.dumps(result))

if __name__ == "__main__":
    main()
