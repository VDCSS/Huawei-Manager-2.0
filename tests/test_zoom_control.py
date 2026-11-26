"""TDD do controle de zoom (lupa + popup redondo).

A suíte cobre: faixa 50–150%, campo com '%' no mesmo widget, botões
circulares, ausência de sobreposição, ancoragem na tela, persistência
e estabilidade do layout quando a lupa aparece/desaparece.
"""
from __future__ import annotations

import re

from PySide6.QtCore import QEvent, QPointF, QSettings, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QToolButton,
    QWidget,
)


def _make_control(qtbot, tmp_path):
    from huawei_manager.widgets.zoom_control import ZoomControl

    settings = QSettings(
        str(tmp_path / "zoom.ini"), QSettings.Format.IniFormat
    )
    control = ZoomControl(settings=settings)
    qtbot.addWidget(control)
    return control, settings


def test_lupa_hidden_at_100_and_visible_at_125_and_85(qtbot, tmp_path):
    zc, _ = _make_control(qtbot, tmp_path)

    assert zc.zoom() == 100
    assert zc.magnifier.isHidden()

    zc.set_zoom(125)
    assert not zc.magnifier.isHidden()

    zc.set_zoom(85)
    assert not zc.magnifier.isHidden()

    zc.set_zoom(100)
    assert zc.magnifier.isHidden()


def test_slot_reserved_prevents_layout_jump(qtbot, tmp_path):
    zc, _ = _make_control(qtbot, tmp_path)

    host = QWidget()
    qtbot.addWidget(host)
    layout = QHBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(zc.slot)
    dummy = QWidget()
    dummy.setFixedSize(30, 30)
    layout.addWidget(dummy)
    host.show()
    qtbot.waitExposed(host)
    QApplication.processEvents()

    x_before = dummy.x()
    zc.set_zoom(150)
    QApplication.processEvents()
    assert zc.slot.width() == 34
    assert dummy.x() == x_before


def test_ctrl_plus_minus_clamp_50_150(qtbot, tmp_path):
    zc, _ = _make_control(qtbot, tmp_path)

    for _ in range(10):
        zc.step(10)
    assert zc.zoom() == 150
    zc.step(10)
    assert zc.zoom() == 150

    for _ in range(20):
        zc.step(-10)
    assert zc.zoom() == 50
    zc.step(-10)
    assert zc.zoom() == 50


def test_ctrl_zero_resets_and_closes_popup(qtbot, tmp_path):
    zc, _ = _make_control(qtbot, tmp_path)
    zc.set_zoom(125)
    zc.show_popup()
    assert zc.popup.isVisible()

    zc.reset()
    assert zc.zoom() == 100
    assert not zc.magnifier.isVisible()
    assert zc.popup.isHidden()


def test_field_has_percent_inside_same_widget(qtbot, tmp_path):
    zc, _ = _make_control(qtbot, tmp_path)
    spin = zc.popup.findChild(QSpinBox)
    assert spin is not None
    assert spin.suffix() == "%"
    assert spin.buttonSymbols() == QSpinBox.ButtonSymbols.NoButtons
    assert spin.minimum() == 50
    assert spin.maximum() == 150


def test_spinbox_clamps_40_to_50_and_200_to_150(qtbot, tmp_path):
    zc, _ = _make_control(qtbot, tmp_path)
    spin = zc.popup.findChild(QSpinBox)
    assert spin is not None

    spin.setValue(200)
    assert zc.zoom() == 150
    spin.setValue(40)
    assert zc.zoom() == 50


def test_all_modal_buttons_are_round(qtbot, tmp_path):
    zc, _ = _make_control(qtbot, tmp_path)
    buttons = zc.popup.findChildren(QToolButton) + zc.popup.findChildren(QPushButton)
    assert len(buttons) == 3
    for btn in buttons:
        assert re.search(r"border-radius:\s*\d+px", btn.styleSheet())

    plus, minus = zc.plus_btn, zc.minus_btn
    assert plus.width() == plus.height() == 40
    assert minus.width() == minus.height() == 40
    assert zc.reset_btn.width() == zc.reset_btn.height() == 56


def test_popup_buttons_order_plus_minus_reset(qtbot, tmp_path):
    zc, _ = _make_control(qtbot, tmp_path)
    widgets = [
        zc.popup.layout().itemAt(i).widget()
        for i in range(zc.popup.layout().count())
    ]
    assert widgets == [zc.spin, zc.plus_btn, zc.minus_btn, zc.reset_btn]


def test_no_child_overlap_in_popup(qtbot, tmp_path):
    zc, _ = _make_control(qtbot, tmp_path)
    zc.popup.show()
    qtbot.waitExposed(zc.popup)
    QApplication.processEvents()

    seq = [zc.spin, zc.plus_btn, zc.minus_btn, zc.reset_btn]
    assert zc.popup.width() == 256
    assert zc.spin.width() == 72
    assert zc.plus_btn.width() == 40
    assert zc.minus_btn.width() == 40
    assert zc.reset_btn.width() == 56
    for first, second in zip(seq, seq[1:]):
        assert not first.geometry().intersects(second.geometry())
        gap = second.geometry().left() - first.geometry().right()
        assert gap >= 8
    zc.popup.hide()


