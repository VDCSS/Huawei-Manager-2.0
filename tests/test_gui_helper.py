"""Testes para GuiTestHelper — infraestrutura de testes GUI com pytest-qt."""

import pytest
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from tests.helpers.gui_test_helper import GuiTestHelper


class TestGuiTestHelper:
    """Testa o helper de testes GUI."""

    def test_can_instantiate(self, qtbot) -> None:
        """GuiTestHelper pode ser instanciado sem erros."""
        helper = GuiTestHelper()
        assert helper is not None

    def test_assert_page_renders_with_valid_widget(self, qtbot) -> None:
        """assert_page_renders não levanta exceção para widget válido."""
        helper = GuiTestHelper()
        widget = QWidget()
        qtbot.addWidget(widget)
        widget.show()
        # Não deve levantar exceção
        helper.assert_page_renders(widget)

    def test_assert_page_renders_raises_for_none(self, qtbot) -> None:
        """assert_page_renders levanta AssertionError se widget é None."""
        helper = GuiTestHelper()
        with pytest.raises(AssertionError, match="widget"):
            helper.assert_page_renders(None)

    def test_assert_loading_state_shows_spinner(self, qtbot) -> None:
        """assert_loading_state detecta texto 'Carregando' ou 'Loading'."""
        helper = GuiTestHelper()
        widget = QWidget()
        qtbot.addWidget(widget)
        layout = QVBoxLayout(widget)
        label = QLabel("Carregando...")
        layout.addWidget(label)
        widget.show()
        helper.assert_loading_state(widget)
        assert label.isVisible()

    def test_assert_loading_state_missing(self, qtbot) -> None:
        """assert_loading_state levanta erro se não há indicador de loading."""
        helper = GuiTestHelper()
        widget = QWidget()
        qtbot.addWidget(widget)
        with pytest.raises(AssertionError, match="loading|Loading|Carregando"):
            helper.assert_loading_state(widget)

    def test_assert_error_state_shows_error(self, qtbot) -> None:
        """assert_error_state detecta texto de erro."""
        helper = GuiTestHelper()
        widget = QWidget()
        qtbot.addWidget(widget)
        layout = QVBoxLayout(widget)
        label = QLabel("Erro: conexão falhou")
        layout.addWidget(label)
        widget.show()
        helper.assert_error_state(widget)

    def test_assert_error_state_missing(self, qtbot) -> None:
        """assert_error_state levanta erro se não há indicador de erro."""
        helper = GuiTestHelper()
        widget = QWidget()
        qtbot.addWidget(widget)
        with pytest.raises(AssertionError, match="erro|error|Error"):
            helper.assert_error_state(widget)

    def test_assert_bindings_exist(self, qtbot) -> None:
        """assert_bindings_exist verifica atalhos de teclado configurados."""
        helper = GuiTestHelper()
        widget = QWidget()
        qtbot.addWidget(widget)
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeySequence, QShortcut

        QShortcut(QKeySequence(Qt.CTRL | Qt.Key_D), widget, lambda: None)
        helper.assert_bindings_exist(widget)
