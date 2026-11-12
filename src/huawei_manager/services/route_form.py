"""Formulário composto de rota estática.

Sintaxe VRP:

``ip route-static <destino> <máscara> [interface] [next-hop] [preference <n>] [description <texto>]``

Regras:

* O **next-hop** ou a **interface** são obrigatórios (no mínimo um deles);
  ambos podem ser informados juntos.
* ``interface`` aceita ``NULL0`` (rota de descarte).
* ``preference`` é 1–255 (padrão VRP: 60).
* O rollback usa ``undo ip route-static <destino> <máscara> [next-hop]`` —
  **sem** ``preference``/``description`` (a VRP recusa
  ``undo ip route-static ... preference <n>`` com "Too many parameters").
* Rotas já existentes no snapshot **não** são removidas no rollback.
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

ROUTE_FORM_SPEC = FormSpec(
    kind="static_route",
    title="Rota Estática",
    sections=(
        FormSection(
            key="routes",
            title="Rotas",
            repeatable=True,
            min_rows=1,
            max_rows=50,
            fields=(
                FormField(
                    key="destination", label="Destino",
                    kind=ParamKind.IPV4,
                    help="Endereço de destino (ex.: 0.0.0.0).",
                ),
                FormField(
                    key="mask", label="Máscara",
                    kind=ParamKind.MASK,
                    help="Ex.: 255.255.255.0 ou /24.",
                ),
                FormField(
                    key="interface", label="Interface de Saída",
                    kind=ParamKind.INTERFACE, required=False,
                    help="Opcional (aceita NULL0). Ex.: GigabitEthernet0/0/0.",
                ),
                FormField(
                    key="next_hop", label="Next-Hop",
                    kind=ParamKind.IPV4, required=False,
                    help="Opcional — mas é obrigatório se não houver interface.",
                ),
                FormField(
                    key="preference", label="Preferência",
                    kind=ParamKind.INT, required=False,
                    minimum=1, maximum=255,
                    help="Opcional (1–255). Padrão VRP: 60.",
                ),
                FormField(
                    key="description", label="Descrição",
                    kind=ParamKind.TEXT, required=False, max_len=80,
                    help="Opcional — texto livre da rota.",
                ),
            ),
        ),
    ),
    consult_command="display ip routing-table",
    allow_patterns=(
        r"^ip\s+route-static\s+\S+\s+\S+",
        r"^undo\s+ip\s+route-static\s+\S+\s+\S+",
    ),
)


def _fail(message: str) -> SdnValidationError:
    return SdnValidationError(f"Rota estática inválida: {message}")


def _route_existed(
    snapshot: str, dest: str, mask: str, iface: str, next_hop: str
) -> bool:
    """A rota (identidade destino/máscara/interface/next-hop) já existia?"""
    pattern = re.compile(
        rf"^\s*ip\s+route-static\s+{re.escape(dest)}\s+{re.escape(mask)}"
        rf"(?:\s+{re.escape(iface)})?"
        rf"(?:\s+{re.escape(next_hop)})?",
        re.IGNORECASE | re.MULTILINE,
    )
    return bool(pattern.search(snapshot))


def build_route_form(values: FormValues) -> RenderedForm:
    """Valida, renderiza e prepara rollback do formulário de rota estática."""
    rows = section_rows(values, "routes")
    if not rows:
        raise _fail("informe ao menos uma rota")

    lines: list[str] = []
    anchors: list[str] = []
    undo_lines: list[str] = []
    created: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    for row in rows:
        dest_fld = require_field(ROUTE_FORM_SPEC, "destination")
        mask_fld = require_field(ROUTE_FORM_SPEC, "mask")
        iface_fld = require_field(ROUTE_FORM_SPEC, "interface")
        nh_fld = require_field(ROUTE_FORM_SPEC, "next_hop")
        pref_fld = require_field(ROUTE_FORM_SPEC, "preference")
        desc_fld = require_field(ROUTE_FORM_SPEC, "description")

        dest = dest_fld.validate(row.get("destination", ""))
        mask = mask_fld.validate(row.get("mask", ""))
        iface = iface_fld.validate(row.get("interface", ""))
        next_hop = nh_fld.validate(row.get("next_hop", ""))
        preference = pref_fld.validate(row.get("preference", ""))
        description = desc_fld.validate(row.get("description", ""))

        if not next_hop and not iface:
            raise _fail(
                f"rota {dest} {mask}: informe o next-hop ou a interface de saída"
            )
        # Identidade completa da rota: o mesmo destino/máscara pode existir
        # com next-hop ou preferências diferentes (rota flutuante/ECMP).
        key = (dest, mask, iface, next_hop, preference)
        if key in seen:
            raise _fail(
                f"rota duplicada: {dest} {mask}"
                + (f" {next_hop}" if next_hop else "")
            )
        seen.add(key)

        line = f"ip route-static {dest} {mask}"
        # Undo: sem 'preference'/'description' (recusados pela VRP).
        undo = f"undo ip route-static {dest} {mask}"
        if iface:
            line += f" {iface}"
            undo += f" {iface}"
        if next_hop:
            line += f" {next_hop}"
            undo += f" {next_hop}"
        if preference:
            line += f" preference {preference}"
        if description:
            line += f" description {description}"

        lines.append(line)
        anchors.append(line)
        undo_lines.append(undo)
        created.append((dest, mask, iface, next_hop))

    def rollback_builder(snapshot: str) -> list[str]:
        """Desfaz as rotas criadas (ordem inversa à de criação).

        Rotas que já existiam no snapshot são preservadas.
        """
        out: list[str] = []
        for undo, (dest, mask, iface, next_hop) in reversed(
            list(zip(undo_lines, created))
        ):
            if _route_existed(snapshot, dest, mask, iface, next_hop):
                continue
            out.append(undo)
        return out

    return RenderedForm(
        lines=tuple(lines),
        anchors=tuple(anchors),
        rollback_builder=rollback_builder,
    )
