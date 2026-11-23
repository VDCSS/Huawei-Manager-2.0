"""Geração de CLI da feature de bloqueio (Bloquear Internet / site).

Módulo **puro** (sem Qt, sem rede): converte um
:class:`~huawei_manager.services.acl_presets.AclBlockProfile` no formato de
valores do formulário de ACL e devolve os blocos de configuração —
**reusando** o renderer canônico (:func:`render_form`) em vez de
reimplementar sintaxe VRP.

Três ações, com semântica distinta:

``apply``
    Cria/altera a ACL e fixa a **cadeia traffic policy**
    (classifier → behavior → policy) na interface.
``unapply``
    Remove **só** o binding da interface — a ACL e a cadeia permanecem
    (D9), para que o botão volte a ser "Aplicar" sem recriar nada.
``delete``
    Remove o binding e, se a ACL foi criada por nós
    (``created_from_snapshot=False``), remove também a cadeia e a ACL.
    Se a ACL já existia no device, ela é **preservada** (fail-closed —
    não apagamos configuração que não foi nossa).

A aplicação usa a cadeia ``traffic policy`` (classifier → behavior →
policy), que é a forma canônica do Huawei e a única aceita por imagens
que não implementam ``traffic-filter`` (ver
:mod:`huawei_manager.services.traffic_policy`).
"""
from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from huawei_manager.exceptions import SdnValidationError
from huawei_manager.services.acl_presets import AclBlockProfile
from huawei_manager.services.form_registry import render_form, rollback_lines
from huawei_manager.services.form_spec import FormValues, RenderedForm
from huawei_manager.services.traffic_policy import (
    TrafficPolicyChain,
    render_chain,
    undo_chain,
    undo_interface_binding,
)

#: Ações suportadas pela feature de bloqueio.
ACTIONS = ("apply", "unapply", "delete")

#: Estratégias do "Bloquear site".
SITE_STRATEGIES = ("deny-list", "all-except")

#: Prefixo dos nomes da cadeia traffic policy de cada feature.
_CHAIN_PREFIX_INTERNET = "BLOQ"
_CHAIN_PREFIX_SITE = "SITE"

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


def _chain(prefix: str, acl_number: int) -> TrafficPolicyChain:
    """Nomes determinísticos da cadeia traffic policy de uma ACL.

    Derivados do número da ACL (por device, já que o perfil é por
    device): ``C_BLOQ_3000`` / ``B_BLOQ_3000`` / ``P_BLOQ_3000``. A ação
    do behavior é ``permit`` — o sistema respeita o permit/deny da
    própria ACL (necessário para o ``all-except`` do Bloquear site).
    """
    base = f"{prefix}_{acl_number}"
    return TrafficPolicyChain(
        classifier=f"C_{base}",
        behavior=f"B_{base}",
        policy=f"P_{base}",
        action="permit",
    )


def suggested_chain(prefix: str, acl_number: int) -> TrafficPolicyChain:
    """Cadeia determinística padrão (wrapper público de :func:`_chain`).

    A UI pode oferecer estes nomes como sugestão no formulário e depois
    devolver a cadeia (potencialmente editada) às funções deste módulo.
    """
    return _chain(prefix, acl_number)


def chain_anchors(
    chain: TrafficPolicyChain, *, acl_number: int, interface: str, direction: str
) -> tuple[str, ...]:
    """Âncoras de presença da cadeia customizada.

    São as âncoras canônicas de :func:`render_chain` mais o binding da
    policy na interface (o ``interface`` é aceito para simetria com as
    demais funções — o binding é identificado pela policy e direção).
    """
    return (
        *render_chain(chain, str(acl_number))[1],
        f"traffic-policy {chain.policy} {direction}",
    )


def chain_absence(
    chain: TrafficPolicyChain, *, interface: str, direction: str
) -> tuple[str, ...]:
    """Linhas canônicas da cadeia + binding para verificação de ausência.

    O chamador não informa a ACL aqui (ela não é removida junto da
    cadeia), então a linha ``if-match acl`` vem de ``render_chain`` com
    referência vazia. Todos os objetos da cadeia e o binding são trechos
    que devem desaparecer do ``running-config``.
    """
    return (
        *render_chain(chain, "")[0],
        f"traffic-policy {chain.policy} {direction}",
    )


def _preserved_snapshot(chain: TrafficPolicyChain) -> str:
    """Snapshot sintético que marca os objetos da cadeia como pré-existentes."""
    return "\n".join(
        (
            f"traffic classifier {chain.classifier}",
            f"traffic behavior {chain.behavior}",
            f"traffic policy {chain.policy}",
        )
    )


