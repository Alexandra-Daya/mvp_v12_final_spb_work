from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from carsharing_sim.demand import ODDemandCell
from carsharing_sim.entities import Zone


class DataContractError(ValueError):
    """Raised when an input CSV does not match the MVP data contract."""


def load_zones_csv(path: str | Path) -> list[Zone]:
    """Load zones from a CSV file compatible with the MVP data contract.

    Required columns:
        zone_id, name, centroid_x, centroid_y,
        population_proxy, jobs_proxy, poi_count

    Optional column:
        zone_type

    This adapter is intended for future NIR1 data integration. The current MVP
    can run on synthetic data, but this function fixes the format expected from
    a processed NIR1 zones table.
    """

    path = Path(path)
    rows = _read_csv(path)
    required = {
        "zone_id",
        "name",
        "centroid_x",
        "centroid_y",
        "population_proxy",
        "jobs_proxy",
        "poi_count",
    }
    _ensure_columns(rows, required, path)

    zones: list[Zone] = []
    for row in rows:
        zones.append(
            Zone(
                zone_id=int(row["zone_id"]),
                name=row["name"],
                centroid_x=float(row["centroid_x"]),
                centroid_y=float(row["centroid_y"]),
                population_proxy=float(row["population_proxy"]),
                jobs_proxy=float(row["jobs_proxy"]),
                poi_count=int(float(row["poi_count"])),
                zone_type=row.get("zone_type", "mixed") or "mixed",
            )
        )
    return zones


def load_od_demand_csv(path: str | Path) -> list[ODDemandCell]:
    """Load OD demand cells from a CSV file compatible with the MVP data contract.

    Required columns:
        origin_zone_id, destination_zone_id, base_demand, distance_km

    This is the main adapter for processed NIR1 OD-pairs. The `base_demand`
    value is interpreted as expected demand intensity before scenario, time-of-day,
    weather and event multipliers are applied.
    """

    path = Path(path)
    rows = _read_csv(path)
    required = {"origin_zone_id", "destination_zone_id", "base_demand", "distance_km"}
    _ensure_columns(rows, required, path)

    cells: list[ODDemandCell] = []
    for row in rows:
        origin = int(row["origin_zone_id"])
        destination = int(row["destination_zone_id"])
        if origin == destination:
            continue
        cells.append(
            ODDemandCell(
                origin_zone_id=origin,
                destination_zone_id=destination,
                base_demand=max(0.0, float(row["base_demand"])),
                distance_km=max(0.0, float(row["distance_km"])),
            )
        )
    return cells


def save_sample_contract_files(output_dir: str | Path) -> tuple[Path, Path]:
    """Create tiny sample CSVs that document the expected NIR1 adapter format."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    zones_path = output_dir / "sample_zones_contract.csv"
    od_path = output_dir / "sample_od_demand_contract.csv"

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
        writer.writerow({
            "zone_id": 0,
            "name": "Zone 0",
            "centroid_x": 0.0,
            "centroid_y": 0.0,
            "population_proxy": 1000,
            "jobs_proxy": 500,
            "poi_count": 30,
            "zone_type": "mixed",
        })

    with od_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["origin_zone_id", "destination_zone_id", "base_demand", "distance_km"],
        )
        writer.writeheader()
        writer.writerow({
            "origin_zone_id": 0,
            "destination_zone_id": 1,
            "base_demand": 0.15,
            "distance_km": 4.2,
        })

    return zones_path, od_path


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        raise DataContractError(f"CSV file is empty: {path}")
    return rows


def _ensure_columns(rows: Iterable[dict[str, str]], required: set[str], path: Path) -> None:
    first = next(iter(rows), None)
    if first is None:
        raise DataContractError(f"CSV file is empty: {path}")
    actual = set(first.keys())
    missing = required - actual
    if missing:
        raise DataContractError(f"Missing required columns in {path}: {sorted(missing)}")
