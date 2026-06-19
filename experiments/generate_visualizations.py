from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carsharing_sim.config import OUTPUTS_DIR
from carsharing_sim.visualization import generate_default_visualizations


def main() -> None:
    generated = generate_default_visualizations(OUTPUTS_DIR)
    if not generated:
        print("No figures generated. Run experiments/run_scenarios.py first.")
        return
    print("Generated figures:")
    for path in generated:
        print(f"- {path}")


if __name__ == "__main__":
    main()