def _undo_existing_chain(
    chain: TrafficPolicyChain, preexisting: bool
) -> list[str]:
    """``undo_chain`` preservando objetos que já existiam no device."""
    snapshot = _preserved_snapshot(chain) if preexisting else ""
    return undo_chain(chain, snapshot)


def update_chain_lines(
    old: TrafficPolicyChain,
    new: TrafficPolicyChain,
    *,
    acl_number: int,
    interface: str,
    direction: str,
    preexisting: bool = False,
) -> list[str]:
    """Troca uma cadeia por outra sem tocar na ACL (ela permanece).

    Ordem: desaplicar o binding antigo → desfazer a cadeia antiga → criar
    a cadeia nova (via ``render_chain``) → aplicar o binding novo. Com
    ``preexisting=True`` os objetos antigos são preservados no device.
    """
    lines = list(undo_interface_binding(interface, old.policy, direction))
    lines.extend(_undo_existing_chain(old, preexisting))
    lines.extend(render_chain(new, str(acl_number))[0])
    lines.extend(
        [
            f"interface {interface}",
            f"traffic-policy {new.policy} {direction}",
            "quit",
        ]
    )
    return lines


def delete_chain_lines(
    old: TrafficPolicyChain,
    *,
    interface: str,
    direction: str,
    preexisting: bool = False,
) -> list[str]:
    """Remove binding e cadeia antiga, deixando a ACL intacta.

    Com ``preexisting=True`` os objetos da cadeia são preservados (só o
    binding é removido) — fail-closed, igual à política de ACL do módulo.
    """
    lines = list(undo_interface_binding(interface, old.policy, direction))
    lines.extend(_undo_existing_chain(old, preexisting))
    return lines


def profile_to_form_values(
    profile: AclBlockProfile, *, chain: TrafficPolicyChain | None = None
) -> FormValues:
    """Converte o perfil no formato de valores do formulário ``acl``.

    ACL **avançada** identificada por **número** (3000–3999) — a única que
    aceita critério de destino, que é o que o bloqueio usa. A aplicação é
    feita pela **cadeia traffic policy** (``where="traffic policy"``).
    """
    effective = chain if chain is not None else suggested_chain(
        _CHAIN_PREFIX_INTERNET, profile.acl_number
    )
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
        "traffic_policy": {
            "classifier_name": effective.classifier,
            "behavior_name": effective.behavior,
            "policy_name": effective.policy,
            "behavior_action": effective.action,
        },
        "applications": [
            {
                "where": "traffic policy",
                "interface": profile.interface,
                "direction": profile.direction,
                "vty_range": "",
            },
        ],
    }


def apply_block(
    profile: AclBlockProfile, *, chain: TrafficPolicyChain | None = None
) -> RenderedForm:
    """Renderiza o bloco de **aplicação** (ACL + binding) via renderer canônico.

    Raises:
        SdnValidationError: perfil fora do contrato ou renderização falhou.
    """
    from huawei_manager.services.acl_presets import validate_profile

    validated = validate_profile(profile)
    return render_form("acl", profile_to_form_values(validated, chain=chain))


def unapply_block(
    profile: AclBlockProfile, *, chain: TrafficPolicyChain | None = None
) -> list[str]:
    """Linhas que removem **apenas** o binding da interface (ACL e cadeia ficam)."""
    from huawei_manager.services.acl_presets import validate_profile

    validated = validate_profile(profile)
    effective = chain if chain is not None else suggested_chain(
        _CHAIN_PREFIX_INTERNET, validated.acl_number
    )
    return [
        f"interface {validated.interface}",
        f"undo traffic-policy {effective.policy} {validated.direction}",
        "quit",
    ]


def delete_block(
    profile: AclBlockProfile, *, chain: TrafficPolicyChain | None = None
) -> list[str]:
    """Linhas de desativação completa (binding + cadeia + ACL, quando é nossa).

    Se ``created_from_snapshot`` é ``True`` a ACL **pré-existia** no
    device: neste caso só o binding é removido e a ACL/cadeia são
    preservadas (não apagamos configuração que não foi nossa).
    """
    from huawei_manager.services.acl_presets import validate_profile

    validated = validate_profile(profile)
    lines = unapply_block(validated, chain=chain)
    if not validated.created_from_snapshot:
        effective = chain if chain is not None else suggested_chain(
            _CHAIN_PREFIX_INTERNET, validated.acl_number
        )
        lines.extend(undo_chain(effective, ""))
        lines.append(f"undo acl number {validated.acl_number}")
    return lines


