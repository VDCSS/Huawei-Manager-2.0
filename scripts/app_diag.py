#!/usr/bin/env python3
"""
Diagnostic: launches the ACTUAL HuaweiRouterApp with debug logging,
dumps the full widget tree, and takes a QWidget.grab() screenshot.
This isolates the issue to the app code itself (NOT QSS).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget


def _dump_tree(w: QWidget, depth: int = 0, max_depth: int = 6) -> None:
    geo = w.geometry()
    vis = w.isVisible()
    ena = w.isEnabled()
    cls = type(w).__name__
    name = w.objectName() or ""
    text = ""
    if hasattr(w, "text"):
        t = w.text()
        if t:
            text = f' text="{t[:50]}"'
    style = w.styleSheet()[:80] if w.styleSheet() else ""
    style_info = f' qss="{style}"' if style else ""
    prefix = "  " * depth
    print(f"{prefix}{cls}({name}){text} vis={vis} ena={ena} geo={geo.width()}x{geo.height()}@{geo.x()},{geo.y()}{style_info}")
    if depth < max_depth:
        for child in w.children():
            if isinstance(child, QWidget):
                _dump_tree(child, depth + 1, max_depth)


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    platform = app.platformName() if hasattr(app, 'platformName') else 'unknown'
    print(f"Platform: {platform}")

    _root = Path(__file__).resolve().parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    if str(_root / "src") not in sys.path:
        sys.path.insert(0, str(_root / "src"))

    from huawei_manager._app import apply_theme, get_app
    from huawei_manager.app import HuaweiRouterApp

    app = get_app()
    apply_theme("dark")

    print("\n=== Creating HuaweiRouterApp ===")
    window = HuaweiRouterApp()
    window.show()
    window.raise_()
    window.activateWindow()

    for _ in range(15):
        app.processEvents()
        time.sleep(0.05)

    print(f"\n=== Window geometry: {window.width()}x{window.height()} ===")
    print(f"=== Central widget: {window.centralWidget()} ===")

    print("\n=== FULL WIDGET TREE (depth=8) ===")
    _dump_tree(window, max_depth=8)

    print("\n=== Window.grab() screenshot ===")
    pixmap = window.grab()
    img = pixmap.toImage()
    w, h = img.width(), img.height()
    print(f"Screenshot size: {w}x{h}")

    bright = 0
    total_sampled = 0
    for y in range(0, h, 3):
        for x in range(0, w, 3):
            c = img.pixelColor(x, y)
            if c.red() + c.green() + c.blue() > 100:
                bright += 1
            total_sampled += 1
    pct = (bright / max(total_sampled, 1)) * 100
    print(f"Bright pixels (sampled): {bright}/{total_sampled} = {pct:.2f}%")

    out_dir = Path(__file__).parent / "diag_screenshots"
    out_dir.mkdir(exist_ok=True)
    pixmap.save(str(out_dir / "full_app_wayland.png"))
    print(f"Saved: scripts/diag_screenshots/full_app_wayland.png")

    print("\n=== Per-page geometry check ===")
    container = window._page_container
    print(f"Page container: {type(container).__name__} geo={container.width()}x{container.height()}")
    print(f"Current widget: {container.currentWidget()}")
    for key, page_w in window.pages.items():
        geo = page_w.geometry()
        print(f"  page '{key}': {type(page_w).__name__} geo={geo.width()}x{geo.height()} vis={page_w.isVisible()}")

    print("\n=== Header children ===")
    for child in window.children():
        if isinstance(child, QWidget):
            cgeo = child.geometry()
            print(f"  Top-level child: {type(child).__name__}({child.objectName()}) geo={cgeo.width()}x{cgeo.height()} vis={child.isVisible()}")

    from PySide6.QtCore import QTimer
    QTimer.singleShot(2000, app.quit)
    app.exec()


if __name__ == "__main__":
    main()
