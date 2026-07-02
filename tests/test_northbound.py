"""Tests for NorthboundAPI — internal facade consumed by GUI."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from huawei_manager.audit_log import AuditLogger
from huawei_manager.sdn_controller.core import ControllerCore, DeviceState
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.southbound import SSHSouthbound

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_controller() -> ControllerCore:
    ctrl = MagicMock(spec=ControllerCore)
    ctrl.list_devices.return_value = ["gw-01", "sw-01"]
    ctrl.get_state.side_effect = lambda dev_id: {
        "gw-01": DeviceState(
            device_id="gw-01", host="10.0.0.1", port=22,
            device_type="router", status="online",
        ),
        "sw-01": DeviceState(
            device_id="sw-01", host="10.0.0.2", port=22,
            device_type="switch", status="unknown",
        ),
    }.get(dev_id)
    return ctrl


@pytest.fixture
def mock_event_queue() -> MagicMock:
    eq = MagicMock(spec=["poll"])
    eq.poll.return_value = [
        Event(type=EventType.DEVICE_CONNECTED, source="gw-01"),
        Event(type=EventType.ALERT, source="gw-01", priority=0),
    ]
    return eq


@pytest.fixture
def mock_audit_logger() -> MagicMock:
    al = MagicMock(spec=AuditLogger)
    al.tail.return_value = [
        {"ts": "2026-07-01T10:00:00", "op": "login", "user": "admin"},
        {"ts": "2026-07-01T10:05:00", "op": "command", "cmd": "display version"},
    ]
    return al


@pytest.fixture
def mock_southbound() -> MagicMock:
    sb = MagicMock(spec=SSHSouthbound)
    sb.send_command.return_value = "display version\nVRP (R) Software"
    sb.send_config.return_value = (True, "OK Config applied")
    sb.is_alive.return_value = True
    return sb


@pytest.fixture
def api(mock_controller, mock_event_queue, mock_audit_logger, mock_southbound):
    from huawei_manager.sdn_controller.northbound import NorthboundAPI

    return NorthboundAPI(
        controller=mock_controller,
        event_queue=mock_event_queue,
        audit_logger=mock_audit_logger,
        sb=mock_southbound,
    )


# ── Response format ──────────────────────────────────────────────────────────


class TestApiResponse:
    """ApiResponse dataclass must have standard fields."""

    def test_success_response(self):
        from huawei_manager.sdn_controller.northbound import ApiResponse

        resp = ApiResponse(data={"devices": []})
        assert resp.success is True
        assert resp.data == {"devices": []}
        assert resp.error is None

    def test_error_response(self):
        from huawei_manager.sdn_controller.northbound import ApiResponse

        resp = ApiResponse(success=False, error="Not found")
        assert resp.success is False
        assert resp.error == "Not found"
        assert resp.data is None

    def test_to_dict(self):
        from huawei_manager.sdn_controller.northbound import ApiResponse

        resp = ApiResponse(data={"key": "val"})
        d = resp.to_dict()
        assert d == {"success": True, "data": {"key": "val"}, "error": None}


# ── get_devices ──────────────────────────────────────────────────────────────


class TestGetDevices:
    """get_devices endpoint."""

    def test_returns_device_list(self, api):
        result = api.get_devices(role="user")
        assert result.success is True
        assert len(result.data) == 2
        ids = [d["device_id"] for d in result.data]
        assert "gw-01" in ids
        assert "sw-01" in ids

    def test_each_device_has_required_fields(self, api):
        result = api.get_devices(role="user")
        assert result.success is True
        for dev in result.data:
            assert "device_id" in dev
            assert "host" in dev
            assert "port" in dev
            assert "device_type" in dev
            assert "status" in dev

    def test_permission_denied(self, api):
        result = api.get_devices(role="unknown")
        assert result.success is False
        assert "Unknown role" in (result.error or "")

    def test_controller_error_returns_error_response(
        self, mock_controller, mock_event_queue, mock_audit_logger, mock_southbound,
    ):
        from huawei_manager.sdn_controller.northbound import NorthboundAPI

        mock_controller.list_devices.side_effect = RuntimeError("Controller down")
        api = NorthboundAPI(
            controller=mock_controller, event_queue=mock_event_queue,
            audit_logger=mock_audit_logger, sb=mock_southbound,
        )
        result = api.get_devices(role="user")
        assert result.success is False
        assert "Controller down" in (result.error or "")


# ── get_topology ─────────────────────────────────────────────────────────────


class TestGetTopology:
    """get_topology endpoint."""

    def test_returns_device_list(self, api):
        result = api.get_topology(role="user")
        assert result.success is True
        assert "devices" in result.data
        assert "total" in result.data
        assert result.data["total"] == 2

    def test_permission_denied(self, api):
        result = api.get_topology(role="user")
        assert result.success is True  # USER can access topology

    def test_invalid_role(self, api):
        result = api.get_topology(role="hacker")
        assert result.success is False


# ── get_events ───────────────────────────────────────────────────────────────


class TestGetEvents:
    """get_events endpoint."""

    def test_returns_events(self, api):
        result = api.get_events(role="user", limit=10)
        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) <= 10

    def test_event_has_required_fields(self, api):
        result = api.get_events(role="user")
        assert result.success is True
        for ev in result.data:
            assert "type" in ev
            assert "source" in ev
            assert "priority" in ev
            assert "timestamp" in ev

    def test_limit_respected(self, api):
        result = api.get_events(role="user", limit=1)
        assert result.success is True
        assert len(result.data) <= 1

    def test_permission_denied(self, api):
        result = api.get_events(role="unknown")
        assert result.success is False


# ── get_config ───────────────────────────────────────────────────────────────


class TestGetConfig:
    """get_config endpoint."""

    def test_returns_config(self, api):
        result = api.get_config(device_id="gw-01", role="user")
        assert result.success is True
        assert "config" in result.data
        assert result.data["device_id"] == "gw-01"

    def test_device_not_found(self, mock_controller, mock_event_queue, mock_audit_logger, mock_southbound):
        from huawei_manager.sdn_controller.northbound import NorthboundAPI

        mock_controller.get_state.return_value = None
        api = NorthboundAPI(
            controller=mock_controller, event_queue=mock_event_queue,
            audit_logger=mock_audit_logger, sb=mock_southbound,
        )
        result = api.get_config(device_id="unknown", role="user")
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    def test_permission_denied(self, api):
        result = api.get_config(device_id="gw-01", role="hacker")
        assert result.success is False


# ── deploy_intent ────────────────────────────────────────────────────────────


class TestDeployIntent:
    """deploy_intent endpoint."""

    def test_deploy_config(self, api):
        result = api.deploy_intent(
            device_id="gw-01",
            config="vlan 10\nquit",
            role="admin",
        )
        assert result.success is True
        assert result.data["device_id"] == "gw-01"
        assert "applied" in result.data.get("message", "").lower()

    def test_user_cannot_deploy(self, api):
        """USER role cannot deploy config."""
        result = api.deploy_intent(
            device_id="gw-01",
            config="vlan 10",
            role="user",
        )
        assert result.success is False
        assert "permission" in (result.error or "").lower()

    def test_tecnico_can_deploy(self, api):
        """TECNICO role can deploy config."""
        result = api.deploy_intent(
            device_id="gw-01",
            config="vlan 10",
            role="tecnico",
        )
        assert result.success is True

    def test_device_not_found(self, api, mock_controller):
        mock_controller.get_state.return_value = None
        result = api.deploy_intent(device_id="unknown", config="test", role="admin")
        assert result.success is False

    def test_southbound_failure_returns_error(self, api, mock_southbound):
        mock_southbound.send_config.return_value = (False, "Error applying")
        result = api.deploy_intent(device_id="gw-01", config="bad config", role="admin")
        assert result.success is False


# ── get_policies ─────────────────────────────────────────────────────────────


class TestGetPolicies:
    """get_policies endpoint (stub for M14-M15)."""

    def test_returns_policy_list(self, api):
        result = api.get_policies(role="user")
        assert result.success is True
        assert isinstance(result.data, list)

    def test_permission_denied(self, api):
        result = api.get_policies(role="hacker")
        assert result.success is False


# ── get_audit_log ────────────────────────────────────────────────────────────


class TestGetAuditLog:
    """get_audit_log endpoint."""

    def test_returns_audit_entries(self, api):
        result = api.get_audit_log(role="admin", limit=10)
        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) >= 1

    def test_user_cannot_access_audit(self, api):
        """USER role cannot access audit log."""
        result = api.get_audit_log(role="user", limit=10)
        assert result.success is False
        assert "permission" in (result.error or "").lower()

    def test_tecnico_can_access_audit(self, api):
        """TECNICO role can access audit log."""
        result = api.get_audit_log(role="tecnico", limit=10)
        assert result.success is True

    def test_permission_denied(self, api):
        result = api.get_audit_log(role="hacker")
        assert result.success is False


# ── Combined ─────────────────────────────────────────────────────────────────


class TestNorthboundAPIInit:
    """Constructor and type checks."""

    def test_requires_controller(self, mock_event_queue, mock_audit_logger, mock_southbound):
        from huawei_manager.sdn_controller.northbound import NorthboundAPI

        with pytest.raises(TypeError):
            NorthboundAPI(
                controller=None,  # type: ignore
                event_queue=mock_event_queue,
                audit_logger=mock_audit_logger,
                sb=mock_southbound,
            )
