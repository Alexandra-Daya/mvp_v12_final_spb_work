from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from carsharing_sim.entities import Vehicle, Zone


@dataclass(frozen=True)
class AllocationResult:
    vehicle: Optional[Vehicle]
    distance_to_vehicle_km: Optional[float]


class BasicAllocator:
    """Assigns an available vehicle to an order origin zone.

    MVP policy:
    1. Prefer vehicles in the same zone.
    2. Otherwise choose the nearest available vehicle by zone centroid distance.
    """

    def __init__(self, zones: list[Zone], max_search_distance_km: float = 10.0):
        self.zones_by_id = {z.zone_id: z for z in zones}
        self.max_search_distance_km = max_search_distance_km

    def allocate(self, origin_zone_id: int, free_vehicles: list[Vehicle]) -> AllocationResult:
        if not free_vehicles:
            return AllocationResult(vehicle=None, distance_to_vehicle_km=None)

        origin = self.zones_by_id[origin_zone_id]
        best_vehicle: Optional[Vehicle] = None
        best_distance = float("inf")

        for vehicle in free_vehicles:
            vehicle_zone = self.zones_by_id[vehicle.current_zone_id]
            distance = self._distance_km(origin, vehicle_zone)
            if distance < best_distance:
                best_distance = distance
                best_vehicle = vehicle

        if best_vehicle is None or best_distance > self.max_search_distance_km:
            return AllocationResult(vehicle=None, distance_to_vehicle_km=None)

        return AllocationResult(vehicle=best_vehicle, distance_to_vehicle_km=round(best_distance, 2))

    @staticmethod
    def _distance_km(a: Zone, b: Zone) -> float:
        return math.sqrt((a.centroid_x - b.centroid_x) ** 2 + (a.centroid_y - b.centroid_y) ** 2) * 4.0
