"""Integration tests for SDN security modules (CommandValidator, DryRunEngine, NorthboundAPI, ControllerCore)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from huawei_manager.audit_log import AuditLogger
from huawei_manager.sdn_controller.core import ControllerCore, DeviceState
from huawei_manager.sdn_controller.dryrun import DryRunEngine
from huawei_manager.sdn_controller.event_queue import Event, EventQueue, EventType
from huawei_manager.sdn_controller.northbound import NorthboundAPI
from huawei_manager.sdn_controller.validator import CommandValidator


# ═══════════════════════════════════════════════════════════════════
#  B1 — CommandValidator: bloqueia comandos perigosos
# ═══════════════════════════════════════════════════════════════════
class TestCommandValidatorBlocking:
    """Verifica que o CommandValidator bloqueia padroes de comandos destrutivos."""

    def test_b1_blocks_format_flash(self):
        v = CommandValidator()
        result = v.validate("format flash:", role="user")
        assert not result.allowed
        assert result.reason is not None
        assert "denied" in result.reason

    def test_b1_blocks_reset_saved_config(self):
        v = CommandValidator()
        result = v.validate("reset saved-configuration", role="user")
        assert not result.allowed

    def test_b1_blocks_delete(self):
        v = CommandValidator()
        result = v.validate("delete /unreserved vrpcfg.zip", role="user")
        assert not result.allowed

    def test_b1_blocks_undo_startup(self):
        v = CommandValidator()
        result = v.validate("undo startup", role="user")
        assert not result.allowed


# ═══════════════════════════════════════════════════════════════════
#  B2 — CommandValidator: bypass para admin/tecnico
# ═══════════════════════════════════════════════════════════════════
class TestCommandValidatorBypass:
    """Admin/Tecnico podem bypassar comandos negados com flag bypass_2fa."""

    def test_b2_admin_can_bypass(self):
        v = CommandValidator()
        result = v.validate("reset saved-configuration", role="admin")
        assert result.allowed
        assert result.bypass_2fa

    def test_b2_tecnico_can_bypass(self):
        v = CommandValidator()
        result = v.validate("reset saved-configuration", role="tecnico")
        assert result.allowed
        assert result.bypass_2fa

    def test_b2_user_cannot_bypass(self):
        v = CommandValidator()
        result = v.validate("reset saved-configuration", role="user")
        assert not result.allowed


# ═══════════════════════════════════════════════════════════════════
#  B3 — DryRunEngine: diff generation
# ═══════════════════════════════════════════════════════════════════
class TestDryRunEngineDiff:
    """Gera diff corretamente entre config atual e proposta."""

    def test_b3_diff_no_changes(self):
        e = DryRunEngine()
        report = e.diff("config", "config")
        assert not report.has_changes

    def test_b3_diff_detects_additions(self):
        e = DryRunEngine()
        report = e.diff("config\n", "config\nnew-line\n")
        assert report.has_changes
        assert report.total_added > 0

    def test_b3_diff_detects_removals(self):
        e = DryRunEngine()
        report = e.diff("config\nold-line\n", "config\n")
        assert report.has_changes
        assert report.total_removed > 0

    def test_b3_diff_summary(self):
        e = DryRunEngine()
        report = e.diff("a\nb\n", "a\nb\nc\n")
        assert "added" in report.summary

    def test_b3_apply_with_rollback(self):
        e = DryRunEngine()
        fake_fn = MagicMock(return_value="config applied")
        result = e.apply(fake_fn, "new config", original="old config")
        assert result.success
        assert result.rollback_command is not None


# ═══════════════════════════════════════════════════════════════════
#  B4 — NorthboundAPI: RBAC enforcement
# ═══════════════════════════════════════════════════════════════════
class TestNorthboundAPIRBAC:
    """NorthboundAPI respeita niveis de acesso por endpoint."""

    @pytest.fixture
    def controller(self):
        c = ControllerCore()
        c.register("rtr-01", "10.0.0.1", 22, "router")
        return c

    @pytest.fixture
    def event_q(self):
        return EventQueue()

    @pytest.fixture
    def audit(self, tmp_audit_path):
        return AuditLogger(str(tmp_audit_path))

    @pytest.fixture
    def api(self, controller, event_q, audit):
        mock_sb = MagicMock()
        mock_sb.is_alive.return_value = True
        mock_sb.send_config.return_value = (True, "config applied")
        return NorthboundAPI(controller, event_q, audit, sb=mock_sb)

    def test_b4_user_can_get_devices(self, api):
        resp = api.get_devices(role="user")
        assert resp.success

    def test_b4_user_cannot_deploy(self, api):
        """deploy_intent requer pelo menos tecnico."""
        resp = api.deploy_intent("rtr-01", "config", role="user")
        assert not resp.success
        assert "denied" in (resp.error or "").lower()

    def test_b4_tecnico_can_deploy(self, api):
        resp = api.deploy_intent("rtr-01", "config", role="tecnico")
        assert resp.success

    def test_b4_invalid_role_returns_error(self, api):
        resp = api.get_devices(role="unknown")
        assert not resp.success


# ═══════════════════════════════════════════════════════════════════
#  B5 — NorthboundAPI: blocagem de acesso nao autorizado
# ═══════════════════════════════════════════════════════════════════
class TestNorthboundAPIUnauthorized:
    """Endpoints retornam erro 403-equivalente para roles insuficientes."""

    @pytest.fixture
    def controller(self):
        c = ControllerCore()
        c.register("rtr-01", "10.0.0.1", 22, "router")
        return c

    @pytest.fixture
    def api(self, controller, audit_logger):
        return NorthboundAPI(controller, MagicMock(), audit_logger)

    def test_b5_deploy_blocked_for_user(self, api):
        resp = api.deploy_intent("rtr-01", "config", role="user")
        assert not resp.success
        assert "Permission denied" in (resp.error or "")

    def test_b5_audit_log_blocked_for_user(self, api):
        resp = api.get_audit_log(role="user")
        assert not resp.success


# ═══════════════════════════════════════════════════════════════════
#  B6 — ControllerCore: gerenciamento de estado
# ═══════════════════════════════════════════════════════════════════
class TestControllerCore:
    """ControllerCore gerencia estado de dispositivos corretamente."""

    def test_b6_register_device(self):
        c = ControllerCore()
        state = c.register("rtr-01", "10.0.0.1", 22, "router")
        assert state.device_id == "rtr-01"
        assert state.status == "unknown"

    def test_b6_get_state(self):
        c = ControllerCore()
        c.register("rtr-01", "10.0.0.1", 22, "router")
        state = c.get_state("rtr-01")
        assert state is not None
        assert state.host == "10.0.0.1"

    def test_b6_get_state_nonexistent(self):
        c = ControllerCore()
        assert c.get_state("nonexistent") is None

    def test_b6_deregister(self):
        c = ControllerCore()
        c.register("rtr-01", "10.0.0.1", 22, "router")
        assert c.deregister("rtr-01")
        assert c.get_state("rtr-01") is None

    def test_b6_update_state(self):
        c = ControllerCore()
        c.register("rtr-01", "10.0.0.1", 22, "router")
        c.update_state("rtr-01", status="online")
        state = c.get_state("rtr-01")
        assert state is not None
        assert state.status == "online"

    def test_b6_list_devices(self):
        c = ControllerCore()
        c.register("rtr-01", "10.0.0.1", 22, "router")
        c.register("sw-01", "10.0.0.2", 22, "switch")
        assert len(c.list_devices()) == 2


# ═══════════════════════════════════════════════════════════════════
#  B7 — EventQueue: eventos e subscriptions
# ═══════════════════════════════════════════════════════════════════
class TestEventQueue:
    """EventQueue thread-safe com prioridade e subscription."""

    def test_b7_put_and_poll(self):
        q = EventQueue()
        assert q.poll(timeout=0.1) == []

        e = Event(type=EventType.DEVICE_CONNECTED, source="rtr-01")
        q.put(e)
        events = q.poll(timeout=0.1)
        assert len(events) == 1
        assert events[0].type == EventType.DEVICE_CONNECTED
        assert events[0].source == "rtr-01"

    def test_b7_subscribe_callback(self):
        q = EventQueue()
        callback = MagicMock()
        q.subscribe(EventType.DEVICE_CONNECTED, callback)

        e = Event(type=EventType.DEVICE_CONNECTED, source="rtr-01")
        q.put(e)
        q.poll(timeout=0.1)

        callback.assert_called_once_with(e)

    def test_b7_event_priority(self):
        q = EventQueue()
        critical = Event(type=EventType.DEVICE_ERROR, source="rtr-01", priority=0)
        normal = Event(type=EventType.DEVICE_CONNECTED, source="rtr-02", priority=10)
        q.put(normal)
        q.put(critical)

        events = q.poll(timeout=0.1)
        assert events[0].priority == 0
        assert events[1].priority == 10
