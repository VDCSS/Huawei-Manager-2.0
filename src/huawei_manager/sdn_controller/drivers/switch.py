"""SwitchDriver — driver para switches Huawei VRP."""
from __future__ import annotations

from huawei_manager.sdn_controller.bus import IEventBus
from huawei_manager.sdn_controller.drivers.router import RouterDriver
from huawei_manager.sdn_controller.southbound import SouthboundProtocol


class SwitchDriver(RouterDriver):
    """Driver para switches Huawei (VRP).

    Herda toda a implementacao do ``RouterDriver`` pois ambos usam o
    mesmo VRP CLI. Metodos especificos de switch (STP, LACP, PoE)
    serao adicionados conforme necessario.
    """

    def __init__(
        self,
        southbound: SouthboundProtocol,
        event_queue: IEventBus,
    ) -> None:
        super().__init__(southbound, event_queue)

    @property
    def device_type(self) -> str:
        return "switch"
