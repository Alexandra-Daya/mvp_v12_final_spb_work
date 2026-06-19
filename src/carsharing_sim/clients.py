from __future__ import annotations

import random

from carsharing_sim.entities import (
    Client,
    ClientProfile,
    ClientProfileType,
    Order,
    SimulationContext,
    Zone,
)
from carsharing_sim.llm_agents import DecisionEngine


class ClientSimulator:
    """Client-side simulator: profiles, order creation and acceptance decisions."""

    def __init__(
        self,
        clients: list[Client],
        seed: int = 42,
        decision_engine: DecisionEngine | None = None,
        llm_agent_share: float = 0.0,
    ):
        self.clients = clients
        self.random = random.Random(seed)
        self._next_order_id = 0
        self.decision_engine = decision_engine
        self.llm_agent_share = min(1.0, max(0.0, llm_agent_share))

    def create_orders(
        self,
        requests: list[tuple[int, int, float]],
        context: SimulationContext,
    ) -> list[Order]:
        orders: list[Order] = []
        for origin_zone_id, destination_zone_id, distance_km in requests:
            client = self.random.choice(self.clients)
            order = Order(
                order_id=self._next_order_id,
                time_step=context.time_step,
                client_id=client.client_id,
                origin_zone_id=origin_zone_id,
                destination_zone_id=destination_zone_id,
                distance_km=distance_km,
            )
            self._next_order_id += 1
            orders.append(order)
        return orders

    def client_accepts_order(self, client_id: int, order: Order, context: SimulationContext) -> bool:
        client = self.clients[client_id % len(self.clients)]

        if self._uses_llm_agent(client.client_id):
            if self.decision_engine is None:
                raise ValueError("llm_agent_share > 0 requires a decision_engine")
            decision = self.decision_engine.decide(client=client, order=order, context=context)
            order.decision_source = decision.source
            order.decision_action = decision.action
            order.decision_explanation = decision.explanation
            return decision.accepted

        return self._rule_based_accepts_order(client=client, order=order, context=context)

    def _uses_llm_agent(self, client_id: int) -> bool:
        if self.decision_engine is None or self.llm_agent_share <= 0:
            return False
        # Deterministic selection of the LLM-agent subset for reproducibility.
        bucket = (client_id * 9973) % 10000 / 10000.0
        return bucket < self.llm_agent_share

    def _rule_based_accepts_order(self, client: Client, order: Order, context: SimulationContext) -> bool:
        profile = client.profile
        order.decision_source = "rule_based"

        if order.distance_to_vehicle_km is None:
            order.decision_action = "reject_distance"
            order.decision_explanation = "No available vehicle distance."
            return False

        # Hard rejection thresholds.
        if context.tariff_factor > profile.max_price_factor:
            order.decision_action = "reject_price"
            order.decision_explanation = "Tariff exceeds the profile threshold."
            return False
        if order.distance_to_vehicle_km > profile.max_distance_to_vehicle_km:
            order.decision_action = "reject_distance"
            order.decision_explanation = "Vehicle is too far for the profile threshold."
            return False

        # Soft probability: hurry and bad weather increase acceptance;
        # high tariff and long walk decrease it.
        probability = 0.72
        probability += 0.12 * profile.urgency
        probability += 0.08 * profile.weather_sensitivity * int(context.weather in {"rain", "snow"})
        probability -= 0.15 * max(0.0, context.tariff_factor - 1.0)
        probability -= 0.05 * order.distance_to_vehicle_km
        probability = min(0.98, max(0.05, probability))
        accepted = self.random.random() < probability
        order.decision_action = "accept" if accepted else "wait"
        order.decision_explanation = "Rule-based profile decision."
        return accepted


def build_synthetic_clients(zones: list[Zone], n_clients: int = 500, seed: int = 42) -> list[Client]:
    rnd = random.Random(seed)
    profiles = build_profiles()
    zone_ids = [z.zone_id for z in zones]
    weights = [max(1.0, z.population_proxy) for z in zones]

    clients: list[Client] = []
    for client_id in range(n_clients):
        home_zone_id = rnd.choices(zone_ids, weights=weights, k=1)[0]
        profile = rnd.choices(
            profiles,
            weights=[0.45, 0.18, 0.18, 0.12, 0.07],
            k=1,
        )[0]
        clients.append(Client(client_id=client_id, home_zone_id=home_zone_id, profile=profile))
    return clients


def build_profiles() -> list[ClientProfile]:
    return [
        ClientProfile(ClientProfileType.REGULAR, max_price_factor=1.4, max_distance_to_vehicle_km=2.5, urgency=0.4, weather_sensitivity=0.4),
        ClientProfile(ClientProfileType.ECONOMY, max_price_factor=1.1, max_distance_to_vehicle_km=2.0, urgency=0.2, weather_sensitivity=0.3),
        ClientProfile(ClientProfileType.HURRY, max_price_factor=1.8, max_distance_to_vehicle_km=3.5, urgency=1.0, weather_sensitivity=0.6),
        ClientProfile(ClientProfileType.PRICE_SENSITIVE, max_price_factor=1.05, max_distance_to_vehicle_km=2.5, urgency=0.3, weather_sensitivity=0.4),
        ClientProfile(ClientProfileType.DISTANCE_SENSITIVE, max_price_factor=1.4, max_distance_to_vehicle_km=1.0, urgency=0.5, weather_sensitivity=0.5),
    ]
