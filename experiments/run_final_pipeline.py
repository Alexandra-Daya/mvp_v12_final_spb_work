from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STEPS = [
    [sys.executable, "experiments/prepare_full_spb_contract.py"],
    [sys.executable, "experiments/run_full_spb_scenarios.py", "--comparison-output", "final_scenario_comparison.csv"],
    [sys.executable, "experiments/visualize_full_spb_shortage.py"],
    [sys.executable, "experiments/analyze_full_spb_sanity.py"],
    [sys.executable, "experiments/make_final_interactive_map.py"],
    [sys.executable, "experiments/make_final_interactive_map_v2.py"],
    [sys.executable, "experiments/make_final_interactive_map_v3.py"],
    [sys.executable, "experiments/make_final_interactive_map_v4.py"],
    [sys.executable, "experiments/diagnose_final_outputs.py"],
]


def main() -> None:
    for command in STEPS:
        print("\n===", " ".join(command), "===")
        subprocess.run(command, cwd=ROOT, check=True)

    print("\nFinal v12.3 pipeline completed.")
    print("Key outputs:")
    print("- outputs/final_scenario_comparison.csv")
    print("- outputs/final_zone_metrics.csv")
    print("- outputs/final_maps/interactive_final_spb_soft_shortage_map.html")
    print("- outputs/final_maps_v2/interactive_final_spb_soft_shortage_map_v2.html")
    print("- outputs/final_maps_v3/interactive_final_spb_clean_map_v3.html")
    print("- outputs/final_maps_v4/interactive_final_spb_map_v4.html")
    print("- outputs/final_diagnostics/final_diagnostics.csv")
    print("- outputs/final_diagnostics/final_map_v2_diagnostics.csv")
    print("- outputs/final_diagnostics/final_map_v3_diagnostics.csv")
    print("- outputs/final_diagnostics/final_map_v4_diagnostics.csv")
    print("- outputs/full_spb_sanity/full_spb_top_problem_zones_with_reference_areas.csv")
    print("\nMAIN FINAL MAP:")
    print("outputs/final_maps_v4/interactive_final_spb_map_v4.html")


if __name__ == "__main__":
    main()
