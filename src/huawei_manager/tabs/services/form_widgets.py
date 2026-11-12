"""Widget genérico de formulário para os serviços compostos (aba Serviços).

Constrói a UI a partir de um :class:`~huawei_manager.services.form_spec.FormSpec`:

* seções únicas → grade de campos (label + editor);
* seções repetíveis → linhas com botão "−" (remove) e botão "＋ Adicionar".

Campos ``ENUM`` viram ``QComboBox``; os demais, ``QLineEdit``. Campos com
``depends_on`` ficam ocultos até que o campo controlador tenha um dos
valores aceitos.
"""
from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager.basic_config.params import ParamKind
from huawei_manager.services.form_spec import (
    FormField,
    FormSection,
    FormSpec,
    FormValues,
    SectionValues,
)
from huawei_manager.tabs import _ui

_INPUT_STYLE = f"""
    QLineEdit, QComboBox {{
        background: {C.BG_BASE}; color: {C.NEON_CYAN};
        border: 1px solid {C.BORDER_NRM}; border-radius: 3px;
        padding: 3px 6px; font: 12px {C.FONT_UI_FAMILY};
    }}
    QLineEdit:focus, QComboBox:focus {{
        border: 1px solid {C.NEON_CYAN};
    }}
    QComboBox::drop-down {{ border: none; }}
    QComboBox QAbstractItemView {{
        background: {C.BG_INPUT}; color: {C.NEON_CYAN};
        selection-background-color: {C.NEON_PURP};
    }}
"""


class _FieldBox:
    """Editor de um campo + acesso ao valor atual."""

    def __init__(self, field: FormField) -> None:
        self.field = field
        self.label: QLabel | None = None
        self.combo: QComboBox | None = None
        self.entry: QLineEdit | None = None
        #: Estado de visibilidade lógica (independe de o widget estar ou não
        #: numa árvore visível) — usado para excluir campos condicionais
        #: ocultos dos valores coletados.
        self.visible: bool = True
        if field.kind is ParamKind.ENUM:
            combo = QComboBox()
            combo.addItems(list(field.choices))
            if field.default:
                combo.setCurrentText(field.default)
            self.combo = combo
            self.widget: QWidget = combo
        else:
            entry = QLineEdit()
            entry.setText(field.default)
            entry.setMaxLength(field.max_len)
            if field.secret:
                entry.setEchoMode(QLineEdit.EchoMode.Password)
            self.entry = entry
            self.widget = entry
        self.widget.setStyleSheet(_INPUT_STYLE)
        self.widget.setToolTip(field.help)

    def value(self) -> str:
        if self.combo is not None:
            return self.combo.currentText().strip()
        if self.entry is not None:
            return self.entry.text().strip()
        return ""

    def reset(self) -> None:
        if self.combo is not None:
            self.combo.setCurrentText(self.field.default)
        elif self.entry is not None:
            self.entry.setText(self.field.default)


