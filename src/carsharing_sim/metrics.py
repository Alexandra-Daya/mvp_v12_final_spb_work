from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from carsharing_sim.entities import Order, OrderStatus, Zone
from carsharing_sim.zone_metrics import build_zone_metrics


class MetricsCollector:
    """Collects order-level, time-step and zone-level metrics."""

    def __init__(self, zones: list[Zone] | None = None) -> None:
        self.zones = zones or []
        self.orders: list[Order] = []
        self.time_snapshots: list[dict[str, Any]] = []

    def record_orders(self, orders: list[Order]) -> None:
        self.orders.extend(orders)

    def record_time_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.time_snapshots.append(snapshot)

    def summary(self, scenario_name: str) -> dict[str, Any]:
        total = len(self.orders)
        completed = sum(o.status == OrderStatus.COMPLETED for o in self.orders)
        cancelled_no_vehicle = sum(o.status == OrderStatus.CANCELLED_NO_VEHICLE for o in self.orders)
        cancelled_by_client = sum(o.status == OrderStatus.CANCELLED_BY_CLIENT for o in self.orders)
        revenue = sum(o.price for o in self.orders if o.status == OrderStatus.COMPLETED)
        avg_wait = _safe_avg(o.wait_time for o in self.orders if o.status == OrderStatus.COMPLETED)
        avg_distance_to_vehicle = _safe_avg(
            o.distance_to_vehicle_km for o in self.orders
            if o.status == OrderStatus.COMPLETED and o.distance_to_vehicle_km is not None
        )
        avg_allocated_distance_to_vehicle = _safe_avg(
            o.distance_to_vehicle_km for o in self.orders
            if o.distance_to_vehicle_km is not None
        )
        avg_nonzero_distance_to_vehicle = _safe_avg(
            o.distance_to_vehicle_km for o in self.orders
            if o.distance_to_vehicle_km is not None and o.distance_to_vehicle_km > 0
        )
        avg_utilization = _safe_avg(s.get("utilization", 0.0) for s in self.time_snapshots)
        avg_free_vehicles = _safe_avg(s.get("free_vehicles", 0.0) for s in self.time_snapshots)
        total_relocated_vehicles = sum(int(s.get("relocated_vehicles", 0) or 0) for s in self.time_snapshots)
        max_zone_shortage = max(self.zone_shortage().values(), default=0)
        llm_orders = sum(str(o.decision_source).endswith("llm_agent") or o.decision_source == "ollama_llm_agent" for o in self.orders)
        llm_completed = sum((str(o.decision_source).endswith("llm_agent") or o.decision_source == "ollama_llm_agent") and o.status == OrderStatus.COMPLETED for o in self.orders)
        rule_based_orders = total - llm_orders

        return {
            "scenario": scenario_name,
            "total_orders": total,
            "completed_orders": completed,
            "cancelled_no_vehicle": cancelled_no_vehicle,
            "cancelled_by_client": cancelled_by_client,
            # Carsharing-specific aliases. In carsharing, a user usually sees the map
            # before booking, so this is better interpreted as unrealized/lost demand,
            # not as a taxi-like failed dispatch after a confirmed order.
            "lost_demand_no_vehicle": cancelled_no_vehicle,
            "client_rejection_after_vehicle_found": cancelled_by_client,
            "completion_rate": round(completed / total, 4) if total else 0.0,
            "cancellation_rate": round((cancelled_no_vehicle + cancelled_by_client) / total, 4) if total else 0.0,
            "no_vehicle_rate": round(cancelled_no_vehicle / total, 4) if total else 0.0,
            "client_rejection_rate": round(cancelled_by_client / total, 4) if total else 0.0,
            "lost_demand_no_vehicle_rate": round(cancelled_no_vehicle / total, 4) if total else 0.0,
            "revenue": round(revenue, 2),
            "avg_wait_time": round(avg_wait, 3),
            "avg_distance_to_vehicle_km": round(avg_distance_to_vehicle, 3),
            "avg_allocated_distance_to_vehicle_km": round(avg_allocated_distance_to_vehicle, 3),
            "avg_nonzero_distance_to_vehicle_km": round(avg_nonzero_distance_to_vehicle, 3),
            "avg_fleet_utilization": round(avg_utilization, 4),
            "avg_free_vehicles": round(avg_free_vehicles, 3),
            "max_zone_shortage": max_zone_shortage,
            "total_relocated_vehicles": total_relocated_vehicles,
            "relocated_vehicles": total_relocated_vehicles,
            "llm_agent_orders": llm_orders,
            "rule_based_orders": rule_based_orders,
            "llm_agent_acceptance_rate": round(llm_completed / llm_orders, 4) if llm_orders else 0.0,
        }

    def zone_shortage(self) -> dict[int, int]:
        shortage = Counter()
        for order in self.orders:
            if order.status == OrderStatus.CANCELLED_NO_VEHICLE:
                shortage[order.origin_zone_id] += 1
        return dict(shortage)

    def orders_by_hour(self) -> dict[int, dict[str, int]]:
        result: dict[int, dict[str, int]] = defaultdict(lambda: {"total": 0, "completed": 0, "cancelled": 0})
        for order in self.orders:
            hour = order.time_step % 24
            result[hour]["total"] += 1
            if order.status == OrderStatus.COMPLETED:
                result[hour]["completed"] += 1
            elif order.status in {OrderStatus.CANCELLED_NO_VEHICLE, OrderStatus.CANCELLED_BY_CLIENT}:
                result[hour]["cancelled"] += 1
        return dict(result)

    def save_orders_csv(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "order_id",
                    "time_step",
                    "client_id",
                    "origin_zone_id",
                    "destination_zone_id",
                    "distance_km",
                    "status",
                    "assigned_vehicle_id",
                    "price",
                    "wait_time",
                    "distance_to_vehicle_km",
                    "cancellation_reason",
                    "decision_source",
                    "decision_action",
                    "decision_explanation",
                ],
            )
            writer.writeheader()
            for o in self.orders:
                writer.writerow({
                    "order_id": o.order_id,
                    "time_step": o.time_step,
                    "client_id": o.client_id,
                    "origin_zone_id": o.origin_zone_id,
                    "destination_zone_id": o.destination_zone_id,
                    "distance_km": o.distance_km,
                    "status": o.status.value,
                    "assigned_vehicle_id": o.assigned_vehicle_id,
                    "price": o.price,
                    "wait_time": o.wait_time,
                    "distance_to_vehicle_km": o.distance_to_vehicle_km,
                    "cancellation_reason": o.cancellation_reason,
                    "decision_source": o.decision_source,
                    "decision_action": o.decision_action,
                    "decision_explanation": o.decision_explanation,
                })

    def save_zone_metrics_csv(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = build_zone_metrics(self.zones, self.orders)
        with path.open("w", newline="", encoding="utf-8") as f:
            fieldnames = list(asdict(rows[0]).keys()) if rows else [
                "zone_id",
                "zone_name",
                "total_orders",
                "completed_orders",
                "cancelled_no_vehicle",
                "cancelled_by_client",
                "completion_rate",
                "shortage_rate",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(asdict(row))

    def save_time_snapshots_csv(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not self.time_snapshots:
            return
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.time_snapshots[0].keys()))
            writer.writeheader()
            writer.writerows(self.time_snapshots)

    @staticmethod
    def save_summary_csv(rows: list[dict[str, Any]], path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            return
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)


def _safe_avg(values) -> float:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else 0.0
