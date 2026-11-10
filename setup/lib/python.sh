#!/usr/bin/env bash
# setup/lib/python.sh — resolução de interpretador Python para o instalador.
#
# Fonte ÚNICA de verdade para localizar um Python >= 3.12 antes de criar a
# .venv. Cadeia determinística (primeiro vencedor vence):
#
#   1. $HM_PYTHON          — override manual (inválido = erro ALTO, sem fallback)
#   2. python3 do sistema  — caminho rápido, comportamento idêntico ao antigo
#   3. python3.13/3.12     — alternativas coexistentes no PATH (mais novo 1º)
#   4. uv já instalado     — CPython gerenciado >= 3.12 já presente (zero download)
#   5. --bootstrap-python  — OPT-IN: instala uv (~/.local/bin, sem root) + CPython 3.12
#   6. Falha rica          — mensagem com versão detectada + 3 remediações
#
# Princípios: fail-closed · NUNCA sudo · nada é baixado sem flag explícita ·
# nenhum fallback silencioso para Python velho.
#
# Globais produzidas por resolve_python / bootstrap_uv_python:
#   PY_BIN     — caminho absoluto do interpretador resolvido
#   PY_SOURCE  — override | system | alt | uv
#
# Consumido por setup/install.sh (após lib/common.sh).

set -euo pipefail

HM_MIN_MAJOR=3
HM_MIN_MINOR=12

# _pylog TIPO MSG — log condicional; _PY_QUIET=1 silencia (modo sonda do check).
_pylog() {
    if [ "${_PY_QUIET:-0}" = "1" ]; then
        return 0
    fi
    case "$1" in
        ok)   ok "$2" ;;
        info) info "$2" ;;
        note) note "$2" ;;
    esac
}

# python_version_ok BIN — 0 se BIN existe/executa e é Python >= 3.12.
# Executa checagem REAL (roda o binário); binários quebrados são descartados.
python_version_ok() {
    local bin="$1"
    [ -n "$bin" ] || return 1
    local resolved
    resolved="$(command -v "$bin" 2>/dev/null)" || return 1
    [ -n "$resolved" ] || return 1
    "$resolved" -c "import sys; sys.exit(0 if sys.version_info >= (${HM_MIN_MAJOR},${HM_MIN_MINOR}) else 1)" >/dev/null 2>&1
}

# python_describe BIN — imprime "X.Y.Z" (ou "desconhecida" se não responder).
python_describe() {
    local ver
    ver="$("$1" --version 2>/dev/null | awk '{print $2}')" || true
    printf '%s' "${ver:-desconhecida}"
}

# bootstrap_uv_python — garante uv em ~/.local/bin (sem root) e instala um
# CPython 3.12 gerenciado. Define PY_BIN/PY_SOURCE ou morre com `die`.
# Só deve ser chamado com consentimento explícito (--bootstrap-python).
bootstrap_uv_python() {
    local uv_bin="$HOME/.local/bin/uv"

    header "Provisionando Python 3.12 (via uv)"

    if [ ! -x "$uv_bin" ] && ! command -v uv >/dev/null 2>&1; then
        _pylog info "Instalando uv em ~/.local/bin (sem root)..."
        mkdir -p "$HOME/.local/bin" || die "Falha ao criar ~/.local/bin — verifique as permissões"
        local installer_url="https://astral.sh/uv/install.sh"
        # INSTALLER_NO_MODIFY_PATH=1: não tocar em .bashrc/.profile — este
        # instalador referencia o uv SEMPRE por caminho absoluto.
        if command -v wget >/dev/null 2>&1; then
            if ! wget -qO- "$installer_url" \
                    | env UV_INSTALL_DIR="$HOME/.local/bin" INSTALLER_NO_MODIFY_PATH=1 sh; then
                die "Download do uv falhou — verifique a conexão e tente novamente"
            fi
        elif command -v curl >/dev/null 2>&1; then
            if ! curl -LsSf "$installer_url" \
                    | env UV_INSTALL_DIR="$HOME/.local/bin" INSTALLER_NO_MODIFY_PATH=1 sh; then
                die "Download do uv falhou — verifique a conexão e tente novamente"
            fi
        else
            die "wget ou curl são necessários para provisionar o Python (--bootstrap-python)"
        fi
        [ -x "$uv_bin" ] || die "Instalador do uv não produziu $uv_bin"
        _pylog ok "uv instalado: $uv_bin"
    fi

    # Caminho ABSOLUTO sempre: o PATH da sessão atual pode estar desatualizado.
    local UV_ABS="$uv_bin"
    if [ ! -x "$UV_ABS" ]; then
        UV_ABS="$(command -v uv)"
    fi

    _pylog info "Baixando CPython 3.12 gerenciado pelo uv (pode levar alguns minutos)..."
    if ! timeout 300 "$UV_ABS" python install 3.12; then
        die "Instalação do CPython 3.12 via uv falhou (rede/disco?)"
    fi
    _pylog ok "CPython 3.12 disponível"

    local py_path
    if ! py_path="$("$UV_ABS" python find 3.12 2>/dev/null)"; then
        die "uv não conseguiu resolver o caminho do CPython 3.12 instalado"
    fi
    if ! python_version_ok "$py_path"; then
        die "CPython do uv ($py_path) não passou na checagem de versão"
    fi

    PY_BIN="$py_path"
    PY_SOURCE="uv"
    _pylog ok "python $(python_describe "$PY_BIN") (${PY_SOURCE}: $PY_BIN)"
}

