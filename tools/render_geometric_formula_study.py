"""Silent 8-second general-term study. Does not modify static mocks or script.

This is a mathematical motion preview, with the follow_up character held still.
It is not the episode timeline and does not accept character animation quality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageChops, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from component_alignment import raster_centering_report
from render_geometric_mockups import (
    Canvas, Rabbit, D, ROOT, W, H, INK, TEAL, MUTED, bounds, font, letters, power,
)

OUT = D / "mockups/general-formula-motion-study.mp4"
QA = D / "qa/general-formula-study"
FFMPEG = ROOT / ".venv/bin/ffmpeg"
FFPROBE = ROOT / ".venv/bin/ffprobe"
FPS, FRAMES = 30, 240
FORMULA_BOX = (610, 285, 1710, 455)
PROGRESS_BOX = (650, 869, 1720, 916)
PAPER = (255, 250, 240)
SAMPLES = {0, 15, 30, 44, 45, 63, 72, 78, 82, 84, 89, 90, 103, 113, 114,
           123, 125, 126, 130, 138, 140, 141, 160, 171, 183, 198, 239}
DECODE_MEASURE = {0, 45, 63, 90, 141, 160, 183, 198, 239}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ease(value):
    value = min(1.0, max(0.0, value))
    return value * value * (3 - 2 * value)


def box_at(x, y, width, height):
    return (x - width / 2, y - height / 2, x + width / 2, y + height / 2)


def boxes_intersect(a, b):
    return max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3])


def compose(parts):
    """Typeset native glyphs while retaining insertion slots for moving values.

    Each part is (id, text, size, downward offset, color, draw it). A hidden
    part still reserves its slot, so substitution does not move other glyphs.
    """
    out = Image.new("RGBA", (2400, 300))
    x = 30
    slots = {}
    for ident, text, size, offset, color, visible in parts:
        layer = letters(text, size, color)
        b = bounds(layer)
        y = round(110 - size * .7 + offset)
        slots[ident] = (x, y, x + b[2] - b[0], y + b[3] - b[1])
        if visible:
            out.alpha_composite(layer, (x - b[0], y - b[1]))
        else:
            # A visible empty slot prevents a travelling n from leaving a false
            # exponent -1, or a missing operand from looking like "2 × = ?".
            ImageDraw.Draw(out).rounded_rectangle(
                (x, y + 2, x + b[2] - b[0], y + b[3] - b[1] - 2),
                radius=4, outline=TEAL, width=2)
        x += b[2] - b[0] + 6
    b = bounds(out)
    crop = (b[0] - 20, b[1] - 20, b[2] + 20, b[3] + 20)
    slots = {key: tuple(value[i] - crop[i % 2] for i in range(4)) for key, value in slots.items()}
    return out.crop(crop), slots


def working_formula(exponent="n", plain=False, blank=False, result="?"):
    parts = [("a", "a", 88, 0, INK, True), ("index", "4", 47, 33, TEAL, True)]
    if plain:
        parts.extend([("prefix", " = 2 × ", 88, 0, INK, True),
                      ("operand", "27", 88, 0, TEAL, not blank)])
    else:
        parts.append(("prefix", " = 2 × 3", 88, 0, INK, True))
        if exponent in {"n", "4"}:
            parts.extend([("substitute", exponent, 47, -28, TEAL, not blank),
                          ("minus-one", "−1", 47, -28, TEAL, True)])
        else:
            parts.append(("substitute", "3", 47, -28, TEAL, not blank))
    parts.append(("result", " = " + result, 88, 0, INK, True))
    return compose(parts)


def put_expression(c, layer, slots, box, ident):
    c.put(layer, box, ident)
    ox, oy = c.records[-1]["measurement_origin_px"]
    return {key: ((value[0] + value[2]) / 2 + ox, (value[1] + value[3]) / 2 + oy)
            for key, value in slots.items()}


def stage_at(t):
    if t < .5:
        return "choose-term-number"
    if t < 1.5:
        return "substitute-four-into-n-minus-one"
    if t < 2.1:
        return "hold-four-minus-one"
    if t < 3.0:
        return "evaluate-exponent-four-minus-one-equals-three"
    if t < 4.15:
        return "expand-three-cubed-into-three-factors"
    if t < 4.65:
        return "multiply-three-factors"
    if t < 5.35:
        return "intermediate-twenty-seven-calculation-only"
    if t < 6.1:
        return "substitute-twenty-seven-into-final-product"
    if t < 6.6:
        return "evaluate-two-times-twenty-seven"
    return "fifty-four-replay-of-term-four"


def render_frame(frame, rabbit):
    t = frame / FPS
    stage = stage_at(t)
    c = Canvas(f"general-formula-frame-{frame:03d}")
    c.header("GENERAL TERM AT WORK", "SILENT FORMULA STUDY  •  timing is for preview only")
    c.panel((540, 250, 1770, 470), fill="#fffaf0")
    c.panel((540, 510, 1770, 750), fill="#fffaf0")
    c.panel((145, 450, 475, 665), fill="#fffaf0")
    c.text("TERM NUMBER", (175, 462, 445, 505), 25, MUTED, "input-label")

    if t < 1.5:
        layer, slots = working_formula("n", blank=t >= .5)
    elif t < 2.6:
        layer, slots = working_formula("4")
    elif t < 3.0:
        layer, slots = working_formula("3", blank=True)
    elif t < 5.35:
        layer, slots = working_formula("3")
    else:
        layer, slots = working_formula(plain=True, blank=t < 6.1, result="54" if t >= 6.6 else "?")
    formula_slots = put_expression(c, layer, slots, FORMULA_BOX, "working-formula")
    formula_origin = c.records[-1]["measurement_origin_px"]
    formula_boxes = {key: tuple(value[i] + formula_origin[i % 2] for i in range(4)) for key, value in slots.items()}
    moving_numeral_question_checks = []
    subtraction_answer_mode = None

    if t < .5:
        c.text("4", (205, 516, 415, 641), 96, TEAL, "input-four")
        c.text("Choose the fourth term.", (610, 566, 1710, 670), 48, INK, "calculation")
    elif t < 1.5:
        raw_progress = (t - .5) / 1.0
        progress = ease(raw_progress)
        target = formula_slots["substitute"]
        # Rise above the baseline expression first, then enter the slot
        # vertically. A straight diagonal would cross the fixed 2 × 3.
        if raw_progress < .7:
            travel = ease(raw_progress / .7)
            x = 310 + (target[0] - 310) * travel
            y = 220 + (578.5 - 220) * (1 - travel) ** 3
        else:
            x = target[0]
            y = 220 + (target[1] - 220) * ease((raw_progress - .7) / .3)
        size = round(96 + (47 - 96) * progress)
        c.text("4", box_at(x, y, 150, 130), size, TEAL, "moving-four")
        moving_numeral_question_checks.append({"component_id": "moving-four", "moving_visible_box": c.records[-1]["visible_box_xyxy"],
                                               "fixed_question_block_box": list(formula_boxes["result"]),
                                               "passed": not boxes_intersect(c.records[-1]["visible_box_xyxy"], formula_boxes["result"])})
        c.text("Put 4 into n − 1.", (610, 566, 1710, 670), 48, INK, "calculation")
    elif t < 3.0:
        # A calculation result is carried, rather than copied over a question
        # mark or a still-visible source 3. Empty slots stay explicit.
        subtraction_answer_mode = "settled-3" if 2.4 <= t < 2.6 else "empty-slot"
        calculation, calc_slots = compose([
            ("subtraction", "4 − 1 = ", 82, 0, INK, True),
            ("answer-three", "3", 82, 0, TEAL, subtraction_answer_mode == "settled-3")])
        calc_positions = put_expression(c, calculation, calc_slots, (610, 553, 1710, 699), "calculation")
        c.records[-1]["text"] = "4 − 1 = 3" if subtraction_answer_mode == "settled-3" else "4 − 1 = [empty slot]"
        if t >= 2.6:
            progress = ease((t - 2.6) / .4)
            target = formula_slots["substitute"]
            source = calc_positions["answer-three"]
            x = source[0] + (target[0] - source[0]) * progress
            y = source[1] + (target[1] - source[1]) * progress
            c.text("3", box_at(x, y, 130, 110), round(82 + (47 - 82) * progress), TEAL, "moving-three")
            moving_numeral_question_checks.append({"component_id": "moving-three", "moving_visible_box": c.records[-1]["visible_box_xyxy"],
                                                   "fixed_question_block_box": list(formula_boxes["result"]),
                                                   "passed": not boxes_intersect(c.records[-1]["visible_box_xyxy"], formula_boxes["result"])})
    elif t < 4.65:
        if t < 4.15:
            spread = ease((t - 3.0) / .8)
            xs = [1110 + (target - 1110) * spread for target in (800, 1110, 1420)]
        else:
            converge = ease((t - 4.15) / .5)
            xs = [target + (1110 - target) * converge for target in (800, 1110, 1420)]
        for index, x in enumerate(xs):
            c.text("3", box_at(x, 625, 150, 150), 100, TEAL, f"factor-three-{index + 1}")
        if 3.8 <= t < 4.15:
            c.text("×", (900, 565, 1010, 685), 68, INK, "multiply-one")
            c.text("×", (1210, 565, 1320, 685), 68, INK, "multiply-two")
    elif t < 5.35:
        c.text("27", (710, 540, 1510, 705), 120, TEAL, "intermediate-27")
    elif t < 6.1:
        progress = ease((t - 5.35) / .75)
        target = formula_slots["operand"]
        x = 1110 + (target[0] - 1110) * ease(progress * 3)
        y = 622.5 + (target[1] - 622.5) * ease((progress - 1 / 3) * 1.5)
        c.text("27", box_at(x, y, 230, 165), round(120 + (88 - 120) * progress), TEAL, "moving-27")
        moving_numeral_question_checks.append({"component_id": "moving-27", "moving_visible_box": c.records[-1]["visible_box_xyxy"],
                                               "fixed_question_block_box": list(formula_boxes["result"]),
                                               "passed": not boxes_intersect(c.records[-1]["visible_box_xyxy"], formula_boxes["result"])})
    elif t < 6.6:
        c.text("2 × 27 = ?", (610, 550, 1710, 705), 84, INK, "calculation")
    else:
        c.text("54", (710, 535, 1510, 705), 132, TEAL, "replayed-54")

    power_relation = None
    if 3.0 <= t < 5.35:
        c.put(power(3, 3, size=64), (565, 550, 695, 690), "power-equivalence")
        if 3.8 <= t < 4.15:
            power_relation = "equals-three-separated-factors-with-times-signs"
            c.text("=", (700, 575, 755, 675), 50, INK, "power-equals")
        elif 4.65 <= t < 5.35:
            power_relation = "equals-settled-27"
            c.text("=", (700, 575, 755, 675), 50, INK, "power-equals")
        else:
            power_relation = "process-arrow-no-equality-asserted"
            c.text("→", (700, 575, 755, 675), 50, INK, "power-process-arrow")

    if t >= 1.5:
        c.text("INPUT USED", (175, 550, 445, 611), 30, MUTED, "input-used")
    caption = {
        "choose-term-number": "n is the term number.",
        "substitute-four-into-n-minus-one": "The input chooses the exponent.",
        "hold-four-minus-one": "Four minus one still needs to be evaluated.",
        "evaluate-exponent-four-minus-one-equals-three": "The exponent becomes 3.",
        "expand-three-cubed-into-three-factors": "Three factors of three.",
        "multiply-three-factors": "Collect the factors.",
        "intermediate-twenty-seven-calculation-only": "27  •  CALCULATION ONLY",
        "substitute-twenty-seven-into-final-product": "27  •  CALCULATION ONLY",
        "evaluate-two-times-twenty-seven": "Multiply the starting value last.",
        "fifty-four-replay-of-term-four": "54  •  REPLAY OF TERM 4",
    }[stage]
    c.text(caption, (590, 778, 1750, 835), 31, TEAL, "stage-caption")
    c.text("MAIN COUNT HELD AT TERM 4", PROGRESS_BOX, 29, MUTED, "main-progress")
    c.text("No new term is counted in this replay.", (590, 930, 1750, 975), 27, MUTED, "progress-rule")
    rabbit.draw(c, "follow_up", 300, (335, 1040))
    component_ids = [record["component_id"] for record in c.records]
    times_sign_count = sum(ident in {"multiply-one", "multiply-two"} for ident in component_ids)
    factor_count = sum(ident.startswith("factor-three-") for ident in component_ids)
    assert all(row["passed"] for row in moving_numeral_question_checks), moving_numeral_question_checks
    if power_relation == "equals-three-separated-factors-with-times-signs":
        assert factor_count == 3 and times_sign_count == 2 and "power-equals" in component_ids
    elif power_relation == "equals-settled-27":
        assert "intermediate-27" in component_ids and "power-equals" in component_ids
    elif power_relation == "process-arrow-no-equality-asserted":
        assert "power-process-arrow" in component_ids and "power-equals" not in component_ids
    if "moving-three" in component_ids:
        assert subtraction_answer_mode == "empty-slot"
    c.notes = {"frame": frame, "time_s": t, "stage": stage, "main_index": 4,
               "progress_delta": 0, "character_pose": "follow_up", "character_pose_held": True,
               "power_relation": power_relation, "factor_marker_count": factor_count,
               "times_sign_count": times_sign_count, "subtraction_answer_mode": subtraction_answer_mode,
               "question_mark_in_subtraction_answer": False,
               "moving_numeral_question_block_nonintersection": moving_numeral_question_checks,
               "intermediate_meaning_check_passed": True}
    for record in c.records:
        record.update(frame=frame, time_s=t, math_stage=stage)
    return c


def read_exact(stream, amount):
    data = bytearray()
    while len(data) < amount:
        block = stream.read(amount - len(data))
        if not block:
            break
        data.extend(block)
    return bytes(data)


def decoded_foreground_report(image, source_record, frame):
    """Independent foreground threshold from encoded RGB on a plain panel."""
    box = tuple(round(v) for v in source_record["content_box_xyxy"])
    red, green, blue = image.crop(box).split()
    # Includes both INK and TEAL glyphs; the cream panel and its border are absent.
    layer = ImageChops.multiply(red.point(lambda x: 255 if x < 174 else 0),
                               green.point(lambda x: 255 if x < 205 else 0))
    layer = ImageChops.multiply(layer, blue.point(lambda x: 255 if x < 200 else 0))
    record = raster_centering_report(layer, box, origin_xy=(box[0], box[1]),
                                      name=f"decoded/{frame:03d}/{source_record['component_id']}", tolerance_px=1.0)
    record.update(frame=frame, time_s=frame / FPS, horizontal="center", vertical="center",
                  extraction="Decoded RGB: R<174 and G<205 and B<200 inside plain #fffaf0 content ROI; frame border excluded",
                  source_component_id=source_record["component_id"])
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace-owned", action="store_true", help="Replace only this study's MP4 and dedicated QA files")
    args = parser.parse_args()
    if OUT.exists() and not args.replace_owned:
        raise FileExistsError(OUT)
    QA.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Other agents own static mock outputs and may revise them in parallel.
    # This study never opens them for writing and does not bind to their SHA.
    guarded = [D / "math/sequence.json", D / "math/speech-script.json", D / "math/speech-script.csv"]
    unchanged_before = {str(p.relative_to(ROOT)): sha(p) for p in guarded}
    rabbit = Rabbit()
    records, states, sampled_records, source_images = [], [], {}, {}
    character_patch_sha = None
    command = [str(FFMPEG), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080", "-r", str(FPS), "-i", "-",
               "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-color_primaries", "bt709",
               "-color_trc", "bt709", "-colorspace", "bt709", "-movflags", "+faststart", str(OUT)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for frame in range(FRAMES):
            c = render_frame(frame, rabbit)
            character_record = next(r for r in c.records if r["component_id"] == "rabbit")
            patch = c.image.crop(tuple(character_record["visible_box_xyxy"]))
            patch_sha = hashlib.sha256(patch.tobytes()).hexdigest()
            if character_patch_sha is None:
                character_patch_sha = patch_sha
            assert patch_sha == character_patch_sha, "Held character patch changed in source frames"
            records.extend(c.records)
            states.append(c.notes)
            if frame in SAMPLES:
                rgb = c.image.convert("RGB")
                rgb.save(QA / f"source-{frame:03d}.png")
                source_images[frame] = rgb
            if frame in DECODE_MEASURE:
                sampled_records[frame] = [r for r in c.records if r["component_id"] == "working-formula"]
            process.stdin.write(c.image.convert("RGB").tobytes())
        process.stdin.close()
        assert process.wait() == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    assert len(states) == FRAMES and all(r["passed"] for r in records)
    assert all(s["main_index"] == 4 and s["progress_delta"] == 0 and s["character_pose"] == "follow_up" for s in states)
    moving_checks = [check for state in states for check in state["moving_numeral_question_block_nonintersection"]]
    semantics = {
        "passed": all(s["intermediate_meaning_check_passed"] for s in states) and all(c["passed"] for c in moving_checks),
        "scope": "All 240 native layer states, actual component identities and moving glyph bounds; not OCR of every encoded glyph.",
        "frames_checked": FRAMES,
        "arithmetic": {"4-1=3": 4 - 1 == 3, "3*3*3=27": 3 * 3 * 3 == 27, "2*27=54": 2 * 27 == 54},
        "moving_factors_use_process_arrow_instead_of_equals": True,
        "expanded_power_equals_only_when_two_times_signs_and_three_separate_factors_are_present": True,
        "power_equals_returns_after_27_settles": True,
        "subtraction_result_uses_empty_slot_before_and_during_carry": True,
        "subtraction_result_has_no_question_mark": True,
        "moving_numeral_vs_fixed_question_block_checks": len(moving_checks),
        "all_moving_numeral_question_nonintersection_checks_pass": all(c["passed"] for c in moving_checks),
        "phase_frames": {mode: sum(s["power_relation"] == mode for s in states) for mode in [
            "process-arrow-no-equality-asserted", "equals-three-separated-factors-with-times-signs", "equals-settled-27"]},
        "main_index": 4, "progress_delta": 0,
        "details": "math-states.json records each frame, relation mode, actual factor/operation component counts and measured moving-numeral boxes."
    }
    assert semantics["passed"] and all(semantics["arithmetic"].values())
    metadata = json.loads(subprocess.check_output([str(FFPROBE), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(OUT)]))
    videos = [s for s in metadata["streams"] if s["codec_type"] == "video"]
    audios = [s for s in metadata["streams"] if s["codec_type"] == "audio"]
    assert len(videos) == 1 and not audios
    video = videos[0]
    assert (video["width"], video["height"], video["r_frame_rate"], video["pix_fmt"]) == (W, H, "30/1", "yuv420p")
    assert int(video["nb_frames"]) == FRAMES and abs(float(metadata["format"]["duration"]) - 8.0) < .001

    decode = subprocess.Popen([str(FFMPEG), "-v", "error", "-i", str(OUT), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    decoded_count = 0
    decoded_records = []
    while True:
        raw = read_exact(decode.stdout, W * H * 3)
        if not raw:
            break
        assert len(raw) == W * H * 3
        if decoded_count in SAMPLES:
            image = Image.frombytes("RGB", (W, H), raw)
            image.save(QA / f"decoded-{decoded_count:03d}.png")
        if decoded_count in DECODE_MEASURE:
            image = Image.frombytes("RGB", (W, H), raw)
            for source_record in sampled_records[decoded_count]:
                decoded_records.append(decoded_foreground_report(image, source_record, decoded_count))
        decoded_count += 1
    assert decode.wait() == 0 and decoded_count == FRAMES
    assert all(r["passed"] for r in decoded_records), [r for r in decoded_records if not r["passed"]]

    sheet = Image.new("RGB", (1920, 300 * ((len(SAMPLES) + 3) // 4)), "#f1e7d7")
    draw = ImageDraw.Draw(sheet)
    for index, frame in enumerate(sorted(SAMPLES)):
        thumb = Image.open(QA / f"decoded-{frame:03d}.png").resize((480, 270), Image.Resampling.LANCZOS)
        x, y = (index % 4) * 480, (index // 4) * 300
        sheet.paste(thumb, (x, y))
        draw.text((x + 12, y + 274), f"{frame / FPS:.2f}s / frame {frame}", font=font(18), fill=INK)
    sheet.save(QA / "decoded-contact-sheet.jpg", quality=94)
    assert {str(p.relative_to(ROOT)): sha(p) for p in guarded} == unchanged_before, "Read-only mathematical inputs changed during study render"
    (QA / "alignment-source-all-frames.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    (QA / "alignment-decoded-samples.json").write_text(json.dumps(decoded_records, ensure_ascii=False, indent=2) + "\n")
    (QA / "math-states.json").write_text(json.dumps(states, ensure_ascii=False, indent=2) + "\n")
    (QA / "intermediate-meaning-audit.json").write_text(json.dumps(semantics, ensure_ascii=False, indent=2) + "\n")
    (QA / "ffprobe.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    report = {"passed": True, "stage": "silent mathematical motion study; not final episode timing or acceptance",
              "output": str(OUT.relative_to(ROOT)), "sha256": sha(OUT),
              "seconds": 8.0, "fps": FPS, "frames": FRAMES, "resolution_px": [W, H], "audio_streams": 0,
              "full_decode_frames": decoded_count,
              "source_alignment_observations": len(records), "source_tolerance_px": .5,
              "source_max_abs_dx_px": max(abs(r["delta_x_px"]) for r in records),
              "source_max_abs_dy_px": max(abs(r["delta_y_px"]) for r in records),
              "decoded_alignment_observations": len(decoded_records), "decoded_tolerance_px": 1.0,
              "decoded_max_abs_dx_px": max(abs(r["delta_x_px"]) for r in decoded_records),
              "decoded_max_abs_dy_px": max(abs(r["delta_y_px"]) for r in decoded_records),
              "alignment_scope": "Every frame's native foreground layers; selected stable formula groups independently measured from encoded RGB. Other encoded frames fully decoded but not all remeasured.",
              "mathematical_stages": list(dict.fromkeys(s["stage"] for s in states)),
              "intermediate_meaning_audit": semantics,
              "transition_sample_frames": sorted(SAMPLES),
              "main_index": 4, "progress_delta": 0,
              "intermediate_27": "CALCULATION ONLY", "final_54": "REPLAY OF TERM 4",
              "character": {"pose": "follow_up", "held_static": True, "crossfade": False,
                            "all_240_source_patches_identical_sha256": character_patch_sha,
                            "not_character_motion_acceptance": True, "sources": rabbit.used},
              "guarded_inputs_unchanged": unchanged_before,
              "static_mock_outputs": "Owned by root; never opened for writing by this study; their changing SHA values are not dependencies.",
              "render_command": command,
              "limitations": "No narration; preview timings are unadopted. This verifies study math, format and measured placement, not the completed episode or sufficient character performance."}
    (QA / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ["passed", "output", "seconds", "frames", "full_decode_frames", "source_alignment_observations", "decoded_alignment_observations"]}))


if __name__ == "__main__":
    main()
