"""Event Queue — Fila de eventos priorizados thread-safe com pub/sub.

Fornece a infraestrutura de eventos assincronos para o ControllerCore.
Usa ``queue.PriorityQueue`` internamente para ordenar eventos por
prioridade (0 = crítica, 10 = normal, 20 = baixa).
Implementa ``IEventBus``.
"""
from __future__ import annotations

import itertools
import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto

from huawei_manager.sdn_controller.bus import IEventBus
from huawei_manager.sdn_controller.events import BaseEventPayload

_LOG = logging.getLogger(__name__)


class EventType(Enum):
    """Categorias de eventos do sistema SDN."""

    DEVICE_CONNECTED = auto()
    DEVICE_DISCONNECTED = auto()
    DEVICE_ERROR = auto()
    CONFIG_CHANGED = auto()
    TOPOLOGY_CHANGED = auto()
    COMMAND_EXECUTED = auto()
    VNF_STATUS_CHANGED = auto()
    ALERT = auto()
    AN_TRIGGER = auto()


@dataclass
class Event:
    """Evento atômico do sistema SDN.

    Attributes:
        type: Categoria do evento.
        source: Identificador do dispositivo ou módulo origem.
        payload: Payload opcional do evento (dataclass tipada).
        priority: Prioridade (0=crítica, 10=normal, 20=baixa).
        timestamp: Instante de criação do evento.
    """

    type: EventType
    source: str
    payload: BaseEventPayload | None = None
    priority: int = 10
    timestamp: datetime = field(default_factory=datetime.now)


# Tipo interno para itens da PriorityQueue: (prioridade, contador, evento)
_PQueueItem = tuple[int, int, Event]


class EventQueue(IEventBus):
    """Fila de eventos priorizados thread-safe com padrão pub/sub.

    Eventos com prioridade mais baixa (0 = crítica) saem primeiro.
    Mesma prioridade mantém ordem de inserção (FIFO).

    Duas formas de consumo:
    * Pull — ``get()`` / ``poll()`` para consumers que processam em loop.
    * Push — ``subscribe()`` para callbacks invocados a cada ``put()``.

    Args:
        maxsize: Capacidade máxima da fila (0 = ilimitado).
    """

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: queue.PriorityQueue[_PQueueItem] = queue.PriorityQueue(
            maxsize=maxsize
        )
        self._subscribers: dict[EventType, list[Callable[[Event], None]]] = {}
        self._lock = threading.Lock()
        self._counter = itertools.count()

    def put(
        self,
        event: Event,
        block: bool = True,
        timeout: float | None = 0.5,
    ) -> None:
        """Publica um evento priorizado na fila e notifica assinantes.

        Args:
            event: Evento a ser publicado.
            block: Se True (padrao), bloqueia se a fila estiver cheia.
            timeout: Tempo maximo de espera em segundos (padrao 0.5s).
        """
        item: _PQueueItem = (event.priority, next(self._counter), event)
        try:
            self._queue.put(item, block=block, timeout=timeout)
        except queue.Full:
            _LOG.warning("EventQueue cheia (%d), descartando %s/%s",
                         self._queue.maxsize, event.type.name, event.source)
            return
        self._notify(event)

    def get(
        self, block: bool = True, timeout: float | None = None
    ) -> Event | None:
        """Consome o próximo evento de maior prioridade.

        Args:
            block: Se True, aguarda até um evento estar disponível.
            timeout: Tempo máximo de espera em segundos (None = infinito).

        Returns:
            O próximo ``Event``, ou None se o timeout expirar.
        """
        try:
            return self._queue.get(block=block, timeout=timeout)[2]
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
                _LOG.exception("Subscriber %r falhou ao processar %s/%s",
                               cb, event.type.name, event.source)

    def poll(self, timeout: float = 0.1, max_events: int = 100) -> list[Event]:
        """Drena eventos disponiveis ate o limite (non-blocking drain).

        Args:
            timeout: Tempo de espera inicial pelo primeiro evento (s).
            max_events: Numero maximo de eventos a drenar (padrao 100).

        Returns:
            Lista de eventos pendentes (pode ser vazia), ordenados por
            prioridade.
        """
        events: list[Event] = []
        head = self.get(block=True, timeout=timeout)
        if head is None:
            return events
        events.append(head)
        while len(events) < max_events:
            ev = self.get(block=False)
            if ev is None:
                break
            events.append(ev)
        return events
