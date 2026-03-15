"""
Claude API agent for premium mod content analysis.

Uses the Anthropic Python SDK to send mod page content to Claude and receive
structured JSON analysis.

The API key is accepted at call time and never stored by this module.
UI must display "Powered by Claude" attribution when this agent is used.
"""

import json
import logging

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

# Default Claude model to use
DEFAULT_MODEL = "claude-3-haiku-20240307"


def analyze_mod_content(
    content: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
) -> dict:
    """
    Analyse mod page content using the Anthropic Claude API.

    Parameters
    ----------
    content:
        Plain-text content extracted from the Nexus Mods page.
    api_key:
        Anthropic API key provided by the user at runtime.
    model:
        Claude model identifier (default: claude-3-haiku-20240307).

    Returns
    -------
    dict with keys ``requirements``, ``patches``, ``known_issues``.
    On error an additional ``error`` key is present with a description,
    and the list keys contain empty lists.

    UI note: Display "Powered by Claude" attribution when showing results
    from this function.
    """
    if not api_key or not api_key.strip():
        return _fallback("No Anthropic API key provided.")

    try:
        import anthropic  # type: ignore
    except ImportError:
        return _fallback(
            "Anthropic package is not installed. Run: pip install anthropic>=0.20.0"
        )

    prompt = _ANALYSIS_PROMPT_TEMPLATE.format(content=content[:8000])

    try:
        client = anthropic.Anthropic(api_key=api_key.strip())
        message = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text: str = message.content[0].text
    except Exception as exc:
        logger.error("Anthropic API request failed: %s", exc)
        return _fallback(f"Claude API request failed: {exc}")

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
        logger.error("Failed to parse Claude response as JSON: %s", exc)
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
        result[key] = [str(item) for item in value]

    return result


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` code fences from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:] if len(lines) > 1 else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        text = "\n".join(inner)
    return text.strip()


def _fallback(error_message: str) -> dict:
    """Return a safe fallback result with an error field."""
    logger.warning("Claude agent fallback: %s", error_message)
    return {
        "requirements": [],
        "patches": [],
        "known_issues": [],
        "error": error_message,
    }
