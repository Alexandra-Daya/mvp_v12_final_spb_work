from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carsharing_sim.allocation import BasicAllocator
from carsharing_sim.clients import ClientSimulator, build_synthetic_clients
from carsharing_sim.config import DEFAULT_CLIENTS, DEFAULT_SEED, DEFAULT_SIMULATION_STEPS, DEFAULT_VEHICLES, OUTPUTS_DIR
from carsharing_sim.data_adapters import save_sample_contract_files
from carsharing_sim.demand import DemandGenerator, build_synthetic_od_demand, build_synthetic_zones
from carsharing_sim.scenarios import baseline
from carsharing_sim.simulation import SimulationEngine
from carsharing_sim.vehicles import VehicleSimulator, build_synthetic_fleet


def main() -> None:
    zones = build_synthetic_zones()
    od_demand = build_synthetic_od_demand(zones)
    clients = build_synthetic_clients(zones, n_clients=DEFAULT_CLIENTS, seed=DEFAULT_SEED)
    scenario = baseline()
    n_vehicles = max(1, int(DEFAULT_VEHICLES * scenario.fleet_size_multiplier))
    vehicles = build_synthetic_fleet(zones, n_vehicles=n_vehicles, seed=DEFAULT_SEED)

    engine = SimulationEngine(
        scenario=scenario,
        zones=zones,
        demand_generator=DemandGenerator(od_demand, seed=DEFAULT_SEED),
        client_simulator=ClientSimulator(clients, seed=DEFAULT_SEED),
        vehicle_simulator=VehicleSimulator(vehicles),
        allocator=BasicAllocator(zones, max_search_distance_km=scenario.max_vehicle_search_distance_km),
        simulation_steps=DEFAULT_SIMULATION_STEPS,
    )
    metrics = engine.run()
    summary = metrics.summary(scenario.name)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    metrics.save_orders_csv(OUTPUTS_DIR / "baseline_orders.csv")
    metrics.save_summary_csv([summary], OUTPUTS_DIR / "baseline_summary.csv")
    metrics.save_zone_metrics_csv(OUTPUTS_DIR / "baseline_zone_metrics.csv")
    metrics.save_time_snapshots_csv(OUTPUTS_DIR / "baseline_time_snapshots.csv")
    save_sample_contract_files(OUTPUTS_DIR)

    print("=== Baseline scenario ===")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"\nSaved: {OUTPUTS_DIR / 'baseline_orders.csv'}")
    print(f"Saved: {OUTPUTS_DIR / 'baseline_summary.csv'}")
    print(f"Saved: {OUTPUTS_DIR / 'baseline_zone_metrics.csv'}")
    print(f"Saved: {OUTPUTS_DIR / 'baseline_time_snapshots.csv'}")
    print(f"Saved sample data contracts in: {OUTPUTS_DIR}")


if __name__ == "__main__":
    main()
