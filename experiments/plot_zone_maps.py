from pathlib import Path

import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt


BASE_DIR = Path(__file__).resolve().parents[1]

ZONES_PATH = BASE_DIR / "data" / "raw" / "nir1" / "zones.geojson"
STATS_PATH = BASE_DIR / "outputs" / "figures" / "zone_shortage_comparison_all_scenarios.csv"

OUT_DIR = BASE_DIR / "outputs" / "zone_maps"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def prepare_zone_ids(df, col="zone_id"):
    df = df.copy()
    df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=[col]).copy()
    df[col] = df[col].astype(int)
    return df


def main():
    if not ZONES_PATH.exists():
        raise FileNotFoundError(f"Не найден файл зон: {ZONES_PATH}")

    if not STATS_PATH.exists():
        raise FileNotFoundError(f"Не найден файл метрик: {STATS_PATH}")

    # --- 1. Загружаем зоны
    zones = gpd.read_file(ZONES_PATH)

    if "zone_id" not in zones.columns:
        zones["zone_id"] = zones.index.astype(int)

    zones = prepare_zone_ids(zones, "zone_id")

    if zones.crs is None:
        # если CRS вдруг потерян, для geojson обычно это WGS84
        zones = zones.set_crs("EPSG:4326")

    # --- 2. Загружаем таблицу по дефициту зон
    stats = pd.read_csv(STATS_PATH)
    stats = prepare_zone_ids(stats, "zone_id")

    required_cols = ["scenario", "zone_id", "shortage_rate", "total_orders", "cancelled_no_vehicle"]
    missing = [c for c in required_cols if c not in stats.columns]
    if missing:
        raise ValueError(f"В CSV не хватает колонок: {missing}")

    if "zone_name" not in stats.columns:
        stats["zone_name"] = "NIR1 zone " + stats["zone_id"].astype(str)

    # --- 3. Проецируем для красивого построения и корректных центроидов
    plot_crs = zones.estimate_utm_crs()
    zones_plot = zones.to_crs(plot_crs)

    # центроиды зон -> потом пригодятся для проверки на карте
    centroids = zones_plot.copy()
    centroids["geometry"] = centroids.geometry.centroid
    centroids = centroids.to_crs("EPSG:4326")
    centroids["centroid_lon"] = centroids.geometry.x
    centroids["centroid_lat"] = centroids.geometry.y
    centroids = centroids[["zone_id", "centroid_lat", "centroid_lon"]]

    # --- 4. Соединяем геометрию с метриками
    merged = zones_plot.merge(stats, on="zone_id", how="inner")
    merged = merged.merge(centroids, on="zone_id", how="left")

    # --- 5. Сохраняем полную таблицу с координатами центров зон
    merged_for_csv = merged.drop(columns="geometry").copy()
    merged_for_csv.to_csv(OUT_DIR / "zone_metrics_with_centroids.csv", index=False, encoding="utf-8-sig")

    # --- 6. Топ-зоны по каждому сценарию
    top_zones = (
        merged.sort_values(
            ["scenario", "shortage_rate", "cancelled_no_vehicle", "total_orders"],
            ascending=[True, False, False, False]
        )
        .groupby("scenario")
        .head(10)
        .drop(columns="geometry")
    )
    top_zones.to_csv(OUT_DIR / "top_10_shortage_zones_with_coords.csv", index=False, encoding="utf-8-sig")

    # --- 7. Карты по сценариям
    scenarios = list(stats["scenario"].dropna().unique())

    for scenario in scenarios:
        scenario_gdf = merged[merged["scenario"] == scenario].copy()
        if scenario_gdf.empty:
            continue

        fig, ax = plt.subplots(figsize=(10, 10))

        # фон: все зоны контуром
        zones_plot.boundary.plot(ax=ax, color="lightgray", linewidth=0.4)

        # заливка по shortage_rate
        scenario_gdf.plot(
            column="shortage_rate",
            ax=ax,
            cmap="Reds",
            linewidth=0.35,
            edgecolor="black",
            legend=True,
            legend_kwds={"label": "Shortage rate", "shrink": 0.7},
            missing_kwds={"color": "whitesmoke"}
        )

        # подпишем топ-5 самых проблемных зон
        top5 = scenario_gdf.sort_values(
            ["shortage_rate", "cancelled_no_vehicle", "total_orders"],
            ascending=False
        ).head(5)

        for _, row in top5.iterrows():
            c = row.geometry.centroid
            label = (
                f"ID {int(row['zone_id'])}\n"
                f"SR={row['shortage_rate']:.2f}\n"
                f"ord={int(row['total_orders'])}"
            )
            ax.scatter(c.x, c.y, s=18)
            ax.text(c.x, c.y, label, fontsize=8)

        ax.set_title(f"Дефицит по зонам: {scenario}", fontsize=14)
        ax.set_axis_off()
        plt.tight_layout()

        out_path = OUT_DIR / f"map_{scenario}.png"
        plt.savefig(out_path, dpi=220, bbox_inches="tight")
        plt.close(fig)

    # --- 8. Повторяемость дефицита между сценариями
    recurrent = (
        stats.assign(shortage_flag=(stats["shortage_rate"] > 0).astype(int))
        .groupby("zone_id", as_index=False)["shortage_flag"]
        .sum()
        .rename(columns={"shortage_flag": "scenarios_with_shortage"})
    )

    recurrent_map = zones_plot.merge(recurrent, on="zone_id", how="left")
    recurrent_map["scenarios_with_shortage"] = recurrent_map["scenarios_with_shortage"].fillna(0)

    fig, ax = plt.subplots(figsize=(10, 10))
    zones_plot.boundary.plot(ax=ax, color="lightgray", linewidth=0.4)
    recurrent_map.plot(
        column="scenarios_with_shortage",
        ax=ax,
        cmap="Blues",
        linewidth=0.35,
        edgecolor="black",
        legend=True,
        legend_kwds={"label": "Число сценариев с дефицитом", "shrink": 0.7},
    )
    ax.set_title("Повторяемость дефицита по зонам", fontsize=14)
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(OUT_DIR / "map_recurrent_shortage.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    print("Готово.")
    print(f"Карты сохранены в: {OUT_DIR}")
    print("Созданы файлы:")
    print("- zone_metrics_with_centroids.csv")
    print("- top_10_shortage_zones_with_coords.csv")
    print("- map_baseline.png / map_high_demand.png / map_fleet_shortage_clean.png / map_system_stress.png")
    print("- map_recurrent_shortage.png")


if __name__ == "__main__":
    main()