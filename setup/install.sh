#!/usr/bin/env bash
# setup/install.sh — instalador canônico do Huawei Manager 2.0.
#
# Uso:
#   setup/install.sh install [--dev|--prod] [--no-fonts] [--bootstrap-python]
#   setup/install.sh fonts
#   setup/install.sh reset  [--dev|--prod] [--no-fonts] [--bootstrap-python]
#   setup/install.sh check
#   setup/install.sh --help
#
# `install` é o modo padrão; `--dev` é o modo padrão de dependências.
# Sem Python >= 3.12 no sistema? Rode com --bootstrap-python (provisiona um
# CPython 3.12 gerenciado pelo uv em ~/.local, sem root). Ou exporte HM_PYTHON.

set -euo pipefail

SETUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_DIR="$(cd "$SETUP_DIR/.." && pwd)"
# shellcheck source=lib/common.sh
source "$SETUP_DIR/lib/common.sh"
# shellcheck source=lib/python.sh
source "$SETUP_DIR/lib/python.sh"

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
  --dev               Com ferramentas de desenvolvimento (padrão)
  --prod              Apenas dependências de produção
  --no-fonts          Pula o download das fontes
  --bootstrap-python  Provisiona CPython 3.12 gerenciado pelo uv (sem sudo,
                      instala em ~/.local) se nenhum Python >= 3.12 existir

Variável de ambiente:
  HM_PYTHON=/caminho/python3.x   Usa esse interpretador explicitamente (>= 3.12)

Exemplos:
  $0                       # Instalação completa (dev + fontes)
  $0 install --prod        # Produção + fontes
  $0 install --prod --no-fonts
  $0 install --bootstrap-python  # Máquina sem Python 3.12+
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
    local bootstrap_python=false

    while [ $# -gt 0 ]; do
        case "$1" in
            --dev)      dep_mode="dev"; shift ;;
            --prod)     dep_mode="prod"; shift ;;
            --no-fonts) do_fonts=false; shift ;;
            --bootstrap-python) bootstrap_python=true; shift ;;
            --help|-h)  usage; exit 0 ;;
            *)          err "Opção desconhecida: $1"; echo; usage; exit 1 ;;
        esac
    done

    header "Pré-requisitos"
    resolve_python "$bootstrap_python"
    timeout 10 "$PY_BIN" -m venv -h >/dev/null 2>&1 \
        || die "Módulo venv não disponível no interpretador resolvido ($PY_BIN)"

    header "Virtual environment"
    if [ -f "$VENV/bin/python3" ]; then
        ok ".venv já existe — reutilizando"
    else
        "$PY_BIN" -m venv "$VENV"
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

    header "Setup banco de dados de usuários"
    "$PY" -c "from huawei_manager.db import ensure_default_admin; ensure_default_admin()" \
        || warn "Setup de admin padrão falhou (não crítico)"

    echo ""
    ok "${BOLD}Instalação completa${NC}"
    echo "  Modo:      $dep_mode"
    echo "  Execute:   $VENV/bin/huawei-manager"
    echo "  Ou digite: huawei manager"
}

reset_mode() {
    local dep_mode="dev"
    local bootstrap_python=false
    while [ $# -gt 0 ]; do
        case "$1" in
            --dev)      dep_mode="dev"; shift ;;
            --prod)     dep_mode="prod"; shift ;;
            --no-fonts) shift ;;
            --bootstrap-python) bootstrap_python=true; shift ;;
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
    if [ "$bootstrap_python" = true ]; then
        install_mode "--$dep_mode" --bootstrap-python
    else
        install_mode "--$dep_mode"
    fi
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

    # Resolução de interpretador (informativa — nunca altera contagens):
    # mostra exatamente o que o instalador usaria agora.
    _PY_QUIET=1
    resolve_python false || true
    unset _PY_QUIET
    if [ -n "${PY_BIN:-}" ]; then
        note "Resolveria com: $PY_BIN (${PY_SOURCE})"
    else
        note "Nenhum Python >= 3.12 resolvível — rode '$0 install --bootstrap-python' ou defina HM_PYTHON"
    fi

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
        --dev|--prod|--no-fonts|--bootstrap-python) install_mode "$@" ;;
        *)
            err "Modo desconhecido: $1"
            echo
            usage
            exit 1
            ;;
    esac
}

main "$@"
