"""Handler da aba Configuração Atual — fetch de config via SSH.

Extraído de ``handlers/fetch.py`` (``FetchMixin._fetch_config``, F2-config
do plano ``plano-abas-independentes.md``): a classe injetada
:class:`ConfigHandlers` ``(ctx, state)`` lê só o :class:`TabContext`.
``_fetch_route/_fetch_arp/_fetch_info`` permanecem no mixin legado até as
abas route/arp/info migrarem (F2).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from huawei_manager.exceptions import SdnError
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import CommandExecutedPayload
from huawei_manager.tabs import _ui

if TYPE_CHECKING:
    from huawei_manager.tabs._contract import TabContext
    from huawei_manager.tabs.config.state import ConfigState


class ConfigHandlers:
    """Fetch da configuração atual (roda na IO thread via ctx.run)."""

    def __init__(self, ctx: TabContext, state: ConfigState) -> None:
        self._ctx = ctx
        self._state = state

    def fetch_config(self) -> None:
        """Busca a configuracao atual do roteador (display current-configuration)."""
        self._ctx.touch_session()
        out = self._state.out
        dispatch = self._ctx.dispatch
        _ui.loading(out, "Carregando configuracao atual…", dispatch)
        try:
            output = self._ctx.sb.send_command("display current-configuration")
        except SdnError as exc:
            self._ctx.sb.invalidate_connection()
            _ui.write(out, f"✘ Falha SSH: {exc}", dispatch)
            return
        _ui.write(out, output, dispatch)
        self._ctx.event_bus.put(Event(EventType.COMMAND_EXECUTED,
                                      source="fetch",
                                      payload=CommandExecutedPayload(
                                          command="display current-configuration")))
