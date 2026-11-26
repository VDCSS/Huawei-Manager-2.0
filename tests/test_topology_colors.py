"""Cores dos nós da topologia: status manda, tipo só informa."""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

import huawei_manager.constants as C
from huawei_manager.device_models import Device
from huawei_manager.topology import TopologyCanvas
from huawei_manager.topology_items import _to_qfont, node_color


@pytest.fixture(autouse=True)
def _app():
    return QApplication.instance() or QApplication([])


def _device(status: str = "online", device_type: str = "ROUTER") -> Device:
    return Device(
        id="r1", name="R1", host="10.0.0.1", port=22,
        type=device_type, status=status, username="admin",
    )


class TestNodeColor:
    def test_up_is_green(self):
        assert node_color(_device("online"), None) == C.NEON_GREEN

    def test_down_is_red(self):
        assert node_color(_device("offline"), None) == C.NEON_RED

    def test_unknown_is_amber(self):
        assert node_color(_device("unknown"), None) == C.NEON_AMBER

    def test_connected_is_neon_blue(self):
        assert node_color(_device("online"), "r1") == C.NEON_CYAN

    def test_connected_overrides_down(self):
        assert node_color(_device("offline"), "r1") == C.NEON_CYAN

    def test_connected_id_must_match(self):
        assert node_color(_device("online"), "other") == C.NEON_GREEN


class TestCanvasConnectedState:
    def test_set_connected_device_updates_state(self):
        canvas = TopologyCanvas()
        canvas.update_devices([_device()])
        canvas.set_connected_device("r1")
        assert canvas._connected_id == "r1"
        canvas.set_connected_device(None)
        assert canvas._connected_id is None


def test_canvas_font_follows_zoom():
    original = C.ui_zoom()
    try:
        C.set_ui_zoom(1.5)
        assert _to_qfont(C.FONT_UI_MEDIUM).pointSize() == round(
            C.FONT_UI_MEDIUM[1] * 1.5
        )
        C.set_ui_zoom(0.5)
        assert _to_qfont(C.FONT_UI_MEDIUM).pointSize() == max(
            1, round(C.FONT_UI_MEDIUM[1] * 0.5)
        )
    finally:
        C.set_ui_zoom(original)
