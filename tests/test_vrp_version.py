"""Testes para detecção de versão VRP."""

from huawei_manager.basic_config.vrp_version import (
    VrpVersion,
    detect_vrp_version,
    is_vrp5,
    is_vrp8,
)


def test_detect_vrp5():
    output = """
Huawei Versatile Routing Platform Software
VRP (R) Version 5.170, ...
"""
    assert detect_vrp_version(output) == VrpVersion.VRP5


def test_detect_vrp8():
    output = """
Huawei Versatile Routing Platform Software
VRP (R) Version 8.200, ...
"""
    assert detect_vrp_version(output) == VrpVersion.VRP8


def test_detect_unknown():
    assert detect_vrp_version("") == VrpVersion.UNKNOWN
    assert detect_vrp_version("Versão desconhecida") == VrpVersion.UNKNOWN
    assert detect_vrp_version("Version 9.000") == VrpVersion.UNKNOWN


def test_is_vrp5():
    assert is_vrp5(VrpVersion.VRP5) is True
    assert is_vrp5(VrpVersion.VRP8) is False
    assert is_vrp5(VrpVersion.UNKNOWN) is False


def test_is_vrp8():
    assert is_vrp8(VrpVersion.VRP8) is True
    assert is_vrp8(VrpVersion.VRP5) is False
    assert is_vrp8(VrpVersion.UNKNOWN) is False


def test_vrp_version_str_enum():
    assert str(VrpVersion.VRP5) == "VRP5"
    assert str(VrpVersion.VRP8) == "VRP8"
    assert str(VrpVersion.UNKNOWN) == "UNKNOWN"
