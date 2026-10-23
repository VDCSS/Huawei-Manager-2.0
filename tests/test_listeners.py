"""Testes das fontes event-driven (Gap 2 — traps SNMP e syslog).

Cobrem publicação em ``EventType.ALERT``, shutdown limpo, isolamento de
datagramas malformados e o opt-in por ambiente.
"""
from __future__ import annotations

import socket
import time
from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

from huawei_manager.sdn_controller.event_queue import EventType
from huawei_manager.sdn_controller.listeners import (
    DEFAULT_SYSLOG_PORT,
    SNMP_TRAP_ENV,
    SNMP_TRAP_PORT_ENV,
    SYSLOG_ENV,
    SYSLOG_PORT_ENV,
    SnmpTrapListener,
    SyslogListener,
    _port,
    start_alert_listeners,
    stop_alert_listeners,
)


def _wait_for(predicate: Callable[[], bool], timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _send(listener: SyslogListener | SnmpTrapListener, payload: bytes) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tx:
        tx.sendto(payload, ("127.0.0.1", listener.port))


class TestSyslogListener:
    def test_publishes_alert_with_severity(self) -> None:
        bus = MagicMock()
        listener = SyslogListener(bus, port=0)
        listener.start()
        try:
            assert listener.is_running()
            _send(listener, b"<11>Oct 20 12:00:00 R1 %%01IFNET/4/LINK: link down")
            assert _wait_for(lambda: bus.put.call_count > 0)
        finally:
            listener.stop()
        assert not listener.is_running()

        event = bus.put.call_args[0][0]
        assert event.type is EventType.ALERT
        assert event.payload.kind == "syslog"
        assert event.payload.severity == "error"  # PRI 11 % 8 == 3
        assert "link down" in event.payload.message
        assert event.payload.host == "127.0.0.1"
        assert event.payload.raw_size > 0

    def test_message_without_priority_is_still_published(self) -> None:
        bus = MagicMock()
        listener = SyslogListener(bus, port=0)
        listener.start()
        try:
            _send(listener, b"mensagem solta sem PRI")
            assert _wait_for(lambda: bus.put.call_count > 0)
        finally:
            listener.stop()
        payload = bus.put.call_args[0][0].payload
        assert payload.severity == "info"
        assert payload.message == "mensagem solta sem PRI"

    def test_stop_is_idempotent(self) -> None:
        listener = SyslogListener(MagicMock(), port=0)
        listener.start()
        listener.stop()
        listener.stop()
        assert not listener.is_running()


def _tlv(tag: int, payload: bytes) -> bytes:
    return bytes([tag, len(payload)]) + payload


def _snmp_v2c_trap(community: str = "public") -> bytes:
    trap_oid = _tlv(0x06, bytes([43, 6, 1, 6, 3, 1, 1, 5, 3]))
    varbind = _tlv(0x30, trap_oid + _tlv(0x05, b""))
    varbinds = _tlv(0x30, varbind)
    pdu = _tlv(
        0xA7,
        _tlv(0x02, b"\x01") + _tlv(0x02, b"\x00")
        + _tlv(0x02, b"\x00") + varbinds,
    )
    body = _tlv(0x02, b"\x01") + _tlv(0x04, community.encode()) + pdu
    return _tlv(0x30, body)


class TestSnmpTrapListener:
    def test_publishes_alert_with_trap_oid(self) -> None:
        bus = MagicMock()
        listener = SnmpTrapListener(bus, port=0)
        listener.start()
        try:
            _send(listener, _snmp_v2c_trap())
            assert _wait_for(lambda: bus.put.call_count > 0)
        finally:
            listener.stop()

        payload = bus.put.call_args[0][0].payload
        assert payload.kind == "snmp-trap"
        assert payload.oid == "1.3.6.1.6.3.1.1.5.3"
        assert payload.severity == "warning"

    def test_community_string_never_leaks(self) -> None:
        bus = MagicMock()
        listener = SnmpTrapListener(bus, port=0)
        listener.start()
        try:
            _send(listener, _snmp_v2c_trap(community="segredo-da-community"))
            assert _wait_for(lambda: bus.put.call_count > 0)
        finally:
            listener.stop()

        event = bus.put.call_args[0][0]
        assert "segredo-da-community" not in event.payload.message
        assert "segredo-da-community" not in repr(event.payload)

    def test_malformed_datagram_is_isolated(self) -> None:
        bus = MagicMock()
        listener = SnmpTrapListener(bus, port=0)
        listener.start()
        try:
            _send(listener, b"\xff\x00\x01")
            assert not _wait_for(lambda: bus.put.call_count > 0, timeout=0.8)
            assert listener.is_running()  # datagrama inválido não derruba
            _send(listener, _snmp_v2c_trap())
            assert _wait_for(lambda: bus.put.call_count > 0)
        finally:
            listener.stop()


class TestStartAlertListeners:
    def test_disabled_by_default(self) -> None:
        assert start_alert_listeners(MagicMock(), env={}) == []

    @pytest.mark.parametrize("flag", ["1", "true", "YES", "on"])
    def test_syslog_opt_in(self, flag: str) -> None:
        started = start_alert_listeners(
            MagicMock(), env={SYSLOG_ENV: flag, SYSLOG_PORT_ENV: "0"})
        try:
            assert len(started) == 1
            assert started[0].is_running()
        finally:
            stop_alert_listeners(started)

    def test_snmp_opt_in(self) -> None:
        started = start_alert_listeners(
            MagicMock(), env={SNMP_TRAP_ENV: "1", SNMP_TRAP_PORT_ENV: "0"})
        try:
            assert [src.name.split(":")[0] for src in started] == ["snmp-trap"]
        finally:
            stop_alert_listeners(started)

    def test_invalid_port_falls_back_to_default(self) -> None:
        assert _port("abc", DEFAULT_SYSLOG_PORT) == DEFAULT_SYSLOG_PORT
        assert _port(None, DEFAULT_SYSLOG_PORT) == DEFAULT_SYSLOG_PORT
        assert _port("70000", DEFAULT_SYSLOG_PORT) == DEFAULT_SYSLOG_PORT
        assert _port("1514", DEFAULT_SYSLOG_PORT) == 1514

    def test_bind_failure_is_isolated(self, monkeypatch) -> None:
        monkeypatch.setattr(
            SyslogListener, "start",
            MagicMock(side_effect=OSError("permission denied")),
        )
        # Não levanta: o app segue sem a fonte que não pôde subir.
        assert start_alert_listeners(MagicMock(), env={SYSLOG_ENV: "1"}) == []

    def test_stop_continues_after_failure(self) -> None:
        broken = MagicMock()
        broken.stop.side_effect = RuntimeError("boom")
        healthy = MagicMock()
        stop_alert_listeners([broken, healthy])
        broken.stop.assert_called_once()
        healthy.stop.assert_called_once()
