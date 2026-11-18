"""Print the repeatable Main Hub artwork review report."""
from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for candidate in (PROJECT_ROOT, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.hub_artwork import ARTWORK_REVIEW_CRITERIA, review_artwork_set
from app.main_hub import HUB_CARD_DIR, HUB_PROFESSIONAL_CARD_DIR, hub_apps


def main() -> int:
    filenames = tuple(dict.fromkeys(app.art for app in hub_apps() if app.art))
    print("AIHuMo Hub Artwork Review")
    print("=" * 72)
    for label, directory, professional, focus in (
        ("Focus Mode", HUB_CARD_DIR, False, True),
        ("Professional", HUB_PROFESSIONAL_CARD_DIR, True, False),
    ):
        print(f"\n[{label}] {directory}")
        for result in review_artwork_set(directory, filenames, professional=professional, focus=focus):
            state = "PASS" if result.passed else "FAIL"
            issues = "; ".join(result.issues) if result.issues else "automated checks passed"
            print(f"{state:4}  {result.filename:22} sat={result.average_saturation:.3f}  "
                  f"contrast={result.luminance_span:6.1f}  {issues}")
    print("\nManual review")
    for index, criterion in enumerate(ARTWORK_REVIEW_CRITERIA, 1):
        print(f"  {index}. {criterion}")
    failed = any(
        not result.passed
        for directory, professional, focus in (
            (HUB_CARD_DIR, False, True), (HUB_PROFESSIONAL_CARD_DIR, True, False)
        )
        for result in review_artwork_set(directory, filenames, professional=professional, focus=focus)
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
