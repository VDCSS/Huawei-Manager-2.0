"""Controller Core — Estado centralizado dos dispositivos SDN.

Fornece o ``ControllerCore`` (gerencia estado em RAM com dump periodico
para JSON) e o dataclass ``DeviceState``.

Headless — sem dependencia Qt. Thread-safe via ``threading.Lock``.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from huawei_manager.sdn_controller.bus import IEventBus
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import (
    DeviceConnectedPayload,
    DeviceErrorPayload,
    VnfStatusChangedPayload,
)

log = logging.getLogger("huawei.sdn.core")

# Mapeamento de EventType → status do device
_EVENT_TO_STATUS: dict[EventType, str] = {
    EventType.DEVICE_CONNECTED: "online",
    EventType.DEVICE_DISCONNECTED: "offline",
    EventType.DEVICE_ERROR: "error",
}


@dataclass
class DeviceState:
    """Estado runtime de um dispositivo gerenciado.

    Attributes:
        device_id: Identificador unico do dispositivo.
        host: Endereco IP ou hostname.
        port: Porta SSH/CLI.
        device_type: Familia do dispositivo (router, switch, firewall, ...).
        status: Status operacional (unknown, online, offline, error, ...).
        last_seen: Timestamp da ultima atividade conhecida.
        metadata: Dicionario extensivel de metadados (versao, site, erro, ...).
    """

    device_id: str
    host: str
    port: int
    device_type: str
    status: str = "unknown"
    last_seen: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializa para dict (compativel com JSON)."""
        raw = asdict(self)
        if raw["last_seen"] is not None:
            raw["last_seen"] = raw["last_seen"].isoformat()
        return raw

    @staticmethod
    def from_dict(data: dict[str, Any]) -> DeviceState:
        """Desserializa de dict."""
        last_seen = None
        if data.get("last_seen"):
            last_seen = datetime.fromisoformat(data["last_seen"])
        return DeviceState(
            device_id=data["device_id"],
            host=data["host"],
            port=data["port"],
            device_type=data["device_type"],
            status=data.get("status", "unknown"),
            last_seen=last_seen,
            metadata=data.get("metadata", {}),
        )


