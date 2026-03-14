"""
MO2 (Mod Organizer 2) reader.

Reads modlist.txt and plugins.txt from an MO2 profile directory to determine
which mods are installed and their load order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class InstalledMod:
    """A mod entry from modlist.txt."""

    name: str
    enabled: bool


@dataclass
class MO2Profile:
    """An MO2 profile with its mod list and load order."""

    profile_name: str
    mods: list[InstalledMod] = field(default_factory=list)
    load_order: list[str] = field(default_factory=list)

    @property
    def enabled_mods(self) -> list[InstalledMod]:
        return [m for m in self.mods if m.enabled]

    @property
    def enabled_mod_names(self) -> list[str]:
        return [m.name for m in self.mods if m.enabled]


_VERSION_RE = re.compile(
    r"[\s_-]+v?\d+(\.\d+)*.*$", re.IGNORECASE
)


class MO2Reader:
    """Reads Mod Organizer 2 instance and profile data."""

    def __init__(self, instance_root: Optional[Path] = None):
        self.instance_root = instance_root or self._default_instance_root()

    @staticmethod
    def _default_instance_root() -> Path:
        import os
        app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        return Path(app_data) / "ModOrganizer"

    # ------------------------------------------------------------------
    # Instance / profile discovery
    # ------------------------------------------------------------------

    def list_instances(self) -> list[str]:
        """Return names of MO2 instances found under ``instance_root``."""
        if not self.instance_root.is_dir():
            return []
        return sorted(
            d.name for d in self.instance_root.iterdir() if d.is_dir()
        )

    def list_profiles(self, instance_name: str) -> list[str]:
        profiles_dir = self.instance_root / instance_name / "profiles"
        if not profiles_dir.is_dir():
            return []
        return sorted(d.name for d in profiles_dir.iterdir() if d.is_dir())

    def read_profile(
        self, instance_name: str, profile_name: str
    ) -> MO2Profile:
        profile_dir = (
            self.instance_root / instance_name / "profiles" / profile_name
        )
        mods = self._read_modlist(profile_dir / "modlist.txt")
        load_order = self._read_plugins(profile_dir / "plugins.txt")
        return MO2Profile(
            profile_name=profile_name,
            mods=mods,
            load_order=load_order,
        )

    # ------------------------------------------------------------------
    # File parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_modlist(path: Path) -> list[InstalledMod]:
        """Parse ``modlist.txt`` into a list of ``InstalledMod``."""
        if not path.is_file():
            return []
        mods = []
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("*"):
                continue
            if line.startswith("+"):
                mods.append(InstalledMod(name=line[1:], enabled=True))
            elif line.startswith("-"):
                mods.append(InstalledMod(name=line[1:], enabled=False))
        return mods

    @staticmethod
    def _read_plugins(path: Path) -> list[str]:
        """Parse ``plugins.txt`` into an ordered list of plugin filenames."""
        if not path.is_file():
            return []
        plugins = []
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("*"):
                line = line[1:]
            plugins.append(line)
        return plugins

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_files(
        cls,
        modlist_path: str,
        plugins_path: Optional[str] = None,
        profile_name: str = "Custom",
    ) -> MO2Profile:
        """Create an ``MO2Profile`` directly from file paths."""
        mods = cls._read_modlist(Path(modlist_path))
        load_order = cls._read_plugins(Path(plugins_path)) if plugins_path else []
        return MO2Profile(
            profile_name=profile_name,
            mods=mods,
            load_order=load_order,
        )

    # ------------------------------------------------------------------
    # Name normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def normalise_name(raw_name: str) -> str:
        """
        Normalise a mod folder name by stripping version suffixes and
        collapsing whitespace.

        Examples::

            "SKSE64 - 2.2.3"   → "skse64"
            "SomePlugin_v1.5"  → "someplugin"
        """
        name = _VERSION_RE.sub("", raw_name)
        name = re.sub(r"\s+", " ", name).strip()
        return name.lower()
