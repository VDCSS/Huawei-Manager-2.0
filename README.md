# HUAWEI MANAGER 2.0

> Interface gráfica corporativa para administração de equipamentos Huawei via SSH/CLI.
> Suporta multi-VNF, topologia SDN interativa, catálogo de 144 serviços, controle RBAC,
> auditoria em cadeia de hashes e múltiplos backends de segredos.

---

## Funcionalidades

### SSH / CLI
- Sessão segura via **Netmiko** (paramiko) com autenticação por chave ED25519 ou senha
- Execução de comandos `show` e `configure` com timeout configurável e retry automático
- Editor de comandos com 14 templates pré-definidos por tipo de dispositivo
- Streaming de output em tempo real com cancelamento do processo ativo

### Catálogo de Serviços (144 comandos)
| Tipo | Qty | Exemplos |
|------|-----|----------|
| **ROUTER** | 78 | BGP, OSPF, IS-IS, MPLS, VRF, QoS, ACL, NAT |
| **SWITCH** | 41 | VLAN, STP, LACP, MAC, LLDP, PoE, port-security |
| **FIREWALL** | 30 | security-policy, IPSec, IKE, IPS, HRP |
| **LOAD-BALANCER** | 11 | virtual-server, health checks |
| **WAN-ACCEL** | 12 | otimização, compressão, fluxos |
| **AP** | 13 | wireless, clientes, rádio, SSIDs |

Execução em dois modos: **mock** (lab/simulação) ou **cli** (Netmiko real).

### Topologia SDN (Canvas Qt)
- Canvas **QGraphicsView/QGraphicsScene** com barra SDN roxa e grid de 4 colunas
- Nós coloridos por tipo de VNF, seleção clicável como alvo SSH
- Tooltip nativo Qt, menu de contexto (right-click) para editar/excluir VNF
- Probe TCP real ou simulação de status; refresh automático a cada 30 s (QTimer)

### Segurança & Auditoria
- **Vault de secrets** com 5 backends: `env`, `crypto` (AES-256-GCM local), `sops` (age), HashiCorp Vault, AWS Secrets Manager
- **Rotação de chave SSH** ED25519 gerada via `cryptography`, push automático ao dispositivo via CLI Netmiko
- **RBAC** com 3 papéis (`user < tecnico < admin`), timeout de inatividade configurável (padrão 300 s)
- **Log de auditoria** em **JSON Lines** (`huawei_audit_structured.jsonl`) com:
  - HMAC-SHA256 por entrada
  - Hash chain SHA-256 encadeado (próxima entrada aponta para o hash da anterior)
  - Campos: `timestamp`, `op`, `user`, `host`, `status`, `duration_ms`, `session_id`, `category`

### Controlador SDN (headless, sem Qt)
- `ControllerCore` — estado centralizado de dispositivos em RAM + dump periódico JSON
- `EventQueue` — fila de prioridade thread-safe com pub/sub (`PriorityQueue`)
- `Southbound` — abstração SSH com retry e sanitização de credenciais em logs
- `Normalizer` — parsers de output CLI → dataclasses (`RouteEntry`, `ArpEntry`, `VlanEntry`, `InterfaceEntry`)
- `Authz` — decorador `@require_role` e `SessionTracker`

### Watcher / Agentes de Scan
- Scans periódicos em `ThreadPoolExecutor` separado (sem bloquear a UI)
- Timeout individual por scan (15 s) e total (30 s)
- Isolamento de falhas: 1 scan falho não afeta os demais

---

## Arquitetura

```
src/huawei_manager/
├── app.py              # QMainWindow — sidebar, header, timers, threading
├── pages.py            # Mixin PageBuilder — 8 abas da interface
├── handlers.py         # Mixin EventHandlers — SSH, auth, VNFs, serviços
├── widgets.py          # ActionButton, NeonButton, helpers de widget
├── _app.py             # QSS dark/light themes, apply_theme(), get_qt_app()
├── _config.py          # Lazy init: logging, secrets backend, audit logger
├── constants.py        # Cores, fontes (Inter/Consolas), filtros CLI
│
├── session.py          # NetmikoSession — connect, run_cli_rpc, edit_config
├── vault.py            # SecretsBackend + 5 backends + rotate_ssh_key()
├── audit_log.py        # AuditLogger (JSON Lines + HMAC + hash chain)
├── topology.py         # TopologyCanvas (QGraphicsView) + VNFNodeRect
├── vnf_models.py       # VNF dataclass, probe_vnfs, load/save inventory
│
├── services.py         # Execução de serviços por tipo de VNF
├── services_data.py    # 144 ServiceDef — definições do catálogo
├── utils.py            # ANSI cleanup, sanitize
│
├── sdn_controller/
│   ├── core.py         # ControllerCore + DeviceState
│   ├── event_queue.py  # EventQueue (PriorityQueue + pub/sub)
│   ├── southbound.py   # SouthboundProtocol + SSHSouthbound
│   ├── normalizer.py   # Parsers CLI → dataclasses
│   ├── authz.py        # Role enum, @require_role, SessionTracker
│   ├── validator.py    # Validação de parâmetros de comandos
│   ├── dryrun.py       # Modo dry-run (simula sem enviar ao dispositivo)
│   ├── security_events.py  # Eventos de segurança (AN triggers)
│   └── drivers/        # BaseDriver + Router, Switch, Firewall
│
└── agents/
    ├── runner.py       # Orquestrador de scans com timeout e isolamento
    ├── watcher.py      # Watcher Qt (QTimer + ThreadPoolExecutor)
    └── scans/          # Módulos de scan individuais

agents/                 # Scans externos (raiz do projeto)
tests/                  # 139 testes pytest (headless, QT_QPA_PLATFORM=offscreen)
.github/workflows/      # CI: ruff → pytest → pyright
Makefile                # install, run, test, lint, typecheck, coverage
```

