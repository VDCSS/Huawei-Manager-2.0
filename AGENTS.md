# Huawei Manager — Memory (v1.1.0 LTS)

## Projeto
Aplicação Tkinter para gerenciamento SSH de equipamentos Huawei via Netmiko.
**Versão LTS estável** — 25/25 testes, entry point funcional, sem NETCONF.

## Pilares (Fases)
1. **Transporte** — Netmiko (SSH/CLI), sem ncclient/NETCONF
2. **Catálogo** — Serviços multi-VNF com execução CLI (show + config)
3. **Segurança** — Secrets vault, rotação SSH, auditoria JSON
4. **Topologia** — Canvas SDN com cadastro manual de VNFs

## Estrutura
```
huawei_manager/               ← Pacote Python
├── __init__.py               ← v1.0.4 → v1.1.0 (LTS)
├── app.py                    ← HuaweiRouterApp (UI principal)
├── session.py                ← NetmikoSession (SSH via Netmiko)
├── constants.py              ← Cores, VIEW_CATEGORIES, CONFIG_CATEGORIES, templates
├── widgets.py                ← Widget helpers neon
├── utils.py                  ← ANSI cleanup, sanitize
├── vault.py                  ← Secrets backend + rotation ED25519
├── audit_log.py              ← Log estruturado .jsonl
├── topology.py               ← VNF dataclass, inventário, TopologyCanvas
└── services.py               ← ServiceDef c/ config_mode, 100+ serviços

huawei_netmiko_gui.py         ← Entry point (importa huawei_manager:main)
.env                          ← Credenciais padrão (lab, texto plano)
secrets.enc.yaml              ← Criptografado via SOPS (age) — produção
pyproject.toml                ← Build setuptools + entry point `huawei-manager`
.sops.yaml                    ← Regra de criação SOPS com chave age pública
sessions/                     ← Session logs Netmiko (criado automaticamente)
```

## SOPS Setup (apenas na primeira vez)
1. `age-keygen -o ~/.config/sops/age/keys.txt`
2. Criar `.sops.yaml` apontando para a public key
3. `sops --encrypt secrets.yaml > secrets.enc.yaml`
4. Deletar `secrets.yaml` e setar `SECRETS_BACKEND=sops`

Chave pública: `age1tr3ktrx3rs2x26a6w2nf0xx48djywthg7eespmdhtkxefmrn0qlsw2eksa`
Chave privada: `/home/victordcss/.config/sops/age/keys.txt`

## Decisões-chave
| Decisão | Escolha |
|---|---|
| Transporte SSH | Netmiko (único) |
| Modos de operação | mock / cli (Netmiko) |
| Admin interno | 🔒/🔓 na Topologia, senha mestra (`.env` ou SOPS) |
| Canvas começa | Vazio (cadastro manual) |
| Credenciais VNF | Por dispositivo no `vnf_inventory.json` |
| Mousewheel | Sem `bind_all` global, scroll por `bind`/`unbind` no `<Enter>`/`<Leave>` |
| Backend de secrets | env / vault / aws / sops (selecionável via `SECRETS_BACKEND`) |
| hostkey_verify | `True` por padrão (`ROUTER_HOSTKEY_VERIFY=false` desliga) |
| Session log | Gravado em `sessions/<host>_<port>_<ts>.log` |
| Conexão SSH | Apenas por senha (chave comentada no `.env`) |
| ED25519 vs RSA | Rotação SSH gera ED25519 + comandos compatíveis |
| `ssh_strict` | Sempre explícito (`False` quando `ROUTER_HOSTKEY_VERIFY=false`) |
| Aba Config | Somente leitura — browser de show commands |
| Aba Serviços | Show + Config commands com `config_mode` |
| Aba Editor | Split layout (listbox + editor), templates variados |

## Estado Atual (v1.1.0 LTS)

