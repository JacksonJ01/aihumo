"""Draw deterministic 12-joint AIHuMo overlays on card artwork."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw


CONNECTIONS = (
    ("left_shoulder", "right_shoulder"),
    ("left_hip", "right_hip"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
    ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"),
)

JOINTS = {
    joint
    for connection in CONNECTIONS
    for joint in connection
}


def _center_crop_16_9(image: Image.Image) -> Image.Image:
    target_ratio = 16 / 9
    ratio = image.width / image.height
    if ratio > target_ratio:
        width = round(image.height * target_ratio)
        left = (image.width - width) // 2
        return image.crop((left, 0, left + width, image.height))
    height = round(image.width / target_ratio)
    top = (image.height - height) // 2
    return image.crop((0, top, image.width, top + height))


def render(input_path: Path, spec_path: Path, output_path: Path) -> None:
    image = Image.open(input_path).convert("RGB")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    line_color = tuple(spec.get("lineColor", (246, 239, 218)))
    node_color = tuple(spec.get("nodeColor", (224, 174, 83)))
    outline_color = tuple(spec.get("outlineColor", (117, 83, 42)))
    line_width = int(spec.get("lineWidth", 7))
    radius = int(spec.get("nodeRadius", 11))
    draw = ImageDraw.Draw(image)

    for person in spec["people"]:
        joints = {name: tuple(point) for name, point in person.items()}
        missing = JOINTS - joints.keys()
        extra = joints.keys() - JOINTS
        if missing or extra:
            raise ValueError(f"Invalid joint set. Missing={sorted(missing)}, extra={sorted(extra)}")
        if len(set(joints.values())) != len(JOINTS):
            raise ValueError("Every person must have 12 distinct landmark locations")
        for start, end in CONNECTIONS:
            draw.line((joints[start], joints[end]), fill=line_color, width=line_width)
        for point in joints.values():
            x, y = point
            draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill=node_color,
                outline=outline_color,
                width=max(2, line_width // 3),
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    _center_crop_16_9(image).resize((640, 360), resampling).save(output_path, quality=94)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("spec", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    render(args.input, args.spec, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
