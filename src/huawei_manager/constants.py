from __future__ import annotations

# ─── PALETA NEON ─────────────────────────────────────────────────────
BG_BASE     = "#0d0d1a"
BG_CARD     = "#13132b"
BG_SIDEBAR  = "#0a0a18"
BG_INPUT    = "#1a1a30"

NEON_CYAN  = "#00e5ff"
NEON_MAG   = "#e040fb"
NEON_PURP  = "#8f6bff"
NEON_AMBER = "#ffab00"
NEON_RED   = "#ff4d4d"

FG_MAIN    = "#e0e0ff"
FG_DIM     = "#8a8abe"
FG_CODE    = "#c8c8ff"

BORDER_NRM = "#2a2a4a"

# ─── FONTES — UI (Proporcional) ──────────────────────────────────────
_FONT_UI_FAMILY       = "IBM Plex Sans"
_FONT_UI_TITLE_FAMILY = "Space Grotesk"
_FONT_MONO_FAMILY     = "JetBrains Mono"
_FALLBACK_UI          = "Inter"
_FALLBACK_MONO        = "Consolas"

# Família da UI exposta para stylesheets QSS montados em f-strings
FONT_UI_FAMILY         = _FONT_UI_FAMILY

FONT_UI_MEDIUM        = (_FONT_UI_FAMILY, 12, _FALLBACK_UI)           # sidebar, botões, inputs
FONT_UI_MEDIUM_B      = (_FONT_UI_FAMILY, 12, "bold", _FALLBACK_UI)
FONT_UI_TITLE         = (_FONT_UI_TITLE_FAMILY, 16, _FALLBACK_UI)    # títulos de página/seção
FONT_UI_TITLE_B       = (_FONT_UI_TITLE_FAMILY, 16, "bold", _FALLBACK_UI)

# Escala de fontes da UI (pt) — 4 passos
FONT_CAPTION = 11
FONT_BODY    = 12
FONT_SUBHEAD = 14
FONT_TITLE   = 16

# Único formato de backup suportado (running-config → .txt)
BACKUP_FMT_TEXT = "Texto (.txt)"

# ─── FONTES — Código (Monospace) ───────────────────────────────────
FONT_XSMALL      = (_FONT_MONO_FAMILY, 9, _FALLBACK_MONO)      # type_item no canvas
FONT_CANVAS_BODY = (_FONT_MONO_FAMILY, 11, _FALLBACK_MONO)     # SDN bar count, address items
FONT_LARGE       = (_FONT_MONO_FAMILY, 13, _FALLBACK_MONO)     # código / output principal
FONT_H1          = (_FONT_MONO_FAMILY, 16, _FALLBACK_MONO)     # SDN bar symbol

FONT_MEDIUM_B    = (_FONT_MONO_FAMILY, 12, "bold", _FALLBACK_MONO)  # name_item no canvas
FONT_LARGE_B     = (_FONT_MONO_FAMILY, 13, "bold", _FALLBACK_MONO)  # SDN bar label

THEME = {
    "BG_BASE":    BG_BASE,    "BG_CARD":    BG_CARD,
    "BG_SIDEBAR": BG_SIDEBAR, "BG_INPUT":   BG_INPUT,
    "NEON_CYAN":  NEON_CYAN,  "NEON_MAG":   NEON_MAG,
    "NEON_PURP":  NEON_PURP,  "NEON_AMBER": NEON_AMBER,
    "NEON_RED":   NEON_RED,
    "FG_MAIN":    FG_MAIN,    "FG_DIM":     FG_DIM,
    "FG_CODE":    FG_CODE,    "BORDER_NRM": BORDER_NRM,
}

# ─── PALETA CLARA (Light Theme) ──────────────────────────────────────
BG_BASE_L     = "#f0f0f8"
BG_CARD_L     = "#ffffff"
BG_SIDEBAR_L  = "#e8e8f0"
BG_INPUT_L    = "#fafafe"

NEON_CYAN_L   = "#0098a0"
NEON_MAG_L    = "#a030c0"
NEON_PURP_L   = "#5a20c0"
NEON_AMBER_L  = "#8a5a00"
NEON_RED_L    = "#c62828"

FG_MAIN_L     = "#1a1a2e"
FG_DIM_L      = "#6a6a8a"
FG_CODE_L     = "#2a2a40"

BORDER_NRM_L  = "#c0c0d0"

