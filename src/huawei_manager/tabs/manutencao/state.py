"""Estado privado da aba Manutenção (Fase 1 — piloto TabModule).

Vive com o módulo :class:`~huawei_manager.tabs.manutencao.page.ManutencaoTab`
entre rebuilds; o App não enxerga nenhum destes campos. Widgets ficam em
``None`` após ``dispose()`` (rebuild) — escritas em lote de um processo em
curso toleram ``None`` (guarda nos helpers).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

# Runtime: o default_factory do rb_group instancia QRadioButton em runtime.
from PySide6.QtWidgets import QRadioButton

if TYPE_CHECKING:
    from collections.abc import Sequence

    from PySide6.QtWidgets import QTextEdit

    from huawei_manager.agents import AgentResult
    from huawei_manager.widgets.neon_button import ActionButton

__all__ = ["ManutencaoState"]


@dataclass
class ManutencaoState:
    """Widgets, filtro e execução corrente da aba — invisível ao App."""

    output: QTextEdit | None = None       # painel de saída (_manut_output)
    summary: QTextEdit | None = None      # resumo de contagens (_manut_summary)
    rb_group: list[QRadioButton] = field(
        default_factory=lambda: list[QRadioButton]())  # rádios do filtro
    mode_btn: ActionButton | None = None      # botão Real/Mock
    watcher_btn: ActionButton | None = None   # botão Auto ON/OFF
    active_filter: str = "all"            # "all" | "error" | "warning" | "info"
    last_results: Sequence[AgentResult] = ()  # últimos resultados exibidos
    cancel_event: threading.Event | None = None  # cancela processo streamado
