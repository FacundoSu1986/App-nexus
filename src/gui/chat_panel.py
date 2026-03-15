"""
Conversational AI chat panel.

Provides a scrollable message history and input field that lets users ask
questions about their mod setup.  The panel delegates to either the local
Ollama agent or the Claude agent depending on user configuration.
"""

import logging
import threading
import tkinter as tk
from tkinter import ttk
from typing import Optional

logger = logging.getLogger(__name__)


class ChatPanel(ttk.LabelFrame):
    """Chat panel widget for conversational AI queries."""

    def __init__(self, parent, db, **kwargs):
        super().__init__(parent, text="AI Chat", **kwargs)
        self._db = db
        self._history_ollama: Optional[list] = None
        self._history_claude: Optional[list] = None
        self._provider = "ollama"
        self._claude_api_key = ""
        self._busy = False
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Chat log
        self._chat_log = tk.Text(
            self,
            wrap="word",
            state="disabled",
            relief="flat",
            font=("Segoe UI", 10),
            padx=6,
            pady=6,
        )
        self._chat_log.grid(row=0, column=0, sticky="nsew")
        self._chat_log.tag_configure("user", foreground="#2563eb", font=("Segoe UI", 10, "bold"))
        self._chat_log.tag_configure("assistant", foreground="#16a34a")
        self._chat_log.tag_configure("system", foreground="#9ca3af", font=("Segoe UI", 9, "italic"))

        sb = ttk.Scrollbar(self, command=self._chat_log.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self._chat_log.configure(yscrollcommand=sb.set)

        # Provider selector + input area
        input_frame = ttk.Frame(self)
        input_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        input_frame.columnconfigure(1, weight=1)

        self._provider_var = tk.StringVar(value="ollama")
        provider_combo = ttk.Combobox(
            input_frame,
            textvariable=self._provider_var,
            values=["ollama", "claude"],
            state="readonly",
            width=8,
        )
        provider_combo.grid(row=0, column=0, padx=(0, 4))
        provider_combo.bind("<<ComboboxSelected>>", self._on_provider_change)

        self._input_var = tk.StringVar()
        self._input_entry = ttk.Entry(
            input_frame,
            textvariable=self._input_var,
        )
        self._input_entry.grid(row=0, column=1, sticky="ew", padx=(0, 4))
        self._input_entry.bind("<Return>", self._on_send)

        self._send_btn = ttk.Button(
            input_frame, text="Send", command=self._on_send, width=6,
        )
        self._send_btn.grid(row=0, column=2)

        # Welcome message
        self._append_message(
            "system",
            "Ask questions about your mods, e.g.:\n"
            '  "What patches do I need for Immersive Weapons?"\n'
            '  "Why is SkyUI showing warnings?"',
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_claude_api_key(self, key: str) -> None:
        """Store the Anthropic API key for Claude chat."""
        self._claude_api_key = key

    def set_db(self, db) -> None:
        """Update the database reference (e.g. after a refresh)."""
        self._db = db

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_provider_change(self, _event=None) -> None:
        self._provider = self._provider_var.get()

    def _on_send(self, _event=None) -> None:
        message = self._input_var.get().strip()
        if not message or self._busy:
            return

        self._input_var.set("")
        self._append_message("user", message)

        provider = self._provider_var.get()
        if provider == "claude" and not self._claude_api_key:
            self._append_message(
                "system",
                "No Anthropic API key configured. "
                "Validate your key in the toolbar first, or switch to Ollama.",
            )
            return

        self._busy = True
        self._send_btn.config(state="disabled")
        self._input_entry.config(state="disabled")
        self._append_message("system", "Thinking…")

        thread = threading.Thread(
            target=self._chat_worker,
            args=(message, provider),
            daemon=True,
        )
        thread.start()

    def _chat_worker(self, message: str, provider: str) -> None:
        """Run the AI chat in a background thread."""
        try:
            if provider == "claude":
                from src.ai.claude_agent import chat as claude_chat

                reply, self._history_claude = claude_chat(
                    user_message=message,
                    db=self._db,
                    api_key=self._claude_api_key,
                    history=self._history_claude,
                )
            else:
                from src.ai.local_agent import chat as local_chat

                reply, self._history_ollama = local_chat(
                    user_message=message,
                    db=self._db,
                    history=self._history_ollama,
                )

            self.after(0, self._remove_thinking)
            self.after(0, self._append_message, "assistant", reply or "(no response)")
        except Exception as exc:
            logger.error("Chat error: %s", exc)
            self.after(0, self._remove_thinking)
            self.after(0, self._append_message, "system", f"Error: {exc}")
        finally:
            self.after(0, self._finish_chat)

    def _finish_chat(self) -> None:
        self._busy = False
        self._send_btn.config(state="normal")
        self._input_entry.config(state="normal")
        self._input_entry.focus_set()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _append_message(self, role: str, text: str) -> None:
        self._chat_log.configure(state="normal")
        if role == "user":
            prefix = "You: "
        elif role == "assistant":
            prefix = "AI: "
        else:
            prefix = ""
        self._chat_log.insert(tk.END, f"{prefix}{text}\n\n", role)
        self._chat_log.see(tk.END)
        self._chat_log.configure(state="disabled")

    def _remove_thinking(self) -> None:
        """Remove the last 'Thinking…' placeholder."""
        self._chat_log.configure(state="normal")
        content = self._chat_log.get("1.0", tk.END)
        idx = content.rfind("Thinking…")
        if idx != -1:
            # Calculate the line/column position
            before = content[:idx]
            line = before.count("\n") + 1
            col = len(before.split("\n")[-1])
            start = f"{line}.{col}"
            # "Thinking…\n\n" = 12 chars (10 + 2 newlines)
            end_idx = idx + len("Thinking…\n\n")
            after = content[:end_idx]
            end_line = after.count("\n") + 1
            end_col = len(after.split("\n")[-1])
            end = f"{end_line}.{end_col}"
            self._chat_log.delete(start, end)
        self._chat_log.configure(state="disabled")
