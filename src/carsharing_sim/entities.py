from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class VehicleStatus(str, Enum):
    FREE = "free"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"


class OrderStatus(str, Enum):
    CREATED = "created"
    COMPLETED = "completed"
    CANCELLED_NO_VEHICLE = "cancelled_no_vehicle"
    CANCELLED_BY_CLIENT = "cancelled_by_client"


class ClientProfileType(str, Enum):
    REGULAR = "regular"
    ECONOMY = "economy"
    HURRY = "hurry"
    PRICE_SENSITIVE = "price_sensitive"
    DISTANCE_SENSITIVE = "distance_sensitive"


@dataclass(frozen=True)
class Zone:
    zone_id: int
    name: str
    centroid_x: float
    centroid_y: float
    population_proxy: float
    jobs_proxy: float
    poi_count: int
    zone_type: str = "mixed"


@dataclass(frozen=True)
class ClientProfile:
    profile_type: ClientProfileType
    max_price_factor: float
    max_distance_to_vehicle_km: float
    urgency: float
    weather_sensitivity: float


@dataclass
class Client:
    client_id: int
    home_zone_id: int
    profile: ClientProfile


@dataclass
class Vehicle:
    vehicle_id: int
    current_zone_id: int
    status: VehicleStatus = VehicleStatus.FREE
    fuel_or_charge: float = 1.0
    car_type: str = "standard"
    available_from: int = 0
    next_zone_id: Optional[int] = None


@dataclass
class Order:
    order_id: int
    time_step: int
    client_id: int
    origin_zone_id: int
    destination_zone_id: int
    distance_km: float
    status: OrderStatus = OrderStatus.CREATED
    assigned_vehicle_id: Optional[int] = None
    price: float = 0.0
    wait_time: float = 0.0
    distance_to_vehicle_km: Optional[float] = None
    cancellation_reason: Optional[str] = None
    decision_source: str = "rule_based"
    decision_action: Optional[str] = None
    decision_explanation: Optional[str] = None


@dataclass
class Trip:
    trip_id: int
    order_id: int
    vehicle_id: int
    start_time: int
    end_time: int
    origin_zone_id: int
    destination_zone_id: int
    distance_km: float
    price: float


@dataclass
class SimulationContext:
    time_step: int
    hour_of_day: int
    season: str
    weather: str
    traffic_factor: float
    tariff_factor: float
    macro_factor: float
    event_factor: float
    demand_multiplier: float
    notes: list[str] = field(default_factory=list)

    @property
    def total_demand_factor(self) -> float:
        """Combined external multiplier for potential demand."""
        return max(
            0.0,
            self.demand_multiplier
            * self.macro_factor
            * self.event_factor
            * self._weather_demand_factor(),
        )

    def _weather_demand_factor(self) -> float:
        if self.weather == "rain":
            return 1.15
        if self.weather == "snow":
            return 1.25
        if self.weather == "storm":
            return 0.85
        return 1.0
