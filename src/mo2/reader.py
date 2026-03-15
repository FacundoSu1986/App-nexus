"""
MO2 (Mod Organizer 2) reader.

Reads modlist.txt and plugins.txt from an MO2 profile directory to determine
which mods are installed and their load order.
"""

from __future__ import annotations

import configparser
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class InstalledMod:
    """A mod entry from modlist.txt."""

    name: str
    enabled: bool
    nexus_id: str = "0"
    version: str = "?"
    esp_masters: list[str] = field(default_factory=list)


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
    def _read_meta_ini(mods_folder: Path, mod_name: str) -> dict:
        """Read ``meta.ini`` from a mod folder and return nexus_id + version."""
        meta_path = mods_folder / mod_name / "meta.ini"
        result = {"nexus_id": "0", "version": "?"}
        if not meta_path.is_file():
            return result
        parser = configparser.RawConfigParser()
        parser.read(str(meta_path), encoding="utf-8")
        if parser.has_section("General"):
            result["nexus_id"] = parser.get("General", "modid", fallback="0")
            result["version"] = parser.get("General", "version", fallback="?")
        return result

    @staticmethod
    def read_esp_masters(esp_path: Path) -> list[str]:
        """Read MAST (master file) records from a ``.esp``/``.esm``/``.esl`` header.

        The method parses the binary TES4 record header and returns an ordered
        list of master plugin filenames that the given plugin depends on.
        Returns an empty list when the file is missing, too small, or does not
        start with a valid TES4 record.
        """
        if not esp_path.is_file():
            return []
        try:
            with open(esp_path, "rb") as fh:
                # TES4 record header: type(4) + datasize(4) + flags(4)
                #   + formid(4) + vc(4) + formver(2) + unk(2) = 24 bytes
                header = fh.read(24)
                if len(header) < 24 or header[:4] != b"TES4":
                    return []
                data_size = struct.unpack_from("<I", header, 4)[0]
                data = fh.read(data_size)
        except OSError:
            return []

        masters: list[str] = []
        offset = 0
        while offset + 6 <= len(data):
            sub_type = data[offset: offset + 4]
            sub_size = struct.unpack_from("<H", data, offset + 4)[0]
            offset += 6
            if offset + sub_size > len(data):
                break
            if sub_type == b"MAST":
                raw = data[offset: offset + sub_size]
                name = raw.rstrip(b"\x00").decode("utf-8", errors="replace")
                if name:
                    masters.append(name)
            offset += sub_size
        return masters

    @staticmethod
    def _collect_mod_masters(
        mods_folder: Path, mod_name: str,
    ) -> list[str]:
        """Scan a mod folder for plugins and return all unique masters."""
        mod_dir = mods_folder / mod_name
        if not mod_dir.is_dir():
            return []
        masters: list[str] = []
        seen: set[str] = set()
        for ext in ("*.esp", "*.esm", "*.esl"):
            for plugin_path in mod_dir.glob(ext):
                for m in MO2Reader.read_esp_masters(plugin_path):
                    key = m.lower()
                    if key not in seen:
                        seen.add(key)
                        masters.append(m)
        return masters

    @staticmethod
    def _read_modlist(path: Path, mods_folder: Optional[Path] = None) -> list[InstalledMod]:
        """Parse ``modlist.txt`` into a list of ``InstalledMod``."""
        if not path.is_file():
            return []
        # mods folder is typically the sibling "mods" directory of the
        # profiles directory, e.g. …/MO2/mods/ when modlist.txt is at
        # …/MO2/profiles/Default/modlist.txt
        if mods_folder is None:
            mods_folder = path.parent.parent.parent / "mods"
        mods = []
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("*"):
                continue
            if line.startswith("+"):
                mod_name = line[1:]
                meta = MO2Reader._read_meta_ini(mods_folder, mod_name)
                masters = MO2Reader._collect_mod_masters(mods_folder, mod_name)
                mods.append(InstalledMod(
                    name=mod_name,
                    enabled=True,
                    nexus_id=meta["nexus_id"],
                    version=meta["version"],
                    esp_masters=masters,
                ))
            elif line.startswith("-"):
                mod_name = line[1:]
                meta = MO2Reader._read_meta_ini(mods_folder, mod_name)
                masters = MO2Reader._collect_mod_masters(mods_folder, mod_name)
                mods.append(InstalledMod(
                    name=mod_name,
                    enabled=False,
                    nexus_id=meta["nexus_id"],
                    version=meta["version"],
                    esp_masters=masters,
                ))
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
        mods_folder: Optional[str] = None,
    ) -> MO2Profile:
        """Create an ``MO2Profile`` directly from file paths.

        Parameters
        ----------
        mods_folder:
            Optional path to the MO2 *mods* directory.  When provided, each
            mod's ``.esp``/``.esm``/``.esl`` plugins are scanned for MAST
            records and the results are stored in
            :py:attr:`InstalledMod.esp_masters`.
        """
        folder = Path(mods_folder) if mods_folder else None
        mods = cls._read_modlist(Path(modlist_path), mods_folder=folder)
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
