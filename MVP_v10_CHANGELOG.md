# MVP v0.10 changelog

This version improves the v0.9 full-SPb branch without touching presentation files.

## Implemented

- Added full v0.10 runner: `experiments/run_v10_full_pipeline.py`.
- Added simple relocation scenarios:
  - `simple_relocation`
  - `relocation_stress`
- Added relocation-related scenario parameters to `ScenarioSettings`.
- Added a naive end-of-step relocation heuristic to `VehicleSimulator` and `SimulationEngine`.
- Added additional distance-to-vehicle metrics:
  - `avg_allocated_distance_to_vehicle_km`
  - `avg_nonzero_distance_to_vehicle_km`
- Added spatial sanity-check script:
  - `experiments/analyze_full_spb_sanity.py`
- Updated full-SPb zone visualization scripts to include relocation scenarios.
- Updated tests: 5 smoke tests pass.
- Updated `requirements.txt` with geospatial/visualization dependencies.

## Main v0.10 test run results

| scenario | total_orders | completed_orders | no_vehicle_rate | client_rejection_rate | avg_allocated_distance_to_vehicle_km | total_relocated_vehicles |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 1151 | 397 | 0.0634 | 0.5917 | 2.562 | 0 |
| high_demand | 1672 | 634 | 0.0538 | 0.5670 | 2.360 | 0 |
| fleet_shortage_clean | 1151 | 74 | 0.9140 | 0.0217 | 0.000 | 0 |
| system_stress | 1828 | 99 | 0.9278 | 0.0181 | 0.000 | 0 |
| simple_relocation | 1151 | 415 | 0.0104 | 0.6290 | 2.463 | 100 |
| relocation_stress | 1672 | 607 | 0.0185 | 0.6184 | 2.483 | 104 |

## Objective interpretation

The simple relocation rule strongly reduces `no_vehicle_rate` in this seeded run, but it does not automatically maximize completed orders because many offered trips are still rejected by clients due to price/distance/profile constraints. Therefore the relocation module is useful as a demonstrator and a baseline for future optimization, not as a final operations policy.

## Known limitations

- NIR1 supplies modeled OD demand, not real carsharing transactions.
- Peripheral zone coverage in the full-SPb branch uses a documented modeling floor.
- Reference-area sanity checks are approximate and are not official administrative district labels.
- The relocation policy is instantaneous and heuristic; future versions should model relocation time/cost and optimize destinations.


## v0.11 refined-SPb grid and calibrated maps

- Added `experiments/prepare_refined_spb_contract.py` to split elongated NIR1 rectangles into smaller square-ish subzones.
- Added refined scenario pipeline: `experiments/run_v11_refined_pipeline.py`.
- Added refined outputs under `outputs/refined_spb_*` and `outputs/refined_spb_maps/`.
- Updated full-SPb soft map scaling: heat intensity now uses one global scale across scenarios, so small baseline shortages are not visually exaggerated.
- Added carsharing-specific aliases for interpretation: `lost_demand_no_vehicle` and `lost_demand_no_vehicle_rate`.

Important: refined subzones are model-derived from the NIR1 grid and OD contract; they improve spatial granularity but are not real operator validation.
