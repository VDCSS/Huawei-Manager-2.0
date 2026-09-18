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

# check_sysdeps — sonda dependências de sistema do PySide6 (cross-distro).
# Suporta: apt (Debian/Ubuntu), dnf (Fedora/RHEL), pacman (Arch).
# Apenas AVISO: nunca aborta a instalação.
check_sysdeps() {
    header "Dependências de sistema (PySide6)"

    local PM="" PM_INSTALL=""
    local DEB_PKGS="libxcb-cursor-dev libxkbcommon-x11-dev"
    local RPM_PKGS="libxcb libxkbcommon-x11"

    if command -v dpkg >/dev/null 2>&1; then
        PM="dpkg"; PM_INSTALL="sudo apt install"
    elif command -v dnf >/dev/null 2>&1; then
        PM="dnf"; PM_INSTALL="sudo dnf install"
    elif command -v yum >/dev/null 2>&1; then
        PM="yum"; PM_INSTALL="sudo yum install"
    elif command -v pacman >/dev/null 2>&1; then
        PM="pacman"; PM_INSTALL="sudo pacman -S"
    else
        warn "Nenhum gerenciador de pacotes detectado — verificação pulada"
        return 0
    fi

    if "$PY_BIN" -c "import sqlite3" 2>/dev/null; then
        ok "sqlite3 (módulo padrão Python)"
    else
        warn "sqlite3 não disponível no Python — pode causar falhas"
    fi

    local MISSING=() PKGS
    case "$PM" in
        dpkg)    PKGS=$DEB_PKGS ;;
        dnf|yum) PKGS=$RPM_PKGS ;;
        pacman)  PKGS="libxcb libxkbcommon" ;;
    esac

    for pkg in $PKGS; do
        case "$PM" in
            dpkg)    dpkg -s "$pkg" >/dev/null 2>&1 && ok "$pkg" || { MISSING+=("$pkg"); warn "$pkg — não encontrado"; } ;;
            dnf|yum) $PM list installed "$pkg" >/dev/null 2>&1 && ok "$pkg" || { MISSING+=("$pkg"); warn "$pkg — não encontrado"; } ;;
            pacman)  pacman -Qi "$pkg" >/dev/null 2>&1 && ok "$pkg" || { MISSING+=("$pkg"); warn "$pkg — não encontrado"; } ;;
        esac
    done

    if [ ${#MISSING[@]} -gt 0 ]; then
        warn "Instale com: $PM_INSTALL ${MISSING[*]}"
        warn "PySide6 pode falhar sem esses pacotes."
    fi
}
