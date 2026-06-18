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
DESKTOP   = huawei-manager.desktop

# ── Instalação completa (primeira vez) ──────────────────────────
install: venv pip-install install-icon install-desktop install-shell
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

# ── Desinstalação ───────────────────────────────────────────────
uninstall:
	rm -f $(APPS_DIR)/$(DESKTOP)
	rm -f $(ICONS_DIR)/48x48/apps/huawei-manager.png
	rm -f $(ICONS_DIR)/256x256/apps/huawei-manager.png
	rm -f $(BIN_DIR)/huawei
	rm -f $(BIN_DIR)/huawei-manager
	rm -f $(COMP_DIR)/huawei
	update-desktop-database $(APPS_DIR) 2>/dev/null || true
	@echo "✔ Huawei Manager removido do sistema."

# ── Testes / CI ─────────────────────────────────────────────────
test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check

typecheck:
	$(PY) -m pyright

ci: lint test typecheck

# ── Limpeza ─────────────────────────────────────────────────────
clean:
	rm -rf .pytest_cache .ruff_cache __pycache__
	find . -name '*.pyc' -delete
