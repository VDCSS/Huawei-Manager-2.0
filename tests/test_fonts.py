"""Testes de caracterização — pacote Google Fonts (E1).

Verifica que as constantes de fontes usam IBM Plex Sans (UI), Space Grotesk (títulos),
JetBrains Mono (código) com fallbacks Inter/Consolas.
"""
from __future__ import annotations

from huawei_manager.constants import (
    _FONT_UI_FAMILY,
    _FONT_UI_TITLE_FAMILY,
    _FONT_MONO_FAMILY,
    _FALLBACK_UI,
    _FALLBACK_MONO,
    FONT_UI_MEDIUM,
    FONT_UI_TITLE,
    FONT_LARGE,
)


class TestFontFamilies:
    def test_ui_family_is_ibm_plex_sans(self):
        assert _FONT_UI_FAMILY == "IBM Plex Sans"

    def test_ui_title_family_is_space_grotesk(self):
        assert _FONT_UI_TITLE_FAMILY == "Space Grotesk"

    def test_mono_family_is_jetbrains_mono(self):
        assert _FONT_MONO_FAMILY == "JetBrains Mono"

    def test_fallback_ui_is_inter(self):
        assert _FALLBACK_UI == "Inter"

    def test_fallback_mono_is_consolas(self):
        assert _FALLBACK_MONO == "Consolas"


class TestFontTuplesUseNewFamilies:
    def test_font_ui_medium_uses_ibm_plex_sans(self):
        # FONT_UI_MEDIUM = (family, size, fallback)
        assert FONT_UI_MEDIUM[0] == "IBM Plex Sans"
        assert FONT_UI_MEDIUM[2] == "Inter"

    def test_font_ui_title_uses_space_grotesk(self):
        assert FONT_UI_TITLE[0] == "Space Grotesk"
        assert FONT_UI_TITLE[2] == "Inter"

    def test_font_large_uses_jetbrains_mono(self):
        assert FONT_LARGE[0] == "JetBrains Mono"
        assert FONT_LARGE[2] == "Consolas"