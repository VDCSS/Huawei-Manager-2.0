"""Tests for ServiceOrchestrator — intent→CLI translation and execution."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from huawei_manager.sdn_controller.core import ControllerCore, DeviceState

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_controller() -> ControllerCore:
    ctrl = MagicMock(spec=ControllerCore)
    ctrl.get_state.side_effect = lambda dev_id: {
        "gw-01": DeviceState(
            device_id="gw-01", host="10.0.0.1", port=22,
            device_type="router", status="online",
        ),
        "sw-01": DeviceState(
            device_id="sw-01", host="10.0.0.2", port=22,
            device_type="switch", status="online",
        ),
        "offline-dev": DeviceState(
            device_id="offline-dev", host="10.0.0.3", port=22,
            device_type="router", status="offline",
        ),
    }.get(dev_id)
    ctrl.list_devices.return_value = ["gw-01", "sw-01", "offline-dev"]
    return ctrl


@pytest.fixture
def mock_executor() -> MagicMock:
    exec_fn = MagicMock()
    exec_fn.return_value = ("display ip routing-table\n...output...", "")
    return exec_fn


@pytest.fixture
def orchestrator(mock_controller, mock_executor):
    from huawei_manager.sdn_controller._dormant.orchestrator import ServiceOrchestrator

    return ServiceOrchestrator(
        controller=mock_controller,
        execute_fn=mock_executor,
    )


# ── lookup ───────────────────────────────────────────────────────────────────


class TestLookup:
    """Service lookup by ID."""

    def test_lookup_existing_service(self, orchestrator):
        svc = orchestrator.lookup("router-routing-table")
        assert svc is not None
        assert svc.id == "router-routing-table"
        assert "ROUTER" in svc.vnf_types

    def test_lookup_nonexistent_returns_none(self, orchestrator):
        assert orchestrator.lookup("nonexistent-service") is None


# ── resolve ──────────────────────────────────────────────────────────────────


class TestResolve:
    """Intent→CLI command resolution."""

    def test_resolve_simple_show(self, orchestrator):
        """Simple show command with no params."""
        commands = orchestrator.resolve(
            service_id="router-routing-table",
        )
        assert commands == ["display ip routing-table"]

    def test_resolve_with_params(self, orchestrator):
        """Resolve with parameter substitution."""
        commands = orchestrator.resolve(
            service_id="router-bgp-routes",
        )
        assert len(commands) >= 1

    def test_resolve_unknown_service_raises(self, orchestrator):
        with pytest.raises(ValueError, match="not found"):
            orchestrator.resolve(service_id="invalid-service")


# ── build_plan ───────────────────────────────────────────────────────────────


class TestBuildPlan:
    """Execution plan building."""

    def test_build_plan_single_device(self, orchestrator):
        plan = orchestrator.build_plan(
            service_id="router-routing-table",
            target_devices=["gw-01"],
        )
        assert len(plan.steps) == 1
        assert plan.steps[0].device_id == "gw-01"
        assert "display ip routing-table" in plan.steps[0].commands[0]

    def test_build_plan_multi_device(self, orchestrator, mock_controller):
        gw_01_state = mock_controller.get_state("gw-01")
        gw_02_state = DeviceState(
            device_id="gw-02", host="10.0.0.10", port=22,
            device_type="router", status="online",
        )
        states = {"gw-01": gw_01_state, "gw-02": gw_02_state}
        mock_controller.get_state.side_effect = lambda dev_id: states.get(dev_id)
        plan = orchestrator.build_plan(
            service_id="router-routing-table",
            target_devices=["gw-01", "gw-02"],
        )
        assert len(plan.steps) == 2
        assert {s.device_id for s in plan.steps} == {"gw-01", "gw-02"}

    def test_build_plan_device_not_in_controller(self, orchestrator, mock_controller):
        mock_controller.get_state.return_value = None
        with pytest.raises(ValueError, match="not registered"):
            orchestrator.build_plan(
                service_id="router-routing-table",
                target_devices=["unknown-dev"],
            )

    def test_build_plan_device_offline(self, orchestrator):
        with pytest.raises(ValueError, match="offline"):
            orchestrator.build_plan(
                service_id="router-routing-table",
                target_devices=["offline-dev"],
            )

    def test_build_plan_service_type_mismatch(self, orchestrator):
        """Service requires ROUTER but target is SWITCH-only type."""
        with pytest.raises(ValueError, match="incompatible"):
            orchestrator.build_plan(
                service_id="router-ospf-peer",
                target_devices=["sw-01"],
            )


# ── execute ──────────────────────────────────────────────────────────────────


class TestExecute:
    """Plan execution."""

    def test_execute_single_device(self, orchestrator):
        plan = orchestrator.build_plan(
            service_id="router-routing-table",
            target_devices=["gw-01"],
        )
        results = orchestrator.execute(plan)
        assert len(results) == 1
        assert results[0].device_id == "gw-01"
        assert results[0].success is True
        assert results[0].output is not None

    def test_execute_multi_device(self, orchestrator, mock_controller):
        gw_01_state = mock_controller.get_state("gw-01")
        gw_02_state = DeviceState(
            device_id="gw-02", host="10.0.0.10", port=22,
            device_type="router", status="online",
        )
        states = {"gw-01": gw_01_state, "gw-02": gw_02_state}
        mock_controller.get_state.side_effect = lambda dev_id: states.get(dev_id)
        plan = orchestrator.build_plan(
            service_id="router-routing-table",
            target_devices=["gw-01", "gw-02"],
        )
        results = orchestrator.execute(plan)
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_execute_propagates_errors(self, orchestrator, mock_executor):
        mock_executor.side_effect = RuntimeError("Connection refused")
        plan = orchestrator.build_plan(
            service_id="router-routing-table",
            target_devices=["gw-01"],
        )
        results = orchestrator.execute(plan)
        assert len(results) == 1
        assert results[0].success is False
        assert "Connection refused" in (results[0].error or "")


# ── execute_intent (convenience) ─────────────────────────────────────────────


class TestExecuteIntent:
    """Convenience: resolve + build_plan + execute in one call."""

    def test_execute_intent_single(self, orchestrator):
        results = orchestrator.execute_intent(
            service_id="router-routing-table",
            target_devices=["gw-01"],
        )
        assert len(results) == 1
        assert results[0].success is True

    def test_execute_intent_multi(self, orchestrator):
        results = orchestrator.execute_intent(
            service_id="router-routing-table",
            target_devices=["gw-01", "sw-01"],
        )
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_execute_intent_invalid_params(self, orchestrator):
        with pytest.raises(ValueError, match="not found"):
            orchestrator.execute_intent(
                service_id="invalid",
                target_devices=["gw-01"],
            )

    def test_execute_intent_device_offline(self, orchestrator):
        results = orchestrator.execute_intent(
            service_id="router-routing-table",
            target_devices=["gw-01", "offline-dev"],
        )
        # gw-01 succeeds, offline-dev fails
        assert results[0].success is True
        assert results[1].success is False
        assert "offline" in (results[1].error or "").lower()


# ── Dataclass tests ──────────────────────────────────────────────────────────


class TestExecutionPlan:
    """ExecutionPlan and ExecutionStep dataclasses."""

    def test_plan_creation(self):
        from huawei_manager.sdn_controller._dormant.orchestrator import (
            ExecutionPlan,
            ExecutionStep,
        )

        step = ExecutionStep(device_id="gw-01", commands=["display version"])
        plan = ExecutionPlan(steps=[step], service_id="sys-version")
        assert len(plan.steps) == 1
        assert plan.service_id == "sys-version"

    def test_step_defaults(self):
        from huawei_manager.sdn_controller._dormant.orchestrator import ExecutionStep

        step = ExecutionStep(device_id="gw-01", commands=["show run"])
        assert step.params == {}


class TestExecutionResult:
    """ExecutionResult dataclass."""

    def test_success_result(self):
        from huawei_manager.sdn_controller._dormant.orchestrator import ExecutionResult

        result = ExecutionResult(
            device_id="gw-01", success=True, output="output data",
        )
        assert result.device_id == "gw-01"
        assert result.success is True
        assert result.output == "output data"
        assert result.error is None

    def test_error_result(self):
        from huawei_manager.sdn_controller._dormant.orchestrator import ExecutionResult

        result = ExecutionResult(
            device_id="gw-01", success=False, output="",
            error="Connection failed",
        )
        assert result.success is False
        assert result.error == "Connection failed"
