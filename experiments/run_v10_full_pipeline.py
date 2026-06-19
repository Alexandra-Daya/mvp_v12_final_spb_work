from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COMMANDS = [
    [sys.executable, "experiments/prepare_full_spb_contract.py"],
    [sys.executable, "experiments/run_full_spb_scenarios.py"],
    [sys.executable, "experiments/visualize_full_spb_shortage.py"],
    [sys.executable, "experiments/make_full_spb_interactive_soft_map.py"],
    [sys.executable, "experiments/analyze_full_spb_sanity.py"],
]


def main() -> None:
    for command in COMMANDS:
        print("\n===", " ".join(command), "===")
        subprocess.run(command, cwd=ROOT, check=True)

    print("\nFull v0.10 pipeline completed.")
    print("Key outputs:")
    print("- outputs/full_spb_scenario_comparison.csv")
    print("- outputs/full_spb_maps/interactive_full_spb_soft_shortage_map.html")
    print("- outputs/full_spb_sanity/full_spb_sanity_by_reference_area.csv")
    print("- outputs/full_spb_sanity/full_spb_top_problem_zones_with_reference_areas.csv")


if __name__ == "__main__":
    main()
