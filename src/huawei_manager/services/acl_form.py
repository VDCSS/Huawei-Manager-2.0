"""Formulário composto de ACL (criação + regras + aplicação).

Escopo (VRP CLI):

* **Identificação** — ACL básica (2000–2999) ou avançada (3000–3999),
  identificada por **número** ou por **nome** (mutuamente exclusivos).
* **Regras** — uma ou mais linhas ``rule <id> <permit|deny> ...``.
* **Aplicação** — ``traffic-filter`` em interface(s) e/ou ``acl ... inbound``
  em ``user-interface vty``.

Sintaxe VRP (verificada no NE40E / VRP 8.180 — EVE-NG):

* ACL básica: ``rule 5 permit source 10.0.0.0 0.0.0.255`` (sem protocolo,
  sem destino).
* ACL avançada: ``rule 5 permit ip source 10.0.0.0 0.0.0.255 destination any
  destination-port eq 443`` — o destino é **obrigatório** quando há porta e a
  palavra-chave é ``destination-port`` (não ``eq`` solto).
* ``acl name <nome>`` aceita sufixo ``basic`` ou ``advance`` (não "advanced").
* ``acl number <n> name <x>`` é **rejeitado** pelo device ("Too many
  parameters") — por isso o modo "ambos" não existe (ver
  :data:`SUPPORTS_ACL_NUMBER_AND_NAME`).
* Em ``user-interface vty`` o comando de remoção é ``undo acl inbound``
  (não ``undo acl <n> inbound``).
"""
from __future__ import annotations

import re

from huawei_manager.basic_config.params import ParamKind
from huawei_manager.exceptions import SdnValidationError
from huawei_manager.services.form_spec import (
    FormField,
    FormSection,
    FormSpec,
    FormValues,
    RenderedForm,
    require_field,
    section_rows,
)

#: A VRP aceita ``acl number <n> name <nome>``?
#:
#: **Não** — verificado no NE40E (VRP 8.180): o comando é recusado com
#: "Too many parameters". Fail-closed: enquanto não houver evidência
#: contrária, o modo "ambos" é rejeitado pelo validador do formulário.
SUPPORTS_ACL_NUMBER_AND_NAME = False

#: "basica" (2000-2999) / "avancada" (3000-3999).
_ACL_TYPE_RANGES = {"basica": (2000, 2999), "avancada": (3000, 3999)}
#: Sufixo do comando ``acl name`` na VRP.
_ACL_NAME_SUFFIX = {"basica": "basic", "avancada": "advance"}
#: Campos de regra que só existem em ACL avançada.
_ADVANCED_ONLY_RULE_FIELDS = (
    "protocol",
    "destination",
    "destination_wildcard",
    "destination_port",
)
#: Campos que a ACL básica **não** aceita (protocolo é apenas ignorado —
#: a sintaxe básica não tem protocolo, mas o valor não altera a semântica).
_BASIC_REJECTED_RULE_FIELDS = (
    "destination",
    "destination_wildcard",
    "destination_port",
)

