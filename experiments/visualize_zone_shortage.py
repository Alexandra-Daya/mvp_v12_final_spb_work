"""Build zone-level shortage/completion visualizations for carsharing digital twin outputs.

The script expects CSV files in outputs/ produced by run_contract_scenarios.py.
It creates ranked tables and bar charts for shortage zones.

Usage:
    python experiments/visualize_zone_shortage.py
    python experiments/visualize_zone_shortage.py --outputs-dir outputs --min-orders 3
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd


def _load_existing(outputs_dir: Path, candidates: Iterable[str]) -> Optional[pd.DataFrame]:
    for name in candidates:
        path = outputs_dir / name
        if path.exists():
            df = pd.read_csv(path)
            df["source_file"] = name
            return df
    return None


def load_zone_metrics(outputs_dir: Path) -> Dict[str, pd.DataFrame]:
    mapping = {
        "baseline": [
            "contract_baseline_zone_metrics.csv",
            "contract_run_zone_metrics.csv",
            "baseline_zone_metrics.csv",
        ],
        "high_demand": [
            "contract_high_demand_zone_metrics.csv",
            "high_demand_zone_metrics.csv",
        ],
        "fleet_shortage_clean": [
            "contract_fleet_shortage_clean_zone_metrics.csv",
            "contract_fleet_shortage_clean_30pct_agents_zone_metrics.csv",
            "fleet_shortage_clean_zone_metrics.csv",
            # legacy file name from older MVP versions; use only if clean file is absent
            "contract_fleet_shortage_zone_metrics.csv",
        ],
        "system_stress": [
            "contract_system_stress_zone_metrics.csv",
            "system_stress_zone_metrics.csv",
        ],
    }

    loaded: Dict[str, pd.DataFrame] = {}
    missing = []
    for scenario, names in mapping.items():
        df = _load_existing(outputs_dir, names)
        if df is None:
            missing.append((scenario, names))
            continue
        required = {
            "zone_id",
            "zone_name",
            "total_orders",
            "completed_orders",
            "cancelled_no_vehicle",
            "cancelled_by_client",
            "completion_rate",
            "shortage_rate",
        }
        absent = required.difference(df.columns)
        if absent:
            raise ValueError(
                f"File for scenario {scenario!r} is missing columns: {sorted(absent)}"
            )
        df = df.copy()
        df["scenario"] = scenario
        loaded[scenario] = df

    if missing:
        print("Warning: some scenario zone_metrics files were not found:")
        for scenario, names in missing:
            print(f"  - {scenario}: tried {', '.join(names)}")
    if not loaded:
        raise FileNotFoundError(f"No zone_metrics CSV files found in {outputs_dir}")
    return loaded


def save_top_tables(loaded: Dict[str, pd.DataFrame], out_dir: Path, min_orders: int) -> pd.DataFrame:
    rows = []
    for scenario, df in loaded.items():
        filtered = df[df["total_orders"] >= min_orders].copy()
        filtered = filtered.sort_values(
            ["shortage_rate", "cancelled_no_vehicle", "total_orders"],
            ascending=[False, False, False],
        )
        filtered["rank_in_scenario"] = range(1, len(filtered) + 1)
        rows.append(filtered)
        filtered.head(20).to_csv(
            out_dir / f"top_shortage_zones_{scenario}.csv", index=False, encoding="utf-8-sig"
        )

    combined = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    combined.to_csv(
        out_dir / "zone_shortage_comparison_all_scenarios.csv",
        index=False,
        encoding="utf-8-sig",
    )
    return combined


def save_bar_chart(df: pd.DataFrame, out_path: Path, title: str, top_n: int) -> None:
    import matplotlib.pyplot as plt

    if df.empty:
        return
    plot_df = df.head(top_n).copy()
    labels = plot_df["zone_name"].astype(str) + " (" + plot_df["zone_id"].astype(str) + ")"
    values = plot_df["shortage_rate"] * 100

    height = max(5, 0.35 * len(plot_df) + 1.5)
    plt.figure(figsize=(10, height))
    plt.barh(labels[::-1], values[::-1])
    plt.xlabel("Shortage rate, %")
    plt.ylabel("Zone")
    plt.title(title)
    plt.xlim(0, 100)
    plt.tight_layout()
    plt.savefig(out_path, dpi=180)
    plt.close()


def save_completion_chart(loaded: Dict[str, pd.DataFrame], out_path: Path, min_orders: int, top_n: int) -> None:
    import matplotlib.pyplot as plt

    if "fleet_shortage_clean" not in loaded and "system_stress" not in loaded:
        return

    stress_source = loaded.get("system_stress", loaded.get("fleet_shortage_clean"))
    top_zones = (
        stress_source[stress_source["total_orders"] >= min_orders]
        .sort_values(["shortage_rate", "cancelled_no_vehicle"], ascending=[False, False])
        .head(top_n)["zone_id"]
        .tolist()
    )
    if not top_zones:
        return

    rows = []
    for scenario, df in loaded.items():
        selected = df[df["zone_id"].isin(top_zones)].copy()
        selected = selected[["zone_id", "zone_name", "completion_rate"]]
        selected["scenario"] = scenario
        rows.append(selected)
    comp = pd.concat(rows, ignore_index=True)
    pivot = comp.pivot_table(
        index=["zone_id", "zone_name"], columns="scenario", values="completion_rate", aggfunc="first"
    ).fillna(0)
    # Keep the order from top_zones
    pivot = pivot.reindex(top_zones, level=0)
    pivot.to_csv(out_path.with_suffix(".csv"), encoding="utf-8-sig")

    labels = [f"{name} ({zone})" for zone, name in pivot.index]
    scenarios = [c for c in ["baseline", "high_demand", "fleet_shortage_clean", "system_stress"] if c in pivot.columns]

    y_positions = range(len(labels))
    width = 0.8 / max(len(scenarios), 1)

    plt.figure(figsize=(11, max(5, 0.4 * len(labels) + 1.5)))
    for i, scenario in enumerate(scenarios):
        offsets = [y + (i - (len(scenarios) - 1) / 2) * width for y in y_positions]
        plt.barh(offsets, pivot[scenario].values * 100, height=width, label=scenario)
    plt.yticks(list(y_positions), labels)
    plt.xlabel("Completion rate, %")
    plt.ylabel("Zone")
    plt.title("Completion rate in top shortage zones")
    plt.xlim(0, 100)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=180)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outputs-dir", default="outputs")
    parser.add_argument("--figures-dir", default="outputs/figures")
    parser.add_argument("--min-orders", type=int, default=3)
    parser.add_argument("--top-n", type=int, default=15)
    args = parser.parse_args()

    outputs_dir = Path(args.outputs_dir)
    figures_dir = Path(args.figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)

    loaded = load_zone_metrics(outputs_dir)
    combined = save_top_tables(loaded, figures_dir, args.min_orders)

    for scenario, df in loaded.items():
        filtered = df[df["total_orders"] >= args.min_orders].sort_values(
            ["shortage_rate", "cancelled_no_vehicle", "total_orders"],
            ascending=[False, False, False],
        )
        save_bar_chart(
            filtered,
            figures_dir / f"zone_shortage_top_{args.top_n}_{scenario}.png",
            f"Top shortage zones: {scenario}",
            args.top_n,
        )

    save_completion_chart(
        loaded,
        figures_dir / "completion_rate_in_top_shortage_zones.png",
        args.min_orders,
        min(args.top_n, 10),
    )

    print("Zone visualization complete.")
    print(f"Loaded scenarios: {', '.join(loaded.keys())}")
    print(f"Saved tables and figures to: {figures_dir}")
    if not combined.empty:
        print("Top shortage zones by scenario:")
        preview = combined[combined["rank_in_scenario"] <= 5][
            [
                "scenario",
                "rank_in_scenario",
                "zone_id",
                "zone_name",
                "total_orders",
                "cancelled_no_vehicle",
                "shortage_rate",
                "completion_rate",
            ]
        ]
        print(preview.to_string(index=False))


if __name__ == "__main__":
    main()
