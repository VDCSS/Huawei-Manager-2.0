"""Testes de caracterização — DashboardMixin (handlers/dashboard.py).

Testa _refresh_dashboard com mocks de widgets e audit.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from ._factories import make_device as _make_device_factory
from huawei_manager.handlers.dashboard import DashboardMixin


def _make_mixin(**attrs) -> DashboardMixin:
    mixin = DashboardMixin()
    defaults = dict(
        _sb=MagicMock(),
        session=MagicMock(),
        _devices=[],
        _dash_conn_status=MagicMock(),
        _dash_conn_host=MagicMock(),
        _dash_device_online=MagicMock(),
        _dash_device_offline=MagicMock(),
        _dash_device_unknown=MagicMock(),
        _dash_audit_text=MagicMock(),
    )
    for k, v in defaults.items():
        setattr(mixin, k, v)
    for k, v in attrs.items():
        setattr(mixin, k, v)
    return mixin


def _make_device(status: str = "online"):
    return _make_device_factory(status=status)


class TestRefreshDashboard:
    def test_online_when_alive(self):
        mixin = _make_mixin()
        mixin._sb.is_alive.return_value = True
        mixin._refresh_dashboard()
        mixin._dash_conn_status.setText.assert_called_with("Online")

    def test_offline_when_dead(self):
        mixin = _make_mixin()
        mixin._sb.is_alive.return_value = False
        mixin._refresh_dashboard()
        mixin._dash_conn_status.setText.assert_called_with("Desconectado")

    def test_alive_exception_sets_offline(self):
        mixin = _make_mixin()
        mixin._sb.is_alive.side_effect = Exception("fail")
        mixin._refresh_dashboard()
        mixin._dash_conn_status.setText.assert_called_with("Desconectado")

    def test_counts_online_devices(self):
        devices = [_make_device("online"), _make_device("online"), _make_device("offline")]
        mixin = _make_mixin(_devices=devices)
        mixin._sb.is_alive.return_value = False
        mixin._refresh_dashboard()
        mixin._dash_device_online.setText.assert_called_with("Online: 2")

    def test_counts_offline_devices(self):
        devices = [_make_device("offline"), _make_device("unknown")]
        mixin = _make_mixin(_devices=devices)
        mixin._sb.is_alive.return_value = False
        mixin._refresh_dashboard()
        mixin._dash_device_offline.setText.assert_called_with("Offline: 1")

    def test_counts_unknown_devices(self):
        devices = [_make_device("unknown"), _make_device("")]
        mixin = _make_mixin(_devices=devices)
        mixin._sb.is_alive.return_value = False
        mixin._refresh_dashboard()
        mixin._dash_device_unknown.setText.assert_called_with("Desconhecido: 2")

    def test_refreshes_audit_text(self):
        mixin = _make_mixin()
        mixin._sb.is_alive.return_value = False
        mixin._refresh_dashboard()
        mixin._dash_audit_text.setPlainText.assert_called_once()

    def test_empty_devices_sets_all_zero(self):
        mixin = _make_mixin(_devices=[])
        mixin._sb.is_alive.return_value = False
        mixin._refresh_dashboard()
        mixin._dash_device_online.setText.assert_called_with("Online: 0")
        mixin._dash_device_offline.setText.assert_called_with("Offline: 0")
        mixin._dash_device_unknown.setText.assert_called_with("Desconhecido: 0")

    def test_handles_audit_error(self):
        mixin = _make_mixin()
        mixin._sb.is_alive.return_value = False
        with patch("huawei_manager.handlers.dashboard.audit") as mock_audit:
            mock_audit.format_tail.side_effect = Exception("read fail")
            mixin._refresh_dashboard()
        mixin._dash_audit_text.setPlainText.assert_called_once_with(
            "  (erro ao ler auditoria)"
        )
        mixin._dash_audit_text.setReadOnly.assert_any_call(True)
