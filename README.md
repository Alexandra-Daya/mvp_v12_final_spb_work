# Carsharing Digital Twin MVP v12.3 final map

This is the final engineering MVP for a digital twin of the St Petersburg carsharing market.

The model is a simulation based on reconstructed NIR1 OD demand, zones and flows. It does not use real operator carsharing transactions.

## Main result

The main final map is:

```text
outputs/final_maps_v4/interactive_final_spb_map_v4.html
```

It uses the stable full-SPb/NIR1 calculation grid, restores the soft heatmap visibility of the stronger v9/v10-style maps, and keeps the grid readable without turning it into visual noise.

## Why v4

- v11 refined-grid is experimental: it can place centroid/heat points in water.
- v12.1 vertical split-grid is experimental: it created too much visual striping.
- v12.2/v3 was cleaner, but baseline/high_demand looked too empty.
- v12.3/v4 keeps full-SPb/NIR1 as the main grid and makes all scenarios with `lost_demand_no_vehicle > 0` visibly render a heatmap.
- Optional horizontal split-grid is visual only and is off by default.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pytest geopandas folium branca
```

If PowerShell blocks `Activate.ps1`, use `activate.bat` as shown above or run commands through `.venv\Scripts\python.exe`.

## Tests

```powershell
python -m pytest -q
```

## Final pipeline

Run from the project root:

```powershell
python experiments/run_final_pipeline.py
```

Main outputs:

```text
outputs/final_scenario_comparison.csv
outputs/final_zone_metrics.csv
outputs/final_maps_v4/interactive_final_spb_map_v4.html
outputs/final_diagnostics/final_map_v4_diagnostics.csv
```

Previous map artifacts are preserved:

```text
outputs/final_maps/interactive_final_spb_soft_shortage_map.html
outputs/final_maps_v2/interactive_final_spb_soft_shortage_map_v2.html
outputs/final_maps_v3/interactive_final_spb_clean_map_v3.html
```

Open the final map:

```powershell
explorer outputs\final_maps_v4
```

## Map method

The v4 map uses:

- stable full-SPb/NIR1 source zones as the calculation grid;
- thin grey grid lines with low opacity;
- scenario-local heatmap normalization so baseline/high_demand remain visible;
- lower opacity for lighter scenarios so they do not look as severe as system stress;
- black top markers for strong shortage scenarios;
- small grey markers for low-intensity baseline/high_demand;
- a soft top-marker water heuristic only; heatmap is not aggressively filtered.

The optional horizontal split-grid layer divides each source zone into lower/upper halves for display only. It is not a calculation grid and does not change OD demand, simulations or metrics.

## Model limits

- No real carsharing operator data is used.
- OD demand comes from reconstructed NIR1 flows and is rescaled for simulation.
- Full-SPb zone coverage floors are modeling assumptions.
- The v11 refined grid and v12.1 vertical split-grid are not the main map.
- The horizontal split-grid is visual only.
- The water-marker filter is heuristic and should be replaced by a real land/water mask for cartographic publication.
