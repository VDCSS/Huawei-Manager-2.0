"""FirewallDriver — driver para firewalls Huawei (USG/Eudemon)."""
from __future__ import annotations

from huawei_manager.sdn_controller.bus import IEventBus
from huawei_manager.sdn_controller.drivers.router import RouterDriver
from huawei_manager.sdn_controller.southbound import SouthboundProtocol


class FirewallDriver(RouterDriver):
    """Driver para firewalls Huawei (USG/Eudemon VRP).

    Herda toda a implementacao do ``RouterDriver`` pois ambos usam o
    mesmo VRP CLI. Metodos especificos de firewall (security-policy,
    IPSec, HRP) serao adicionados conforme necessario.
    """

    def __init__(
        self,
        southbound: SouthboundProtocol,
        event_queue: IEventBus,
    ) -> None:
        super().__init__(southbound, event_queue)

    @property
    def device_type(self) -> str:
        return "firewall"
