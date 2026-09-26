# Huawei Manager 2.0 — Diagnóstico e Correções

**Repositório:** `/home/aluno20/Huawei-Manager-2.0`
**Data:** 2026-09-25 · **Branch:** `main` · **Base:** `5fd053a`
**Método:** análise estática (AST/`ruff`/`pyright`) + execução real do app (PySide6 offscreen) + leitura de código.
**Nenhum arquivo do repositório foi modificado durante esta análise.** Working tree limpo (apenas `.venv/` untracked).

**Estrutura:** §1-10 = frontend, styling, texto e ambiente (Parte 1) · §11-12 = **backend**: SSH, sessão, concorrência (Parte 2) · §13-16 = **frontend**: Qt, ciclo de vida, widgets (Parte 3) · **§19-24 = stress tests, fuzz, concorrência e escala (Parte 4)** · §17-18 = ordem de aplicação e verificação consolidadas.
**Ação mais urgente: §11.1 — bypass de RBAC por separador de comando (o papel `user` apaga a configuração do equipamento sem prompt). O vetor não é só `\n`: `;` também encadeia comandos no VRP.**

---

## 1. Resumo executivo

| Categoria | Achados | Quebram o app? |
|---|---|---|
| **Bugs de segurança (P0-S)** | 1 | **Sim — escalação de privilégio** |
| **Bugs de runtime (P0)** | 10 | **Sim** |
| **Bugs de conexão/SSH (P1-B)** | 7 | Parcial |
| **Bugs de correção (P1)** | 22 | Parcial |
| **Consistência visual (P2)** | 21 | Não |
| **Texto / i18n (P3)** | 40+ | Não |
| **Ambiente / DevX (P4)** | 3 | Não |
| **Dívida de lint** | 76 | Não |
| **🔎 Erros no próprio relatório (corrigidos)** | 4 | — |

### 🔴 P0-S — Escalação de privilégio (backend, achado mais grave)

**Bypass do RBAC via separador de comando.** O `user` — o papel de menor privilégio — consegue executar `reset saved-configuration` no equipamento, **sem diálogo de confirmação e sem tocar na deny-list**.

Cadeia completa verificada empiricamente (seção 11.1):
`validator.py:98-101` retorna no allow-list → `commands.py:42` só pede confirmação se `bypass_2fa` (que é `False`) → `app.py:84` não injeta validator no transporte → `southbound.py:203` `if self._validator is not None` é falso → `commands.py:98` envia o buffer cru.

**Vetor real (corrigido na Parte 4):** não é só `\n`. O VRP aceita **`;`**, então o payload pode ser uma **única linha**:
```
display version;system-view;reset saved-configuration
```
que passa por qualquer filtro que só bloqueie newlines. A correção definitiva (dividir em comandos lógicos + negar antes de permitir) está em §11.1.

### 🔴 Os 10 bugs P0 que quebram o app

| # | Bug | Onde | Efeito |
|---|---|---|---|
| 1 | **Bypass de RBAC por comando multi-linha** | `validator.py:98-101` | `user` apaga config do device sem prompt |
| 2 | **`closeEvent` sombreado** | `app.py:61` | Sessão SSH nunca desconectada; processo pendurado ao fechar. **Causa do "não atualiza"** |
| 3 | **Enter/Shift+Enter mortos no editor** | `pages/cmd.py:143` | Filtro de evento sem pai é coletado pelo GC; comandos nunca executam pelo teclado |
| 4 | **`_rebuild_ui` deixa refs obsoletas** | `app.py:592` | `RuntimeError` ao trocar de página; resultado de comando some silenciosamente |
| 5 | **`_event_drop_count` nunca inicializado** | `app_threading.py:30` | `AttributeError` no timer a cada 50ms sob carga; pipeline SDN trava |
| 6 | **10× `except RuntimeError` mortos** | `handlers/*.py` | `SdnError` não é `RuntimeError`; erros nuncatreatmentados, painel fica "Carregando…" |
| 7 | **Ctrl+K é no-op** | `app_shortcuts.py:148` | Stub `pass` sombreia o método real no MRO |
| 8 | **Escape de emoji quebrado** | `topology.py:358` | Botão "Excluir" não renderiza 🗑 |
| 9 | **String sem `f`** | `auth_overlay.py:98` | Qt descarta o bloco QSS inteiro |
| 10 | **Devices fora da tela inacessíveis** | `topology.py:110-111` | Scrollbars `AlwaysOff` + cena maior que o viewport; 16 de 40 devices inalcançáveis |

### Estado dos gates do CI (todos verdes)

| Gate | Resultado |
|---|---|
| `ruff check src/huawei_manager/` | ✅ passa |
| `pytest` | ✅ 1075 passed, 1 skipped |
| `pytest --cov-fail-under=60` | ✅ 77,01% |
| `pyright` | ✅ 0 errors (1791 warnings) |

> **Os gates estão verdes apesar de 10 bugs P0.** Motivo: os testes usam *fakes* com **MRO e cycle-of-life diferentes da classe real**, então exercitam caminhos que nunca executam em produção. Detalhado em 4.1 e 12.6.

---

## 2. Como reproduzir

```bash
cd /home/aluno20/Huawei-Manager-2.0
QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
import sys; sys.path.insert(0,'src')
from huawei_manager.app import HuaweiRouterApp
from huawei_manager.app_notify import NotifyMixin
print('closeEvent resolve para:', HuaweiRouterApp.closeEvent.__qualname__)
print('é o do NotifyMixin?     ', HuaweiRouterApp.closeEvent is NotifyMixin.closeEvent)
"
# Saída: QWidget.closeEvent / False   <-- BUG
```

---

## 3. P0 — Bugs de runtime

### 3.1 `NotifyMixin.closeEvent` sombreado (CAUSA DO APP NÃO ATUALIZAR)

**Arquivo:** `src/huawei_manager/app.py:61`
**Classe real:** `AppCore(QMainWindow, ThreadingMixin, NotifyMixin)`

O MRO de `HuaweiRouterApp` é:

```
HuaweiRouterApp → AppStateMixin → ShortcutsMixin → AppCore
               → QMainWindow → QThread → QWidget   ← define closeEvent
               → ThreadingMixin → NotifyMixin      ← JAMAIS ALCANÇADO
```

`QWidget` (C++) define `closeEvent` e aparece **antes** de `NotifyMixin` no MRO. Portanto `HuaweiRouterApp.closeEvent` resolve para `QWidget.closeEvent` — um no-op — e **todo o corpo de `_on_close()` é ignorado**.

**O que deixa de acontecer ao fechar a janela** (`app_notify.py:16-32`):

| Ação | Status |
|---|---|
| `self._shutdown = True` | ❌ nunca executado |
| Parar os 6 `QTimer` | ❌ nunca executado |
| `self._session_factory.dispose()` | ❌ **pool de sessões SSH vazado** |
| `self._watcher.shutdown(wait=False)` | ❌ nunca executado |
| `self._sb.disconnect()` | ❌ **sessão SSH fica aberta** |
| `self._cleanup_executors()` | ⚠️ só via `atexit` (`app.py:153`) |

**Verificado empiricamente:** após `w.close()`, `w._shutdown` continua `False`.

**Consequência prática (o sintoma que você observou):**
1. Você fecha a janela → `closeEvent` é no-op → `_sb.disconnect()` não roda.
2. `atexit` dispara `_cleanup_executors()` com `shutdown(wait=False, cancel_futures=True)`.
3. `wait=False` **não interrompe tarefas em execução** — só cancela as pendentes.
4. O `concurrent.futures.thread._python_exit` faz `t.join()` em todas as threads do pool → **o processo fica pendurado** até a última operação SSH/CLI terminar.
5. Você roda `make run` de novo → **abre uma segunda instância** por cima da anterior. Não há trava de instância única (sem `QLocalServer`/lockfile), então as duas janelas coexistem e a que está em cima é a velha.

**Medição real** (tarefa em voo de N segundos):

| Tarefa em voo | `close()` | `app.exec()` | Processo total |
|---|---|---|---|
| 2s | 0,00s | 0,89s | **3,8s** |
| 8s | 0,00s | 0,91s | **9,8s** |

#### Correção

Reordenar as bases para que `NotifyMixin` venha antes de `QMainWindow`:

```diff
--- a/src/huawei_manager/app.py
+++ b/src/huawei_manager/app.py
@@ -61,1 +61,1 @@
-class AppCore(QMainWindow, ThreadingMixin, NotifyMixin):
+class AppCore(NotifyMixin, QMainWindow, ThreadingMixin):
     """Mixin principal Qt — inicializa janela, layout, navegação e helpers de threading."""
```

Validado:

```
ATUAL  AppCore(QMainWindow, ThreadingMixin, NotifyMixin):  -> QWidget.closeEvent      ✗
NOVO  AppCore(NotifyMixin, QMainWindow, ThreadingMixin):  -> NotifyMixin.closeEvent  ✓
```

**Workaround imediato (enquanto não aplicar):**
```bash
pkill -f huawei-manager && make run
```

---

### 3.2 `topology.py:358` — escape de emoji quebrado

```python
357:  edit_action   = menu.addAction("\u270f\ufe0f  Editar Dispositivo")   # ✅
358:  delete_action = menu.addAction("\ud83d\uddd1  Excluir Dispositivo")   # ❌
```

O literal em `:358` contém **surrogates literais** (U+D83D U+DDD1), não o caractere composto 🗑 (U+1F5D1). Confirmado via AST — o valor da string é `'\ud83d\uddd1'`, um par inválido para o Qt.

**Efeito:** o botão "Excluir Dispositivo" exibe um caractere de substituição ou caixa vazia, e quebra em qualquer comparação de string.

#### Correção

```diff
--- a/src/huawei_manager/topology.py
+++ b/src/huawei_manager/topology.py
@@ -358,1 +358,1 @@
-        delete_action = menu.addAction("\ud83d\uddd1  Excluir Dispositivo")
+        delete_action = menu.addAction("\U0001f5d1  Excluir Dispositivo")
```

> Alternativa mais consistente com o resto do código: usar o caractere literal `🗑` ou adicionar `\uFE0F` como em `:357`.

---

### 3.3 `auth_overlay.py:98` — f-string ausente

```python
 97:  self._error_lbl.setStyleSheet(
 98:      "color: #ff4444; background: transparent; border: none; font: 12px {_C.FONT_UI_FAMILY};")
```

Falta o prefixo `f`. O Qt recebe literalmente `{_C.FONT_UI_FAMILY}` e cai na fonte padrão do sistema. As linhas **71-72, 80 e 106-108 do mesmo arquivo** usam `f` corretamente — é inconsistência local.

Além disso `#ff4444` está hardcoded; a paleta tem `NEON_RED = "#ff4d4d"` (`constants.py:13`).

#### Correção

```diff
--- a/src/huawei_manager/widgets/auth_overlay.py
+++ b/src/huawei_manager/widgets/auth_overlay.py
@@ -97,2 +97,2 @@
         self._error_lbl.setStyleSheet(
-            "color: #ff4444; background: transparent; border: none; font: 12px {_C.FONT_UI_FAMILY};")
+            f"color: {_C.NEON_RED}; background: transparent; border: none; font: 12px {_C.FONT_UI_FAMILY};")
```

---

## 4. P1 — Bugs de correção

### 4.1 Por que os 1075 testes não pegam o bug 3.1

O teste em `tests/test_app_threading.py:323` usa um fake com **MRO diferente do real**:

```python
class _NotifyFakeApp(NotifyMixin, _FakeBase):   # NotifyMixin PRIMEIRO
```

No fake, `NotifyMixin.closeEvent` é alcançado. Na classe real, não é. **O teste valida um caminho de código que nunca executa em produção.**

```python
# Correção: o fake precisa ter a mesma ordem de bases da classe real
class _NotifyFakeApp(_FakeBase, NotifyMixin):   # espelha AppCore
```

E adicionar um teste que verifique a resolução do MRO:

```python
def test_close_event_nao_e_sombreado(self) -> None:
    from huawei_manager.app_notify import NotifyMixin
    assert HuaweiRouterApp.closeEvent is NotifyMixin.closeEvent
```

### 4.2 `_ui_queue` não é limpa em `_rebuild_ui`

`app.py:154` cria `self._ui_queue: deque = deque(maxlen=1000)`. Callbacks despachados por `_dispatch()` (`app_threading.py:40`) capturam referências a widgets.

`_rebuild_ui()` (`app.py:592`) destrói e recria toda a UI, mas **não limpa a fila**. Callbacks pendentes que referenciam widgets destruídos executam depois sobre objetos C++ já deletados.

O `try/except` em `app_threading.py:48-50` evita o crash, mas:
- enche o log com `_poll_queue: callback ... falhou`
- **o usuário não vê o resultado**: um "Carregar Configuração" que termina durante um rebuild de tema escreve num widget morto e nada aparece na tela

#### Correção — em `app.py:592`, início de `_rebuild_ui`

```diff
     def _rebuild_ui(self) -> None:
+        # Descarta callbacks pendentes: referenciam widgets que serão destruídos
+        self._ui_queue.clear()
         # 1. Parar todos os timers antes de destruir widgets
```

### 4.3 `pyproject.toml:57` — `skips = ["B101"]` desabilita Bandit em `src/`

```toml
[tool.bandit]
exclude_dirs = ["tests", ".venv", "setup"]
skips = ["B101"]  # assert used in tests is fine
```

O comentário diz "usado em testes", mas `tests` **já está em `exclude_dirs`**. Ou seja, o skip só tem efeito em `src/` — desabilitando ali a checagem que o comentário diz querer preservar.

