# System-View Edge Case — P3.7

> **Data:** 05/07/2026  
> **Arquivo:** `src/huawei_manager/handlers.py`  
> **Referência:** Plano SDN Unificado, Frente C4

---

## Descrição

O **system-view** é um modo de acesso especial em equipamentos Huawei que permite
executar comandos de configuração sem sair do terminal. No Huawei Manager, este
modo é suportado via um checkbox na aba **Editor de Comandos** (pages.py:317).

Quando ativado, o comando do usuário é executado **dentro** de uma sessão
`system-view`, ou seja:

```
system-view
<comando do usuário>
quit
```

## Localização no Código

**handlers.py** — método `_exec_cmd()`, linhas 227-235:

```python
if self._sysview_var.get():
    self._loading(...)
    self.session.run_cli_timing("system-view")   # entra no modo
    result = self.session.run_cli_timing(cmd)     # executa comando
    self.session.run_cli_timing("quit")           # sai do modo
else:
    self._loading(...)
    result = self._sb.send_command(cmd or "")     # modo normal
```

## Por que é um Edge Case?

### 1. Bypass do CommandValidator

Comandos executados via system-view **não passam pelo `CommandValidator`**
(validator.py). O fluxo `send_command()` (usado pelo Southbound) tem validação,
mas `run_cli_timing()` (usado no system-view) **não**:

| Fluxo | Validação | Mecanismo |
|-------|-----------|-----------|
| `send_command()` via `_exec_config` | ✅ `CommandValidator.validate()` + `DryRunEngine.diff()` | handlers.py:247-257 |
| `run_cli_timing()` via `_exec_cmd` + system-view | ❌ Nenhuma validação | handlers.py:230-232 |

### 2. Mecanismo Diferente de Transporte

- `send_command()` — usa método assíncrono do Southbound (`SSHSouthbound`),
  passa pelo rate limiter e event queue
- `run_cli_timing()` — chama diretamente o `NetmikoSession`, sem rate limit,
  sem event queue, sem auditoria de comando

### 3. Auditoria Parcial

O evento `COMMAND_EXECUTED` é adicionado à event queue
(handlers.py:237-238), mas o comando **não** é registrado no audit log
com detalhes de operação.

## Risco

| Fator | Avaliação |
|-------|-----------|
| Probabilidade de exploração | Baixa (requer acesso ao Editor de Comandos) |
| Impacto | Médio (comando arbitrário via system-view) |
| Mitigação | Só acessível a usuários autenticados; `_exec_config` tem validação |

## Recomendação

Para versões futuras:

1. **Adicionar `CommandValidator.validate()`** antes de `run_cli_timing("system-view")`
2. **Registrar no audit log** comandos executados via system-view com operação `system_view_exec`
3. **Restringir system-view** a papéis TECNICO/ADMIN apenas

```python
# Recomendado para futura implementação:
if self._sysview_var.get():
    # Validar antes de entrar em system-view
    validator = getattr(self, "_cmd_validator", None)
    if validator is not None:
        vr = validator.validate(cmd, getattr(self, "_access_level", "user"))
        if not vr.allowed:
            self._write(self.out_cmd, f"✘ Bloqueado: {vr.reason}")
            return
    # Executar dentro de system-view
    ...
```

## Estado Atual

- ✅ Edge case identificado e documentado
- ⏳ Validação e auditoria — pendente para próxima iteração
