from pathlib import Path

import pandas as pd
import geopandas as gpd
import folium
from branca.colormap import linear


BASE_DIR = Path(__file__).resolve().parents[1]

ZONES_PATH = BASE_DIR / "data" / "raw" / "nir1" / "zones.geojson"
STATS_PATH = BASE_DIR / "outputs" / "figures" / "zone_shortage_comparison_all_scenarios.csv"

OUT_DIR = BASE_DIR / "outputs" / "zone_maps"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    zones = gpd.read_file(ZONES_PATH)

    if "zone_id" not in zones.columns:
        zones["zone_id"] = zones.index.astype(int)

    zones["zone_id"] = zones["zone_id"].astype(int)

    stats = pd.read_csv(STATS_PATH)
    stats["zone_id"] = stats["zone_id"].astype(int)

    if zones.crs is None:
        zones = zones.set_crs("EPSG:4326")

    zones_wgs = zones.to_crs("EPSG:4326")

    center = zones_wgs.geometry.union_all().centroid
    m = folium.Map(
        location=[center.y, center.x],
        zoom_start=10,
        tiles="CartoDB positron",
        control_scale=True,
    )

    colormap = linear.YlOrRd_09.scale(0, 1)
    colormap.caption = "Shortage rate"

    scenarios = ["baseline", "high_demand", "fleet_shortage_clean", "system_stress"]

    for scenario in scenarios:
        scenario_stats = stats[stats["scenario"] == scenario].copy()

        gdf = zones_wgs.merge(scenario_stats, on="zone_id", how="left")
        gdf["shortage_rate"] = gdf["shortage_rate"].fillna(0)
        gdf["total_orders"] = gdf["total_orders"].fillna(0)
        gdf["cancelled_no_vehicle"] = gdf["cancelled_no_vehicle"].fillna(0)
        gdf["completion_rate"] = gdf["completion_rate"].fillna(0)

        layer = folium.FeatureGroup(name=scenario, show=(scenario == "fleet_shortage_clean"))

        def style_function(feature):
            sr = feature["properties"].get("shortage_rate", 0)
            orders = feature["properties"].get("total_orders", 0)

            # зоны без заказов делаем почти прозрачными
            if orders == 0:
                return {
                    "fillColor": "#eeeeee",
                    "color": "#999999",
                    "weight": 0.4,
                    "fillOpacity": 0.12,
                }

            return {
                "fillColor": colormap(sr),
                "color": "#444444",
                "weight": 0.5,
                "fillOpacity": 0.65,
            }

        tooltip = folium.GeoJsonTooltip(
            fields=[
                "zone_id",
                "scenario",
                "total_orders",
                "cancelled_no_vehicle",
                "shortage_rate",
                "completion_rate",
            ],
            aliases=[
                "Zone ID:",
                "Scenario:",
                "Orders:",
                "Cancelled no vehicle:",
                "Shortage rate:",
                "Completion rate:",
            ],
            localize=True,
            sticky=True,
        )

        folium.GeoJson(
            gdf,
            name=scenario,
            style_function=style_function,
            tooltip=tooltip,
        ).add_to(layer)

        # топ-5 проблемных зон — отдельными маркерами
        top5 = gdf.sort_values(
            ["shortage_rate", "cancelled_no_vehicle", "total_orders"],
            ascending=False,
        ).head(5)

        for _, row in top5.iterrows():
            point = row.geometry.centroid
            folium.CircleMarker(
                location=[point.y, point.x],
                radius=5,
                color="black",
                fill=True,
                fill_color="black",
                fill_opacity=0.8,
                popup=(
                    f"<b>{scenario}</b><br>"
                    f"zone_id: {int(row['zone_id'])}<br>"
                    f"orders: {int(row['total_orders'])}<br>"
                    f"cancelled_no_vehicle: {int(row['cancelled_no_vehicle'])}<br>"
                    f"shortage_rate: {row['shortage_rate']:.3f}<br>"
                    f"completion_rate: {row['completion_rate']:.3f}"
                ),
            ).add_to(layer)

        layer.add_to(m)

    colormap.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    out_path = OUT_DIR / "interactive_zone_shortage_map.html"
    m.save(out_path)

    print("Готово.")
    print(f"Интерактивная карта сохранена: {out_path}")


if __name__ == "__main__":
    main()