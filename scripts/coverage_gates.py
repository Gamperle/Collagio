"""Enforce per-package coverage minimums from IMPLEMENTATION_PLAN.md.

Run after `pytest --cov` (reads the .coverage data file):
    uv run python scripts/coverage_gates.py
"""

from __future__ import annotations

import io
import sys

from coverage import Coverage
from coverage.exceptions import NoDataError

GATES: dict[str, float] = {
    "core": 95,
    "layout": 95,
    "styles": 90,
    "render": 90,
    "imaging": 85,
    "cli": 85,
    "app": 60,
}


def main() -> int:
    cov = Coverage()
    cov.load()
    failed = False
    for package, minimum in GATES.items():
        try:
            percent = cov.report(include=[f"*/collagio/{package}/*"], file=io.StringIO())
        except NoDataError:
            print(f"FAIL  {package:<8} no coverage data")
            failed = True
            continue
        ok = percent >= minimum
        failed |= not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {package:<8} {percent:6.2f} %  (gate {minimum:g} %)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
