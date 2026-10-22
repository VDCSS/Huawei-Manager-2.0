"""Testes da aba Info do Sistema — InfoHandlers (tabs/info/handlers.py).

Migrados de tests/test_fetch_mixin.py (F2-info do plano
plano-abas-independentes). _fetch_info era o último método do
FetchMixin — o mixin legado foi removido junto com fetch.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from huawei_manager.exceptions import SdnError
from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.info.handlers import InfoHandlers
from huawei_manager.tabs.info.state import InfoState


def _make(**overrides) -> tuple[InfoHandlers, InfoState, TabContext]:
    """(handlers, state, ctx) — drv é getter no ctx (lambda sobre o mock)."""
    drv = overrides.pop("drv", MagicMock())
    fields: dict = dict(
        sb=MagicMock(),
        audit=None,
        event_bus=MagicMock(),
        role=lambda: "admin",
        device=lambda: None,
        dispatch=lambda fn: fn() if callable(fn) else None,
        require_access=lambda level: True,
        spawn_io=lambda fn, *a: fn(*a),
        spawn_cpu=lambda fn, *a: fn(*a),
        watcher=MagicMock(),
        is_mock=lambda: False,
        toggle_mock=lambda: False,
        show_auth_dialog=lambda: None,
        watcher_results=lambda: None,
        set_watcher_results=MagicMock(),
        session=MagicMock(),
        run=MagicMock(),
        set_status=MagicMock(),
        touch_session=MagicMock(),
        cmd_validator=None,
        dry_run=None,
        get_last_config_command=MagicMock(return_value=None),
        set_last_config_command=MagicMock(),
        drv=lambda: drv,
        devices=lambda: [],
        show_page=MagicMock(),
        svc_mode=lambda: "mock",
        ui_bridge=lambda: None,
        ensure_device_ready=MagicMock(return_value=None),
    )
    fields.update(overrides)
    ctx = TabContext(**fields)
    state = InfoState()
    state.out = MagicMock()
    return InfoHandlers(ctx, state), state, ctx


def _output_texts(out) -> str:
    """Concatena tudo que foi 'escrito' no out (setPlainText + append)."""
    parts = []
    for c in out.setPlainText.call_args_list:
        parts.append(str(c.args[0]) if c.args else "")
    for c in out.append.call_args_list:
        parts.append(str(c.args[0]) if c.args else "")
    return "\n".join(parts)


class TestFetchInfo:
    def test_writes_info(self):
        h, st, ctx = _make()
        ctx.sb.send_command.return_value = "info data"
        h.fetch_info()
        assert "info data" in _output_texts(st.out)
        assert ctx.sb.send_command.call_count == 6
        assert ctx.event_bus.put.call_count == 1

    def test_includes_interfaces_when_present(self):
        drv_mock = MagicMock()
        intf = MagicMock()
        intf.name = "GE0/0/1"
        intf.status = "up"
        intf.protocol_status = "up"
        drv_mock.get_interfaces.return_value = [intf]
        h, st, ctx = _make(drv=drv_mock)
        ctx.sb.send_command.return_value = "info"
        h.fetch_info()
        texts = _output_texts(st.out)
        assert "GE0/0/1" in texts
        assert "Interfaces" in texts

    def test_shows_no_interfaces_message(self):
        drv_mock = MagicMock()
        drv_mock.get_interfaces.return_value = []
        h, st, ctx = _make(drv=drv_mock)
        ctx.sb.send_command.return_value = "info"
        h.fetch_info()
        assert "nenhuma interface" in _output_texts(st.out)

    def test_runtime_error_invalidates(self):
        h, st, ctx = _make()
        ctx.sb.send_command.side_effect = SdnError("fail")
        h.fetch_info()
        ctx.sb.invalidate_connection.assert_called_once()
        assert "Falha SSH" in _output_texts(st.out)
