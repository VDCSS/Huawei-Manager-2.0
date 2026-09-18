# HUAWEI MANAGER 2.0

> Interface gráfica corporativa para administração de equipamentos Huawei via SSH/CLI.
> Suporta multi-VNF, topologia SDN interativa, catálogo de 144 serviços, controle RBAC,
> auditoria em cadeia de hashes e múltiplos backends de segredos.

---

## Funcionalidades

### SSH / CLI
- Sessão segura via **Netmiko** (paramiko) com autenticação por chave ED25519 ou senha
- Execução de comandos `show` e `configure` com timeout configurável e retry automático
- Editor de comandos com 21 templates pré-definidos por tipo de dispositivo
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
├── app.py              # QMainWindow — app core + mixin inheritance
├── app_threading.py    # ThreadingMixin — dispatch, spawn_io, poll queue
├── _protocols.py       # AppCoreProtocol — type contract for 11 mixins
├── widgets/            # ActionButton, NeonButton, helpers de widget
├── _app.py             # QSS dark/light themes, apply_theme(), get_qt_app()
├── _config.py          # Lazy init: logging, secrets backend, audit logger
├── constants.py        # Cores, famílias de fonte, filtros CLI
├── exceptions.py       # Custom exceptions
│
├── pages/              # PageBuilder — 10 abas da interface
├── handlers/           # EventHandlers — SSH, auth, VNFs, serviços
│
├── session.py          # NetmikoSession — connect, run_cli_rpc, edit_config
├── vault.py            # SecretsBackend + 5 backends + rotate_ssh_key()
├── audit_log.py        # AuditLogger (JSON Lines + HMAC + hash chain)
├── topology.py         # TopologyCanvas (QGraphicsView) + VNFNodeRect
├── vnf_models.py       # VNF dataclass
├── vnf_crypto.py       # Funções de criptografia de VNF
├── vnf_inventory.py    # load/save vnf_inventory.json
│
├── services/           # Catálogo de serviços (144 comandos)
├── sdn_controller/     # ControllerCore, Southbound, Normalizer, Authz, drivers
├── agents/             # Watcher, Runner, scans
│
tests/                  # 1150+ testes pytest (headless)
.github/workflows/      # CI: ruff → pytest → pyright
Makefile                # install, run, test, lint, typecheck, coverage
```

---

## Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| **Linguagem** | Python 3.12+ |
| **Interface** | PySide6 6.10+ (Qt for Python) |
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

## Instalação Rápida

```bash
# Clone
git clone https://github.com/VDCSS/Huawei-Manager-2.0.git
cd Huawei-Manager-2.0

# Instalação completa (dev + fontes + assets)
make install
# ou
bash setup/install.sh install --dev

# Produção (sem ferramentas de dev)
make install-prod
# ou
bash setup/install.sh install --prod
```

### Requisitos

- **Python 3.12+** — o instalador resolve automaticamente: `HM_PYTHON` → `python3` do sistema → alternativos → uv. Sem disponível: `install --bootstrap-python`
- **Linux** com servidor gráfico (X11/Wayland) para a GUI
- **Pacotes de sistema**: `libxcb-cursor-dev`, `libxkbcommon-x11-dev` (Debian/Ubuntu) ou equivalentes
- **Acesso SSH** à porta 22 do equipamento Huawei (modo real)

### O que o instalador faz

1. Cria `.venv/` com Python 3.12+
2. Instala dependências via pip (core + extras `[vault,aws]` + `[dev]` se `--dev`)
3. Baixa fontes Google Fonts em `~/.local/share/fonts/`
4. Instala ícone em `~/.local/share/icons/`
5. Instala `.desktop` em `~/.local/share/applications/`
6. Instala comando `huawei` com tab-completion em `~/.local/bin/`
7. Inicializa banco SQLite (`~/.huawei_manager/inventory.db`) com admin padrão
8. Verifica dependências de sistema (cross-distro: apt/dnf/yum/pacman)
9. Auto-gera `~/.config/huawei-manager/.env` com `AUDIT_HMAC_KEY` no primeiro boot

### Modos e flags

```bash
bash setup/install.sh                       # install completo: dev + fontes (padrão)
bash setup/install.sh install --prod        # produção (apenas runtime)
bash setup/install.sh install --no-fonts    # pula download das fontes
bash setup/install.sh fonts                 # apenas fontes Google Fonts
bash setup/install.sh reset --prod          # limpa .venv/caches/logs e reinstala
bash setup/install.sh check                 # diagnóstico do ambiente
bash setup/install.sh --help                # mostra ajuda

