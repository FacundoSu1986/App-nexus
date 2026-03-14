"""Tests for NexusScraper (mocked HTTP)."""

import pytest
import responses as responses_lib

from src.nexus.scraper import NexusScraper, NEXUS_BASE, SKYRIM_SE_PATH


# ---------------------------------------------------------------------------
# Requirements parsing
# ---------------------------------------------------------------------------

REQUIREMENTS_HTML = """
<html><body>
  <div id="requirements">
    <ul>
      <li><a href="/skyrimspecialedition/mods/100">SKSE64</a></li>
      <li><a href="/skyrimspecialedition/mods/200">SkyUI Patch</a></li>
    </ul>
  </div>
</body></html>
"""

ISSUES_HTML = """
<html><body>
  <ul class="bugs-list">
    <li>
      <h3><a href="https://www.nexusmods.com/bugs/1">CTD on startup</a></h3>
      <p>Game crashes immediately.</p>
      <span class="username">user123</span>
      <time datetime="2024-02-01T10:00:00">Feb 1</time>
    </li>
  </ul>
</body></html>
"""

INCOMPAT_HTML = """
<html><body>
  <p>This mod is <strong>incompatible</strong> with
     <a href="/skyrimspecialedition/mods/99">BadMod</a>.</p>
</body></html>
"""


@pytest.fixture
def scraper():
    return NexusScraper(delay=0)  # no throttle in tests


class TestGetRequirements:
    @responses_lib.activate
    def test_parses_requirement_links(self, scraper):
        url = f"{NEXUS_BASE}{SKYRIM_SE_PATH}/3328"
        responses_lib.add(
            responses_lib.GET, url, body=REQUIREMENTS_HTML, status=200,
            content_type="text/html",
        )
        reqs = scraper.get_requirements(3328)
        names = [r["required_name"] for r in reqs]
        assert "SKSE64" in names

    @responses_lib.activate
    def test_patch_keyword_detection(self, scraper):
        url = f"{NEXUS_BASE}{SKYRIM_SE_PATH}/3328"
        responses_lib.add(
            responses_lib.GET, url, body=REQUIREMENTS_HTML, status=200,
            content_type="text/html",
        )
        reqs = scraper.get_requirements(3328)
        patch_reqs = [r for r in reqs if r["is_patch"]]
        assert any("Patch" in r["required_name"] for r in patch_reqs)

    @responses_lib.activate
    def test_empty_when_no_requirements_section(self, scraper):
        url = f"{NEXUS_BASE}{SKYRIM_SE_PATH}/9999"
        responses_lib.add(
            responses_lib.GET, url,
            body="<html><body><p>No requirements here.</p></body></html>",
            status=200,
            content_type="text/html",
        )
        reqs = scraper.get_requirements(9999)
        assert reqs == []


class TestGetIssues:
    @responses_lib.activate
    def test_parses_bug_entries(self, scraper):
        url = f"{NEXUS_BASE}{SKYRIM_SE_PATH}/3328"
        responses_lib.add(
            responses_lib.GET, url,
            body=ISSUES_HTML, status=200,
            content_type="text/html",
        )
        issues = scraper.get_issues(3328, max_pages=1)
        assert len(issues) >= 1
        assert "CTD on startup" in issues[0]["title"]

    @responses_lib.activate
    def test_no_issues_when_no_bugs_section(self, scraper):
        url = f"{NEXUS_BASE}{SKYRIM_SE_PATH}/9999"
        responses_lib.add(
            responses_lib.GET, url,
            body="<html><body></body></html>",
            status=200,
            content_type="text/html",
        )
        issues = scraper.get_issues(9999, max_pages=1)
        assert issues == []


class TestIncompatibilityDetection:
    def test_detects_incompatibility_in_description(self, scraper):
        incompat = scraper.get_incompatibilities_from_description(INCOMPAT_HTML)
        assert len(incompat) >= 1
        assert any("BadMod" in i["incompatible_name"] for i in incompat)

    def test_empty_when_no_incompatibilities(self, scraper):
        result = scraper.get_incompatibilities_from_description(
            "<html><body><p>This mod works great!</p></body></html>"
        )
        assert result == []
