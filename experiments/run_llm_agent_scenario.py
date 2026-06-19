from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carsharing_sim.allocation import BasicAllocator
from carsharing_sim.clients import ClientSimulator, build_synthetic_clients
from carsharing_sim.config import DEFAULT_CLIENTS, DEFAULT_SEED, DEFAULT_SIMULATION_STEPS, DEFAULT_VEHICLES, OUTPUTS_DIR
from carsharing_sim.demand import DemandGenerator, build_synthetic_od_demand, build_synthetic_zones
from carsharing_sim.llm_agents import AgentDecision, HeuristicLLMDecisionEngine, OllamaDecisionEngine
from carsharing_sim.metrics import MetricsCollector
from carsharing_sim.scenarios import llm_agent_experiment
from carsharing_sim.simulation import SimulationEngine
from carsharing_sim.vehicles import VehicleSimulator, build_synthetic_fleet


class LimitedDecisionEngine:
    """Calls the real engine only for the first N LLM-agent decisions.

    This keeps local Ollama tests short. After the limit is reached, the wrapper
    uses a heuristic fallback and marks those rows separately, so summary metrics
    count only real Ollama calls as `llm_agent_orders`.
    """

    def __init__(self, real_engine, max_real_calls: int | None = None, seed: int = DEFAULT_SEED):
        self.real_engine = real_engine
        self.max_real_calls = max_real_calls
        self.real_calls = 0
        self.fallback = HeuristicLLMDecisionEngine(seed=seed)

    def decide(self, client, order, context) -> AgentDecision:
        if self.max_real_calls is None or self.real_calls < self.max_real_calls:
            self.real_calls += 1
            return self.real_engine.decide(client=client, order=order, context=context)
        d = self.fallback.decide(client=client, order=order, context=context)
        return AgentDecision(
            action=d.action,
            accepted=d.accepted,
            confidence=d.confidence,
            explanation="Ollama call skipped after max_llm_orders; heuristic fallback used. " + d.explanation,
            source="heuristic_after_ollama_limit",
        )


def build_decision_engine(engine_name: str, model: str, max_llm_orders: int | None):
    if engine_name == "none":
        return None
    if engine_name == "heuristic":
        return HeuristicLLMDecisionEngine(seed=DEFAULT_SEED)
    if engine_name == "ollama":
        return LimitedDecisionEngine(
            OllamaDecisionEngine(model=model, endpoint="http://127.0.0.1:11434/api/generate", timeout=90.0),
            max_real_calls=max_llm_orders,
            seed=DEFAULT_SEED,
        )
    raise ValueError(f"Unknown engine: {engine_name}")


def run_case(label: str, llm_agent_share: float, decision_engine) -> dict:
    zones = build_synthetic_zones()
    od_demand = build_synthetic_od_demand(zones)
    clients = build_synthetic_clients(zones, n_clients=DEFAULT_CLIENTS, seed=DEFAULT_SEED)
    scenario = llm_agent_experiment()
    vehicles = build_synthetic_fleet(zones, n_vehicles=DEFAULT_VEHICLES, seed=DEFAULT_SEED)

    client_simulator = ClientSimulator(
        clients,
        seed=DEFAULT_SEED,
        decision_engine=decision_engine,
        llm_agent_share=llm_agent_share,
    )

    engine = SimulationEngine(
        scenario=scenario,
        zones=zones,
        demand_generator=DemandGenerator(od_demand, seed=DEFAULT_SEED),
        client_simulator=client_simulator,
        vehicle_simulator=VehicleSimulator(vehicles),
        allocator=BasicAllocator(zones, max_search_distance_km=scenario.max_vehicle_search_distance_km),
        simulation_steps=DEFAULT_SIMULATION_STEPS,
    )
    metrics = engine.run()
    summary = metrics.summary(label)
    metrics.save_orders_csv(OUTPUTS_DIR / f"{label}_orders.csv")
    metrics.save_zone_metrics_csv(OUTPUTS_DIR / f"{label}_zone_metrics.csv")
    metrics.save_time_snapshots_csv(OUTPUTS_DIR / f"{label}_time_snapshots.csv")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run rule-based vs heuristic/Ollama LLM-agent comparison.")
    parser.add_argument("--engine", choices=["heuristic", "ollama"], default="heuristic")
    parser.add_argument("--model", default="llama3.2:3b")
    parser.add_argument("--llm-agent-share", type=float, default=0.30)
    parser.add_argument("--max-llm-orders", type=int, default=None)
    parser.add_argument("--output-prefix", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.engine == "heuristic":
        experiment_label = "llm_comparison_30pct_agents"
        comparison_path = OUTPUTS_DIR / "llm_agent_comparison.csv"
    else:
        safe_model = args.model.replace(":", "_").replace("/", "_")
        experiment_label = f"ollama_comparison_{safe_model}_{int(args.llm_agent_share * 100)}pct_agents"
        if args.output_prefix:
            experiment_label = args.output_prefix
        comparison_path = OUTPUTS_DIR / f"{experiment_label}_comparison.csv"

    rows = [
        run_case("llm_comparison_rule_based", llm_agent_share=0.0, decision_engine=None),
        run_case(
            experiment_label,
            llm_agent_share=args.llm_agent_share,
            decision_engine=build_decision_engine(args.engine, args.model, args.max_llm_orders),
        ),
    ]
    MetricsCollector.save_summary_csv(rows, comparison_path)

    print("=== LLM-agent layer comparison ===")
    print(f"engine={args.engine}, model={args.model}, llm_agent_share={args.llm_agent_share}, max_llm_orders={args.max_llm_orders}")
    for row in rows:
        print(
            f"{row['scenario']}: orders={row['total_orders']}, "
            f"completed={row['completed_orders']}, completion_rate={row['completion_rate']}, "
            f"client_rejection_rate={row['client_rejection_rate']}, "
            f"llm_agent_orders={row['llm_agent_orders']}, "
            f"llm_acceptance_rate={row['llm_agent_acceptance_rate']}"
        )
    print(f"\nSaved comparison: {comparison_path}")
    print("Saved order-level outputs with the same scenario prefix in outputs/.")


if __name__ == "__main__":
    main()
