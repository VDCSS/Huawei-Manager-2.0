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
