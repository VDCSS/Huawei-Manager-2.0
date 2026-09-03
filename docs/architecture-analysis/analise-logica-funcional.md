# Análise Lógica Funcional — Huawei Manager 2.0

> **Gerado automaticamente** a partir do knowledge graph (graphify) — 3.773 nós, 7.817 arestas, 216 comunidades  
> **Data:** 2026-09-02  
> **Versão:** 1.0

---

## Sumário

1. [Entry Point & Bootstrap](#1-entry-point--bootstrap)
2. [Apresentação (GUI) — PySide6/Qt](#2-apresentação-gui--pyside6qt)
3. [Controle SDN — sdn_controller/](#3-controle-sdn--sdn_controller)
4. [Segredo & Vault — vault_backends/](#4-segredo--vault--vault_backends)
5. [Auditoria & Compliance — audit_log.py](#5-auditoria--compliance--audit_logpy)
6. [Persistência & Modelos](#6-persistência--modelos)
7. [Serviços & Catálogo](#7-serviços--catálogo)
8. [Instalação & Deploy — setup/](#8-instalação--deploy--setup)
9. [Fluxos de Dados Principais](#9-fluxos-de-dados-principais)
10. [Testes & Qualidade](#10-testes--qualidade)
11. [Agentes de Scan](#11-agentes-de-scan)
12. [Tema & Constantes](#12-tema--constantes)
13. [Mapeamento Arquivo → Domínio → Responsabilidade](#13-mapeamento-arquivo--domínio--responsabilidade)
14. [Padrões Arquiteturais Identificados](#14-padrões-arquiteturais-identificados)

---

## 1. Entry Point & Bootstrap

### Arquivos

| Arquivo | Papel |
|---------|-------|
| `src/huawei_manager/app.py` | **Main Window** — `HuaweiRouterApp(QMainWindow)`: inicializa Qt, carrega temas, cria `PageBuilder`, injeta `AppCoreProtocol` nos mixins, gerencia lifecycle (closeEvent, timers), coordena 10 abas |
| `src/huawei_manager/_config.py` | **Module-level setup** — configura logging estruturado, inicializa `AuditLogger`, carrega secrets via `vault.get_backend()`, define constantes globais (`VNF_ENCRYPT_KEY`, `AUDIT_HMAC_KEY`) |
| `src/huawei_manager/_protocols.py` | **Contrato Type-Safe** — `AppCoreProtocol` (Protocol): define interface obrigatória para mixins (UI + eventos + threading + vault + devices), evita acoplamento circular |

### Fluxo de Inicialização

```
main() → HuaweiRouterApp.__init__()
    → _config.setup_logging() + AuditLogger.__init__()
    → vault.get_backend() → carrega secrets
    → PageBuilder.__init__() → registra 10 page mixins
    → Injeta AppCoreProtocol em todos mixins (handlers, app_state, app_threading, app_notify)
    → show() → event loop Qt
```

---

## 2. Apresentação (GUI) — PySide6/Qt

### 2.1 Páginas (10 abas) — `src/huawei_manager/pages/`

| Arquivo | Aba | Responsabilidade |
|---------|-----|------------------|
| `builder.py` | Core | `PageBuilder` — factory de páginas, layout base (splitter esquerda/direita), registro de mixins |
| `dashboard.py` | Dashboard | Cards de saúde, métricas SDN, alertas recentes, atalhos rápidos |
| `topology.py` | Topologia/VNFs | `TopologyCanvas` (QGraphicsView), grade adaptativa, nós coloridos por tipo VNF, seleção multi-dispositivo |
| `config_atual.py` | Config Atual | Visualização running-config, diff com startup, busca/filtro |
| `routing.py` | Roteamento | Tabelas de rotas, protocolos dinâmicos, nexthop tracking |
| `arp.py` | ARP | Tabela ARP/NDP, aging, conflitos IP-MAC |
| `system_info.py` | Info Sistema | CPU, memória, interfaces, uptime, versão firmware |
| `cmd.py` | Editor Comandos | Catálogo 144 serviços, templates, dry-run preview, validação sintaxe |
| `backup.py` | Backup | Histórico snapshots, agendamento, restore point-and-click |
| `services.py` | Serviços | Catálogo hierárquico (144 serviços), filtros, dependências |
| `manutencao.py` | Manutenção | Diagnósticos, ping/trace, reboot agendado, health checks |

### 2.2 Widgets Reutilizáveis — `src/huawei_manager/widgets/`

| Arquivo | Componente | Descrição |
|---------|------------|-----------|
| `auth_overlay.py` | `AuthOverlay` | Modal full-screen autenticação (PIN/biometria), **gate de atalhos globais** (Enter/Escape/Ctrl+Q bloqueados quando aberta) |
| `neon_button.py` | `NeonButton` | Botão temático dark/light, variants (primary/danger/ghost), loading state, acessibilidade WCAG AA |
| `neon_entry.py` | `NeonEntry` / `NeonTextEdit` | Inputs estilizados, validação visual, placeholder animado |
| `helpers.py` | `_css_font()` | Factory de fontes CSS (IBM Plex Sans, Space Grotesk, JetBrains Mono) com fallbacks |
| `__init__.py` | Exports | `ActionButton`, `NeonButton`, `NeonEntry`, `styled_text`, `output_text` |

### 2.3 Mixins de Lógica UI — `src/huawei_manager/handlers/`

| Arquivo | Mixin | Responsabilidade |
|---------|-------|------------------|
| `devices.py` | `DevicesMixin` | Ponte fina UI ↔ `DeviceService`: CRUD dispositivos, seleção canvas, refresh lista, dialog add/edit |
| `ssh.py` | `SshMixin` | Conexão SSH per-device: `_do_connect`, `_toggle_connect`, error handling (auth/timeout/validation), session tracker |
| `commands.py` | `CommandsMixin` | Execução comandos CLI: validação prévia, dry-run, apply com rollback, auditoria automática |
| `vnfs.py` | `VnfsMixin` | Orquestração VNFs: deploy, scale, heal, sync com `ControllerCore` |

### 2.4 Infraestrutura UI — `src/huawei_manager/`

| Arquivo | Mixin/Classe | Função |
|---------|--------------|--------|
| `app_threading.py` | `ThreadingMixin` | Async UI: `dispatch()` (callbacks UI thread), `spawn_io()` (I/O bound), `spawn_cpu()` (CPU bound), `write()` (output seguro), `loading()` (spinner), `run()` (corrotinas) |
| `app_notify.py` | `NotifyMixin` | Toasts/notificações: success/error/warning/info, auto-dismiss, queue limitada |
| `app_state.py` | `AppStateMixin` | **Bridge SDN → UI**: `_on_sdn_event()` consome `EventQueue`, atualiza estado visual (device online/offline/error, métricas polling) |

---

## 3. Controle SDN — `src/huawei_manager/sdn_controller/`

### 3.1 Estado Centralizado

| Arquivo | Classe | Responsabilidade |
|---------|--------|------------------|
| `core.py` | `ControllerCore` | **Single Source of Truth** — estado RAM de todos dispositivos (DeviceState: status, metadata, última coleta), JSON dump periódico (`dump_interval`), thread-safe (RLock), integração `EventQueue` pub/sub |
| `event_queue.py` | `EventQueue` + `EventType` | Fila **PriorityQueue** thread-safe com backpressure, pub/sub múltiplos consumidores, enum `EventType`: `DEVICE_CONNECTED`, `DEVICE_DISCONNECTED`, `DEVICE_ERROR`, `DEVICE_STATUS_CHANGED`, `POLLING_TICK`, `CONFIG_CHANGED`, `AUDIT_LOGGED` |
| `bus.py` | `IEventBus` / `IEventConsumer` | Protocolos abstratos para barramento de eventos (desacoplamento producer/consumer) |

### 3.2 Southbound (Comunicação Dispositivos)

| Arquivo | Classe | Responsabilidade |
|---------|--------|------------------|
| `southbound.py` | `SouthboundProtocol` (ABC) | Contrato: `connect()`, `disconnect()`, `is_alive()`, `send_command()`, `send_config()` |
| `southbound.py` | `SSHSouthbound` | Implementação **Netmiko/Paramiko**: sanitização saída (`_sanitize()`), host key verification, ED25519 preference, timeouts configuráveis |
| `session.py` | `NetmikoSession` | Sessão SSH stateful: `ConnectionConfig`, host keys (`~/.ssh/known_hosts`), credential validation, `clean_output()` |
| `session_factory.py` | `SSHSessionFactory` | **Pool per-device** — reusa conexões, polling adaptativo (intervalo dinâmico via `PollingManager`), health checks, cleanup automático |

### 3.3 Validação & Segurança

| Arquivo | Classe | Responsabilidade |
|---------|--------|------------------|
| `validator.py` | `CommandValidator` | **Allow/Deny lists** por role (user/tecnico/admin), regex patterns, `bypass_2fa` flag para admin/tecnico, `validate_and_audit()` integra `AuditLogger`, retorna `ValidationResult(allowed, reason, requires_2fa)` |
| `dryrun.py` | `DryRunEngine` | **Diff engine**: `diff(current, proposed)` → `DiffReport`, `dry_run()` simula sem side effects, `apply()` executa + gera rollback command, `rollback()` restaura config anterior |

### 3.4 Polling Adaptativo

| Arquivo | Classe | Responsabilidade |
|---------|--------|------------------|
| `polling_manager.py` | `PollingManager` | Agendamento inteligente: `IntervalDecider` (exponential backoff), `StabilityTracker` (consecutive successes/failures), prioridade por criticidade do device, consolida serviços por device |
| `polling_manager.py` | `IntervalDecider` | Calcula próximo intervalo: min/max bounds, backoff em erro, reset em estabilidade |
| `polling_manager.py` | `StabilityTracker` | Conta transições estável/instável, dispara eventos `DEVICE_STATUS_CHANGED` |

### 3.5 Drivers (Extensibilidade)

| Arquivo | Classe | Responsabilidade |
|---------|--------|------------------|
| `drivers/base.py` | `BaseDriver` (ABC) | Contrato: `get_capabilities()`, `parse_cli_output()`, `build_config_commands()` |
| `drivers/router.py` | `RouterDriver` | Implementação Huawei: parsers VRP, templates config, model-specific quirks |

---

## 4. Segredo & Vault — `src/huawei_manager/vault_backends/`

### 4.1 Contrato Base

| Arquivo | Classe | Responsabilidade |
|---------|--------|------------------|
| `base.py` | `SecretsBackend` (ABC) | Interface: `get(key)`, `put(key, value)`, `backend_name()`, `last_rotation()`, `_record_rotation()`, `_generate_ed25519()` (ED25519 keygen), `rotate_ssh_key()` (rotação automática) |

### 4.2 5 Implementações Plugáveis

| Arquivo | Backend | Storage | Use Case |
|---------|---------|---------|----------|
| `backends_env.py` | `EnvBackend` | Variáveis ambiente | Dev/CI, secrets não-sensiveis |
| `backends_crypto.py` | `CryptoEnvBackend` | Arquivo cifrado (AES-256-GCM + Fernet) | Produção standalone, **fail-closed** (sem chave = erro) |
| `backends_sops.py` | `SopsBackend` | Arquivos `.sops.yaml` (age) | GitOps, secrets versionados |
| `backends_vault.py` | `VaultBackend` | HashiCorp Vault HTTP API | Enterprise, dynamic secrets, lease |
| `backends_aws.py` | `AWSBackend` | AWS Secrets Manager | Cloud-native, IAM integration |

### 4.3 Factory & Bridge

| Arquivo | Função |
|---------|--------|
| `__init__.py` | `get_backend(name)` → instancia backend configurado, `rotate_ssh_key()` delega para backend ativo |
| `../vault.py` | **Bridge compatibilidade** — re-exports `get_backend`, `rotate_ssh_key`, todos backends, `SecretsBackend` |

---

## 5. Auditoria & Compliance — `src/huawei_manager/audit_log.py`

### 5.1 Estrutura de Dados

| Classe/Struct | Campos Obrigatórios (Schema Imutável) |
|---------------|----------------------------------------|
| `AuditEntry` | `timestamp` (ISO8601), `op` (string), `user`, `host`, `status` (ok/error/timeout), `duration_ms`, `session_id` (UUID), `category` (cli/config/auth/polling), `details` (JSON), `prev_hash` (SHA-256), `hmac` (HMAC-SHA256) |

### 5.2 Mecanismos de Integridade

| Método | Função |
|--------|--------|
| `_hmac(key, data)` | HMAC-SHA256 com `AUDIT_HMAC_KEY` |
| `_entry_hash(entry)` | SHA-256(entry_json + prev_hash) — **hash chain** |
| `_write(entry)` | Append JSON Lines + atualiza tail hash |
| `verify_chain()` | Valida integridade completa (recalcula hashes + HMACs) |
| `timed()` | Context manager: mede duração, captura status, log automático |

### 5.3 Integração

- **Chamado por**: `CommandValidator.validate_and_audit()`, `SSHSouthbound.send_command()`, `PollingManager`, `DeviceRepository` CRUD
- **Fail-closed**: Se `AUDIT_HMAC_KEY` ausente → erro na inicialização (`_config.py`)

---

## 6. Persistência & Modelos

### 6.1 Modelos de Domínio — `src/huawei_manager/`

| Arquivo | Classe/Enum | Descrição |
|---------|-------------|-----------|
| `device_models.py` | `Device` (dataclass) | `id`, `name`, `host`, `type` (ROUTER/SWITCH/FIREWALL/AP), `status` (ONLINE/OFFLINE/ERROR/UNKNOWN), `credentials` (encrypted), `metadata`, `last_seen` |
| `device_models.py` | `DeviceType` / `DeviceStatus` | Enums type-safe |
| `device_inventory.py` | `VnfInventory` | Legacy JSON inventory (migração para SQLite) |
| `services_data.py` | `ServiceDef` / `_SvcSpec` | Catálogo 144 serviços: `id`, `name`, `category`, `cli_template`, `params`, `dependencies`, `risk_level` |
| `catalog.py` | `get_service_by_id()`, `search_services()` | Lookup otimizado, filtros por categoria/risk |

### 6.2 Repositório SQLite — `src/huawei_manager/device_repository.py`

| Método | Operação |
|--------|----------|
| `create_device()` / `update_device()` | Upsert com criptografia senha (`device_crypto._encrypt_val`) |
| `get_device()` / `list_devices()` | Descriptografia transparente (`_decrypt_val`) |
| `delete_device()` / `search_devices()` | Filtros por nome/host/tipo/status |
| `_device_to_row()` / `_row_to_device()` | Serialização ↔ DB (campos: id, name, host, type, status, encrypted_password, metadata_json) |

### 6.3 Migração — `src/huawei_manager/migration.py`

| Função | Descrição |
|--------|-----------|
| `migrate_json_inventory()` | JSON → SQLite idempotente, dry-run mode, preserva metadata extra, rollback-safe |

### 6.4 Criptografia Dispositivos — `src/huawei_manager/device_crypto.py`

| Função | Descrição |
|--------|-----------|
| `_get_fernet_encrypt()` | Requer `VNF_ENCRYPT_KEY` (base64url 32 bytes), **sem fallback** |
| `_get_fernet_decrypt()` | Requer `VNF_ENCRYPT_KEY`, **ignora `AUDIT_HMAC_KEY`** (fail-closed) |
| `_encrypt_val()` / `_decrypt_val()` | Fernet (AES-128-GCM), round-trip testado, dados HMAC-only não decriptam |

---

## 7. Serviços & Catálogo — `src/huawei_manager/services/`

| Arquivo | Classe | Responsabilidade |
|---------|--------|------------------|
| `device_service.py` | `DeviceService` | **Domain layer** — lógica de negócio dispositivos: validação, conexão, coleta dados, orquestração com `ControllerCore` |
| `catalog.py` | `ServiceCatalog` | 144 serviços pré-definidos: templates CLI, parâmetros tipados, dependências, risk assessment |
| `services_data.py` | `ServiceDef` / `_SvcSpec` | Dataclasses imutáveis, `cli()` retorna template renderizado |

---

## 8. Instalação & Deploy — `setup/`

| Arquivo | Função |
|---------|--------|
| `install.sh` | Entry point: `install --dev\|--prod`, `check`, `reset`, `--bootstrap-python` (uv auto-install Python 3.12+), `HM_PYTHON` override |
| `lib/python.sh` | **Python Resolver**: cadeia HM_PYTHON → system python3 → alt (3.13/3.12) → uv → bootstrap opt-in → falha rica com 3 remediações |
| `lib/common.sh` | `log_info/warn/error`, `die()` (STDOUT per spec), cores ANSI |
| `setup.sh` | Shell dispatcher: `huawei` command + tab-completion + `.desktop` entry |
| `Makefile` | Delegador puro: `install` (dev), `install-prod` (runtime), `reinstall-prod`, `fonts`, `run`, `test`, `ci`, `clean-all` |
| `requirements/prod.txt` | 6 deps runtime `~=` (PySide6, hvac, boto3, pyyaml, netmiko, cryptography) |
| `requirements/dev.txt` | `-r prod.txt` + 5 tools (ruff, pyright, pytest, pytest-qt, pytest-cov) |

---

## 9. Fluxos de Dados Principais

### 9.1 Conexão Dispositivo (UI → SSH → Device)

```
User clica "Conectar" (Topology page)
    → SshMixin._toggle_connect() [handlers/ssh.py]
    → SshMixin._do_connect() → spawn_io()
    → SSHSouthbound.connect() [sdn_controller/southbound.py]
    → NetmikoSession.connect() [session.py]
    → SSHSessionFactory.get_session() [session_factory.py] (pool per-device)
    → DeviceRepository.get_device() [device_repository.py] (descriptografa credenciais)
    → vault.get_backend().get() [vault_backends/] (secrets)
    → ControllerCore.register() [core.py] + EventQueue.publish(DEVICE_CONNECTED)
    → AppStateMixin._on_sdn_event() [app_state.py] → UI update
    → AuditLogger.log_operation() [audit_log.py]
```

### 9.2 Execução Comando com Validação & Dry-Run

```
User executa comando (Editor page)
    → CommandsMixin.execute_command() [handlers/commands.py]
    → CommandValidator.validate_and_audit() [validator.py]
        → allow/deny list + role check + bypass_2fa
        → AuditLogger.log_operation()
    → Se permitido: DryRunEngine.dry_run() [dryrun.py]
        → SSHSouthbound.send_command() → diff simulado
    → User confirma: DryRunEngine.apply() [dryrun.py]
        → SSHSouthbound.send_config() + rollback command gerado
    → ControllerCore.update_state() + EventQueue.publish(CONFIG_CHANGED)
    → AuditLogger.log_operation() (resultado final)
```

### 9.3 Polling Adaptativo (Background → UI)

```
PollingManager.tick() [polling_manager.py] (timer)
    → Para cada device online: SSHSessionFactory.get_session()
    → SSHSouthbound.send_command() (comandos de coleta)
    → Normalizer.parse() [normalizer.py] → dataclasses estruturadas
    → ControllerCore.update_device_state() [core.py]
    → EventQueue.publish(DEVICE_STATUS_CHANGED / POLLING_TICK)
    → AppStateMixin._on_sdn_event() [app_state.py]
    → UI atualiza: status badge, métricas, topology canvas
```

---

## 10. Testes & Qualidade — `tests/`

| Arquivo/Pasta | Cobertura | Tipo |
|---------------|-----------|------|
| `test_controller_core.py` | ControllerCore CRUD, events, dump/load, concorrência | Unit + Integration |
| `test_dryrun.py` | Diff generation, dry-run, apply, rollback | Unit |
| `test_polling_manager.py` | IntervalDecider, StabilityTracker, adaptive polling | Unit |
| `test_southbound.py` | SouthboundProtocol ABC, SSHSouthbound mock | Unit |
| `test_session.py` | NetmikoSession lifecycle, credentials, commands | Unit |
| `test_vnf_crypto.py` | device_crypto fail-closed, round-trip, HMAC separation | Unit |
| `test_migration.py` | JSON → SQLite idempotente, dry-run | Integration |
| `test_security_integration.py` | CommandValidator bypass, DryRunEngine, ControllerCore | Integration |
| `test_concurrency_patterns.py` | Thread-safety: ControllerCore, Vault, AuditLog | Stress |
| `test_app_threading.py` | ThreadingMixin: dispatch, spawn, loading, shutdown | Unit (headless) |
| `test_pages_resize.py` | 10 suites: responsive layout 800px/1060px/1220px | UI Characterization |
| `test_widgets.py` | NeonButton, NeonEntry, _css_font | Unit |
| `test_agents.py` | Scan agents: deps, cross_ref, dead_code, security, style | Unit |
| `test_vnf_service.py` | DeviceService, catalog | Integration |
| `helpers/gui_test_helper.py` | `GuiTestHelper`: assert_page_renders, key_click, wait | Test Infrastructure |

### Quality Gates (CI)

```bash
make ci  # ruff → pytest → pyright (strict, 0 errors)
```

---

## 11. Agentes de Scan — `src/huawei_manager/agents/`

| Arquivo | Scanner | Função |
|---------|---------|--------|
| `scans/deps.py` | `scan()` | Cruza imports reais (AST) com `pyproject.toml` — detecta missing/extra |
| `scans/cross_ref.py` | `scan()` | Valida `constants.py` vs uso no projeto — aliases, assignments |
| `scans/security.py` | `scan()` | Detecta: hardcoded secrets, SQL injection, command injection, weak crypto |
| `scans/dead_code.py` | `scan()` | Funções/classes não referenciadas (AST + call graph) |
| `scans/structure.py` | `scan()` | Arquitetura: god nodes, ciclos, layer violations |
| `scans/style.py` | `scan()` | Naming, docstrings, type hints, complexity |
| `runner.py` | `AgentRunner` | Orquestração paralela, isolamento falhas (um scan falho não derruba outros) |
| `watcher.py` | `FileWatcher` | Incremental scans on file change (debounced) |

---

## 12. Tema & Constantes — `src/huawei_manager/constants.py`

| Categoria | Constantes |
|-----------|------------|
| **Cores** | `NEON_BLUE`, `NEON_GREEN`, `NEON_RED`, `NEON_AMBER`, `NEON_PURPLE` + variants dark/light |
| **Fontes** | `FONT_UI` (IBM Plex Sans), `FONT_MONO` (JetBrains Mono), `FONT_DISPLAY` (Space Grotesk), tamanhos 8-24px |
| **Temas** | `THEME_DARK` / `THEME_LIGHT` — QSS completo, contraste ≥4.5:1 WCAG AA |
| **Dimensões** | Breakpoints: 800px (mobile), 1060px (tablet), 1220px (desktop), grid 4-col |
| **Enums** | `DeviceType`, `DeviceStatus`, `EventType`, `UserRole` (USER/TECNICO/ADMIN) |

---

## 13. Mapeamento Arquivo → Domínio → Responsabilidade

```
src/huawei_manager/
├── app.py                    → ENTRY POINT          → Main window, lifecycle, DI
├── _config.py                → BOOTSTRAP            → Logging, audit, secrets, constants
├── _protocols.py             → CONTRACT             → AppCoreProtocol (type-safe mixins)
├── constants.py              → DESIGN SYSTEM        → Cores, fontes, temas, enums, breakpoints
├── device_models.py          → DOMAIN MODEL         → Device, DeviceType, DeviceStatus
├── device_inventory.py       → LEGACY               → JSON inventory (migração)
├── device_crypto.py          → CRYPTO               → Fernet AES-256-GCM (fail-closed)
├── device_repository.py      → PERSISTENCE          → SQLite CRUD + crypto transparente
├── device_probe.py           → DISCOVERY            → Probe/identificação dispositivos
├── migration.py              → MIGRATION            → JSON → SQLite idempotente
├── session.py                → SOUTHBOUND           → NetmikoSession (SSH stateful)
├── utils.py                  → UTILS                → clean_output, helpers
├── exceptions.py             → ERROR HIERARCHY      → SdnError → Connection/Validation/Command/Auth
├── audit_log.py              → AUDIT                → JSON Lines + HMAC-SHA256 + hash chain
├── vault.py                  → VAULT BRIDGE         → Re-exports vault_backends
├── vault_backends/           → SECRETS (5 backends) → Env, Crypto, Sops, Vault, AWS + factory
├── app_threading.py          → UI THREADING         → Async UI (dispatch, spawn, loading)
├── app_notify.py             → UI NOTIFICATIONS     → Toasts queue
├── app_state.py              → UI ↔ SDN BRIDGE      → EventQueue consumer → UI update
├── handlers/                 → UI LOGIC (mixins)    → Devices, SSH, Commands, VNFs
├── pages/                    → UI PAGES (10 tabs)   → Dashboard, Topology, Config, Routing, ARP, System, Cmd, Backup, Services, Manutenção
├── widgets/                  → UI COMPONENTS        → AuthOverlay, NeonButton, NeonEntry, helpers
├── services/                 → DOMAIN SERVICES      → DeviceService, Catalog (144 services)
└── sdn_controller/
    ├── core.py               → STATE                → ControllerCore (RAM + JSON dump)
    ├── event_queue.py        → EVENT BUS            → PriorityQueue + pub/sub + EventType
    ├── bus.py                → PROTOCOLS            → IEventBus, IEventConsumer
    ├── southbound.py         → SOUTHBOUND           → ABC + SSHSouthbound (Netmiko)
    ├── session_factory.py    → SESSION POOL         → Per-device pool + adaptive polling
    ├── validator.py          → VALIDATION           → Allow/deny + bypass_2fa + audit
    ├── dryrun.py             → DRY-RUN ENGINE       → Diff, simulate, apply, rollback
    ├── polling_manager.py    → POLLING              → Adaptive intervals + stability tracking
    └── drivers/              → DRIVERS              → BaseDriver + RouterDriver (Huawei VRP)
```

---

## 14. Padrões Arquiteturais Identificados

| Padrão | Onde Aplicado | Benefício |
|--------|---------------|-----------|
| **Protocol/Interface Segregation** | `_protocols.py`, `bus.py`, `southbound.py`, `vault_backends/base.py` | Desacoplamento, testabilidade, substituição |
| **Mixin Composition** | `handlers/*.py`, `app_threading.py`, `app_notify.py`, `app_state.py` | Reuso sem herança múltipla problemática |
| **Repository Pattern** | `device_repository.py` | Separação domínio/persistência, testável |
| **Factory** | `vault_backends/__init__.py`, `setup/lib/python.sh` | Criação configurável, extensível |
| **Observer/Pub-Sub** | `event_queue.py`, `bus.py`, `app_state.py` | Desacoplamento temporal, múltiplos consumidores |
| **Command Pattern** | `dryrun.py` (ApplyResult com rollback command) | Undo/redo, auditoria, transacionalidade |
| **Circuit Breaker** | `PollingManager` (backoff), `SSHSessionFactory` (health check) | Resiliência, fail-fast |
| **Fail-Closed** | `device_crypto.py`, `vault_backends/base.py`, `audit_log.py` | Segurança por padrão |
| **Single Source of Truth** | `ControllerCore` | Consistência estado, elimina race conditions |

---

## Apêndice: God Nodes (Top 5 — Núcleo da Arquitetura)

| Node | Edges | Responsabilidade |
|------|-------|------------------|
| **Device** | 188 | Entidade central — modelo, repositório, crypto, inventory |
| **Event** | 162 | Barramento de eventos SDN (pub/sub, types, queue) |
| **AuditLogger** | 120 | Auditoria JSON Lines + HMAC-SHA256 + hash chain |
| **EventQueue** | 117 | Fila thread-safe prioritizada com backpressure |
| **AppCoreProtocol** | 98 | Contrato type-safe para mixins da UI |

---

## Referências

- **Knowledge Graph**: `graphify-out/graph.json` (3.773 nós, 7.817 arestas)
- **Documentação Arquitetural**: `docs/architecture.md`
- **Levantamento Bibliográfico**: `docs/PRA-levantamento-bibliografico-redes-autonomicas.md`
- **Regras de Engenharia**: `AGENTS.md` (seção "Boas Práticas de Engenharia")
- **Security Report**: `docs/security-report.md`

---

*Documento gerado via análise de grafo de conhecimento (graphify) + inspeção de código. Para atualizar: `graphify update .`*