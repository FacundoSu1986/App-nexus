"""Tests for MO2 mod installer."""

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.mo2.installer import install_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_mo2(tmp_path: Path, modlist_content: str = "") -> Path:
    """Create a minimal MO2 folder structure under *tmp_path*."""
    mods_dir = tmp_path / "mods"
    mods_dir.mkdir()
    profile_dir = tmp_path / "profiles" / "Default"
    profile_dir.mkdir(parents=True)
    modlist = profile_dir / "modlist.txt"
    modlist.write_text(textwrap.dedent(modlist_content), encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Extraction tests (mocked)
# ---------------------------------------------------------------------------

class TestExtraction:
    """Verify that archives are extracted correctly."""

    @patch("src.mo2.installer.py7zr.SevenZipFile")
    def test_7z_extraction(self, mock_7z_cls, tmp_path):
        mo2 = _setup_mo2(tmp_path)
        archive = tmp_path / "mod.7z"
        archive.write_text("fake")

        mock_ctx = MagicMock()
        mock_7z_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_7z_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = install_mod(str(archive), "TestMod", str(mo2))

        assert result is True
        mock_7z_cls.assert_called_once_with(str(archive), mode="r")
        mock_ctx.extractall.assert_called_once()

    @patch("src.mo2.installer.shutil.unpack_archive")
    def test_zip_extraction(self, mock_unpack, tmp_path):
        mo2 = _setup_mo2(tmp_path)
        archive = tmp_path / "mod.zip"
        archive.write_text("fake")

        result = install_mod(str(archive), "ZipMod", str(mo2))

        assert result is True
        mock_unpack.assert_called_once()

    @patch("src.mo2.installer.py7zr.SevenZipFile")
    def test_7z_uppercase_extension(self, mock_7z_cls, tmp_path):
        mo2 = _setup_mo2(tmp_path)
        archive = tmp_path / "MOD.7Z"
        archive.write_text("fake")

        mock_ctx = MagicMock()
        mock_7z_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_7z_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = install_mod(str(archive), "UpperMod", str(mo2))

        assert result is True
        mock_7z_cls.assert_called_once()


# ---------------------------------------------------------------------------
# modlist.txt activation tests
# ---------------------------------------------------------------------------

class TestModlistActivation:
    """Verify modlist.txt is updated correctly."""

    @patch("src.mo2.installer.shutil.unpack_archive")
    def test_append_new_mod(self, mock_unpack, tmp_path):
        mo2 = _setup_mo2(tmp_path, modlist_content="+ExistingMod\n")
        archive = tmp_path / "mod.zip"
        archive.write_text("fake")

        install_mod(str(archive), "NewMod", str(mo2))

        modlist = (mo2 / "profiles" / "Default" / "modlist.txt").read_text(
            encoding="utf-8"
        )
        assert "+NewMod\n" in modlist
        assert "+ExistingMod\n" in modlist

    @patch("src.mo2.installer.shutil.unpack_archive")
    def test_reenable_disabled_mod(self, mock_unpack, tmp_path):
        mo2 = _setup_mo2(tmp_path, modlist_content="-DisabledMod\n")
        archive = tmp_path / "mod.zip"
        archive.write_text("fake")

        install_mod(str(archive), "DisabledMod", str(mo2))

        modlist = (mo2 / "profiles" / "Default" / "modlist.txt").read_text(
            encoding="utf-8"
        )
        assert "+DisabledMod\n" in modlist
        assert "-DisabledMod" not in modlist

    @patch("src.mo2.installer.shutil.unpack_archive")
    def test_already_enabled_mod_unchanged(self, mock_unpack, tmp_path):
        mo2 = _setup_mo2(tmp_path, modlist_content="+AlreadyEnabled\n")
        archive = tmp_path / "mod.zip"
        archive.write_text("fake")

        result = install_mod(str(archive), "AlreadyEnabled", str(mo2))

        assert result is True
        modlist = (mo2 / "profiles" / "Default" / "modlist.txt").read_text(
            encoding="utf-8"
        )
        assert modlist.count("+AlreadyEnabled") == 1


# ---------------------------------------------------------------------------
# Error handling & cleanup
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Verify cleanup and error paths."""

    def test_missing_archive_returns_false(self, tmp_path):
        mo2 = _setup_mo2(tmp_path)
        result = install_mod("/nonexistent/mod.7z", "Ghost", str(mo2))
        assert result is False

    @patch("src.mo2.installer.shutil.unpack_archive", side_effect=RuntimeError("corrupt"))
    def test_cleanup_on_extraction_failure(self, mock_unpack, tmp_path):
        mo2 = _setup_mo2(tmp_path)
        archive = tmp_path / "bad.zip"
        archive.write_text("broken")

        result = install_mod(str(archive), "BadMod", str(mo2))

        assert result is False
        target = mo2 / "mods" / "BadMod"
        assert not target.exists(), "Partial folder should be cleaned up"
