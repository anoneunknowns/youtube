"""Number-specific ordinary effects for the original bright-garden cue sheet.

This module only composites into an in-memory RGB video frame. It never reads,
rewrites or exports source artwork, and it schedules no audio. The caller draws
the bear, number board and progress after this background-effects pass.
"""

from __future__ import annotations

from functools import lru_cache
import math
from typing import Any

from PIL import Image, ImageDraw, ImageFilter


_BIRDS = {10, 60, 120, 160, 210, 260}
_WIND = {20, 70, 110, 170, 220, 270}
_RAINBOWS = {30, 80, 140, 180, 240, 290}
_PLANES = {40, 90, 130, 190, 230, 280}
_ORDINARY = _BIRDS | _WIND | _RAINBOWS | _PLANES


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _smooth(value: float) -> float:
    value = _clamp(value)
    return value * value * (3.0 - 2.0 * value)


def _fade(age: float, duration: float, edge: float = 0.3) -> float:
    return min(_smooth(age / edge), _smooth((duration - age) / edge))


def _paste(frame: Image.Image, sprite: Image.Image, xy: tuple[float, float], alpha: float = 1.0) -> None:
    alpha = _clamp(alpha)
    if alpha <= 0.0:
        return
    if alpha < 0.999:
        sprite = sprite.copy()
        sprite.putalpha(sprite.getchannel("A").point(lambda value: round(value * alpha)))
    frame.paste(sprite, (round(xy[0]), round(xy[1])), sprite)


