from __future__ import annotations

from dataclasses import dataclass

from carsharing_sim.entities import SimulationContext


@dataclass(frozen=True)
class ScenarioSettings:
    """Scenario-level parameters.

    These parameters implement the requirement that the market model must allow
    changes in circumstances: time of day, season, macroeconomic state, events,
    weather, traffic and tariffs. Some parameters also control technical stress
    tests such as fleet shortage.
    """

    name: str
    season: str = "spring"
    demand_multiplier: float = 1.0
    tariff_factor: float = 1.0
    traffic_multiplier: float = 1.0
    macro_factor: float = 1.0
    event_factor: float = 1.0
    bad_weather: bool = False
    city_event_hours: tuple[int, ...] = ()
    fleet_size_multiplier: float = 1.0
    max_vehicle_search_distance_km: float = 10.0
    relocation_enabled: bool = False
    relocation_fraction: float = 0.0
    relocation_max_vehicles_per_step: int = 0
    relocation_min_shortage_orders: int = 1


class ContextEngine:
    """Creates changing circumstances for every simulation time step.

    This module addresses the requirement: the market model must allow changes
    in circumstances such as time of day, season, macroeconomic conditions,
    traffic, weather, tariffs, and events.
    """

    def __init__(self, settings: ScenarioSettings):
        self.settings = settings

    def get_context(self, time_step: int) -> SimulationContext:
        hour = time_step % 24
        notes: list[str] = []

        weather = self._weather_for_hour(hour)
        traffic_factor = self._traffic_factor_for_hour(hour) * self.settings.traffic_multiplier
        event_factor = self.settings.event_factor

        if hour in self.settings.city_event_hours:
            event_factor *= 1.35
            notes.append("city_event")

        return SimulationContext(
            time_step=time_step,
            hour_of_day=hour,
            season=self.settings.season,
            weather=weather,
            traffic_factor=traffic_factor,
            tariff_factor=self.settings.tariff_factor,
            macro_factor=self.settings.macro_factor,
            event_factor=event_factor,
            demand_multiplier=self.settings.demand_multiplier,
            notes=notes,
        )

    def _weather_for_hour(self, hour: int) -> str:
        if not self.settings.bad_weather:
            return "clear"
        if self.settings.season == "winter":
            return "snow"
        if 7 <= hour <= 22:
            return "rain"
        return "clear"

    @staticmethod
    def _traffic_factor_for_hour(hour: int) -> float:
        if 7 <= hour <= 10:
            return 1.35
        if 17 <= hour <= 20:
            return 1.45
        if 23 <= hour or hour <= 5:
            return 0.75
        return 1.0
