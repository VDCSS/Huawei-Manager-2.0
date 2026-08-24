.PHONY: install install-prod fonts install-fonts run test lint typecheck coverage ci \
        clean clean-all uninstall reinstall reinstall-prod help

VENV      = .venv
PY        = $(VENV)/bin/python3
PIP       = $(PY) -m pip
HUAWEI    = $(VENV)/bin/huawei-manager
INSTALLER = ./setup/install.sh

ICONS_DIR = $(HOME)/.local/share/icons/hicolor
APPS_DIR  = $(HOME)/.local/share/applications
BIN_DIR   = $(HOME)/.local/bin
COMP_DIR  = $(HOME)/.local/share/bash-completion/completions
FONTS_DIR = $(HOME)/.local/share/fonts

# ── Instalação (delega ao instalador canônico setup/install.sh) ────
install:
	$(INSTALLER) install --dev

install-prod:
	$(INSTALLER) install --prod

# Apenas fontes Google Fonts (IBM Plex Sans, Space Grotesk, JetBrains Mono)
fonts:
	$(INSTALLER) fonts

install-fonts: fonts

# ── Execução ────────────────────────────────────────────────────────
run:
	$(HUAWEI)

# ── Reinstalação (após git pull — só dependências) ──────────────────
reinstall:
	$(PIP) install -e ".[dev,vault,aws]"

reinstall-prod:
	$(PIP) install -e ".[vault,aws]"
	@echo "✔ Dependências de produção atualizadas e pacote reinstalado."

# ── Remoção simétrica (inclui fontes) ───────────────────────────────
uninstall:
	rm -f $(APPS_DIR)/huawei-manager.desktop
	rm -f $(ICONS_DIR)/48x48/apps/huawei-manager.png
	rm -f $(ICONS_DIR)/256x256/apps/huawei-manager.png
	rm -f $(BIN_DIR)/huawei
	rm -f $(BIN_DIR)/huawei-manager
	rm -f $(COMP_DIR)/huawei
	rm -f $(FONTS_DIR)/IBMPlexSans.ttf
	rm -f $(FONTS_DIR)/SpaceGrotesk.ttf
	rm -f $(FONTS_DIR)/JetBrainsMono.ttf
	-@fc-cache -f $(FONTS_DIR) >/dev/null 2>&1
	update-desktop-database $(APPS_DIR) >/dev/null 2>&1 || true
	@echo "✔ Huawei Manager removido do sistema."

# ── Criptografia ────────────────────────────────────────────────────
encrypt-env:
	SECRETS_KEY=$${SECRETS_KEY} scripts/encrypt-env.sh

decrypt-env:
	SECRETS_KEY=$${SECRETS_KEY} scripts/decrypt-env.sh

# ── Testes / CI ─────────────────────────────────────────────────────
test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check src/huawei_manager/

typecheck:
	$(PY) -m pyright

coverage:
	$(PY) -m pytest --cov=src/huawei_manager --cov-report=term-missing

ci: lint test typecheck

# ── Limpeza ─────────────────────────────────────────────────────────
# clean remove APENAS caches e artefatos de cobertura.
# NUNCA remove .venv nem logs (use clean-all para isso, explicitamente).
clean:
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	find . -name '*.pyc' -delete
	find . -name '*,cover' -delete

# clean-all remove tudo — incluindo .venv e logs (destrutivo, opt-in).
clean-all: clean
	rm -rf $(VENV) logs

help:
	@echo "Targets: install install-prod fonts run reinstall reinstall-prod uninstall"
	@echo "         test lint typecheck coverage ci encrypt-env decrypt-env clean clean-all"
