# ADR 003: TOFU para Verificação de Host Key SSH

## Status
Aceito.

## Context
Ao conectar via SSH a um dispositivo Huawei pela primeira vez, o cliente SSH
precisa verificar a identidade do servidor através da host key. Em ambiente
de laboratório (GNS3/EVE-NG), as VMs são recriadas frequentemente, trocando
a host key a cada rebuild. A verificação estrita (StrictHostKeyChecking=yes)
quebra o fluxo de lab. Desligar completamente a verificação expõe a
man-in-the-middle (MITM) em produção.

## Decision
Implementar **3 modos de verificação de host key**, configuráveis via
`ROUTER_HOSTKEY_VERIFY` no `.env`:

| Modo | Comportamento | Uso |
|------|--------------|------|
| `tofu` (padrão) | Trust On First Use: aceita na primeira conexão, rejeita se mudar | Lab + desenvolvimento |
| `strict` | Rejeita qualquer host key desconhecida ou alterada | Produção |
| `off` | Aceita qualquer host key sem verificação | Troubleshooting rápido |

### Detalhes Técnicos
- Cache de host keys em `~/.ssh/known_hosts` (formato OpenSSH)
- Modo `tofu`: se host key não está em known_hosts, adiciona; se está e diverge, REJEITA
- Modo `strict`: delega ao paramiko `MissingHostKeyPolicy.RejectPolicy`
- Modo `off`: usa `AutoAddPolicy` (conveniente, mas inseguro — apenas troubleshooting)
- Configuração lida em `_config.py` e passada à sessão SSH

## Consequences
### Positivas
- Balanceamento entre segurança e usabilidade
- TOFU é prática padrão em SSH (equivalente ao `StrictHostKeyChecking=accept-new`)
- Compatível com lab: rebuild de VM = chave nova, TOFU avisa
- Produção seguro com strict: MITM detectado

### Negativas
- TOFU é vulnerável na **primeira** conexão (sem verificação inicial)
- known_hosts pode acumular entradas órfãs (VMs descartadas)
- Modo `off` é risco de segurança consciente (apenas troubleshooting)

### Riscos
- Ataque MITM na primeira conexão com TOFU (mitigação: verificação manual da fingerprint no lab)
- Usuário configurar `off` permanentemente (mitigação: warning em log, recomendação strict em produção)
