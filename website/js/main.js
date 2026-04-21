(function () {
  const siteConfig = {
    brand: "5minBot",
    logoPath: "/website/logo.svg",
    dashboardUrl: "/dashboard?onboarding=1",
    workspaceUrl: "/dashboard",
    supportUrl: "/support",
    fallbackDemoSiteId: "d94c64af-65d2-410f-a6d4-c9f05f9919c0",
    fallbackAppUrl: "https://ai-website-agent-aikinley.onrender.com",
    appUrl: window.location.origin,
    heroPreviewPath: "/website/hero-preview.html",
  };

  const navLinks = [
    { href: "/features", label: "Features", page: "features" },
    { href: "/pricing", label: "Pricing", page: "pricing" },
    { href: "/how-it-works", label: "How it works", page: "how-it-works" },
    { href: "/demo", label: "Live demo", page: "demo" },
    { href: "/blog", label: "Insights", page: "blog" },
  ];

  const footerColumns = [
    {
      title: "Product",
      links: [
        { href: "/features", label: "Features" },
        { href: "/pricing", label: "Pricing" },
        { href: "/how-it-works", label: "How it works" },
        { href: "/demo", label: "Live demo" },
      ],
    },
    {
      title: "Resources",
      links: [
        { href: "/blog", label: "Insights" },
        { href: "/support", label: "Support" },
        { href: "/security", label: "Security" },
        { href: "/privacy", label: "Privacy" },
      ],
    },
    {
      title: "Legal",
      links: [
        { href: "/privacy", label: "Privacy" },
        { href: "/terms", label: "Terms" },
        { href: "/security", label: "Security" },
      ],
    },
  ];

  const pageName = document.body.dataset.page || "";
  const year = new Date().getFullYear();
  let demoConfigPromise = null;
  let demoWidgetReadyPromise = null;
  let demoWidgetBootstrapped = false;

  function buildNav() {
    return `
      <div class="container">
        <div class="nav-inner">
          <a class="brand" href="/" aria-label="${siteConfig.brand} home">
            <svg class="brand-logo" width="240" height="44" viewBox="0 0 240 44" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${siteConfig.brand}">
              <defs>
                <linearGradient id="nav-logo-icon-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stop-color="#8B5CF6"/>
                  <stop offset="100%" stop-color="#06B6D4"/>
                </linearGradient>
                <linearGradient id="nav-logo-text-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stop-color="#8B5CF6"/>
                  <stop offset="100%" stop-color="#06B6D4"/>
                </linearGradient>
              </defs>
              <rect x="0" y="4" width="36" height="36" rx="10" fill="url(#nav-logo-icon-gradient)"/>
              <path d="M19 12 L13 22 L18 22 L15 32 L23 20 L18 20 Z" fill="white"/>
              <text x="50" y="29" font-family="system-ui,-apple-system,sans-serif" font-size="22" font-weight="800" fill="#F1F0FF" letter-spacing="-0.8px">5min</text>
              <text x="108" y="29" font-family="system-ui,-apple-system,sans-serif" font-size="22" font-weight="800" fill="url(#nav-logo-text-gradient)" letter-spacing="-0.8px">Bot</text>
            </svg>
          </a>
          <nav class="nav-links" aria-label="Primary navigation">
            ${navLinks
              .map((link) => `<a href="${link.href}" class="${pageName === link.page ? "active" : ""}">${link.label}</a>`)
              .join("")}
          </nav>
          <div class="nav-cta">
            <a class="button button-ghost button-sm" href="${siteConfig.workspaceUrl}">Sign in</a>
            <a class="button button-primary button-sm" href="${siteConfig.dashboardUrl}">Start free</a>
            <button class="nav-mobile-toggle" type="button" aria-label="Open menu">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
                <path d="M3 5H15" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
                <path d="M3 9H15" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
                <path d="M3 13H11" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
      <div class="nav-panel" aria-label="Mobile navigation">
        ${navLinks.map((link) => `<a href="${link.href}" class="${pageName === link.page ? "active" : ""}">${link.label}</a>`).join("")}
        <a href="${siteConfig.supportUrl}">Support</a>
        <a class="button button-ghost" href="${siteConfig.workspaceUrl}">Sign in</a>
        <a class="button button-primary" href="${siteConfig.dashboardUrl}">Start free</a>
      </div>
      <div class="nav-scrim"></div>
    `;
  }

  function buildFooter() {
    return `
      <div class="container footer-grid">
        <div class="footer-intro">
          <a class="footer-logo" href="/" aria-label="${siteConfig.brand} home">
            <svg class="brand-logo" width="240" height="44" viewBox="0 0 240 44" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${siteConfig.brand}">
              <defs>
                <linearGradient id="footer-logo-icon-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stop-color="#8B5CF6"/>
                  <stop offset="100%" stop-color="#06B6D4"/>
                </linearGradient>
                <linearGradient id="footer-logo-text-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stop-color="#8B5CF6"/>
                  <stop offset="100%" stop-color="#06B6D4"/>
                </linearGradient>
              </defs>
              <rect x="0" y="4" width="36" height="36" rx="10" fill="url(#footer-logo-icon-gradient)"/>
              <path d="M19 12 L13 22 L18 22 L15 32 L23 20 L18 20 Z" fill="white"/>
              <text x="50" y="29" font-family="system-ui,-apple-system,sans-serif" font-size="22" font-weight="800" fill="#F1F0FF" letter-spacing="-0.8px">5min</text>
              <text x="108" y="29" font-family="system-ui,-apple-system,sans-serif" font-size="22" font-weight="800" fill="url(#footer-logo-text-gradient)" letter-spacing="-0.8px">Bot</text>
            </svg>
          </a>
          <p>Launch a premium website chatbot trained on your public pages in minutes. Answer buyer questions, guide the next click, and keep selling after hours.</p>
          <div class="button-row">
            <a class="button button-primary button-sm" href="${siteConfig.dashboardUrl}">Start free</a>
            <a class="button button-ghost button-sm" href="/demo">Try demo</a>
          </div>
          <div class="social-links" aria-label="Social links">
            <a href="/" aria-label="5minBot on X">X</a>
            <a href="/" aria-label="5minBot on LinkedIn">in</a>
            <a href="/" aria-label="5minBot on GitHub">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M12 0.5C5.65 0.5 0.5 5.65 0.5 12c0 5.09 3.3 9.41 7.88 10.93.58.11.79-.25.79-.56 0-.28-.01-1.02-.02-2-3.21.7-3.89-1.55-3.89-1.55-.53-1.33-1.28-1.68-1.28-1.68-1.05-.72.08-.71.08-.71 1.16.08 1.77 1.19 1.77 1.19 1.03 1.76 2.69 1.25 3.35.96.1-.75.4-1.25.72-1.54-2.56-.29-5.25-1.28-5.25-5.69 0-1.26.45-2.29 1.19-3.09-.12-.29-.52-1.46.11-3.04 0 0 .98-.31 3.2 1.18.93-.26 1.93-.39 2.92-.39s1.99.13 2.92.39c2.22-1.49 3.2-1.18 3.2-1.18.63 1.58.23 2.75.11 3.04.74.8 1.19 1.83 1.19 3.09 0 4.42-2.69 5.39-5.26 5.68.41.35.78 1.03.78 2.08 0 1.5-.01 2.71-.01 3.08 0 .31.21.67.8.56A11.5 11.5 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z"/>
              </svg>
            </a>
          </div>
        </div>
        ${footerColumns
          .map(
            (column) => `
              <div class="footer-column">
                <h4>${column.title}</h4>
                <div class="footer-links">
                  ${column.links.map((link) => `<a href="${link.href}">${link.label}</a>`).join("")}
                </div>
              </div>
            `
          )
          .join("")}
      </div>
      <div class="container footer-bottom">
        <p>&copy; ${year} ${siteConfig.brand}. Your 24/7 AI salesman. Live in 5 minutes.</p>
        <p>Built for founders who want a fast website chatbot that actually helps buyers convert.</p>
      </div>
    `;
  }

  function mountSharedChrome() {
    const navHost = document.querySelector("[data-nav]");
    const footerHost = document.querySelector("[data-footer]");

    if (navHost) {
      navHost.innerHTML = buildNav();
      const toggle = navHost.querySelector(".nav-mobile-toggle");
      const panel = navHost.querySelector(".nav-panel");
      const scrim = navHost.querySelector(".nav-scrim");

      const closePanel = () => {
        navHost.classList.remove("nav-open");
        document.body.classList.remove("nav-open");
      };

      const openPanel = () => {
        navHost.classList.add("nav-open");
        document.body.classList.add("nav-open");
      };

      if (toggle && panel && scrim) {
        toggle.addEventListener("click", function () {
          if (navHost.classList.contains("nav-open")) closePanel();
          else openPanel();
        });
        scrim.addEventListener("click", closePanel);
        panel.querySelectorAll("a").forEach((link) => link.addEventListener("click", closePanel));
        document.addEventListener("keydown", function (event) {
          if (event.key === "Escape") closePanel();
        });
      }

      const setScrolled = () => navHost.classList.toggle("is-scrolled", window.scrollY > 12);
      setScrolled();
      window.addEventListener("scroll", setScrolled, { passive: true });
    }

    if (footerHost) footerHost.innerHTML = buildFooter();
  }

  function setupRevealAnimations() {
    const targets = Array.from(document.querySelectorAll("[data-reveal], .animate-on-scroll"));
    if (!targets.length) return;

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    targets.forEach((node, index) => {
      node.classList.add("reveal-ready");
      const delay = Number(node.dataset.delay || 0) || (index % 3) * 90;
      node.style.transitionDelay = `${delay}ms`;
      if (prefersReducedMotion) node.classList.add("is-visible");
    });
    if (prefersReducedMotion) return;

    const observer = new IntersectionObserver(
      (entries, obs) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          obs.unobserve(entry.target);
        });
      },
      { threshold: 0.16, rootMargin: "0px 0px -10% 0px" }
    );
    targets.forEach((node) => observer.observe(node));
  }

  function animateCount(node) {
    const value = Number(node.dataset.value || 0);
    const suffix = node.dataset.suffix || "";
    const duration = 1200;
    const start = performance.now();

    function tick(now) {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      node.textContent = `${Math.round(value * eased)}${suffix}`;
      if (progress < 1) requestAnimationFrame(tick);
    }

    requestAnimationFrame(tick);
  }

  function setupCounters() {
    const counters = Array.from(document.querySelectorAll("[data-count-up]"));
    if (!counters.length) return;
    const observer = new IntersectionObserver(
      (entries, obs) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          animateCount(entry.target);
          obs.unobserve(entry.target);
        });
      },
      { threshold: 0.4 }
    );
    counters.forEach((node) => observer.observe(node));
  }

  function setupShowcases() {
    document.querySelectorAll("[data-showcase]").forEach((shell) => {
      const tabs = Array.from(shell.querySelectorAll("[data-showcase-tab]"));
      const panels = Array.from(shell.querySelectorAll("[data-showcase-panel]"));
      if (!tabs.length || !panels.length) return;

      let activeIndex = 0;
      let timer = null;

      const activate = (index) => {
        activeIndex = index;
        tabs.forEach((tab, tabIndex) => tab.classList.toggle("active", tabIndex === index));
        panels.forEach((panel, panelIndex) => panel.classList.toggle("active", panelIndex === index));
      };

      const startAuto = () => {
        if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
        timer = window.setInterval(() => {
          activate((activeIndex + 1) % tabs.length);
        }, 5200);
      };

      const stopAuto = () => {
        if (timer) {
          window.clearInterval(timer);
          timer = null;
        }
      };

      tabs.forEach((tab, index) => {
        tab.addEventListener("click", () => {
          stopAuto();
          activate(index);
          startAuto();
        });
      });

      shell.addEventListener("mouseenter", stopAuto);
      shell.addEventListener("mouseleave", startAuto);
      activate(0);
      startAuto();
    });
  }

  function setupPricingToggle() {
    const toggle = document.querySelector("[data-pricing-toggle]");
    if (!toggle) return;
    const cards = Array.from(document.querySelectorAll("[data-plan]"));

    const update = (mode) => {
      document.body.classList.add("pricing-switching");
      toggle.querySelectorAll("button").forEach((button) => {
        button.classList.toggle("active", button.dataset.billing === mode);
      });

      cards.forEach((card) => {
        const price = card.querySelector("[data-price]");
        const note = card.querySelector("[data-price-note]");
        if (!price || !note) return;
        price.textContent = card.dataset[mode === "annual" ? "annualPrice" : "monthlyPrice"] || "";
        note.textContent = card.dataset[mode === "annual" ? "annualNote" : "monthlyNote"] || "";
      });

      window.setTimeout(() => document.body.classList.remove("pricing-switching"), 180);
    };

    toggle.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-billing]");
      if (!button) return;
      update(button.dataset.billing);
    });

    update("monthly");
  }

  function setupFaqAccordions() {
    document.querySelectorAll("[data-faq-item]").forEach((item, index) => {
      const trigger = item.querySelector("[data-faq-trigger]");
      const content = item.querySelector(".faq-content");
      if (!trigger || !content) return;

      const setOpen = (open) => {
        item.classList.toggle("open", open);
        content.style.maxHeight = open ? `${content.scrollHeight}px` : "0px";
      };

      trigger.addEventListener("click", () => {
        const shouldOpen = !item.classList.contains("open");
        document.querySelectorAll("[data-faq-item]").forEach((other) => {
          if (other !== item) {
            other.classList.remove("open");
            const otherContent = other.querySelector(".faq-content");
            if (otherContent) otherContent.style.maxHeight = "0px";
          }
        });
        setOpen(shouldOpen);
      });

      setOpen(index === 0 || item.dataset.open === "true");
    });
  }

  function setupUrlForms() {
    document.querySelectorAll("[data-url-form]").forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        const input = form.querySelector("input[name='url']");
        const raw = input ? input.value.trim() : "";
        const target = raw ? `${siteConfig.dashboardUrl}&url=${encodeURIComponent(raw)}` : siteConfig.dashboardUrl;
        window.location.href = target;
      });
    });
  }

  async function resolveDemoConfig() {
    if (demoConfigPromise) return demoConfigPromise;

    demoConfigPromise = (async function () {
      const fallback = {
        appUrl: siteConfig.fallbackAppUrl,
        siteId: siteConfig.fallbackDemoSiteId,
      };

      try {
        const response = await fetch("/api/sites");
        if (!response.ok) return fallback;
        const payload = await response.json();
        const sites = Array.isArray(payload) ? payload : Array.isArray(payload.sites) ? payload.sites : [];
        const readySites = sites.filter((site) => site && site.status === "ready" && site.site_id);
        if (!readySites.length) return fallback;

        const currentHost = window.location.hostname.toLowerCase();
        const preferred =
          readySites.find((site) => {
            const url = String(site.url || "").toLowerCase();
            const name = String(site.name || "").toLowerCase();
            return url.includes(currentHost) || url.includes("5minbot.com") || name.includes("5minbot");
          }) || readySites[0];

        return {
          appUrl: window.location.origin,
          siteId: preferred.site_id,
        };
      } catch (error) {
        return fallback;
      }
    })();

    return demoConfigPromise;
  }

  async function mountPreview(targetSelector, mode) {
    const mount = document.querySelector(targetSelector);
    if (!mount) return;

    const demoConfig = await resolveDemoConfig();
    const iframe = document.createElement("iframe");
    iframe.className = "hero-preview-frame";
    iframe.loading = "lazy";
    iframe.title = mode === "demo" ? "Interactive 5minBot demo" : "Interactive 5minBot preview";
    iframe.setAttribute("allow", "clipboard-read; clipboard-write");
    iframe.src =
      `${siteConfig.heroPreviewPath}?mode=${encodeURIComponent(mode)}&site_id=${encodeURIComponent(demoConfig.siteId)}` +
      `&app_url=${encodeURIComponent(demoConfig.appUrl)}`;

    mount.innerHTML = "";
    mount.appendChild(iframe);
  }

  async function loadDemoFloatingWidget() {
    if (pageName !== "demo") return;

    const demoConfig = await resolveDemoConfig();
    if (demoWidgetBootstrapped || document.querySelector('script[data-5minbot-demo-widget="true"]')) return;

    demoWidgetBootstrapped = true;
    demoWidgetReadyPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = `${demoConfig.appUrl}/widget/agent.js`;
      script.setAttribute("data-site-id", demoConfig.siteId);
      script.setAttribute("data-5minbot-demo-widget", "true");
      script.onload = function () {
        window.setTimeout(function () {
          const toggle = document.getElementById("aiwa-toggle");
          const panel = document.getElementById("aiwa-panel");
          if (toggle && panel && !panel.classList.contains("aiwa-open")) toggle.click();
          resolve();
        }, 280);
      };
      script.onerror = function (error) {
        demoWidgetBootstrapped = false;
        reject(error);
      };
      document.body.appendChild(script);
    }).catch(function () {});
  }

  function sendPromptToEmbeddedWidget(question) {
    const tryRealWidget = () => {
      const toggle = document.querySelector("#aiwa-toggle");
      const panel = document.querySelector("#aiwa-panel");
      const input = document.querySelector("#aiwa-input");
      const send = document.querySelector("#aiwa-send");
      if (!toggle || !input || !send) return false;

      if (panel && !panel.classList.contains("aiwa-open")) toggle.click();

      window.setTimeout(function () {
        input.value = question;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        send.click();
      }, 200);
      return true;
    };

    if (tryRealWidget()) return true;

    if (demoWidgetReadyPromise) {
      demoWidgetReadyPromise.then(function () {
        tryRealWidget();
      });
      return true;
    }

    const iframe = document.querySelector("[data-live-preview] iframe");
    if (!iframe || !iframe.contentWindow) return false;

    try {
      const targetOrigin = new URL(iframe.src, window.location.href).origin;
      iframe.contentWindow.postMessage({ type: "5minbot:ask", question }, targetOrigin);
      return true;
    } catch (error) {
      return false;
    }
  }

  function wirePromptChips() {
    document.querySelectorAll("[data-demo-ask]").forEach((chip) => {
      chip.addEventListener("click", function () {
        const question = chip.dataset.demoAsk || "";
        if (question) sendPromptToEmbeddedWidget(question);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    mountSharedChrome();
    setupRevealAnimations();
    setupCounters();
    setupShowcases();
    setupPricingToggle();
    setupFaqAccordions();
    setupUrlForms();
    mountPreview("[data-live-preview]", "hero");
    loadDemoFloatingWidget();
    wirePromptChips();
    document.body.classList.add("page-ready");
  });
})();
