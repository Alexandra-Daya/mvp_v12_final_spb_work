"""Prepare a full-coverage St Petersburg NIR1 contract for the MVP simulator.

This script is intentionally separate from prepare_nir1_contract.py.
The older converter keeps only top OD links, which is fast but collapses the
active map to ~40 zones. This converter keeps the full NIR1 zone grid and all
positive OD links, then applies a small explicit coverage floor for populated
zones so peripheral districts are not silently dropped from the simulation.

The coverage floor is a modeling assumption, not observed carsharing demand.
It should be documented as such.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

HOUR_FACTOR_SUM = 7 * 0.35 + 4 * 1.5 + 6 * 1.0 + 4 * 1.8 + 3 * 0.8  # 24.05 for the current demand generator

DEMAND_CANDIDATES = ["ml_flow", "real_flow", "gravity_scaled", "radiation_scaled", "gravity_flow", "radiation_flow"]


def choose_demand_column(df: pd.DataFrame, requested: str | None) -> str:
    if requested:
        if requested not in df.columns:
            raise ValueError(f"Requested demand column not found: {requested}. Available: {list(df.columns)}")
        return requested
    for col in DEMAND_CANDIDATES:
        if col in df.columns:
            return col
    raise ValueError(f"No supported demand column found. Available: {list(df.columns)}")


def positive_numeric(series: pd.Series, default: float = 0.0) -> pd.Series:
    out = pd.to_numeric(series, errors="coerce").fillna(default)
    out = out.replace([float("inf"), -float("inf")], default)
    return out.clip(lower=0.0)


def collect_zone_features(od: pd.DataFrame) -> pd.DataFrame:
    origin = od[["origin", "pop_i", "jobs_i"]].rename(
        columns={"origin": "zone_id", "pop_i": "population_proxy", "jobs_i": "jobs_proxy"}
    )
    dest = od[["dest", "pop_j", "jobs_j"]].rename(
        columns={"dest": "zone_id", "pop_j": "population_proxy", "jobs_j": "jobs_proxy"}
    )
    features = pd.concat([origin, dest], ignore_index=True)
    features["zone_id"] = positive_numeric(features["zone_id"]).astype(int)
    features["population_proxy"] = positive_numeric(features["population_proxy"])
    features["jobs_proxy"] = positive_numeric(features["jobs_proxy"])
    result = features.groupby("zone_id", as_index=False).agg(
        population_proxy=("population_proxy", "mean"),
        jobs_proxy=("jobs_proxy", "mean"),
    )
    # Jobs proxy in the original notebook is derived from POI count + 1 in many zones.
    result["poi_count"] = result["jobs_proxy"].round().clip(lower=1).astype(int)
    result["zone_type"] = result.apply(classify_zone, axis=1)
    return result


def classify_zone(row: pd.Series) -> str:
    pop = float(row.get("population_proxy", 0.0))
    jobs = float(row.get("jobs_proxy", 0.0))
    if pop <= 1 and jobs <= 1:
        return "inactive_or_water"
    if jobs > pop * 0.08 and jobs > 500:
        return "business_mixed"
    if pop > 5000 and jobs < 50:
        return "residential"
    return "mixed"


def prepare_zones_contract(zones_geojson: Path, zone_features: pd.DataFrame, output_path: Path) -> pd.DataFrame:
    zones = gpd.read_file(zones_geojson)
    if "zone_id" not in zones.columns:
        zones["zone_id"] = zones.index.astype(int)
    zones["zone_id"] = pd.to_numeric(zones["zone_id"], errors="coerce").astype("Int64")
    zones = zones.dropna(subset=["zone_id"]).copy()
    zones["zone_id"] = zones["zone_id"].astype(int)

    if zones.crs is None:
        zones = zones.set_crs("EPSG:4326")

    try:
        local_crs = zones.estimate_utm_crs() or "EPSG:32636"
    except Exception:
        local_crs = "EPSG:32636"

    zones_local = zones.to_crs(local_crs)
    centroid = zones_local.geometry.centroid
    min_x = float(centroid.x.min())
    min_y = float(centroid.y.min())

    # BasicAllocator multiplies centroid distance by 4.0. Store local km / 4
    # so simulated distances remain approximately in kilometres.
    zones_local["centroid_x"] = ((centroid.x - min_x) / 1000.0) / 4.0
    zones_local["centroid_y"] = ((centroid.y - min_y) / 1000.0) / 4.0

    zones_out = zones_local[["zone_id", "centroid_x", "centroid_y"]].merge(
        zone_features,
        on="zone_id",
        how="left",
    )
    zones_out["population_proxy"] = zones_out["population_proxy"].fillna(0.0)
    zones_out["jobs_proxy"] = zones_out["jobs_proxy"].fillna(1.0)
    zones_out["poi_count"] = zones_out["poi_count"].fillna(1).astype(int)
    zones_out["zone_type"] = zones_out["zone_type"].fillna("inactive_or_water")
    zones_out["name"] = "NIR1 full SPb zone " + zones_out["zone_id"].astype(str)

    zones_out = zones_out[
        [
            "zone_id",
            "name",
            "centroid_x",
            "centroid_y",
            "population_proxy",
            "jobs_proxy",
            "poi_count",
            "zone_type",
        ]
    ].sort_values("zone_id")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    zones_out.to_csv(output_path, index=False, encoding="utf-8")
    return zones_out


def prepare_full_od_contract(
    od: pd.DataFrame,
    demand_column: str,
    zones_contract: pd.DataFrame,
    output_path: Path,
    target_total_base_demand: float,
    min_origin_daily_demand: float,
    min_population_for_floor: float,
    min_jobs_for_floor: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {"origin", "dest", "distance", demand_column}
    missing = required - set(od.columns)
    if missing:
        raise ValueError(f"Missing columns in OD file: {sorted(missing)}")

    work = od.copy()
    work["origin_zone_id"] = positive_numeric(work["origin"]).astype(int)
    work["destination_zone_id"] = positive_numeric(work["dest"]).astype(int)
    work["distance_km"] = positive_numeric(work["distance"], default=1.0).clip(lower=0.1)
    work["source_flow"] = positive_numeric(work[demand_column])
    work = work[(work["origin_zone_id"] != work["destination_zone_id"]) & (work["source_flow"] > 0)].copy()

    if work.empty:
        raise ValueError("No positive OD rows after filtering.")

    base_scale = target_total_base_demand / work["source_flow"].sum()
    work["base_demand_raw_scaled"] = work["source_flow"] * base_scale
    work["base_demand"] = work["base_demand_raw_scaled"]

    zone_activity = zones_contract[["zone_id", "population_proxy", "jobs_proxy", "zone_type"]].copy()
    eligible_zone_ids = set(
        zone_activity[
            (zone_activity["population_proxy"] >= min_population_for_floor)
            | (zone_activity["jobs_proxy"] >= min_jobs_for_floor)
        ]["zone_id"].astype(int)
    )

    origin_base = work.groupby("origin_zone_id")["base_demand"].sum()
    floor_rows = []
    for origin_id, current_base in origin_base.items():
        if int(origin_id) not in eligible_zone_ids:
            continue
        current_daily = float(current_base) * HOUR_FACTOR_SUM
        if current_daily <= 0:
            continue
        if current_daily < min_origin_daily_demand:
            factor = min_origin_daily_demand / current_daily
            work.loc[work["origin_zone_id"] == origin_id, "base_demand"] *= factor
            floor_rows.append({
                "zone_id": int(origin_id),
                "daily_before_floor": current_daily,
                "daily_after_floor": min_origin_daily_demand,
                "boost_factor": factor,
            })

    out = work[["origin_zone_id", "destination_zone_id", "base_demand", "distance_km", "source_flow"]].copy()
    out["base_demand"] = out["base_demand"].round(8)
    out["distance_km"] = out["distance_km"].round(4)
    out["source_flow"] = out["source_flow"].round(8)
    out = out.sort_values(["origin_zone_id", "destination_zone_id"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False, encoding="utf-8")

    floors = pd.DataFrame(floor_rows)
    return out, floors


def write_diagnostics(
    zones_contract: pd.DataFrame,
    od_contract: pd.DataFrame,
    floors: pd.DataFrame,
    output_path: Path,
) -> pd.DataFrame:
    zone_ids = set(zones_contract["zone_id"].astype(int))
    origin_ids = set(od_contract["origin_zone_id"].astype(int))
    dest_ids = set(od_contract["destination_zone_id"].astype(int))
    daily_by_origin = od_contract.groupby("origin_zone_id")["base_demand"].sum() * HOUR_FACTOR_SUM

    rows = [
        ["zones_in_geojson_contract", len(zone_ids)],
        ["od_rows_in_full_contract", len(od_contract)],
        ["origin_zones_in_od_contract", len(origin_ids)],
        ["destination_zones_in_od_contract", len(dest_ids)],
        ["zones_without_origin_demand", len(zone_ids - origin_ids)],
        ["zones_without_destination_demand", len(zone_ids - dest_ids)],
        ["total_base_demand_per_hour_after_floor", round(float(od_contract["base_demand"].sum()), 4)],
        ["expected_orders_per_day_after_floor", round(float(od_contract["base_demand"].sum() * HOUR_FACTOR_SUM), 2)],
        ["origins_with_expected_daily_orders_below_1", int((daily_by_origin < 1).sum())],
        ["origins_boosted_by_coverage_floor", len(floors)],
    ]
    diagnostics = pd.DataFrame(rows, columns=["metric", "value"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(output_path, index=False, encoding="utf-8-sig")
    return diagnostics


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare full-coverage St Petersburg contracts from NIR1 OD predictions and zones.geojson.")
    parser.add_argument("--input", default=str(ROOT / "data" / "raw" / "nir1" / "od_pairs_with_predictions.csv"))
    parser.add_argument("--zones-geojson", default=str(ROOT / "data" / "raw" / "nir1" / "zones.geojson"))
    parser.add_argument("--output-dir", default=str(ROOT / "data" / "processed"))
    parser.add_argument("--demand-column", default=None, help="Default: first available from ml_flow, real_flow, gravity_scaled, ...")
    parser.add_argument("--target-total-base-demand", type=float, default=45.0)
    parser.add_argument("--min-origin-daily-demand", type=float, default=1.0)
    parser.add_argument("--min-population-for-floor", type=float, default=100.0)
    parser.add_argument("--min-jobs-for-floor", type=float, default=5.0)
    args = parser.parse_args()

    input_path = Path(args.input)
    zones_geojson = Path(args.zones_geojson)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    od = pd.read_csv(input_path)
    demand_column = choose_demand_column(od, args.demand_column)
    zone_features = collect_zone_features(od)

    zones_path = output_dir / "zones_from_nir1_full_spb_contract.csv"
    od_path = output_dir / "od_demand_from_nir1_full_spb_contract.csv"
    diagnostics_path = output_dir / "full_spb_contract_diagnostics.csv"
    floors_path = output_dir / "full_spb_origin_floor_boosts.csv"

    zones_contract = prepare_zones_contract(zones_geojson, zone_features, zones_path)
    od_contract, floors = prepare_full_od_contract(
        od=od,
        demand_column=demand_column,
        zones_contract=zones_contract,
        output_path=od_path,
        target_total_base_demand=args.target_total_base_demand,
        min_origin_daily_demand=args.min_origin_daily_demand,
        min_population_for_floor=args.min_population_for_floor,
        min_jobs_for_floor=args.min_jobs_for_floor,
    )
    diagnostics = write_diagnostics(zones_contract, od_contract, floors, diagnostics_path)
    floors.to_csv(floors_path, index=False, encoding="utf-8-sig")

    print("Prepared full SPb NIR1 contracts.")
    print(f"Demand column: {demand_column}")
    print(f"zones: {zones_path}")
    print(f"od_demand: {od_path}")
    print(f"diagnostics: {diagnostics_path}")
    print(f"origin floor boosts: {floors_path}")
    print("\nDiagnostics:")
    print(diagnostics.to_string(index=False))
    print("\nNext:")
    print(f"python experiments/run_full_spb_scenarios.py --zones {zones_path} --od-demand {od_path}")


if __name__ == "__main__":
    main()