LIGHT_THEME = {
    "BG_BASE":    BG_BASE_L,    "BG_CARD":    BG_CARD_L,
    "BG_SIDEBAR": BG_SIDEBAR_L, "BG_INPUT":   BG_INPUT_L,
    "NEON_CYAN":  NEON_CYAN_L,  "NEON_MAG":   NEON_MAG_L,
    "NEON_PURP":  NEON_PURP_L,  "NEON_AMBER": NEON_AMBER_L,
    "NEON_RED":   NEON_RED_L,
    "FG_MAIN":    FG_MAIN_L,    "FG_DIM":     FG_DIM_L,
    "FG_CODE":    FG_CODE_L,    "BORDER_NRM": BORDER_NRM_L,
}

# Cópia congelada do tema escuro — NUNCA mutada, usada como fonte para re-aplicar dark
DARK_THEME = THEME.copy()

_active_theme: str = "dark"


def set_theme(name: str) -> None:
    """Swap all module-level colour constants to the named palette."""
    global _active_theme
    global BG_BASE, BG_CARD, BG_SIDEBAR, BG_INPUT
    global NEON_CYAN, NEON_MAG, NEON_PURP, NEON_AMBER, NEON_RED
    global FG_MAIN, FG_DIM, FG_CODE, BORDER_NRM

    pal = LIGHT_THEME if name == "light" else DARK_THEME

    BG_BASE    = pal["BG_BASE"]
    BG_CARD    = pal["BG_CARD"]
    BG_SIDEBAR = pal["BG_SIDEBAR"]
    BG_INPUT   = pal["BG_INPUT"]
    NEON_CYAN  = pal["NEON_CYAN"]
    NEON_MAG   = pal["NEON_MAG"]
    NEON_PURP  = pal["NEON_PURP"]
    NEON_AMBER = pal["NEON_AMBER"]
    NEON_RED   = pal["NEON_RED"]
    FG_MAIN    = pal["FG_MAIN"]
    FG_DIM     = pal["FG_DIM"]
    FG_CODE    = pal["FG_CODE"]
    BORDER_NRM = pal["BORDER_NRM"]

    THEME.clear()
    THEME.update(pal)
    _active_theme = name

# ─── COMANDOS CLI — filtros da aba Roteamento ───────────────────────
CLI_FILTERS: dict[str, str] = {
    "interfaces":          "display interface",
    "interfaces_counters": "display counters interface",
    "routing":             "display ip routing-table",
    "bgp":                 "display bgp peer",
    "vrfs":                "display ip vpn-instance",
    "ospf":                "display ospf peer",
    "lldp":                "display lldp neighbor brief",
    "qos":                 "display qos policy",
    "huawei_mpls":         "display mpls ldp peer",
}

# ─── ROTULOS DESCRITIVOS para o combobox de Roteamento ─────────────
ROUTE_FILTER_LABELS: dict[str, str] = {
    "routing":            "Tabela de Rotas do Roteador",
    "interfaces":         "Status de Todas as Interfaces de Rede",
    "interfaces_counters":"Contadores de Tráfego das Interfaces",
    "bgp":                "Vizinhos BGP (Roteamento entre Sistemas)",
    "vrfs":               "Redes Virtuais (VRF)",
    "ospf":               "Vizinhos OSPF (Roteamento Interno)",
    "lldp":               "Dispositivos Vizinhos Conectados (LLDP)",
    "qos":                "Qualidade de Serviço (QoS)",
    "huawei_mpls":        "Vizinhos MPLS (Rotas por Etiquetas)",
}

# ─── ROTULOS DESCRITIVOS para o combobox de Categoria (Serviços) ──
SERVICE_CAT_LABELS: dict[str, str] = {
    "todas":           "Todas as Categorias",
    "config-nat":      "NAT",
    "config-interface": "Interfaces",
    "config-acl":      "ACL",
    "config-bgp":      "BGP",
    "config-ospf":     "OSPF",
    "config-vlan":     "VLAN",
}


# Comandos gerenciados por abas dedicadas — não duplicar no editor de templates
BUILTIN_CMDS: frozenset[str] = frozenset({
    "display current-configuration",
    "display version", "display device", "display license",
    "display cpu-usage", "display memory-usage",
    "display interface brief", "display lldp neighbor brief",
    "display arp",
    "display interface", "display counters interface",
    "display ip routing-table", "display bgp peer",
    "display ip vpn-instance", "display ospf peer",
    "display qos policy", "display mpls ldp peer",
})

