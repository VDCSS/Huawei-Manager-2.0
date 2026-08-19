"""Testes de caracterização — paridade dark/light em output, hover e cores semânticas (D1+D2+D3).

Verifica que:
- o QTextEdit read-only usa cor theme-aware (FG_CODE), não #b0b0d0 hardcoded;
- NeonButton deriva hover/active de BG_INPUT/BG_SIDEBAR, não de #1a1a3a/#1a1a3e;
- NEON_RED_L/NEON_AMBER_L existem, entram no LIGHT_THEME e têm contraste WCAG AA ≥ 4.5:1
  sobre BG_CARD_L (#ffffff).
"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

import huawei_manager.constants as C
from huawei_manager.widgets.neon_button import NeonButton
from huawei_manager.widgets.neon_entry import output_text


def _luminance(hex_color: str) -> float:
    def chan(v: int) -> float:
        s = v / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def _contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


class TestSemanticColors:
    def test_light_theme_has_red_and_amber(self):
        assert C.LIGHT_THEME["NEON_RED"] == C.NEON_RED_L
        assert C.LIGHT_THEME["NEON_AMBER"] == C.NEON_AMBER_L

    def test_red_contrast_aa_on_white(self):
        assert _contrast(C.NEON_RED_L, C.BG_CARD_L) >= 4.5

    def test_amber_contrast_aa_on_white(self):
        assert _contrast(C.NEON_AMBER_L, C.BG_CARD_L) >= 4.5

    def test_set_theme_light_swaps_red(self):
        original = C.NEON_RED
        try:
            C.set_theme("light")
            assert C.NEON_RED == C.NEON_RED_L
        finally:
            C.set_theme("dark")
            assert C.NEON_RED == original


class TestOutputThemeAware:
    def test_readonly_uses_fg_code(self):
        QApplication.instance() or QApplication([])
        ed = output_text()
        css = ed.styleSheet()
        assert f"color: {C.FG_CODE}" in css
        assert "#b0b0d0" not in css

    def test_readonly_block_theme_aware(self):
        # O bloco read-only herda FG_CODE (varia com o tema), nunca cor fixa.
        QApplication.instance() or QApplication([])
        ed = output_text()
        block = ed.styleSheet().split("read-only")[1]
        assert f"color: {C.FG_CODE}" in block


class TestNeonButtonThemeAware:
    def test_active_bg_derived_from_input(self):
        QApplication.instance() or QApplication([])
        btn = NeonButton(None, "x", None, C.NEON_CYAN)
        btn._active = True
        btn._apply_style()
        css = btn.styleSheet()
        assert f"background-color: {C.BG_INPUT}" in css
        assert "#1a1a3a" not in css

    def test_hover_bg_derived_from_input(self):
        QApplication.instance() or QApplication([])
        btn = NeonButton(None, "x", None, C.NEON_CYAN)
        btn._apply_style()
        css = btn.styleSheet()
        assert f"background-color: {C.BG_INPUT}" in css.split("hover")[1]
        assert "#1a1a3e" not in css

    def test_focus_rule_border_left(self):
        QApplication.instance() or QApplication([])
        btn = NeonButton(None, "x", None, C.NEON_CYAN)
        btn._apply_style()
        css = btn.styleSheet()
        assert "NeonButton:focus" in css
        assert "border-left: 4px solid" in css

    def test_action_button_focus_border_color(self):
        from huawei_manager.widgets.neon_button import ActionButton
        QApplication.instance() or QApplication([])
        btn = ActionButton(None, "x", None, C.NEON_CYAN)
        btn._apply_style()
        css = btn.styleSheet()
        assert "ActionButton:focus" in css
        assert "border-color:" in css


class TestContrastAA:
    def test_fg_dim_contrast_aa_on_dark(self):
        assert _contrast(C.FG_DIM, C.BG_BASE) >= 4.5

    def test_neon_purp_contrast_aa_on_dark(self):
        assert _contrast(C.NEON_PURP, C.BG_BASE) >= 4.5

    def test_fg_dim_light_contrast_aa_on_white(self):
        assert _contrast(C.FG_DIM_L, C.BG_CARD_L) >= 4.5

    def test_neon_purp_light_contrast_aa_on_white(self):
        assert _contrast(C.NEON_PURP_L, C.BG_CARD_L) >= 4.5


class TestFocusRules:
    def test_themes_qss_listwidget_focus_paired(self):
        from huawei_manager.themes import QSS_DARK, QSS_LIGHT
        assert "QListWidget:focus" in QSS_DARK
        assert "border-color: #00e5ff" in QSS_DARK
        assert "QListWidget:focus" in QSS_LIGHT
        assert "border-color: #0098a0" in QSS_LIGHT

    def test_services_qss_listwidget_focus_paired(self):
        import huawei_manager.pages.services as svc
        import inspect
        source = inspect.getsource(svc.PageBuilderServicesMixin._build_services_split)
        assert "QListWidget:focus" in source
        assert "border:" in source and "NEON_CYAN" in source


class TestTemplatesAccessible:
    def test_cmd_templates_use_qlistwidget(self):
        from huawei_manager.pages.builder import PageBuilder
        from huawei_manager.widgets.neon_button import ActionButton
        from PySide6.QtWidgets import QListWidget, QStackedWidget
        from PySide6.QtCore import Qt
        from unittest.mock import MagicMock
        QApplication.instance() or QApplication([])
        builder = PageBuilder()
        builder._page_container = QStackedWidget()
        builder._access_level = "user"
        builder._target_device = None
        builder._run = MagicMock()
        builder._get_editor_cmd = MagicMock(return_value="display version")
        builder._exec_cmd = MagicMock()
        builder._exec_config = MagicMock()
        builder._build_cmd_page()
        page = builder._page_container.widget(0)
        tpl_list = page.findChild(QListWidget)
        assert tpl_list is not None
        assert tpl_list.count() > 0
        assert tpl_list.focusPolicy() == Qt.FocusPolicy.StrongFocus


class TestNoPixelSize:
    def test_no_setpixelsize_in_src(self):
        import subprocess
        result = subprocess.run(
            ["grep", "-rn", "pixelSize", "src/huawei_manager/"],
            capture_output=True, text=True
        )
        assert result.returncode == 1, f"pixelSize found: {result.stdout}"
