from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carsharing_sim.config import OUTPUTS_DIR
from carsharing_sim.validation import (
    save_validation_csv,
    save_validation_report,
    validate_expected_scenario_behavior,
)


def main() -> None:
    scenario_csv = OUTPUTS_DIR / "scenario_comparison.csv"
    if not scenario_csv.exists():
        raise FileNotFoundError("Run experiments/run_scenarios.py before validation.")

    checks = validate_expected_scenario_behavior(scenario_csv)
    report_path = save_validation_report(checks, OUTPUTS_DIR / "validation_report.txt")
    csv_path = save_validation_csv(checks, OUTPUTS_DIR / "validation_checks.csv")

    print(report_path.read_text(encoding="utf-8"))
    print(f"Saved: {report_path}")
    print(f"Saved: {csv_path}")


if __name__ == "__main__":
    main()
