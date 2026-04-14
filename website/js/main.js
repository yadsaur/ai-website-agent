(function () {
  const siteConfig = {
    brand: "SiteCloser",
    tagline: "The AI sales rep trained on your website",
    appUrl: "https://ai-website-agent-aikinley.onrender.com",
    dashboardUrl: "/dashboard",
    demoSiteId: "d94c64af-65d2-410f-a6d4-c9f05f9919c0",
  };

  const navLinks = [
    { href: "/", label: "Home", page: "home" },
    { href: "/features", label: "Features", page: "features" },
    { href: "/pricing", label: "Pricing", page: "pricing" },
    { href: "/how-it-works", label: "How It Works", page: "how-it-works" },
    { href: "/demo", label: "Demo", page: "demo" },
    { href: "/blog", label: "Blog", page: "blog" },
  ];

  const footerColumns = [
    {
      title: "Product",
      links: [
        { href: "/features", label: "Features" },
        { href: "/pricing", label: "Pricing" },
        { href: "/how-it-works", label: "How It Works" },
        { href: "/demo", label: "Live Demo" },
      ],
    },
    {
      title: "Resources",
      links: [
        { href: "/blog", label: "Blog" },
        { href: "/dashboard", label: "Dashboard" },
        { href: "/demo", label: "Try the bot" },
        { href: "mailto:hello@sitecloser.ai", label: "Contact" },
      ],
    },
    {
      title: "Use Cases",
      links: [
        { href: "/features#sales", label: "Sales teams" },
        { href: "/features#support", label: "Support deflection" },
        { href: "/features#pricing-intent", label: "Pricing pages" },
        { href: "/features#ui-awareness", label: "UI-aware answers" },
      ],
    },
    {
      title: "Company",
      links: [
        { href: "/blog/ai-salesman", label: "Why SiteCloser" },
        { href: "/blog/visitor-questions", label: "Buying questions" },
        { href: "/blog/ui-layout-ai", label: "Engineering" },
        { href: "https://ai-website-agent-aikinley.onrender.com", label: "App status" },
      ],
    },
  ];

  const pageName = document.body.dataset.page || "";
  const year = new Date().getFullYear();

  function buildNav() {
    return `
      <div class="container">
        <div class="nav-inner">
          <a class="brand" href="/">
            <span class="brand-mark"></span>
            <span class="brand-text">
              <span>${siteConfig.brand}</span>
              <small>AI sales conversion</small>
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
            <a class="button button-primary" href="${siteConfig.dashboardUrl}">Start Free →</a>
            <button class="nav-mobile-toggle" type="button" aria-label="Open menu">☰</button>
          </div>
        </div>
        <div class="nav-panel" aria-label="Mobile navigation">
          ${navLinks
            .map(
              (link) =>
                `<a href="${link.href}" class="${pageName === link.page ? "active" : ""}">${link.label}</a>`
            )
            .join("")}
          <a href="${siteConfig.dashboardUrl}" class="button button-primary">Start Free →</a>
        </div>
      </div>
    `;
  }

  function buildFooter() {
    return `
      <div class="container footer-grid">
        <div>
          <a class="footer-logo" href="/">
            <span class="brand-mark"></span>
            <span>${siteConfig.brand}</span>
          </a>
          <p>${siteConfig.tagline}. Train it on your content, deploy one script tag, and let it close more visitors while your team sleeps.</p>
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
      <div class="container" style="margin-top: 26px;">
        <p style="margin: 0; color: #8d92a9;">© ${year} ${siteConfig.brand}. Built for teams who want their website to sell harder.</p>
      </div>
    `;
  }

  function mountSharedChrome() {
    const navHost = document.querySelector("[data-nav]");
    const footerHost = document.querySelector("[data-footer]");
    if (navHost) {
      navHost.innerHTML = buildNav();
      const nav = navHost.querySelector(".site-nav");
      const panel = navHost.querySelector(".nav-panel");
      const toggle = navHost.querySelector(".nav-mobile-toggle");
      if (toggle && panel) {
        toggle.addEventListener("click", () => {
          panel.classList.toggle("open");
        });
      }
      const handleScroll = () => {
        if (!nav) {
          return;
        }
        nav.classList.toggle("scrolled", window.scrollY > 8);
      };
      handleScroll();
      window.addEventListener("scroll", handleScroll, { passive: true });
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
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("revealed");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.16, rootMargin: "0px 0px -30px 0px" }
    );

    nodes.forEach((node, index) => {
      node.style.transitionDelay = `${Math.min(index * 60, 360)}ms`;
      observer.observe(node);
    });
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

  function loadDemoWidget() {
    const mount = document.querySelector("[data-demo-widget]");
    if (!mount || !siteConfig.demoSiteId) {
      return;
    }
    const script = document.createElement("script");
    script.src = `${siteConfig.appUrl}/widget/agent.js`;
    script.dataset.siteId = siteConfig.demoSiteId;
    mount.appendChild(script);
  }

  function wirePromptChips() {
    document.querySelectorAll("[data-demo-ask]").forEach((chip) => {
      chip.addEventListener("click", () => {
        const input = document.querySelector("#aiwa-input");
        const send = document.querySelector("#aiwa-send");
        if (!input || !send) {
          return;
        }
        input.value = chip.dataset.demoAsk || "";
        input.dispatchEvent(new Event("input", { bubbles: true }));
        send.click();
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    mountSharedChrome();
    setupRevealAnimations();
    setupPricingToggle();
    loadDemoWidget();
    wirePromptChips();
  });
})();
