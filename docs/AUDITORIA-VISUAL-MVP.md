# Auditoria de fidelidade visual — MVP (`huawei-manager-mvp-main`) vs PySide6

Data: 2026-11-10 · Fonte da verdade: `huawei-manager-mvp-main/style.css` (estado final
efetivo, incluindo o bloco “Proporções gerais” da linha 5324, que **sobrescreve** a
escala compacta original — ex.: item de nav 40 px, ícone 19 px, corpo 14 px, h1 34 px).

Legenda de status: ✅ já fiel · ⚠️ divergência menor · ❌ divergência relevante ·
🧩 exceção intencional (mecânica do app mantida, ver README).

## Resumo

Todas as ações de ajuste visual foram aplicadas: `NeonButton` custom-paint (gradiente ativo +
barra 3 px + ícone SVG 19 px + badge live), `ActionButton` com 5 variantes, shell refeito
(sidebar, topbar, statusbar, controles de janela), QSS global atualizado à escala MVP, páginas
das abas com novos tamanhos/padding/fonte, ícones em SVG no lugar de emoji, e testes
revisados. Os itens marcados ⚠️/🧩 abaixo são exceções documentadas intencionais (mecânica
preservada) ou divergências menores aceitas por limitação do Qt.

## 1. Sidebar

| Item | MVP | Branch (atual) | Status | Ação |
|---|---|---|---|---|
| Largura | 268 px, borda direita 1 px `--border` | 268 px ✓ | ✅ | — |
| Cabeçalho | 68 px, logo 30 px (radius 5, cyan-soft, cyan-border), nome 11 px cyan `ls .14em`, versão 9 px | logo radius 6, nome cyan | ✅ | — |
| Label de grupo | 10.5 px, 600, faint, uppercase, `ls .12em`, margens 12/16/7 | 10.5 px, padding 12/16/7 | ✅ | — |
| Item de nav | min-height 40 px, margens 0 8 px, padding 8/11, gap 11, 13.5 px, radius 6 | 40 px, padding 8/11, gap 11, 13.5 px, radius 6 | ✅ | — |
| Item ativo | gradiente `cyan-soft → transparent 92%` + barra 3 px em `left:-8` (glow cyan no dark; sem glow no light; barra `--cyan`) | paintEvent com gradiente + barra 3 px | ✅ | — |
| Item hover | `--surface-hover` (#1e1e3b dark / #e4e4e4 light), texto `--text` | surface-hover / e4e4e4 | ✅ | — |
| Ícones | SVG 19×19 stroke 1.75 na cor `--item-color` (cyan/amber/magenta/purple) | sprite SVG + QIcon 19 px | ✅ | — |
| Badge “live” | pílula mono 9.5 px green-soft/green-border + dot 4 px | desenhado no item Dashboard | ✅ | — |
| Subitens/accordions | pais com chevron e sublista 34 px/12.8 px/ícone 15 px | navegação plana (10 abas) | 🧩 | exceção: manter navegação plana (mecânica) |
| Rodapé sidebar | target-card (padding 10/11, radius 6, hover cyan-border) + user-card (avatar 32 px mono 12) | target-card 10/11 + user-card avatar 32 px | ✅ | — |
| Cores por grupo | Dispositivos=amber, Ferramentas=purple, Admin=magenta | alinhado ao mapping do MVP | ✅ | — |

## 2. Topbar (header)

| Item | MVP | Branch (atual) | Status | Ação |
|---|---|---|---|---|
| Altura/padding | 68 px, padding 0 20 px, gap 18 | 68 px, padding 0 20 px, gap 18 | ✅ | — |
| Wordmark | caixa 38 px (radius 5) + texto 17 px display “**HUAWEI** MANAGER” | caixa 38 px + texto 17 px | ✅ | — |
| Breadcrumb | 12.5 px, “Aplicativo › página”, ícone chevron 14 px faint | “Aplicativo › página”, 12.5 px / chevron 14 px | ✅ | — |
| Searchbox | 290×38, radius 6, `--input`, ícone 16 px, placeholder “Buscar serviço…”, kbd “Ctrl K” mono 10 px | 290×38, ícone 16 px, “Buscar serviço…”, Ctrl K mono 10 px | ✅ | — |
| Conn-state | dot 6 px red/green + label 12.5 px dim | dot 6 px + label 12.5 px | ✅ | — |
| Botão Conectar | `.btn--outline` (transparente, cyan, cyan-border; hover cyan + cyan-ink) | ActionButton `outline`, ícone power | ✅ | — |
| Theme selector | página Preferências (3 radios) | botão único ciclando no topbar | 🧩 | exceção documentada; manter |
| Avatar | 32 px, mono 12 px, radius 50%, cyan-soft/cyan-border | 32 px, mono 12 px | ✅ | — |
| Controles de janela | titlebar nativa do MVP (44 px) — botões 44 px | botões 34 px no topbar | 🧩/⚠️ | manter no topbar (exceção); close hover `#c42b1c` |
| Titlebar dedicada | 44 px com logo/título/versão/contexto/sessão | não existe (janela nativa) | 🧩 | exceção: sem frameless |

## 3. Cartões, botões, badges

| Item | MVP | Branch (atual) | Status | Ação |
|---|---|---|---|---|
| Painel/card | surface, borda `--border`, radius 10 (md), header 18/20/15 com h2 18 px | radius 10, padding 20/18/20/16, h2 18 px | ✅ | — |
| Stat card | padding 20/20/18, label 11 px uppercase, valor 34 px mono 600, small 12 px | padding 20/20/18, label 11 px, valor 34 px | ✅ | — |
| Linha de acento do card | gradiente 1 px topo `transparent→accent→transparent` op. 0.55 | `rgba(accent, 0.55)` 1 px topo | ✅ | — |
| Botão `.btn` | min-height 38 px, padding 0 16, 13.5 px, radius 6, `surface-2`, hover `surface-hover`+`border-strong` | 38 px, 0 16, 13.5 px, radius 6 | ✅ | — |
| `.btn--primary` | cyan + cyan-ink + glow | usado nos botões default | ✅ | — |
| Badge/chip | 10 px mono, padding 3/8, radius 8 | 10 px, 3 8, radius 8 | ✅ | — |

## 4. Tipografia / espaçamento

| Item | MVP | Branch (atual) | Status | Ação |
|---|---|---|---|---|
| Corpo base | 14 px | 14 px (QSS base) | ✅ | — |
| h1 de página | 34 px display 650 | 34 px, Space Grotesk | ✅ | — |
| Subtítulo | 14 px dim | 14 px | ✅ | — |
| Eyebrow | 11 px mono `ls .11em` + marca 6 px | 11 px mono + marca 6 px | ✅ | — |
| Fontes | ui: “IBM Plex Sans, Segoe UI, Noto Sans”; display: “Space Grotesk…”; mono: “JetBrains Mono, Cascadia, Consolas” | stacks idênticas ao MVP (fallback Segoe UI) | ✅ | — |
| Padding do conteúdo | 28/32/40 | 32/28/32/40 | ✅ | — |

## 5. Temas

| Item | MVP | Branch (atual) | Status | Ação |
|---|---|---|---|---|
| Dark | tokens idênticos | tokens idênticos | ✅ | — |
| Light `--input` | `#ffffff` | `BG_INPUT_L = #ffffff` | ✅ | — |
| Light ativo nav | bg `#e0e0e0`, texto `#1a1a1a`, barra `--cyan` sem glow | bg `#e0e0e0`, texto `#1a1a1a`, barra cyan | ✅ | — |
| Light `data-table th` | `#ececec` (surface-3) | surface-3 | ✅ | — |
| Huawei | tokens idênticos | tokens idênticos | ✅ | — |

## 6. Transições / estados

| Item | MVP | Branch (atual) | Status | Ação |
|---|---|---|---|---|
| Transições | `--speed: 0.22s` ease (220 ms) | instantâneo (QSS não anima) | 🧩 | Qt não suporta transition CSS; estados finais fiéis; documentar |
| Focus | outline cyan-border | border-color cyan ✓ | ✅ | — |

## 7. Outros

| Item | MVP | Branch (atual) | Status | Ação |
|---|---|---|---|---|
| Statusbar | 30 px ✓, 11 px, brand 11.5 + logo 16 cyan, “Conexão segura” verde c/ lock 13 px, relógio dim | 30 px, 11 px, ícones SVG + cores | ✅ | — |
| Drawer | 440 px, ícone 40 px amber-soft, h2 20 px, body 24/22, foot surface-2 18/22 | 440 px, ícone 40 px, h2 20 px | ✅ | — |
| Tabelas | td 13/14 px 12.5, th 11/14 10.5 uppercase | td 13/14 px 12.5, th 10.5 px | ✅ | — |
| Scrollbar | 9 px ✓ handle border-strong radius 4 | ✓ | ✅ | — |

## Exceções intencionais (mecânica preservada)

1. **Navegação plana** — o MVP usa pais com accordion + subitens; o app tem 10 abas
   planas no registry. Itens recebem o visual de `.nav__item` do MVP (40 px, ícone
   19 px colorido, barra de acento) sem introduzir mecânica de expansão.
2. **Seletor de tema único** — o MVP troca o tema em Preferências (3 radios); o app
   mantém o botão que cicla dark→light→huawei no topbar.
3. **Sem titlebar custom** — o MVP é frameless com titlebar própria; o app mantém a
   janela nativa e os controles (min/max/close) no topbar.
4. **Modais só nas Configurações / telemetria** — conforme decisão anterior.
5. **Transições animadas** — QSS não tem `transition`; os estados hover/active/focus
   finais são fiéis, mas a animação de 220 ms do MVP não é reproduzida.

## Verificação

- `tests/` executados com sucesso: 1232 passed, 2 skipped (Qt offscreen).
- Screenshots offscreen capturados para 10 páginas × 3 temas em `/tmp/opencode/fidelity/`;
  validação de geometria/paleta feita por introspecção Qt (sem input de imagem).
- Nenhuma mecânica do app foi alterada — apenas visual/design.
