"""Testes do PollingManager (TODO 5/9b).

Usa VnfService fake (fonte do inventário — D6) e SSHSouthbound fake
(sem SSH). get_service_by_id do módulo é patchado para retornos
determinísticos; poll_services explícitos por teste.
"""
import time
from unittest.mock import MagicMock

import pytest

from huawei_manager.sdn_controller.polling_manager import (
    IntervalDecider,
    PollingManager,
    StabilityTracker,
)
from huawei_manager.sdn_controller.southbound import SSHSouthbound
from huawei_manager.services_data import ServiceDef
from huawei_manager.vnf_models import VNF


def _vnf_fake(device_id: str, status: str = "online", vtype: str = "ROUTER") -> VNF:
    return VNF(
        id=device_id,
        name=device_id,
        host="10.0.0.1",
        username="admin",
        password="secret",
        status=status,
        type=vtype,
        port=22,
    )


def _svc(svc_id: str, vnf_types: list[str], cmds: list[str]) -> ServiceDef:
    return ServiceDef(
        id=svc_id,
        name=svc_id,
        description=svc_id,
        category="c",
        vnf_types=vnf_types,
        cli_commands=cmds,
    )


class _FakeVnfService:
    """Fonte de inventário controlável (load_inventory retorna lista fixa)."""

    def __init__(self, vnfs: list[VNF]) -> None:
        self._vnfs = vnfs

    def load_inventory(self) -> list[VNF]:
        return list(self._vnfs)


class _FakeFactory:
    """Factory fake que registra get/release/purge e entrega MagicMock."""

    def __init__(self) -> None:
        self.get_calls: list[str] = []
        self.release_calls: list[str] = []
        self.purge_count = 0
        self.active_sessions = 0
        self._ssb = MagicMock(spec=SSHSouthbound)

    def get(self, vnf: VNF) -> SSHSouthbound | None:
        self.get_calls.append(vnf.id)
        return self._ssb

    def release(self, device_id: str) -> None:
        self.release_calls.append(device_id)

    def purge_expired(self) -> None:
        self.purge_count += 1


@pytest.fixture
def root_svc():
    return _svc("router-routing-table", ["ROUTER"], ["display ip routing-table"])


@pytest.fixture
def make_manager(monkeypatch):
    def _make(vnfs, services=None, poll_services=None, enabled=True, ssb_out="stable output"):
        svc_objs = list(services or [])
        lookup = {s.id: s for s in svc_objs}
        # Patcheia get_service_by_id do MÓDULO polling_manager com o
        # lookup deterministico (ids reais do catalogo casam com varias
        # vnf_types — videos usar fakes para o teste de skip ser preciso)
        import huawei_manager.sdn_controller.polling_manager as pm
        monkeypatch.setattr(pm, "get_service_by_id", lookup.get)
        factory = _FakeFactory()
        factory._ssb.send_service_commands.return_value = ssb_out
        vnf_service = _FakeVnfService(vnfs)
        ids = poll_services if poll_services is not None else [s.id for s in svc_objs]
        mgr = PollingManager(
            factory=factory,
            vnf_service=vnf_service,
            enabled=enabled,
            poll_services=ids,
        )
        return mgr, factory
    return _make


def test_tick_no_exceptions(make_manager):
    mgr, _ = make_manager([_vnf_fake("r1")])
    mgr.tick()  # não lança


def test_tick_noop_when_disabled(make_manager):
    mgr, factory = make_manager([_vnf_fake("r1")], enabled=False)
    mgr.tick()
    assert factory.get_calls == []


def test_tick_sources_online_from_inventory(make_manager, root_svc):
    # NÃO usa ControllerCore (D6): v.status=="online" decide
    offline = _vnf_fake("off", status="offline")
    online = _vnf_fake("on", status="online")
    mgr, factory = make_manager([offline, online], services=[root_svc])
    mgr.tick()
    assert factory.get_calls == ["on"]


def test_tick_respects_next_due(make_manager):
    # device com next_due futuro NÃO é pollado (regressão B3)
    mgr, factory = make_manager([_vnf_fake("r1")])
    mgr._next_due["r1"] = 9999999999.0
    mgr.tick()
    assert factory.get_calls == []


def test_tick_consolidates_services_per_device(make_manager, root_svc):
    svc2 = _svc("router-bgp-summary", ["ROUTER"], ["display bgp summary"])
    mgr, factory = make_manager(
        [_vnf_fake("r1")],
        services=[root_svc, svc2],
    )
    mgr.tick()
    factory._ssb.send_service_commands.assert_called_once_with(
        ["display ip routing-table", "display bgp summary"]
    )


def test_tick_skips_device_without_matching_services(make_manager, root_svc):
    # VNF SWITCH não casa com serviço ROUTER → skip, zero custo
    switch = _vnf_fake("sw1", vtype="SWITCH")
    mgr, factory = make_manager([switch], services=[root_svc])
    mgr.tick()
    assert factory.get_calls == []
    factory._ssb.send_service_commands.assert_not_called()


