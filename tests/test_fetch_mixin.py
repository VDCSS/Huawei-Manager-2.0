"""Testes de caracterização — FetchMixin (handlers/fetch.py).

Testa caminhos de _fetch_config, _fetch_route, _fetch_arp, _fetch_info.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from huawei_manager.handlers.fetch import FetchMixin


def _make_mixin(**attrs) -> FetchMixin:
    mixin = FetchMixin()
    defaults = dict(
        _session_tracker=MagicMock(),
        _sb=MagicMock(),
        _drv=MagicMock(),
        _write=MagicMock(),
        _loading=MagicMock(),
        _event_queue=MagicMock(),
        out_config=MagicMock(),
        out_route=MagicMock(),
        out_arp=MagicMock(),
        out_info=MagicMock(),
    )
    for k, v in defaults.items():
        setattr(mixin, k, v)
    for k, v in attrs.items():
        setattr(mixin, k, v)
    return mixin


class TestFetchConfig:
    def test_writes_output(self):
        mixin = _make_mixin()
        mixin._sb.send_command.return_value = "interface GigabitEthernet0/0/1"
        mixin._fetch_config()
        mixin._write.assert_called_once_with(mixin.out_config, "interface GigabitEthernet0/0/1")

    def test_posts_event(self):
        mixin = _make_mixin()
        mixin._sb.send_command.return_value = "config"
        mixin._fetch_config()
        mixin._event_queue.put.assert_called_once()

    def test_invalidates_on_error(self):
        mixin = _make_mixin()
        mixin._sb.send_command.side_effect = RuntimeError("fail")
        mixin._fetch_config()
        mixin._sb.invalidate_connection.assert_called_once()


class TestFetchRoute:
    def test_routing_uses_driver(self):
        mixin = _make_mixin()
        entry = MagicMock()
        entry.destination = "0.0.0.0"
        entry.mask = "0"
        entry.protocol = "static"
        entry.preference = 60
        entry.cost = 0
        entry.next_hop = "10.0.0.1"
        entry.interface = "GE0/0/1"
        mixin._drv.get_routing_table.return_value = [entry]
        mixin._fetch_route(fkey="routing")
        mixin._drv.get_routing_table.assert_called_once()
        mixin._write.assert_called_once()

    def test_other_filter_uses_send_command(self):
        mixin = _make_mixin()
        mixin._sb.send_command.return_value = "route data"
        mixin._fetch_route(fkey="bgp")
        mixin._sb.send_command.assert_called_once()
        mixin._write.assert_called_once()

    def test_routing_runtime_error_invalidates(self):
        mixin = _make_mixin()
        mixin._drv.get_routing_table.side_effect = RuntimeError("fail")
        mixin._fetch_route(fkey="routing")
        mixin._sb.invalidate_connection.assert_called_once()


class TestFetchArp:
    def test_writes_arp_table(self):
        mixin = _make_mixin()
        entry = MagicMock()
        entry.ip_address = "10.0.0.1"
        entry.mac_address = "aa:bb:cc:dd:ee:ff"
        entry.status = "static"
        entry.interface = "GE0/0/1"
        mixin._drv.get_arp_table.return_value = [entry]
        mixin._fetch_arp()
        mixin._write.assert_called_once()
        written = mixin._write.call_args[0][1]
        assert "10.0.0.1" in written

    def test_runtime_error_invalidates(self):
        mixin = _make_mixin()
        mixin._drv.get_arp_table.side_effect = RuntimeError("fail")
        mixin._fetch_arp()
        mixin._sb.invalidate_connection.assert_called_once()


class TestFetchInfo:
    def test_writes_info(self):
        mixin = _make_mixin()
        mixin._sb.send_command.return_value = "info data"
        mixin._drv.get_interfaces.return_value = []
        mixin._fetch_info()
        mixin._write.assert_called_once()

    def test_includes_interfaces_when_present(self):
        mixin = _make_mixin()
        mixin._sb.send_command.return_value = "info"
        intf = MagicMock()
        intf.name = "GE0/0/1"
        intf.status = "up"
        intf.protocol_status = "up"
        mixin._drv.get_interfaces.return_value = [intf]
        mixin._fetch_info()
        written = mixin._write.call_args[0][1]
        assert "GE0/0/1" in written

    def test_shows_no_interfaces_message(self):
        mixin = _make_mixin()
        mixin._sb.send_command.return_value = "info"
        mixin._drv.get_interfaces.return_value = []
        mixin._fetch_info()
        written = mixin._write.call_args[0][1]
        assert "nenhuma interface" in written

    def test_runtime_error_invalidates(self):
        mixin = _make_mixin()
        mixin._sb.send_command.side_effect = RuntimeError("fail")
        mixin._fetch_info()
        mixin._sb.invalidate_connection.assert_called_once()
