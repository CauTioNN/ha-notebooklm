/*
 * NotebookLM Chat Card — a self-contained custom Lovelace card.
 *
 * Ships with the NotebookLM integration and is registered automatically
 * (via `frontend.add_extra_js_url`), so it shows up under "Add card →
 * Community cards" with no manual resource setup and no card-mod.
 *
 * Everything lives in a Shadow DOM with explicit colors, so the card looks
 * the same on any theme (light or dark) — the answer text can never inherit
 * a theme color that blends into the background.
 *
 * It drives the integration's own entities:
 *   - select.notebooklm_active_notebook   (header "contact")
 *   - sensor.notebooklm_authentication_status (online / signed out)
 *   - sensor.notebooklm_last_answer        (question + answer attributes)
 *   - text.notebooklm_question + button.notebooklm_ask (send path)
 * Sending sets the text box then presses the Ask button, so the existing
 * server-side behaviour (brevity instruction, notification) is reused as-is.
 */

const DEFAULTS = {
  active_notebook_entity: "select.notebooklm_active_notebook",
  status_entity: "sensor.notebooklm_authentication_status",
  answer_entity: "sensor.notebooklm_last_answer",
  question_entity: "text.notebooklm_question",
  ask_button_entity: "button.notebooklm_ask",
  avatar: "/notebooklm_static/icon.png",
  title: "NotebookLM Chat",
  max_height: 460,
};

// Both cards localize their text from `hass.language` (any non-Hebrew → en).
const I18N = {
  en: {
    ask_placeholder: "Ask the active notebook…",
    send: "Send",
    default_notebook: "Default notebook",
    active_notebook: "Active notebook",
    online: "online",
    offline: "signed out",
    no_notebooks: "No notebooks",
    convo_hint: "👋 Ask the active notebook anything — type below and press send.",
    expand: "Click to expand / collapse",
    waiting: "Waiting for NotebookLM…",
    notebooks_word: "notebooks",
    no_answer: "No answer yet.",
    generate: "Generate",
    act_audio: "Podcast",
    act_quiz: "Quiz",
    act_report: "Report",
    act_mind: "Mind map",
    action_sent: "Action sent — running in the background.",
  },
  he: {
    ask_placeholder: "שאל את המחברת הפעילה…",
    send: "שלח",
    default_notebook: "מחברת ברירת מחדל",
    active_notebook: "מחברת פעילה",
    online: "מחובר",
    offline: "מנותק",
    no_notebooks: "אין מחברות",
    convo_hint: "👋 שאל את המחברת הפעילה כל דבר — כתוב למטה ולחץ שליחה.",
    expand: "לחץ להרחבה / כיווץ",
    waiting: "ממתין ל-NotebookLM…",
    notebooks_word: "מחברות",
    no_answer: "עדיין אין תשובה.",
    generate: "פעולות יצירה",
    act_audio: "פודקאסט",
    act_quiz: "מבחן",
    act_report: "דוח",
    act_mind: "מפת חשיבה",
    action_sent: "הפעולה נשלחה — רצה ברקע.",
  },
};

function t(hass, key) {
  const lang = (hass && hass.language) || "en";
  const table = I18N[lang] || I18N.en;
  return table[key] != null ? table[key] : I18N.en[key];
}

