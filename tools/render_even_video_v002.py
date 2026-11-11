"""Render the even episode without crossfading incompatible teaching labels.

The v001 renderer is retained unchanged because its completed production is
hash-bound. All timing, geometry, number states and encoding remain inherited.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

import render_even_video as previous


class Scene(previous.Scene):
    """Fade only diagram content over a clean, consistently labelled field."""

    def diagram_image(self, target: Image.Image, alpha: int) -> Image.Image:
        base = target.copy()
        previous.rounded(ImageDraw.Draw(base), previous.TEACHING_FIELD,
                         '#f9f0dd', '#e1cfb2', 2, 21)
        return Image.blend(base, target, alpha / 255)

    def image(self, frame: previous.Frame) -> Image.Image:
        if frame.cream == 255:
            return previous.FADE_COLOR
        if frame.phase == 'intro' and frame.intro_mode == 'six':
            # Both images use PAIR CHECK. No EVEN NUMBER text is blended into it.
            image = self.diagram_image(self.still(6, 'pairs'), frame.diagram_alpha)
        elif frame.phase == 'count' and frame.teaching and frame.diagram_alpha:
            kind = 'twenty-pairs' if frame.teaching == 'T020' else 'final-digit-rule'
            # The target header and final-zero outline remain fixed. The normal
            # instruction is absent beneath the fading tokens or digit chips.
            image = self.diagram_image(self.still(frame.value, kind), frame.diagram_alpha)
        else:
            return super().image(frame)
        return (Image.blend(image, previous.FADE_COLOR, frame.cream / 255)
                if frame.cream else image)

    def audit(self) -> dict:
        result = super().audit()
        result.update(
            renderer=Path(__file__).relative_to(previous.ROOT).as_posix(),
            renderer_sha256=previous.file_hash(Path(__file__)),
            base_renderer=Path(previous.__file__).relative_to(previous.ROOT).as_posix(),
            base_renderer_sha256=previous.file_hash(Path(previous.__file__)),
            transition_revision='v002-clean-teaching-field',
            teaching_transition_policy={
                'different_header_labels_crossfaded': False,
                'normal_instruction_visible_beneath_diagram_fade': False,
                'large_number_reading_and_progression_changed': False,
                'intro_six_header': 'PAIR CHECK throughout diagram fade',
                'normal_instruction_restored': 'After the diagram reaches zero opacity',
            },
        )
        return result


def main() -> None:
    original = previous.Scene
    try:
        # Reuse the existing CLI and encoder with an episode-local Scene class.
        # No filesystem or standard-library function is patched.
        previous.Scene = Scene
        previous.main()
    finally:
        previous.Scene = original


if __name__ == '__main__':
    main()
