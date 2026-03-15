"""
Main application window.

Layout
------
┌────────────────────────────────────────────────────────────┐
│  Toolbar (API key, MO2 path, Sync button)                  │
├────────────────┬───────────────────────────────────────────┤
│  Mod list      │  Mod detail panel (tabs)                  │
│  (left pane)   │  Summary / Description / Requirements     │
├────────────────┴───────────────────────────────────────────┤
│  Report panel (missing mods, patches)                      │
└────────────────────────────────────────────────────────────┘
"""

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional
import webbrowser
from datetime import datetime, timezone

import sv_ttk

from src.analyzer.compatibility import CompatibilityAnalyzer
from src.database.manager import DatabaseManager
from src.gui.mod_detail_frame import ModDetailFrame
from src.loot.masterlist import update_masterlist
from src.mo2.reader import MO2Reader, MO2Profile
from src.nexus.api import NexusAPI, RateLimitError, NexusAPIError

logger = logging.getLogger(__name__)


class MainWindow(tk.Tk):
    """Top-level application window."""

    APP_TITLE = "App-nexus — Skyrim Mod Compatibility Manager"
    GEOMETRY = "1280x800"

    def __init__(self):
        super().__init__()
        self.title(self.APP_TITLE)
        self.geometry(self.GEOMETRY)
        self.minsize(900, 600)

        self._db = DatabaseManager()
        self._db.connect()

        self._profile: Optional[MO2Profile] = None
        self._api: Optional[NexusAPI] = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=3)
        self.rowconfigure(2, weight=1)

        self._build_toolbar()
        self._build_main_area()
        self._build_report_panel()
        self._build_status_bar()

    def _build_toolbar(self) -> None:
        toolbar = ttk.Frame(self, relief="ridge", padding=6)
        toolbar.grid(row=0, column=0, sticky="ew")

        # API key
        ttk.Label(toolbar, text="Nexus API Key:").pack(side="left", padx=(0, 4))
        self._api_key_var = tk.StringVar()
        api_entry = ttk.Entry(toolbar, textvariable=self._api_key_var, width=42, show="*")
        api_entry.pack(side="left", padx=(0, 8))

        ttk.Button(
            toolbar, text="Validate Key", command=self._validate_api_key
        ).pack(side="left", padx=(0, 12))

        ttk.Separator(toolbar, orient="vertical").pack(
            side="left", fill="y", padx=8
        )

        # MO2 path
        ttk.Label(toolbar, text="MO2 Profile:").pack(side="left", padx=(0, 4))
        self._modlist_path_var = tk.StringVar()
        ttk.Entry(
            toolbar, textvariable=self._modlist_path_var, width=32
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            toolbar, text="Browse…", command=self._browse_modlist
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            toolbar, text="Load Mods", command=self._load_mod_list
        ).pack(side="left", padx=(0, 12))

        ttk.Separator(toolbar, orient="vertical").pack(
            side="left", fill="y", padx=8
        )

        # Sync + Analyse
        self._btn_sync = ttk.Button(
            toolbar,
            text="🔄 Sync Nexus",
            command=self._sync_mods_threaded,
        )
        self._btn_sync.pack(side="left", padx=(0, 6))

        self._btn_analyse = ttk.Button(
            toolbar,
            text="🔍 Analyse",
            command=self._analyse,
        )
        self._btn_analyse.pack(side="left")

        ttk.Separator(toolbar, orient="vertical").pack(
            side="left", fill="y", padx=8
        )

        self._btn_loot = ttk.Button(
            toolbar,
            text="📋 Update LOOT",
            command=self._update_loot_threaded,
        )
        self._btn_loot.pack(side="left")

        ttk.Separator(toolbar, orient="vertical").pack(
            side="left", fill="y", padx=8
        )

        self._btn_ai = ttk.Button(
            toolbar,
            text="🤖 Analyze with AI",
            command=self._show_ai_dialog,
        )
        self._btn_ai.pack(side="left")

        ttk.Separator(toolbar, orient="vertical").pack(
            side="left", fill="y", padx=8
        )

        self._theme_btn = ttk.Button(
            toolbar,
            text="☀️",
            width=3,
            command=self._toggle_theme,
        )
        self._theme_btn.pack(side="left")

    def _build_main_area(self) -> None:
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)

        # Left: mod list
        left_frame = ttk.Frame(paned, padding=4)
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(1, weight=1)
        paned.add(left_frame, weight=1)

        ttk.Label(left_frame, text="Installed Mods", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        self._mod_list = ttk.Treeview(
            left_frame,
            columns=("name", "status"),
            show="headings",
            selectmode="browse",
        )
        self._mod_list.heading("name", text="Mod Name")
        self._mod_list.heading("status", text="Status")
        self._mod_list.column("name", width=220)
        self._mod_list.column("status", width=70)
        self._mod_list.grid(row=1, column=0, sticky="nsew")
        self._mod_list.bind("<<TreeviewSelect>>", self._on_mod_select)

        sb = ttk.Scrollbar(left_frame, command=self._mod_list.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self._mod_list.configure(yscrollcommand=sb.set)

        # Right: detail panel
        self._detail = ModDetailFrame(paned, padding=4)
        paned.add(self._detail, weight=3)

    def _build_report_panel(self) -> None:
        report_frame = ttk.LabelFrame(self, text="Analysis Report", padding=6)
        report_frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 4))
        report_frame.columnconfigure(0, weight=1)
        report_frame.rowconfigure(0, weight=1)

        self._report_text = tk.Text(
            report_frame,
            height=8,
            wrap="word",
            state="disabled",
            relief="flat",
            font=("Courier New", 9),
        )
        self._report_text.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(report_frame, command=self._report_text.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self._report_text.configure(yscrollcommand=sb.set)

    def _build_status_bar(self) -> None:
        status_frame = ttk.Frame(self)
        status_frame.grid(row=3, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)

        self._status_var = tk.StringVar(value="Ready.")
        ttk.Label(
            status_frame,
            textvariable=self._status_var,
            relief="sunken",
            anchor="w",
            padding=(4, 2),
        ).grid(row=0, column=0, sticky="ew")

        ttk.Label(
            status_frame,
            text="Masterlist data: LOOT (loot.github.io) — CC BY-NC-SA 4.0",
            anchor="e",
            foreground="grey",
            padding=(4, 2),
        ).grid(row=0, column=1, sticky="e")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _toggle_theme(self) -> None:
        """Switch between dark and light sv-ttk themes."""
        sv_ttk.toggle_theme()
        if sv_ttk.get_theme() == "dark":
            self._theme_btn.config(text="☀️")
        else:
            self._theme_btn.config(text="🌙")

    def _validate_api_key(self) -> None:
        key = self._api_key_var.get().strip()
        if not key:
            messagebox.showwarning("No API Key", "Please enter your Nexus Mods API key.")
            return
        self._set_status("Validating API key…")
        try:
            api = NexusAPI(api_key=key)
            info = api.validate_api_key()
            name = info.get("name", "unknown user")
            messagebox.showinfo("API Key Valid", f"Authenticated as: {name}")
            self._api = api
            self._set_status(f"API key valid — logged in as {name}.")
            logger.info("API key validated for user: %s", name)
        except Exception as exc:
            messagebox.showerror("API Key Error", str(exc))
            self._set_status("API key validation failed.")
            logger.error("API key validation failed: %s", exc)

    def _browse_modlist(self) -> None:
        path = filedialog.askopenfilename(
            title="Select MO2 modlist.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self._modlist_path_var.set(path)

    def _load_mod_list(self) -> None:
        path = self._modlist_path_var.get().strip()
        if not path:
            # "Seleccioná un archivo" era el texto en voseo rioplatense
            messagebox.showwarning(
                "No Path", "Please select a Mod Organizer 2 modlist.txt file."
            )
            return
        try:
            modlist_path = Path(path)
            plugins_path = modlist_path.parent / "plugins.txt"

            self._profile = MO2Reader.from_files(
                modlist_path=str(modlist_path),
                plugins_path=str(plugins_path) if plugins_path.exists() else None,
            )
            self._populate_mod_list()
            self._set_status(
                f"Loaded {len(self._profile.mods)} mods "
                f"({len(self._profile.enabled_mods)} enabled, "
                f"{len(self._profile.load_order)} plugins)."
            )
            logger.info(
                "Loaded mod list: %d mods (%d enabled, %d plugins)",
                len(self._profile.mods),
                len(self._profile.enabled_mods),
                len(self._profile.load_order),
            )
        except Exception as exc:
            messagebox.showerror("Load Error", str(exc))
            logger.error("Failed to load mod list: %s", exc)

    def _populate_mod_list(self) -> None:
        self._mod_list.delete(*self._mod_list.get_children())
        if self._profile is None:
            return
        for mod in self._profile.mods:
            status = "✔ ON" if mod.enabled else "✘ OFF"
            tag = "enabled" if mod.enabled else "disabled"
            self._mod_list.insert("", tk.END, values=(mod.name, status), tags=(tag,))
        self._mod_list.tag_configure("disabled", foreground="grey")

    def _on_mod_select(self, _event) -> None:
        selection = self._mod_list.selection()
        if not selection:
            self._detail.clear()
            return
        item = self._mod_list.item(selection[0])
        mod_name = item["values"][0]
        results = self._db.search_mods_by_name(mod_name)
        if results:
            self._detail.show_mod(results[0], db=self._db)
        else:
            self._detail.clear()
            self._set_status(f"'{mod_name}' not in database. Sync to fetch its data.")

    def _sync_mods_threaded(self) -> None:
        """Run the Nexus sync in a background thread so the UI stays responsive."""
        if self._api is None:
            # "Validá tu clave" era el texto en voseo rioplatense
            messagebox.showwarning(
                "No API Key", "Please validate your Nexus Mods API key first."
            )
            return
        if self._profile is None:
            # "Cargá tu modlist" era el texto en voseo rioplatense
            messagebox.showwarning(
                "No Mod List", "Please load your MO2 modlist.txt first."
            )
            return

        # Disable buttons to prevent concurrent syncs
        self._btn_sync.config(state="disabled")
        self._btn_analyse.config(state="disabled")

        thread = threading.Thread(target=self._sync_mods, daemon=True)
        thread.start()

    def _sync_mods(self) -> None:
        """
        Iterate over the enabled mods and fetch their Nexus page by nexus_id
        read from each mod's meta.ini.  Falls back gracefully when the id is
        missing or zero.

        Uses a thread-local DatabaseManager because SQLite connections cannot
        be shared across threads.
        """
        # Create a thread-local DB connection
        thread_db = DatabaseManager(db_path=self._db.db_path)
        thread_db.connect()
        try:
            mods = self._profile.enabled_mods  # type: ignore[union-attr]
            total = len(mods)

            for idx, mod in enumerate(mods, start=1):
                self.after(0, self._set_status, f"Syncing mod {idx}/{total}: {mod.name}…")

                # Skip mods without a valid nexus_id
                if not mod.nexus_id or mod.nexus_id == "0":
                    self.after(
                        0, self._set_status,
                        f"Skipping '{mod.name}' (no Nexus ID in meta.ini).",
                    )
                    continue

                nexus_id = int(mod.nexus_id)

                # Check local cache to avoid burning API quota
                if thread_db.get_mod(nexus_id):
                    self.after(
                        0, self._set_status,
                        f"Skipping '{mod.name}' (already cached).",
                    )
                    continue

                try:
                    full_data = self._api.get_mod(nexus_id)  # type: ignore[union-attr]
                    thread_db.upsert_mod(full_data)

                    requirements = self._api.get_mod_requirements(nexus_id)  # type: ignore[union-attr]
                    if requirements:
                        thread_db.upsert_requirements(nexus_id, requirements)

                except RateLimitError:
                    self.after(
                        0,
                        self._set_status,
                        "Rate limit reached. Stopping sync.",
                    )
                    break
                except NexusAPIError as exc:
                    self.after(0, self._set_status, f"API error for '{mod.name}': {exc}")
                    logger.error("API error for '%s': %s", mod.name, exc)
                except Exception as exc:
                    self.after(0, self._set_status, f"Error syncing '{mod.name}': {exc}")
                    logger.error("Error syncing '%s': %s", mod.name, exc)
        finally:
            thread_db.close()
            # Refresh main thread DB after sync (single callback to avoid race)
            self.after(0, self._refresh_main_db)
            # Restore UI safely on main thread (must be inside finally so
            # buttons are always re-enabled even when an error bubbles up)
            self.after(0, self._finish_sync)

    def _finish_sync(self) -> None:
        """Helper to cleanly finish the sync process on the main thread."""
        self._set_status("Sync complete.")
        self._populate_mod_list()
        self._btn_sync.config(state="normal")
        self._btn_analyse.config(state="normal")
        logger.info("Sync complete.")

    def _update_loot_threaded(self) -> None:
        """Run the LOOT masterlist update in a background thread."""
        self._btn_loot.config(state="disabled")
        self._btn_sync.config(state="disabled")
        self._btn_analyse.config(state="disabled")

        thread = threading.Thread(target=self._update_loot, daemon=True)
        thread.start()

    def _update_loot(self) -> None:
        """Download and parse the LOOT masterlist in a background thread."""
        thread_db = DatabaseManager(db_path=self._db.db_path)
        thread_db.connect()
        try:
            self.after(0, self._set_status, "Downloading LOOT masterlist…")
            count = update_masterlist(thread_db)
            self.after(0, self._set_status, f"LOOT masterlist updated: {count} plugin entries.")
            logger.info("LOOT masterlist updated: %d entries.", count)
        except Exception as exc:
            self.after(0, self._set_status, f"LOOT update failed: {exc}")
            logger.error("LOOT update failed: %s", exc)
        finally:
            thread_db.close()
            self.after(0, self._refresh_main_db)
            self.after(0, self._finish_loot_update)

    def _finish_loot_update(self) -> None:
        """Re-enable buttons after LOOT update completes."""
        self._btn_loot.config(state="normal")
        self._btn_sync.config(state="normal")
        self._btn_analyse.config(state="normal")

    def _analyse(self) -> None:
        if self._profile is None:
            messagebox.showwarning(
                "No Mod List", "Please load your MO2 modlist.txt first."
            )
            return
        analyser = CompatibilityAnalyzer(self._db)
        report = analyser.analyse(self._profile)
        self._display_report(report)

    # ------------------------------------------------------------------
    # AI Analysis
    # ------------------------------------------------------------------

    def _show_ai_dialog(self) -> None:
        """Open a dialog to choose AI provider and run analysis."""
        if self._profile is None:
            messagebox.showwarning(
                "No Mod List", "Please load your MO2 modlist.txt first."
            )
            return

        # Get the currently selected mod
        selection = self._mod_list.selection()
        if not selection:
            messagebox.showwarning(
                "No Mod Selected",
                "Please select a mod from the list to analyze.",
            )
            return

        item = self._mod_list.item(selection[0])
        mod_name = item["values"][0]

        # Find the nexus_id for the selected mod
        nexus_id = None
        if self._profile:
            for mod in self._profile.mods:
                if mod.name == mod_name and mod.nexus_id and mod.nexus_id != "0":
                    nexus_id = mod.nexus_id
                    break

        if not nexus_id:
            messagebox.showwarning(
                "No Nexus ID",
                f"'{mod_name}' has no Nexus Mods ID in meta.ini.",
            )
            return

        dialog = tk.Toplevel(self)
        dialog.title("AI Mod Analysis")
        dialog.geometry("420x260")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(
            dialog,
            text=f"Analyze: {mod_name}",
            font=("Segoe UI", 11, "bold"),
        ).pack(pady=(12, 6))

        ttk.Label(dialog, text="Select AI provider:").pack(anchor="w", padx=16)

        provider_var = tk.StringVar(value="ollama")

        radio_frame = ttk.Frame(dialog)
        radio_frame.pack(anchor="w", padx=24, pady=4)

        ttk.Radiobutton(
            radio_frame,
            text="Local (Ollama — Free)",
            variable=provider_var,
            value="ollama",
            command=lambda: api_key_entry.config(state="disabled"),
        ).pack(anchor="w")

        ttk.Radiobutton(
            radio_frame,
            text="Claude API (Premium)",
            variable=provider_var,
            value="claude",
            command=lambda: api_key_entry.config(state="normal"),
        ).pack(anchor="w")

        key_frame = ttk.Frame(dialog)
        key_frame.pack(fill="x", padx=16, pady=(8, 0))
        ttk.Label(key_frame, text="Anthropic API Key:").pack(anchor="w")
        api_key_var = tk.StringVar()
        api_key_entry = ttk.Entry(
            key_frame, textvariable=api_key_var, width=48, show="*"
        )
        api_key_entry.pack(fill="x")
        api_key_entry.config(state="disabled")

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=12)

        def on_run():
            dialog.destroy()
            provider = provider_var.get()
            api_key = api_key_var.get().strip()
            if provider == "claude" and not api_key:
                messagebox.showwarning(
                    "No API Key",
                    "Please enter your Anthropic API key for Claude.",
                )
                return
            self._run_ai_analysis(nexus_id, mod_name, provider, api_key)

        ttk.Button(btn_frame, text="Run Analysis", command=on_run).pack(
            side="left", padx=4
        )
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(
            side="left", padx=4
        )

    def _run_ai_analysis(
        self,
        nexus_id: str,
        mod_name: str,
        provider: str,
        api_key: str,
    ) -> None:
        """Launch AI analysis in a background thread."""
        self._btn_ai.config(state="disabled")
        self._btn_sync.config(state="disabled")

        thread = threading.Thread(
            target=self._ai_analysis_worker,
            args=(nexus_id, mod_name, provider, api_key),
            daemon=True,
        )
        thread.start()

    def _ai_analysis_worker(
        self,
        nexus_id: str,
        mod_name: str,
        provider: str,
        api_key: str,
    ) -> None:
        """Background worker for AI analysis."""
        thread_db = DatabaseManager(db_path=self._db.db_path)
        thread_db.connect()
        try:
            # Step 1: Extract page data with Playwright
            self.after(
                0, self._set_status,
                f"Browsing Nexus page for '{mod_name}'…",
            )
            try:
                from src.browser.nexus_browser import extract_mod_page_data

                page_data = extract_mod_page_data(nexus_id, headless=True)
            except ImportError as exc:
                self.after(
                    0, self._set_status,
                    f"Playwright not available: {exc}",
                )
                return
            except Exception as exc:
                self.after(
                    0, self._set_status,
                    f"Browser error: {exc}",
                )
                return

            # Step 2: Analyse with selected AI provider
            self.after(
                0, self._set_status,
                f"Analyzing '{mod_name}' with {provider}…",
            )
            attribution = None
            try:
                if provider == "claude":
                    from src.ai.claude_agent import analyse_mod as claude_analyse
                    from src.ai.claude_agent import ATTRIBUTION

                    result = claude_analyse(page_data, api_key=api_key)
                    attribution = ATTRIBUTION
                else:
                    from src.ai.local_agent import analyse_mod as local_analyse

                    result = local_analyse(page_data)
            except ImportError as exc:
                self.after(0, self._set_status, f"AI package error: {exc}")
                return
            except RuntimeError as exc:
                self.after(0, self._set_status, str(exc))
                return

            # Step 3: Save to database
            analysis_record = {
                "nexus_id": str(nexus_id),
                "requirements": result.get("requirements", []),
                "patches": result.get("patches", []),
                "known_issues": result.get("known_issues", []),
                "analyzed_by": provider,
                "last_analyzed": datetime.now(timezone.utc).isoformat(),
            }
            thread_db.upsert_ai_analysis(analysis_record)

            # Step 4: Display results on main thread
            self.after(
                0,
                self._display_ai_report,
                mod_name,
                analysis_record,
                attribution,
            )

        except Exception as exc:
            self.after(0, self._set_status, f"AI analysis error: {exc}")
            logger.error("AI analysis error: %s", exc)
        finally:
            thread_db.close()
            self.after(0, self._refresh_main_db)
            self.after(0, self._finish_ai_analysis)

    def _finish_ai_analysis(self) -> None:
        """Re-enable buttons after AI analysis completes."""
        self._btn_ai.config(state="normal")
        self._btn_sync.config(state="normal")
        self._set_status("AI analysis complete.")

    def _display_ai_report(
        self,
        mod_name: str,
        analysis: dict,
        attribution: Optional[str] = None,
    ) -> None:
        """Format and display an AI analysis report in the report panel."""
        lines = [
            "╔══════════════════════════════════════════════════════════╗",
            f"  AI Analysis: {mod_name}",
            f"  Provider: {analysis['analyzed_by']}",
            f"  Analyzed: {analysis['last_analyzed']}",
            "╚══════════════════════════════════════════════════════════╝",
            "",
        ]

        reqs = analysis.get("requirements", [])
        if reqs:
            lines.append("── REQUIREMENTS (AI-detected) ──")
            for r in reqs:
                lines.append(f"  • {r}")
            lines.append("")

        patches = analysis.get("patches", [])
        if patches:
            lines.append("── PATCHES (AI-detected) ──")
            for p in patches:
                lines.append(f"  • {p}")
            lines.append("")

        issues = analysis.get("known_issues", [])
        if issues:
            lines.append("── KNOWN ISSUES (AI-detected) ──")
            for issue in issues:
                lines.append(f"  ⚠ {issue}")
            lines.append("")

        if not reqs and not patches and not issues:
            lines.append("✔ No additional issues detected by AI analysis.")
            lines.append("")

        if attribution:
            lines.append(f"— {attribution}")

        self._set_text(self._report_text, "\n".join(lines))

    def _display_report(self, report: dict) -> None:
        stats = report["stats"]
        lines = [
            "╔══════════════════════════════════════════════════════════╗",
            f"  Mods analysed   : {stats['enabled_mods']} enabled / {stats['total_mods']} total",
            f"  Missing mods    : {stats['missing_count']}  (patches: {stats['missing_patches']})",
            f"  LOOT conflicts  : {stats.get('loot_incompatible', 0)}",
            f"  LOOT warnings   : {stats.get('loot_warnings', 0)}",
            "╚══════════════════════════════════════════════════════════╝",
            "",
        ]

        if report["missing_requirements"]:
            lines.append("── MISSING REQUIREMENTS ──")
            for m in report["missing_requirements"]:
                tag = "[PATCH]" if m["is_patch"] else "[REQUIRED]"
                lines.append(
                    f"  {tag} '{m['required_name']}' required by '{m['mod_name']}'"
                )
                if m.get("required_url"):
                    lines.append(f"    → {m['required_url']}")
            lines.append("")

        if report.get("loot_incompatibilities"):
            lines.append("── LOOT INCOMPATIBILITIES ──")
            for inc in report["loot_incompatibilities"]:
                lines.append(
                    f"  [INCOMPATIBLE] '{inc['mod_name']}' conflicts with '{inc['incompatible_with']}'"
                )
            lines.append("")

        if report.get("loot_warnings"):
            lines.append("── LOOT WARNINGS ──")
            for w in report["loot_warnings"]:
                lines.append(f"  ⚠ {w['mod_name']}: {w['message']}")
            lines.append("")

        if (
            not report["missing_requirements"]
            and not report.get("loot_incompatibilities")
            and not report.get("loot_warnings")
        ):
            lines.append("✔ No issues detected in the cached database.")

        self._set_text(self._report_text, "\n".join(lines))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, message: str) -> None:
        self._status_var.set(message)

    def _refresh_main_db(self) -> None:
        """Close and reopen the main-thread DB so it sees data written by the sync thread."""
        self._db.close()
        self._db.connect()

    @staticmethod
    def _set_text(widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.configure(state="disabled")

    def _on_close(self) -> None:
        self._db.close()
        self.destroy()
