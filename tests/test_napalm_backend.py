"""Testes do backend NAPALM opcional (flag HW_BACKEND)."""

from __future__ import annotations

from typing import Any

import pytest

from huawei_manager.exceptions import SdnCommandError
from huawei_manager.sdn_controller.napalm_backend import (
    BACKEND_ENV,
    BACKEND_NAPALM,
    BACKEND_NETMIKO,
    NapalmVRPBackend,
    backend_from_session,
    detect_vrp_errors,
    napalm_status,
    resolve_backend,
)


class FakeConn:
    """Conexão Netmiko falsa: registra chamadas e devolve respostas programadas."""

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.responses = responses or {}

    def send_command(
        self, command: str, expect_string: str | None = None,
        read_timeout: float | None = None, **kw: Any,
    ) -> str:
        self.calls.append((command, expect_string))
        return self.responses.get(command, f"{command} ok")

    @property
    def commands(self) -> list[str]:
        return [c for c, _ in self.calls]


class FakeAudit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def log_operation(self, op: str, **kw: Any) -> None:
        self.entries.append({"op": op, **kw})


class FakeDriver:
    def __init__(self, diff: str = "- old\n+ new", error: bool = False) -> None:
        self.diff = diff
        self.error = error
        self.loaded: str | None = None
        self.discarded = False

    def load_merge_candidate(self, filename: str | None = None,
                             config: str | None = None) -> None:
        self.loaded = config or ""

    def compare_config(self) -> str:
        if self.error:
            raise RuntimeError("boom")
        return self.diff

    def discard_config(self) -> None:
        self.discarded = True


# ── flag de feature ──────────────────────────────────────────────────
def test_resolve_backend_padrao_e_netmiko() -> None:
    backend, warning = resolve_backend({})
    assert backend == BACKEND_NETMIKO
    assert warning == ""


def test_resolve_backend_invalido_cai_para_netmiko_com_aviso() -> None:
    backend, warning = resolve_backend({BACKEND_ENV: "banana"})
    assert backend == BACKEND_NETMIKO
    assert "invalido" in warning


def test_resolve_backend_napalm_disponivel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "huawei_manager.sdn_controller.napalm_backend.napalm_status",
        lambda: (True, ""),
    )
    backend, warning = resolve_backend({BACKEND_ENV: BACKEND_NAPALM})
    assert backend == BACKEND_NAPALM
    assert warning == ""


