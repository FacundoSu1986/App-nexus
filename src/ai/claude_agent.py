"""
Premium AI agent powered by the Anthropic Claude API.

Same interface as ``local_agent`` but uses Claude for smarter/faster analysis.
The user must supply their own Anthropic API key.

Attribution: **Powered by Claude** (Anthropic) — displayed in the UI when
this agent is used.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-20250514"

ATTRIBUTION = "Powered by Claude"

_SYSTEM_PROMPT = (
    "You are a Skyrim mod compatibility analyst.  Given the raw HTML/text "
    "from a Nexus Mods page, extract:\n"
    "1. requirements — a JSON list of mod names that this mod requires.\n"
    "2. patches — a JSON list of compatibility patches mentioned.\n"
    "3. known_issues — a JSON list of known issues or incompatibilities "
    "reported by users.\n\n"
    "Respond ONLY with valid JSON in this exact format:\n"
    '{"requirements": [], "patches": [], "known_issues": []}\n'
    "Do NOT include any explanation or markdown."
)


def _import_anthropic():
    """Import anthropic lazily to avoid hard dependency at import time."""
    try:
        import anthropic
        return anthropic
    except ImportError:
        raise ImportError(
            "Anthropic Python package is not installed.  Run:\n"
            "  pip install anthropic"
        )


def _build_user_prompt(page_data: dict) -> str:
    """Build the user prompt from extracted page data."""
    parts = []
    if page_data.get("requirements_html"):
        parts.append(
            f"== REQUIREMENTS SECTION ==\n{page_data['requirements_html']}"
        )
    if page_data.get("description_html"):
        parts.append(
            f"== DESCRIPTION SECTION ==\n{page_data['description_html']}"
        )
    if page_data.get("posts_html"):
        parts.append(
            f"== POSTS / COMMENTS ==\n{page_data['posts_html']}"
        )
    if not parts:
        parts.append("No mod page data was extracted.")
    return "\n\n".join(parts)


def _parse_response(raw: str) -> dict:
    """Best-effort parse of the Claude response into our expected schema."""
    default = {"requirements": [], "patches": [], "known_issues": []}
    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        data = json.loads(cleaned)
        return {
            "requirements": data.get("requirements", []),
            "patches": data.get("patches", []),
            "known_issues": data.get("known_issues", []),
        }
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Could not parse Claude response as JSON: %s", raw[:200])
        return default


def analyse_mod(
    page_data: dict,
    api_key: str,
    model: str = DEFAULT_MODEL,
) -> dict:
    """
    Use the Anthropic Claude API to analyse extracted mod page data.

    Parameters
    ----------
    page_data : dict
        Output of ``nexus_browser.extract_mod_page_data``.
    api_key : str
        The user's Anthropic API key.
    model : str
        Claude model name (default ``claude-sonnet-4-20250514``).

    Returns
    -------
    dict
        ``{"requirements": [...], "patches": [...], "known_issues": [...]}``
    """
    anthropic = _import_anthropic()

    user_prompt = _build_user_prompt(page_data)
    logger.info("Sending mod data to Claude model '%s'…", model)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_prompt},
            ],
        )
        raw_text = message.content[0].text
        return _parse_response(raw_text)
    except Exception as exc:
        logger.error("Claude analysis failed: %s", exc)
        raise RuntimeError(
            f"Claude analysis failed: {exc}\n\n"
            "Make sure your Anthropic API key is valid."
        ) from exc
