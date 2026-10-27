"""Normalize a GPT Image delivery: python tools/normalize_delivery.py --original ... --result ... --size 350x512."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from creative_workbench.normalization import main


if __name__ == "__main__":
    raise SystemExit(main())
