from carsharing_sim.allocation import BasicAllocator
from carsharing_sim.clients import ClientSimulator, build_synthetic_clients
from carsharing_sim.data_adapters import save_sample_contract_files, load_od_demand_csv, load_zones_csv
from carsharing_sim.demand import DemandGenerator, build_synthetic_od_demand, build_synthetic_zones
from carsharing_sim.scenarios import baseline, fleet_shortage
from carsharing_sim.simulation import SimulationEngine
from carsharing_sim.vehicles import VehicleSimulator, build_synthetic_fleet
from pathlib import Path
import importlib.util

import geopandas as gpd
from shapely.geometry import box


def _run(scenario, n_vehicles=10, steps=4):
    zones = build_synthetic_zones()
    od = build_synthetic_od_demand(zones)
    clients = build_synthetic_clients(zones, n_clients=50)
    vehicles = build_synthetic_fleet(zones, n_vehicles=n_vehicles)
    engine = SimulationEngine(
        scenario=scenario,
        zones=zones,
        demand_generator=DemandGenerator(od),
        client_simulator=ClientSimulator(clients),
        vehicle_simulator=VehicleSimulator(vehicles),
        allocator=BasicAllocator(zones, max_search_distance_km=scenario.max_vehicle_search_distance_km),
        simulation_steps=steps,
    )
    return engine.run().summary(scenario.name)


def test_simulation_runs():
    summary = _run(baseline())
    assert summary["total_orders"] >= 0
    assert "completion_rate" in summary
    assert "no_vehicle_rate" in summary


def test_fleet_shortage_can_create_no_vehicle_cancellations():
    summary = _run(fleet_shortage(), n_vehicles=2, steps=8)
    assert summary["cancelled_no_vehicle"] >= 0
    assert "max_zone_shortage" in summary


def test_data_contract_samples_roundtrip(tmp_path):
    zones_path, od_path = save_sample_contract_files(tmp_path)
    zones = load_zones_csv(zones_path)
    od = load_od_demand_csv(od_path)
    assert len(zones) == 1
    assert len(od) == 1


def test_llm_agent_decision_layer_runs():
    from carsharing_sim.llm_agents import HeuristicLLMDecisionEngine

    zones = build_synthetic_zones()
    od = build_synthetic_od_demand(zones)
    clients = build_synthetic_clients(zones, n_clients=50)
    vehicles = build_synthetic_fleet(zones, n_vehicles=10)
    scenario = baseline()
    engine = SimulationEngine(
        scenario=scenario,
        zones=zones,
        demand_generator=DemandGenerator(od),
        client_simulator=ClientSimulator(
            clients,
            decision_engine=HeuristicLLMDecisionEngine(),
            llm_agent_share=0.30,
        ),
        vehicle_simulator=VehicleSimulator(vehicles),
        allocator=BasicAllocator(zones, max_search_distance_km=scenario.max_vehicle_search_distance_km),
        simulation_steps=4,
    )
    summary = engine.run().summary("llm_smoke")
    assert "llm_agent_orders" in summary
    assert summary["llm_agent_orders"] >= 0


def test_simple_relocation_scenario_reports_relocations():
    from carsharing_sim.scenarios import simple_relocation

    summary = _run(simple_relocation(), n_vehicles=10, steps=4)
    assert "total_relocated_vehicles" in summary
    assert "relocated_vehicles" in summary
    assert summary["total_relocated_vehicles"] >= 0
    assert summary["relocated_vehicles"] == summary["total_relocated_vehicles"]
    assert "avg_allocated_distance_to_vehicle_km" in summary


def test_final_v12_entrypoints_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "experiments" / "run_final_pipeline.py").exists()
    assert (root / "experiments" / "make_final_interactive_map.py").exists()
    assert (root / "experiments" / "make_final_interactive_map_v2.py").exists()
    assert (root / "experiments" / "make_final_interactive_map_v3.py").exists()
    assert (root / "experiments" / "make_final_interactive_map_v4.py").exists()
    assert (root / "experiments" / "diagnose_final_outputs.py").exists()


