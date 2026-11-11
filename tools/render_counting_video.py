"""Render a measured counting timeline with reusable, registered PNG artwork.

Pillow composes video frames; ffmpeg encodes/muxes them. Original PNGs are never
modified. --demo --sample-reel is an explicitly synthetic, silent motion check.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import dataclass
from functools import lru_cache
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SIZE = (1920, 1080)
FPS = 30
CREAM = (255, 245, 221)
BROWN = (104, 63, 31)
DEFAULT_BACKGROUND = "assets/library/render-sources/counting-garden/v001/garden-background.png"
DEFAULT_THEME = "design/counting-video-v1/themes/bright-garden-v002.json"


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def local_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def output_path(value: str | Path) -> Path:
    """Keep render artifacts away from immutable library/original inputs."""
    path = local_path(value).resolve()
    allowed = (ROOT / "output").resolve()
    if not path.is_relative_to(allowed) or path == allowed:
        raise ValueError(f"Render artifacts must be below {allowed}: {path}")
    return path


def color(value: Any, default: tuple[int, ...]) -> tuple[int, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return ImageColor.getrgb(value)
    if not isinstance(value, (list, tuple)) or len(value) not in (3, 4):
        raise ValueError("Theme colors must be RGB/RGBA arrays or Pillow color strings")
    if any(not isinstance(channel, int) or not 0 <= channel <= 255 for channel in value):
        raise ValueError("Theme color channels must be integers from 0 to 255")
    return tuple(value)


def reference_sprite(reference: dict[str, Any]) -> Image.Image:
    """Read a registered theme sprite without altering its original PNG."""
    image = Image.open(local_path(reference["image_path"])).convert("RGBA")
    region = reference.get("source_box_xywh", reference.get("region_xywh", reference.get("box_xywh")))
    if reference.get("registration_path"):
        registration = read_json(local_path(reference["registration_path"]))
        name = reference.get("region_name")
        if not name or name not in registration.get("regions", {}):
            raise ValueError(f"Theme sprite has no registered region: {name}")
        region = registration["regions"][name]
        if isinstance(region, dict):
            region = region.get("box_xywh", region.get("region", region.get("region_px")))
    if region is not None:
        if not isinstance(region, list) or len(region) != 4 or not all(
                isinstance(value, (int, float)) and math.isfinite(value) for value in region):
            raise ValueError("Theme sprite crop must be a registered x,y,width,height array")
        x, y, width, height = region
        if min(x, y) < 0 or min(width, height) <= 0 or x + width > image.width or y + height > image.height:
            raise ValueError("Theme sprite region is outside its source PNG")
        image = image.crop(box_xywh(region))
    return image


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def smooth(value: float) -> float:
    value = clamp(value)
    return value * value * (3 - 2 * value)


def blend_window(age: float, length: float, fade: float = 0.3) -> float:
    return min(smooth(age / fade), smooth((length - age) / fade))


def box_xywh(box: list[float]) -> tuple[int, int, int, int]:
    x, y, width, height = box
    return round(x), round(y), round(x + width), round(y + height)


def resized(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return image.resize((max(1, size[0]), max(1, size[1])), Image.Resampling.LANCZOS)


def opacity(image: Image.Image, value: float) -> Image.Image:
    if value >= 0.999:
        return image
    result = image.copy()
    result.putalpha(result.getchannel("A").point(lambda alpha: round(alpha * clamp(value))))
    return result


def paste(target: Image.Image, sprite: Image.Image, xy: tuple[float, float], alpha: float = 1) -> None:
    if alpha <= 0:
        return
    sprite = opacity(sprite, alpha)
    target.paste(sprite, (round(xy[0]), round(xy[1])), sprite)


@dataclass(frozen=True)
class Segment:
    start_s: float
    duration_s: float
    label: str


class Timeline:
    def __init__(self, plan: dict[str, Any], cues: dict[str, Any]):
        self.plan = plan
        self.duration = float(plan["duration_s"])
        self.count_end = int(plan["count_end"])
        self.numbers = sorted(plan["number_displays"], key=lambda row: float(row["start_s"]))
        if [int(row["number"]) for row in self.numbers] != list(range(1, self.count_end + 1)):
            raise ValueError("Timeline must display every number from 1 to N exactly once, in order")
        self.starts = [float(row["start_s"]) for row in self.numbers]
        if any(self.starts[i] >= self.starts[i + 1] for i in range(len(self.starts) - 1)):
            raise ValueError("Number display starts must strictly increase")
        self.cue_specs = {int(row["count"]): row for row in cues["cues"]}
        self.groups = sorted(plan.get("cue_groups", []), key=lambda row: float(row["anchor_s"]))
        self.group_starts = [float(group["anchor_s"]) for group in self.groups]
        self.by_count = {int(group["count"]): group for group in self.groups}
        self.finale = next((group for group in self.groups if group.get("role") == "finale"), None)
        if self.finale is None and self.count_end in self.by_count:
            self.finale = self.by_count[self.count_end]
        self.bloom_times = [
            (float(group["anchor_s"]) + (0 if int(group["count"]) == self.count_end else 0.1),
             int(group.get("bloom_count", int(group["count"]) // 50)))
            for group in self.groups if int(group["count"]) % 50 == 0
        ]

    def number_at(self, seconds: float) -> tuple[int | None, float]:
        index = bisect_right(self.starts, seconds) - 1
        return (None, 0) if index < 0 else (int(self.numbers[index]["number"]), self.starts[index])

    def blooms_at(self, seconds: float) -> int:
        blooms = 0
        for start, count in self.bloom_times:
            if seconds >= start:
                blooms = max(blooms, count)
        return min(self.count_end // 50, blooms)

    def active_group(self, seconds: float) -> tuple[dict[str, Any] | None, float]:
        index = bisect_right(self.group_starts, seconds) - 1
        if index < 0:
            return None, 0
        group = self.groups[index]
        spec = self.cue_specs.get(int(group["count"]), {})
        length = max(float(group.get("duration_s") or 0), float(spec.get("visual_duration_s") or 0))
        age = seconds - float(group["anchor_s"])
        return (group, age) if age < length else (None, 0)

    def sample_segments(self) -> list[Segment]:
        segments = [Segment(0, 3, "intro"), Segment(max(0, self.starts[0] - 0.5), 3, "first number")]
        for count, offset, length, label in (
            (10, 0, 3.5, "bird"), (40, 0, 3.5, "airplane"),
            (100, 0, 4, "100 celebration"), (200, 2.1, 3.2, "sit and stretch"),
            (200, 11.8, 3, "return standing"), (self.count_end, 0, 3, "finale"),
            (self.count_end, 16, 4, "closing fade"),
        ):
            if count in self.by_count:
                start = float(self.by_count[count]["anchor_s"]) + offset
                segments.append(Segment(start, min(length, self.duration - start), label))
        return [segment for segment in segments if segment.duration_s > 0]

    def cue_segments(self) -> list[Segment]:
        """Short source-time excerpts of all thirty cues, not a new schedule."""
        segments = [Segment(.6, 1.5, "intro header"), Segment(11.3, .7, "intro glance")]
        for group in self.groups:
            count, anchor = int(group["count"]), float(group["anchor_s"])
            if count == 100:
                segments.append(Segment(anchor + 4.9, 3.1, "100 rainbow continuous fade"))
            elif count == 200:
                segments.extend([Segment(anchor + 2.1, 3.2, "200 seated stretch"),
                                 Segment(anchor + 17.7, 2.3, "200 return and glance")])
            elif group.get("role") == "finale":
                segments.extend([Segment(anchor + 6.8, 1.7, "300 seven-second wave"),
                                 Segment(anchor + 17.5, 2.5, "300 cream fade")])
            else:
                offset = 1.7 if count == 240 else 1.0 if count in (120, 140) else .8 if count in (190, 280) else .1
                length = float(self.cue_specs[count].get("visual_duration_s", 3.5))
                segments.append(Segment(anchor + offset, min(1.8, length - offset), f"CUE {count:03d}"))
        return segments


def demo_plan(cue_sheet: dict[str, Any], count_end: int = 300) -> dict[str, Any]:
    """Synthetic silent schedule for motion review, never a measured audio plan."""
    cursor = 12.0
    numbers: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    for number in range(1, count_end + 1):
        start = cursor
        cursor += 1.5
        if number % 10 == 0:
            spec = next(row for row in cue_sheet["cues"] if row["count"] == number)
            pause = 20 if number == count_end else 20 if number == 200 else 8 if number == 100 else 0
            groups.append({
                "cue_id": spec["cue_id"], "count": number, "anchor_s": cursor,
                "role": "finale" if number == count_end else "pause" if pause else "ordinary",
                "bloom_count": number // 50, "held_number": number,
                "duration_s": pause or float(spec["visual_duration_s"]),
            })
            cursor += pause
        numbers.append({"number": number, "start_s": start, "end_s": cursor})
    return {"schema_version": 1, "duration_s": cursor, "count_end": count_end,
            "number_displays": numbers, "cue_groups": groups, "events": [],
            "synthetic_demo_only": True}


class Artwork:
    def __init__(self, manifest: dict[str, Any], sprite_overrides: dict[str, Any] | None = None):
        self.manifest = manifest
        self.images = {key: Image.open(local_path(row["path"])).convert("RGBA")
                       for key, row in manifest["images"].items()}
        self.font_path = local_path(manifest["font"]["path"])
        self.overrides = {name: reference_sprite(reference) for name, reference in (sprite_overrides or {}).items()}

    @lru_cache(maxsize=96)
    def region(self, name: str, width: int, height: int, mirror: bool = False) -> Image.Image:
        if name in self.overrides:
            image = self.overrides[name].copy()
        else:
            row = self.manifest["regions"][name]
            image = self.images[row["source"]].crop(box_xywh(row["box_xywh"]))
        image.thumbnail((width, height), Image.Resampling.LANCZOS)
        return ImageOps.mirror(image) if mirror else image

    @lru_cache(maxsize=32)
    def font(self, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(self.font_path), size)


class Bear:
    """Registered sprite geometry; source pixels and aspect ratios stay unchanged."""

    def __init__(self, natural_height: float = 650, root: tuple[float, float] | None = None):
        self.height = natural_height
        # A small scene-wide left margin also keeps the new stretch hand clear
        # of the board; every pose uses this same root without a per-pose shift.
        self.root = root if root is not None else (435.0, 840.0)
        if not math.isfinite(natural_height) or natural_height <= 0 or len(self.root) != 2 or not all(
                math.isfinite(value) for value in self.root):
            raise ValueError("Theme bear requires a positive height and a finite two-coordinate root")
        self.canonical = Image.open(local_path(
            "assets/library/characters/bear-beret/references/canonical-neutral-v001.png")).convert("RGBA")
        source_dir = ROOT / "assets/library/characters/bear-beret/sources/v001"
        self.reactions = Image.open(source_dir / "reactions-v2.png").convert("RGBA")
        self.playful = Image.open(source_dir / "playful-v1.png").convert("RGBA")
        self.reaction = read_json(source_dir / "reactions-registration-v4.json")["characters"]["bear-beret"]
        self.idle = read_json(source_dir / "idle-registration-v1.json")["characters"]["bear-beret"]
        wave_dir = ROOT / "assets/library/characters/bear-beret/animations/wave/v001"
        self.wave = Image.open(wave_dir / "wave-sheet.png").convert("RGBA")
        self.wave_registration = read_json(wave_dir / "registration.json")
        postures_dir = ROOT / "assets/library/characters/bear-beret/animations/postures/v001"
        self.postures = Image.open(postures_dir / "postures-sheet.png").convert("RGBA")
        self.postures_registration = read_json(postures_dir / "registration.json")
        self.postures_scale = (natural_height / self.reaction["neutral_natural_height_px"]
                               * self.postures_registration["head_width_calibration"]["sheet_to_canonical_width_ratio"])
        self.frames = {row["id"]: row for row in self.reaction["frames"]}
        self.idle_frames = {row["id"]: row for row in self.idle["frames"]}
        canonical_visible = self.reaction["neutral_visible_bbox_px"]
        canonical_visible_height = canonical_visible[3] - canonical_visible[1]
        wave_visible = self.wave_registration["frames"][0]["visible_bbox_alpha128"]
        wave_visible_height = wave_visible[3] - wave_visible[1]
        self.wave_scale = (natural_height / self.reaction["neutral_natural_height_px"]
                           * canonical_visible_height / wave_visible_height)

    @lru_cache(maxsize=28)
    def sprite(self, name: str) -> tuple[Image.Image, tuple[float, float]]:
        if name == "neutral":
            image = self.canonical
            scale = self.height / self.reaction["neutral_natural_height_px"]
            anchor = self.reaction["neutral_anchor_px"]
            shift = (-anchor[0], -anchor[1])
        elif name.startswith("wave_"):
            row = self.wave_registration["frames"][int(name.split("_")[1])]
            image = self.wave.crop(box_xywh(row["region"]))
            scale = self.wave_scale
            anchor = row["support_anchor_local"]
            shift = (-anchor[0], -anchor[1])
        elif name in ("posture_standing", "half_seated", "seated_neutral", "seated_stretch"):
            index = {"posture_standing": 0, "half_seated": 1, "seated_neutral": 2, "seated_stretch": 3}[name]
            row = self.postures_registration["frames"][index]
            image = self.postures.crop(box_xywh(row["region"]))
            scale = self.postures_scale
            anchor = row["support_anchor_local"]
            shift = (-anchor[0], -anchor[1])
        else:
            idle = name in self.idle_frames
            profile = self.idle if idle else self.reaction
            row = (self.idle_frames if idle else self.frames)[name]
            image = (self.playful if idle else self.reactions).crop(box_xywh(row["region_px"]))
            scale = self.height / profile["atlas_natural_height_px"]
            anchor = profile["atlas_anchor_px"]
            shift = (row["translation_px"][0] - anchor[0], row["translation_px"][1] - anchor[1])
            if row.get("rotation_degrees", 0):
                raise ValueError("This renderer does not use the registered rotated nap pose")
        image = resized(image, (round(image.width * scale), round(image.height * scale)))
        return image, (self.root[0] + shift[0] * scale, self.root[1] + shift[1] * scale)

    @staticmethod
    def wave_pose(age: float) -> str:
        sequence = [(0, 3), (1, 5), (2, 6), (3, 8), (2, 6), (1, 5), (0, 3)]
        frame = min(35, max(0, int(age * FPS)))
        for index, duration in sequence:
            if frame < duration:
                return f"wave_{index}"
            frame -= duration
        return "wave_0"

    @staticmethod
    def short_transition(first: str, second: str, progress: float) -> list[tuple[str, float]]:
        # Completed drawings have different face/hat positions. A deliberate
        # sprite pose cut avoids a dissolve producing two eyes and two hats.
        return [(first if progress < 0.5 else second, 1)]

    def poses(self, seconds: float, group: dict[str, Any] | None, age: float,
              bright: bool = False) -> list[tuple[str, float]]:
        if bright:
            # The original plan permits brief existing-pose expressions; it
            # does not require a new head/eye rig or alter the counting audio.
            if 11.3 <= seconds < 11.7:
                return [("think", 1)]
            if group is not None:
                count = int(group["count"])
                if group.get("role") == "finale" and 7 <= age < 8.2:
                    return [(self.wave_pose(age - 7), 1)]
                if count == 10 and .25 <= age < 1.1:
                    return [("think", 1)]
                if count == 200 and 18.1 <= age < 18.35:
                    return [("think", 1)]
                if count == 250:
                    return [("think" if .3 <= age < 1.05 else "neutral", 1)]
                if count == 150:
                    return [("neutral", 1)]
                clap = count == 50 and .2 <= age < 1.4 or count == 100 and 2.4 <= age < 3.6
                if clap:
                    start = .2 if count == 50 else 2.4
                    return [("cheer" if int((age - start) * 5) % 2 == 0 else "success_ready", 1)]
        if 3.2 <= seconds < 4.4:
            return [(self.wave_pose(seconds - 3.2), 1)]
        if group is not None:
            count = int(group["count"])
            if group.get("role") == "finale":
                if 4.6 <= age < 5.6:
                    return [("success_air" if age < 5.1 else "success_land", 1)]
                if 10 <= age < 14 or 14 <= age < 16:
                    return [(self.wave_pose((age - 10) % 1.2), 1)]
                if 16 <= age < 17.2:
                    return [(self.wave_pose(age - 16), 1)]
                return [("neutral", 1)]
            if count == 200:
                if 2.2 <= age < 3:
                    progress = (age - 2.2) / 0.8
                    return [("neutral" if progress < .2 else "half_seated" if progress < .75 else "seated_neutral", 1)]
                if 3 <= age < 5:
                    if age < 3.2:
                        return self.short_transition("seated_neutral", "seated_stretch", (age - 3) / 0.2)
                    if age > 4.8:
                        return self.short_transition("seated_stretch", "seated_neutral", (age - 4.8) / 0.2)
                    return [("seated_stretch", 1)]
                if 5 <= age < 12:
                    return [("seated_neutral", 1)]
                if 12 <= age < 14:
                    progress = (age - 12) / 2
                    return [("seated_neutral" if progress < .25 else "half_seated" if progress < .8 else "neutral", 1)]
                if 18.6 <= age < 18.8:
                    return [("blink", 1)]
                return [("neutral", 1)]
            if count == 100:
                if age < 1.2:
                    return [("success_ready" if age < 0.2 else "success_air" if age < 0.7 else
                             "success_land" if age < 0.9 else "neutral", 1)]
                if 2.4 <= age < 3.6:
                    return [("cheer" if int((age - 2.4) * 4) % 2 == 0 else "neutral", 1)]
                return [("neutral", 1)]
            if count % 50 == 0 and 0.2 <= age < 1.4:
                return [("cheer" if int((age - 0.2) * 3) % 2 == 0 else "neutral", 1)]
        # One brief blink every few seconds, independent of the spoken numbers.
        return [("blink" if seconds >= 12 and 2.8 <= seconds % 5.7 < 2.96 else "neutral", 1)]

    def draw(self, frame: Image.Image, poses: list[tuple[str, float]], alpha: float = 1,
             offset_y: float = 0) -> None:
        for name, weight in poses:
            sprite, xy = self.sprite(name)
            paste(frame, sprite, (xy[0], xy[1] + offset_y), weight * alpha)


class Scene:
    def __init__(self, timeline: Timeline, artwork: Artwork, background: Path,
                 theme: dict[str, Any] | None = None):
        self.timeline = timeline
        self.art = artwork
        self.theme = theme or {}
        self.bright = (self.theme.get("theme_id") == "counting-garden-original-blue-sky-v001"
                       or self.theme.get("baseline_theme_id") == "counting-garden-original-blue-sky-v001")
        self.ink_centered = self.theme.get("alignment", {}).get("mode") == "ink_bbox"
        self.bright_effects = None
        if self.bright:
            from bright_garden_effects import BrightGardenEffects
            self.bright_effects = BrightGardenEffects(artwork)
        bear = self.theme.get("bear", {})
        root = tuple(float(value) for value in bear["root"]) if "root" in bear else None
        self.bear = Bear(float(bear.get("natural_height_px", 650)), root)
        self.digit_color = color(self.theme.get("digit_color"), BROWN)
        self.background = ImageOps.fit(Image.open(background).convert("RGB"), SIZE, Image.Resampling.LANCZOS)
        self.board_layer = self.make_board()
        self.header_layer = self.make_header() if self.bright else None
        self.shadow_layer = Image.new("RGBA", SIZE)
        if bear:
            radius = 220 * self.bear.height / 650
            shadow = (self.bear.root[0] - radius, self.bear.root[1] - 16,
                      self.bear.root[0] + radius, self.bear.root[1] + 24)
        else:
            shadow = (215, 824, 655, 864)
        ImageDraw.Draw(self.shadow_layer).ellipse(shadow, fill=(115, 120, 60, 38))
        self.milestones = list(range(50, timeline.count_end + 1, 50))
        self.positions = [360 + index * 1150 / max(1, len(self.milestones) - 1)
                          for index in range(len(self.milestones))]
        positions = self.theme.get("progress", {}).get("milestone_x")
        if positions is not None:
            if len(positions) != len(self.milestones) or not all(
                    isinstance(value, (int, float)) and math.isfinite(value) for value in positions):
                raise ValueError("Theme progress.milestone_x must contain one finite position per milestone")
            self.positions = list(positions)
        self._cached_key: tuple[Any, ...] | None = None
        self._cached_frame: Image.Image | None = None

    def make_board(self) -> Image.Image:
        layer = Image.new("RGBA", SIZE)
        draw = ImageDraw.Draw(layer)
        board = self.theme.get("board", {})
        if board.get("image_path"):
            x, y, width, height = board.get("bbox_xywh", [720, 240, 880, 540])
            if min(width, height) <= 0:
                raise ValueError("Theme board has invalid destination dimensions")
            paste(layer, resized(reference_sprite(board), (round(width), round(height))), (x, y))
        else:
            draw.rounded_rectangle((727, 252, 1606, 792), radius=65, fill=(120, 82, 35, 34))
            draw.rounded_rectangle((720, 240, 1600, 780), radius=65,
                                   fill=color(board.get("outer_fill"), (220, 176, 112)),
                                   outline=color(board.get("outer_outline"), (139, 92, 47)), width=7)
            draw.rounded_rectangle((735, 254, 1585, 764), radius=52,
                                   fill=color(board.get("rim_fill"), (245, 218, 174)),
                                   outline=color(board.get("rim_outline"), (236, 197, 139)), width=4)
            draw.rounded_rectangle((753, 272, 1567, 746), radius=38,
                                   fill=color(board.get("inner_fill"), (255, 247, 226)),
                                   outline=color(board.get("inner_outline"), (190, 143, 86)), width=3)
            for index in range(11):
                y = 260 + index * 45
                draw.line((738, y, 743, y + 7), fill=color(board.get("grain_color"), (193, 145, 89)), width=2)
                draw.line((1578, y, 1584, y + 8), fill=color(board.get("grain_color"), (193, 145, 89)), width=2)
        if not self.bright:
            draw.rounded_rectangle((770, 42, 1150, 142), radius=45,
                                   fill=color(board.get("header_fill"), (255, 247, 226)),
                                   outline=color(board.get("header_outline"), (160, 111, 60)), width=4)
            if self.ink_centered:
                self.header_text(layer)
            else:
                self.center_text(draw, (960, 89), f"1 → {self.timeline.count_end}",
                                 self.art.font(int(board.get("header_font_size", 49))), self.digit_color)
        return layer

    def make_header(self) -> Image.Image:
        layer = Image.new("RGBA", SIZE)
        board = self.theme.get("board", {})
        draw = ImageDraw.Draw(layer)
        draw.rounded_rectangle((770, 42, 1150, 142), radius=45,
                               fill=color(board.get("header_fill"), (255, 247, 226)),
                               outline=color(board.get("header_outline"), (160, 111, 60)), width=4)
        if self.ink_centered:
            self.header_text(layer)
        else:
            self.center_text(draw, (960, 89), f"1 → {self.timeline.count_end}",
                             self.art.font(int(board.get("header_font_size", 49))), self.digit_color)
        return layer

    def header_text(self, layer: Image.Image) -> None:
        board = self.theme.get("board", {})
        x, y, width, height = board.get("header_bbox_xywh", [770, 42, 380, 100])
        # A symmetric outline shrinks each side equally, so its inner-field
        # center is also the exact center of the allocated rounded rectangle.
        self.ink_center_text(layer, (x + width / 2, y + height / 2),
                             f"1 → {self.timeline.count_end}",
                             self.art.font(int(board.get("header_font_size", 49))), self.digit_color)

    @staticmethod
    def center_text(draw: ImageDraw.ImageDraw, center: tuple[float, float], text: str,
                    font: ImageFont.FreeTypeFont, fill: tuple[int, ...]) -> None:
        box = draw.textbbox((0, 0), text, font=font)
        draw.text((center[0] - (box[2] - box[0]) / 2 - box[0],
                   center[1] - (box[3] - box[1]) / 2 - box[1]), text, font=font, fill=fill)

    @staticmethod
    def ink_center_text(layer: Image.Image, center: tuple[float, float], text: str,
                        font: ImageFont.FreeTypeFont, fill: tuple[int, ...]) -> None:
        """Center painted glyphs rather than advances/side bearings.

        textbbox includes font bearings (notably different for 1, 10 and 300).
        Render with padding, retain every nonzero alpha pixel, then position the
        tight ink rectangle. Odd-sized ink is centered to the nearest half pixel.
        """
        box = font.getbbox(text)
        glyphs = Image.new("RGBA", (max(1, box[2] - box[0]) + 32,
                                     max(1, box[3] - box[1]) + 32))
        ImageDraw.Draw(glyphs).text((16 - box[0], 16 - box[1]), text, font=font, fill=fill)
        ink = glyphs.getchannel("A").getbbox()
        if ink is None:
            return
        glyphs = glyphs.crop(ink)
        paste(layer, glyphs, (center[0] - glyphs.width / 2, center[1] - glyphs.height / 2))

    @lru_cache(maxsize=18)
    def digits(self, number: int) -> Image.Image:
        text = str(number)
        size = int(self.theme.get("digit_font_size", 390))
        while self.art.font(size).getlength(text) > float(self.theme.get("digit_max_width", 740)):
            size -= 2
        layer = Image.new("RGBA", (820, 460))
        if self.ink_centered:
            board = self.theme.get("board", {})
            x, y, width, height = board.get("inner_bbox_xywh", board.get("bbox_xywh", [720, 240, 880, 540]))
            # The existing digits layer is pasted at (750,278). Its local ink
            # center is derived from the registered board field, not a digit's
            # advance width or a new per-number layout position.
            self.ink_center_text(layer, (x + width / 2 - 750, y + height / 2 - 278),
                                 text, self.art.font(size), self.digit_color)
        else:
            self.center_text(ImageDraw.Draw(layer), (410, 230), text, self.art.font(size), self.digit_color)
        return layer

    @lru_cache(maxsize=8)
    def progress(self, blooms: int, pop_index: int = -1, pop_percent: int = 100,
                 bud_angle: int = 0) -> Image.Image:
        layer = Image.new("RGBA", SIZE)
        draw = ImageDraw.Draw(layer)
        progress = self.theme.get("progress", {})
        baseline = float(progress.get("baseline_y", 990))
        vine = color(progress.get("vine_color"), (103, 135, 63, 220))
        points = [(round(x), round(baseline - 4 + 5 * math.sin((x - 290) / 90))) for x in range(290, 1601, 6)]
        draw.line(points, fill=vine, width=int(progress.get("vine_width", 5)))
        if progress.get("leaf_pairs", False):
            for center in (315, 715, 1135, 1570):
                y = baseline - 4 + 5 * math.sin((center - 290) / 90)
                draw.line((center - 9, y - 9, center, y, center + 13, y - 7), fill=vine, width=3)
                draw.ellipse((center - 28, y - 24, center - 4, y - 9), fill=vine)
                draw.ellipse((center + 5, y - 18, center + 29, y - 3), fill=vine)
        for index, (count, x) in enumerate(zip(self.milestones, self.positions, strict=True)):
            is_open = index < blooms
            height = int(progress.get("flower_height", 132) if is_open else progress.get("bud_height", 112))
            sprite = self.art.region("flower" if is_open else "bud", int(progress.get("sprite_max_width", 120)), height)
            if index == pop_index and pop_percent != 100:
                sprite = resized(sprite, (round(sprite.width * pop_percent / 100), round(sprite.height * pop_percent / 100)))
            if index == len(self.positions) - 1 and not is_open and bud_angle:
                sprite = sprite.rotate(bud_angle, Image.Resampling.BICUBIC, expand=True)
            paste(layer, sprite, (x - sprite.width / 2, baseline - sprite.height))
            if self.ink_centered and self.theme.get("alignment", {}).get("progress_labels", True):
                self.ink_center_text(layer, (x, baseline + 32), str(count),
                                     self.art.font(int(progress.get("label_font_size", 37))),
                                     color(progress.get("label_color"), BROWN))
            else:
                self.center_text(draw, (x, baseline + 32), str(count),
                                 self.art.font(int(progress.get("label_font_size", 37))),
                                 color(progress.get("label_color"), BROWN))
        return layer

    def props(self, frame: Image.Image, alpha: float = 1, seconds: float = 0) -> None:
        settings = self.theme.get("props", {})
        plant = self.art.region("pot_herbs", *settings.get("plant_size", [172, 175]))
        can = self.art.region("watering_can", *settings.get("can_size", [125, 120]))
        plant_xy = settings.get("plant_xy", [1660, 665])
        if self.bright and 150 in self.timeline.by_count:
            growth = smooth((seconds - float(self.timeline.by_count[150]["anchor_s"])) / 2)
            if growth > 0:
                sprout = self.art.region("sprout", 70, 60)
                bounds = sprout.getchannel("A").point(lambda value: 255 if value >= 16 else 0).getbbox()
                if bounds:
                    sprout = sprout.crop(bounds)
                target_height = round(20 + 15 * growth)
                sprout = resized(sprout, (round(sprout.width * target_height / sprout.height), target_height))
                paste(frame, sprout, (plant_xy[0] + plant.width / 2 - sprout.width / 2,
                                      plant_xy[1] + 45 - sprout.height), alpha * growth)
        paste(frame, plant, tuple(plant_xy), alpha)
        paste(frame, can, tuple(settings.get("can_xy", [1763, 805])), alpha)

    def effects(self, frame: Image.Image, group: dict[str, Any] | None, age: float) -> None:
        if group is None:
            return
        count = int(group["count"])
        spec = self.timeline.cue_specs.get(count, {})
        length = float((group.get("duration_s") if group.get("role") in ("pause", "finale") else None)
                       or spec.get("visual_duration_s") or group.get("duration_s") or 3.5)
        if self.bright:
            if self.bright_effects is not None and self.bright_effects.draw(frame, group, age, spec):
                return
            if count == 100 or group.get("role") == "finale":
                is_final = group.get("role") == "finale"
                rainbow = self.art.region("rainbow", 460 if is_final else 350, 235)
                strength = smooth((age - .1) / (.9 if is_final else .55))
                if not is_final:
                    strength *= 1 - smooth((age - 5.2) / 2.8)
                paste(frame, rainbow, (1190, 85), strength * .9)
                sparkle = Image.new("RGBA", SIZE)
                draw = ImageDraw.Draw(sparkle)
                for index in range(4):
                    x, y = 1180 + index * 120, 125 + 30 * math.sin(age * 1.4 + index)
                    radius = 4 + 2 * math.sin(age * 2 + index)
                    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(237, 198, 94, 255))
                paste(frame, sparkle, (0, 0), strength)
                return
        if group.get("role") == "finale" or count == 100:
            if age <= length - 0.5:
                rainbow = self.art.region("rainbow", 460 if group.get("role") == "finale" else 350, 235)
                paste(frame, rainbow, (1190, 85), blend_window(age, length, 0.65) * 0.9)
                draw = ImageDraw.Draw(frame)
                for index in range(4):
                    x = 1180 + index * 120
                    y = 125 + 30 * math.sin(age * 1.4 + index)
                    radius = 4 + 2 * math.sin(age * 2 + index)
                    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(237, 198, 94))
            return
        if count == 200:
            # Hat leaf is drawn separately above the bear, rather than hidden
            # behind its opaque hat/body with background effects.
            return
        if age > length:
            return
        alpha = blend_window(age, length, 0.3)
        u = clamp(age / length)
        sfx = spec.get("sfx_id")
        if sfx == "SE_BIRD":
            sprite = self.art.region(f"bird_flight_{int(age * 7) % 3 + 1}", 165, 165, mirror=True)
            x = -140 + u * 2180
            y = 115 + 23 * math.sin(u * math.tau)
            paste(frame, sprite, (x, y), alpha)
            if count == 160:
                paste(frame, sprite, (x - 220, y - 35), alpha)
        elif sfx == "SE_PLANE":
            reverse = count == 130
            sprite = self.art.region(f"airplane_{int(age * 4) % 2}", 225 if count != 230 else 170, 145, mirror=reverse)
            x = 2100 - 2400 * u if reverse else -250 + 2350 * u
            y = 80 + 40 * math.sin(u * math.pi)
            paste(frame, sprite, (x, y), alpha)
        elif sfx == "SE_RAINBOW":
            sprite = self.art.region("rainbow", 370, 205)
            paste(frame, sprite, (1190, 80), alpha * 0.85)
            if count == 240:
                smaller = self.art.region("rainbow", 290, 160)
                paste(frame, smaller, (1230, 120), alpha * 0.35)
        elif sfx == "SE_WIND":
            if count == 110:
                sprite = self.art.region("leaf", 62, 70)
                paste(frame, sprite, (1700 - u * 950, 110 + 80 * math.sin(u * math.pi)), alpha)
            else:
                sprite = self.art.region("rain_cloud", 240, 155)
                paste(frame, sprite, (1670 - u * 900, 75), alpha * 0.75)
                if count in (70, 170, 270):
                    paste(frame, sprite, (1040 + u * 440, 90), alpha * 0.5)
        elif sfx == "SE_BLOOM":
            draw = ImageDraw.Draw(frame)
            if age < 1.1:
                x = self.positions[min(len(self.positions) - 1, count // 50 - 1)]
                for index in range(5):
                    angle = index * math.tau / 5 - math.pi / 2
                    radius = 30 + age * 55
                    cx, cy = x + math.cos(angle) * radius, 916 + math.sin(angle) * radius
                    draw.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=(239, 199, 105))

    def foreground_leaf(self, frame: Image.Image, group: dict[str, Any] | None, age: float) -> None:
        if group is None or int(group["count"]) != 200 or not 0 <= age < 8.2:
            return
        factor = self.bear.height / 650
        leaf = self.art.region("leaf", round(72 * factor), round(75 * factor))
        if age < 0.45:
            u = smooth(age / 0.45)
            xy = (510 - 50 * u, 80 + 60 * u)
        elif age < 5.6:
            seated = smooth((age - 2.2) / 0.8)
            xy = (460, 140 + 44 * seated)
        else:
            u = smooth((age - 5.6) / 2.6)
            xy = (460 + 260 * u, 184 + 390 * u)
        xy = (self.bear.root[0] + (xy[0] - 435) * factor,
              self.bear.root[1] + (xy[1] - 840) * factor)
        paste(frame, leaf, xy, min(1, smooth((8.2 - age) / 0.5)))

    def frame(self, seconds: float) -> Image.Image:
        number, start = self.timeline.number_at(seconds)
        blooms = self.timeline.blooms_at(seconds)
        group, age = self.timeline.active_group(seconds)
        poses = self.bear.poses(seconds, group, age, self.bright)
        nod = (1.5 * math.sin(math.pi * clamp((seconds - start) / .4))
               if self.bright and group is None and number is not None and number % 5 == 0 and seconds - start < .4 else 0)
        static_key = ((number, blooms, tuple(poses))
                      if number is not None and group is None and seconds - start >= 0.18 and not nod else None)
        if static_key is not None and static_key == self._cached_key and self._cached_frame is not None:
            return self._cached_frame
        frame = self.background.copy()
        if seconds < 0.6:
            frame = Image.blend(Image.new("RGB", SIZE, CREAM), frame, smooth(seconds / 0.6))
        self.effects(frame, group, age)
        actor_alpha = smooth((seconds - 0.6) / 0.4)
        paste(frame, self.shadow_layer, (0, 0), actor_alpha)
        self.bear.draw(frame, poses, actor_alpha, nod)
        self.foreground_leaf(frame, group, age)
        board_alpha = smooth((seconds - 4.5) / 0.5)
        paste(frame, self.board_layer, (0, 0), board_alpha)
        if self.header_layer is not None:
            paste(frame, self.header_layer, (0, 0), actor_alpha)
        if number is not None:
            bounce = -5 * math.sin(math.pi * clamp((seconds - start) / 0.18)) if seconds - start < 0.18 else 0
            paste(frame, self.digits(number), (750, 278 + bounce))
        progress_alpha = smooth((seconds - 6.7) / 1.8)
        if self.bright:
            pop_index, pop_percent, bud_angle = -1, 100, 0
            for bloom_time, bloom_count in self.timeline.bloom_times:
                if 0 <= seconds - bloom_time < .35 and bloom_count:
                    u = (seconds - bloom_time) / .35
                    pop_index, pop_percent = bloom_count - 1, round(100 * (1 - .15 * (1 - u) ** 2 + .08 * math.sin(math.pi * u)))
            if group is not None and int(group["count"]) == 290:
                bud_angle = round(3 * math.sin(age * math.tau * 1.25) * blend_window(age, 3.5))
            progress_layer = self.progress(blooms, pop_index, pop_percent, bud_angle)
        else:
            progress_layer = self.progress(blooms)
        paste(frame, progress_layer, (0, 0), progress_alpha)
        self.props(frame, smooth(seconds / 0.6), seconds)
        if self.timeline.finale is not None:
            final_age = seconds - float(self.timeline.finale["anchor_s"])
            if final_age >= 18:
                frame = Image.blend(frame, Image.new("RGB", SIZE, CREAM), smooth((final_age - 18) / 2))
        self._cached_key = static_key
        self._cached_frame = frame if static_key is not None else None
        return frame


def find_ffmpeg(explicit: str | None) -> str:
    if explicit:
        path = local_path(explicit)
        if not path.is_file():
            raise ValueError(f"ffmpeg does not exist: {path}")
        return str(path)
    found = shutil.which("ffmpeg")
    if found:
        return found
    candidates = sorted(Path("D:/dev/FFmpeg").glob("*/bin/ffmpeg.exe"), reverse=True)
    if candidates:
        return str(candidates[0])
    raise ValueError("Install/use the registered shared ffmpeg, or pass --ffmpeg")


def covering_frame_count(duration_s: float) -> int:
    """Cover the entire requested interval without truncating its final audio samples."""
    if not math.isfinite(duration_s) or duration_s <= 0:
        raise ValueError("Frame duration must be finite and positive")
    return math.ceil(duration_s * FPS - 1e-9)


def encode(scene: Scene, segments: list[Segment], output: Path, ffmpeg: str,
           audio: Path | None, crf: int, preset: str) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    total_frames = sum(covering_frame_count(segment.duration_s) for segment in segments)
    duration = total_frames / FPS
    command = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-f", "rawvideo",
               "-pixel_format", "rgb24", "-video_size", "1920x1080", "-framerate", str(FPS), "-i", "pipe:0"]
    if audio is not None:
        if len(segments) != 1:
            raise ValueError("A montage sample is silent; audio muxing requires a single continuous segment")
        command += ["-ss", str(segments[0].start_s), "-i", str(audio)]
    command += ["-map", "0:v:0", "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                "-vf", "scale=in_range=full:out_range=limited:out_color_matrix=bt709,setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709",
                "-pix_fmt", "yuv420p", "-color_range", "tv", "-color_primaries", "bt709", "-color_trc", "bt709",
                "-colorspace", "bt709", "-movflags", "+faststart"]
    command += (["-map", "1:a:0", "-af", "volume=-0.5dB", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
                if audio is not None else ["-an"])
    command += ["-t", f"{duration:.9f}", str(output)]
    log_path = output.with_suffix(".ffmpeg.log")
    start_clock = time.perf_counter()
    frames_written = 0
    last_image: Image.Image | None = None
    last_bytes = b""
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
        assert process.stdin is not None
        try:
            for segment in segments:
                print(f"Rendering {segment.label}: source {segment.start_s:.2f}s, {segment.duration_s:.2f}s", flush=True)
                for frame_index in range(covering_frame_count(segment.duration_s)):
                    seconds = segment.start_s + frame_index / FPS
                    image = scene.frame(seconds)
                    if image is not last_image:
                        last_bytes = image.tobytes()
                        last_image = image
                    process.stdin.write(last_bytes)
                    frames_written += 1
                    if frames_written % 300 == 0:
                        print(f"{frames_written}/{total_frames} frames ({frames_written / max(.01, time.perf_counter() - start_clock):.1f} fps)", flush=True)
            process.stdin.close()
            return_code = process.wait()
        except BaseException:
            process.stdin.close()
            process.terminate()
            process.wait()
            raise
    if return_code:
        raise RuntimeError(f"ffmpeg exited {return_code}; see {log_path}")
    return {"output": str(output), "width": 1920, "height": 1080, "fps": FPS,
            "frames": total_frames, "duration_s": duration, "audio_muxed": audio is not None,
            "frame_rounding": "Ceil to cover every timeline/audio sample; excess is less than one video frame.",
            "audio_mux_gain_db": -0.5 if audio is not None else None,
            "rgb_to_yuv_matrix": "bt709", "yuv_range": "limited",
            "render_elapsed_s": round(time.perf_counter() - start_clock, 3), "ffmpeg_log": str(log_path)}


def contact_sheet(scene: Scene, segments: list[Segment], output: Path) -> None:
    samples: list[tuple[str, float]] = []
    for segment in segments:
        offset = segment.duration_s - 0.5 if "fade" in segment.label else min(segment.duration_s / 2, 1.8)
        samples.append((segment.label, segment.start_s + max(0, offset)))
    columns = 3
    tile_width, tile_height = 640, 360
    rows = math.ceil(len(samples) / columns)
    sheet = Image.new("RGB", (columns * tile_width, rows * (tile_height + 42)), CREAM)
    draw = ImageDraw.Draw(sheet)
    font = scene.art.font(22)
    for index, (label, seconds) in enumerate(samples):
        x, y = index % columns * tile_width, index // columns * (tile_height + 42)
        sheet.paste(resized(scene.frame(seconds), (tile_width, tile_height)), (x, y))
        draw.text((x + 12, y + tile_height + 6), f"{label} / source {seconds:.2f}s", fill=BROWN, font=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeline", help="Measured build_plan JSON; required unless --demo")
    parser.add_argument("--episode", default="episodes/counting-garden-001.json")
    parser.add_argument("--asset-manifest", default="catalogs/render-assets-v1.json")
    parser.add_argument("--theme", default=DEFAULT_THEME, help="Versioned theme JSON; defaults to the current blue-sky composition")
    parser.add_argument("--background", help="Override the current theme background")
    parser.add_argument("--audio", help="Parent-produced master.wav, optionally muxed into the continuous render")
    parser.add_argument("--output", required=True, help="Explicit new output path; existing deliverables are never replaced")
    parser.add_argument("--ffmpeg")
    parser.add_argument("--demo", action="store_true", help="Synthetic, silent timeline for visual/motion QA only")
    parser.add_argument("--sample-reel", action="store_true", help="Silent short montage of intro, effects, break and finale")
    parser.add_argument("--cue-montage", action="store_true", help="Silent excerpts of all thirty original cues")
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--contact-sheet", help="Save a contact sheet of the source sample positions")
    parser.add_argument("--still", action="append", default=[], metavar="SECONDS:PATH", help="Save a composed source-time frame")
    parser.add_argument("--no-video", action="store_true", help="Only write explicitly requested still/contact-sheet QA artifacts")
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--preset", default="veryfast")
    args = parser.parse_args()
    if not args.demo and not args.timeline:
        parser.error("Supply a measured --timeline, or explicitly request --demo for a synthetic silent preview")
    if args.demo and args.audio:
        parser.error("Synthetic --demo must not be muxed with production audio")
    episode = read_json(local_path(args.episode))
    cue_sheet = read_json(local_path(episode["cue_sheet"]))
    plan = demo_plan(cue_sheet, int(episode["count_end"])) if args.demo else read_json(local_path(args.timeline))
    timeline = Timeline(plan, cue_sheet)
    theme = read_json(local_path(args.theme)) if args.theme else {}
    if theme and theme.get("schema_version") != 1:
        parser.error("Theme schema_version must be 1")
    background = local_path(args.background or theme.get("background") or DEFAULT_BACKGROUND)
    scene = Scene(timeline, Artwork(read_json(local_path(args.asset_manifest)), theme.get("sprite_overrides")),
                  background, theme)
    if args.sample_reel and args.cue_montage:
        parser.error("Choose --sample-reel or --cue-montage")
    if args.cue_montage:
        segments = timeline.cue_segments()
    elif args.sample_reel:
        segments = timeline.sample_segments()
    else:
        duration = args.duration if args.duration is not None else timeline.duration - args.start
        if args.start < 0 or duration <= 0 or args.start + duration > timeline.duration + 0.001:
            parser.error("Requested segment is outside the timeline")
        segments = [Segment(args.start, duration, "continuous")]
    for value in args.still:
        seconds, path_text = value.split(":", 1)
        path = output_path(path_text)
        path.parent.mkdir(parents=True, exist_ok=True)
        scene.frame(float(seconds)).save(path)
    if args.contact_sheet:
        contact_sheet(scene, segments, output_path(args.contact_sheet))
    if not args.no_video:
        audio = local_path(args.audio) if args.audio else None
        if audio is not None and not audio.is_file():
            parser.error(f"Audio does not exist: {audio}")
        output = output_path(args.output)
        report = encode(scene, segments, output, find_ffmpeg(args.ffmpeg), audio, args.crf, args.preset)
        report.update({"schema_version": 1, "synthetic_demo_only": args.demo,
                       "sample_reel": args.sample_reel or args.cue_montage,
                       "timeline": args.timeline, "background": str(background),
                       "source_pngs_modified": False,
                       "segments": [segment.__dict__ for segment in segments],
                       "motion_limitations": [
                           "wave uses one common baseline-visible-height scale; actual motion is reviewed from this render",
                           "clap uses finished contact and neutral poses, not a full hand-open anatomy sequence",
                           "sit/stretch/stand uses the new half-seated/neutral/stretch sheet with one head-width scale and measured support anchors; pose cuts avoid double faces",
                           "seated leaf-follow and gaze-only board differences are unavailable; body remains front-facing",
                       ]})
        if args.theme:
            report.update({"theme_path": args.theme, "theme_id": theme.get("theme_id")})
        if scene.bright:
            report["original_baseline"] = "design/counting-video-v1/blue-sky-baseline-1848-v001.txt"
            report["motion_limitations"] = [
                "The thirty original cue groups use their individual specified variations; no extra speech or sound is generated.",
                "Brief existing think poses express looking up or glancing; this is completed-pose expression rather than a new eye rig.",
                "Small claps alternate existing cheer and success_ready chest poses; no new hand-open/closed rig is claimed.",
                "Gentle nods are at most 1.5 output pixels; registered source proportions and PNGs remain unchanged.",
                "Sit/stretch/stand uses the measured new posture sheet and discrete key poses without double-face crossfades.",
            ]
        report_path = output.with_suffix(".render.json")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"Render error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