ACL_FORM_SPEC = FormSpec(
    kind="acl",
    title="ACL — Criação, Regras e Aplicação",
    sections=(
        FormSection(
            key="identificacao",
            title="Identificação da ACL",
            fields=(
                FormField(
                    key="acl_type", label="Tipo de ACL",
                    kind=ParamKind.ENUM, default="avancada",
                    choices=("basica", "avancada"),
                    help="Básica: 2000–2999 (só origem). Avançada: 3000–3999.",
                ),
                FormField(
                    key="id_mode", label="Identificação",
                    kind=ParamKind.ENUM, default="numero",
                    choices=("numero", "nome"),
                    help="Número ou nome (exclusivos — a VRP não aceita ambos).",
                ),
                FormField(
                    key="acl_number", label="Número da ACL",
                    kind=ParamKind.ACL_ID, required=False, max_len=4,
                    depends_on=("id_mode", ("numero",)),
                    help="2000–2999 (básica) ou 3000–3999 (avançada).",
                ),
                FormField(
                    key="acl_name", label="Nome da ACL",
                    kind=ParamKind.ACL_NAME, required=False, max_len=32,
                    depends_on=("id_mode", ("nome",)),
                    help="1–32 caracteres: letras, números, '-' e '_'.",
                ),
            ),
        ),
        FormSection(
            key="rules",
            title="Regras",
            repeatable=True,
            min_rows=1,
            max_rows=50,
            fields=(
                FormField(
                    key="rule_id", label="ID da Regra",
                    kind=ParamKind.RULE_ID, minimum=0, maximum=65534,
                    help="Número da regra dentro da ACL (0–65534).",
                ),
                FormField(
                    key="action", label="Ação",
                    kind=ParamKind.ENUM, default="permit",
                    choices=("permit", "deny"),
                ),
                FormField(
                    key="protocol", label="Protocolo",
                    kind=ParamKind.ENUM, default="ip",
                    choices=("ip", "tcp", "udp", "icmp"),
                    depends_on=("acl_type", ("avancada",)),
                    help="Usado apenas em ACL avançada.",
                ),
                FormField(
                    key="source", label="Origem",
                    kind=ParamKind.WILDCARD,
                    help="Endereço de origem ou 'any'.",
                ),
                FormField(
                    key="source_wildcard", label="Máscara Origem",
                    kind=ParamKind.WILDCARD, required=False,
                    help="Máscara curinga da origem (ex.: 0.0.0.255).",
                ),
                FormField(
                    key="destination", label="Destino",
                    kind=ParamKind.WILDCARD, required=False,
                    depends_on=("acl_type", ("avancada",)),
                    help="Endereço de destino ou 'any' (só ACL avançada).",
                ),
                FormField(
                    key="destination_wildcard", label="Máscara Destino",
                    kind=ParamKind.WILDCARD, required=False,
                    depends_on=("acl_type", ("avancada",)),
                ),
                FormField(
                    key="destination_port", label="Porta Destino",
                    kind=ParamKind.PORT, required=False,
                    minimum=1, maximum=65535,
                    depends_on=("acl_type", ("avancada",)),
                    help="Somente para tcp/udp (comando 'destination-port eq').",
                ),
            ),
        ),
        FormSection(
            key="applications",
            title="Aplicação",
            repeatable=True,
            min_rows=0,
            max_rows=50,
            fields=(
                FormField(
                    key="where", label="Aplicar em",
                    kind=ParamKind.ENUM, default="interface",
                    choices=("interface", "vty"),
                ),
                FormField(
                    key="interface", label="Interface",
                    kind=ParamKind.INTERFACE, required=False,
                    depends_on=("where", ("interface",)),
                ),
                FormField(
                    key="direction", label="Direção",
                    kind=ParamKind.ENUM, default="inbound",
                    choices=("inbound", "outbound"),
                    depends_on=("where", ("interface",)),
                ),
                FormField(
                    key="vty_range", label="Faixa VTY",
                    kind=ParamKind.VTY_RANGE, default="0 4",
                    depends_on=("where", ("vty",)),
                ),
            ),
        ),
    ),
    consult_command="display acl all",
    # Allowlist declarada (não derivada das linhas renderizadas): qualquer
    # linha fora destes padrões é bloqueada pelo validador de política.
    allow_patterns=(
        r"^acl\s+number\s+\d{4}\s*$",
        r"^acl\s+name\s+[A-Za-z0-9_-]+\s+(basic|advance)\s*$",
        r"^rule\s+\d+\s+(permit|deny)\s+",
        r"^interface\s+\S+$",
        r"^traffic-filter\s+(inbound|outbound)\s+acl\s+\S+$",
        r"^user-interface\s+vty\s+\d+\s+\d+$",
        r"^acl\s+\S+\s+inbound$",
        r"^quit$",
        r"^undo\s+rule\s+\d+$",
        r"^undo\s+acl\s+number\s+\d{4}$",
        r"^undo\s+acl\s+name\s+[A-Za-z0-9_-]+$",
        r"^undo\s+acl\s+inbound$",
        r"^undo\s+traffic-filter\s+(inbound|outbound)\s+acl\s+\S+$",
    ),
    # Linhas que podem cortar o próprio acesso do operador → confirmação.
    confirm_patterns=(
        r"^traffic-filter\s+(inbound|outbound)\s+acl\s+\S+$",
        r"^acl\s+\S+\s+inbound$",
    ),
)


def _fail(message: str) -> SdnValidationError:
    return SdnValidationError(f"ACL inválida: {message}")


def _acl_existed(
    snapshot: str, id_mode: str, number: str, name: str
) -> bool:
    """A ACL **efetiva** já existia no snapshot?

    O modo de identificação é respeitado: uma ACL numérica não casa com
    ``acl name ...`` e vice-versa — evita que o rollback apague as regras de
    uma ACL homônima de outro tipo.
    """
    if id_mode == "numero" and number:
        return bool(
            re.search(
                rf"\bacl\s+number\s+{re.escape(number)}\b",
                snapshot,
                re.IGNORECASE,
            )
        )
    if id_mode == "nome" and name:
        return bool(
            re.search(
                rf"\bacl\s+name\s+{re.escape(name)}\b",
                snapshot,
                re.IGNORECASE,
            )
        )
    return False


