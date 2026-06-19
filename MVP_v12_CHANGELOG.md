# MVP v12 changelog

## v12.3 final map update

This update adds the main final map:

```text
outputs/final_maps_v4/interactive_final_spb_map_v4.html
```

Changes:

- Added `experiments/make_final_interactive_map_v4.py`.
- Restored the v9/v10-style full-SPb soft heatmap logic.
- Kept full-SPb/NIR1 as the main calculation grid.
- Added optional horizontal-only visual split-grid, off by default.
- Removed vertical split-grid from the main map.
- Uses scenario-local heat normalization so baseline/high_demand are visible.
- Does not apply the water heuristic to heatmap points.
- Applies a soft heuristic only to top markers.
- Added `outputs/final_diagnostics/final_map_v4_diagnostics.csv`.

## v12.2 clean final map

This update adds the main final map:

```text
outputs/final_maps_v3/interactive_final_spb_clean_map_v3.html
```

Changes:

- Added `experiments/make_final_interactive_map_v3.py`.
- Returned the main visualization to the stable full-SPb/NIR1 calculation grid.
- Removed v12.1 visual split-grid from the main map.
- Kept v11 refined-grid and v12.1 split-grid maps as experimental artifacts only.
- Restored heatmap visibility for low/medium scenarios without visually equating them to stress scenarios.
- Uses a soft water heuristic only for black top markers, not for the heatmap.
- Added `outputs/final_diagnostics/final_map_v3_diagnostics.csv`.

## v12.1 final map update

This update keeps the v12 calculation model and adds an improved reporting map:

```text
outputs/final_maps_v2/interactive_final_spb_soft_shortage_map_v2.html
```

Changes:

- Added `experiments/make_final_interactive_map_v2.py`.
- Added a visual-only split grid: each full-SPb/NIR1 source zone is displayed as two equal orthogonal halves.
- Metrics remain aggregated by the original full-SPb/NIR1 zones; the split grid is not a recalculation.
- Top markers and heat points are filtered from obvious water-artifact locations with a conservative heuristic.
- Black top markers are suppressed for low-lost-demand scenarios such as baseline/high_demand when they would be visually misleading.
- Added `outputs/final_diagnostics/final_map_v2_diagnostics.csv`.

## v12 final-SPb engineering version

This version consolidates the older v5 baseline and the later v10/v11 full-SPb/refined-SPb work into a separate final project folder:

```text
mvp_v12_final_spb_work
```

Source folders `mvp_v05_work` and `mvp_v10_full_spb_work` were left unchanged.

## Main decisions

- The final pipeline is `experiments/run_final_pipeline.py`.
- The final map builder is `experiments/make_final_interactive_map.py`.
- The final diagnostics script is `experiments/diagnose_final_outputs.py`.
- The final reporting map uses the stable full-SPb/NIR1 grid.
- The v11 refined grid is diagnostic-only, not the main map, because it can produce water/centroid artifacts and visually misleading subzones.

## Output contract

The final pipeline creates:

```text
outputs/final_scenario_comparison.csv
outputs/final_zone_metrics.csv
outputs/final_maps/interactive_final_spb_soft_shortage_map.html
outputs/final_diagnostics/final_diagnostics.csv
outputs/final_diagnostics/final_diagnostics.txt
outputs/final_diagnostics/top_10_problem_zones.csv
```

## Terminology

Final CSV outputs expose carsharing-specific aliases while keeping older fields for compatibility:

- `cancelled_no_vehicle` remains available.
- `lost_demand_no_vehicle` is the reporting alias.
- `shortage_rate` and `no_vehicle_rate` remain available where produced.
- `lost_demand_no_vehicle_rate` is the reporting alias.
- `cancelled_by_client` remains available.
- `client_rejection_after_vehicle_found` is the reporting alias.

## Interpretation

This is a model simulation based on reconstructed NIR1 OD demand. It does not use real operator carsharing transactions and should not be described as an exact operator model.
