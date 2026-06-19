from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carsharing_sim.config import OUTPUTS_DIR
from run_from_contract import run_contract_simulation

DEFAULT_SCENARIOS = [
    ("baseline", "contract_run"),
    ("high_demand", "contract_high_demand"),
    ("fleet_shortage_clean", "contract_fleet_shortage_clean"),
    ("system_stress", "contract_system_stress"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run key contract-based scenarios and save comparison CSV.")
    parser.add_argument("--zones", required=True, help="Path to zones contract CSV")
    parser.add_argument("--od-demand", required=True, help="Path to OD demand contract CSV")
    parser.add_argument("--comparison-output", default="contract_scenario_comparison.csv")
    args = parser.parse_args()

    rows: list[dict] = []
    for scenario_name, prefix in DEFAULT_SCENARIOS:
        print(f"\n=== Running {scenario_name} ===")
        summary = run_contract_simulation(
            zones_path=args.zones,
            od_demand_path=args.od_demand,
            scenario_name=scenario_name,
            output_prefix=prefix,
        )
        rows.append(summary)
        for key, value in summary.items():
            print(f"{key}: {value}")

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUTS_DIR / args.comparison_output
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved comparison: {out_path}")
    print("Scenarios included: baseline, high_demand, fleet_shortage_clean, system_stress")


if __name__ == "__main__":
    main()
