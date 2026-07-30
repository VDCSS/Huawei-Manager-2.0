"""Testes de caracterização — PageBuilderManutencaoMixin (pages/manutencao.py).

Testa _display_watcher_results, _cancel_and_clear, _on_manut_filter_toggled.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from huawei_manager.pages.manutencao import PageBuilderManutencaoMixin


def _make_mixin(**attrs) -> PageBuilderManutencaoMixin:
    mixin = PageBuilderManutencaoMixin()
    defaults = dict(
        _manut_summary=MagicMock(),
        _manut_output=MagicMock(),
        _manut_filter="all",
        _last_manut_results=[],
        _cancel_event=None,
        _dispatch=MagicMock(side_effect=lambda fn: fn() if callable(fn) else None),
        _write=MagicMock(),
        _access_level="tecnico",
    )
    for k, v in defaults.items():
        setattr(mixin, k, v)
    for k, v in attrs.items():
        setattr(mixin, k, v)
    return mixin


def _make_result(name: str, status: str, items=None):
    r = MagicMock()
    r.name = name
    r.status = status
    r.summary = f"{name} summary"
    r.items = items or []
    return r


def _make_item(severity: str = "info"):
    item = MagicMock()
    item.severity = severity
    item.file = "test.py"
    item.message = "test message"
    item.suggestion = "fix it"
    return item


class TestDisplayWatcherResults:
    def test_sets_summary_text(self):
        mixin = _make_mixin()
        results = [_make_result("style", "ok"), _make_result("deps", "warning")]
        mixin._display_watcher_results(results)
        mixin._manut_summary.setPlainText.assert_called_once()
        text = mixin._manut_summary.setPlainText.call_args[0][0]
        assert "Total:" in text

    def test_counts_errors(self):
        mixin = _make_mixin()
        results = [_make_result("a", "error"), _make_result("b", "error")]
        mixin._display_watcher_results(results)
        text = mixin._manut_summary.setPlainText.call_args[0][0]
        assert "2" in text

    def test_writes_items_filtered(self):
        mixin = _make_mixin()
        item = _make_item("error")
        results = [_make_result("a", "error", items=[item])]
        mixin._display_watcher_results(results)
        mixin._write.assert_called()
        written = mixin._write.call_args[0][1]
        assert "test.py" in written

    def test_stores_last_results(self):
        mixin = _make_mixin()
        results = [_make_result("a", "ok")]
        mixin._display_watcher_results(results)
        assert mixin._last_manut_results is results


class TestCancelAndClear:
    def test_sets_event_when_exists(self):
        mixin = _make_mixin()
        cancel = MagicMock()
        mixin._cancel_event = cancel
        mixin._cancel_and_clear()
        cancel.set.assert_called_once()
        assert mixin._cancel_event is None

    def test_clears_output_when_no_event(self):
        mixin = _make_mixin()
        mixin._cancel_and_clear()
        mixin._write.assert_called_once_with(mixin._manut_output, "")


class TestOnManutFilterToggled:
    def test_sets_filter_when_checked(self):
        mixin = _make_mixin()
        mixin._on_manut_filter_toggled(True, "error")
        assert mixin._manut_filter == "error"

    def test_ignores_when_unchecked(self):
        mixin = _make_mixin()
        mixin._on_manut_filter_toggled(False, "error")
        assert mixin._manut_filter == "all"
