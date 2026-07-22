"""Bus Protocol — barramento de eventos abstrato para o SDN Controller.

Define o contrato ``IEventBus`` que o ``EventQueue`` implementa.
Permite trocar a implementação da fila sem alterar consumidores.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from huawei_manager.sdn_controller.event_queue import Event, EventType


@runtime_checkable
class IEventBus(Protocol):
    """Protocolo do barramento de eventos SDN.

    Contrato mínimo para put/subscribe/unsubscribe/poll.
    Qualquer implementação deve ser thread-safe.
    """

    def put(
        self,
        event: Event,
        block: bool = True,
        timeout: float | None = 0.5,
    ) -> None: ...

    def get(
        self, block: bool = True, timeout: float | None = None
    ) -> Event | None: ...

    def poll(
        self, timeout: float = 0.1, max_events: int = 100
    ) -> list[Event]: ...

    def subscribe(
        self, event_type: EventType, callback: Callable[[Event], None]
    ) -> None: ...

    def unsubscribe(
        self, event_type: EventType, callback: Callable[[Event], None]
    ) -> None: ...


@runtime_checkable
class IEventConsumer(Protocol):
    """Algo que consome eventos do barramento."""

    def on_event(self, event: Event) -> None: ...
