"""Interactive soft shortage map for full-SPb scenario outputs.

The map uses the original NIR1 zones.geojson as the geometry, but the demand and
zone metrics come from the full-SPb contract. Zones with no orders are grey;
shortage is shown as a heat layer weighted by cancelled_no_vehicle so a tiny
zone with 1/1 cancelled orders does not look as important as a zone with many
cancelled orders.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import HeatMap

ROOT = Path(__file__).resolve().parents[1]
ZONES_PATH = ROOT / "data" / "raw" / "nir1" / "zones.geojson"
STATS_PATH = ROOT / "outputs" / "full_spb_figures" / "full_spb_zone_shortage_comparison_all_scenarios.csv"
OUT_DIR = ROOT / "outputs" / "full_spb_maps"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SCENARIOS: list[str] | None = None
MIN_MARKER_CANCELLED = 3


def main() -> None:
    zones = gpd.read_file(ZONES_PATH)
    if "zone_id" not in zones.columns:
        zones["zone_id"] = zones.index.astype(int)
    zones["zone_id"] = pd.to_numeric(zones["zone_id"], errors="coerce").astype("Int64")
    zones = zones.dropna(subset=["zone_id"]).copy()
    zones["zone_id"] = zones["zone_id"].astype(int)
    if zones.crs is None:
        zones = zones.set_crs("EPSG:4326")
    zones = zones.to_crs("EPSG:4326")

    stats = pd.read_csv(STATS_PATH)
    stats["zone_id"] = pd.to_numeric(stats["zone_id"], errors="coerce").astype("Int64")
    stats = stats.dropna(subset=["zone_id"]).copy()
    stats["zone_id"] = stats["zone_id"].astype(int)

    global_scale = max(float(stats["cancelled_no_vehicle"].quantile(0.98)), 1.0)
    global_max = max(float(stats["cancelled_no_vehicle"].max()), 1.0)

    center = zones.geometry.union_all().centroid
    m = folium.Map(location=[center.y, center.x], zoom_start=10, tiles="CartoDB positron", control_scale=True)

    folium.GeoJson(
        zones,
        name="Расчётная сетка НИР1: все зоны",
        style_function=lambda feature: {
            "fillColor": "#dddddd",
            "color": "#999999",
            "weight": 0.35,
            "fillOpacity": 0.03,
        },
    ).add_to(m)

    scenario_list = SCENARIOS or list(stats["scenario"].dropna().unique())
    for scenario in scenario_list:
        scenario_stats = stats[stats["scenario"] == scenario].copy()
        gdf = zones.merge(scenario_stats, on="zone_id", how="left")
        for col in ["total_orders", "cancelled_no_vehicle", "shortage_rate", "completion_rate"]:
            gdf[col] = gdf[col].fillna(0)
        gdf["scenario"] = gdf["scenario"].fillna(scenario)

        layer = folium.FeatureGroup(name=f"{scenario}: активные зоны + мягкий дефицит", show=(scenario == "fleet_shortage_clean"))

        # Active zones: visible but not aggressively filled.
        active = gdf[gdf["total_orders"] > 0].copy()
        inactive = gdf[gdf["total_orders"] <= 0].copy()

        if not inactive.empty:
            folium.GeoJson(
                inactive,
                name=f"{scenario}: зоны без заказов",
                style_function=lambda feature: {
                    "fillColor": "#bbbbbb",
                    "color": "#aaaaaa",
                    "weight": 0.25,
                    "fillOpacity": 0.08,
                },
                tooltip=folium.GeoJsonTooltip(fields=["zone_id"], aliases=["Zone ID:"], sticky=True),
            ).add_to(layer)

        if not active.empty:
            folium.GeoJson(
                active,
                name=f"{scenario}: зоны с заказами",
                style_function=lambda feature: {
                    "fillColor": "#ffffff",
                    "color": "#444444",
                    "weight": 0.55,
                    "fillOpacity": 0.02,
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=["zone_id", "total_orders", "cancelled_no_vehicle", "shortage_rate", "completion_rate"],
                    aliases=["Zone ID:", "Orders:", "No vehicle:", "Shortage rate:", "Completion rate:"],
                    localize=True,
                    sticky=True,
                ),
            ).add_to(layer)

        heat_points = []
        for _, row in active.iterrows():
            cancelled = float(row["cancelled_no_vehicle"])
            if cancelled <= 0:
                continue
            c = row.geometry.centroid
            # Use one global scale across scenarios. Otherwise baseline zones with only
            # 3-5 lost requests can look as intense as stress zones with 50-70.
            heat_points.append([c.y, c.x, min(1.0, cancelled / global_scale)])

        if heat_points:
            HeatMap(
                heat_points,
                name=f"{scenario}: heatmap дефицита",
                radius=32,
                blur=38,
                min_opacity=0.06,
                max_zoom=13,
                gradient={0.2: "#ffff99", 0.45: "#ffcc33", 0.7: "#ff6600", 1.0: "#990000"},
            ).add_to(layer)

        top5 = active[active["cancelled_no_vehicle"] >= MIN_MARKER_CANCELLED].sort_values(["cancelled_no_vehicle", "shortage_rate", "total_orders"], ascending=False).head(5)
        for _, row in top5.iterrows():
            c = row.geometry.centroid
            radius = 4 + 4 * min(1.0, float(row["cancelled_no_vehicle"]) / global_max)
            folium.CircleMarker(
                location=[c.y, c.x],
                radius=radius,
                color="black",
                fill=True,
                fill_color="black",
                fill_opacity=0.85,
                popup=(
                    f"<b>{scenario}</b><br>"
                    f"zone_id: {int(row['zone_id'])}<br>"
                    f"orders: {int(row['total_orders'])}<br>"
                    f"cancelled_no_vehicle: {int(row['cancelled_no_vehicle'])}<br>"
                    f"shortage_rate: {float(row['shortage_rate']):.3f}<br>"
                    f"completion_rate: {float(row['completion_rate']):.3f}"
                ),
            ).add_to(layer)

        layer.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    out_path = OUT_DIR / "interactive_full_spb_soft_shortage_map.html"
    m.save(out_path)
    print(f"Saved interactive full-SPb soft map: {out_path}")
    print(f"Global heat scale used: 98th percentile = {global_scale:.2f}; max = {global_max:.2f}")


if __name__ == "__main__":
    main()
