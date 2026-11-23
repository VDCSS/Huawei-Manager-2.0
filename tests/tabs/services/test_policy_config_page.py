"""TDD da etapa editável da cadeia traffic policy nos modais de bloqueio.

O operador configura os nomes do classifier/behavior/policy (e a ação do
behavior) na primeira vez, e depois pode editar/atualizar/excluir a cadeia
salva. ACL e interface vêm do formulário, aparecem como campos normais
somente-leitura — **sem** rótulo "[HERDADO]" na tela.
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QWidget,
)

from huawei_manager.services.acl_presets import AclBlockProfile
from huawei_manager.widgets.block_dialog import BlockInternetDialog, BlockSiteDialog


@pytest.fixture(autouse=True)
def _no_msgbox(monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)


def _profile(**over) -> AclBlockProfile:
    base = dict(
        device_key="RTR-01@10.0.0.1",
        acl_name="bloqueio-padrão",
        acl_number=3000,
        destination_ip="203.0.113.10",
        destination_mask="0.0.0.0",
        interface="GigabitEthernet0/0/0",
        direction="outbound",
        created_from_snapshot=False,
        applied=False,
    )
    base.update(over)
    return AclBlockProfile(**base)  # type: ignore[arg-type]


def _show(qtbot, dialog) -> None:
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(10)


def _button(widget: QWidget, needle: str) -> QPushButton:
    for btn in widget.findChildren(QPushButton):
        if btn.isVisible() and needle in btn.text():
            return btn
    raise AssertionError(f"botão visível '{needle}' não encontrado")


def _entry(dialog: QWidget, name: str) -> QLineEdit:
    hits = dialog.findChildren(QLineEdit, name)
    assert hits, f"campo '{name}' não existe"
    return hits[0]


def _combo(dialog: QWidget, name: str) -> QComboBox:
    hits = dialog.findChildren(QComboBox, name)
    assert hits, f"combo '{name}' não existe"
    return hits[0]


def _preview(dialog: QWidget) -> str:
    hits = dialog.findChildren(QPlainTextEdit, "chain_preview")
    assert hits, "preview da cadeia não existe"
    return hits[0].toPlainText()


def _panel(dialog: QWidget) -> QWidget:
    hits = dialog.findChildren(QWidget, "policy_config_panel")
    assert hits, "painel de configuração da cadeia não existe"
    return hits[0]


def _visible_labels(dialog: QWidget) -> str:
    return "\n".join(
        label.text()
        for label in dialog.findChildren(QLabel)
        if label.isVisible()
    )


def _from_form(qtbot) -> BlockInternetDialog:
    dialog = BlockInternetDialog()
    dialog.set_device_key("RTR-01@10.0.0.1")
    _show(qtbot, dialog)
    _button(dialog, "Revisar…").click()
    return dialog


class TestInternetConfigPage:
    def test_first_time_opens_config_page_prefilled(self, qtbot):
        dialog = _from_form(qtbot)

        assert _panel(dialog).isVisible()
        assert _entry(dialog, "chain_classifier").text() == "C_BLOQ_3000"
        assert _entry(dialog, "chain_behavior").text() == "B_BLOQ_3000"
        assert _entry(dialog, "chain_policy").text() == "P_BLOQ_3000"
        assert _combo(dialog, "chain_action").currentText() == "permit"
        assert "traffic classifier C_BLOQ_3000" in _preview(dialog)

    def test_no_herdado_label_on_screen(self, qtbot):
        dialog = _from_form(qtbot)

        assert "herdado" not in _visible_labels(dialog).lower()
        assert "[]" not in _visible_labels(dialog)

    def test_acl_and_interface_are_plain_readonly_fields(self, qtbot):
        dialog = _from_form(qtbot)

        acl = _entry(dialog, "chain_acl")
        iface = _entry(dialog, "chain_interface")
        assert acl.isReadOnly() and iface.isReadOnly()
        assert "3000" in acl.text()
        assert "GigabitEthernet0/0/0" in iface.text()

    def test_editing_name_updates_preview_live(self, qtbot):
        dialog = _from_form(qtbot)

        _entry(dialog, "chain_classifier").setText("C_MEU_3000")

        assert "traffic classifier C_MEU_3000" in _preview(dialog)
        assert "classifier C_MEU_3000 behavior B_BLOQ_3000" in _preview(dialog)

    def test_behavior_action_can_be_denied(self, qtbot):
        dialog = _from_form(qtbot)

        _combo(dialog, "chain_action").setCurrentText("deny")

        assert "\ndeny\n" in f"\n{_preview(dialog)}\n"

    def test_restore_suggested_per_field_and_global(self, qtbot):
        dialog = _from_form(qtbot)
        _entry(dialog, "chain_classifier").setText("C_MEU_3000")
        _entry(dialog, "chain_policy").setText("P_OUTRO")

        _button(dialog, "↺ sugerido").click()
        assert _entry(dialog, "chain_classifier").text() == "C_BLOQ_3000"
        assert _entry(dialog, "chain_policy").text() == "P_OUTRO"

        _button(dialog, "↺ Restaurar sugeridos").click()
        assert _entry(dialog, "chain_policy").text() == "P_BLOQ_3000"

    def test_invalid_name_blocks_advance(self, qtbot):
        dialog = _from_form(qtbot)
        _entry(dialog, "chain_classifier").setText("X" * 33)

        _button(dialog, "Avançar p/ revisão").click()

        assert _panel(dialog).isVisible()

    def test_custom_names_reach_review_and_decision(self, qtbot):
        dialog = _from_form(qtbot)
        _entry(dialog, "chain_policy").setText("P_CUSTOMIZADA")
        _button(dialog, "Avançar p/ revisão").click()

        assert dialog._cli_box is not None
        assert "traffic policy P_CUSTOMIZADA" in dialog._cli_box.toPlainText()

        _button(dialog, "Salvar/Enviar").click()

        decision = dialog.get_decision()
        assert decision.chain is not None
        assert decision.chain.policy == "P_CUSTOMIZADA"
        assert decision.chain.action == "permit"


class TestInternetChainLifecycle:
    def test_manage_offers_chain_actions(self, qtbot):
        dialog = BlockInternetDialog(profile=_profile())
        _show(qtbot, dialog)

        assert _button(dialog, "Editar cadeia").isVisible()
        assert _button(dialog, "Atualizar cadeia").isVisible()
        assert _button(dialog, "Excluir cadeia").isVisible()
        assert _button(dialog, "Apagar regra").isVisible()

    def test_edit_chain_goes_to_config_then_review(self, qtbot):
        dialog = BlockInternetDialog(profile=_profile())
        _show(qtbot, dialog)
        _button(dialog, "Editar cadeia").click()

        assert _panel(dialog).isVisible()
        _entry(dialog, "chain_behavior").setText("B_NOVO")
        _button(dialog, "Avançar p/ revisão").click()
        _button(dialog, "Salvar/Enviar").click()

        decision = dialog.get_decision()
        assert decision.config_action == "save"
        assert decision.chain is not None
        assert decision.chain.behavior == "B_NOVO"

    def test_update_chain_goes_config_to_review(self, qtbot):
        dialog = BlockInternetDialog(profile=_profile())
        _show(qtbot, dialog)
        _button(dialog, "Atualizar cadeia").click()
        _button(dialog, "Avançar p/ revisão").click()

        assert dialog._cli_box is not None
        cli = dialog._cli_box.toPlainText()
        assert "undo traffic policy P_BLOQ_3000" in cli
        assert "traffic policy P_BLOQ_3000" in cli

        _button(dialog, "Salvar/Enviar").click()
        assert dialog.get_decision().config_action == "update"

    def test_delete_chain_keeps_acl_step_out(self, qtbot):
        dialog = BlockInternetDialog(profile=_profile(applied=True), applied=True)
        _show(qtbot, dialog)
        _button(dialog, "Excluir cadeia").click()

        step_cli = "\n".join(
            box.toPlainText()
            for box in dialog.findChildren(QPlainTextEdit, "policy_step_cli")
        )
        assert "undo traffic-policy P_BLOQ_3000 outbound" in step_cli
        assert "undo traffic policy P_BLOQ_3000" in step_cli
        assert "undo acl number 3000" not in step_cli

        _button(dialog, "Avançar p/ revisão").click()
        _button(dialog, "Salvar/Enviar").click()
        assert dialog.get_decision().config_action == "delete"


class TestSiteConfigPage:
    def _at_application(self, qtbot, **kwargs):
        dialog = BlockSiteDialog(resolver=lambda host: ["203.0.113.10"], **kwargs)
        _show(qtbot, dialog)
        _button(dialog, "Avançar").click()
        entry = next(
            e
            for e in dialog.findChildren(QLineEdit)
            if e.isVisible() and "destino" in e.placeholderText().lower()
        )
        entry.setText("example.com")
        _button(dialog, "Adicionar").click()
        _button(dialog, "Avançar").click()
        return dialog

    def test_site_config_page_prefilled(self, qtbot):
        dialog = self._at_application(qtbot)

        _button(dialog, "Avançar").click()

        assert _panel(dialog).isVisible()
        assert _entry(dialog, "chain_classifier").text() == "C_SITE_3100"
        assert "3100" in _entry(dialog, "chain_acl").text()
        assert "herdado" not in _visible_labels(dialog).lower()

    def test_site_custom_names_reach_review_and_decision(self, qtbot):
        dialog = self._at_application(qtbot)
        _button(dialog, "Avançar").click()
        _entry(dialog, "chain_policy").setText("P_SITE_CUSTOM")
        _button(dialog, "Avançar p/ revisão").click()

        assert dialog._cli_box is not None
        assert "traffic policy P_SITE_CUSTOM" in dialog._cli_box.toPlainText()

        _button(dialog, "Salvar/Enviar").click()

        decision = dialog.get_decision()
        assert decision.chain is not None
        assert decision.chain.policy == "P_SITE_CUSTOM"

    def test_site_with_saved_chain_offers_lifecycle(self, qtbot):
        from huawei_manager.services.traffic_policy import TrafficPolicyChain

        chain = TrafficPolicyChain(
            classifier="C_SALVA", behavior="B_SALVA", policy="P_SALVA"
        )
        dialog = self._at_application(qtbot, chain=chain)

        assert _button(dialog, "Editar cadeia").isVisible()
        assert _button(dialog, "Atualizar cadeia").isVisible()
        assert _button(dialog, "Excluir cadeia").isVisible()
        _button(dialog, "Editar cadeia").click()
        assert _entry(dialog, "chain_policy").text() == "P_SALVA"
