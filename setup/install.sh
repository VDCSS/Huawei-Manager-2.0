#!/usr/bin/env bash
# setup/install.sh — instalador canônico do Huawei Manager 2.0.
#
# Uso:
#   setup/install.sh install [--dev|--prod] [--no-fonts]
#   setup/install.sh fonts
#   setup/install.sh reset  [--dev|--prod]
#   setup/install.sh check
#   setup/install.sh --help
#
# `install` é o modo padrão; `--dev` é o modo padrão de dependências.

set -euo pipefail

SETUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_DIR="$(cd "$SETUP_DIR/.." && pwd)"
# shellcheck source=lib/common.sh
source "$SETUP_DIR/lib/common.sh"

VENV="$SCRIPT_DIR/.venv"
PY="$VENV/bin/python3"
PIP="$VENV/bin/pip"

usage() {
    cat <<EOF
Huawei Manager 2.0 — Instalador

Uso: $0 <modo> [opções]

Modos:
  install      Instalação completa (padrão)
  fonts        Instala apenas as fontes Google Fonts
  reset        Limpa .venv/caches/logs e reinstala
  check        Diagnóstico do ambiente
  --help       Mostra esta mensagem

Opções (install / reset):
  --dev        Com ferramentas de desenvolvimento (padrão)
  --prod       Apenas dependências de produção
  --no-fonts   Pula o download das fontes

Exemplos:
  $0                       # Instalação completa (dev + fontes)
  $0 install --prod        # Produção + fontes
  $0 install --prod --no-fonts
  $0 fonts                 # Apenas fontes
  $0 reset --prod          # Limpa e reinstala em produção
  $0 check                 # Diagnóstico do ambiente
EOF
}

install_deps() {
    local mode="$1"
    header "Dependências"
    "$PIP" install --upgrade pip -q
    if [ "$mode" = "prod" ]; then
        "$PIP" install -e ".[vault,aws]" -q
        ok "Dependências de produção instaladas (core + vault + aws extras)"
    else
        "$PIP" install -e ".[dev,vault,aws]" -q
        ok "Dependências de desenvolvimento instaladas (core + vault + aws + dev extras)"
    fi
}

install_assets() {
    header "Ícone"
    local ICONS_DIR="$HOME/.local/share/icons/hicolor"
    local size
    for size in 48x48 256x256; do
        install -Dm 644 "$SCRIPT_DIR/share/icons/huawei-manager.png" \
            "$ICONS_DIR/$size/apps/huawei-manager.png" >/dev/null 2>&1 || true
    done
    ok "Ícone instalado"

    header "Desktop entry"
    local APPS_DIR="$HOME/.local/share/applications"
    mkdir -p "$APPS_DIR"
    render_template "$SCRIPT_DIR/share/huawei-manager.desktop" \
        "$APPS_DIR/huawei-manager.desktop" "$VENV/bin/huawei-manager" "$VENV"
    chmod 644 "$APPS_DIR/huawei-manager.desktop"
    update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
    ok "Desktop entry instalado"

    header "Shell dispatcher"
    local BIN_DIR="$HOME/.local/bin"
    local COMP_DIR="$HOME/.local/share/bash-completion/completions"
    mkdir -p "$BIN_DIR" "$COMP_DIR"

    render_template "$SCRIPT_DIR/share/shell/huawei" "$BIN_DIR/huawei" \
        "$VENV/bin/huawei-manager" "$VENV"
    chmod 755 "$BIN_DIR/huawei"

    { echo '#!/usr/bin/env bash'; echo "exec $VENV/bin/huawei-manager \"\$@\""; } \
        > "$BIN_DIR/huawei-manager"
    chmod 755 "$BIN_DIR/huawei-manager"

    install -Dm 644 "$SCRIPT_DIR/share/shell/completion/huawei" \
        "$COMP_DIR/huawei" >/dev/null 2>&1 || true
    ok "Shell: huawei / huawei-manager"
}

fonts_mode() {
    header "Fontes Google Fonts"
    install_fonts
    ok "Fontes instaladas (falhas individuais foram ignoradas)."
}

