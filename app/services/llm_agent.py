"""Claude-backed fertilizer advisor.

Given the current sensor readings and the active crop profile's target ranges,
asks Claude to recommend dosing actions. Output is *structured* (via tool use)
so it can be rendered safely and fed straight into ActuatorHub.dose() once the
user approves.
"""

import os
import json
import logging

import anthropic
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

MODEL = "claude-sonnet-4-6"

# Pump names must match ActuatorHub (_PUMP_CONFIG in actuators.py).
_PUMP_NAMES = ["Nutrient A", "Nutrient B", "pH Up", "pH Down", "Water"]

_RECOMMEND_TOOL = {
    "name": "recommend_dosing",
    "description": (
        "Provide fertilizer/pH dosing recommendations based on the current "
        "sensor readings and the crop's target ranges."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "One or two sentences on the overall state and rationale.",
            },
            "actions": {
                "type": "array",
                "description": "Dosing actions to bring readings toward target. May be empty if all nominal.",
                "items": {
                    "type": "object",
                    "properties": {
                        "pump": {"type": "string", "enum": _PUMP_NAMES},
                        "amount_ml": {"type": "number", "description": "Amount to dispense in millilitres."},
                        "reason": {"type": "string", "description": "Why this action, referencing the relevant reading."},
                    },
                    "required": ["pump", "amount_ml", "reason"],
                },
            },
        },
        "required": ["summary", "actions"],
    },
}


class LLMError(Exception):
    """Raised when a recommendation cannot be obtained."""


def _client() -> anthropic.Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise LLMError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")
    return anthropic.Anthropic(api_key=key)


def _build_prompt(readings: dict, targets: dict, profile_name: str) -> str:
    lines = [
        f"Crop profile: {profile_name}",
        "",
        "Current readings vs target ranges:",
    ]
    units = {"EC": "mS/cm", "PH": "pH", "Temperature": "°C", "Humidity": "%"}
    for name, tgt in targets.items():
        val = readings.get(name)
        val_str = f"{val:.2f}" if isinstance(val, (int, float)) and val == val else "n/a"
        lines.append(
            f"  - {name}: {val_str} {units.get(name, '')}"
            f" (target {tgt['min']}–{tgt['max']})"
        )
    lines += [
        "",
        "Available pumps: Nutrient A, Nutrient B (raise EC), "
        "pH Up, pH Down (adjust pH), Water (dilute / lower EC).",
        "Temperature and Humidity cannot be dosed — only note them.",
        "Recommend conservative dosing to move readings toward target. "
        "If everything is within range, return an empty actions list.",
        "Call the recommend_dosing tool with your answer.",
    ]
    return "\n".join(lines)


def recommend(readings: dict, targets: dict, profile_name: str = "") -> dict:
    """Ask Claude for dosing recommendations.

    Returns {"summary": str, "actions": [{"pump", "amount_ml", "reason"}, ...]}.
    Raises LLMError on any failure (missing key, network, malformed response).
    """
    client = _client()
    prompt = _build_prompt(readings, targets, profile_name)

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=[_RECOMMEND_TOOL],
            tool_choice={"type": "tool", "name": "recommend_dosing"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        logger.error("LLM request failed: %s", exc)
        raise LLMError(f"Request to Claude failed: {exc}") from exc

    for block in message.content:
        if block.type == "tool_use" and block.name == "recommend_dosing":
            data = block.input
            # block.input is already a dict, but be defensive.
            if isinstance(data, str):
                data = json.loads(data)
            data.setdefault("summary", "")
            data.setdefault("actions", [])
            return data

    raise LLMError("Claude did not return a structured recommendation.")
