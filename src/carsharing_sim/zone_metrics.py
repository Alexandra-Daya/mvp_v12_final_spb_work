from __future__ import annotations

from dataclasses import dataclass

from carsharing_sim.entities import Order, OrderStatus, Zone


@dataclass(frozen=True)
class ZoneMetricRow:
    zone_id: int
    zone_name: str
    total_orders: int
    completed_orders: int
    cancelled_no_vehicle: int
    cancelled_by_client: int
    lost_demand_no_vehicle: int
    client_rejection_after_vehicle_found: int
    completion_rate: float
    shortage_rate: float


def build_zone_metrics(zones: list[Zone], orders: list[Order]) -> list[ZoneMetricRow]:
    """Aggregate order outcomes by origin zone."""

    zone_by_id = {z.zone_id: z for z in zones}
    rows: list[ZoneMetricRow] = []
    for zone in zones:
        zone_orders = [o for o in orders if o.origin_zone_id == zone.zone_id]
        total = len(zone_orders)
        completed = sum(o.status == OrderStatus.COMPLETED for o in zone_orders)
        no_vehicle = sum(o.status == OrderStatus.CANCELLED_NO_VEHICLE for o in zone_orders)
        by_client = sum(o.status == OrderStatus.CANCELLED_BY_CLIENT for o in zone_orders)
        rows.append(
            ZoneMetricRow(
                zone_id=zone.zone_id,
                zone_name=zone_by_id[zone.zone_id].name,
                total_orders=total,
                completed_orders=completed,
                cancelled_no_vehicle=no_vehicle,
                cancelled_by_client=by_client,
                lost_demand_no_vehicle=no_vehicle,
                client_rejection_after_vehicle_found=by_client,
                completion_rate=round(completed / total, 4) if total else 0.0,
                shortage_rate=round(no_vehicle / total, 4) if total else 0.0,
            )
        )
    return rows
