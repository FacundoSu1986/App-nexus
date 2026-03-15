"""
Local AI agent powered by Ollama (free, runs entirely on the user's machine).

Analyses raw HTML/text extracted by the Playwright browser agent and returns
structured JSON with requirements, patches, and known issues.

Requires Ollama to be installed and running locally with a supported model
(llama3 or mistral).
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama3"

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


def _import_ollama():
    """Import ollama lazily to avoid hard dependency at import time."""
    try:
        import ollama
        return ollama
    except ImportError:
        raise ImportError(
            "Ollama Python package is not installed.  Run:\n"
            "  pip install ollama\n\n"
            "You also need the Ollama server running locally.\n"
            "Download it from https://ollama.com and then run:\n"
            "  ollama pull llama3"
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
    """Best-effort parse of the model response into our expected schema."""
    default = {"requirements": [], "patches": [], "known_issues": []}
    try:
        # Strip markdown code fences if present
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
        logger.warning("Could not parse Ollama response as JSON: %s", raw[:200])
        return default


def analyse_mod(
    page_data: dict,
    model: str = DEFAULT_MODEL,
) -> dict:
    """
    Use a local Ollama model to analyse extracted mod page data.

    Parameters
    ----------
    page_data : dict
        Output of ``nexus_browser.extract_mod_page_data``.
    model : str
        Ollama model name (default ``llama3``).

    Returns
    -------
    dict
        ``{"requirements": [...], "patches": [...], "known_issues": [...]}``
    """
    ollama = _import_ollama()

    user_prompt = _build_user_prompt(page_data)
    logger.info("Sending mod data to Ollama model '%s'…", model)

    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw_text = response["message"]["content"]
        return _parse_response(raw_text)
    except Exception as exc:
        logger.error("Ollama analysis failed: %s", exc)
        raise RuntimeError(
            f"Ollama analysis failed: {exc}\n\n"
            "Make sure the Ollama server is running (ollama serve) "
            f"and the model '{model}' is pulled (ollama pull {model})."
        ) from exc
