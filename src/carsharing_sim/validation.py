from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ValidationCheck:
    name: str
    passed: bool
    expected: str
    observed: str


def read_scenario_comparison(path: str | Path) -> dict[str, dict[str, float]]:
    path = Path(path)
    with path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    data: dict[str, dict[str, float]] = {}
    for row in rows:
        name = row["scenario"]
        data[name] = {}
        for key, value in row.items():
            if key == "scenario":
                continue
            try:
                data[name][key] = float(value)
            except (TypeError, ValueError):
                data[name][key] = 0.0
    return data


def validate_expected_scenario_behavior(scenario_comparison_csv: str | Path) -> list[ValidationCheck]:
    data = read_scenario_comparison(scenario_comparison_csv)
    baseline = data.get("baseline", {})
    checks: list[ValidationCheck] = []

    def add(name: str, condition: bool, expected: str, observed: str) -> None:
        checks.append(ValidationCheck(name=name, passed=bool(condition), expected=expected, observed=observed))

    high_demand = data.get("high_demand", {})
    add(
        "high_demand_increases_total_orders",
        high_demand.get("total_orders", 0) > baseline.get("total_orders", 0),
        "high_demand.total_orders > baseline.total_orders",
        f"{high_demand.get('total_orders', 0)} > {baseline.get('total_orders', 0)}",
    )

    bad_weather = data.get("bad_weather", {})
    add(
        "bad_weather_does_not_reduce_orders_in_this_scenario",
        bad_weather.get("total_orders", 0) >= baseline.get("total_orders", 0),
        "bad_weather.total_orders >= baseline.total_orders",
        f"{bad_weather.get('total_orders', 0)} >= {baseline.get('total_orders', 0)}",
    )

    fleet_shortage = data.get("fleet_shortage", {})
    add(
        "fleet_shortage_increases_no_vehicle_rate",
        fleet_shortage.get("no_vehicle_rate", 0) > baseline.get("no_vehicle_rate", 0),
        "fleet_shortage.no_vehicle_rate > baseline.no_vehicle_rate",
        f"{fleet_shortage.get('no_vehicle_rate', 0)} > {baseline.get('no_vehicle_rate', 0)}",
    )

    add(
        "fleet_shortage_reduces_completion_rate",
        fleet_shortage.get("completion_rate", 0) < baseline.get("completion_rate", 0),
        "fleet_shortage.completion_rate < baseline.completion_rate",
        f"{fleet_shortage.get('completion_rate', 0)} < {baseline.get('completion_rate', 0)}",
    )

    high_tariff = data.get("high_tariff", {})
    add(
        "high_tariff_increases_client_rejection_rate",
        high_tariff.get("client_rejection_rate", 0) >= baseline.get("client_rejection_rate", 0),
        "high_tariff.client_rejection_rate >= baseline.client_rejection_rate",
        f"{high_tariff.get('client_rejection_rate', 0)} >= {baseline.get('client_rejection_rate', 0)}",
    )

    return checks


def save_validation_report(checks: list[ValidationCheck], output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        passed = sum(c.passed for c in checks)
        f.write(f"Validation checks passed: {passed}/{len(checks)}\n\n")
        for check in checks:
            status = "PASS" if check.passed else "FAIL"
            f.write(f"[{status}] {check.name}\n")
            f.write(f"  expected: {check.expected}\n")
            f.write(f"  observed: {check.observed}\n\n")
    return output_path


def save_validation_csv(checks: list[ValidationCheck], output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "passed", "expected", "observed"])
        writer.writeheader()
        for check in checks:
            writer.writerow({
                "name": check.name,
                "passed": check.passed,
                "expected": check.expected,
                "observed": check.observed,
            })
    return output_path