### Infraestrutura
- [x] Documentação alinhada com Netmiko
- [x] pyproject.toml com build e entry point funcionais
- [x] requirements.txt sincronizado (secundário)
- [x] Runtime artifacts (.log, .jsonl) no .gitignore
- [x] Criptografia via SOPS (age v1.2.1 + sops v3.9.4)
- [x] 25/25 testes passando

### UI
- [x] Fontes maiores (sidebar, output)
- [x] Título limpo: "HUAWEI MANAGER"
- [x] Sidebar reordenada: "Topologia / VNFs" em primeiro
- [x] Sidebar renomeada: "Editor RPC/XML" → "Editor"
- [x] Admin login + tooltip seletivo + menu contexto
- [x] Estilização com cards (`BG_INPUT`, `highlightthickness=1`)

### Abas
- [x] **Topologia**: Canvas vazio, toolbar reformulada, cadastro manual
- [x] **Configuração**: 2 cards — "Configuração Atual" (filtro + get-config) + "Comandos de Visualização" (categorias Rede/Protocolos/Diagnóstico)
- [x] **Roteamento**: display ip routing-table com filtros
- [x] **ARP**: display arp
- [x] **Info do Sistema**: display version / device / license / cpu / mem
- [x] **Editor**: Split layout (listbox templates 220px + editor), templates expandidos (display device, license, ping, tracert, sysname, commit, interface...)
- [x] **Backup**: export current-configuration para arquivo
- [x] **Serviços**: 100+ serviços, c/ badge CONFIG, modo mock/cli
- [x] **Segurança**: secrets backend, rotação SSH, auditoria

### Serviços de Configuração (20 novos)
- [x] NAT: outbound, inbound, server, static, address-group
- [x] Interface: GigabitEthernet, ip address, description, shutdown
- [x] ACL: number, rule permit/deny
- [x] BGP: bgp, router-id, peer, network
- [x] OSPF: ospf, area, network
- [x] VLAN: vlan batch, port link-type, port default vlan

### Session / SSH
- [x] `clean_output()` aplicado a toda saída CLI via `session._cmd()`
- [x] `run_cli_timing()` com `send_command_timing` (system-view)
- [x] Checkbox "system-view" no editor
- [x] `ssh_strict` explícito (sempre setado, respeitando `.env`)
- [x] Conexão SSH apenas por senha (sem chave ativa)
- [x] `rotate_ssh_key()` só persiste chave se CLI push teve sucesso
- [x] `EnvBackend.put()` trata linhas comentadas (não duplica)

### Segurança / Vault
- [x] Hardening de sessão (hostkey, session_log, rate limit)
- [x] Admin rate limit: 3 tentativas → lockout 30s
- [x] vault.py: ED25519 corrigido (era RSA)
- [x] `EnvBackend.put()` substitui linhas comentadas em vez de duplicar
- [x] Log redundante removido (só `huawei_audit_structured.jsonl`)
- [x] Dead code removido (imports, run_cmd(), TopologyPoller, etc.)

### Pendente
- [ ] Testes de connect/disconnect/edit_config

## Atenção
- `NetmikoSession` tem `override_*` para host/port/user/pass/ssh_key
- `_show_device_dialog(VNF?)` serve tanto cadastro (None) quanto edição
- Tooltip mostra info sensível só com `admin=True`
- `_init_topology_backend` simplificado (sem auto-load nem poller)
- `requirements.txt` é secundário; `pyproject.toml` é a fonte primária de deps
- `huawei_manager_audit.log` removido — só `huawei_audit_structured.jsonl` é gerado
- `VIEW_CATEGORIES` em `constants.py` alimenta o browser de show commands na Config
- `CONFIG_CATEGORIES` em `constants.py` é template para novos serviços de config
- Serviços com `config_mode=True` executam via `send_config_set()` com system-view automático
- `CMD_TEMPLATES` expandido alimenta a listbox do Editor
- Ao adicionar novo serviço de config: criar `ServiceDef(config_mode=True)`, adicionar categoria em `VNF_CATEGORIES`