def preview_lines(
    profile: AclBlockProfile, action: str, *,
    chain: TrafficPolicyChain | None = None,
) -> list[str]:
    """Bloco que será enviado para a ação indicada (para a revisão)."""
    if action not in ACTIONS:
        raise _fail(f"ação desconhecida: '{action}' (use {', '.join(ACTIONS)})")
    if action == "apply":
        return list(apply_block(profile, chain=chain).lines)
    if action == "unapply":
        return unapply_block(profile, chain=chain)
    return delete_block(profile, chain=chain)


def anchors_for(
    profile: AclBlockProfile, action: str, *,
    chain: TrafficPolicyChain | None = None,
) -> tuple[str, ...]:
    """Âncoras de verificação **pós-aplicação** para a ação indicada.

    ``apply``: as âncoras do renderer (regras + binding). As demais ações
    não têm âncora de presença — a verificação é de **ausência** (ver
    :func:`absence_check`).
    """
    if action not in ACTIONS:
        raise _fail(f"ação desconhecida: '{action}'")
    if action == "apply":
        return apply_block(profile, chain=chain).anchors
    return ()


def absence_check(
    profile: AclBlockProfile, action: str, *,
    chain: TrafficPolicyChain | None = None,
) -> tuple[str, ...]:
    """Trechos que precisam **desaparecer** do running-config.

    Usado nas ações ``unapply``/``delete``: o ``verify_fn`` do
    ``ConfigCommand`` recebe estas âncoras e reporta sucesso quando
    nenhuma delas está mais presente.
    """
    if action not in ACTIONS:
        raise _fail(f"ação desconhecida: '{action}'")
    if action == "apply":
        return ()
    effective = chain if chain is not None else suggested_chain(
        _CHAIN_PREFIX_INTERNET, profile.acl_number
    )
    check: list[str] = [
        f"traffic-policy {effective.policy} {profile.direction}"
    ]
    if action == "delete" and not profile.created_from_snapshot:
        check.extend(
            [
                f"traffic classifier {effective.classifier}",
                f"traffic behavior {effective.behavior}",
                f"traffic policy {effective.policy}",
                f"acl number {profile.acl_number}",
            ]
        )
    return tuple(check)


