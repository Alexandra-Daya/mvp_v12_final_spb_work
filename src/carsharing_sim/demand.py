from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterable

from carsharing_sim.entities import SimulationContext, Zone


@dataclass(frozen=True)
class ODDemandCell:
    origin_zone_id: int
    destination_zone_id: int
    base_demand: float
    distance_km: float


class DemandGenerator:
    """Generates potential trip demand by OD cells and current context."""

    def __init__(self, od_demand: list[ODDemandCell], seed: int = 42):
        self.od_demand = od_demand
        self.random = random.Random(seed)

    def generate_order_requests(self, context: SimulationContext) -> list[tuple[int, int, float]]:
        """Return tuples: (origin_zone_id, destination_zone_id, distance_km)."""
        requests: list[tuple[int, int, float]] = []
        hour_factor = self._hour_factor(context.hour_of_day)

        for cell in self.od_demand:
            expected = cell.base_demand * hour_factor * context.total_demand_factor
            count = self._sample_count(expected)
            requests.extend(
                (cell.origin_zone_id, cell.destination_zone_id, cell.distance_km)
                for _ in range(count)
            )

        self.random.shuffle(requests)
        return requests

    def _sample_count(self, expected: float) -> int:
        """Simple deterministic+stochastic count approximation.

        We avoid numpy in v0.1. Integer part is guaranteed; fractional part is
        sampled as Bernoulli. For MVP this is enough and reproducible.
        """
        integer_part = int(math.floor(expected))
        fractional = expected - integer_part
        return integer_part + int(self.random.random() < fractional)

    @staticmethod
    def _hour_factor(hour: int) -> float:
        if 7 <= hour <= 10:
            return 1.5
        if 17 <= hour <= 20:
            return 1.8
        if 11 <= hour <= 16:
            return 1.0
        if 21 <= hour <= 23:
            return 0.8
        return 0.35


def build_synthetic_zones() -> list[Zone]:
    """Synthetic zones. Later this function should be replaced by NIR1 data."""
    return [
        Zone(0, "Residential North", 0.0, 1.0, 1200, 300, 25, "residential"),
        Zone(1, "Business Center", 1.0, 1.0, 500, 1800, 120, "business"),
        Zone(2, "University Area", 0.0, 0.0, 900, 900, 90, "mixed"),
        Zone(3, "Transport Hub", 1.0, 0.0, 600, 1400, 110, "transport"),
        Zone(4, "Residential South", 2.0, 0.0, 1500, 350, 30, "residential"),
        Zone(5, "Leisure District", 2.0, 1.0, 700, 1000, 140, "leisure"),
    ]


def build_synthetic_od_demand(zones: Iterable[Zone]) -> list[ODDemandCell]:
    """Build synthetic OD demand from population/jobs/distance proxies.

    This mirrors the logic of NIR1 at a minimal level: origin generation is
    related to population proxy, destination attraction is related to jobs/POI,
    and distance reduces interaction.
    """
    zones_list = list(zones)
    cells: list[ODDemandCell] = []

    for origin in zones_list:
        for destination in zones_list:
            if origin.zone_id == destination.zone_id:
                continue
            distance = euclidean_distance_km(origin, destination)
            attraction = destination.jobs_proxy + 8 * destination.poi_count
            generation = origin.population_proxy
            base = (generation * attraction) / ((distance + 1.0) ** 2)
            # Scale to a convenient MVP range.
            base_demand = max(0.02, base / 180_000)
            cells.append(
                ODDemandCell(
                    origin_zone_id=origin.zone_id,
                    destination_zone_id=destination.zone_id,
                    base_demand=base_demand,
                    distance_km=distance,
                )
            )
    return cells


def euclidean_distance_km(a: Zone, b: Zone) -> float:
    return round(math.sqrt((a.centroid_x - b.centroid_x) ** 2 + (a.centroid_y - b.centroid_y) ** 2) * 4.0, 2)
