"""Diagnostics for the final v12 SPb carsharing MVP outputs."""
from __future__ import annotations

from pathlib import Path
import shutil

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
DIAG_DIR = OUTPUTS / "final_diagnostics"
DIAG_DIR.mkdir(parents=True, exist_ok=True)

FULL_ZONES = ROOT / "data" / "raw" / "nir1" / "zones.geojson"
REFINED_ZONES = ROOT / "data" / "processed" / "refined_spb_zones.geojson"
FINAL_SCENARIOS = OUTPUTS / "final_scenario_comparison.csv"
FINAL_ZONES = OUTPUTS / "final_zone_metrics.csv"
FINAL_MAP = OUTPUTS / "final_maps" / "interactive_final_spb_soft_shortage_map.html"
FINAL_MAP_V2 = OUTPUTS / "final_maps_v2" / "interactive_final_spb_soft_shortage_map_v2.html"
FINAL_MAP_V2_DIAG = DIAG_DIR / "final_map_v2_diagnostics.csv"
FINAL_MAP_V3 = OUTPUTS / "final_maps_v3" / "interactive_final_spb_clean_map_v3.html"
FINAL_MAP_V3_DIAG = DIAG_DIR / "final_map_v3_diagnostics.csv"
FINAL_MAP_V4 = OUTPUTS / "final_maps_v4" / "interactive_final_spb_map_v4.html"
FINAL_MAP_V4_DIAG = DIAG_DIR / "final_map_v4_diagnostics.csv"
FULL_SANITY_DIR = OUTPUTS / "full_spb_sanity"
FINAL_SANITY_DIR = OUTPUTS / "final_sanity"


def _count_geojson(path: Path) -> int | None:
    if not path.exists():
        return None
    return int(len(gpd.read_file(path)))


