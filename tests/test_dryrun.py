"""Tests for DryRunEngine — diff generation, dry-run, apply, rollback."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from huawei_manager.sdn_controller.dryrun import DryRunEngine

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def engine() -> DryRunEngine:
    return DryRunEngine()


CONFIG_ORIGINAL = """#
sysname R1
#
interface GigabitEthernet0/0/0
 ip address 10.0.0.1 255.255.255.0
#
interface GigabitEthernet0/0/1
 ip address 10.0.1.1 255.255.255.0
#
ospf 1
 area 0.0.0.0
  network 10.0.0.0 0.0.0.255
"""

CONFIG_MODIFIED = """#
sysname R1
#
interface GigabitEthernet0/0/0
 ip address 10.0.0.1 255.255.255.0
#
interface GigabitEthernet0/0/1
 ip address 192.168.1.1 255.255.255.0
#
ospf 1
 area 0.0.0.0
  network 10.0.0.0 0.0.0.255
  network 192.168.1.0 0.0.0.255
#"""


# ── Diff generation ──────────────────────────────────────────────────────────


class TestDiffGeneration:
    """DryRunEngine must generate accurate diffs."""

    def test_no_changes(self, engine: DryRunEngine):
        report = engine.diff(CONFIG_ORIGINAL, CONFIG_ORIGINAL)
        assert report.has_changes is False
        assert len(report.added) == 0
        assert len(report.removed) == 0

    def test_add_line_detected(self, engine: DryRunEngine):
        report = engine.diff(CONFIG_ORIGINAL, CONFIG_MODIFIED)
        assert report.has_changes is True
        assert any("network 192.168.1.0" in line for line in report.added)

    def test_remove_line_detected(self, engine: DryRunEngine):
        report = engine.diff(CONFIG_ORIGINAL, CONFIG_MODIFIED)
        assert report.has_changes is True
        assert any("10.0.1.1" in line for line in report.removed)

    def test_diff_summary_format(self, engine: DryRunEngine):
        report = engine.diff(CONFIG_ORIGINAL, CONFIG_MODIFIED)
        assert report.total_added > 0
        assert report.total_removed > 0
        assert isinstance(report.summary, str)
        assert len(report.summary) > 0

    def test_diff_includes_context(self, engine: DryRunEngine):
        """Diff should include surrounding context lines."""
        report = engine.diff(CONFIG_ORIGINAL, CONFIG_MODIFIED)
        assert report.context_lines is not None


# ── Dry-run execution ────────────────────────────────────────────────────────


class TestDryRunExecution:
    """dry_run simulates command execution without side effects."""

    def test_dry_run_captures_output(self, engine: DryRunEngine):
        fn = MagicMock(return_value="config output\nline2")
        report = engine.dry_run(fn, CONFIG_ORIGINAL, CONFIG_MODIFIED)
        assert report.has_changes is True
        # fn should NOT have been called (simulation mode)
        fn.assert_not_called()

    def test_dry_run_no_changes(self, engine: DryRunEngine):
        fn = MagicMock(return_value="output")
        report = engine.dry_run(fn, CONFIG_ORIGINAL, CONFIG_ORIGINAL)
        assert report.has_changes is False
        fn.assert_not_called()

    def test_dry_run_returns_report(self, engine: DryRunEngine):
        fn = MagicMock(return_value="output")
        report = engine.dry_run(fn, CONFIG_ORIGINAL, CONFIG_MODIFIED)
        assert hasattr(report, "has_changes")
        assert hasattr(report, "added")
        assert hasattr(report, "removed")
        assert hasattr(report, "summary")


# ── Apply ────────────────────────────────────────────────────────────────────


class TestApply:
    """apply executes the proposed config and returns result."""

    def test_apply_executes_fn(self, engine: DryRunEngine):
        fn = MagicMock(return_value="config applied")
        result = engine.apply(fn, CONFIG_MODIFIED)
        fn.assert_called_once()
        assert result.success is True
        assert result.output == "config applied"

    def test_apply_with_original_creates_rollback(self, engine: DryRunEngine):
        fn = MagicMock(return_value="applied")
        result = engine.apply(fn, CONFIG_MODIFIED, original=CONFIG_ORIGINAL)
        assert result.success is True
        assert result.rollback_command is not None

    def test_apply_failure_reported(self, engine: DryRunEngine):
        fn = MagicMock(side_effect=RuntimeError("SSH failed"))
        result = engine.apply(fn, CONFIG_MODIFIED)
        assert result.success is False
        assert "SSH failed" in (result.error or "")


# ── Rollback ─────────────────────────────────────────────────────────────────


class TestRollback:
    """rollback restores the original config."""

    def test_rollback_executes_with_original(self, engine: DryRunEngine):
        fn = MagicMock(return_value="rollback ok")
        result = engine.rollback(fn, CONFIG_ORIGINAL)
        fn.assert_called_once()
        assert result.success is True

    def test_rollback_failure_reported(self, engine: DryRunEngine):
        fn = MagicMock(side_effect=RuntimeError("rollback failed"))
        result = engine.rollback(fn, CONFIG_ORIGINAL)
        assert result.success is False
        assert "rollback" in (result.error or "").lower()

    def test_rollback_from_apply_result(self, engine: DryRunEngine):
        """Rollback using the command stored in ApplyResult."""
        apply_fn = MagicMock(return_value="applied")
        apply_result = engine.apply(
            apply_fn, CONFIG_MODIFIED, original=CONFIG_ORIGINAL,
        )
        assert apply_result.rollback_command is not None

        rollback_fn = MagicMock(return_value="rollback ok")
        rollback_result = engine.rollback(
            rollback_fn, apply_result.rollback_command,
        )
        assert rollback_result.success is True
        rollback_fn.assert_called_once()


# ── ApplyResult dataclass ────────────────────────────────────────────────────


class TestApplyResult:
    """ApplyResult dataclass fields."""

    def test_defaults(self):
        from huawei_manager.sdn_controller.dryrun import ApplyResult

        r = ApplyResult(success=True, output="ok")
        assert r.success is True
        assert r.output == "ok"
        assert r.error is None
        assert r.rollback_command is None

    def test_failure(self):
        from huawei_manager.sdn_controller.dryrun import ApplyResult

        r = ApplyResult(success=False, output="", error="timeout")
        assert r.success is False
        assert r.error == "timeout"


# ── DiffReport dataclass ─────────────────────────────────────────────────────


class TestDiffReport:
    """DiffReport dataclass fields."""

    def test_no_changes_default(self):
        from huawei_manager.sdn_controller.dryrun import DiffReport

        r = DiffReport()
        assert r.has_changes is False
        assert r.added == []
        assert r.removed == []
        assert r.total_added == 0
        assert r.total_removed == 0

    def test_with_changes(self):
        from huawei_manager.sdn_controller.dryrun import DiffReport

        r = DiffReport(
            has_changes=True,
            added=["+ network 10.0.0.0"],
            removed=["- network 192.168.0.0"],
        )
        assert r.has_changes is True
        assert r.total_added == 1
        assert r.total_removed == 1
        assert "1 added" in r.summary
        assert "1 removed" in r.summary