# resolve_python [bootstrap_requested] — implementa a cadeia de resolução.
#   bootstrap_requested: "true"/"false" (default false). NUNCA inferir de env.
# Em falha total: imprime mensagem rica e EXITA (comportamento padrão), OU
# apenas retorna 1 quando chamado em modo sonda (_PY_QUIET=1, usado pelo check).
resolve_python() {
    local bootstrap="${1:-false}"
    PY_BIN=""
    PY_SOURCE=""

    # 1) Override manual — pedido explícito do usuário; inválido = falha alta.
    if [ -n "${HM_PYTHON:-}" ]; then
        if python_version_ok "$HM_PYTHON"; then
            PY_BIN="$(command -v "$HM_PYTHON")"
            PY_SOURCE="override"
            _pylog ok "python $(python_describe "$PY_BIN") (${PY_SOURCE}: $PY_BIN)"
            return 0
        fi
        err "HM_PYTHON='${HM_PYTHON}' não é um Python >= ${HM_MIN_MAJOR}.${HM_MIN_MINOR} utilizável"
        # NOTA: não usar die() aqui porque err() + return 1 é necessário
        # para _PY_QUIET=1 (check_mode sonda). die() bypassaria o check silencioso.
        [ "${_PY_QUIET:-0}" = "1" ] && return 1
        exit 1
    fi

    # 2) Sistema — caminho rápido (comportamento idêntico às versões antigas).
    if python_version_ok python3; then
        PY_BIN="$(command -v python3)"
        PY_SOURCE="system"
        _pylog ok "python3 $(python_describe "$PY_BIN") (${PY_SOURCE})"
        return 0
    fi

    if command -v python3 >/dev/null 2>&1; then
        _pylog note "python3 do sistema é $(python_describe python3) (< ${HM_MIN_MAJOR}.${HM_MIN_MINOR}) — procurando alternativas"
    else
        _pylog note "python3 não encontrado no PATH — procurando alternativas"
    fi

    # 3) Alternativas coexistentes (mais novo primeiro). Binários quebrados
    #    são descartados pela checagem real, com UMA linha informativa.
    local cand
    for cand in python3.13 python3.12; do
        command -v "$cand" >/dev/null 2>&1 || continue
        if python_version_ok "$cand"; then
            PY_BIN="$(command -v "$cand")"
            PY_SOURCE="alt"
            _pylog ok "$cand $(python_describe "$cand") (${PY_SOURCE}: $PY_BIN)"
            return 0
        fi
        _pylog note "$cand presente, mas não é um Python >= ${HM_MIN_MAJOR}.${HM_MIN_MINOR} utilizável"
    done

    # 4) uv já instalado com CPython gerenciado >= 3.12 (zero download).
    local uv_bin=""
    if command -v uv >/dev/null 2>&1; then
        uv_bin="$(command -v uv)"
    elif [ -x "$HOME/.local/bin/uv" ]; then
        uv_bin="$HOME/.local/bin/uv"
    fi
    if [ -n "$uv_bin" ]; then
        local minor uv_py=""
        for minor in 3.12 3.13 3.14; do
            if uv_py="$("$uv_bin" python find "$minor" 2>/dev/null)" \
                && [ -n "$uv_py" ] && python_version_ok "$uv_py"; then
                PY_BIN="$uv_py"
                PY_SOURCE="uv"
                _pylog ok "python $(python_describe "$PY_BIN") (${PY_SOURCE}: $PY_BIN)"
                return 0
            fi
        done
        _pylog note "uv presente, mas sem CPython >= ${HM_MIN_MAJOR}.${HM_MIN_MINOR} gerenciado"
    fi

    # 5) Bootstrap opt-in — somente com consentimento explícito.
    if [ "$bootstrap" = "true" ]; then
        bootstrap_uv_python
        return 0
    fi

    # 6) Falha rica — instruções acionáveis, nenhuma ação automática.
    local sys_desc="ausente"
    command -v python3 >/dev/null 2>&1 && sys_desc="$(python_describe python3)"
    err "Nenhum Python >= ${HM_MIN_MAJOR}.${HM_MIN_MINOR} disponível (python3 do sistema: ${sys_desc})"
    if [ "${_PY_QUIET:-0}" = "1" ]; then
        return 1
    fi
    cat >&2 <<EOF

O Huawei Manager requer Python ${HM_MIN_MAJOR}.${HM_MIN_MINOR}+. Opções:

  1) Instale um Python recente pela sua distro ou gerenciador. Exemplos:
       sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.12
       pyenv install 3.12 && pyenv global 3.12

  2) Aponte manualmente para um binário já existente:
       export HM_PYTHON=/caminho/para/python3.12

  3) Deixe o instalador provisionar um CPython ${HM_MIN_MAJOR}.${HM_MIN_MINOR} gerenciado pelo uv
     (sem root; instala em ~/.local):
       $0 install --bootstrap-python

EOF
    exit 1
}
