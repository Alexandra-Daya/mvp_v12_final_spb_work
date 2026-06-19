"""Build the improved v12.1/v13-style final SPb carsharing map.

The calculation model remains the stable full-SPb/NIR1 zone model from v12.
This script adds a visual-only split grid: every source zone is drawn as two
orthogonal rectangle halves for easier reading. Metrics are still attached to
the original full-SPb/NIR1 zones and are not recalculated for visual subzones.
"""
from __future__ import annotations

from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd
from folium.plugins import HeatMap
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
ZONES_PATH = ROOT / "data" / "raw" / "nir1" / "zones.geojson"
FINAL_ZONE_METRICS_PATH = ROOT / "outputs" / "final_zone_metrics.csv"
FINAL_SCENARIO_COMPARISON_PATH = ROOT / "outputs" / "final_scenario_comparison.csv"
OUT_DIR = ROOT / "outputs" / "final_maps_v2"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DIAG_DIR = ROOT / "outputs" / "final_diagnostics"
DIAG_DIR.mkdir(parents=True, exist_ok=True)
DIAG_PATH = DIAG_DIR / "final_map_v2_diagnostics.csv"

DEFAULT_SCENARIO = "fleet_shortage_clean"
MIN_HEAT_LOST_DEMAND = 1.0
MIN_TOP_MARKER_LOST_DEMAND = 10.0
MIN_SCENARIO_MAX_FOR_BLACK_MARKERS = 10.0

SCENARIO_LABELS = {
    "baseline": "Baseline: потерянный спрос",
    "high_demand": "High demand: рост спроса",
    "fleet_shortage_clean": "Fleet shortage: нехватка парка",
    "system_stress": "System stress: высокий спрос + нехватка парка",
    "simple_relocation": "Simple relocation: простая перебалансировка",
    "relocation_stress": "Relocation stress: стресс + перебалансировка",
}


def read_stable_zones() -> gpd.GeoDataFrame:
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


