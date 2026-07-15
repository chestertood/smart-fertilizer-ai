"""Claude-backed fertilizer advisor.

Given the current sensor readings and the active crop profile's target ranges,
asks Claude to recommend dosing actions. Output is *structured* (via tool use)
so it can be rendered safely and fed straight into ActuatorHub.dose() once the
user approves.
"""

import os
import json
import base64
import logging

import anthropic
from dotenv import load_dotenv

from app.services import knowledge

logger = logging.getLogger(__name__)

load_dotenv()

DEFAULT_MODEL = "claude-sonnet-5"

# Models selectable from the chat panel. (id, label, short description shown
# under the label). Kept here — not in the UI — so a future Telegram bridge
# can offer the same list.
AVAILABLE_MODELS = [
    ("claude-opus-4-8", "Opus 4.8", "Most capable"),
    ("claude-sonnet-5", "Sonnet 5", "Balanced"),
    ("claude-haiku-4-5", "Haiku 4.5", "Fast & cheap"),
]

# USD per million tokens (input, output) — for the Settings cost estimate.
# Sticker prices as of 2026-06; update when Anthropic changes pricing.
PRICING_PER_MTOK = {
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Rough spend estimate from token counts. Unknown models price as Opus."""
    inp, out = PRICING_PER_MTOK.get(model, PRICING_PER_MTOK["claude-opus-4-8"])
    return input_tokens / 1_000_000 * inp + output_tokens / 1_000_000 * out


def _usage_dict(message, model: str) -> dict:
    """Flatten message.usage for local logging. Cache fields are counted into
    input so totals stay honest if caching is ever enabled."""
    u = getattr(message, "usage", None)
    inp = (getattr(u, "input_tokens", 0) or 0) \
        + (getattr(u, "cache_creation_input_tokens", 0) or 0) \
        + (getattr(u, "cache_read_input_tokens", 0) or 0)
    out = getattr(u, "output_tokens", 0) or 0
    return {"model": model, "input_tokens": inp, "output_tokens": out}

# Attachment media types Claude accepts as image blocks.
_IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
# Plain-text attachment extensions inlined into the message text.
_TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".log"}

# Pump names must match ActuatorHub (_PUMP_CONFIG in actuators.py).
_PUMP_NAMES = ["Nutrient A", "Nutrient B", "pH Up", "pH Down", "Water"]

# Matches config.i18n.LANGUAGES — the app's language toggle overrides
# whatever language the operator happens to type in, so replies always match
# the selected UI language.
_LANG_NAMES = {"en": "English", "th": "Thai"}


def _lang_instruction(lang: str) -> str:
    name = _LANG_NAMES.get(lang, "English")
    return f"Always reply in {name}, regardless of what language the operator writes in."

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


def build_user_content(text: str, attachments: list[dict] | None = None):
    """Build Anthropic message content from text + optional attachments.

    `attachments` is a list of {"name": str, "data": bytes}. Images become
    vision blocks, PDFs become document blocks, small text files are inlined,
    anything else is mentioned by name only. UI-independent so a Telegram
    bridge (photos/files sent to the bot) can reuse it as-is.

    Returns a plain string when there are no attachments (keeps history
    readable), else a list of content blocks.
    """
    if not attachments:
        return text
    blocks = []
    notes = []
    for att in attachments:
        name = att.get("name", "file")
        data = att.get("data") or b""
        ext = os.path.splitext(name)[1].lower()
        if ext in _IMAGE_TYPES:
            blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _IMAGE_TYPES[ext],
                    "data": base64.standard_b64encode(data).decode("ascii"),
                },
            })
        elif ext == ".pdf":
            blocks.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(data).decode("ascii"),
                },
            })
        elif ext in _TEXT_EXTS:
            try:
                body = data.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                body = "(unreadable)"
            # Cap inlined text so a huge log can't blow the context window.
            if len(body) > 20_000:
                body = body[:20_000] + "\n…(truncated)"
            notes.append(f'Attached file "{name}":\n{body}')
        else:
            notes.append(f'(The operator attached a file "{name}" of an '
                         "unsupported type; contents not included.)")
    full_text = "\n\n".join([text, *notes]) if notes else text
    blocks.append({"type": "text", "text": full_text or "(no message)"})
    return blocks


def _client() -> anthropic.Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise LLMError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")
    return anthropic.Anthropic(api_key=key)


def _build_prompt(
    readings: dict, targets: dict, profile_name: str, volume_liters: float | None = None,
    lang: str = "en",
) -> str:
    lines = [
        _lang_instruction(lang),
        "",
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
    if volume_liters is not None:
        lines.append(f"  - Reservoir volume: ~{volume_liters:.1f} liters")
    lines += [
        "",
        "Available pumps: Nutrient A, Nutrient B (raise EC), "
        "pH Up, pH Down (adjust pH), Water (dilute / lower EC).",
        "Temperature and Humidity cannot be dosed — only note them.",
        "Size dosing amounts (ml) proportionally to the reservoir volume above "
        "when given — the same EC correction needs much more concentrate in a "
        "large tank than a small one. If volume is not given, assume a small "
        "~20L reservoir and say so in the reason.",
        "Recommend conservative dosing to move readings toward target. "
        "If everything is within range, return an empty actions list.",
        "Call the recommend_dosing tool with your answer.",
    ]
    return "\n".join(lines)


def _last_user_text(history: list) -> str:
    """Latest user message as plain text (flattens content blocks). Used to
    build a retrieval query for the chat flow."""
    for msg in reversed(history):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
    return ""


def _knowledge_block(query: str) -> str:
    """Retrieve crop knowledge for `query` and format it for prompt injection.
    Returns '' when nothing is retrieved (best-effort — never raises)."""
    hits = knowledge.retrieve(query, k=4)
    if not hits:
        return ""
    body = "\n\n".join(f"[{h['source']}]\n{h['text']}" for h in hits)
    return "\n\nReference knowledge (curated crop data — use if relevant):\n" + body


def recommend(
    readings: dict, targets: dict, profile_name: str = "", volume_liters: float | None = None,
    lang: str = "en", model: str | None = None,
) -> dict:
    """Ask Claude for dosing recommendations.

    `volume_liters`, if known, lets Claude size ml amounts to the actual
    reservoir size instead of guessing a generic tank. `lang` ("en"/"th")
    forces the summary/reason text to that language, matching the app's UI
    language toggle rather than guessing from input. `model` overrides
    DEFAULT_MODEL (the operator's pick from the chat panel).

    Returns {"summary": str, "actions": [{"pump", "amount_ml", "reason"}, ...],
    "usage": {"model", "input_tokens", "output_tokens"}}.
    Raises LLMError on any failure (missing key, network, malformed response).
    """
    client = _client()
    prompt = _build_prompt(readings, targets, profile_name, volume_liters, lang)
    prompt += _knowledge_block(f"{profile_name} EC pH dosing target ranges")

    try:
        message = client.messages.create(
            model=model or DEFAULT_MODEL,
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
            data["usage"] = _usage_dict(message, model or DEFAULT_MODEL)
            return data

    raise LLMError("Claude did not return a structured recommendation.")


# ---------------------------------------------------------------------------
# Free-form chat assistant (for the floating chat widget)
# ---------------------------------------------------------------------------

_CHAT_SYSTEM = (
    "You are the assistant inside a Smart Fertilizer hydroponic control app. "
    "Answer the operator's questions about their sensor readings, fertigation, "
    "EC/pH/temperature/humidity, and dosing. Be concise and practical. "
    "You can advise but you do NOT control hardware directly — the operator "
    "doses manually. If asked to do something outside fertigation, say so briefly.\n\n"
    "When the operator asks you to set up / configure target parameters for a "
    "crop (e.g. 'I'm going to grow kale, set the parameters for me'), call the "
    "set_parameters tool with appropriate min/max ranges for all four sensors. "
    "The operator will review and approve before anything is applied.\n\n"
    "When the operator describes growth stages for a crop (e.g. 'I'm growing "
    "kale, set up growth stages: seedling, growing, mature' or gives you the "
    "stage names/durations), call the set_growth_stages tool instead — propose "
    "each stage with a name, duration in days, and its own target ranges "
    "(early stages usually want lower EC, later stages higher). If the "
    "operator doesn't give durations, use realistic typical values for that "
    "crop. The operator approves before stages are created and planting starts."
)

# Sensor keys must match config.sensors.SENSORS / state.targets.
_RANGE_SCHEMA = {
    "type": "object",
    "properties": {
        "min": {"type": "number"},
        "max": {"type": "number"},
    },
    "required": ["min", "max"],
}

_SET_PARAMS_TOOL = {
    "name": "set_parameters",
    "description": (
        "Propose new target min/max ranges for the crop the operator wants to "
        "grow. Use realistic hydroponic fertigation values. The operator "
        "approves before they are saved."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "crop": {"type": "string", "description": "Crop name as stated by the operator."},
            "rationale": {
                "type": "string",
                "description": "Short explanation of the chosen ranges, in the operator's language.",
            },
            "targets": {
                "type": "object",
                "properties": {
                    "EC": _RANGE_SCHEMA,
                    "PH": _RANGE_SCHEMA,
                    "Temperature": _RANGE_SCHEMA,
                    "Humidity": _RANGE_SCHEMA,
                },
                "required": ["EC", "PH", "Temperature", "Humidity"],
            },
        },
        "required": ["crop", "rationale", "targets"],
    },
}

_SET_GROWTH_TOOL = {
    "name": "set_growth_stages",
    "description": (
        "Propose a sequence of growth stages (e.g. seedling, growing, mature) "
        "for the crop the operator wants to grow, each with its own duration "
        "and target ranges. The operator approves before stages are created "
        "and the grow cycle starts (planting date = today)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "crop": {"type": "string", "description": "Crop name as stated by the operator."},
            "rationale": {
                "type": "string",
                "description": "Short explanation of the stage breakdown, in the operator's language.",
            },
            "stages": {
                "type": "array",
                "description": "Ordered growth stages, earliest first.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Stage name, e.g. 'Seedling'."},
                        "duration_days": {"type": "integer", "description": "How many days this stage lasts."},
                        "targets": {
                            "type": "object",
                            "properties": {
                                "EC": _RANGE_SCHEMA,
                                "PH": _RANGE_SCHEMA,
                                "Temperature": _RANGE_SCHEMA,
                                "Humidity": _RANGE_SCHEMA,
                            },
                            "required": ["EC", "PH", "Temperature", "Humidity"],
                        },
                    },
                    "required": ["name", "duration_days", "targets"],
                },
            },
        },
        "required": ["crop", "rationale", "stages"],
    },
}


def _context_block(
    readings: dict, targets: dict, profile_name: str, volume_liters: float | None = None
) -> str:
    units = {"EC": "mS/cm", "PH": "pH", "Temperature": "°C", "Humidity": "%"}
    lines = [f"Current crop profile: {profile_name or 'n/a'}", "Live readings:"]
    for name in ("EC", "PH", "Temperature", "Humidity"):
        val = readings.get(name)
        val_str = f"{val:.2f}" if isinstance(val, (int, float)) and val == val else "n/a"
        tgt = targets.get(name, {})
        rng = f" (target {tgt['min']}–{tgt['max']})" if tgt else ""
        lines.append(f"  - {name}: {val_str} {units.get(name, '')}{rng}")
    if volume_liters is not None:
        lines.append(f"  - Reservoir volume: ~{volume_liters:.1f} liters")
        lines.append(
            "When discussing dosing amounts, size them proportionally to this "
            "reservoir volume, not a generic guess."
        )
    return "\n".join(lines)


def chat(
    history: list, readings: dict, targets: dict, profile_name: str = "",
    volume_liters: float | None = None, lang: str = "en", model: str | None = None,
) -> dict:
    """Free-form Q&A. `history` is a list of {"role", "content"} messages
    (user/assistant); user content may be a plain string or content blocks
    from build_user_content() when files/images are attached. Current sensor
    context is injected as a system block so the assistant can reference live
    values. `volume_liters`, if known, lets Claude size any dosing math to the
    actual reservoir. `lang` ("en"/"th") forces replies to that language,
    matching the app's UI language toggle rather than guessing from whatever
    language the operator typed in. `model` overrides DEFAULT_MODEL.

    Returns {"text": str, "param_proposal": dict | None, "growth_proposal":
    dict | None, "usage": {"model", "input_tokens", "output_tokens"}}.
    When the operator asks to configure a crop, Claude calls set_parameters and
    `param_proposal` carries {"crop", "rationale", "targets": {sensor: {min,max}}}.
    When the operator describes growth stages, Claude calls set_growth_stages and
    `growth_proposal` carries {"crop", "rationale", "stages": [{"name",
    "duration_days", "targets"}, ...]}. Either way the UI renders an approve
    card before anything is applied. Raises LLMError on failure."""
    client = _client()
    system = (
        _CHAT_SYSTEM + "\n\n" + _lang_instruction(lang) + "\n\n"
        + _context_block(readings, targets, profile_name, volume_liters)
        + _knowledge_block(_last_user_text(history) or profile_name)
    )
    try:
        message = client.messages.create(
            model=model or DEFAULT_MODEL,
            max_tokens=1536,
            system=system,
            tools=[_SET_PARAMS_TOOL, _SET_GROWTH_TOOL],
            messages=history,
        )
    except Exception as exc:
        logger.error("LLM chat failed: %s", exc)
        raise LLMError(f"Request to Claude failed: {exc}") from exc

    text_parts = [b.text for b in message.content if getattr(b, "type", None) == "text"]
    param_proposal = None
    growth_proposal = None
    for block in message.content:
        if getattr(block, "type", None) != "tool_use":
            continue
        data = block.input
        if isinstance(data, str):
            data = json.loads(data)
        if block.name == "set_parameters":
            param_proposal = data
        elif block.name == "set_growth_stages":
            growth_proposal = data

    text = "\n".join(text_parts).strip()
    if not text:
        proposal = param_proposal or growth_proposal
        if proposal:
            text = proposal.get("rationale", "")
    return {
        "text": text or "(no reply)",
        "param_proposal": param_proposal,
        "growth_proposal": growth_proposal,
        "usage": _usage_dict(message, model or DEFAULT_MODEL),
    }
