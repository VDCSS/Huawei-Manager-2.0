"""Testes do wiring NAPALM em ``ServicesMixin`` (handlers/services.py).

Cobrem o fluxo preview → diff → confirmação do usuário → apply → auditoria
com ``HW_BACKEND=napalm``, e garantem que o caminho Netmiko padrão permanece
inalterado (nenhuma chamada NAPALM) quando o backend efetivo é o Netmiko ou o
serviço não é de configuração.

O módulo ``FakeBridge`` substitui o ``UiBridge`` real (um ``QObject``) nos
testes de fluxo — ele implementa os dois caminhos de :func:`ask_from_worker`
(``handle_ask`` direto na thread GUI e ``ask.emit`` cross-thread); o caminho
real com ``UiBridge``/``QMessageBox`` é coberto pelos testes de
``ask_from_worker`` no fim do arquivo.
"""
from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from huawei_manager.exceptions import SdnError
from huawei_manager.handlers.services import ServicesMixin
from huawei_manager.sdn_controller.event_queue import EventType
from huawei_manager.sdn_controller.napalm_backend import (
    BACKEND_NAPALM,
    BACKEND_NETMIKO,
    BACKEND_ENV,
    ApplyResult,
)
from huawei_manager.services import ServiceDef


# ── fábricas ─────────────────────────────────────────────────────────
def _make_svc(**overrides) -> ServiceDef:
    defaults = dict(
        id="svc-napalm",
        name="Napalm Service",
        description="test command <param1>",
        category="test",
        device_types=["ROUTER"],
        cli_commands=["test command <param1>"],
        config_mode=True,
    )
    defaults.update(overrides)
    return ServiceDef(**defaults)


class FakeAudit:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def log_operation(self, op: str, **kw) -> None:
        self.entries.append({"op": op, **kw})


class _RecordingSignal:
    """Duck-type do ``Signal`` do UiBridge para testes headless."""

    def __init__(self, bridge: FakeBridge) -> None:
        self._bridge = bridge

    def emit(self, payload) -> None:  # noqa: ANN001 — payload é AskPayload
        self._bridge._respond(payload)


class FakeBridge:
    """Substituto do ``UiBridge``: registra o payload e responde programaticamente."""

    def __init__(self, answer: bool) -> None:
        self._answer = answer
        self.payloads: list[dict] = []
        self.direct_calls = 0
        self.ask = _RecordingSignal(self)

    def handle_ask(self, payload) -> None:  # noqa: ANN001
        # caminho "thread GUI" de ask_from_worker (chamada direta)
        self.direct_calls += 1
        self._respond(payload)

    def _respond(self, payload) -> None:  # noqa: ANN001
        self.payloads.append(payload)
        payload["answer"] = self._answer
        payload["event"].set()


def _make_mixin(**attrs) -> ServicesMixin:
    mixin = ServicesMixin()
    device = MagicMock()
    defaults = dict(
        _svc_mode_var="cli",
        _target_device=None,
        _svc_device_lbl=MagicMock(),
        _svc_output=MagicMock(),
        _svc_param_entries={},
        _sb=MagicMock(),
        session=None,
        audit_logger=None,
        _ui_bridge=None,
        _write=MagicMock(),
        _loading=MagicMock(),
        _event_queue=MagicMock(),
        _devices=[device],
        _device_service=MagicMock(),
        _access_level="user",
        _get_selected_device=MagicMock(return_value=device),
        _set_status=MagicMock(),
        _ensure_device_ready=MagicMock(return_value=device),
    )
    for k, v in defaults.items():
        setattr(mixin, k, v)
    for k, v in attrs.items():
        setattr(mixin, k, v)
    return mixin


def _run(mixin: ServicesMixin, svc: ServiceDef) -> None:
    """Roda ``_run_service`` de forma síncrona (executa ``_do`` na hora)."""
    mixin._spawn_io = lambda fn: fn()
    mixin._run_service(svc)


