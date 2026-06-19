"""Build the final v12 interactive SPb carsharing shortage map.

The final map intentionally uses the stable full-SPb/NIR1 zone geometry as the
main visual layer. The refined v11 grid is kept as a diagnostic experiment, not
as the reporting map, because its centroid-based heat layer can place visual
points in the Gulf of Finland and make some split zones look misleading.
"""
from __future__ import annotations

from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd
from folium.plugins import HeatMap

ROOT = Path(__file__).resolve().parents[1]
ZONES_PATH = ROOT / "data" / "raw" / "nir1" / "zones.geojson"
STATS_PATH = ROOT / "outputs" / "full_spb_figures" / "full_spb_zone_shortage_comparison_all_scenarios.csv"
SCENARIO_COMPARISON_PATH = ROOT / "outputs" / "final_scenario_comparison.csv"
OUT_DIR = ROOT / "outputs" / "final_maps"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FINAL_ZONE_METRICS_PATH = ROOT / "outputs" / "final_zone_metrics.csv"

DEFAULT_SCENARIO = "fleet_shortage_clean"
MIN_MARKER_LOST_DEMAND = 3


def _read_zones() -> gpd.GeoDataFrame:
    zones = gpd.read_file(ZONES_PATH)
    if "zone_id" not in zones.columns:
        zones["zone_id"] = zones.index.astype(int)
    zones["zone_id"] = pd.to_numeric(zones["zone_id"], errors="coerce").astype("Int64")
    zones = zones.dropna(subset=["zone_id"]).copy()
    zones["zone_id"] = zones["zone_id"].astype(int)
    if zones.crs is None:
        zones = zones.set_crs("EPSG:4326")
    zones = zones.to_crs("EPSG:4326")
    zones = zones[zones.geometry.notna() & ~zones.geometry.is_empty].copy()
    zones["geometry"] = zones.geometry.make_valid()
    return zones


