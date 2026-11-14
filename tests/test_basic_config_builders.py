"""Testes para adaptação de templates VRP por versão (VRP5 vs VRP8)."""

from huawei_manager.basic_config.models import (
    AdminUserConfig,
    BasicConfigPlan,
    InterfaceL3Config,
    SshConfig,
    VrpVersion,
)


def test_vrp8_uses_irreversible_cipher_for_local_user():
    plan = BasicConfigPlan(
        admin_user=AdminUserConfig(
            username="admin",
            password="S3nh@Forte12",
            privilege="15",
        )
    )
    lines = plan.build_lines(vrp_version=VrpVersion.VRP8)
    assert any("password irreversible-cipher" in l for l in lines)
    assert not any("password simple" in l for l in lines)


def test_vrp5_uses_simple_for_local_user():
    plan = BasicConfigPlan(
        admin_user=AdminUserConfig(
            username="admin",
            password="S3nh@Forte12",
            privilege="15",
        )
    )
    lines = plan.build_lines(vrp_version=VrpVersion.VRP5)
    assert any("password simple" in l for l in lines)
    assert not any("irreversible-cipher" in l for l in lines)


def test_vrp8_ssh_uses_irreversible_cipher():
    plan = BasicConfigPlan(
        ssh=SshConfig(username="sshuser", password="S3nh@Forte12", vty_range="0 4")
    )
    lines = plan.build_lines(vrp_version=VrpVersion.VRP8)
    assert any("password irreversible-cipher" in l for l in lines)


def test_vrp5_ssh_uses_simple_password():
    plan = BasicConfigPlan(
        ssh=SshConfig(username="sshuser", password="S3nh@Forte12", vty_range="0 4")
    )
    lines = plan.build_lines(vrp_version=VrpVersion.VRP5)
    assert any("password simple" in l for l in lines)
    assert not any("irreversible-cipher" in l for l in lines)


def test_vrp8_undo_portswitch_included_when_requested():
    plan = BasicConfigPlan(
        interface_l3=InterfaceL3Config(
            interface="GigabitEthernet1/0/1",
            ip="10.0.0.1",
            mask="255.255.255.0",
            undo_portswitch=True,
            is_switch=True,
        )
    )
    lines = plan.build_lines(vrp_version=VrpVersion.VRP8)
    assert any("undo portswitch" in l for l in lines)


def test_vrp5_undo_portswitch_omitted():
    plan = BasicConfigPlan(
        interface_l3=InterfaceL3Config(
            interface="GigabitEthernet1/0/1",
            ip="10.0.0.1",
            mask="255.255.255.0",
            undo_portswitch=True,
            is_switch=True,
        )
    )
    lines = plan.build_lines(vrp_version=VrpVersion.VRP5)
    assert not any("undo portswitch" in l for l in lines)


def test_router_undo_portswitch_omitted_even_vrp8():
    """Roteador nunca recebe undo portswitch, mesmo em VRP8."""
    plan = BasicConfigPlan(
        interface_l3=InterfaceL3Config(
            interface="GigabitEthernet1/0/1",
            ip="10.0.0.1",
            mask="255.255.255.0",
            undo_portswitch=True,
            is_switch=False,
        )
    )
    lines = plan.build_lines(vrp_version=VrpVersion.VRP8)
    assert not any("undo portswitch" in l for l in lines)


def test_unknown_defaults_to_vrp8_syntax():
    plan = BasicConfigPlan(
        admin_user=AdminUserConfig(username="u", password="SenhaForte123", privilege="15")
    )
    lines_unknown = plan.build_lines(vrp_version=VrpVersion.UNKNOWN)
    lines_vrp8 = plan.build_lines(vrp_version=VrpVersion.VRP8)
    assert lines_unknown == lines_vrp8


def test_build_rollback_lines_accepts_vrp_version():
    # build_rollback_lines não altera comportamento por versão, mas
    # deve aceitar o parâmetro sem erro.
    plan = BasicConfigPlan(
        interface_l3=InterfaceL3Config(
            interface="GigabitEthernet1/0/1",
            ip="10.0.0.1",
            mask="255.255.255.0",
        )
    )
    lines = plan.build_rollback_lines(vrp_version=VrpVersion.VRP5)
    assert any("undo ip address" in l for l in lines)
    lines_vrp8 = plan.build_rollback_lines(vrp_version=VrpVersion.VRP8)
    assert lines == lines_vrp8


def test_build_rollback_lines_skips_undo_when_local_user_existed_before():
    """Conta já existia no snapshot → rollback NÃO apaga (senha anterior
    desconhecida; restauração manual necessária)."""
    snapshot = """
aaa
 local-user admin password irreversible-cipher *****
 local-user admin privilege level 15
 local-user admin service-type ssh terminal
quit
"""
    plan = BasicConfigPlan(
        admin_user=AdminUserConfig(
            username="admin", password="SenhaNovaForte123", privilege="15"
        )
    )
    lines = plan.build_rollback_lines(vrp_version=VrpVersion.VRP8, snapshot=snapshot)
    assert not any("undo local-user" in l for l in lines), (
        "não deve gerar undo de usuário que já existia antes"
    )


def test_build_rollback_lines_undos_when_local_user_is_new():
    """Conta não existia no snapshot → rollback gera undo local-user."""
    snapshot = "sysname RTR\n"
    plan = BasicConfigPlan(
        admin_user=AdminUserConfig(
            username="novo", password="SenhaNovaForte123", privilege="15"
        )
    )
    lines = plan.build_rollback_lines(vrp_version=VrpVersion.VRP8, snapshot=snapshot)
    assert any("undo local-user novo" in l for l in lines)


def test_admin_user_services_rendered_in_block():
    plan = BasicConfigPlan(
        admin_user=AdminUserConfig(
            username="operador",
            password="SenhaForte1234",
            privilege="15",
            services="ssh terminal http",
        )
    )
    lines = plan.build_lines(vrp_version=VrpVersion.VRP8)
    assert any("service-type ssh terminal http" in l for l in lines)


def test_admin_user_services_omits_line_when_empty():
    plan = BasicConfigPlan(
        admin_user=AdminUserConfig(
            username="operador", password="SenhaForte1234", services=""
        )
    )
    lines = plan.build_lines(vrp_version=VrpVersion.VRP8)
    assert not any("service-type" in l for l in lines)
