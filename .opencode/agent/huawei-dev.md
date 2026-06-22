You are the **Huawei-Manager Dev Agent**. You have full tool access for development.

## Project
- **App:** Gerenciador SSH/CLI para dispositivos de rede Huawei
- **Stack:** Python 3.12+ (3.14 na prática), Tkinter, Netmiko
- **Class hierarchy:** `HuaweiRouterApp(AppCore, PageBuilder, EventHandlers): pass`
  - `AppCore` (app.py) → init, layout, navegação, ThreadPoolExecutor
  - `PageBuilder` (pages.py) → 8 páginas, sub-builders, service list
  - `EventHandlers` (handlers.py) → SSH, backup, auth, VNFs
- **14 módulos em** `src/huawei_manager/`

## Tooling
- `make lint` → ruff (select E,F,W,I,UP)
- `make typecheck` → pyright
- `make test` → pytest (119 tests)
- `make ci` → lint + test + typecheck
- `make coverage` → pytest com relatório de cobertura
- `make run` → `.venv/bin/huawei-manager`

## Conventions
- Zero comentários no código
- Line-length máximo 120
- Template strings (f-strings) para concatenação
- ThreadPoolExecutor(max_workers=4) para tasks assíncronas
- Sanitizar IP/porta/credenciais em logs (DEBUG só)
- AuditLogger para operações críticas (JSONL estruturado)
- .env com ROUTER_HOST, ROUTER_USERNAME, ROUTER_PASSWORD, ADMIN_PASSWORD, TECNICO_PASSWORD
- 3 níveis de acesso: user / admin / tecnico
- Testes em tests/ com fixtures em conftest.py
