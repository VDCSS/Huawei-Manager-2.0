from __future__ import annotations

# ─── DESIGN TOKENS — espelho do MVP HTML/CSS (Black Theme) ──────────
# Os nomes históricos (BG_BASE/BG_CARD/BG_SIDEBAR/BG_INPUT) são mantidos
# para não tocar na mecânica das abas; os nomes novos completam a paleta
# do MVP (superfícies, bordas suaves, verde e estado).
BG_BASE        = "#0d0d1a"   # fundo da janela / workspace
BG_DEEP        = "#080812"   # fundo profundo
BG_SOFT        = "#101021"   # fundo suave
BG_CARD        = "#13132b"   # cartões e painéis (surface)
BG_SURFACE_2   = "#171733"   # superfície elevada
BG_SURFACE_3   = "#1a1a30"   # chips / ícones / trilha
BG_HOVER       = "#1e1e3b"   # hover de superfícies
BG_SIDEBAR     = "#0a0a18"
BG_TITLEBAR    = "#070711"
BG_STATUS      = "#090914"
BG_INPUT       = "#14142a"   # inputs (o cartão usa BG_CARD)
BG_CODE        = "#080812"   # painéis de código / saída

BORDER_NRM     = "#2a2a4a"
BORDER_SOFT    = "#23233d"   # ≈ rgba(138,138,190,0.16) sobre superfície
BORDER_STRONG  = "#3b3b63"

FG_MAIN        = "#e0e0ff"
FG_DIM         = "#8a8abe"
FG_FAINT       = "#62628c"
FG_CODE        = "#c8c8ff"

NEON_CYAN        = "#00e5ff"
NEON_CYAN_STRONG = "#63edff"
NEON_MAG         = "#e040fb"
NEON_PURP        = "#8f6bff"
NEON_AMBER       = "#ffab00"
NEON_RED         = "#ff4d4d"
NEON_GREEN       = "#3ddc97"

# ─── FONTES — UI (Proporcional) ──────────────────────────────────────
# Stacks idênticas ao MVP: ``--font-ui``, ``--font-display`` e ``--font-mono``
# de style.css (IBM Plex Sans/Space Grotesk/JetBrains Mono com os mesmos
# fallbacks encadeados).
_FONT_UI_FAMILY       = "IBM Plex Sans"
_FONT_UI_TITLE_FAMILY = "Space Grotesk"
_FONT_MONO_FAMILY     = "JetBrains Mono"
_FALLBACK_UI          = "Segoe UI"
_FALLBACK_MONO        = "Consolas"

# Família da UI exposta para stylesheets QSS montados em f-strings
FONT_UI_FAMILY         = _FONT_UI_FAMILY
FONT_UI_TITLE_FAMILY   = _FONT_UI_TITLE_FAMILY
FONT_MONO_FAMILY       = _FONT_MONO_FAMILY

# Escala efetiva do MVP (bloco “Proporções gerais” do style.css):
# .btn/.nav__item/.field 13.5 px, h1 34 px, eyebrow 11, subtítulo 14.
FONT_UI_MEDIUM        = (_FONT_UI_FAMILY, 13.5, _FALLBACK_UI)         # sidebar, botões, inputs
FONT_UI_MEDIUM_B      = (_FONT_UI_FAMILY, 13.5, "bold", _FALLBACK_UI)
FONT_UI_TITLE         = (_FONT_UI_TITLE_FAMILY, 34, _FALLBACK_UI)     # títulos de página/seção

# Escala de fontes da UI (px) — espelha o MVP final
# (badge 10 · body/inputs 13 · subtítulo 14 · h1 34).
FONT_CAPTION = 11
FONT_BODY    = 13
FONT_SUBHEAD = 14
FONT_TITLE   = 34

# ─── GEOMETRIA — espelho do style.css (Proporções gerais) ───────────
SIDEBAR_WIDTH       = 268   # --sidebar-width
TOPBAR_HEIGHT       = 68    # --topbar-height
STATUSBAR_HEIGHT    = 30    # --statusbar-height
NAV_ITEM_HEIGHT     = 40    # .nav__item min-height
NAV_ICON_SIZE       = 19    # .nav__icon
NAV_ITEM_RADIUS     = 6     # .nav__item border-radius (radius-sm)
NAV_ACCENT_BAR_W    = 3     # .nav__item::before width
NAV_BADGE_FONT_SIZE = 9.5   # .nav__badge
BTN_MIN_HEIGHT      = 38    # .btn min-height
BTN_FONT_SIZE       = 13.5  # .btn font-size
FIELD_MIN_HEIGHT    = 42    # .field input min-height

# Único formato de backup suportado (running-config → .txt)
BACKUP_FMT_TEXT = "Texto (.txt)"

