# ADR 001: SSH/CLI como Único Protocolo Southbound

## Status
Aceito.

## Context
Os dispositivos Huawei alvo (CE6800, S5700, USG6000) não suportam NETCONF/YANG,
OpenFlow, gRPC/gNMI ou RESTCONF. A única interface de gerenciamento disponível
em todos os modelos é a linha de comando via SSH (VRP). Controladores SDN de
terceiros (ONOS, OpenDaylight, Ryu) também exigiriam pelo menos NETCONF ou
OpenFlow, que não estão disponíveis.

## Decision
Utilizar **exclusivamente SSH/CLI via Netmiko** como protocolo southbound.
Toda comunicação com dispositivos gerenciados será através de:
- Sessão SSH (paramiko) encapsulada pelo Netmiko
- Comandos de texto plano (`display`, `configure terminal`, etc.)
- Parsing de output textual (regex, não structured data)

## Consequences
### Positivas
- Funciona em qualquer Huawei VRP (CE, S, AR, USG) sem dependência de versão
- Código mais simples, sem protobuf/gRPC/YANG toolchain
- Testável offline via MockSshDevice com outputs pré-gravados
- Segurança nativa: SSH já cifra o canal, sem camada adicional de criptografia

### Negativas
- Sem structured data nativo (tudo é texto) — parsing frágil
- Sem transações ou rollback automático (depende de dry-run humano)
- Performance: cada comando é uma requisição/response textual (sem pipeline)
- Escalabilidade limitada: N conexões SSH paralelas = N threads
- Múltiplas sessões simultâneas para operações paralelas

### Riscos
- Mudança de output entre versões VRP pode quebrar parsers (mitigação: testes de integração com fixtures)
- Latência alta em topologias grandes (mitigação: parallel execution com pool de threads)
