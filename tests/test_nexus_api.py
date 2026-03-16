"""Tests for NexusAPI wrapper (mocked HTTP)."""

import pytest
import responses as responses_lib
from requests.exceptions import ConnectionError as RequestsConnectionError, Timeout

from src.nexus.api import NexusAPI, NexusAPIError, RateLimitError, BASE_URL, SKYRIM_SE_DOMAIN


SAMPLE_MOD = {
    "mod_id": 3328,
    "game_id": 1704,
    "name": "SKSE64",
    "summary": "Script extender",
    "description": "<p>Full description</p>",
    "version": "2.2.3",
    "author": "ianpatt",
    "category_id": 39,
    "mod_downloads": 999999,
    "endorsement_count": 50000,
    "picture_url": "https://staticdelivery.nexusmods.com/mods/1704/images/3328.jpg",
}


@pytest.fixture
def api():
    return NexusAPI(api_key="FAKE_KEY_1234", game_domain=SKYRIM_SE_DOMAIN)


class TestNexusAPIInit:
    def test_raises_without_key(self):
        with pytest.raises(ValueError, match="API key"):
            NexusAPI(api_key="")

    def test_session_has_api_key_header(self, api):
        assert api._session.headers["apikey"] == "FAKE_KEY_1234"


class TestGetMod:
    @responses_lib.activate
    def test_get_mod_success(self, api):
        url = f"{BASE_URL}/games/{SKYRIM_SE_DOMAIN}/mods/3328.json"
        responses_lib.add(responses_lib.GET, url, json=SAMPLE_MOD, status=200)

        mod = api.get_mod(3328)
        assert mod["mod_id"] == 3328
        assert mod["name"] == "SKSE64"
        assert mod["author"] == "ianpatt"
        assert mod["downloads"] == 999999
        assert mod["mod_url"].startswith("https://www.nexusmods.com/")

    @responses_lib.activate
    def test_get_mod_rate_limit(self, api):
        url = f"{BASE_URL}/games/{SKYRIM_SE_DOMAIN}/mods/3328.json"
        responses_lib.add(responses_lib.GET, url, status=429)
        with pytest.raises(RateLimitError):
            api.get_mod(3328)

    @responses_lib.activate
    def test_get_mod_server_error(self, api):
        url = f"{BASE_URL}/games/{SKYRIM_SE_DOMAIN}/mods/3328.json"
        responses_lib.add(responses_lib.GET, url, status=500)
        with pytest.raises(NexusAPIError):
            api.get_mod(3328)


class TestGetModRequirements:
    @responses_lib.activate
    def test_get_mod_requirements_success(self, api):
        url = f"{BASE_URL}/games/{SKYRIM_SE_DOMAIN}/mods/3328/requirements.json"
        raw_requirements = [
            {"mod_id": 100, "name": "SKSE64"}
        ]
        responses_lib.add(responses_lib.GET, url, json=raw_requirements, status=200)

        result = api.get_mod_requirements(3328)
        assert len(result) == 1
        assert result[0]["required_mod_id"] == 100
        assert result[0]["required_name"] == "SKSE64"
        assert result[0]["required_url"] == f"https://www.nexusmods.com/{SKYRIM_SE_DOMAIN}/mods/100"
        assert result[0]["is_patch"] is False

    @responses_lib.activate
    def test_get_mod_requirements_empty(self, api):
        url = f"{BASE_URL}/games/{SKYRIM_SE_DOMAIN}/mods/9999/requirements.json"
        responses_lib.add(responses_lib.GET, url, json=[], status=200)

        result = api.get_mod_requirements(9999)
        assert result == []

    @responses_lib.activate
    def test_get_mod_requirements_patch_detection(self, api):
        url = f"{BASE_URL}/games/{SKYRIM_SE_DOMAIN}/mods/5000/requirements.json"
        raw_requirements = [
            {"mod_id": 200, "name": "Unofficial Skyrim Patch"},
            {"mod_id": 201, "name": "Bug Fix Collection"},
            {"mod_id": 202, "name": "Compatibility Tweaks"},
            {"mod_id": 203, "name": "Normal Texture Mod"},
        ]
        responses_lib.add(responses_lib.GET, url, json=raw_requirements, status=200)

        result = api.get_mod_requirements(5000)
        assert result[0]["is_patch"] is True   # "Patch"
        assert result[1]["is_patch"] is True   # "Fix"
        assert result[2]["is_patch"] is True   # "Compat"
        assert result[3]["is_patch"] is False  # none

    @responses_lib.activate
    def test_get_mod_requirements_missing_mod_id(self, api):
        url = f"{BASE_URL}/games/{SKYRIM_SE_DOMAIN}/mods/6000/requirements.json"
        raw_requirements = [
            {"name": "Some Requirement"}
        ]
        responses_lib.add(responses_lib.GET, url, json=raw_requirements, status=200)

        result = api.get_mod_requirements(6000)
        assert len(result) == 1
        assert result[0]["required_mod_id"] is None
        assert result[0]["required_name"] == "Some Requirement"
        assert result[0]["required_url"] == ""


