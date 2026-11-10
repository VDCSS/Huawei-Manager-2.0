"""Testes dos helpers de UI puros (tabs/_ui.py) — herdeiros do PageBuilder.

O ``pages/builder.py`` (husk da F2) foi dissolvido na F3: os helpers
puros vivem em ``tabs/_ui.py`` e as abas os chamam via módulo.
"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication, QVBoxLayout

from huawei_manager.tabs import _ui


class TestCssLabel:
    def test_basic_css(self):
        result = _ui.css_label("#fff", "#000", 12, True)
        assert "#fff" in result
        assert "#000" in result
        assert "12px" in result
        assert "bold" in result

    def test_no_background(self):
        assert "background:" not in _ui.css_label("#fff")

    def test_normal_weight(self):
        assert "normal" in _ui.css_label("#fff", bold=False)


class TestPageFrame:
    def test_object_name_and_layout(self):
        app = QApplication.instance() or QApplication([])
        p = _ui.page_frame("cmd")
        assert p.objectName() == "page_cmd"
        assert isinstance(p.layout(), QVBoxLayout)
        assert app is not None
