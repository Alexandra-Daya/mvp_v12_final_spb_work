"""Build the clean final v12.2/v3 SPb carsharing shortage map.

This map intentionally returns to the stable full-SPb/NIR1 calculation grid.
The v11 refined grid and v12.1 visual split-grid are kept as experimental
artifacts, but are not used as the main map layers here.
"""
from __future__ import annotations

from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd
from folium.plugins import HeatMap

ROOT = Path(__file__).resolve().parents[1]
ZONES_PATH = ROOT / "data" / "raw" / "nir1" / "zones.geojson"
FINAL_ZONE_METRICS_PATH = ROOT / "outputs" / "final_zone_metrics.csv"
FINAL_SCENARIO_COMPARISON_PATH = ROOT / "outputs" / "final_scenario_comparison.csv"
OUT_DIR = ROOT / "outputs" / "final_maps_v3"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DIAG_DIR = ROOT / "outputs" / "final_diagnostics"
DIAG_DIR.mkdir(parents=True, exist_ok=True)
DIAG_PATH = DIAG_DIR / "final_map_v3_diagnostics.csv"

DEFAULT_SCENARIO = "fleet_shortage_clean"
MIN_HEAT_LOST_DEMAND = 1.0
MIN_TOP_MARKER_LOST_DEMAND = 5.0
BASELINE_TOP_MARKERS_ENABLED = False

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


def is_obvious_water_marker(lat: float, lon: float) -> bool:
    """Soft heuristic for black top markers only; this is not a land mask."""
    if lon < 29.75:
        return True
    if lon < 29.95 and lat > 60.02:
        return True
    if lon < 30.10 and lat > 60.17:
        return True
    return False


def display_point(geom) -> tuple[float, float]:
    point = geom.representative_point()
    return float(point.y), float(point.x)


def _numeric(gdf: gpd.GeoDataFrame, columns: list[str]) -> gpd.GeoDataFrame:
    for col in columns:
        gdf[col] = pd.to_numeric(gdf[col], errors="coerce").fillna(0)
    return gdf


def main() -> None:
    zones = read_stable_zones()
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
            "fillColor": "#d9d9d9",
            "color": "#8d8d8d",
            "weight": 0.28,
            "fillOpacity": 0.018,
        },
        tooltip=folium.GeoJsonTooltip(fields=["zone_id"], aliases=["zone_id:"], sticky=True),
    ).add_to(m)

    diag_rows: list[dict[str, object]] = [
        {"metric": "main_final_map", "value": "outputs/final_maps_v3/interactive_final_spb_clean_map_v3.html"},
        {"metric": "source_full_spb_zones", "value": int(len(zones))},
        {"metric": "refined_grid_used_as_main_final_map", "value": 0},
        {"metric": "split_grid_used_as_main_final_map", "value": 0},
        {"metric": "heat_filter_applied_to_heatmap", "value": 0},
        {"metric": "top_marker_water_filter", "value": "soft heuristic for obvious water markers only"},
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
                    "fillColor": "#bdbdbd",
                    "color": "#aaaaaa",
                    "weight": 0.18,
                    "fillOpacity": 0.045,
                },
                tooltip=folium.GeoJsonTooltip(fields=["scenario", "zone_id"], aliases=["scenario:", "zone_id:"], sticky=True),
            ).add_to(layer)

        if not active.empty:
            folium.GeoJson(
                active,
                name=f"{label}: активные зоны",
                style_function=lambda feature: {
                    "fillColor": "#ffffff",
                    "color": "#5f5f5f",
                    "weight": 0.26,
                    "fillOpacity": 0.008,
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
        for _, row in active.iterrows():
            lost = float(row["lost_demand_no_vehicle"])
            if lost < MIN_HEAT_LOST_DEMAND:
                continue
            lat, lon = display_point(row.geometry)
            heat_points.append([lat, lon, min(1.0, lost / global_scale)])

        if heat_points:
            low_intensity = scenario_max < MIN_TOP_MARKER_LOST_DEMAND
            HeatMap(
                heat_points,
                name=f"{label}: heatmap lost_demand_no_vehicle",
                radius=30 if low_intensity else 34,
                blur=38 if low_intensity else 42,
                min_opacity=0.055 if low_intensity else 0.07,
                max_zoom=13,
                gradient={0.18: "#fff4b0", 0.42: "#ffc857", 0.72: "#ee6c2f", 1.0: "#7c1f1f"},
            ).add_to(layer)

        top_markers = 0
        filtered_top = 0
        top_candidates = active[active["lost_demand_no_vehicle"] >= MIN_TOP_MARKER_LOST_DEMAND].sort_values(
            ["lost_demand_no_vehicle", "lost_demand_no_vehicle_rate", "total_orders"],
            ascending=False,
        ).head(10)

        if scenario == "baseline" and not BASELINE_TOP_MARKERS_ENABLED:
            filtered_top += int(len(top_candidates))
        else:
            for _, row in top_candidates.iterrows():
                lat, lon = display_point(row.geometry)
                if is_obvious_water_marker(lat, lon):
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
        diag_rows.extend(
            [
                {"metric": f"{scenario}.max_lost_demand_no_vehicle", "value": scenario_max},
                {"metric": f"{scenario}.heat_points_created", "value": len(heat_points)},
                {"metric": f"{scenario}.top_markers_created", "value": top_markers},
                {"metric": f"{scenario}.top_markers_hidden_water_or_low_demand", "value": filtered_top},
            ]
        )

    diag_rows.append({"metric": "scenario_layers_created", "value": scenario_layers_created})

    note_html = """
    <div style="position: fixed; bottom: 18px; left: 18px; z-index: 9999;
        width: 430px; padding: 10px 12px; background: rgba(255,255,255,0.94);
        border: 1px solid #888; font-size: 12px; line-height: 1.35;">
        <b>Финальная карта v12.2 / v3</b><br>
        Основной слой: стабильная расчётная сетка full-SPb / НИР1. Зоны являются
        модельными, а не административными районами. Зоны, частично попадающие
        на воду, не интерпретируются как реальные районы спроса. Тепловой слой
        показывает потерянный спрос из-за отсутствия доступной машины.
    </div>
    """
    m.get_root().html.add_child(folium.Element(note_html))
    folium.LayerControl(collapsed=False).add_to(m)

    out_path = OUT_DIR / "interactive_final_spb_clean_map_v3.html"
    m.save(out_path)

    diag_rows.extend(
        [
            {"metric": "output_exists.outputs/final_maps_v3/interactive_final_spb_clean_map_v3.html", "value": int(out_path.exists())},
            {"metric": "global_heat_scale_p98", "value": round(global_scale, 4)},
            {"metric": "global_lost_demand_max", "value": round(global_max, 4)},
        ]
    )
    pd.DataFrame(diag_rows).to_csv(DIAG_PATH, index=False, encoding="utf-8-sig")

    print(f"Saved clean final v3 map: {out_path}")
    print(f"Saved final v3 diagnostics: {DIAG_PATH}")


if __name__ == "__main__":
    main()
