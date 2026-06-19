# Final engineering report: MVP v12.3 final-SPb map

## What was found

- The workspace contains `mvp_v05_work` and `mvp_v10_full_spb_work`.
- The later refined-SPb v11 work is inside `mvp_v10_full_spb_work`, not in a separate v11 folder.
- The v10/v11 branch contains the most complete code: full-SPb contract preparation, six final scenarios, relocation heuristics, refined-grid experiments, interactive maps and sanity checks.
- The existing README mixed older MVP text with v10/v11 notes, so v12 needed a clean entry point and output contract.

## Why the v11 map produced artifacts

The refined v11 pipeline splits 197 parent zones into 394 subzones. Its interactive map builds the heat layer from refined-subzone centroids. Some refined subzones and their centroid/heat points can visually fall in the Gulf of Finland or produce awkward-looking geometry. Without a real land-mask layer, forcing those subzones into a polished final map would be methodologically misleading.

## v12 final map choice

The final v12 reporting map uses the stable full-SPb/NIR1 grid:

```text
outputs/final_maps/interactive_final_spb_soft_shortage_map.html
```

The refined v11 grid is kept as diagnostic material only. The final map shows inactive zones as grey transparent zones and uses a soft glow only for active full-SPb zones with modeled lost demand.

## v12.1 map improvement

After review, the v12 map still had visual issues: some black top markers could appear on obvious water or boundary zones, and low-shortage scenarios such as `baseline` and `high_demand` could look like sparse black points without meaningful heat.

v12.1 keeps the same full-SPb/NIR1 calculation model and adds a new display map:

```text
outputs/final_maps_v2/interactive_final_spb_soft_shortage_map_v2.html
```

The new visual split grid divides each source full-SPb/NIR1 zone into two equal orthogonal bounding-box halves. This is only a visual layer. It is not a new OD model and it does not recalculate demand or simulation metrics. Metrics remain aggregated by the original full-SPb/NIR1 zones.

The v11 refined grid remains experimental. It is not used as the final map because its subzone geometry and centroid heat points can produce water artifacts.

v12.1 also changes the map behavior:

- heat points use safe representative points, not raw centroids;
- obvious water-artifact point locations are filtered with a conservative heuristic because no true land-mask is available;
- top black markers are shown only when scenario lost demand is materially large;
- `baseline` and `high_demand` keep weak heat where appropriate but do not overstate low lost demand with black problem markers;
- final labels use `lost_demand_no_vehicle` terminology instead of treating this as a confirmed order that failed after dispatch.

## v12.2 clean map correction

After review, the v12.1 split-grid map was not accepted as the main final visualization. The visual split-grid made the map look like a set of vertical strips and added too much visual noise. The water filter in v12.1 was also too aggressive for the heatmap and made low/medium scenarios look almost empty.

v12.2 fixes this by returning the main map to the cleaner v10/v12 approach:

```text
outputs/final_maps_v3/interactive_final_spb_clean_map_v3.html
```

Main decisions:

- v11 refined-grid remains experimental because it created water/centroid artifacts.
- v12.1 split-grid remains an artifact, not the main map.
- The final v3 map uses the stable full-SPb/NIR1 calculation grid.
- Grid lines are thinner, grey and low-opacity.
- Heatmap visibility is restored for `baseline` and `high_demand`.
- The heatmap is not aggressively filtered by water heuristics.
- Black top markers are filtered softly and only for obvious water/low-value cases.
- `lost_demand_no_vehicle` remains the reporting terminology.

## v12.3 final map correction

After review, v12.3/v4 became the main final map:

```text
outputs/final_maps_v4/interactive_final_spb_map_v4.html
```

Why previous attempts were not enough:

- v11 refined-grid produced water/centroid artifacts.
- v12.1 split-grid used vertical splitting and created visual striping.
- v12.2/v3 returned to full-SPb but made baseline/high_demand look too empty.

What v4 fixes:

- returns to the successful full-SPb/NIR1 soft heatmap logic;
- keeps the full-SPb/NIR1 grid as the main model grid;
- adds horizontal split-grid only as an optional visual layer, off by default;
- never uses vertical split-grid in the final map;
- normalizes heatmap within each scenario so baseline/high_demand are visible;
- uses lighter heat opacity for baseline/high_demand so they are not visually equated with system stress;
- applies water filtering only to top markers, not to the heatmap;
- keeps `lost_demand_no_vehicle` as the reporting terminology.

## What to run

From the v12 project root:

```powershell
python -m pytest -q
python experiments/run_final_pipeline.py
```

## Main outputs

```text
outputs/final_scenario_comparison.csv
outputs/final_zone_metrics.csv
outputs/final_maps/interactive_final_spb_soft_shortage_map.html
outputs/final_maps_v2/interactive_final_spb_soft_shortage_map_v2.html
outputs/final_maps_v3/interactive_final_spb_clean_map_v3.html
outputs/final_maps_v4/interactive_final_spb_map_v4.html
outputs/final_diagnostics/final_diagnostics.csv
outputs/final_diagnostics/final_map_v2_diagnostics.csv
outputs/final_diagnostics/final_map_v3_diagnostics.csv
outputs/final_diagnostics/final_map_v4_diagnostics.csv
outputs/final_diagnostics/top_10_problem_zones.csv
outputs/full_spb_sanity/full_spb_top_problem_zones_with_reference_areas.csv
```

## Remaining limits

- No real carsharing operator data is used.
- Demand is reconstructed from NIR1 OD flows and rescaled for simulation.
- The full-SPb coverage floor is a modeling assumption.
- The relocation scenarios are heuristic tests, not optimized operations algorithms.
- The visual split grid is only a display grid, not a recalculation.
- The v12.1 water filter is heuristic and should be replaced by a real land/water mask for cartographic publication.
- v12.2 still uses a heuristic water filter for black top markers only; it is not a real land-mask.
- v12.3 also uses only a soft marker heuristic and does not claim a real land-mask.
- The optional horizontal split-grid is visual only and does not recalculate demand.
- A true land-mask or administrative GIS layer would be needed before refined subzones could be safely used as a final public map.

## Next improvements

- Add a real land/water mask and validate refined subzone representative points against it.
- Calibrate demand intensity with observed carsharing or mobility-platform data if available.
- Replace the simple relocation rule with an explicit optimization or simulation-based control policy.
- Add visual regression checks for generated HTML maps.
