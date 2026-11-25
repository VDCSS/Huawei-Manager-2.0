"""Validações de regras de negócio do DeviceService (TDD).

Cobre as lacunas identificadas:
* formato de host (IPv4/IPv6/domínio RFC1035) deve ser validado;
* name e host devem ser únicos (sem duplicidade);
* type deve estar em lista permitida;
* porta inválida deve ser rejeitada (não fallback silencioso).
"""
from __future__ import annotations

import pytest

from huawei_manager.device_models import Device


def _make_svc(tmp_path, monkeypatch, devices: list[Device] | None = None, db_name: str = "test_validation.db"):
    """Cria DeviceService com repository real (tmp_path) carregado com devices."""
    from huawei_manager.db import get_connection, init_database
    from huawei_manager.device_repository import DeviceRepository
    from huawei_manager.services.device_service import DeviceService

    db_file = tmp_path / db_name
    conn = get_connection(str(db_file))
    init_database(conn)
    repo = DeviceRepository(conn)
    if devices:
        for d in devices:
            repo.create_device(d)
    svc = DeviceService(
        inventory_path=str(tmp_path / "vnf_inventory.json"),
        repository=repo,
    )
    return svc, conn


class TestHostValidation:
    """Host deve ser IPv4, IPv6 ou domínio RFC1035 válido."""

    def test_ipv4_host_accepted(self, tmp_path, monkeypatch):
        svc, _conn = _make_svc(tmp_path, monkeypatch)
        dev = svc.add_device(
            {"name": "gw-01", "host": "10.0.0.1", "port": 22}
        )
        assert dev.host == "10.0.0.1"

    def test_ipv4_with_mask_rejected(self, tmp_path, monkeypatch):
        """CIDR no host não é um endpoint válido para device."""
        svc, _conn = _make_svc(tmp_path, monkeypatch)
        with pytest.raises(ValueError, match="host"):
            svc.add_device({"name": "gw-01", "host": "10.0.0.1/24", "port": 22})

    def test_ipv6_host_accepted(self, tmp_path, monkeypatch):
        svc, _conn = _make_svc(tmp_path, monkeypatch)
        dev = svc.add_device({"name": "gw-01", "host": "::1", "port": 22})
        assert dev.host == "::1"

    def test_domain_host_accepted(self, tmp_path, monkeypatch):
        svc, _conn = _make_svc(tmp_path, monkeypatch)
        dev = svc.add_device({"name": "gw-01", "host": "router.example.com", "port": 22})
        assert dev.host == "router.example.com"

    def test_empty_host_rejected(self, tmp_path, monkeypatch):
        svc, _conn = _make_svc(tmp_path, monkeypatch)
        with pytest.raises(ValueError, match="host"):
            svc.add_device({"name": "gw-01", "host": "", "port": 22})

    def test_garbage_host_rejected(self, tmp_path, monkeypatch):
        svc, _conn = _make_svc(tmp_path, monkeypatch)
        with pytest.raises(ValueError, match="host"):
            svc.add_device({"name": "gw-01", "host": "!!!invalid!!!", "port": 22})

    def test_host_with_spaces_is_stripped_and_accepted(self, tmp_path, monkeypatch):
        """Espacos nas bordas sao stripados (limpeza de entrada), não rejeitados."""
        svc, _conn = _make_svc(tmp_path, monkeypatch)
        dev = svc.add_device({"name": "gw-01", "host": " 10.0.0.1 ", "port": 22})
        assert dev.host == "10.0.0.1"

    def test_host_with_internal_space_rejected(self, tmp_path, monkeypatch):
        """Espaco no meio invalida o host."""
        svc, _conn = _make_svc(tmp_path, monkeypatch)
        with pytest.raises(ValueError, match="host"):
            svc.add_device({"name": "gw-01", "host": "10.0.0.1 extra", "port": 22})