def _writes(mixin: ServicesMixin) -> list[str]:
    return [c.args[1] for c in mixin._write.call_args_list
            if len(c.args) >= 2]


def _fake_executor(monkeypatch, *, diff: str = "- old\n+ new"):
    """Substitui ``NapalmVRPBackend`` no namespace do handler e devolve mocks."""
    executor = MagicMock()
    executor.preview.return_value = diff
    executor.apply.return_value = ApplyResult(
        snapshot="snap pré", output="cfg ok", duration_ms=5.0)
    cls = MagicMock(return_value=executor)
    monkeypatch.setattr("huawei_manager.handlers.services.NapalmVRPBackend",
                        cls)
    return executor, cls


def _backend(monkeypatch, backend: str = BACKEND_NAPALM,
             warning: str = "") -> None:
    monkeypatch.setattr(
        "huawei_manager.handlers.services.resolve_backend",
        lambda: (backend, warning),
    )


# ══════════════════════════════════════════════════════════════════════
#  1) backend Netmiko: caminho atual intacto, zero NAPALM
# ══════════════════════════════════════════════════════════════════════
def test_netmiko_padrao_nao_toca_napalm(monkeypatch) -> None:
    monkeypatch.delenv(BACKEND_ENV, raising=False)
    _backend(monkeypatch, BACKEND_NETMIKO)
    napalm_cls = MagicMock()
    monkeypatch.setattr("huawei_manager.handlers.services.NapalmVRPBackend",
                        napalm_cls)
    mixin = _make_mixin()
    svc = _make_svc()

    _run(mixin, svc)

    mixin._sb.send_service_commands.assert_called_once_with(
        svc.cli_commands, config_mode=True, requires_privilege=False)
    napalm_cls.assert_not_called()          # nenhuma chamada NAPALM
    ev = mixin._event_queue.put.call_args[0][0]
    assert ev.type is EventType.COMMAND_EXECUTED
    assert ev.payload.data == {"mode": "cli"}  # payload original, sem backend


# ══════════════════════════════════════════════════════════════════════
#  1b) snapshot pré-mudança do caminho Netmiko (Command pattern)
# ══════════════════════════════════════════════════════════════════════
def test_netmiko_config_takes_snapshot_before_apply(monkeypatch) -> None:
    monkeypatch.delenv(BACKEND_ENV, raising=False)
    _backend(monkeypatch, BACKEND_NETMIKO)
    mixin = _make_mixin()
    mixin._sb.send_command.return_value = "baseline cfg"
    svc = _make_svc()

    _run(mixin, svc)

    mixin._sb.send_command.assert_called_once_with(
        "display current-configuration")
    mixin._sb.send_service_commands.assert_called_once_with(
        svc.cli_commands, config_mode=True, requires_privilege=False)
    command = mixin._last_config_command
    assert command.snapshot == "baseline cfg"  # rollback disponível


def test_netmiko_config_snapshot_failure_is_fail_closed(monkeypatch) -> None:
    monkeypatch.delenv(BACKEND_ENV, raising=False)
    _backend(monkeypatch, BACKEND_NETMIKO)
    mixin = _make_mixin()
    mixin._sb.send_command.side_effect = SdnError("conexão caiu")
    svc = _make_svc()

    _run(mixin, svc)

    # fail-closed: sem snapshot nada foi aplicado e não há o que desfazer
    mixin._sb.send_service_commands.assert_not_called()
    assert any("nada foi aplicado" in t for t in _writes(mixin))
    assert not hasattr(mixin, "_last_config_command")