Existem **9 `assert` em código de produção**:

| Arquivo:Linha | Assert | Risco sob `python -O` |
|---|---|---|
| `handlers/fetch.py:43` | `assert fkey, "_fetch_route: fkey must be extracted..."` | **Alto** — `fkey` vazio passa silenciosamente e executa o caminho de fetch errado |
| `pages/manutencao.py:302` | `assert proc.stdout is not None` | **Médio** — `for line in proc.stdout` → `TypeError` |
| `pages/manutencao.py:465` | `assert proc.stdout is not None` | **Médio** — idem |
| `app.py:80-81` | `assert _secrets is not None` | Baixo — guard de ordem de init |
| `pages/builder.py:56` | `assert isinstance(layout, QVBoxLayout)` | Baixo — narrowing de tipo |
| `pages/services.py:100` | `assert isinstance(parent_layout, QVBoxLayout)` | Baixo — narrowing de tipo |
| `_app.py:19` | `assert isinstance(app, QApplication)` | Baixo — narrowing de tipo |

#### Correção

```diff
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -56,3 +56,2 @@
 exclude_dirs = ["tests", ".venv", "setup"]
-skips = ["B101"]
```

E converter os 3 asserts de risco médio/alto para `raise`:

```diff
--- a/src/huawei_manager/handlers/fetch.py
+++ b/src/huawei_manager/handlers/fetch.py
-        assert fkey, "_fetch_route: fkey must be extracted in UI thread before calling"
+        if not fkey:
+            raise ValueError("_fetch_route: fkey must be extracted in UI thread before calling")
```

### 4.4 `_css_font()` descarta o fallback — `widgets/helpers.py:1-4`

```python
def _css_font(font_tuple: tuple) -> str:
    family, size, *_ = font_tuple          # ← fallback (_FALLBACK_UI) descartado
    weight = "bold" if len(font_tuple) > 2 and font_tuple[2] == "bold" else "normal"
    return f"{weight} {size}px '{family}'"
```

Retorna `"normal 12px 'IBM Plex Sans'"` — **sem fallback**, enquanto o QSS global (`themes/__init__.py`) declara `"IBM Plex Sans", "Inter", "Segoe UI", sans-serif`. Duas fontes de verdade para a mesma família.

Usado em `neon_button.py:49` e `neon_entry.py`.

#### Correção

```python
def _css_font(font_tuple: tuple) -> str:
    family, size, *rest = font_tuple
    weight = "bold" if "bold" in rest else "normal"
    fallback = rest[-1] if rest and "bold" not in rest[-1] else None
    stack = f"'{family}'" + (f", '{fallback}'" if fallback else "")
    return f"{weight} {size}px {stack}"
```

### 4.5 Cores hardcoded que **não** trocam com o tema

| Arquivo:Linha | Valor | Correto seria |
|---|---|---|
| `widgets/neon_button.py:35` | `#555566` | cinza invisível sobre `BG_INPUT` no tema light |
| `pages/cmd.py:105` | `#2a2a4a` | `C.BORDER_NRM` |
| `pages/services.py:136` | `#2a2a4a` | `C.BORDER_NRM` |
| `widgets/auth_overlay.py:98` | `#ff4444` | `C.NEON_RED` |

O mecanismo de tema (`app.py:527` `_toggle_theme`) faz 3 passos: `set_theme()` troca as constantes (`constants.py:95`), `apply_theme()` aplica o QSS global (`_app.py:23`), e `_rebuild_ui()` recria a UI. Qualquer valor **literal** ignora os três.

---

## 5. P2 — Consistência visual

### 5.1 8 cores órfãs no QSS não derivam de `constants.py`

`QSS_DARK` tem 13 cores; 4 não estão na paleta:

| Cor | Qtd. | Onde | Problema |
|---|---|---|---|
| `#1a1a3e` | 4 | hover de botão/lista | não existe na paleta |
| `#6a6a9a` | 4 | `:disabled` | ≠ `FG_DIM` (`#8a8abe`) e ≠ `FG_DIM_L` (`#6a6a8a`) |
| `#40eeff` | 1 | `border-color` hover | ≠ `NEON_CYAN` (`#00e5ff`) |
| `#0e0e20` | 1 | `:pressed` | não existe na paleta |

`QSS_LIGHT` tem 4 órfãs: `#00b0b8` (1), `#8a8aaa` (2), `#d0d8e0` (2), `#e0e8f0` (3).

Cada tema é internamente consistente (o QSS inteiro troca junto), mas os valores estão **duplicados** e podem divergir da paleta. Correção estrutural: converter `QSS_DARK`/`QSS_LIGHT` em templates preenchidos a partir de `constants.py` em `_app.py:23-38`.

### 5.2 Escala de fontes: `px` vs `pt`

- `constants.py:35-39` define a escala em **`pt`**: `FONT_CAPTION=11`, `FONT_BODY=12`, `FONT_SUBHEAD=14`, `FONT_TITLE=16`
- **32 declarações `font:` inline em `px`** em 9 arquivos

Distribuição: `11px`×11, `12px`×10, `10px`×4, `14px`×3, `18px`×2, `16px`×2.

| Arquivo | Linhas |
|---|---|
| `widgets/device_dialog.py` | 44, 56, 120, 144, 165, 176, 205, 215 |
| `app.py` | 307, 312, 325, 331, 434, 440 |
| `pages/manutencao.py` | 65, 98, 125, 148, 186, 370 |
| `pages/services.py` | 83, 126, 206, 345 |
| `handlers/dashboard.py` | 26, 31 |
| `pages/builder.py` | 112, 304 |
| `pages/cmd.py` | 95, 163 |
| `app_state.py` / `topology.py` | 49 / 347 |

### 5.3 `Space Grotesk` declarada e morta

`constants.py:23` define `_FONT_UI_TITLE_FAMILY = "Space Grotesk"` e `FONT_UI_TITLE:33` a consome. **Nenhum `font:` inline nem regra QSS referencia `FONT_UI_TITLE`.** A fonte de títulos nunca é aplicada.

### 5.4 Atributo privado usado cross-módulo

`widgets/command_palette.py:230,241,247` usa `C._FONT_UI_FAMILY` entre aspas; o resto do projeto usa o público `C.FONT_UI_FAMILY` (`constants.py:29`).

### 5.5 Mesmo conceito, glifos diferentes

141 literais com símbolos, **42 glifos distintos**:

| Conceito | Variantes em uso |
|---|---|
| Fechar/cancelar | `✕` U+2715 (`auth_overlay.py:68`) · `✖` U+2716 (`builder.py:242`, `manutencao.py:245`, `services.py:306`) · `✘` U+2718 (14×, `handlers/commands.py`) |
| Refresh | `↻` U+21BB (`builder.py:81,123,138,150,237`) · `🔄` U+1F504 (`manutencao.py:116,168,357,361`) |
| Check | `✔` U+2714 (5×, `vault_backends`) · `✅` U+2705 (5×, `manutencao.py`) |
| Executar | `▶` U+25B6 (`manutencao.py:89`, `cmd.py:152`, `services.py:301`) · `🔍` U+1F50D (`manutencao.py:110`) |
| Engrenagem | `⚙` U+2699 em 4 ações distintas: Lint (`manutencao.py:77`), Install (`:164`), Enviar Config (`cmd.py:156`), nome de serviço (`services.py:236`) |

### 5.6 Ícones semanticamente errados

- `pages/builder.py:315` — `📡` no card **DISPOSITIVOS**, mas `app.py:385` usa `📡` para **Tabela ARP**. Mesmo ícone, dois destinos.
- `pages/builder.py:299` — `🔌` (tomada elétrica) no card **CONEXÃO** de rede.

### 5.7 Separador ícone→texto inconsistente

- **2 espaços**: `builder.py:81,123,138,150,206,232,237,242`; `manutencao.py:45,77,81,85,89,110,160,164,168,245`; `services.py:306`; `topology.py:357,358`
- **1 espaço**: `builder.py:180` (`📁 Escolha`), `cmd.py:152` (`▶ Executar`), `cmd.py:156` (`⚙ Enviar Config`)

### 5.8 Padding manual por espaços

`pages/builder.py:364-367` — atalhos alinhados à mão:
```python
"config": "  📋 Config  ",
"route":  "  🌐 Rotas   ",   # 3 espaços finais
"backup": "  💾 Backup  ",
"cmd":    "  ⌨  Editor  ",  # espaço duplo interno
```
Brittle e desalinhado com os demais botões.

### 5.9 Codificação de emoji inconsistente no mesmo bloco

`app.py:377-396` — 10 entradas estruturalmente idênticas misturam emoji literal e `\U0001fXXX`. `\u2328` (⌨) e `\u26a1` (⚡) são BMP opaco, desalinhados ao lado de 🏠/📋.

---

## 6. P3 — Texto e i18n

### 6.1 Textos sem acento (16 confirmados como exibidos)

| Arquivo:Linha | Texto atual | Correto |
|---|---|---|
| `app_threading.py:92` | `Conexao indisponivel. Reconecte.` | `Conexão indisponível. Reconecte.` |
| `handlers/commands.py:50` | `✘  Comando cancelado pelo usuario.` | `✘  Comando cancelado pelo usuário.` |
| `handlers/commands.py:115` | `✘  Editor vazio — digite os comandos de configuracao` | `… de configuração` |
| `handlers/commands.py:136` | `ℹ  Nenhuma alteracao detectada em relacao a config atual.` | `alteração … relação` |
| `handlers/commands.py:144` | `✘  Dry-run falhou — configuracao NAO aplicada. Verifique o log.` | `configuração NÃO` |
| `handlers/commands.py:147` | `Aplicando configuracao…` | `Aplicando configuração…` |
| `handlers/commands.py:152` | `✘  Sessao SSH inativa. Conecte-se primeiro.` | `Sessão SSH` |
| `handlers/commands.py:172` | `Coletando configuracao para backup…` | `configuração` |
| `handlers/devices.py:160` | `(roteador padrao)` | `(roteador padrão)` |
| `handlers/fetch.py:25` | `Carregando configuracao atual…` | `configuração` |
| `handlers/fetch.py:95` | `Coletando informacoes do sistema…` | `informações` |
| `handlers/services.py:141` | `✘  Sem sessao SSH ativa. Conecte-se primeiro.` | `sessão` |
| `handlers/ssh.py:66` | `Falha de autenticacao` | `Falha de autenticação` |
| `handlers/ssh.py:70` | `Timeout de conexao` | `Timeout de conexão` |
| `manutencao.py:255` | `Watcher ativo — resultados em ate 60s...` | `até 60s…` |
| `services.py:231` | `  Nenhum servico de configuracao para este tipo de Device` | `serviço de configuração` |

**+ 24 títulos/botões:** `app.py:391,394,437` · `builder.py:77,81,89,145,157,215,225,273,299,333,356,380` · `cmd.py:87,171` · `manutencao.py:38,45,51,320,483` · `services.py:163` · `device_dialog.py:34,37`

**Contrastes corretos (padrão a seguir):** `services_data.py` (100% acentuado), `exceptions.py`, `widgets/auth_overlay.py`, `topology_items.py`, `handlers/services.py:67,68,72`.

### 6.2 Rótulos em inglês no Command Palette

`widgets/command_palette.py:321-323` — o palette diverge da navegação e das páginas:

| Destino | Sidebar (`app.py`) | Command Palette |
|---|---|---|
| Rotas | `Roteamento` (384) | **`Routing`** (321) |
| ARP | `Tabela ARP` (385) | **`ARP Table`** (322) |
| Info | `Info do Sistema` (386) | **`Info`** (323) |

### 6.3 Erros em inglês vazando para output em PT

`sdn_controller/validator.py` gera `reason` em inglês, injetado em mensagens portuguesas:

```python
validator.py:96   reason="Empty command"
validator.py:109  reason=f"Admin bypass for: {command}"
validator.py:114  reason=f"Command denied by policy: {command}"
validator.py:120  reason=f"Unknown command: {command}"
```

**Na tela:**
```
✘  Comando bloqueado: Command denied by policy: reset saved-configuration
✘  Comando bloqueado: Unknown command: display foo
✘  Config bloqueada: Admin bypass for: undo startup
✘  Comando bloqueado (Empty command):
```

Consumidores: `handlers/commands.py:40,84,121` e `handlers/services.py:106`.

> ⚠️ Atenção: `sdn_controller/polling_manager.py:41` (`_ERROR_PREFIXES`) casa a string `"Unknown command"` para classificar erros. Traduzir exige atualizar essa lista.

Também em inglês: `services/catalog.py:388` e `sdn_controller/southbound.py:277` → `">  Config applied:"` (vs `"Configuracao aplicada"` em `session_commands.py:102`).

### 6.4 "Device" vs "device" no mesmo texto

`pages/services.py:47` — `"Device: (selecione um device na aba Topologia)"`: maiúsculo e minúsculo **na mesma string**.

### 6.5 Quatro variantes de "sem conexão"

| Variante | Local |
|---|---|
| `"Sem conexao"` | `session_commands.py:17,27,87` |
| `"Sem conexão CLI ativa"` | `services/catalog.py:378` |
| `"✘  Sem sessao SSH ativa."` | `handlers/services.py:141` |
| `"✘  Sessao SSH inativa."` | `handlers/commands.py:152` |

### 6.6 Pontuação inconsistente

