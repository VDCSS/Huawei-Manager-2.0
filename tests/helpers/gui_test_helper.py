"""GuiTestHelper — utilitários para testes GUI com PySide6 e pytest-qt.

Fornece assertions visuais (loading state, error state, page render)
e helpers de interação (atrasos, foco, atalhos de teclado).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget


class GuiTestHelper:
    """Helper para testes GUI com PySide6.

    Uso:
        helper = GuiTestHelper()
        helper.assert_page_renders(page_widget)
        helper.assert_loading_state(page_widget)
        helper.assert_error_state(page_widget)
    """

    # Textos que indicam estado de carregamento
    _LOADING_INDICATORS = frozenset({
        "carregando",
        "loading",
        "aguarde",
        "wait",
    })

    # Textos que indicam estado de erro
    _ERROR_INDICATORS = frozenset({
        "erro",
        "error",
        "falhou",
        "failed",
        "falha",
    })

    def assert_page_renders(self, widget: QWidget | None) -> None:
        """Verifica que um widget de página foi renderizado corretamente.

        Levanta AssertionError se widget é None ou invisível.
        """
        assert widget is not None, (
            "widget não pode ser None — página não foi construída"
        )
        assert isinstance(widget, QWidget), (
            f"esperado QWidget, obtido {type(widget).__name__}"
        )
        assert widget.isVisible(), (
            "widget da página não está visível"
        )

    def assert_loading_state(self, widget: QWidget) -> None:
        """Verifica que o widget está exibindo indicador de carregamento."""
        found = self._find_text_in_descendants(widget, self._LOADING_INDICATORS)
        assert found, (
            "Nenhum indicador de loading encontrado na página. "
            "Esperado um dos: " + ", ".join(self._LOADING_INDICATORS)
        )

    def assert_error_state(self, widget: QWidget) -> None:
        """Verifica que o widget está exibindo indicador de erro."""
        found = self._find_text_in_descendants(widget, self._ERROR_INDICATORS)
        assert found, (
            "Nenhum indicador de erro encontrado na página. "
            "Esperado um dos: " + ", ".join(self._ERROR_INDICATORS)
        )

    def assert_bindings_exist(self, widget: QWidget) -> None:
        """Verifica que atalhos de teclado foram configurados no widget."""
        shortcuts = widget.findChildren(QShortcut)
        assert len(shortcuts) > 0, (
            "Nenhum QShortcut encontrado no widget"
        )

    @staticmethod
    def wait(widget: QWidget, ms: int = 100) -> None:
        """Avança o loop de eventos Qt por N milissegundos.

        Útil para esperar timers (poll_queue, clock, etc.) processarem.
        """
        QTest.qWait(ms)

    @staticmethod
    def key_click(
        widget: QWidget, key: int, modifier: Qt.KeyboardModifier | None = None
    ) -> None:
        """Simula pressionamento de tecla via QTest."""
        QTest.keyClick(widget, key, modifier or Qt.NoModifier)

    @staticmethod
    def _find_text_in_descendants(
        widget: QWidget, indicators: frozenset[str]
    ) -> bool:
        """Busca texto indicador recursivamente nos filhos do widget."""
        from PySide6.QtWidgets import QLabel, QTextEdit

        stack: list[Any] = [widget]
        while stack:
            child = stack.pop()
            for c in child.children():
                if isinstance(c, (QLabel, QTextEdit)):
                    text = c.text() if isinstance(c, QLabel) else c.toPlainText()
                    text_lower = text.lower()
                    if any(ind in text_lower for ind in indicators):
                        return True
                if isinstance(c, QWidget):
                    stack.append(c)
        return False
