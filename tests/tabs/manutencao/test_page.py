"""Testes de caracterização — ManutencaoTab (tabs/manutencao/page.py).

Cobrem _display_results (paridade com _display_watcher_results legado) e
_on_manut_filter_toggled. cancel_and_clear vive nos handlers — coberto em
test_handlers.py (mesmos asserts do legado).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.manutencao.page import ManutencaoTab
from huawei_manager.tabs.manutencao.state import ManutencaoState


def _make_ctx(**overrides: Any) -> TabContext:
    """TabContext fake — mesmos defaults de test_handlers.py."""
    fields: dict[str, Any] = dict(
        sb=MagicMock(),
        audit=None,
        event_bus=MagicMock(),
        role=lambda: "tecnico",
        device=lambda: None,
        dispatch=lambda fn: fn() if callable(fn) else None,
        require_access=lambda level: True,
        spawn_io=lambda fn, *args: fn(*args),
        spawn_cpu=lambda fn, *args: fn(*args),
        watcher=MagicMock(),
        is_mock=lambda: False,
        toggle_mock=lambda: False,
        show_auth_dialog=lambda: None,
        watcher_results=lambda: None,
        set_watcher_results=MagicMock(),
    )
    fields.update(overrides)
    return TabContext(**fields)


def _make_tab(**ctx_overrides: Any) -> tuple[ManutencaoTab, ManutencaoState]:
    """Aba com estado/UI listeners prontos, SEM build (lógica pura)."""
    tab = ManutencaoTab()
    tab._ctx = _make_ctx(**ctx_overrides)
    st = tab.state
    st.output = MagicMock()
    st.summary = MagicMock()
    return tab, st


def _make_result(name, status, items=None):
    r = MagicMock()
    r.name = name
    r.status = status
    r.summary = f"{name} summary"
    r.items = items if items is not None else []
    return r


def _make_item(severity="info"):
    it = MagicMock()
    it.severity = severity
    it.file = "test.py"
    it.message = "test message"
    it.suggestion = "fix it"
    return it


class TestDisplayResults:
    def test_sets_summary_text(self):
        tab, st = _make_tab()
        results = [_make_result("style", "ok"),
                   _make_result("deps", "warning")]
        tab._display_results(results)
        st.summary.setPlainText.assert_called_once()
        text = st.summary.setPlainText.call_args[0][0]
        assert "Total:" in text

    def test_counts_errors(self):
        tab, st = _make_tab()
        results = [_make_result("a", "error"), _make_result("b", "error")]
        tab._display_results(results)
        text = st.summary.setPlainText.call_args[0][0]
        assert "2" in text

    def test_writes_items_filtered(self):
        tab, st = _make_tab()
        item = _make_item("error")
        results = [_make_result("a", "error", items=[item])]
        tab._display_results(results)
        texts = [str(c.args[0])
                 for c in st.output.setPlainText.call_args_list]
        assert any("test.py" in t for t in texts)

    def test_stores_last_results(self):
        tab, st = _make_tab()
        results = [_make_result("a", "ok")]
        tab._display_results(results)
        assert st.last_results is results


class TestOnManutFilterToggled:
    def test_sets_filter_when_checked(self):
        tab, st = _make_tab()
        tab._on_manut_filter_toggled(True, "error")
        assert st.active_filter == "error"

    def test_ignores_when_unchecked(self):
        tab, st = _make_tab()
        tab._on_manut_filter_toggled(False, "error")
        assert st.active_filter == "all"
