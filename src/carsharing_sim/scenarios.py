from __future__ import annotations

from carsharing_sim.context import ScenarioSettings


def baseline() -> ScenarioSettings:
    return ScenarioSettings(name="baseline")


def high_demand() -> ScenarioSettings:
    return ScenarioSettings(name="high_demand", demand_multiplier=1.45)


def bad_weather() -> ScenarioSettings:
    return ScenarioSettings(name="bad_weather", bad_weather=True, demand_multiplier=1.10)


def fleet_shortage_clean() -> ScenarioSettings:
    """Pure fleet shortage: baseline demand, fewer cars and smaller search radius.

    This scenario changes only the supply side. It is useful for a clean
    interpretation: with the same demand as baseline, what happens if the fleet
    is not sufficient or poorly accessible?
    """

    return ScenarioSettings(
        name="fleet_shortage_clean",
        demand_multiplier=1.0,
        fleet_size_multiplier=0.10,
        max_vehicle_search_distance_km=2.5,
    )


def system_stress() -> ScenarioSettings:
    """Combined stress scenario: more demand and fewer cars.

    This preserves the original v0.5 fleet_shortage behavior, but gives it a
    clearer interpretation: this is not a pure shortage test, but a joint stress
    of demand growth and limited fleet supply.
    """

    return ScenarioSettings(
        name="system_stress",
        demand_multiplier=1.60,
        fleet_size_multiplier=0.10,
        max_vehicle_search_distance_km=2.5,
    )


def fleet_shortage() -> ScenarioSettings:
    """Backward-compatible alias for the original v0.5 shortage stress scenario.

    Kept to avoid breaking previous commands and validation scripts. For final
    interpretation prefer using `fleet_shortage_clean` and `system_stress`.
    """

    return ScenarioSettings(
        name="fleet_shortage",
        demand_multiplier=1.60,
        fleet_size_multiplier=0.10,
        max_vehicle_search_distance_km=2.5,
    )


def simple_relocation() -> ScenarioSettings:
    """Baseline demand with a simple operational relocation policy.

    At the end of each time step, the simulator can move a limited number of
    idle cars from zones with surplus free vehicles to zones where orders were
    cancelled because no car was available. This is a deliberately simple MVP
    policy, not an optimized relocation algorithm.
    """

    return ScenarioSettings(
        name="simple_relocation",
        demand_multiplier=1.0,
        fleet_size_multiplier=1.0,
        max_vehicle_search_distance_km=10.0,
        relocation_enabled=True,
        relocation_fraction=0.35,
        relocation_max_vehicles_per_step=10,
        relocation_min_shortage_orders=1,
    )


def relocation_stress() -> ScenarioSettings:
    """High-demand scenario with the same simple relocation policy.

    Useful for checking whether a naive repositioning rule still helps under
    higher pressure. It is a heuristic scenario, not an operations-optimized
    control policy.
    """

    return ScenarioSettings(
        name="relocation_stress",
        demand_multiplier=1.45,
        fleet_size_multiplier=1.0,
        max_vehicle_search_distance_km=10.0,
        relocation_enabled=True,
        relocation_fraction=0.35,
        relocation_max_vehicles_per_step=10,
        relocation_min_shortage_orders=1,
    )


def high_tariff() -> ScenarioSettings:
    return ScenarioSettings(name="high_tariff", tariff_factor=1.35)


def city_event() -> ScenarioSettings:
    return ScenarioSettings(
        name="city_event",
        demand_multiplier=1.10,
        event_factor=1.10,
        city_event_hours=(18, 19, 20, 21),
    )


def winter_macro_stress() -> ScenarioSettings:
    return ScenarioSettings(
        name="winter_macro_stress",
        season="winter",
        bad_weather=True,
        tariff_factor=1.2,
        traffic_multiplier=1.15,
        macro_factor=0.9,
        fleet_size_multiplier=0.75,
        max_vehicle_search_distance_km=6.0,
    )


def llm_agent_experiment() -> ScenarioSettings:
    """Scenario for comparing rule-based clients with an LLM-agent decision layer."""
    return ScenarioSettings(
        name="llm_agent_experiment",
        demand_multiplier=1.20,
        tariff_factor=1.15,
        bad_weather=True,
        max_vehicle_search_distance_km=5.0,
    )


def all_scenarios() -> list[ScenarioSettings]:
    return [
        baseline(),
        high_demand(),
        bad_weather(),
        fleet_shortage_clean(),
        system_stress(),
        simple_relocation(),
        relocation_stress(),
        fleet_shortage(),
        high_tariff(),
        city_event(),
        winter_macro_stress(),
        llm_agent_experiment(),
    ]
