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
from datetime import datetime, timezone
from typing import Optional

from src.ai.tools import CHAT_SYSTEM_PROMPT, OLLAMA_TOOLS, ToolExecutor

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama3.2"

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
            "  ollama pull llama3.2"
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
        Ollama model name (default ``llama3.2``).

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
# Cached analysis from description + sticky posts
# ------------------------------------------------------------------

_CACHE_SYSTEM_PROMPT = (
    "You are a Skyrim mod compatibility analyst.  Given a mod description "
    "and optional sticky/pinned posts from its Nexus Mods page, extract "
    "ONLY the following four categories:\n\n"
    "1. requirements — Hard requirements: mod names that MUST be installed "
    "for this mod to work.\n"
    "2. patches — Recommended compatibility patches.\n"
    "3. known_issues — Known bugs, incompatibilities or issues.\n"
    "4. load_order — Any load-order notes or recommendations.\n\n"
    "Respond ONLY with valid JSON in this exact format:\n"
    '{"requirements": [], "patches": [], "known_issues": [], '
    '"load_order": []}\n'
    "Do NOT include any explanation or markdown."
)


def analyse_and_cache_mod(
    nexus_id: str,
    description: str,
    sticky_posts: list[str],
    db,
    model: str = DEFAULT_MODEL,
) -> dict:
    """
    Analyse a mod using its cached description and sticky posts, then
    save the result to the ``ai_mod_analysis`` table.

    Parameters
    ----------
    nexus_id : str
        The Nexus Mods mod ID.
    description : str
        The mod's full description text (from the database).
    sticky_posts : list[str]
        Text content of pinned/sticky posts (may be empty).
    db : DatabaseManager
        An open database connection.
    model : str
        Ollama model name (default ``llama3.2``).

    Returns
    -------
    dict
        The parsed analysis result with keys ``requirements``, ``patches``,
        ``known_issues``, ``load_order``.
    """
    default_result = {
        "requirements": [],
        "patches": [],
        "known_issues": [],
        "load_order": [],
    }

    if not description and not sticky_posts:
        logger.info(
            "Skipping cached analysis for %s: no description or sticky posts.",
            nexus_id,
        )
        return default_result

    ollama = _import_ollama()

    parts = []
    if description:
        parts.append(f"== MOD DESCRIPTION ==\n{description}")
    if sticky_posts:
        parts.append(
            "== STICKY / PINNED POSTS ==\n" + "\n---\n".join(sticky_posts)
        )
    if not parts:
        parts.append("No mod data available.")

    user_prompt = "\n\n".join(parts)
    logger.info(
        "Analysing mod %s with Ollama model '%s' (cached)…", nexus_id, model
    )

    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": _CACHE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw_text = response["message"]["content"]
        result = _parse_response(raw_text)
    except Exception as exc:
        logger.error("Ollama cached analysis failed for %s: %s", nexus_id, exc)
        return default_result

    analysis_record = {
        "nexus_id": str(nexus_id),
        "requirements": result.get("requirements", []),
        "patches": result.get("patches", []),
        "known_issues": result.get("known_issues", []),
        "load_order": result.get("load_order", []),
        "analyzed_by": "ollama",
        "last_analyzed": datetime.now(timezone.utc).isoformat(),
    }
    db.upsert_ai_analysis(analysis_record)
    logger.info("Cached AI analysis saved for mod %s.", nexus_id)

    return result


def chat(
    user_message: str,
    db,
    model: str = DEFAULT_MODEL,
    history: Optional[list] = None,
) -> tuple[str, list]:
    """
    Main chat function called by chat_panel.py.

    Interacts with Ollama, executes tools if the AI requests them,
    and returns the response.

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

    try:
        # Step 1: First call to AI passing the tools
        response = ollama.chat(
            model=model,
            messages=history,
            tools=OLLAMA_TOOLS,
        )

        # Step 2: Check if AI decided to use a tool
        tool_calls = (
            response.message.tool_calls
            if hasattr(response, "message")
            and hasattr(response.message, "tool_calls")
            else response.get("message", {}).get("tool_calls")
        )

        if tool_calls:
            # Append the assistant message that requested the tool calls
            if hasattr(response, "message"):
                history.append(response.message)
            else:
                history.append(response["message"])

            for tool in tool_calls:
                # Support both attribute and dict access
                if hasattr(tool, "function"):
                    tool_name = tool.function.name
                    args = tool.function.arguments
                else:
                    fn = tool.get("function", {})
                    tool_name = fn.get("name")
                    args = fn.get("arguments")

                if not tool_name:
                    logger.warning("Received tool call with no name; skipping.")
                    continue

                if args is None:
                    logger.warning(
                        "Tool call '%s' missing arguments; defaulting to empty dict.",
                        tool_name,
                        )
                    args = {}

                logger.info(
                    "AI requested tool: %s with args: %s", tool_name, args
                )

                tool_result_str = executor.execute(tool_name, args)

                # Step 3: Return tool result to AI
                history.append({
                    "role": "tool",
                    "content": tool_result_str,
                    "name": tool_name,
                })

            # Step 4: Second call so AI reads DB data and writes final response
            final_response = ollama.chat(
                model=model,
                messages=history,
            )
            if hasattr(final_response, "message"):
                history.append(final_response.message)
                return final_response.message.content, history
            else:
                msg = final_response["message"]
                history.append(msg)
                return msg.get("content", ""), history

        else:
            # No tools used — simple conversation
            if hasattr(response, "message"):
                history.append(response.message)
                return response.message.content, history
            else:
                msg = response["message"]
                history.append(msg)
                return msg.get("content", ""), history

    except Exception as e:
        logger.error("Error in Ollama chat: %s", e)
        # Fallback: try without tools if model doesn't support them
        try:
            context = f"{CHAT_SYSTEM_PROMPT}\n\nUser question: {user_message}"
            fallback_response = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": context}],
            )
            if hasattr(fallback_response, "message"):
                return fallback_response.message.content, history
            return fallback_response["message"]["content"], history
        except Exception as fallback_error:
            logger.error("Fallback also failed: %s", fallback_error)
            return f"Error processing query: {fallback_error}", history
