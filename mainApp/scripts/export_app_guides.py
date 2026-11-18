"""Export the Main Hub in-app guides as a reviewable Markdown document."""
from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for candidate in (PROJECT_ROOT, PROJECT_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.app_guides import guides_markdown
from app.main_hub import hub_apps


def main() -> int:
    output = PROJECT_ROOT / "docs" / "APP_GUIDES.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(guides_markdown(hub_apps()), encoding="utf-8")
    print(f"Saved {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
