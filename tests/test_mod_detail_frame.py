"""Tests for clean_bbcode() and get_resource_path() in src/gui/mod_detail_frame."""

import os
import sys

import pytest

from src.gui.mod_detail_frame import clean_bbcode, get_resource_path


class TestCleanBBCode:
    """Unit tests for the BBCode / HTML stripping helper."""

    # -- <br> conversion --------------------------------------------------

    def test_br_tag_to_newline(self):
        assert clean_bbcode("line1<br>line2") == "line1\nline2"

    def test_br_self_closing_to_newline(self):
        assert clean_bbcode("line1<br/>line2") == "line1\nline2"

    def test_br_self_closing_space_to_newline(self):
        assert clean_bbcode("line1<br />line2") == "line1\nline2"

    def test_br_case_insensitive(self):
        assert clean_bbcode("a<BR>b<Br/>c") == "a\nb\nc"

    # -- simple tag removal -----------------------------------------------

    @pytest.mark.parametrize(
        "tag",
        ["b", "i", "u", "center"],
    )
    def test_simple_tags_removed(self, tag):
        text = f"[{tag}]hello[/{tag}]"
        assert clean_bbcode(text) == "hello"

    @pytest.mark.parametrize(
        "tag",
        ["B", "I", "U", "CENTER"],
    )
    def test_simple_tags_case_insensitive(self, tag):
        text = f"[{tag}]hello[/{tag}]"
        assert clean_bbcode(text) == "hello"

    # -- parameterised tag removal ----------------------------------------

    def test_size_tag_removed(self):
        assert clean_bbcode("[size=3]big text[/size]") == "big text"

    def test_color_tag_removed(self):
        assert clean_bbcode("[color=#FF0000]red[/color]") == "red"

    def test_font_tag_removed(self):
        assert clean_bbcode("[font=Arial]styled[/font]") == "styled"

    # -- [url=...] conversion ---------------------------------------------

    def test_url_tag_keeps_link_text(self):
        text = "[url=https://example.com]Example[/url]"
        assert clean_bbcode(text) == "Example"

    def test_url_tag_case_insensitive(self):
        text = "[URL=https://example.com]Link[/URL]"
        assert clean_bbcode(text) == "Link"

    # -- [img] removal ----------------------------------------------------

    def test_img_tag_removed(self):
        assert clean_bbcode("[img]https://img.png[/img]") == ""

    def test_img_tag_case_insensitive(self):
        assert clean_bbcode("[IMG]https://img.png[/IMG]") == ""

    # -- [youtube] removal ------------------------------------------------

    def test_youtube_tag_removed(self):
        assert clean_bbcode("[youtube]abc123[/youtube]") == ""

    def test_youtube_tag_case_insensitive(self):
        assert clean_bbcode("[YOUTUBE]abc123[/YOUTUBE]") == ""

    # -- combined / realistic input ---------------------------------------

    def test_combined_markup(self):
        raw = (
            "[b]Title[/b]<br>"
            "[color=#FFF]Desc[/color]<br/>"
            "[url=https://nexus.com]Nexus[/url] "
            "[img]https://img.png[/img]"
            "[youtube]vid123[/youtube]"
        )
        expected = "Title\nDesc\nNexus "
        assert clean_bbcode(raw) == expected

    def test_plain_text_unchanged(self):
        assert clean_bbcode("just plain text") == "just plain text"

    def test_empty_string(self):
        assert clean_bbcode("") == ""


class TestGetResourcePath:
    """Unit tests for the PyInstaller-compatible resource path helper."""

    def test_returns_absolute_path_in_dev(self):
        result = get_resource_path("logo.png")
        assert os.path.isabs(result)
        assert result.endswith("logo.png")

    def test_uses_meipass_when_set(self, monkeypatch):
        monkeypatch.setattr(sys, "_MEIPASS", "/tmp/fake_meipass")
        result = get_resource_path("logo.png")
        assert result == os.path.join("/tmp/fake_meipass", "logo.png")

    def test_falls_back_to_cwd_without_meipass(self, monkeypatch):
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        result = get_resource_path("logo.png")
        expected = os.path.join(os.path.abspath("."), "logo.png")
        assert result == expected

    def test_handles_subdirectory_path(self):
        result = get_resource_path(os.path.join("assets", "logo.png"))
        assert result.endswith(os.path.join("assets", "logo.png"))