# Sem Python >= 3.12:
bash setup/install.sh install --bootstrap-python   # baixa Python via uv para ~/.local
HM_PYTHON=/caminho/python3.12 bash setup/install.sh install
```

### Comando `huawei`

Após a instalação, o comando `huawei` fica disponível em `~/.local/bin/`:

```bash
huawei manager              # Abre a interface gráfica
huawei check                # Diagnóstico do ambiente
huawei version              # Mostra a versão
huawei help                 # Ajuda completa
```

> **Nota**: Adicione `~/.local/bin` ao PATH se ainda não estiver:
> ```bash
> export PATH="$HOME/.local/bin:$PATH"    # adicione ao ~/.bashrc ou ~/.zshrc
> ```

---

## Configuração

O arquivo `.env` é auto-gerado em `~/.config/huawei-manager/.env` no primeiro boot.
Edite-o para configurar credenciais e backends:

```ini
ROUTER_HOST=192.168.1.1
ROUTER_PORT=22
ROUTER_USERNAME=admin
ROUTER_PASSWORD=
ROUTER_SSH_KEY=~/.ssh/huawei_ed25519
# Verificação de host key: strict | tofu | off
ROUTER_HOSTKEY_VERIFY=strict

# Secrets backend: env | crypto | sops | vault | aws
SECRETS_BACKEND=env

# VNF_ENCRYPT_KEY: auto-gerada no primeiro boot se ausente
# AUDIT_HMAC_KEY: auto-gerada no primeiro boot
```

### Backends de segredos

| Backend | Configuração | Extra |
|---------|-------------|-------|
| `env` (padrão) | Variáveis no `.env` | — |
| `crypto` | `SECRETS_KEY` (32 bytes) | `cryptography` |
| `sops` | SOPS/age configurado | — |
| `vault` | `VAULT_ADDR`, `VAULT_TOKEN` | `hvac` |
| `aws` | `AWS_REGION`, `AWS_SECRET_NAME` | `boto3` |

---

## Execução

> ⚠ A interface requer servidor gráfico (DISPLAY). Não funciona em headless puro.

```bash
make run             # via Makefile
huawei manager       # via comando instalado
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
make reinstall       # pip install -e ".[dev,vault,aws]" (após git pull)
make reinstall-prod  # pip install -e ".[vault,aws]" (produção)
make uninstall       # Remove atalhos, ícone, comando e fontes
make clean           # Remove caches (nunca remove .venv nem logs)
make clean-all       # DESTRUTIVO: clean + .venv + logs
```

---

## Abas da Interface

| Aba | Descrição |
|-----|-----------|
| 🏠 **Dashboard** | Status da conexão, VNFs, últimas operações de auditoria |
| 🗺 **Topologia / VNFs** | Canvas SDN interativo, seleção de alvo SSH |
| 📋 **Configuração Atual** | `display current-configuration` com filtros |
| 🌐 **Roteamento** | Tabela de roteamento, BGP, OSPF |
| 📡 **ARP** | Tabela ARP via CLI |
| 💻 **Info do Sistema** | Versão, CPU, memória, interfaces, LLDP |
| ⌨ **Editor de Comandos** | Editor CLI com 21 templates, streaming de output |
| 💾 **Backup** | Backup da running-config para arquivo |
| ⚡ **Serviços** | Catálogo completo de 144 comandos por tipo de VNF |
| 🔧 **Manutenção** | Dev tools, scans de agentes, setup |

---

## Modos de Operação

| Modo | Descrição |
|------|-----------|
| **Mock (lab)** | Inventário local + status simulados sem dispositivo real |
| **CLI real** | Sessão Netmiko SSH ativa, comandos executados no equipamento |
| **Híbrido** | Mock para demonstração + CLI para VNFs disponíveis |

---

## Licença

Proprietário — Uso interno / demonstração.
