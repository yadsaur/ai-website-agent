(function () {
  const siteConfig = {
    brand: "5minBot",
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
        { href: "/demo", label: "Demo" },
        { href: "/dashboard", label: "Workspace" },
      ],
    },
    {
      title: "Resources",
      links: [
        { href: "/how-it-works", label: "How it works" },
        { href: "/blog", label: "Insights" },
        { href: "/support", label: "Support" },
      ],
    },
    {
      title: "Trust",
      links: [
        { href: "/security", label: "Security" },
        { href: "/privacy", label: "Privacy" },
        { href: "/terms", label: "Terms" },
      ],
    },
    {
      title: "Get started",
      links: [
        { href: "/dashboard?onboarding=1", label: "Add your site" },
        { href: "/demo", label: "Try the live demo" },
        { href: "/pricing", label: "See pricing" },
      ],
    },
  ];

  const pageName = document.body.dataset.page || "";
  const year = new Date().getFullYear();
  let demoConfigPromise = null;

  function buildNav() {
    return `
      <div class="container">
        <div class="nav-inner">
          <a class="brand" href="/" aria-label="${siteConfig.brand} home">
            <span class="brand-mark"></span>
            <span class="brand-text">${siteConfig.brand}</span>
          </a>
          <nav class="nav-links" aria-label="Primary navigation">
            ${navLinks
              .map((link) => `<a href="${link.href}" class="${pageName === link.page ? "active" : ""}">${link.label}</a>`)
              .join("")}
          </nav>
          <div class="nav-cta">
            <a class="button button-ghost" href="${siteConfig.workspaceUrl}">Workspace</a>
            <a class="button button-primary" href="${siteConfig.dashboardUrl}">Add your site</a>
            <button class="nav-mobile-toggle" type="button" aria-label="Open menu">&#9776;</button>
          </div>
        </div>
        <div class="nav-panel" aria-label="Mobile navigation">
          ${navLinks.map((link) => `<a href="${link.href}" class="${pageName === link.page ? "active" : ""}">${link.label}</a>`).join("")}
          <a href="/support">Support</a>
          <a href="${siteConfig.workspaceUrl}" class="button button-ghost">Workspace</a>
          <a href="${siteConfig.dashboardUrl}" class="button button-primary">Add your site</a>
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
          <p>Deploy a chatbot trained on your public website in about five minutes. It answers buyer questions, guides visitors to the next click, and helps teams launch a cleaner conversion experience without a long setup project.</p>
          <div class="footer-actions">
            <a class="button button-primary" href="${siteConfig.dashboardUrl}">Add your site</a>
            <a class="button button-ghost" href="/demo">Try the demo</a>
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
        <p>&copy; ${year} ${siteConfig.brand}. Public-site chatbot deployment in minutes.</p>
      </div>
    `;
  }

  function mountSharedChrome() {
    const navHost = document.querySelector("[data-nav]");
    const footerHost = document.querySelector("[data-footer]");

    if (navHost) {
      navHost.innerHTML = buildNav();
      const panel = navHost.querySelector(".nav-panel");
      const toggle = navHost.querySelector(".nav-mobile-toggle");

      if (toggle && panel) {
        toggle.addEventListener("click", function () {
          panel.classList.toggle("open");
        });
      }

      const setScrolled = () => {
        navHost.classList.toggle("scrolled", window.scrollY > 8);
      };

      setScrolled();
      window.addEventListener("scroll", setScrolled, { passive: true });
    }

    if (footerHost) {
      footerHost.innerHTML = buildFooter();
    }
  }

  function setupRevealAnimations() {
    document.querySelectorAll("[data-reveal]").forEach((node) => {
      node.classList.add("revealed");
      node.style.transitionDelay = "0ms";
    });
  }

  async function resolveDemoConfig() {
    if (demoConfigPromise) {
      return demoConfigPromise;
    }

    demoConfigPromise = (async function () {
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

    toggle.addEventListener("click", function (event) {
      const button = event.target.closest("button[data-billing]");
      if (!button) {
        return;
      }
      update(button.dataset.billing);
    });

    update("monthly");
  }

  async function mountPreview(targetSelector, mode) {
    const mount = document.querySelector(targetSelector);
    if (!mount) {
      return;
    }

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

  function sendPromptToEmbeddedWidget(question) {
    const iframe =
      document.querySelector("[data-demo-widget] iframe") ||
      document.querySelector("[data-hero-preview] iframe");

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
        sendPromptToEmbeddedWidget(question);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    mountSharedChrome();
    setupRevealAnimations();
    setupPricingToggle();
    mountPreview("[data-hero-preview]", "hero");
    mountPreview("[data-demo-widget]", "demo");
    wirePromptChips();
    document.body.classList.add("page-ready");
  });
})();
