from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Iterable


class NIR1AdapterError(ValueError):
    """Raised when NIR1 exported CSV cannot be converted to MVP contracts."""


NIR1_COLUMN_ALIASES = {
    "origin": ["origin", "origin_zone_id", "i", "zone_i"],
    "destination": ["dest", "destination", "destination_zone_id", "j", "zone_j"],
    "distance": ["distance", "distance_km", "dist_km"],
    "population_origin": ["pop_i", "population_i", "origin_population", "population_origin"],
    "jobs_origin": ["jobs_i", "origin_jobs", "jobs_origin"],
    "population_destination": ["pop_j", "population_j", "destination_population", "population_destination"],
    "jobs_destination": ["jobs_j", "destination_jobs", "jobs_destination"],
    "demand": ["ml_flow", "real_flow", "gravity_scaled", "radiation_scaled", "gravity_flow", "radiation_flow", "base_demand", "demand"],
}


def convert_nir1_od_predictions_to_contract(
    input_csv: str | Path,
    output_dir: str | Path,
    demand_column: str | None = None,
    max_pairs: int = 600,
    target_total_base_demand: float = 45.0,
) -> tuple[Path, Path]:
    """Convert exported NIR1 OD table to MVP data contracts.

    Expected NIR1 artifact is usually `artifacts/od_pairs_with_predictions.csv`
    from the previous research notebook. The notebook uses columns like:
    `origin`, `dest`, `distance`, `pop_i`, `jobs_i`, `pop_j`, `jobs_j`,
    `gravity_scaled`, `radiation_scaled`, `ml_flow`, `real_flow`.

    The MVP simulator requires two simple CSV contracts:
    1. zones_contract.csv
    2. od_demand_contract.csv

    Important modeling note:
    NIR1 flows are transport-demand estimates, not real carsharing orders.
    Therefore this converter rescales the selected flow column to a convenient
    simulation intensity. The rescaling is explicit and should be described in
    the report as a modeling assumption.
    """

    input_csv = Path(input_csv)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = _read_rows(input_csv)
    column_map = _detect_columns(rows[0], demand_column=demand_column)

    raw_od = []
    zone_features: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for row in rows:
        origin = int(float(row[column_map["origin"]]))
        destination = int(float(row[column_map["destination"]]))
        if origin == destination:
            continue

        distance = _positive_float(row[column_map["distance"]], default=1.0)
        demand = _positive_float(row[column_map["demand"]], default=0.0)
        if demand <= 0:
            continue

        raw_od.append({
            "origin_zone_id": origin,
            "destination_zone_id": destination,
            "raw_demand": demand,
            "distance_km": distance,
        })

        _append_zone_feature(zone_features, origin, "population_proxy", row, column_map.get("population_origin"))
        _append_zone_feature(zone_features, origin, "jobs_proxy", row, column_map.get("jobs_origin"))
        _append_zone_feature(zone_features, destination, "population_proxy", row, column_map.get("population_destination"))
        _append_zone_feature(zone_features, destination, "jobs_proxy", row, column_map.get("jobs_destination"))

    if not raw_od:
        raise NIR1AdapterError("No positive OD demand rows were found in NIR1 CSV.")

    # Keep the strongest OD links to keep the MVP fast and readable.
    raw_od = sorted(raw_od, key=lambda r: r["raw_demand"], reverse=True)[:max_pairs]
    total_raw = sum(r["raw_demand"] for r in raw_od)
    scale = target_total_base_demand / total_raw if total_raw > 0 else 1.0

    zones_path = output_dir / "zones_from_nir1_contract.csv"
    od_path = output_dir / "od_demand_from_nir1_contract.csv"

    involved_zone_ids = sorted({r["origin_zone_id"] for r in raw_od} | {r["destination_zone_id"] for r in raw_od})
    coords = _grid_coordinates(involved_zone_ids)

    with zones_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "zone_id",
                "name",
                "centroid_x",
                "centroid_y",
                "population_proxy",
                "jobs_proxy",
                "poi_count",
                "zone_type",
            ],
        )
        writer.writeheader()
        for zone_id in involved_zone_ids:
            pop = _mean_or_default(zone_features[zone_id].get("population_proxy"), default=1.0)
            jobs = _mean_or_default(zone_features[zone_id].get("jobs_proxy"), default=1.0)
            x, y = coords[zone_id]
            writer.writerow({
                "zone_id": zone_id,
                "name": f"NIR1 zone {zone_id}",
                "centroid_x": round(x, 4),
                "centroid_y": round(y, 4),
                "population_proxy": round(pop, 4),
                "jobs_proxy": round(jobs, 4),
                "poi_count": max(1, int(round(jobs))),
                "zone_type": "mixed",
            })

    with od_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "origin_zone_id",
                "destination_zone_id",
                "base_demand",
                "distance_km",
                "source_flow",
            ],
        )
        writer.writeheader()
        for row in raw_od:
            writer.writerow({
                "origin_zone_id": row["origin_zone_id"],
                "destination_zone_id": row["destination_zone_id"],
                "base_demand": round(row["raw_demand"] * scale, 6),
                "distance_km": round(row["distance_km"], 4),
                "source_flow": round(row["raw_demand"], 6),
            })

    return zones_path, od_path


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise NIR1AdapterError(f"CSV file is empty: {path}")
    return rows


def _detect_columns(first_row: dict[str, str], demand_column: str | None = None) -> dict[str, str]:
    available = set(first_row.keys())
    result: dict[str, str] = {}

    for logical_name, aliases in NIR1_COLUMN_ALIASES.items():
        if logical_name == "demand" and demand_column:
            if demand_column not in available:
                raise NIR1AdapterError(f"Requested demand column not found: {demand_column}")
            result[logical_name] = demand_column
            continue
        match = next((name for name in aliases if name in available), None)
        if match:
            result[logical_name] = match

    required = {"origin", "destination", "distance", "demand"}
    missing = required - set(result)
    if missing:
        raise NIR1AdapterError(
            "Cannot detect required columns in NIR1 CSV. "
            f"Missing logical columns: {sorted(missing)}. "
            f"Available columns: {sorted(available)}"
        )
    return result


def _append_zone_feature(storage: dict[int, dict[str, list[float]]], zone_id: int, feature: str, row: dict[str, str], column: str | None) -> None:
    if not column:
        return
    value = _positive_float(row.get(column, ""), default=0.0)
    if value > 0:
        storage[zone_id][feature].append(value)


def _positive_float(value: str | float | int | None, default: float = 0.0) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if math.isnan(parsed) or math.isinf(parsed):
        return default
    return max(0.0, parsed)


def _mean_or_default(values: Iterable[float] | None, default: float) -> float:
    if not values:
        return default
    values = list(values)
    return sum(values) / len(values) if values else default


def _grid_coordinates(zone_ids: list[int]) -> dict[int, tuple[float, float]]:
    # The NIR1 OD table contains distances but not necessarily centroids after export.
    # These coordinates are only a fallback for MVP allocation distance calculations.
    n = len(zone_ids)
    width = max(1, int(math.ceil(math.sqrt(n))))
    coords: dict[int, tuple[float, float]] = {}
    for idx, zone_id in enumerate(zone_ids):
        coords[zone_id] = (float(idx % width), float(idx // width))
    return coords
