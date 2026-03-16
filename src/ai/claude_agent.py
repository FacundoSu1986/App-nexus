"""
Premium AI agent powered by the Anthropic Claude API.

Same interface as ``local_agent`` but uses Claude for smarter/faster analysis.
The user must supply their own Anthropic API key.

Also provides a conversational ``chat`` interface that uses Anthropic's
``tool_use`` feature so the model can query the local mod database.

Attribution: **Powered by Claude** (Anthropic) — displayed in the UI when
this agent is used.
"""

import json
import logging
from typing import Optional

from src.ai.tools import ANTHROPIC_TOOLS, CHAT_SYSTEM_PROMPT, ToolExecutor

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-20250514"

ATTRIBUTION = "Powered by Claude"

_SYSTEM_PROMPT = (
    "You are a Skyrim mod compatibility analyst.  Given the raw HTML/text "
    "from a Nexus Mods page, extract the following four categories:\n"
    "1. requirements — a JSON list of mod names that this mod requires.\n"
    "2. patches — a JSON list of compatibility patches mentioned.\n"
    "3. known_issues — a JSON list of known issues or incompatibilities "
    "reported by users.\n"
    "4. load_order — a JSON list of load-order notes or recommendations.\n\n"
    "Respond ONLY with valid JSON in this exact format:\n"
    '{"requirements": [], "patches": [], "known_issues": [], '
    '"load_order": []}\n'
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
    default = {
        "requirements": [],
        "patches": [],
        "known_issues": [],
        "load_order": [],
    }
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
            "load_order": data.get("load_order", []),
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
        ``{"requirements": [...], "patches": [...], "known_issues": [...], "load_order": [...]}``
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


# ------------------------------------------------------------------
# Conversational chat with function calling (tool_use)
# ------------------------------------------------------------------

_MAX_TOOL_ROUNDS = 5


def chat(
    user_message: str,
    db,
    api_key: str,
    model: str = DEFAULT_MODEL,
    history: Optional[list] = None,
) -> tuple[str, list]:
    """
    Send a conversational message and let Claude call tools as needed.

    Parameters
    ----------
    user_message : str
        The user's question or message.
    db : DatabaseManager
        An open database connection for tool execution.
    api_key : str
        Anthropic API key.
    model : str
        Claude model name.
    history : list or None
        Previous message history (list of dicts).  A new list is created
        when ``None``.

    Returns
    -------
    tuple[str, list]
        ``(assistant_reply, updated_history)``
    """
    anthropic = _import_anthropic()
    client = anthropic.Anthropic(api_key=api_key)
    executor = ToolExecutor(db)

    if history is None:
        history = []

    history.append({"role": "user", "content": user_message})

    for _ in range(_MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=CHAT_SYSTEM_PROMPT,
            tools=ANTHROPIC_TOOLS,
            messages=history,
        )

        # Collect text blocks and tool-use blocks from the response
        assistant_content = response.content
        history.append({"role": "assistant", "content": assistant_content})

        # Check if the model wants to call any tools
        tool_use_blocks = [
            block for block in assistant_content
            if getattr(block, "type", None) == "tool_use"
        ]

        if not tool_use_blocks:
            # Extract text from the response
            text_parts = [
                block.text
                for block in assistant_content
                if getattr(block, "type", None) == "text"
            ]
            return "\n".join(text_parts), history

        # Execute tools and feed results back
        tool_results = []
        for block in tool_use_blocks:
            tool_name = block.name
            arguments = block.input
            logger.info("Claude tool call: %s(%s)", tool_name, arguments)

            result_str = executor.execute(tool_name, arguments)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_str,
            })

        history.append({"role": "user", "content": tool_results})

    # Safety: extract text from last assistant response
    text_parts = []
    last = history[-1]
    if isinstance(last.get("content"), list):
        for block in last["content"]:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
    return "\n".join(text_parts) if text_parts else "", history
