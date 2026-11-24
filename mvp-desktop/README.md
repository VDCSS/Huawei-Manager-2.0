# Huawei Manager 2.0 — MVP Desktop

Réplica visual em **HTML5, CSS3 e JavaScript puro** do Huawei Manager 2.0, modelada como
aplicativo desktop (janela, barra de menus, sidebar, barra de status e taskbar), sem
frameworks ou dependências externas.

## Como abrir

### Opção 1 — arquivo único

Abra `huawei-manager-desktop.html` diretamente no navegador. CSS, JavaScript e ícones SVG
estão embutidos no arquivo; não é necessário servidor.

### Opção 2 — arquivos separados

```bash
cd mvp-desktop
python3 -m http.server 8000
```

Depois acesse <http://localhost:8000/>.

Também é possível abrir `index.html` diretamente, mas um servidor local evita restrições
do navegador para alguns recursos (por exemplo, área de transferência).

## O que está implementado

- **Dois temas**: Black (padrão) e White/slate, alternáveis em tempo real e persistidos
  em `localStorage`.
- **Sidebar desktop**: ícones + texto, recolhimento animado para 64 px, tooltips e rótulos
  acessíveis no modo recolhido, submenus em acordeão.
- **Dashboard de Serviços**: grade modular com estatísticas, quick actions, tabela de ACLs
  e linha do tempo de atividades.
- **Ação obrigatória `Bloquear Internet`**: abre um wizard de ACL em quatro etapas
  (Destino → Estratégia → Exceções → Revisão), com validação, tags de destinos/exceções,
  prévia da CLI e aplicação simulada.
- **Modais para todos os destinos** da sidebar, catálogo, menus e cards de serviço.
- **Confirmação de descarte** do wizard em diálogo próprio, no visual do aplicativo.
- **Barra de menus e controles de janela**: minimizar, maximizar/restaurar, fechar e
  reabrir pela taskbar ou atalho da área de trabalho.
- **Extras funcionais**: busca de serviços, filtros do catálogo, conectar/desconectar,
  editor de comandos em modo dry-run, backup simulado, auditoria e preferências.
- **Responsivo**: abaixo de 960 px a sidebar vira um painel off-canvas com scrim.

> Todos os dados, comandos, backups e aplicações de ACL são **simulações em modo mock**.
> Nenhuma conexão SSH real é feita.

## Atalhos

| Atalho | Ação |
| --- | --- |
| `Ctrl+B` | Recolher / expandir a sidebar |
| `Ctrl+J` | Alternar tema claro/escuro |
| `Ctrl+K` | Focar a busca de serviços |
| `Ctrl+N` | Abrir o wizard de nova regra ACL |
| `F11` | Maximizar / restaurar a janela |
| `Esc` | Fechar diálogo, menu ou sidebar móvel |

Alguns atalhos podem ser interceptados pelo navegador ou pelo sistema operacional; os
controles visíveis continuam disponíveis.

## Estrutura

| Arquivo | Função |
| --- | --- |
| `index.html` | Marcação da janela, sidebar, dashboard, diálogos e templates |
| `style.css` | Temas, layout desktop, componentes, wizard e responsividade |
| `script.js` | Tema, navegação, modais, wizard, dados mock e atalhos |
| `huawei-manager-desktop.html` | Versão standalone com CSS/JS embutidos |

## Compatibilidade

Chrome, Edge e Firefox recentes. O layout foi desenhado para desktop; a versão estreita é
um fallback funcional, não o alvo principal.
