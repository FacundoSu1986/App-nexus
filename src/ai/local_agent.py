"""
Local AI agent using Ollama for offline mod content analysis.

Uses llama3 or mistral (user's choice) to parse extracted mod page content
and return structured JSON with requirements, patches, and known issues.

If Ollama is not installed or not reachable the function returns a safe
fallback structure with an ``error`` field so the UI can display a helpful
message.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_ANALYSIS_PROMPT_TEMPLATE = """\
You are a mod compatibility analyser for Skyrim Special Edition mods hosted on Nexus Mods.

Analyse the following mod page content and extract:
1. "requirements" — a list of mods or tools that this mod requires (e.g. SKSE64, SkyUI, etc.)
2. "patches" — a list of compatibility patches mentioned by the author or users
3. "known_issues" — a list of known bugs, conflicts, or incompatibilities mentioned in comments

Return ONLY valid JSON with exactly this schema (no extra keys, no markdown):
{{
  "requirements": ["<mod name>", ...],
  "patches": ["<patch name>", ...],
  "known_issues": ["<description>", ...]
}}

Mod page content:
{content}
"""

# Expected keys in a valid analysis result
_REQUIRED_KEYS = {"requirements", "patches", "known_issues"}


def analyze_mod_content(
    content: str,
    model: str = "llama3",
) -> dict:
    """
    Analyse mod page content using a locally running Ollama model.

    Parameters
    ----------
    content:
        Plain-text content extracted from the Nexus Mods page (requirements
        section + comments).
    model:
        Ollama model identifier, e.g. ``"llama3"`` or ``"mistral"``.

    Returns
    -------
    dict with keys ``requirements``, ``patches``, ``known_issues``.
    On error an additional ``error`` key is present and the list keys
    contain empty lists.
    """
    try:
        import ollama  # type: ignore
    except ImportError:
        logger.warning("Ollama package not installed.")
        return _fallback("Ollama is not installed. Run: pip install ollama>=0.1.0")

    prompt = _ANALYSIS_PROMPT_TEMPLATE.format(content=content[:8000])

    try:
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text: str = response["message"]["content"]
    except Exception as exc:
        logger.error("Ollama request failed: %s", exc)
        return _fallback(
            f"Ollama is not reachable or the model '{model}' is not available. "
            f"Make sure Ollama is running and the model is pulled. Error: {exc}"
        )

    return _parse_response(raw_text)


# ------------------------------------------------------------------
# Internal helpers (also used by tests)
# ------------------------------------------------------------------

def _parse_response(raw_text: str) -> dict:
    """
    Attempt to parse a raw LLM response into the expected dict schema.

    Strips markdown code fences if present, then JSON-parses and validates.
    Returns a fallback structure on any parse/validation error.
    """
    cleaned = _strip_markdown_fences(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Ollama response as JSON: %s", exc)
        return _fallback(f"Could not parse AI response as JSON: {exc}")

    return _validate_schema(data)


def _validate_schema(data: object) -> dict:
    """Ensure the parsed data matches the expected schema."""
    if not isinstance(data, dict):
        return _fallback("AI response was not a JSON object.")

    missing = _REQUIRED_KEYS - data.keys()
    if missing:
        return _fallback(f"AI response missing keys: {missing}")

    result: dict = {}
    for key in _REQUIRED_KEYS:
        value = data[key]
        if not isinstance(value, list):
            return _fallback(f"AI response key '{key}' is not a list.")
        # Ensure every item is a string
        result[key] = [str(item) for item in value]

    return result


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` code fences from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first line (```json or ```) and last line (```)
        inner = lines[1:] if len(lines) > 1 else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        text = "\n".join(inner)
    return text.strip()


def _fallback(error_message: str) -> dict:
    """Return a safe fallback result with an error field."""
    logger.warning("Local agent fallback: %s", error_message)
    return {
        "requirements": [],
        "patches": [],
        "known_issues": [],
        "error": error_message,
    }
