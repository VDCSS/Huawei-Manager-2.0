# HUAWEI MANAGER

> Interface gráfica corporativa para administração de equipamentos Huawei via SSH/CLI, com suporte a multi-VNF, topologia SDN, catálogo de serviços e modo lab integrado.

---

## Funcionalidades

### Fase 1 — Transporte SSH via Netmiko
- Sessão SSH segura via `netmiko` com autenticação por chave ou senha
- Execução de comandos `show` e `configure` com timeout configurável
- Fallback automático entre chave SSH e senha
- Editor de comandos com templates pré-definidos

### Fase 2 — Catálogo de Serviços Multi-VNF
- Catálogo com +120 comandos organizados por tipo de dispositivo e categoria
- Suporte a ROUTER, SWITCH, FIREWALL, LOAD-BALANCER, WAN-ACCEL, AP
- Execução em 2 modos: **mock** (lab) ou **cli** (Netmiko via SSH)

### Fase 3 — Segurança e Auditoria
- **Vault de secrets** com 4 backends: `.env` (lab), SOPS (age), HashiCorp Vault, AWS Secrets Manager
- **Rotação de chave SSH** ED25519 com push automático ao dispositivo via CLI
- **Log de auditoria** estruturado em JSON Lines com tempo de resposta, status e session-id

### Fase 4 — Topologia SDN / Multi-VNF
- **Canvas PySide6 (QGraphicsView)** com barra SDN no topo + grid 4 colunas, nós coloridos por tipo
- Barra roxa com contador de dispositivos gerenciados + tooltip nativo Qt
- Status online/offline/unknown com simulação ou probe TCP real
- Seleção clicável de VNF como alvo SSH
- Timer Qt a cada 30s para refresh automático de VNFs

### Catálogo de Serviços (144 comandos)
- 78 serviços para **ROUTER**: routing-table, BGP, OSPF, IS-IS, MPLS, VRF, QoS, ACL, NAT, além de templates de config (nat, interface, acl, bgp, ospf, vlan)
- 41 serviços para **SWITCH**: VLAN, STP, LACP, MAC, LLDP, PoE, IGMP snooping, DHCP snooping, port-security
- 30 serviços para **FIREWALL**: security-policy, session-table, IPSec, IKE, IPS, antivírus, URL filter, zonas, HRP
- 11 serviços para **LOAD-BALANCER**: service-group, virtual-server, real-server, health checks
- 12 serviços para **WAN-ACCEL**: otimização, compressão, fluxos
- 13 serviços para **AP**: wireless, clientes, rádio, SSIDs
- Execução em 2 modos: **mock** (lab) ou **cli** (Netmiko via SSH)
- Catálogo definido via factory `_svc()`, 0 boilerplate, 0 duplicação

---

## Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| **Linguagem** | Python 3.12+ |
| **Interface** | PySide6 (Qt for Python) |
| **SSH/CLI** | Netmiko (paramiko) |

| **Secrets** | python-dotenv / hvac / boto3 |
| **Criptografia** | cryptography (ED25519) |
| **Auditoria** | JSON Lines estruturado |
| **Topologia** | Canvas PySide6 (QGraphicsView/QGraphicsScene) |
| **SDN Mock** | JSON local + simulação de status |
| **Tema Visual** | Neon / Cyberpunk dark |

---

## Estrutura do Projeto

```
.
├── src/
│   ├── huawei_manager/            # Pacote Python principal
│   │   ├── app.py                 # Aplicação principal (GUI PySide6)
│   │   ├── pages.py               # Construtor de páginas (8 abas)
│   │   ├── handlers.py            # Eventos SSH, auth, VNFs
│   │   ├── _config.py             # Config (logging, secrets, audit)
│   │   ├── session.py             # Sessão SSH via Netmiko
│   │   ├── constants.py           # Cores, filtros CLI, templates
│   │   ├── widgets.py             # Widget helpers neon
│   │   ├── utils.py               # ANSI cleanup, sanitize
│   │   ├── vault.py               # Abstração de secrets (env/sops/vault/aws)
│   │   ├── audit_log.py           # Logger de auditoria JSON Lines
│   │   ├── topology.py            # Controller SDN + Canvas topologia
│   │   └── services.py            # Catálogo de serviços por tipo VNF
│   └── huawei_manager_gui.py      # Entry point (thin, src/)
├── huawei_manager_gui.py          # Entry point (thin, raiz)
├── tests/                         # Testes automatizados (pytest)
├── requirements/
│   ├── prod.txt                   # Dependências de runtime
│   └── dev.txt                    # Dependências de desenvolvimento
├── Makefile                       # Atalhos: install, run, test, lint, typecheck
├── vnf_inventory.json             # Inventário local de VNFs (modo mock)
├── .env.example                   # Template de credenciais
├── .env                           # Credenciais e configuração (texto plano, lab)
├── secrets.enc.yaml               # Credenciais criptografadas via SOPS (produção)
├── .sops.yaml                     # Regras de criação SOPS com chave age
├── pyproject.toml                 # Build setuptools + entry point `huawei-manager`
├── .github/workflows/ci.yml       # CI (ruff → pytest → pyright)
├── .venv/                         # Virtual environment
└── .gitignore
```

