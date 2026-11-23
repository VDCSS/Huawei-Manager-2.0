"""Integração da cadeia traffic policy nos handlers da aba Serviços.

Cobre o ciclo de vida configurável: o preset por device/fluxo chega ao
modal, ``save`` persiste sem tocar no device, ``update`` troca a cadeia e
``delete`` remove cadeia + JSON preservando a ACL.
"""
from __future__ import annotations

from huawei_manager.services.acl_presets import load_profile, save_profile
from huawei_manager.services.traffic_policy import (
    TrafficPolicyChain,
    render_chain,
)
from huawei_manager.services.traffic_policy_presets import (
    TrafficPolicyPreset,
    load_preset,
    save_preset,
)
from huawei_manager.widgets.block_dialog import (
    BlockInternetDecision,
    BlockSiteDecision,
)
from tests.tabs.services.test_block_internet import (
    _DEVICE_KEY,
    _build,
    _button,
    _fake_ctx,
    _fake_dialog as _fake_internet_dialog,
    _out,
    _profile,
    _sb_mock,
)

_IFACE = "GigabitEthernet0/0/0"


def _preset(flow: str = "internet", **over) -> TrafficPolicyPreset:
    base = dict(
        device_key=_DEVICE_KEY,
        flow=flow,
        classifier="C_OLD",
        behavior="B_OLD",
        policy="P_OLD",
        behavior_action="permit",
        acl_number=3000,
        interface=_IFACE,
        direction="outbound",
        applied=True,
        preexisting=False,
    )
    base.update(over)
    return TrafficPolicyPreset(**base)


def _chain(**over) -> TrafficPolicyChain:
    base = dict(
        classifier="C_NEW", behavior="B_NEW", policy="P_NEW", action="permit"
    )
    base.update(over)
    return TrafficPolicyChain(**base)


def _running_with(chain: TrafficPolicyChain, acl: int = 3000) -> str:
    return "\n".join(
        [
            *render_chain(chain, str(acl))[0],
            f"interface {_IFACE}",
            f"traffic-policy {chain.policy} outbound",
            "quit",
        ]
    )


class TestPresetReachesDialog:
    def test_internet_dialog_receives_saved_chain(self, qtbot, monkeypatch,
                                                  tmp_path):
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        save_preset(_preset(behavior_action="deny"))
        ctx = _fake_ctx(sb=_sb_mock(running_config=""))
        _tab, widget = _build(qtbot, ctx, "svc-acl")
        cap = _fake_internet_dialog(monkeypatch, reject=True)

        _button(widget, "Bloquear Internet").click()

        assert cap["chain"] is not None
        assert cap["chain"].policy == "P_OLD"
        assert cap["chain"].action == "deny"

    def test_site_dialog_receives_saved_chain(self, qtbot, monkeypatch,
                                              tmp_path):
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        save_preset(_preset(flow="site"))
        ctx = _fake_ctx(sb=_sb_mock(running_config=""))
        _tab, widget = _build(qtbot, ctx, "svc-acl")
        from tests.tabs.services.test_block_site import (
            _fake_dialog as _fake_site_dialog,
        )

        cap = _fake_site_dialog(monkeypatch, reject=True)

        _button(widget, "Bloquear site").click()

        assert cap["chain"] is not None
        assert cap["chain"].policy == "P_OLD"


