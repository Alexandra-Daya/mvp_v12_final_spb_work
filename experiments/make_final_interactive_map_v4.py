"""Build the v12.3/v4 final SPb carsharing map.

The main map returns to the visually successful full-SPb/NIR1 grid and soft
heatmap approach. The optional split-grid is horizontal-only and visual-only:
it does not change OD demand, scenario results or zone metrics.
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
OUT_DIR = ROOT / "outputs" / "final_maps_v4"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DIAG_DIR = ROOT / "outputs" / "final_diagnostics"
DIAG_DIR.mkdir(parents=True, exist_ok=True)
DIAG_PATH = DIAG_DIR / "final_map_v4_diagnostics.csv"

DEFAULT_SCENARIO = "fleet_shortage_clean"
MIN_HEAT_LOST_DEMAND = 1.0
BIG_TOP_MARKER_THRESHOLD = 10.0
SMALL_MARKER_THRESHOLD = 1.0

SCENARIO_LABELS = {
    "baseline": "Baseline: потерянный спрос",
    "high_demand": "High demand: рост спроса",
    "fleet_shortage_clean": "Fleet shortage: нехватка парка",
    "system_stress": "System stress: высокий спрос + нехватка парка",
    "simple_relocation": "Simple relocation: простая перебалансировка",
    "relocation_stress": "Relocation stress: стресс + перебалансировка",
}

LOW_INTENSITY = {"baseline", "high_demand"}
MEDIUM_INTENSITY = {"simple_relocation", "relocation_stress"}


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


def build_horizontal_visual_split_grid(zones: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Split every zone bounding box into lower and upper visual halves."""
    rows: list[dict[str, object]] = []
    for _, row in zones.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        minx, miny, maxx, maxy = geom.bounds
        ymid = (miny + maxy) / 2.0
        zone_id = int(row["zone_id"])
        parts = [
            ("lower", box(minx, miny, maxx, ymid)),
            ("upper", box(minx, ymid, maxx, maxy)),
        ]
        for suffix, part in parts:
            rows.append(
                {
                    "parent_zone_id": zone_id,
                    "visual_subzone_id": f"{zone_id}_{suffix}",
                    "is_visual_only": 1,
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


def display_point(geom) -> tuple[float, float]:
    point = geom.representative_point()
    return float(point.y), float(point.x)


def is_obvious_water_marker(lat: float, lon: float) -> bool:
    """Soft heuristic for top markers only; this is not a land mask."""
    if lon < 29.75:
        return True
    if lon < 29.95 and lat > 60.04:
        return True
    if lon < 30.08 and lat > 60.19:
        return True
    return False


def heat_style_for_scenario(scenario: str) -> dict[str, float | int]:
    if scenario in LOW_INTENSITY:
        return {"radius": 34, "blur": 42, "min_opacity": 0.14}
    if scenario in MEDIUM_INTENSITY:
        return {"radius": 32, "blur": 40, "min_opacity": 0.10}
    return {"radius": 34, "blur": 42, "min_opacity": 0.08}


def _numeric(gdf: gpd.GeoDataFrame, columns: list[str]) -> gpd.GeoDataFrame:
    for col in columns:
        gdf[col] = pd.to_numeric(gdf[col], errors="coerce").fillna(0)
    return gdf


def main() -> None:
    zones = read_stable_zones()
    horizontal_split = build_horizontal_visual_split_grid(zones)
    zone_stats = add_aliases(pd.read_csv(FINAL_ZONE_METRICS_PATH))
    scenario_stats = add_aliases(pd.read_csv(FINAL_SCENARIO_COMPARISON_PATH))
    zone_stats["zone_id"] = pd.to_numeric(zone_stats["zone_id"], errors="coerce").astype("Int64")
    zone_stats = zone_stats.dropna(subset=["zone_id"]).copy()
    zone_stats["zone_id"] = zone_stats["zone_id"].astype(int)

    center = zones.geometry.union_all().centroid
    m = folium.Map(location=[center.y, center.x], zoom_start=10, tiles=None, control_scale=True)
    folium.TileLayer("CartoDB positron", name="Подложка: CartoDB Positron", control=True).add_to(m)
    folium.TileLayer("OpenStreetMap", name="Подложка: OpenStreetMap", control=True).add_to(m)

    folium.GeoJson(
        zones[["zone_id", "geometry"]],
        name="Расчётная сетка full-SPb / НИР1",
        show=True,
        style_function=lambda feature: {
            "fillColor": "#dcdcdc",
            "color": "#888888",
            "weight": 0.32,
            "fillOpacity": 0.02,
        },
        tooltip=folium.GeoJsonTooltip(fields=["zone_id"], aliases=["zone_id:"], sticky=True),
    ).add_to(m)

    folium.GeoJson(
        horizontal_split[["visual_subzone_id", "parent_zone_id", "is_visual_only", "geometry"]],
        name="Визуальная сетка: горизонтальное деление зон на 2 части",
        show=False,
        style_function=lambda feature: {
            "fillColor": "#ffffff",
            "color": "#555555",
            "weight": 0.18,
            "fillOpacity": 0.0,
            "dashArray": "2,4",
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["visual_subzone_id", "parent_zone_id", "is_visual_only"],
            aliases=["visual_subzone_id:", "parent_zone_id:", "visual only, not recalculated:"],
            sticky=True,
        ),
    ).add_to(m)

    diag_rows: list[dict[str, object]] = [
        {"metric": "main_final_map", "value": "outputs/final_maps_v4/interactive_final_spb_map_v4.html"},
        {"metric": "source_full_spb_zones", "value": int(len(zones))},
        {"metric": "refined_grid_used_as_main_final_map", "value": 0},
        {"metric": "vertical_split_grid_used", "value": 0},
        {"metric": "horizontal_visual_split_grid_available", "value": 1},
        {"metric": "horizontal_visual_split_subzones", "value": int(len(horizontal_split))},
        {"metric": "horizontal_visual_split_grid_used_as_calculation", "value": 0},
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

        label = SCENARIO_LABELS.get(scenario, scenario)
        layer = folium.FeatureGroup(name=label, show=(scenario == DEFAULT_SCENARIO))
        inactive = gdf[gdf["total_orders"] <= 0].copy()
        active = gdf[gdf["total_orders"] > 0].copy()

        if not inactive.empty:
            folium.GeoJson(
                inactive,
                name=f"{label}: зоны без модельного спроса",
                style_function=lambda feature: {
                    "fillColor": "#bfbfbf",
                    "color": "#aaaaaa",
                    "weight": 0.18,
                    "fillOpacity": 0.04,
                },
                tooltip=folium.GeoJsonTooltip(fields=["scenario", "zone_id"], aliases=["scenario:", "zone_id:"], sticky=True),
            ).add_to(layer)

        if not active.empty:
            folium.GeoJson(
                active,
                name=f"{label}: активные зоны",
                style_function=lambda feature: {
                    "fillColor": "#ffffff",
                    "color": "#666666",
                    "weight": 0.22,
                    "fillOpacity": 0.006,
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

        scenario_positive = active[active["lost_demand_no_vehicle"] >= MIN_HEAT_LOST_DEMAND].copy()
        scenario_scale = max(float(scenario_positive["lost_demand_no_vehicle"].max()), 1.0) if not scenario_positive.empty else 1.0
        heat_points = []
        for _, row in scenario_positive.iterrows():
            lat, lon = display_point(row.geometry)
            weight = min(1.0, float(row["lost_demand_no_vehicle"]) / scenario_scale)
            heat_points.append([lat, lon, weight])

        if heat_points:
            style = heat_style_for_scenario(scenario)
            HeatMap(
                heat_points,
                name=f"{label}: heatmap lost_demand_no_vehicle",
                radius=int(style["radius"]),
                blur=int(style["blur"]),
                min_opacity=float(style["min_opacity"]),
                max_zoom=13,
                gradient={0.18: "#fff6b8", 0.42: "#ffd15c", 0.72: "#ef7a35", 1.0: "#842121"},
            ).add_to(layer)

        top_markers = 0
        hidden_top = 0
        if scenario in LOW_INTENSITY:
            candidates = active[active["lost_demand_no_vehicle"] >= SMALL_MARKER_THRESHOLD].sort_values(
                ["lost_demand_no_vehicle", "lost_demand_no_vehicle_rate", "total_orders"],
                ascending=False,
            ).head(8)
            for _, row in candidates.iterrows():
                lat, lon = display_point(row.geometry)
                if is_obvious_water_marker(lat, lon):
                    hidden_top += 1
                    continue
                top_markers += 1
                folium.CircleMarker(
                    location=[lat, lon],
                    radius=3.0,
                    color="#555555",
                    fill=True,
                    fill_color="#777777",
                    fill_opacity=0.55,
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
            candidates = active[active["lost_demand_no_vehicle"] >= BIG_TOP_MARKER_THRESHOLD].sort_values(
                ["lost_demand_no_vehicle", "lost_demand_no_vehicle_rate", "total_orders"],
                ascending=False,
            ).head(10)
            for _, row in candidates.iterrows():
                lat, lon = display_point(row.geometry)
                if is_obvious_water_marker(lat, lon):
                    hidden_top += 1
                    continue
                top_markers += 1
                radius = 4 + 5 * min(1.0, float(row["lost_demand_no_vehicle"]) / max(float(zone_stats["lost_demand_no_vehicle"].max()), 1.0))
                folium.CircleMarker(
                    location=[lat, lon],
                    radius=radius,
                    color="black",
                    fill=True,
                    fill_color="black",
                    fill_opacity=0.82,
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

        layer.add_to(m)
        total_lost = float(active["lost_demand_no_vehicle"].sum())
        max_lost = float(active["lost_demand_no_vehicle"].max()) if not active.empty else 0.0
        diag_rows.extend(
            [
                {"scenario": scenario, "metric": "total_lost_demand_no_vehicle", "value": int(total_lost)},
                {"scenario": scenario, "metric": "max_zone_lost_demand_no_vehicle", "value": max_lost},
                {"scenario": scenario, "metric": "heat_points_count", "value": len(heat_points)},
                {"scenario": scenario, "metric": "top_markers_count", "value": top_markers},
                {"scenario": scenario, "metric": "hidden_top_markers_count", "value": hidden_top},
                {"scenario": scenario, "metric": "heatmap_visible_expected", "value": int(total_lost > 0)},
                {"scenario": scenario, "metric": "map_layer_created", "value": 1},
            ]
        )

    diag_rows.append({"metric": "scenario_layers_created", "value": scenario_layers_created})

    note_html = """
    <div style="position: fixed; bottom: 18px; left: 18px; z-index: 9999;
        width: 450px; padding: 10px 12px; background: rgba(255,255,255,0.94);
        border: 1px solid #888; font-size: 12px; line-height: 1.35;">
        <b>Финальная карта v12.3 / v4</b><br>
        Основной слой: стабильная расчётная сетка full-SPb / НИР1. Зоны являются
        модельными, а не административными районами. Слой горизонтального деления
        зон — только визуальный и не меняет расчёты. Тепловой слой показывает
        потерянный спрос из-за отсутствия доступной машины. Внутри каждого сценария
        цвет показывает относительную концентрацию; абсолютные значения смотреть в CSV.
    </div>
    """
    m.get_root().html.add_child(folium.Element(note_html))
    folium.LayerControl(collapsed=False).add_to(m)

    out_path = OUT_DIR / "interactive_final_spb_map_v4.html"
    m.save(out_path)
    diag_rows.append({"metric": "output_exists.outputs/final_maps_v4/interactive_final_spb_map_v4.html", "value": int(out_path.exists())})
    pd.DataFrame(diag_rows).to_csv(DIAG_PATH, index=False, encoding="utf-8-sig")

    print(f"Saved final v4 map: {out_path}")
    print(f"Saved final v4 diagnostics: {DIAG_PATH}")


if __name__ == "__main__":
    main()
