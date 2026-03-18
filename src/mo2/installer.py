"""
MO2 mod installer.

Extracts a downloaded mod archive into the MO2 mods folder and activates it
in the MO2 profile's modlist.txt.
"""

from __future__ import annotations

import logging
import os
import shutil

import py7zr

logger = logging.getLogger(__name__)


def install_mod(
    archive_path: str,
    mod_name: str,
    mo2_base_path: str,
    profile_name: str = "Default",
) -> bool:
    """Install a mod archive into MO2 and activate it in the profile.

    Parameters
    ----------
    archive_path:
        Path to the downloaded mod archive (.7z, .zip, etc.).
    mod_name:
        Human-readable name for the mod (used as the folder name).
    mo2_base_path:
        Root path of the MO2 installation.
    profile_name:
        MO2 profile to activate the mod in (default ``"Default"``).

    Returns
    -------
    bool
        ``True`` if the mod was installed and activated successfully.
    """
    # ------------------------------------------------------------------
    # 1. Validate archive
    # ------------------------------------------------------------------
    if not os.path.isfile(archive_path):
        logger.error("Archive not found: %s", archive_path)
        return False

    # ------------------------------------------------------------------
    # 2. Extract archive
    # ------------------------------------------------------------------
    target_dir = os.path.join(mo2_base_path, "mods", mod_name)
    logger.info("Extracting '%s' to '%s'", archive_path, target_dir)

    try:
        os.makedirs(target_dir, exist_ok=True)

        if archive_path.lower().endswith(".7z"):
            with py7zr.SevenZipFile(archive_path, mode="r") as archive:
                archive.extractall(path=target_dir)
        else:
            shutil.unpack_archive(archive_path, target_dir)

        logger.info("Extraction complete for '%s'", mod_name)
    except Exception:
        logger.error("Extraction failed for '%s'", mod_name, exc_info=True)
        shutil.rmtree(target_dir, ignore_errors=True)
        return False

    # ------------------------------------------------------------------
    # 3. Activate in modlist.txt
    # ------------------------------------------------------------------
    modlist_path = os.path.join(
        mo2_base_path, "profiles", profile_name, "modlist.txt"
    )
    enabled_entry = f"+{mod_name}"
    disabled_entry = f"-{mod_name}"

    try:
        if os.path.isfile(modlist_path):
            with open(modlist_path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
        else:
            lines = []

        # Check whether the mod is already listed
        found = False
        for idx, line in enumerate(lines):
            stripped = line.rstrip("\n")
            if stripped == enabled_entry:
                logger.info("Mod '%s' already enabled in modlist.txt", mod_name)
                found = True
                break
            if stripped == disabled_entry:
                lines[idx] = enabled_entry + "\n"
                logger.info(
                    "Re-enabled mod '%s' in modlist.txt", mod_name
                )
                found = True
                break

        if not found:
            lines.append(enabled_entry + "\n")
            logger.info("Appended mod '%s' to modlist.txt", mod_name)

        with open(modlist_path, "w", encoding="utf-8") as fh:
            fh.writelines(lines)

    except Exception:
        logger.error(
            "Failed to update modlist.txt for '%s'", mod_name, exc_info=True
        )
        return False

    logger.info("Mod '%s' installed and activated successfully", mod_name)
    return True