def _rule_existed(snapshot: str, rendered_rule: str) -> bool:
    """A regra (já renderizada) existia no snapshot?"""
    return rendered_rule.strip().lower() in snapshot.lower()


def _render_rule(rule: dict[str, str], acl_type: str) -> str:
    """Renderiza uma linha ``rule`` conforme o tipo da ACL."""
    action = rule["action"]
    rule_id = rule["rule_id"]
    source = rule["source"]
    src_wc = rule.get("source_wildcard", "")
    dest = rule.get("destination", "")
    dst_wc = rule.get("destination_wildcard", "")
    port = rule.get("destination_port", "")

    if acl_type == "basica":
        # ACL básica: apenas origem (protocolo/destino/porta não existem).
        if dest or dst_wc:
            raise _fail("ACL básica não suporta origem/destino — use ACL avançada")
        if port:
            raise _fail("ACL básica não suporta porta de destino")
        if source == "any":
            if src_wc:
                raise _fail(
                    f"regra {rule_id}: máscara de origem é ignorada com 'any'"
                )
            return f"rule {rule_id} {action} source any"
        if not src_wc:
            raise _fail(f"regra {rule_id}: informe a máscara da origem")
        if src_wc == "any":
            raise _fail(
                f"regra {rule_id}: máscara da origem não pode ser 'any'"
            )
        return f"rule {rule_id} {action} source {source} {src_wc}"

    protocol = rule["protocol"]
    if port and protocol not in ("tcp", "udp"):
        raise _fail(
            f"regra {rule_id}: porta de destino exige protocolo tcp/udp"
        )
    if source == "any":
        if src_wc:
            raise _fail(
                f"regra {rule_id}: máscara de origem é ignorada com 'any'"
            )
        src_part = "source any"
    else:
        if not src_wc:
            raise _fail(f"regra {rule_id}: informe a máscara da origem")
        if src_wc == "any":
            raise _fail(
                f"regra {rule_id}: máscara da origem não pode ser 'any'"
            )
        src_part = f"source {source} {src_wc}"

    line = f"rule {rule_id} {action} {protocol} {src_part}"
    if dest:
        if dest == "any":
            if dst_wc:
                raise _fail(
                    f"regra {rule_id}: máscara de destino é ignorada com 'any'"
                )
            dest_part = "destination any"
        else:
            if not dst_wc:
                raise _fail(f"regra {rule_id}: informe a máscara do destino")
            if dst_wc == "any":
                raise _fail(
                    f"regra {rule_id}: máscara do destino não pode ser 'any'"
                )
            dest_part = f"destination {dest} {dst_wc}"
        line += f" {dest_part}"
        if port:
            # Sintaxe canônica da VRP: 'destination-port eq <porta>'.
            line += f" destination-port eq {port}"
    elif port:
        raise _fail(f"regra {rule_id}: porta de destino exige um destino")
    return line


