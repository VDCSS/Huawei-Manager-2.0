"""Contrato TabModule — abas independentes (Fundação F0).

Modelo alvo (plano ``plano-abas-independentes.md``): cada aba é um módulo
fechado em ``huawei_manager/tabs/<aba>/`` (página, handlers e estado
privados), recebendo **serviços centrais** via :class:`TabContext` e nunca
vendo o ``App``. Comunicação entre abas: event bus + facade read-only.

Este módulo define só o contrato — o registry fica em ``tabs/__init__``.
Não importa ``app.py`` nem ``pages/`` (evita ciclo): o :class:`LegacyTabAdapter`
recebe os builders legados já vinculados, construídos pelo App.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from PySide6.QtWidgets import QWidget

    from huawei_manager.agents import AgentResult
    from huawei_manager.agents.watcher import Watcher
    from huawei_manager.audit_log import AuditLogger
    from huawei_manager.command import ConfigCommand
    from huawei_manager.device_models import Device
    from huawei_manager.sdn_controller.bus import IEventBus
    from huawei_manager.sdn_controller.drivers.base import BaseDriver
    from huawei_manager.sdn_controller.dryrun import DryRunEngine
    from huawei_manager.sdn_controller.southbound import SouthboundProtocol
    from huawei_manager.sdn_controller.validator import CommandValidator
    from huawei_manager.services.ui_bridge import UiBridge
    from huawei_manager.session import NetmikoSession

__all__ = ["LegacyTabAdapter", "TabContext", "TabDef", "TabModule"]


@dataclass(frozen=True)
class TabContext:
    """Serviços que uma aba pode ver — nunca o App inteiro.

    Montado uma vez pelo App e injetado em ``TabModule.build``. Os callables
    (``role``/``device``) são consultados sob demanda: o valor muda em
    runtime (troca de device/papel) e a aba não pode capturar cópia velha.
    """

    sb: SouthboundProtocol          # operações no device (validator + auditoria)
    audit: AuditLogger | None       # auditoria (None = indisponível; call sites guardam)
    event_bus: IEventBus            # barramento de eventos (cruzamento entre abas)
    role: Callable[[], str]         # papel atual sob demanda ("user"/"tecnico"/"admin")
    device: Callable[[], Device | None]  # device selecionado sob demanda
    dispatch: Callable[..., None]   # agendamento na thread GUI (App._dispatch)
    # Fase 1 (piloto Manutenção) — serviços que a aba real consome:
    require_access: Callable[[str], bool]   # RBAC de ação (App._require_access)
    spawn_io: Callable[..., None]           # thread de IO (App._spawn_io)
    spawn_cpu: Callable[..., None]          # thread de CPU (App._spawn_cpu)
    watcher: Watcher                        # watcher global (is_active/start/stop)
    is_mock: Callable[[], bool]             # modo probe global (App._mock_mode)
    toggle_mock: Callable[[], bool]         # alterna e devolve o novo modo
    show_auth_dialog: Callable[[], None]    # diálogo de login (App._show_auth_dialog)
    watcher_results: Callable[[], Sequence[AgentResult] | None]  # snapshot global
    set_watcher_results: Callable[[Sequence[AgentResult]], None]  # grava snapshot
    # Fase 2 (aba Editor de Comandos — F2-cmd) — serviços que o módulo consome:
    session: NetmikoSession            # sessão SSH (is_connected/run_cli_rpc/_user/_host)
    run: Callable[..., None]           # device + sessão + IO thread (App._run)
    set_status: Callable[[str, str], None]  # rodapé de status (App._set_status)
    touch_session: Callable[[], None]  # heartbeat de sessão (SessionTracker.touch)
    cmd_validator: CommandValidator | None   # RBAC por comando (None = desativado)
    dry_run: DryRunEngine | None             # pré-visualização de config (None = off)
    # Snapshot de rollback compartilhado com Serviços (attribute do App):
    get_last_config_command: Callable[[], ConfigCommand | None]
    set_last_config_command: Callable[[ConfigCommand | None], None]
    # Fase 2 (aba Roteamento — F2-route) — driver sob demanda: o App RE-CRIA
    # o driver em handlers/devices.py ao trocar de device, então o contexto
    # expõe um getter (NUNCA bind direto — capturaria cópia velha).
    drv: Callable[[], BaseDriver]  # driver atual sob demanda (App._drv)
    # Fase 2 (aba Dashboard — F2-home) — inventário e navegação:
    devices: Callable[[], Sequence[Device]]  # inventário sob demanda (App._devices)
    show_page: Callable[[str], None]         # navegação de página (App._show_page)
    # Fase 2 (aba Serviços — F2-services) — modo, ponte I/O→GUI e device-ready:
    svc_mode: Callable[[], str]              # modo mock/cli sob demanda (App._svc_mode_var)
    ui_bridge: Callable[[], UiBridge | None]  # ponte p/ confirmação NAPALM (App._ui_bridge)
    ensure_device_ready: Callable[[str], Device | None]  # device pronto ou None (App._ensure_device_ready)
    refresh_devices: Callable[[], None]            # recarrega inventário (App._refresh_devices)
    show_device_dialog: Callable[..., None]        # diálogo de device (App._show_device_dialog)
    on_device_selected: Callable[[Device], None]   # seleção no canvas (App._on_device_selected)
    delete_device: Callable[[Device], None]        # remoção via canvas (App._delete_device)
    clear_device_target: Callable[[], None]        # limpa alvo SSH (App._clear_device_target)


@runtime_checkable
class TabModule(Protocol):
    """Ciclo de vida de uma aba: ``build`` (lazy, na primeira visita) e ``dispose``.

    ``build`` retorna a ``QWidget`` da aba (o App registra no
    ``QStackedWidget``) ou ``None`` quando o registro já foi feito pelo
    caminho legado. ``dispose`` é chamado no rebuild da aba; subscriptions
    feitas via contexto devem ser canceladas aqui.
    """

    def build(self, ctx: TabContext) -> QWidget | None: ...
    def dispose(self) -> None: ...


@dataclass(frozen=True)
class TabDef:
    """Entrada do registry — fonte única de sidebar, builders e RBAC."""

    key: str                       # "manutencao" — identifica em _show_page/palette
    label: str                     # rótulo da sidebar
    icon: str                      # caractere do ícone
    color: str                     # cor neon do botão
    group: str                     # seção da sidebar ("DASHBOARD", "DISPOSITIVOS", ...)
    min_role: str                  # "user" | "tecnico" | "admin" (hoje todos "user")
    description: str               # descrição na command palette
    shortcut: str | None           # atalho de navegação na palette (Ctrl+N)
    module: TabModule


class LegacyTabAdapter:
    """Embrulha um builder legado (``self._build_<aba>_page``) como :class:`TabModule`.

    O builder legado registra a página sozinho (``App._make_page``), por isso
    ``build`` retorna ``None`` — o App só registra quando há widget retornado.
    """

    def __init__(self, builder: Callable[[], None]) -> None:
        self._builder = builder

    def build(self, ctx: TabContext) -> None:  # noqa: ARG002 — ctx reservado p/ migração
        self._builder()
        return None

    def dispose(self) -> None:
        return None
