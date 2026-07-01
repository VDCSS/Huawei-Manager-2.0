"""Event Queue — Fila de eventos thread-safe com pub/sub.

Fornece a infraestrutura de eventos assincronos para o ControllerCore.
Usada internamente pelo pacote ``sdn_controller/``.
"""
from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto


class EventType(Enum):
    """Categorias de eventos do sistema SDN."""

    DEVICE_CONNECTED = auto()
    DEVICE_DISCONNECTED = auto()
    DEVICE_ERROR = auto()
    CONFIG_CHANGED = auto()
    TOPOLOGY_CHANGED = auto()
    COMMAND_EXECUTED = auto()
    VNF_STATUS_CHANGED = auto()


@dataclass
class Event:
    """Evento atômico do sistema SDN.

    Attributes:
        type: Categoria do evento.
        source: Identificador do dispositivo ou módulo origem.
        data: Payload opcional do evento (dict).
        timestamp: Instante de criação do evento.
    """

    type: EventType
    source: str
    data: dict | None = None
    timestamp: datetime = field(default_factory=datetime.now)


class EventQueue:
    """Fila de eventos thread-safe com padrão pub/sub.

    Duas formas de consumo:
    * Pull — ``get()`` / ``poll()`` para consumers que processam em loop.
    * Push — ``subscribe()`` para callbacks invocados a cada ``put()``.

    Args:
        maxsize: Capacidade máxima da fila (0 = ilimitado).
    """

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: queue.Queue[Event] = queue.Queue(maxsize=maxsize)
        self._subscribers: dict[EventType, list[Callable[[Event], None]]] = {}
        self._lock = threading.Lock()

    def put(
        self,
        event: Event,
        block: bool = True,
        timeout: float | None = None,
    ) -> None:
        """Publica um evento na fila e notifica assinantes.

        Args:
            event: Evento a ser publicado.
            block: Se True (padrao), bloqueia se a fila estiver cheia.
            timeout: Tempo maximo de espera em segundos se block=True.
        """
        self._queue.put(event, block=block, timeout=timeout)
        self._notify(event)

    def get(
        self, block: bool = True, timeout: float | None = None
    ) -> Event | None:
        """Consome o próximo evento da fila.

        Args:
            block: Se True, aguarda até um evento estar disponível.
            timeout: Tempo máximo de espera em segundos (None = infinito).

        Returns:
            O próximo ``Event``, ou None se o timeout expirar.
        """
        try:
            return self._queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    def subscribe(
        self, event_type: EventType, callback: Callable[[Event], None]
    ) -> None:
        """Registra um callback para um tipo de evento."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)

    def unsubscribe(
        self, event_type: EventType, callback: Callable[[Event], None]
    ) -> None:
        """Remove o registro de um callback."""
        with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type].remove(callback)

    def _notify(self, event: Event) -> None:
        """Notifica todos os assinantes de um evento."""
        with self._lock:
            callbacks = list(self._subscribers.get(event.type, []))
        for cb in callbacks:
            try:
                cb(event)
            except Exception:
                pass  # Assinante não quebra a fila

    def poll(self, timeout: float = 0.1) -> list[Event]:
        """Drena todos os eventos disponíveis (non-blocking drain).

        Args:
            timeout: Tempo de espera inicial pelo primeiro evento (s).

        Returns:
            Lista de eventos pendentes (pode ser vazia).
        """
        events: list[Event] = []
        head = self.get(block=True, timeout=timeout)
        if head is None:
            return events
        events.append(head)
        while True:
            ev = self.get(block=False)
            if ev is None:
                break
            events.append(ev)
        return events
