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
    from PySide6.QtWidgets import QWidget

    from huawei_manager.audit_log import AuditLogger
    from huawei_manager.device_models import Device
    from huawei_manager.sdn_controller.bus import IEventBus
    from huawei_manager.sdn_controller.southbound import SouthboundProtocol

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
