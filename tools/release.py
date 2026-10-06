#!/usr/bin/env python3
"""
release.py -- regenerate every feed so episodes whose release time has passed become visible.
Run hourly by .github/workflows/release.yml; safe to run by hand from the repo root:

    python tools/release.py

Prints one line per newly released episode. Exits 0 either way; the workflow commits only if files changed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import feedgen  # noqa: E402

SITE = Path(__file__).resolve().parents[1]


def main() -> int:
    newly = feedgen.regenerate(SITE)
    total = 0
    for slug, titles in newly.items():
        for t in titles:
            print(f"released [{slug}] {t}")
            total += 1
    if not total:
        print("nothing newly released")
    return 0


if __name__ == "__main__":
    sys.exit(main())
