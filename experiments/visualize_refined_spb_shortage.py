"""Build zone shortage tables for refined square-ish SPb contract outputs."""
from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
OUT_DIR = OUTPUTS / "refined_spb_figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SCENARIO_FILES = {
    "baseline": "refined_spb_baseline_zone_metrics.csv",
    "high_demand": "refined_spb_high_demand_zone_metrics.csv",
    "fleet_shortage_clean": "refined_spb_fleet_shortage_clean_zone_metrics.csv",
    "system_stress": "refined_spb_system_stress_zone_metrics.csv",
    "simple_relocation": "refined_spb_simple_relocation_zone_metrics.csv",
    "relocation_stress": "refined_spb_relocation_stress_zone_metrics.csv",
}


def main() -> None:
    rows = []
    for scenario, filename in SCENARIO_FILES.items():
        path = OUTPUTS / filename
        if not path.exists():
            raise FileNotFoundError(path)
        df = pd.read_csv(path)
        df["scenario"] = scenario
        df = df.sort_values(
            ["cancelled_no_vehicle", "shortage_rate", "total_orders"],
            ascending=[False, False, False],
        )
        df["rank_in_scenario"] = range(1, len(df) + 1)
        df.to_csv(OUT_DIR / f"refined_spb_top_shortage_zones_{scenario}.csv", index=False, encoding="utf-8-sig")
        rows.append(df)

    combined = pd.concat(rows, ignore_index=True)
    combined.to_csv(OUT_DIR / "refined_spb_zone_shortage_comparison_all_scenarios.csv", index=False, encoding="utf-8-sig")

    diagnostics = []
    for scenario, df in combined.groupby("scenario"):
        diagnostics.append({
            "scenario": scenario,
            "zones_total": int(df["zone_id"].nunique()),
            "zones_with_orders": int((df["total_orders"] > 0).sum()),
            "zones_with_shortage": int((df["cancelled_no_vehicle"] > 0).sum()),
            "zones_with_full_shortage": int((df["shortage_rate"] >= 1.0).sum()),
            "total_orders_sum_by_zones": int(df["total_orders"].sum()),
            "cancelled_no_vehicle_sum_by_zones": int(df["cancelled_no_vehicle"].sum()),
            "max_cancelled_no_vehicle_in_zone": int(df["cancelled_no_vehicle"].max()),
        })
    diag = pd.DataFrame(diagnostics)
    diag.to_csv(OUT_DIR / "refined_spb_zone_coverage_summary.csv", index=False, encoding="utf-8-sig")

    print("Refined-SPb zone visualization tables saved:")
    print(OUT_DIR / "refined_spb_zone_shortage_comparison_all_scenarios.csv")
    print(OUT_DIR / "refined_spb_zone_coverage_summary.csv")
    print("\nCoverage summary:")
    print(diag.to_string(index=False))
    print("\nTop 5 by scenario:")
    preview = combined[combined["rank_in_scenario"] <= 5][[
        "scenario", "rank_in_scenario", "zone_id", "zone_name", "total_orders", "cancelled_no_vehicle", "shortage_rate", "completion_rate"
    ]]
    print(preview.to_string(index=False))


if __name__ == "__main__":
    main()
