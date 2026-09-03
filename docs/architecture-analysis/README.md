# Índice — Análise Arquitetural Huawei Manager 2.0

> **Diretório:** `docs/architecture-analysis/`  
> **Gerado:** 2026-09-02

---

## Documentos

| Arquivo | Descrição |
|---------|-----------|
| [`analise-logica-funcional.md`](analise-logica-funcional.md) | **Análise lógica completa** — 14 domínios funcionais, mapeamento arquivo→responsabilidade, fluxos de dados, padrões arquiteturais |
| `README.md` | Este arquivo |

---

## Estrutura do Projeto (Resumo)

```
src/huawei_manager/
├── app.py                    # Entry point (HuaweiRouterApp)
├── _config.py                # Bootstrap (logging, audit, secrets)
├── _protocols.py             # AppCoreProtocol (type-safe contracts)
├── constants.py              # Design system (cores, fontes, temas)
├── device_models.py          # Domain models (Device, enums)
├── device_crypto.py          # Fail-closed crypto (Fernet)
├── device_repository.py      # SQLite repository + crypto
├── device_probe.py           # Device discovery
├── migration.py              # JSON → SQLite migration
├── session.py                # NetmikoSession (SSH)
├── audit_log.py              # AuditLogger (HMAC-SHA256 + hash chain)
├── vault.py                  # Vault bridge
├── vault_backends/           # 5 backends (Env, Crypto, Sops, Vault, AWS)
├── app_threading.py          # ThreadingMixin (async UI)
├── app_notify.py             # NotifyMixin (toasts)
├── app_state.py              # AppStateMixin (SDN events → UI)
├── handlers/                 # UI mixins (Devices, SSH, Commands, VNFs)
├── pages/                    # 10 page builders (tabs)
├── widgets/                  # Reusable components
├── services/                 # DeviceService, Catalog (144 services)
└── sdn_controller/
    ├── core.py               # ControllerCore (state + JSON dump)
    ├── event_queue.py        # EventQueue + EventType enum
    ├── bus.py                # IEventBus / IEventConsumer
    ├── southbound.py         # SouthboundProtocol + SSHSouthbound
    ├── session_factory.py    # SSHSessionFactory (pool per-device)
    ├── validator.py          # CommandValidator (allow/deny + audit)
    ├── dryrun.py             # DryRunEngine (diff/apply/rollback)
    ├── polling_manager.py    # Adaptive polling + stability tracking
    └── drivers/              # BaseDriver + RouterDriver
```

---

## Fluxos Principais

1. **Conexão Dispositivo** → UI → SshMixin → SSHSouthbound → NetmikoSession → SSHSessionFactory → DeviceRepository → Vault → ControllerCore → EventQueue → AppStateMixin → UI + AuditLogger
2. **Execução Comando** → UI → CommandsMixin → CommandValidator → DryRunEngine → SSHSouthbound → ControllerCore → EventQueue → AuditLogger
3. **Polling Adaptativo** → PollingManager → SSHSessionFactory → SSHSouthbound → Normalizer → ControllerCore → EventQueue → AppStateMixin → UI

---

## Quality Gates

```bash
make ci  # ruff → pytest → pyright (strict, 0 errors)
```

- **Lint**: ruff (E/F/W/I/UP, line-length=120)
- **Tipos**: pyright strict, `exclude = ["tests/**"]`
- **Testes**: pytest + pytest-qt + pytest-cov, headless (`QT_QPA_PLATFORM=offscreen`)
- **CI**: GitHub Actions ubuntu-latest
- **Graphify**: Auto-updated knowledge graph

---

## Próximos Passos Arquiteturais

- [ ] NETCONF/gNMI — SouthboundProtocol nativo
- [ ] AIOps/ML — Anomaly detection em PollingManager/EventQueue
- [ ] Telemetria YANG-Push — Streaming vs polling
- [ ] Service Mesh — mTLS entre componentes SDN
- [ ] GraphQL API — Integração externa