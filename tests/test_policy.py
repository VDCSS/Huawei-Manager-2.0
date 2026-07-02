"""Tests for PolicyEngine — condition-action rules with JSON persistence."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from huawei_manager.sdn_controller.policy import PolicyEngine, PolicyRule

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def engine() -> PolicyEngine:
    return PolicyEngine()


@pytest.fixture
def always_true() -> MagicMock:
    return MagicMock(return_value=True)


@pytest.fixture
def always_false() -> MagicMock:
    return MagicMock(return_value=False)


@pytest.fixture
def sample_action() -> MagicMock:
    return MagicMock()


# ── Rule creation ────────────────────────────────────────────────────────────


class TestRuleCreation:
    """PolicyRule must store condition, action, and metadata."""

    def test_create_rule(self, always_true, sample_action):
        rule = PolicyRule(
            id="rule-1",
            name="Block high CPU",
            condition=always_true,
            action=sample_action,
            priority=10,
        )
        assert rule.id == "rule-1"
        assert rule.name == "Block high CPU"
        assert rule.priority == 10
        assert rule.enabled is True

    def test_rule_disabled_by_default(self, always_true, sample_action):
        rule = PolicyRule(
            id="r1", name="test",
            condition=always_true, action=sample_action,
            enabled=False,
        )
        assert rule.enabled is False

    def test_rule_string_repr(self, always_true, sample_action):
        rule = PolicyRule(
            id="r1", name="test",
            condition=always_true, action=sample_action,
        )
        s = str(rule)
        assert "r1" in s
        assert "test" in s


# ── Add / remove rules ───────────────────────────────────────────────────────


class TestAddRemove:
    """PolicyEngine must support adding and removing rules."""

    def test_add_rule(self, engine, always_true, sample_action):
        rule = PolicyRule("r1", "test", always_true, sample_action)
        engine.add_rule(rule)
        assert "r1" in engine.list_rules()

    def test_add_duplicate_id_raises(self, engine, always_true, sample_action):
        rule = PolicyRule("r1", "test", always_true, sample_action)
        engine.add_rule(rule)
        with pytest.raises(ValueError, match="already exists"):
            engine.add_rule(rule)

    def test_remove_rule(self, engine, always_true, sample_action):
        rule = PolicyRule("r1", "test", always_true, sample_action)
        engine.add_rule(rule)
        engine.remove_rule("r1")
        assert "r1" not in engine.list_rules()

    def test_remove_nonexistent_raises(self, engine):
        with pytest.raises(KeyError, match="not found"):
            engine.remove_rule("nonexistent")

    def test_list_rules_empty(self, engine):
        assert engine.list_rules() == []

    def test_list_rules_returns_ids(self, engine, always_true, sample_action):
        engine.add_rule(PolicyRule("r1", "t1", always_true, sample_action))
        engine.add_rule(PolicyRule("r2", "t2", always_true, sample_action))
        assert sorted(engine.list_rules()) == ["r1", "r2"]


# ── Evaluate rules ───────────────────────────────────────────────────────────


class TestEvaluate:
    """Engine must evaluate rules and execute matching actions."""

    def test_condition_true_executes_action(self, engine, always_true, sample_action):
        engine.add_rule(PolicyRule("r1", "test", always_true, sample_action))
        engine.evaluate()
        sample_action.assert_called_once()

    def test_condition_false_skips_action(self, engine, always_false, sample_action):
        engine.add_rule(PolicyRule("r1", "test", always_false, sample_action))
        engine.evaluate()
        sample_action.assert_not_called()

    def test_multiple_rules_all_true(self, engine, always_true, sample_action):
        a2 = MagicMock()
        engine.add_rule(PolicyRule("r1", "t1", always_true, sample_action))
        engine.add_rule(PolicyRule("r2", "t2", always_true, a2))
        engine.evaluate()
        sample_action.assert_called_once()
        a2.assert_called_once()

    def test_mixed_conditions(self, engine, always_true, always_false, sample_action):
        a2 = MagicMock()
        engine.add_rule(PolicyRule("r1", "t1", always_true, sample_action))
        engine.add_rule(PolicyRule("r2", "t2", always_false, a2))
        engine.evaluate()
        sample_action.assert_called_once()
        a2.assert_not_called()

    def test_disabled_rule_skipped(self, engine, always_true, sample_action):
        engine.add_rule(PolicyRule("r1", "test", always_true, sample_action, enabled=False))
        engine.evaluate()
        sample_action.assert_not_called()

    def test_evaluate_returns_results_list(self, engine, always_true, sample_action):
        engine.add_rule(PolicyRule("r1", "test", always_true, sample_action))
        results = engine.evaluate()
        assert len(results) == 1
        assert results[0]["rule_id"] == "r1"
        assert results[0]["triggered"] is True


# ── Priority ─────────────────────────────────────────────────────────────────


class TestPriority:
    """Rules must execute in priority order."""

    def test_higher_priority_executed_first(self, engine):
        execution_order: list[str] = []

        def make_action(rule_id: str):
            def action() -> None:
                execution_order.append(rule_id)
            return action

        engine.add_rule(PolicyRule(
            "r-low", "low", lambda: True, make_action("r-low"),
            priority=50,
        ))
        engine.add_rule(PolicyRule(
            "r-high", "high", lambda: True, make_action("r-high"),
            priority=10,
        ))
        engine.evaluate()
        assert execution_order == ["r-high", "r-low"]

    def test_equal_priority_maintains_insertion_order(self, engine):
        execution_order: list[str] = []

        def make_action(rule_id: str):
            def action() -> None:
                execution_order.append(rule_id)
            return action

        engine.add_rule(PolicyRule(
            "r1", "first", lambda: True, make_action("r1"),
            priority=10,
        ))
        engine.add_rule(PolicyRule(
            "r2", "second", lambda: True, make_action("r2"),
            priority=10,
        ))
        engine.evaluate()
        assert execution_order == ["r1", "r2"]


# ── Loop prevention ──────────────────────────────────────────────────────────


class TestLoopPrevention:
    """Engine must detect and prevent re-entrant evaluation loops."""

    def test_action_triggers_evaluate_raises(self, engine, always_true):
        """If an action calls evaluate(), the engine should raise."""
        action_called = False

        def recursive_action() -> None:
            nonlocal action_called
            action_called = True
            with pytest.raises(RuntimeError, match="re-entrant"):
                engine.evaluate()

        engine.add_rule(PolicyRule(
            "r1", "recursive", always_true, recursive_action,
        ))
        engine.evaluate()
        assert action_called is True

    def test_nested_evaluate_allowed_after_completion(self, engine, always_true):
        """After evaluate() completes, a new evaluate() should work."""
        a1 = MagicMock()
        engine.add_rule(PolicyRule("r1", "t1", always_true, a1))
        engine.evaluate()
        a1.assert_called_once()
        # Second evaluate must work
        a2 = MagicMock()
        engine.add_rule(PolicyRule("r2", "t2", always_true, a2))
        engine.evaluate()
        a2.assert_called_once()


# ── JSON persistence ─────────────────────────────────────────────────────────


class TestJSONPersistence:
    """Rules must be serializable to and from JSON."""

    def test_save_to_dict(self, engine, always_true, sample_action):
        engine.add_rule(PolicyRule("r1", "test", always_true, sample_action))
        data = engine.to_dict()
        assert "r1" in data
        assert data["r1"]["name"] == "test"

    def test_load_from_dict(self, engine, sample_action):
        data = {
            "r1": {
                "name": "test",
                "condition_type": "always",
                "action_type": "callback",
                "priority": 10,
                "enabled": True,
            }
        }
        engine.load_rules_from_dict(data, action_map={"callback": sample_action})
        assert "r1" in engine.list_rules()

    def test_save_to_json_file(self, engine, always_true, sample_action, tmp_path):
        path = tmp_path / "rules.json"
        engine.add_rule(PolicyRule("r1", "test", always_true, sample_action))
        engine.save_json(str(path))
        assert path.exists()
        assert path.read_text(encoding="utf-8") != ""

    def test_load_from_json_file(self, engine, sample_action, tmp_path):
        path = tmp_path / "rules.json"
        path.write_text(
            '{"r1": {"name": "test", "condition_type": "always",'
            '"action_type": "callback", "priority": 10, "enabled": true}}',
            encoding="utf-8",
        )
        engine.load_json(str(path), action_map={"callback": sample_action})
        assert "r1" in engine.list_rules()

    def test_load_nonexistent_file_raises(self, engine):
        with pytest.raises(FileNotFoundError):
            engine.load_json("/nonexistent/rules.json")


# ── Audit integration ────────────────────────────────────────────────────────


class TestAudit:
    """Engine should log rule evaluations via audit."""

    def test_triggered_rule_logged(self, engine, always_true, sample_action):
        mock_audit = MagicMock()
        engine.set_audit_logger(mock_audit)
        engine.add_rule(PolicyRule("r1", "test", always_true, sample_action))
        engine.evaluate()
        mock_audit.log_operation.assert_called_once()

    def test_not_triggered_not_logged(self, engine, always_false, sample_action):
        mock_audit = MagicMock()
        engine.set_audit_logger(mock_audit)
        engine.add_rule(PolicyRule("r1", "test", always_false, sample_action))
        engine.evaluate()
        mock_audit.log_operation.assert_not_called()


# ── Edge cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Handle edge cases gracefully."""

    def test_no_rules(self, engine):
        results = engine.evaluate()
        assert results == []

    def test_condition_returns_none_skipped(self, engine, sample_action):
        cond = MagicMock(return_value=None)
        engine.add_rule(PolicyRule("r1", "test", cond, sample_action))
        engine.evaluate()
        sample_action.assert_not_called()

    def test_action_raises_does_not_break_other_rules(self, engine, always_true):
        def failing_action() -> None:
            msg = "Action failed"
            raise RuntimeError(msg)

        a2 = MagicMock()
        engine.add_rule(PolicyRule("r1", "failing", always_true, failing_action))
        engine.add_rule(PolicyRule("r2", "working", always_true, a2))
        results = engine.evaluate()
        assert results[0]["error"] is not None
        a2.assert_called_once()

    def test_clear_rules(self, engine, always_true, sample_action):
        engine.add_rule(PolicyRule("r1", "test", always_true, sample_action))
        engine.clear_rules()
        assert engine.list_rules() == []