// Strip the markdown markers NotebookLM sprinkles into answers (**bold**,
// *italic*, `code`, # headings, > quotes, [text](url), bullet stars) so the
// bubble shows clean plain text — no stray asterisks or hashes.
function stripMarkdown(text) {
  if (!text) return text;
  return text
    .replace(/```([\s\S]*?)```/g, "$1")          // fenced code blocks
    .replace(/`([^`]+)`/g, "$1")                  // inline code
    .replace(/\*\*([^*]+)\*\*/g, "$1")            // **bold**
    .replace(/__([^_]+)__/g, "$1")                // __bold__
    .replace(/\*([^*]+)\*/g, "$1")                // *italic*
    .replace(/(^|\s)_([^_]+)_(?=\s|$)/g, "$1$2")  // _italic_ (not entity_ids)
    .replace(/~~([^~]+)~~/g, "$1")                // ~~strikethrough~~
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")      // [text](url) -> text
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")           // # headings
    .replace(/^\s{0,3}>\s?/gm, "")                // > blockquotes
    .replace(/^\s*[-*+]\s+/gm, "• ")              // bullet markers -> •
    .replace(/\*+/g, "")                          // any leftover asterisks
    .trim();
}

class NotebookLMChatCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._built = false;
    this._sending = false;
  }

  setConfig(config) {
    this._config = { ...DEFAULTS, ...(config || {}) };
    if (this._built) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    this._render();
  }

  getCardSize() {
    return 6;
  }

  static getStubConfig() {
    return {};
  }

  // --------------------------------------------------------------- skeleton
  _build() {
    const max = this._config?.max_height ?? DEFAULTS.max_height;
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        .wrap {
          border-radius: 18px; overflow: hidden;
          box-shadow: 0 2px 8px rgba(0,0,0,.12);
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
        }
        .header {
          display: flex; align-items: center; gap: 8px;
          background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
          color: #fff; padding: 10px 14px;
        }
        .header img {
          width: 24px; height: 24px; border-radius: 50%;
          background: rgba(255,255,255,.18); padding: 4px; box-sizing: border-box;
          object-fit: cover;
        }
        .header .meta { line-height: 1.2; }
        .header .name { font-size: 1.05rem; font-weight: 600; }
        .header .sub {
          font-size: .8rem; opacity: .9; margin-top: 2px;
          display: flex; align-items: center; gap: 6px;
        }
        .header select {
          font: inherit; font-size: .8rem; color: #fff;
          background: rgba(255,255,255,.18);
          border: 1px solid rgba(255,255,255,.35);
          border-radius: 8px; padding: 2px 6px; max-width: 220px;
          cursor: pointer; outline: none;
        }
        .header select option { color: #111; }
        .convo {
          background: #f3f4f6; padding: 8px 12px;
          min-height: 90px; max-height: ${max}px; overflow-y: auto;
        }
        .bubble {
          padding: 10px 14px; margin: 8px 0; width: fit-content;
          max-width: 85%; box-shadow: 0 1px 1px rgba(0,0,0,.12);
          white-space: pre-wrap; word-wrap: break-word; font-size: .95rem;
        }
        .q {
          background: #4f46e5; color: #fff; margin-left: auto;
          border-radius: 18px 18px 4px 18px; max-width: 78%;
        }
        .a {
          background: #fff; color: #111; margin-right: auto;
          border-radius: 18px 18px 18px 4px;
        }
        .a.collapsible { cursor: pointer; }
        .a.collapsed {
          display: -webkit-box; -webkit-line-clamp: 3;
          -webkit-box-orient: vertical; overflow: hidden;
        }
        .placeholder { color: #555; padding: 14px 4px; font-size: .9rem; }
        .spinner {
          width: 20px; height: 20px; margin: 12px 6px;
          border: 2px solid #cdd0d8; border-top-color: #4f46e5;
          border-radius: 50%; animation: nlmspin .8s linear infinite;
        }
        @keyframes nlmspin { to { transform: rotate(360deg); } }
        .composer {
          display: flex; align-items: center; gap: 8px;
          background: #fff; padding: 8px 10px;
          border-top: 1px solid #e5e7eb;
        }
        .composer input {
          flex: 1; border: 1px solid #d1d5db; border-radius: 20px;
          padding: 9px 14px; font-size: .95rem; outline: none; color: #111;
          background: #fff;
        }
        .composer input:focus { border-color: #4f46e5; }
        .composer button {
          border: none; background: #4f46e5; color: #fff;
          width: 38px; height: 38px; border-radius: 50%; cursor: pointer;
          font-size: 1.1rem; display: flex; align-items: center;
          justify-content: center; flex: 0 0 auto;
        }
        .composer button:disabled { opacity: .5; cursor: default; }
      </style>
      <div class="wrap">
        <div class="header">
          <img id="avatar" alt="">
          <div class="meta">
            <div class="name" id="title"></div>
            <div class="sub">
              <select id="nb" title="${t(this._hass, "default_notebook")}"></select>
              <span id="status"></span>
            </div>
          </div>
        </div>
        <div class="convo" id="convo"></div>
        <div class="composer">
          <input id="input" type="text" placeholder="${t(this._hass, "ask_placeholder")}">
          <button id="send" title="${t(this._hass, "send")}">➤</button>
        </div>
      </div>
    `;

    this._convo = this.shadowRoot.getElementById("convo");
    this._input = this.shadowRoot.getElementById("input");
    this._sendBtn = this.shadowRoot.getElementById("send");
    this._nbSel = this.shadowRoot.getElementById("nb");
    this._status = this.shadowRoot.getElementById("status");

    this._nbSel.addEventListener("change", () => this._selectNotebook(this._nbSel.value));
    this._sendBtn.addEventListener("click", () => this._send());
    this._input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        this._send();
      }
    });

    this._built = true;
  }

  // ----------------------------------------------------------------- render
  _render() {
    if (!this._built || !this._hass) return;
    const cfg = this._config;
    const states = this._hass.states;

    this.shadowRoot.getElementById("avatar").src = cfg.avatar;
    this.shadowRoot.getElementById("title").textContent = cfg.title;

    const nb = states[cfg.active_notebook_entity];
    const status = states[cfg.status_entity];
    const online = status && status.state === "ok";

    // Populate the default-notebook dropdown from the select entity's options.
    // Only rebuild when the option list actually changes, so an open dropdown
    // isn't disrupted on every state tick.
    const options = (nb && nb.attributes && Array.isArray(nb.attributes.options))
      ? nb.attributes.options
      : [];
    const key = JSON.stringify(options);
    if (key !== this._nbOptionsKey) {
      this._nbOptionsKey = key;
      this._nbSel.innerHTML = "";
      if (!options.length) {
        const o = document.createElement("option");
        o.value = "";
        o.textContent = t(this._hass, "no_notebooks");
        this._nbSel.appendChild(o);
      }
      for (const opt of options) {
        const o = document.createElement("option");
        o.value = opt;
        o.textContent = opt;
        this._nbSel.appendChild(o);
      }
    }
    if (nb && nb.state && options.includes(nb.state)) {
      this._nbSel.value = nb.state;
    }
    this._status.textContent = `· ${online ? t(this._hass, "online") : t(this._hass, "offline")}`;

    const ans = states[cfg.answer_entity];
    const question = ans && ans.attributes ? ans.attributes.question : null;
    const answer = ans && ans.attributes ? ans.attributes.answer : null;

    // A pending send shows the question + a spinner until a new answer lands.
    if (
      this._waiting &&
      ((answer && answer !== this._waitAnswer) ||
        (question && question === this._pendingQuestion && answer))
    ) {
      this._waiting = false;
      clearTimeout(this._waitTimer);
    }
    if (this._waiting) {
      const key = "wait:" + (this._pendingQuestion || "");
      if (key !== this._convoKey) {
        this._convoKey = key;
        this._convo.innerHTML = "";
        if (this._pendingQuestion) {
          const q = document.createElement("div");
          q.className = "bubble q";
          q.textContent = this._pendingQuestion;
          this._convo.appendChild(q);
        }
        const s = document.createElement("div");
        s.className = "spinner";
        s.title = t(this._hass, "waiting");
        this._convo.appendChild(s);
        this._convo.scrollTop = this._convo.scrollHeight;
      }
      return;
    }

    // Only rebuild the conversation when the Q/A actually changes, so the
    // user's expand/collapse toggle isn't reset on every state tick. A new
    // answer rebuilds and starts collapsed.
    const convoKey = JSON.stringify([question || "", answer || ""]);
    if (convoKey !== this._convoKey) {
      this._convoKey = convoKey;
      this._convo.innerHTML = "";
      if (answer) {
        if (question) {
          const q = document.createElement("div");
          q.className = "bubble q";
          q.textContent = question;
          this._convo.appendChild(q);
        }
        const a = document.createElement("div");
        a.className = "bubble a collapsible collapsed";
        a.title = t(this._hass, "expand");
        a.textContent = stripMarkdown(answer);
        // click the answer to expand the full text / collapse it back
        a.addEventListener("click", () => a.classList.toggle("collapsed"));
        this._convo.appendChild(a);
        // keep the latest answer in view
        this._convo.scrollTop = this._convo.scrollHeight;
      } else {
        const p = document.createElement("div");
        p.className = "placeholder";
        p.textContent = t(this._hass, "convo_hint");
        this._convo.appendChild(p);
      }
    }
  }

  // --------------------------------------------------------- select notebook
  async _selectNotebook(option) {
    if (!option) return;
    try {
      await this._hass.callService("select", "select_option", {
        entity_id: this._config.active_notebook_entity,
        option,
      });
    } catch (err) {
      this.dispatchEvent(
        new CustomEvent("hass-notification", {
          detail: { message: `NotebookLM: ${err.message || err}` },
          bubbles: true,
          composed: true,
        })
      );
    }
  }

  // ------------------------------------------------------------------- send
  async _send() {
    if (this._sending) return;
    const cfg = this._config;
    const q = (this._input.value || "").trim();
    if (!q) return;

    this._sending = true;
    this._sendBtn.disabled = true;

    // Remember the answer shown right now, so we can tell when a NEW one lands,
    // and show the spinner immediately.
    const cur = this._hass.states[cfg.answer_entity];
    this._waitAnswer = cur && cur.attributes ? cur.attributes.answer || "" : "";
    this._pendingQuestion = q;
    this._waiting = true;
    this._input.value = "";
    clearTimeout(this._waitTimer);
    // Safety net: stop spinning after 2 min even if no answer arrives.
    this._waitTimer = setTimeout(() => {
      this._waiting = false;
      this._render();
    }, 120000);
    this._render();

    try {
      await this._hass.callService("text", "set_value", {
        entity_id: cfg.question_entity,
        value: q,
      });
      await this._hass.callService("button", "press", {
        entity_id: cfg.ask_button_entity,
      });
    } catch (err) {
      this._waiting = false;
      clearTimeout(this._waitTimer);
      this._render();
      // surface the failure to the HA UI
      this.dispatchEvent(
        new CustomEvent("hass-notification", {
          detail: { message: `NotebookLM: ${err.message || err}` },
          bubbles: true,
          composed: true,
        })
      );
    } finally {
      this._sending = false;
      this._sendBtn.disabled = false;
    }
  }
}

