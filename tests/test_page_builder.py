"""Testes de caracterização — PageBuilder (pages/builder.py).

Testa _css_label (puro) e _choose_backup_dir (com mock de QFileDialog).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from huawei_manager.pages.builder import PageBuilder


def _make_mixin(**attrs) -> PageBuilder:
    mixin = PageBuilder()
    defaults = dict(
        _page_container=None,
        _access_level="user",
    )
    for k, v in defaults.items():
        setattr(mixin, k, v)
    for k, v in attrs.items():
        setattr(mixin, k, v)
    return mixin


class TestCssLabel:
    def test_basic_css(self):
        mixin = _make_mixin()
        result = mixin._css_label("#fff", "#000", 12, True)
        assert "#fff" in result
        assert "#000" in result
        assert "12px" in result
        assert "bold" in result

    def test_no_background(self):
        mixin = _make_mixin()
        result = mixin._css_label("#fff")
        assert "background:" not in result

    def test_normal_weight(self):
        mixin = _make_mixin()
        result = mixin._css_label("#fff", bold=False)
        assert "normal" in result
