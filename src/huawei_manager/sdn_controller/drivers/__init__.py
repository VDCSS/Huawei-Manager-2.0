"""Device Drivers — Router, Switch, Firewall.

Cada driver implementa operacoes especificas por familia de dispositivo
Huawei, usando ``SouthboundProtocol`` para comunicacao e ``normalizer``
para parsing de outputs CLI.
"""
from __future__ import annotations
