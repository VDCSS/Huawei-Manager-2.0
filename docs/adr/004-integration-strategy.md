# ADR 004: Estratégia de Integração do Controlador SDN

## Status

Aceito

## Context

O Huawei Manager existente utiliza um padrão de **herança múltipla de mixins** para compor a classe final da aplicação:

```python
class HuaweiRouterAppQt(AppCoreQt, PageBuilderQt, EventHandlersQt):
    pass
```

O novo módulo `sdn_controller/` precisa ser integrado a esta arquitetura. As opções consideradas foram:

1. **Novo mixin** — criar `SdnControllerMixin` e adicioná-lo à MRO
2. **Objeto interno** — instanciar `ControllerCore` como atributo de `AppCoreQt`
3. **Singleton global** — acessar o controller via import direto de módulo

Além disso, o plano prevê criação de `sdn_controller/topology.py` para o Topology Manager (LLDP discovery), que colide com o nome do módulo `topology.py` existente (472 linhas, canvas PySide6).

## Decision

### 1. `sdn_controller/` como objeto interno (não mixin)

O controlador SDN será instanciado como atributo dentro de `AppCoreQt`:

```python
# Em app.py (AppCore.__init__)
from huawei_manager.sdn_controller.core import ControllerCore

self._controller = ControllerCore()
```

**Razões:**
- **MRO já complexa** — `HuaweiRouterAppQt(AppCoreQt, PageBuilderQt, EventHandlersQt)` tem 3 níveis de mixin. Adicionar um quarto aumenta risco de conflito de nomes e dificulta rastreamento de chamadas.
- **Acoplamento frouxo** — O controller é um serviço independente, não um conjunto de capacidades da GUI. Como objeto interno, pode ser passado como dependência explícita.
- **Testabilidade** — Mockar `self._controller` em testes é trivial com `unittest.mock.patch.object`.
- **Isolamento de falhas** — Se o controller falha na inicialização, a GUI ainda pode mostrar estado de erro, sem crash total.

### 2. Renomear `sdn_controller/topology.py` para `sdn_controller/lldp_discovery.py`

O módulo de descoberta de topologia via LLDP (parse de `display lldp neighbor`) será nomeado `lldp_discovery.py` dentro do pacote `sdn_controller/`, **não** `topology.py`.

**Razões:**
- O módulo existente `topology.py` (src/huawei_manager/topology.py) gerencia o canvas PySide6 e o inventário de VNFs — responsabilidade completamente diferente
- Dois módulos com mesmo nome em pacotes diferentes (`huawei_manager.topology` e `huawei_manager.sdn_controller.topology`) causam confusão em imports e debug
- `lldp_discovery.py` descreve exatamente o que o módulo faz

### 3. Coexistência via import explícito

O controller será acessível de duas formas:

```python
# De dentro da GUI (app.py, pages.py, handlers.py):
self._controller.get_devices()
self._controller.deploy_intent(...)

# De dentro do pacote sdn_controller/ (import circular evitado):
from huawei_manager.sdn_controller import get_controller
```

> ⚠ O padrão de acesso global (`get_controller()`) é usado **apenas dentro do próprio pacote sdn_controller/** para evitar fios de import circular. De fora (GUI), o acesso é sempre via `self._controller`.

## Consequences

### Positivas
- Zero risco de colisão de nomes na MRO
- Controller substituível em testes (basta instanciar mock no lugar de `ControllerCore`)
- Inicialização lazy: controller só é criado quando a GUI está pronta
- Nomes de módulo auto-documentados (`lldp_discovery.py` diz o que faz)

### Negativas
- A GUI precisa passar `self._controller` para handlers e pages (acoplamento por parâmetro em vez de herança)
- Handler de eventos (`EventHandlersQt`) não herda do controller — precisa recebê-lo como dependência
- Refatoração necessária em `app.py.__init__()` para instanciar e expor o controller

### Riscos
- **Import circular** se `sdn_controller/` importar da GUI — mitigado pela regra: `sdn_controller/` nunca importa de `app.py`/`pages.py`/`handlers.py`
- **Controller singleton sem recovery** se `ControllerCore` falhar — mitigado por periodic JSON dump (T28.5)

## Notas de Implementação

1. O diretório `src/huawei_manager/sdn_controller/` conterá:
   - `__init__.py` — exporta símbolos públicos
   - `core.py` — `ControllerCore` (singleton de estado)
   - `southbound.py` — `SSHSouthbound` (wrapper Netmiko)
   - `lldp_discovery.py` — Topology Manager LLDP
   - `drivers/` — Router/Switch/Firewall drivers
   - `normalizer.py` — Output CLI parser
   - `orchestrator.py` — Intent→CLI
   - `policy.py` — Policy Engine
   - `event_queue.py` — Event Queue
   - `authz.py` — RBAC decorator
   - `ratelimit.py` — Token bucket
   - `nfv.py` — NFV-lite lifecycle
   - `dryrun.py` — Dry-run engine
   - `baseline.py` — Baseline/drift
   - `validator.py` — Command allow/deny list

2. A GUI consome o controller via `self._controller`, nunca importando diretamente os módulos internos de `sdn_controller/`.

3. O arquivo `topology.py` existente permanece inalterado — suas funções de canvas e inventário VNF são complementares ao Topology Manager (LLDP discovery).