---

## Instalação

```bash
git clone https://github.com/VDCSS/Huawei-Manager-2.0.git
cd Huawei-Manager-2.0
cp .env.example .env
# Edite .env com as credenciais do seu ambiente
make install
```

O comando `make install` faz tudo:
1. Cria ambiente virtual (`.venv`)
2. Instala o pacote com dependências
3. Instala o ícone em `~/.local/share/icons/`
4. Instala o atalho de menu em `~/.local/share/applications/`
5. Instala o comando `huawei` no terminal com tab complete

## Configuração

Edite o `.env`:

```ini
ROUTER_HOST=192.168.1.1
ROUTER_PORT=22
ROUTER_USERNAME=admin
ROUTER_PASSWORD=
ROUTER_SSH_KEY=~/.ssh/huawei_rsa
ROUTER_HOSTKEY_VERIFY=false

# Secrets backend: env | vault | aws | sops
SECRETS_BACKEND=env
```

## Execução

> ⚠ A interface requer PySide6 com servidor gráfico (DISPLAY). Não funciona em CI/terminal headless.

```bash
# No menu de aplicações
# Procure "Huawei Manager" e clique

# No terminal — via Makefile
make run

# No terminal — via comando nativo
huawei manager
```

O comando `huawei manager` tem tab complete: digite `huawei` + TAB + Enter.

## Atualização

```bash
git pull
make reinstall
```

## Desinstalação

```bash
make uninstall          # remove atalho, ícone e comando do sistema
rm -rf .venv            # remove ambiente virtual (opcional)
```

---

## Uso

### Abas do Menu

| Aba | Descrição |
|-----|-----------|
| **🏠 Dashboard** | Resumo: conexão, VNFs, últimas operações, atalhos |
| **🗺 Topologia / VNFs** | Canvas SDN com VNFs clicáveis, seleção de alvo SSH |
| **📋 Configuração Atual** | `display current-configuration` com filtros de comando |
| **🌐 Roteamento** | Tabela de roteamento, BGP, OSPF |
| **📡 Tabela ARP** | Tabela ARP via comando CLI |
| **💻 Info do Sistema** | Versão, CPU, memória, interfaces, LLDP |
| **⌨ Editor de Comandos** | Editor de comandos CLI com templates |
| **💾 Backup** | Backup da running-config para arquivo TXT |
| **⚡ Serviços** | Catálogo completo (+120 comandos) por tipo de VNF |

### Topologia / VNFs
- Abra a aba **🗺 Topologia / VNFs**
- Barra SDN roxa no topo com contador de dispositivos + grid 4 colunas
- Tooltip flutuante com detalhes do VNF ao passar o mouse (toggle administrador)
- Menu de contexto (botão direito): editar ou excluir VNF
- Clique em um VNF para selecionar como alvo SSH
- Botão **"🔌 Conectar ao VNF selecionado"** conecta a sessão ao host/porta do VNF
- Botão **"✖ Voltar ao padrão"** retorna ao dispositivo do `.env`

### Catálogo de Serviços
- Na aba **⚡ Serviços**, selecione um VNF na topologia primeiro
- Filtre por categoria (BGP, OSPF, VLAN, policy, etc.)
- Escolha o modo: **mock** (dados simulados, ideal para lab) ou **cli** (CLI via Netmiko)
- Clique **"▶ Executar"** no serviço desejado

---

## Modos de Operação

### Modo Lab / Mock (padrão)
- Inventário local (`vnf_inventory.json`)
- Status simulados com variação automática
- 144 serviços executáveis com output realista simulado

### Modo Real (SSH direto)
- Conecte a um VNF real via SSH/CLI (se houver dispositivo acessível)
- Execute serviços no modo `cli` via Netmiko

### Modo Híbrido
- Conecte a um VNF real via SSH/CLI (se houver dispositivo acessível)
- Execute serviços no modo `cli` via Netmiko
- Use mock para demonstração quando não houver dispositivo

---

## Requisitos

- Python 3.12+
- Acesso SSH ao equipamento Huawei (SSH/CLI, porta 22)
- Pacotes: `python-dotenv`, `netmiko`, `cryptography`, `pyyaml`

---

## Licença

Proprietário — Uso interno / demonstração.
