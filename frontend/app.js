/* ============================================================
   TAC Voice — frontend logic
   Brutalist-Minimalist design system.
   Dispatches on <body data-page="…">.
   ============================================================ */

(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const PAGE = document.body.dataset.page || "home";
  const TOKEN_KEY = "tac_admin_token";

  /* ---------- helpers ---------- */

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function getToken() {
    try { return localStorage.getItem(TOKEN_KEY) || ""; } catch (e) { return ""; }
  }

  async function fetchJSON(url, options) {
    const opts = options || {};
    const headers = Object.assign({}, opts.headers || {});
    if (opts.auth && opts.auth === true) {
      const token = getToken();
      if (token) headers.Authorization = "Bearer " + token;
    }
    const res = await fetch(url, Object.assign({}, opts, { headers }));
    let data = {};
    try { data = await res.json(); } catch (e) { /* non-JSON */ }
    if (!res.ok) {
      const err = new Error(data && data.detail ? data.detail : "Request failed");
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function fmtTime(iso) {
    if (!iso) return "\u2014";
    const d = new Date(iso);
    return d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function initials(name) {
    return String(name || "?")
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0].toUpperCase())
      .join("") || "?";
  }

  /* ---------- status ---------- */

  function setStatus(ok, text) {
    const dataState = ok === null ? "checking" : ok ? "up" : "down";
    $$(".status-pill").forEach((pill) => {
      pill.dataset.state = dataState;
      const dot = pill.querySelector(".dot");
      if (dot) {
        dot.style.background = ok === null ? "#fbbf24" : ok ? "#FF4D1C" : "#f87171";
        if (ok) dot.style.animation = "pulse 2.4s infinite";
      }
      const t = pill.querySelector(".status-text");
      if (t) t.textContent = text;
    });
  }

  async function checkHealth() {
    try {
      const res = await fetch("/health", { cache: "no-store" });
      const data = await res.json();
      const ok = res.ok && data.ok === true;
      setStatus(ok, ok ? "All systems operational" : "Degraded");
      if (data.environment) {
        const envEl = $("#status-env");
        if (envEl) envEl.textContent = data.environment;
      }
      return ok;
    } catch (e) {
      setStatus(false, "Unreachable");
      return false;
    }
  }

  /* ---------- voice card renderers ---------- */

  function voiceCardFeatured(v) {
    var avatarUrl = (v.avatar_url || "").trim();
    var imgTag = avatarUrl
      ? '<img alt="' + esc(v.name) + '" class="absolute inset-0 w-full h-full object-cover grayscale mix-blend-luminosity opacity-40 group-hover:opacity-80 group-hover:scale-105 transition-all duration-700 ease-out" src="' + esc(avatarUrl) + '"/>'
      : '';
    return (
      '<a class="group relative aspect-[3/4] md:aspect-[4/5] border-b md:border-b-0 md:border-r border-outline-variant flex flex-col justify-end overflow-hidden p-6 hover:bg-surface-container transition-colors" href="influencer.html?id=' + v.id + '">' +
        imgTag +
        '<div class="absolute inset-0 bg-gradient-to-t from-surface-container-lowest via-surface-container-lowest/50 to-transparent"></div>' +
        '<div class="relative z-10 flex flex-col gap-2">' +
          '<div class="flex items-center gap-2 mb-2">' +
            '<div class="w-2 h-2 rounded-full bg-secondary-container animate-pulse"></div>' +
            '<span class="font-label-mono text-[10px] text-secondary-container uppercase tracking-widest">Active Node</span>' +
          '</div>' +
          '<h3 class="font-headline-lg text-headline-lg-mobile md:text-headline-lg text-on-surface group-hover:text-primary transition-colors leading-none">' + esc(v.name) + '</h3>' +
          '<p class="font-label-mono text-[11px] text-on-surface-variant uppercase tracking-widest">' + esc(v.tagline || "AI Voice Agent") + '</p>' +
        '</div>' +
      '</a>'
    );
  }

  function voiceRowDirectory(v) {
    var avatarUrl = (v.avatar_url || "").trim();
    var imgTag = avatarUrl
      ? '<img class="w-16 h-16 object-cover rounded-[2px]" src="' + esc(avatarUrl) + '" alt="' + esc(v.name) + '"/>'
      : '<div class="w-16 h-16 rounded-[2px] bg-surface-container-high flex items-center justify-center font-label-mono text-on-surface-variant text-[18px]">' + esc(initials(v.name)) + '</div>';
    return (
      '<a class="group flex items-center justify-between py-stack-sm border-b border-[#2A2620] hover:bg-[#1A1713] transition-colors px-2 -mx-2" href="influencer.html?id=' + v.id + '">' +
        '<div class="flex items-center gap-stack-md w-full md:w-auto">' +
          imgTag +
          '<div class="flex flex-col gap-1">' +
            '<span class="font-headline-lg text-[28px] leading-[28px] text-[#F5F0E8]">' + esc(v.name) + '</span>' +
            '<span class="font-body-md text-body-md text-[#6B645C]">' + esc(v.tagline || "AI Voice Agent") + '</span>' +
          '</div>' +
        '</div>' +
        '<div class="hidden md:flex items-center gap-stack-lg w-[300px] justify-between">' +
          '<span class="font-label-mono text-label-mono text-[#F5F0E8]">VOICE</span>' +
          '<div class="flex items-center gap-4">' +
            '<span class="font-label-mono text-label-mono text-[#FF4D1C] group-hover:hidden block">AVAILABLE</span>' +
            '<span class="font-label-mono text-label-mono text-[#F5F0E8] hidden group-hover:block underline decoration-[#FF4D1C] underline-offset-4">INITIATE CALL</span>' +
          '</div>' +
        '</div>' +
      '</a>'
    );
  }

  function adminVoiceRow(v) {
    var avatarUrl = (v.avatar_url || "").trim();
    var imgTag = avatarUrl
      ? '<img class="w-12 h-12 object-cover rounded-[2px]" src="' + esc(avatarUrl) + '" alt="' + esc(v.name) + '"/>'
      : '<div class="w-12 h-12 rounded-[2px] bg-surface-container-high flex items-center justify-center font-label-mono text-on-surface-variant">' + esc(initials(v.name)) + '</div>';
    return (
      '<div class="group grid grid-cols-4 font-label-mono text-primary border-b border-[#2A2620] py-5 items-center hover:bg-surface-container-lowest transition-colors">' +
        '<div class="flex items-center gap-4">' +
          imgTag +
          '<div class="flex flex-col">' +
            '<span class="text-primary group-hover:text-[#FF4D1C] transition-colors">' + esc(v.name) + '</span>' +
            '<span class="text-on-surface-variant text-[11px]">' + esc(v.tagline || "\u2014") + '</span>' +
          '</div>' +
        '</div>' +
        '<div class="text-on-surface-variant">#' + v.id + '</div>' +
        '<div><a class="text-primary underline decoration-[#2A2620] hover:decoration-[#FF4D1C] transition-colors" href="influencer.html?id=' + v.id + '">View</a></div>' +
        '<div class="text-right"><button class="text-[#6B645C] hover:text-[#fca5a5] transition-colors uppercase" data-del="' + v.id + '">Delete</button></div>' +
      '</div>'
    );
  }

  function callRequestRow(c) {
    var statusColor = c.status === "completed" ? "#6B645C" : c.status === "failed" ? "#fca5a5" : "#FF4D1C";
    return (
      '<div class="grid grid-cols-6 font-label-mono text-primary border-b border-[#2A2620] py-5 items-center hover:bg-surface-container-lowest transition-colors">' +
        '<div class="text-on-surface-variant">' + esc(fmtTime(c.created_at)) + '</div>' +
        '<div>#' + c.influencer_id + '</div>' +
        '<div class="text-on-surface-variant">' + esc(c.user_name || "\u2014") + '</div>' +
        '<div class="text-on-surface-variant">' + esc(c.user_phone) + '</div>' +
        '<div style="color:' + statusColor + '">' + esc(c.status || "\u2014").toUpperCase() + '</div>' +
        '<div class="text-right text-on-surface-variant text-[11px]">' + esc(c.call_sid || "\u2014") + '</div>' +
      '</div>'
    );
  }

  /* ============================================================
     HOME
     ============================================================ */
  async function initHome() {
    setStatus(null, "Checking\u2026");
    checkHealth();
    setInterval(checkHealth, 30000);

    // Pipeline stats from /info
    try {
      const info = await fetchJSON("/info", { cache: "no-store" });
      const p = info.pipeline || {};
      const set = (sel, v) => { const el = $(sel); if (el && v) el.textContent = v; };
      set("#stat-stt", p.stt);
      set("#stat-llm", p.llm);
      set("#stat-tts", p.tts);
      const envBadge = $("#env-badge");
      if (envBadge && info.environment) envBadge.textContent = info.environment;
    } catch (e) { /* non-fatal */ }

    // Featured voices
    try {
      const data = await fetchJSON("/api/influencers", { cache: "no-store" });
      const voices = data.influencers || [];
      const stat = $("#stat-voices");
      if (stat) stat.textContent = String(voices.length);
      const grid = $("#voice-grid");
      if (grid) {
        if (voices.length === 0) {
          grid.innerHTML = '<p class="font-body-md text-on-surface-variant p-6">No voices published yet \u2014 check back soon.</p>';
        } else {
          grid.innerHTML = voices.slice(0, 3).map(voiceCardFeatured).join("");
        }
      }
    } catch (e) {
      const grid = $("#voice-grid");
      if (grid) grid.innerHTML = '<p class="font-body-md text-on-surface-variant p-6">Could not load voices right now.</p>';
    }
  }

  /* ============================================================
     DIRECTORY
     ============================================================ */
  async function initDirectory() {
    const list = $("#voice-list");
    const errEl = $("#grid-error");
    const countEl = $("#voice-count");
    try {
      const data = await fetchJSON("/api/influencers", { cache: "no-store" });
      const voices = data.influencers || [];
      if (countEl) countEl.textContent = String(voices.length);
      if (voices.length === 0) {
        list.innerHTML = '<p class="font-body-md text-on-surface-variant py-8">No voices published yet \u2014 check back soon.</p>';
      } else {
        list.innerHTML = voices.map(voiceRowDirectory).join("");
      }
    } catch (e) {
      if (list) list.innerHTML = "";
      if (errEl) errEl.classList.remove("hidden");
    }

    // Search filter
    const searchInput = $("#search-input");
    if (searchInput && list) {
      searchInput.addEventListener("input", function () {
        var q = this.value.toLowerCase();
        var rows = list.querySelectorAll("a");
        rows.forEach(function (row) {
          var text = row.textContent.toLowerCase();
          row.style.display = text.includes(q) ? "" : "none";
        });
      });
    }
  }

  /* ============================================================
     INFLUENCER PROFILE
     ============================================================ */
  async function initProfile() {
    const params = new URLSearchParams(window.location.search);
    const id = params.get("id");

    if (!id || !/^\d+$/.test(id)) {
      showProfileError("This voice could not be found.");
      return;
    }

    var influencer;
    try {
      const data = await fetchJSON("/api/influencers/" + id, { cache: "no-store" });
      influencer = data.influencer;
    } catch (e) {
      showProfileError("This voice could not be found.");
      return;
    }

    var nameEl = $("#profile-name");
    if (nameEl) nameEl.textContent = influencer.name;
    var taglineEl = $("#profile-tagline");
    if (taglineEl) taglineEl.textContent = influencer.tagline || "";
    var bioEl = $("#profile-bio");
    if (bioEl) bioEl.textContent = influencer.bio || "No bio yet.";
    var callNameEl = $("#call-name");
    if (callNameEl) callNameEl.textContent = "Contact " + influencer.name;

    document.title = influencer.name + " \u2014 TAC Voice";

    // Portrait image
    var portrait = $("#profile-portrait");
    if (portrait && influencer.avatar_url) {
      portrait.style.backgroundImage = "url('" + influencer.avatar_url + "')";
      portrait.style.backgroundSize = "cover";
      portrait.style.backgroundPosition = "center";
    }

    // Powered-by chips
    try {
      const info = await fetchJSON("/info", { cache: "no-store" });
      const p = info.pipeline || {};
      const chips = [
        p.stt && "STT \u00b7 " + p.stt,
        p.llm && "LLM \u00b7 " + p.llm,
        p.tts && "TTS \u00b7 " + p.tts,
      ].filter(Boolean);
      const row = $("#powered-chips");
      if (row && chips.length) {
        row.innerHTML = chips.map(function (c) {
          return '<span class="font-label-mono text-[11px] text-on-surface-variant uppercase tracking-widest px-3 py-1 border border-[#2A2620]">' + esc(c) + '</span>';
        }).join("");
      }
    } catch (e) { /* non-fatal */ }

    // Call form
    var form = $("#call-form");
    var submit = $("#call-submit");
    var result = $("#call-result");
    if (!form) return;

    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      if (submit.disabled) return;

      var user_name = ($("#user-name") || {}).value || "";
      user_name = user_name.trim();
      var user_phone = ($("#user-phone") || {}).value || "";
      user_phone = user_phone.trim();
      var phoneError = $("#phone-error");

      if (phoneError) phoneError.classList.add("hidden");
      if (!/^\+?[0-9\s().-]{7,20}$/.test(user_phone)) {
        if (phoneError) {
          phoneError.textContent = "That number doesn't look right \u2014 use digits with an optional + country code.";
          phoneError.classList.remove("hidden");
        }
        var phoneInput = $("#user-phone");
        if (phoneInput) phoneInput.focus();
        return;
      }

      submit.disabled = true;
      var label = submit.querySelector(".btn-label");
      if (label) label.textContent = "Calling\u2026";

      try {
        const data = await fetchJSON("/api/call-requests", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ influencer_id: influencer.id, user_name: user_name, user_phone: user_phone }),
        });
        result.innerHTML =
          '<div class="result-box success">' +
            '<span>\u260E ' + esc(data.message || "The call is on its way.") + '</span>' +
            '<span class="r-detail">Answer your phone when it rings. (Call SID ' + esc(data.call_sid || "\u2014") + ')</span>' +
          '</div>';
      } catch (err) {
        var friendly = friendlyError(err.message);
        result.innerHTML =
          '<div class="result-box error">' +
            '<span>Call could not be started</span>' +
            '<span class="r-detail">' + esc(friendly) + '</span>' +
          '</div>';
      } finally {
        submit.disabled = false;
        if (label) label.textContent = "Call me now";
      }
    });
  }

  function showProfileError(message) {
    var name = $("#profile-name");
    if (name) name.textContent = message;
    var card = $("#call-card");
    if (card) card.classList.add("hidden");
  }

  function friendlyError(text) {
    var t = String(text || "");
    var lower = t.toLowerCase();
    if (lower.includes("not configured") || lower.includes("calling is not configured"))
      return "Calling isn\u2019t configured on the server yet (missing Twilio keys). Contact the operator.";
    if (lower.includes("twilio rejected"))
      return "Twilio rejected the call \u2014 check the credentials and number verification.";
    return t;
  }

  /* ============================================================
     STUDIO (admin)
     ============================================================ */
  function initStudio() {
    var tokenInput = $("#admin-token");
    var tokenSave = $("#token-save");

    if (tokenInput) {
      tokenInput.value = getToken();
      if (tokenSave) {
        tokenSave.addEventListener("click", function () {
          try { localStorage.setItem(TOKEN_KEY, tokenInput.value.trim()); } catch (e) { /* ignore */ }
          setFormMsg("#create-msg", "Token saved for this browser.", "ok");
          loadStudioData();
        });
      }
    }

    loadStudioData();
  }

  async function loadStudioData() {
    // Voices
    try {
      const data = await fetchJSON("/api/influencers", { cache: "no-store" });
      const voices = data.influencers || [];
      var statVoices = $("#stat-total-voices");
      if (statVoices) statVoices.textContent = String(voices.length);

      var rows = $("#admin-rows");
      if (rows) {
        if (voices.length === 0) {
          rows.innerHTML = '<p class="font-label-mono text-on-surface-variant py-4">No voices yet \u2014 create your first one.</p>';
        } else {
          // Render as a table with header
          rows.innerHTML =
            '<div class="grid grid-cols-4 font-label-mono text-on-surface-variant uppercase border-b border-[#2A2620] pb-4 mb-2">' +
              '<div>Voice</div><div>ID</div><div>View</div><div class="text-right">Actions</div>' +
            '</div>' +
            voices.map(adminVoiceRow).join("");
          $$("[data-del]").forEach(function (btn) {
            btn.addEventListener("click", function () { deleteInfluencer(Number(btn.dataset.del)); });
          });
        }
      }
    } catch (err) {
      var rows = $("#admin-rows");
      if (rows) rows.innerHTML = '<p class="font-label-mono text-on-surface-variant py-4">Could not load voices \u2014 ' + esc(err.message) + '</p>';
    }

    // Creator identity and safety review queue
    try {
      const reviewData = await fetchJSON("/api/creator-reviews?limit=50", {
        cache: "no-store",
        auth: true,
      });
      const reviews = reviewData.reviews || [];
      var reviewCount = $("#review-count");
      if (reviewCount) reviewCount.textContent = reviews.length + (reviews.length === 1 ? " waiting" : " waiting");
      var reviewRows = $("#creator-review-rows");
      if (reviewRows) {
        if (!reviews.length) {
          reviewRows.innerHTML = '<div class="font-label-mono text-on-surface-variant py-4 border-t border-[#2A2620]">No creator profiles are waiting for review.</div>';
        } else {
          reviewRows.innerHTML = reviews.map(function (review) {
            return '<article class="grid grid-cols-12 gap-4 py-5 border-t border-[#2A2620] items-center">' +
              '<div class="col-span-3"><strong class="block text-primary">' + esc(review.name) + '</strong><span class="font-label-mono text-[10px] text-on-surface-variant">' + esc(review.owner_email) + '</span></div>' +
              '<p class="col-span-5 text-on-surface-variant m-0">' + esc(review.tagline || "No tagline") + '</p>' +
              '<span class="col-span-2 font-label-mono uppercase text-[11px] ' + (review.review_status === "pending" ? 'text-[#FF4D1C]' : 'text-on-surface-variant') + '">' + esc(review.review_status) + '</span>' +
              '<div class="col-span-2 flex justify-end gap-3">' +
                '<button class="font-label-mono text-[11px] uppercase text-primary underline underline-offset-4" data-review-id="' + Number(review.id) + '" data-review-decision="approved">Approve</button>' +
                '<button class="font-label-mono text-[11px] uppercase text-error underline underline-offset-4" data-review-id="' + Number(review.id) + '" data-review-decision="rejected">Reject</button>' +
              '</div></article>';
          }).join("");
          $$("[data-review-decision]").forEach(function (button) {
            button.addEventListener("click", function () {
              reviewCreator(Number(button.dataset.reviewId), button.dataset.reviewDecision);
            });
          });
        }
      }
    } catch (err) {
      var reviewRows = $("#creator-review-rows");
      if (reviewRows) reviewRows.innerHTML = '<div class="font-label-mono text-on-surface-variant py-4 border-t border-[#2A2620]">Could not load creator reviews \u2014 ' + esc(err.message) + '</div>';
    }

    // Pipeline info
    try {
      const info = await fetchJSON("/info", { cache: "no-store" });
      var statPipeline = $("#stat-pipeline");
      if (statPipeline && info.pipeline) {
        statPipeline.textContent = [info.pipeline.stt, info.pipeline.llm, info.pipeline.tts].filter(Boolean).length + "/3";
      }
      var statEnv = $("#stat-env");
      if (statEnv && info.environment) statEnv.textContent = info.environment;
    } catch (e) { /* non-fatal */ }

    // Call requests
    try {
      const data = await fetchJSON("/api/call-requests?limit=20", { cache: "no-store", auth: true });
      const calls = data.call_requests || [];
      var statCalls = $("#stat-total-calls");
      if (statCalls) statCalls.textContent = String(calls.length);

      var callsBody = $("#calls-body");
      if (!callsBody) return;
      if (calls.length === 0) {
        callsBody.innerHTML = '<div class="font-label-mono text-on-surface-variant py-4">No call requests yet.</div>';
        return;
      }
      callsBody.innerHTML = calls.map(callRequestRow).join("");
    } catch (err) {
      var callsBody = $("#calls-body");
      if (callsBody) callsBody.innerHTML = '<div class="font-label-mono text-on-surface-variant py-4">' + esc(err.message) + '</div>';
    }
  }

  async function deleteInfluencer(id) {
    if (!window.confirm("Delete voice #" + id + "? This cannot be undone.")) return;
    try {
      await fetchJSON("/api/influencers/" + id, { method: "DELETE", auth: true });
      loadStudioData();
    } catch (err) {
      setFormMsg("#create-msg", err.message, "err");
    }
  }

  async function reviewCreator(id, decision) {
    var verb = decision === "approved" ? "approve" : "reject";
    if (!window.confirm(verb.charAt(0).toUpperCase() + verb.slice(1) + " creator profile #" + id + "?")) return;
    try {
      await fetchJSON("/api/creator-reviews/" + id, {
        method: "PATCH",
        auth: true,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision: decision }),
      });
      setFormMsg("#create-msg", "Creator profile " + decision + ".", "ok");
      loadStudioData();
    } catch (err) {
      setFormMsg("#create-msg", err.message, "err");
    }
  }

  /* ============================================================
     CONFIG (create/edit voice)
     ============================================================ */
  function initConfig() {
    var tokenInput = $("#admin-token");
    var tokenSave = $("#token-save");

    if (tokenInput) {
      tokenInput.value = getToken();
      if (tokenSave) {
        tokenSave.addEventListener("click", function () {
          try { localStorage.setItem(TOKEN_KEY, tokenInput.value.trim()); } catch (e) { /* ignore */ }
          setFormMsg("#config-msg", "Token saved.", "ok");
        });
      }
    }

    var form = $("#create-form");
    if (form) {
      form.addEventListener("submit", async function (event) {
        event.preventDefault();
        var name = ($("#f-name") || {}).value || "";
        name = name.trim();
        if (name.length < 2) {
          setFormMsg("#config-msg", "Name is required (min 2 characters).", "err");
          return;
        }
        var payload = {
          name: name,
          tagline: (($("#f-tagline") || {}).value || "").trim(),
          bio: (($("#f-bio") || {}).value || "").trim(),
          avatar_url: (($("#f-avatar") || {}).value || "").trim(),
          voice_id: (($("#f-voice") || {}).value || "").trim(),
          system_prompt: (($("#f-prompt") || {}).value || "").trim(),
        };
        try {
          await fetchJSON("/api/influencers", {
            method: "POST",
            auth: true,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          setFormMsg("#config-msg", "Voice created successfully.", "ok");
          form.reset();
        } catch (err) {
          setFormMsg("#config-msg", err.message, "err");
        }
      });
    }

    // Character count for system prompt
    var textarea = $("#f-prompt");
    var charCount = $("#char-count");
    if (textarea && charCount) {
      textarea.addEventListener("input", function () {
        charCount.textContent = this.value.length.toLocaleString();
      });
    }

    // --- Voice clone / select ---

    // Audio file preview
    var cloneFile = $("#clone-file");
    var clonePreview = $("#clone-preview");
    if (cloneFile && clonePreview) {
      cloneFile.addEventListener("change", function () {
        var file = cloneFile.files && cloneFile.files[0];
        if (file) {
          clonePreview.src = URL.createObjectURL(file);
          clonePreview.classList.remove("hidden");
        } else {
          clonePreview.classList.add("hidden");
          clonePreview.src = "";
        }
      });
    }

    // Load existing voices into dropdown
    var voiceSelect = $("#voice-select");
    async function loadVoices() {
      if (!voiceSelect) return;
      try {
        var data = await fetchJSON("/api/voices", { auth: true });
        var voices = data.voices || [];
        voiceSelect.innerHTML = '<option value="">\u2014 select a voice \u2014</option>';
        voices.forEach(function (v) {
          var opt = document.createElement("option");
          opt.value = v.id;
          opt.textContent = v.name + " (" + v.id.slice(0, 8) + "\u2026)";
          voiceSelect.appendChild(opt);
        });
      } catch (e) {
        // non-fatal — dropdown stays empty
      }
    }
    loadVoices();

    // Select existing voice -> fill voice ID field
    if (voiceSelect) {
      voiceSelect.addEventListener("change", function () {
        var voiceInput = $("#f-voice");
        if (voiceInput && voiceSelect.value) {
          voiceInput.value = voiceSelect.value;
        }
      });
    }

    // Clone button
    var cloneBtn = $("#clone-btn");
    var cloneStatus = $("#clone-status");
    if (cloneBtn) {
      cloneBtn.addEventListener("click", async function () {
        var file = cloneFile && cloneFile.files && cloneFile.files[0];
        var name = ($("#clone-name") || {}).value || "";
        name = name.trim();
        var language = ($("#clone-lang") || {}).value || "en";

        if (!name) {
          if (cloneStatus) { cloneStatus.textContent = "Voice name is required."; cloneStatus.style.color = "#fca5a5"; }
          return;
        }
        if (!file) {
          if (cloneStatus) { cloneStatus.textContent = "Please select an audio file."; cloneStatus.style.color = "#fca5a5"; }
          return;
        }

        cloneBtn.disabled = true;
        if (cloneStatus) { cloneStatus.textContent = "Cloning voice\u2026"; cloneStatus.style.color = ""; }

        var fd = new FormData();
        fd.append("clip", file);
        fd.append("name", name);
        fd.append("language", language);

        try {
          var token = getToken();
          var headers = {};
          if (token) headers["Authorization"] = "Bearer " + token;

          var res = await fetch("/api/voice-clone", { method: "POST", headers: headers, body: fd });
          var data = {};
          try { data = await res.json(); } catch (e) { /* */ }
          if (!res.ok) {
            throw new Error(data.detail || "Clone request failed");
          }

          var voiceInput = $("#f-voice");
          if (voiceInput) voiceInput.value = data.voice_id;
          if (cloneStatus) { cloneStatus.textContent = "Voice cloned: " + data.name + " (" + data.voice_id.slice(0, 8) + "\u2026)"; cloneStatus.style.color = "#4ade80"; }

          // Refresh the dropdown
          loadVoices();
        } catch (err) {
          if (cloneStatus) { cloneStatus.textContent = err.message; cloneStatus.style.color = "#fca5a5"; }
        } finally {
          cloneBtn.disabled = false;
        }
      });
    }
  }

  /* ============================================================
     LOGIN / SIGNUP (non-functional UI)
     ============================================================ */
  function initLogin() {
    var form = $("form");
    if (form) {
      form.addEventListener("submit", function (e) { e.preventDefault(); });
    }
  }

  function initSignup() {
    var form = $("form");
    if (form) {
      form.addEventListener("submit", function (e) { e.preventDefault(); });
    }
  }

  /* ============================================================
     CONNECTING / CONNECTED (decorative states)
     ============================================================ */
  function initConnecting() {
    // Timer is in inline script on the page
  }

  function initConnected() {
    // Waveform animation is in inline script on the page
  }

  /* ============================================================
     404 / ERROR (static pages)
     ============================================================ */
  function initError404() { /* static */ }
  function initError() { /* static */ }

  /* ---------- utility ---------- */

  function setFormMsg(sel, message, kind) {
    var el = $(sel);
    if (!el) return;
    el.textContent = message;
    el.className = "form-msg " + (kind || "");
  }

  /* ============================================================
     BOOT
     ============================================================ */
  function boot() {
    var pages = {
      home: initHome,
      influencers: initDirectory,
      influencer: initProfile,
      admin: initStudio,
      config: initConfig,
      login: initLogin,
      signup: initSignup,
      connecting: initConnecting,
      connected: initConnected,
      error404: initError404,
      error: initError,
    };

    var init = pages[PAGE] || initHome;
    init();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
