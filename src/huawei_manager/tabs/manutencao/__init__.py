"""Aba Manutenção (piloto F1) — módulo TabModule independente.

Exporta o módulo construível; o :class:`~huawei_manager.tabs._contract.TabDef`
(ícone/label/grupo/RBAC) fica no registry único ``huawei_manager.tabs``.
"""
from huawei_manager.tabs.manutencao.page import ManutencaoTab

__all__ = ["ManutencaoTab"]
