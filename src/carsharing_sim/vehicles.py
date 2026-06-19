from __future__ import annotations

import random

from carsharing_sim.entities import Trip, Vehicle, VehicleStatus, Zone


class VehicleSimulator:
    """Vehicle-side simulator: fleet state and time synchronization."""

    def __init__(self, vehicles: list[Vehicle]):
        self.vehicles = vehicles
        self.completed_trips: list[Trip] = []
        self._active_trips: list[Trip] = []

    def release_finished_trips(self, time_step: int) -> None:
        still_active: list[Trip] = []
        for trip in self._active_trips:
            if trip.end_time <= time_step:
                vehicle = self.vehicles[trip.vehicle_id]
                vehicle.current_zone_id = trip.destination_zone_id
                vehicle.status = VehicleStatus.FREE
                vehicle.available_from = time_step
                vehicle.next_zone_id = None
                vehicle.fuel_or_charge = max(0.05, vehicle.fuel_or_charge - 0.01 * trip.distance_km)
                self.completed_trips.append(trip)
            else:
                still_active.append(trip)
        self._active_trips = still_active

    def start_trip(self, trip: Trip) -> None:
        vehicle = self.vehicles[trip.vehicle_id]
        vehicle.status = VehicleStatus.BUSY
        vehicle.available_from = trip.end_time
        vehicle.next_zone_id = trip.destination_zone_id
        self._active_trips.append(trip)

    def get_free_vehicles(self, time_step: int) -> list[Vehicle]:
        return [
            v for v in self.vehicles
            if v.status == VehicleStatus.FREE and v.available_from <= time_step
        ]

    def fleet_snapshot(self, time_step: int) -> dict[str, int | float]:
        free = len(self.get_free_vehicles(time_step))
        busy = sum(v.status == VehicleStatus.BUSY for v in self.vehicles)
        unavailable = sum(v.status == VehicleStatus.UNAVAILABLE for v in self.vehicles)
        return {
            "fleet_size": len(self.vehicles),
            "free_vehicles": free,
            "busy_vehicles": busy,
            "unavailable_vehicles": unavailable,
            "utilization": round(busy / len(self.vehicles), 4) if self.vehicles else 0.0,
        }


    def free_vehicle_counts_by_zone(self, time_step: int) -> dict[int, int]:
        counts: dict[int, int] = {}
        for vehicle in self.get_free_vehicles(time_step):
            counts[vehicle.current_zone_id] = counts.get(vehicle.current_zone_id, 0) + 1
        return counts

    def relocate_free_vehicles(
        self,
        target_zone_ids: list[int],
        max_relocations: int,
        time_step: int,
    ) -> int:
        """Move free vehicles from surplus zones to requested target zones.

        This is an MVP operational heuristic. It relocates cars instantly at the
        end of a simulation step so that the next step sees a better spatial
        distribution. A zone is considered a donor only if it has at least two
        free cars, so the rule avoids fully emptying any donor zone.
        """
        if max_relocations <= 0 or not target_zone_ids:
            return 0

        moved = 0
        target_index = 0

        while moved < max_relocations and target_index < len(target_zone_ids):
            counts = self.free_vehicle_counts_by_zone(time_step)
            donor_candidates = [
                (zone_id, count) for zone_id, count in counts.items()
                if count >= 2 and zone_id != target_zone_ids[target_index]
            ]
            if not donor_candidates:
                break

            donor_zone_id = max(donor_candidates, key=lambda item: item[1])[0]
            vehicle_to_move = next(
                v for v in self.get_free_vehicles(time_step)
                if v.current_zone_id == donor_zone_id
            )
            vehicle_to_move.current_zone_id = target_zone_ids[target_index]
            vehicle_to_move.available_from = time_step + 1
            moved += 1
            target_index = (target_index + 1) % len(target_zone_ids)

        return moved


def build_synthetic_fleet(zones: list[Zone], n_vehicles: int = 80, seed: int = 42) -> list[Vehicle]:
    rnd = random.Random(seed)
    zone_ids = [z.zone_id for z in zones]
    # Place more cars where activity is higher.
    weights = [max(1.0, z.population_proxy * 0.4 + z.jobs_proxy * 0.6 + z.poi_count * 10) for z in zones]
    vehicles: list[Vehicle] = []
    for vehicle_id in range(n_vehicles):
        zone_id = rnd.choices(zone_ids, weights=weights, k=1)[0]
        vehicles.append(
            Vehicle(
                vehicle_id=vehicle_id,
                current_zone_id=zone_id,
                fuel_or_charge=round(rnd.uniform(0.45, 1.0), 2),
                car_type="standard",
            )
        )
    return vehicles
