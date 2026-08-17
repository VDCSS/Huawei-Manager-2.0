"""Topology Manager — LLDP discovery, graph building, change detection.

Descobre vizinhos via ``display lldp neighbor brief``, constroi grafo
em dict, detecta dispositivos novos/perdidos e emite eventos.
Fallback ARP quando LLDP nao esta disponivel.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TopologyNode:
    """Um dispositivo no grafo de topologia.

    Attributes:
        device_id: Identificador unico do dispositivo.
        name: Nome do device (ex: R1-Huawei).
        device_type: Tipo do dispositivo (router, switch, etc).
        neighbors: Lista de device_ids vizinhos.
    """

    device_id: str
    name: str
    device_type: str = "unknown"
    neighbors: list[str] = field(default_factory=list)


@dataclass
class TopologyLink:
    """Um link entre dois dispositivos.

    Attributes:
        source: Interface de origem.
        target: Interface de destino.
        source_device: Device_id da origem.
        target_device: Device_id ou nome do destino.
    """

    source: str
    target: str
    source_device: str
    target_device: str



class TopologyManager:
    """Gerenciador de topologia de rede.

    Descobre vizinhos via LLDP, mantem um grafo, detecta mudancas
    e notifica via callback de eventos.
    """

    def __init__(self) -> None:
        self._graph: dict[str, list[TopologyLink]] = {}
        self._event_callback: Callable[..., Any] | None = None

    # ── Event callback ──────────────────────────────────────────────────

    def set_event_callback(self, callback: Callable[..., Any] | None) -> None:
        """Registra callback para eventos de topologia.

        O callback recebe kwargs: device, event_type (new/lost),
        details.
        """
        self._event_callback = callback

    # ── LLDP discovery ──────────────────────────────────────────────────

    def lldp_discovery(
        self,
        device_id: str,
        execute_fn: Callable[[str], str],
    ) -> list[TopologyLink]:
        """Descobre vizinhos via ``display lldp neighbor brief``.

        Args:
            device_id: Identificador do dispositivo.
            execute_fn: Funcao que executa comando CLI e retorna output.

        Returns:
            Lista de ``TopologyLink`` descobertos.
        """
        try:
            output = execute_fn("display lldp neighbor brief")
        except RuntimeError:
            return []

        return self._parse_lldp_output(device_id, output)

    def _parse_lldp_output(
        self, device_id: str, output: str,
    ) -> list[TopologyLink]:
        """Parseia output do comando LLDP."""
        links: list[TopologyLink] = []
        lines = output.strip().splitlines()

        # Skip header line if present
        start = 0
        for i, line in enumerate(lines):
            if "Local Interface" in line and "Neighbor" in line:
                start = i + 1
                break

        for line in lines[start:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 3:
                links.append(TopologyLink(
                    source=parts[0],
                    target=parts[1],
                    source_device=device_id,
                    target_device=parts[2],
                ))

        return links

    # ── ARP fallback ────────────────────────────────────────────────────

    def arp_discovery(
        self,
        device_id: str,
        execute_fn: Callable[[str], str],
    ) -> list[TopologyNode]:
        """Descobre vizinhos via ``display arp`` como fallback.

        Args:
            device_id: Identificador do dispositivo.
            execute_fn: Funcao que executa comando CLI.

        Returns:
            Lista de ``TopologyNode`` encontrados via ARP.
        """
        try:
            output = execute_fn("display arp")
        except RuntimeError:
            return []

        return self._parse_arp_output(output)

    def _parse_arp_output(self, output: str) -> list[TopologyNode]:
        """Parseia output do comando ARP."""
        nodes: list[TopologyNode] = []
        lines = output.strip().splitlines()

        start = 0
        for i, line in enumerate(lines):
            if "IP Address" in line and "MAC" in line:
                start = i + 1
                break

        for line in lines[start:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                nodes.append(TopologyNode(
                    device_id=parts[1],
                    name=parts[1],
                    device_type="unknown",
                ))

        return nodes

    # ── Graph management ────────────────────────────────────────────────

    def add_links(self, device_id: str, links: list[TopologyLink]) -> None:
        """Adiciona links ao grafo para um dispositivo.

        Args:
            device_id: Identificador do dispositivo.
            links: Lista de links a adicionar.
        """
        self._graph[device_id] = list(links)

    def get_graph(self) -> dict[str, list[TopologyLink]]:
        """Retorna o grafo de topologia atual.

        Returns:
            Dict: device_id → lista de TopologyLink.
        """
        return dict(self._graph)

    def clear_graph(self) -> None:
        """Limpa o grafo de topologia."""
        self._graph.clear()

    # ── Poll / change detection ─────────────────────────────────────────

    def poll(
        self,
        device_id: str,
        execute_fn: Callable[[str], str],
    ) -> dict[str, Any]:
        """Executa descoberta e detecta mudancas na topologia.

        Args:
            device_id: Identificador do dispositivo.
            execute_fn: Funcao de execucao CLI.

        Returns:
            Dict com resultado: new_links, lost_links, error (opcional).
        """
        result: dict[str, Any] = {
            "new_links": 0,
            "lost_links": 0,
            "error": None,
        }

        try:
            current_links = self.lldp_discovery(device_id, execute_fn)
        except RuntimeError as e:
            result["error"] = str(e)
            return result

        old_links = self._graph.get(device_id, [])
        old_set = {(link.source, link.target, link.target_device) for link in old_links}
        new_set = {(link.source, link.target, link.target_device) for link in current_links}

        lost = old_set - new_set
        gained = new_set - old_set

        result["new_links"] = len(gained)
        result["lost_links"] = len(lost)

        self._graph[device_id] = current_links

        # Notify via event callback
        if self._event_callback is not None:
            if lost:
                for src, tgt, tgt_dev in lost:
                    self._event_callback(
                        device=device_id,
                        event_type="lost",
                        details=f"Link lost: {src} → {tgt} ({tgt_dev})",
                    )
            if gained:
                for src, tgt, tgt_dev in gained:
                    self._event_callback(
                        device=device_id,
                        event_type="new",
                        details=f"New link: {src} → {tgt} ({tgt_dev})",
                    )

        return result
