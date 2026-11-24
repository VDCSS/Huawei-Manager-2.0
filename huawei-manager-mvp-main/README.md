# Huawei Manager 2.0 — MVP Desktop

Aplicação demonstrativa do Huawei Manager 2.0 em **HTML5, CSS3 e JavaScript puro**,
modelada como aplicativo desktop. Sem frameworks, bibliotecas ou dependências externas.

**Demo:** https://izzieee.github.io/huawei-manager-mvp/

## Conteúdo

- `index.html` — versão modular da interface.
- `style.css` — temas Black/White, layout desktop, wizard e responsividade.
- `script.js` — navegação, modais, wizard de ACL, dados mock e atalhos.
- `huawei-manager-desktop.html` — versão standalone com CSS/JS embutidos.

## Executar localmente

Abra `index.html` diretamente ou use um servidor local:

```bash
python3 -m http.server 8000
```

Depois acesse <http://localhost:8000/>.

## Recursos

- Temas **Black** e **White/slate** com persistência em `localStorage`.
- Sidebar recolhível (64 px), tooltips, acordeões e navegação acessível.
- Dashboard de Serviços com estatísticas, quick actions, ACLs e atividades.
- Ação **Bloquear Internet** com wizard de ACL em 4 etapas, validação, exceções,
  revisão da CLI e aplicação simulada.
- Modais para os destinos da sidebar, catálogo, menus e cards de serviço.
- Confirmação de descarte do wizard em diálogo próprio.
- Controles de janela, barra de menus, taskbar, busca, comandos dry-run e backup mock.
- Layout responsivo com sidebar off-canvas abaixo de 960 px.

## Atalhos

| Atalho | Ação |
| --- | --- |
| `Ctrl+B` | Recolher / expandir a sidebar |
| `Ctrl+J` | Alternar tema |
| `Ctrl+K` | Buscar serviços |
| `Ctrl+N` | Nova regra ACL |
| `F11` | Maximizar / restaurar a janela |
| `Esc` | Fechar diálogo, menu ou sidebar móvel |

> Todos os dados, comandos, backups e aplicações de ACL são simulações em modo mock.
> Nenhuma conexão SSH real é realizada.

## Origem

Espelho de `mvp-desktop/` da branch `Modelagem-APP` do repositório
[VDCSS/Huawei-Manager-2.0](https://github.com/VDCSS/Huawei-Manager-2.0).
