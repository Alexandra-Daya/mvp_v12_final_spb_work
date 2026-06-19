from pathlib import Path

import pandas as pd
import geopandas as gpd


BASE_DIR = Path(__file__).resolve().parents[1]

ZONES_PATH = BASE_DIR / "data" / "raw" / "nir1" / "zones.geojson"
DEMAND_PATH = BASE_DIR / "data" / "processed" / "od_demand_from_nir1_contract.csv"

STATS_CANDIDATES = [
    BASE_DIR / "outputs" / "zone_shortage_comparison_all_scenarios.csv",
    BASE_DIR / "outputs" / "figures" / "zone_shortage_comparison_all_scenarios.csv",
]

OUT_DIR = BASE_DIR / "outputs" / "zone_maps"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def find_existing(paths):
    for p in paths:
        if p.exists():
            return p
    raise FileNotFoundError("Не найден zone_shortage_comparison_all_scenarios.csv")


def find_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def main():
    stats_path = find_existing(STATS_CANDIDATES)

    zones = gpd.read_file(ZONES_PATH)
    if "zone_id" not in zones.columns:
        zones["zone_id"] = zones.index.astype(int)

    zones["zone_id"] = pd.to_numeric(zones["zone_id"], errors="coerce").astype("Int64")
    zones = zones.dropna(subset=["zone_id"]).copy()
    zones["zone_id"] = zones["zone_id"].astype(int)

    if zones.crs is None:
        zones = zones.set_crs("EPSG:4326")

    zones_wgs = zones.to_crs("EPSG:4326")
    zones_wgs["centroid_lon"] = zones_wgs.geometry.centroid.x
    zones_wgs["centroid_lat"] = zones_wgs.geometry.centroid.y

    stats = pd.read_csv(stats_path)
    stats["zone_id"] = pd.to_numeric(stats["zone_id"], errors="coerce").astype("Int64")
    stats = stats.dropna(subset=["zone_id"]).copy()
    stats["zone_id"] = stats["zone_id"].astype(int)

    demand = pd.read_csv(DEMAND_PATH)

    origin_col = find_col(demand, ["origin_zone_id", "origin", "origin_zone", "origin_id"])
    dest_col = find_col(demand, ["destination_zone_id", "dest", "destination", "dest_zone", "destination_id"])

    if origin_col is None or dest_col is None:
        raise ValueError(f"Не нашёл origin/destination колонки в demand. Колонки: {list(demand.columns)}")

    demand[origin_col] = pd.to_numeric(demand[origin_col], errors="coerce").astype("Int64")
    demand[dest_col] = pd.to_numeric(demand[dest_col], errors="coerce").astype("Int64")

    origin_zones = set(demand[origin_col].dropna().astype(int))
    dest_zones = set(demand[dest_col].dropna().astype(int))
    demand_zones = origin_zones | dest_zones

    geo_zones = set(zones_wgs["zone_id"])
    stats_zones = set(stats["zone_id"])

    rows = []

    rows.append(["Всего зон в zones.geojson", len(geo_zones)])
    rows.append(["Зон-источников спроса в OD demand", len(origin_zones)])
    rows.append(["Зон-назначений спроса в OD demand", len(dest_zones)])
    rows.append(["Уникальных зон в OD demand", len(demand_zones)])
    rows.append(["Зон, которые есть в OD demand, но нет в zones.geojson", len(demand_zones - geo_zones)])
    rows.append(["Зон, которые есть в stats, но нет в zones.geojson", len(stats_zones - geo_zones)])
    rows.append(["Зон из геометрии без участия в OD demand", len(geo_zones - demand_zones)])

    for scenario in sorted(stats["scenario"].unique()):
        s = stats[stats["scenario"] == scenario].copy()
        rows.append([f"{scenario}: зон с total_orders > 0", int((s["total_orders"] > 0).sum())])
        rows.append([f"{scenario}: зон с shortage_rate > 0", int((s["shortage_rate"] > 0).sum())])
        rows.append([f"{scenario}: зон с shortage_rate = 1", int((s["shortage_rate"] >= 1.0).sum())])
        rows.append([f"{scenario}: сумма total_orders по zone stats", int(s["total_orders"].sum())])
        rows.append([f"{scenario}: сумма cancelled_no_vehicle по zone stats", int(s["cancelled_no_vehicle"].sum())])

    report = pd.DataFrame(rows, columns=["check", "value"])
    report.to_csv(OUT_DIR / "zone_coverage_diagnostics.csv", index=False, encoding="utf-8-sig")

    enriched = zones_wgs[["zone_id", "centroid_lat", "centroid_lon", "geometry"]].merge(
        stats,
        on="zone_id",
        how="left",
    )

    enriched["has_demand_zone"] = enriched["zone_id"].isin(demand_zones)
    enriched["has_stats"] = enriched["zone_id"].isin(stats_zones)

    enriched.drop(columns="geometry").to_csv(
        OUT_DIR / "zone_coverage_enriched.csv",
        index=False,
        encoding="utf-8-sig",
    )

    print("\n=== DIAGNOSTICS ===")
    print(report.to_string(index=False))

    print("\nSaved:")
    print(OUT_DIR / "zone_coverage_diagnostics.csv")
    print(OUT_DIR / "zone_coverage_enriched.csv")

    print("\nTop problematic zones in fleet_shortage_clean:")
    top = (
        enriched[enriched["scenario"] == "fleet_shortage_clean"]
        .sort_values(["shortage_rate", "cancelled_no_vehicle", "total_orders"], ascending=False)
        .head(15)
    )
    print(top[["zone_id", "centroid_lat", "centroid_lon", "total_orders", "cancelled_no_vehicle", "shortage_rate"]].to_string(index=False))


if __name__ == "__main__":
    main()