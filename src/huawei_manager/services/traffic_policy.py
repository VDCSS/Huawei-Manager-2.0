"""Cadeia ``traffic policy`` — alternativa ao ``traffic-filter``.

A aplicação direta de uma ACL em interface (``traffic-filter <dir> acl
<ref>``) não existe em todas as imagens VRP. A cadeia canônica do Huawei
(submit) é:

1. **ACL** — ``acl number 3000`` + regras + ``quit``;
2. **Traffic Classifier** — ``traffic classifier C_BLOQUEIO`` /
   ``if-match acl 3000`` / ``quit``;
3. **Traffic Behavior** — ``traffic behavior B_ACAO`` / ``permit`` / ``quit``;
4. **Traffic Policy** — ``traffic policy P_FILTRO_INTERFACE`` /
   ``classifier C_BLOQUEIO behavior B_ACAO`` / ``quit``;
5. **Aplicação na interface** — ``interface GigabitEthernet0/0/1`` /
   ``traffic-policy P_FILTRO_INTERFACE inbound`` / ``quit``.

Semântica do *behavior* (importante): com ``permit`` o sistema respeita os
comandos ``permit``/``deny`` **da própria ACL**; com ``deny`` no behavior
tudo que casar com a ACL é bloqueado.

Este módulo é **puramente declarativo**: descreve a seção do formulário,
renderiza o bloco da cadeia e monta as linhas de ``undo`` (preservando o
estado pré-existente no snapshot). Nada aqui fala com o device.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from huawei_manager.basic_config.params import ParamKind
from huawei_manager.services.form_spec import FormField, FormSection

#: Chave da seção do formulário que descreve a cadeia traffic-policy.
TRAFFIC_POLICY_SECTION_KEY = "traffic_policy"

#: Ações válidas do *traffic behavior*.
BEHAVIOR_ACTIONS = ("permit", "deny")

#: Nomes dos objetos da cadeia (usados nos ``undo``).
_OBJECT_KINDS = ("classifier", "behavior", "policy")


@dataclass(frozen=True)
class TrafficPolicyChain:
    """Cadeia classifier → behavior → policy (nomes já validados)."""

    classifier: str
    behavior: str
    policy: str
    action: str = "permit"


def build_traffic_policy_section() -> FormSection:
    """Seção do formulário com os nomes da cadeia traffic-policy.

    Só são pedidos **nomes** (mais a ação do behavior): todo o resto da
    cadeia — ``if-match acl <ACL>``, ``classifier <C> behavior <B>`` e o
    ``traffic-policy <P> inbound`` na interface — é derivado
    automaticamente da ACL e da aplicação escolhidas.

    Todos os campos são **opcionais**: a cadeia só é renderizada quando
    alguma aplicação usa ``traffic policy``. Preencher os nomes sem
    configurar a aplicação é rejeitado (fail-closed) pelo renderizador.
    """
    return FormSection(
        key=TRAFFIC_POLICY_SECTION_KEY,
        title="Traffic Policy — só os nomes (classifier → behavior → policy)",
        hint=(
            "Preencha apenas os nomes (sem o comando): o 'if-match acl <ACL>', "
            "o 'classifier <C> behavior <B>' e o 'traffic-policy <P> inbound' "
            "são gerados automaticamente a partir da ACL e da interface "
            "escolhidas. O único campo além do nome é a ação do behavior."
        ),
        fields=(
            FormField(
                key="classifier_name",
                label="Classificador — nome",
                kind=ParamKind.VRP_NAME, required=False, max_len=32,
                help="Só o nome do classifier (sem 'traffic classifier'). "
                     "O 'if-match acl <ACL>' é gerado automaticamente a "
                     "partir da ACL aplicada. Ex.: C_BLOQUEIO",
            ),
            FormField(
                key="behavior_name",
                label="Behavior — nome",
                kind=ParamKind.VRP_NAME, required=False, max_len=32,
                help="Só o nome do behavior (sem 'traffic behavior'). A ação "
                     "do behavior é o campo seguinte. Ex.: B_ACAO",
            ),
            FormField(
                key="policy_name",
                label="Policy — nome",
                kind=ParamKind.VRP_NAME, required=False, max_len=32,
                help="Só o nome da policy (sem 'traffic policy'). É este "
                     "nome que vai na interface: 'traffic-policy <nome> "
                     "inbound'. O 'classifier <C> behavior <B>' é gerado "
                     "automaticamente. Ex.: P_FILTRO_INTERFACE",
            ),
            FormField(
                key="behavior_action",
                label="Ação do behavior",
                kind=ParamKind.ENUM, default="permit",
                choices=BEHAVIOR_ACTIONS,
                help="'permit' = o sistema respeita o permit/deny da própria "
                     "ACL. 'deny' = bloqueia TODO o tráfego que casar com a "
                     "ACL (inclusive as regras permit). Ex.: permit",
            ),
        ),
    )


def render_chain(chain: TrafficPolicyChain, acl_ref: str) -> tuple[
    tuple[str, ...], tuple[str, ...]
]:
    """Renderiza o bloco da cadeia.

    Args:
        chain: nomes já validados.
        acl_ref: referência da ACL (``3000`` ou o nome da ACL nomeada).

    Returns:
        ``(linhas, âncoras)`` — as âncoras são trechos que precisam existir
        no ``running-config`` para confirmar a aplicação.
    """
    lines = (
        f"traffic classifier {chain.classifier}",
        f"if-match acl {acl_ref}",
        "quit",
        f"traffic behavior {chain.behavior}",
        chain.action,
        "quit",
        f"traffic policy {chain.policy}",
        f"classifier {chain.classifier} behavior {chain.behavior}",
        "quit",
    )
    anchors = (
        f"traffic classifier {chain.classifier}",
        f"if-match acl {acl_ref}",
        f"traffic behavior {chain.behavior}",
        f"traffic policy {chain.policy}",
        f"classifier {chain.classifier} behavior {chain.behavior}",
    )
    return lines, anchors


def object_existed(snapshot: str, kind: str, name: str) -> bool:
    """O objeto da cadeia já existia no snapshot?

    Usado no rollback para **preservar** o estado pré-existente: um
    ``traffic classifier`` que já existia não pode ser removido.
    """
    if kind not in _OBJECT_KINDS or not name:
        return False
    return bool(
        re.search(
            rf"\btraffic\s+{re.escape(kind)}\s+{re.escape(name)}\b",
            snapshot,
            re.IGNORECASE,
        )
    )


def undo_chain(chain: TrafficPolicyChain, snapshot: str) -> list[str]:
    """Linhas de ``undo`` da cadeia (ordem inversa da criação).

    Só remove os objetos que **não** existiam no snapshot.
    """
    out: list[str] = []
    for kind, name in (
        ("policy", chain.policy),
        ("behavior", chain.behavior),
        ("classifier", chain.classifier),
    ):
        if object_existed(snapshot, kind, name):
            continue
        out.append(f"undo traffic {kind} {name}")
    return out


def undo_interface_binding(interface: str, policy: str, direction: str) -> list[str]:
    """Linhas de ``undo`` da aplicação da policy na interface."""
    return [
        f"interface {interface}",
        f"undo traffic-policy {policy} {direction}",
        "quit",
    ]
