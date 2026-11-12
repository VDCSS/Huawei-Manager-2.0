"""TDD da base compartilhada pelos formulários de Serviços (F0).

Cobre:
- ``ParamKind.ACL_NAME`` (nome de ACL nomeada VRP);
- ``ParamKind.INTERFACE`` aceitando ``NULL0`` (rota estática de descarte);
- ``requires_commit(UNKNOWN)`` → True (fail-closed: sem identificar a VRP
  assume-se a variante que exige commit explícito);
- ``ServiceDef.visible`` / ``ServiceDef.form_kind`` no catálogo.
"""
from __future__ import annotations

import pytest

from huawei_manager.basic_config.params import (
    ParamKind,
    ParamSpec,
    validate_value,
)
from huawei_manager.basic_config.vrp_version import VrpVersion, requires_commit
from huawei_manager.exceptions import SdnValidationError
from huawei_manager.services import SERVICE_REGISTRY, get_service_by_id


def _spec(kind: ParamKind, **kw) -> ParamSpec:
    return ParamSpec(key=kw.pop("key", "v"), label=kw.pop("label", "Valor"),
                     kind=kind, **kw)


class TestAclNameParam:
    def test_acl_name_accepts_letters_digits_dash_underscore(self):
        spec = _spec(ParamKind.ACL_NAME, max_len=32)
        assert validate_value(spec, "MGT_INBOUND") == "MGT_INBOUND"
        assert validate_value(spec, "acl-1") == "acl-1"

    def test_acl_name_rejects_invalid_chars(self):
        spec = _spec(ParamKind.ACL_NAME, max_len=32)
        with pytest.raises(SdnValidationError):
            validate_value(spec, "acl com espaco")
        with pytest.raises(SdnValidationError):
            validate_value(spec, "acl;shutdown")

    def test_acl_name_rejects_too_long(self):
        spec = _spec(ParamKind.ACL_NAME, max_len=32)
        with pytest.raises(SdnValidationError):
            validate_value(spec, "A" * 33)

    def test_acl_name_optional_when_not_required(self):
        spec = _spec(ParamKind.ACL_NAME, required=False, max_len=32)
        assert validate_value(spec, "") == ""


class TestNull0Interface:
    def test_null0_is_accepted_as_interface(self):
        spec = _spec(ParamKind.INTERFACE)
        assert validate_value(spec, "NULL0") == "NULL0"

    def test_null0_lowercase_is_rejected(self):
        """A VRP exige 'NULL0' maiúsculo; não normalizamos case."""
        spec = _spec(ParamKind.INTERFACE)
        with pytest.raises(SdnValidationError):
            validate_value(spec, "null0")


class TestRequiresCommitUnknown:
    def test_unknown_requires_commit_is_true(self):
        """Fail-closed: VRP não identificada assume o fluxo com commit."""
        assert requires_commit(VrpVersion.UNKNOWN) is True

    def test_vrp5_does_not_require_commit(self):
        assert requires_commit(VrpVersion.VRP5) is False

    def test_vrp8_requires_commit(self):
        assert requires_commit(VrpVersion.VRP8) is True


class TestServiceDefFormMetadata:
    def test_service_def_has_visible_and_form_kind_defaults(self):
        svc = get_service_by_id("router-routing-table")
        assert svc is not None
        assert svc.visible is True
        assert svc.form_kind is None

    def test_new_acl_service_is_visible_and_has_form_kind(self):
        svc = get_service_by_id("svc-acl")
        assert svc is not None, "serviço svc-acl ausente no catálogo"
        assert svc.visible is True
        assert svc.form_kind == "acl"
        assert svc.config_mode is True
        assert svc.category == "config-acl"

    def test_new_static_route_service_is_visible_and_has_form_kind(self):
        svc = get_service_by_id("svc-static-route")
        assert svc is not None, "serviço svc-static-route ausente no catálogo"
        assert svc.visible is True
        assert svc.form_kind == "static_route"
        assert svc.config_mode is True
        assert svc.category == "config-route"

    def test_legacy_acl_services_are_hidden_but_kept(self):
        """Entradas legadas permanecem no registro, mas invisíveis na UI."""
        legacy = [
            "router-config-acl-number",
            "router-config-acl-rule",
            "router-config-acl-create",
            "router-config-acl-rule-basic",
            "router-config-acl-rule-advanced",
            "router-config-traffic-filter",
            "router-config-vty-acl",
        ]
        for svc_id in legacy:
            svc = get_service_by_id(svc_id)
            assert svc is not None, f"{svc_id} não deve ser removido do catálogo"
            assert svc.visible is False, f"{svc_id} deveria estar oculto"

    def test_legacy_static_route_service_is_hidden_but_kept(self):
        svc = get_service_by_id("router-config-route-static")
        assert svc is not None
        assert svc.visible is False

    def test_registry_still_contains_every_service(self):
        """Nenhum serviço é removido do registro (só ocultado)."""
        ids = {s.id for s in SERVICE_REGISTRY}
        assert "router-config-acl-rule-basic" in ids
        assert "router-config-route-static" in ids
        assert "svc-acl" in ids
        assert "svc-static-route" in ids