# ══════════════════════════════════════════════════════════════════════
#  2) napalm + diff → usuário aceita → apply com os comandos certos
# ══════════════════════════════════════════════════════════════════════
def test_napalm_diff_confirmado_aplica_comandos(monkeypatch) -> None:
    _backend(monkeypatch)
    executor, cls = _fake_executor(monkeypatch, diff="- old\n+ new")
    bridge = FakeBridge(answer=True)
    mixin = _make_mixin(_ui_bridge=bridge)
    svc = _make_svc()

    _run(mixin, svc)

    cls.assert_called_once()
    executor.preview.assert_called_once_with(svc.cli_commands)
    executor.apply.assert_called_once_with(svc.cli_commands)
    # o diálogo recebeu exatamente a diff proposta
    assert len(bridge.payloads) == 1
    assert bridge.payloads[0]["message"] == "- old\n+ new"
    # o caminho Netmiko NÃO foi usado
    mixin._sb.send_service_commands.assert_not_called()
    # output do apply visível + evento COMMAND_EXECUTED com backend napalm
    assert any("cfg ok" in t for t in _writes(mixin))
    ev = mixin._event_queue.put.call_args[0][0]
    assert ev.type is EventType.COMMAND_EXECUTED
    assert ev.payload.data == {"mode": "cli", "backend": BACKEND_NAPALM}


# ══════════════════════════════════════════════════════════════════════
#  3) usuário recusa → sem apply, sem Netmiko, audit blocked
# ══════════════════════════════════════════════════════════════════════
def test_napalm_usuario_recusa_nao_aplica(monkeypatch) -> None:
    _backend(monkeypatch)
    executor, _cls = _fake_executor(monkeypatch)
    audit = FakeAudit()
    bridge = FakeBridge(answer=False)
    mixin = _make_mixin(_ui_bridge=bridge, audit_logger=audit)
    svc = _make_svc()

    _run(mixin, svc)

    executor.apply.assert_not_called()
    mixin._sb.send_service_commands.assert_not_called()
    assert any("Cancelado" in t for t in _writes(mixin))
    assert any(e["status"] == "blocked" for e in audit.entries)


# ══════════════════════════════════════════════════════════════════════
#  4) preview falha → fail-closed: audit blocked, sem fallback Netmiko
# ══════════════════════════════════════════════════════════════════════
def test_napalm_preview_falha_fail_closed(monkeypatch) -> None:
    _backend(monkeypatch)
    executor, _cls = _fake_executor(monkeypatch)
    executor.preview.side_effect = RuntimeError("driver boom")
    audit = FakeAudit()
    mixin = _make_mixin(audit_logger=audit)
    svc = _make_svc()

    _run(mixin, svc)

    executor.apply.assert_not_called()
    # recusa explícita: NUNCA fallback silencioso para Netmiko
    mixin._sb.send_service_commands.assert_not_called()
    assert any("preview" in t.lower() and "\u2718" in t for t in _writes(mixin))
    blocked = [e for e in audit.entries if e["status"] == "blocked"]
    assert len(blocked) == 1
    assert "preview falhou" in blocked[0]["reason"]


# ══════════════════════════════════════════════════════════════════════
#  5) diff vazio → sem apply e sem diálogo
# ══════════════════════════════════════════════════════════════════════
def test_napalm_diff_vazio_sem_apply(monkeypatch) -> None:
    _backend(monkeypatch)
    executor, _cls = _fake_executor(monkeypatch, diff="")
    bridge = FakeBridge(answer=True)
    mixin = _make_mixin(_ui_bridge=bridge)
    svc = _make_svc()

    _run(mixin, svc)

    executor.apply.assert_not_called()
    mixin._sb.send_service_commands.assert_not_called()
    assert bridge.payloads == []            # nenhum diálogo para diff vazio
    assert any("Sem mudancas a aplicar" in t for t in _writes(mixin))


