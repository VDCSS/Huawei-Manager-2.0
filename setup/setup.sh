#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$SCRIPT_DIR/.venv"
PY="$VENV/bin/python3"
PIP="$VENV/bin/pip"
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
header(){ echo -e "\n${BOLD}$1${NC}"; echo "────────────────────────────────────────"; }

install_mode() {
    header "Pré-requisitos"
    command -v python3 >/dev/null || { err "python3 não encontrado"; exit 1; }
    python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" \
        || { err "Python 3.12+ necessário"; exit 1; }
    python3 -m venv -h >/dev/null 2>&1 \
        || { err "Módulo venv não disponível"; exit 1; }
    ok "python3 $(python3 --version | cut -d' ' -f2)"

    header "Virtual environment"
    python3 -m venv "$VENV"
    ok ".venv criado"

    header "Dependências"
    $PIP install --upgrade pip -q
    $PIP install -e ".[dev]" -q
    ok "pip install concluído"

    header "Ícone"
    ICONS_DIR="$HOME/.local/share/icons/hicolor"
    for size in 48x48 256x256; do
        install -Dm 644 "$SCRIPT_DIR/share/icons/huawei-manager.png" \
            "$ICONS_DIR/$size/apps/huawei-manager.png" 2>/dev/null || true
    done
    ok "Ícone instalado"

    header "Desktop entry"
    APPS_DIR="$HOME/.local/share/applications"
    sed "s|__EXEC_PATH__|$VENV/bin/huawei-manager|g" \
        "$SCRIPT_DIR/share/huawei-manager.desktop" > "$APPS_DIR/huawei-manager.desktop"
    chmod 644 "$APPS_DIR/huawei-manager.desktop"
    update-desktop-database "$APPS_DIR" 2>/dev/null || true
    ok "Desktop entry instalado"

    header "Shell dispatcher"
    BIN_DIR="$HOME/.local/bin"
    COMP_DIR="$HOME/.local/share/bash-completion/completions"
    mkdir -p "$BIN_DIR" "$COMP_DIR"

    sed "s|__VENV_DIR__|$VENV|g" "$SCRIPT_DIR/share/shell/huawei" > "$BIN_DIR/huawei"
    chmod 755 "$BIN_DIR/huawei"

    { echo '#!/usr/bin/env bash'; echo "exec $VENV/bin/huawei-manager \"\$@\""; } \
        > "$BIN_DIR/huawei-manager"
    chmod 755 "$BIN_DIR/huawei-manager"

    install -Dm 644 "$SCRIPT_DIR/share/shell/completion/huawei" "$COMP_DIR/huawei" 2>/dev/null || true
    ok "Shell: huawei / huawei-manager"

    echo ""
    ok "${BOLD}Setup completo${NC}"
    echo "  Execute:  $VENV/bin/huawei-manager"
    echo "  Ou digite: huawei manager"
}

reset_mode() {
    header "Limpando"
    rm -rf "$VENV"
    rm -rf "$SCRIPT_DIR/logs"
    rm -rf "$SCRIPT_DIR/.pytest_cache" "$SCRIPT_DIR/.ruff_cache" "$SCRIPT_DIR/__pycache__"
    find "$SCRIPT_DIR" -name '*.pyc' -delete
    ok "Cache e .venv removidos"

    header "Reinstalando"
    exec "$0" install
}

check_mode() {
    header "Diagnóstico"
    errors=0
    warnings=0

    check() {
        local desc="$1" cmd="$2" sev="${3:-error}"
        if eval "$cmd" >/dev/null 2>&1; then
            ok "$desc"
        elif [ "$sev" = "warning" ]; then
            warn "$desc"
            warnings=$((warnings + 1))
        else
            err "$desc"
            errors=$((errors + 1))
        fi
    }

    check "python3" "command -v python3"
    check "python3 >= 3.12" 'python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)"'
    check ".venv existe" "test -f $VENV/bin/python3"
    check "entry point huawei-manager" "test -f $VENV/bin/huawei-manager"
    check "import huawei_manager" "$PY -c \"from huawei_manager import main\""
    check "pytest instalado" "$PY -c \"import pytest\"" "warning"
    check "ruff instalado" "$PY -c \"import ruff\"" "warning"
    check "pyright instalado" "command -v $VENV/bin/pyright" "warning"
    check "desktop entry" "test -f $HOME/.local/share/applications/huawei-manager.desktop" "warning"
    check "shell dispatcher" "test -x $HOME/.local/bin/huawei" "warning"
    check "entry point direct" "test -x $HOME/.local/bin/huawei-manager" "warning"
    check "tab complete" "test -f $HOME/.local/share/bash-completion/completions/huawei" "warning"
    check "logs directory" "test -d $SCRIPT_DIR/logs" "info"

    echo ""
    if [ $errors -gt 0 ] || [ $warnings -gt 0 ]; then
        echo -e "${RED}${errors} erro(s)${NC} · ${YELLOW}${warnings} warning(s)${NC}"
        [ $errors -gt 0 ] && echo -e "  ${BOLD}Dica:${NC} Rode ${CYAN}$0 reset${NC}"
        [ $warnings -gt 0 ] && echo -e "  ${BOLD}Dica:${NC} Rode ${CYAN}$0 install${NC}"
    else
        echo -e "${GREEN}Tudo OK${NC}"
    fi
}

case "${1:-install}" in
    install) install_mode ;;
    reset)   reset_mode ;;
    check)   check_mode ;;
    *)
        echo "Uso: $0 {install|reset|check}"
        exit 1
        ;;
esac
