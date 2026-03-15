"""
Local AI agent powered by Ollama (free, runs entirely on the user's machine).

Analyses raw HTML/text extracted by the Playwright browser agent and returns
structured JSON with requirements, patches, and known issues.

Also provides a conversational ``chat`` interface that uses Ollama's function
calling (``tools`` parameter) so the model can query the local mod database.

Requires Ollama to be installed and running locally with a supported model
(llama3 or mistral).
"""

import json
import logging
from typing import Optional

from src.ai.tools import CHAT_SYSTEM_PROMPT, OLLAMA_TOOLS, ToolExecutor

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama3"

_SYSTEM_PROMPT = (
    "You are a Skyrim mod compatibility analyst.  Given the raw HTML/text "
    "from a Nexus Mods page, extract the following four categories:\n\n"
    "1. requirements — Hard dependencies: mod names that MUST be installed "
    "for this mod to work (e.g. SKSE64, SkyUI, Address Library).  "
    "Include every mod listed in the Requirements tab or description.\n\n"
    "2. patches — Recommended compatibility patches between this mod and "
    "other mods (e.g. 'Mod X - Mod Y Compatibility Patch').  Include the "
    "names of both mods involved if possible.\n\n"
    "3. known_issues — Known incompatibilities or conflicts reported by "
    "users or the mod author (e.g. 'Incompatible with Mod Z', 'CTD when "
    "used with ENB').  Include specifics when available.\n\n"
    "4. load_order — Any load-order recommendations mentioned by the author "
    "or users (e.g. 'Load after USSEP', 'Place near bottom of load order')."
    "\n\n"
    "Respond ONLY with valid JSON in this exact format:\n"
    '{"requirements": [], "patches": [], "known_issues": [], '
    '"load_order": []}\n'
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
    default = {
        "requirements": [],
        "patches": [],
        "known_issues": [],
        "load_order": [],
    }
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
            "load_order": data.get("load_order", []),
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
        ``{"requirements": [...], "patches": [...], "known_issues": [...],
        "load_order": [...]}``
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


# ------------------------------------------------------------------
# Conversational chat with function calling
# ------------------------------------------------------------------

_MAX_TOOL_ROUNDS = 5


def chat(
    user_message: str,
    db,
    model: str = DEFAULT_MODEL,
    history: Optional[list] = None,
) -> tuple[str, list]:
    """
    Send a conversational message and let the model call tools as needed.

    Parameters
    ----------
    user_message : str
        The user's question or message.
    db : DatabaseManager
        An open database connection for tool execution.
    model : str
        Ollama model name.
    history : list or None
        Previous message history (list of dicts).  A new list is created
        when ``None``.

    Returns
    -------
    tuple[str, list]
        ``(assistant_reply, updated_history)``
    """
    ollama = _import_ollama()
    executor = ToolExecutor(db)

    if history is None:
        history = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]

    history.append({"role": "user", "content": user_message})

    for _ in range(_MAX_TOOL_ROUNDS):
        response = ollama.chat(
            model=model,
            messages=history,
            tools=OLLAMA_TOOLS,
        )

        msg = response["message"]
        history.append(msg)

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            # No more tool calls — the model produced a final text response
            return msg.get("content", ""), history

        # Execute each requested tool and feed results back
        for call in tool_calls:
            fn = call["function"]
            tool_name = fn["name"]
            arguments = fn.get("arguments", {})
            logger.info("Ollama tool call: %s(%s)", tool_name, arguments)

            result_str = executor.execute(tool_name, arguments)
            history.append({
                "role": "tool",
                "content": result_str,
            })

    # Safety: if we exhaust rounds, return whatever the last message was
    return history[-1].get("content", ""), history
