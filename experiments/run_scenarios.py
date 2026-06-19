from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carsharing_sim.allocation import BasicAllocator
from carsharing_sim.clients import ClientSimulator, build_synthetic_clients
from carsharing_sim.config import DEFAULT_CLIENTS, DEFAULT_SEED, DEFAULT_SIMULATION_STEPS, DEFAULT_VEHICLES, OUTPUTS_DIR
from carsharing_sim.demand import DemandGenerator, build_synthetic_od_demand, build_synthetic_zones
from carsharing_sim.metrics import MetricsCollector
from carsharing_sim.scenarios import all_scenarios
from carsharing_sim.simulation import SimulationEngine
from carsharing_sim.vehicles import VehicleSimulator, build_synthetic_fleet


def main() -> None:
    zones = build_synthetic_zones()
    od_demand = build_synthetic_od_demand(zones)
    clients = build_synthetic_clients(zones, n_clients=DEFAULT_CLIENTS, seed=DEFAULT_SEED)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for idx, scenario in enumerate(all_scenarios()):
        n_vehicles = max(1, int(DEFAULT_VEHICLES * scenario.fleet_size_multiplier))
        vehicles = build_synthetic_fleet(zones, n_vehicles=n_vehicles, seed=DEFAULT_SEED + idx)
        engine = SimulationEngine(
            scenario=scenario,
            zones=zones,
            demand_generator=DemandGenerator(od_demand, seed=DEFAULT_SEED + idx),
            client_simulator=ClientSimulator(clients, seed=DEFAULT_SEED + idx),
            vehicle_simulator=VehicleSimulator(vehicles),
            allocator=BasicAllocator(zones, max_search_distance_km=scenario.max_vehicle_search_distance_km),
            simulation_steps=DEFAULT_SIMULATION_STEPS,
        )
        metrics = engine.run()
        rows.append(metrics.summary(scenario.name))
        metrics.save_zone_metrics_csv(OUTPUTS_DIR / f"{scenario.name}_zone_metrics.csv")
        metrics.save_time_snapshots_csv(OUTPUTS_DIR / f"{scenario.name}_time_snapshots.csv")

    output_path = OUTPUTS_DIR / "scenario_comparison.csv"
    MetricsCollector.save_summary_csv(rows, output_path)

    print("=== Scenario comparison ===")
    for row in rows:
        print(
            f"{row['scenario']}: "
            f"orders={row['total_orders']}, "
            f"completed={row['completed_orders']}, "
            f"completion_rate={row['completion_rate']}, "
            f"no_vehicle_rate={row['no_vehicle_rate']}, "
            f"client_rejection_rate={row['client_rejection_rate']}, "
            f"revenue={row['revenue']}"
        )
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