def build_visual_split_grid(zones: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Create two orthogonal visual rectangles for each source zone.

    This is not a calculation grid. It uses each source zone bounding box and
    splits it in half along the longer bounding-box side.
    """
    rows: list[dict[str, object]] = []
    for _, row in zones.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        minx, miny, maxx, maxy = geom.bounds
        width = maxx - minx
        height = maxy - miny
        zone_id = int(row["zone_id"])

        if width >= height:
            mid = (minx + maxx) / 2.0
            parts = [
                ("a", box(minx, miny, mid, maxy)),
                ("b", box(mid, miny, maxx, maxy)),
            ]
        else:
            mid = (miny + maxy) / 2.0
            parts = [
                ("a", box(minx, miny, maxx, mid)),
                ("b", box(minx, mid, maxx, maxy)),
            ]

        for suffix, part in parts:
            rows.append(
                {
                    "zone_id": zone_id,
                    "parent_zone_id": zone_id,
                    "visual_subzone_id": f"{zone_id}_{suffix}",
                    "is_visual_split": 1,
                    "geometry": part,
                }
            )

    return gpd.GeoDataFrame(rows, geometry="geometry", crs=zones.crs)


def add_aliases(df: pd.DataFrame) -> pd.DataFrame:
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
    for col in [
        "total_orders",
        "completed_orders",
        "lost_demand_no_vehicle",
        "lost_demand_no_vehicle_rate",
        "client_rejection_after_vehicle_found",
        "completion_rate",
        "avg_allocated_distance_to_vehicle_km",
        "relocated_vehicles",
    ]:
        if col not in out.columns:
            out[col] = 0
    return out


def scenario_order(stats: pd.DataFrame) -> list[str]:
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


def is_likely_water_point(lat: float, lon: float) -> bool:
    """Conservative no-land-mask filter for obvious Gulf of Finland points."""
    if lon < 29.85:
        return True
    if lon < 30.05 and lat > 59.84:
        return True
    if lon < 30.25 and lat > 60.10:
        return True
    return False


def safe_display_point(geom) -> tuple[float, float, bool]:
    point = geom.representative_point()
    lat = float(point.y)
    lon = float(point.x)
    return lat, lon, is_likely_water_point(lat, lon)


def _numeric(gdf: gpd.GeoDataFrame, columns: list[str]) -> gpd.GeoDataFrame:
    for col in columns:
        gdf[col] = pd.to_numeric(gdf[col], errors="coerce").fillna(0)
    return gdf


def main() -> None:
    zones = read_stable_zones()
    visual_grid = build_visual_split_grid(zones)

    zone_stats = add_aliases(pd.read_csv(FINAL_ZONE_METRICS_PATH))
    scenario_stats = add_aliases(pd.read_csv(FINAL_SCENARIO_COMPARISON_PATH))
    zone_stats["zone_id"] = pd.to_numeric(zone_stats["zone_id"], errors="coerce").astype("Int64")
    zone_stats = zone_stats.dropna(subset=["zone_id"]).copy()
    zone_stats["zone_id"] = zone_stats["zone_id"].astype(int)

    global_scale = max(float(zone_stats["lost_demand_no_vehicle"].quantile(0.98)), 1.0)
    global_max = max(float(zone_stats["lost_demand_no_vehicle"].max()), 1.0)

    center = zones.geometry.union_all().centroid
    m = folium.Map(location=[center.y, center.x], zoom_start=10, tiles=None, control_scale=True)
    folium.TileLayer("CartoDB positron", name="Подложка: CartoDB Positron", control=True).add_to(m)
    folium.TileLayer("OpenStreetMap", name="Подложка: OpenStreetMap", control=True).add_to(m)

    folium.GeoJson(
        zones[["zone_id", "geometry"]],
        name="Расчётная сетка full-SPb / НИР1",
        style_function=lambda feature: {
            "fillColor": "#d8d8d8",
            "color": "#787878",
            "weight": 0.45,
            "fillOpacity": 0.025,
        },
        tooltip=folium.GeoJsonTooltip(fields=["zone_id"], aliases=["zone_id:"], sticky=True),
    ).add_to(m)

    folium.GeoJson(
        visual_grid[["visual_subzone_id", "parent_zone_id", "is_visual_split", "geometry"]],
        name="Визуальная сетка: зоны разделены на 2 части",
        style_function=lambda feature: {
            "fillColor": "#ffffff",
            "color": "#2f2f2f",
            "weight": 0.35,
            "fillOpacity": 0.0,
            "dashArray": "2,3",
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["visual_subzone_id", "parent_zone_id", "is_visual_split"],
            aliases=["visual_subzone_id:", "parent_zone_id:", "visual only:"],
            sticky=True,
        ),
    ).add_to(m)

    diag_rows: list[dict[str, object]] = [
        {"metric": "source_full_spb_zones", "value": int(len(zones))},
        {"metric": "visual_split_subzones", "value": int(len(visual_grid))},
        {"metric": "visual_split_used_for_calculation", "value": 0},
        {"metric": "visual_split_method", "value": "two bounding-box halves per source full-SPb/NIR1 zone"},
    ]

    scenario_layers_created = 0
    for scenario in scenario_order(zone_stats):
        scenario_layers_created += 1
        scenario_zone = zone_stats[zone_stats["scenario"] == scenario].copy()
        scenario_summary = scenario_stats[scenario_stats["scenario"] == scenario].head(1)
        avg_allocated = float(scenario_summary["avg_allocated_distance_to_vehicle_km"].iloc[0]) if not scenario_summary.empty else 0.0
        relocated = int(scenario_summary["relocated_vehicles"].iloc[0]) if not scenario_summary.empty else 0

        gdf = zones.merge(scenario_zone, on="zone_id", how="left")
        gdf["scenario"] = gdf["scenario"].fillna(scenario)
        gdf["avg_allocated_distance_to_vehicle_km"] = avg_allocated
        gdf["relocated_vehicles"] = relocated
        gdf = _numeric(
            gdf,
            [
                "total_orders",
                "completed_orders",
                "lost_demand_no_vehicle",
                "lost_demand_no_vehicle_rate",
                "client_rejection_after_vehicle_found",
                "completion_rate",
                "avg_allocated_distance_to_vehicle_km",
                "relocated_vehicles",
            ],
        )

        scenario_max = float(gdf["lost_demand_no_vehicle"].max())
        label = SCENARIO_LABELS.get(scenario, scenario)
        layer = folium.FeatureGroup(name=label, show=(scenario == DEFAULT_SCENARIO))

        inactive = gdf[gdf["total_orders"] <= 0].copy()
        active = gdf[gdf["total_orders"] > 0].copy()
        if not inactive.empty:
            folium.GeoJson(
                inactive,
                name=f"{label}: зоны без модельного спроса",
                style_function=lambda feature: {
                    "fillColor": "#b7b7b7",
                    "color": "#a0a0a0",
                    "weight": 0.2,
                    "fillOpacity": 0.07,
                },
                tooltip=folium.GeoJsonTooltip(fields=["scenario", "zone_id"], aliases=["scenario:", "zone_id:"], sticky=True),
            ).add_to(layer)

        if not active.empty:
            folium.GeoJson(
                active,
                name=f"{label}: активные исходные зоны",
                style_function=lambda feature: {
                    "fillColor": "#ffffff",
                    "color": "#4b4b4b",
                    "weight": 0.35,
                    "fillOpacity": 0.012,
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=[
                        "scenario",
                        "zone_id",
                        "total_orders",
                        "completed_orders",
                        "lost_demand_no_vehicle",
                        "lost_demand_no_vehicle_rate",
                        "client_rejection_after_vehicle_found",
                        "completion_rate",
                        "avg_allocated_distance_to_vehicle_km",
                        "relocated_vehicles",
                    ],
                    aliases=[
                        "scenario:",
                        "zone_id:",
                        "total_orders:",
                        "completed_orders:",
                        "lost_demand_no_vehicle:",
                        "lost_demand_no_vehicle_rate:",
                        "client_rejection_after_vehicle_found:",
                        "completion_rate:",
                        "avg_allocated_distance_to_vehicle_km:",
                        "relocated_vehicles:",
                    ],
                    localize=True,
                    sticky=True,
                ),
            ).add_to(layer)

        heat_points = []
        filtered_heat = 0
        for _, row in active.iterrows():
            lost = float(row["lost_demand_no_vehicle"])
            if lost < MIN_HEAT_LOST_DEMAND:
                continue
            lat, lon, water = safe_display_point(row.geometry)
            if water:
                filtered_heat += 1
                continue
            heat_points.append([lat, lon, min(1.0, lost / global_scale)])

        if heat_points:
            HeatMap(
                heat_points,
                name=f"{label}: heatmap lost_demand_no_vehicle",
                radius=26 if scenario_max < MIN_SCENARIO_MAX_FOR_BLACK_MARKERS else 32,
                blur=34 if scenario_max < MIN_SCENARIO_MAX_FOR_BLACK_MARKERS else 38,
                min_opacity=0.035 if scenario_max < MIN_SCENARIO_MAX_FOR_BLACK_MARKERS else 0.06,
                max_zoom=13,
                gradient={0.2: "#fff5ae", 0.45: "#ffc94d", 0.72: "#f06d2f", 1.0: "#7f1d1d"},
            ).add_to(layer)

        top_markers = 0
        filtered_top = 0
        if scenario_max >= MIN_SCENARIO_MAX_FOR_BLACK_MARKERS:
            top = active[active["lost_demand_no_vehicle"] >= MIN_TOP_MARKER_LOST_DEMAND].sort_values(
                ["lost_demand_no_vehicle", "lost_demand_no_vehicle_rate", "total_orders"],
                ascending=False,
            ).head(10)
            for _, row in top.iterrows():
                lat, lon, water = safe_display_point(row.geometry)
                if water:
                    filtered_top += 1
                    continue
                top_markers += 1
                radius = 4 + 5 * min(1.0, float(row["lost_demand_no_vehicle"]) / global_max)
                folium.CircleMarker(
                    location=[lat, lon],
                    radius=radius,
                    color="black",
                    fill=True,
                    fill_color="black",
                    fill_opacity=0.84,
                    popup=(
                        f"<b>{label}</b><br>"
                        f"scenario: {scenario}<br>"
                        f"zone_id: {int(row['zone_id'])}<br>"
                        f"total_orders: {int(row['total_orders'])}<br>"
                        f"completed_orders: {int(row['completed_orders'])}<br>"
                        f"lost_demand_no_vehicle: {int(row['lost_demand_no_vehicle'])}<br>"
                        f"lost_demand_no_vehicle_rate: {float(row['lost_demand_no_vehicle_rate']):.3f}<br>"
                        f"client_rejection_after_vehicle_found: {int(row['client_rejection_after_vehicle_found'])}<br>"
                        f"completion_rate: {float(row['completion_rate']):.3f}<br>"
                        f"avg_allocated_distance_to_vehicle_km: {avg_allocated:.3f}<br>"
                        f"relocated_vehicles: {relocated}"
                    ),
                ).add_to(layer)
        else:
            filtered_top = int((active["lost_demand_no_vehicle"] > 0).sum())

        layer.add_to(m)
        diag_rows.extend(
            [
                {"metric": f"{scenario}.max_lost_demand_no_vehicle", "value": scenario_max},
                {"metric": f"{scenario}.heat_points_created", "value": len(heat_points)},
                {"metric": f"{scenario}.heat_points_filtered_water", "value": filtered_heat},
                {"metric": f"{scenario}.top_markers_created", "value": top_markers},
                {"metric": f"{scenario}.top_markers_filtered_or_suppressed", "value": filtered_top},
            ]
        )

    diag_rows.append({"metric": "scenario_layers_created", "value": scenario_layers_created})

    note_html = """
    <div style="position: fixed; bottom: 18px; left: 18px; z-index: 9999;
        width: 410px; padding: 10px 12px; background: rgba(255,255,255,0.94);
        border: 1px solid #888; font-size: 12px; line-height: 1.35;">
        <b>v12.1 final map</b><br>
        Сетка является модельной. Визуальная сетка делит исходные расчётные зоны
        на две равные части только для отображения; метрики остаются по full-SPb/НИР1 зонам.
        Зоны над водой не интерпретируются как реальные зоны спроса. Тепловые точки
        строятся только по активным зонам с потерянным спросом.
    </div>
    """
    m.get_root().html.add_child(folium.Element(note_html))
    folium.LayerControl(collapsed=False).add_to(m)

    out_path = OUT_DIR / "interactive_final_spb_soft_shortage_map_v2.html"
    m.save(out_path)

    diag_rows.extend(
        [
            {"metric": "output_exists.outputs/final_maps_v2/interactive_final_spb_soft_shortage_map_v2.html", "value": int(out_path.exists())},
            {"metric": "global_heat_scale_p98", "value": round(global_scale, 4)},
            {"metric": "global_lost_demand_max", "value": round(global_max, 4)},
        ]
    )
    pd.DataFrame(diag_rows).to_csv(DIAG_PATH, index=False, encoding="utf-8-sig")

    print(f"Saved final v2 map: {out_path}")
    print(f"Saved final v2 diagnostics: {DIAG_PATH}")
    print(f"Visual split subzones: {len(visual_grid)} from source zones: {len(zones)}")


if __name__ == "__main__":
    main()