class FormWidget(QWidget):
    """Formulário renderizado a partir de um :class:`FormSpec`."""

    def __init__(self, spec: FormSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spec = spec
        # seção única -> {field_key: _FieldBox}
        self._single: dict[str, dict[str, _FieldBox]] = {}
        # seção repetível -> lista de linhas (cada linha: {field_key: _FieldBox})
        self._rows: dict[str, list[dict[str, _FieldBox]]] = {}
        self._row_containers: dict[str, list[QWidget]] = {}
        self._rows_layout: dict[str, QVBoxLayout] = {}
        self._boxes: list[_FieldBox] = []
        self._warn_labels: list[QLabel] = []
        self._build()
        self._refresh_visibility()

    # ── construção ──────────────────────────────────────────────────
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        for section in self._spec.sections:
            frame = QFrame(self)
            frame.setStyleSheet(
                f"background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM}; "
                "border-radius: 4px;"
            )
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(8, 4, 8, 6)

            title = QLabel(section.title.upper(), frame)
            title.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_INPUT, 10, True))
            fl.addWidget(title)

            if section.repeatable:
                rows_box = QVBoxLayout()
                rows_box.setContentsMargins(0, 0, 0, 0)
                fl.addLayout(rows_box)
                self._rows_layout[section.key] = rows_box
                for _ in range(section.min_rows):
                    self._add_row(section)
                add_btn = QPushButton("＋ Adicionar linha", frame)
                add_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {C.BG_BASE}; color: {C.NEON_CYAN};
                        border: 1px solid {C.BORDER_NRM}; border-radius: 3px;
                        padding: 4px 8px; font: 11px {C.FONT_UI_FAMILY};
                    }}
                    QPushButton:hover {{ border: 1px solid {C.NEON_CYAN}; }}
                """)
                add_btn.clicked.connect(lambda _=False, s=section: self._add_row(s))
                fl.addWidget(add_btn)
            else:
                grid = QGridLayout()
                grid.setContentsMargins(0, 0, 0, 0)
                boxes = self._add_fields(grid, section.fields)
                fl.addLayout(grid)
                self._single[section.key] = {
                    f.key: box for f, box in zip(section.fields, boxes)
                }
            outer.addWidget(frame)

        # Avisos condicionais — um rótulo por aviso (fora do laço de
        # seções, para não duplicar nem dessincronizar os avisos).
        for warning in self._spec.warnings:
            lbl = QLabel(f"⚠  {warning.message}", self)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(_ui.css_label(C.NEON_AMBER, C.BG_INPUT, 10))
            lbl.setVisible(False)
            outer.addWidget(lbl)
            self._warn_labels.append(lbl)

    def _add_fields(
        self, grid: QGridLayout, fields: tuple[FormField, ...]
    ) -> list[_FieldBox]:
        """Adiciona os campos numa grade de 2 pares por linha."""
        created: list[_FieldBox] = []
        for idx, field in enumerate(fields):
            box = _FieldBox(field)
            created.append(box)
            self._boxes.append(box)
            row = idx // 2
            col = (idx % 2) * 2
            label = QLabel(f"{field.label}:", grid.parentWidget())
            label.setStyleSheet(_ui.css_label(C.FG_DIM, C.BG_INPUT, 11))
            box.label = label
            grid.addWidget(label, row, col)
            grid.addWidget(box.widget, row, col + 1)
            if box.combo is not None:
                box.combo.currentTextChanged.connect(self._on_change)
            elif box.entry is not None:
                box.entry.textChanged.connect(self._on_change)
        return created

    def _add_row(self, section: FormSection) -> None:
        """Cria uma nova linha numa seção repetível (respeita ``max_rows``)."""
        existing = self._rows.get(section.key, [])
        if len(existing) >= section.max_rows:
            return
        container = QFrame(self)
        container.setStyleSheet(
            f"background: {C.BG_BASE}; border: 1px solid {C.BORDER_NRM}; "
            "border-radius: 3px;"
        )
        grid = QGridLayout(container)
        grid.setContentsMargins(6, 4, 6, 4)
        boxes = self._add_fields(grid, section.fields)
        del_btn = QPushButton("−", container)
        del_btn.setFixedWidth(28)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.BG_CARD}; color: {C.NEON_RED};
                border: 1px solid {C.BORDER_NRM}; border-radius: 3px;
                font: 12px {C.FONT_UI_FAMILY};
            }}
            QPushButton:hover {{ border: 1px solid {C.NEON_RED}; }}
        """)
        del_btn.setToolTip("Remover esta linha")
        grid.addWidget(
            del_btn, len(section.fields) // 2, 4,
            Qt.AlignmentFlag.AlignBottom,
        )
        rows = self._rows.setdefault(section.key, [])
        rows.append({f.key: box for f, box in zip(section.fields, boxes)})
        self._row_containers.setdefault(section.key, []).append(container)
        self._rows_layout[section.key].addWidget(container)
        del_btn.clicked.connect(
            lambda _=False, s=section, c=container: self._remove_row(s, c)
        )
        self._refresh_visibility()

    def _remove_row(self, section: FormSection, container: QWidget) -> None:
        rows = self._rows.get(section.key, [])
        if len(rows) <= section.min_rows:
            return
        for row in rows:
            if any(box.widget.parent() is container for box in row.values()):
                rows.remove(row)
                break
        containers = self._row_containers.get(section.key, [])
        if container in containers:
            containers.remove(container)
        container.setParent(None)
        container.deleteLater()
        self._refresh_visibility()

    # ── valores ─────────────────────────────────────────────────────
    def values(self) -> FormValues:
        """Coleta os valores atuais do formulário.

        Campos **ocultos** (condicionais e inativos) são omitidos — assim
        um valor residual de um campo que deixou de se aplicar não chega ao
        renderizador (que valida e renderiza apenas o que é efetivo).
        """
        out: dict[str, SectionValues | list[SectionValues]] = {}
        for section in self._spec.sections:
            if section.repeatable:
                out[section.key] = [
                    {key: box.value() for key, box in row.items() if box.visible}
                    for row in self._rows.get(section.key, [])
                ]
            else:
                out[section.key] = {
                    key: box.value()
                    for key, box in self._single.get(section.key, {}).items()
                    if box.visible
                }
        return out

    def section_values(self, section_key: str) -> list[SectionValues]:
        """Valores de uma seção em lista de linhas (campos ocultos omitidos)."""
        rows = self._rows.get(section_key, [])
        return [
            {k: b.value() for k, b in row.items() if b.visible}
            for row in rows
        ]

    def set_value(
        self, section_key: str, key: str, value: str, row: int = 0
    ) -> None:
        """Define o valor de um campo (pré-preenchimento / testes).

        Seções repetíveis endereçam a linha por ``row``.
        """
        if section_key in self._rows:
            rows = self._rows.get(section_key, [])
            if row >= len(rows):
                raise IndexError(
                    f"linha {row} inexistente na seção '{section_key}'"
                )
            box = rows[row].get(key)
        else:
            box = self._single.get(section_key, {}).get(key)
        if box is None:
            raise KeyError(f"campo '{key}' inexistente em '{section_key}'")
        if box.combo is not None:
            box.combo.setCurrentText(value)
        elif box.entry is not None:
            box.entry.setText(value)
        self._refresh_visibility()

    def add_row(self, section_key: str) -> None:
        """Adiciona uma linha a uma seção repetível."""
        section = self._spec.section(section_key)
        if section is None or not section.repeatable:
            raise KeyError(f"seção repetível inexistente: '{section_key}'")
        self._add_row(section)

    def clear(self) -> None:
        """Restaura os defaults e remove as linhas extras."""
        for boxes in self._single.values():
            for box in boxes.values():
                box.reset()
        for section in self._spec.sections:
            if not section.repeatable:
                continue
            for container in self._row_containers.get(section.key, []):
                container.setParent(None)
                container.deleteLater()
            self._row_containers[section.key] = []
            self._rows[section.key] = []
            for _ in range(section.min_rows):
                self._add_row(section)
        self._refresh_visibility()

    # ── visibilidade ────────────────────────────────────────────────
    def _on_change(self, *_args: object) -> None:
        self._refresh_visibility()

    def _flat_values(self) -> dict[str, str]:
        flat: dict[str, str] = {}
        for boxes in self._single.values():
            for key, box in boxes.items():
                flat[key] = box.value()
        for rows in self._rows.values():
            if rows:
                for key, box in rows[0].items():
                    flat.setdefault(key, box.value())
        return flat

    def _refresh_visibility(self) -> None:
        """Aplica a visibilidade condicional (``depends_on``).

        Em seções repetíveis a dependência é resolvida **por linha**: o
        controlador é o valor da própria linha (ex.: uma aplicação em VTY
        numa linha e em interface noutra). Controladores de outra seção
        caem no mapa global.
        """
        global_flat = self._flat_values()
        for section in self._spec.sections:
            if section.repeatable:
                for row in self._rows.get(section.key, []):
                    row_flat = dict(global_flat)
                    row_flat.update({k: b.value() for k, b in row.items()})
                    self._apply_visibility(row.values(), row_flat)
            else:
                boxes = self._single.get(section.key, {})
                row_flat = dict(global_flat)
                row_flat.update({k: b.value() for k, b in boxes.items()})
                self._apply_visibility(boxes.values(), row_flat)
        for warning, lbl in zip(self._spec.warnings, self._warn_labels):
            lbl.setVisible(
                global_flat.get(warning.field_key, "") in warning.values)

    @staticmethod
    def _apply_visibility(
        boxes: Iterable[_FieldBox], flat: dict[str, str]
    ) -> None:
        for box in boxes:
            dep = box.field.depends_on
            if dep is None:
                box.visible = True
                box.widget.setVisible(True)
                if box.label is not None:
                    box.label.setVisible(True)
                continue
            controller, allowed = dep
            visible = flat.get(controller, "") in allowed
            box.visible = visible
            box.widget.setVisible(visible)
            if box.label is not None:
                box.label.setVisible(visible)
