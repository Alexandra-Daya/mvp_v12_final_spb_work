from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carsharing_sim.nir1_adapter import convert_nir1_od_predictions_to_contract


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert NIR1 OD predictions CSV to MVP simulator contracts.")
    parser.add_argument("--input", required=True, help="Path to NIR1 artifacts/od_pairs_with_predictions.csv")
    parser.add_argument("--output-dir", default=str(ROOT / "data" / "processed"), help="Directory for converted contracts")
    parser.add_argument("--demand-column", default=None, help="Flow column to use: ml_flow, real_flow, gravity_scaled, etc.")
    parser.add_argument("--max-pairs", type=int, default=600, help="Keep top-N OD pairs by selected demand column")
    parser.add_argument("--target-total-base-demand", type=float, default=45.0, help="Rescale top OD pairs to this total base demand intensity")
    args = parser.parse_args()

    zones_path, od_path = convert_nir1_od_predictions_to_contract(
        input_csv=args.input,
        output_dir=args.output_dir,
        demand_column=args.demand_column,
        max_pairs=args.max_pairs,
        target_total_base_demand=args.target_total_base_demand,
    )

    print("Converted NIR1 data contracts:")
    print(f"zones: {zones_path}")
    print(f"od_demand: {od_path}")
    print("\nNext command example:")
    print(f"python experiments/run_from_contract.py --zones {zones_path} --od-demand {od_path}")


if __name__ == "__main__":
    main()