# ══════════════════════════════════════════════════════════════════════
#  6) bridge indisponível (None) → aplica sem confirmação
# ══════════════════════════════════════════════════════════════════════
def test_napalm_sem_bridge_aplica_sem_confirmacao(monkeypatch) -> None:
    _backend(monkeypatch)
    executor, _cls = _fake_executor(monkeypatch)
    mixin = _make_mixin(_ui_bridge=None)   # app sem GUI / testes headless
    svc = _make_svc()

    _run(mixin, svc)

    executor.preview.assert_called_once()
    executor.apply.assert_called_once_with(svc.cli_commands)
    mixin._sb.send_service_commands.assert_not_called()
    assert any("cfg ok" in t for t in _writes(mixin))


# ══════════════════════════════════════════════════════════════════════
#  7) config_mode=False (leitura) → nunca toca NAPALM
# ══════════════════════════════════════════════════════════════════════
def test_servico_leitura_ignora_napalm(monkeypatch) -> None:
    _backend(monkeypatch, BACKEND_NAPALM)
    napalm_cls = MagicMock()
    monkeypatch.setattr("huawei_manager.handlers.services.NapalmVRPBackend",
                        napalm_cls)
    mixin = _make_mixin()
    svc = _make_svc(config_mode=False)

    _run(mixin, svc)

    napalm_cls.assert_not_called()
    mixin._sb.send_service_commands.assert_called_once_with(
        svc.cli_commands, config_mode=False, requires_privilege=False)


# ══════════════════════════════════════════════════════════════════════
#  8) ask_from_worker: timeout devolve False e não trava o worker
# ══════════════════════════════════════════════════════════════════════
def test_ask_from_worker_timeout_retorna_false() -> None:
    from PySide6.QtWidgets import QApplication

    from huawei_manager.services.ui_bridge import UiBridge, ask_from_worker

    # Patch no binding que o código realmente usa (import de topo em
    # ui_bridge) — patchar PySide6.QtWidgets.QMessageBox não afeta
    # ui_bridge.QMessageBox e deixaria o diálogo real travar a suíte.
    with patch("huawei_manager.services.ui_bridge.QMessageBox") as msgbox:
        msgbox.question.return_value = msgbox.StandardButton.No
        bridge = UiBridge()               # criado na thread dos testes (GUI)
        results: list[bool] = []

        def _worker() -> None:
            # worker nunca recebe resposta → deve desbloquear no timeout
            results.append(ask_from_worker(bridge, title="t", message="m",
                                           timeout=0.2))

        t = threading.Thread(target=_worker)
        t.start()
        t.join(timeout=5)
        assert not t.is_alive()
        # drena a entrega queued pendente sob o patch (nunca diálogo real)
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    assert results == [False]


# ══════════════════════════════════════════════════════════════════════
#  9) ask_from_worker na thread GUI → handler direto, sem fila
# ══════════════════════════════════════════════════════════════════════
def test_ask_from_worker_na_thread_gui_chama_direto() -> None:
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QApplication

    from huawei_manager.services.ui_bridge import ask_from_worker

    app = QApplication.instance()
    if app is None or QThread.currentThread() is not app.thread():
        pytest.skip("sem QApplication na thread dos testes")
    bridge = FakeBridge(answer=True)

    assert ask_from_worker(bridge, title="t", message="m", timeout=5) is True
    assert bridge.direct_calls == 1        # handle_ask direto (não via fila)
    assert len(bridge.payloads) == 1


# ══════════════════════════════════════════════════════════════════════
#  10) conexão Netmiko exposta somente-leitura para o NAPALM
# ══════════════════════════════════════════════════════════════════════
def test_southbound_connection_somente_leitura() -> None:
    from huawei_manager.audit_log import AuditLogger
    from huawei_manager.sdn_controller.southbound import SSHSouthbound
    from huawei_manager.vault import EnvBackend

    session = MagicMock()
    session.connection = "netmiko-conn"
    sb = SSHSouthbound(EnvBackend(), AuditLogger(), session=session)

    assert sb.connection == "netmiko-conn"
    prop = SSHSouthbound.__dict__["connection"]
    assert isinstance(prop, property)
    assert prop.fset is None               # somente leitura (sem setter)