- **Reticências**: `…` U+2026 em `app.py:546`, `handlers/fetch.py:25,63,95`, `handlers/commands.py:88,95,147,172` — mas `...` ASCII em `manutencao.py:255,278,342,440`
- **Ponto final** em mensagens irmãs: `commands.py:78,115` sem ponto vs `:144,50` com ponto
- **Cancelamento**: `handlers/services.py:72` `"Operação cancelada pelo usuário."` (com acento, sem glyph) vs `commands.py:50` `"✘  Comando cancelado pelo usuario."` (com glyph, sem acento) — **mesmo evento**
- **Parênteses**: `app.py:437` / `devices.py:160` `(roteador padrao)` sem ponto vs `topology_items.py:38` `(padrão .env)` com ponto

### 6.7 Anglicismos no status bar

`app_state.py:44` — `"Sessão expirada — acesso user"` (EN); `:45` — `"resetado para user"`.

### 6.8 Codificação de emoji: um único VS16 no projeto

`topology.py:357` (`✏️`) é o **único** lugar com `\uFE0F` explícito.

### 6.9 Docstring desatualizada

`sdn_controller/__init__.py:9` lista `lldp_discovery` como "Submódulo planejado" — o módulo não existe.

---

## 7. P4 — Ambiente / DevX

### 7.1 PySide6 não resolvido no VSCode

**Não é problema de código.** Verificado:

- `pyright` na CLI: **0 erros**, **0 imports não resolvidos**
- PySide6 6.10.3 instalado em `.venv/lib/python3.12/site-packages/PySide6` ✅
- **`/home/aluno20/Huawei-Manager-2.0/.vscode/` não existe** ← a causa

O `pyproject.toml:38-41` já declara `venvPath = "."` / `venv = ".venv"`, mas o VSCode precisa que o interpretador esteja *selecionado*.

**Correção:** `Ctrl+Shift+P` → **Python: Select Interpreter** → `/home/aluno20/Huawei-Manager-2.0/.venv/bin/python3.12`

Opcional — criar `.vscode/settings.json`:
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python3.12",
  "python.terminal.activateEnvInCurrentTerminal": true,
  "python.analysis.extraPaths": ["${workspaceFolder}/src"]
}
```

### 7.2 Fragilidade: erros detectados por prefixo de texto

`sdn_controller/polling_manager.py:41`:
```python
_ERROR_PREFIXES = ("ERRO:", "Sem conex", "Error:", "Unknown command",
                   "Incomplete command", "Ambiguous", "Unrecognized",
                   "Invalid input")
```

Detecção de erro por **casamento de string em texto localizado**. Se o idioma mudar, o texto for reescrito ou o device retornar inglês, a detecção falha silenciosamente. Considerar código de saída ou sentinel estruturado.

### 7.3 12 handlers de exceção silenciosos (`except: pass`)

| Arquivo:Linha |
|---|
| `_config.py:49`, `_config.py:115` |
| `app.py:75`, `app.py:302`, `app.py:371` |
| `audit_log.py:345` |
| `pages/manutencao.py:331`, `pages/manutencao.py:494` |
| `widgets/auth_overlay.py:235` |
| `widgets/neon_button.py:79`, `widgets/neon_entry.py:74` |
| `agents/scans/security.py:83` |

A maioria é legítima (ícone ausente, botão já deletado). Mas `audit_log.py:345` e `_config.py:49` silenciam falhas de auditoria/segurança — deveriam logar em nível warning.

---

## 8. Dívida de lint

`src/` tem **zero**. Em `tests/` + `setup/`: **76 avisos** (o CI roda apenas `ruff check src/huawei_manager/`, então não bloqueia).

| Regra | Qtd. | Exemplos |
|---|---|---|
| `I001` imports não ordenados | 28 | `tests/test_vnfs_mixin.py:7` |
| `F401` import não usado | 21 | `tests/test_commands_mixin.py:7` (`os`) |
| `W292` falta newline no EOF | 16 | `tests/test_theme.py:63` |
| `F841` variável não usada | 5 | `tests/test_probe_status.py:136` |
| `E501` linha > 120 | 4 | `tests/test_vnf_crypto.py:245` (136) |
| `UP038` `isinstance` não-PEP604 | 2 | `tests/test_vault.py:130` |

```bash
.venv/bin/ruff check src/ tests/ setup/ --fix    # resolve 62 de 76
```

Os 5 `F841` e 2 `UP038` precisam de decisão manual. **Verifiquei os 5 `F841` de `test_probe_status.py`: não são bug** — `probe_devices()` muta o device e as asserções checam `device.status`; o `result =` é resto inofensivo.

---

## 9. Ordem de aplicação sugerida

| # | Ação | Arquivo | Esforço |
|---|---|---|---|
| 1 | Reordenar bases do `AppCore` (MRO) | `app.py:61` | 1 linha |
| 2 | Corrigir escape do emoji | `topology.py:358` | 1 linha |
| 3 | Adicionar prefixo `f` + usar `NEON_RED` | `auth_overlay.py:98` | 1 linha |
| 4 | Espelhar MRO no fake + teste de regressão | `tests/test_app_threading.py:323` | ~10 linhas |
| 5 | `self._ui_queue.clear()` em `_rebuild_ui` | `app.py:592` | 1 linha |
| 6 | Remover `skips = ["B101"]` | `pyproject.toml:57` | 1 linha |
| 7 | Converter asserts de risco | `fetch.py:43`, `manutencao.py:302,465` | 3 blocos |
| 8 | `closeEvent` finalizando `_shutdown` + encurtar lingering | `app_notify.py` | opcional |
| 9 | 4 cores hardcoded → constantes | §4.5 | 4 linhas |
| 10 | Unificar glifos (check/cross/refresh/⚙) | §5.5 | ~20 linhas |
| 11 | Acentuar 40 textos | §6.1 | 40 linhas |
| 12 | Traduzir reasons do validador (+ atualizar `_ERROR_PREFIXES`) | §6.3 | 6 linhas |
| 13 | `.vscode/settings.json` | novo | 5 linhas |
| 14 | `ruff --fix` em `tests/` | §8 | automático |

> ⚠️ **Esta ordem é da Parte 1 (frontend/styling). Com a auditoria de backend e frontend, a ordem de aplicação canônica é a da **seção 17**, que começa pelo bypass de RBAC.**

---

## 10. Comandos de verificação

```bash
cd /home/aluno20/Huawei-Manager-2.0

# gates do CI
.venv/bin/ruff check src/huawei_manager/
.venv/bin/python -m pytest tests/ -q --cov=src/huawei_manager --cov-fail-under=60
.venv/bin/pyright

# lint completo (inclui tests)
.venv/bin/ruff check src/ tests/ setup/