def _add_aliases(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "lost_demand_no_vehicle" not in out.columns and "cancelled_no_vehicle" in out.columns:
        out["lost_demand_no_vehicle"] = out["cancelled_no_vehicle"]
    if "lost_demand_no_vehicle_rate" not in out.columns:
        if "shortage_rate" in out.columns:
            out["lost_demand_no_vehicle_rate"] = out["shortage_rate"]
        elif "no_vehicle_rate" in out.columns:
            out["lost_demand_no_vehicle_rate"] = out["no_vehicle_rate"]
    if "client_rejection_after_vehicle_found" not in out.columns and "cancelled_by_client" in out.columns:
        out["client_rejection_after_vehicle_found"] = out["cancelled_by_client"]
    return out


def main() -> None:
    rows: list[dict[str, object]] = []
    warnings: list[str] = []

    full_zone_count = _count_geojson(FULL_ZONES)
    refined_zone_count = _count_geojson(REFINED_ZONES)
    rows.append({"metric": "full_spb_source_zones", "value": full_zone_count if full_zone_count is not None else "missing"})
    rows.append({"metric": "main_final_map", "value": "outputs/final_maps_v4/interactive_final_spb_map_v4.html"})
    rows.append({"metric": "refined_subzones_available_diagnostic_only", "value": refined_zone_count if refined_zone_count is not None else "missing"})
    rows.append({"metric": "refined_grid_used_as_main_final_map", "value": 0})
    rows.append({"metric": "visual_split_grid_used_for_calculation", "value": 0})
    rows.append({"metric": "split_grid_used_as_main_final_map", "value": 0})
    rows.append({"metric": "vertical_split_grid_used", "value": 0})
    rows.append({"metric": "horizontal_visual_split_grid_available", "value": 1})
    rows.append({"metric": "horizontal_visual_split_grid_used_as_calculation", "value": 0})

    if FULL_SANITY_DIR.exists():
        FINAL_SANITY_DIR.mkdir(parents=True, exist_ok=True)
        for path in FULL_SANITY_DIR.glob("*.csv"):
            shutil.copy2(path, FINAL_SANITY_DIR / path.name)
        rows.append({"metric": "final_sanity_csv_files", "value": len(list(FINAL_SANITY_DIR.glob("*.csv")))})
    else:
        warnings.append(f"Missing full-SPb sanity directory: {FULL_SANITY_DIR}")

    if FINAL_SCENARIOS.exists():
        scenarios = _add_aliases(pd.read_csv(FINAL_SCENARIOS))
        for _, row in scenarios.iterrows():
            scenario = row.get("scenario", "unknown")
            rows.append({"metric": f"{scenario}.total_orders", "value": int(row.get("total_orders", 0))})
            rows.append({"metric": f"{scenario}.lost_demand_no_vehicle", "value": int(row.get("lost_demand_no_vehicle", 0))})
            rows.append({"metric": f"{scenario}.completed_orders", "value": int(row.get("completed_orders", 0))})
    else:
        warnings.append(f"Missing final scenario comparison: {FINAL_SCENARIOS}")

    top_path = DIAG_DIR / "top_10_problem_zones.csv"
    if FINAL_ZONES.exists():
        zone_metrics = _add_aliases(pd.read_csv(FINAL_ZONES))
        for scenario, df in zone_metrics.groupby("scenario"):
            active = int((pd.to_numeric(df["total_orders"], errors="coerce").fillna(0) > 0).sum())
            rows.append({"metric": f"{scenario}.active_zones", "value": active})

        top = zone_metrics.sort_values(
            ["lost_demand_no_vehicle", "lost_demand_no_vehicle_rate", "total_orders"],
            ascending=False,
        ).head(10)
        top.to_csv(top_path, index=False, encoding="utf-8-sig")
    else:
        warnings.append(f"Missing final zone metrics: {FINAL_ZONES}")

    if FINAL_MAP_V2_DIAG.exists():
        v2_diag = pd.read_csv(FINAL_MAP_V2_DIAG)
        for _, row in v2_diag.iterrows():
            rows.append({"metric": f"map_v2.{row['metric']}", "value": row["value"]})

    if FINAL_MAP_V3_DIAG.exists():
        v3_diag = pd.read_csv(FINAL_MAP_V3_DIAG)
        for _, row in v3_diag.iterrows():
            rows.append({"metric": f"map_v3.{row['metric']}", "value": row["value"]})

    if FINAL_MAP_V4_DIAG.exists():
        v4_diag = pd.read_csv(FINAL_MAP_V4_DIAG)
        for _, row in v4_diag.iterrows():
            prefix = f"map_v4.{row['scenario']}." if "scenario" in v4_diag.columns and pd.notna(row.get("scenario")) else "map_v4."
            rows.append({"metric": f"{prefix}{row['metric']}", "value": row["value"]})

    for path in [FINAL_SCENARIOS, FINAL_ZONES, FINAL_MAP, FINAL_MAP_V2, FINAL_MAP_V2_DIAG, FINAL_MAP_V3, FINAL_MAP_V3_DIAG, FINAL_MAP_V4, FINAL_MAP_V4_DIAG, FINAL_SANITY_DIR, top_path]:
        rows.append({"metric": f"output_exists.{path.relative_to(ROOT)}", "value": int(path.exists())})
        if not path.exists():
            warnings.append(f"Expected output was not created: {path}")

    rows.append({
        "metric": "final_map_method",
        "value": "stable full-SPb grid; refined v11 grid kept diagnostic-only because of visual water/centroid artifacts",
    })

    diag = pd.DataFrame(rows)
    csv_path = DIAG_DIR / "final_diagnostics.csv"
    txt_path = DIAG_DIR / "final_diagnostics.txt"
    diag.to_csv(csv_path, index=False, encoding="utf-8-sig")

    lines = ["Final v12 diagnostics", "", diag.to_string(index=False), ""]
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("Warnings: none")
    txt_path.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\nSaved diagnostics: {csv_path}")
    print(f"Saved top problem zones: {top_path}")
    if warnings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
