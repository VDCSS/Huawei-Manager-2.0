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
class DeviceStatusChangedPayload(BaseEventPayload):
    """Payload para ``EventType.DEVICE_STATUS_CHANGED``."""

    status: str


@dataclass
class AlertPayload(BaseEventPayload):
    """Payload para ``EventType.ALERT``."""

    message: str
    severity: str = "info"


@dataclass
class TopologyChangedPayload(BaseEventPayload):
    """Payload para ``EventType.TOPOLOGY_CHANGED``.

    Attributes:
        action: Tipo de mudanca (added, removed, link_changed, status_changed).
        device_id: ID do dispositivo afetado.
        previous_state: Estado anterior (opcional, para comparacoes).
        new_state: Novo estado do dispositivo/topologia.
    """

    action: str  # added | removed | link_changed | status_changed
    device_id: str
    previous_state: dict[str, Any] | None = None
    new_state: dict[str, Any] | None = None


@dataclass
class AnTriggerPayload(BaseEventPayload):
    """Payload para ``EventType.AN_TRIGGER``.

    Attributes:
        trigger_source: Origem do trigger (monitor, policy, scheduler).
        device_id: ID do dispositivo alvo.
        an_action: Acao AN a ser executada (heal, optimize, scale).
        context: Dados adicionais para decisao da politica AN.
    """

    trigger_source: str  # monitor | policy | scheduler
    device_id: str
    an_action: str  # heal | optimize | scale | rebalance
    context: dict[str, Any] | None = None
