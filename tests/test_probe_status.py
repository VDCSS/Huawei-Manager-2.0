"""Testes para simulate_status e probe_vnfs — transições de status."""
from __future__ import annotations

import random
import socket
from unittest.mock import MagicMock, patch

from huawei_manager.vnf_models import VNF
from huawei_manager.vnf_probe import clear_probe_cache, probe_vnfs, simulate_status


def _reset_mock_last_update():
    """Reseta o timer do mock para forçar execução do simulate_status."""
    import huawei_manager.vnf_probe as probe_mod
    probe_mod._probe.mock_last_update = 0.0


def _reset_probe_cache():
    """Limpa o cache de probe entre testes."""
    clear_probe_cache()


def _make_vnf(status: str = "unknown", host: str = "10.0.0.1") -> VNF:
    return VNF(id="test-001", name="test-vnf", host=host, port=22,
               type="ROUTER", status=status)


class TestSimulateStatusUnknown:
    def test_unknown_transitions_to_online(self):
        _reset_mock_last_update()
        vnf = _make_vnf(status="unknown")
        random.seed(9999)
        result = simulate_status([vnf])
        assert result[0].status in ("online", "offline")
        assert result[0].status != "unknown"

    def test_unknown_always_transitions(self):
        _reset_mock_last_update()
        transitions = set()
        for seed in range(200):
            _reset_mock_last_update()
            vnf = _make_vnf(status="unknown")
            random.seed(seed)
            simulate_status([vnf])
            transitions.add(vnf.status)
        assert "unknown" not in transitions
        assert transitions <= {"online", "offline"}

    def test_unknown_80pct_online(self):
        _reset_mock_last_update()
        online_count = 0
        for seed in range(100):
            _reset_mock_last_update()
            vnf = _make_vnf(status="unknown")
            random.seed(seed)
            simulate_status([vnf])
            if vnf.status == "online":
                online_count += 1
        assert 60 <= online_count <= 95

    def test_unknown_20pct_offline(self):
        _reset_mock_last_update()
        offline_count = 0
        for seed in range(100):
            _reset_mock_last_update()
            vnf = _make_vnf(status="unknown")
            random.seed(seed)
            simulate_status([vnf])
            if vnf.status == "offline":
                offline_count += 1
        assert 5 <= offline_count <= 40

    def test_offline_can_transition_to_online(self):
        _reset_mock_last_update()
        online_count = 0
        for seed in range(200):
            _reset_mock_last_update()
            vnf = _make_vnf(status="offline")
            random.seed(seed)
            simulate_status([vnf])
            if vnf.status == "online":
                online_count += 1
        assert online_count > 0

    def test_online_can_transition_to_offline(self):
        _reset_mock_last_update()
        offline_count = 0
        for seed in range(500):
            _reset_mock_last_update()
            vnf = _make_vnf(status="online")
            random.seed(seed)
            simulate_status([vnf])
            if vnf.status == "offline":
                offline_count += 1
        assert offline_count > 0

    def test_online_does_not_go_to_unknown(self):
        _reset_mock_last_update()
        unknown_count = 0
        for seed in range(500):
            _reset_mock_last_update()
            vnf = _make_vnf(status="online")
            random.seed(seed)
            simulate_status([vnf])
            if vnf.status == "unknown":
                unknown_count += 1
        assert unknown_count == 0

    def test_empty_list_returns_empty(self):
        _reset_mock_last_update()
        result = simulate_status([])
        assert result == []

    def test_multiple_vnfs_independent(self):
        _reset_mock_last_update()
        random.seed(42)
        vnfs = [_make_vnf(status="unknown", host=f"10.0.0.{i}") for i in range(10)]
        result = simulate_status(vnfs)
        statuses = {v.status for v in result}
        assert statuses <= {"online", "offline"}
        assert len(statuses) == 2


