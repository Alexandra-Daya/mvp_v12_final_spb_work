from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carsharing_sim.allocation import BasicAllocator
from carsharing_sim.clients import ClientSimulator, build_synthetic_clients
from carsharing_sim.config import DEFAULT_CLIENTS, DEFAULT_SEED, DEFAULT_SIMULATION_STEPS, DEFAULT_VEHICLES, OUTPUTS_DIR
from carsharing_sim.data_adapters import load_od_demand_csv, load_zones_csv
from carsharing_sim.demand import DemandGenerator
from carsharing_sim.scenarios import (
    baseline,
    fleet_shortage,
    fleet_shortage_clean,
    high_demand,
    system_stress,
    simple_relocation,
    relocation_stress,
)
from carsharing_sim.simulation import SimulationEngine
from carsharing_sim.vehicles import VehicleSimulator, build_synthetic_fleet

SCENARIOS = {
    "baseline": baseline,
    "high_demand": high_demand,
    "fleet_shortage_clean": fleet_shortage_clean,
    "system_stress": system_stress,
    "simple_relocation": simple_relocation,
    "relocation_stress": relocation_stress,
    # Backward-compatible old stress scenario name from v0.5
    "fleet_shortage": fleet_shortage,
}


def run_contract_simulation(
    zones_path: str | Path,
    od_demand_path: str | Path,
    scenario_name: str = "baseline",
    output_prefix: str = "contract_run",
) -> dict:
    zones = load_zones_csv(zones_path)
    od_demand = load_od_demand_csv(od_demand_path)
    scenario = SCENARIOS[scenario_name]()
    clients = build_synthetic_clients(zones, n_clients=DEFAULT_CLIENTS, seed=DEFAULT_SEED)
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
    prefix = output_prefix
    metrics.save_orders_csv(OUTPUTS_DIR / f"{prefix}_orders.csv")
    metrics.save_summary_csv([summary], OUTPUTS_DIR / f"{prefix}_summary.csv")
    metrics.save_zone_metrics_csv(OUTPUTS_DIR / f"{prefix}_zone_metrics.csv")
    metrics.save_time_snapshots_csv(OUTPUTS_DIR / f"{prefix}_time_snapshots.csv")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MVP simulation from CSV data contracts.")
    parser.add_argument("--zones", required=True, help="Path to zones contract CSV")
    parser.add_argument("--od-demand", required=True, help="Path to OD demand contract CSV")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="baseline")
    parser.add_argument("--output-prefix", default="contract_run")
    args = parser.parse_args()

    summary = run_contract_simulation(
        zones_path=args.zones,
        od_demand_path=args.od_demand,
        scenario_name=args.scenario,
        output_prefix=args.output_prefix,
    )

    print(f"=== Contract data run: {args.scenario} ===")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"\nSaved outputs with prefix '{args.output_prefix}' in: {OUTPUTS_DIR}")


if __name__ == "__main__":
    main()
