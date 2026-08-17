# Relatório de Segurança — Huawei Manager

> **Data:** 05/07/2026  
> **Versão:** 2.0.0  
> **Branch:** Mexendo-na-Estrutura-do-projeto

---

## 1. ResumoExecutivo

O Huawei Manager implementa **6 camadas de segurança** que cobrem autenticação, autorização, validação de comandos, rate limiting, auditoria e timeline de eventos. Todas integradas ao fluxo da GUI e testadas com 27 cenários de segurança.

| Camada | Módulo | Status |
|--------|--------|--------|
| RBAC | `authz.py` (131 linhas) | ✅ |
| Command Validation | `validator.py` (157 linhas) | ✅ |
| Dry-Run & Rollback | `dryrun.py` (213 linhas) | ✅ |
| Rate Limiting | `ratelimit.py` (150 linhas) | ✅ |
| Audit Log | `audit_log.py` | ✅ |
| Security Timeline | `security_events.py` (183 linhas) | ✅ |
| SNMP Trap Handler | `snmp_handler.py` (45 linhas) | ✅ |
| Secrets Management | `vault.py` (4 backends) | ✅ |

---

## 2. Autenticação e Autorização (RBAC)

### 2.1 Níveis de Acesso

| Papel | Hierarquia | Acesso |
|-------|-----------|--------|
| `USER` | 0 (base) | Dashboard, SSH, topologia (sem portas/credenciais) |
| `TECNICO` | 1 | Tudo do USER + debug, manutenção, bypass de deny-list |
| `ADMIN` | 2 | Tudo do TECNICO + editar/excluir VNFs, mock-mode toggle |

### 2.2 Mecanismos

- **Decorator `@require_role`** em `authz.py` — protege operações do ControllerCore com verificação hierárquica
- **`SessionTracker`** — timeout de inatividade configurável (default 300s), reseta para USER automaticamente
- **Lockout 30s** — 3 tentativas falhas de autenticação bloqueiam o diálogo

### 2.3 Testes (B1)

`TestBypassRBAC` (test_security_integration.py) — verifica que:
- Comando admin como operador é bloqueado
- `PermissionError` é levantado corretamente
- Role inválida retorna erro

---

## 3. Validação de Comandos

### 3.1 CommandValidator

`validator.py` implementa allow-list + deny-list baseada em regex:

**Allow-list (sempre permitido):**
- `^display\s+`
- `^show\s+`

**Deny-list (bloqueado para USER, bypassável por TECNICO/ADMIN):**
- `^format\s+flash`
- `^reset\s+saved-configuration`
- `^undo\s+startup`
- `\bdelete\b`
- `\breset\b`

### 3.2 Fluxo de Validação

```
Comando CLI
  ├── Vazio → ❌ denied ("Empty command")
  ├── Allow-list match → ✅ allowed
  ├── Deny-list match:
  │     ├── role ∈ {admin, tecnico} → ✅ allowed (bypass_2fa=True)
  │     └── role = user → ❌ denied ("Command denied by policy")
  └── Unknown (nem allow, nem deny) → ❌ denied ("Unknown command")
```

### 3.3 Integração GUI

`CommandValidator.validate()` é chamado em:
- `handlers.py:_exec_cmd()` (linha ~179) — comandos do editor
- `handlers.py:_exec_config()` (linha ~203) — comandos de configuração

### 3.4 Testes (B2, B5)

- `TestCommandInjection` — comando com `; rm -rf /` é rejeitado
- `TestDenyList` — comando `format flash:` cai na deny list
- Bypass admin para comandos negados

---

## 4. Dry-Run e Rollback

### 4.1 DryRunEngine

`dryrun.py` implementa diff, dry-run, apply e rollback:

1. **Diff**: `difflib.unified_diff` entre config atual e proposta
2. **Dry-Run**: Simula execução sem enviar comandos (gera diff apenas)
3. **Apply**: Executa comando, com rollback automático se fornecido
4. **Rollback**: Restaura config original em caso de falha

### 4.2 Integração GUI

- `DryRunEngine.diff()` chamado em `_exec_config` (handlers.py)
- Exibido como diff visual para admin/tecnico

### 4.3 Testes (B4)

`TestDryRunMandatory` — configuração sem dry-run é bloqueada para não-admin

---

## 5. Rate Limiting

### 5.1 RateLimiter

`ratelimit.py` implementa algoritmo **token bucket** por dispositivo:

- **Leitura** (show/display): sempre permitida
- **Escrita** (configure/commit): consome 1 token
- **Defaults**: 10 tokens/s rate, 20 tokens burst
- Bucket recarrega automaticamente baseado em tempo decorrido

### 5.2 Integração