class BrightGardenEffects:
    """Implement exactly the 24 ordinary visual cues, without foreground actors.

    ``art.region(name, width, height, mirror=False)`` supplies a registered RGBA
    sprite. ``draw`` returns True for a handled ordinary cue, including its end
    window; it returns False for milestones, pauses, finales and unknown cues.
    """

    def __init__(self, art: Any):
        self.art = art

    def draw(self, frame: Image.Image, group: dict[str, Any] | None,
             age: float, spec: dict[str, Any]) -> bool:
        if group is None or group.get("role", "ordinary") != "ordinary":
            return False
        count = int(group["count"])
        if count not in _ORDINARY:
            return False
        duration = float(spec.get("visual_duration_s") or group.get("duration_s") or 3.5)
        if duration <= 0.0 or age < 0.0 or age >= duration:
            return True
        u = _clamp(age / duration)
        alpha = _fade(age, duration)
        if count in _BIRDS:
            self._bird(frame, count, age, u, alpha)
        elif count in _WIND:
            self._wind(frame, count, age, duration, u, alpha)
        elif count in _RAINBOWS:
            self._rainbow(frame, count, age, duration, u, alpha)
        else:
            self._plane(frame, count, u, alpha)
        return True

    def _bird(self, frame: Image.Image, count: int, age: float,
              u: float, alpha: float) -> None:
        reverse = count == 260
        progress = u
        if count == 120:
            # Ease to one short hover, then continue in the original direction.
            if u < 0.38:
                progress = 0.43 * _smooth(u / 0.38)
            elif u < 0.57:
                progress = 0.43
            else:
                progress = 0.43 + 0.57 * _smooth((u - 0.57) / 0.43)
        x = 2050 - progress * 2240 if reverse else -180 + progress * 2240
        y = 14.0
        if count == 60:
            y += 18.0 * math.sin(u * math.tau * 1.5)
        elif count == 120:
            y += 5.0 * math.sin(age * 5.0)
        elif count == 160:
            y += 10.0 * math.sin(u * math.tau)
        elif count == 210:
            y = 52.0 - 64.0 * _smooth(u)
        else:
            y += 5.0 * math.sin(u * math.pi)
        sprite = self.art.region(f"bird_flight_{int(age * 7) % 3 + 1}",
                                 138, 138, mirror=not reverse)
        _paste(frame, sprite, (x, y), alpha)
        if count == 160:
            follower = self.art.region(f"bird_flight_{(int(age * 7) + 1) % 3 + 1}",
                                       138, 138, mirror=True)
            _paste(frame, follower, (x - 210, y - 16), alpha)

    @staticmethod
    @lru_cache(maxsize=1)
    def _tree_mask() -> Image.Image:
        mask = Image.new("L", (440, 580), 0)
        ImageDraw.Draw(mask).rectangle((0, 0, 365, 505), fill=255)
        return mask.filter(ImageFilter.GaussianBlur(24))

    def _tree_sway(self, frame: Image.Image, age: float, alpha: float) -> None:
        # Feather a tiny movement into the top-left tree area. The underlying
        # frame and the original PNG stay separate; the lawn/actor root is fixed.
        dx = 1.8 * math.sin(age * 2.4) * alpha
        patch = frame.crop((0, 0, 440, 580))
        moved = patch.transform(patch.size, Image.Transform.AFFINE,
                                (1, 0, -dx, 0, 1, 0),
                                resample=Image.Resampling.BICUBIC,
                                fillcolor=patch.getpixel((0, 0)))
        frame.paste(moved, (0, 0), self._tree_mask())

    @staticmethod
    def _soft_light(frame: Image.Image, strength: float) -> None:
        if strength <= 0.0:
            return
        overlay = Image.new("RGBA", frame.size)
        draw = ImageDraw.Draw(overlay)
        draw.polygon(((1270, 58), (1380, 58), (1750, 720), (1000, 720)),
                     fill=(255, 250, 222, round(22 * strength)))
        overlay = overlay.filter(ImageFilter.GaussianBlur(32))
        _paste(frame, overlay, (0, 0))

    def _wind(self, frame: Image.Image, count: int, age: float,
              duration: float, u: float, alpha: float) -> None:
        if count == 110:
            self._tree_sway(frame, age, alpha)
            leaf = self.art.region("leaf", 52, 58)
            _paste(frame, leaf, (1850 - 2050 * u, 65 + 30 * math.sin(u * math.pi)), alpha)
            return
        if count == 70:
            # Two genuinely different sizes overlap once, then separate.
            large = self.art.region("rain_cloud", 300, 180)
            small = self.art.region("rain_cloud", 170, 105)
            progress = _smooth(u)
            _paste(frame, large, (1750 - 1200 * progress, 47), alpha * 0.78)
            _paste(frame, small, (650 + 650 * progress, 82), alpha * 0.66)
            return
        if count == 170:
            self._soft_light(frame, math.sin(math.pi * u) ** 2)
            left = self.art.region("rain_cloud", 290, 175)
            right = self.art.region("rain_cloud", 245, 150)
            _paste(frame, left, (1010 - 150 * _smooth(u), 43), alpha * 0.76)
            _paste(frame, right, (1420 + 150 * _smooth(u), 65), alpha * 0.70)
            return
        if count == 220:
            cloud = self.art.region("rain_cloud", 360, 205)
            # This is a video transform for the explicitly long-cloud cue; it
            # neither rescales character anatomy nor rewrites the source sprite.
            long_cloud = cloud.resize((440, 118), Image.Resampling.LANCZOS)
            _paste(frame, long_cloud, (2040 - 2560 * u, 60), alpha * 0.75)
            return
        if count == 270:
            left = self.art.region("rain_cloud", 300, 175)
            right = self.art.region("rain_cloud", 270, 160)
            progress = _smooth(u)
            _paste(frame, left, (875 - 1275 * progress, 48), alpha * 0.77)
            _paste(frame, right, (995 + 1150 * progress, 61), alpha * 0.72)
            return
        cloud = self.art.region("rain_cloud", 255, 155)
        _paste(frame, cloud, (2050 - 2600 * u, 62), alpha * 0.76)

    def _rainbow(self, frame: Image.Image, count: int, age: float,
                 duration: float, u: float, alpha: float) -> None:
        if count == 80:
            rainbow = self.art.region("rainbow", 400, 200).resize(
                (400, 142), Image.Resampling.LANCZOS)
            width = round(rainbow.width * _smooth(u / 0.64))
            if width > 0:
                _paste(frame, rainbow.crop((0, 0, width, rainbow.height)),
                       (1190, 58), alpha * 0.76)
            return
        if count == 140:
            rainbow = self.art.region("rainbow", 285, 145)
            reveal = _smooth((u - 0.1) / 0.45)
            _paste(frame, rainbow, (1220, 66), alpha * reveal * 0.82)
            cloud = self.art.region("rain_cloud", 370, 210)
            _paste(frame, cloud, (1165 + 425 * _smooth(u), 30), alpha * 0.92)
            return
        if count == 180:
            rainbow = self.art.region("rainbow", 350, 178)
            visible_height = round(rainbow.height * _smooth(u / 0.64))
            if visible_height > 0:
                top = rainbow.height - visible_height
                _paste(frame, rainbow.crop((0, top, rainbow.width, rainbow.height)),
                       (1220, 45 + top), alpha * 0.80)
            return
        if count == 240:
            outer = self.art.region("rainbow", 420, 205)
            inner = self.art.region("rainbow", 315, 155)
            appear = _smooth(u / 0.15)
            outer_alpha = appear * (1 - _smooth((u - 0.53) / 0.25))
            inner_alpha = appear * (1 - _smooth((u - 0.76) / 0.24))
            _paste(frame, outer, (1150, 35), outer_alpha * 0.68)
            _paste(frame, inner, (1200, 85), inner_alpha * 0.68)
            return
        rainbow = self.art.region("rainbow", 260 if count == 290 else 300, 150)
        _paste(frame, rainbow, (1380 if count == 290 else 1260, 44), alpha * 0.78)

    @lru_cache(maxsize=128)
    def _plane_sprite(self, index: int, width: int, angle_half_degrees: int,
                      mirror: bool) -> Image.Image:
        sprite = self.art.region(f"airplane_{index}", width, round(width * 0.66), mirror=mirror)
        angle = angle_half_degrees / 2.0
        return (sprite.rotate(angle, Image.Resampling.BICUBIC, expand=True)
                if angle else sprite)

    def _plane(self, frame: Image.Image, count: int, u: float, alpha: float) -> None:
        reverse = count == 130
        width = 138 if count == 230 else 214
        x = 2080 - 2440 * u if reverse else -260 + 2380 * u
        y = 24.0
        angle = 0.0
        index = 0
        if count == 90:
            y += 45 * math.sin(u * math.pi)
            angle = -10 * math.cos(u * math.pi)
            index = 1 if 0.25 < u < 0.75 else 0
        elif count == 190:
            phase = _clamp((u - 0.20) / 0.58)
            angle = 14 * math.sin(phase * math.pi)
            index = int(angle > 6)
        elif count == 280:
            phase = _clamp((u - 0.52) / 0.36)
            angle = -12 * math.sin(phase * math.pi)
            index = int(angle < -5)
        elif count == 230:
            y = 14.0
        else:
            y += 5 * math.sin(u * math.pi)
        sprite = self._plane_sprite(index, width, round(angle * 2), reverse)
        # Center expanded rotation bounds on the same flight trajectory.
        _paste(frame, sprite, (x - (sprite.width - width) / 2,
                               y - max(0, sprite.height - width * 0.66) / 2), alpha)
