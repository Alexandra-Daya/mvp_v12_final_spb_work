from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _as_float(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    return float(value) if value not in {"", None} else 0.0


def _save_bar_chart(labels: list[str], values: list[float], title: str, ylabel: str, output_path: str | Path) -> Path:
    import matplotlib.pyplot as plt

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(10, 5))
    ax = fig.add_subplot(111)
    ax.bar(labels, values)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return output_path


def _save_line_chart(x: list[int], series: dict[str, list[float]], title: str, ylabel: str, output_path: str | Path) -> Path:
    import matplotlib.pyplot as plt

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(10, 5))
    ax = fig.add_subplot(111)
    for label, values in series.items():
        ax.plot(x, values, marker="o", label=label)
    ax.set_title(title)
    ax.set_xlabel("simulation step / hour")
    ax.set_ylabel(ylabel)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return output_path


def plot_scenario_completion_rates(scenario_comparison_csv: str | Path, output_path: str | Path) -> Path:
    rows = _read_csv(scenario_comparison_csv)
    labels = [r["scenario"] for r in rows]
    values = [_as_float(r, "completion_rate") for r in rows]
    return _save_bar_chart(labels, values, "Scenario comparison: completion rate", "completion rate", output_path)


def plot_scenario_no_vehicle_rates(scenario_comparison_csv: str | Path, output_path: str | Path) -> Path:
    rows = _read_csv(scenario_comparison_csv)
    labels = [r["scenario"] for r in rows]
    values = [_as_float(r, "no_vehicle_rate") for r in rows]
    return _save_bar_chart(labels, values, "Scenario comparison: no-vehicle cancellation rate", "no-vehicle rate", output_path)


def plot_scenario_revenue(scenario_comparison_csv: str | Path, output_path: str | Path) -> Path:
    rows = _read_csv(scenario_comparison_csv)
    labels = [r["scenario"] for r in rows]
    values = [_as_float(r, "revenue") for r in rows]
    return _save_bar_chart(labels, values, "Scenario comparison: conditional revenue", "revenue", output_path)


def plot_time_dynamics(time_snapshots_csv: str | Path, output_path: str | Path) -> Path:
    rows = _read_csv(time_snapshots_csv)
    x = [int(float(r["time_step"])) for r in rows]
    series = {
        "new_orders": [_as_float(r, "new_orders") for r in rows],
        "completed_orders": [_as_float(r, "completed_orders") for r in rows],
        "cancelled_no_vehicle": [_as_float(r, "cancelled_no_vehicle") for r in rows],
        "cancelled_by_client": [_as_float(r, "cancelled_by_client") for r in rows],
    }
    return _save_line_chart(x, series, "Baseline dynamics by simulation step", "count", output_path)


def plot_zone_shortage(zone_metrics_csv: str | Path, output_path: str | Path, title: str = "Zone shortage") -> Path:
    rows = _read_csv(zone_metrics_csv)
    labels = [r.get("zone_name", r.get("zone_id", "zone")) for r in rows]
    values = [_as_float(r, "cancelled_no_vehicle") for r in rows]
    return _save_bar_chart(labels, values, title, "cancelled orders due to no vehicle", output_path)


def generate_default_visualizations(outputs_dir: str | Path) -> list[Path]:
    outputs_dir = Path(outputs_dir)
    figures_dir = outputs_dir / "figures"
    generated: list[Path] = []

    scenario_csv = outputs_dir / "scenario_comparison.csv"
    if scenario_csv.exists():
        generated.append(plot_scenario_completion_rates(scenario_csv, figures_dir / "scenario_completion_rate.png"))
        generated.append(plot_scenario_no_vehicle_rates(scenario_csv, figures_dir / "scenario_no_vehicle_rate.png"))
        generated.append(plot_scenario_revenue(scenario_csv, figures_dir / "scenario_revenue.png"))

    baseline_time = outputs_dir / "baseline_time_snapshots.csv"
    if baseline_time.exists():
        generated.append(plot_time_dynamics(baseline_time, figures_dir / "baseline_time_dynamics.png"))

    shortage_zone = outputs_dir / "fleet_shortage_zone_metrics.csv"
    if shortage_zone.exists():
        generated.append(plot_zone_shortage(shortage_zone, figures_dir / "fleet_shortage_by_zone.png", "Fleet shortage scenario: shortage by zone"))

    return generated
