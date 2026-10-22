"""Registry único de abas — fonte da sidebar, dos builders e do RBAC.

Fase 0 (fundação): as 10 abas são definidas por :class:`TabDef` com metadados
declarativos (label, ícone, cor, grupo, min_role, descrição, atalho). Os
builders ainda são os métodos legados do App, embrulhados por
:class:`LegacyTabAdapter` — cada Fase 2 troca a entrada pelo módulo real
``tabs/<aba>/`` sem tocar neste contrato.

Ordem da lista = ordem da sidebar. Grupos na ordem de exibição.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import huawei_manager.constants as C
from huawei_manager.sdn_controller.authz import role_meets
from huawei_manager.tabs._contract import LegacyTabAdapter, TabDef, TabModule

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
    method: str                    # nome do builder legado no App ("" = módulo real)
    min_role: str = "user"         # hoje tudo visível; RBAC de visibilidade via registry
    module_factory: Callable[[], TabModule] | None = None  # módulo real (F1+)


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


def _manutencao_module() -> TabModule:
    """Módulo real da Manutenção (Fase 1) — import lazy evita ciclo."""
    from huawei_manager.tabs.manutencao import ManutencaoTab
    return ManutencaoTab()


_TAB_META: tuple[_TabMeta, ...] = (
    _TabMeta("home", "Dashboard", "\U0001f3e0", C.NEON_CYAN, "DASHBOARD",
             "Visão geral do sistema", "Ctrl+1", "_build_home_page"),
    _TabMeta("topology", "Topologia / Devices", "\U0001f5fa", C.NEON_AMBER, "DISPOSITIVOS",
             "Visualizar e gerenciar dispositivos", "Ctrl+2", "_build_topology_page"),
    _TabMeta("config", "Config Atual", "\U0001f4cb", C.NEON_CYAN, "DISPOSITIVOS",
             "Exibir configuração atual do roteador", "Ctrl+3", "", module_factory=_config_module),
    _TabMeta("route", "Roteamento", "\U0001f310", C.NEON_CYAN, "DISPOSITIVOS",
             "Tabela de roteamento", "Ctrl+4", "", module_factory=_route_module),
    _TabMeta("arp", "Tabela ARP", "\U0001f4e1", C.NEON_CYAN, "DISPOSITIVOS",
             "Tabela ARP", "Ctrl+5", "_build_arp_page"),
    _TabMeta("info", "Info do Sistema", "\U0001f4bb", C.NEON_MAG, "DISPOSITIVOS",
             "Informações do sistema", "Ctrl+6", "_build_info_page"),
    _TabMeta("cmd", "Editor de Comandos", "⌨", C.NEON_MAG, "FERRAMENTAS",
             "Executar comandos personalizados", "Ctrl+7", "", module_factory=_cmd_module),
    _TabMeta("backup", "Backup", "\U0001f4be", C.NEON_PURP, "FERRAMENTAS",
             "Gerenciar backups de configuração", "Ctrl+8", "", module_factory=_backup_module),
    _TabMeta("services", "Servicos", "⚡", C.NEON_AMBER, "FERRAMENTAS",
             "Gerenciar serviços do roteador", "Ctrl+9", "_build_services_page"),
    _TabMeta("manutencao", "Manutencao", "\U0001f6e0", C.NEON_MAG, "ADMINISTRACAO",
             "Ferramentas de manutenção", "Ctrl+0", "",
             module_factory=_manutencao_module),
)


class _HostProtocol(Protocol):
    """Superfície do App exigida pelo registry (builders legados vinculados)."""

    def _build_home_page(self) -> None: ...
    def _build_topology_page(self) -> None: ...
    def _build_arp_page(self) -> None: ...
    def _build_info_page(self) -> None: ...
    def _build_services_page(self) -> None: ...


def build_registry(host: _HostProtocol) -> list[TabDef]:
    """Constrói o registry de abas a partir dos builders legados do host.

    Args:
        host: Instância com os métodos ``_build_<aba>_page`` (o App).

    Returns:
        Lista ordenada como a sidebar. Aba sem builder correspondente é
        ignorada com KeyError propagado (fail-fast no boot).
    """
    tabs: list[TabDef] = []
    for meta in _TAB_META:
        if meta.module_factory is not None:
            module: TabModule = meta.module_factory()
        else:
            builder = getattr(host, meta.method, None)
            if builder is None:
                raise RuntimeError(f"host sem builder legado: {meta.method}")
            module = LegacyTabAdapter(builder)
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
