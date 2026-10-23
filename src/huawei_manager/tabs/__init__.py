"""Registry único de abas — fonte da sidebar e do RBAC.

As 10 abas são módulos reais ``tabs/<aba>/`` construídos pelo
``module_factory`` de cada :class:`_TabMeta` (Fase 2 completa). Adicionar
aba = criar o pacote + uma entrada aqui (ver README).

Ordem da lista = ordem da sidebar. Grupos na ordem de exibição.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import huawei_manager.constants as C
from huawei_manager.sdn_controller.authz import role_meets
from huawei_manager.tabs._contract import TabDef, TabModule

__all__ = ["TabDef", "TabModule", "build_registry", "tab_by_key", "visible_tabs"]

_ROLES = ("user", "tecnico", "admin")


@dataclass(frozen=True)
class _TabMeta:
    """Metadados declarativos de uma aba (sem o módulo — construído no registry)."""

    key: str
    label: str
    icon: str
    color: str
    group: str
    description: str
    shortcut: str | None
    module_factory: Callable[[], TabModule]  # módulo real — obrigatório (F2 completa)
    min_role: str = "user"         # hoje tudo visível; RBAC de visibilidade via registry


def _cmd_module() -> TabModule:
    from huawei_manager.tabs.cmd import CmdTab

    return CmdTab()


def _backup_module() -> TabModule:
    from huawei_manager.tabs.backup import BackupTab

    return BackupTab()


def _config_module() -> TabModule:
    from huawei_manager.tabs.config import ConfigTab

    return ConfigTab()


def _route_module() -> TabModule:
    from huawei_manager.tabs.route import RouteTab

    return RouteTab()


def _arp_module() -> TabModule:
    from huawei_manager.tabs.arp import ArpTab

    return ArpTab()


def _info_module() -> TabModule:
    from huawei_manager.tabs.info import InfoTab

    return InfoTab()


def _home_module() -> TabModule:
    from huawei_manager.tabs.home import HomeTab

    return HomeTab()


def _services_module() -> TabModule:
    from huawei_manager.tabs.services import ServicesTab

    return ServicesTab()


def _manutencao_module() -> TabModule:
    """Módulo real da Manutenção (Fase 1) — import lazy evita ciclo."""
    from huawei_manager.tabs.manutencao import ManutencaoTab
    return ManutencaoTab()


def _topology_module() -> TabModule:
    """Módulo real da Topologia (F2-topology) — import lazy evita ciclo."""
    from huawei_manager.tabs.topology import TopologyTab
    return TopologyTab()


_TAB_META: tuple[_TabMeta, ...] = (
    _TabMeta("home", "Dashboard", "\U0001f3e0", C.NEON_CYAN, "DASHBOARD",
             "Visão geral do sistema", "Ctrl+1", module_factory=_home_module),
    _TabMeta("topology", "Topologia / Devices", "\U0001f5fa", C.NEON_AMBER, "DISPOSITIVOS",
             "Visualizar e gerenciar dispositivos", "Ctrl+2", module_factory=_topology_module),
    _TabMeta("config", "Config Atual", "\U0001f4cb", C.NEON_CYAN, "DISPOSITIVOS",
             "Exibir configuração atual do roteador", "Ctrl+3", module_factory=_config_module),
    _TabMeta("route", "Roteamento", "\U0001f310", C.NEON_CYAN, "DISPOSITIVOS",
             "Tabela de roteamento", "Ctrl+4", module_factory=_route_module),
    _TabMeta("arp", "Tabela ARP", "\U0001f4e1", C.NEON_CYAN, "DISPOSITIVOS",
             "Tabela ARP", "Ctrl+5", module_factory=_arp_module),
    _TabMeta("info", "Info do Sistema", "\U0001f4bb", C.NEON_MAG, "DISPOSITIVOS",
             "Informações do sistema", "Ctrl+6", module_factory=_info_module),
    _TabMeta("cmd", "Editor de Comandos", "⌨", C.NEON_MAG, "FERRAMENTAS",
             "Executar comandos personalizados", "Ctrl+7", module_factory=_cmd_module),
    _TabMeta("backup", "Backup", "\U0001f4be", C.NEON_PURP, "FERRAMENTAS",
             "Gerenciar backups de configuração", "Ctrl+8", module_factory=_backup_module),
    _TabMeta("services", "Servicos", "⚡", C.NEON_AMBER, "FERRAMENTAS",
             "Gerenciar serviços do roteador", "Ctrl+9", module_factory=_services_module),
    _TabMeta("manutencao", "Manutencao", "\U0001f6e0", C.NEON_MAG, "ADMINISTRACAO",
             "Ferramentas de manutenção", "Ctrl+0",
             module_factory=_manutencao_module),
)


def build_registry() -> list[TabDef]:
    """Constrói o registry de abas — todas as abas têm módulo real.

    Returns:
        Lista de :class:`TabDef` ordenada como a sidebar.
    """
    tabs: list[TabDef] = []
    for meta in _TAB_META:
        module: TabModule = meta.module_factory()
        tabs.append(TabDef(
            key=meta.key, label=meta.label, icon=meta.icon, color=meta.color,
            group=meta.group, min_role=meta.min_role,
            description=meta.description, shortcut=meta.shortcut,
            module=module,
        ))
    return tabs


def tab_by_key(tabs: list[TabDef], key: str) -> TabDef | None:
    """Retorna a :class:`TabDef` da chave ou ``None``."""
    for td in tabs:
        if td.key == key:
            return td
    return None


def visible_tabs(tabs: list[TabDef], role: str) -> list[TabDef]:
    """Filtra as abas visíveis para o papel (``authz.role_meets``)."""
    if role not in _ROLES:
        role = "user"  # fail-closed: papel desconhecido vê o mínimo
    return [td for td in tabs if role_meets(role, td.min_role)]
