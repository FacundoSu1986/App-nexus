"""
Mod Organizer 2 reader.

Reads the mod list and profile configuration produced by Mod Organizer 2 so
the application knows which mods the user has installed and enabled.

Default MO2 profile structure::

    %LOCALAPPDATA%\\ModOrganizer\\<instance>\\profiles\\<profile>\\modlist.txt
    %LOCALAPPDATA%\\ModOrganizer\\<instance>\\profiles\\<profile>\\plugins.txt

``modlist.txt`` lines:
    ``+ModName``  → enabled mod
    ``-ModName``  → disabled mod
    ``*ModName``  → a special (separator) entry

``plugins.txt`` lines:
    ``*PluginName.esp``  → active plugin
    ``PluginName.esp``   → inactive plugin
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class InstalledMod:
    name: str
    enabled: bool
    plugins: list = field(default_factory=list)


@dataclass
class MO2Profile:
    profile_name: str
    mods: list = field(default_factory=list)
    load_order: list = field(default_factory=list)  # ordered list of plugin names

    @property
    def enabled_mods(self) -> list:
        return [m for m in self.mods if m.enabled]

    @property
    def enabled_mod_names(self) -> list:
        return [m.name for m in self.enabled_mods]


class MO2Reader:
    """Reads Mod Organizer 2 installation data from the file system."""

    DEFAULT_INSTANCE_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "ModOrganizer"

    def __init__(self, instance_root: Optional[Path] = None):
        self.instance_root = Path(instance_root) if instance_root else self.DEFAULT_INSTANCE_ROOT

    # ------------------------------------------------------------------
    # Instance / profile discovery
    # ------------------------------------------------------------------

    def list_instances(self) -> list:
        """Return the names of all MO2 instances found on this machine."""
        if not self.instance_root.exists():
            return []
        return [
            d.name
            for d in self.instance_root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]

    def list_profiles(self, instance: str) -> list:
        """Return the profile names for the given MO2 instance."""
        profiles_dir = self.instance_root / instance / "profiles"
        if not profiles_dir.exists():
            return []
        return [
            d.name
            for d in profiles_dir.iterdir()
            if d.is_dir()
        ]

    def read_profile(self, instance: str, profile: str) -> MO2Profile:
        """
        Read and return the full mod list and load order for a profile.

        Parameters
        ----------
        instance:
            The MO2 instance name (sub-folder under the instance root).
        profile:
            The profile name.

        Returns
        -------
        MO2Profile
            Object containing the list of installed mods and their load order.
        """
        profile_dir = self.instance_root / instance / "profiles" / profile
        mods = self._read_modlist(profile_dir / "modlist.txt")
        load_order = self._read_plugins(profile_dir / "plugins.txt")
        return MO2Profile(
            profile_name=profile,
            mods=mods,
            load_order=load_order,
        )

    # ------------------------------------------------------------------
    # File parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_modlist(path: Path) -> list:
        """Parse ``modlist.txt`` and return a list of ``InstalledMod`` objects."""
        mods: list = []
        if not path.exists():
            return mods

        with path.open(encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                if line.startswith("+"):
                    mods.append(InstalledMod(name=line[1:], enabled=True))
                elif line.startswith("-"):
                    mods.append(InstalledMod(name=line[1:], enabled=False))
                # Lines starting with '*' are separator entries — skip them.

        return mods

    @staticmethod
    def _read_plugins(path: Path) -> list:
        """
        Parse ``plugins.txt`` and return an ordered list of active plugin names.
        The list preserves load order (first entry loads first).
        """
        plugins: list = []
        if not path.exists():
            return plugins

        with path.open(encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                # Active plugins are prefixed with '*' in newer MO2 versions.
                if line.startswith("*"):
                    plugins.append(line[1:])
                else:
                    plugins.append(line)
        return plugins

    # ------------------------------------------------------------------
    # Convenience: read from explicit file paths
    # ------------------------------------------------------------------

    @classmethod
    def from_files(
        cls,
        modlist_path: str,
        plugins_path: Optional[str] = None,
        profile_name: str = "custom",
    ) -> MO2Profile:
        """
        Build an ``MO2Profile`` directly from file paths.

        Useful when the user manually points the app at their MO2 files.
        """
        modlist_path_obj = Path(modlist_path)
        plugins_path_obj = Path(plugins_path) if plugins_path else None

        mods = cls._read_modlist(modlist_path_obj)
        load_order = (
            cls._read_plugins(plugins_path_obj) if plugins_path_obj else []
        )
        return MO2Profile(
            profile_name=profile_name,
            mods=mods,
            load_order=load_order,
        )

    # ------------------------------------------------------------------
    # Fuzzy name normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def normalise_name(name: str) -> str:
        """
        Normalise a mod name for fuzzy matching.

        Strips version suffixes, extra spaces, and lowercases the string so
        that ``"SKSE64 - 2.2.3"`` matches the Nexus page titled ``"SKSE64"``.
        """
        # Strip trailing version patterns like " - 2.2.3", "_v1.5", " v2.0"
        name = re.sub(r"[\s_]*[-v]\s*\d[\d.]*.*$", "", name, flags=re.IGNORECASE)
        name = re.sub(r"\s+", " ", name)
        return name.strip().lower()
