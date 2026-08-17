# ADR 006 — Consumo de Eventos SDN + Nomenclatura PNF×VNF

**Status:** Aceito  
**Data:** 2026-08-06  
**Decisor:** Usuário (D1 = Opção A — Integrar)  
**Revisado por:** Athena (arquitetura), Hades (bugs), Momus (plano), Artemis (testes)

---

## Contexto

O `ControllerCore` gera eventos via `EventQueue` (`DEVICE_DISCONNECTED`, `VNF_STATUS_CHANGED`, `DEVICE_CONNECTED`, `CONFIG_CHANGED`), mas o `_poll_queue` na `ThreadingMixin` **drenava e descartava** esses eventos (`drained += 1`, `log.debug`). A topologia nunca refletia mudanças de conectividade em tempo real.

Módulos em `sdn_controller/_dormant/` (~1.143 LOC) existiam sem consumidor: `orchestrator.py`, `policy.py`, `ratelimit.py`, `security_events.py`, `snmp_handler.py`, `topology_manager.py`.

## Decisão

### 1. Consumir eventos mínimos na UI thread

Consumir apenas os eventos que impactam a apresentação visual:

| Evento | Ação |
|--------|------|
| `DEVICE_DISCONNECTED` | `set_device_status(source, "offline")` |
| `DEVICE_CONNECTED` | `set_device_status(source, "online")` |
| `VNF_STATUS_CHANGED` | `set_device_status(source, "online")` |
| `CONFIG_CHANGED` | Log info + refresh dashboard |

Eventos sem mapeamento visual são logados em `debug` e descartados.

### 2. `_EVENT_BATCH = 50` (bounded drain)

Limitar a drenagem por ciclo do QTimer a 50 eventos (`_EVENT_BATCH`). Eventos excedentes permanecem na fila para o próximo ciclo. Isso impede spin infinito sob carga e garante que a UI thread não fique bloqueada.

### 3. Drop contado e logado (nunca silencioso)

Sob `_ui_queue` cheia (backpressure), o drop de evento SDN é **contado e logado** em ambos os lados:
- Evento: `_app_log.warning("SDN event drop (%d total): ...")`
- `_ui_queue`: `_app_log.warning("UI queue overflow — callback descartado")`

`DEVICE_DISCONNECTED` (prioridade 0 no `EventQueue`) é processado **direto no drain** (não via `_dispatch`) para minimizar perda.

### 4. `dump_path` real

`ControllerCore` recebe `dump_path=~/.huawei_manager/sdn_state.json` para persistência periódica de estado.

### 5. `_dormant/` postergado (não integrado)

Os módulos `_dormant/` **não são deletados** e **não são integrados** neste ciclo. `tests/test_security_events.py` continua rodando (sem `@pytest.mark.skip`) como garantia de que os módulos dormentes não apodrecem.

## Nomenclatura

| Termo | Definição |
|-------|-----------|
| **PNF** (Physical Network Function) | Dispositivo físico (router, switch, firewall) |
| **VNF** (Virtual Network Function) | Função virtualizada rodando em PNF |
| **Device** | Qualquer elemento na topologia (PNF ou VNF) |
| **Node** | Elemento visual no canvas `QGraphicsScene` |

## Consequências

### Positivas
- Topologia reflete estado real em tempo real (< 100ms latência via QTimer 50ms)
- Estado persiste entre reinícios (`dump_path`)
- Nenhum evento descartado silenciosamente (audit trail completo)

### Negativos
- `_dormant/` acumula código não utilizado (débito técnico aceito)
- `_EVENT_BATCH` pode causar latência sob carga extrema (>50 eventos/ciclo = 2+ ciclos)

## Referências

- `app_threading.py:17` — `_EVENT_BATCH = 50`
- `app_threading.py:39-60` — `_poll_queue` com bounded drain
- `app_state.py:12-25` — `_on_sdn_event`
- `topology.py:145-152` — `set_device_status`
- `app.py:85` — `dump_path`
- `_dormant/` — módulos postergados
- `tests/test_security_events.py` — teste mantido (R14)
