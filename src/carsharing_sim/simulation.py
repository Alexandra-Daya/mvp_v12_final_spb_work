from __future__ import annotations

import math

from carsharing_sim.allocation import BasicAllocator
from carsharing_sim.clients import ClientSimulator
from carsharing_sim.context import ContextEngine, ScenarioSettings
from carsharing_sim.demand import DemandGenerator
from collections import Counter

from carsharing_sim.entities import Order, OrderStatus, Trip, Zone
from carsharing_sim.metrics import MetricsCollector
from carsharing_sim.vehicles import VehicleSimulator


class SimulationEngine:
    """Synchronizes client and vehicle simulators over time.

    At every time step:
    1. update circumstances;
    2. release vehicles from finished trips;
    3. generate client order requests;
    4. allocate vehicles;
    5. process client acceptance;
    6. start trips and update vehicle state;
    7. record metrics.
    """

    def __init__(
        self,
        scenario: ScenarioSettings,
        zones: list[Zone],
        demand_generator: DemandGenerator,
        client_simulator: ClientSimulator,
        vehicle_simulator: VehicleSimulator,
        allocator: BasicAllocator,
        simulation_steps: int = 24,
    ) -> None:
        self.scenario = scenario
        self.zones = zones
        self.context_engine = ContextEngine(scenario)
        self.demand_generator = demand_generator
        self.client_simulator = client_simulator
        self.vehicle_simulator = vehicle_simulator
        self.allocator = allocator
        self.simulation_steps = simulation_steps
        self.metrics = MetricsCollector(zones=zones)
        self._next_trip_id = 0

    def run(self) -> MetricsCollector:
        for time_step in range(self.simulation_steps):
            context = self.context_engine.get_context(time_step)
            self.vehicle_simulator.release_finished_trips(time_step)

            requests = self.demand_generator.generate_order_requests(context)
            orders = self.client_simulator.create_orders(requests, context)

            processed_orders: list[Order] = []
            for order in orders:
                self._process_order(order, context)
                processed_orders.append(order)

            self.metrics.record_orders(processed_orders)

            relocated_vehicles = self._relocate_after_shortage(processed_orders, time_step)

            snapshot = self.vehicle_simulator.fleet_snapshot(time_step)
            snapshot.update({
                "time_step": time_step,
                "hour_of_day": context.hour_of_day,
                "weather": context.weather,
                "tariff_factor": context.tariff_factor,
                "traffic_factor": context.traffic_factor,
                "orders_created": len(orders),
                "relocated_vehicles": relocated_vehicles,
                "scenario": self.scenario.name,
            })
            self.metrics.record_time_snapshot(snapshot)

        # Release trips that finish immediately after the final step for consistency.
        self.vehicle_simulator.release_finished_trips(self.simulation_steps + 10)
        return self.metrics

    def _relocate_after_shortage(self, processed_orders: list[Order], time_step: int) -> int:
        if not self.scenario.relocation_enabled:
            return 0

        shortage_counts = Counter(
            order.origin_zone_id
            for order in processed_orders
            if order.status == OrderStatus.CANCELLED_NO_VEHICLE
        )
        if not shortage_counts:
            return 0

        target_zones = [
            zone_id for zone_id, count in shortage_counts.most_common()
            if count >= self.scenario.relocation_min_shortage_orders
        ]
        if not target_zones:
            return 0

        free_count = len(self.vehicle_simulator.get_free_vehicles(time_step))
        max_by_fraction = int(max(1, round(free_count * self.scenario.relocation_fraction)))
        max_relocations = min(self.scenario.relocation_max_vehicles_per_step, max_by_fraction)
        return self.vehicle_simulator.relocate_free_vehicles(
            target_zone_ids=target_zones,
            max_relocations=max_relocations,
            time_step=time_step,
        )

    def _process_order(self, order: Order, context) -> None:
        free_vehicles = self.vehicle_simulator.get_free_vehicles(context.time_step)
        allocation = self.allocator.allocate(order.origin_zone_id, free_vehicles)

        if allocation.vehicle is None:
            order.status = OrderStatus.CANCELLED_NO_VEHICLE
            order.cancellation_reason = "no_available_vehicle"
            return

        order.assigned_vehicle_id = allocation.vehicle.vehicle_id
        order.distance_to_vehicle_km = allocation.distance_to_vehicle_km
        order.wait_time = self._estimate_wait_time(order.distance_to_vehicle_km, context.traffic_factor)
        order.price = self._estimate_price(order.distance_km, context.tariff_factor)

        accepted = self.client_simulator.client_accepts_order(
            client_id=order.client_id,
            order=order,
            context=context,
        )

        if not accepted:
            order.status = OrderStatus.CANCELLED_BY_CLIENT
            order.cancellation_reason = "client_rejected_conditions"
            return

        order.status = OrderStatus.COMPLETED
        duration_steps = self._estimate_duration_steps(order.distance_km, context.traffic_factor)
        trip = Trip(
            trip_id=self._next_trip_id,
            order_id=order.order_id,
            vehicle_id=allocation.vehicle.vehicle_id,
            start_time=context.time_step,
            end_time=context.time_step + duration_steps,
            origin_zone_id=order.origin_zone_id,
            destination_zone_id=order.destination_zone_id,
            distance_km=order.distance_km,
            price=order.price,
        )
        self._next_trip_id += 1
        self.vehicle_simulator.start_trip(trip)

    @staticmethod
    def _estimate_wait_time(distance_to_vehicle_km: float | None, traffic_factor: float) -> float:
        if distance_to_vehicle_km is None:
            return 0.0
        return round(3.0 + distance_to_vehicle_km * 4.0 * traffic_factor, 2)

    @staticmethod
    def _estimate_price(distance_km: float, tariff_factor: float) -> float:
        base_fee = 80.0
        price_per_km = 28.0
        return round((base_fee + price_per_km * distance_km) * tariff_factor, 2)

    @staticmethod
    def _estimate_duration_steps(distance_km: float, traffic_factor: float) -> int:
        # One simulation step is one hour. Most trips finish within 1 step;
        # long trips under traffic may take 2 steps.
        approximate_minutes = distance_km / 22.0 * 60.0 * traffic_factor
        return max(1, int(math.ceil(approximate_minutes / 60.0)))
