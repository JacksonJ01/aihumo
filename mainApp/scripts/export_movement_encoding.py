"""CLI for exporting confirmed repetition encodings without changing sources."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aihumo.movement_encoding import EncodingConfig, export_movement_encodings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sample-points", type=int, choices=(32, 64), default=32)
    args = parser.parse_args(argv)
    result = export_movement_encodings(
        args.parquet, args.annotations, args.output,
        config=EncodingConfig(sample_points=args.sample_points),
    )
    print(result["manifest_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