install_mode() {
    local dep_mode="dev"
    local do_fonts=true

    while [ $# -gt 0 ]; do
        case "$1" in
            --dev)      dep_mode="dev"; shift ;;
            --prod)     dep_mode="prod"; shift ;;
            --no-fonts) do_fonts=false; shift ;;
            --help|-h)  usage; exit 0 ;;
            *)          err "Opção desconhecida: $1"; echo; usage; exit 1 ;;
        esac
    done

    header "Pré-requisitos"
    command -v python3 >/dev/null 2>&1 || die "python3 não encontrado"
    python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" \
        || die "Python 3.12+ necessário"
    python3 -m venv -h >/dev/null 2>&1 || die "Módulo venv não disponível"
    ok "python3 $(python3 --version | cut -d' ' -f2)"

    header "Virtual environment"
    if [ -f "$VENV/bin/python3" ]; then
        ok ".venv já existe — reutilizando"
    else
        python3 -m venv "$VENV"
        ok ".venv criado"
    fi

    check_sysdeps

    install_deps "$dep_mode"

    if [ "$do_fonts" = true ]; then
        fonts_mode
    else
        info "Download de fontes pulado (--no-fonts)"
    fi

    install_assets

    echo ""
    ok "${BOLD}Instalação completa${NC}"
    echo "  Modo:      $dep_mode"
    echo "  Execute:   $VENV/bin/huawei-manager"
    echo "  Ou digite: huawei manager"
}

reset_mode() {
    local dep_mode="dev"
    while [ $# -gt 0 ]; do
        case "$1" in
            --dev)      dep_mode="dev"; shift ;;
            --prod)     dep_mode="prod"; shift ;;
            --no-fonts) shift ;;
            --help|-h)  usage; exit 0 ;;
            *)          err "Opção desconhecida: $1"; echo; usage; exit 1 ;;
        esac
    done

    header "Limpando"
    rm -rf "$VENV"
    rm -rf "$SCRIPT_DIR/logs"
    rm -rf "$SCRIPT_DIR/.pytest_cache" "$SCRIPT_DIR/.ruff_cache"
    find "$SCRIPT_DIR/src" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
    find "$SCRIPT_DIR" -maxdepth 1 -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
    find "$SCRIPT_DIR/src" -name '*.pyc' -delete 2>/dev/null || true
    ok "Cache, logs e .venv removidos"

    header "Reinstalando"
    install_mode "--$dep_mode"
}

check_mode() {
    header "Diagnóstico"
    local errors=0 warnings=0

    # Severidades honestas: error conta como erro; warning conta como aviso;
    # info é apenas informativo e NUNCA entra nas contagens (nem sugere reset).
    check() {
        local desc="$1" cmd="$2" sev="${3:-error}"
        if eval "$cmd" >/dev/null 2>&1; then
            ok "$desc"
            return
        fi
        case "$sev" in
            error)   err "$desc"; errors=$((errors + 1)) ;;
            warning) warn "$desc"; warnings=$((warnings + 1)) ;;
            *)       note "$desc — ausente (informativo)" ;;
        esac
    }

    check "python3" "command -v python3"
    check "python3 >= 3.12" 'python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)"'
    check ".venv existe" "test -f $VENV/bin/python3"
    check "entry point huawei-manager" "test -x $VENV/bin/huawei-manager"
    check "import huawei_manager" "$PY -c \"from huawei_manager import main\""
    check "pytest instalado" "$PY -c \"import pytest\"" "warning"
    check "ruff instalado" "$PY -c \"import ruff\"" "warning"
    check "pyright instalado" "$PY -m pyright --version" "warning"
    check "desktop entry" "test -f $HOME/.local/share/applications/huawei-manager.desktop" "warning"
    check "shell dispatcher" "test -x $HOME/.local/bin/huawei" "warning"
    check "entry point direct" "test -x $HOME/.local/bin/huawei-manager" "warning"
    check "tab complete" "test -f $HOME/.local/share/bash-completion/completions/huawei" "warning"
    check "logs directory" "test -d $SCRIPT_DIR/logs" "info"

    echo ""
    if [ "$errors" -gt 0 ] && [ "$warnings" -gt 0 ]; then
        echo -e "${RED}${errors} erro(s)${NC} · ${YELLOW}${warnings} warning(s)${NC}"
        echo -e "  ${BOLD}Dica:${NC} Rode ${CYAN}$0 reset${NC}"
        return 1
    elif [ "$errors" -gt 0 ]; then
        echo -e "${RED}${errors} erro(s)${NC}"
        echo -e "  ${BOLD}Dica:${NC} Rode ${CYAN}$0 reset${NC}"
        return 1
    elif [ "$warnings" -gt 0 ]; then
        echo -e "${YELLOW}${warnings} warning(s)${NC}"
        echo -e "  ${BOLD}Dica:${NC} Rode ${CYAN}$0 install${NC}"
        return 0
    else
        echo -e "${GREEN}Tudo OK${NC}"
        return 0
    fi
}

main() {
    if [ $# -eq 0 ]; then
        install_mode
        return
    fi
    case "$1" in
        install) shift; install_mode "$@" ;;
        fonts)   fonts_mode ;;
        reset)   shift; reset_mode "$@" ;;
        check)   check_mode ;;
        --help|-h|help) usage; exit 0 ;;
        --dev|--prod|--no-fonts) install_mode "$@" ;;
        *)
            err "Modo desconhecido: $1"
            echo
            usage
            exit 1
            ;;
    esac
}

main "$@"
