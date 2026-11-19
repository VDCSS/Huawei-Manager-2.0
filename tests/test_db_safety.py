"""Segurança do banco: nenhum teste deve tocar o DB real ~/.huawei_manager/inventory.db.

Regressão do incidente de 18/11/2026: durante `make ci`, um teste chamou
``DeviceService.save_inventory()`` contra o repositório SQLite real e a
reconciliação destrutiva (``existing - current``) apagou 3 devices.

Camadas de defesa:
1. ``tests/conftest.py`` — fixture autouse define ``HW_DATA_DIR`` /
   ``HUAWEI_MANAGER_DIR`` → ``tmp_path`` para TODOS os testes.
2. ``huawei_manager/db.py`` — ``get_database_path()`` levanta erro se sob
   pytest e nenhuma das env vars acima estiver definida (fail-closed:
   nunca abre o banco real silenciosamente durante testes).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


def _real_db_path() -> Path:
    return Path.home() / ".huawei_manager" / "inventory.db"


class TestDatabasePathNeverRealDuringPytest:
    """get_database_path() nunca deve resolver para o banco real sob pytest."""

    def test_returns_tmp_path_not_real_db(self, monkeypatch: pytest.MonkeyPatch):
        """Com HW_DATA_DIR definido (conftest), caminho é tmp_path, nunca real."""
        # Não faz delenv: o conftest já define HW_DATA_DIR para tmp_path.
        # O teste verifica que get_database_path() respeita o sandbox.

        from huawei_manager.db import get_database_path

        path = get_database_path()
        assert path.name == "inventory.db"
        real = _real_db_path()
        assert str(path) != str(real), "get_database_path() não deve retornar o banco real sob pytest"

    def test_raises_when_no_custom_dir_during_pytest(self, monkeypatch):
        """Sem HW_DATA_DIR/HUAWEI_MANAGER_DIR sob pytest → RuntimeError (fail-closed)."""
        monkeypatch.delenv("HW_DATA_DIR", raising=False)
        monkeypatch.delenv("HUAWEI_MANAGER_DIR", raising=False)
        # PYTEST_CURRENT_TEST é definido automaticamente pelo pytest durante a execução.
        assert "PYTEST_CURRENT_TEST" in os.environ, "teste deve rodar sob pytest"

        from huawei_manager.db import get_database_path

        with pytest.raises(RuntimeError, match="banco real"):
            get_database_path()


class TestSaveInventoryNeverDeletesRealDb:
    """DeviceService.save_inventory() nunca deve deletar do banco real."""

    def test_uses_sandbox_dir_not_home(self, monkeypatch, tmp_path):
        """Com HW_DATA_DIR apontando para tmp_path, save_inventory opera lá."""
        sandbox = tmp_path / "sandbox"
        monkeypatch.setenv("HW_DATA_DIR", str(sandbox))

        from huawei_manager.device_models import Device
        from huawei_manager.services.device_service import DeviceService

        repo = __import__(
            "huawei_manager.device_repository", fromlist=["DeviceRepository"]
        ).DeviceRepository
        from huawei_manager.db import get_connection, init_database

        conn = get_connection(sandbox / "inventory.db")
        try:
            init_database(conn)
            svc = DeviceService(
                inventory_path=str(sandbox / "vnf_inventory.json"),
                repository=repo(conn),
            )
            dev = Device(
                id="dev-sandbox", name="Sandbox", host="10.0.0.1", port=22
            )
            svc.save_inventory([dev])

            # O banco real em ~/.huawei_manager não deve conter dev-sandbox.
            real_conn = get_connection(_real_db_path())
            try:
                row = real_conn.execute(
                    "SELECT COUNT(*) FROM devices WHERE id = ?", ("dev-sandbox",)
                ).fetchone()
                assert row[0] == 0, "banco real foi poluído pelo teste"
            finally:
                real_conn.close()
        finally:
            conn.close()
