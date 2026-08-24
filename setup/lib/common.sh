#!/usr/bin/env bash
# setup/lib/common.sh — funções compartilhadas do instalador Huawei Manager.
#
# Fonte ÚNICA de verdade para: cores/logging, URLs das fontes Google Fonts,
# substituição de placeholders dos templates em share/ e sonda de sysdeps.
# Consumido por setup/install.sh.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

info()  { echo -e "${CYAN}INFO${NC}  $1"; }
ok()    { echo -e "${GREEN}OK${NC}    $1"; }
warn()  { echo -e "${YELLOW}WARN${NC}  $1"; }
err()   { echo -e "${RED}ERRO${NC}  $1"; }
# Linha informativa usada pelo `check`: NUNCA conta como erro nem aviso.
note()  { echo -e "       ·  $1"; }
header() { echo -e "\n${BOLD}$1${NC}"; echo "────────────────────────────────────────"; }

die() { err "$1"; exit 1; }

# ── Fontes canônicas (mesmas famílias usadas por constants.py) ──────────
IBM_PLEX_SANS_URL="https://github.com/google/fonts/raw/main/ofl/ibmplexsans/IBMPlexSans%5Bwght%5D.ttf"
SPACE_GROTESK_URL="https://github.com/google/fonts/raw/main/ofl/spacegrotesk/SpaceGrotesk%5Bwght%5D.ttf"
JETBRAINS_MONO_URL="https://github.com/google/fonts/raw/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf"

# render_template ORIGEM DESTINO EXEC_PATH VENV_DIR
# Função ÚNICA de substituição de placeholders dos templates em share/.
# Placeholders suportados: __EXEC_PATH__ e __VENV_DIR__.
render_template() {
    local src="$1" dst="$2" exec_path="$3" venv_dir="$4"
    sed -e "s|__EXEC_PATH__|${exec_path}|g" -e "s|__VENV_DIR__|${venv_dir}|g" \
        "$src" > "$dst"
}

# install_fonts — baixa e instala IBM Plex Sans / Space Grotesk / JetBrains Mono
# em ~/.local/share/fonts. Falhas individuais são warnings (nunca abortam).
install_fonts() {
    local FONTS_DIR="$HOME/.local/share/fonts"
    if ! command -v wget >/dev/null 2>&1; then
        warn "wget não encontrado; pulando fontes"
        return 0
    fi
    mkdir -p "$FONTS_DIR"

    wget -q -O /tmp/IBMPlexSans.ttf "$IBM_PLEX_SANS_URL" 2>/dev/null &&
        cp /tmp/IBMPlexSans.ttf "$FONTS_DIR/IBMPlexSans.ttf" &&
        ok "IBM Plex Sans" || warn "IBM Plex Sans — download falhou (ignorado)"
    wget -q -O /tmp/SpaceGrotesk.ttf "$SPACE_GROTESK_URL" 2>/dev/null &&
        cp /tmp/SpaceGrotesk.ttf "$FONTS_DIR/SpaceGrotesk.ttf" &&
        ok "Space Grotesk" || warn "Space Grotesk — download falhou (ignorado)"
    wget -q -O /tmp/JetBrainsMono.ttf "$JETBRAINS_MONO_URL" 2>/dev/null &&
        cp /tmp/JetBrainsMono.ttf "$FONTS_DIR/JetBrainsMono.ttf" &&
        ok "JetBrains Mono" || warn "JetBrains Mono — download falhou (ignorado)"

    fc-cache -f "$FONTS_DIR" >/dev/null 2>&1 || true
}

# check_sysdeps — sonda dependências de sistema do PySide6 (dpkg).
# Apenas AVISO: nunca aborta a instalação (distros sem dpkg pulam a sonda).
check_sysdeps() {
    header "Dependências de sistema (PySide6)"
    if ! command -v dpkg >/dev/null 2>&1; then
        warn "dpkg não disponível — verificação de pacotes de sistema pulada"
        return 0
    fi
    local MISSING_SYSDEPS=()
    local pkg
    for pkg in libxcb-cursor-dev libxkbcommon-x11-dev; do
        if dpkg -s "$pkg" >/dev/null 2>&1; then
            ok "$pkg"
        else
            MISSING_SYSDEPS+=("$pkg")
            warn "$pkg — não encontrado"
        fi
    done
    if [ ${#MISSING_SYSDEPS[@]} -gt 0 ]; then
        warn "Instale com: sudo apt install ${MISSING_SYSDEPS[*]}"
        warn "PySide6 pode falhar sem esses pacotes."
    fi
}
