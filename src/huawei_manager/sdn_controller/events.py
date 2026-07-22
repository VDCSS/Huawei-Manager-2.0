"""Event Payloads — Dataclasses tipadas para payloads de eventos SDN.

Cada subclasse de ``BaseEventPayload`` carrega os dados específicos
de um tipo de evento, substituindo gradualmente o campo ``data``
genérico (``dict | None``) do evento.

Uso:
    >>> from huawei_manager.sdn_controller.events import DeviceConnectedPayload
    >>> payload = DeviceConnectedPayload(host="10.0.0.1", session_id="abc")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class BaseEventPayload:
    """Classe base para payloads de evento.

    Serve como marcador de tipo — todos os payloads de evento
    devem herdar desta classe.
    """


@dataclass
class DeviceConnectedPayload(BaseEventPayload):
    """Payload para ``EventType.DEVICE_CONNECTED``."""

    host: str
    session_id: str | None = None


@dataclass
class DeviceDisconnectedPayload(BaseEventPayload):
    """Payload para ``EventType.DEVICE_DISCONNECTED``."""

    reason: str = "unknown"


@dataclass
class DeviceErrorPayload(BaseEventPayload):
    """Payload para ``EventType.DEVICE_ERROR``."""

    error: str


@dataclass
class ConfigChangedPayload(BaseEventPayload):
    """Payload para ``EventType.CONFIG_CHANGED``."""

    commands: list[str] | None = None
    status: str = "unknown"
    data: dict[str, Any] | None = None  # dados adicionais legado


@dataclass
class CommandExecutedPayload(BaseEventPayload):
    """Payload para ``EventType.COMMAND_EXECUTED``.

    ``command`` é opcional para acomodar consumidores que publicam
    apenas ``status`` sem o comando (ex: ``commands.py`` linha ~120).
    """

    command: str | None = None
    status: str = "ok"
    output: str | None = None
    data: dict[str, Any] | None = None  # dados adicionais legado


@dataclass
class VnfStatusChangedPayload(BaseEventPayload):
    """Payload para ``EventType.VNF_STATUS_CHANGED``."""

    status: str


@dataclass
class AlertPayload(BaseEventPayload):
    """Payload para ``EventType.ALERT``."""

    message: str
    severity: str = "info"


# ── Eventos sem payload específico (usar BaseEventPayload) ─────
# TOPOLOGY_CHANGED — sem payload no momento
# AN_TRIGGER — sem payload no momento
#
# Estes tipos podem receber payloads específicos no futuro.