# ─── FONTES — Código (Monospace) ───────────────────────────────────
FONT_XSMALL      = (_FONT_MONO_FAMILY, 9, _FALLBACK_MONO)      # type_item no canvas
FONT_CANVAS_BODY = (_FONT_MONO_FAMILY, 11, _FALLBACK_MONO)     # SDN bar count, address items
FONT_LARGE       = (_FONT_MONO_FAMILY, 13, _FALLBACK_MONO)     # código / output principal
FONT_H1          = (_FONT_MONO_FAMILY, 16, _FALLBACK_MONO)     # SDN bar symbol

FONT_MEDIUM_B    = (_FONT_MONO_FAMILY, 12, "bold", _FALLBACK_MONO)  # name_item no canvas
FONT_LARGE_B     = (_FONT_MONO_FAMILY, 13, "bold", _FALLBACK_MONO)  # SDN bar label


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Converte ``#rrggbb`` em uma tupla RGB (usado por ``rgba``)."""
    value = hex_color.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def rgba(hex_color: str, alpha: float) -> str:
    """CSS/Qt ``rgba(...)`` a partir de um hex e opacidade 0–1.

    O Qt Style Sheets aceita percentual no canal alfa; usamos percentual
    para manter a mesma leitura dos tokens do CSS do MVP.
    """
    r, g, b = hex_to_rgb(hex_color)
    return f"rgba({r}, {g}, {b}, {max(0.0, min(1.0, alpha)) * 100:.0f}%)"


THEME = {
    "BG_BASE":        BG_BASE,        "BG_DEEP":        BG_DEEP,
    "BG_SOFT":        BG_SOFT,        "BG_CARD":        BG_CARD,
    "BG_SURFACE_2":   BG_SURFACE_2,   "BG_SURFACE_3":   BG_SURFACE_3,
    "BG_HOVER":       BG_HOVER,       "BG_SIDEBAR":     BG_SIDEBAR,
    "BG_TITLEBAR":    BG_TITLEBAR,    "BG_STATUS":      BG_STATUS,
    "BG_INPUT":       BG_INPUT,       "BG_CODE":        BG_CODE,
    "BORDER_NRM":     BORDER_NRM,     "BORDER_SOFT":    BORDER_SOFT,
    "BORDER_STRONG":  BORDER_STRONG,
    "FG_MAIN":        FG_MAIN,        "FG_DIM":         FG_DIM,
    "FG_FAINT":       FG_FAINT,       "FG_CODE":        FG_CODE,
    "NEON_CYAN":      NEON_CYAN,      "NEON_CYAN_STRONG": NEON_CYAN_STRONG,
    "NEON_MAG":       NEON_MAG,       "NEON_PURP":      NEON_PURP,
    "NEON_AMBER":     NEON_AMBER,     "NEON_RED":       NEON_RED,
    "NEON_GREEN":     NEON_GREEN,
}

# ─── PALETA CLARA (White/slate — espelho do MVP) ────────────────────
BG_BASE_L        = "#ffffff"
BG_DEEP_L        = "#f2f2f2"
BG_SOFT_L        = "#f7f7f7"
BG_CARD_L        = "#f2f2f2"
BG_SURFACE_2_L   = "#f7f7f7"
BG_SURFACE_3_L   = "#ececec"
BG_HOVER_L       = "#e4e4e4"
BG_SIDEBAR_L     = "#f2f2f2"
BG_TITLEBAR_L    = "#f2f2f2"
BG_STATUS_L      = "#f2f2f2"
BG_INPUT_L       = "#ffffff"   # --input (White Theme) — inputs claros
BG_CODE_L        = "#14161c"

BORDER_NRM_L     = "#d0d0d0"
BORDER_SOFT_L    = "#e2e2e2"
BORDER_STRONG_L  = "#b4b4b4"

FG_MAIN_L        = "#1a1a1a"
FG_DIM_L         = "#5a5a5a"
FG_FAINT_L       = "#7c7c7c"
FG_CODE_L        = "#e6e8ee"

NEON_CYAN_L        = "#0e7490"
NEON_CYAN_STRONG_L = "#155e75"
NEON_MAG_L         = "#a21caf"
NEON_PURP_L        = "#5b21b6"
NEON_AMBER_L       = "#92400e"
NEON_RED_L         = "#b91c1c"
NEON_GREEN_L       = "#15803d"

LIGHT_THEME = {
    "BG_BASE":        BG_BASE_L,        "BG_DEEP":        BG_DEEP_L,
    "BG_SOFT":        BG_SOFT_L,        "BG_CARD":        BG_CARD_L,
    "BG_SURFACE_2":   BG_SURFACE_2_L,   "BG_SURFACE_3":   BG_SURFACE_3_L,
    "BG_HOVER":       BG_HOVER_L,       "BG_SIDEBAR":     BG_SIDEBAR_L,
    "BG_TITLEBAR":    BG_TITLEBAR_L,    "BG_STATUS":      BG_STATUS_L,
    "BG_INPUT":       BG_INPUT_L,       "BG_CODE":        BG_CODE_L,
    "BORDER_NRM":     BORDER_NRM_L,     "BORDER_SOFT":    BORDER_SOFT_L,
    "BORDER_STRONG":  BORDER_STRONG_L,
    "FG_MAIN":        FG_MAIN_L,        "FG_DIM":         FG_DIM_L,
    "FG_FAINT":       FG_FAINT_L,       "FG_CODE":        FG_CODE_L,
    "NEON_CYAN":      NEON_CYAN_L,      "NEON_CYAN_STRONG": NEON_CYAN_STRONG_L,
    "NEON_MAG":       NEON_MAG_L,       "NEON_PURP":      NEON_PURP_L,
    "NEON_AMBER":     NEON_AMBER_L,     "NEON_RED":       NEON_RED_L,
    "NEON_GREEN":     NEON_GREEN_L,
}

