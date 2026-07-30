# ADR 005: Mixins como Padrão de Composição na GUI

## Status
Aceito (documentação de decisão existente).

## Context

A GUI do Huawei Manager usa 11 mixins via herança múltipla:
- `AppCoreQt` (core + state)
- `PageBuilderQt` (3 sub-mixins: builder, cmd, manutencao, services)
- `EventHandlersQt` (7 sub-mixins: auth, commands, dashboard, fetch, services, ssh, vnfs)

`AppCoreProtocol` (89 linhas) define o contrato type-safe entre mixins,
eliminando ~150 pyright warnings. Os ~150 warnings restantes são de
atributos puramente locais (ex: `_dash_conn_status`, `_cmd_editor`).

## Decision

Manter mixins como padrão de composição para a GUI.

## Razões

### 1. Qt widgets requerem estado compartilhado
Cada handler precisa acessar:
- Widgets da UI (`_dash_conn_status`, `_topo_canvas`, etc.)
- Threading (`_io_executor`, `_ui_queue`)
- Estado de sessão (`_sb`, `_session`, `_target_vnf`)
- Serviços (`_vnf_service`, `_cmd_validator`)

Composição exigiria passar 15+ dependências para cada handler —
mais verboso, mais propenso a erro, menos legível.

### 2. Protocol fornece type safety sem overhead
`AppCoreProtocol` elimina a necessidade de casts ou `# type: ignore`
quando um mixin acessa atributos de outro mixin. É o padrão
recomendado pelo Python para herança múltipla com type checking.

### 3. Mixins são testáveis
Cada mixin pode ser testado individualmente com mocks:
```python
mixin = DashboardMixin()
mixin._sb = MagicMock()
mixin._refresh_dashboard()
```

### 4. Alternativas são piores
| Alternativa | Problema |
|-------------|----------|
| Composição pura | 15+ dependências por handler, verboso |
| Service locator | Hidden dependencies, difícil de testar |
| Event bus global | Acoplamento implícito, debugging difícil |
| God object | Já temos (AppCore), mixins organizam |

## Consequences

### Positivas
- Type safety via Protocol (150 warnings eliminados)
- Testabilidade individual de cada mixin
- Organização clara por responsabilidade
- Padrão Qt idiomático (muitos apps Qt usam mixins)

### Negativas
- ~150 pyright warnings de atributos locais (aceito)
- MRO complexa (3 níveis: AppCore → PageBuilder → Handlers)
- Refactor futuro requer mudar múltiplos arquivos

### Riscos
- **Limite de mixins**: 11 é perto do limite sustentável (~15)
  - Mitigação: novos handlers devem ser sub-mixins de existentes
- **Conflitos de nomes**: podem surgir com novos mixins
  - Mitigação: prefixo `_` em todos os atributos privados

## Notas de Implementação

1. `AppCoreProtocol` deve ser atualizado quando novos atributos
   são adicionados ao AppCore.

2. Atributos puramente locais (ex: `_cmd_editor`) NÃO devem ser
   adicionados ao Protocol — apenas compartilhados.

3. Novos handlers devem herdar de `EventHandlersQt` e usar
   `self: AppCoreProtocol` nos métodos que acessam estado compartilhado.
