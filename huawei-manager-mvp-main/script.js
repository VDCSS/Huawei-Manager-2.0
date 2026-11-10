/* ═══════════════════════════════════════════════════════════════════════
   HUAWEI MANAGER 2.0 · DESKTOP UI
   script.js — temas, navegação SPA por páginas dedicadas, sidebar,
   drawer de confirmação e wizard de ACL.
   Vanilla JS (ES2020). Sem dependências.
   ═══════════════════════════════════════════════════════════════════════ */
(() => {
  "use strict";

  /* ───────────────────────── Helpers ───────────────────────── */
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const icon = (name, className = "icon") =>
    `<svg class="${className}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;

  const escapeHtml = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[character]));

  const formatNumber = (value) =>
    new Intl.NumberFormat("pt-BR").format(Number(value) || 0);

  const pad = (value) => String(value).padStart(2, "0");
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const directionLabel = (direction) =>
    direction === "inbound" ? "Entrada" : "Saída";

  const modeLabel = (mode) =>
    mode === "all-except" ? "Bloquear tudo, exceto" : "Bloquear destinos específicos";

  const readStorage = (key) => {
    try { return localStorage.getItem(key); } catch { return null; }
  };

  const writeStorage = (key, value) => {
    try { localStorage.setItem(key, value); } catch { /* storage indisponível */ }
  };

  const STORAGE = {
    theme: "hw-manager-theme",
    collapsed: "hw-manager-sidebar-collapsed",
    reducedMotion: "hw-manager-reduced-motion",
    confirmClose: "hw-manager-confirm-close",
  };

  const THEMES = {
    dark: { label: "Black Theme", meta: "#05050d", icon: "moon" },
    light: { label: "White Theme", meta: "#ffffff", icon: "sun" },
    huawei: { label: "Huawei Theme", meta: "#ffffff", icon: "sun" },
  };

  /* ───────────────────────── Dados de demonstração ───────────────────────── */
  const devices = [
    {
      id: "router-lab",
      name: "ROTEADOR-LAB",
      host: "192.168.1.1",
      type: "Router",
      model: "AR617VW",
      status: "online",
      interfaces: ["GigabitEthernet0/0/0", "GigabitEthernet0/0/1", "GigabitEthernet0/0/2"],
    },
    {
      id: "router-edge",
      name: "ROTEADOR-EDGE",
      host: "10.20.0.1",
      type: "Router",
      model: "AR651",
      status: "online",
      interfaces: ["GigabitEthernet0/0/0", "GigabitEthernet0/0/1"],
    },
    {
      id: "switch-access",
      name: "SWITCH-ACESSO",
      host: "10.20.1.2",
      type: "Switch",
      model: "S5735-L",
      status: "online",
      interfaces: ["GigabitEthernet0/0/12", "GigabitEthernet0/0/24", "Vlanif100"],
    },
    {
      id: "fw-lab",
      name: "FIREWALL-LAB",
      host: "10.20.0.254",
      type: "Firewall",
      model: "USG6311E",
      status: "maintenance",
      interfaces: ["GigabitEthernet1/0/0", "GigabitEthernet1/0/1"],
    },
  ];

  const services = [
    {
      id: "acl-block",
      title: "Política de bloqueio",
      category: "acl",
      categoryLabel: "ACL",
      iconName: "shield-off",
      color: "red",
      description: "Negue destinos específicos ou toda a saída para a WAN.",
      action: { type: "wizard", preset: "deny-site" },
    },
    {
      id: "acl-exceptions",
      title: "Exceções de acesso",
      category: "acl",
      categoryLabel: "ACL",
      iconName: "key",
      color: "amber",
      description: "Libere hosts e faixas administrativas antes das regras de bloqueio.",
      action: { type: "wizard", preset: "block" },
    },
    {
      id: "traffic-filter",
      title: "Traffic Filter",
      category: "acl",
      categoryLabel: "ACL",
      iconName: "layers",
      color: "cyan",
      description: "Aplique e remova ACLs por interface e direção de tráfego.",
      action: { type: "page", page: "acl" },
    },
    {
      id: "nat",
      title: "Sessões NAT",
      category: "security",
      categoryLabel: "Segurança",
      iconName: "activity",
      color: "magenta",
      description: "Inspecione traduções ativas e consumo da tabela NAT.",
      action: { type: "page", page: "commands", command: "display nat session all" },
    },
    {
      id: "qos",
      title: "QoS & Tráfego",
      category: "qos",
      categoryLabel: "QoS",
      iconName: "sliders",
      color: "purple",
      description: "Verifique filas, policies e limites de banda por classe.",
      action: { type: "page", page: "commands", command: "display traffic policy" },
    },
    {
      id: "interface",
      title: "Interfaces",
      category: "interfaces",
      categoryLabel: "Interfaces",
      iconName: "cpu",
      color: "cyan",
      description: "Consulte estado operacional, erros e contadores de porta.",
      action: { type: "page", page: "commands", command: "display interface brief" },
    },
    {
      id: "diagnostics",
      title: "Diagnóstico de link",
      category: "diagnostics",
      categoryLabel: "Diagnóstico",
      iconName: "wifi",
      color: "green",
      description: "Execute ping e traceroute para validar conectividade.",
      action: { type: "page", page: "commands", command: "ping -c 4 8.8.8.8" },
    },
    {
      id: "backup",
      title: "Backup de configuração",
      category: "backup",
      categoryLabel: "Backup",
      iconName: "archive",
      color: "amber",
      description: "Exporte o running-config antes de aplicar uma nova ACL.",
      action: { type: "page", page: "backup" },
    },
  ];

  const SITE_MAP = {
    "huawei.com": "121.36.14.208",
    "github.com": "140.82.112.3",
    "microsoft.com": "20.70.246.20",
    "office.com": "52.96.0.0",
    "google.com": "142.250.79.14",
    "youtube.com": "142.250.72.14",
    "tiktok.com": "157.240.22.53",
    "whatsapp.com": "157.240.22.53",
    "cloudflare.com": "104.16.132.229",
    "slack.com": "3.33.0.0",
  };

  const rules = [
    {
      id: "rule-3000",
      acl: 3000,
      name: "Bloqueio de sites",
      deviceId: "router-lab",
      iface: "GigabitEthernet0/0/1",
      direction: "outbound",
      mode: "deny-list",
      destinations: ["youtube.com", "tiktok.com"],
      exceptions: [],
      hits: 8412,
      status: "active",
      createdAt: "Hoje, 14:02",
    },
    {
      id: "rule-3001",
      acl: 3001,
      name: "Exceções de administração",
      deviceId: "router-lab",
      iface: "GigabitEthernet0/0/0",
      direction: "inbound",
      mode: "all-except",
      destinations: [],
      exceptions: ["192.168.1.0/24"],
      hits: 214,
      status: "active",
      createdAt: "Hoje, 13:41",
    },
    {
      id: "rule-3002",
      acl: 3002,
      name: "Bloqueio IoT",
      deviceId: "switch-access",
      iface: "GigabitEthernet0/0/12",
      direction: "inbound",
      mode: "deny-list",
      destinations: ["10.20.30.0/24"],
      exceptions: [],
      hits: 1028,
      status: "active",
      createdAt: "Ontem, 18:26",
    },
    {
      id: "rule-3003",
      acl: 3003,
      name: "Quarentena convidados",
      deviceId: "router-lab",
      iface: "GigabitEthernet0/0/2",
      direction: "outbound",
      mode: "deny-list",
      destinations: ["172.16.50.0/24"],
      exceptions: [],
      hits: 0,
      status: "paused",
      createdAt: "Ontem, 16:05",
    },
  ];

  const activities = [
    {
      tone: "success",
      iconName: "shield",
      title: "ACL 3000 atualizada em ROTEADOR-LAB",
      detail: "Lucas Silva · há 2 min · 192.168.1.24",
      badge: "aplicado",
      badgeTone: "success",
    },
    {
      tone: "success",
      iconName: "archive",
      title: "Backup de configuração concluído",
      detail: "Lucas Silva · há 18 min · SWITCH-ACESSO",
      badge: "backup",
      badgeTone: "success",
    },
    {
      tone: "warning",
      iconName: "refresh",
      title: "Sessão SSH restabelecida",
      detail: "sistema · há 34 min · FIREWALL-LAB",
      badge: "sessão",
      badgeTone: "warning",
    },
    {
      tone: "success",
      iconName: "check",
      title: "Regra ACL 3002 sincronizada",
      detail: "sistema · há 1 h · SWITCH-ACESSO",
      badge: "sync",
      badgeTone: "success",
    },
    {
      tone: "cyan",
      iconName: "eye",
      title: "Consulta ao catálogo de serviços",
      detail: "Lucas Silva · hoje, 12:40 · ROTEADOR-LAB",
      badge: "leitura",
      badgeTone: "",
    },
    {
      tone: "danger",
      iconName: "lock",
      title: "Tentativa de login recusada",
      detail: "usuário desconhecido · hoje, 11:12 · 10.20.0.55",
      badge: "negado",
      badgeTone: "danger",
    },
  ];

  const WIZARD_PRESETS = {
    block: {
      title: "Bloquear Internet",
      mode: "all-except",
      name: "Bloqueio de Internet",
      destinations: [],
      exceptions: ["huawei.com", "github.com"],
      allowDns: true,
      allowUpdates: false,
    },
    "deny-site": {
      title: "Bloquear site específico",
      mode: "deny-list",
      name: "Bloqueio de sites",
      destinations: ["youtube.com", "tiktok.com"],
      exceptions: [],
      allowDns: false,
      allowUpdates: false,
    },
    custom: {
      title: "Nova regra ACL",
      mode: "deny-list",
      name: "Nova política de acesso",
      destinations: [],
      exceptions: [],
      allowDns: true,
      allowUpdates: false,
    },
  };

  const PAGES = {
    dashboard: {
      title: "Visão geral",
      eyebrow: "Dashboard",
      subtitle: "Ponto de partida para as operações, páginas e dispositivos da sessão.",
      icon: "home",
      template: "tpl-dashboard",
    },
    services: {
      title: "Painel de Serviços",
      eyebrow: "Serviços",
      subtitle: "Indicadores, regras ativas, atividade recente e catálogo de operações.",
      icon: "gauge",
      template: "tpl-services",
    },
    topology: {
      title: "Topologia / Devices",
      eyebrow: "Dispositivos",
      subtitle: "Inventário de dispositivos e seleção do alvo das operações.",
      icon: "target",
      template: "tpl-topology",
    },
    config: {
      title: "Configuração Atual",
      eyebrow: "Dispositivos",
      subtitle: "Running-config recuperado do device alvo em modo somente leitura.",
      icon: "file-text",
      template: "tpl-config",
    },
    routing: {
      title: "Tabela de Roteamento",
      eyebrow: "Dispositivos",
      subtitle: "Rotas ativas, próximo salto e interface de saída.",
      icon: "route",
      template: "tpl-routing",
    },
    arp: {
      title: "Tabela ARP",
      eyebrow: "Dispositivos",
      subtitle: "Mapeamento entre endereços IP e endereços físicos observados.",
      icon: "radio",
      template: "tpl-arp",
    },
    sysinfo: {
      title: "Informações do Sistema",
      eyebrow: "Dispositivos",
      subtitle: "Inventário, versão de software e utilização de recursos.",
      icon: "cpu",
      template: "tpl-sysinfo",
    },
    catalog: {
      title: "Catálogo de Serviços",
      eyebrow: "Serviços",
      subtitle: "Operações disponíveis para o tipo de device selecionado.",
      icon: "layers",
      template: "tpl-catalog",
    },
    acl: {
      title: "Regras ACL",
      eyebrow: "Serviços",
      subtitle: "Políticas aplicadas, contadores e estado de sincronização.",
      icon: "shield",
      template: "tpl-acl",
    },
    commands: {
      title: "Editor de Comandos",
      eyebrow: "Ferramentas",
      subtitle: "Execute comandos de leitura em modo dry-run, sem alterar o device.",
      icon: "terminal",
      template: "tpl-commands",
    },
    backup: {
      title: "Backup de Configuração",
      eyebrow: "Ferramentas",
      subtitle: "Exportação do running-config e histórico de arquivos locais.",
      icon: "archive",
      template: "tpl-backup",
    },
    audit: {
      title: "Auditoria",
      eyebrow: "Ferramentas",
      subtitle: "Trilha de eventos e alterações registradas nesta sessão.",
      icon: "audit",
      template: "tpl-audit",
    },
    maintenance: {
      title: "Manutenção e Diagnóstico",
      eyebrow: "Administração",
      subtitle: "Lint, testes, tipos e verificação do ambiente local.",
      icon: "wrench",
      template: "tpl-maintenance",
    },
    settings: {
      title: "Preferências",
      eyebrow: "Administração",
      subtitle: "Tema, barra lateral e preferências locais da interface.",
      icon: "settings",
      template: "tpl-settings",
    },
    about: {
      title: "Sobre o Huawei Manager",
      eyebrow: "Ajuda",
      subtitle: "Informações da build e da réplica desktop.",
      icon: "info",
      template: "tpl-about",
    },
    shortcuts: {
      title: "Atalhos de Teclado",
      eyebrow: "Ajuda",
      subtitle: "Comandos rápidos para operar a interface com o teclado.",
      icon: "key",
      template: "tpl-shortcuts",
    },
  };

  const state = {
    theme: "dark",
    collapsed: readStorage(STORAGE.collapsed) === "true",
    connected: false,
    targetDeviceId: "router-lab",
    serviceFilter: "all",
    pageFilter: "all",
    search: "",
    reducedMotion: readStorage(STORAGE.reducedMotion) === "true",
    confirmClose: readStorage(STORAGE.confirmClose) !== "false",
    lastUpdated: "há 2 min",
    pendingCommand: null,
    wizard: null,
    currentPage: "dashboard",
    wizardReturnPage: "dashboard",
    pendingDrawerAction: null,
    drawerTrigger: null,
  };

  const els = {
    html: document.documentElement,
    body: document.body,
    appWindow: $("#appWindow"),
    sidebar: $("#sidebar"),
    sidebarToggle: $("#sidebarToggle"),
    sidebarScrim: $("#sidebarScrim"),
    mobileMenuToggle: $("#mobileMenuToggle"),
    globalSearch: $("#globalSearch"),
    mainContent: $("#main-content"),
    contentScroll: $("#contentScroll"),
    pageHost: $("#pageHost"),
    wizardMount: $("#wizardMount"),
    wizardPage: $("#wizardPage"),
    breadcrumbGroup: $("#breadcrumbGroup"),
    breadcrumbPage: $("#breadcrumbPage"),
    connDot: $("#connDot"),
    connLabel: $("#connLabel"),
    connectBtn: $("#connectBtn"),
    windowContext: $("#windowContext"),
    menubarTarget: $("#menubarTarget"),
    toastRegion: $("#toastRegion"),
    statusClock: $("#statusClock"),
    drawerScrim: $("#drawerScrim"),
    discardDrawer: $("#discardDrawer"),
    confirmDiscardBtn: $("#confirmDiscardBtn"),
    wizardTitle: $("#wizardTitle"),
    wizardForm: $("#wizardForm"),
    wizardStepper: $("#wizardStepper"),
    wizardProgressBar: $("#wizardProgressBar"),
    wizardBack: $("#wizardBack"),
    wizardNext: $("#wizardNext"),
    wizardApply: $("#wizardApply"),
    wizardCounter: $("#wizardCounter"),
    wizardFormError: $("#wizardFormError"),
    wizardSuccess: $("#wizardSuccess"),
    wizardDevice: $("#wizardDevice"),
    wizardInterface: $("#wizardInterface"),
    wizardName: $("#wizardName"),
    wizardAclId: $("#wizardAclId"),
    wizardNameError: $("#wizardNameError"),
    wizardAclIdError: $("#wizardAclIdError"),
    destinationsTags: $("#destinationsTags"),
    destinationsInput: $("#destinationsInput"),
    destinationsError: $("#destinationsError"),
    exceptionsTags: $("#exceptionsTags"),
    exceptionsInput: $("#exceptionsInput"),
    exceptionsError: $("#exceptionsError"),
    exceptionsImpact: $("#exceptionsImpact"),
    wizardAllowDns: $("#wizardAllowDns"),
    wizardAllowUpdates: $("#wizardAllowUpdates"),
    reviewDevice: $("#reviewDevice"),
    reviewEndpoint: $("#reviewEndpoint"),
    reviewPolicy: $("#reviewPolicy"),
    reviewAcl: $("#reviewAcl"),
    reviewMode: $("#reviewMode"),
    reviewTags: $("#reviewTags"),
    cliPreview: $("#cliPreview"),
    reviewWarning: $("#reviewWarning"),
    successPolicy: $("#successPolicy"),
    successDevice: $("#successDevice"),
    successAcl: $("#successAcl"),
    successRules: $("#successRules"),
    successInterface: $("#successInterface"),
  };

  /* ───────────────────────── Tema ───────────────────────── */
  function setTheme(theme, persist = true) {
    const next = THEMES[theme] ? theme : "dark";
    state.theme = next;
    els.html.dataset.theme = next;
    els.body.dataset.theme = next;

    const themeMeta = $('meta[name="theme-color"]');
    if (themeMeta) themeMeta.setAttribute("content", THEMES[next].meta);

    $$("[data-set-theme]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.setTheme === next));
    });

    if (persist) writeStorage(STORAGE.theme, next);
  }

  /* ───────────────────────── Sidebar ───────────────────────── */
  const mobileQuery = window.matchMedia("(max-width: 960px)");
  const isMobile = () => mobileQuery.matches;

  function applySidebarState() {
    const collapsed = state.collapsed && !isMobile();
    els.sidebar.classList.toggle("is-collapsed", collapsed);
    els.sidebarToggle.setAttribute("aria-expanded", String(!collapsed));
    const label = collapsed ? "Expandir barra lateral" : "Recolher barra lateral";
    els.sidebarToggle.setAttribute("aria-label", label);
    els.sidebarToggle.title = `${label} (Ctrl+B)`;

    if (!isMobile()) {
      els.sidebar.classList.remove("is-open");
      els.sidebarScrim.classList.remove("is-visible");
      els.mobileMenuToggle.setAttribute("aria-expanded", "false");
    }

    // Quando os rótulos somem, mantém um nome acessível para cada ícone.
    $$(".nav__item[data-tooltip]").forEach((item) => {
      if (collapsed) item.setAttribute("aria-label", item.dataset.tooltip);
      else item.removeAttribute("aria-label");
    });
  }

  function setSidebarCollapsed(collapsed, persist = true) {
    state.collapsed = Boolean(collapsed);
    if (persist) writeStorage(STORAGE.collapsed, String(state.collapsed));
    applySidebarState();
  }

  function setMobileSidebar(open) {
    els.sidebar.classList.toggle("is-open", open);
    els.sidebarScrim.classList.toggle("is-visible", open);
    els.mobileMenuToggle.setAttribute("aria-expanded", String(open));
    els.sidebarToggle.setAttribute("aria-expanded", String(open));
  }

  function closeMobileSidebar() {
    if (isMobile()) setMobileSidebar(false);
  }

  function toggleSidebar() {
    if (isMobile()) {
      setMobileSidebar(!els.sidebar.classList.contains("is-open"));
      return;
    }
    setSidebarCollapsed(!state.collapsed);
  }

  function setAccordion(button, open) {
    button.classList.toggle("is-open", open);
    button.setAttribute("aria-expanded", String(open));
    const submenu = document.getElementById(button.getAttribute("aria-controls"));
    if (submenu) {
      submenu.classList.toggle("is-open", open);
      submenu.inert = !open;
    }
  }

  function initAccordions() {
    $$("[data-accordion]").forEach((button) => {
      const submenu = document.getElementById(button.getAttribute("aria-controls"));
      const initiallyOpen = button.classList.contains("is-open");
      setAccordion(button, initiallyOpen);
      if (submenu) submenu.inert = !initiallyOpen;

      button.addEventListener("click", () => {
        if (!isMobile() && els.sidebar.classList.contains("is-collapsed")) {
          setSidebarCollapsed(false);
        }
        const willOpen = !button.classList.contains("is-open");
        $$("[data-accordion]").forEach((other) => {
          if (other !== button) setAccordion(other, false);
        });
        setAccordion(button, willOpen);
      });
    });
  }

  function setActivePageInNav(pageKey) {
    $$(".nav__item.is-active, .nav__subitem.is-active", els.sidebar).forEach((item) => {
      item.classList.remove("is-active");
    });
    const trigger = els.sidebar.querySelector(`[data-page="${pageKey}"]`);
    if (trigger) trigger.classList.add("is-active");
  }

  function openAccordionForPage(pageKey) {
    const trigger = els.sidebar.querySelector(`[data-page="${pageKey}"]`);
    const submenu = trigger?.closest(".nav__submenu");
    if (!submenu) return;
    const parent = $(`[data-accordion][aria-controls="${submenu.id}"]`);
    if (parent && !parent.classList.contains("is-open")) setAccordion(parent, true);
  }

  /* ───────────────────────── Menus ───────────────────────── */
  function closeMenus() {
    $$(".menu.is-open").forEach((menu) => {
      menu.classList.remove("is-open");
      const trigger = $(".menu__trigger", menu);
      if (trigger) trigger.setAttribute("aria-expanded", "false");
    });
  }

  function toggleMenu(menu) {
    const wasOpen = menu.classList.contains("is-open");
    closeMenus();
    if (!wasOpen) {
      menu.classList.add("is-open");
      const trigger = $(".menu__trigger", menu);
      if (trigger) trigger.setAttribute("aria-expanded", "true");
    }
  }

  function initMenus() {
    $$(".menu__trigger").forEach((trigger) => {
      trigger.addEventListener("click", (event) => {
        event.stopPropagation();
        toggleMenu(trigger.closest(".menu"));
      });
    });

    document.addEventListener("pointerdown", (event) => {
      if (!event.target.closest(".menu")) closeMenus();
    });
  }

  function handleMenuAction(action) {
    closeMenus();
    const actions = {
      backup: () => navigateToPage("backup"),
      config: () => navigateToPage("config"),
      settings: () => navigateToPage("settings"),
      search: () => {
        els.globalSearch.focus();
        els.globalSearch.select();
      },
      sidebar: toggleSidebar,
      wizard: () => openWizard("custom"),
      commands: () => navigateToPage("commands"),
      catalog: () => navigateToPage("catalog"),
      about: () => navigateToPage("about"),
      shortcuts: () => navigateToPage("shortcuts"),
    };
    if (actions[action]) actions[action]();
  }

  /* ───────────────────────── Conexão / relógio ───────────────────────── */
  function updateConnectionUI() {
    const online = state.connected;
    els.connLabel.textContent = online ? "Conectado" : "Desconectado";
    els.connDot.classList.toggle("status-dot--online", online);
    els.connDot.classList.toggle("status-dot--warning", false);
    els.connectBtn.textContent = online ? "Desconectar" : "Conectar";
    els.connectBtn.classList.toggle("btn--outline", !online);
    els.connectBtn.classList.toggle("btn--danger", online);
    const stateWrap = els.connLabel.closest(".conn-state");
    if (stateWrap) stateWrap.classList.toggle("is-online", online);
  }

  function toggleConnection() {
    state.connected = !state.connected;
    updateConnectionUI();
    if (state.connected) {
      const device = getTargetDevice();
      addActivity({
        tone: "success",
        iconName: "link",
        title: `Sessão SSH estabelecida com ${device.name}`,
        detail: "Lucas Silva · agora · modo mock",
        badge: "sessão",
        badgeTone: "success",
      });
      showToast("Device conectado", `Sessão SSH simulada com ${device.name} (${device.host}).`, "success", "link");
    } else {
      showToast("Device desconectado", "A sessão SSH simulada foi encerrada.", "warning", "power");
    }
  }

  function updateClock() {
    const now = new Date();
    const time = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
    if (els.statusClock) els.statusClock.textContent = time;
  }

  /* ───────────────────────── Dados auxiliares ───────────────────────── */
  function getTargetDevice() {
    return devices.find((device) => device.id === state.targetDeviceId) || devices[0];
  }

  function getDevice(deviceId) {
    return devices.find((device) => device.id === deviceId) || devices[0];
  }

  function updateTargets() {
    const device = getTargetDevice();
    $$("[data-target-name]").forEach((element) => {
      element.textContent = device.name;
    });
    $$("[data-target-host]").forEach((element) => {
      element.textContent = device.host;
    });
    if (els.menubarTarget) els.menubarTarget.textContent = device.name;
    const statusHost = $(".statusbar__center .mono");
    if (statusHost) statusHost.textContent = device.host;
  }

  function updateStats() {
    const active = rules.filter((rule) => rule.status === "active");
    const hits = rules.reduce((total, rule) => total + Number(rule.hits || 0), 0);
    const statRules = $("#statRules");
    const statHits = $("#statHits");
    const rulesCount = $("#rulesCount");
    const statUpdated = $("#statUpdated");
    const aclPageCount = $("#aclPageCount");
    if (statRules) statRules.textContent = String(active.length);
    if (statHits) statHits.textContent = formatNumber(hits);
    if (rulesCount) rulesCount.textContent = String(rules.length);
    if (statUpdated) statUpdated.textContent = state.lastUpdated;
    if (aclPageCount) aclPageCount.textContent = `${rules.length} regras`;
  }

  function updateData() {
    renderRules();
    renderStatsTimeline();
    updateStats();
    updateTargets();
    renderAclPage();
  }

  function renderStatsTimeline() {
    const activityList = $("#activityList");
    if (activityList) {
      activityList.innerHTML = activities.slice(0, 4).map((activity) => timelineMarkup(activity)).join("");
    }
  }

  function timelineMarkup(activity, compact = false, roomy = false) {
    const badge = roomy && activity.badge
      ? `<span class="badge${activity.badgeTone ? ` badge--${activity.badgeTone}` : ""}">${escapeHtml(activity.badge)}</span>`
      : "";
    return `<li class="timeline__item${compact ? " timeline__item--compact" : ""}">
      <span class="timeline__dot timeline__dot--${escapeHtml(activity.tone)}"></span>
      <div><strong>${escapeHtml(activity.title)}</strong><small>${escapeHtml(activity.detail)}</small></div>
      ${badge}
    </li>`;
  }

  function addActivity(activity) {
    activities.unshift(activity);
    if (activities.length > 24) activities.length = 24;
    state.lastUpdated = "agora";
    renderStatsTimeline();
    updateStats();
  }

  function renderRules() {
    const body = $("#rulesBody");
    if (!body) return;
    body.innerHTML = rules.map((rule) => {
      const device = getDevice(rule.deviceId);
      return `<tr>
        <td class="rule-acl">${rule.acl}</td>
        <td>
          <div class="rule-name">
            <strong>${escapeHtml(rule.name)}</strong>
            <small>${escapeHtml(device.name)} · ${escapeHtml(shortInterface(rule.iface))}</small>
          </div>
        </td>
        <td class="mono">${escapeHtml(shortInterface(rule.iface))} · ${rule.direction === "outbound" ? "LAN→WAN" : "WAN→LAN"}</td>
        <td>${directionLabel(rule.direction)}</td>
        <td class="is-numeric mono">${formatNumber(rule.hits)}</td>
        <td>
          <span class="rule-status${rule.status === "active" ? "" : " is-paused"}">
            <span class="status-dot"></span>${rule.status === "active" ? "Ativa" : "Pausada"}
          </span>
        </td>
      </tr>`;
    }).join("");
  }

  function renderAclPage() {
    const body = $("#aclPageRules");
    if (!body) return;
    body.innerHTML = rules.map((rule) => {
      const device = getDevice(rule.deviceId);
      return `<tr>
        <td class="mono">${rule.acl}</td>
        <td><div class="rule-name"><strong>${escapeHtml(rule.name)}</strong><small>${escapeHtml(device.name)}</small></div></td>
        <td class="mono">${escapeHtml(shortInterface(rule.iface))}</td>
        <td>${directionLabel(rule.direction)}</td>
        <td class="is-numeric mono">${formatNumber(rule.hits)}</td>
        <td><span class="badge${rule.status === "active" ? " badge--success" : ""}">${rule.status === "active" ? "Ativa" : "Pausada"}</span></td>
        <td class="is-numeric">
          <div class="rule-actions">
            <button class="icon-btn" type="button" data-toggle-rule="${rule.id}" title="${rule.status === "active" ? "Pausar regra" : "Ativar regra"}" aria-label="${rule.status === "active" ? "Pausar regra" : "Ativar regra"}">
              ${icon(rule.status === "active" ? "pause" : "play")}
            </button>
            <button class="icon-btn is-danger" type="button" data-delete-rule="${rule.id}" title="Remover regra" aria-label="Remover regra">${icon("trash")}</button>
          </div>
        </td>
      </tr>`;
    }).join("");
  }

  function renderAudit() {
    const list = $("#auditList");
    if (!list) return;
    list.innerHTML = activities.map((activity) => timelineMarkup(activity, false, true)).join("");
    const count = $("#auditCount");
    if (count) count.textContent = `${activities.length} eventos`;
  }

  function shortInterface(name) {
    return String(name || "").replace("GigabitEthernet", "GE");
  }

  function renderTopology() {
    const body = $("#topologyBody");
    if (!body) return;
    body.innerHTML = devices.map((device) => {
      const isTarget = device.id === state.targetDeviceId;
      const online = device.status === "online";
      return `<tr>
        <td><strong class="${isTarget ? "text-cyan" : ""}">${escapeHtml(device.name)}</strong><br><small class="text-faint">${escapeHtml(device.model)}</small></td>
        <td>${escapeHtml(device.type)}</td>
        <td class="mono">${escapeHtml(device.host)}</td>
        <td><span class="badge${online ? " badge--success" : " badge--warning"}">${online ? "online" : "manutenção"}</span></td>
        <td class="is-numeric">
          <button class="btn btn--sm ${isTarget ? "btn--primary" : "btn--secondary"}" type="button" data-set-target="${device.id}" ${online ? "" : "disabled"}>
            ${isTarget ? "Alvo atual" : online ? "Selecionar" : "Indisponível"}
          </button>
        </td>
      </tr>`;
    }).join("");
  }

  /* ───────────────────────── Catálogo ───────────────────────── */
  function matchesSearch(service) {
    if (!state.search) return true;
    const haystack = `${service.title} ${service.categoryLabel} ${service.description}`.toLowerCase();
    return haystack.includes(state.search);
  }

  function filteredServices(filter) {
    return services.filter((service) => {
      const byCategory = filter === "all" || service.category === filter;
      return byCategory && matchesSearch(service);
    });
  }

  function serviceCardMarkup(service) {
    const isWizard = service.action.type === "wizard";
    const actionAttrs = isWizard
      ? `data-wizard-preset="${service.action.preset}"`
      : `data-page="${service.action.page}"${service.action.command ? ` data-command="${escapeHtml(service.action.command)}"` : ""}`;
    return `<button class="service-card" type="button" ${actionAttrs} title="${escapeHtml(service.description)}" style="--service-color: var(--${service.color})">
      <span class="service-card__icon">${icon(service.iconName)}</span>
      <span class="service-card__copy">
        <strong>${escapeHtml(service.title)}</strong>
        <small>${escapeHtml(service.description)}</small>
      </span>
      <span class="service-card__cat">${escapeHtml(service.categoryLabel)}</span>
    </button>`;
  }

  function renderServices() {
    const grid = $("#servicesGrid");
    if (!grid) return;
    const list = filteredServices(state.serviceFilter);
    grid.innerHTML = list.map(serviceCardMarkup).join("");
    const empty = $("#servicesEmpty");
    if (empty) empty.hidden = list.length > 0;
    const count = $("#servicesCount");
    if (count) count.textContent = String(services.length);
    const catalogCount = $("#catalogCount");
    if (catalogCount) catalogCount.textContent = `${list.length} ${list.length === 1 ? "serviço" : "serviços"}`;
    syncFilterButtons("[data-service-filter]", "serviceFilter", state.serviceFilter);
  }

  function renderPageServices() {
    const grid = $("#pageServicesGrid");
    if (!grid) return;
    const list = filteredServices(state.pageFilter);
    grid.innerHTML = list.length
      ? list.map(serviceCardMarkup).join("")
      : `<div class="empty-state" style="grid-column:1/-1"><span class="empty-state__icon">${icon("search")}</span><h3>Nenhum serviço</h3><p>Ajuste o filtro ou a busca.</p></div>`;
    const count = $("#pageCatalogCount");
    if (count) count.textContent = `${list.length} ${list.length === 1 ? "serviço" : "serviços"}`;
    syncFilterButtons("[data-page-filter]", "pageFilter", state.pageFilter);
  }

  function syncFilterButtons(selector, stateKey, value) {
    $$(selector).forEach((button) => {
      const active = button.dataset[stateKey] === value;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function clearServiceFilters() {
    state.serviceFilter = "all";
    state.pageFilter = "all";
    state.search = "";
    if (els.globalSearch) els.globalSearch.value = "";
    renderServices();
    renderPageServices();
  }

  function refreshCatalogForSearch() {
    renderServices();
    renderPageServices();
  }

  /* ───────────────────────── Roteador SPA ───────────────────────── */
  function pageHeaderMarkup(definition) {
    return `<header class="page-heading">
      <div class="page-heading__copy">
        <p class="eyebrow"><span class="eyebrow__mark" aria-hidden="true"></span>${escapeHtml(definition.eyebrow)}</p>
        <h1>${escapeHtml(definition.title)}</h1>
        <p class="page-subtitle">${escapeHtml(definition.subtitle)}</p>
      </div>
      <div class="page-heading__actions">
        <button class="target-chip" type="button" data-page="topology" title="Trocar device alvo">
          <span class="status-dot status-dot--online" aria-hidden="true"></span>
          <span class="target-chip__label">Alvo</span>
          <strong data-target-name>ROTEADOR-LAB</strong>
          <svg class="icon" aria-hidden="true"><use href="#i-chevron-down"/></svg>
        </button>
      </div>
    </header>`;
  }

  function renderPage(pageKey, options = {}) {
    const definition = PAGES[pageKey];
    if (!definition) return;
    const template = document.getElementById(definition.template);
    if (!template) return;

    els.pageHost.hidden = false;
    els.wizardMount.hidden = true;
    els.wizardPage.hidden = true;
    els.pageHost.innerHTML = `${pageHeaderMarkup(definition)}<div class="page-body"></div>`;
    $(".page-body", els.pageHost).appendChild(template.content.cloneNode(true));

    state.currentPage = pageKey;
    els.mainContent.dataset.page = pageKey;
    els.windowContext.textContent = definition.title;
    els.breadcrumbGroup.textContent = definition.eyebrow;
    els.breadcrumbPage.textContent = definition.title;

    setActivePageInNav(pageKey);
    openAccordionForPage(pageKey);

    els.contentScroll.scrollTop = 0;
    postRenderPage(pageKey, options);
    updateTargets();
    closeMenus();
    closeMobileSidebar();
  }

  function postRenderPage(pageKey, options = {}) {
    if (pageKey === "dashboard") {
      updateTargets();
    }
    if (pageKey === "services") {
      renderServices();
      renderStatsTimeline();
      renderRules();
      updateStats();
    }
    if (pageKey === "catalog") renderPageServices();
    if (pageKey === "acl") {
      renderAclPage();
      updateStats();
    }
    if (pageKey === "audit") renderAudit();
    if (pageKey === "topology") renderTopology();
    if (pageKey === "settings") syncSettingsUI();
    if (pageKey === "commands") {
      const input = $("#commandInput");
      if (input) {
        if (options.command) {
          input.value = options.command;
        } else if (state.pendingCommand) {
          input.value = state.pendingCommand;
          state.pendingCommand = null;
        } else if (!input.value) {
          input.value = "display version";
        }
      }
    }
  }

  function navigateToPage(pageKey, options = {}) {
    if (pageKey === "acl-new") {
      openWizard(options.preset || "block");
      return;
    }
    if (!PAGES[pageKey]) return;

    if (state.wizard && !options.force) {
      if (isWizardDirty() && state.confirmClose) {
        openDrawer(() => {
          hideWizardPage();
          navigateToPage(pageKey, { ...options, force: true });
        });
        return;
      }
      hideWizardPage();
    }

    renderPage(pageKey, options);
  }

  /* ───────────────────────── Drawer de confirmação ───────────────────────── */
  function openDrawer(onConfirm) {
    state.pendingDrawerAction = typeof onConfirm === "function" ? onConfirm : null;
    state.drawerTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    els.discardDrawer.classList.add("is-open");
    els.discardDrawer.setAttribute("aria-hidden", "false");
    els.drawerScrim.classList.add("is-visible");
    setTimeout(() => $("[data-close-drawer]", els.discardDrawer)?.focus(), 60);
  }

  function closeDrawer() {
    const trigger = state.drawerTrigger;
    els.discardDrawer.classList.remove("is-open");
    els.discardDrawer.setAttribute("aria-hidden", "true");
    els.drawerScrim.classList.remove("is-visible");
    state.pendingDrawerAction = null;
    state.drawerTrigger = null;
    if (trigger && document.contains(trigger) && trigger.offsetParent !== null) {
      trigger.focus();
    }
  }

  function confirmDrawerAction() {
    const action = state.pendingDrawerAction;
    state.pendingDrawerAction = null;
    closeDrawer();
    if (action) action();
  }

  /* ───────────────────────── Wizard de ACL ───────────────────────── */
  function isWizardDirty() {
    return Boolean(state.wizard && !state.wizard.applied && state.wizard.step > 1);
  }

  function nextAclId() {
    const used = new Set(rules.map((rule) => Number(rule.acl)));
    let candidate = 3004;
    while (used.has(candidate) && candidate <= 3999) candidate += 1;
    return candidate;
  }

  function openWizard(preset = "custom") {
    const safePreset = WIZARD_PRESETS[preset] ? preset : "custom";
    const config = WIZARD_PRESETS[safePreset];
    const onlineDevices = devices.filter((device) => device.status === "online");
    const target = onlineDevices.find((device) => device.id === state.targetDeviceId) || onlineDevices[0] || devices[0];

    closeDrawer();
    if (state.currentPage !== "acl-new") state.wizardReturnPage = state.currentPage;
    resetWizardUI();

    state.wizard = {
      preset: safePreset,
      step: 1,
      applying: false,
      applied: false,
      cli: "",
      successCli: "",
      data: {
        deviceId: target.id,
        iface: target.interfaces[0],
        direction: "outbound",
        name: config.name,
        aclId: nextAclId(),
        mode: config.mode,
        destinations: config.destinations.slice(),
        exceptions: config.exceptions.slice(),
        allowDns: config.allowDns,
        allowUpdates: config.allowUpdates,
      },
    };

    els.wizardTitle.textContent = config.title;
    els.wizardForm.hidden = false;
    els.wizardSuccess.hidden = true;
    els.wizardStepper.hidden = false;
    clearWizardErrors();
    fillWizard();
    updateWizardStepUI();

    state.currentPage = "acl-new";
    els.mainContent.dataset.page = "acl-new";
    els.pageHost.hidden = true;
    els.wizardMount.hidden = false;
    els.wizardPage.hidden = false;
    els.windowContext.textContent = `Wizard de ACL · ${config.title}`;
    els.breadcrumbGroup.textContent = "Serviços";
    els.breadcrumbPage.textContent = config.title;
    setActivePageInNav("acl-new");
    openAccordionForPage("acl-new");
    els.contentScroll.scrollTop = 0;

    setTimeout(() => $(".wizard-step:not([hidden]) h3", els.wizardPage)?.focus(), 60);
  }

  function hideWizardPage() {
    els.wizardPage.hidden = true;
    els.wizardMount.hidden = true;
    resetWizardUI();
  }

  function wizardPropsReset() {
    els.wizardApply.classList.remove("is-loading");
    els.wizardApply.disabled = false;
    els.wizardBack.disabled = false;
    els.wizardFormError.hidden = true;
    els.wizardFormError.textContent = "";
    els.wizardProgressBar.style.width = "25%";
  }

  function fillWizard() {
    const wizard = state.wizard;
    if (!wizard) return;

    els.wizardDevice.innerHTML = devices.map((device) => {
      const disabled = device.status !== "online" ? " disabled" : "";
      const suffix = device.status !== "online" ? " — manutenção" : "";
      return `<option value="${device.id}"${disabled}>${escapeHtml(device.name)} · ${escapeHtml(device.host)}${suffix}</option>`;
    }).join("");
    els.wizardDevice.value = wizard.data.deviceId;

    populateInterfaceOptions();
    els.wizardName.value = wizard.data.name;
    els.wizardAclId.value = String(wizard.data.aclId);

    const direction = $(`input[name="wizardDirection"][value="${wizard.data.direction}"]`);
    if (direction) direction.checked = true;
    const mode = $(`input[name="wizardMode"][value="${wizard.data.mode}"]`);
    if (mode) mode.checked = true;

    renderWizardTags("destinations");
    renderWizardTags("exceptions");
    els.wizardAllowDns.checked = Boolean(wizard.data.allowDns);
    els.wizardAllowUpdates.checked = Boolean(wizard.data.allowUpdates);
    updateModePanels();
    updateExceptionsImpact();
  }

  function populateInterfaceOptions() {
    const wizard = state.wizard;
    if (!wizard) return;
    const device = getDevice(wizard.data.deviceId);
    if (!device.interfaces.includes(wizard.data.iface)) {
      wizard.data.iface = device.interfaces[0] || "";
    }
    els.wizardInterface.innerHTML = device.interfaces
      .map((iface) => `<option value="${escapeHtml(iface)}">${escapeHtml(iface)}</option>`)
      .join("");
    els.wizardInterface.value = wizard.data.iface;
  }

  function updateModePanels() {
    const wizard = state.wizard;
    if (!wizard) return;
    $$("[data-mode-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.modePanel !== wizard.data.mode;
    });
  }

  function updateExceptionsImpact() {
    const wizard = state.wizard;
    if (!wizard) return;
    const exceptions = wizard.data.exceptions;
    let text;
    if (wizard.data.mode === "all-except") {
      text = exceptions.length
        ? `A saída para a internet será negada, exceto para <strong>${exceptions.length}</strong> destino(s) permitido(s).`
        : "Toda a saída para a internet será negada. Nenhum destino excepcional está configurado.";
    } else {
      text = exceptions.length
        ? `Apenas os <strong>${wizard.data.destinations.length}</strong> destinos bloqueados serão negados. As <strong>${exceptions.length}</strong> exceções são avaliadas antes das negações.`
        : `Apenas os <strong>${wizard.data.destinations.length}</strong> destinos bloqueados serão negados. O restante do tráfego permanece liberado.`;
    }
    if (els.exceptionsImpact) {
      els.exceptionsImpact.innerHTML = `${icon("info")}<p>${text}</p>`;
    }
  }

  function renderWizardTags(type) {
    const wizard = state.wizard;
    if (!wizard) return;
    const container = type === "destinations" ? els.destinationsTags : els.exceptionsTags;
    if (!container) return;
    const list = wizard.data[type];
    container.innerHTML = list.map((value, index) => `<li class="tag">
      ${escapeHtml(value)}
      <button type="button" data-remove-tag="${type}" data-tag-index="${index}" aria-label="Remover ${escapeHtml(value)}">${icon("x")}</button>
    </li>`).join("");
  }

  function clearWizardErrors() {
    setFieldError(els.wizardName, els.wizardNameError, "");
    setFieldError(els.wizardAclId, els.wizardAclIdError, "");
    setTagError("destinations", "");
    setTagError("exceptions", "");
    els.wizardFormError.hidden = true;
    els.wizardFormError.textContent = "";
  }

  function setFieldError(input, errorElement, message) {
    if (errorElement) errorElement.textContent = message;
    if (input) {
      if (message) input.setAttribute("aria-invalid", "true");
      else input.removeAttribute("aria-invalid");
    }
  }

  function setTagError(type, message) {
    const errorElement = type === "destinations" ? els.destinationsError : els.exceptionsError;
    const input = type === "destinations" ? els.destinationsInput : els.exceptionsInput;
    const field = input?.closest(".tag-field");
    if (errorElement) errorElement.textContent = message;
    if (field) field.classList.toggle("is-invalid", Boolean(message));
  }

  function normalizeTag(raw) {
    return String(raw || "")
      .trim()
      .replace(/^https?:\/\//i, "")
      .replace(/\/.*$/, "")
      .toLowerCase();
  }

  function isValidIPv4(value) {
    const parts = value.split(".");
    return parts.length === 4 && parts.every((part) => /^\d{1,3}$/.test(part) && Number(part) >= 0 && Number(part) <= 255);
  }

  function validateTagValue(value) {
    if (!value) return "Informe um domínio, endereço IPv4 ou CIDR.";
    if (value.length > 120) return "O valor é longo demais.";

    if (value.includes("/")) {
      const [address, prefix] = value.split("/");
      if (!isValidIPv4(address) || !/^\d{1,2}$/.test(prefix) || Number(prefix) > 32) {
        return "CIDR inválido. Use, por exemplo, 192.168.1.0/24.";
      }
      return "";
    }

    if (/^[\d.]+$/.test(value)) {
      return isValidIPv4(value) ? "" : "Endereço IPv4 inválido.";
    }

    const domainPattern = /^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$/i;
    return domainPattern.test(value) ? "" : "Informe um domínio válido (ex.: huawei.com) ou um IP.";
  }

  function addWizardTag(type, raw) {
    const wizard = state.wizard;
    if (!wizard) return false;
    const input = type === "destinations" ? els.destinationsInput : els.exceptionsInput;
    const value = normalizeTag(raw);
    const error = validateTagValue(value);
    if (error) {
      setTagError(type, error);
      return false;
    }
    if (wizard.data[type].includes(value)) {
      setTagError(type, "Este destino já foi adicionado.");
      return false;
    }
    wizard.data[type].push(value);
    if (input) input.value = "";
    setTagError(type, "");
    renderWizardTags(type);
    updateExceptionsImpact();
    if (wizard.step === 4) renderReview();
    return true;
  }

  function removeWizardTag(type, index) {
    const wizard = state.wizard;
    if (!wizard) return;
    const list = wizard.data[type];
    if (index < 0 || index >= list.length) return;
    list.splice(index, 1);
    renderWizardTags(type);
    updateExceptionsImpact();
    if (wizard.step === 4) renderReview();
  }

  function commitPendingTag(type) {
    const input = type === "destinations" ? els.destinationsInput : els.exceptionsInput;
    if (!input || !input.value.trim()) return true;
    return addWizardTag(type, input.value);
  }

  function validateStep(step) {
    const wizard = state.wizard;
    if (!wizard) return false;
    let ok = true;

    if (step === 1) {
      const name = els.wizardName.value.trim();
      const acl = Number(els.wizardAclId.value);
      const device = getDevice(els.wizardDevice.value);

      wizard.data.deviceId = els.wizardDevice.value;
      wizard.data.iface = els.wizardInterface.value;
      wizard.data.name = name;
      wizard.data.aclId = acl;

      if (name.length < 3) {
        setFieldError(els.wizardName, els.wizardNameError, "Use pelo menos 3 caracteres.");
        ok = false;
      } else {
        setFieldError(els.wizardName, els.wizardNameError, "");
      }

      if (!Number.isInteger(acl) || acl < 3000 || acl > 3999) {
        setFieldError(els.wizardAclId, els.wizardAclIdError, "Informe um número entre 3000 e 3999.");
        ok = false;
      } else if (rules.some((rule) => Number(rule.acl) === acl)) {
        setFieldError(els.wizardAclId, els.wizardAclIdError, "Esta ACL já existe. Escolha outro número.");
        ok = false;
      } else {
        setFieldError(els.wizardAclId, els.wizardAclIdError, "");
      }

      if (!device || device.status !== "online") {
        els.wizardFormError.hidden = false;
        els.wizardFormError.textContent = "Selecione um device com sessão SSH ativa.";
        ok = false;
      }
      if (!wizard.data.iface) {
        els.wizardFormError.hidden = false;
        els.wizardFormError.textContent = "Selecione uma interface para aplicar a ACL.";
        ok = false;
      }
    }

    if (step === 2) {
      if (!commitPendingTag("destinations")) ok = false;
      if (wizard.data.mode === "deny-list" && wizard.data.destinations.length === 0) {
        setTagError("destinations", "Adicione ao menos um destino para bloquear.");
        ok = false;
      } else {
        setTagError("destinations", "");
      }
    }

    if (step === 3) {
      if (!commitPendingTag("exceptions")) ok = false;
    }

    if (step === 4) {
      ok = validateStep(1) && validateStep(2) && validateStep(3) && ok;
    }

    if (!ok && step !== 1) {
      els.wizardFormError.hidden = false;
      if (!els.wizardFormError.textContent) {
        els.wizardFormError.textContent = "Revise os campos destacados antes de continuar.";
      }
    } else if (ok) {
      els.wizardFormError.hidden = true;
      els.wizardFormError.textContent = "";
    }

    return ok;
  }

  function updateWizardStepUI() {
    const wizard = state.wizard;
    if (!wizard) return;
    const step = wizard.step;

    $$(".stepper__item", els.wizardStepper).forEach((item) => {
      const number = Number(item.dataset.stepTarget);
      item.classList.toggle("is-current", number === step);
      item.classList.toggle("is-complete", number < step);
      if (number === step) item.setAttribute("aria-current", "step");
      else item.removeAttribute("aria-current");
    });

    els.wizardProgressBar.style.width = `${step * 25}%`;
    els.wizardCounter.textContent = `Passo ${step} de 4`;
    $$(".wizard-step", els.wizardForm).forEach((section) => {
      section.hidden = Number(section.dataset.step) !== step;
    });
    els.wizardBack.disabled = step === 1;
    els.wizardNext.hidden = step === 4;
    els.wizardApply.hidden = step !== 4;
    els.wizardFormError.hidden = true;
    els.wizardFormError.textContent = "";

    if (step === 4) renderReview();
    setTimeout(() => $(".wizard-step:not([hidden]) h3")?.focus(), 40);
  }

  function resolveAddress(value) {
    const normalized = normalizeTag(value);
    if (SITE_MAP[normalized]) {
      return { address: `${SITE_MAP[normalized]} 0`, comment: `${normalized} → ${SITE_MAP[normalized]}` };
    }
    if (normalized.includes("/")) {
      const [address, prefix] = normalized.split("/");
      return { address: `${address} ${cidrWildcard(Number(prefix))}`, comment: normalized };
    }
    if (isValidIPv4(normalized)) {
      return { address: `${normalized} 0`, comment: "" };
    }
    return { address: "203.0.113.45 0", comment: `${normalized} — IP não resolvido (mock)` };
  }

  function cidrWildcard(prefix) {
    const mask = prefix === 0 ? 0 : (0xffffffff << (32 - prefix)) >>> 0;
    const wildcard = (~mask) >>> 0;
    return [24, 16, 8, 0].map((shift) => (wildcard >>> shift) & 255).join(".");
  }

  function buildCli() {
    const wizard = state.wizard;
    if (!wizard) return "";
    const data = wizard.data;
    const device = getDevice(data.deviceId);
    const lines = [
      `# Huawei Manager 2.0 · ACL ${data.aclId}`,
      `# ${data.name}`,
      "# Gerado em modo dry-run — revise antes de aplicar",
      "system-view",
      `acl number ${data.aclId}`,
    ];
    let sequence = 5;

    if (data.allowDns) {
      lines.push(` rule ${sequence} permit udp destination-port eq 53`);
      sequence += 5;
    }
    if (data.allowUpdates) {
      lines.push(` rule ${sequence} permit ip destination 52.96.0.0 0.15.255.255`);
      sequence += 5;
    }

    if (data.mode === "all-except") {
      data.exceptions.forEach((value) => {
        const resolved = resolveAddress(value);
        if (resolved.comment) lines.push(`# ${resolved.comment}`);
        lines.push(` rule ${sequence} permit ip destination ${resolved.address}`);
        sequence += 5;
      });
      lines.push(` rule ${sequence} deny ip`);
      sequence += 5;
    } else {
      data.exceptions.forEach((value) => {
        const resolved = resolveAddress(value);
        if (resolved.comment) lines.push(`# ${resolved.comment}`);
        lines.push(` rule ${sequence} permit ip destination ${resolved.address}`);
        sequence += 5;
      });
      data.destinations.forEach((value) => {
        const resolved = resolveAddress(value);
        if (resolved.comment) lines.push(`# ${resolved.comment}`);
        lines.push(` rule ${sequence} deny ip destination ${resolved.address}`);
        sequence += 5;
      });
      lines.push(` rule ${sequence} permit ip`);
      sequence += 5;
    }

    lines.push(" quit");
    lines.push(`interface ${data.iface}`);
    lines.push(` traffic-filter ${data.direction} acl ${data.aclId}`);
    lines.push(" quit");
    lines.push("return");
    lines.push(`# device: ${device.name} · direção: ${directionLabel(data.direction)}`);
    return lines.join("\n");
  }

  function renderReview() {
    const wizard = state.wizard;
    if (!wizard) return;
    const data = wizard.data;
    const device = getDevice(data.deviceId);
    const tags = data.mode === "all-except" ? data.exceptions : data.destinations;

    els.reviewDevice.textContent = device.name;
    els.reviewEndpoint.textContent = `${data.iface} · ${directionLabel(data.direction)}`;
    els.reviewPolicy.textContent = data.name;
    els.reviewAcl.textContent = `ACL ${data.aclId} · ${data.mode === "all-except" ? "all-except" : "deny-list"}`;
    els.reviewMode.textContent = modeLabel(data.mode);

    const chips = tags.map((value) => `<span class="tag">${escapeHtml(value)}</span>`);
    if (data.allowDns) chips.push('<span class="tag">DNS · porta 53</span>');
    if (data.allowUpdates) chips.push('<span class="tag">Microsoft Update</span>');
    if (!chips.length) chips.push('<span class="tag">Toda a saída</span>');
    els.reviewTags.innerHTML = chips.join("");

    if (data.mode === "all-except" && data.exceptions.length === 0) {
      els.reviewWarning.className = "inline-note inline-note--danger";
      els.reviewWarning.innerHTML = `${icon("alert-triangle")}<p>Atenção: sem exceções, <strong>todo o tráfego de saída</strong> será negado, incluindo o acesso administrativo.</p>`;
    } else {
      els.reviewWarning.className = "inline-note inline-note--warning";
      els.reviewWarning.innerHTML = `${icon("alert-triangle")}<p>Ao aplicar, a ACL entra em vigor imediatamente no device selecionado. Esta é uma simulação em modo mock.</p>`;
    }

    wizard.cli = buildCli();
    els.cliPreview.textContent = wizard.cli;
  }

  function advanceWizard() {
    const wizard = state.wizard;
    if (!wizard || wizard.applying) return;
    if (!validateStep(wizard.step)) return;
    if (wizard.step < 4) {
      wizard.step += 1;
      updateWizardStepUI();
    }
  }

  function goToWizardStep(target) {
    const wizard = state.wizard;
    if (!wizard || wizard.applying) return;
    const step = Number(target);
    if (!Number.isInteger(step) || step < 1 || step > 4) return;
    if (step < wizard.step) {
      wizard.step = step;
      updateWizardStepUI();
    }
  }

  async function applyWizard() {
    const wizard = state.wizard;
    if (!wizard || wizard.applying) return;
    if (!validateStep(1) || !validateStep(2) || !validateStep(3)) return;

    wizard.applying = true;
    els.wizardApply.disabled = true;
    els.wizardApply.classList.add("is-loading");
    els.wizardBack.disabled = true;
    els.wizardTitle.textContent = "Aplicando regra…";

    await sleep(850);

    const data = wizard.data;
    const device = getDevice(data.deviceId);
    const ruleCount = (wizard.cli.match(/^\s*rule\s+/gm) || []).length;
    const newRule = {
      id: `rule-${data.aclId}`,
      acl: data.aclId,
      name: data.name,
      deviceId: data.deviceId,
      iface: data.iface,
      direction: data.direction,
      mode: data.mode,
      destinations: data.destinations.slice(),
      exceptions: data.exceptions.slice(),
      hits: 0,
      status: "active",
      createdAt: "Agora",
    };

    rules.push(newRule);
    state.lastUpdated = "agora";
    wizard.applied = true;
    wizard.successCli = wizard.cli;
    addActivity({
      tone: "success",
      iconName: "shield-check",
      title: `ACL ${data.aclId} criada em ${device.name}`,
      detail: `Lucas Silva · agora · ${shortInterface(data.iface)}`,
      badge: "aplicado",
      badgeTone: "success",
    });
    updateData();

    els.successPolicy.textContent = data.name;
    els.successDevice.textContent = device.name;
    els.successAcl.textContent = `ACL ${data.aclId}`;
    els.successRules.textContent = `${ruleCount} ${ruleCount === 1 ? "regra" : "regras"}`;
    els.successInterface.textContent = `${shortInterface(data.iface)} · ${directionLabel(data.direction)}`;

    els.wizardForm.hidden = true;
    els.wizardSuccess.hidden = false;
    els.wizardProgressBar.style.width = "100%";
    $$(".stepper__item", els.wizardStepper).forEach((item) => {
      item.classList.remove("is-current");
      item.classList.add("is-complete");
      item.removeAttribute("aria-current");
    });

    wizard.applying = false;
    els.wizardApply.classList.remove("is-loading");
    els.wizardApply.disabled = false;
    els.wizardBack.disabled = false;
    els.wizardTitle.textContent = "Regra aplicada";

    const successTitle = $("#wizardSuccessTitle");
    if (successTitle) {
      successTitle.setAttribute("tabindex", "-1");
      successTitle.focus();
    }

    showToast("Regra aplicada com sucesso", `ACL ${data.aclId} criada em ${device.name} · ${ruleCount} regras (mock).`, "success", "shield-check");
  }

  function requestCloseWizard() {
    if (!state.wizard || state.wizard.applying) return;
    if (state.wizard.applied) {
      hideWizardPage();
      navigateToPage("acl", { force: true });
      return;
    }
    if (isWizardDirty() && state.confirmClose) {
      openDrawer(() => {
        const back = state.wizardReturnPage || "dashboard";
        hideWizardPage();
        navigateToPage(back, { force: true });
      });
      return;
    }
    const back = state.wizardReturnPage || "dashboard";
    hideWizardPage();
    navigateToPage(back, { force: true });
  }

  function resetWizardUI() {
    state.wizard = null;
    els.wizardForm.hidden = false;
    els.wizardSuccess.hidden = true;
    els.wizardStepper.hidden = false;
    els.wizardProgressBar.style.width = "25%";
    els.wizardApply.classList.remove("is-loading");
    els.wizardApply.disabled = false;
    els.wizardBack.disabled = false;
    els.wizardFormError.hidden = true;
    els.wizardFormError.textContent = "";
    els.wizardTitle.textContent = "Bloquear Internet";
    $$(".stepper__item", els.wizardStepper).forEach((item) => {
      item.classList.remove("is-complete", "is-current");
      item.removeAttribute("aria-current");
    });
    wizardPropsReset();
  }

  /* ───────────────────────── Toasts / clipboard ───────────────────────── */
  function showToast(title, message, tone = "success", iconName = "circle-check") {
    const toast = document.createElement("div");
    toast.className = `toast toast--${tone}`;
    toast.innerHTML = `
      <span class="toast__icon">${icon(iconName)}</span>
      <span class="toast__copy"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(message)}</span></span>
    `;
    els.toastRegion.appendChild(toast);

    const remove = () => {
      toast.classList.add("is-leaving");
      setTimeout(() => toast.remove(), 190);
    };
    const timer = setTimeout(remove, 4200);
    toast.addEventListener("click", () => {
      clearTimeout(timer);
      remove();
    });
  }

  async function copyText(text) {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      showToast("Copiado", "Conteúdo copiado para a área de transferência.", "success", "copy");
    } catch {
      const helper = document.createElement("textarea");
      helper.value = text;
      helper.style.position = "fixed";
      helper.style.opacity = "0";
      document.body.appendChild(helper);
      helper.select();
      try {
        document.execCommand("copy");
        showToast("Copiado", "Conteúdo copiado para a área de transferência.", "success", "copy");
      } catch {
        showToast("Não foi possível copiar", "Selecione o texto manualmente.", "danger", "alert-triangle");
      }
      helper.remove();
    }
  }

  /* ───────────────────────── Ações internas das páginas ───────────────────────── */
  function runCommand() {
    const input = $("#commandInput");
    const output = $("#commandOutput");
    if (!input || !output) return;
    const command = input.value.trim();
    if (!command) {
      showToast("Comando vazio", "Digite ou selecione um comando para executar.", "warning", "terminal");
      return;
    }
    const device = getTargetDevice();
    const commandKey = command.toLowerCase();
    const outputs = {
      "display version": `Huawei Versatile Routing Platform Software
VRP (R) software, Version 8.180 (AR617VW V800R021C10SPC500)
Copyright (C) 2012-2026 Huawei Technologies Co., Ltd.
HUAWEI AR617VW uptime is 12 days, 4 hours, 31 minutes`,
      "display current-configuration": `sysname ${device.name}
#
interface GigabitEthernet0/0/0
 ip address ${device.host} 255.255.255.0
#
acl number 3000
 rule 5 deny ip destination 203.0.113.0 0.0.0.255
 rule 100 permit ip
#
return`,
      "display interface brief": `Interface                         PHY     Protocol  InUti  OutUti
GigabitEthernet0/0/0              up      up        2%     1%
GigabitEthernet0/0/1              up      up        18%    24%
GigabitEthernet0/0/2              down    down      0%     0%
NULL0                             up      up(s)     0%     0%`,
      "display ip routing-table": `Destination/Mask    Proto   Pre  Cost  NextHop         Interface
0.0.0.0/0           Static  60   0     10.20.0.2       GE0/0/1
10.20.0.0/30        Direct  0    0     10.20.0.1       GE0/0/1
192.168.1.0/24      Direct  0    0     192.168.1.1     GE0/0/0`,
      "ping -c 4 8.8.8.8": `PING 8.8.8.8: 56 data bytes, press CTRL_C to break
Reply from 8.8.8.8: bytes=56 Sequence=1 ttl=118 time=14 ms
Reply from 8.8.8.8: bytes=56 Sequence=2 ttl=118 time=13 ms
Reply from 8.8.8.8: bytes=56 Sequence=3 ttl=118 time=14 ms
Reply from 8.8.8.8: bytes=56 Sequence=4 ttl=118 time=13 ms
--- 8.8.8.8 ping statistics ---
4 packet(s) transmitted, 4 packet(s) received, 0.00% packet loss`,
    };
    const body = outputs[commandKey] || `Info: "${command}" executado em modo dry-run.
Nenhuma alteração foi enviada ao device ${device.name}.
Resultado simulado para modelagem da interface.`;
    const stamp = new Date().toLocaleTimeString("pt-BR");
    output.textContent = `[${stamp}] ${device.name} (${device.host})\n<${command}>\n\n${body}`;
    showToast("Comando executado", `${command} · modo dry-run`, "success", "terminal");
  }

  function createBackup() {
    const body = $("#backupBody");
    if (!body) return;
    const device = getTargetDevice();
    const now = new Date();
    const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
    const time = `${pad(now.getHours())}-${pad(now.getMinutes())}`;
    const file = `${device.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}_${date}_${time}.txt`;
    const row = document.createElement("tr");
    row.innerHTML = `<td class="mono">${escapeHtml(file)}</td><td>${escapeHtml(device.name)}</td><td>Agora</td><td>18,6 KB</td><td class="is-numeric"><button class="icon-btn" type="button" data-toast="Download simulado do backup iniciado.">${icon("download")}</button></td>`;
    body.prepend(row);
    addActivity({
      tone: "success",
      iconName: "archive",
      title: `Backup de configuração de ${device.name}`,
      detail: "Lucas Silva · agora · arquivo local",
      badge: "backup",
      badgeTone: "success",
    });
    showToast("Backup concluído", `${file} salvo em /var/backups/huawei (mock).`, "success", "archive");
  }

  function runMaintenance(tool) {
    const output = $("#maintenanceOutput");
    if (!output) return;
    const stamp = new Date().toLocaleTimeString("pt-BR");
    const messages = {
      lint: `[${stamp}] lint · 0 erros, 2 avisos
  src/huawei_manager/tabs/services/page.py:118  unused-import (informativo)
  src/huawei_manager/widgets/neon_button.py:42  line-too-long (informativo)
Resultado: ambiente íntegro.`,
      tests: `[${stamp}] pytest -q
.................................................... [100%]
52 passed in 2.41s
Resultado: todos os testes passaram.`,
      types: `[${stamp}] mypy src
Success: no issues found in 146 source files
Resultado: tipagem consistente.`,
      install: `[${stamp}] verificação de dependências
PySide6 .............. 6.8.0
napalm ............... 4.1.0
cryptography ......... 43.0.1
Resultado: dependências satisfeitas.`,
      reset: `[${stamp}] cache local limpo
  __pycache__ · 14 diretórios
  .pytest_cache · 1 diretório
Resultado: cache reiniciado.`,
    };
    if (tool === "clear") {
      output.innerHTML = '<span class="code-muted">Selecione uma ferramenta para iniciar o diagnóstico.</span>';
      return;
    }
    output.textContent = messages[tool] || "Ferramenta executada (mock).";
    showToast("Diagnóstico concluído", "A saída foi atualizada no painel de manutenção.", "success", "wrench");
  }

  function syncSettingsUI() {
    $$("[data-set-theme]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.setTheme === state.theme));
    });
    const reduced = $("#prefReducedMotion");
    if (reduced) reduced.checked = state.reducedMotion;
    const confirm = $("#prefConfirmClose");
    if (confirm) confirm.checked = state.confirmClose;
  }

  function applyReducedMotion(value) {
    state.reducedMotion = Boolean(value);
    els.html.classList.toggle("reduce-motion", state.reducedMotion);
    writeStorage(STORAGE.reducedMotion, String(state.reducedMotion));
  }

  function setTarget(deviceId) {
    const device = getDevice(deviceId);
    if (!device || device.status !== "online") {
      showToast("Device indisponível", "Este device está em manutenção e não pode receber novas regras.", "warning", "alert-triangle");
      return;
    }
    state.targetDeviceId = device.id;
    updateTargets();
    renderTopology();
    showToast("Device alvo atualizado", `${device.name} · ${device.host}`, "success", "target");
  }

  /* ───────────────────────── Eventos globais ───────────────────────── */
  function handleDocumentClick(event) {
    const target = event.target;

    const closeButton = target.closest("[data-close-dialog]");
    if (closeButton) {
      if (closeButton.dataset.closeDialog === "wizard") requestCloseWizard();
      return;
    }

    if (target.closest("[data-close-drawer]")) {
      closeDrawer();
      return;
    }

    const themeChoice = target.closest("[data-set-theme]");
    if (themeChoice) {
      const theme = themeChoice.dataset.setTheme;
      setTheme(theme);
      syncSettingsUI();
      showToast("Tema atualizado", `${THEMES[theme].label} ativado.`, "success", THEMES[theme].icon);
      return;
    }

    const wizardTrigger = target.closest("[data-wizard-preset]");
    if (wizardTrigger) {
      closeMobileSidebar();
      openWizard(wizardTrigger.dataset.wizardPreset);
      return;
    }

    // Somente controles reais navegam. O host de conteúdo também carrega
    // data-page para indicar a página atual, mas não deve capturar cliques.
    const pageTrigger = target.closest("button[data-page], a[data-page], [role='button'][data-page]");
    if (pageTrigger) {
      closeMobileSidebar();
      const pageKey = pageTrigger.dataset.page;
      if (pageKey === "acl-new") {
        openWizard(pageTrigger.dataset.wizardPreset || "block");
      } else {
        navigateToPage(pageKey, { command: pageTrigger.dataset.command });
      }
      return;
    }

    const addTag = target.closest("[data-add-tag]");
    if (addTag) {
      const type = addTag.dataset.addTag;
      const input = type === "destinations" ? els.destinationsInput : els.exceptionsInput;
      addWizardTag(type, input?.value || "");
      return;
    }

    const removeTag = target.closest("[data-remove-tag]");
    if (removeTag) {
      removeWizardTag(removeTag.dataset.removeTag, Number(removeTag.dataset.tagIndex));
      return;
    }

    const quickTag = target.closest("[data-quick-tag]");
    if (quickTag) {
      addWizardTag("exceptions", quickTag.dataset.quickTag);
      return;
    }

    const serviceFilter = target.closest("[data-service-filter]");
    if (serviceFilter) {
      state.serviceFilter = serviceFilter.dataset.serviceFilter;
      renderServices();
      return;
    }

    const pageFilter = target.closest("[data-page-filter]");
    if (pageFilter) {
      state.pageFilter = pageFilter.dataset.pageFilter;
      renderPageServices();
      return;
    }

    if (target.closest("[data-clear-service-filters]")) {
      clearServiceFilters();
      return;
    }

    const setTargetButton = target.closest("[data-set-target]");
    if (setTargetButton) {
      setTarget(setTargetButton.dataset.setTarget);
      return;
    }

    const toggleRuleButton = target.closest("[data-toggle-rule]");
    if (toggleRuleButton) {
      const rule = rules.find((item) => item.id === toggleRuleButton.dataset.toggleRule);
      if (rule) {
        rule.status = rule.status === "active" ? "paused" : "active";
        updateData();
        showToast(
          rule.status === "active" ? "Regra ativada" : "Regra pausada",
          `ACL ${rule.acl} · ${rule.name}`,
          rule.status === "active" ? "success" : "warning",
          rule.status === "active" ? "play" : "pause"
        );
      }
      return;
    }

    const deleteRuleButton = target.closest("[data-delete-rule]");
    if (deleteRuleButton) {
      const index = rules.findIndex((item) => item.id === deleteRuleButton.dataset.deleteRule);
      if (index >= 0) {
        const [removed] = rules.splice(index, 1);
        updateData();
        showToast("Regra removida", `ACL ${removed.acl} removida do device (mock).`, "warning", "trash");
      }
      return;
    }

    const copyCli = target.closest("[data-copy-cli]");
    if (copyCli) {
      copyText(state.wizard?.successCli || state.wizard?.cli || "");
      return;
    }

    const copyTarget = target.closest("[data-copy-target]");
    if (copyTarget) {
      const source = $(copyTarget.dataset.copyTarget);
      copyText(source?.textContent || "");
      return;
    }

    const toastButton = target.closest("[data-toast]");
    if (toastButton) {
      showToast("Huawei Manager", toastButton.dataset.toast, "success", "info");
      return;
    }

    const refresh = target.closest("[data-refresh-demo]");
    if (refresh) {
      showToast("Dados atualizados", "Consulta concluída em modo mock.", "success", "refresh");
      return;
    }

    if (target.closest("[data-toggle-sidebar]")) {
      toggleSidebar();
      return;
    }

    if (target.closest("[data-reset-sidebar]")) {
      setSidebarCollapsed(false);
      showToast("Barra lateral restaurada", "O menu voltou ao estado expandido.", "success", "panel-expand");
      return;
    }

    const maintenanceButton = target.closest("[data-maintenance]");
    if (maintenanceButton) {
      runMaintenance(maintenanceButton.dataset.maintenance);
      return;
    }

    if (target.closest("#runCommandBtn")) {
      runCommand();
      return;
    }

    if (target.closest("#clearCommandBtn")) {
      const output = $("#commandOutput");
      if (output) output.innerHTML = '<span class="code-muted">Aguardando execução…</span>';
      return;
    }

    if (target.closest("#createBackupBtn")) {
      createBackup();
      return;
    }

    if (target.closest("#loadConfigBtn")) {
      const output = $("#configOutput");
      if (output) {
        output.textContent = `! Recarregado em ${new Date().toLocaleTimeString("pt-BR")}\n${output.textContent.replace(/^! Recarregado.*\n?/, "")}`;
      }
      showToast("Configuração carregada", "Running-config atualizado em modo somente leitura.", "success", "refresh");
      return;
    }

    const menuAction = target.closest("[data-menu-action]");
    if (menuAction) {
      handleMenuAction(menuAction.dataset.menuAction);
      return;
    }
  }

  function initWizardEvents() {
    els.wizardNext.addEventListener("click", advanceWizard);
    els.wizardBack.addEventListener("click", () => {
      const wizard = state.wizard;
      if (!wizard || wizard.applying || wizard.step <= 1) return;
      wizard.step -= 1;
      updateWizardStepUI();
    });
    els.wizardApply.addEventListener("click", applyWizard);
    els.wizardForm.addEventListener("submit", (event) => {
      event.preventDefault();
      advanceWizard();
    });

    els.wizardStepper.addEventListener("click", (event) => {
      const item = event.target.closest("[data-step-target]");
      if (item) goToWizardStep(item.dataset.stepTarget);
    });

    els.wizardDevice.addEventListener("change", () => {
      const wizard = state.wizard;
      if (!wizard) return;
      wizard.data.deviceId = els.wizardDevice.value;
      wizard.data.iface = "";
      populateInterfaceOptions();
      setFieldError(els.wizardName, els.wizardNameError, "");
      setFieldError(els.wizardAclId, els.wizardAclIdError, "");
    });

    els.wizardInterface.addEventListener("change", () => {
      if (state.wizard) state.wizard.data.iface = els.wizardInterface.value;
    });

    $$('input[name="wizardDirection"]').forEach((radio) => {
      radio.addEventListener("change", () => {
        if (state.wizard && radio.checked) state.wizard.data.direction = radio.value;
      });
    });

    $$('input[name="wizardMode"]').forEach((radio) => {
      radio.addEventListener("change", () => {
        if (!state.wizard || !radio.checked) return;
        state.wizard.data.mode = radio.value;
        updateModePanels();
        updateExceptionsImpact();
        setTagError("destinations", "");
        if (state.wizard.step === 4) renderReview();
      });
    });

    els.wizardName.addEventListener("input", () => {
      if (state.wizard) state.wizard.data.name = els.wizardName.value;
      setFieldError(els.wizardName, els.wizardNameError, "");
    });

    els.wizardAclId.addEventListener("input", () => {
      if (state.wizard) state.wizard.data.aclId = Number(els.wizardAclId.value);
      setFieldError(els.wizardAclId, els.wizardAclIdError, "");
    });

    [
      [els.destinationsInput, "destinations"],
      [els.exceptionsInput, "exceptions"],
    ].forEach(([input, type]) => {
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === ",") {
          event.preventDefault();
          event.stopPropagation();
          addWizardTag(type, input.value);
        }
      });
      input.addEventListener("input", () => setTagError(type, ""));
    });

    els.wizardAllowDns.addEventListener("change", () => {
      if (state.wizard) {
        state.wizard.data.allowDns = els.wizardAllowDns.checked;
        if (state.wizard.step === 4) renderReview();
      }
    });

    els.wizardAllowUpdates.addEventListener("change", () => {
      if (state.wizard) {
        state.wizard.data.allowUpdates = els.wizardAllowUpdates.checked;
        if (state.wizard.step === 4) renderReview();
      }
    });

    els.confirmDiscardBtn?.addEventListener("click", confirmDrawerAction);
  }

  function initEvents() {
    els.sidebarToggle.addEventListener("click", toggleSidebar);
    els.mobileMenuToggle.addEventListener("click", () => setMobileSidebar(!els.sidebar.classList.contains("is-open")));
    els.sidebarScrim.addEventListener("click", () => setMobileSidebar(false));
    els.connectBtn.addEventListener("click", toggleConnection);
    els.drawerScrim.addEventListener("click", closeDrawer);

    els.globalSearch.addEventListener("input", () => {
      state.search = els.globalSearch.value.trim().toLowerCase();
      refreshCatalogForSearch();
    });

    els.globalSearch.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        navigateToPage("catalog");
      }
      if (event.key === "Escape") {
        els.globalSearch.value = "";
        state.search = "";
        refreshCatalogForSearch();
        els.globalSearch.blur();
      }
    });

    document.addEventListener("change", (event) => {
      const commandPreset = event.target.closest("#commandPreset");
      if (commandPreset) {
        const input = $("#commandInput");
        if (input) input.value = commandPreset.value;
      }

      if (event.target.id === "prefReducedMotion") {
        applyReducedMotion(event.target.checked);
      }

      if (event.target.id === "prefConfirmClose") {
        state.confirmClose = event.target.checked;
        writeStorage(STORAGE.confirmClose, String(state.confirmClose));
      }
    });

    document.addEventListener("keydown", (event) => {
      const modifier = event.ctrlKey || event.metaKey;

      if (event.key === "Escape") {
        if (els.discardDrawer.classList.contains("is-open")) {
          closeDrawer();
          return;
        }
        if ($$(".menu.is-open").length) {
          closeMenus();
          return;
        }
        if (isMobile() && els.sidebar.classList.contains("is-open")) {
          setMobileSidebar(false);
          return;
        }
        if (state.wizard) {
          event.preventDefault();
          requestCloseWizard();
        }
        return;
      }

      if (!modifier) return;
      const key = event.key.toLowerCase();
      if (key === "b") {
        event.preventDefault();
        toggleSidebar();
      } else if (key === "k") {
        event.preventDefault();
        els.globalSearch.focus();
        els.globalSearch.select();
      } else if (key === "n") {
        event.preventDefault();
        openWizard("custom");
      }
    });

    mobileQuery.addEventListener("change", () => {
      setMobileSidebar(false);
      applySidebarState();
    });

    document.addEventListener("click", handleDocumentClick);
    initMenus();
  }

  function init() {
    const initialTheme = ["light", "dark", "huawei"].includes(els.html.dataset.theme)
      ? els.html.dataset.theme
      : "dark";
    setTheme(initialTheme, false);

    // O wizard é uma página dedicada: ele vive dentro da área de conteúdo.
    els.wizardMount.appendChild(els.wizardPage);

    applySidebarState();
    initAccordions();
    initEvents();
    initWizardEvents();
    updateConnectionUI();
    updateTargets();
    navigateToPage("dashboard", { force: true });
    window.__hwm = { state, els, rules, advanceWizard, validateStep };
    updateData();
    updateClock();
    setInterval(updateClock, 1000);
    applyReducedMotion(state.reducedMotion);
    syncSettingsUI();
  }

  init();
})();
