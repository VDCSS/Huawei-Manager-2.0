"""RouterDriver — driver para roteadores Huawei VRP."""
from __future__ import annotations

from huawei_manager.sdn_controller.bus import IEventBus
from huawei_manager.sdn_controller.drivers.base import BaseDriver
from huawei_manager.sdn_controller.normalizer import (
    ArpEntry,
    InterfaceEntry,
    RouteEntry,
    VlanEntry,
    parse_arp_table,
    parse_interfaces,
    parse_routing_table,
    parse_vlans,
)
from huawei_manager.sdn_controller.southbound import SouthboundProtocol


class RouterDriver(BaseDriver):
    """Driver para roteadores Huawei (VRP).

    Implementa todos os metodos abstratos de ``BaseDriver`` delegando
    ao ``SouthboundProtocol`` para comunicacao e ao ``normalizer`` para
    parsing dos outputs CLI.
    """

    def __init__(
        self,
        southbound: SouthboundProtocol,
        event_queue: IEventBus,
    ) -> None:
        super().__init__(southbound, event_queue)

    @property
    def device_type(self) -> str:
        return "router"

    def send_command(self, command: str) -> str:
        return self._sb.send_command(command)

    def send_config(self, commands: list[str]) -> tuple[bool, str]:
        return self._sb.send_config(commands)

    def get_routing_table(self) -> list[RouteEntry]:
        output = self._sb.send_command("display ip routing-table")
        return parse_routing_table(output)

    def get_interfaces(self) -> list[InterfaceEntry]:
        output = self._sb.send_command("display interface brief")
        return parse_interfaces(output)

    def get_arp_table(self) -> list[ArpEntry]:
        output = self._sb.send_command("display arp")
        return parse_arp_table(output)

    def get_vlans(self) -> list[VlanEntry]:
        output = self._sb.send_command("display vlan")
        return parse_vlans(output)
