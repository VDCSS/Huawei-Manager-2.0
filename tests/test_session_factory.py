"""Testes do SSHSessionFactory (TODO 4/9a).

Backend fake em memória — NUNCA EnvBackend (Artemis): não persiste no
.env real nem lê creds do ambiente. Sessões são MagicMock (sem SSH).
"""
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from huawei_manager.audit_log import AuditLogger
from huawei_manager.sdn_controller.session_factory import (
    SSHSessionFactory,
    _OriginAuditWrapper,
)
from huawei_manager.sdn_controller.southbound import SSHSouthbound
from huawei_manager.vault_backends.base import SecretsBackend
from huawei_manager.vnf_models import VNF


class _FakeBackend(SecretsBackend):
    """Backend em memória, SEM ROUTER_* — provoca fail-closed se houver fallback."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self.get_calls: list[str] = []

    def get(self, key: str, default: str = "") -> str:
        self.get_calls.append(key)
        return self._data.get(key, default)

    def put(self, key: str, value: str) -> None:
        self._data[key] = value


def _vnf(**overrides: object) -> VNF:
    base: dict[str, object] = {
        "id": "vnf-001-router",
        "name": "R1",
        "host": "10.0.0.1",
        "port": 22,
        "type": "ROUTER",
        "username": "admin",
        "password": "secret",
    }
    base.update(overrides)
    return VNF(**base)


@pytest.fixture
def factory(audit_logger):
    """Factory com builder fake: registra overrides e devolve MagicMock."""
    backend = _FakeBackend()
    overrides: list[dict] = []

    def fake_builder(_backend, _audit, **kwargs):
        overrides.append(kwargs)
        return MagicMock(spec=SSHSouthbound)

    fac = SSHSessionFactory(
        backend, audit_logger, session_builder=fake_builder,
    )
    return SimpleNamespace(factory=fac, backend=backend, overrides=overrides)


def test_factory_creates_per_device_session(factory):
    s1 = factory.factory.get(_vnf(id="vnf-1-a", name="A", host="10.0.0.1"))
    s2 = factory.factory.get(_vnf(id="vnf-2-b", name="B", host="10.0.0.2"))
    assert s1 is not None and s2 is not None
    assert s1 is not s2
    assert factory.factory.active_sessions == 2


def test_factory_skips_missing_credentials(factory):
    assert factory.factory.get(_vnf(host="")) is None
    assert factory.factory.get(_vnf(username="")) is None
    assert factory.factory.get(_vnf(password="", ssh_key="")) is None
    assert factory.factory.active_sessions == 0


def test_factory_never_falls_back_to_global_creds(factory):
    # Backend fake NÃO tem ROUTER_*; VNF incompleto → None e NENHUMA
    # consulta ao backend (sem fallback global — regressão B4)
    assert factory.factory.get(_vnf(password="", ssh_key="")) is None
    assert factory.backend.get_calls == []


def test_factory_reuses_cached_session(factory):
    vnf = _vnf()
    s1 = factory.factory.get(vnf)
    s2 = factory.factory.get(vnf)
    assert s1 is s2
    assert len(factory.overrides) == 1


def test_factory_maps_override_port(factory):
    factory.factory.get(_vnf(port=22))
    factory.factory.get(_vnf(id="vnf-2-b", name="B", host="10.0.0.2", port=0))
    factory.factory.get(_vnf(id="vnf-3-c", name="C", host="10.0.0.3", port=2222))
    assert factory.overrides[0]["override_port"] == 22
    # port 0/None → 22 (D21/D22: nunca cai no fallback global)
    assert factory.overrides[1]["override_port"] == 22
    # porta explícita preservada
    assert factory.overrides[2]["override_port"] == 2222


def test_connect_failure_does_not_poison_pool(audit_logger):
    def failing_builder(_backend, _audit, **kwargs):
        ssb = MagicMock(spec=SSHSouthbound)
        ssb.connect.side_effect = RuntimeError("auth fail")
        return ssb

    fac = SSHSessionFactory(
        _FakeBackend(), audit_logger, session_builder=failing_builder,
    )
    vnf = _vnf()
    assert fac.get(vnf) is None
    assert fac.active_sessions == 0
    # 2ª chamada tenta de novo — não reusa sessão morta
    assert fac.get(vnf) is None


def test_purge_expired_closes_idle_sessions(audit_logger):
    ssb = MagicMock(spec=SSHSouthbound)
    fac = SSHSessionFactory(
        _FakeBackend(), audit_logger,
        session_builder=lambda _b, _a, **k: ssb,
        ttl_seconds=0.001,
    )
    fac.get(_vnf())
    assert fac.active_sessions == 1
    time.sleep(0.01)
    fac.purge_expired()
    assert fac.active_sessions == 0
    ssb.disconnect.assert_called()


def test_release_and_dispose(factory):
    v1 = _vnf(id="vnf-1-a", name="A", host="10.0.0.1")
    v2 = _vnf(id="vnf-2-b", name="B", host="10.0.0.2")
    s1 = factory.factory.get(v1)
    s2 = factory.factory.get(v2)
    factory.factory.release("vnf-1-a")
    assert factory.factory.active_sessions == 1
    s1.disconnect.assert_called()
    factory.factory.dispose()
    assert factory.factory.active_sessions == 0
    s2.disconnect.assert_called()


def test_ui_session_untouched(factory):
    # VNF completo: factory NUNCA consulta backend (ROUTER_* não usado)
    factory.factory.get(_vnf())
    assert factory.backend.get_calls == []


def test_audit_wrapper_adds_origin(tmp_path):
    inner = AuditLogger(str(tmp_path / "audit.jsonl"))
    wrapper = _OriginAuditWrapper(inner)
    wrapper.log_operation("get", user="u", host="h", status="ok")
    entry = inner.tail(1)[0]
    assert entry["extra"]["origin"] == "auto-poll"


def test_audit_wrapper_timed_adds_origin(tmp_path):
    inner = AuditLogger(str(tmp_path / "audit.jsonl"))
    wrapper = _OriginAuditWrapper(inner)
    with wrapper.timed("get", user="u", host="h"):
        pass
    entry = inner.tail(1)[0]
    assert entry["extra"]["origin"] == "auto-poll"