def test_tick_survives_device_exception_and_releases(make_manager, root_svc):
    mgr, factory = make_manager([_vnf_fake("r1")], services=[root_svc])
    factory._ssb.send_service_commands.side_effect = RuntimeError("boom")
    mgr.tick()  # não lança (D20: try/except por device)
    assert factory.release_calls == ["r1"]


def test_tick_releases_only_on_error(make_manager, root_svc):
    # D20: sucesso NÃO chama release — sessão fica no pool
    mgr, factory = make_manager([_vnf_fake("r1")], services=[root_svc])
    mgr.tick()
    assert factory.release_calls == []


def test_tick_sets_backoff_after_device_error(make_manager, root_svc):
    # D20: next_due = now + POLL_DEFAULT_INTERVAL (anti hot-loop)
    mgr, factory = make_manager([_vnf_fake("r1")], services=[root_svc])
    factory._ssb.send_service_commands.side_effect = RuntimeError("boom")
    mgr.tick()
    # POLL_DEFAULT_INTERVAL = 60; now não é injetável, então basta o
    # intervalo ser grande o suficiente para não re-poll no próximo tick
    assert mgr._next_due["r1"] > time.time() + 55


def test_error_string_marks_unstable(make_manager, root_svc):
    # D13: output com "ERRO:" → instável, next_due curto (POLL_MIN_INTERVAL)
    mgr, factory = make_manager(
        [_vnf_fake("r1")],
        services=[root_svc],
        ssb_out="ERRO: comando invalido",
    )
    mgr.tick()
    assert factory.release_calls == []  # erro-como-string NÃO é exceção
    assert mgr._next_due["r1"] <= time.time() + 20  # instável → min 15s
    assert mgr.get_status()["stable"].get("r1") is not True


def test_overlapping_ticks_are_skipped(make_manager):
    mgr, factory = make_manager([_vnf_fake("r1")])
    mgr._tick_lock.acquire(blocking=False)
    try:
        mgr.tick()
        assert factory.get_calls == []
    finally:
        mgr._tick_lock.release()


def test_force_poll_clears_next_due(make_manager):
    mgr, _ = make_manager([_vnf_fake("r1")])
    mgr._next_due["r1"] = 9999999999.0
    mgr.force_poll("r1", service_id="router-routing-table")
    assert "r1" not in mgr._next_due


class TestStabilityTracker:
    def test_stable_after_n_equal(self):
        t = StabilityTracker(history_size=3)
        assert t.record("dev", "aa") is False
        assert t.record("dev", "aa") is False
        assert t.record("dev", "aa") is True

    def test_unstable_on_change(self):
        t = StabilityTracker(history_size=3)
        t.record("dev", "aa")
        t.record("dev", "aa")
        t.record("dev", "bb")
        assert t.is_stable("dev") is False

    def test_reset_by_device(self):
        t = StabilityTracker(history_size=2)
        t.record("dev", "aa")
        t.record("dev", "aa")
        t.reset("dev")
        assert t.is_stable("dev") is False

    def test_reset_all(self):
        t = StabilityTracker(history_size=2)
        t.record("a", "aa")
        t.record("a", "aa")
        t.record("b", "bb")
        t.record("b", "bb")
        t.reset()
        assert t.get_all_states() == {}


class TestIntervalDecider:
    def test_progression_and_cap(self):
        d = IntervalDecider(min_interval=15, max_interval=300, multiplier=2.0)
        assert d.next_interval("dev", is_stable=True) == pytest.approx(30)
        assert d.next_interval("dev", is_stable=True) == pytest.approx(60)
        assert d.next_interval("dev", is_stable=True) == pytest.approx(120)
        assert d.next_interval("dev", is_stable=True) == pytest.approx(240)
        assert d.next_interval("dev", is_stable=True) == pytest.approx(300)

    def test_unstable_resets_to_min(self):
        d = IntervalDecider(min_interval=15, max_interval=300, multiplier=2.0)
        d.next_interval("dev", is_stable=True)
        d.next_interval("dev", is_stable=True)
        assert d.next_interval("dev", is_stable=False) == pytest.approx(15)

    def test_offline_goes_to_max(self):
        d = IntervalDecider(min_interval=15, max_interval=300, multiplier=2.0)
        assert d.next_interval("dev", is_stable=True, is_offline=True) == pytest.approx(300)

    def test_new_device_goes_to_min(self):
        d = IntervalDecider(min_interval=15, max_interval=300, multiplier=2.0)
        assert d.next_interval("dev", is_stable=True) >= 15


def test_polling_imports_flow(make_manager, root_svc):
    # smoke: real get status após um tick
    mgr, factory = make_manager([_vnf_fake("r1")], services=[root_svc])
    mgr.tick()
    status = mgr.get_status()
    assert status["enabled"] is True
    assert "r1" in status["stable"]