class TestUniquenessValidation:
    """Name e host devem ser únicos entre devices."""

    def test_duplicate_name_rejected(self, tmp_path, monkeypatch):
        existing = [Device(id="dev-001", name="gw-01", host="10.0.0.1", port=22)]
        svc, _conn = _make_svc(tmp_path, monkeypatch, devices=existing)
        with pytest.raises(ValueError, match="existe"):
            svc.add_device({"name": "gw-01", "host": "10.0.0.2", "port": 22})

    def test_duplicate_host_rejected(self, tmp_path, monkeypatch):
        existing = [Device(id="dev-001", name="gw-01", host="10.0.0.1", port=22)]
        svc, _conn = _make_svc(tmp_path, monkeypatch, devices=existing)
        with pytest.raises(ValueError, match="existe"):
            svc.add_device({"name": "gw-02", "host": "10.0.0.1", "port": 22})

    def test_different_name_and_host_accepted(self, tmp_path, monkeypatch):
        existing = [Device(id="dev-001", name="gw-01", host="10.0.0.1", port=22)]
        svc, _conn = _make_svc(tmp_path, monkeypatch, devices=existing)
        dev = svc.add_device({"name": "gw-02", "host": "10.0.0.2", "port": 22})
        assert dev.name == "gw-02"
        assert dev.host == "10.0.0.2"

    def test_update_keeps_own_name_and_host(self, tmp_path, monkeypatch):
        """Editar um device mantendo seu próprio name/host não deve falhar."""
        existing = [Device(id="dev-001", name="gw-01", host="10.0.0.1", port=22)]
        svc, _conn = _make_svc(tmp_path, monkeypatch, devices=existing)
        dev = Device(
            id="dev-001", name="gw-01", host="10.0.0.1", port=22,
            type="SWITCH", username="admin",
        )
        updated = svc.update_device(dev, {"name": "gw-01", "host": "10.0.0.1"})
        assert updated.name == "gw-01"

    def test_update_to_another_device_name_rejected(self, tmp_path, monkeypatch):
        existing = [
            Device(id="dev-001", name="gw-01", host="10.0.0.1", port=22),
            Device(id="dev-002", name="gw-02", host="10.0.0.2", port=22),
        ]
        svc, _conn = _make_svc(tmp_path, monkeypatch, devices=existing)
        dev = Device(id="dev-001", name="gw-01", host="10.0.0.1", port=22)
        with pytest.raises(ValueError, match="existe"):
            svc.update_device(dev, {"name": "gw-02", "host": "10.0.0.1"})

    def test_update_to_another_device_host_rejected(self, tmp_path, monkeypatch):
        existing = [
            Device(id="dev-001", name="gw-01", host="10.0.0.1", port=22),
            Device(id="dev-002", name="gw-02", host="10.0.0.2", port=22),
        ]
        svc, _conn = _make_svc(tmp_path, monkeypatch, devices=existing)
        dev = Device(id="dev-001", name="gw-01", host="10.0.0.1", port=22)
        with pytest.raises(ValueError, match="existe"):
            svc.update_device(dev, {"name": "gw-01", "host": "10.0.0.2"})


class TestTypeValidation:
    """Type deve estar na lista permitida."""

    ALLOWED_TYPES = ("ROUTER", "SWITCH", "FIREWALL", "LOAD-BALANCER", "WAN-ACCEL", "AP")

    def test_allowed_types_accepted(self, tmp_path, monkeypatch):
        for i, t in enumerate(self.ALLOWED_TYPES):
            svc, _conn = _make_svc(tmp_path, monkeypatch, db_name=f"test_type_{i}.db")
            dev = svc.add_device({"name": f"dev-{t}", "host": "10.0.0.1", "port": 22, "type": t})
            assert dev.type == t

    def test_invalid_type_rejected(self, tmp_path, monkeypatch):
        svc, _conn = _make_svc(tmp_path, monkeypatch)
        with pytest.raises(ValueError, match="tipo"):
            svc.add_device({"name": "dev-x", "host": "10.0.0.1", "port": 22, "type": "INVALID"})

    def test_default_type_is_router(self, tmp_path, monkeypatch):
        svc, _conn = _make_svc(tmp_path, monkeypatch)
        dev = svc.add_device({"name": "dev-x", "host": "10.0.0.1", "port": 22})
        assert dev.type == "ROUTER"