def _add_final_aliases(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "cancelled_no_vehicle" in out.columns and "lost_demand_no_vehicle" not in out.columns:
        out["lost_demand_no_vehicle"] = out["cancelled_no_vehicle"]
    if "cancelled_by_client" in out.columns and "client_rejection_after_vehicle_found" not in out.columns:
        out["client_rejection_after_vehicle_found"] = out["cancelled_by_client"]
    if "shortage_rate" in out.columns:
        out["lost_demand_no_vehicle_rate"] = out["shortage_rate"]
    elif "no_vehicle_rate" in out.columns:
        out["lost_demand_no_vehicle_rate"] = out["no_vehicle_rate"]

    for col in [
        "total_orders",
        "completed_orders",
        "lost_demand_no_vehicle",
        "client_rejection_after_vehicle_found",
        "lost_demand_no_vehicle_rate",
        "completion_rate",
    ]:
        if col not in out.columns:
            out[col] = 0
    return out


def _save_final_zone_metrics(stats: pd.DataFrame) -> pd.DataFrame:
    final = _add_final_aliases(stats)
    preferred = [
        "scenario",
        "zone_id",
        "zone_name",
        "total_orders",
        "completed_orders",
        "lost_demand_no_vehicle",
        "client_rejection_after_vehicle_found",
        "lost_demand_no_vehicle_rate",
        "completion_rate",
        "cancelled_no_vehicle",
        "cancelled_by_client",
        "shortage_rate",
        "rank_in_scenario",
    ]
    cols = [c for c in preferred if c in final.columns] + [c for c in final.columns if c not in preferred]
    final = final[cols]
    final.to_csv(FINAL_ZONE_METRICS_PATH, index=False, encoding="utf-8-sig")
    return final


def _scenario_order(stats: pd.DataFrame) -> list[str]:
    preferred = [
        "baseline",
        "high_demand",
        "fleet_shortage_clean",
        "system_stress",
        "simple_relocation",
        "relocation_stress",
    ]
    available = list(stats["scenario"].dropna().unique())
    ordered = [s for s in preferred if s in available]
    ordered.extend(s for s in available if s not in ordered)
    return ordered


def main() -> None:
    zones = _read_zones()
    stats = pd.read_csv(STATS_PATH)
    stats["zone_id"] = pd.to_numeric(stats["zone_id"], errors="coerce").astype("Int64")
    stats = stats.dropna(subset=["zone_id"]).copy()
    stats["zone_id"] = stats["zone_id"].astype(int)
    stats = _save_final_zone_metrics(stats)

    global_scale = max(float(stats["lost_demand_no_vehicle"].quantile(0.98)), 1.0)
    global_max = max(float(stats["lost_demand_no_vehicle"].max()), 1.0)

    center = zones.geometry.union_all().centroid
    m = folium.Map(location=[center.y, center.x], zoom_start=10, tiles="CartoDB positron", control_scale=True)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)

    folium.GeoJson(
        zones[["zone_id", "geometry"]],
        name="Stable full-SPb calculation grid",
        style_function=lambda feature: {
            "fillColor": "#d7d7d7",
            "color": "#8e8e8e",
            "weight": 0.35,
            "fillOpacity": 0.035,
        },
        tooltip=folium.GeoJsonTooltip(fields=["zone_id"], aliases=["zone_id:"], sticky=True),
    ).add_to(m)

    scenario_list = _scenario_order(stats)
    for scenario in scenario_list:
        scenario_stats = stats[stats["scenario"] == scenario].copy()
        gdf = zones.merge(scenario_stats, on="zone_id", how="left")
        gdf["scenario"] = gdf["scenario"].fillna(scenario)
        for col in [
            "total_orders",
            "completed_orders",
            "lost_demand_no_vehicle",
            "client_rejection_after_vehicle_found",
            "lost_demand_no_vehicle_rate",
            "completion_rate",
        ]:
            gdf[col] = pd.to_numeric(gdf[col], errors="coerce").fillna(0)

        layer = folium.FeatureGroup(
            name=f"{scenario}: full-SPb zones and soft lost-demand glow",
            show=(scenario == DEFAULT_SCENARIO),
        )
        active = gdf[gdf["total_orders"] > 0].copy()
        inactive = gdf[gdf["total_orders"] <= 0].copy()

        if not inactive.empty:
            folium.GeoJson(
                inactive,
                name=f"{scenario}: zones without modeled demand",
                style_function=lambda feature: {
                    "fillColor": "#bcbcbc",
                    "color": "#a0a0a0",
                    "weight": 0.25,
                    "fillOpacity": 0.08,
                },
                tooltip=folium.GeoJsonTooltip(fields=["zone_id", "scenario"], aliases=["zone_id:", "scenario:"], sticky=True),
            ).add_to(layer)

        if not active.empty:
            folium.GeoJson(
                active,
                name=f"{scenario}: active modeled zones",
                style_function=lambda feature: {
                    "fillColor": "#ffffff",
                    "color": "#404040",
                    "weight": 0.55,
                    "fillOpacity": 0.018,
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=[
                        "zone_id",
                        "scenario",
                        "total_orders",
                        "completed_orders",
                        "lost_demand_no_vehicle",
                        "client_rejection_after_vehicle_found",
                        "lost_demand_no_vehicle_rate",
                        "completion_rate",
                    ],
                    aliases=[
                        "zone_id:",
                        "scenario:",
                        "total_orders:",
                        "completed_orders:",
                        "lost_demand_no_vehicle:",
                        "client_rejection_after_vehicle_found:",
                        "lost_demand_no_vehicle_rate:",
                        "completion_rate:",
                    ],
                    localize=True,
                    sticky=True,
                ),
            ).add_to(layer)

        heat_points = []
        for _, row in active.iterrows():
            lost = float(row["lost_demand_no_vehicle"])
            if lost <= 0 or row.geometry is None or row.geometry.is_empty:
                continue
            point = row.geometry.representative_point()
            heat_points.append([point.y, point.x, min(1.0, lost / global_scale)])

        if heat_points:
            HeatMap(
                heat_points,
                name=f"{scenario}: soft glow for lost_demand_no_vehicle",
                radius=30,
                blur=36,
                min_opacity=0.06,
                max_zoom=13,
                gradient={0.2: "#fff6a6", 0.45: "#ffcf4d", 0.7: "#f06b2f", 1.0: "#8b1a1a"},
            ).add_to(layer)

        top = active[active["lost_demand_no_vehicle"] >= MIN_MARKER_LOST_DEMAND].sort_values(
            ["lost_demand_no_vehicle", "lost_demand_no_vehicle_rate", "total_orders"],
            ascending=False,
        ).head(10)
        for _, row in top.iterrows():
            point = row.geometry.representative_point()
            radius = 4 + 5 * min(1.0, float(row["lost_demand_no_vehicle"]) / global_max)
            folium.CircleMarker(
                location=[point.y, point.x],
                radius=radius,
                color="black",
                fill=True,
                fill_color="black",
                fill_opacity=0.86,
                popup=(
                    f"<b>{scenario}</b><br>"
                    f"zone_id: {int(row['zone_id'])}<br>"
                    f"total_orders: {int(row['total_orders'])}<br>"
                    f"completed_orders: {int(row['completed_orders'])}<br>"
                    f"lost_demand_no_vehicle: {int(row['lost_demand_no_vehicle'])}<br>"
                    f"client_rejection_after_vehicle_found: {int(row['client_rejection_after_vehicle_found'])}<br>"
                    f"lost_demand_no_vehicle_rate: {float(row['lost_demand_no_vehicle_rate']):.3f}<br>"
                    f"completion_rate: {float(row['completion_rate']):.3f}"
                ),
            ).add_to(layer)

        layer.add_to(m)

    note_html = """
    <div style="position: fixed; bottom: 18px; left: 18px; z-index: 9999;
        width: 360px; padding: 10px 12px; background: rgba(255,255,255,0.92);
        border: 1px solid #999; font-size: 12px; line-height: 1.35;">
        <b>v12 final map</b><br>
        Main layer: stable full-SPb/NIR1 grid. Refined v11 subzones are not used
        as the reporting map because diagnostic review found water/centroid
        artifacts. Heat points use active full-zone representative points only.
    </div>
    """
    m.get_root().html.add_child(folium.Element(note_html))
    folium.LayerControl(collapsed=False).add_to(m)

    out_path = OUT_DIR / "interactive_final_spb_soft_shortage_map.html"
    m.save(out_path)

    print(f"Saved final v12 interactive map: {out_path}")
    print(f"Saved final zone metrics: {FINAL_ZONE_METRICS_PATH}")
    print(f"Global heat scale: 98th percentile = {global_scale:.2f}; max = {global_max:.2f}")
    if not SCENARIO_COMPARISON_PATH.exists():
        print(f"Warning: scenario comparison not found yet: {SCENARIO_COMPARISON_PATH}")


if __name__ == "__main__":
    main()
