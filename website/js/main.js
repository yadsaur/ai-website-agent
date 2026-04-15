(function () {
  const siteConfig = {
    brand: "SiteCloser",
    tagline: "Grounded website sales assistant",
    dashboardUrl: "/dashboard?onboarding=1",
    workspaceUrl: "/dashboard",
    fallbackDemoSiteId: "d94c64af-65d2-410f-a6d4-c9f05f9919c0",
    fallbackAppUrl: "https://ai-website-agent-aikinley.onrender.com",
    appUrl: window.location.origin,
    heroPreviewPath: "/website/hero-preview.html",
  };

  const navLinks = [
    { href: "/features", label: "Features", page: "features" },
    { href: "/pricing", label: "Pricing", page: "pricing" },
    { href: "/how-it-works", label: "How it works", page: "how-it-works" },
    { href: "/demo", label: "Demo", page: "demo" },
    { href: "/blog", label: "Insights", page: "blog" },
  ];

  const footerColumns = [
    {
      title: "Product",
      links: [
        { href: "/features", label: "Features" },
        { href: "/pricing", label: "Pricing" },
        { href: "/how-it-works", label: "How it works" },
        { href: "/demo", label: "Interactive demo" },
      ],
    },
    {
      title: "Resources",
      links: [
        { href: "/blog", label: "Insights" },
        { href: "/support", label: "Support" },
        { href: "/security", label: "Security" },
        { href: "/dashboard", label: "Workspace" },
      ],
    },
    {
      title: "Legal",
      links: [
        { href: "/privacy", label: "Privacy" },
        { href: "/terms", label: "Terms" },
      ],
    },
    {
      title: "Get started",
      links: [
        { href: "/dashboard?onboarding=1", label: "Start onboarding" },
        { href: "/demo", label: "Try the live assistant" },
        { href: "/support", label: "Talk to support" },
      ],
    },
  ];

  const pageName = document.body.dataset.page || "";
  const year = new Date().getFullYear();
  let demoConfigPromise = null;
  let demoWidgetReadyPromise = null;

  function buildNav() {
    return `
      <div class="container">
        <div class="nav-inner">
          <a class="brand" href="/" aria-label="${siteConfig.brand} home">
            <span class="brand-mark"></span>
            <span class="brand-text">
              <span>${siteConfig.brand}</span>
              <small>${siteConfig.tagline}</small>
            </span>
          </a>
          <nav class="nav-links" aria-label="Primary navigation">
            ${navLinks
              .map(
                (link) =>
                  `<a href="${link.href}" class="${pageName === link.page ? "active" : ""}">${link.label}</a>`
              )
              .join("")}
          </nav>
          <div class="nav-cta">
            <a class="button button-ghost" href="${siteConfig.workspaceUrl}">Workspace</a>
            <a class="button button-primary" href="${siteConfig.dashboardUrl}">Start free &rarr;</a>
            <button class="nav-mobile-toggle" type="button" aria-label="Open menu">&#9776;</button>
          </div>
        </div>
        <div class="nav-panel" aria-label="Mobile navigation">
          ${navLinks
            .map(
              (link) =>
                `<a href="${link.href}" class="${pageName === link.page ? "active" : ""}">${link.label}</a>`
            )
            .join("")}
          <a href="${siteConfig.workspaceUrl}" class="button button-ghost">Workspace</a>
          <a href="${siteConfig.dashboardUrl}" class="button button-primary">Start free &rarr;</a>
        </div>
      </div>
    `;
  }

  function buildFooter() {
    return `
      <div class="container footer-grid">
        <div class="footer-intro">
          <a class="footer-logo" href="/">
            <span class="brand-mark"></span>
            <span>${siteConfig.brand}</span>
          </a>
          <p>${siteConfig.brand} turns your website into a grounded, conversion-focused assistant that can answer buyer questions, guide visitors, and help teams launch faster.</p>
          <div class="footer-actions">
            <a class="button button-primary" href="${siteConfig.dashboardUrl}">Start free &rarr;</a>
            <a class="button button-ghost" href="/support">Get help</a>
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
        <p>&copy; ${year} ${siteConfig.brand}. Clear answers. Sharper buying journeys.</p>
      </div>
    `;
  }

  function mountSharedChrome() {
    const navHost = document.querySelector("[data-nav]");
    const footerHost = document.querySelector("[data-footer]");

    if (navHost) {
      navHost.innerHTML = buildNav();
      const nav = navHost;
      const panel = navHost.querySelector(".nav-panel");
      const toggle = navHost.querySelector(".nav-mobile-toggle");

      if (toggle && panel) {
        toggle.addEventListener("click", () => {
          panel.classList.toggle("open");
        });
      }

      const handleScroll = () => {
        nav.classList.toggle("scrolled", window.scrollY > 8);
      };
      let navTicking = false;
      const onScroll = () => {
        if (navTicking) {
          return;
        }
        navTicking = true;
        window.requestAnimationFrame(() => {
          handleScroll();
          navTicking = false;
        });
      };

      handleScroll();
      window.addEventListener("scroll", onScroll, { passive: true });
    }

    if (footerHost) {
      footerHost.innerHTML = buildFooter();
    }
  }

  function setupRevealAnimations() {
    const nodes = document.querySelectorAll("[data-reveal]");
    if (!nodes.length) {
      return;
    }
    nodes.forEach((node) => {
      node.classList.add("revealed");
      node.style.transitionDelay = "0ms";
    });
  }

  async function resolveDemoConfig() {
    if (demoConfigPromise) {
      return demoConfigPromise;
    }

    demoConfigPromise = (async () => {
      const fallback = {
        appUrl: siteConfig.fallbackAppUrl,
        siteId: siteConfig.fallbackDemoSiteId,
      };

      try {
        const response = await fetch("/api/sites");
        if (!response.ok) {
          return fallback;
        }

        const payload = await response.json();
        const sites = Array.isArray(payload) ? payload : Array.isArray(payload.sites) ? payload.sites : [];
        const readySites = sites.filter((site) => site && site.status === "ready" && site.site_id);
        if (!readySites.length) {
          return fallback;
        }

        const currentHost = window.location.hostname.toLowerCase();
        const preferred = readySites.find((site) => {
          const url = String(site.url || "").toLowerCase();
          const name = String(site.name || "").toLowerCase();
          return (
            url.includes("ai-website-agent-aikinley.onrender.com") ||
            url.includes(currentHost) ||
            name.includes("sitecloser")
          );
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

  function setupPricingToggle() {
    const toggle = document.querySelector("[data-pricing-toggle]");
    if (!toggle) {
      return;
    }

    const cards = document.querySelectorAll("[data-plan]");

    const update = (mode) => {
      toggle.querySelectorAll("button").forEach((button) => {
        button.classList.toggle("active", button.dataset.billing === mode);
      });

      cards.forEach((card) => {
        const price = card.querySelector("[data-price]");
        const note = card.querySelector("[data-price-note]");
        if (!price || !note) {
          return;
        }
        price.textContent = card.dataset[mode === "annual" ? "annualPrice" : "monthlyPrice"] || "";
        note.textContent = card.dataset[mode === "annual" ? "annualNote" : "monthlyNote"] || "";
      });
    };

    toggle.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-billing]");
      if (!button) {
        return;
      }
      update(button.dataset.billing);
    });

    update("monthly");
  }

  async function loadDemoWidget() {
    if (pageName !== "demo") {
      return;
    }

    const demoConfig = await resolveDemoConfig();
    if (document.querySelector('script[data-sitecloser-demo-widget="true"]')) {
      return;
    }

    demoWidgetReadyPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = `${demoConfig.appUrl}/widget/agent.js`;
      script.setAttribute("data-site-id", demoConfig.siteId);
      script.setAttribute("data-sitecloser-demo-widget", "true");
      script.onload = () => {
        window.setTimeout(() => {
          const toggle = document.getElementById("aiwa-toggle");
          const panel = document.getElementById("aiwa-panel");
          if (toggle && panel && !panel.classList.contains("aiwa-open")) {
            toggle.click();
          }
          resolve();
        }, 240);
      };
      script.onerror = reject;
      document.body.appendChild(script);
    }).catch(() => {});
  }

  async function loadHeroPreview() {
    const mount = document.querySelector("[data-hero-preview]");
    if (!mount) {
      return;
    }

    const demoConfig = await resolveDemoConfig();
    const iframe = document.createElement("iframe");
    iframe.className = "hero-preview-frame";
    iframe.loading = "lazy";
    iframe.title = "Interactive SiteCloser preview";
    iframe.setAttribute("allow", "clipboard-read; clipboard-write");
    iframe.src =
      `${siteConfig.heroPreviewPath}?mode=hero&site_id=${encodeURIComponent(demoConfig.siteId)}` +
      `&app_url=${encodeURIComponent(demoConfig.appUrl)}`;
    mount.innerHTML = "";
    mount.appendChild(iframe);
  }

  function sendPromptToEmbeddedWidget(question) {
    const iframe =
      document.querySelector("[data-demo-widget] iframe") ||
      document.querySelector("[data-hero-preview] iframe");

    if (iframe) {
      try {
        const targetOrigin = new URL(iframe.src, window.location.href).origin;
        iframe.contentWindow.postMessage(
          { type: "sitecloser:ask", question },
          targetOrigin
        );
        return true;
      } catch (error) {
        return false;
      }
    }

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

      window.setTimeout(() => {
        input.value = question;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        send.click();
      }, 180);

      return true;
    };

    if (tryRealWidget()) {
      return true;
    }

    if (demoWidgetReadyPromise) {
      demoWidgetReadyPromise.then(() => {
        tryRealWidget();
      });
      return true;
    }

    return false;
  }

  function wirePromptChips() {
    document.querySelectorAll("[data-demo-ask]").forEach((chip) => {
      chip.addEventListener("click", () => {
        const question = chip.dataset.demoAsk || "";
        if (sendPromptToEmbeddedWidget(question)) {
          return;
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    mountSharedChrome();
    setupRevealAnimations();
    setupPricingToggle();
    loadDemoWidget();
    loadHeroPreview();
    wirePromptChips();
    document.body.classList.add("page-ready");
  });
})();
