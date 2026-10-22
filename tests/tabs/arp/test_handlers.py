"""Testes da aba Tabela ARP — ArpHandlers (tabs/arp/handlers.py).

Migrados de tests/test_fetch_mixin.py (F2-arp do plano
plano-abas-independentes). _fetch_info permanece legado.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from huawei_manager.exceptions import SdnError
from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.arp.handlers import ArpHandlers
from huawei_manager.tabs.arp.state import ArpState


def _make(**overrides) -> tuple[ArpHandlers, ArpState, TabContext]:
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
    state = ArpState()
    state.out = MagicMock()
    return ArpHandlers(ctx, state), state, ctx


def _output_texts(out) -> str:
    """Concatena tudo que foi 'escrito' no out (setPlainText + append)."""
    parts = []
    for c in out.setPlainText.call_args_list:
        parts.append(str(c.args[0]) if c.args else "")
    for c in out.append.call_args_list:
        parts.append(str(c.args[0]) if c.args else "")
    return "\n".join(parts)


class TestFetchArp:
    def test_writes_arp_table(self):
        drv_mock = MagicMock()
        entry = MagicMock()
        entry.ip_address = "10.0.0.1"
        entry.mac_address = "aa:bb:cc:dd:ee:ff"
        entry.status = "static"
        entry.interface = "GE0/0/1"
        drv_mock.get_arp_table.return_value = [entry]
        h, st, ctx = _make(drv=drv_mock)
        h.fetch_arp()
        drv_mock.get_arp_table.assert_called_once()
        texts = _output_texts(st.out)
        assert "10.0.0.1" in texts
        assert "aa:bb:cc:dd:ee:ff" in texts
        assert ctx.event_bus.put.call_count == 1

    def test_runtime_error_invalidates(self):
        drv_mock = MagicMock()
        drv_mock.get_arp_table.side_effect = SdnError("fail")
        h, st, ctx = _make(drv=drv_mock)
        h.fetch_arp()
        ctx.sb.invalidate_connection.assert_called_once()
        assert "Falha SSH" in _output_texts(st.out)
