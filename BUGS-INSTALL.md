# Bugs de Instalação Encontrados

## Bug 1: `pip-install-prod` não instala o pacote

**Sintoma:** `make install-prod` falha porque `.venv/bin/huawei-manager` não existe.

**Causa:** O target `pip-install-prod` só roda `pip install -r requirements/prod.txt`, que instala as dependências (netmiko, PySide6, etc.) mas **não instala o pacote do projeto**. Sem `pip install .`, o setuptools não cria o entry point `huawei-manager` em `.venv/bin/`.

**Correção no Makefile:**

```makefile
# ANTES (linha 38-39):
pip-install-prod:
	$(PIP) install -r requirements/prod.txt

# DEPOIS:
pip-install-prod:
	$(PIP) install -r requirements/prod.txt
	$(PIP) install .
```

---

## Bug 2: `install-desktop` grava o `.desktop` em path errado

**Sintoma:** O atalho de menu não aparece no desktop.

**Causa:** A variável `DESKTOP` é usada tanto como caminho de origem quanto no path de destino, criando um path duplicado:

```makefile
# Linha 15:
DESKTOP   = share/huawei-manager.desktop

# Linha 54-55:
install-desktop: install-icon
	sed ... $(DESKTOP) > $(APPS_DIR)/$(DESKTOP)
#                            ^^^^^^^^^^^^^^^^^^^^^^^
#                            Resultado: ~/.local/share/applications/share/huawei-manager.desktop
#                            Deveria ser: ~/.local/share/applications/huawei-manager.desktop
```

**Correção no Makefile:**

```makefile
# ANTES (linha 54-55):
install-desktop: install-icon
	sed 's|__EXEC_PATH__|$(abspath $(VENV))/bin/huawei-manager|g' \
		$(DESKTOP) > $(APPS_DIR)/$(DESKTOP)
	chmod 644 $(APPS_DIR)/$(DESKTOP)

# DEPOIS:
install-desktop: install-icon
	sed 's|__EXEC_PATH__|$(abspath $(VENV))/bin/huawei-manager|g' \
		$(DESKTOP) > $(APPS_DIR)/huawei-manager.desktop
	chmod 644 $(APPS_DIR)/huawei-manager.desktop
```

---

## Resumo

| Bug | Linha(s) | Impacto |
|-----|----------|---------|
| `pip-install-prod` falta `pip install .` | 38-39 | App não roda — entry point não criado |
| `install-desktop` path duplicado | 54-55 | Atalho de menu não aparece |