class TestPortValidation:
    """Porta deve ser inteiro entre 1 e 65535 no serviço."""

    def test_valid_port_accepted(self, tmp_path, monkeypatch):
        svc, _conn = _make_svc(tmp_path, monkeypatch)
        dev = svc.add_device({"name": "gw-01", "host": "10.0.0.1", "port": 2222})
        assert dev.port == 2222

    def test_port_zero_rejected(self, tmp_path, monkeypatch):
        svc, _conn = _make_svc(tmp_path, monkeypatch)
        with pytest.raises(ValueError, match="porta"):
            svc.add_device({"name": "gw-01", "host": "10.0.0.1", "port": 0})

    def test_port_65536_rejected(self, tmp_path, monkeypatch):
        svc, _conn = _make_svc(tmp_path, monkeypatch)
        with pytest.raises(ValueError, match="porta"):
            svc.add_device({"name": "gw-01", "host": "10.0.0.1", "port": 65536})

    def test_negative_port_rejected(self, tmp_path, monkeypatch):
        svc, _conn = _make_svc(tmp_path, monkeypatch)
        with pytest.raises(ValueError, match="porta"):
            svc.add_device({"name": "gw-01", "host": "10.0.0.1", "port": -1})


class TestSaveInventoryDeletionGuard:
    """save_inventory não deve deletar devices sem permissao explicita."""

    def test_save_inventory_rejects_partial_list_without_allow(
        self, tmp_path, monkeypatch
    ):
        """Lista parcial sem allow_deletion deve rejeitar."""
        existing = [
            Device(id="dev-001", name="gw-01", host="10.0.0.1", port=22),
            Device(id="dev-002", name="gw-02", host="10.0.0.2", port=22),
        ]
        svc, _conn = _make_svc(tmp_path, monkeypatch, devices=existing)
        # Lista parcial: so tem dev-001, dev-002 deveria ser preservado.
        partial = [Device(id="dev-001", name="gw-01", host="10.0.0.1", port=22)]
        with pytest.raises(ValueError, match="delet"):
            svc.save_inventory(partial)
        # Nenhum device deve ter sido removido.
        assert svc.load_inventory() == existing or len(svc.load_inventory()) == 2

    def test_save_inventory_allows_deletion_with_flag(self, tmp_path, monkeypatch):
        """com allow_deletion=True, lista parcial pode remover devices."""
        existing = [
            Device(id="dev-001", name="gw-01", host="10.0.0.1", port=22),
            Device(id="dev-002", name="gw-02", host="10.0.0.2", port=22),
        ]
        svc, _conn = _make_svc(tmp_path, monkeypatch, devices=existing)
        partial = [Device(id="dev-001", name="gw-01", host="10.0.0.1", port=22)]
        # Deve funcionar sem levantar erro.
        svc.save_inventory(partial, allow_deletion=True)
        remaining = svc.load_inventory()
        assert len(remaining) == 1
        assert remaining[0].id == "dev-001"

    def test_save_inventory_complete_list_ok(self, tmp_path, monkeypatch):
        """Lista completa (sem delecoes) deve funcionar sem flag."""
        existing = [
            Device(id="dev-001", name="gw-01", host="10.0.0.1", port=22),
            Device(id="dev-002", name="gw-02", host="10.0.0.2", port=22),
        ]
        svc, _conn = _make_svc(tmp_path, monkeypatch, devices=existing)
        svc.save_inventory(existing)
        assert len(svc.load_inventory()) == 2
