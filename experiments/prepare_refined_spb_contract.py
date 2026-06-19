"""Prepare a refined square-ish full-SPb contract from the v0.10 full-SPb contract.

Why this exists
---------------
The original NIR1 grid is coarse and many cells are elongated rectangles. That is
fine for a first MVP, but visually and operationally it can produce sharp jumps
between neighbouring zones and a map that looks too blocky.

This converter keeps the same underlying NIR1 demand source, but splits each
parent NIR1 zone along its longest side into smaller square-ish subzones. The
parent OD demand is then distributed to subzones by the area/activity share of
subzones. This is still model-derived demand, not observed carsharing demand.

Outputs:
    data/processed/refined_spb_zones.geojson
    data/processed/zones_from_nir1_refined_spb_contract.csv
    data/processed/od_demand_from_nir1_refined_spb_contract.csv
    data/processed/refined_spb_contract_diagnostics.csv
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _to_int_zone_id(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype("Int64")


def _safe_positive(series: pd.Series, default: float = 0.0) -> pd.Series:
    out = pd.to_numeric(series, errors="coerce").fillna(default)
    out = out.replace([float("inf"), -float("inf")], default)
    return out.clip(lower=0.0)


def _split_counts(width: float, height: float, max_splits_per_axis: int) -> tuple[int, int]:
    """Split only along the longest side to make elongated rectangles closer to squares."""
    if width <= 0 or height <= 0:
        return 1, 1
    aspect = max(width / height, height / width)
    if aspect < 1.20:
        return 1, 1
    splits = max(2, int(round(aspect)))
    splits = min(max_splits_per_axis, splits)
    if width >= height:
        return splits, 1
    return 1, splits


def build_refined_geometries(
    zones_geojson: Path,
    parent_zones_contract: pd.DataFrame,
    output_geojson: Path,
    max_splits_per_axis: int,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    zones = gpd.read_file(zones_geojson)
    if "zone_id" not in zones.columns:
        zones["zone_id"] = zones.index.astype(int)
    zones["zone_id"] = _to_int_zone_id(zones["zone_id"])
    zones = zones.dropna(subset=["zone_id"]).copy()
    zones["zone_id"] = zones["zone_id"].astype(int)
    if zones.crs is None:
        zones = zones.set_crs("EPSG:4326")

    try:
        local_crs = zones.estimate_utm_crs() or "EPSG:32636"
    except Exception:
        local_crs = "EPSG:32636"

    zones_local = zones.to_crs(local_crs)

    parent = parent_zones_contract.copy()
    parent["zone_id"] = _to_int_zone_id(parent["zone_id"])
    parent = parent.dropna(subset=["zone_id"]).copy()
    parent["zone_id"] = parent["zone_id"].astype(int)
    parent = parent.set_index("zone_id", drop=False)

    refined_rows = []
    for _, row in zones_local.iterrows():
        parent_id = int(row["zone_id"])
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        minx, miny, maxx, maxy = geom.bounds
        width = float(maxx - minx)
        height = float(maxy - miny)
        nx, ny = _split_counts(width, height, max_splits_per_axis=max_splits_per_axis)
        dx = width / nx
        dy = height / ny

        part_index = 0
        parent_area = max(float(geom.area), 1.0)
        for ix in range(nx):
            for iy in range(ny):
                cell = box(minx + ix * dx, miny + iy * dy, minx + (ix + 1) * dx, miny + (iy + 1) * dy)
                piece = geom.intersection(cell)
                if piece.is_empty or float(piece.area) <= 1.0:
                    continue
                subzone_id = parent_id * 100 + part_index
                refined_rows.append(
                    {
                        "zone_id": subzone_id,
                        "parent_zone_id": parent_id,
                        "parent_part_index": part_index,
                        "area_share_raw": float(piece.area) / parent_area,
                        "geometry": piece,
                    }
                )
                part_index += 1

    refined = gpd.GeoDataFrame(refined_rows, geometry="geometry", crs=local_crs)
    if refined.empty:
        raise ValueError("No refined zones were created.")

    # Normalize area shares within each parent zone. Clipping/intersection can leave tiny numerical residue.
    refined["area_share"] = refined.groupby("parent_zone_id")["area_share_raw"].transform(lambda s: s / s.sum())

    local_centroid = refined.geometry.centroid
    min_x = float(local_centroid.x.min())
    min_y = float(local_centroid.y.min())
    refined["centroid_x"] = ((local_centroid.x - min_x) / 1000.0) / 4.0
    refined["centroid_y"] = ((local_centroid.y - min_y) / 1000.0) / 4.0

    # Attach and distribute parent attributes.
    attr_cols = ["name", "population_proxy", "jobs_proxy", "poi_count", "zone_type"]
    parent_attrs = parent[attr_cols].copy()
    refined = refined.merge(parent_attrs, left_on="parent_zone_id", right_index=True, how="left")

    refined["population_proxy"] = _safe_positive(refined["population_proxy"]) * refined["area_share"]
    refined["jobs_proxy"] = _safe_positive(refined["jobs_proxy"], default=1.0) * refined["area_share"]
    refined["poi_count"] = (_safe_positive(refined["poi_count"], default=1.0) * refined["area_share"]).round().clip(lower=1).astype(int)
    refined["zone_type"] = refined["zone_type"].fillna("mixed")
    refined["name"] = (
        "NIR1 refined SPb zone "
        + refined["zone_id"].astype(str)
        + " / parent "
        + refined["parent_zone_id"].astype(str)
    )

    output_geojson.parent.mkdir(parents=True, exist_ok=True)
    refined.to_crs("EPSG:4326").to_file(output_geojson, driver="GeoJSON")

    refined_contract = refined[
        [
            "zone_id",
            "parent_zone_id",
            "name",
            "centroid_x",
            "centroid_y",
            "population_proxy",
            "jobs_proxy",
            "poi_count",
            "zone_type",
            "area_share",
        ]
    ].sort_values(["parent_zone_id", "zone_id"])

    return refined, refined_contract


def prepare_refined_od(
    parent_od_path: Path,
    refined_contract: pd.DataFrame,
    output_path: Path,
    min_base_demand: float,
) -> pd.DataFrame:
    parent_od = pd.read_csv(parent_od_path)
    required = {"origin_zone_id", "destination_zone_id", "base_demand", "distance_km"}
    missing = required - set(parent_od.columns)
    if missing:
        raise ValueError(f"Missing columns in parent OD file: {sorted(missing)}")

    refined = refined_contract.copy()
    refined["zone_id"] = refined["zone_id"].astype(int)
    refined["parent_zone_id"] = refined["parent_zone_id"].astype(int)

    # Subzone weights combine area and activity. This prevents an empty sliver from receiving
    # the same demand as a denser part of the parent zone.
    refined["activity"] = (
        refined["population_proxy"].clip(lower=0.0) * 0.55
        + refined["jobs_proxy"].clip(lower=0.0) * 0.35
        + refined["poi_count"].clip(lower=1).astype(float) * 10.0
    )
    refined["raw_weight"] = (0.30 * refined["area_share"] + 0.70 * refined["activity"])
    refined["subzone_weight"] = refined.groupby("parent_zone_id")["raw_weight"].transform(lambda s: s / s.sum())

    children: dict[int, list[dict]] = {}
    for _, r in refined.iterrows():
        children.setdefault(int(r["parent_zone_id"]), []).append(
            {
                "zone_id": int(r["zone_id"]),
                "weight": float(r["subzone_weight"]),
                "cx": float(r["centroid_x"]),
                "cy": float(r["centroid_y"]),
            }
        )

    rows = []
    for _, od in parent_od.iterrows():
        origin_parent = int(od["origin_zone_id"])
        dest_parent = int(od["destination_zone_id"])
        base = float(od["base_demand"])
        if base <= 0:
            continue
        origin_children = children.get(origin_parent)
        dest_children = children.get(dest_parent)
        if not origin_children or not dest_children:
            continue
        for oc in origin_children:
            for dc in dest_children:
                if oc["zone_id"] == dc["zone_id"]:
                    continue
                refined_base = base * oc["weight"] * dc["weight"]
                if refined_base < min_base_demand:
                    continue
                distance_km = math.sqrt((oc["cx"] - dc["cx"]) ** 2 + (oc["cy"] - dc["cy"]) ** 2) * 4.0
                rows.append(
                    {
                        "origin_zone_id": oc["zone_id"],
                        "destination_zone_id": dc["zone_id"],
                        "parent_origin_zone_id": origin_parent,
                        "parent_destination_zone_id": dest_parent,
                        "base_demand": round(refined_base, 10),
                        "distance_km": round(max(0.1, distance_km), 4),
                    }
                )

    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError("Refined OD contract is empty.")
    out = out.sort_values(["origin_zone_id", "destination_zone_id"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False, encoding="utf-8")
    return out


def write_diagnostics(refined_contract: pd.DataFrame, refined_od: pd.DataFrame, output_path: Path) -> pd.DataFrame:
    rows = [
        ["refined_zones", int(refined_contract["zone_id"].nunique())],
        ["parent_zones", int(refined_contract["parent_zone_id"].nunique())],
        ["avg_subzones_per_parent", round(float(refined_contract.groupby("parent_zone_id").size().mean()), 3)],
        ["refined_od_rows", int(len(refined_od))],
        ["origin_subzones_in_od", int(refined_od["origin_zone_id"].nunique())],
        ["destination_subzones_in_od", int(refined_od["destination_zone_id"].nunique())],
        ["total_base_demand_per_hour", round(float(refined_od["base_demand"].sum()), 6)],
    ]
    diag = pd.DataFrame(rows, columns=["metric", "value"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    diag.to_csv(output_path, index=False, encoding="utf-8-sig")
    return diag


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a square-ish refined SPb contract from the v0.10 full-SPb contract.")
    parser.add_argument("--zones-geojson", default=str(ROOT / "data" / "raw" / "nir1" / "zones.geojson"))
    parser.add_argument("--parent-zones", default=str(ROOT / "data" / "processed" / "zones_from_nir1_full_spb_contract.csv"))
    parser.add_argument("--parent-od", default=str(ROOT / "data" / "processed" / "od_demand_from_nir1_full_spb_contract.csv"))
    parser.add_argument("--output-dir", default=str(ROOT / "data" / "processed"))
    parser.add_argument("--max-splits-per-axis", type=int, default=3)
    parser.add_argument("--min-base-demand", type=float, default=1e-9)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    parent_zones = pd.read_csv(args.parent_zones)

    refined_geojson_path = output_dir / "refined_spb_zones.geojson"
    refined_zones_path = output_dir / "zones_from_nir1_refined_spb_contract.csv"
    refined_od_path = output_dir / "od_demand_from_nir1_refined_spb_contract.csv"
    diag_path = output_dir / "refined_spb_contract_diagnostics.csv"

    _, refined_contract = build_refined_geometries(
        zones_geojson=Path(args.zones_geojson),
        parent_zones_contract=parent_zones,
        output_geojson=refined_geojson_path,
        max_splits_per_axis=max(1, args.max_splits_per_axis),
    )
    refined_contract.to_csv(refined_zones_path, index=False, encoding="utf-8")

    refined_od = prepare_refined_od(
        parent_od_path=Path(args.parent_od),
        refined_contract=refined_contract,
        output_path=refined_od_path,
        min_base_demand=args.min_base_demand,
    )
    diag = write_diagnostics(refined_contract, refined_od, diag_path)

    print("Prepared refined square-ish SPb contracts.")
    print(f"refined zones geojson: {refined_geojson_path}")
    print(f"refined zones contract: {refined_zones_path}")
    print(f"refined OD contract: {refined_od_path}")
    print(f"diagnostics: {diag_path}")
    print("\nDiagnostics:")
    print(diag.to_string(index=False))


if __name__ == "__main__":
    main()
