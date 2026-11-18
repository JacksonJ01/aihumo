"""Repeatable quality checks for the two Main Hub artwork libraries."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtGui import QColor, QImage


CARD_SIZE = (640, 360)
PROFESSIONAL_MAX_AVERAGE_SATURATION = 0.58
FOCUS_MAX_AVERAGE_SATURATION = 0.60
MINIMUM_LUMINANCE_SPAN = 60.0

ARTWORK_REVIEW_CRITERIA = (
    "One dominant focal concept communicates the app before supporting detail.",
    "The subject remains recognizable in both a 16:9 card and a centered circular crop.",
    "Color, material, lighting, and depth match the selected artwork library.",
    "Text is avoided inside artwork; the interface supplies accessible names and descriptions.",
    "The image avoids unnecessary motion cues, clutter, stereotypes, and unsupported medical claims.",
    "Foreground and background retain sufficient luminance separation at thumbnail size.",
)


@dataclass(frozen=True)
class ArtworkReview:
    filename: str
    size: tuple[int, int]
    average_saturation: float
    luminance_span: float
    issues: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.issues


def review_artwork(path: Path, *, professional: bool = False, focus: bool = False) -> ArtworkReview:
    image = QImage(str(path))
    if image.isNull():
        return ArtworkReview(path.name, (0, 0), 0.0, 0.0, ("Image could not be loaded.",))
    size = (image.width(), image.height())
    saturations: list[float] = []
    luminances: list[float] = []
    step_x = max(1, image.width() // 64)
    step_y = max(1, image.height() // 36)
    for y in range(0, image.height(), step_y):
        for x in range(0, image.width(), step_x):
            color = QColor(image.pixel(x, y))
            saturations.append(color.hsvSaturationF())
            luminances.append(0.2126 * color.red() + 0.7152 * color.green() + 0.0722 * color.blue())
    average_saturation = sum(saturations) / max(1, len(saturations))
    luminance_span = max(luminances, default=0.0) - min(luminances, default=0.0)
    issues: list[str] = []
    if size != CARD_SIZE:
        issues.append(f"Expected {CARD_SIZE[0]}×{CARD_SIZE[1]}, found {size[0]}×{size[1]}.")
    if professional and average_saturation > PROFESSIONAL_MAX_AVERAGE_SATURATION:
        issues.append("Average saturation is too high for the Professional artwork system.")
    if focus and average_saturation > FOCUS_MAX_AVERAGE_SATURATION:
        issues.append("Average saturation is too high for Focus Mode.")
    if luminance_span < MINIMUM_LUMINANCE_SPAN:
        issues.append("The image lacks enough luminance separation at thumbnail size.")
    return ArtworkReview(
        path.name,
        size,
        round(average_saturation, 4),
        round(luminance_span, 2),
        tuple(issues),
    )


def review_artwork_set(directory: Path, filenames: tuple[str, ...], *, professional: bool = False,
                       focus: bool = False) -> tuple[ArtworkReview, ...]:
    return tuple(review_artwork(directory / filename, professional=professional, focus=focus) for filename in filenames)
