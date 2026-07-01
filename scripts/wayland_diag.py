#!/usr/bin/env python3
"""
Diagnostic script: tests QSS layer by layer on Wayland to find which rule(s)
cause blank/dark rendering.

Usage:
  python scripts/wayland_diag.py              # runs each test sequentially
  QT_QPA_PLATFORM=offscreen python scripts/wayland_diag.py  # baseline comparison

Each test creates a minimal window with 3 QLabel widgets + 3 QPushButton widgets.
It applies ONE QSS rule at a time and takes a screenshot.
If the screenshot has < 1% bright pixels, that QSS rule is flagged as problematic.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QScreen
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# ─── QSS RULES TO TEST (one per test) ────────────────────────────────
TESTS: list[tuple[str, str]] = [
    # (name, qss)
    ("0_no_qss", ""),
    ("1_global_widget", "QWidget { background-color: #0d0d1a; color: #e0e0ff; }"),
    ("2_global_widget_with_font", "QWidget { background-color: #0d0d1a; color: #e0e0ff; font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 10pt; }"),
    ("3_qpushbutton", "QPushButton { background-color: #13132b; color: #e0e0ff; border: 1px solid #00e5ff; border-radius: 6px; padding: 6px 16px; }"),
    ("4_qlabel_transparent", "QLabel { background: transparent; color: #e0e0ff; }"),
    ("5_qlabel_colored", "QLabel { background-color: #0d0d1a; color: #e0e0ff; }"),
    ("6_qlineedit", "QLineEdit { background-color: #1a1a30; color: #e0e0ff; border-bottom: 2px solid #00e5ff; }"),
    ("7_qtextedit", "QTextEdit { background-color: #1a1a30; color: #c8c8ff; border: 1px solid #2a2a4a; }"),
    ("8_qscrollbar", "QScrollBar:vertical { background: #1a1a30; width: 8px; } QScrollBar::handle:vertical { background: #00e5ff; min-height: 30px; border-radius: 4px; }"),
    ("9_full_qss_no_transparent", """
        QWidget { background-color: #0d0d1a; color: #e0e0ff; font-family: "Inter", "Segoe UI", sans-serif; font-size: 10pt; }
        QPushButton { background-color: #13132b; color: #e0e0ff; border: 1px solid #00e5ff; border-radius: 6px; padding: 6px 16px; }
        QPushButton:hover { background-color: #1a1a3e; border-color: #40eeff; }
        QLabel { background-color: #0d0d1a; color: #e0e0ff; }
        QLineEdit { background-color: #1a1a30; color: #e0e0ff; border: none; border-bottom: 2px solid #00e5ff; border-radius: 4px; padding: 4px 8px; }
        QTextEdit { background-color: #1a1a30; color: #c8c8ff; border: 1px solid #2a2a4a; border-radius: 4px; padding: 4px; }
    """),
    ("10_full_qss_with_transparent", """
        QWidget { background-color: #0d0d1a; color: #e0e0ff; font-family: "Inter", "Segoe UI", sans-serif; font-size: 10pt; }
        QPushButton { background-color: #13132b; color: #e0e0ff; border: 1px solid #00e5ff; border-radius: 6px; padding: 6px 16px; }
        QPushButton:hover { background-color: #1a1a3e; border-color: #40eeff; }
        QLabel { background: transparent; color: #e0e0ff; }
        QLineEdit { background-color: #1a1a30; color: #e0e0ff; border: none; border-bottom: 2px solid #00e5ff; border-radius: 4px; padding: 4px 8px; }
        QTextEdit { background-color: #1a1a30; color: #c8c8ff; border: 1px solid #2a2a4a; border-radius: 4px; padding: 4px; }
    """),
    ("11_actionbutton_class", """
        QWidget { background-color: #0d0d1a; color: #e0e0ff; font-family: "Inter", "Segoe UI", sans-serif; font-size: 10pt; }
        QPushButton { background-color: #13132b; color: #e0e0ff; border: 1px solid #00e5ff; border-radius: 6px; padding: 6px 16px; }
        ActionButton { background-color: #1a1a30; color: #00e5ff; border: 1px solid #00e5ff; border-radius: 6px; padding: 6px 16px; }
        ActionButton:hover { background-color: #00e5ff; color: #0d0d1a; }
        NeonButton { background-color: #0a0a18; color: #e0e0ff; border: none; border-radius: 0px; padding: 0px 0px 0px 12px; text-align: left; }
        NeonButton:hover { background-color: #1a1a3e; }
        QLabel { background: transparent; color: #e0e0ff; }
    """),
]


def _count_bright_pixels(img) -> tuple[int, int, float]:
    """Count pixels with R+G+B > 100 (non-dark). Returns (total_bright, total_pixels, ratio)."""
    from PySide6.QtGui import QImage
    w, h = img.width(), img.height()
    total = w * h
    bright = 0
    for y in range(0, max(h, 1), 2):  # sample every 2nd row for speed
        for x in range(0, max(w, 1), 2):  # sample every 2nd col
            c = img.pixelColor(x, y)
            if c.red() + c.green() + c.blue() > 100:
                bright += 1
    return bright, total, bright / max(total / 4, 1)


def _create_test_widget(qss: str) -> tuple[QWidget, list[QWidget]]:
    """Create a minimal window with labels, buttons, and an input.
    Returns (window, list_of_widgets_to_grab)."""
    from PySide6.QtWidgets import QLineEdit, QTextEdit

    w = QWidget()
    w.setWindowTitle("QSS Test")
    w.resize(600, 400)

    layout = QVBoxLayout(w)

    lbl1 = QLabel("HUAWEI MANAGER", w)
    layout.addWidget(lbl1)

    lbl2 = QLabel("Dashboard — Conectividade, VNFs, Operacoes", w)
    layout.addWidget(lbl2)

    lbl3 = QLabel("Status: Desconectado", w)
    layout.addWidget(lbl3)

    btn_row = QHBoxLayout()
    for name in ["Config", "Rotas", "Backup", "Editor"]:
        btn = QPushButton(name, w)
        btn_row.addWidget(btn)
    layout.addLayout(btn_row)

    txt = QTextEdit(w)
    txt.setPlainText("Output area — aqui vai o resultado dos comandos")
    layout.addWidget(txt)

    entry = QLineEdit(w)
    entry.setPlaceholderText("Digite um comando...")
    layout.addWidget(entry)

    w.show()
    return w, [lbl1, lbl2, lbl3, txt, entry]


def _dump_widget_tree(w: QWidget, indent: int = 0) -> None:
    geo = w.geometry()
    vis = w.isVisible()
    cls = type(w).__name__
    name = w.objectName() or ""
    text = ""
    if hasattr(w, "text"):
        t = w.text()
        if t:
            text = f' text="{t[:40]}"'
    print(f"{'  ' * indent}{cls}({name}){text}  visible={vis}  geo={geo.width()}x{geo.height()}@{geo.x()},{geo.y()}")
    for child in w.children():
        if isinstance(child, QWidget):
            _dump_widget_tree(child, indent + 1)


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    platform = app.platformName() if hasattr(app, 'platformName') else 'unknown'
    print(f"Platform: {platform}")
    print(f"Number of tests: {len(TESTS)}")
    print("=" * 60)

    results: list[tuple[str, float, str]] = []

    for i, (name, qss) in enumerate(TESTS):
        print(f"\n--- Test {i+1}/{len(TESTS)}: {name} ---")

        # Reset stylesheet
        app.setStyleSheet("")

        if qss:
            app.setStyleSheet(qss)

        win, grab_targets = _create_test_widget(qss)

        # Process events and wait for Wayland compositor to paint
        for _ in range(10):
            app.processEvents()
            time.sleep(0.05)

        # Force layout
        win.show()
        win.raise_()
        win.activateWindow()
        for _ in range(10):
            app.processEvents()
            time.sleep(0.05)

        # Dump widget tree
        print(f"  Widget tree:")
        _dump_widget_tree(win)

        # Grab using QWidget.grab() — works on Wayland (unlike grabWindow)
        pixmap = win.grab()
        img = pixmap.toImage()

        bright, total, ratio = _count_bright_pixels(img)
        pct = ratio * 100
        status = "OK" if pct > 0.5 else "BLANK!"

        print(f"  Screenshot (QWidget.grab): {img.width()}x{img.height()}")
        print(f"  Bright pixels (sampled): {bright} / ~{total // 4} (sampled) = {pct:.2f}%")
        print(f"  Status: {status}")

        results.append((name, pct, status))

        # Save screenshot
        out_dir = Path(__file__).parent / "diag_screenshots"
        out_dir.mkdir(exist_ok=True)
        pixmap.save(str(out_dir / f"{name}.png"))
        print(f"  Saved: scripts/diag_screenshots/{name}.png")

        win.close()
        app.processEvents()
        app.setStyleSheet("")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, pct, status in results:
        marker = " <<<" if status == "BLANK!" else ""
        print(f"  {name:35s}  {pct:6.2f}%  {status}{marker}")

    blank_tests = [(n, p, s) for n, p, s in results if s == "BLANK!"]
    if blank_tests:
        print(f"\n{len(blank_tests)} test(s) showed BLANK rendering!")
        print("The QSS rules in those tests are likely causing the Wayland issue.")
    else:
        print("\nNo blank rendering detected — the issue may be specific to the full app QSS.")

    # Find the transition: which rule FIRST causes blanking?
    if len(results) >= 2:
        print("\n--- Transition analysis ---")
        prev_ok = True
        for name, pct, status in results:
            is_ok = pct > 0.5
            if prev_ok and not is_ok:
                print(f"  FIRST BLANK at: {name} ({pct:.2f}%)")
            elif not prev_ok and is_ok:
                print(f"  RECOVERED at:   {name} ({pct:.2f}%)")
            prev_ok = is_ok


if __name__ == "__main__":
    main()
