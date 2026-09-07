(function () {
  "use strict";

  var page = document.body.dataset.publicPage || "";
  var creatorCache = [];
  var activeAudio = null;

  function $(selector, root) {
    return (root || document).querySelector(selector);
  }

  function $$(selector, root) {
    return Array.from((root || document).querySelectorAll(selector));
  }

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function initials(name) {
    return String(name || "TAC")
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map(function (part) { return part.charAt(0).toUpperCase(); })
      .join("") || "TAC";
  }

  function toneFor(id) {
    var value = Number(id);
    return "tone-" + (Number.isFinite(value) ? Math.abs(value) % 6 : 0);
  }

  async function fetchJSON(url, options) {
    var response = await fetch(url, options || {});
    var data = {};
    try { data = await response.json(); } catch (error) { /* non-JSON response */ }
    if (!response.ok) {
      var requestError = new Error(data.detail || "Request failed");
      requestError.status = response.status;
      throw requestError;
    }
    return data;
  }

  function track(name, detail) {
    var safeDetail = Object.assign({}, detail || {});
    delete safeDetail.phone;
    delete safeDetail.user_phone;
    window.dispatchEvent(new CustomEvent("tac:" + name, { detail: safeDetail }));
    if (Array.isArray(window.dataLayer)) {
      window.dataLayer.push(Object.assign({ event: "tac_" + name }, safeDetail));
    }
  }

  function avatarMarkup(creator) {
    var image = String(creator.avatar_url || "").trim();
    return (
      '<span aria-hidden="true">' + esc(initials(creator.name)) + "</span>" +
      (image ? '<img data-avatar src="' + esc(image) + '" alt="Portrait of ' + esc(creator.name) + '">' : "")
    );
  }

  function installImageFallbacks(root) {
    $$('img[data-avatar]', root).forEach(function (image) {
      image.addEventListener("error", function () { image.remove(); }, { once: true });
    });
  }

  function setAvatar(element, creator) {
    if (!element) return;
    element.className = element.className
      .replace(/\btone-\d\b/g, "")
      .trim() + " " + toneFor(creator.id);
    element.innerHTML = avatarMarkup(creator);
    installImageFallbacks(element);
  }

  function creatorCard(creator) {
    var id = Number(creator.id);
    var url = "influencer.html?id=" + encodeURIComponent(id);
    var hasPreview = Boolean(creator.preview_url);
    var languageLabel = (creator.supported_languages || [creator.primary_language || "en"]).map(function (code) { return String(code).toUpperCase(); }).join(" · ");
    return (
      '<article class="creator-card" data-creator-id="' + id + '">' +
        '<a class="creator-photo-link" href="' + url + '" aria-label="View ' + esc(creator.name) + '">' +
          '<div class="creator-photo avatar-fallback ' + toneFor(id) + '">' + avatarMarkup(creator) + "</div>" +
        "</a>" +
        '<div class="creator-card-body">' +
          '<div class="creator-name-row"><a href="' + url + '"><h3>' + esc(creator.name) + "</h3></a></div>" +
          '<p class="creator-tagline">' + esc(creator.tagline || "A demo creator ready to chat") + "</p>" +
          '<p class="creator-languages">' + esc(languageLabel) + '</p>' +
          '<div class="card-actions">' +
            '<a class="button button-primary" href="' + url + '">Talk now <span aria-hidden="true">→</span></a>' +
            '<button class="sample-unavailable" type="button" data-preview-id="' + id + '" ' +
              (hasPreview ? 'aria-label="Play voice sample"' : 'disabled aria-label="Voice sample unavailable"') + '>▶</button>' +
          "</div>" +
        "</div>" +
      "</article>"
    );
  }

  function setupPreviewButtons(root, creators) {
    var byId = {};
    creators.forEach(function (creator) { byId[String(creator.id)] = creator; });
    $$('[data-preview-id]', root).forEach(function (button) {
      var creator = byId[button.dataset.previewId];
      if (!creator || !creator.preview_url) return;
      button.addEventListener("click", function () {
        playPreview(creator, button);
      });
    });
  }

  function playPreview(creator, button) {
    if (!creator.preview_url) return;
    if (activeAudio) {
      activeAudio.pause();
      activeAudio = null;
    }
    var audio = new Audio(creator.preview_url);
    activeAudio = audio;
    button.setAttribute("aria-label", "Playing voice sample");
    button.textContent = "■";
    track("voice_preview_started", { creator_id: creator.id });
    audio.addEventListener("ended", function () {
      button.textContent = "▶";
      button.setAttribute("aria-label", "Play voice sample");
      activeAudio = null;
      track("voice_preview_completed", { creator_id: creator.id });
    }, { once: true });
    audio.addEventListener("error", function () {
      button.textContent = "▶";
      button.setAttribute("aria-label", "Voice sample unavailable");
      activeAudio = null;
    }, { once: true });
    audio.play().catch(function () {
      button.textContent = "▶";
      activeAudio = null;
    });
  }

  async function loadCreators() {
    var data = await fetchJSON("/api/influencers", { cache: "no-store" });
    creatorCache = Array.isArray(data.influencers) ? data.influencers : [];
    return creatorCache;
  }

  async function installAccountNav() {
    var nav = $(".desktop-nav");
    if (!nav || $("[data-account-nav]", nav)) return;
    var link = document.createElement("a");
    link.dataset.accountNav = "true";
    link.href = "login.html";
    link.textContent = "Sign in";
    nav.appendChild(link);
    try {
      var data = await fetchJSON("/api/auth/me", { cache: "no-store" });
      link.href = data.user.role === "creator" ? "creator-dashboard.html" : "account.html";
      link.textContent = data.user.role === "creator" ? "Backstage" : "My account";
    } catch (error) {
      // Guests keep the optional sign-in link; calls remain open without it.
    }
  }

  async function initHome() {
    track("landing_viewed");
    var rail = $("#featured-creators");
    try {
      var creators = await loadCreators();
      if (creators.length) {
        var featured = creators.length > 1 ? creators[1] : creators[0];
        setAvatar($("#hero-avatar"), featured);
        $("#hero-name").textContent = featured.name + " is ready";
        $("#hero-tagline").textContent = featured.tagline || "A useful conversation is one tap away.";
        $("#hero-profile-link").href = "influencer.html?id=" + encodeURIComponent(featured.id);
        $("#hero-profile-link").textContent = "View " + featured.name.split(/\s+/)[0] + "'s profile →";
        setupHeroPreview(featured);
      } else {
        $("#hero-name").textContent = "New voices are on the way";
        $("#hero-tagline").textContent = "Check back soon for the first demo conversation.";
        $("#hero-profile-link").textContent = "Explore TAC Voice →";
        $("#hero-profile-link").href = "influencers.html";
      }

      if (rail) {
        if (!creators.length) {
          rail.innerHTML = '<div class="error-state"><h2>No demo creators yet.</h2><p>The first conversations are being prepared.</p></div>';
        } else {
          var visible = creators.slice(0, 3);
          rail.innerHTML = visible.map(creatorCard).join("");
          installImageFallbacks(rail);
          setupPreviewButtons(rail, visible);
        }
      }
    } catch (error) {
      if (rail) rail.innerHTML = '<div class="error-state"><h2>Creators could not load.</h2><p>Visit Explore to try again.</p><a class="button button-secondary" href="influencers.html">Open Explore</a></div>';
    }
  }

  function setupHeroPreview(creator) {
    var button = $("#hero-preview");
    if (!button || !creator.preview_url) return;
    button.disabled = false;
    button.querySelector("span:last-child").textContent = "Hear " + creator.name.split(/\s+/)[0] + "'s voice";
    button.addEventListener("click", function () { playPreview(creator, button); });
  }

  async function initDirectory() {
    track("directory_viewed");
    var list = $("#voice-list");
    var errorState = $("#grid-error");
    var emptyState = $("#directory-empty");
    var input = $("#search-input");
    var clear = $("#search-clear");
    var emptyClear = $("#empty-clear");
    var retry = $("#directory-retry");

    function render(creators, query) {
      var normalized = String(query || "").trim().toLowerCase();
      var filtered = creators.filter(function (creator) {
        var haystack = [creator.name, creator.tagline, creator.bio].join(" ").toLowerCase();
        return !normalized || haystack.indexOf(normalized) !== -1;
      });

      $("#voice-count").textContent = creators.length + (creators.length === 1 ? " creator" : " creators");
      $("#directory-result-line").textContent = normalized
        ? filtered.length + (filtered.length === 1 ? " match" : " matches") + " for “" + query.trim() + "”"
        : "Showing everyone";
      clear.hidden = !normalized;
      emptyState.hidden = filtered.length !== 0;
      list.hidden = filtered.length === 0;
      list.innerHTML = filtered.map(creatorCard).join("");
      installImageFallbacks(list);
      setupPreviewButtons(list, filtered);
    }

    async function load() {
      errorState.hidden = true;
      emptyState.hidden = true;
      list.hidden = false;
      list.innerHTML = '<div class="creator-card skeleton-card"></div><div class="creator-card skeleton-card"></div><div class="creator-card skeleton-card"></div>';
      try {
        var creators = await loadCreators();
        render(creators, input.value);
      } catch (error) {
        list.hidden = true;
        errorState.hidden = false;
        $("#voice-count").textContent = "Unavailable";
        $("#directory-result-line").textContent = "The creator list is temporarily unavailable.";
      }
    }

    input.addEventListener("input", function () { render(creatorCache, input.value); });
    input.addEventListener("search", function () { render(creatorCache, input.value); });
    clear.addEventListener("click", function () { input.value = ""; render(creatorCache, ""); input.focus(); });
    emptyClear.addEventListener("click", function () { input.value = ""; render(creatorCache, ""); input.focus(); });
    retry.addEventListener("click", load);
    load();
  }

  function promptsFor(creator) {
    var text = (creator.tagline + " " + creator.bio).toLowerCase();
    if (/fitness|training|marathon|nutrition/.test(text)) {
      return ["How do I stay consistent when motivation drops?", "What should a beginner focus on first?", "Can you help me plan a realistic training week?"];
    }
    if (/marketing|brand|content|customer/.test(text)) {
      return ["How would you find a startup's first 1,000 customers?", "What is the biggest mistake small brands make?", "Can you make my content idea more specific?"];
    }
    if (/estate|property|home|budget/.test(text)) {
      return ["What should I check before viewing a home?", "How do I set a realistic buying budget?", "Which questions should I ask an estate agent?"];
    }
    return ["What is one lesson you learned the hard way?", "What should a beginner do first?", "Can you give me honest advice about my idea?"];
  }

  function renderPrompts(creator) {
    var container = $("#conversation-prompts");
    container.innerHTML = promptsFor(creator).map(function (prompt) {
      return '<button class="prompt-button" type="button" aria-pressed="false"><span>“' + esc(prompt) + '”</span><span aria-hidden="true">+</span></button>';
    }).join("");
    $$(".prompt-button", container).forEach(function (button) {
      button.addEventListener("click", function () {
        $$(".prompt-button", container).forEach(function (other) { other.setAttribute("aria-pressed", "false"); });
        button.setAttribute("aria-pressed", "true");
        track("conversation_prompt_selected", { creator_id: creator.id, prompt: button.textContent.trim().slice(0, 100) });
      });
    });
  }

  function showToast(message) {
    var oldToast = $(".share-toast");
    if (oldToast) oldToast.remove();
    var toast = document.createElement("div");
    toast.className = "share-toast";
    toast.setAttribute("role", "status");
    toast.textContent = message;
    document.body.appendChild(toast);
    window.setTimeout(function () { toast.remove(); }, 2400);
  }

  function setupShare(creator) {
    var button = $("#share-profile");
    button.addEventListener("click", async function () {
      var shareData = {
        title: creator.name + " on TAC Voice",
        text: "Talk with the clearly disclosed AI voice of " + creator.name + ".",
        url: window.location.href
      };
      try {
        if (navigator.share) {
          await navigator.share(shareData);
        } else if (navigator.clipboard) {
          await navigator.clipboard.writeText(window.location.href);
          showToast("Profile link copied");
        } else {
          showToast("Copy the profile link from your browser");
        }
        track("profile_shared", { creator_id: creator.id });
      } catch (error) {
        if (error && error.name !== "AbortError") showToast("Sharing is not available in this browser");
      }
    });
  }

  async function initProfile() {
    var id = new URLSearchParams(window.location.search).get("id");
    var loading = $("#profile-loading");
    var content = $("#profile-content");
    var errorState = $("#profile-error");

    if (!id || !/^\d+$/.test(id)) {
      loading.hidden = true;
      errorState.hidden = false;
      return;
    }

    try {
      var data = await fetchJSON("/api/influencers/" + encodeURIComponent(id), { cache: "no-store" });
      var creator = data.influencer;
      if (!creator) throw new Error("Creator not found");

      document.title = creator.name + " — TAC Voice";
      $("#profile-name").textContent = creator.name;
      $("#profile-tagline").textContent = creator.tagline || "A demo creator ready to talk.";
      $("#profile-bio").textContent = creator.bio || "This demo persona does not have a bio yet.";
      $("#profile-kind").textContent = creator.is_demo ? "Demo persona" : "Verified creator AI";
      $("#profile-languages").innerHTML = (creator.supported_languages || [creator.primary_language || "en"]).map(function (code) { return '<span>' + esc(String(code).toUpperCase()) + '</span>'; }).join("");
      $("#call-limit-label").textContent = "Up to " + Math.max(1, Math.round((creator.max_call_seconds || 300) / 60)) + " min";
      $("#call-name").textContent = creator.name.split(/\s+/)[0];
      setAvatar($("#profile-avatar"), creator);
      renderPrompts(creator);
      setupProfilePreview(creator);
      if (window.TACWebCall) window.TACWebCall.setup(creator, track);
      setupShare(creator);

      try {
        var account = await fetchJSON("/api/auth/me", { cache: "no-store" });
        var nameInput = $("#user-name");
        if (nameInput && !nameInput.value) nameInput.value = account.user.display_name;
      } catch (accountError) { /* guest call */ }

      loading.hidden = true;
      content.hidden = false;
      track("creator_profile_viewed", { creator_id: creator.id });
    } catch (error) {
      loading.hidden = true;
      errorState.hidden = false;
    }
  }

  function setupProfilePreview(creator) {
    var button = $("#profile-preview");
    if (!creator.preview_url) return;
    button.disabled = false;
    button.setAttribute("aria-label", "Play " + creator.name + " voice sample");
    $("#preview-note").textContent = "A short preview of this AI voice.";
    button.addEventListener("click", function () { playPreview(creator, button); });
  }

  function boot() {
    installAccountNav();
    if (page === "home") initHome();
    if (page === "directory") initDirectory();
    if (page === "profile") initProfile();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
