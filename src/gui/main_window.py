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
from tkinter import filedialog, messagebox, ttk
from typing import Optional
import webbrowser

from src.analyzer.compatibility import CompatibilityAnalyzer
from src.database.manager import DatabaseManager
from src.gui.mod_detail_frame import ModDetailFrame
from src.mo2.reader import MO2Reader, MO2Profile
from src.nexus.api import NexusAPI, RateLimitError, NexusAPIError

logger = logging.getLogger(__name__)


class MainWindow(tk.Tk):
    """Top-level application window."""

    APP_TITLE = "App-nexus — Skyrim Mod Compatibility Manager"
    GEOMETRY = "1200x750"

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
        ttk.Label(toolbar, text="MO2 modlist.txt:").pack(side="left", padx=(0, 4))
        self._modlist_path_var = tk.StringVar()
        ttk.Entry(
            toolbar, textvariable=self._modlist_path_var, width=32
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            toolbar, text="Browse…", command=self._browse_modlist
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            toolbar, text="Load Mod List", command=self._load_mod_list
        ).pack(side="left", padx=(0, 12))

        ttk.Separator(toolbar, orient="vertical").pack(
            side="left", fill="y", padx=8
        )

        # Sync + Analyse
        self._btn_sync = ttk.Button(
            toolbar,
            text="🔄 Sync from Nexus",
            command=self._sync_mods_threaded,
        )
        self._btn_sync.pack(side="left", padx=(0, 6))

        self._btn_analyse = ttk.Button(
            toolbar,
            text="🔍 Analyse",
            command=self._analyse,
        )
        self._btn_analyse.pack(side="left")

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
        self._status_var = tk.StringVar(value="Ready.")
        ttk.Label(
            self,
            textvariable=self._status_var,
            relief="sunken",
            anchor="w",
            padding=(4, 2),
        ).grid(row=3, column=0, sticky="ew")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

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
            messagebox.showwarning(
                "No Path", "Please select a modlist.txt file from Mod Organizer 2."
            )
            return
        try:
            self._profile = MO2Reader.from_files(modlist_path=path)
            self._populate_mod_list()
            self._set_status(
                f"Loaded {len(self._profile.mods)} mods "
                f"({len(self._profile.enabled_mods)} enabled)."
            )
            logger.info(
                "Loaded mod list: %d mods (%d enabled)",
                len(self._profile.mods),
                len(self._profile.enabled_mods),
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
            self._set_status(f"'{mod_name}' not yet in database. Sync to fetch data.")

    def _sync_mods_threaded(self) -> None:
        """Run the Nexus sync in a background thread so the UI stays responsive."""
        if self._api is None:
            messagebox.showwarning(
                "No API Key", "Please validate your Nexus Mods API key first."
            )
            return
        if self._profile is None:
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
        """
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
            if self._db.get_mod(nexus_id):
                self.after(
                    0, self._set_status,
                    f"Skipping '{mod.name}' (already cached).",
                )
                continue

            try:
                full_data = self._api.get_mod(nexus_id)  # type: ignore[union-attr]
                self._db.upsert_mod(full_data)

                requirements = self._api.get_mod_requirements(nexus_id)  # type: ignore[union-attr]
                if requirements:
                    self._db.upsert_requirements(nexus_id, requirements)

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

        # Restore UI safely on main thread
        self.after(0, self._finish_sync)

    def _finish_sync(self) -> None:
        """Helper to cleanly finish the sync process on the main thread."""
        self._set_status("Sync complete.")
        self._populate_mod_list()
        self._btn_sync.config(state="normal")
        self._btn_analyse.config(state="normal")
        logger.info("Sync complete.")

    def _analyse(self) -> None:
        if self._profile is None:
            messagebox.showwarning(
                "No Mod List", "Please load your MO2 modlist.txt first."
            )
            return
        analyser = CompatibilityAnalyzer(self._db)
        report = analyser.analyse(self._profile)
        self._display_report(report)

    def _display_report(self, report: dict) -> None:
        stats = report["stats"]
        lines = [
            "╔══════════════════════════════════════════════════════════╗",
            f"  Mods analysed : {stats['enabled_mods']} enabled / {stats['total_mods']} total",
            f"  Missing mods  : {stats['missing_count']}  (patches: {stats['missing_patches']})",
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

        if not report["missing_requirements"]:
            lines.append("✔ No issues detected in the cached database.")

        self._set_text(self._report_text, "\n".join(lines))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, message: str) -> None:
        self._status_var.set(message)

    @staticmethod
    def _set_text(widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.configure(state="disabled")

    def _on_close(self) -> None:
        self._db.close()
        self.destroy()
