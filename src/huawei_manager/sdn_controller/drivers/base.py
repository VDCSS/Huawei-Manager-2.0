"""BaseDriver — classe abstrata para drivers de dispositivo.

Fornece a interface comum que todos os drivers de dispositivo Huawei
devem implementar. Cada driver concreto especifica os comandos CLI
para sua familia de dispositivo e usa o normalizer para estruturar
a saida.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from huawei_manager.sdn_controller.bus import IEventBus
from huawei_manager.sdn_controller.normalizer import (
    ArpEntry,
    InterfaceEntry,
    RouteEntry,
    VlanEntry,
)
from huawei_manager.sdn_controller.southbound import SouthboundProtocol


class BaseDriver(ABC):
    """Classe base abstrata para drivers de dispositivo Huawei.

    Args:
        southbound: Instancia de ``SouthboundProtocol`` para comunicacao.
        event_queue: Instancia de ``IEventBus`` para eventos do driver.
    """

    def __init__(
        self,
        southbound: SouthboundProtocol,
        event_queue: IEventBus,
    ) -> None:
        self._sb = southbound
        self._eq = event_queue

    @property
    @abstractmethod
    def device_type(self) -> str:
        """Identificador do tipo de dispositivo (ex: 'router', 'switch')."""

    @abstractmethod
    def send_command(self, command: str) -> str:
        """Executa um comando CLI e retorna o output bruto."""

    @abstractmethod
    def send_config(self, commands: list[str]) -> tuple[bool, str]:
        """Envia comandos de configuracao. Retorna (sucesso, mensagem)."""

    @abstractmethod
    def get_routing_table(self) -> list[RouteEntry]:
        """Retorna a tabela de roteamento do dispositivo."""

    @abstractmethod
    def get_interfaces(self) -> list[InterfaceEntry]:
        """Retorna lista de interfaces do dispositivo."""

    @abstractmethod
    def get_arp_table(self) -> list[ArpEntry]:
        """Retorna a tabela ARP do dispositivo."""

    @abstractmethod
    def get_vlans(self) -> list[VlanEntry]:
        """Retorna lista de VLANs configuradas no dispositivo."""
