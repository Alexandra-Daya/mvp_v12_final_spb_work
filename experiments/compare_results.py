from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "outputs" / "scenario_comparison.csv"


def main() -> None:
    if not PATH.exists():
        raise FileNotFoundError("Run experiments/run_scenarios.py first.")
    with PATH.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
