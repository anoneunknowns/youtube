"""Make time-labelled contact sheets from the encoded MP4 for visual review."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--timeline", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    timeline = json.loads(args.timeline.read_text(encoding="utf-8-sig"))
    groups = {row["count"]: row for row in timeline["cue_groups"]}
    numbers = {row["number"]: row for row in timeline["number_displays"]}
    samples = [
        ("intro", 1.5), ("greeting", 3.8), ("blank board", 5.3), ("first number", 12.1),
        ("bird", groups[10]["anchor_s"] + 0.8), ("cloud", groups[20]["anchor_s"] + 0.8),
        ("rainbow", groups[30]["anchor_s"] + 0.8), ("airplane", groups[40]["anchor_s"] + 0.8),
        ("first bloom", groups[50]["anchor_s"] + 0.2),
        ("100 celebration", groups[100]["anchor_s"] + 2.8), ("normal count", numbers[128]["start_s"] + 0.3),
        ("200 stretch", groups[200]["anchor_s"] + 3.8), ("200 seated", groups[200]["anchor_s"] + 10),
        ("201 resumes", numbers[201]["start_s"] + 0.3), ("299", numbers[299]["start_s"] + 0.3),
        ("300 finale", groups[300]["anchor_s"] + 0.8), ("farewell", groups[300]["anchor_s"] + 16.5),
        ("final cream", (round(timeline["duration_s"] * 30) - 1) / 30),
    ]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    font_path = ROOT / "assets/library/render-sources/counting-garden/v001/MPLUSRounded1c-Black.ttf"
    font = ImageFont.truetype(str(font_path), 22)
    frames = []
    for index, (label, seconds) in enumerate(samples):
        target = args.output_dir / f"{index + 1:02}-{label.replace(' ', '-')}.png"
        subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-n",
                        "-ss", f"{seconds:.9f}", "-i", str(args.video), "-frames:v", "1", str(target)], check=True)
        frames.append({"label": label, "seconds": seconds, "path": str(target)})
    sheets = []
    for sheet_index, offset in enumerate(range(0, len(frames), 9), 1):
        sheet = Image.new("RGB", (1920, 1200), (255, 245, 221))
        draw = ImageDraw.Draw(sheet)
        for index, row in enumerate(frames[offset:offset + 9]):
            x, y = (index % 3) * 640, (index // 3) * 400
            with Image.open(row["path"]) as frame:
                sheet.paste(frame.resize((640, 360), Image.Resampling.LANCZOS), (x, y))
            draw.text((x + 10, y + 365), f"{row['label']} / {row['seconds']:.3f}s",
                      fill=(104, 63, 31), font=font)
        target = args.output_dir / f"decoded-contact-{sheet_index}.png"
        sheet.save(target)
        sheets.append(str(target))
    report = {"source_video": str(args.video), "frames": frames, "sheets": sheets,
              "method": "Frames decoded directly from the final encoded MP4, not recomposed from source artwork."}
    with (args.output_dir / "visual-samples.json").open("x", encoding="utf-8") as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
    print(json.dumps({"sample_count": len(frames), "contact_sheets": sheets}))

if __name__ == "__main__":
    main()