def build_acl_form(values: FormValues) -> RenderedForm:
    """Valida, renderiza e prepara rollback do formulário de ACL."""
    ident_rows = section_rows(values, "identificacao")
    ident = ident_rows[0] if ident_rows else {}

    acl_type = ident.get("acl_type", "avancada")
    id_mode = ident.get("id_mode", "numero")
    raw_number = ident.get("acl_number", "")
    raw_name = ident.get("acl_name", "")

    if acl_type not in _ACL_TYPE_RANGES:
        raise _fail(f"tipo desconhecido: {acl_type}")
    if id_mode == "ambos" and not SUPPORTS_ACL_NUMBER_AND_NAME:
        raise _fail(
            "modo 'ambos' (número + nome) não é suportado pela VRP "
            "('acl number <n> name <x>' é recusado pelo device). "
            "Use apenas número ou apenas nome."
        )
    if id_mode not in ("numero", "nome"):
        raise _fail(f"modo de identificação desconhecido: {id_mode}")

    # ── identificação: SOMENTE o campo do modo efetivo é lido ──────
    # (campos do outro modo são ignorados — nunca "sobram" do formulário)
    number = ""
    name = ""
    if id_mode == "numero":
        number = require_field(ACL_FORM_SPEC, "acl_number").validate(raw_number)
        if not number:
            raise _fail("informe o número da ACL")
        low, high = _ACL_TYPE_RANGES[acl_type]
        if not low <= int(number) <= high:
            raise _fail(
                f"número {number} fora da faixa da ACL {acl_type} ({low}–{high})"
            )
    else:
        name = require_field(ACL_FORM_SPEC, "acl_name").validate(raw_name)
        if not name:
            raise _fail("informe o nome da ACL")

    # ── linhas de configuração ─────────────────────────────────────
    lines: list[str] = []
    if id_mode == "numero":
        lines.append(f"acl number {number}")
        header = f"acl number {number}"
        ref = number
    else:
        lines.append(f"acl name {name} {_ACL_NAME_SUFFIX[acl_type]}")
        header = f"acl name {name} {_ACL_NAME_SUFFIX[acl_type]}"
        ref = name

    rule_rows = section_rows(values, "rules")
    if not rule_rows:
        raise _fail("informe ao menos uma regra")

    anchors: list[str] = []
    rendered_rules: list[tuple[str, str]] = []  # (rule_id, linha renderizada)
    seen_rule_ids: set[str] = set()
    for row in rule_rows:
        rule = {
            "rule_id": row.get("rule_id", ""),
            "action": row.get("action", "permit"),
            "protocol": row.get("protocol", "ip"),
            "source": row.get("source", ""),
            "source_wildcard": row.get("source_wildcard", ""),
            "destination": row.get("destination", ""),
            "destination_wildcard": row.get("destination_wildcard", ""),
            "destination_port": row.get("destination_port", ""),
        }
        # Em ACL básica os campos avançados são rejeitados (destino/porta) ou
        # ignorados (protocolo — não existe na sintaxe básica).
        if acl_type == "basica":
            for key in _BASIC_REJECTED_RULE_FIELDS:
                if rule[key]:
                    raise _fail(
                        "ACL básica não suporta destino/porta — use ACL avançada"
                    )
            rule["protocol"] = ""
        # validação canônica (fonte única: validate_value)
        for key, value in list(rule.items()):
            if acl_type == "basica" and key == "protocol":
                continue
            rule[key] = require_field(ACL_FORM_SPEC, key).validate(value)
        if rule["rule_id"] in seen_rule_ids:
            raise _fail(f"ID de regra duplicado: {rule['rule_id']}")
        seen_rule_ids.add(rule["rule_id"])
        rendered = _render_rule(rule, acl_type)
        rendered_rules.append((rule["rule_id"], rendered))
        lines.append(rendered)
        anchors.append(rendered)

    lines.append("quit")

    # ── aplicações ─────────────────────────────────────────────────
    app_rows = section_rows(values, "applications")
    rendered_apps: list[tuple[str, list[str], list[str]]] = []
    for row in app_rows:
        where = row.get("where", "interface")
        if where == "interface":
            iface_name = require_field(
                ACL_FORM_SPEC, "interface").validate(row.get("interface", ""))
            if not iface_name:
                raise _fail("informe a interface da aplicação")
            if iface_name.upper() == "NULL0":
                raise _fail(
                    "NULL0 não é uma interface válida para aplicação de ACL"
                )
            dir_name = require_field(
                ACL_FORM_SPEC, "direction").validate(row.get("direction", "inbound"))
            block = [
                f"interface {iface_name}",
                f"traffic-filter {dir_name} acl {ref}",
                "quit",
            ]
            undo = [
                f"interface {iface_name}",
                f"undo traffic-filter {dir_name} acl {ref}",
                "quit",
            ]
            anchors.append(f"traffic-filter {dir_name} acl {ref}")
        else:
            vty_range = require_field(
                ACL_FORM_SPEC, "vty_range").validate(row.get("vty_range", "0 4"))
            block = [
                f"user-interface vty {vty_range}",
                f"acl {ref} inbound",
                "quit",
            ]
            # A VRP remove a política do VTY com 'undo acl inbound'
            # ('undo acl <n> inbound' é recusado pelo device).
            undo = [
                f"user-interface vty {vty_range}",
                "undo acl inbound",
                "quit",
            ]
            anchors.append(f"acl {ref} inbound")
        lines.extend(block)
        rendered_apps.append((where, block, undo))

    def rollback_builder(snapshot: str) -> list[str]:
        """Desfaz aplicações → regras → ACL (nesta ordem obrigatória)."""
        out: list[str] = []
        for _where, _block, undo in rendered_apps:
            out.extend(undo)
        if _acl_existed(snapshot, id_mode, number, name):
            # A ACL já existia: desfaz apenas as regras **novas** (as que já
            # estavam no snapshot não são tocadas).
            out.append(header)
            for rule_id, rendered in rendered_rules:
                if _rule_existed(snapshot, rendered):
                    continue
                out.append(f"undo rule {rule_id}")
            out.append("quit")
        else:
            # A ACL não existia: remove a ACL inteira.
            if id_mode == "numero":
                out.append(f"undo acl number {number}")
            else:
                out.append(f"undo acl name {name}")
        return out

    return RenderedForm(
        lines=tuple(lines),
        anchors=tuple(anchors),
        rollback_builder=rollback_builder,
    )
