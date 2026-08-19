"""Testes para grade adaptativa da topologia — reflow em janelas estreitas (A1)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication

from huawei_manager.device_models import Device
from huawei_manager.topology import TopologyCanvas


@pytest.fixture(autouse=True)
def _app():
    app = QApplication.instance() or QApplication([])
    yield app


def _canvas_with_devices(n: int = 8) -> TopologyCanvas:
    canvas = TopologyCanvas()
    devices = [
        Device(
            id=f"r{i}", name=f"R{i}", host=f"10.0.0.{i}",
            port=22, type="ROUTER", status="online",
        )
        for i in range(n)
    ]
    canvas._devices = devices
    canvas._device_map = {v.id: v for v in devices}
    return canvas


class TestAdaptiveGrid:
    def test_narrow_viewport_reflows_to_fewer_columns(self):
        canvas = _canvas_with_devices(8)
        vp = canvas._view.viewport()
        with patch.object(vp, "width", return_value=534), \
             patch.object(vp, "height", return_value=400):
            positions = canvas._layout()
        xs = sorted({round(x, 1) for x, _ in positions.values()})
        assert len(xs) <= 3
        for x, _ in positions.values():
            assert x + canvas.NODE_W / 2 <= 534

    def test_wide_viewport_keeps_four_columns(self):
        canvas = _canvas_with_devices(8)
        vp = canvas._view.viewport()
        with patch.object(vp, "width", return_value=1220), \
             patch.object(vp, "height", return_value=700):
            positions = canvas._layout()
        xs = sorted({round(x, 1) for x, _ in positions.values()})
        assert len(xs) == 4

    def test_scene_rect_equals_viewport(self):
        canvas = _canvas_with_devices(8)
        vp = canvas._view.viewport()
        with patch.object(vp, "width", return_value=534), \
             patch.object(vp, "height", return_value=400):
            canvas._layout()
        rect = canvas._scene.sceneRect()
        assert rect.width() == 534
        assert rect.height() >= 400