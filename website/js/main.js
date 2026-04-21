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
    {
      title: "Get started",
      links: [
        { href: siteConfig.dashboardUrl, label: "Add your site" },
        { href: siteConfig.workspaceUrl, label: "Workspace" },
        { href: "/demo", label: "Try the demo" },
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
            <img class="brand-logo" src="${siteConfig.logoPath}" alt="${siteConfig.brand}">
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
        ${navLinks
          .map((link) => `<a href="${link.href}" class="${pageName === link.page ? "active" : ""}">${link.label}</a>`)
          .join("")}
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
            <img src="${siteConfig.logoPath}" alt="${siteConfig.brand}">
          </a>
          <p>Launch a website chatbot trained on your public pages in about five minutes. Answer buyer questions, guide visitors to the next click, and stay live 24/7 without extra setup.</p>
          <div class="button-row">
            <a class="button button-primary button-sm" href="${siteConfig.dashboardUrl}">Start free</a>
            <a class="button button-ghost button-sm" href="/demo">Try demo</a>
          </div>
          <div class="social-links" aria-label="Social links">
            <a href="/" aria-label="5minBot on X">X</a>
            <a href="/" aria-label="5minBot on LinkedIn">in</a>
            <a href="/" aria-label="5minBot on GitHub">gh</a>
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
        <p>&copy; ${year} ${siteConfig.brand}. Built for founders who want a website chatbot live fast.</p>
        <p>Your 24/7 AI salesman. Live in about 5 minutes.</p>
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
          if (navHost.classList.contains("nav-open")) {
            closePanel();
          } else {
            openPanel();
          }
        });

        scrim.addEventListener("click", closePanel);
        panel.querySelectorAll("a").forEach((link) => link.addEventListener("click", closePanel));
        document.addEventListener("keydown", function (event) {
          if (event.key === "Escape") {
            closePanel();
          }
        });
      }

      const setScrolled = () => {
        navHost.classList.toggle("is-scrolled", window.scrollY > 12);
      };

      setScrolled();
      window.addEventListener("scroll", setScrolled, { passive: true });
    }

    if (footerHost) {
      footerHost.innerHTML = buildFooter();
    }
  }

  function setupRevealAnimations() {
    const targets = Array.from(document.querySelectorAll("[data-reveal], .animate-on-scroll"));
    if (!targets.length) return;

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    targets.forEach((node, index) => {
      node.classList.add("reveal-ready");
      const delay = Number(node.dataset.delay || 0) || (index % 3) * 70;
      node.style.transitionDelay = `${delay}ms`;
      if (prefersReducedMotion) {
        node.classList.add("is-visible");
      }
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
      const current = Math.round(value * eased);
      node.textContent = `${current}${suffix}`;
      if (progress < 1) {
        requestAnimationFrame(tick);
      }
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

      const activate = (index) => {
        tabs.forEach((tab, tabIndex) => tab.classList.toggle("active", tabIndex === index));
        panels.forEach((panel, panelIndex) => panel.classList.toggle("active", panelIndex === index));
      };

      tabs.forEach((tab, index) => {
        tab.addEventListener("click", () => activate(index));
      });

      activate(0);
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
        const target = raw
          ? `${siteConfig.dashboardUrl}&url=${encodeURIComponent(raw)}`
          : siteConfig.dashboardUrl;
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
    if (demoWidgetBootstrapped || document.querySelector('script[data-5minbot-demo-widget="true"]')) {
      return;
    }

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
          if (toggle && panel && !panel.classList.contains("aiwa-open")) {
            toggle.click();
          }
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

      if (!toggle || !input || !send) {
        return false;
      }

      if (panel && !panel.classList.contains("aiwa-open")) {
        toggle.click();
      }

      window.setTimeout(function () {
        input.value = question;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        send.click();
      }, 200);

      return true;
    };

    if (tryRealWidget()) {
      return true;
    }

    if (demoWidgetReadyPromise) {
      demoWidgetReadyPromise.then(function () {
        tryRealWidget();
      });
      return true;
    }

    const iframe = document.querySelector("[data-hero-preview] iframe");
    if (!iframe || !iframe.contentWindow) {
      return false;
    }

    try {
      const targetOrigin = new URL(iframe.src, window.location.href).origin;
      iframe.contentWindow.postMessage({ type: "sitecloser:ask", question }, targetOrigin);
      return true;
    } catch (error) {
      return false;
    }
  }

  function wirePromptChips() {
    document.querySelectorAll("[data-demo-ask]").forEach((chip) => {
      chip.addEventListener("click", function () {
        const question = chip.dataset.demoAsk || "";
        if (question) {
          sendPromptToEmbeddedWidget(question);
        }
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
    mountPreview("[data-hero-preview]", "hero");
    loadDemoFloatingWidget();
    wirePromptChips();
    document.body.classList.add("page-ready");
  });
})();