def test_carsharing_alias_fields_are_reported():
    summary = _run(fleet_shortage(), n_vehicles=2, steps=8)
    assert "lost_demand_no_vehicle" in summary
    assert "lost_demand_no_vehicle_rate" in summary
    assert "client_rejection_after_vehicle_found" in summary
    assert summary["lost_demand_no_vehicle"] == summary["cancelled_no_vehicle"]


def test_refined_grid_is_not_final_main_map():
    root = Path(__file__).resolve().parents[1]
    final_map = (root / "experiments" / "make_final_interactive_map.py").read_text(encoding="utf-8")
    assert "diagnostic experiment" in final_map
    assert "reporting map" in final_map
    assert 'ZONES_PATH = ROOT / "data" / "raw" / "nir1" / "zones.geojson"' in final_map
    assert 'ZONES_PATH = ROOT / "data" / "processed" / "refined_spb_zones.geojson"' not in final_map


def test_visual_split_grid_creates_two_halves():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "experiments" / "make_final_interactive_map_v2.py"
    spec = importlib.util.spec_from_file_location("make_final_interactive_map_v2", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    zones = gpd.GeoDataFrame(
        [{"zone_id": 7, "geometry": box(0, 0, 4, 2)}],
        geometry="geometry",
        crs="EPSG:4326",
    )
    split = module.build_visual_split_grid(zones)

    assert len(split) == 2
    assert set(split["visual_subzone_id"]) == {"7_a", "7_b"}
    assert set(split["parent_zone_id"]) == {7}
    assert set(split["is_visual_split"]) == {1}


def test_v3_clean_map_is_main_without_refined_or_split_grid():
    root = Path(__file__).resolve().parents[1]
    script = (root / "experiments" / "make_final_interactive_map_v3.py").read_text(encoding="utf-8")
    pipeline = (root / "experiments" / "run_final_pipeline.py").read_text(encoding="utf-8")
    diagnostics = (root / "experiments" / "diagnose_final_outputs.py").read_text(encoding="utf-8")

    assert "interactive_final_spb_clean_map_v3.html" in script
    assert "interactive_final_spb_clean_map_v3.html" in pipeline
    assert "refined_grid_used_as_main_final_map" in script
    assert "split_grid_used_as_main_final_map" in script
    assert '"refined_grid_used_as_main_final_map", "value": 0' in script
    assert '"split_grid_used_as_main_final_map", "value": 0' in script
    assert "FINAL_MAP_V3" in diagnostics


def test_v4_horizontal_split_grid_creates_two_halves_only():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "experiments" / "make_final_interactive_map_v4.py"
    spec = importlib.util.spec_from_file_location("make_final_interactive_map_v4", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    zones = gpd.GeoDataFrame(
        [{"zone_id": 11, "geometry": box(0, 0, 4, 2)}],
        geometry="geometry",
        crs="EPSG:4326",
    )
    split = module.build_horizontal_visual_split_grid(zones)

    assert len(split) == 2
    assert set(split["visual_subzone_id"]) == {"11_lower", "11_upper"}
    assert set(split["parent_zone_id"]) == {11}
    assert set(split["is_visual_only"]) == {1}


def test_v4_is_main_map_without_refined_or_vertical_split():
    root = Path(__file__).resolve().parents[1]
    script = (root / "experiments" / "make_final_interactive_map_v4.py").read_text(encoding="utf-8")
    pipeline = (root / "experiments" / "run_final_pipeline.py").read_text(encoding="utf-8")
    diagnostics = (root / "experiments" / "diagnose_final_outputs.py").read_text(encoding="utf-8")

    assert "interactive_final_spb_map_v4.html" in script
    assert "interactive_final_spb_map_v4.html" in pipeline
    assert "FINAL_MAP_V4" in diagnostics
    assert '"refined_grid_used_as_main_final_map", "value": 0' in script
    assert '"vertical_split_grid_used", "value": 0' in script
    assert '"horizontal_visual_split_grid_used_as_calculation", "value": 0' in script
