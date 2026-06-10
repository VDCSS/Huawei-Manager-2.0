import json

import pytest

from huawei_manager.audit_log import AUDIT_FILE, AuditLogger


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
