"""
Mod detail panel.

Displays the full information about a single mod that was selected in the main
mod list, including its description and requirements.
"""

import re
import tkinter as tk
from tkinter import ttk
import webbrowser


def clean_bbcode(text: str) -> str:
    """Strip BBCode / HTML markup and return plain text."""
    # Convert <br> / <br/> / <br /> to newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)

    # Remove [img]...[/img] entirely
    text = re.sub(r"\[img\][^\[]*\[/img\]", "", text, flags=re.IGNORECASE)

    # Remove [youtube]...[/youtube] entirely
    text = re.sub(r"\[youtube\][^\[]*\[/youtube\]", "", text, flags=re.IGNORECASE)

    # Convert [url=...]text[/url] -> text
    text = re.sub(
        r"\[url=[^\]]*\]([^\[]*)\[/url\]", r"\1", text, flags=re.IGNORECASE
    )

    # Remove simple BBCode tags (opening and closing)
    text = re.sub(
        r"\[/?(b|i|u|center|size|color|font)(=[^\]]*)?\]",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text


class ModDetailFrame(ttk.Frame):
    """Right-hand panel that shows detailed information for a selected mod."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ── Title bar ──────────────────────────────────────────────────
        title_frame = ttk.Frame(self)
        title_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        title_frame.columnconfigure(0, weight=1)

        # Placeholder: "Seleccioná un mod" en voseo rioplatense
        self._title_var = tk.StringVar(value="— Select a mod —")
        ttk.Label(
            title_frame,
            textvariable=self._title_var,
            font=("Segoe UI", 13, "bold"),
            wraplength=400,
        ).grid(row=0, column=0, sticky="w")

        self._url_btn = ttk.Button(
            title_frame,
            text="Open on Nexus Mods ↗",
            command=self._open_url,
            state="disabled",
        )
        self._url_btn.grid(row=0, column=1, padx=(8, 0))
        self._current_url: str = ""

        # ── Notebook (tabs) ────────────────────────────────────────────
        self._notebook = ttk.Notebook(self)
        self._notebook.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        self._tab_summary = self._make_text_tab("Summary")
        self._tab_description = self._make_text_tab("Description")
        self._tab_requirements = self._make_list_tab("Requirements")

    # ------------------------------------------------------------------
    # Tab factories
    # ------------------------------------------------------------------

    def _make_text_tab(self, label: str) -> tk.Text:
        frame = ttk.Frame(self._notebook)
        self._notebook.add(frame, text=label)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        text = tk.Text(
            frame,
            wrap="word",
            state="disabled",
            relief="flat",
            font=("Segoe UI", 10),
            padx=6,
            pady=6,
        )
        text.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(frame, command=text.yview)
        sb.grid(row=0, column=1, sticky="ns")
        text.configure(yscrollcommand=sb.set)
        return text

    def _make_list_tab(self, label: str) -> ttk.Treeview:
        frame = ttk.Frame(self._notebook)
        self._notebook.add(frame, text=label)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        tree = ttk.Treeview(frame, show="headings", selectmode="browse")
        tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(frame, command=tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=sb.set)
        return tree

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_mod(self, mod: dict, db=None) -> None:
        """
        Populate all tabs with data for ``mod``.

        Parameters
        ----------
        mod:
            Dict returned by ``DatabaseManager.get_mod()``.
        db:
            Optional ``DatabaseManager`` instance used to load related data
            (requirements, etc.).
        """
        self._title_var.set(mod.get("name", "Unknown mod"))
        self._current_url = mod.get("mod_url", "")
        self._url_btn.configure(
            state="normal" if self._current_url else "disabled"
        )

        self._set_text(self._tab_summary, mod.get("summary", "No summary available."))
        self._set_text(
            self._tab_description,
            clean_bbcode(
                # "Intentá sincronizar" era el texto en voseo rioplatense
                mod.get("description", "No description cached. Try syncing this mod.")
            ),
        )

        if db is not None:
            mod_id = mod["mod_id"]
            self._populate_requirements(db.get_requirements(mod_id))

    def clear(self) -> None:
        """Reset all tabs to their empty state."""
        self._title_var.set("— Select a mod —")
        self._current_url = ""
        self._url_btn.configure(state="disabled")
        for tab in (
            self._tab_summary,
            self._tab_description,
        ):
            self._set_text(tab, "")
        self._tab_requirements.delete(*self._tab_requirements.get_children())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _set_text(widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.configure(state="disabled")

    def _populate_requirements(self, requirements: list) -> None:
        tree = self._tab_requirements
        tree.delete(*tree.get_children())
        tree["columns"] = ("name", "type", "url")
        tree.heading("name", text="Required Mod")
        tree.heading("type", text="Type")
        tree.heading("url", text="URL")
        tree.column("name", width=200)
        tree.column("type", width=80)
        tree.column("url", width=300)

        for req in requirements:
            req_type = "Patch" if req.get("is_patch") else "Required"
            tree.insert(
                "", tk.END,
                values=(req["required_name"], req_type, req.get("required_url", "")),
            )

    def _open_url(self) -> None:
        if self._current_url:
            webbrowser.open(self._current_url)
