"""Testes do wiring NAPALM em ``ServicesHandlers`` (tabs/services/handlers.py).

Migrados de tests/test_services_napalm_wiring.py (F2-services do plano
plano-abas-independentes). Cobrem o fluxo preview → diff → confirmação do
usuário → apply → auditoria com ``HW_BACKEND=napalm``, e garantem que o
caminho Netmiko padrão permanece inalterado (nenhuma chamada NAPALM) quando
o backend efetivo é o Netmiko ou o serviço não é de configuração.

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
from huawei_manager.sdn_controller.event_queue import EventType
from huawei_manager.sdn_controller.napalm_backend import (
    BACKEND_ENV,
    BACKEND_NAPALM,
    BACKEND_NETMIKO,
    ApplyResult,
)
from huawei_manager.services import ServiceDef
from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.services.handlers import ServicesHandlers
from huawei_manager.tabs.services.state import ServicesState


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


def _make(**overrides) -> tuple[ServicesHandlers, ServicesState, TabContext]:
    """(handlers, state, ctx) — modo cli síncrono por padrão (paridade legado)."""
    device = MagicMock()
    drv = overrides.pop("drv", MagicMock())
    fields: dict = dict(
        sb=MagicMock(),
        audit=None,
        event_bus=MagicMock(),
        role=lambda: "admin",
        device=lambda: None,
        dispatch=lambda fn: fn() if callable(fn) else None,
        require_access=lambda level: True,
        spawn_io=lambda fn, *a: fn(*a),
        spawn_cpu=lambda fn, *a: fn(*a),
        watcher=MagicMock(),
        is_mock=lambda: False,
        toggle_mock=lambda: False,
        show_auth_dialog=lambda: None,
        watcher_results=lambda: None,
        set_watcher_results=MagicMock(),
        session=None,
        run=MagicMock(),
        set_status=MagicMock(),
        touch_session=MagicMock(),
        cmd_validator=None,
        dry_run=None,
        get_last_config_command=MagicMock(return_value=None),
        set_last_config_command=MagicMock(),
        drv=lambda: drv,
        devices=lambda: [],
        show_page=MagicMock(),
        svc_mode=lambda: "cli",
        ui_bridge=lambda: None,
        ensure_device_ready=MagicMock(return_value=device),
    )
    fields.update(overrides)
    ctx = TabContext(**fields)
    state = ServicesState()
    state.output = MagicMock()
    state.device_lbl = MagicMock()
    return ServicesHandlers(ctx, state), state, ctx


def _run(h: ServicesHandlers, svc: ServiceDef) -> None:
    """Roda ``run_service`` de forma síncrona (spawn executa ``_do`` na hora)."""
    h.run_service(svc)


def _writes(st: ServicesState) -> list[str]:
    """Textos escritos no output (setPlainText + append via _ui.write/_loading)."""
    out = st.output
    parts = [str(c.args[0]) for c in out.setPlainText.call_args_list
             if c.args]
    parts += [str(c.args[0]) for c in out.append.call_args_list if c.args]
    return parts


def _fake_executor(monkeypatch, *, diff: str = "- old\n+ new"):
    """Substitui ``NapalmVRPBackend`` no namespace do handler e devolve mocks."""
    executor = MagicMock()
    executor.preview.return_value = diff
    executor.apply.return_value = ApplyResult(
        snapshot="snap pré", output="cfg ok", duration_ms=5.0)
    cls = MagicMock(return_value=executor)
    monkeypatch.setattr("huawei_manager.tabs.services.handlers.NapalmVRPBackend",
                        cls)
    return executor, cls


def _backend(monkeypatch, backend: str = BACKEND_NAPALM,
             warning: str = "") -> None:
    monkeypatch.setattr(
        "huawei_manager.tabs.services.handlers.resolve_backend",
        lambda: (backend, warning),
    )


# ══════════════════════════════════════════════════════════════════════
#  1) backend Netmiko: caminho atual intacto, zero NAPALM
# ══════════════════════════════════════════════════════════════════════
def test_netmiko_padrao_nao_toca_napalm(monkeypatch) -> None:
    monkeypatch.delenv(BACKEND_ENV, raising=False)
    _backend(monkeypatch, BACKEND_NETMIKO)
    napalm_cls = MagicMock()
    monkeypatch.setattr("huawei_manager.tabs.services.handlers.NapalmVRPBackend",
                        napalm_cls)
    h, st, ctx = _make()
    svc = _make_svc()

    _run(h, svc)

    ctx.sb.send_service_commands.assert_called_once_with(
        svc.cli_commands, config_mode=True, requires_privilege=False)
    napalm_cls.assert_not_called()          # nenhuma chamada NAPALM
    ev = ctx.event_bus.put.call_args[0][0]
    assert ev.type is EventType.COMMAND_EXECUTED
    assert ev.payload.data == {"mode": "cli"}  # payload original, sem backend


# ══════════════════════════════════════════════════════════════════════
#  1b) snapshot pré-mudança do caminho Netmiko (Command pattern)
# ══════════════════════════════════════════════════════════════════════
def test_netmiko_config_takes_snapshot_before_apply(monkeypatch) -> None:
    monkeypatch.delenv(BACKEND_ENV, raising=False)
    _backend(monkeypatch, BACKEND_NETMIKO)
    h, st, ctx = _make()
    ctx.sb.send_command.return_value = "baseline cfg"
    svc = _make_svc()

    _run(h, svc)

    ctx.sb.send_command.assert_called_once_with(
        "display current-configuration")
    ctx.sb.send_service_commands.assert_called_once_with(
        svc.cli_commands, config_mode=True, requires_privilege=False)
    command = ctx.set_last_config_command.call_args[0][0]
    assert command.snapshot == "baseline cfg"  # rollback disponível


def test_netmiko_config_snapshot_failure_is_fail_closed(monkeypatch) -> None:
    monkeypatch.delenv(BACKEND_ENV, raising=False)
    _backend(monkeypatch, BACKEND_NETMIKO)
    h, st, ctx = _make()
    ctx.sb.send_command.side_effect = SdnError("conexão caiu")
    svc = _make_svc()

    _run(h, svc)

    # fail-closed: sem snapshot nada foi aplicado e não há o que desfazer
    ctx.sb.send_service_commands.assert_not_called()
    assert any("nada foi aplicado" in t for t in _writes(st))
    ctx.set_last_config_command.assert_not_called()


# ══════════════════════════════════════════════════════════════════════
#  2) napalm + diff → usuário aceita → apply com os comandos certos
# ══════════════════════════════════════════════════════════════════════
def test_napalm_diff_confirmado_aplica_comandos(monkeypatch) -> None:
    _backend(monkeypatch)
    executor, cls = _fake_executor(monkeypatch, diff="- old\n+ new")
    bridge = FakeBridge(answer=True)
    h, st, ctx = _make(ui_bridge=lambda: bridge)
    svc = _make_svc()

    _run(h, svc)

    cls.assert_called_once()
    executor.preview.assert_called_once_with(svc.cli_commands)
    executor.apply.assert_called_once_with(svc.cli_commands)
    # o diálogo recebeu exatamente a diff proposta
    assert len(bridge.payloads) == 1
    assert bridge.payloads[0]["message"] == "- old\n+ new"
    # o caminho Netmiko NÃO foi usado
    ctx.sb.send_service_commands.assert_not_called()
    # output do apply visível + evento COMMAND_EXECUTED com backend napalm
    assert any("cfg ok" in t for t in _writes(st))
    ev = ctx.event_bus.put.call_args[0][0]
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
    h, st, ctx = _make(ui_bridge=lambda: bridge, audit=audit)
    svc = _make_svc()

    _run(h, svc)

    executor.apply.assert_not_called()
    ctx.sb.send_service_commands.assert_not_called()
    assert any("Cancelado" in t for t in _writes(st))
    assert any(e["status"] == "blocked" for e in audit.entries)


# ══════════════════════════════════════════════════════════════════════
#  4) preview falha → fail-closed: audit blocked, sem fallback Netmiko
# ══════════════════════════════════════════════════════════════════════
def test_napalm_preview_falha_fail_closed(monkeypatch) -> None:
    _backend(monkeypatch)
    executor, _cls = _fake_executor(monkeypatch)
    executor.preview.side_effect = RuntimeError("driver boom")
    audit = FakeAudit()
    h, st, ctx = _make(audit=audit)
    svc = _make_svc()

    _run(h, svc)

    executor.apply.assert_not_called()
    # recusa explícita: NUNCA fallback silencioso para Netmiko
    ctx.sb.send_service_commands.assert_not_called()
    assert any("preview" in t.lower() and "\u2718" in t for t in _writes(st))
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
    h, st, ctx = _make(ui_bridge=lambda: bridge)
    svc = _make_svc()

    _run(h, svc)

    executor.apply.assert_not_called()
    ctx.sb.send_service_commands.assert_not_called()
    assert bridge.payloads == []            # nenhum diálogo para diff vazio
    assert any("Sem mudancas a aplicar" in t for t in _writes(st))


# ══════════════════════════════════════════════════════════════════════
#  6) bridge indisponível (None) → aplica sem confirmação
# ══════════════════════════════════════════════════════════════════════
def test_napalm_sem_bridge_aplica_sem_confirmacao(monkeypatch) -> None:
    _backend(monkeypatch)
    executor, _cls = _fake_executor(monkeypatch)
    h, st, ctx = _make(ui_bridge=lambda: None)   # app sem GUI / headless
    svc = _make_svc()

    _run(h, svc)

    executor.preview.assert_called_once()
    executor.apply.assert_called_once_with(svc.cli_commands)
    ctx.sb.send_service_commands.assert_not_called()
    assert any("cfg ok" in t for t in _writes(st))


# ══════════════════════════════════════════════════════════════════════
#  7) config_mode=False (leitura) → nunca toca NAPALM
# ══════════════════════════════════════════════════════════════════════
def test_servico_leitura_ignora_napalm(monkeypatch) -> None:
    _backend(monkeypatch, BACKEND_NAPALM)
    napalm_cls = MagicMock()
    monkeypatch.setattr("huawei_manager.tabs.services.handlers.NapalmVRPBackend",
                        napalm_cls)
    h, st, ctx = _make()
    svc = _make_svc(config_mode=False)

    _run(h, svc)

    napalm_cls.assert_not_called()
    ctx.sb.send_service_commands.assert_called_once_with(
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
