"""Tests for English translation strings in the GUI modules."""

import ast
import pytest

from src.gui.main_window import MainWindow
from src.gui.mod_detail_frame import clean_bbcode


class TestMainWindowEnglishStrings:
    """Verify that MainWindow contains the expected English UI strings."""

    def _get_source(self):
        """Return the source code of main_window.py as a string."""
        import inspect
        import src.gui.main_window as mod
        return inspect.getsource(mod)

    def test_app_title_in_english(self):
        assert MainWindow.APP_TITLE == "App-nexus — Skyrim Mod Compatibility Manager"

    @pytest.mark.parametrize(
        "english_string",
        [
            "Validate Key",
            "MO2 Profile:",
            "Browse…",
            "Load Mods",
            "Sync Nexus",
            "Analyse",
            "Update LOOT",
            "Installed Mods",
            "Mod Name",
            "Status",
            "Analysis Report",
            "Ready.",
            "Sync complete.",
            "No issues detected in the cached database.",
            "Nexus API Key:",
            "No API Key",
            "Validating API key",
            "API Key Valid",
            "Authenticated as:",
            "API Key Error",
            "API key validation failed.",
            "Select MO2 modlist.txt",
            "Text files",
            "No Path",
            "Load Error",
            "No Mod List",
            "Syncing mod",
            "Skipping",
            "already cached",
            "Rate limit reached",
            "API error for",
            "Error syncing",
            "Downloading LOOT masterlist",
            "LOOT masterlist updated",
            "LOOT update failed",
            "MISSING REQUIREMENTS",
            "[PATCH]",
            "[REQUIRED]",
            "required by",
            "LOOT INCOMPATIBILITIES",
            "conflicts with",
            "LOOT WARNINGS",
            "Mods analysed",
            "Missing mods",
            "LOOT conflicts",
            "LOOT warnings",
        ],
    )
    def test_english_string_present_in_source(self, english_string):
        source = self._get_source()
        assert english_string in source, (
            f"Expected English string '{english_string}' not found in main_window.py"
        )

    @pytest.mark.parametrize(
        "spanish_string",
        [
            "Validar Clave",
            "Perfil MO2:",
            "Explorar…",
            "Cargar Mods",
            "Sincronizar Nexus",
            "Analizar",
            "Actualizar LOOT",
            "Mods Instalados",
            "Nombre del Mod",
            "Reporte de Análisis",
            "Listo.",
            "Sincronización completa.",
            "No se detectaron problemas en la base de datos.",
            "Clave API Nexus:",
            "Sin Clave API",
            "Validando clave API",
            "Clave API Válida",
            "Autenticado como:",
            "Error de Clave API",
            "La validación de clave API falló.",
            "Seleccionar modlist.txt de MO2",
            "Archivos de texto",
            "Sin Ruta",
            "Error de Carga",
            "Sin Lista de Mods",
            "Sincronizando mod",
            "Omitiendo",
            "ya en caché",
            "Límite de consultas alcanzado",
            "Error de API para",
            "Error sincronizando",
            "Descargando masterlist de LOOT",
            "Masterlist de LOOT actualizada",
            "Actualización de LOOT falló",
            "REQUISITOS FALTANTES",
            "[PARCHE]",
            "[REQUERIDO]",
            "requerido por",
            "INCOMPATIBILIDADES LOOT",
            "en conflicto con",
            "ADVERTENCIAS LOOT",
            "Mods analizados",
            "Mods faltantes",
            "Conflictos LOOT",
            "Advertencias LOOT",
        ],
    )
    def test_spanish_string_absent_from_source(self, spanish_string):
        source = self._get_source()
        assert spanish_string not in source, (
            f"Spanish string '{spanish_string}' should have been translated "
            f"in main_window.py"
        )


class TestModDetailFrameEnglishStrings:
    """Verify that ModDetailFrame contains the expected English UI strings."""

    def _get_source(self):
        import inspect
        import src.gui.mod_detail_frame as mod
        return inspect.getsource(mod)

    @pytest.mark.parametrize(
        "english_string",
        [
            "Select a mod",
            "Open on Nexus Mods",
            "Summary",
            "Description",
            "Requirements",
            "No summary available.",
            "No description cached. Try syncing this mod.",
            "Required Mod",
            "Type",
            "Patch",
            "Required",
        ],
    )
    def test_english_string_present_in_source(self, english_string):
        source = self._get_source()
        assert english_string in source, (
            f"Expected English string '{english_string}' not found in mod_detail_frame.py"
        )

    @pytest.mark.parametrize(
        "spanish_string",
        [
            "Seleccioná un mod",
            "Abrir en Nexus Mods",
            "Resumen",
            "Descripción",
            "Requisitos",
            "Resumen no disponible.",
            "Descripción no almacenada. Intentá sincronizar este mod.",
            "Mod Requerido",
            "Tipo",
            "Parche",
            "Requerido",
        ],
    )
    def test_spanish_string_absent_from_source(self, spanish_string):
        source = self._get_source()
        assert spanish_string not in source, (
            f"Spanish string '{spanish_string}' should have been translated "
            f"in mod_detail_frame.py"
        )
