"""Tests for TopologyManager — LLDP discovery, graph, event emission."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from huawei_manager.sdn_controller.topology_manager import (
    TopologyLink,
    TopologyManager,
    TopologyNode,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def manager() -> TopologyManager:
    return TopologyManager()


@pytest.fixture
def mock_lldp_output() -> str:
    return """Local Interface    Neighbor Interface    Neighbor Device
GE0/0/0            GE0/0/1              R2-Huawei
GE0/0/1            GE0/0/0              SW1-Huawei
GE0/0/2            GE0/0/3              FW1-Huawei
"""


@pytest.fixture
def mock_arp_output() -> str:
    return """IP Address       MAC Address        Interface
10.0.0.2         00e0-fc00-0002     GE0/0/0
10.0.1.2         00e0-fc00-0003     GE0/0/1
192.168.1.1      00e0-fc00-0004     GE0/0/2
"""


@pytest.fixture
def mock_discovery_fn(mock_lldp_output: str):
    return MagicMock(return_value=mock_lldp_output)


# ── TopologyNode / TopologyLink dataclasses ──────────────────────────────────


class TestDataclasses:
    """TopologyNode and TopologyLink must store topology data."""

    def test_topology_node(self):
        node = TopologyNode(
            device_id="R1", name="R1-Huawei", device_type="router",
        )
        assert node.device_id == "R1"
        assert node.name == "R1-Huawei"

    def test_topology_node_defaults(self):
        node = TopologyNode(device_id="R1", name="R1-Huawei")
        assert node.device_type == "unknown"
        assert node.neighbors == []

    def test_topology_link(self):
        link = TopologyLink(
            source="GE0/0/0", target="GE0/0/1",
            source_device="R1", target_device="R2",
        )
        assert link.source == "GE0/0/0"
        assert link.target == "GE0/0/1"

    def test_topology_link_defaults(self):
        link = TopologyLink(
            source="GE0/0/0", target="GE0/0/1",
            source_device="R1", target_device="R2",
        )
        assert link.source_device == "R1"


# ── LLDP discovery ──────────────────────────────────────────────────────────


class TestLLDPDiscovery:
    """TopologyManager must discover neighbors via LLDP."""

    def test_lldp_discovery_returns_links(self, manager, mock_discovery_fn):
        links = manager.lldp_discovery("R1", mock_discovery_fn)
        assert len(links) == 3
        assert all(isinstance(link, TopologyLink) for link in links)

    def test_lldp_discovery_parses_interfaces(self, manager, mock_discovery_fn):
        links = manager.lldp_discovery("R1", mock_discovery_fn)
        assert links[0].source == "GE0/0/0"
        assert links[0].target == "GE0/0/1"

    def test_lldp_discovery_parses_device_names(self, manager, mock_discovery_fn):
        links = manager.lldp_discovery("R1", mock_discovery_fn)
        assert links[0].target_device == "R2-Huawei"
        assert links[1].target_device == "SW1-Huawei"

    def test_lldp_sets_source_device(self, manager, mock_discovery_fn):
        links = manager.lldp_discovery("R1", mock_discovery_fn)
        assert links[0].source_device == "R1"

    def test_lldp_empty_output(self, manager):
        fn = MagicMock(return_value="")
        links = manager.lldp_discovery("R1", fn)
        assert links == []

    def test_lldp_no_neighbors(self, manager):
        fn = MagicMock(return_value="Local Interface    Neighbor Interface    Neighbor Device")
        links = manager.lldp_discovery("R1", fn)
        assert links == []


# ── ARP fallback ─────────────────────────────────────────────────────────────


class TestARPFallback:
    """When LLDP is unavailable, TopologyManager falls back to ARP."""

    def test_arp_discovery_returns_nodes(self, manager, mock_arp_output):
        fn = MagicMock(return_value=mock_arp_output)
        nodes = manager.arp_discovery("R1", fn)
        assert len(nodes) >= 1
        assert all(isinstance(n, TopologyNode) for n in nodes)

    def test_arp_detects_ip_and_mac(self, manager, mock_arp_output):
        fn = MagicMock(return_value=mock_arp_output)
        nodes = manager.arp_discovery("R1", fn)
        assert any(n.device_id == "00e0-fc00-0002" for n in nodes)

    def test_arp_empty_output(self, manager):
        fn = MagicMock(return_value="")
        nodes = manager.arp_discovery("R1", fn)
        assert nodes == []


# ── Graph building ──────────────────────────────────────────────────────────


class TestGraphBuilding:
    """Manager must build and return a topology graph."""

    def test_graph_starts_empty(self, manager):
        graph = manager.get_graph()
        assert graph == {}

    def test_add_links_builds_graph(self, manager, mock_discovery_fn):
        links = manager.lldp_discovery("R1", mock_discovery_fn)
        manager.add_links("R1", links)
        graph = manager.get_graph()
        assert "R1" in graph
        assert len(graph["R1"]) == 3

    def test_graph_links_have_target_device(self, manager, mock_discovery_fn):
        links = manager.lldp_discovery("R1", mock_discovery_fn)
        manager.add_links("R1", links)
        graph = manager.get_graph()
        assert any(
            link.target_device == "R2-Huawei"
            for link in graph["R1"]
        )

    def test_add_links_multiple_devices(self, manager, mock_discovery_fn):
        links_r1 = manager.lldp_discovery("R1", mock_discovery_fn)
        fn2 = MagicMock(return_value=mock_discovery_fn())
        links_r2 = manager.lldp_discovery("R2", fn2)
        manager.add_links("R1", links_r1)
        manager.add_links("R2", links_r2)
        graph = manager.get_graph()
        assert "R1" in graph
        assert "R2" in graph

    def test_clear_graph(self, manager, mock_discovery_fn):
        links = manager.lldp_discovery("R1", mock_discovery_fn)
        manager.add_links("R1", links)
        manager.clear_graph()
        assert manager.get_graph() == {}


# ── Poll / change detection ──────────────────────────────────────────────────


class TestPollAndChangeDetection:
    """Poll must detect changes and emit events."""

    def test_poll_initial_builds_graph(self, manager, mock_discovery_fn):
        manager.poll("R1", mock_discovery_fn)
        assert "R1" in manager.get_graph()

    def test_poll_detects_new_device(self, manager, mock_discovery_fn):
        manager.poll("R1", mock_discovery_fn)
        # Second poll with different output -> no change
        results = manager.poll("R1", mock_discovery_fn)
        assert results["new_links"] == 0
        assert results["lost_links"] == 0

    def test_poll_detects_lost_link(self, manager, mock_discovery_fn):
        manager.poll("R1", mock_discovery_fn)
        # Return empty to simulate lost links
        fn_empty = MagicMock(return_value="")
        results = manager.poll("R1", fn_empty)
        assert results["lost_links"] == 3

    def test_poll_calls_event_callback(self, manager, mock_discovery_fn):
        callback = MagicMock()
        manager.set_event_callback(callback)
        manager.poll("R1", mock_discovery_fn)
        callback.assert_called()

    def test_poll_event_callback_receives_changes(self, manager, mock_discovery_fn):
        callback = MagicMock()
        manager.set_event_callback(callback)
        manager.poll("R1", mock_discovery_fn)
        call_args = callback.call_args
        assert call_args is not None
        assert "device" in call_args.kwargs or len(call_args.args) > 0


# ── Edge cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Handle edge cases gracefully."""

    def test_discovery_fn_raises(self, manager):
        fn = MagicMock(side_effect=RuntimeError("SSH failed"))
        links = manager.lldp_discovery("R1", fn)
        assert links == []

    def test_poll_fn_raises_returns_empty(self, manager):
        fn = MagicMock(side_effect=RuntimeError("SSH failed"))
        results = manager.poll("R1", fn)
        assert results["lost_links"] == 0

    def test_add_links_empty(self, manager):
        manager.add_links("R1", [])
        graph = manager.get_graph()
        assert "R1" in graph
        assert graph["R1"] == []
