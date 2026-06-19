from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STEPS = [
    [sys.executable, "experiments/prepare_full_spb_contract.py"],
    [sys.executable, "experiments/run_full_spb_scenarios.py"],
    [sys.executable, "experiments/visualize_full_spb_shortage.py"],
    [sys.executable, "experiments/make_full_spb_interactive_soft_map.py"],
    [sys.executable, "experiments/analyze_full_spb_sanity.py"],
    [sys.executable, "experiments/prepare_refined_spb_contract.py"],
    [sys.executable, "experiments/run_refined_spb_scenarios.py"],
    [sys.executable, "experiments/visualize_refined_spb_shortage.py"],
    [sys.executable, "experiments/make_refined_spb_interactive_soft_map.py"],
]


def main() -> None:
    for command in STEPS:
        print("\n===", " ".join(command), "===")
        subprocess.run(command, cwd=ROOT, check=True)
    print("\nFull v0.11 refined-SPb pipeline completed.")
    print("Key outputs:")
    print("- outputs/full_spb_maps/interactive_full_spb_soft_shortage_map.html")
    print("- outputs/refined_spb_scenario_comparison.csv")
    print("- outputs/refined_spb_maps/interactive_refined_spb_soft_shortage_map.html")
    print("- data/processed/refined_spb_zones.geojson")
    print("- data/processed/refined_spb_contract_diagnostics.csv")


if __name__ == "__main__":
    main()
