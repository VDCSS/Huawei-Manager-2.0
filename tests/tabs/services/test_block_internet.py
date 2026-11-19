"""Fase 2: botão "Bloquear Internet" — modal + execução da decisão.

Regressão do wiring (clique real) e do contrato D2/D3/D8/D9:

* o clique dispara ``ServicesHandlers.block_internet()``;
* o modal recebe o perfil por device e o estado detectado (device vs
  cache — MOCK/offline exibe "estado estimado");
* a decisão confirmada envia o bloco com snapshot/verify/rollback;
* persistência (startup-config + JSON) **só** com ``result.ok`` + save
  marcado + papel admin (D3);
* desaplicar remove só o binding e mantém o perfil/ACL (D9);
* apagar remove o perfil do JSON (D8).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtWidgets import QPushButton

from huawei_manager.services.acl_presets import (
    AclBlockProfile,
    load_profile,
    save_profile,
)
from huawei_manager.services.block_cli import apply_block
from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.services import handlers as handlers_mod
from huawei_manager.tabs.services.handlers import ServicesHandlers
from huawei_manager.tabs.services.page import ServicesTab

#: pytest-qt guarda referências fracas — mantemos a página viva no teste.
_KEEP_ALIVE: list = []

_DEVICE_KEY = "RTR-01@10.0.0.1"


def _device():
    dev = MagicMock()
    dev.name = "RTR-01"
    dev.host = "10.0.0.1"
    dev.port = 22
    dev.type = "ROUTER"
    dev.status = "online"
    return lambda: dev


def _sb_mock(running_config: str = "") -> MagicMock:
    sb = MagicMock()
    sb.is_alive.return_value = True

    def _send_command(cmd, *a, **kw):
        if "version" in cmd:
            return "VRP (R) Version 8.180"
        if "current-configuration" in cmd:
            return running_config
        return ""

    sb.send_command.side_effect = _send_command
    sb.send_config_block.return_value = (True, "OK")
    sb.save_running_config.return_value = (True, "OK salvo")
    return sb


def _fake_ctx(**overrides) -> TabContext:
    fields: dict = dict(
        sb=_sb_mock(),
        audit=None,
        event_bus=MagicMock(),
        role=lambda: "admin",
        device=_device(),
        dispatch=lambda fn: fn() if callable(fn) else None,
        require_access=lambda level: True,
        spawn_io=lambda fn, *a: fn(*a),
        spawn_cpu=lambda fn, *a: fn(*a),
        watcher=MagicMock(),
        is_mock=lambda: False,
        toggle_mock=lambda: False,
        show_auth_dialog=lambda: None,
        watcher_results=lambda: None,
        set_watcher_results=MagicMock(),
        session=MagicMock(),
        run=MagicMock(),
        set_status=MagicMock(),
        touch_session=MagicMock(),
        cmd_validator=None,
        dry_run=None,
        get_last_config_command=MagicMock(return_value=None),
        set_last_config_command=MagicMock(),
        drv=lambda: MagicMock(),
        devices=lambda: [],
        show_page=MagicMock(),
        svc_mode=lambda: "cli",
        ui_bridge=lambda: None,
        ensure_device_ready=MagicMock(return_value=True),
        refresh_devices=MagicMock(),
        show_device_dialog=MagicMock(),
        delete_device=MagicMock(),
        on_device_selected=MagicMock(),
        clear_device_target=MagicMock(),
    )
    fields.update(overrides)
    return TabContext(**fields)


def _build(qtbot, ctx: TabContext, svc_id: str):
    tab = ServicesTab()
    widget = tab.build(ctx)
    qtbot.addWidget(widget)
    _KEEP_ALIVE.append(widget)
    tab.refresh_service_list()
    for idx, svc in enumerate(tab.state.services):
        if svc.id == svc_id:
            tab.state.listbox.setCurrentRow(idx)
            break
    else:  # pragma: no cover - serviço ausente = falha de catálogo
        raise AssertionError(f"serviço '{svc_id}' não está na lista")
    qtbot.wait(20)
    return tab, widget


def _button(widget, needle: str) -> QPushButton:
    for btn in widget.findChildren(QPushButton):
        if needle in btn.text():
            return btn
    raise AssertionError(f"botão '{needle}' não encontrado")


def _out(tab) -> str:
    return tab.state.output.toPlainText() if tab.state.output else ""


def _profile(**over) -> AclBlockProfile:
    base = dict(
        device_key=_DEVICE_KEY,
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


def _fake_dialog(monkeypatch, *, decision=None, reject: bool = False):
    """Substitui ``BlockInternetDialog`` capturando os kwargs do handler."""
    cap: dict = {}

    class FakeDialog:
        def __init__(self, parent=None, *, profile=None, applied=False,
                     applied_source="cache", can_save=True):
            cap.update(
                profile=profile,
                applied=applied,
                applied_source=applied_source,
                can_save=can_save,
            )

        def set_device_key(self, key: str) -> None:
            cap["device_key"] = key

        def exec(self) -> int:
            return 0 if reject else 1

        def get_decision(self):
            assert not reject, "get_decision() não deveria ser chamado"
            return decision

    monkeypatch.setattr(handlers_mod, "BlockInternetDialog", FakeDialog)
    return cap


class TestBlockInternetOpen:
    """O clique no botão abre o modal com o estado correto do device."""

    def test_click_calls_block_internet_handler(self, qtbot, monkeypatch):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, "svc-acl")
        called: list[bool] = []
        monkeypatch.setattr(
            ServicesHandlers, "block_internet",
            lambda self: called.append(True),
        )

        _button(widget, "Bloquear Internet").click()

        assert called == [True]

    def test_opens_dialog_without_profile(self, qtbot, monkeypatch,
                                          tmp_path):
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        ctx = _fake_ctx(sb=_sb_mock(running_config=""))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        cap = _fake_dialog(monkeypatch, reject=True)

        _button(widget, "Bloquear Internet").click()

        assert cap["profile"] is None
        assert cap["device_key"] == _DEVICE_KEY
        assert cap["applied"] is False
        assert cap["can_save"] is True
        assert "cancelada" in _out(tab)

    def test_opens_dialog_with_saved_profile_not_applied(
        self, qtbot, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        save_profile(None, _profile(applied=False))
        ctx = _fake_ctx(sb=_sb_mock(running_config=""))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        cap = _fake_dialog(monkeypatch, reject=True)

        _button(widget, "Bloquear Internet").click()

        assert cap["profile"] is not None
        assert cap["profile"].acl_number == 3000
        # SB vivo + running sem as âncoras → detectado no device.
        assert cap["applied"] is False
        assert cap["applied_source"] == "device"

    def test_applied_detected_from_running_config(self, qtbot, monkeypatch,
                                                  tmp_path):
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        profile = _profile(applied=False)
        save_profile(None, profile)
        running = "\n".join(
            ln for ln in apply_block(profile).lines
            if not ln.startswith("acl number")
        )
        ctx = _fake_ctx(sb=_sb_mock(running_config=running))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        cap = _fake_dialog(monkeypatch, reject=True)

        _button(widget, "Bloquear Internet").click()

        assert cap["applied"] is True
        assert cap["applied_source"] == "device"

    def test_offline_falls_back_to_cache_state(self, qtbot, monkeypatch,
                                               tmp_path):
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        save_profile(None, _profile(applied=True))
        sb = _sb_mock()
        sb.is_alive.return_value = False
        ctx = _fake_ctx(sb=sb)
        tab, widget = _build(qtbot, ctx, "svc-acl")
        cap = _fake_dialog(monkeypatch, reject=True)

        _button(widget, "Bloquear Internet").click()

        assert cap["applied"] is True
        assert cap["applied_source"] == "cache"

    def test_cancel_sends_nothing(self, qtbot, monkeypatch, tmp_path):
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, "svc-acl")
        _fake_dialog(monkeypatch, reject=True)

        _button(widget, "Bloquear Internet").click()

        assert not ctx.sb.send_config_block.called
        assert not ctx.sb.save_running_config.called
        assert "cancelada" in _out(tab)


class TestBlockInternetApply:
    """Aplicar: bloco enviado + verificação + persistência (D3)."""

    def test_apply_sends_block_and_persists(self, qtbot, monkeypatch,
                                            tmp_path):
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        profile = _profile()
        # Running sem o header da ACL (ACL ainda não existe → nossa),
        # mas com interface + âncoras (pré-checagem e verify passam).
        running = "\n".join(
            ln for ln in apply_block(profile).lines
            if not ln.startswith("acl number")
        )
        ctx = _fake_ctx(sb=_sb_mock(running_config=running))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        from huawei_manager.widgets.block_dialog import BlockInternetDecision
        decision = BlockInternetDecision(
            action="apply", profile=profile, save=True,
        )
        _fake_dialog(monkeypatch, decision=decision)

        _button(widget, "Bloquear Internet").click()

        assert ctx.sb.send_config_block.called
        lines = ctx.sb.send_config_block.call_args.args[0]
        assert lines[0] == "acl number 3000"
        assert any(ln.startswith("rule 5 deny") for ln in lines), lines
        assert "traffic-filter outbound acl 3000" in lines
        ctx.sb.save_running_config.assert_called()

        saved = load_profile(None, _DEVICE_KEY)
        assert saved is not None
        assert saved.applied is True
        assert saved.created_from_snapshot is False
        assert tab.state.last_config_command is not None
        assert "persistido" in _out(tab).lower()

    def test_apply_without_save_persists_nothing(self, qtbot, monkeypatch,
                                                 tmp_path):
        """D3: sem save marcado → nem startup-config, nem JSON."""
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        profile = _profile()
        running = "\n".join(
            ln for ln in apply_block(profile).lines
            if not ln.startswith("acl number")
        )
        ctx = _fake_ctx(sb=_sb_mock(running_config=running))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        from huawei_manager.widgets.block_dialog import BlockInternetDecision
        decision = BlockInternetDecision(
            action="apply", profile=profile, save=False,
        )
        _fake_dialog(monkeypatch, decision=decision)

        _button(widget, "Bloquear Internet").click()

        assert ctx.sb.send_config_block.called
        assert not ctx.sb.save_running_config.called
        assert load_profile(None, _DEVICE_KEY) is None
        assert "não persistido" in _out(tab).lower()


class TestBlockInternetUnapplyDelete:
    """Desaplicar mantém a ACL (D9); apagar remove o perfil (D8)."""

    def test_unapply_keeps_acl_and_clears_applied(self, qtbot, monkeypatch,
                                                  tmp_path):
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        profile = _profile(applied=True)
        save_profile(None, profile)
        # Binding já removido no running (verify de ausência passa) e a
        # interface presente (pré-checagem passa).
        running = "interface GigabitEthernet0/0/0\n"
        ctx = _fake_ctx(sb=_sb_mock(running_config=running))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        from huawei_manager.widgets.block_dialog import BlockInternetDecision
        decision = BlockInternetDecision(
            action="unapply", profile=profile, save=True,
        )
        _fake_dialog(monkeypatch, decision=decision)

        _button(widget, "Bloquear Internet").click()

        assert ctx.sb.send_config_block.called
        lines = ctx.sb.send_config_block.call_args.args[0]
        assert "undo traffic-filter outbound acl 3000" in lines
        assert not any("undo acl" in ln for ln in lines), lines
        ctx.sb.save_running_config.assert_called()

        saved = load_profile(None, _DEVICE_KEY)
        assert saved is not None, "D9: perfil/ACL devem permanecer"
        assert saved.applied is False

    def test_delete_removes_binding_and_profile(self, qtbot, monkeypatch,
                                                tmp_path):
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        profile = _profile(applied=True, created_from_snapshot=False)
        save_profile(None, profile)
        running = "interface GigabitEthernet0/0/0\n"
        ctx = _fake_ctx(sb=_sb_mock(running_config=running))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        from huawei_manager.widgets.block_dialog import BlockInternetDecision
        decision = BlockInternetDecision(
            action="delete", profile=profile, save=True,
        )
        _fake_dialog(monkeypatch, decision=decision)

        _button(widget, "Bloquear Internet").click()

        assert ctx.sb.send_config_block.called
        lines = ctx.sb.send_config_block.call_args.args[0]
        assert "undo traffic-filter outbound acl 3000" in lines
        assert "undo acl number 3000" in lines
        ctx.sb.save_running_config.assert_called()
        assert load_profile(None, _DEVICE_KEY) is None, "D8: apagar remove o JSON"

    def test_delete_preserves_preexisting_acl_in_json(self, qtbot, monkeypatch,
                                                      tmp_path):
        """ACL que não era nossa → delete remove só o binding (fail-closed)."""
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        profile = _profile(applied=True, created_from_snapshot=True)
        save_profile(None, profile)
        running = "interface GigabitEthernet0/0/0\n"
        ctx = _fake_ctx(sb=_sb_mock(running_config=running))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        from huawei_manager.widgets.block_dialog import BlockInternetDecision
        decision = BlockInternetDecision(
            action="delete", profile=profile, save=True,
        )
        _fake_dialog(monkeypatch, decision=decision)

        _button(widget, "Bloquear Internet").click()

        lines = ctx.sb.send_config_block.call_args.args[0]
        assert "undo traffic-filter outbound acl 3000" in lines
        assert not any("undo acl" in ln for ln in lines), lines
        assert load_profile(None, _DEVICE_KEY) is None