def rollback_for(
    profile: AclBlockProfile, action: str, snapshot: str, *,
    chain: TrafficPolicyChain | None = None,
) -> list[str]:
    """Linhas de rollback (desfaz a ação) para o snapshot anterior.

    * ``apply`` → usa o ``rollback_builder`` do renderer canônico, que
      remove binding → cadeia → ACL (preservando o que já existia).
    * ``unapply`` → reaplica o binding da policy (ACL/cadeia intactas).
    * ``delete`` → recria ACL + cadeia + binding quando a ACL era nossa.
    """
    if action not in ACTIONS:
        raise _fail(f"ação desconhecida: '{action}'")
    effective = chain if chain is not None else suggested_chain(
        _CHAIN_PREFIX_INTERNET, profile.acl_number
    )
    binding = [
        f"interface {profile.interface}",
        f"traffic-policy {effective.policy} {profile.direction}",
        "quit",
    ]
    if action == "apply":
        return rollback_lines(apply_block(profile, chain=chain), snapshot)
    if action == "unapply":
        return binding
    # delete: recriar binding; ACL + cadeia só se eram nossas.
    if profile.created_from_snapshot:
        return binding
    return list(apply_block(profile, chain=chain).lines)


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
    chain: TrafficPolicyChain | None = None,
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
    effective = chain if chain is not None else suggested_chain(
        _CHAIN_PREFIX_SITE, acl_number
    )
    return {
        "identificacao": {
            "acl_type": "avancada",
            "id_mode": "numero",
            "acl_number": str(acl_number),
            "acl_name": "",
        },
        "rules": rules,
        "traffic_policy": {
            "classifier_name": effective.classifier,
            "behavior_name": effective.behavior,
            "policy_name": effective.policy,
            "behavior_action": effective.action,
        },
        "applications": [
            {
                "where": "traffic policy",
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
    chain: TrafficPolicyChain | None = None,
) -> RenderedForm:
    values = site_form_values(
        strategy=strategy,
        acl_number=acl_number,
        interface=interface,
        direction=direction,
        resolved=resolved,
        chain=chain,
    )
    return render_form("acl", values)


def preview_site_lines(
    *,
    strategy: str,
    acl_number: int,
    interface: str,
    direction: str,
    resolved: Sequence[tuple[str, str]],
    chain: TrafficPolicyChain | None = None,
) -> list[str]:
    """Bloco do Bloquear site para a revisão (renderizador canônico)."""
    return list(
        _site_rendered(
            strategy=strategy,
            acl_number=acl_number,
            interface=interface,
            direction=direction,
            resolved=resolved,
            chain=chain,
        ).lines
    )


def site_anchors(
    *,
    strategy: str,
    acl_number: int,
    interface: str,
    direction: str,
    resolved: Sequence[tuple[str, str]],
    chain: TrafficPolicyChain | None = None,
) -> tuple[str, ...]:
    """Âncoras de verificação pós-aplicação do Bloquear site."""
    return tuple(
        _site_rendered(
            strategy=strategy,
            acl_number=acl_number,
            interface=interface,
            direction=direction,
            resolved=resolved,
            chain=chain,
        ).anchors
    )


def site_rollback(
    *,
    strategy: str,
    acl_number: int,
    interface: str,
    direction: str,
    resolved: Sequence[tuple[str, str]],
    snapshot: str,
    chain: TrafficPolicyChain | None = None,
) -> list[str]:
    """Rollback da aplicação do Bloquear site.

    Usa o ``rollback_builder`` do renderer canônico: remove o binding,
    desfaz a cadeia (preservando o que já existia no snapshot) e remove a
    ACL quando ela não existia antes (fail-closed: nunca apagamos
    configuração que não foi nossa).
    """
    rendered = _site_rendered(
        strategy=strategy,
        acl_number=acl_number,
        interface=interface,
        direction=direction,
        resolved=resolved,
        chain=chain,
    )
    return rollback_lines(rendered, snapshot)


# ── Passo a passo visual da cadeia traffic policy (para os modais) ─────


@dataclass(frozen=True)
class PolicyStep:
    """Um passo da cadeia exibido no wizard dos botões de bloqueio.

    ``lines`` são as linhas **exatas** que serão enviadas ao device: a
    concatenação de todos os passos reproduz o bloco canônico gerado por
    :func:`apply_block` / :func:`preview_site_lines` (ou o de remoção).
    """

    number: int
    title: str
    hint: str
    lines: tuple[str, ...]


#: Rótulos dos passos de criação (não contêm sintaxe VRP — vem do renderer).
_STEP_LABELS: dict[int, tuple[str, str]] = {
    1: (
        "ACL — define o tráfego",
        "Regras de permissão/negação que a cadeia vai casar.",
    ),
    2: (
        "Traffic Classifier — seleciona o tráfego",
        "Liga o classificador à ACL escolhida.",
    ),
    3: (
        "Traffic Behavior — define a ação",
        "permit = respeita as regras permit/deny da própria ACL.",
    ),
    4: (
        "Traffic Policy — liga classifier ao behavior",
        "A policy é o objeto aplicado na interface.",
    ),
    5: (
        "Aplicação na interface — ativa a policy",
        "Associa a policy à interface e à direção escolhidas.",
    ),
}

#: Rótulos dos passos de remoção (ordem inversa da criação).
_UNDO_LABELS: dict[int, tuple[str, str]] = {
    5: (
        "Desaplicar — remover o binding",
        "A ACL e a cadeia permanecem no device (D9).",
    ),
    4: (
        "Remover Traffic Policy",
        "Desfaz a ligação entre classifier e behavior.",
    ),
    3: ("Remover Traffic Behavior", "Remove a ação da cadeia."),
    2: (
        "Remover Traffic Classifier",
        "Remove o seletor de tráfego da ACL.",
    ),
    1: (
        "Remover ACL",
        "Só se a ACL foi criada por nós — pré-existente é preservada.",
    ),
}


def _subsequence_start(lines: Sequence[str], block: Sequence[str]) -> int:
    """Índice onde ``block`` aparece contíguo em ``lines`` (ou ``-1``)."""
    if not block or len(block) > len(lines):
        return -1
    for i in range(len(lines) - len(block) + 1):
        if list(lines[i:i + len(block)]) == list(block):
            return i
    return -1


def _split_chain_block(
    lines: Sequence[str], chain: TrafficPolicyChain, acl_ref: str
) -> tuple[list[str], list[str], list[str]]:
    """Separa ``(ACL, cadeia, binding)`` do bloco canônico gerado.

    A cadeia vem de :func:`render_chain` (3 linhas por objeto, na ordem
    classifier → behavior → policy); nada de sintaxe VRP reimplementada.
    """
    chain_lines = list(render_chain(chain, acl_ref)[0])
    start = _subsequence_start(lines, chain_lines)
    if start < 0:
        raise _fail("bloco renderizado não contém a cadeia traffic policy")
    return (
        list(lines[:start]),
        chain_lines,
        list(lines[start + len(chain_lines):]),
    )


def _step(number: int, lines: Sequence[str], labels: dict[int, tuple[str, str]]) -> PolicyStep:
    title, hint = labels[number]
    return PolicyStep(number, title, hint, tuple(lines))


def _apply_policy_steps(
    lines: Sequence[str], chain: TrafficPolicyChain, acl_ref: str, *,
    extra_hint: str = "",
) -> tuple[PolicyStep, ...]:
    acl_lines, chain_lines, binding = _split_chain_block(lines, chain, acl_ref)
    chunks = (acl_lines, chain_lines[:3], chain_lines[3:6], chain_lines[6:], binding)
    steps = [
        _step(i + 1, chunk, _STEP_LABELS) for i, chunk in enumerate(chunks)
    ]
    if extra_hint:
        first = steps[0]
        steps[0] = PolicyStep(
            first.number, first.title, f"{first.hint} {extra_hint}", first.lines
        )
    return tuple(steps)


def policy_steps(
    profile: AclBlockProfile, action: str, *,
    chain: TrafficPolicyChain | None = None,
) -> tuple[PolicyStep, ...]:
    """Passos da cadeia traffic policy do Bloquear Internet.

    * ``apply`` → ❶ ACL → ❷ classifier → ❸ behavior → ❹ policy → ❺ binding;
    * ``unapply`` → só ❺ (ACL/cadeia ficam — D9);
    * ``delete`` → ❺→❹→⓷→❷→❶ (a ACL só se for nossa — fail-closed).

    Raises:
        SdnValidationError: ação desconhecida ou perfil inválido.
    """
    from huawei_manager.services.acl_presets import validate_profile

    if action not in ACTIONS:
        raise _fail(f"ação desconhecida: '{action}' (use {', '.join(ACTIONS)})")
    validated = validate_profile(profile)
    effective = chain if chain is not None else suggested_chain(
        _CHAIN_PREFIX_INTERNET, validated.acl_number
    )

    if action == "apply":
        return _apply_policy_steps(
            apply_block(validated, chain=chain).lines,
            effective,
            str(validated.acl_number),
        )

    binding = unapply_block(validated, chain=chain)
    if action == "unapply":
        return (_step(5, binding, _UNDO_LABELS),)

    removal = delete_block(validated, chain=chain)
    tail = removal[len(binding):]
    undo_chain_lines = undo_chain(effective, "")
    undo_chain_part = tail[:len(undo_chain_lines)]
    undo_acl_part = tail[len(undo_chain_lines):]
    # ``undo_chain`` devolve uma linha por objeto (policy, behavior,
    # classifier) — diferente do ``render_chain`` (3 linhas por objeto).
    parts = {
        5: binding,
        4: undo_chain_part[0:1],
        3: undo_chain_part[1:2],
        2: undo_chain_part[2:3],
        1: undo_acl_part,
    }
    numbers = (5, 4, 3, 2, 1) if undo_acl_part else (5, 4, 3, 2)
    return tuple(_step(number, parts[number], _UNDO_LABELS) for number in numbers)


def site_policy_steps(
    *,
    strategy: str,
    acl_number: int,
    interface: str,
    direction: str,
    resolved: Sequence[tuple[str, str]],
    chain: TrafficPolicyChain | None = None,
) -> tuple[PolicyStep, ...]:
    """Passos da cadeia traffic policy do Bloquear site (5 etapas).

    As linhas vêm de :func:`preview_site_lines` — estratégia ``all-except``
    ganha uma dica extra sobre a regra final ``999``.
    """
    lines = preview_site_lines(
        strategy=strategy,
        acl_number=acl_number,
        interface=interface,
        direction=direction,
        resolved=resolved,
        chain=chain,
    )
    effective = chain if chain is not None else suggested_chain(
        _CHAIN_PREFIX_SITE, acl_number
    )
    extra = (
        "No all-except, a regra final 999 nega tudo o que não foi permitido."
        if strategy == "all-except"
        else ""
    )
    return _apply_policy_steps(
        lines, effective, str(acl_number), extra_hint=extra
    )
