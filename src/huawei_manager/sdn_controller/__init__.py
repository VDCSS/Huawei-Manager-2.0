"""SDN Controller — módulo de controle SDN para dispositivos Huawei.

Este pacote contém a lógica SDN que será integrada à GUI PySide6
existente via self._controller = ControllerCore().

Submódulos planejados:
- southbound:  Camada de abstração southbound (SSH/CLI)
- drivers:     Drivers por família de dispositivo
- normalizer:  Parsing de outputs CLI
- core:        Controller Core (estado central)
- event_queue: Fila de eventos thread-safe
- lldp_discovery: Descoberta de topologia via LLDP
"""

from __future__ import annotations
