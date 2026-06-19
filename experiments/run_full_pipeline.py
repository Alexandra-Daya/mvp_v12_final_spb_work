from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script: str) -> None:
    print(f"\n=== Running {script} ===")
    subprocess.run([sys.executable, str(ROOT / script)], check=True)


def main() -> None:
    run("experiments/run_baseline.py")
    run("experiments/run_scenarios.py")
    run("experiments/validate_scenarios.py")
    run("experiments/generate_visualizations.py")
    run("experiments/run_llm_agent_scenario.py")
    print("\nFull MVP v0.5 pipeline completed.")


if __name__ == "__main__":
    main()