# ══════════════════════════════════════════════════════════════════════════
#  probe_vnfs — real TCP probe com unknown status
# ══════════════════════════════════════════════════════════════════════════


class TestProbeVnfs:
    def test_unknown_status_gets_probed(self):
        """VNFs com status unknown são incluídos no probe TCP."""
        _reset_probe_cache()
        vnf = _make_vnf(status="unknown", host="10.0.0.99")
        with patch("huawei_manager.vnf_probe.socket.create_connection") as mock_sock:
            mock_sock.return_value = MagicMock()
            result = probe_vnfs([vnf], timeout=1)
            assert vnf.status in ("online", "offline")

    def test_probe_online_on_tcp_success(self):
        """Conexão TCP bem-sucedida → status online."""
        _reset_probe_cache()
        vnf = _make_vnf(status="unknown")
        with patch("huawei_manager.vnf_probe.socket.create_connection") as mock_sock:
            mock_sock.return_value = MagicMock()
            result = probe_vnfs([vnf], timeout=1)
            assert vnf.status == "online"

    def test_probe_offline_on_tcp_failure(self):
        """Exceção OSError → status offline."""
        _reset_probe_cache()
        vnf = _make_vnf(status="unknown")
        with patch("huawei_manager.vnf_probe.socket.create_connection") as mock_sock:
            mock_sock.side_effect = OSError("Connection refused")
            result = probe_vnfs([vnf], timeout=1)
            assert vnf.status == "offline"

    def test_probe_offline_on_timeout(self):
        """TimeoutError → status offline."""
        _reset_probe_cache()
        vnf = _make_vnf(status="unknown")
        with patch("huawei_manager.vnf_probe.socket.create_connection") as mock_sock:
            mock_sock.side_effect = TimeoutError("timed out")
            result = probe_vnfs([vnf], timeout=1)
            assert vnf.status == "offline"

    def test_probe_skips_vnf_without_host(self):
        """VNFs sem host são ignorados (mantêm status original)."""
        _reset_probe_cache()
        vnf = _make_vnf(status="unknown", host="")
        result = probe_vnfs([vnf], timeout=1)
        assert vnf.status == "unknown"

    def test_probe_uses_cache(self):
        """Cache hit evita nova conexão TCP."""
        _reset_probe_cache()
        vnf = _make_vnf(status="unknown")
        with patch("huawei_manager.vnf_probe.socket.create_connection") as mock_sock:
            mock_sock.return_value = MagicMock()
            probe_vnfs([vnf], timeout=1)
            assert vnf.status == "online"
            call_count_1 = mock_sock.call_count

            vnf2 = _make_vnf(status="unknown")
            probe_vnfs([vnf2], timeout=1)
            call_count_2 = mock_sock.call_count
            assert call_count_2 == call_count_1, "Cache should prevent second probe"

    def test_probe_clear_cache(self):
        """clear_probe_cache() força novo probe no próximo ciclo."""
        _reset_probe_cache()
        vnf = _make_vnf(status="unknown")
        with patch("huawei_manager.vnf_probe.socket.create_connection") as mock_sock:
            mock_sock.return_value = MagicMock()
            probe_vnfs([vnf], timeout=1)
            clear_probe_cache()
            vnf2 = _make_vnf(status="unknown")
            probe_vnfs([vnf2], timeout=1)
            assert mock_sock.call_count == 2

    def test_probe_mixed_status(self):
        """Mistura de unknown, online e offline: todos são tratados corretamente."""
        _reset_probe_cache()
        vnfs = [
            _make_vnf(status="unknown", host="10.0.0.1"),
            _make_vnf(status="online", host="10.0.0.2"),
            _make_vnf(status="offline", host="10.0.0.3"),
        ]
        with patch("huawei_manager.vnf_probe.socket.create_connection") as mock_sock:
            mock_sock.return_value = MagicMock()
            result = probe_vnfs(vnfs, timeout=1)
            for v in result:
                assert v.status in ("online", "offline")
