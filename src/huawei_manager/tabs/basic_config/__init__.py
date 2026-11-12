"""Aba de Configuração Básica de Dispositivos (admin-only)."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from huawei_manager.tabs._contract import TabModule


def _basic_config_module() -> TabModule:
    """Factory lazy para instanciar o módulo TabModule da Config Básica."""
    from huawei_manager.tabs.basic_config.page import BasicConfigTab

    return BasicConfigTab()


__all__ = ["_basic_config_module"]
