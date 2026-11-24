"""Driver Factory — resolve o driver concreto pelo tipo do dispositivo.

``BaseDriver`` é o contrato (Adapter); ``RouterDriver`` é o perfil padrão
do CLI VRP e ``SwitchDriver``/``FirewallDriver`` o especializam. Esta
factory fecha o Gap 1 do mapeamento de padrões: antes, ``app.py``
instanciava ``RouterDriver`` fixamente e os demais drivers nunca eram
usados.

O ``Device.type`` do inventário é grafado em maiúsculas
(``ROUTER``/``SWITCH``/``FIREWALL``/...), por isso a comparação é
case-insensitive.
"""
from __future__ import annotations

from huawei_manager.device_models import Device
from huawei_manager.sdn_controller.bus import IEventBus
from huawei_manager.sdn_controller.drivers.base import BaseDriver
from huawei_manager.sdn_controller.drivers.firewall import FirewallDriver
from huawei_manager.sdn_controller.drivers.router import RouterDriver
from huawei_manager.sdn_controller.drivers.switch import SwitchDriver
from huawei_manager.sdn_controller.southbound import SouthboundProtocol

# Perfil padrão: roteador VRP. Vale também para tipos que falam o mesmo
# CLI (load-balancer, wan-accel, ap) — a especialização é incremental.
_DRIVER_BY_TYPE: dict[str, type[BaseDriver]] = {
    "router": RouterDriver,
    "switch": SwitchDriver,
    "firewall": FirewallDriver,
}
_DEFAULT_DRIVER: type[BaseDriver] = RouterDriver


def normalize_device_type(device_type: str | None) -> str:
    """Normaliza ``Device.type`` para comparação (minúsculo, sem espaços)."""
    return (device_type or "").strip().lower()


def driver_for(
    device: Device | None,
    southbound: SouthboundProtocol,
    event_queue: IEventBus,
) -> BaseDriver:
    """Cria o driver adequado ao ``device.type``.

    Args:
        device: dispositivo alvo; ``None`` (nenhum selecionado no boot)
            resolve para o driver padrão.
        southbound: transporte SSH usado pelos métodos do driver.
        event_queue: barramento onde o driver publica eventos.

    Returns:
        ``SwitchDriver`` para ``switch``, ``FirewallDriver`` para
        ``firewall`` e ``RouterDriver`` para ``router`` e demais tipos
        conhecidos/desconhecidos (fail-safe: o perfil VRP padrão nunca
        deixa o dispositivo sem driver).
    """
    kind = normalize_device_type(device.type if device is not None else None)
    driver_cls = _DRIVER_BY_TYPE.get(kind, _DEFAULT_DRIVER)
    return driver_cls(southbound=southbound, event_queue=event_queue)