def test_resolve_backend_napalm_ausente_degrada_fechado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sem o pacote o app segue no Netmiko — nunca levanta exceção."""
    monkeypatch.setattr(
        "huawei_manager.sdn_controller.napalm_backend.napalm_status",
        lambda: (False, "pacote indisponivel (x)"),
    )
    backend, warning = resolve_backend({BACKEND_ENV: BACKEND_NAPALM})
    assert backend == BACKEND_NETMIKO
    assert "napalm" in warning


# ── detecção de erro VRP (risco 3 do driver: substring 'error') ─────
def test_detect_vrp_errors_pega_erros_vrp() -> None:
    out = (
        "[Huawei] acl number 3000\n"
        "% Unrecognized command.\n"
        "% Wrong parameter found.\n"
        "% Incomplete command.\n"
    )
    assert len(detect_vrp_errors(out)) == 3


def test_detect_vrp_errors_nao_falso_positivo() -> None:
    out = (
        "interface GigabitEthernet0/0/1\n"
        "Info: The configuration takes effect.\n"
        "Configured successfully, errorless\n"
        "display version — Huawei Versatile Routing Platform Software\n"
    )
    assert detect_vrp_errors(out) == []


# ── aplicação (risco 1 = commit, risco 2 = save) ────────────────────
def test_apply_sequencia_prompt_driven_sem_save() -> None:
    conn = FakeConn()
    engine = NapalmVRPBackend(conn)
    cmds = ["acl number 3000", "rule 1 permit ip"]

    result = engine.apply(cmds)
    seq = conn.commands

    # 1) snapshot pré-mudança (leitura) ANTES de qualquer escrita
    assert seq[0] == "display current-configuration"
    # 2) entra no config mode e espera o prompt [view] em cada linha
    assert seq[1] == "system-view"
    assert conn.calls[1][1] == r"\[.+\]"
    assert seq[2:4] == cmds
    assert all(expect == r"\[.+\]" for _, expect in conn.calls[2:4])
    # 3) sai com return esperando o prompt de user view < ... >
    assert seq[-1] == "return"
    assert conn.calls[-1][1] == r"<.+>"
    # risco 2: o backend padrão NÃO grava na startup-config
    assert not any(c.split()[0] in {"save", "format", "delete"} for c in seq)
    # risco 1: `commit` só entra quando explicitamente habilitado
    assert "commit" not in seq
    assert result.snapshot == "display current-configuration ok"
    assert result.duration_ms >= 0.0


def test_apply_commit_exigindo_flag_explicita() -> None:
    conn = FakeConn()
    engine = NapalmVRPBackend(conn, commit=True)
    engine.apply(["interface GigabitEthernet0/0/1"])
    assert "commit" in conn.commands


def test_apply_rejeicao_descarta_e_levera_sdn_command_error() -> None:
    conn = FakeConn({"acl number 3000": "% Unrecognized command."})
    engine = NapalmVRPBackend(conn)

    with pytest.raises(SdnCommandError) as excinfo:
        engine.apply(["acl number 3000"])

    assert "Unrecognized" in str(excinfo.value)
    assert "alteracoes descartadas" in str(excinfo.value)
    # saiu do config mode mesmo com erro (rollback imediato)
    assert conn.commands[-1] == "return"
    assert "commit" not in conn.commands


def test_apply_aborta_no_primeiro_comando_rejeitado() -> None:
    """Fail-fast: comando rejeitado aborta o lote e descarta o que já entrou."""
    conn = FakeConn({"rule 1 permit ip": "% Wrong parameter found."})
    engine = NapalmVRPBackend(conn)

    with pytest.raises(SdnCommandError):
        engine.apply(["acl number 3000", "rule 1 permit ip", "rule 2 permit ip"])

    # o terceiro comando nunca chega ao dispositivo
    assert "rule 2 permit ip" not in conn.commands
    # e a sessão sai do config mode (descarte)
    assert conn.commands[-1] == "return"


def test_apply_sem_conexao_levanta_sdn_connection_error() -> None:
    from huawei_manager.exceptions import SdnConnectionError

    engine = NapalmVRPBackend(None)
    with pytest.raises(SdnConnectionError):
        engine.apply(["display current-configuration"])


# ── auditoria (schema preservado) ────────────────────────────────────
def test_apply_registra_auditoria_com_schema_completo() -> None:
    audit = FakeAudit()
    engine = NapalmVRPBackend(FakeConn(), user="op", host="10.0.0.1",
                               session_id="s-1", audit=audit)
    engine.apply(["interface GigabitEthernet0/0/1"])

    assert len(audit.entries) == 1
    entry = audit.entries[0]
    assert entry["op"] == "config_apply"
    assert entry["user"] == "op"
    assert entry["host"] == "10.0.0.1"
    assert entry["status"] == "ok"
    assert entry["session_id"] == "s-1"
    assert entry["category"] == "config"
    assert entry["backend"] == BACKEND_NAPALM
    assert isinstance(entry["duration_ms"], float)


def test_apply_auditoria_falha_nao_derruba_operacao() -> None:
    class BoomAudit:
        def log_operation(self, *a: Any, **kw: Any) -> None:
            raise RuntimeError("audit down")

    engine = NapalmVRPBackend(FakeConn(), audit=BoomAudit())
    assert engine.apply(["interface GigabitEthernet0/0/1"]).output


# ── dry-run / snapshot ───────────────────────────────────────────────
def test_preview_carrega_candidate_e_devolve_diff() -> None:
    engine = NapalmVRPBackend(FakeConn())
    driver = FakeDriver()
    engine._driver = driver  # injeção direta: nenhum SSH real nos testes

    diff = engine.preview(["acl number 3000", "rule 1 permit ip"])

    assert diff == "- old\n+ new"
    assert driver.loaded == "acl number 3000\nrule 1 permit ip"
    assert not driver.discarded


def test_preview_erro_descarta_candidate() -> None:
    engine = NapalmVRPBackend(FakeConn())
    driver = FakeDriver(error=True)
    engine._driver = driver

    with pytest.raises(RuntimeError):
        engine.preview(["acl number 3000"])

    assert driver.discarded


def test_discard_sem_driver_e_noop() -> None:
    NapalmVRPBackend(FakeConn()).discard()  # não levanta


# ── fabricação do executor ───────────────────────────────────────────
def test_backend_from_session_padrao_sem_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(BACKEND_ENV, raising=False)
    backend, warning, executor = backend_from_session(object())
    assert backend == BACKEND_NETMIKO
    assert warning == ""
    assert executor is None


def test_backend_from_session_napalm_sem_pacote_degrada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(BACKEND_ENV, BACKEND_NAPALM)
    monkeypatch.setattr(
        "huawei_manager.sdn_controller.napalm_backend.napalm_status",
        lambda: (False, "faltando"),
    )
    backend, warning, executor = backend_from_session(object())
    assert backend == BACKEND_NETMIKO
    assert "faltando" in warning
    assert executor is None


def test_backend_from_session_napalm_retorna_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(BACKEND_ENV, BACKEND_NAPALM)
    ok, reason = napalm_status()
    if not ok:
        pytest.skip(f"napalm nao instalado: {reason}")
    backend, warning, executor = backend_from_session(FakeConn(), user="op")
    assert backend == BACKEND_NAPALM
    assert executor is not None
    assert callable(executor)
    assert warning == ""