customElements.define("notebooklm-chat-card", NotebookLMChatCard);

// Advertise the card in the "Add card → Community cards" picker.
window.customCards = window.customCards || [];
window.customCards.push({
  type: "notebooklm-chat-card",
  name: "NotebookLM Chat",
  description:
    "Chat with your active NotebookLM notebook — branded header, message bubbles and a send box. No card-mod needed.",
  preview: true,
  documentationURL: "https://github.com/CauTioNN/ha-notebooklm",
});

/* =========================================================================
 * NotebookLM Panel Card — the "regular" control card as a custom element.
 * Notebook picker + status, an ask box, the last answer, and compact
 * generate-action buttons (podcast / quiz / report / mind map).
 * ========================================================================= */
class NotebookLMPanelCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._built = false;
    this._sending = false;
  }

  setConfig(config) {
    this._config = {
      ...DEFAULTS,
      notebooks_entity: "sensor.notebooklm_notebooks",
      ...(config || {}),
    };
    if (this._built) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    this._render();
  }

  getCardSize() {
    return 8;
  }

  static getStubConfig() {
    return {};
  }

  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        .wrap {
          border-radius: 16px; overflow: hidden; background: #fff; color: #111;
          box-shadow: 0 2px 8px rgba(0,0,0,.12);
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
        }
        .head {
          background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
          color: #fff; padding: 12px 14px; font-size: 1.1rem; font-weight: 600;
          display: flex; align-items: center; gap: 8px;
        }
        .head img {
          width: 22px; height: 22px; border-radius: 50%;
          background: rgba(255,255,255,.18); padding: 3px; box-sizing: border-box;
        }
        .body { padding: 10px 14px; }
        .row { display: flex; align-items: center; gap: 8px; margin: 6px 0; }
        .row label { font-size: .85rem; color: #555; min-width: 84px; }
        select, .ask input {
          font: inherit; font-size: .9rem; color: #111; background: #fff;
          border: 1px solid #d1d5db; border-radius: 8px; padding: 6px 10px; outline: none;
        }
        select { flex: 1; cursor: pointer; }
        select:focus, .ask input:focus { border-color: #4f46e5; }
        .status { font-size: .8rem; color: #555; }
        .ask { display: flex; gap: 8px; margin-top: 8px; }
        .ask input { flex: 1; border-radius: 20px; }
        .ask button {
          border: none; background: #4f46e5; color: #fff; width: 38px; height: 38px;
          border-radius: 50%; cursor: pointer; font-size: 1.05rem; flex: 0 0 auto;
        }
        .ask button:disabled { opacity: .5; }
        .answer {
          background: #f3f4f6; color: #111; border-radius: 10px;
          padding: 10px 12px; margin-top: 10px; white-space: pre-wrap;
          word-wrap: break-word; font-size: .92rem; cursor: pointer;
        }
        .answer.collapsed {
          display: -webkit-box; -webkit-line-clamp: 3;
          -webkit-box-orient: vertical; overflow: hidden;
        }
        .lbl { font-size: .8rem; color: #555; margin: 12px 0 4px; }
        /* compact action buttons (smaller than the default button cards) */
        .actions { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }
        .act {
          display: flex; align-items: center; justify-content: center; gap: 6px;
          border: 1px solid #d1d5db; border-radius: 10px; background: #fff;
          color: #111; padding: 7px 8px; font-size: .85rem; cursor: pointer;
        }
        .act:hover { background: #f3f4f6; }
      </style>
      <div class="wrap">
        <div class="head"><img id="avatar" alt=""> NotebookLM Actions</div>
        <div class="body">
          <div class="row">
            <label>${t(this._hass, "active_notebook")}</label>
            <select id="nb"></select>
          </div>
          <div class="row"><span class="status" id="status"></span></div>
          <div class="lbl">${t(this._hass, "generate")}</div>
          <div class="actions">
            <div class="act" data-svc="generate_audio">🎙️ ${t(this._hass, "act_audio")}</div>
            <div class="act" data-svc="generate_quiz">❓ ${t(this._hass, "act_quiz")}</div>
            <div class="act" data-svc="generate_report">📄 ${t(this._hass, "act_report")}</div>
            <div class="act" data-svc="generate_mind_map">🧠 ${t(this._hass, "act_mind")}</div>
          </div>
        </div>
      </div>
    `;

    this._nbSel = this.shadowRoot.getElementById("nb");
    this._status = this.shadowRoot.getElementById("status");

    this._nbSel.addEventListener("change", () => this._selectNotebook(this._nbSel.value));
    this.shadowRoot.querySelectorAll(".act").forEach((el) =>
      el.addEventListener("click", () => this._action(el.getAttribute("data-svc")))
    );

    this._built = true;
  }

  _render() {
    if (!this._built || !this._hass) return;
    const cfg = this._config;
    const states = this._hass.states;
    this.shadowRoot.getElementById("avatar").src = cfg.avatar;

    const nb = states[cfg.active_notebook_entity];
    const status = states[cfg.status_entity];
    const online = status && status.state === "ok";

    const options = (nb && nb.attributes && Array.isArray(nb.attributes.options))
      ? nb.attributes.options
      : [];
    const key = JSON.stringify(options);
    if (key !== this._nbOptionsKey) {
      this._nbOptionsKey = key;
      this._nbSel.innerHTML = "";
      if (!options.length) {
        const o = document.createElement("option");
        o.value = "";
        o.textContent = t(this._hass, "no_notebooks");
        this._nbSel.appendChild(o);
      }
      for (const opt of options) {
        const o = document.createElement("option");
        o.value = opt;
        o.textContent = opt;
        this._nbSel.appendChild(o);
      }
    }
    if (nb && nb.state && options.includes(nb.state)) this._nbSel.value = nb.state;

    const nbCount = states[cfg.notebooks_entity];
    const count = nbCount ? nbCount.state : "—";
    const conn = online ? t(this._hass, "online") : t(this._hass, "offline");
    this._status.textContent = `${conn} · ${count} ${t(this._hass, "notebooks_word")}`;
  }

  async _selectNotebook(option) {
    if (!option) return;
    try {
      await this._hass.callService("select", "select_option", {
        entity_id: this._config.active_notebook_entity,
        option,
      });
    } catch (err) {
      this._notify(err);
    }
  }

  async _action(service) {
    if (!service) return;
    try {
      await this._hass.callService("notebooklm", service, {});
      this._notify(t(this._hass, "action_sent"));
    } catch (err) {
      this._notify(err);
    }
  }

  _notify(msg) {
    this.dispatchEvent(
      new CustomEvent("hass-notification", {
        detail: { message: typeof msg === "string" ? msg : `NotebookLM: ${msg.message || msg}` },
        bubbles: true,
        composed: true,
      })
    );
  }
}

customElements.define("notebooklm-panel-card", NotebookLMPanelCard);
window.customCards.push({
  type: "notebooklm-panel-card",
  name: "NotebookLM Panel",
  description:
    "Full NotebookLM control panel — notebook picker, ask box, last answer and compact generate actions (podcast, quiz, report, mind map).",
  preview: true,
  documentationURL: "https://github.com/CauTioNN/ha-notebooklm",
});

console.info(
  "%c NOTEBOOKLM-CARDS %c chat + panel loaded ",
  "color:#fff;background:#4f46e5;border-radius:3px 0 0 3px;padding:1px 4px",
  "color:#4f46e5;background:#eef;border-radius:0 3px 3px 0;padding:1px 4px"
);
