"""Spatial sanity checks for the full-SPb MVP run.

This script does not use official administrative district boundaries. Instead it
attaches each model zone centroid to the nearest coarse reference area
(Centre, Kolpino, Pushkin, Peterhof, Kronstadt, etc.). The output is intended as
a human sanity check for people who know St Petersburg, not as strict GIS
validation.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUTPUTS_DIR = ROOT / "outputs"
DEFAULT_SCENARIOS = {
    "baseline": OUTPUTS_DIR / "full_spb_baseline_zone_metrics.csv",
    "high_demand": OUTPUTS_DIR / "full_spb_high_demand_zone_metrics.csv",
    "fleet_shortage_clean": OUTPUTS_DIR / "full_spb_fleet_shortage_clean_zone_metrics.csv",
    "system_stress": OUTPUTS_DIR / "full_spb_system_stress_zone_metrics.csv",
    "simple_relocation": OUTPUTS_DIR / "full_spb_simple_relocation_zone_metrics.csv",
    "relocation_stress": OUTPUTS_DIR / "full_spb_relocation_stress_zone_metrics.csv",
}

# Approximate reference points. These are not legal district centroids; they are
# enough to orient a map/debug table spatially.
REFERENCE_AREAS = [
    ("city_centre", 59.9398, 30.3146),
    ("vasileostrovsky_petrovsky", 59.9430, 30.2600),
    ("north_primorsky", 60.0100, 30.2450),
    ("north_vyborgsky", 60.0400, 30.3400),
    ("east_nevsky", 59.9100, 30.4700),
    ("south_moskovsky", 59.8500, 30.3200),
    ("south_kupchino", 59.8300, 30.3900),
    ("south_west", 59.8450, 30.1750),
    ("kolpino", 59.7500, 30.6000),
    ("pushkin_pavlovsk", 59.7200, 30.4100),
    ("peterhof_strelna", 59.8850, 29.9100),
    ("lomonosov", 59.9100, 29.7700),
    ("kronstadt", 59.9900, 29.7750),
    ("sestroretsk_kurortny", 60.0950, 29.9600),
    ("krasnoe_selo", 59.7350, 30.0850),
]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_reference_area(lat: float, lon: float) -> tuple[str, float]:
    best_name = "unknown"
    best_distance = float("inf")
    for name, ref_lat, ref_lon in REFERENCE_AREAS:
        d = haversine_km(lat, lon, ref_lat, ref_lon)
        if d < best_distance:
            best_name = name
            best_distance = d
    return best_name, round(best_distance, 2)


def load_zone_centroids(zones_geojson: Path) -> pd.DataFrame:
    zones = gpd.read_file(zones_geojson)
    if "zone_id" not in zones.columns:
        zones["zone_id"] = zones.index.astype(int)
    zones["zone_id"] = pd.to_numeric(zones["zone_id"], errors="coerce").astype("Int64")
    zones = zones.dropna(subset=["zone_id"]).copy()
    zones["zone_id"] = zones["zone_id"].astype(int)
    if zones.crs is None:
        zones = zones.set_crs("EPSG:4326")
    zones = zones.to_crs("EPSG:4326")
    local_crs = zones.estimate_utm_crs() or "EPSG:32636"
    local = zones.to_crs(local_crs)
    points = local.geometry.centroid
    cent = gpd.GeoDataFrame(zones[["zone_id"]].copy(), geometry=points, crs=local_crs).to_crs("EPSG:4326")
    cent["centroid_lon"] = cent.geometry.x
    cent["centroid_lat"] = cent.geometry.y
    refs = cent.apply(lambda row: nearest_reference_area(row["centroid_lat"], row["centroid_lon"]), axis=1)
    cent["nearest_reference_area"] = [x[0] for x in refs]
    cent["distance_to_reference_km"] = [x[1] for x in refs]
    return cent.drop(columns="geometry")


def main() -> None:
    parser = argparse.ArgumentParser(description="Spatial sanity-check tables for full-SPb scenario outputs.")
    parser.add_argument("--zones-geojson", default=str(ROOT / "data" / "raw" / "nir1" / "zones.geojson"))
    parser.add_argument("--output-dir", default=str(OUTPUTS_DIR / "full_spb_sanity"))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    centroids = load_zone_centroids(Path(args.zones_geojson))

    scenario_rows = []
    for scenario, path in DEFAULT_SCENARIOS.items():
        if not path.exists():
            continue
        df = pd.read_csv(path)
        df["scenario"] = scenario
        df["zone_id"] = pd.to_numeric(df["zone_id"], errors="coerce").astype("Int64")
        df = df.dropna(subset=["zone_id"]).copy()
        df["zone_id"] = df["zone_id"].astype(int)
        scenario_rows.append(df)

    if not scenario_rows:
        raise FileNotFoundError("No full_spb_*_zone_metrics.csv files found in outputs/. Run experiments/run_full_spb_scenarios.py first.")

    metrics = pd.concat(scenario_rows, ignore_index=True)
    enriched = metrics.merge(centroids, on="zone_id", how="left")
    enriched.to_csv(output_dir / "full_spb_zone_metrics_with_reference_areas.csv", index=False, encoding="utf-8-sig")

    grouped = (
        enriched.groupby(["scenario", "nearest_reference_area"], dropna=False)
        .agg(
            zones=("zone_id", "nunique"),
            active_zones=("total_orders", lambda s: int((s > 0).sum())),
            total_orders=("total_orders", "sum"),
            completed_orders=("completed_orders", "sum"),
            cancelled_no_vehicle=("cancelled_no_vehicle", "sum"),
            cancelled_by_client=("cancelled_by_client", "sum"),
        )
        .reset_index()
    )
    grouped["completion_rate"] = (grouped["completed_orders"] / grouped["total_orders"]).where(grouped["total_orders"] > 0, 0).round(4)
    grouped["shortage_rate"] = (grouped["cancelled_no_vehicle"] / grouped["total_orders"]).where(grouped["total_orders"] > 0, 0).round(4)
    grouped = grouped.sort_values(["scenario", "cancelled_no_vehicle", "total_orders"], ascending=[True, False, False])
    grouped.to_csv(output_dir / "full_spb_sanity_by_reference_area.csv", index=False, encoding="utf-8-sig")

    top = (
        enriched[enriched["total_orders"] > 0]
        .sort_values(["scenario", "cancelled_no_vehicle", "shortage_rate", "total_orders"], ascending=[True, False, False, False])
        .groupby("scenario")
        .head(15)
    )
    cols = [
        "scenario", "zone_id", "zone_name", "nearest_reference_area", "centroid_lat", "centroid_lon",
        "total_orders", "completed_orders", "cancelled_no_vehicle", "shortage_rate", "completion_rate",
    ]
    top[cols].to_csv(output_dir / "full_spb_top_problem_zones_with_reference_areas.csv", index=False, encoding="utf-8-sig")

    print("Saved spatial sanity outputs to:", output_dir)
    print("Top reference areas by no-vehicle cancellations:")
    print(grouped.groupby("scenario").head(5).to_string(index=False))


if __name__ == "__main__":
    main()
