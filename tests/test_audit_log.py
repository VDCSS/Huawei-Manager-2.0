import hashlib
import json

import pytest

from huawei_manager.audit_log import (
    AN_ACTION,
    AUDIT_FILE,
    AUTH_FAILURE,
    AUTH_SUCCESS,
    CMD_BLOCKED,
    CMD_EXECUTED,
    CONFIG_CHANGE,
    DEVICE_ADD,
    DEVICE_DELETE,
    DRIFT_DETECTED,
    AuditLogger,
)


class TestInit:
    def test_default_filename(self):
        logger = AuditLogger()
        assert str(logger._path) == AUDIT_FILE

    def test_custom_filename(self, tmp_audit_path):
        logger = AuditLogger(str(tmp_audit_path))
        assert logger._path == tmp_audit_path


class TestWrite:
    def test_writes_json_line(self, audit_logger):
        from huawei_manager.audit_log import AuditEntry
        entry = AuditEntry(
            timestamp="2026-01-01T00:00:00",
            op="test", user="u", host="h",
            datastore=None, status="ok",
            duration_ms=1.0, session_id=None,
        )
        audit_logger._write(entry)
        lines = audit_logger._path.read_text().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["op"] == "test"

    def test_writes_newline(self, audit_logger):
        from huawei_manager.audit_log import AuditEntry
        entry = AuditEntry(
            timestamp="2026-01-01T00:00:00",
            op="test", user="u", host="h",
            datastore=None, status="ok",
            duration_ms=1.0, session_id=None,
        )
        audit_logger._write(entry)
        raw = audit_logger._path.read_bytes()
        assert raw.endswith(b"\n")

    def test_creates_file_if_not_exists(self, tmp_audit_path):
        assert not tmp_audit_path.exists()
        logger = AuditLogger(str(tmp_audit_path))
        from huawei_manager.audit_log import AuditEntry
        entry = AuditEntry(
            timestamp="2026-01-01T00:00:00",
            op="test", user="u", host="h",
            datastore=None, status="ok",
            duration_ms=1.0, session_id=None,
        )
        logger._write(entry)
        assert tmp_audit_path.exists()


class TestLogOperation:
    def test_logs_required_fields(self, audit_logger):
        audit_logger.log_operation("op123", "user1", "host1")
        entries = audit_logger.tail(1)
        assert entries[0]["op"] == "op123"
        assert entries[0]["user"] == "user1"
        assert entries[0]["host"] == "host1"

    def test_extra_included(self, audit_logger):
        audit_logger.log_operation("op", "u", "h", extra_field="x")
        entries = audit_logger.tail(1)
        assert entries[0]["extra"]["extra_field"] == "x"

    def test_datastore_none(self, audit_logger):
        audit_logger.log_operation("op", "u", "h")
        entries = audit_logger.tail(1)
        assert entries[0]["datastore"] is None


class TestTimed:
    def test_success_records_ok(self, audit_logger):
        with audit_logger.timed("get", user="u", host="h"):
            pass
        entries = audit_logger.tail(1)
        assert entries[0]["status"] == "ok"
        assert entries[0]["duration_ms"] >= 0

    def test_custom_status(self, audit_logger):
        with audit_logger.timed("get", user="u", host="h") as ctx:
            ctx.set_status("timeout")
        entries = audit_logger.tail(1)
        assert entries[0]["status"] == "timeout"

    def test_exception_records_error_and_raises(self, audit_logger):
        with pytest.raises(ValueError):
            with audit_logger.timed("get", user="u", host="h"):
                raise ValueError("fail")
        entries = audit_logger.tail(1)
        assert entries[0]["status"] == "error"

    def test_finish_called_on_exception(self, audit_logger):
        with pytest.raises(RuntimeError):
            with audit_logger.timed("get", user="u", host="h"):
                raise RuntimeError("fail")
        entries = audit_logger.tail(1)
        assert len(entries) == 1


class TestTail:
    def test_no_file_returns_empty(self, tmp_audit_path):
        logger = AuditLogger(str(tmp_audit_path))
        assert logger.tail() == []

    def test_skips_malformed_lines(self, audit_logger):
        audit_logger._path.write_text("{invalid}\n{\"valid\": true}\n", encoding="utf-8")
        entries = audit_logger.tail(5)
        assert len(entries) == 1
        assert entries[0]["valid"] is True


class TestFormatTail:
    def test_no_entries_returns_message(self, audit_logger):
        result = audit_logger.format_tail()
        assert "nenhuma entrada" in result

    def test_formats_columns(self, audit_logger):
        audit_logger.log_operation("get-config", "admin", "10.0.0.1", status="ok")
        result = audit_logger.format_tail()
        assert "get-config" in result
        assert "ms" in result


