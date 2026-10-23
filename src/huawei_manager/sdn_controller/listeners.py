"""Event Sources — fontes event-driven de eventos para o ``EventQueue``.

Fecha o Gap 2 do mapeamento de padrões: além do polling, o sistema passa
a ter origem *push* (traps SNMP e mensagens syslog). Cada listener é uma
thread daemon independente que publica ``Event(EventType.ALERT)`` no
barramento. Falha de um listener — inclusive bind negado — é isolada:
vira warning e o app continua operando com as demais fontes.

Opt-in por ambiente (desligado por padrão, superfície de rede nula):

* ``HW_SNMP_TRAP_LISTENER=1`` — escuta traps SNMP v1/v2c em
  ``HW_SNMP_TRAP_PORT`` (padrão 162);
* ``HW_SYSLOG_LISTENER=1`` — escuta syslog RFC 3164 em
  ``HW_SYSLOG_PORT`` (padrão 514).

Portas < 1024 exigem privilégio; sem ele o listener apenas registra o
aviso e o app segue funcionando.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from huawei_manager.sdn_controller.bus import IEventBus
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import AlertPayload

log = logging.getLogger(__name__)

SNMP_TRAP_ENV = "HW_SNMP_TRAP_LISTENER"
SNMP_TRAP_PORT_ENV = "HW_SNMP_TRAP_PORT"
SYSLOG_ENV = "HW_SYSLOG_LISTENER"
SYSLOG_PORT_ENV = "HW_SYSLOG_PORT"
DEFAULT_SNMP_TRAP_PORT = 162
DEFAULT_SYSLOG_PORT = 514

_MAX_DATAGRAM = 65_535
_RECV_TIMEOUT_S = 0.5
_JOIN_TIMEOUT_S = 2.0
_MAX_MESSAGE_CHARS = 500

# Severidade syslog (RFC 3164): PRI % 8.
_SYSLOG_SEVERITY: dict[int, str] = {
    0: "critical",
    1: "critical",
    2: "critical",
    3: "error",
    4: "warning",
    5: "info",
    6: "info",
    7: "info",
}


class EventSource(Protocol):
    """Contrato de uma fonte push de eventos."""

    @property
    def name(self) -> str: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def is_running(self) -> bool: ...


class _UdpListener(ABC):
    """Base: socket UDP + thread daemon + shutdown limpo e idempotente."""

    kind = "udp"

    def __init__(self, bus: IEventBus, host: str = "0.0.0.0",
                 port: int = 0) -> None:
        self._bus = bus
        self._host = host
        self._port = port
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def name(self) -> str:
        return f"{self.kind}:{self._host}:{self.port}"

    @property
    def port(self) -> int:
        """Porta efetiva (``port=0`` pede porta efêmera ao SO)."""
        sock = self._sock
        if sock is not None:
            try:
                return int(sock.getsockname()[1])
            except OSError:  # pragma: no cover — socket já fechado
                return self._port
        return self._port

    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def start(self) -> None:
        """Abre o socket e inicia a thread daemon.

        Raises:
            OSError: bind indisponível (porta ocupada ou sem privilégio).
        """
        if self.is_running():
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((self._host, self._port))
        except OSError:
            sock.close()
            raise
        sock.settimeout(_RECV_TIMEOUT_S)
        self._sock = sock
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name=f"listener-{self.kind}",
            daemon=True,
        )
        self._thread.start()
        log.info("listener %s ativo", self.name)

    def stop(self) -> None:
        """Sinaliza parada, fecha o socket e aguarda a thread."""
        self._stop.set()
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:  # pragma: no cover — fechamento idempotente
                pass
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=_JOIN_TIMEOUT_S)

    def _loop(self) -> None:
        while not self._stop.is_set():
            sock = self._sock
            if sock is None:
                return
            try:
                data, addr = sock.recvfrom(_MAX_DATAGRAM)
            except TimeoutError:
                continue
            except OSError:
                # socket fechado por stop() — encerra sem ruído
                return
            try:
                self._handle(data, str(addr[0]))
            except Exception:
                # justificativa: um datagrama malformado nunca pode
                # derrubar o listener nem o app (isolamento de falhas).
                log.exception("listener %s falhou em um datagrama", self.kind)

    @abstractmethod
    def _handle(self, data: bytes, host: str) -> None:
        """Traduz um datagrama em evento publicado no barramento."""

    def _publish(self, payload: AlertPayload) -> None:
        self._bus.put(Event(
            type=EventType.ALERT,
            source=payload.host,
            payload=payload,
        ))


class SyslogListener(_UdpListener):
    """Escuta mensagens syslog (RFC 3164) e publica ``ALERT``."""

    kind = "syslog"

    def _handle(self, data: bytes, host: str) -> None:
        text = data.decode("utf-8", errors="replace").strip()
        if not text:
            return
        priority, rest = _split_priority(text)
        severity = "info"
        if priority is not None:
            severity = _SYSLOG_SEVERITY.get(priority % 8, "info")
        self._publish(AlertPayload(
            kind="syslog",
            severity=severity,
            message=rest[:_MAX_MESSAGE_CHARS],
            host=host,
            raw_size=len(data),
        ))


class SnmpTrapListener(_UdpListener):
    """Escuta traps SNMP v1/v2c e publica ``ALERT`` com o trap OID.

    Decodificador BER mínimo (sem dependência externa): identifica a
    versão/PDU e, em v2c, o ``snmpTrapOID`` do primeiro varbind. A
    community string é apenas percorrida no offset — nunca é logada nem
    publicada no evento.
    """

    kind = "snmp-trap"

    def _handle(self, data: bytes, host: str) -> None:
        info = _decode_trap(data)
        if info is None:
            log.debug("trap SNMP ilegível de %s (%d bytes)", host, len(data))
            return
        message = f"trap SNMP {info.version}"
        if info.oid:
            message += f" {info.oid}"
        self._publish(AlertPayload(
            kind="snmp-trap",
            severity="warning",
            message=message,
            host=host,
            oid=info.oid or info.enterprise,
            raw_size=len(data),
        ))


@dataclass(frozen=True)
class _TrapInfo:
    version: str
    oid: str | None
    enterprise: str | None


def _split_priority(text: str) -> tuple[int | None, str]:
    """Separa ``<PRI>`` do restante da mensagem syslog."""
    if not text.startswith("<"):
        return None, text
    end = text.find(">")
    if end <= 1:
        return None, text
    try:
        return int(text[1:end]), text[end + 1:].strip()
    except ValueError:
        return None, text


def _read_tlv(data: bytes, offset: int) -> tuple[int, bytes, int]:
    """Lê um TLV BER: ``(tag, valor, próximo offset)``.

    Raises:
        ValueError: TLV truncado ou comprimento inválido.
    """
    if offset + 2 > len(data):
        raise ValueError("TLV truncado")
    tag = data[offset]
    first = data[offset + 1]
    pos = offset + 2
    if first & 0x80:
        count = first & 0x7F
        if count == 0 or count > 4 or pos + count > len(data):
            raise ValueError("comprimento BER inválido")
        length = int.from_bytes(data[pos:pos + count], "big")
        pos += count
    else:
        length = first
    end = pos + length
    if end > len(data):
        raise ValueError("TLV truncado")
    return tag, data[pos:end], end


def _decode_oid(raw: bytes) -> str:
    """Decodifica um OBJECT IDENTIFIER BER para ``1.3.6.1...``."""
    if not raw:
        return ""
    first = raw[0]
    parts = [str(first // 40), str(first % 40)]
    value = 0
    for byte in raw[1:]:
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            parts.append(str(value))
            value = 0
    return ".".join(parts)


def _decode_trap(data: bytes) -> _TrapInfo | None:
    """Extrai versão, trap OID e enterprise de um trap SNMP v1/v2c."""
    try:
        tag, body, _ = _read_tlv(data, 0)
        if tag != 0x30:  # SEQUENCE
            return None
        _tag, version_raw, pos = _read_tlv(body, 0)
        version = int.from_bytes(version_raw, "big") if version_raw else 0
        # A community string (posição seguinte) é um segredo: só é
        # percorrida para avançar o offset e é descartada.
        _tag, _community, pos = _read_tlv(body, pos)
        pdu_tag, pdu_body, _ = _read_tlv(body, pos)
        if pdu_tag == 0xA7:  # SNMPv2c trap
            return _decode_v2_trap(pdu_body)
        if pdu_tag == 0xA4:  # SNMPv1 trap
            return _decode_v1_trap(pdu_body)
        return _TrapInfo(version=f"v{version + 1}", oid=None, enterprise=None)
    except (ValueError, IndexError):
        return None


def _decode_v2_trap(body: bytes) -> _TrapInfo:
    _tag, _request_id, pos = _read_tlv(body, 0)
    _tag, _error_status, pos = _read_tlv(body, pos)
    _tag, _error_index, pos = _read_tlv(body, pos)
    _tag, varbinds, _ = _read_tlv(body, pos)
    oid: str | None = None
    if varbinds:
        _tag, first_varbind, _ = _read_tlv(varbinds, 0)
        if first_varbind:
            _tag, oid_raw, _ = _read_tlv(first_varbind, 0)
            oid = _decode_oid(oid_raw) or None
    return _TrapInfo(version="v2c", oid=oid, enterprise=None)


def _decode_v1_trap(body: bytes) -> _TrapInfo:
    _tag, enterprise_raw, pos = _read_tlv(body, 0)
    _tag, _agent_addr, pos = _read_tlv(body, pos)
    _tag, _generic_trap, pos = _read_tlv(body, pos)
    _tag, _specific_trap, pos = _read_tlv(body, pos)
    _tag, _time_stamp, _ = _read_tlv(body, pos)
    return _TrapInfo(
        version="v1",
        oid=None,
        enterprise=_decode_oid(enterprise_raw) or None,
    )


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _port(value: str | None, default: int) -> int:
    if not value:
        return default
    try:
        port = int(value)
    except ValueError:
        return default
    return port if 0 <= port <= _MAX_DATAGRAM - 1 else default


def start_alert_listeners(
    bus: IEventBus,
    env: Mapping[str, str] | None = None,
    host: str = "0.0.0.0",
) -> list[EventSource]:
    """Liga as fontes push habilitadas por ambiente.

    Cada listener é iniciado em ``try/except`` próprio: bind negado
    (porta ocupada ou sem privilégio) vira warning e o app segue sem
    aquela fonte — isolamento de falhas.

    Returns:
        Listeners efetivamente iniciados (para ``stop_alert_listeners``).
    """
    source = os.environ if env is None else env
    candidates: list[EventSource] = []
    if _enabled(source.get(SNMP_TRAP_ENV)):
        candidates.append(SnmpTrapListener(
            bus,
            host=host,
            port=_port(source.get(SNMP_TRAP_PORT_ENV),
                       DEFAULT_SNMP_TRAP_PORT),
        ))
    if _enabled(source.get(SYSLOG_ENV)):
        candidates.append(SyslogListener(
            bus,
            host=host,
            port=_port(source.get(SYSLOG_PORT_ENV), DEFAULT_SYSLOG_PORT),
        ))
    started: list[EventSource] = []
    for listener in candidates:
        try:
            listener.start()
        except OSError as exc:
            log.warning("listener %s indisponível: %s", listener.name, exc)
            continue
        started.append(listener)
    return started


def stop_alert_listeners(listeners: Sequence[EventSource]) -> None:
    """Encerra as fontes push; falha de uma não impede as demais."""
    for listener in listeners:
        try:
            listener.stop()
        except Exception:
            # justificativa: shutdown nunca pode travar o fechamento do app.
            log.exception("falha ao parar listener %s", listener.name)
