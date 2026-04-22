(function () {
  var currentScript = document.currentScript;
  if (!currentScript) {
    var scripts = document.getElementsByTagName("script");
    currentScript = scripts[scripts.length - 1];
  }
  if (!currentScript) return;

  var siteId = currentScript.getAttribute("data-site-id");
  if (!siteId) return;

  var baseUrl = new URL(currentScript.src, window.location.href).origin;
  var FALLBACK_MESSAGE = "I don't have that specific information here, but the team behind this site would be able to give you a definitive answer. Is there anything else I can help you with?";
  var TRIAL_ENDED_MESSAGE = "This chatbot is inactive. Please upgrade.";
  var state = {
    open: false,
    siteName: "this site",
    siteTheme: null,
    sessionId: "aiwa-" + Math.random().toString(36).slice(2) + Date.now().toString(36),
    activeEventSource: null,
    suggestedQuestions: null,
    suggestedQuestionsRequested: false,
    starterDismissed: false
  };

  var markedLoader = null;

  var root = document.createElement("div");
  root.id = "aiwa-widget";
  root.innerHTML = [
    '<button id="aiwa-toggle" type="button" aria-label="Open website chat"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 7.5C6 6.12 7.12 5 8.5 5h7A2.5 2.5 0 0 1 18 7.5v5A2.5 2.5 0 0 1 15.5 15H11l-3.75 3v-3H8.5A2.5 2.5 0 0 1 6 12.5v-5Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></button>',
    '<div id="aiwa-panel" aria-hidden="true">',
    '  <div id="aiwa-header">',
    '    <div id="aiwa-title">Chat with this site</div>',
    '    <button id="aiwa-close" type="button" aria-label="Close chat">&times;</button>',
    "  </div>",
    '  <div id="aiwa-messages"></div>',
    '  <div id="aiwa-input-row">',
    '    <input id="aiwa-input" type="text" placeholder="Ask a question..." />',
    '    <button id="aiwa-send" type="button">Send</button>',
    "  </div>",
    '  <div id="aiwa-footer">Powered by 5minBot</div>',
    "</div>"
  ].join("");

  var style = document.createElement("style");
  style.textContent = [
    "#aiwa-widget { all: initial; font-family: system-ui, -apple-system, sans-serif; --aiwa-accent: #7c3aed; --aiwa-accent-strong: #5b21b6; --aiwa-bg: #0a0f1d; --aiwa-panel-top: #12182a; --aiwa-panel-bottom: #090d18; --aiwa-text: #f8fafc; --aiwa-muted: #94a3b8; --aiwa-border: rgba(255, 255, 255, 0.1); }",
    "#aiwa-widget, #aiwa-widget * { box-sizing: border-box; font-family: system-ui, -apple-system, sans-serif; }",
    "#aiwa-widget { position: fixed; right: 20px; bottom: 20px; z-index: 9999; color: var(--aiwa-text); }",
    "#aiwa-widget button, #aiwa-widget input { border: none; outline: none; font: inherit; }",
    "#aiwa-toggle { width: 58px; height: 58px; border-radius: 999px; background: linear-gradient(135deg, var(--aiwa-accent), var(--aiwa-accent-strong)); color: #ffffff; box-shadow: 0 16px 38px color-mix(in srgb, var(--aiwa-accent-strong) 42%, transparent); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; }",
    "#aiwa-toggle svg { width: 24px; height: 24px; }",
    "#aiwa-toggle:hover { transform: translateY(-2px); }",
    "#aiwa-panel { position: absolute; right: 0; bottom: 74px; width: 380px; height: 560px; background: linear-gradient(180deg, var(--aiwa-panel-top), var(--aiwa-panel-bottom)); border: 1px solid var(--aiwa-border); border-radius: 22px; box-shadow: 0 28px 80px rgba(2, 6, 23, 0.52); display: none; overflow: hidden; transform: translateY(12px); opacity: 0; }",
    "#aiwa-panel.aiwa-open { display: flex; flex-direction: column; animation: aiwa-slide-up 0.2s ease forwards; }",
    "#aiwa-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 18px; background: linear-gradient(135deg, var(--aiwa-accent), var(--aiwa-accent-strong)); color: #ffffff; border-bottom: 1px solid var(--aiwa-border); }",
    "#aiwa-title { font-size: 14px; font-weight: 700; letter-spacing: 0.01em; }",
    "#aiwa-close { background: transparent; color: #ffffff; cursor: pointer; font-size: 22px; line-height: 1; }",
    "#aiwa-messages { flex: 1; overflow-y: auto; padding: 16px; background: radial-gradient(circle at top left, color-mix(in srgb, var(--aiwa-accent) 16%, transparent), transparent 28%), linear-gradient(180deg, var(--aiwa-bg), var(--aiwa-panel-bottom)); }",
    "#aiwa-input-row { display: flex; gap: 10px; padding: 14px; border-top: 1px solid var(--aiwa-border); background: color-mix(in srgb, var(--aiwa-panel-bottom) 88%, black 12%); }",
    "#aiwa-input { flex: 1; min-width: 0; border: 1px solid var(--aiwa-border); border-radius: 999px; padding: 12px 14px; background: rgba(255, 255, 255, 0.05); color: var(--aiwa-text); }",
    "#aiwa-input::placeholder { color: var(--aiwa-muted); }",
    "#aiwa-send { background: linear-gradient(135deg, var(--aiwa-accent), var(--aiwa-accent-strong)); color: #ffffff; border-radius: 999px; padding: 10px 16px; cursor: pointer; font-weight: 700; }",
    "#aiwa-footer { padding: 10px 14px; border-top: 1px solid var(--aiwa-border); color: var(--aiwa-muted); font-size: 11px; background: color-mix(in srgb, var(--aiwa-panel-bottom) 88%, black 12%); }",
    "#aiwa-widget .aiwa-row { display: flex; margin-bottom: 10px; }",
    "#aiwa-widget .aiwa-row.user { justify-content: flex-end; }",
    "#aiwa-widget .aiwa-row.assistant { justify-content: flex-start; flex-direction: column; align-items: flex-start; gap: 8px; }",
    "#aiwa-widget .aiwa-bubble { max-width: 85%; padding: 12px 14px; border-radius: 18px; font-size: 14px; line-height: 1.55; white-space: pre-wrap; word-break: break-word; }",
    "#aiwa-widget .aiwa-row.user .aiwa-bubble { background: linear-gradient(135deg, var(--aiwa-accent), var(--aiwa-accent-strong)); color: #ffffff; border-top-right-radius: 8px; box-shadow: 0 12px 30px color-mix(in srgb, var(--aiwa-accent-strong) 24%, transparent); }",
    "#aiwa-widget .aiwa-row.assistant .aiwa-bubble { background: rgba(255, 255, 255, 0.08); color: var(--aiwa-text); border: 1px solid var(--aiwa-border); border-top-left-radius: 8px; box-shadow: 0 10px 24px rgba(15, 23, 42, 0.18); }",
    "#aiwa-widget .aiwa-assistant-bubble, #aiwa-widget .aiwa-assistant-bubble * { color: inherit; }",
    "#aiwa-widget .aiwa-assistant-bubble p { margin: 0 0 8px 0; }",
    "#aiwa-widget .aiwa-assistant-bubble p:last-child { margin-bottom: 0; }",
    "#aiwa-widget .aiwa-assistant-bubble strong { font-weight: 600; }",
    "#aiwa-widget .aiwa-assistant-bubble em { font-style: italic; }",
    "#aiwa-widget .aiwa-assistant-bubble ol, #aiwa-widget .aiwa-assistant-bubble ul { margin: 6px 0; padding-left: 20px; }",
    "#aiwa-widget .aiwa-assistant-bubble li { margin-bottom: 4px; line-height: 1.5; }",
    "#aiwa-widget .aiwa-assistant-bubble h1, #aiwa-widget .aiwa-assistant-bubble h2, #aiwa-widget .aiwa-assistant-bubble h3 { font-size: 14px; font-weight: 600; margin: 8px 0 4px 0; }",
    "#aiwa-widget .aiwa-sources { margin-top: 8px; display: flex; flex-direction: column; gap: 8px; }",
    "#aiwa-widget .aiwa-sources-label { font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--aiwa-muted); }",
    "#aiwa-widget .aiwa-source-list { display: flex; flex-wrap: wrap; gap: 8px; }",
    "#aiwa-widget .aiwa-source-link { display: inline-flex; align-items: center; max-width: 100%; padding: 7px 11px; border-radius: 999px; background: color-mix(in srgb, var(--aiwa-accent) 16%, transparent); color: var(--aiwa-text); text-decoration: none; font-size: 12px; font-weight: 600; border: 1px solid color-mix(in srgb, var(--aiwa-accent) 28%, transparent); }",
    "#aiwa-widget .aiwa-source-link:hover { background: color-mix(in srgb, var(--aiwa-accent) 24%, transparent); }",
    "#aiwa-widget .aiwa-chip-stack { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; margin-bottom: 12px; }",
    "#aiwa-widget .aiwa-chip-group { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }",
    "#aiwa-widget .aiwa-chip { display: inline-flex; align-items: center; justify-content: flex-start; width: fit-content; max-width: 90%; padding: 8px 16px; border-radius: 20px; border: 1px solid var(--aiwa-border); background: rgba(255, 255, 255, 0.04); color: var(--aiwa-text); cursor: pointer; font-size: 13px; line-height: 1.35; text-align: left; }",
    "#aiwa-widget .aiwa-chip:hover { background: color-mix(in srgb, var(--aiwa-accent) 12%, transparent); border-color: color-mix(in srgb, var(--aiwa-accent) 32%, transparent); }",
    "#aiwa-widget .aiwa-followup-chip { font-size: 12px; padding: 6px 14px; }",
    "#aiwa-widget .aiwa-typing { opacity: 0.78; font-style: italic; color: color-mix(in srgb, var(--aiwa-text) 78%, var(--aiwa-muted)); }",
    "@keyframes aiwa-slide-up { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }",
    "@media (max-width: 479px) { #aiwa-panel { width: 92vw; height: min(78vh, 560px); right: 0; } }"
  ].join("\n");

  document.head.appendChild(style);
  document.body.appendChild(root);

  function loadMarked() {
    if (window.marked && typeof window.marked.parse === "function") {
      return Promise.resolve(window.marked);
    }
    if (markedLoader) return markedLoader;
    markedLoader = new Promise(function (resolve, reject) {
      var existing = document.querySelector('script[data-aiwa-marked="true"]');
      if (existing) {
        existing.addEventListener("load", function () { resolve(window.marked); }, { once: true });
        existing.addEventListener("error", reject, { once: true });
        return;
      }
      var markedScript = document.createElement("script");
      markedScript.src = "https://cdn.jsdelivr.net/npm/marked/marked.min.js";
      markedScript.async = true;
      markedScript.setAttribute("data-aiwa-marked", "true");
      markedScript.onload = function () { resolve(window.marked); };
      markedScript.onerror = reject;
      document.head.appendChild(markedScript);
    });
    return markedLoader;
  }

  function renderAssistantContent(bubble, text) {
    var value = text || "";
    if (window.marked && typeof window.marked.parse === "function") {
      bubble.innerHTML = window.marked.parse(value);
    } else {
      bubble.textContent = value;
    }
  }

  var toggle = document.getElementById("aiwa-toggle");
  var panel = document.getElementById("aiwa-panel");
  var closeBtn = document.getElementById("aiwa-close");
  var title = document.getElementById("aiwa-title");
  var messages = document.getElementById("aiwa-messages");
  var input = document.getElementById("aiwa-input");
  var send = document.getElementById("aiwa-send");

  function setOpen(nextOpen) {
    state.open = nextOpen;
    if (nextOpen) {
      panel.style.display = "flex";
      panel.classList.add("aiwa-open");
      panel.setAttribute("aria-hidden", "false");
      window.setTimeout(function () { input.focus(); }, 60);
      ensureStarterSuggestions();
    } else {
      panel.classList.remove("aiwa-open");
      panel.setAttribute("aria-hidden", "true");
      panel.style.display = "none";
    }
  }

  function scrollToBottom() {
    messages.scrollTop = messages.scrollHeight;
  }

  function hasConversationMessages() {
    return !!messages.querySelector(".aiwa-row");
  }

  function addMessage(role, text) {
    var row = document.createElement("div");
    row.className = "aiwa-row " + role;
    var bubble = document.createElement("div");
    bubble.className = "aiwa-bubble";
    if (role === "assistant") {
      bubble.className += " aiwa-assistant-bubble";
      renderAssistantContent(bubble, text);
    } else {
      bubble.textContent = text;
    }
    row.appendChild(bubble);
    messages.appendChild(row);
    scrollToBottom();
    return { row: row, bubble: bubble };
  }

  function addTyping() {
    removeTyping();
    var row = document.createElement("div");
    row.className = "aiwa-row assistant";
    row.id = "aiwa-typing";
    var bubble = document.createElement("div");
    bubble.className = "aiwa-bubble aiwa-typing";
    bubble.textContent = "Thinking...";
    row.appendChild(bubble);
    messages.appendChild(row);
    scrollToBottom();
  }

  function removeTyping() {
    var typing = document.getElementById("aiwa-typing");
    if (typing) typing.remove();
  }

  function removeStarterSuggestions() {
    var starters = messages.querySelector(".aiwa-starter-stack");
    if (starters) starters.remove();
    state.starterDismissed = true;
  }

  function clearFollowupGroups() {
    messages.querySelectorAll(".aiwa-followup-stack").forEach(function (node) { node.remove(); });
  }

  function closeExistingEventSource() {
    if (state.activeEventSource) {
      state.activeEventSource.close();
      state.activeEventSource = null;
    }
  }

  function normalizeSources(payload) {
    var sources = [];
    if (payload && payload.sources && payload.sources.length) {
      sources = payload.sources.slice(0, 1);
    } else if (payload && payload.urls && payload.urls.length) {
      var displayUrls = payload.urls.slice(0, 1);
      sources = displayUrls.map(function (url, index) {
        return { url: url, title: "Source " + (index + 1), section: "" };
      });
    }
    return sources.slice(0, 1);
  }

  function sourceLabel(source, index) {
    if (source.title && source.section) return source.title + " - " + source.section;
    if (source.title) return source.title;
    return "Source " + (index + 1);
  }

  function appendSources(container, payload) {
    var sources = normalizeSources(payload);
    if (!sources.length) return;
    var wrap = document.createElement("div");
    wrap.className = "aiwa-sources";
    var label = document.createElement("div");
    label.className = "aiwa-sources-label";
    label.textContent = "Sources";
    wrap.appendChild(label);
    var list = document.createElement("div");
    list.className = "aiwa-source-list";
    sources.forEach(function (source, index) {
      var link = document.createElement("a");
      link.className = "aiwa-source-link";
      link.href = source.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = sourceLabel(source, index);
      list.appendChild(link);
    });
    wrap.appendChild(list);
    container.appendChild(wrap);
    scrollToBottom();
  }

  function isFallbackAnswer(text) {
    return (text || "").trim() === FALLBACK_MESSAGE;
  }

  function applyTheme(theme) {
    if (!theme) return;
    state.siteTheme = theme;
    root.style.setProperty("--aiwa-accent", theme.accent || "#7c3aed");
    root.style.setProperty("--aiwa-accent-strong", theme.accent_strong || "#5b21b6");
    root.style.setProperty("--aiwa-bg", theme.background || "#0a0f1d");
    root.style.setProperty("--aiwa-panel-top", theme.panel_top || "#12182a");
    root.style.setProperty("--aiwa-panel-bottom", theme.panel_bottom || "#090d18");
    root.style.setProperty("--aiwa-text", theme.text || "#f8fafc");
    root.style.setProperty("--aiwa-muted", theme.muted || "#94a3b8");
    root.style.setProperty("--aiwa-border", "color-mix(in srgb, " + (theme.accent || "#7c3aed") + " 22%, rgba(255,255,255,0.12))");
  }

  async function loadSiteName() {
    try {
      var response = await fetch(baseUrl + "/api/public/sites/" + encodeURIComponent(siteId) + "/status");
      if (!response.ok) return;
      var data = await response.json();
      state.siteName = data.name || "this site";
      title.textContent = "Chat with " + state.siteName;
    } catch (err) {
    }
  }

  async function loadSiteTheme() {
    try {
      var response = await fetch(baseUrl + "/api/public/sites/" + encodeURIComponent(siteId) + "/theme");
      if (!response.ok) return;
      var data = await response.json();
      if (data && data.name) {
        state.siteName = data.name;
        title.textContent = "Chat with " + state.siteName;
      }
      applyTheme(data && data.theme ? data.theme : null);
    } catch (err) {
    }
  }

  function renderStarterSuggestions(questions) {
    if (!questions || !questions.length || state.starterDismissed || hasConversationMessages()) return;
    if (messages.querySelector(".aiwa-starter-stack")) return;
    var wrap = document.createElement("div");
    wrap.className = "aiwa-chip-stack aiwa-starter-stack";
    questions.slice(0, 3).forEach(function (question) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "aiwa-chip";
      chip.textContent = "\u2192 " + question;
      chip.addEventListener("click", function () {
        removeStarterSuggestions();
        input.value = question;
        sendMessage(question, { preserveFollowups: true, preserveStarter: true });
      });
      wrap.appendChild(chip);
    });
    messages.appendChild(wrap);
    scrollToBottom();
  }

  async function prefetchStarterSuggestions() {
    if (state.suggestedQuestionsRequested || Array.isArray(state.suggestedQuestions)) return;
    state.suggestedQuestionsRequested = true;
    try {
      var response = await fetch(baseUrl + "/api/sites/" + encodeURIComponent(siteId) + "/suggested-questions");
      if (!response.ok) return;
      var data = await response.json();
      if (!data.questions || !data.questions.length) return;
      state.suggestedQuestions = data.questions.slice(0, 3);
      renderStarterSuggestions(state.suggestedQuestions);
    } catch (err) {
    }
  }

  async function ensureStarterSuggestions() {
    if (state.starterDismissed || hasConversationMessages()) return;
    prefetchStarterSuggestions();
    if (Array.isArray(state.suggestedQuestions)) {
      renderStarterSuggestions(state.suggestedQuestions);
    }
  }

  function appendFollowupSuggestions(container, questions) {
    if (!questions || !questions.length) return;
    var wrap = document.createElement("div");
    wrap.className = "aiwa-chip-group aiwa-followup-stack";
    questions.slice(0, 2).forEach(function (question) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "aiwa-chip aiwa-followup-chip";
      chip.textContent = "\u2192 " + question;
      chip.addEventListener("click", function () {
        wrap.remove();
        sendMessage(question, { preserveFollowups: true, preserveStarter: true });
      });
      wrap.appendChild(chip);
    });
    container.appendChild(wrap);
    scrollToBottom();
  }

  async function fetchFollowupSuggestions(lastQuestion, lastAnswer, container) {
    try {
      var controller = new AbortController();
      var timeoutId = window.setTimeout(function () { controller.abort(); }, 3000);
      var response = await fetch(baseUrl + "/api/sites/" + encodeURIComponent(siteId) + "/followup-questions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          last_question: lastQuestion,
          last_answer: lastAnswer,
          session_id: state.sessionId
        }),
        signal: controller.signal
      });
      window.clearTimeout(timeoutId);
      if (!response.ok) return;
      var data = await response.json();
      if (!data.questions || !data.questions.length) return;
      appendFollowupSuggestions(container, data.questions);
    } catch (err) {
    }
  }

  function sendMessage(forcedQuestion, options) {
    options = options || {};
    var value = (typeof forcedQuestion === "string" ? forcedQuestion : input.value).trim();
    if (!value) return;

    closeExistingEventSource();
    if (!options.preserveStarter) removeStarterSuggestions();
    if (!options.preserveFollowups) clearFollowupGroups();

    addMessage("user", value);
    input.value = "";
    addTyping();

    var assistantMessage = addMessage("assistant", "");
    var assistantBubble = assistantMessage.bubble;
    var answerText = "";
    var hadNoAnswer = false;
    var url = baseUrl + "/api/chat?site_id=" + encodeURIComponent(siteId) + "&q=" + encodeURIComponent(value) + "&session_id=" + encodeURIComponent(state.sessionId);
    var eventSource = new EventSource(url);
    state.activeEventSource = eventSource;
    loadMarked().then(function () {
      renderAssistantContent(assistantBubble, answerText);
    }).catch(function () {});

    eventSource.onmessage = function (event) {
      try {
        var data = JSON.parse(event.data);
        if (data.type === "token") {
          removeTyping();
          answerText += data.content;
          renderAssistantContent(assistantBubble, answerText);
          scrollToBottom();
        } else if (data.type === "sources") {
          appendSources(assistantMessage.row, data);
        } else if (data.type === "no_answer") {
          removeTyping();
          hadNoAnswer = true;
          answerText = FALLBACK_MESSAGE;
          renderAssistantContent(assistantBubble, FALLBACK_MESSAGE);
          scrollToBottom();
        } else if (data.type === "trial_ended") {
          removeTyping();
          hadNoAnswer = true;
          answerText = data.message || TRIAL_ENDED_MESSAGE;
          renderAssistantContent(assistantBubble, answerText);
          scrollToBottom();
        } else if (data.type === "done") {
          removeTyping();
          eventSource.close();
          state.activeEventSource = null;
          if (!hadNoAnswer && !isFallbackAnswer(answerText)) {
            window.setTimeout(function () {
              fetchFollowupSuggestions(value, answerText, assistantMessage.row);
            }, 0);
          }
        }
      } catch (err) {
        removeTyping();
        renderAssistantContent(assistantBubble, "Something went wrong. Please try again.");
        eventSource.close();
        state.activeEventSource = null;
      }
    };

    eventSource.onerror = function () {
      removeTyping();
      if (!assistantBubble.textContent && !assistantBubble.innerHTML) {
        renderAssistantContent(assistantBubble, "Something went wrong. Please try again.");
      }
      eventSource.close();
      state.activeEventSource = null;
    };
  }

  toggle.addEventListener("click", function () { setOpen(!state.open); });
  closeBtn.addEventListener("click", function () { setOpen(false); });
  send.addEventListener("click", function () { sendMessage(); });
  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      sendMessage();
    }
  });

  loadSiteName();
  loadSiteTheme();
  prefetchStarterSuggestions();
  loadMarked().catch(function () {});
})();