# smoke test de inicialização
QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
import sys; sys.path.insert(0,'src')
from huawei_manager._config import init; init()
from huawei_manager._app import get_app, apply_theme
from huawei_manager.app import HuaweiRouterApp
from huawei_manager.app_notify import NotifyMixin
app=get_app(); apply_theme('dark')
w=HuaweiRouterApp(); w.show(); app.processEvents()
print('title   :', w.windowTitle())
print('pagina  :', w._current_page)
print('MRO fix :', HuaweiRouterApp.closeEvent is NotifyMixin.closeEvent)
w.close()
print('shutdown:', w._shutdown)
"
```

**Estado atual esperado desta última checagem:**
```
MRO fix : False     <-- BUG 3.1
shutdown: False     <-- BUG 3.1
```

---

## Apêndice — Integridade do refactor `cf6a889`

O commit removeu `auth_service.py` (204 linhas) e `sdn_controller/_dormant/` (6 arquivos, 1143 linhas).

| Verificação | Resultado |
|---|---|
| `ruff check src/` regras `F` | ✅ All checks passed |
| `compileall src/ tests/ setup/` | ✅ exit 0 |
| Import real via `pkgutil.walk_packages` | ✅ 80/80 módulos |
| Referências a `auth_service` / `_dormant/*` | ✅ 0 |
| `SdnError` (classe base) | ✅ usada via herança |
| Definições duplicadas | ✅ nenhuma (só o par `@property`/`@setter` em `polling_manager.py:197/201`) |

**Conclusão: o refactor deixou zero imports órfãos.** Nenhuma referência aos módulos removidos.

**Segurança verificada:** nenhum `shell=True`; nenhum segredo em log; `secrets.enc.yaml` versionado mas criptografado com SOPS (`ENC[AES256_GCM]`), com `.sops.yaml` presente; `.env` e `.env.enc` no `.gitignore`.

---

*Fim da Parte 1 (frontend/styling). Gerado por análise estática + execução real do app. Nenhum arquivo do repositório foi modificado.*

---

# PARTE 2 — BACKEND (conexão, SSH, sessão, concorrência)

Variação de segunda leva, com auditoria dos módulos de sessão, southbound, polling, banco, cripto, vault e handlers. Método: leitura integral + checagem cruzada contra a API do Netmiko 4.4 + reprodução em runtime.

## 11. Bugs de backend

### 11.1 🔴 P0-S — Bypass de RBAC: allow-list retorna antes da deny-list

**Arquivo:** `src/huawei_manager/sdn_controller/validator.py:98-101`

```python
# Check allow-list
for pattern in self._allow:
    if pattern.search(command):          # ← casa no buffer INTEIRO
        return ValidationResult(allowed=True)   # ← retorna ANTES do deny-list

# Check deny-list
for pattern in self._deny:               # ← nunca chega aqui se casou no allow
```

`pattern.search()` roda sobre a string **completa**. Se qualquer linha do editor casar com o allow-list, a função retorna `allowed=True` **antes** de examinar a deny-list. O `reason` fica `None` e `bypass_2fa` fica `False`.

**Reprodução verificada:**
```python
v = CommandValidator()
v.validate("display version\nsystem-view\nreset saved-configuration", role="user")
#   allowed  : True        <-- ESCALACAO
#   reason   : None
#   bypass2fa: False       <-- sem dialogo de confirmacao

v.validate("reset saved-configuration", role="user")
#   allowed  : False       <-- bloqueado corretamente quando isolado
#   reason   : Command denied by policy: reset saved-configuration
```

**Cadeia completa (4 elos, todos verificados):**

| # | Arquivo:linha | Fato verificado |
|---|---|---|
| 1 | `validator.py:98-101` | allow-list casa `display` → retorna `allowed=True`, `bypass_2fa=False` |
| 2 | `commands.py:42` | `if vr.bypass_2fa:` → `False` → **nenhum `QMessageBox` é exibido** |
| 3 | `commands.py:82-84` | re-valida o mesmo buffer → mesmo early-return `allowed=True` |
| 4 | `app.py:84` | `SSHSouthbound(_secrets, audit, session=self.session)` — **sem `validator=`** |
| 5 | `southbound.py:203` | `if self._validator is not None:` → `False` → **sem segunda checagem no transporte** |
| 6 | `commands.py:98` | `self._sb.send_command(cmd)` envia a string crua; netmiko executa cada `\n` como comando próprio |

O editor aceita Shift+Enter de propósito (`cmd.py`), então o buffer multi-linha é um caminho normal de uso — não um caso exótico.

**Payload para o papel `user`, sem prompt:**
```
display version
system-view
reset saved-configuration
```

#### 🔴 CORREÇÃO (stress test): o fix acima sozinho NÃO fecha o bypass

Testei a correção com um stress test dedicated (§19.2) e ela **não é suficiente**: o VRP aceita **`;`** como separador de comandos, e o `;` **não** é `\n`. O payload abaixo é uma **única linha**, passa pelo filtro de multi-linha, e executa três comandos no equipamento:

```python
v.validate("display version;system-view;reset saved-configuration", role="user")
#   allowed  : True     <-- BYPASS, e a string tem ZERO newlines
#   bypass2fa: False
```

Resultado do fuzz de separadores (todos com `role="user"`):

| Payload | `allowed` | `bypass_2fa` | Sobrevive ao fix de "só bloquear `\n`"? |
|---|---|---|---|
| `display version\nsystem-view\nreset saved-configuration` | `True` | `False` | ❌ bloqueado |
| `display version;system-view;reset saved-configuration` | `True` | `False` | 🔴 **CONTINUA PASSANDO** |
| `display version ; system-view ; reset saved-configuration` | `True` | `False` | 🔴 **CONTINUA PASSANDO** |
| `display version\rsystem-view\rreset saved-configuration` | `True` | `False` | ❌ bloqueado |
| `display\tversion;reset saved-configuration` | `True` | `False` | 🔴 **CONTINUA PASSANDO** |
| `display cpu-usage \| include cpu` (pipe legítimo) | `True` | `False` | ✅ deve continuar permitido |

Note que `;reset saved-configuration` **isolado** é bloqueado (o padrão `\breset\b` da deny-list não é ancorado) — o exploit **exige** que o allow-list dispare primeiro. Por isso a falha é sempre o *early return*, nunca a deny-list.

#### Correção definitiva — validar **cada comando lógico**, não o buffer

Não basta bloquear `\n`: é preciso **dividir** o buffer em comandos lógicos e validar cada um. O separador do VRP é `;` (e whitespace ao redor). O pipe `|` **não** divide — é um filtro legítimo (`display cpu-usage | include cpu`).

```diff
--- a/src/huawei_manager/sdn_controller/validator.py
+++ b/src/huawei_manager/sdn_controller/validator.py
@@
 class CommandValidator:
+    # Separadores de comando do VRP. ";" encadeia comandos; "|" e apenas
+    # um filtro de pipe e NAO pode dividir.
+    _CMD_SEPARATORS = re.compile(r"[;\r\n]+")
+
+    def _split_logical(self, command: str) -> list[str]:
+        """Divide o buffer em comandos logicos, recusando entradas vazias."""
+        return [c.strip() for c in self._CMD_SEPARATORS.split(command) if c.strip()]
+
     def validate(self, command: str, role: str = "user") -> ValidationResult:
         if not command.strip():
             return ValidationResult(allowed=False, reason="Empty command")
 
-        # Check allow-list
-        for pattern in self._allow:
-            if pattern.search(command):
-                return ValidationResult(allowed=True)
+        # Cada comando logico precisa PASSAR na politica. O mais restritivo
+        # vence: um unico comando negado derruba o buffer inteiro.
+        parts = self._split_logical(command)
+        if not parts:
+            return ValidationResult(allowed=False, reason="Empty command")
+        for part in parts:
+            r = self._validate_one(part, role)
+            if not r.allowed:
+                return r
+        return ValidationResult(allowed=True)
 
-        # Check deny-list
+    def _validate_one(self, command: str, role: str) -> ValidationResult:
+        """Aplica a politica a UM comando logico. Deny-list vence allow-list."""
+        # Deny-list PRIMEIRO: um comando nao permitido nunca deve ser
+        # liberado por ter casado com a allow-list.
         for pattern in self._deny:
             if pattern.search(command):
                 if role in _BYPASS_ROLES:
@@
                     reason=f"Command denied by policy: {command}",
                 )
 
+        for pattern in self._allow:
+            if pattern.search(command):
+                return ValidationResult(allowed=True)
+
         # Unknown command
         return ValidationResult(allowed=False, reason=f"Unknown command: {command}")
```

**Três invariantes que o teste de regressão precisa fixar** (bloco de testes em §16):
1. Deny-list é avaliada **antes** da allow-list.
2. Nenhum separador (`\n`, `\r`, `;`) permite encadear um comando negado.
3. `|` **não** divide — pipes legítimos continuam funcionando.

⚠️ **Com `_validate_one` exigindo bypass por comando, um buffer com 1 comando negado e `role="admin"` vai retornar `bypass_2fa=True`** — o que é o comportamento correto (o operador vê o diálogo e confirma o comando destrutivo específico).

**Defesa em profundidade — injetar o validator no transporte** (fecha o bypass mesmo se o validador da UI falhar):

```diff
--- a/src/huawei_manager/app.py
+++ b/src/huawei_manager/app.py
@@ -84,3 +84,4 @@
-        self._sb = SSHSouthbound(_secrets, audit, session=self.session)
         self._cmd_validator = CommandValidator()
+        self._sb = SSHSouthbound(_secrets, audit, session=self.session,
+                                 validator=self._cmd_validator)
```

⚠️ **`send_config` tem o mesmo furo.** `southbound.py:233-239` valida `"\n".join(commands)` como **uma** string, então o defeito reaparece em config. Depois de bloquear `\n` no validator, validar **cada elemento** de `commands` individualmente.

---

### 11.2 🟠 P1-B — `send_service_commands` envia `quit` em user view: um clique em Serviços mata a sessão SSH

**Arquivo:** `src/huawei_manager/sdn_controller/southbound.py:249-285`

```python
if need_sysview:
    self._session.run_cli_rpc("system-view")      # 271 → vai para <Huawei>
parts: list[str] = []
for cmd in commands:
    if config_mode:
        ok, msg = self.send_config([cmd])         # 276 → edit_config SAI do config mode
    ...
if need_sysview:
    self._session.run_cli_rpc("quit")             # 283 → roda em USER view
```

`send_config` → `edit_config` → `send_config_set(..., read_timeout=120)` (`session_commands.py:95`). O netmiko chama `exit_config_mode()` ao final, então o equipamento já voltou a `<Huawei>` (user view) quando a linha 283 executa. **`quit` em user view encerra a sessão CLI.** E `SSHSouthbound._connected` continua `True` — nada o reseta — então todo comando posterior falha num canal morto.

**Alcançável:** `handlers/services.py:145-149` passa `config_mode=final_svc.config_mode` do catálogo, e **22 serviços embarcados têm `config=True`** (`services_data.py`).

**Segundo defeito na mesma função:** não há `try/finally` (274-283). Se `send_config`/`send_command` levantar em 276/279, o `quit` é pulado e o equipamento fica **em `system-view` para a sessão compartilhada**.

```diff
--- a/src/huawei_manager/sdn_controller/southbound.py
+++ b/src/huawei_manager/sdn_controller/southbound.py
@@ -268,18 +268,22 @@
         need_sysview = config_mode or requires_privilege
-
         if need_sysview:
             self._session.run_cli_rpc("system-view")
-
-        parts: list[str] = []
-        for cmd in commands:
-            if config_mode:
-                ok, msg = self.send_config([cmd])
-                parts.append(f">  Config applied:\n{'─' * 40}\n{msg}")
-            else:
-                out = self.send_command(cmd)
-                parts.append(f">  {cmd}\n{'─' * 40}\n{out}")
-
-        if need_sysview:
-            self._session.run_cli_rpc("quit")
+        try:
+            parts: list[str] = []
+            for cmd in commands:
+                if config_mode:
+                    # set_config ja entra em system-view e volta sozinho
+                    ok, msg = self._session.edit_config(
+                        cmd, target="running", save=False)
+                    parts.append(f">  Config applied:\n{'─' * 40}\n{msg}")
+                else:
+                    out = self.send_command(cmd)
+                    parts.append(f">  {cmd}\n{'─' * 40}\n{out}")
+        finally:
+            if need_sysview:
+                try:
+                    # "return" e no-op em user view e sai de system-view
+                    # em config view -> restaura o estado de forma idempotente.
+                    self._session.run_cli_rpc("return")
+                except Exception:
+                    log.exception("falha ao restaurar user view")
+                    self.invalidate_connection()
 
         return "\n\n".join(parts)
```

---

### 11.3 🟠 P1-B — 10× `except RuntimeError` mortos; erros escapam silenciosamente

**Arquivos:** `handlers/fetch.py:28,47,66,79,110` · `handlers/commands.py:91,98,150,175` · `handlers/auth.py`

`exceptions.py:11` → `class SdnError(Exception)`. **Não é `RuntimeError`.** Toda falha de `SSHSouthbound` levanta `SdnConnectionError` / `SdnCommandError` / `SdnAuthError` (`southbound.py:202,208,214,232,239`).

```python
except RuntimeError:                 # fetch.py:28 — NUNCA casa
    self._sb.invalidate_connection()
```

**Consequências:** a exceção sobe para a future do executor, é logada pelo done-callback (`app_threading.py:71-72`), e o usuário fica olhando o texto permanente de `_loading(...)` ("Executando: …") **sem erro no painel**. E `invalidate_connection()` nunca roda — sessão morta nunca é marcada como morta.

```diff
--- a/src/huawei_manager/handlers/commands.py
+++ b/src/huawei_manager/handlers/commands.py
@@ -88,13 +88,16 @@
             try:
                 _ok, result = self._sb.send_config(cmd.strip().splitlines())
-            except RuntimeError:
+            except SdnError as exc:
                 self._sb.invalidate_connection()
+                self._write(self.out_cmd, f"✘  Falha SSH: {exc}")
                 return
         else:
             self._loading(self.out_cmd, f"Executando: {cmd}…")
             try:
                 result = self._sb.send_command(cmd or "")
-            except RuntimeError:
+            except SdnError as exc:
                 self._sb.invalidate_connection()
+                self._write(self.out_cmd, f"✘  Falha SSH: {exc}")
                 return
```

Aplicar a mesma troca em `commands.py:150,175` e nos 5 pontos de `fetch.py`, adicionando `from huawei_manager.exceptions import SdnError`.

---

### 11.4 🟠 P1-B — Exceções convertidas em `"ERRO: …"`: o log de auditoria registra falha como `ok`

**Arquivo:** `src/huawei_manager/session_commands.py:15-23`

```python
def _cmd(self, command: str) -> str:
    if not self._conn:
        return "Sem conexao"          # 17 — string sentinela, não um erro
    try:
        out = self._conn.send_command(command, read_timeout=120)
    except Exception as e:
        log.exception("Comando falhou: %s", command)
        return f"ERRO: {e}"           # 23 — f"{e}" embute host/port/tipo
```

Os chamadores então marcam o contexto como sucesso, tornando os próprios `except` **código morto inalcançável**:

| Método | Marca `ok` | `except` morto |
|---|---|---|
| `get_config` | `session_commands.py:57` | 59-61 |
| `get` | `session_commands.py:73` | 75-77 |
| `run_cli_rpc` | `session_commands.py:118` | 120-123 |
| `edit_config` | ✅ correto (`:104` `set_status("error")`) | — |

**Efeito líquido:** `audit_log.jsonl` grava `status: "ok"` para sessões que morreram, caíram ou deram timeout — **o rastro de auditoria não é confiável** para as três operações mais usadas. E `f"ERRO: {e}"` vaza host/porta para a UI.

```diff
--- a/src/huawei_manager/session_commands.py
+++ b/src/huawei_manager/session_commands.py
@@ -15,9 +15,10 @@
     def _cmd(self, command: str) -> str:
         if not self._conn:
-            return "Sem conexao"
+            raise SdnConnectionError("Sem conexao SSH")
         try:
-            out = self._conn.send_command(command, read_timeout=120)
+            out = self._conn.send_command(command, read_timeout=self._read_timeout)
             return clean_output(str(out))
         except Exception as e:
-            log.exception("Comando falhou: %s", command)
-            return f"ERRO: {e}"
+            log.exception("Comando falhou: %s", sanitize_command(command))
+            raise SdnCommandError(sanitize_error(str(e))) from e
@@ -117,2 +118,0 @@
-                result = self._cmd(cmd)
-                ctx.set_status("ok")
+                result = self._cmd(cmd)     # propaga; o ctx marca "error" no __exit__
                 return result
-            except Exception as e:
-                ctx.set_status("error")
-                log.exception("CLI falhou")
-                return f"ERRO: {e}"
```

Isso permite ainda **deletar** as heurísticas frágeis `polling_manager._ERROR_PREFIXES` (`:41-43`) e o sniffing de `"Sem conexao"` / `"ERRO:"` em `handlers/dashboard.py`.

---

### 11.5 🟠 P1-B — `disconnect()` não é exclusivo de comandos em voo; shutdown derruba no meio

**Arquivo:** `src/huawei_manager/session.py:230-237`

`disconnect()` nunca toma `self._lock`, enquanto todo wrapper de comando a segura por até `read_timeout=120` (`session_commands.py:29,50,66,88,111`):

```python
def disconnect(self) -> None:
    if self._conn:                  # check
        try:
            self._conn.disconnect()  # ...socket fechado aqui
        ...
        self._conn = None
```

`app_notify.py:26-27` chama `self._sb.disconnect()` na thread principal **antes** de `_cleanup_executors()` — então na saída a corrida é garantida. Um comando em voo morre no meio de `read_channel` e, por 11.4, é reportado ao usuário e à auditoria como **`ok`**. `is_connected` (`session.py:239-241`) e `connect()` (`:200`) têm o mesmo acesso sem lock.

```diff
--- a/src/huawei_manager/session.py
+++ b/src/huawei_manager/session.py
@@ -48,6 +48,7 @@
         self._lock = threading.Lock()
+        self._closing = False
@@ -199,3 +200,8 @@
-            self._conn = ConnectHandler(**kwargs)
+            conn = ConnectHandler(**kwargs)      # constrói antes de publicar
+            with self._lock:
+                old, self._conn = self._conn, conn
+            if old is not None:
+                try:
+                    old.disconnect()             # não deixa órfão
+                except Exception:
+                    log.warning("disconnect do _conn anterior falhou", exc_info=True)
@@ -230,8 +236,17 @@
-    def disconnect(self) -> None:
-        if self._conn:
+    def disconnect(self) -> None:
+        with self._lock:
+            self._closing = True
+            conn, self._conn = self._conn, None
+        if conn:
             try:
-                self._conn.disconnect()
+                conn.disconnect()               # fora do lock: nao bloqueia a UI
             except Exception as exc:
                 log.warning("disconnect: %s", exc)
-            self._conn = None
             log.info("Sessao SSH encerrada")
+        with self._lock:
+            self._closing = False
```

> **Deliberadamente sem segurar o lock** em `conn.disconnect()`: o lock fica preso por até 120s quando há comando rodando, então travar ali congelaria o `closeEvent` por dois minutos. O swap para `None` + o flag `_closing` é que torna o teardown seguro.

---

### 11.6 🟠 P1-B — Sessão SSH morta nunca é liberada: o poller a tenta para sempre

**Arquivo:** `src/huawei_manager/sdn_controller/polling_manager.py:250-254`

```python
if _is_error_string(out):
    log.warning("device %s erro-como-string — instável", device.id)
    self._decider.next_interval(device.id, False)
    self._set_next_due(device.id, POLL_MIN_INTERVAL)
    return                       # ← sem self._factory.release(...)
```

A recuperação depende de `purge_expired()` (`session_factory.py:159-168`, TTL 600s), mas `get()` atualiza `last_used` em **toda** chamada (linha 133). Uma sessão morta que continua sendo consultada tem `last_used` renovado a cada `POLL_MIN_INTERVAL` e **nunca expira** — a entrada do pool nunca é descartada, `_create()` nunca re-executa, e o device faz polling de um transporte morto indefinidamente.

```diff
--- a/src/huawei_manager/sdn_controller/polling_manager.py
+++ b/src/huawei_manager/sdn_controller/polling_manager.py
@@ -250,4 +250,5 @@
             if _is_error_string(out):
                 log.warning("device %s erro-como-string — instável", device.id)
+                self._factory.release(device.id)   # garante recriacao no proximo tick
                 self._decider.next_interval(device.id, False)
```

---

### 11.7 🟠 P1-B — `_devices_lock` segurada durante I/O de rede e disco

**Arquivo:** `src/huawei_manager/handlers/devices.py:20-38`

Envolve `load_inventory`, `probe_or_simulate` (ThreadPoolExecutor, 5s de timeout TCP por device) e `save_inventory`. O `try/finally` está correto, mas **cada refresh do dashboard disputa por esses segundos de lock**. Um device inalcançável trava o dashboard inteiro.

**Correção:** ler um snapshot sob o lock, fazer o I/O fora, revalidar sob o lock antes de trocar.

---

### 11.8 🟠 P1-B — Logout e expiração de sessão não desconectam o transporte privilegiado

**Arquivos:** `handlers/auth.py:22-39` e `app_state.py:34-45`

Resetam `_access_role` e reconstroem a UI, mas **nunca chamam `self._sb.disconnect()`**. O canal SSH autenticado com as credenciais *elevadas* do equipamento continua vivo depois que o usuário fez logout ou expirou.

**Correção:** chamar `self._sb.disconnect()` no logout e na expiração do `SessionTracker`.

---

## 12. Achados de backend — P2 (robustez)

| # | Local | Achado | Correção |
|---|---|---|---|
| 12.1 | `session_factory.py:162-166` | ⚠️ **CORRIGIDO — era um falso positivo meu.** `purge_expired` itera sobre `list(self._pool.items())`, que é um **snapshot**; logo **não** ocorre `RuntimeError: dictionary changed size during iteration`. Confirmado em stress test com 16 threads × 300 ops + 240 `purge_expired()`: **0 exceções**. Resta apenas uma corrida benigna entre o snapshot e o `release()` (uma entry pode ser fechada nesse intervalo) — **severidade real: P3, não P1**. | Nenhuma correção necessária; se quiser, mover o snapshot para dentro do lock |
| 12.2 | `app_threading.py:27-40` | Race check-then-act em `_ui_queue`: `len(...) >= maxlen` e `append` não são atômicos entre as threads IO/watcher/UI. Com deque cheio, `append` descarta silenciosamente o callback **mais antigo**. | `try: self._ui_queue.append(fn) except IndexError:` e remover o pre-check |
| 12.3 | `session_commands.py:19,35,95` | `read_timeout=120` hardcoded e independente do `SSH_TIMEOUT` de conexão (`session.py:144-147,190`); `banner_timeout`/`blocking_timeout` nunca configurados (defaults netmiko 15s/20s). Um comando pode segurar um worker por 2 minutos sem checagem de política. | `ConnectionConfig` única / `read_timeout` no nível da sessão |
| 12.4 | `pages/manutencao.py:303-315`, `466-478` | O loop `for line in proc.stdout` bloqueia até o filho fechar o pipe; `proc.wait(timeout=180)` (linha 315) / `timeout=120` (478) só é alcançado **depois** do loop. Filho travado com pipe aberto = worker pendurado para sempre. | Ler com deadline numa thread, ou impor o wall clock dentro do loop |
| 12.5 | `manutencao.py:333`, `496` | Handle de cancelamento sobrescrito por worker obsoleto: se a execução B começou depois do cancelamento de A, o `finally` de A zera o handle de B e B fica incancelável. | Capturar o `Event` e limpar só se ainda for o atual |
| 12.6 | `handlers/fetch.py:114` | `intf_entries = self._drv.get_interfaces()` fica **fora** do tratamento de erro; um `SdnError` propaga e deixa o painel preso em "⏳ Carregando…" para sempre. | Envolver em `try/except SdnError` e escrever o erro |
| 12.7 | `polling_manager.py:41-43` | Detecção de erro por **prefixo de texto localizado** (`"Unknown command"`, `"Sem conex"`). Se o idioma mudar ou o device responder em inglês, falha silenciosamente. | Código de saída ou sentinel estruturado |
| 12.8 | `session_factory.py:124-150` | `get()` faz check-then-create não-atômico. O perdedor é fechado corretamente em 147-149 — apenas handshakes desperdiçados. | Aceitável; opcionalmente um lock por device |

### Verificados como **corretos** (não corrigir)

- API do Netmiko 4.4: `session_log`, `conn_timeout`, `timeout`, `fast_cli` são todos válidos; nenhum kwarg inexistente. `fast_cli=True` já é o default 4.4.
- `send_config_set` sem `config_mode_command` é correto — `HuaweiBase.config_mode()` usa `system-view`.
- Sem `shell=True` em lugar nenhum. Sem interpolação de SQL. Sem `timeout=None`.
- `verify_password` usa Argon2 `PasswordHasher.verify` — sem comparação de segredo em texto puro.
- `_cmd` não toma `self._lock` de propósito: os 3 call sites já a seguram, e a lock é não-reentrante.
- `SdnError` é usada corretamente como base das 4 subclasses.

---

# PARTE 3 — FRONTEND (Qt, widgets, ciclo de vida)

Auditoria dos módulos de UI, widgets, topologia e temas. Método: leitura integral + **reproduções em runtime contra o `HuaweiRouterApp` real** (PySide6 6.10.3, offscreen).

## 13. Bugs de frontend — P0

### 13.1 🔴 F0-1 — `closeEvent` inalcançável (já detalhado em 3.1)

Ver e diff em **3.1**. Resumo: `app.py:61` `class AppCore(QMainWindow, ThreadingMixin, NotifyMixin)` → `QWidget.closeEvent` vence no MRO → `_on_close()` nunca roda. Medido com tarefa de 6s em voo: `close()` retorna em **0,00s**, processo leva **7,2s** para sair.

### 13.2 🔴 F0-2 — Enter e Shift+Enter **nunca** funcionam no editor de comandos

**Arquivo:** `src/huawei_manager/pages/cmd.py:143-144`

```python
cmd_filter = _CmdReturnFilter(self)          # ← variável local
self._cmd_editor.installEventFilter(cmd_filter)
```

`cmd_filter` é uma **local**. O filtro é um `QObject` **sem pai**, e `installEventFilter` do PySide6 **não** adquire ownership nem guarda referência Python. O objeto é coletado pelo GC assim que `_build_cmd_page` retorna.

**Prova (weakref + `gc.collect()`):**
```
isParent() == None ?  True
objeto sobrevive apos del+gc ?  False   <-- o filter MORRE
```

**Reprodução no app real** (`QTest.keyClick`, editor com foco, conteúdo `"display version"`):

| Tecla | `_run_cmd_safe` chamado | Texto do editor depois |
|---|---|---|
| Enter | `[]` | `'\ndisplay version'` |
| Shift+Enter | `[]` | `'\n\ndisplay version'` |
| Enter, **filter mantido vivo** | `['display version']` | inalterado |
| Shift+Enter, filter vivo | `[]` | `'\ndisplay version'` (quebra de linha) |

Enter está morto e a quebra de linha é inserida na **posição 0**.

> `tests/test_editor_enter.py` passa **17/17** porque exercita a classe do filtro isoladamente, mantendo a referência. O teste não pode observar o bug de ciclo de vida.

```diff
--- a/src/huawei_manager/pages/cmd.py
+++ b/src/huawei_manager/pages/cmd.py
@@ -143,2 +143,3 @@
-        cmd_filter = _CmdReturnFilter(self)
+        cmd_filter = _CmdReturnFilter(self)
+        cmd_filter.setParent(self)   # pai = app -> o C++ assume a posse
         self._cmd_editor.installEventFilter(cmd_filter)
```

### 13.3 🔴 F0-3 — `_rebuild_ui` deixa referências obsoletas: `RuntimeError` e output perdido

**Arquivo:** `src/huawei_manager/app.py:592` — zera apenas `_active_btn`, `_topo_canvas`, `self.pages` e `self.content`. **Todo o resto sobrevive** apontando para objetos C++ que `old.deleteLater()` já destruiu.

**Reprodução** (Services → Home → `_rebuild_ui()` → `sendPostedEvents(DeferredDelete)`):
```
RuntimeError: Internal C++ object (PySide6.QtWidgets.QListWidget) already deleted.
  origem: src/huawei_manager/pages/services.py:183   self._svc_listbox.clear()
```

A mesma classe de falha **descarta resultados assíncronos silenciosamente** — `app_threading.py:96-100`:
```python
def _write(self, widget, text: str) -> None:
    self._dispatch(lambda w=widget, t=text: (w.clear(), w.setPlainText(t)))
```
O widget é capturado por valor no momento do dispatch, mas o poll de 50ms roda **depois** do rebuild ter deletado ele. Verificado:
```
[ERROR] huawei.app — _poll_queue: callback <..._write.<locals>.<lambda>> falhou
  app_threading.py:49  fn()
  app_threading.py:97  (w.clear(), w.setPlainText(t))
RuntimeError: Internal C++ object (PySide6.QtWidgets.QTextEdit) already deleted.
```
O usuário roda um comando, a janela reconstrói, e **o output nunca aparece** — a única pista é uma exceção num arquivo de log.

Atributos afetados: `_svc_listbox`, `_svc_output`, `_svc_device_lbl`, `_svc_type_lbl`, `_svc_cat_cb`, `_svc_detail_frame`, `_svc_param_entries`, `_dash_*`, `_manut_*`, `_cmd_editor`, `_backup_entry`, `_auth_overlay`, `_router_ip`.

```diff
--- a/src/huawei_manager/app.py
+++ b/src/huawei_manager/app.py
@@ def _rebuild_ui(self)
         self._active_btn = None
         self._topo_canvas = None
         self.pages.clear()
+        # Invalida toda referencia a widget antes de destruir a arvore.
+        for attr in (
+            "_svc_listbox", "_svc_output", "_svc_device_lbl", "_svc_type_lbl",
+            "_svc_cat_cb", "_svc_detail_frame", "_svc_param_entries",
+            "_dash_conn_status", "_dash_conn_host", "_dash_device_online",
+            "_dash_device_offline", "_dash_device_unknown", "_dash_audit_text",
+            "_dash_shortcut_btns", "_manut_filter", "_manut_log",
+            "_cmd_editor", "_backup_entry", "_auth_overlay", "_router_ip",
+        ):
+            if hasattr(self, attr):
+                setattr(self, attr, None)
```

E endurecer o destino do dispatch para nunca mais perder output:
```diff
--- a/src/huawei_manager/app_threading.py
+++ b/src/huawei_manager/app_threading.py
@@ def _write(self, widget, text)
-        self._dispatch(lambda w=widget, t=text: (w.clear(), w.setPlainText(t)))
+        self._dispatch(lambda: self._safe_write(widget, text))
+
+    def _safe_write(self, widget, text: str) -> None:
+        # ATENCAO: os DOIS except sao necessarios. Medido em stress test:
+        #   - objeto C++ destruido pelo rebuild -> RuntimeError
+        #   - atributo Python removido            -> AttributeError
+        if widget is None:
+            return
+        try:
+            widget.clear()
+            widget.setPlainText(text)
+        except (RuntimeError, AttributeError):   # widget morto por um rebuild
+            _app_log.debug("_safe_write: widget destruido por rebuild — descartado")
```

> ⚠️ **Autocorreção:** a primeira versão deste patch capturava só `RuntimeError`. O stress test (§19.4) mostrou que o modo de falha predominante é **`AttributeError`** — a referência Python do widget some do `__dict__` do `AppCore` quando o `deleteLater()` é processado. Sem os dois `except`, o patch não corrige nada.

### 13.4 🔴 F0-4 — Devices abaixo da dobra são inalcançáveis na topologia

**Arquivo:** `src/huawei_manager/topology.py:110-111` desliga as duas barras de rolagem, e `:199-200` define um `sceneRect` maior que o viewport:

```python
self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
...
max_y = start_y + (n // cols) * (self.NODE_H + pad_y) + self.NODE_H + 40
self._scene.setSceneRect(0, 0, w, max(float(max_y), float(vh)))
```

Sem scrollbar, sem drag-to-pan, sem zoom. **Medido com 40 devices em viewport 1000×620:**
```
sceneRect: 1000 x 1150
node y range: 100 .. 946  (10 linhas)
nodes com borda inferior abaixo do viewport: 16 de 40
vScroll range: 530   (mas a barra esta AlwaysOff)
itens realmente renderizados: 192 de 288
```

Esses 16 devices não podem ser vistos, selecionados, editados nem excluídos.

```diff
--- a/src/huawei_manager/topology.py
+++ b/src/huawei_manager/topology.py
@@ class _TopoView.__init__
         self._canvas = canvas
+        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
+        self.setTransformationAnchor(
+            QGraphicsView.ViewportAnchor.AnchorUnderMouse)

@@ -110,2 +112,2 @@
-        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
-        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
+        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
+        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

@@ -199,2 +201,3 @@
-        max_y = start_y + (n // cols) * (self.NODE_H + pad_y) + self.NODE_H + 40
+        rows = (n + cols - 1) // cols      # ceil, nao n // cols
+        max_y = start_y + (rows - 1) * (self.NODE_H + pad_y) + self.NODE_H + 40
```

### 13.5 🔴 F0-5 — `_event_drop_count` nunca inicializado: `AttributeError` no timer

**Arquivo:** `src/huawei_manager/app_threading.py:26-40`

```python
if maxlen is not None and len(self._ui_queue) >= maxlen:
    if sdn:
        self._event_drop_count += 1        # 30 — atributo NUNCA inicializado
```

Busca em todo o `src/`: a única atribuição está no **fake de teste** (`tests/test_app_threading.py:35`). `app.py` e `_init_common_attrs` nunca definem. `_protocols.py:37` é só uma declaração de `Protocol`, sem efeito em runtime.

**Reprodução verificada:**
```
tem _event_drop_count? -> False
>>> AttributeError: 'HuaweiRouterApp' object has no attribute '_event_drop_count'
```

Com a fila de UI cheia e `sdn=True`, a linha 30 levanta `AttributeError` dentro do callback do `QTimer`. Isso **aborta o resto do loop de drenagem** (53-62) **a cada 50ms** — o pipeline SDN fica permanentemente travado sob carga, com um traceback por tick.

```diff
--- a/src/huawei_manager/app.py
+++ b/src/huawei_manager/app.py
@@ -207,2 +207,3 @@
         self._devices_lock = threading.Lock()
+        self._event_drop_count = 0
```

E tornar o contador à prova de falha:
```diff
--- a/src/huawei_manager/app_threading.py
+++ b/src/huawei_manager/app_threading.py
@@ -29,2 +29,2 @@
             if sdn:
-                self._event_drop_count += 1
+                self._event_drop_count = getattr(self, "_event_drop_count", 0) + 1
```

## 14. Bugs de frontend — P1

| # | Local | Bug | Correção |
|---|---|---|---|
| **14.1** | `app_shortcuts.py:148-150` | **`Ctrl+K` é no-op.** `ShortcutsMixin._toggle_command_palette` é um stub `pass` e o MRO é `AppStateMixin → ShortcutsMixin → AppCore` — o stub **vence**. Verificado: `HuaweiRouterApp._toggle_command_palette is ShortcutsMixin._toggle_command_palette` → `True` | Deletar o stub em `app_shortcuts.py:148-150` |
| **14.2** | `command_palette.py:415` | **"Copiar IP" chama método inexistente.** `app._notify(...)` não existe no `HuaweiRouterApp` nem em nenhum mixin/handler (único match: `event_queue.py:140`, API não relacionada). Copia o IP e morre com `AttributeError` | Trocar por um helper tolerante que faz log se não houver notificador |
| **14.3** | `auth_overlay.py` (parent) + `app_shortcuts.py:142-146` | **Todo atalho global quebra com overlay obsoleto.** O overlay é filho de `self.content`, que `_rebuild_ui` destrói; `_auth_overlay` nunca é resetado e os atalhos não têm `try/except`. Verificado: `_on_ctrl_l`, `_on_escape`, `_on_enter`, `_on_f5`, `_on_ctrl_shift_a` → todos `RuntimeError: Internal C++ object (AuthOverlay) already deleted`. `handlers/auth.py:41-45` já protege — os atalhos não | `try/except RuntimeError` nos atalhos + `_auth_overlay` na lista de reset do 13.3 |
| **14.4** | `audit_log.py:324-349` via `dashboard.py:17-43` | **Dashboard lê o arquivo de auditoria inteiro na thread GUI, a cada 5s.** `self._path.read_text()`. Medido: 10 MiB → 39,4ms / 22 MiB; **200 MiB → 1021,4ms e 521 MiB de RAM**, a cada 5 segundos, para sempre | `deque(self._path.open(...), maxlen=n*4)` + rotacionar o arquivo do `AuditLogger` |
| **14.5** | `session.py:239-241` via `dashboard.py` e `app_threading.py:83` | **I/O de socket bloqueante na thread GUI.** `is_alive()` do netmiko faz leitura de canal; o cache de 2s de `southbound.py:162-178` **sempre** expira porque o timer do dashboard é de 5s. Provado: `sb.is_alive()` bloqueou a thread por 800ms com transporte travado, e a thread era `MainThread` | Sondar fora da thread GUI; o timer só cacheia o último resultado |
| **14.6** | `widgets/auth_overlay.py` | **Overlay não é modal nem bloqueia clique.** `setWindowModality` em **widget filho** é ignorado pelo Qt. Verificado: `isWindow(): False`, `modalWindow(): None`, `activeModalWidget(): None`, e cliques atravessaram. Também não há `mousePressEvent`, então o clique propaga para os widgets de baixo | `Qt.WindowType.Dialog` + `mousePressEvent` que faz `accept()` |
| **14.7** | `device_dialog.py:219-225` | **Porta inválida é reescrita silenciosamente para 22**, sem aviso. Sem `QIntValidator`. Medido: `'abc'`, `'0'`, `'70000'`, `'22a2'`, `'-1'`, `'999...9'` → **todos aceitos como 22**. Errar a porta de gerência redireciona o device para a 22 | `QIntValidator(1, 65535)` + erro visível |
| **14.8** | `auth_overlay.py:152-173` | **Argon2 + nova conexão SQLite por tentativa, na thread GUI.** `conn` nunca é fechado → **um descritor de arquivo vazado por tentativa**. No primeiro boot, `seed_default_users()` roda 3 hashes → UI congelada | Mover para thread + `conn.close()` no `finally` |
| **14.9** | `topology.py:66-68` | **Reconstrução completa da cena a cada `resizeEvent`.** `resizeEvent` chama `_canvas._draw()`, que faz `self._scene.clear()` e recria tudo, incluindo um `QGraphicsDropShadowEffect` novo por nó. Medido com 60 devices: **60 redraws = 2732,3ms (45,5ms cada), 409 itens recriados** por vez. Arrastar a janela 60px custa 2,7s | Só re-layoutar se o número de colunas mudou; `set_device_status` deve atualizar o item, não redesenhar |
| **14.10** | `topology.py:126-133` | **Apagar o último device o deixa no canvas.** `if not devices and self._devices: return` trata lista vazia como espúria. Verificado: `update_devices([one])` → 1; `update_devices([])` → **ainda 1** | Aceitar lista vazia e limpar o canvas |

## 15. Achados de frontend — P2

| # | Local | Achado |
|---|---|---|
| 15.1 | `services.py:176` | `QTimer.singleShot(500, ...)` nunca cancelado; após rebuild dispara contra o listbox deletado (traceback confirmado) |
| 15.2 | `themes/__init__.py:60-66` | `QLabel[dim="true"]` / `[code="true"]` são **regras mortas** — nenhum `setProperty()` existe em `src/`. Verificado: sem a propriedade o label fica `#000000`; com `setProperty("dim", True)` vira `#6a6a9a` |
| 15.3 | `device_dialog.py:202-217` | O stylesheet de erro vermelho nunca é resetado — após um save falho e um corrigido, os campos ficam vermelhos para sempre |
| 15.4 | `topology.py:342` | `QMenu(self)` sem pai e nunca deletado. Verificado: 20 menus não referenciados → `findChildren(QMenu)` retorna 40. **Um vazamento por clique direito** |
| 15.5 | `app.py:295-298` | Logo de 62×61 espremido em 62×40 pelo `setFixedHeight(56)`; `hasScaledContents()` é `False` → **logo achatado 34% verticalmente** |
| 15.6 | `app_state.py:16-19` | `self._topo_canvas.set_device_status(...)` sem guarda de `None`; `_rebuild_ui` põe `_topo_canvas = None`, então um evento SDN fora da página Topologia levanta `AttributeError` (engolido em `:24-25`) |
| 15.7 | `device_dialog.py:230-252` | Sem validação de `username` (aceita vazio) nem de lista `device_types` vazia (grava `type: ""`) |
| 15.8 | 12× `except: pass` | `_config.py:49,115` · `app.py:75,302,371` · `audit_log.py:345` · `manutencao.py:331,494` · `auth_overlay.py:235` · `neon_button.py:79` · `neon_entry.py:74` · `agents/scans/security.py:83`. A maioria é legítima, mas **`audit_log.py:345` e `_config.py:49` silenciam falhas de auditoria/segurança** — deveriam logar em `warning` |

### Verificados como **corretos** (não corrigir)

- **Nomes de método duplicados no MRO:** varredura AST achou só 2 colisões não triviais. `app.py:471-474` `_make_page` → `super()._make_page()` → `builder.py:38` é o padrão de delegação correto. `_toggle_command_palette` é a **exceção** — ver 14.1, é um bug real.
- ** afinidade de thread dos workers:** todos os pontos de entrada revisados fazem I/O ou trabalho Python puro fora da thread e marshalam escritas de UI via `_dispatch`/`_loading`/`_write`. A exceção é `_run` em `app_threading.py:83` (ver 14.5).
- **Ciclo de vida de `QShortcut`:** `app_shortcuts.py` e `command_palette.py` não guardam referência Python, mas cada `QShortcut` tem um widget pai — o pai C++ possui o objeto. Verificado com weakref: sobrevive. **Não é** o mesmo que 13.2, onde o filtro é um `QObject` sem pai.
- **Seletor `ActionButton` no QSS:** `neon_button.py:43` usa `ActionButton { ... }` sem `Q_PROPERTY`/`setObjectName`. O PySide6 casa pelo nome da subclasse Python — medido: `sizeHint` 110px para `"  CONECTAR  "` vs 41px para `"x"`, o `padding: 6px 16px` **é** aplicado.
- **`ActionButton:hover` desabilitado:** ignora `_disabled` na regra `:hover`, mas `setEnabled(False)` faz o Qt nunca marcar `State_MouseOver`. Medido: enabled+hover `#00e5ff`, disabled+hover `#1a1a30` (`BG_INPUT`). Sem vazamento.
- **Foco do Command Palette com `WA_ShowWithoutActivating`:** é uma janela `Tool` real; medido `isActiveWindow() == True`, `search.hasFocus() == True` após `showEvent`, digitação funciona, Enter dispara a ação.
- **Sanitização de parâmetros na página Serviços:** `handlers/services.py:82-93` rejeita `[;&|`$(){}]` por parâmetro e `:102` re-valida o comando substituído via `_validate_service`, com entrada de auditoria para cada negação. Sólido.
- **Crescimento de itens em `draw_background_grid`:** `topology_effects.py:23-45` adiciona linhas sem limpar, mas só é chamada de `_draw` logo após `scene.clear()` (`topology.py:157`). Sem vazamento — o custo é a frequência de reconstrução (14.9).
- **Enter no `DeviceDialog`:** o diálogo é `setModal(True)` e o Qt atribui o botão default automaticamente (`isDefault()` é `True`); Enter aceita.
- **`ElideLabel`, `AuthOverlay`:** todos os overrides de `paintEvent`/`resizeEvent`/`keyPressEvent` chamam `super()` corretamente. Nenhum `super()` faltando encontrado.

## 16. Por que a suíte de testes não pega nada disso

| Teste | Passa | Bug que não pega | Motivo |
|---|---|---|---|
| `test_editor_enter.py` | 17/17 | F0-2 (Enter morto) | Constrói `_CmdReturnFilter` direto e mantém a referência — nunca observa o bug de lifetime |
| `test_app_threading.py:380` | ✅ | 3.1 (`closeEvent`) | `_NotifyFakeApp(NotifyMixin, _FakeBase)` — MRO **oposto** ao da classe real |
| `test_pages_resize.py` | ✅ | 14.9 / F0-4 | Não exercita o `HuaweiRouterApp` real |
| `test_state_labels.py` | ✅ | 13.5 | `_event_drop_count` só existe no fake |
| suíte completa | 1075 ✅ | 10 P0 | Fakes com MRO e ciclo de vida diferentes da produção |

**Testes de regressão que fechariam as lacunas:**

```python
# F0-2: precisa do app real
app = HuaweiRouterApp(); app._show_page("cmd")
app._cmd_editor.setPlainText("display version"); app._cmd_editor.setFocus()
QTest.keyClick(app._cmd_editor, Qt.Key.Key_Return)
assert calls == ["display version"]        # falha antes do fix de 13.2

# 3.1: resolução de MRO
def test_close_event_nao_e_sombreado(self) -> None:
    assert HuaweiRouterApp.closeEvent is NotifyMixin.closeEvent

# F0-5: atributo existe
def test_event_drop_count_inicializado(self) -> None:
    app = HuaweiRouterApp()
    assert app._event_drop_count == 0

# 14.1: stub removido
def test_ctrl_k_abre_palette(self) -> None:
    assert HuaweiRouterApp._toggle_command_palette is AppCore._toggle_command_palette

# 11.1: bypass de RBAC
def test_multilinha_bloqueado_para_user(self) -> None:
    v = CommandValidator()
    r = v.validate("display version\nreset saved-configuration", role="user")
    assert r.allowed is False
```

---

## 17. Ordem de aplicação revisada (com backend e frontend)

| # | Ação | Arquivo | Risco |
|---|---|---|---|
| 1 | **Bloquear comando multi-linha no validator** | `validator.py:96-101` | Baixo |
| 2 | **Injetar validator no transporte** | `app.py:84` | Baixo |
| 3 | Reordenar bases do `AppCore` (MRO) | `app.py:61` | Baixo |
| 4 | `setParent` no filtro de eventos | `pages/cmd.py:143` | Baixo |
| 5 | Inicializar `_event_drop_count` | `app.py:208` | Baixo |
| 6 | Trocar `except RuntimeError` → `SdnError` (10×) | `handlers/*.py` | Médio |
| 7 | Zenar refs de widget + `_ui_queue.clear()` no rebuild | `app.py:592`, `app_threading.py:97` | Médio |
| 8 | Deletar o stub `_toggle_command_palette` | `app_shortcuts.py:148-150` | Baixo |
| 9 | Corrigir `send_service_commands` (try/finally + `return`) | `southbound.py:268-285` | Médio |
| 10 | `except SdnError` propagando em vez de `"ERRO: …"` | `session_commands.py:15-23` | Médio |
| 11 | Scrollbars da topologia + ceil de linhas | `topology.py:110-111,199` | Baixo |
| 12 | `_notify` inexistente no palette | `command_palette.py:415` | Baixo |
| 13 | Escape do emoji | `topology.py:358` | Baixo |
| 14 | Prefixo `f` + `NEON_RED` | `auth_overlay.py:98` | Baixo |
| 15 | `try/except RuntimeError` nos atalhos | `app_shortcuts.py:142-146` | Baixo |
| 16 | Fechar conexão SQLite no `_verify` | `auth_overlay.py:152-173` | Baixo |
| 17 | `read_timeout` único no nível da sessão | `session_commands.py` | Médio |
| 18 | `release()` no erro do poller | `polling_manager.py:253` | Baixo |
| 19 | `tail()` sem ler o arquivo inteiro | `audit_log.py:324` | Médio |
| 20 | Remover `skips = ["B101"]` | `pyproject.toml:57` | Baixo |

**Itens 1-5** fecham os 5 P0 mais graves com risco baixíssimo. **Item 1 é o mais urgente** — é o único com impacto de segurança.

---

## 18. Comandos de verificação (estendidos)

```bash
cd /home/aluno20/Huawei-Manager-2.0

# 1. Bypass de RBAC (P0-S) — deve imprimir allowed=False
.venv/bin/python -c "
import sys; sys.path.insert(0,'src')
from huawei_manager.sdn_controller.validator import CommandValidator
r = CommandValidator().validate('display version\nreset saved-configuration', role='user')
print('allowed:', r.allowed)
assert r.allowed is False, 'BYPASS AINDA EXISTE'
"

# 2. MRO do closeEvent e do Ctrl+K
QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
import sys; sys.path.insert(0,'src')
from huawei_manager.app import HuaweiRouterApp, AppCore
from huawei_manager.app_notify import NotifyMixin
from huawei_manager.app_shortcuts import ShortcutsMixin
print('closeEvent  ok:', HuaweiRouterApp.closeEvent is NotifyMixin.closeEvent)
print('Ctrl+K      ok:', HuaweiRouterApp._toggle_command_palette is AppCore._toggle_command_palette)
"

# 3. _event_drop_count
QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
import sys; sys.path.insert(0,'src')
from huawei_manager._config import init; init()
from huawei_manager._app import get_app, apply_theme
from huawei_manager.app import HuaweiRouterApp
app=get_app(); apply_theme('dark'); w=HuaweiRouterApp()
assert w._event_drop_count == 0; print('ok')
"

# gates
.venv/bin/ruff check src/huawei_manager/
.venv/bin/python -m pytest tests/ -q --cov=src/huawei_manager --cov-fail-under=60
.venv/bin/pyright
```

**Estado atual esperado (antes dos fixes):**
```
allowed: True      <-- BYPASS
closeEvent  ok: False
Ctrl+K      ok: False
AssertionError     <-- _event_drop_count
```

---

---

# PARTE 4 — STRESS TESTS

Auditoria de carga: fuzz, saturação de filas, concorrência, escala e teardown. Objetivo duplo — (a) medir o impacto dos bugs já documentados e (b) **auditar o próprio relatório**, porque os números de stress test expuseram erros nas correções propostas.

**Harness:** PySide6 6.10.3 `offscreen`, app real (`HuaweiRouterApp`), sem mocks de MRO. Quando o teste depende de SSH/secrets, isso está declarado como limitação.

> **A Parte 4 mudou este documento.** Os stress tests encontraram **4 erros nas correções que eu mesmo propus** (§21) — o mais grave: a correção de §11.1 **não fechava o bypass**, porque o VRP também aceita `;` como separador de comandos. Todos foram corrigidos no texto.

## 19. Resultados

### 19.1 `CommandValidator` — fuzz de 200k + ReDoS: **robusto**

| Teste | Resultado |
|---|---|
| ReDoS: 8 payloads adversariais até 160.000 chars | pior caso **2,68 ms** — **sem ReDoS** |
| Fuzz: 200.000 entradas aleatórias | 1,2 s · **0 exceções** · **0 bypasses de linha única** |
| Throughput: 20.000 `display interface …` | 0,03 s = **718.884/s** (1,4 µs cada) |

Alfabeto do fuzz: `\t \n \r ; | ? & < > / * ' " \` $ ( ) { } [ ]` + `display`, `show`, `reset`, `saved-configuration`, `format`, `flash`, `undo`, `startup`, `delete`, `system-view`, `quit`, `return`, `--`, `#`, `!`.

**Por que não há ReDoS:** nenhum dos 7 padrões (`validator.py:15-27`) tem quantificador aninhado — são `^display\s+`, `^format\s+flash`, `\bdelete\b` etc. Sem retrocesso catastrófico.

**Conclusão:** o validador é **robusto**. O defeito de §11.1 é **puramente de lógica de política** (ordem allow/deny), não de robustez de regex. Isso é bom: significa que a correção da §11.1 é uma mudança pequena e bem-acotada.

### 19.2 Fuzz de separadores — **o teste que invalidou meu próprio fix**

| Payload (todas com `role="user"`) | `allowed` | Sobrevive ao fix "só bloquear `\n`"? |
|---|---|---|
| `display version\nsystem-view\nreset saved-configuration` | `True` | ❌ bloqueado |
| `display version;system-view;reset saved-configuration` | `True` | 🔴 **CONTINUA PASSANDO** |
| `display version ; system-view ; reset saved-configuration` | `True` | 🔴 **CONTINUA PASSANDO** |
| `display version\rsystem-view\rreset saved-configuration` | `True` | ❌ bloqueado |
| `display\tversion;reset saved-configuration` | `True` | 🔴 **CONTINUA PASSANDO** |
| `display cpu-usage \| include cpu` (pipe legítimo) | `True` | ✅ deve continuar permitido |
| `;reset saved-configuration` (isolado) | `False` | ✅ bloqueado |

**Achado:** o `;` é separador de comandos no VRP e **não** é `\n`. A correção original de §11.1 **não fechava o bypass**. Substituída pela versão "dividir em comandos lógicos" em §11.1.

### 19.3 🔴 ST-1 (P1, NOVO) — Log flood: o backpressure se anula sozinho

**Arquivos:** `event_queue.py:100-102` e `app_threading.py:31-38` — um `WARNING` **por evento descartado**, sem rate limiting.

```
200.000 put() com a fila cheia (maxsize=1000)
  -> 5,82 s            (34.368 put/s — o gargalo é o logging, não a fila)
  -> 199.000 linhas WARNING
  -> 11,9 MiB de log  (2,0 MiB/s)
  -> extrapolado: 122 MiB/min  |  7,2 GiB/h
```

O mecanismo de descarte existe **para** aliviar a pressão. Logar por descarte transforma o alívio em carga: o `RotatingFileHandler` síncrono (`_config.py:83-86`, 5 MB × 3) rotaciona a **2,5 s** por arquivo, então **o histórico diagnóstico inteiro (20 MB) é substituído a cada ~10 s durante o flood**.

> **Isto destrói a evidência forense exatamente quando ela é necessária** — durante um incidente de overwhelm, o log que deveria explicar a causa já foi sobrescrito 300 vezes.

Pior: o **`AuditLogger` não tem rotação** (`audit_log.py` não importa `RotatingFileHandler`) — o JSONL cresce sem limite, e é justamente ele que o dashboard lê a cada 5 s (§19.9).

```diff
--- a/src/huawei_manager/sdn_controller/event_queue.py
+++ b/src/huawei_manager/sdn_controller/event_queue.py
@@ class EventQueue
+        self._drop_log_every = 100          # 1 linha a cada 100 descartes
+        self._dropped_since_log = 0
+
     def put(self, event, block=True, timeout=0.5) -> None:
         try:
             self._queue.put(item, block=block, timeout=timeout)
         except queue.Full:
-            _LOG.warning("EventQueue cheia (%d), descartando %s/%s",
-                         self._queue.maxsize, event.type.name, event.source)
+            self._dropped_since_log += 1
+            if self._dropped_since_log % self._drop_log_every == 1:
+                _LOG.warning("EventQueue cheia (%d): %d descartos desde o ultimo log",
+                             self._queue.maxsize, self._dropped_since_log)
             return
```

Aplicar o mesmo padrão em `app_threading.py:31-38`. E **rodar a rotação do audit log** (ou trocar `tail()` por leitura em streaming, §19.9).

### 19.4 🔴 ST-2 (P1, NOVO) — F0-5 é pior do que "perde um evento"

```
8 threads × 5.000 _dispatch(sdn=True) + 30 _rebuild_ui() concorrentes
  -> 39.500 AttributeError  (98,75% de tudo que encontrou a fila cheia)
  -> _shutdown/_event_drop_count ausente

Mesmíssimo cenario com sdn=False
  -> 0 exceções
```

**Leitura:** com `sdn=False` o caminho de descarte é silencioso e inofensivo. Com `sdn=True` (todo evento do barramento SDN), **cada dispatch que encontra a fila cheia levanta `AttributeError`**. E como a exceção sai da linha 30 — antes do `append` — **o callback nunca entra na fila**: o evento é perdido *e* o traceback é gerado. Pior, a exceção aborta o restante de `_poll_queue` (`app_threading.py:43-62`) naquele tick.

O fix de §13.5 (inicializar o atributo) resolve, mas o `+=` continua sendo **read-modify-write não-atômico** entre 8 threads. Usar `itertools.count` ou proteger com o lock.

### 19.5 🟠 ST-3 (P1, NOVO) — Teto de vazão e perda silenciosa de 95,8%

| Parâmetro | Valor | Teto efetivo |
|---|---|---|
| `maxlen` da `_ui_queue` | 1.000 (medido) | — |
| `_POLL_BATCH` (`app_threading.py:14`) | 500 por tick de 50 ms | **10.000 callbacks/s** |
| `_EVENT_BATCH` (`app_threading.py:17`) | 50 por tick de 50 ms | **1.000 eventos/s** |

```
24.000 _dispatch() submetidos de 8 threads
  -> 1.000 sobrevivem na fila
  -> 23.000 descartados (95,8%) SEM RASTRO no output do usuario
```

O `deque(maxlen=1000)` descarta **o mais antigo** quando cheio, e o check-then-act de `app_threading.py:27-28` é racioso. O sintoma para o usuário é um dashboard que **para de atualizar** sem erro, sem aviso e sem log de nível operável.

### 19.6 🟠 ST-4 (P1) — Perda de output quantificada (§13.3)

```
20.000 _write() × 30 _rebuild_ui() COM DeferredDelete processado
  -> 1.000 callbacks falharam (5,0%), todas "Internal C++ object ... already deleted"
  -> 1.000 = exatamente o maxlen  -> perda limitada pelos callbacks pendentes

Mesmo teste SEM processar DeferredDelete
  -> 0 falhas
```

**O bug é intermitente por natureza:** só se manifesta quando o event loop realmente executa os `deleteLater()`. Numa máquina lenta ou sob carga, simula um defeito que "aparece sozinho". Isso explica por que nunca foi reportado por usuário.

### 19.7 🔴 ST-5 (P1) — Escala da topologia: linear, e 1000 devices são inalcançáveis

| devices | `update_devices` | `_draw()` (redraw) | `sceneRect` | itens na cena |
|---|---|---|---|---|
| 40 | 100,9 ms | 15,8 ms | 924×**1.150** | 283 |
| 100 | 58,5 ms | 37,5 ms | 924×**2.560** | 643 |
| 250 | 90,4 ms | 93,7 ms | 924×**6.038** | 1.543 |
| 500 | 186,0 ms | 195,3 ms | 924×**11.960** | 3.043 |
| 1.000 | 387,3 ms | **429,9 ms** | 924×**23.710** | 6.043 |

Crescimento **linear, ~0,43 ms por device**. Um inventário de 1.000 routers (razoável para um NOC) custa **430 ms de congelamento por redraw**.

E o pior: com `scrollBarPolicy = AlwaysOff` **e** `dragMode = NoDrag` (ambos medidos), numa janela de 740 px cabem ~26 dos 1.000 nodes. **974 dispositivos não podem ser vistos, selecionados, editados nem excluídos.** Não há zoom, não há pan, não há scrollbar, não há minimapa.

Confirmado junto: `update_devices([])` deixa os 49 itens anteriores no lugar, e o log registra
`update_devices: ignorando lista vazia (existem 1000 Devices)` — **não há como esvaziar a topologia pela UI**.

### 19.8 🔴 ST-6 (P1) — `resizeEvent` reconstrói a cena inteira

```
60 resize() consecutivos, 1.000 devices na cena
  -> 24,9 s no total = 415 ms por resizeEvent
  -> arrastar a janela pela tela = 25 s de UI congelada

com 40 devices: 45,5 ms por resizeEvent
```

§14.9 quantificado. O `resizeEvent` → `_draw()` → `scene.clear()` → recriar 6.043 itens, incluindo um `QGraphicsDropShadowEffect` **novo por node**, a cada pixel de arrasto. Correção: re-layoutar só quando o número de colunas muda, e reaproveitar os itens existentes.

### 19.9 🟠 ST-7 (P2) — `tail()` lê o arquivo inteiro, na thread GUI, a cada 5 s

| entradas | tamanho | `tail(5)` | RAM pico |
|---|---|---|---|
| 40.000 | 12,0 MiB | 38,37 ms | ~24 MiB |
| 100.000 | 30,1 MiB | 95,93 ms | ~60 MiB |
| 420.000 | 126,3 MiB | **422,31 ms** | ~253 MiB |

**Linear: 3,35 ms por MiB.** O dashboard chama `audit.format_tail(5)` (`handlers/dashboard.py:43`) num `QTimer` de 5 s, e `AuditLogger.tail` faz `self._path.read_text()` do arquivo **inteiro** (`audit_log.py:330`) só para usar as 5 últimas linhas.

A 126 MiB isso já são **422 ms de congelamento a cada 5 segundos = 8,4% do tempo wall permanentemente travado**. O arquivo não tem rotação, então **degrada sem limite** até o app ficar inutilizável. A 1 GiB seriam 3,3 s por chamada.

E a escrita também é rápida: `log_operation` faz **12.668 entradas/s**, 20.000 entradas = 6,0 MiB. Um operador ativo gera ~6 MiB de audit por 1,6 s de atividade.

```diff
--- a/src/huawei_manager/audit_log.py
+++ b/src/huawei_manager/audit_log.py
@@ def tail(self, n)
-        lines = self._path.read_text(encoding="utf-8").splitlines()
+        # Le a cauda pela FRENTE: O(1) em memoria em vez de O(arquivo).
+        lines = deque(self._path.open(encoding="utf-8"), maxlen=n)
         entries = []
-        for line in reversed(lines):
+        for line in reversed(list(lines)):
```

### 19.10 ✅ ST-8 — Teardown confirmado (§3.1) em três escalas

| tarefas em voo (3 s cada) | `close()` retornou em | `_shutdown` |
|---|---|---|
| 10 | 0,5 ms | `False` |
| 100 | 0,7 ms | `False` |
| 500 | 0,6 ms | `False` |

`close()` é **instantâneo e idêntico** em todas as escalas: a teardown nunca executa, o que é a assinatura exata do `closeEvent` sombreado (§3.1). O processo fica pendurado até o último `ThreadPoolExecutor` drenar.

**Achado adicional (P3):** `_shutdown` é apenas **consultivo**. `_spawn_io` o respeita (`app_threading.py:67`), mas um `submit()` direto o ignora — medido: com `_shutdown=True`, `submit()` ainda executou a tarefa. Como `closeEvent` nunca liga o flag (§3.1), hoje isso é academicamente irrelevante, mas vira um vetor de corrida assim que §3.1 for corrigido.

### 19.11 ⚠️ ST-9 — `SSHSessionFactory` sob concorrência: 0 exceções, mas **teste inconclusivo**

```
16 threads × 300 ops  =  4.800 get() + 240 purge_expired() + 96 release()
  -> 0,2 s   -> 0 exceções   -> 'dictionary changed size' NÃO ocorreu
```

Isso **confirma a correção do item 12.1** (o snapshot via `list()` evita o `RuntimeError`).

**Limitação declarada:** sem um backend de secrets, `get()` retorna cedo e o `session_builder` **nunca é chamado** (0 sessões construídas para 40 device ids). Este teste **não** exercita o caminho de criação do pool — logo a corrida check-then-create de §12.8 permanece **não comprovada** (e não comprovada também como problema).

## 20. Achados novos de stress test

| # | Sev | Achado | Onde |
|---|---|---|---|
| **ST-1** | P1 | Log flood: 1 WARNING por descarte → 7,2 GiB/h; rotaciona o histórico diagnóstico inteiro a cada ~10 s | `event_queue.py:101`, `app_threading.py:31-38` |
| **ST-2** | P1 | F0-5 amplificado: 98,75% dos dispatches SDN com fila cheia levantam exceção; com `sdn=False` são 0 | `app_threading.py:30` |
| **ST-3** | P1 | Teto de 10.000 callbacks/s; 95,8% dos callbacks descartados sem rastro | `app_threading.py:14,27-28` |
| **ST-4** | P1 | Perda de output de 5,0% sob rebuild; intermitente conforme o loop executa `deleteLater()` | `app_threading.py:96-97` |
| **ST-5** | P1 | 1.000 devices → 430 ms por redraw e 974 inalcançáveis (sem scrollbar, sem pan) | `topology.py:110-111,199` |
| **ST-6** | P1 | 415 ms por `resizeEvent`; arrastar a janela = 25 s congelados | `topology.py:66-68` |
| **ST-7** | P2 | `tail()` O(arquivo) a cada 5 s na GUI: 3,35 ms/MiB, sem limite de crescimento | `audit_log.py:330`, `handlers/dashboard.py:43` |
| **ST-8** | P3 | Audit JSONL sem rotação (o log da app tem) | `audit_log.py` |
| **ST-9** | P3 | `_shutdown` é consultivo; `submit()` direto o ignora | `app_threading.py:67` |
| **ST-10** | P3 | `self._event_drop_count += 1` é read-modify-write não-atômico entre threads | `app_threading.py:30` |

## 21. 🔎 Autocorreções: o que os stress tests.erraram no relatório

| # | Onde | Erro | Como foi detectado | Correção |
|---|---|---|---|---|
| **1** | §11.1 (correção) | O fix bloqueava só `\n` — **não fechava o bypass**, porque `;` também é separador no VRP | Fuzz de separadores (§19.2) | Reescrito para dividir em comandos lógicos (§11.1) |
| **2** | §13.3 (patch) | `_safe_write` capturava só `RuntimeError`; o modo de falha real é **`AttributeError`** | Stress C (39.500 exceções, todas `AttributeError`) | `except (RuntimeError, AttributeError)` + guarda `widget is None` |
| **3** | §12.1 | **Falso positivo.** `purge_expired` usa `list(self._pool.items())` (snapshot) → **não** há `RuntimeError` | ST-9 (0 exceções em 4.800 ops) | Rebaixado para **P3** e marcado como não-comprovado |
| **4** | §11.1 (tabela) | Citava `commands.py:40` para `if vr.bypass_2fa:`; a linha correta é **42** | Leitura integral de `commands.py` | Corrigido para `:42` |

**Confirmados como verdadeiros** (sem mudança): §3.2 (o emoji são 2 surrogates solitários `U+D83D U+DDD1`, e a string **não é codificável em UTF-8** — `"surrogates not allowed"`), §3.3 (o Qt **descarta o bloco QSS inteiro**: `color: #ff4444` não é aplicado, `foregroundRole()` fica `#000000`), §3.1, §13.2, §13.4 (ambos `AlwaysOff` **e** `dragMode = NoDrag`), §15.10 (49 itens antes e depois de `update_devices([])`), §11.2 (22 de 144 serviços com `config_mode=True`).

## 22. O que os stress tests **refutaram** (e é importante registrar)

- ❌ **Não há ReDoS** no `CommandValidator` — 2,68 ms no pior caso de 160.000 chars.
- ❌ **Não há bypass de linha única** — 200.000 entradas de fuzz, zero.
- ❌ **Não há vazamento de memória nos rebuilds** — 300 rebuilds com `deleteLater()`: RSS **130 MiB → 130 MiB (delta 0)**, exatamente 2 `QTextEdit` vivos. A taxa é 21 rebuilds/s.
- ❌ **`purge_expired` não levanta `RuntimeError`** (item 12.1 rebaixado).
- ❌ **O validador não é gargalo de CPU** — 718.884 validações/s.
- ❌ **As APIs do Netmiko usadas são válidas** (confirmado contra 4.4).

## 23. Ordem de aplicação — atualização final

**Bloque 0 (novo, obrigatório antes de qualquer coisa):**

| # | Ação | Arquivo | Risco |
|---|---|---|---|
| 0.1 | **Dividir o buffer em comandos lógicos + deny antes de allow** | `validator.py:96-121` | Baixo |
| 0.2 | **Testes de regressão dos 3 invariantes** (§11.1) | `tests/` | Baixo |
| 0.3 | Injetar `validator=` no transporte | `app.py:84-85` | Baixo |

**Bloco 1 (P0 de runtime, risco baixo):**

| # | Ação | Arquivo |
|---|---|---|
| 1.1 | Inicializar `_event_drop_count` + torná-lo atômico | `app.py:208`, `app_threading.py:30` |
| 1.2 | Reordenar bases do `AppCore` (MRO) | `app.py:61` |
| 1.3 | `setParent` no filtro de eventos | `pages/cmd.py:143` |
| 1.4 | Zenar refs de widget + `_ui_queue.clear()` + `_safe_write` com os 2 `except` | `app.py:592`, `app_threading.py:96` |
| 1.5 | Deletar o stub `_toggle_command_palette` | `app_shortcuts.py:148-150` |

**Bloco 2 (P1, risco médio):**

| # | Ação | Arquivo |
|---|---|---|
| 2.1 | Rate-limit no log de descarte | `event_queue.py:101`, `app_threading.py:31-38` |
| 2.2 | `tail()` em streaming + rotação do audit log | `audit_log.py:330` |
| 2.3 | Scrollbars + `ScrollHandDrag` + re-layout no resize | `topology.py:110-111,66-68,199` |
| 2.4 | `except RuntimeError` → `SdnError` (10×) | `handlers/*.py` |
| 2.5 | Corrigir `send_service_commands` (try/finally + `return`) | `southbound.py:268-285` |
| 2.6 | `SdnError` propagando em vez de `"ERRO: …"` | `session_commands.py:15-23` |
| 2.7 | Corrigir `update_devices([])` | `topology.py:126-133` |

**Bloco 3 (P2, dívida):** §17 itens 12-20, na ordem original.

## 24. Como reproduzir os stress tests

```bash
cd /home/aluno20/Huawei-Manager-2.0

# 19.1 — fuzz + ReDoS do validador (sem Qt, ~2 s)
.venv/bin/python -c "
import sys, random, time; sys.path.insert(0,'src')
from huawei_manager.sdn_controller.validator import CommandValidator
v = CommandValidator()
t=time.perf_counter(); v.validate('display ' + 'a'*100000); print('ReDoS ms:', (time.perf_counter()-t)*1000)
alpha=list('abc \t\n\r;|?&=<>()')+['display','reset','saved-configuration','format','flash']
random.seed(1234); bad=0
for _ in range(200_000):
    c=''.join(random.choice(alpha) for _ in range(random.randint(0,8)))
    r=v.validate(c, role='user')
    if r.allowed and any(k in c.lower() for k in ('reset saved','format flash')) and '\n' not in c and ';' not in c: bad+=1
print('bypasses de linha unica:', bad)
"

# 19.2 — o bypass por ';' que o fix original nao pegava
.venv/bin/python -c "
import sys; sys.path.insert(0,'src')
from huawei_manager.sdn_controller.validator import CommandValidator
v=CommandValidator()
for c in ['display version;system-view;reset saved-configuration',
          'display version ; system-view ; reset saved-configuration',
          'display cpu-usage | include cpu']:
    r=v.validate(c, role='user'); print(repr(c[:48]), '->', r.allowed)
"

# 19.3 — log flood (mede o arquivo)
.venv/bin/python -c "
import sys, time, logging, tempfile, pathlib; sys.path.insert(0,'src')
from huawei_manager.sdn_controller import event_queue as eq
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import DeviceStatusChangedPayload
p=pathlib.Path(tempfile.mkdtemp())/'f.log'
h=logging.FileHandler(p); eq._LOG.handlers=[h]; eq._LOG.propagate=False
q=eq.EventQueue(maxsize=1000); q.get(block=False)
t=time.perf_counter()
for i in range(200_000):
    q.put(Event(EventType.DEVICE_STATUS_CHANGED,source='s',payload=DeviceStatusChangedPayload(status='online')),block=False)
h.flush(); print('WARNINGs:', sum(1 for _ in p.open()), '| MiB:', round(p.stat().st_size/1048576,1))
"

# 19.4 / 19.7 / 19.8 — os testes que precisam do app real
QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
import sys, time, threading; sys.path.insert(0,'src')
import logging; logging.disable(logging.CRITICAL)
from huawei_manager._config import init; init()
from huawei_manager._app import get_app, apply_theme
from huawei_manager.app import HuaweiRouterApp
from huawei_manager.device_models import Device
app=get_app(); apply_theme('dark'); w=HuaweiRouterApp(); w.show(); app.processEvents()
w._show_page('topology'); app.processEvents()
errs=[]
def wk():
    for _ in range(5000):
        try: w._dispatch(lambda: None, sdn=True)
        except Exception as e: errs.append(type(e).__name__)
ts=[threading.Thread(target=wk) for _ in range(8)]
for t in ts: t.start()
for t in ts: t.join()
print('ST-2 excecoes com fila cheia:', len(errs))
w._topo_canvas.update_devices([Device(id=f'd{i}',name=f'R{i}',host='1.1.1.1') for i in range(1000)])
t0=time.perf_counter(); w._topo_canvas._draw()
print('ST-5 redraw 1000 devices: %.0f ms | scene %s' % ((time.perf_counter()-t0)*1000, w._topo_canvas._view.sceneRect()))
"
```

**Saída esperada hoje (antes dos fixes):** `ReDoS ms` < 5 · `bypasses de linha unica: 0` · `WARNINGs: ~199000` · `;` → `True` · `ST-2 excecoes: ~39500` · `redraw 1000 devices: ~430 ms | scene 924x23710`.

---

*Fim do documento. Gerado por análise estática (AST/`ruff`/`pyright`) + reprodução em runtime contra o app real + bateria de stress tests. Nenhum arquivo do repositório foi modificado.*