class TestInternetChainLifecycle:
    def test_save_persists_without_touching_device(self, qtbot, monkeypatch,
                                                   tmp_path):
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        ctx = _fake_ctx(sb=_sb_mock(running_config=""))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        decision = BlockInternetDecision(
            action="apply", profile=_profile(), save=False,
            chain=_chain(), config_action="save",
        )
        _fake_internet_dialog(monkeypatch, decision=decision)

        _button(widget, "Bloquear Internet").click()

        saved = load_preset(_DEVICE_KEY, "internet")
        assert saved is not None
        assert saved.policy == "P_NEW"
        assert not ctx.sb.send_config_block.called
        assert "salva localmente" in _out(tab).lower()

    def test_update_sends_new_chain_and_persists(self, qtbot, monkeypatch,
                                                  tmp_path):
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        save_preset(_preset())
        chain = _chain()
        ctx = _fake_ctx(sb=_sb_mock(running_config=_running_with(chain)))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        decision = BlockInternetDecision(
            action="apply", profile=_profile(), save=True,
            chain=chain, config_action="update",
        )
        _fake_internet_dialog(monkeypatch, decision=decision)

        _button(widget, "Bloquear Internet").click()

        lines = ctx.sb.send_config_block.call_args.args[0]
        assert "undo traffic-policy P_OLD outbound" in lines
        assert "traffic policy P_NEW" in lines
        assert "traffic-policy P_NEW outbound" in lines
        saved = load_preset(_DEVICE_KEY, "internet")
        assert saved is not None
        assert saved.policy == "P_NEW"

    def test_delete_removes_chain_preset_but_keeps_acl(self, qtbot, monkeypatch,
                                                       tmp_path):
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        save_profile(None, _profile(applied=True))
        save_preset(_preset())
        ctx = _fake_ctx(sb=_sb_mock(running_config=f"interface {_IFACE}\n"))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        decision = BlockInternetDecision(
            action="unapply", profile=_profile(applied=True), save=True,
            chain=_chain(), config_action="delete",
        )
        _fake_internet_dialog(monkeypatch, decision=decision)

        _button(widget, "Bloquear Internet").click()

        lines = ctx.sb.send_config_block.call_args.args[0]
        assert "undo traffic-policy P_OLD outbound" in lines
        assert "undo traffic policy P_OLD" in lines
        assert not any("undo acl" in ln for ln in lines), lines
        assert load_preset(_DEVICE_KEY, "internet") is None
        assert load_profile(None, _DEVICE_KEY) is not None
        assert tab.state.last_config_command is not None


class TestSiteChainLifecycle:
    def test_save_site_chain_without_device(self, qtbot, monkeypatch,
                                            tmp_path):
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        ctx = _fake_ctx(sb=_sb_mock(running_config=""))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        from tests.tabs.services.test_block_site import (
            _fake_dialog as _fake_site_dialog,
        )

        decision = BlockSiteDecision(
            strategy="deny-list", acl_number=3100, interface=_IFACE,
            direction="outbound", destinations=("10.1.2.3",),
            resolved=(("10.1.2.3", "0.0.0.0"),), save=False,
            chain=_chain(), config_action="save",
        )
        _fake_site_dialog(monkeypatch, decision=decision)

        _button(widget, "Bloquear site").click()

        saved = load_preset(_DEVICE_KEY, "site")
        assert saved is not None
        assert saved.policy == "P_NEW"
        assert not ctx.sb.send_config_block.called

    def test_update_site_chain_sends_both_policies(self, qtbot, monkeypatch,
                                                   tmp_path):
        monkeypatch.setenv("HW_DATA_DIR", str(tmp_path))
        save_preset(_preset(flow="site", acl_number=3100))
        chain = _chain()
        ctx = _fake_ctx(sb=_sb_mock(running_config=_running_with(chain, 3100)))
        _tab, widget = _build(qtbot, ctx, "svc-acl")
        from tests.tabs.services.test_block_site import (
            _fake_dialog as _fake_site_dialog,
        )

        decision = BlockSiteDecision(
            strategy="deny-list", acl_number=3100, interface=_IFACE,
            direction="outbound", destinations=("10.1.2.3",),
            resolved=(("10.1.2.3", "0.0.0.0"),), save=True,
            chain=chain, config_action="update",
        )
        _fake_site_dialog(monkeypatch, decision=decision)

        _button(widget, "Bloquear site").click()

        lines = ctx.sb.send_config_block.call_args.args[0]
        assert "undo traffic-policy P_OLD outbound" in lines
        assert "traffic policy P_NEW" in lines
        saved = load_preset(_DEVICE_KEY, "site")
        assert saved is not None
        assert saved.policy == "P_NEW"
