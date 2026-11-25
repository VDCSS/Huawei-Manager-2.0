"""Núcleo de configuração básica de dispositivos Huawei (VRP).

Este pacote concentra a parametrização tipada, os builders de blocos de
configuração e as rotinas de verificação/rollback usadas pela aba
"Config Básica" e pelos serviços de ACL.

Regra de ouro: nenhum valor digitado pelo operador é enviado ao device sem
passar por :func:`normalize_values`. O renderizador produz um bloco
hierárquico único, que deve ser aplicado em uma única sessão ``system-view``.
"""
from __future__ import annotations

from huawei_manager.basic_config.params import (
    ConfigTemplate,
    ParamKind,
    ParamSpec,
    normalize_values,
)

__all__ = [
    "ConfigTemplate",
    "ParamKind",
    "ParamSpec",
    "normalize_values",
]
