"""
AI function-calling tools for mod compatibility queries.

Provides tool definitions in both Ollama and Anthropic formats, plus an
executor that dispatches tool calls to the local SQLite database.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Tool definitions — Ollama format (OpenAI-compatible)
# ------------------------------------------------------------------

OLLAMA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_mod",
            "description": (
                "Search installed mods in the local database by name. "
                "Returns a list of matching mod records."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Mod name (or partial name) to search for.",
                    }
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_mod_requirements",
            "description": (
                "Get the requirements (dependencies and patches) for a mod "
                "identified by its Nexus Mods ID."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nexus_id": {
                        "type": "string",
                        "description": "The Nexus Mods numeric ID of the mod.",
                    }
                },
                "required": ["nexus_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_loot_warnings",
            "description": (
                "Get LOOT masterlist warnings and messages for a specific "
                "plugin file (e.g. 'SkyUI_SE.esp')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plugin_name": {
                        "type": "string",
                        "description": "The plugin filename (e.g. 'SkyUI_SE.esp').",
                    }
                },
                "required": ["plugin_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_patches",
            "description": (
                "Search for compatibility patches related to a mod. "
                "Looks in the requirements table for entries flagged as patches."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mod_name": {
                        "type": "string",
                        "description": "The mod name to find patches for.",
                    }
                },
                "required": ["mod_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_mod_description",
            "description": (
                "Get the AI-analyzed summary for a mod identified by its "
                "Nexus Mods ID.  Returns cached requirements, patches, "
                "known issues and load order notes extracted by AI."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nexus_id": {
                        "type": "string",
                        "description": "The Nexus Mods numeric ID of the mod.",
                    }
                },
                "required": ["nexus_id"],
            },
        },
    },
]

# ------------------------------------------------------------------
# Tool definitions — Anthropic format
# ------------------------------------------------------------------

ANTHROPIC_TOOLS = [
    {
        "name": "search_mod",
        "description": (
            "Search installed mods in the local database by name. "
            "Returns a list of matching mod records."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Mod name (or partial name) to search for.",
                }
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_mod_requirements",
        "description": (
            "Get the requirements (dependencies and patches) for a mod "
            "identified by its Nexus Mods ID."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nexus_id": {
                    "type": "string",
                    "description": "The Nexus Mods numeric ID of the mod.",
                }
            },
            "required": ["nexus_id"],
        },
    },
    {
        "name": "get_loot_warnings",
        "description": (
            "Get LOOT masterlist warnings and messages for a specific "
            "plugin file (e.g. 'SkyUI_SE.esp')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "plugin_name": {
                    "type": "string",
                    "description": "The plugin filename (e.g. 'SkyUI_SE.esp').",
                }
            },
            "required": ["plugin_name"],
        },
    },
    {
        "name": "find_patches",
        "description": (
            "Search for compatibility patches related to a mod. "
            "Looks in the requirements table for entries flagged as patches."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mod_name": {
                    "type": "string",
                    "description": "The mod name to find patches for.",
                }
            },
            "required": ["mod_name"],
        },
    },
    {
        "name": "get_mod_description",
        "description": (
            "Get the AI-analyzed summary for a mod identified by its "
            "Nexus Mods ID.  Returns cached requirements, patches, "
            "known issues and load order notes extracted by AI."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nexus_id": {
                    "type": "string",
                    "description": "The Nexus Mods numeric ID of the mod.",
                }
            },
            "required": ["nexus_id"],
        },
    },
]

# ------------------------------------------------------------------
# Chat system prompt (shared by both agents)
# ------------------------------------------------------------------

CHAT_SYSTEM_PROMPT = (
    "You are a helpful Skyrim mod compatibility assistant.  You have access "
    "to the user's local mod database and can look up installed mods, their "
    "requirements, LOOT warnings, and compatibility patches.\n\n"
    "Use the provided tools to answer questions accurately.  When you call a "
    "tool, wait for its result before composing your final answer.  Be concise "
    "and helpful."
)

# ------------------------------------------------------------------
# Tool executor
# ------------------------------------------------------------------


class ToolExecutor:
    """Execute tool calls against a :class:`DatabaseManager` instance."""

    def __init__(self, db):
        """
        Parameters
        ----------
        db : DatabaseManager
            An open database connection.
        """
        self._db = db

    def execute(self, tool_name: str, arguments: dict) -> str:
        """Run a tool and return the result as a JSON string."""
        handler = {
            "search_mod": self._search_mod,
            "get_mod_requirements": self._get_mod_requirements,
            "get_loot_warnings": self._get_loot_warnings,
            "find_patches": self._find_patches,
            "get_mod_description": self._get_mod_description,
        }.get(tool_name)

        if handler is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        try:
            result = handler(arguments)
            return json.dumps(result, default=str)
        except Exception as exc:
            logger.error("Tool '%s' failed: %s", tool_name, exc)
            return json.dumps({"error": str(exc)})

    # -- Individual tool implementations --------------------------------

    def _search_mod(self, args: dict) -> list:
        name = args.get("name", "")
        mods = self._db.search_mods_by_name(name)
        return [
            {
                "mod_id": m["mod_id"],
                "name": m["name"],
                "version": m.get("version", ""),
                "author": m.get("author", ""),
            }
            for m in mods
        ]

    def _get_mod_requirements(self, args: dict) -> list:
        nexus_id = args.get("nexus_id", "")
        try:
            mod_id = int(nexus_id)
        except (ValueError, TypeError):
            return [{"error": f"Invalid nexus_id: {nexus_id}"}]
        reqs = self._db.get_requirements(mod_id)
        return [
            {
                "required_name": r["required_name"],
                "is_patch": bool(r.get("is_patch", False)),
                "required_url": r.get("required_url", ""),
            }
            for r in reqs
        ]

    def _get_loot_warnings(self, args: dict) -> dict:
        plugin_name = args.get("plugin_name", "")
        entry = self._db.get_loot_entry(plugin_name)
        if entry is None:
            # Fall back to a partial match
            entries = self._db.search_loot_entries_by_name(plugin_name)
            if not entries:
                return {"plugin": plugin_name, "warnings": [], "note": "No LOOT data found."}
            entry = entries[0]
        return {
            "plugin": entry["name"],
            "requirements": entry.get("req", []),
            "incompatibilities": entry.get("inc", []),
            "messages": entry.get("msg", []),
        }

    def _find_patches(self, args: dict) -> list:
        mod_name = args.get("mod_name", "")
        mods = self._db.search_mods_by_name(mod_name)
        patches = []
        for mod in mods:
            reqs = self._db.get_requirements(mod["mod_id"])
            for r in reqs:
                if r.get("is_patch"):
                    patches.append({
                        "mod_name": mod["name"],
                        "patch_name": r["required_name"],
                        "url": r.get("required_url", ""),
                    })
        # Also check if any of the already-found mods are patches themselves
        for m in mods:
            if "patch" in m["name"].lower() and m["name"] not in [
                p["patch_name"] for p in patches
            ]:
                patches.append({
                    "mod_name": mod_name,
                    "patch_name": m["name"],
                    "url": m.get("mod_url", ""),
                })
        return patches

    def _get_mod_description(self, args: dict) -> dict:
        nexus_id = args.get("nexus_id", "")
        analysis = self._db.get_ai_analysis(str(nexus_id))
        if analysis is None:
            return {
                "nexus_id": nexus_id,
                "note": "No AI analysis cached for this mod.",
            }
        return {
            "nexus_id": analysis["nexus_id"],
            "requirements": analysis.get("requirements", []),
            "patches": analysis.get("patches", []),
            "known_issues": analysis.get("known_issues", []),
            "load_order": analysis.get("load_order", []),
            "analyzed_by": analysis.get("analyzed_by", ""),
            "last_analyzed": analysis.get("last_analyzed", ""),
        }
