"""Ponte de UI — pedir confirmação ao usuário a partir de uma thread de I/O.

Motivação: ``QMessageBox`` NUNCA pode ser criado fora da thread GUI (comportamento
não definido / crash no Qt). Os serviços em modo CLI rodam numa thread de I/O
(``_spawn_io``) e o caminho NAPALM exige **preview → diff → confirmação do
usuário → apply** — ou seja, uma resposta do usuário no meio do ``_do``.

Solução (ponte sinal + ``threading.Event``):

* ``UiBridge`` é um ``QObject`` criado na thread GUI; o worker monta o payload
  (título, mensagem, ``answer=False``, ``threading.Event``) e faz
  ``bridge.ask.emit(payload)``. Como o receptor (``handle_ask``) vive na GUI e o
  ``emit`` vem de outra thread, o Qt usa **QueuedConnection automaticamente**
  (AutoConnection) — nenhum ``QMetaObject.invokeMethod`` envolvido.
* O slot ``handle_ask`` (thread GUI) exibe o ``QMessageBox.question`` e grava
  ``payload["answer"]`` + ``payload["event"].set()``; o ``set()`` roda em
  ``finally`` — se o diálogo falhar, o worker desbloqueia e recebe ``False``
  (fail-closed) em vez de travar até o timeout.
* Se o ``emit`` for chamado pela própria thread GUI, o handler roda direto
  (guarda ``QThread.currentThread() is QApplication.instance().thread()`` em
  :func:`ask_from_worker`), sem depender de fila/event loop.
* Timeout (padrão 120s) ou GUI encerrada → ``False`` (fail-closed: cancela).

A conexão ``self.ask.connect(self.handle_ask)`` é feita no ``__init__`` do
próprio bridge — a app só precisa instanciá-lo (ver ``AppCore._init_common_attrs``);
a partir daí qualquer thread pode chamar :func:`ask_from_worker`.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, cast

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication, QMessageBox

_log = logging.getLogger(__name__)

# Payload heterogêneo (título: str, mensagem: str, resposta: bool, sincronizador:
# threading.Event) que atravessa o Signal(object) da ponte. Any é o preço do
# Signal(object) genérico; a validação real acontece em handle_ask (isinstance).
AskPayload = dict[str, Any]


class UiBridge(QObject):
    """Ponte thread-I/O → thread GUI para confirmações (``QMessageBox``).

    Crie uma instância **na thread GUI** (ex.: ``UiBridge(self)`` no ``__init__``
    da janela principal) e injete como atributo ``_ui_bridge`` do app; workers
    usam :func:`ask_from_worker` para perguntar com segurança.
    """

    # payload: AskPayload — title, message, answer, event (ver módulo).
    ask = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # AutoConnection: emit cross-thread → enfileirado na thread GUI do
        # receptor; emit na própria GUI → chamada direta.
        self.ask.connect(self.handle_ask)

    @Slot(object)
    def handle_ask(self, payload: object) -> None:
        """Exibe o diálogo na thread GUI e **sempre** libera o worker.

        Roda como slot (via fila, cross-thread) ou direto quando chamado pela
        própria thread GUI — nos dois casos a thread é a GUI.
        """
        if not isinstance(payload, dict):
            _log.error("UiBridge.ask: payload invalido (%s)",
                       type(payload).__name__)
            return
        data = cast(AskPayload, payload)  # dict checado acima; campos validados a seguir
        event = data.get("event")
        try:
            # Explícito Yes|No com default **No**: um Enter acidental nunca
            # aprova uma mudança de configuração (fail-closed também no diálogo).
            reply = QMessageBox.question(
                None,
                str(data.get("title", "")),
                str(data.get("message", "")),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            data["answer"] = reply == QMessageBox.StandardButton.Yes
        except Exception:  # diálogo indisponível (widget destruído/app saindo)
            # justificativa: falha do diálogo vira "não confirmado" (fail-closed);
            # o finally abaixo ainda desbloqueia o worker.
            data["answer"] = False
            _log.exception("UiBridge: falha ao exibir dialogo de confirmacao")
        finally:
            if isinstance(event, threading.Event):
                event.set()


def _on_gui_thread() -> bool:
    """True quando o chamador já está na thread GUI (``QApplication``)."""
    app = QApplication.instance()
    return app is not None and QThread.currentThread() is app.thread()


def ask_from_worker(bridge: UiBridge, *, title: str, message: str,
                    timeout: float = 120.0) -> bool:
    """Pede confirmação sim/não ao usuário a partir de uma thread de I/O.

    Nunca cria ``QMessageBox`` no chamador: o diálogo é montado na thread GUI
    via :class:`UiBridge`. Bloqueia no máximo ``timeout`` segundos.

    Args:
        bridge: Ponte criada na thread GUI (se ``None`` o chamador deve pular
            a confirmação — ver fluxo NAPALM em ``handlers/services.py``).
        title: Título do diálogo.
        message: Corpo do diálogo (ex.: diff de configuração proposto).
        timeout: Espera máxima pela resposta da GUI, em segundos.

    Returns:
        ``True`` apenas com resposta explícita "Sim"; qualquer outra situação
        (timeout, GUI encerrada, diálogo falho) devolve ``False`` — fail-closed.
    """
    payload: AskPayload = {
        "title": title,
        "message": message,
        "answer": False,
        "event": threading.Event(),
    }
    if _on_gui_thread():
        # emit pela própria thread GUI: handler direto, sem depender da fila
        # (uma fila aqui exigiria o event loop para ser resolvida).
        bridge.handle_ask(payload)
    else:
        # emit cross-thread: AutoConnection enfileira na thread GUI do receptor
        # (QueuedConnection automática — receptor vive na GUI).
        bridge.ask.emit(payload)
    if not payload["event"].wait(timeout):  # GUI fechou / nunca respondeu
        return False                          # fail-closed: cancela
    return bool(payload["answer"])