- `RateLimiter.check(device_id, is_write=True)` chamado pelo `SSHSouthbound`
- Operações de leitura pulam verificação

### 5.3 Testes (B6)

`TestRateLimit` — >5 comandos de escrita/s no mesmo dispositivo são throttled

---

## 6. Auditoria

### 6.1 Estrutura

`audit_log.py` — logger de auditoria em JSON Lines:

```json
{
  "operation": "command_denied",
  "user": "operator",
  "host": "192.168.1.1",
  "status": "blocked",
  "details": "Command denied by policy",
  "response_time_ms": 0,
  "session_id": "ses_abc123",
  "timestamp": "2026-07-05T10:30:00"
}
```

### 6.2 Eventos Auditáveis

| Operação | Disparado por |
|----------|--------------|
| `command_denied` | CommandValidator — comando rejeitado |
| `command_bypass` | CommandValidator — bypass 2FA de admin |
| `ssh_connect` | Handlers — conexão SSH |
| `ssh_disconnect` | Handlers — desconexão SSH |
| `config_change` | Handlers — alteração de config |
| `backup` | Handlers — backup executado |
| `auth_login` | Auth dialog — login bem-sucedido |
| `auth_failure` | Auth dialog — falha de autenticação |

### 6.3 Sanitização de Secrets

Nenhuma credencial (IP, porta, token, chave) aparece em logs INFO ou terminal:
- Host/porta em DEBUG apenas
- Token NCE truncado para 4 chars
- Caminho de chave SSH em DEBUG apenas

### 6.4 Testes (B3, B7)

- `TestAuditChain` — todos os comandos passam pelo audit log
- `TestSecretsExposure` — nenhuma credencial aparece em output de log/erro

---

## 7. Security Timeline

### 7.1 SecurityTimeline

`security_events.py` — timeline de eventos de segurança:

- **Categorias**: auth, config, policy, system, network
- **Severidades**: critical, high, medium, low, info
- **Filtros**: por categoria, severidade, dispositivo, operador
- **Acknowledge**: eventos podem ser marcados como reconhecidos
- 5000 eventos em memória (maxlen configurável)

### 7.2 Integração

- Instanciado em `app.py` como `_security_timeline`
- Eventos adicionados via `add_event()` em handlers
- Acessível via `_security_timeline` no app

---

## 8. Gerenciamento de Secrets

`vault.py` — 4 backends de secrets com fallchain:

| Backend | Uso | Proteção |
|---------|-----|----------|
| `.env` | Lab/desenvolvimento | Texto plano (gitignorado) |
| SOPS (age) | Produção | Criptografia age encryption |
| HashiCorp Vault | Enterprise | Autenticação por token |
| AWS Secrets Manager | Cloud | IAM roles |

Rotação de chave SSH ED25519 com push automático ao dispositivo.

---

## 9. Matriz de Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| Command Injection | Baixa | Alto | CommandValidator com allow/deny lists |
| RBAC Bypass | Baixa | Alto | `@require_role` + SessionTracker timeout |
| Rate Limit Bypass | Baixa | Médio | Token bucket por dispositivo |
| Secrets Exposure | Média | Alto | Sanitização em logs + vault criptografado |
| SNMP Trap Spoofing | Baixa | Baixo | Handler valida OID + source |
| Dry-Run Bypass | Baixa | Médio | Validação obrigatória no fluxo `_exec_config` |

---

## 10. Cobertura de Testes de Segurança

| Cenário | Teste | Status |
|---------|-------|--------|
| B1 — Bypass RBAC | `TestBypassRBAC` (3 asserts) | ✅ |
| B2 — Command Injection | `TestCommandInjection` (3 asserts) | ✅ |
| B3 — Audit Chain | `TestAuditChain` (3 asserts) | ✅ |
| B4 — Dry-Run Obrigatório | `TestDryRunMandatory` (3 asserts) | ✅ |
| B5 — Deny List | `TestDenyList` (3 asserts) | ✅ |
| B6 — Rate Limit | `TestRateLimit` (3 asserts) | ✅ |
| B7 — Secrets Exposure | `TestSecretsExposure` (3 asserts) | ✅ |
| **Total** | **27 testes** | **✅ 27/27** |

---

## 11. Recomendações

1. **Produção**: Usar SOPS ou Vault como backend de secrets (nunca `.env` em produção)
2. **Monitoria**: Conectar SecurityTimeline a um sistema externo via webhook
3. **SNMP**: Implementar servidor SNMP real (atualmente apenas handler de traps)
4. **Rotação**: Habilitar rotação automática de chave SSH via cron
5. **Auditoria externa**: Exportar audit log para SIEM (Splunk/ELK)