class TestValidateKey:
    @responses_lib.activate
    def test_validate_returns_user_info(self, api):
        url = f"{BASE_URL}/users/validate.json"
        responses_lib.add(
            responses_lib.GET,
            url,
            json={"name": "Tester", "email": "t@example.com"},
            status=200,
        )
        info = api.validate_api_key()
        assert info["name"] == "Tester"


class TestErrorHandling:
    @responses_lib.activate
    def test_timeout_raises_nexus_api_error(self, api):
        url = f"{BASE_URL}/users/validate.json"
        responses_lib.add(
            responses_lib.GET,
            url,
            body=Timeout("Connection timed out"),
        )
        with pytest.raises(NexusAPIError, match="timed out"):
            api.validate_api_key()

    @responses_lib.activate
    def test_connection_error_raises_nexus_api_error(self, api):
        url = f"{BASE_URL}/users/validate.json"
        responses_lib.add(
            responses_lib.GET,
            url,
            body=RequestsConnectionError("DNS resolution failed"),
        )
        with pytest.raises(NexusAPIError, match="Network error"):
            api.validate_api_key()


class TestNormalisation:
    def test_normalise_mod_fields(self, api):
        normalised = api._normalise_mod(SAMPLE_MOD)
        assert normalised["mod_id"] == SAMPLE_MOD["mod_id"]
        assert normalised["downloads"] == SAMPLE_MOD["mod_downloads"]
        assert normalised["endorsements"] == SAMPLE_MOD["endorsement_count"]
        assert normalised["last_updated"] != ""

    def test_normalise_mod_uses_game_domain(self, api):
        normalised = api._normalise_mod(SAMPLE_MOD)
        assert f"/{SKYRIM_SE_DOMAIN}/mods/" in normalised["mod_url"]

    def test_normalise_search_result(self, api):
        raw = {
            "mod_id": 100,
            "name": "Some Mod",
            "description": "A short description",
            "username": "author_name",
            "version": "1.0",
            "downloads": 200,
            "endorsements": 10,
        }
        normalised = api._normalise_search_result(raw)
        assert normalised["mod_id"] == 100
        assert normalised["author"] == "author_name"
        assert normalised["summary"] == "A short description"
        assert f"/{SKYRIM_SE_DOMAIN}/mods/" in normalised["mod_url"]


class TestQuotaTracking:
    """Verify that daily_quota_remaining is updated from response headers."""

    def test_default_quota_is_unknown(self, api):
        assert api.daily_quota_remaining == "Unknown"

    @responses_lib.activate
    def test_quota_updated_from_response_headers(self, api):
        url = f"{BASE_URL}/users/validate.json"
        responses_lib.add(
            responses_lib.GET,
            url,
            json={"name": "Tester"},
            status=200,
            headers={
                "x-rl-daily-remaining": "95",
                "x-rl-hourly-remaining": "45",
            },
        )
        api.validate_api_key()
        assert api.daily_quota_remaining == "Daily: 95 | Hourly: 45"

    @responses_lib.activate
    def test_quota_missing_headers_shows_question_marks(self, api):
        url = f"{BASE_URL}/users/validate.json"
        responses_lib.add(
            responses_lib.GET,
            url,
            json={"name": "Tester"},
            status=200,
        )
        api.validate_api_key()
        assert api.daily_quota_remaining == "Daily: ? | Hourly: ?"

    @responses_lib.activate
    def test_quota_updated_on_mod_fetch(self, api):
        url = f"{BASE_URL}/games/{SKYRIM_SE_DOMAIN}/mods/3328.json"
        responses_lib.add(
            responses_lib.GET,
            url,
            json=SAMPLE_MOD,
            status=200,
            headers={
                "x-rl-daily-remaining": "80",
                "x-rl-hourly-remaining": "30",
            },
        )
        api.get_mod(3328)
        assert api.daily_quota_remaining == "Daily: 80 | Hourly: 30"
