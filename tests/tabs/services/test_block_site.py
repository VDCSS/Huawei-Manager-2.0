"""Fase 4: botão "Bloquear site" — modal + execução da decisão.

Regressão do wiring (clique real) e do contrato do fluxo B:

* o clique dispara ``ServicesHandlers.block_site()``;
* o modal recebe ``can_save`` conforme o papel (D6);
* a decisão confirmada envia o bloco com snapshot/verify/rollback;
* persistência na startup-config **só** com ``result.ok`` + save
  marcado + papel admin (D3) — sem JSON de perfil (o JSON é só do
  Bloquear Internet);
* modo MOCK não toca o device.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtWidgets import QPushButton

from huawei_manager.services.block_cli import preview_site_lines
from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.services import handlers as handlers_mod
from huawei_manager.tabs.services.handlers import ServicesHandlers
from huawei_manager.tabs.services.page import ServicesTab

#: pytest-qt guarda referências fracas — mantemos a página viva no teste.
_KEEP_ALIVE: list = []

_DEVICE_KEY = "RTR-01@10.0.0.1"

_SITE_KW = dict(
    strategy="deny-list",
    acl_number=3100,
    interface="GigabitEthernet0/0/0",
    direction="outbound",
    resolved=(("10.1.2.3", "0.0.0.0"),),
)


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


def _running_ok() -> str:
    """Running-config em que pré-checagem e verify do site passam."""
    return "\n".join(preview_site_lines(**_SITE_KW))


def _fake_dialog(monkeypatch, *, decision=None, reject: bool = False):
    """Substitui ``BlockSiteDialog`` capturando os kwargs do handler."""
    cap: dict = {}

    class FakeDialog:
        def __init__(self, parent=None, *, can_save=True, resolver=None,
                     chain=None):
            cap.update(can_save=can_save, resolver=resolver, chain=chain)

        def exec(self) -> int:
            return 0 if reject else 1

        def get_decision(self):
            assert not reject, "get_decision() não deveria ser chamado"
            return decision

    monkeypatch.setattr(handlers_mod, "BlockSiteDialog", FakeDialog)
    return cap


def _decision(**over):
    from huawei_manager.widgets.block_dialog import BlockSiteDecision

    base = dict(
        strategy="deny-list",
        acl_number=3100,
        interface="GigabitEthernet0/0/0",
        direction="outbound",
        destinations=("10.1.2.3",),
        resolved=(("10.1.2.3", "0.0.0.0"),),
        save=True,
    )
    base.update(over)
    return BlockSiteDecision(**base)  # type: ignore[arg-type]


class TestBlockSiteOpen:
    """O clique no botão abre o modal com o papel correto."""

    def test_click_calls_block_site_handler(self, qtbot, monkeypatch):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, "svc-acl")
        called: list[bool] = []
        monkeypatch.setattr(
            ServicesHandlers, "block_site",
            lambda self: called.append(True),
        )

        _button(widget, "Bloquear site").click()

        assert called == [True]

    def test_opens_dialog_with_admin_can_save(self, qtbot, monkeypatch):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, "svc-acl")
        cap = _fake_dialog(monkeypatch, reject=True)

        _button(widget, "Bloquear site").click()

        assert cap["can_save"] is True
        assert "cancelada" in _out(tab)

    def test_opens_dialog_without_admin_can_save(self, qtbot, monkeypatch):
        """D6: papel sem admin recebe o checkbox de save desabilitado."""
        ctx = _fake_ctx(role=lambda: "tecnico")
        tab, widget = _build(qtbot, ctx, "svc-acl")
        cap = _fake_dialog(monkeypatch, reject=True)

        _button(widget, "Bloquear site").click()

        assert cap["can_save"] is False

    def test_cancel_sends_nothing(self, qtbot, monkeypatch):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, "svc-acl")
        _fake_dialog(monkeypatch, reject=True)

        _button(widget, "Bloquear site").click()

        assert not ctx.sb.send_config_block.called
        assert not ctx.sb.save_running_config.called
        assert "cancelada" in _out(tab)

    def test_requires_admin(self, qtbot, monkeypatch):
        ctx = _fake_ctx(require_access=lambda level: False)
        tab, widget = _build(qtbot, ctx, "svc-acl")
        _fake_dialog(monkeypatch, reject=True)

        _button(widget, "Bloquear site").click()

        assert "negada" in _out(tab)
        assert not ctx.sb.send_config_block.called


class TestBlockSiteApply:
    """Aplicar: bloco enviado + verificação + save D3 (sem JSON)."""

    def test_apply_sends_site_block_and_saves(self, qtbot, monkeypatch,
                                              tmp_path):
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        ctx = _fake_ctx(sb=_sb_mock(running_config=_running_ok()))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        _fake_dialog(monkeypatch, decision=_decision(save=True))

        _button(widget, "Bloquear site").click()

        assert ctx.sb.send_config_block.called
        lines = ctx.sb.send_config_block.call_args.args[0]
        assert lines[0] == "acl number 3100"
        assert any(ln.startswith("rule 5 deny") for ln in lines), lines
        assert "traffic-policy P_SITE_3100 outbound" in lines
        ctx.sb.save_running_config.assert_called()
        assert tab.state.last_config_command is not None
        assert "não persistido" not in _out(tab).lower() or (
            "startup-config" in _out(tab).lower()
        )

    def test_apply_without_save_persists_nothing(self, qtbot, monkeypatch,
                                                 tmp_path):
        """D3: sem save marcado → nem startup-config, nem JSON."""
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        ctx = _fake_ctx(sb=_sb_mock(running_config=_running_ok()))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        _fake_dialog(monkeypatch, decision=_decision(save=False))

        _button(widget, "Bloquear site").click()

        assert ctx.sb.send_config_block.called
        assert not ctx.sb.save_running_config.called
        assert "não persistido" in _out(tab).lower()

    def test_site_flow_writes_no_json_profile(self, qtbot, monkeypatch,
                                              tmp_path):
        """O fluxo B não usa o JSON por device (D2 é só do Internet)."""
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        ctx = _fake_ctx(sb=_sb_mock(running_config=_running_ok()))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        _fake_dialog(monkeypatch, decision=_decision(save=True))

        _button(widget, "Bloquear site").click()

        from huawei_manager.services.acl_presets import load_profile

        assert load_profile(None, _DEVICE_KEY) is None

    def test_mock_mode_sends_nothing(self, qtbot, monkeypatch, tmp_path):
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        ctx = _fake_ctx(svc_mode=lambda: "mock")
        tab, widget = _build(qtbot, ctx, "svc-acl")
        _fake_dialog(monkeypatch, decision=_decision(save=True))

        _button(widget, "Bloquear site").click()

        assert not ctx.sb.send_config_block.called
        assert "Modo MOCK" in _out(tab)

    def test_napalm_mode_blocked(self, qtbot, monkeypatch, tmp_path):
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        ctx = _fake_ctx(svc_mode=lambda: "napalm")
        tab, widget = _build(qtbot, ctx, "svc-acl")
        _fake_dialog(monkeypatch, decision=_decision())

        _button(widget, "Bloquear site").click()

        assert "NAPALM" in _out(tab)
        assert not ctx.sb.send_config_block.called
