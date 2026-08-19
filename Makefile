.PHONY: install run test lint typecheck clean \
        install-desktop install-icon install-shell uninstall reinstall

VENV      = .venv
PY        = $(VENV)/bin/python3
PIP       = $(PY) -m pip
HUAWEI    = $(VENV)/bin/huawei-manager

ICONS_DIR = $(HOME)/.local/share/icons/hicolor
APPS_DIR  = $(HOME)/.local/share/applications
BIN_DIR   = $(HOME)/.local/bin
COMP_DIR  = $(HOME)/.local/share/bash-completion/completions
FONTS_DIR = $(HOME)/.local/share/fonts
DESKTOP   = share/huawei-manager.desktop

# Google Fonts URLs
IBM_PLEX_SANS_URL = https://github.com/google/fonts/raw/main/ofl/ibmplexsans/IBMPlexSans%5Bwght%5D.ttf
SPACE_GROTESK_URL = https://github.com/google/fonts/raw/main/ofl/spacegrotesk/SpaceGrotesk%5Bwght%5D.ttf
JETBRAINS_MONO_URL = https://github.com/google/fonts/raw/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf

# ── Instalação completa (primeira vez) ──────────────────────────
install: venv pip-install install-fonts install-icon install-desktop install-shell
	@echo "✔ Huawei Manager instalado."
	@echo "  Procure 'Huawei Manager' no menu ou digite 'huawei manager'."

venv:
	python3 -m venv $(VENV)

pip-install:
	$(PIP) install -e ".[dev]"

# ── Execução ────────────────────────────────────────────────────
run:
	$(HUAWEI)

# ── Reinstalação (após git pull) ────────────────────────────────
reinstall:
	$(PIP) install -e .

# ── Desktop Entry ───────────────────────────────────────────────
install-desktop: install-icon
	sed 's|__EXEC_PATH__|$(abspath $(VENV))/bin/huawei-manager|g' \
		$(DESKTOP) > $(APPS_DIR)/$(DESKTOP)
	chmod 644 $(APPS_DIR)/$(DESKTOP)
	update-desktop-database $(APPS_DIR) 2>/dev/null || true
	@echo "✔ Atalho de menu instalado."

# ── Ícone ───────────────────────────────────────────────────────
install-icon:
	install -Dm 644 share/icons/huawei-manager.png \
		$(ICONS_DIR)/48x48/apps/huawei-manager.png 2>/dev/null || true
	install -Dm 644 share/icons/huawei-manager.png \
		$(ICONS_DIR)/256x256/apps/huawei-manager.png 2>/dev/null || true
	@echo "✔ Icone instalado (se o arquivo existir)."

# ── Shell dispatcher "huawei manager" + tab complete ────────────
install-shell:
	sed 's|__VENV_DIR__|$(abspath $(VENV))|g' share/shell/huawei > $(BIN_DIR)/huawei
	chmod 755 $(BIN_DIR)/huawei
	install -Dm 644 share/shell/completion/huawei $(COMP_DIR)/huawei
	{ echo '#!/usr/bin/env bash'; echo 'exec $(abspath $(VENV))/bin/huawei-manager "$$@"'; } \
		> $(BIN_DIR)/huawei-manager
	chmod 755 $(BIN_DIR)/huawei-manager
	@echo "✔ Comando 'huawei' instalado."
	@echo "  Recarregue o shell: exec bash"
	@echo "  Teste: huawei<TAB> → huawei manager"

# ── Fontes Google Fonts ───────────────────────────────────────────
install-fonts:
	mkdir -p $(FONTS_DIR)
	# IBM Plex Sans
	wget -q -O /tmp/IBMPlexSans.ttf "$(IBM_PLEX_SANS_URL)" && \
		cp /tmp/IBMPlexSans.ttf $(FONTS_DIR)/IBMPlexSans.ttf && \
		echo "✔ IBM Plex Sans instalada"
	# Space Grotesk
	wget -q -O /tmp/SpaceGrotesk.ttf "$(SPACE_GROTESK_URL)" && \
		cp /tmp/SpaceGrotesk.ttf $(FONTS_DIR)/SpaceGrotesk.ttf && \
		echo "✔ Space Grotesk instalada"
	# JetBrains Mono
	wget -q -O /tmp/JetBrainsMono.ttf "$(JETBRAINS_MONO_URL)" && \
		cp /tmp/JetBrainsMono.ttf $(FONTS_DIR)/JetBrainsMono.ttf && \
		echo "✔ JetBrains Mono instalada"
	fc-cache -f $(FONTS_DIR) 2>/dev/null || true
	@echo "✔ Fontes Google Fonts instaladas e cache atualizado."

uninstall:
	rm -f $(APPS_DIR)/$(DESKTOP)
	rm -f $(ICONS_DIR)/48x48/apps/huawei-manager.png
	rm -f $(ICONS_DIR)/256x256/apps/huawei-manager.png
	rm -f $(BIN_DIR)/huawei
	rm -f $(BIN_DIR)/huawei-manager
	rm -f $(COMP_DIR)/huawei
	update-desktop-database $(APPS_DIR) 2>/dev/null || true
	@echo "✔ Huawei Manager removido do sistema."

# ── Criptografia ────────────────────────────────────────────────
encrypt-env:
	SECRETS_KEY=$${SECRETS_KEY} scripts/encrypt-env.sh

decrypt-env:
	SECRETS_KEY=$${SECRETS_KEY} scripts/decrypt-env.sh

# ── Testes / CI ─────────────────────────────────────────────────
test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check src/huawei_manager/

typecheck:
	$(PY) -m pyright

coverage:
	$(PY) -m pytest --cov=src/huawei_manager --cov-report=term-missing

ci: lint test typecheck

# ── Limpeza ─────────────────────────────────────────────────────
clean:
	rm -rf .pytest_cache .ruff_cache __pycache__
	find . -name '*.pyc' -delete
	find . -name '*,cover' -delete
