"""Despacho dos formulários compostos da aba Serviços.

Ponto único de entrada para a UI: dado um ``form_kind`` (campo
``ServiceDef.form_kind``) devolve a especificação do formulário, e dado um
conjunto de valores devolve o bloco renderizado + âncoras de verificação +
rollback.
"""
from __future__ import annotations

import re

from huawei_manager.exceptions import SdnValidationError
from huawei_manager.services.acl_form import ACL_FORM_SPEC, build_acl_form
from huawei_manager.services.form_spec import (
    FormSpec,
    FormValues,
    RenderedForm,
)
from huawei_manager.services.route_form import ROUTE_FORM_SPEC, build_route_form

#: Formulários conhecidos, por ``ServiceDef.form_kind``.
_FORM_SPECS: dict[str, FormSpec] = {
    ACL_FORM_SPEC.kind: ACL_FORM_SPEC,
    ROUTE_FORM_SPEC.kind: ROUTE_FORM_SPEC,
}

_BUILDERS = {
    ACL_FORM_SPEC.kind: build_acl_form,
    ROUTE_FORM_SPEC.kind: build_route_form,
}


def get_form_spec(kind: str) -> FormSpec:
    """Devolve a especificação do formulário; erro se o kind é desconhecido."""
    try:
        return _FORM_SPECS[kind]
    except KeyError as exc:
        raise SdnValidationError(
            f"Formulário desconhecido: '{kind}'"
        ) from exc


def render_form(kind: str, values: FormValues) -> RenderedForm:
    """Valida e renderiza o formulário indicado."""
    try:
        builder = _BUILDERS[kind]
    except KeyError as exc:
        raise SdnValidationError(
            f"Formulário desconhecido: '{kind}'"
        ) from exc
    return builder(values)


def verify_anchors(rendered: RenderedForm) -> tuple[str, ...]:
    """Trechos que precisam existir no running-config após a aplicação."""
    return rendered.anchors


def rollback_lines(rendered: RenderedForm, snapshot: str) -> list[str]:
    """Linhas de rollback para o snapshot anterior à mudança."""
    if rendered.rollback_builder is None:
        return []
    return list(rendered.rollback_builder(snapshot))


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


#: ``rule <id> <ação> <protocolo> [critérios...]``
_RULE_ANCHOR_RE = re.compile(
    r"^rule\s+(?P<id>\d+)\s+(?P<action>permit|deny)\s+(?P<proto>\S+)"
    r"(?P<rest>.*)$"
)
#: Critérios concretos de uma regra (os "any" são redundantes na VRP: o
#: device normaliza ``rule 10 permit ip source any destination any`` para
#: ``rule 10 permit ip``).
_SOURCE_RE = re.compile(r"\bsource\s+(\S+)(?:\s+(\S+))?")
_DEST_RE = re.compile(r"\bdestination\s+(\S+)(?:\s+(\S+))?")
_PORT_RE = re.compile(r"\bdestination-port\s+eq\s+(\S+)")


def _rule_requirements(rest: str) -> list[str]:
    """Trechos que a regra precisa preservar (critérios concretos)."""
    required: list[str] = []
    match = _SOURCE_RE.search(rest)
    if match and match.group(1) != "any":
        required.append(f"source {match.group(1)}")
        if match.group(2) and match.group(2) != "any":
            required.append(f"source {match.group(1)} {match.group(2)}")
    match = _DEST_RE.search(rest)
    if match and match.group(1) != "any":
        required.append(f"destination {match.group(1)}")
        if match.group(2) and match.group(2) != "any":
            required.append(f"destination {match.group(1)} {match.group(2)}")
    match = _PORT_RE.search(rest)
    if match:
        required.append(f"destination-port eq {match.group(1)}")
    return required


def _rule_applied(lines: list[str], anchor: str) -> bool:
    """A regra da âncora está presente (semântica, não textual)?

    A VRP **normaliza** as regras: ``rule 10 permit ip source any
    destination any`` é gravado como ``rule 10 permit ip``. Por isso a
    comparação usa o prefixo (id + ação + protocolo) e exige apenas os
    critérios concretos (endereços e portas).
    """
    match = _RULE_ANCHOR_RE.match(anchor)
    if match is None:
        return False
    prefix = (
        f"rule {match.group('id')} {match.group('action')} "
        f"{match.group('proto')}"
    )
    required = _rule_requirements(match.group("rest"))
    for line in lines:
        if not line.startswith(prefix):
            continue
        if all(req in line for req in required):
            return True
    return False


def check_anchors(running_config: str, anchors: tuple[str, ...]) -> list[str]:
    """Retorna a lista de âncoras **ausentes** no running-config.

    Comparação por normalização (minúsculas + espaços colapsados), pois o
    device reformata o bloco ao exibi-lo. Regras de ACL são comparadas
    semanticamente (a VRP normaliza os critérios "any").
    """
    haystack = _normalize(running_config)
    lines = [
        _normalize(line) for line in running_config.splitlines() if line.strip()
    ]
    missing: list[str] = []
    for anchor in anchors:
        normalized = _normalize(anchor)
        if normalized in haystack:
            continue
        if normalized.startswith("rule ") and _rule_applied(lines, normalized):
            continue
        missing.append(anchor)
    return missing