---

## Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| **Linguagem** | Python 3.12+ |
| **Interface** | PySide6 6.8+ (Qt for Python) |
| **SSH / CLI** | Netmiko 4+ (paramiko) |
| **Secrets** | python-dotenv / cryptography / hvac / boto3 / sops |
| **Criptografia** | cryptography — ED25519, AES-256-GCM |
| **Auditoria** | JSON Lines + HMAC-SHA256 + hash chain |
| **Topologia** | QGraphicsView / QGraphicsScene |
| **Testes** | pytest + pytest-cov + pytest-qt |
| **Lint** | ruff (E, F, W, I, UP) |
| **Tipos** | pyright (strict warnings, 0 errors) |
| **CI** | GitHub Actions (ubuntu-latest) |
| **Build** | setuptools PEP 517 |

---

## Instalação

```bash
git clone https://github.com/VDCSS/Huawei-Manager-2.0.git
cd Huawei-Manager-2.0
cp .env.example .env
# Edite .env com as credenciais do seu ambiente
make install
```

`make install` faz tudo:
1. Cria `.venv` e instala o pacote com `pip install -e ".[dev]"`
2. Instala o ícone em `~/.local/share/icons/`
3. Instala o `.desktop` entry no menu de aplicações
4. Instala o comando `huawei` com tab complete

---

## Configuração

Edite `.env`:

```ini
ROUTER_HOST=192.168.1.1
ROUTER_PORT=22
ROUTER_USERNAME=admin
ROUTER_PASSWORD=
ROUTER_SSH_KEY=~/.ssh/huawei_ed25519
ROUTER_HOSTKEY_VERIFY=false

# Secrets backend: env | crypto | sops | vault | aws
SECRETS_BACKEND=env
# Chave AES-256-GCM (obrigatória se SECRETS_BACKEND=crypto)
# SECRETS_KEY=sua-chave-32-bytes
```

---

## Execução

> ⚠ A interface requer servidor gráfico (DISPLAY). Não funciona em headless puro.

```bash
make run             # via Makefile
huawei manager       # via comando instalado (tab complete)
```

---

## Comandos de Desenvolvimento

```bash
make test            # pytest tests/ -q
make lint            # ruff check src/huawei_manager/
make typecheck       # pyright
make coverage        # pytest --cov + relatório de cobertura
make ci              # lint + test + typecheck (pipeline completa)

# Secrets
make encrypt-env     # Criptografa .env → .env.enc
make decrypt-env     # Descriptografa .env.enc → .env

# Manutenção
make reinstall       # pip install -e . (após git pull)
make uninstall       # Remove atalho, ícone e comando do sistema
make clean           # Remove caches (__pycache__, .pytest_cache, .ruff_cache)
```

---

## Abas da Interface

| Aba | Descrição |
|-----|-----------|
| 🏠 **Dashboard** | Status da conexão, VNFs, últimas operações de auditoria, atalhos |
| 🗺 **Topologia / VNFs** | Canvas SDN interativo, seleção de alvo SSH |
| 📋 **Configuração Atual** | `display current-configuration` com filtros |
| 🌐 **Roteamento** | Tabela de roteamento, BGP, OSPF |
| 📡 **ARP** | Tabela ARP via CLI |
| 💻 **Info do Sistema** | Versão, CPU, memória, interfaces, LLDP |
| ⌨ **Editor de Comandos** | Editor CLI com 14 templates, streaming de output |
| 💾 **Backup** | Backup da running-config para arquivo |
| ⚡ **Serviços** | Catálogo completo de 144 comandos por tipo de VNF |
| 🔧 **Manutenção** | Dev tools, scans de agentes, setup |

Atalhos de teclado: `Ctrl+1..9` navega pelas abas, `Ctrl+Tab` avança, `Ctrl+Shift+Tab` volta.

---

## Modos de Operação

| Modo | Descrição |
|------|-----------|
| **Mock (lab)** | Inventário local + status simulados + output realista sem dispositivo real |
| **CLI real** | Sessão Netmiko SSH ativa, comandos executados no equipamento |
| **Híbrido** | Mock para demonstração + CLI para VNFs disponíveis simultaneamente |

---

## Requisitos

- Python **3.12+**
- Linux com servidor gráfico X11/Wayland (para a GUI)
- Pacotes de sistema (CI): `libxcb-cursor-dev`, `libxkbcommon-x11-dev`
- Acesso SSH à porta 22 do equipamento Huawei (para modo real)

---

## Licença

Proprietário — Uso interno / demonstração.
