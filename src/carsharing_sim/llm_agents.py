from __future__ import annotations

import json
import random
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from carsharing_sim.entities import Client, ClientProfileType, Order, SimulationContext


@dataclass(frozen=True)
class AgentDecision:
    """Structured decision produced by an economic agent model."""

    action: str
    accepted: bool
    confidence: float
    explanation: str
    source: str


class DecisionEngine(Protocol):
    """Interface for user decision engines.

    Implementations may be ordinary rule-based models, controlled heuristic
    stand-ins, or real local LLM integrations. The simulation only depends on
    the structured output, not on a particular LLM provider.
    """

    def decide(self, client: Client, order: Order, context: SimulationContext) -> AgentDecision:
        ...


def build_agent_prompt(client: Client, order: Order, context: SimulationContext) -> str:
    """Build a transparent prompt for an LLM-like economic agent.

    The prompt is intentionally structured so that it can later be sent to a
    local model through Ollama or another provider. In the default MVP run this
    prompt is consumed by a deterministic heuristic stand-in, not by an actual
    LLM. This keeps the project reproducible without external dependencies.
    """

    return (
        "You are a carsharing user deciding whether to accept a trip.\n"
        f"Profile: {client.profile.profile_type.value}.\n"
        f"Hour of day: {context.hour_of_day}. Season: {context.season}. Weather: {context.weather}.\n"
        f"Tariff factor: {context.tariff_factor:.2f}. Traffic factor: {context.traffic_factor:.2f}.\n"
        f"Trip distance: {order.distance_km:.2f} km. "
        f"Distance to vehicle: {order.distance_to_vehicle_km:.2f} km. "
        f"Estimated price: {order.price:.2f}. Estimated wait: {order.wait_time:.2f} min.\n"
        "Return one action from: accept, reject_price, reject_distance, wait, alternative."
    )


class HeuristicLLMDecisionEngine:
    """Controlled LLM-agent stand-in for the MVP.

    This class does not claim to be a real LLM. It mimics the role of a
    prompt-driven economic agent in a reproducible way and produces structured
    explanations. It is useful for comparing a profile-aware agent layer with
    the baseline rule-based behaviour before adding Ollama.
    """

    def __init__(self, seed: int = 42):
        self.random = random.Random(seed)

    def decide(self, client: Client, order: Order, context: SimulationContext) -> AgentDecision:
        if order.distance_to_vehicle_km is None:
            return AgentDecision(
                action="reject_distance",
                accepted=False,
                confidence=0.95,
                explanation="No vehicle distance is available, so the user cannot evaluate access effort.",
                source="heuristic_llm_agent",
            )

        profile_type = client.profile.profile_type
        prompt = build_agent_prompt(client, order, context)
        del prompt  # kept for transparency and future integration; not needed by the heuristic.

        if context.tariff_factor > client.profile.max_price_factor:
            return AgentDecision(
                action="reject_price",
                accepted=False,
                confidence=0.85,
                explanation="The tariff factor exceeds the user's price tolerance.",
                source="heuristic_llm_agent",
            )

        if order.distance_to_vehicle_km > client.profile.max_distance_to_vehicle_km:
            return AgentDecision(
                action="reject_distance",
                accepted=False,
                confidence=0.82,
                explanation="The nearest available vehicle is farther than the user's walking tolerance.",
                source="heuristic_llm_agent",
            )

        score = 0.58
        score += 0.18 * client.profile.urgency
        score += 0.12 * client.profile.weather_sensitivity * int(context.weather in {"rain", "snow"})
        score -= 0.20 * max(0.0, context.tariff_factor - 1.0)
        score -= 0.08 * order.distance_to_vehicle_km
        score -= 0.04 * max(0.0, context.traffic_factor - 1.0)

        if profile_type == ClientProfileType.ECONOMY:
            score -= 0.10 * max(0.0, context.tariff_factor - 1.0)
        elif profile_type == ClientProfileType.HURRY:
            score += 0.12
        elif profile_type == ClientProfileType.PRICE_SENSITIVE:
            score -= 0.18 * max(0.0, context.tariff_factor - 1.0)
        elif profile_type == ClientProfileType.DISTANCE_SENSITIVE:
            score -= 0.10 * order.distance_to_vehicle_km

        score = min(0.98, max(0.02, score))
        accepted = self.random.random() < score

        if accepted:
            action = "accept"
            explanation = "The trip conditions are acceptable for the user's profile."
        elif context.tariff_factor > 1.15:
            action = "alternative"
            explanation = "The user prefers an alternative because the tariff is high."
        else:
            action = "wait"
            explanation = "The user does not accept immediately and would wait or reconsider."

        return AgentDecision(
            action=action,
            accepted=accepted,
            confidence=round(score, 3),
            explanation=explanation,
            source="heuristic_llm_agent",
        )


class OllamaDecisionEngine:
    """Optional local LLM decision engine via Ollama.

    The engine asks a local Ollama model to return a strict JSON decision.
    If the model response is malformed, the parser falls back to a conservative
    textual interpretation instead of crashing the simulation.
    """

    def __init__(self, model: str = "llama3.2:3b", endpoint: str = "http://127.0.0.1:11434/api/generate", timeout: float = 60.0):
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout

    def decide(self, client: Client, order: Order, context: SimulationContext) -> AgentDecision:
        prompt = build_agent_prompt(client, order, context)
        payload = {
            "model": self.model,
            "prompt": (
                prompt
                + "\n\nReturn ONLY valid JSON, no markdown, no prose. "
                + "Use this schema exactly: "
                + '{"action":"accept|reject_price|reject_distance|wait|alternative",'
                + '"accepted":true/false,"explanation":"short reason"}'
            ),
            "stream": False,
            "options": {"temperature": 0.0},
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return AgentDecision(
                action="fallback_error",
                accepted=False,
                confidence=0.0,
                explanation=f"Ollama decision failed: {exc}",
                source="ollama_error",
            )

        text = raw.get("response", "").strip()
        parsed = self._parse_json_response(text)
        if parsed is not None:
            accepted = bool(parsed.get("accepted", False))
            action = str(parsed.get("action", "accept" if accepted else "alternative"))
            explanation = str(parsed.get("explanation", text[:200]))
        else:
            lowered = text.lower()
            # Conservative fallback: accept only if the model clearly says accept/true
            # and does not clearly reject.
            has_accept = '"accepted": true' in lowered or 'accepted: true' in lowered or lowered.strip().startswith("accept")
            has_reject = "reject" in lowered or '"accepted": false' in lowered or 'accepted: false' in lowered
            accepted = bool(has_accept and not has_reject)
            action = "accept" if accepted else "alternative"
            explanation = text[:300] if text else "Malformed or empty Ollama response."

        return AgentDecision(
            action=action,
            accepted=accepted,
            confidence=0.5,
            explanation=explanation,
            source="ollama_llm_agent",
        )

    @staticmethod
    def _parse_json_response(text: str) -> dict | None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Many local models wrap JSON in explanatory text. Extract the first JSON object.
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return None
        return None
