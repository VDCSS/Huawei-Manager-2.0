"""Geração de CLI da feature de bloqueio (Bloquear Internet / site).

Módulo **puro** (sem Qt, sem rede): converte um
:class:`~huawei_manager.services.acl_presets.AclBlockProfile` no formato de
valores do formulário de ACL e devolve os blocos de configuração —
**reusando** o renderer canônico (:func:`render_form`) em vez de
reimplementar sintaxe VRP.

Três ações, com semântica distinta:

``apply``
    Cria/altera a ACL e fixa o ``traffic-filter`` na interface.
``unapply``
    Remove **só** o binding da interface — a ACL permanece (D9), para que
    o botão volte a ser "Aplicar" sem recriar nada.
``delete``
    Remove o binding e, se a ACL foi criada por nós
    (``created_from_snapshot=False``), remove também a ACL. Se a ACL já
    existia no device, ela é **preservada** (fail-closed — não apagamos
    configuração que não foi nossa).

Limitação (VRP): a imagem NE40E do EVE-NG (VRP 8.180) não implementa
``traffic-filter``; o modo MOCK é o baseline nesse ambiente.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable, Sequence

from huawei_manager.exceptions import SdnValidationError
from huawei_manager.services.acl_presets import AclBlockProfile
from huawei_manager.services.form_registry import render_form
from huawei_manager.services.form_spec import FormValues, RenderedForm

#: Ações suportadas pela feature de bloqueio.
ACTIONS = ("apply", "unapply", "delete")

#: Estratégias do "Bloquear site".
SITE_STRATEGIES = ("deny-list", "all-except")

#: Máximo de destinos por ACL de site (IDs de regra em passo 5 até 500;
#: a negação final do all-except usa 999 — sem colisão).
MAX_SITE_DESTINATIONS = 100

#: Posição/intervalo das regras geradas (compatível com o MVP: passo 5).
RULE_ID_START = 5
_RULE_ID_STEP = 5
#: ID da regra final do all-except (nega tudo o que não foi permitido).
_DENY_ALL_RULE_ID = "999"

#: Domínio RFC 1035 simplificado (labels alfanuméricos, TLD alfabético).
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z]{2,63}$"
)


def _fail(message: str) -> SdnValidationError:
    return SdnValidationError(f"Bloqueio inválido: {message}")


def profile_to_form_values(profile: AclBlockProfile) -> FormValues:
    """Converte o perfil no formato de valores do formulário ``acl``.

    ACL **avançada** identificada por **número** (3000–3999) — a única que
    aceita critério de destino, que é o que o bloqueio usa.
    """
    return {
        "identificacao": {
            "acl_type": "avancada",
            "id_mode": "numero",
            "acl_number": str(profile.acl_number),
            "acl_name": "",
        },
        "rules": [
            {
                "rule_id": str(RULE_ID_START),
                "action": "deny",
                "protocol": "ip",
                "source": "any",
                "source_wildcard": "",
                "destination": profile.destination_ip,
                "destination_wildcard": profile.destination_mask,
                "destination_port": "",
            },
        ],
        "applications": [
            {
                "where": "interface",
                "interface": profile.interface,
                "direction": profile.direction,
                "vty_range": "",
            },
        ],
    }


def apply_block(profile: AclBlockProfile) -> RenderedForm:
    """Renderiza o bloco de **aplicação** (ACL + binding) via renderer canônico.

    Raises:
        SdnValidationError: perfil fora do contrato ou renderização falhou.
    """
    from huawei_manager.services.acl_presets import validate_profile

    validated = validate_profile(profile)
    return render_form("acl", profile_to_form_values(validated))


def unapply_block(profile: AclBlockProfile) -> list[str]:
    """Linhas que removem **apenas** o binding da interface (ACL fica)."""
    from huawei_manager.services.acl_presets import validate_profile

    validated = validate_profile(profile)
    return [
        f"interface {validated.interface}",
        f"undo traffic-filter {validated.direction} acl {validated.acl_ref}",
        "quit",
    ]


def delete_block(profile: AclBlockProfile) -> list[str]:
    """Linhas de desativação completa (binding + ACL, quando é nossa).

    Se ``created_from_snapshot`` é ``True`` a ACL **pré-existia** no
    device: neste caso só o binding é removido e a ACL é preservada
    (não apagamos configuração que não foi nossa).
    """
    from huawei_manager.services.acl_presets import validate_profile

    validated = validate_profile(profile)
    lines = unapply_block(validated)
    if not validated.created_from_snapshot:
        lines.append(f"undo acl number {validated.acl_number}")
    return lines


def preview_lines(profile: AclBlockProfile, action: str) -> list[str]:
    """Bloco que será enviado para a ação indicada (para a revisão)."""
    if action not in ACTIONS:
        raise _fail(f"ação desconhecida: '{action}' (use {', '.join(ACTIONS)})")
    if action == "apply":
        return list(apply_block(profile).lines)
    if action == "unapply":
        return unapply_block(profile)
    return delete_block(profile)


def anchors_for(profile: AclBlockProfile, action: str) -> tuple[str, ...]:
    """Âncoras de verificação **pós-aplicação** para a ação indicada.

    ``apply``: as âncoras do renderer (regras + binding). As demais ações
    não têm âncora de presença — a verificação é de **ausência** (ver
    :func:`absence_check`).
    """
    if action not in ACTIONS:
        raise _fail(f"ação desconhecida: '{action}'")
    if action == "apply":
        return apply_block(profile).anchors
    return ()


def absence_check(profile: AclBlockProfile, action: str) -> tuple[str, ...]:
    """Trechos que precisam **desaparecer** do running-config.

    Usado nas ações ``unapply``/``delete``: o ``verify_fn`` do
    ``ConfigCommand`` recebe estas âncoras e reporta sucesso quando
    nenhuma delas está mais presente.
    """
    if action not in ACTIONS:
        raise _fail(f"ação desconhecida: '{action}'")
    if action == "apply":
        return ()
    check: list[str] = [
        f"traffic-filter {profile.direction} acl {profile.acl_ref}"
    ]
    if action == "delete" and not profile.created_from_snapshot:
        check.append(f"acl number {profile.acl_number}")
    return tuple(check)


def rollback_for(profile: AclBlockProfile, action: str) -> list[str]:
    """Linhas de rollback (desfaz a ação) para o snapshot anterior.

    * ``apply`` → reaplica o binding se ele existia no snapshot; caso
      contrário remove a ACL que nós criamos.
    * ``unapply`` → reaplica o binding (a ACL nunca foi tocada).
    * ``delete`` → reaplica o binding e, se a ACL era nossa, recria a ACL.
    """
    if action not in ACTIONS:
        raise _fail(f"ação desconhecida: '{action}'")
    ref = profile.acl_ref
    binding = [
        f"interface {profile.interface}",
        f"traffic-filter {profile.direction} acl {ref}",
        "quit",
    ]
    remove_binding = [
        f"interface {profile.interface}",
        f"undo traffic-filter {profile.direction} acl {ref}",
        "quit",
    ]
    if action == "unapply":
        return binding
    if action == "apply":
        # Desfazer uma aplicação = remover o binding que acabamos de pôr.
        return remove_binding
    # delete: recriar binding; a ACL só é recriada se era nossa.
    out = list(binding)
    if not profile.created_from_snapshot:
        out = _recreate_acl(profile) + out
    return out


def _recreate_acl(profile: AclBlockProfile) -> list[str]:
    """Recria a ACL a partir do perfil (usado pelo rollback do delete)."""
    rendered = apply_block(profile)
    lines = list(rendered.lines)
    # Mantém só a criação da ACL (header + regras + quit), sem binding.
    out: list[str] = []
    for line in lines:
        if line.startswith("interface "):
            break
        out.append(line)
    return out


# ── Bloquear site: destinos, estratégias e geração do bloco ───────────


def cidr_to_wildcard(prefix: str) -> str:
    """Converte prefixo CIDR (``0``–``32``) em máscara wildcard VRP."""
    try:
        p = int(prefix)
    except ValueError as exc:
        raise _fail(f"máscara CIDR inválida: '{prefix}'") from exc
    if not 0 <= p <= 32:
        raise _fail(f"prefixo fora do intervalo 0-32: {p}")
    mask = (0xFFFFFFFF << (32 - p)) & 0xFFFFFFFF
    return str(ipaddress.IPv4Address(mask ^ 0xFFFFFFFF))


def parse_destination(raw: str) -> tuple[str, str, str]:
    """Classifica um destino do Bloquear site.

    Returns:
        ``(kind, value, wildcard)`` — ``kind`` é ``"ip"`` (com
        ``value``/``wildcard`` prontos para a regra) ou ``"domain"``
        (``value`` = domínio, ``wildcard`` vazio — resolver depois).

    Raises:
        SdnValidationError: entrada não é IPv4[/máscara] nem domínio
            válido (fail-closed — nada de aceitar lixo silenciosamente).
    """
    token = raw.strip()
    if not token:
        raise _fail("destino vazio")
    if "/" in token:
        ip_part, _, prefix = token.partition("/")
        try:
            ipaddress.IPv4Address(ip_part)
        except ipaddress.AddressValueError as exc:
            raise _fail(f"destino inválido: '{raw}'") from exc
        return ("ip", ip_part, cidr_to_wildcard(prefix))
    try:
        ipaddress.IPv4Address(token)
        return ("ip", token, "0.0.0.0")
    except ipaddress.AddressValueError:
        pass
    if _DOMAIN_RE.match(token):
        return ("domain", token.lower(), "")
    raise _fail(
        f"destino inválido: '{raw}' (use IPv4, IPv4/máscara ou domínio)"
    )


def _dns_resolve(host: str) -> list[str]:
    """Resolve ``host`` em IPv4 (fail-closed se o DNS não responder)."""
    try:
        infos = socket.getaddrinfo(
            host, None, socket.AF_INET, socket.SOCK_STREAM
        )
    except OSError as exc:
        raise _fail(f"não foi possível resolver '{host}': {exc}") from exc
    seen: list[str] = []
    for info in infos:
        ip = str(info[4][0])
        if ip not in seen:
            seen.append(ip)
    return seen


def resolve_destinations(
    destinations: Sequence[str],
    resolver: Callable[[str], Sequence[str]] | None = None,
) -> tuple[tuple[str, str], ...]:
    """Resolve a lista de destinos em pares ``(ip, wildcard)``.

    IPs passam direto; domínios passam pelo ``resolver`` (DNS real por
    padrão — injetável em testes). Falha de resolução propaga
    ``SdnValidationError``: sem IP não há regra, e sem regra não há
    revisão (fail-closed).
    """
    resolve = resolver if resolver is not None else _dns_resolve
    out: list[tuple[str, str]] = []
    for raw in destinations:
        kind, value, wildcard = parse_destination(raw)
        if kind == "ip":
            out.append((value, wildcard))
            continue
        try:
            ips = resolve(value)
        except SdnValidationError:
            raise
        except OSError as exc:
            raise _fail(f"não foi possível resolver '{value}': {exc}") from exc
        if not ips:
            raise _fail(f"não foi possível resolver '{value}'")
        for ip in ips:
            try:
                ipaddress.IPv4Address(ip)
            except ipaddress.AddressValueError as exc:
                raise _fail(
                    f"DNS de '{value}' devolveu IP inválido: '{ip}'"
                ) from exc
            out.append((str(ip), "0.0.0.0"))
    return tuple(out)


def site_form_values(
    *,
    strategy: str,
    acl_number: int,
    interface: str,
    direction: str,
    resolved: Sequence[tuple[str, str]],
) -> FormValues:
    """Valores do formulário ACL para o Bloquear site.

    ``deny-list`` → uma regra ``deny`` por destino.
    ``all-except`` → uma regra ``permit`` por destino e uma regra final
    ``deny`` sem destino (nega tudo o que não foi permitido — a ACL é
    avaliada de cima para baixo, primeiro match vence).
    """
    if strategy not in SITE_STRATEGIES:
        raise _fail(
            f"estratégia desconhecida: '{strategy}' "
            f"(use {', '.join(SITE_STRATEGIES)})"
        )
    if len(resolved) > MAX_SITE_DESTINATIONS:
        raise _fail(
            f"máximo de {MAX_SITE_DESTINATIONS} destinos "
            f"(recebidos: {len(resolved)})"
        )
    action = "deny" if strategy == "deny-list" else "permit"
    rules: list[dict[str, str]] = []
    for i, (ip, wildcard) in enumerate(resolved):
        rules.append(
            {
                "rule_id": str((i + 1) * _RULE_ID_STEP),
                "action": action,
                "protocol": "ip",
                "source": "any",
                "source_wildcard": "",
                "destination": ip,
                "destination_wildcard": wildcard,
                "destination_port": "",
            }
        )
    if strategy == "all-except":
        rules.append(
            {
                "rule_id": _DENY_ALL_RULE_ID,
                "action": "deny",
                "protocol": "ip",
                "source": "any",
                "source_wildcard": "",
                "destination": "",
                "destination_wildcard": "",
                "destination_port": "",
            }
        )
    return {
        "identificacao": {
            "acl_type": "avancada",
            "id_mode": "numero",
            "acl_number": str(acl_number),
            "acl_name": "",
        },
        "rules": rules,
        "applications": [
            {
                "where": "interface",
                "interface": interface,
                "direction": direction,
                "vty_range": "",
            },
        ],
    }


def _site_rendered(
    *,
    strategy: str,
    acl_number: int,
    interface: str,
    direction: str,
    resolved: Sequence[tuple[str, str]],
) -> RenderedForm:
    values = site_form_values(
        strategy=strategy,
        acl_number=acl_number,
        interface=interface,
        direction=direction,
        resolved=resolved,
    )
    return render_form("acl", values)


def preview_site_lines(
    *,
    strategy: str,
    acl_number: int,
    interface: str,
    direction: str,
    resolved: Sequence[tuple[str, str]],
) -> list[str]:
    """Bloco do Bloquear site para a revisão (renderizador canônico)."""
    return list(
        _site_rendered(
            strategy=strategy,
            acl_number=acl_number,
            interface=interface,
            direction=direction,
            resolved=resolved,
        ).lines
    )


def site_anchors(
    *,
    strategy: str,
    acl_number: int,
    interface: str,
    direction: str,
    resolved: Sequence[tuple[str, str]],
) -> tuple[str, ...]:
    """Âncoras de verificação pós-aplicação do Bloquear site."""
    return tuple(
        _site_rendered(
            strategy=strategy,
            acl_number=acl_number,
            interface=interface,
            direction=direction,
            resolved=resolved,
        ).anchors
    )


def site_rollback(
    *,
    acl_number: int,
    interface: str,
    direction: str,
    snapshot: str,
) -> list[str]:
    """Rollback da aplicação do Bloquear site.

    Remove sempre o binding da interface; remove também a ACL quando
    ela **não** existia no snapshot pré-aplicação (fail-closed: nunca
    apagamos configuração que não foi nossa).
    """
    lines = [
        f"interface {interface}",
        f"undo traffic-filter {direction} acl {acl_number}",
        "quit",
    ]
    if f"acl number {acl_number}" not in snapshot:
        lines.append(f"undo acl number {acl_number}")
    return lines