class ControllerCore:
    """Estado centralizado dos dispositivos SDN.

    Mantem o estado de todos os dispositivos registrados em RAM,
    atualiza automaticamente conforme eventos do ``EventQueue``,
    e persiste periodicamente em JSON.

    Args:
        event_queue: Opcional — fila de eventos para publicar mudancas
            de estado. Se fornecida, o core tambem se inscreve para
            processar eventos automaticamente.
        dump_path: Caminho do arquivo JSON para persistencia.
        dump_interval: Intervalo em segundos entre dumps periodicos.
            Padrao: 60s. ``0`` desabilita dump periodico.
    """

    def __init__(
        self,
        event_queue: IEventBus | None = None,
        dump_path: str | None = None,
        dump_interval: float = 60,
    ) -> None:
        self._event_queue = event_queue
        self._dump_path = dump_path
        self._dump_interval = dump_interval
        self._lock = threading.Lock()
        self._devices: dict[str, DeviceState] = {}
        self._timer: threading.Timer | None = None
        self._running = False

        if self._event_queue is not None:
            self._event_queue.subscribe(EventType.DEVICE_CONNECTED, self._on_event)
            self._event_queue.subscribe(EventType.DEVICE_DISCONNECTED, self._on_event)
            self._event_queue.subscribe(EventType.DEVICE_ERROR, self._on_event)
            self._event_queue.subscribe(EventType.CONFIG_CHANGED, self._on_event)
            self._event_queue.subscribe(EventType.VNF_STATUS_CHANGED, self._on_event)

    # ── Gestao de dispositivos ─────────────────────────────────────────────

    def register(
        self,
        device_id: str,
        host: str,
        port: int,
        device_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> DeviceState:
        """Registra um dispositivo no controlador.

        Se o device_id ja existir, sobrescreve o estado anterior.
        Publica um evento ``DEVICE_CONNECTED`` se houver ``event_queue``.
        """
        state = DeviceState(
            device_id=device_id,
            host=host,
            port=port,
            device_type=device_type,
            metadata=metadata or {},
        )
        with self._lock:
            self._devices[device_id] = state

        if self._event_queue is not None:
            self._event_queue.put(
                Event(type=EventType.DEVICE_CONNECTED, source=device_id,
                      payload=DeviceConnectedPayload(host=host))
            )
        return state

    def get_state(self, device_id: str) -> DeviceState | None:
        """Retorna o estado de um dispositivo, ou None se nao existir."""
        with self._lock:
            return self._devices.get(device_id)

    def deregister(self, device_id: str) -> bool:
        """Remove um dispositivo do controlador.

        Returns:
            True se o dispositivo existia e foi removido, False caso contrario.
        """
        with self._lock:
            if device_id not in self._devices:
                return False
            del self._devices[device_id]

        if self._event_queue is not None:
            self._event_queue.put(
                Event(type=EventType.DEVICE_DISCONNECTED, source=device_id)
            )
        return True

    def list_devices(self) -> list[str]:
        """Retorna a lista de IDs de dispositivos registrados."""
        with self._lock:
            return list(self._devices.keys())

    def update_state(
        self,
        device_id: str,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeviceState | None:
        """Atualiza campos do estado de um dispositivo.

        Args:
            device_id: Identificador do dispositivo.
            status: Novo status (opcional).
            metadata: Metadados a serem mesclados (opcional).

        Returns:
            O ``DeviceState`` atualizado, ou None se o dispositivo nao existir.
        """
        with self._lock:
            state = self._devices.get(device_id)
            if state is None:
                return None
            if status is not None:
                state.status = status
            if metadata:
                state.metadata.update(metadata)
        return state

    # ── Eventos ────────────────────────────────────────────────────────────

    def process_event(self, event: Event) -> None:
        """Processa um evento e atualiza o estado do device correspondente.

        Efeitos por tipo de evento:

        * ``DEVICE_CONNECTED`` — status → ``online``, ``last_seen`` → agora.
        * ``DEVICE_DISCONNECTED`` — status → ``offline``.
        * ``DEVICE_ERROR`` — status → ``error``, metadata guarda o erro.
        * ``CONFIG_CHANGED`` — metadata registra ``last_config_change``.
        * ``VNF_STATUS_CHANGED`` — status extraido de ``event.payload.status``.

        Eventos para dispositivos nao registrados sao ignorados.
        """
        state = self.get_state(event.source)
        if state is None:
            return

        now = datetime.now()

        if event.type in _EVENT_TO_STATUS:
            with self._lock:
                state.status = _EVENT_TO_STATUS[event.type]
                state.last_seen = now
            if event.type == EventType.DEVICE_ERROR:
                error_msg = "unknown"
                if isinstance(event.payload, DeviceErrorPayload) and event.payload.error:
                    error_msg = event.payload.error
                with self._lock:
                    state.metadata["last_error"] = error_msg

        elif event.type == EventType.VNF_STATUS_CHANGED:
            new_status: str | None = None
            if isinstance(event.payload, VnfStatusChangedPayload):
                new_status = event.payload.status
            if new_status:
                with self._lock:
                    state.status = new_status

        elif event.type == EventType.CONFIG_CHANGED:
            with self._lock:
                state.metadata["last_config_change"] = now.isoformat()

    def _on_event(self, event: Event) -> None:
        """Callback interno para eventos do EventQueue."""
        self.process_event(event)
        # WAL simplificado: dump imediato em eventos criticos
        # (evita perda de estado em crash entre dumps periodicos)
        if event.type in (
            EventType.DEVICE_CONNECTED,
            EventType.DEVICE_DISCONNECTED,
            EventType.DEVICE_ERROR,
        ):
            try:
                self.dump()
            except Exception:
                log.debug("immediate dump after %s failed", event.type.name)

    # ── Persistencia ───────────────────────────────────────────────────────

    def dump(self, path: str | None = None) -> None:
        """Serializa o estado de todos os dispositivos para JSON.

        Args:
            path: Caminho do arquivo. Se omitido, usa ``dump_path`` da
                configuracao. Se nenhum estiver configurado, e um no-op.
        """
        target = path or self._dump_path
        if target is None:
            log.debug("dump_path not configured — skipping dump")
            return

        with self._lock:
            serialized = {dev_id: state.to_dict() for dev_id, state in self._devices.items()}

        Path(target).write_text(json.dumps(serialized, indent=2, ensure_ascii=False))
        log.debug("dumped %d devices to %s", len(serialized), target)

    def load(self, path: str) -> int:
        """Carrega o estado de dispositivos de um arquivo JSON.

        Args:
            path: Caminho do arquivo JSON.

        Returns:
            Numero de dispositivos carregados (0 se o arquivo nao existir).
        """
        filepath = Path(path)
        if not filepath.exists():
            log.warning("state file not found: %s", path)
            return 0

        raw = json.loads(filepath.read_text())
        count = 0
        for dev_id, data in raw.items():
            state = DeviceState.from_dict(data)
            with self._lock:
                self._devices[dev_id] = state
            count += 1

        log.info("loaded %d devices from %s", count, path)
        return count

    # ── Timer periodico ────────────────────────────────────────────────────

    def sync_from_vnfs(
        self,
        vnfs: list[Any],
        publish_events: bool = True,
    ) -> None:
        """Sincroniza o estado do ControllerCore com o inventario do vnf_models.

        Registra VNFs do inventario que ainda nao estao no controlador.
        Nao remove dispositivos que existem no core mas nao no inventario
        (eles podem estar offline temporariamente).

        Args:
            vnfs: Lista de objetos VNF do vnf_models (com .id, .host, .port, .type).
            publish_events: Se False, evita publicar eventos durante o sync
                para nao gerar feedback loop no drain queue.
        """
        for vnf in vnfs:
            if vnf.id not in self._devices:
                state = DeviceState(
                    device_id=vnf.id,
                    host=vnf.host,
                    port=vnf.port,
                    device_type=vnf.type or "unknown",
                    status="unknown",
                )
                with self._lock:
                    self._devices[vnf.id] = state
                if publish_events and self._event_queue is not None:
                    self._event_queue.put(
                        Event(type=EventType.VNF_STATUS_CHANGED, source=vnf.id,
                              payload=VnfStatusChangedPayload(status="unknown"))
                    )

    def start(self) -> None:
        """Inicia o timer de dump periodico.

        Dispara um dump a cada ``dump_interval`` segundos.
        Nao faz nada se ``dump_interval <= 0`` ou ``dump_path`` nao configurado.
        """
        if self._dump_interval <= 0 or self._dump_path is None:
            return
        self._running = True
        self._schedule_dump()

    def stop(self) -> None:
        """Para o timer de dump periodico."""
        self._running = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _schedule_dump(self) -> None:
        """Agenda o proximo dump periodico."""
        if not self._running:
            return
        self._timer = threading.Timer(self._dump_interval, self._periodic_dump)
        self._timer.daemon = True
        self._timer.start()

    def _periodic_dump(self) -> None:
        """Callback do timer: executa dump e reagenda."""
        try:
            self.dump()
        except Exception:
            log.exception("periodic dump failed")
        self._schedule_dump()