# ─── PALETA HUAWEI (Huawei Theme — foco no vermelho #C8102E) ─────────
BG_BASE_H        = "#ffffff"
BG_DEEP_H        = "#f2f2f2"
BG_SOFT_H        = "#f7f7f7"
BG_CARD_H        = "#f2f2f2"
BG_SURFACE_2_H   = "#f7f7f7"
BG_SURFACE_3_H   = "#ececec"
BG_HOVER_H       = "#e4e4e4"
BG_SIDEBAR_H     = "#f2f2f2"
BG_TITLEBAR_H    = "#f2f2f2"
BG_STATUS_H      = "#f2f2f2"
BG_INPUT_H       = "#ffffff"
BG_CODE_H        = "#17181c"

BORDER_NRM_H     = "#d0d0d0"
BORDER_SOFT_H    = "#e2e2e2"
BORDER_STRONG_H  = "#b4b4b4"

FG_MAIN_H        = "#1a1a1a"
FG_DIM_H         = "#5a5a5a"
FG_FAINT_H       = "#7c7c7c"
FG_CODE_H        = "#ececec"

# O vermelho Huawei assume o papel de acento principal
HUAWEI_RED         = "#c8102e"
NEON_CYAN_H        = "#c8102e"
NEON_CYAN_STRONG_H = "#a50d25"
NEON_MAG_H         = "#be185d"
NEON_PURP_H        = "#6d28d9"
NEON_AMBER_H       = "#a16207"
NEON_RED_H         = "#c8102e"
NEON_GREEN_H       = "#15803d"

HUAWEI_THEME = {
    "BG_BASE":        BG_BASE_H,        "BG_DEEP":        BG_DEEP_H,
    "BG_SOFT":        BG_SOFT_H,        "BG_CARD":        BG_CARD_H,
    "BG_SURFACE_2":   BG_SURFACE_2_H,   "BG_SURFACE_3":   BG_SURFACE_3_H,
    "BG_HOVER":       BG_HOVER_H,       "BG_SIDEBAR":     BG_SIDEBAR_H,
    "BG_TITLEBAR":    BG_TITLEBAR_H,    "BG_STATUS":      BG_STATUS_H,
    "BG_INPUT":       BG_INPUT_H,       "BG_CODE":        BG_CODE_H,
    "BORDER_NRM":     BORDER_NRM_H,     "BORDER_SOFT":    BORDER_SOFT_H,
    "BORDER_STRONG":  BORDER_STRONG_H,
    "FG_MAIN":        FG_MAIN_H,        "FG_DIM":         FG_DIM_H,
    "FG_FAINT":       FG_FAINT_H,       "FG_CODE":        FG_CODE_H,
    "NEON_CYAN":      NEON_CYAN_H,      "NEON_CYAN_STRONG": NEON_CYAN_STRONG_H,
    "NEON_MAG":       NEON_MAG_H,       "NEON_PURP":      NEON_PURP_H,
    "NEON_AMBER":     NEON_AMBER_H,     "NEON_RED":       NEON_RED_H,
    "NEON_GREEN":     NEON_GREEN_H,
}

# Cópia congelada do tema escuro — NUNCA mutada, usada como fonte para re-aplicar dark
DARK_THEME = THEME.copy()


def set_theme(name: str) -> None:
    """Swap all module-level colour constants to the named palette."""
    if name == "light":
        pal = LIGHT_THEME
    elif name == "huawei":
        pal = HUAWEI_THEME
    else:
        pal = DARK_THEME

    # Atualiza todos os tokens de uma vez. ``globals()`` mantém a mesma
    # semântica anterior (``constants.NOME`` sempre enxerga o tema atual),
    # mas evita esquecer um token novo no ``global`` manual.
    for key, value in pal.items():
        globals()[key] = value

    THEME.clear()
    THEME.update(pal)

# ─── COMANDOS CLI — filtros da aba Roteamento ───────────────────────
CLI_FILTERS: dict[str, str] = {
    "interfaces":          "display interface",
    "interfaces_counters": "display counters interface",
    "routing":             "display ip routing-table",
    "bgp":                 "display bgp peer",
    "vrfs":                "display ip vpn-instance",
    "ospf":                "display ospf peer",
    "lldp":                "display lldp neighbor brief",
    "qos":                 "display traffic policy",
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
    "config-qos":      "QoS / Tráfego",
    "config-route":    "Rotas",
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
    "display traffic policy", "display mpls ldp peer",
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
