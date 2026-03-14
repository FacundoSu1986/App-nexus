"""
Mod detail panel.

Displays the full information about a single mod that was selected in the main
mod list, including its description, requirements, incompatibilities, load-order
rules and user-reported issues.
"""

import tkinter as tk
from tkinter import ttk
import webbrowser


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
        self._tab_incompatibilities = self._make_list_tab("Incompatibilities")
        self._tab_load_order = self._make_list_tab("Load Order Rules")
        self._tab_issues = self._make_text_tab("Issues / Posts")

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
            (requirements, issues, etc.).
        """
        self._title_var.set(mod.get("name", "Unknown mod"))
        self._current_url = mod.get("mod_url", "")
        self._url_btn.configure(
            state="normal" if self._current_url else "disabled"
        )

        self._set_text(self._tab_summary, mod.get("summary", "No summary available."))
        self._set_text(
            self._tab_description,
            mod.get("description", "No description cached. Try syncing this mod."),
        )

        if db is not None:
            mod_id = mod["mod_id"]
            self._populate_requirements(db.get_requirements(mod_id))
            self._populate_incompatibilities(db.get_incompatibilities(mod_id))
            self._populate_load_order_rules(db.get_load_order_rules(mod_id))
            self._populate_issues(db.get_issues(mod_id))

    def clear(self) -> None:
        """Reset all tabs to their empty state."""
        self._title_var.set("— Select a mod —")
        self._current_url = ""
        self._url_btn.configure(state="disabled")
        for tab in (
            self._tab_summary,
            self._tab_description,
            self._tab_issues,
        ):
            self._set_text(tab, "")
        for tree in (
            self._tab_requirements,
            self._tab_incompatibilities,
            self._tab_load_order,
        ):
            tree.delete(*tree.get_children())

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

    def _populate_incompatibilities(self, incompatibilities: list) -> None:
        tree = self._tab_incompatibilities
        tree.delete(*tree.get_children())
        tree["columns"] = ("name", "reason")
        tree.heading("name", text="Incompatible Mod")
        tree.heading("reason", text="Reason")
        tree.column("name", width=200)
        tree.column("reason", width=380)

        for inc in incompatibilities:
            tree.insert(
                "", tk.END,
                values=(inc["incompatible_name"], inc.get("reason", "")),
            )

    def _populate_load_order_rules(self, rules: list) -> None:
        tree = self._tab_load_order
        tree.delete(*tree.get_children())
        tree["columns"] = ("rule", "target", "notes")
        tree.heading("rule", text="Rule")
        tree.heading("target", text="Target Mod")
        tree.heading("notes", text="Notes")
        tree.column("rule", width=70)
        tree.column("target", width=200)
        tree.column("notes", width=280)

        for rule in rules:
            tree.insert(
                "", tk.END,
                values=(
                    rule["rule_type"],
                    rule["target_mod_name"],
                    rule.get("notes", ""),
                ),
            )

    def _populate_issues(self, issues: list) -> None:
        text = ""
        for issue in issues:
            text += f"[{issue.get('posted_at', '')}] {issue['title']}\n"
            if issue.get("author"):
                text += f"  Author: {issue['author']}\n"
            if issue.get("body"):
                text += f"  {issue['body']}\n"
            if issue.get("url"):
                text += f"  URL: {issue['url']}\n"
            text += "\n"
        self._set_text(self._tab_issues, text or "No issues cached.")

    def _open_url(self) -> None:
        if self._current_url:
            webbrowser.open(self._current_url)