class TestHashChain:
    """M09 — Hash chain SHA-256 para auditoria inviolavel."""

    def test_verify_chain_no_file(self, tmp_audit_path):
        """verify_chain retorna False se arquivo nao existe."""
        assert AuditLogger.verify_chain(str(tmp_audit_path)) is False

    def test_verify_chain_single_entry(self, audit_logger):
        """Cadeia com 1 entrada — sem hash anterior, valida."""
        audit_logger.log_operation("test", "u", "h")
        assert AuditLogger.verify_chain(str(audit_logger._path)) is True

    def test_verify_chain_multiple_ok(self, audit_logger):
        """3 entradas consecutivas formam cadeia valida."""
        for i in range(3):
            audit_logger.log_operation(f"op{i}", "u", "h")
        assert AuditLogger.verify_chain(str(audit_logger._path)) is True

    def test_verify_chain_tampered(self, audit_logger):
        """Modificar campo de uma entrada quebra a cadeia."""
        audit_logger.log_operation("op1", "u", "h")
        audit_logger.log_operation("op2", "u", "h")
        audit_logger.log_operation("op3", "u", "h")

        # Adultera o usuario da segunda entrada
        lines = audit_logger._path.read_text(encoding="utf-8").splitlines()
        entry2 = json.loads(lines[1])
        entry2["user"] = "attacker"
        lines[1] = json.dumps(entry2, ensure_ascii=False)
        audit_logger._path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        assert AuditLogger.verify_chain(str(audit_logger._path)) is False

    def test_verify_chain_tampered_hmac_ignored(self, audit_logger):
        """HMAC field nao participa do hash chain — alterar hmac nao quebra."""
        audit_logger.log_operation("op1", "u", "h")
        audit_logger.log_operation("op2", "u", "h")

        lines = audit_logger._path.read_text(encoding="utf-8").splitlines()
        entry1 = json.loads(lines[0])
        entry1["hmac"] = "0000deadbeef"
        lines[0] = json.dumps(entry1, ensure_ascii=False)
        audit_logger._path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Alterar HMAC nao deve quebrar a cadeia (hmac é excluido do hash)
        assert AuditLogger.verify_chain(str(audit_logger._path)) is True

    def test_first_entry_empty_previous_hash(self, audit_logger):
        """Primeira entrada tem previous_hash vazio (raiz da cadeia)."""
        audit_logger.log_operation("first", "u", "h")
        data = audit_logger.tail(1)[0]
        assert data["previous_hash"] == ""

    def test_entries_chain_correctly(self, audit_logger):
        """Cada entrada apos a primeira tem previous_hash = SHA-256 da anterior."""
        audit_logger.log_operation("a", "u", "h")
        audit_logger.log_operation("b", "u", "h")
        audit_logger.log_operation("c", "u", "h")

        lines = audit_logger._path.read_text(encoding="utf-8").splitlines()
        entries = [json.loads(line) for line in lines if line.strip()]

        # previous_hash da entrada 2 deve ser SHA-256 da entrada 1 (sem hmac)
        for i in range(1, len(entries)):
            prev = {k: v for k, v in entries[i - 1].items() if k != "hmac"}
            raw = json.dumps(prev, sort_keys=True, ensure_ascii=False)
            expected = hashlib.sha256(raw.encode()).hexdigest()
            assert entries[i]["previous_hash"] == expected

    def test_reopen_and_verify_chain(self, tmp_audit_path):
        """Escreve entradas, fecha logger, re-abre, verify_chain OK."""
        logger = AuditLogger(str(tmp_audit_path))
        logger.log_operation("op1", "u", "h")
        logger.log_operation("op2", "u", "h")
        del logger  # Fecha (descarta referência)

        logger2 = AuditLogger(str(tmp_audit_path))
        logger2.log_operation("op3", "u", "h")
        assert AuditLogger.verify_chain(str(tmp_audit_path)) is True


class TestCategories:
    """M09 — Categorias de eventos de segurança."""

    @pytest.mark.parametrize("cat", [
        AUTH_SUCCESS, AUTH_FAILURE, CMD_EXECUTED, CMD_BLOCKED,
        CONFIG_CHANGE, DEVICE_ADD, DEVICE_DELETE, DRIFT_DETECTED, AN_ACTION,
    ])
    def test_log_with_category(self, audit_logger, cat):
        """Cada categoria e armazenada corretamente."""
        audit_logger.log_operation("test", "u", "h", category=cat)
        data = audit_logger.tail(1)[0]
        assert data["category"] == cat

    def test_default_category(self, audit_logger):
        """Sem categoria explicita, usa 'general'."""
        audit_logger.log_operation("test", "u", "h")
        data = audit_logger.tail(1)[0]
        assert data["category"] == "general"

    def test_timed_with_category(self, audit_logger):
        """Context manager timed aceita e armazena category."""
        with audit_logger.timed("get", user="u", host="h", category=CONFIG_CHANGE):
            pass
        data = audit_logger.tail(1)[0]
        assert data["category"] == CONFIG_CHANGE