CMD_TEMPLATES: dict[str, str] = {
    "(vazio — digite um comando)": "",
    "display device": "display device",
    "display license": "display license",
    "display logbuffer": "display logbuffer",
    "display diagnostic-information": "display diagnostic-information",
    "display this": "display this",
    "display ip interface brief": "display ip interface brief",
    "display elabel": "display elabel",
    "display alarm active": "display alarm active",
    "display environment": "display environment",
    "display temperature": "display temperature",
    "display fan": "display fan",
    "display power": "display power",
    "ping": "ping 10.0.0.1",
    "tracert": "tracert 10.0.0.1",
    "sysname": "sysname ROTEADOR-MEU",
    "commit": "commit",
    "interface GigabitEthernet": "interface GigabitEthernet0/0/0",
    "interface NULL 0": "interface NULL 0",
    "reset counters interface": "reset counters interface GigabitEthernet0/0/0",
    "display current-configuration": "display current-configuration",
}

LINT_SUGGESTIONS: dict[str, str] = {
    "F401": "Módulo importado mas não utilizado. Remova o import ou use `# noqa: F401`.",
    "E501": "Linha muito longa (>120 chars). Quebre em múltiplas linhas ou use parênteses.",
    "F821": "Variável não definida. Verifique spelling, imports ou escopo.",
    "F841": "Variável local atribuída mas não usada. Remova ou prefixe com `_`.",
    "UP007": "Use sintaxe `X | Y` em vez de `Union[X, Y]` (Python 3.10+).",
    "I001": "Imports fora de ordem. Organize: stdlib → third-party → local.",
    "E302": "Esperadas 2 linhas em branco antes da definição.",
    "E402": "Import no meio do módulo. Mova para o topo.",
    "W291": "Espaço em branco no final da linha. Remova.",
    "E701": "Múltiplos comandos numa linha. Quebre em linhas separadas.",
    "reportGeneralTypeIssues": "Erro de tipo: verifique a assinatura da função.",
    "reportOptionalMemberAccess": "Acesso a membro em tipo opcional: adicione `if x is not None`.",
    "reportArgumentType": "Tipo de argumento incorreto na chamada.",
    "reportAttributeAccessIssue": "Atributo não existe no tipo. Verifique a definição.",
    "reportOptionalSubscript": "Subscrito em tipo opcional: verifique se não é None.",
    "reportUnusedVariable": "Variável declarada mas não usada. Remova.",
    "reportMissingTypeArgument": "Tipo genérico sem argumento de tipo. Adicione `[...]`.",
}

# ─── POLLING ADAPTATIVO ───────────────────────────────────────────────
# Dispositivos estáveis são pollados com menos frequência, instáveis com
# mais (15s → 300s). Feature flag HW_ADAPTIVE_POLLING default OFF.
POLL_MIN_INTERVAL = 15          # segundos — instável/novo device
POLL_MAX_INTERVAL = 300         # 5 min máximo — estável
POLL_STABLE_MULTIPLIER = 2.0    # dobra a cada ciclo estável
POLL_HISTORY_SIZE = 5           # amostras p/ estabilidade
POLL_DEFAULT_INTERVAL = 60      # fallback em erro (backoff D20)
POLL_ENABLED_ENV = "HW_ADAPTIVE_POLLING"
POLL_MAX_DEVICES = 10           # bound por tick (enforcement no loop)
POLL_MAX_WORKERS = 4            # paralelismo máximo do sub-pool
POLL_ORIGIN = "auto-poll"       # origin no audit (via wrapper)
POLL_TICK_FLOOR_MS = 5000       # piso do re-arm (evita busy loop)

# Serviços estruturalmente estáveis — EXCLUÍDOS os voláteis:
# sys-cpu, sys-mem, fw-session-table, ap-client (nunca estabilizam).
POLL_SERVICES: list[str] = [
    "router-routing-table", "router-bgp-summary", "router-ospf-peer",
    "router-interface-brief",
    "switch-arp", "switch-mac", "switch-vlan", "switch-stp",
    "fw-security-policy", "fw-zone", "fw-cpu", "fw-mem",
    "slb-service-group", "slb-virtual-server",
    "ap-radio",
]
