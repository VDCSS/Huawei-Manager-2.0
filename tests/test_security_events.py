"""Tests for SecurityTimeline — event categories, filters, severity."""
from __future__ import annotations

from datetime import datetime, timedelta, UTC

import pytest

from huawei_manager.sdn_controller._dormant.security_events import (
    SecurityEvent,
    SecurityTimeline,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def timeline() -> SecurityTimeline:
    return SecurityTimeline()


@pytest.fixture
def sample_events() -> list[SecurityEvent]:
    now = datetime.now(UTC)
    return [
        SecurityEvent(
            timestamp=now - timedelta(hours=2),
            category="auth",
            severity="critical",
            device="R1",
            operator="unknown",
            description="Failed login attempt from 10.0.0.99",
        ),
        SecurityEvent(
            timestamp=now - timedelta(hours=1),
            category="config",
            severity="high",
            device="R1",
            operator="admin01",
            description="Running-config changed by admin01",
        ),
        SecurityEvent(
            timestamp=now - timedelta(minutes=30),
            category="auth",
            severity="medium",
            device="SW1",
            operator="tecnico01",
            description="SSH session timeout",
        ),
        SecurityEvent(
            timestamp=now - timedelta(minutes=10),
            category="policy",
            severity="low",
            device="R2",
            operator="admin01",
            description="Policy violation on interface GE0/0/0",
        ),
        SecurityEvent(
            timestamp=now,
            category="system",
            severity="info",
            device="FW1",
            operator="system",
            description="System backup completed",
        ),
    ]


# ── SecurityEvent dataclass ──────────────────────────────────────────────────


class TestSecurityEvent:
    """SecurityEvent must store event data."""

    def test_create_event(self):
        ts = datetime.now(UTC)
        ev = SecurityEvent(
            timestamp=ts,
            category="auth",
            severity="critical",
            device="R1",
            operator="admin",
            description="Test event",
        )
        assert ev.category == "auth"
        assert ev.severity == "critical"
        assert ev.device == "R1"

    def test_event_defaults(self):
        ts = datetime.now(UTC)
        ev = SecurityEvent(
            timestamp=ts,
            category="auth",
            severity="medium",
            device="R1",
            operator="admin",
            description="Test",
        )
        assert ev.id is not None
        assert ev.acknowledged is False


# ── Add events ───────────────────────────────────────────────────────────────


class TestAddEvents:
    """Timeline must accept and store events."""

    def test_add_event(self, timeline: SecurityTimeline, sample_events):
        timeline.add_event(sample_events[0])
        assert len(timeline.get_events()) == 1

    def test_add_multiple_events(self, timeline: SecurityTimeline, sample_events):
        for ev in sample_events:
            timeline.add_event(ev)
        assert len(timeline.get_events()) == 5


# ── Ordering ─────────────────────────────────────────────────────────────────


class TestOrdering:
    """Events must be sorted newest-first."""

    def test_events_sorted_newest_first(self, timeline: SecurityTimeline, sample_events):
        for ev in sample_events:
            timeline.add_event(ev)
        events = timeline.get_events()
        assert events[0].severity == "info"  # newest
        assert events[-1].severity == "critical"  # oldest

    def test_reverse_chronological(self, timeline: SecurityTimeline, sample_events):
        for ev in reversed(sample_events):
            timeline.add_event(ev)
        events = timeline.get_events()
        assert events[0].description == "System backup completed"  # newest


# ── Category filter ──────────────────────────────────────────────────────────


class TestCategoryFilter:
    """Timeline must filter events by category."""

    def test_filter_by_category(self, timeline: SecurityTimeline, sample_events):
        for ev in sample_events:
            timeline.add_event(ev)
        auth_events = timeline.get_events(category="auth")
        assert len(auth_events) == 2
        assert all(e.category == "auth" for e in auth_events)

    def test_filter_category_nonexistent(self, timeline: SecurityTimeline, sample_events):
        for ev in sample_events:
            timeline.add_event(ev)
        result = timeline.get_events(category="nonexistent")
        assert result == []

    def test_get_categories(self, timeline: SecurityTimeline, sample_events):
        for ev in sample_events:
            timeline.add_event(ev)
        cats = timeline.get_categories()
        assert "auth" in cats
        assert "config" in cats
        assert "policy" in cats
        assert "system" in cats


# ── Severity filter ──────────────────────────────────────────────────────────


class TestSeverityFilter:
    """Timeline must filter events by severity."""

    def test_filter_by_severity(self, timeline: SecurityTimeline, sample_events):
        for ev in sample_events:
            timeline.add_event(ev)
        critical = timeline.get_events(severity="critical")
        assert len(critical) == 1
        assert critical[0].severity == "critical"

    def test_filter_by_min_severity(self, timeline: SecurityTimeline, sample_events):
        for ev in sample_events:
            timeline.add_event(ev)
        # min_severity=high should include high and critical
        result = timeline.get_events(min_severity="high")
        assert len(result) >= 2
        for e in result:
            assert e.severity in ("high", "critical")

    def test_get_severities(self, timeline: SecurityTimeline, sample_events):
        for ev in sample_events:
            timeline.add_event(ev)
        sevs = timeline.get_severities()
        assert "critical" in sevs
        assert "high" in sevs
        assert "medium" in sevs
        assert "low" in sevs
        assert "info" in sevs


# ── Device and operator filters ──────────────────────────────────────────────


class TestDeviceOperatorFilter:
    """Timeline must filter by device and operator."""

    def test_filter_by_device(self, timeline: SecurityTimeline, sample_events):
        for ev in sample_events:
            timeline.add_event(ev)
        result = timeline.get_events(device="R1")
        assert len(result) == 2
        assert all(e.device == "R1" for e in result)

    def test_filter_by_operator(self, timeline: SecurityTimeline, sample_events):
        for ev in sample_events:
            timeline.add_event(ev)
        result = timeline.get_events(operator="admin01")
        assert len(result) == 2
        assert all(e.operator == "admin01" for e in result)


# ── Combined filters ─────────────────────────────────────────────────────────


class TestCombinedFilters:
    """Filters must compose correctly."""

    def test_category_and_device(self, timeline: SecurityTimeline, sample_events):
        for ev in sample_events:
            timeline.add_event(ev)
        result = timeline.get_events(category="auth", device="SW1")
        assert len(result) == 1
        assert result[0].device == "SW1"

    def test_severity_and_operator(self, timeline: SecurityTimeline, sample_events):
        for ev in sample_events:
            timeline.add_event(ev)
        result = timeline.get_events(min_severity="high", operator="admin01")
        assert len(result) == 1  # only config event


# ── Critical events ──────────────────────────────────────────────────────────


class TestCriticalEvents:
    """Critical events must be identifiable."""

    def test_critical_event_flag(self, timeline: SecurityTimeline, sample_events):
        for ev in sample_events:
            timeline.add_event(ev)
        critical = timeline.get_events(severity="critical")
        assert len(critical) == 1
        assert critical[0].is_critical is True

    def test_non_critical_not_flagged(self):
        ev = SecurityEvent(
            timestamp=datetime.now(UTC),
            category="info",
            severity="info",
            device="R1",
            operator="system",
            description="Log entry",
        )
        assert ev.is_critical is False


# ── Acknowledge ──────────────────────────────────────────────────────────────


class TestAcknowledge:
    """Events must support acknowledge/dismiss."""

    def test_acknowledge_event(self, timeline: SecurityTimeline, sample_events):
        for ev in sample_events:
            timeline.add_event(ev)
        ev_id = sample_events[0].id
        assert timeline.acknowledge(ev_id) is True
        ev = timeline.get_event(ev_id)
        assert ev is not None
        assert ev.acknowledged is True

    def test_acknowledge_nonexistent(self, timeline: SecurityTimeline):
        assert timeline.acknowledge("nonexistent") is False

    def test_unacknowledged_count(self, timeline: SecurityTimeline, sample_events):
        for ev in sample_events:
            timeline.add_event(ev)
        assert timeline.unacknowledged_count() == 5
        timeline.acknowledge(sample_events[0].id)
        assert timeline.unacknowledged_count() == 4


# ── Clear ────────────────────────────────────────────────────────────────────


class TestClear:
    """Timeline must support clearing events."""

    def test_clear_all(self, timeline: SecurityTimeline, sample_events):
        for ev in sample_events:
            timeline.add_event(ev)
        timeline.clear()
        assert len(timeline.get_events()) == 0
        assert timeline.unacknowledged_count() == 0


# ── Edge cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Handle edge cases gracefully."""

    def test_empty_timeline(self, timeline: SecurityTimeline):
        assert timeline.get_events() == []
        assert timeline.get_categories() == []
        assert timeline.get_severities() == []
        assert timeline.unacknowledged_count() == 0

    def test_duplicate_id(self, timeline: SecurityTimeline):
        """Adding event with same ID twice should overwrite."""
        ev = SecurityEvent(
            timestamp=datetime.now(UTC),
            category="auth",
            severity="low",
            device="R1",
            operator="test",
            description="First",
            event_id="dup",
        )
        timeline.add_event(ev)
        ev2 = SecurityEvent(
            timestamp=datetime.now(UTC),
            category="auth",
            severity="critical",
            device="R1",
            operator="test",
            description="Second",
            event_id="dup",
        )
        timeline.add_event(ev2)
        events = timeline.get_events()
        assert len(events) == 1
        assert events[0].description == "Second"