def test_plus_and_minus_have_2px_border_and_radius_half(qtbot, tmp_path):
    zc, _ = _make_control(qtbot, tmp_path)
    for btn in (zc.plus_btn, zc.minus_btn):
        css = btn.styleSheet()
        assert re.search(r"border:\s*2px solid", css)
        assert re.search(r"border-radius:\s*20px", css)


def test_hover_rule_keeps_circular_radius_and_thickens_border(qtbot, tmp_path):
    zc, _ = _make_control(qtbot, tmp_path)
    css = zc.plus_btn.styleSheet() + zc.minus_btn.styleSheet()
    assert re.search(r":hover\s*\{[^}]*border:\s*2px solid", css)
    assert re.search(r":hover\s*\{[^}]*border-radius:\s*20px", css)


def test_hover_does_not_change_geometry(qtbot, tmp_path):
    zc, _ = _make_control(qtbot, tmp_path)
    zc.popup.show()
    qtbot.waitExposed(zc.popup)
    QApplication.processEvents()
    before = [w.geometry() for w in (zc.plus_btn, zc.minus_btn, zc.reset_btn)]

    # Reaplicar o stylesheet de hover não pode alterar fixed sizes.
    zc.plus_btn.setStyleSheet(zc.plus_btn.styleSheet())
    zc.minus_btn.setStyleSheet(zc.minus_btn.styleSheet())
    QApplication.processEvents()
    after = [w.geometry() for w in (zc.plus_btn, zc.minus_btn, zc.reset_btn)]
    assert after == before
    zc.popup.hide()


def test_popup_anchored_and_inside_screen(qtbot, tmp_path):
    zc, _ = _make_control(qtbot, tmp_path)
    zc.set_zoom(125)
    zc.show_popup()
    qtbot.waitExposed(zc.popup)

    screen = QApplication.primaryScreen().availableGeometry()
    geo = zc.popup.geometry()
    assert screen.contains(geo)
    assert geo.top() >= zc.magnifier.mapToGlobal(zc.magnifier.rect().bottomLeft()).y()
    zc.popup.hide()


def test_click_outside_closes_popup(qtbot, tmp_path):
    zc, _ = _make_control(qtbot, tmp_path)
    zc.set_zoom(125)
    zc.show_popup()
    assert zc.popup.isVisible()

    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(9999, 9999),
        QtMouseLeft(),
        QtMouseLeft(),
        Qt.NoModifier,
    )
    QApplication.sendEvent(QApplication.instance(), event)
    QApplication.processEvents()
    assert zc.popup.isHidden()


def QtMouseLeft():
    from PySide6.QtCore import Qt

    return Qt.MouseButton.LeftButton


def test_zoom_persists_in_qsettings(qtbot, tmp_path):
    zc, settings = _make_control(qtbot, tmp_path)
    zc.set_zoom(137)
    assert int(settings.value("ui_zoom", 100)) == 137

    from huawei_manager.widgets.zoom_control import ZoomControl

    other = ZoomControl(
        settings=QSettings(str(tmp_path / "zoom2.ini"), QSettings.Format.IniFormat)
    )
    assert other.zoom() == 100
    reread = QSettings(str(tmp_path / "zoom.ini"), QSettings.Format.IniFormat)
    ZoomControl = __import__(
        "huawei_manager.widgets.zoom_control", fromlist=["ZoomControl"]
    ).ZoomControl
    assert ZoomControl(settings=reread).zoom() == 137


def test_qss_font_sizes_scale():
    from huawei_manager.themes import scale_qss

    tiny = scale_qss("QWidget { font-size: 10px; } #x { font-size: 12.5px; }", 1.5)
    assert "font-size: 15px" in tiny
    assert "font-size: 18.75px" in tiny
    assert scale_qss("QWidget { font-size: 10px; }", 0.5).count("font-size: 5px") == 1


class TestZoomAppIntegration:
    @staticmethod
    def _boot():
        import huawei_manager._config as cfg

        if cfg._secrets is None or cfg.audit is None:
            cfg._INITIALIZED = False
            cfg.init()
        from huawei_manager._app import get_app

        qapp = get_app()
        return qapp

    def test_app_has_zoom_slot_and_no_window_controls(self, tmp_path):
        from unittest.mock import patch

        from huawei_manager.app import HuaweiRouterApp

        qapp = self._boot()
        settings = QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)
        with (
            patch("huawei_manager.app.apply_theme"),
            patch("huawei_manager.app._preferences", return_value=settings),
        ):
            window = HuaweiRouterApp()
        try:
            assert window.zoom_control is not None
            assert window.findChild(QWidget, "zoomSlot") is not None
            assert window.findChild(QToolButton, "zoomMagnifierBtn") is not None
            assert window.findChild(QWidget, "windowControls") is None
        finally:
            window.close()
            qapp.processEvents()

    def test_zoom_signal_reapplies_theme_with_factor(self, tmp_path):
        from unittest.mock import patch

        from huawei_manager.app import HuaweiRouterApp

        qapp = self._boot()
        settings = QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)
        with (
            patch("huawei_manager.app.apply_theme") as apply,
            patch("huawei_manager.app._preferences", return_value=settings),
        ):
            window = HuaweiRouterApp()
            try:
                apply.reset_mock()
                window.zoom_control.set_zoom(125)
                apply.assert_called_once_with("dark", zoom=1.25)
            finally:
                window.close()
                qapp.processEvents()
