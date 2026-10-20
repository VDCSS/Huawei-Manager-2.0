"""Testes do Command pattern — snapshot fail-closed e rollback honesto.

Cobrem o contrato de ``huawei_manager.command``: mutação só acontece
com snapshot pré-mudança; rollback restaura o restaurável e reporta
parcialidade (status ``partial``) sem nunca mentir sobre o resultado.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from huawei_manager.command import ConfigCommand, audit_config_op
from huawei_manager.exceptions import SdnError, SnapshotError

SNAP = "hostname R1\nntp server 1.1.1.1\n"
CHANGED = "hostname R1\n"  # perdeu o ntp server
EXTRA = "hostname R1\nntp server 1.1.1.1\ninterface GigabitEthernet0/0/1\n"


def _make_cmd(
    states: list[str | Exception],
    *,
    apply_ok: bool = True,
    apply_msg: str = "ok",
    apply_side_effect: Exception | None = None,
) -> tuple[ConfigCommand, MagicMock, list[list[str]]]:
    """Monta ConfigCommand com leitura sequencial e apply espião.

    ``states`` aceita exceções misturadas: itens ``Exception`` são
    levantados na chamada correspondente (semântica do MagicMock).
    """
    read = MagicMock(side_effect=list(states))

    applied: list[list[str]] = []

    def _apply(lines: list[str]) -> tuple[bool, str]:
        if apply_side_effect is not None:
            raise apply_side_effect
        applied.append(list(lines))
        return apply_ok, apply_msg

    cmd = ConfigCommand(
        ["ntp server 1.1.1.1"],
        read_state=read,
        apply_fn=_apply,
    )
    return cmd, read, applied


class TestExecute:
    """execute(): snapshot fail-closed + aplicação."""

    def test_captures_snapshot_and_applies(self):
        cmd, read, applied = _make_cmd([SNAP])
        result = cmd.execute()
        assert result.ok is True
        assert result.status == "ok"
        assert result.message == "ok"
        assert cmd.snapshot == SNAP
        assert applied == [["ntp server 1.1.1.1"]]

    def test_snapshot_failure_is_fail_closed(self):
        cmd, _read, applied = _make_cmd([SdnError("sessão caiu")])
        with pytest.raises(SnapshotError):
            cmd.execute()
        assert applied == []          # nada foi aplicado
        assert cmd.snapshot is None   # sem snapshot não há rollback

    def test_snapshot_generic_failure_wrapped(self):
        cmd, _read, applied = _make_cmd([ValueError("estado inválido")])
        with pytest.raises(SnapshotError):
            cmd.execute()
        assert applied == []

    def test_apply_failure_propagates_sdn_error_not_snapshot(self):
        cmd, _read, _applied = _make_cmd(
            [SNAP], apply_side_effect=SdnError("ssh morreu"))
        with pytest.raises(SdnError) as excinfo:
            cmd.execute()
        # SnapshotError É SdnError — a aplicação deve propagar o erro
        # original (não o de snapshot) para o chamador tratar distinto.
        assert type(excinfo.value) is SdnError
        assert cmd.snapshot == SNAP   # snapshot ficou válido p/ rollback

    def test_apply_refused_returns_error_result(self):
        cmd, _read, _applied = _make_cmd(
            [SNAP], apply_ok=False, apply_msg="recusado")
        result = cmd.execute()
        assert result.ok is False
        assert result.status == "error"
        assert result.message == "recusado"
        assert cmd.snapshot == SNAP


class TestRollback:
    """rollback(): restaura o restaurável e reporta pendências."""

    def test_without_snapshot_is_blocked(self):
        cmd, read, applied = _make_cmd([])
        result = cmd.rollback()
        assert result.ok is False
        assert result.status == "blocked"
        read.assert_not_called()      # nem tenta sem snapshot
        assert applied == []

    def test_restores_missing_lines_without_diff_headers(self):
        # execute lê SNAP; rollback lê CHANGED (atual) e SNAP (verificação)
        cmd, _read, applied = _make_cmd([SNAP, CHANGED, SNAP])
        cmd.execute()
        result = cmd.rollback()
        assert result.ok is True
        assert result.status == "ok"
        assert result.restored == 1
        assert result.pending == 0
        # restaurou exatamente a linha que faltava…
        assert applied[-1] == ["ntp server 1.1.1.1"]
        # …e NUNCA os cabeçalhos do unified_diff (+++/---)
        for line in applied[-1]:
            assert not line.startswith("++")
            assert not line.startswith("--")

    def test_partial_when_lines_require_manual_undo(self):
        # snapshot ≠ atual apenas por LINHA EXTRA — não há como remover
        # via send_config: parcialidade honesta, sem apply de rollback.
        cmd, _read, applied = _make_cmd([SNAP, EXTRA, EXTRA])
        cmd.execute()
        result = cmd.rollback()
        assert result.ok is False
        assert result.status == "partial"
        assert result.restored == 0
        assert result.pending == 1     # a linha "interface ..." extra
        assert "undo manual" in result.message
        assert len(applied) == 1       # só a mutação original, sem rollback

    def test_no_changes_reports_original_state(self):
        cmd, _read, applied = _make_cmd([SNAP, SNAP])
        cmd.execute()
        result = cmd.rollback()
        assert result.ok is True
        assert result.status == "ok"
        assert "estado original" in result.message
        assert len(applied) == 1       # nada para restaurar

    def test_apply_refused_reports_error_with_pending(self):
        cmd, read, _applied = _make_cmd(
            [SNAP, CHANGED, CHANGED], apply_ok=False, apply_msg="negado")
        cmd.execute()
        result = cmd.rollback()
        assert result.ok is False
        assert result.status == "error"
        assert "negado" in result.message
        assert result.pending == 1     # ntp server ainda ausente
        assert read.call_count == 3    # snapshot + atual + verificação

    def test_read_failure_propagates_sdn_error(self):
        cmd, _read, _applied = _make_cmd([SNAP, SdnError("caiu")])
        cmd.execute()
        with pytest.raises(SdnError):
            cmd.rollback()


class TestAuditConfigOp:
    """audit_config_op: schema preservado, auditoria nunca derruba."""

    def test_none_audit_is_noop(self):
        audit_config_op(None, op="config_apply", user="u", host="h",
                        status="ok")

    def test_preserves_canonical_schema(self):
        mock_audit = MagicMock()
        audit_config_op(
            mock_audit,
            op="config_apply",
            user="admin",
            host="10.0.0.1",
            status="partial",
            duration_ms=12.5,
            session_id="s-1",
            restored=2,
            pending=1,
        )
        kwargs = mock_audit.log_operation.call_args.kwargs
        assert mock_audit.log_operation.call_args.args == ("config_apply",)
        assert kwargs["user"] == "admin"
        assert kwargs["host"] == "10.0.0.1"
        assert kwargs["status"] == "partial"
        assert kwargs["duration_ms"] == 12.5
        assert kwargs["session_id"] == "s-1"
        assert kwargs["category"] == "config"
        assert kwargs["restored"] == 2
        assert kwargs["pending"] == 1

    def test_swallows_audit_failure(self):
        mock_audit = MagicMock()
        mock_audit.log_operation.side_effect = RuntimeError("disco cheio")
        audit_config_op(mock_audit, op="config_apply", user="u",
                        host="h", status="ok")  # não levanta
