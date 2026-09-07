(function () {
  "use strict";

  var page = document.body.dataset.authPage || "";

  function $(selector, root) {
    return (root || document).querySelector(selector);
  }

  async function request(url, options) {
    var response = await fetch(url, Object.assign({
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" }
    }, options || {}));
    var data = {};
    try { data = await response.json(); } catch (error) { /* empty response */ }
    if (!response.ok) {
      var requestError = new Error(data.detail || "Something went wrong.");
      requestError.status = response.status;
      throw requestError;
    }
    return data;
  }

  function setMessage(element, message, kind) {
    if (!element) return;
    element.textContent = message || "";
    element.className = "auth-message" + (kind ? " " + kind : "");
    element.hidden = !message;
  }

  function safeNext(fallback) {
    var value = new URLSearchParams(window.location.search).get("next") || "";
    if (!/^[a-z0-9][a-z0-9-]*\.html(?:[?#][^\s]*)?$/i.test(value)) return fallback;
    return value;
  }

  function destinationFor(user) {
    return user.role === "creator" ? "creator-dashboard.html" : "account.html";
  }

  async function initLogin() {
    var form = $("#login-form");
    var message = $("#auth-message");
    var button = $("#auth-submit");
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      setMessage(message, "", "");
      button.disabled = true;
      button.textContent = "Signing in…";
      try {
        var data = await request("/api/auth/login", {
          method: "POST",
          body: JSON.stringify({
            email: $("#email").value.trim(),
            password: $("#password").value
          })
        });
        window.location.assign(safeNext(destinationFor(data.user)));
      } catch (error) {
        setMessage(message, error.message, "error");
        button.disabled = false;
        button.textContent = "Sign in";
      }
    });
  }

  function initSignup() {
    var form = $("#signup-form");
    var message = $("#auth-message");
    var button = $("#auth-submit");
    var accountType = "user";
    document.querySelectorAll("[data-account-type]").forEach(function (choice) {
      choice.addEventListener("click", function () {
        accountType = choice.dataset.accountType;
        document.querySelectorAll("[data-account-type]").forEach(function (other) {
          other.setAttribute("aria-pressed", String(other === choice));
        });
        $("#account-type").value = accountType;
      });
    });

    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      setMessage(message, "", "");
      var password = $("#password").value;
      if (password.length < 8) {
        setMessage(message, "Use at least 8 characters for your password.", "error");
        return;
      }
      button.disabled = true;
      button.textContent = "Creating account…";
      try {
        var data = await request("/api/auth/signup", {
          method: "POST",
          body: JSON.stringify({
            display_name: $("#display-name").value.trim(),
            email: $("#email").value.trim(),
            password: password,
            account_type: accountType
          })
        });
        window.location.assign(destinationFor(data.user));
      } catch (error) {
        setMessage(message, error.message, "error");
        button.disabled = false;
        button.textContent = "Create account";
      }
    });
  }

  function formatDuration(seconds) {
    var value = Math.max(0, Number(seconds) || 0);
    var minutes = Math.floor(value / 60);
    var remainder = value % 60;
    return minutes + ":" + String(remainder).padStart(2, "0");
  }

  function formatDate(value) {
    if (!value) return "Just now";
    return new Date(value).toLocaleString([], {
      month: "short", day: "numeric", hour: "numeric", minute: "2-digit"
    });
  }

  function callReceipt(call, creatorView) {
    var item = document.createElement("li");
    item.className = "call-receipt";
    var avatar = document.createElement("span");
    avatar.className = "receipt-avatar";
    var label = creatorView ? (call.caller_name || "Guest") : (call.influencer_name || "TAC creator");
    avatar.textContent = label.trim().charAt(0).toUpperCase() || "T";
    var copy = document.createElement("div");
    var title = document.createElement("strong");
    title.textContent = label;
    var meta = document.createElement("span");
    meta.textContent = formatDate(call.started_at) + " · " + formatDuration(call.duration_seconds);
    copy.append(title, meta);
    var status = document.createElement("span");
    status.className = "receipt-status " + (call.status === "failed" ? "failed" : "");
    status.textContent = call.status === "failed" ? "Dropped" : "Finished";
    item.append(avatar, copy, status);
    return item;
  }

  function wireLogout() {
    var button = $("#logout-button");
    if (!button) return;
    button.addEventListener("click", async function () {
      button.disabled = true;
      try { await request("/api/auth/logout", { method: "POST", body: "{}" }); } catch (error) { /* clear locally anyway */ }
      window.location.assign("index.html");
    });
  }

  async function initAccount() {
    var loading = $("#account-loading");
    try {
      var data = await request("/api/auth/me", { method: "GET", headers: {} });
      $("#account-name").textContent = data.user.display_name;
      $("#account-email").textContent = data.user.email;
      $("#account-avatar").textContent = data.user.display_name.charAt(0).toUpperCase();
      $("#display-name").value = data.user.display_name;
      if (data.user.role === "creator") {
        $("#creator-dashboard-link").hidden = false;
      }
      var list = $("#account-calls");
      list.innerHTML = "";
      if (!data.recent_calls.length) {
        $("#account-empty").hidden = false;
      } else {
        data.recent_calls.forEach(function (call) { list.appendChild(callReceipt(call, false)); });
      }
      loading.hidden = true;
      $("#account-content").hidden = false;
    } catch (error) {
      if (error.status === 401) {
        window.location.replace("login.html?next=account.html");
        return;
      }
      loading.textContent = error.message;
    }

    $("#account-form").addEventListener("submit", async function (event) {
      event.preventDefault();
      var message = $("#account-message");
      try {
        var result = await request("/api/auth/me", {
          method: "PATCH",
          body: JSON.stringify({ display_name: $("#display-name").value.trim() })
        });
        $("#account-name").textContent = result.user.display_name;
        $("#account-avatar").textContent = result.user.display_name.charAt(0).toUpperCase();
        setMessage(message, "Name updated.", "success");
      } catch (error) {
        setMessage(message, error.message, "error");
      }
    });
    wireLogout();
  }

  function updateCreatorPreview(profile) {
    $("#preview-name").textContent = profile.name || "Your name";
    $("#preview-tagline").textContent = profile.tagline || "Add a short reason to call you.";
    $("#preview-avatar").textContent = (profile.name || "T").charAt(0).toUpperCase();
    $("#preview-avatar").style.backgroundImage = profile.avatar_url ? "url(\"" + profile.avatar_url.replace(/\"/g, "%22") + "\")" : "";
    var previewLabel = "Private draft";
    if (profile.is_published) previewLabel = "Live on TAC";
    else if (profile.review_status === "pending") previewLabel = "Under review";
    else if (profile.review_status === "rejected") previewLabel = "Needs changes";
    else if (profile.review_status === "approved") previewLabel = "Approved · private";
    $("#preview-status").textContent = previewLabel;
    $("#preview-status").className = "preview-status " + (profile.is_published ? "live" : "");
    $("#view-public-profile").hidden = !profile.is_published;
    $("#view-public-profile").href = "influencer.html?id=" + encodeURIComponent(profile.id);
  }

  function setCreatorAction(profile) {
    var button = $("#publish-button");
    button.disabled = false;
    button.dataset.published = String(profile.is_published);
    button.dataset.reviewStatus = profile.review_status;
    if (profile.review_status === "pending") {
      button.textContent = "Review pending";
      button.disabled = true;
    } else if (profile.review_status === "approved") {
      button.textContent = profile.is_published ? "Unpublish profile" : "Publish profile";
    } else {
      button.textContent = profile.review_status === "rejected" ? "Resubmit for review" : "Submit for review";
    }
  }

  function setVoiceBooth(profile) {
    var booth = $(".voice-booth");
    var state = $("#voice-state");
    var locked = $("#voice-locked");
    var button = $("#voice-clone-button");
    if (!booth || !state || !profile.voice) return;

    state.className = "voice-state";
    if (profile.voice.status === "custom") {
      state.textContent = "Your voice active · …" + profile.voice.id_suffix;
      state.classList.add("active");
      button.textContent = "Replace my voice";
    } else if (profile.voice.status === "default") {
      state.textContent = "House voice active";
      button.textContent = "Create my voice";
    } else {
      state.textContent = "Voice unavailable";
      button.textContent = "Create my voice";
    }

    var canClone = Boolean(profile.voice.clone_available);
    booth.classList.toggle("is-locked", !canClone);
    locked.hidden = canClone;
    booth.querySelectorAll("input, select").forEach(function (control) {
      control.disabled = !canClone;
    });
    button.disabled = !canClone;
    if (!canClone) {
      var title = locked.querySelector("strong");
      var copy = locked.querySelector("span");
      if (profile.review_status === "approved") {
        title.textContent = "Voice cloning is temporarily unavailable.";
        copy.textContent = "Your active voice is unchanged. TAC needs the voice provider enabled before you can create or replace it.";
      } else {
        title.textContent = "Voice cloning unlocks after identity review.";
        copy.textContent = "Finish your profile and submit it for review. This protects creators from unauthorised impersonation.";
      }
    }
  }

  function renderCreator(data) {
    var profile = data.profile;
    var analytics = data.analytics;
    $("#creator-greeting").textContent = "Hi, " + data.user.display_name.split(/\s+/)[0] + ".";
    $("#creator-email").textContent = data.user.email;
    $("#profile-name-input").value = profile.name;
    $("#profile-tagline-input").value = profile.tagline;
    $("#profile-bio-input").value = profile.bio;
    $("#profile-avatar-input").value = profile.avatar_url;
    $("#profile-prompt-input").value = profile.system_prompt;
    $("#profile-language-input").value = profile.primary_language || "en";
    document.querySelectorAll("input[name='profile-language']").forEach(function (input) {
      input.checked = (profile.supported_languages || [profile.primary_language || "en"]).includes(input.value);
    });
    $("#voice-language").value = profile.primary_language || "en";
    $("#stat-calls").textContent = String(analytics.total_calls);
    $("#stat-minutes").textContent = String(Math.ceil(analytics.total_seconds / 60));
    $("#stat-finished").textContent = analytics.total_calls
      ? Math.round((analytics.completed_calls / analytics.total_calls) * 100) + "%"
      : "—";
    setCreatorAction(profile);
    setVoiceBooth(profile);
    updateCreatorPreview(profile);
    var list = $("#creator-calls");
    list.innerHTML = "";
    if (!analytics.recent_calls.length) {
      $("#creator-empty").hidden = false;
    } else {
      $("#creator-empty").hidden = true;
      analytics.recent_calls.forEach(function (call) { list.appendChild(callReceipt(call, true)); });
    }
  }

  async function initCreator() {
    var data;
    try {
      data = await request("/api/creator/dashboard", { method: "GET", headers: {} });
      renderCreator(data);
      $("#creator-loading").hidden = true;
      $("#creator-content").hidden = false;
    } catch (error) {
      if (error.status === 401) {
        window.location.replace("login.html?next=creator-dashboard.html");
        return;
      }
      if (error.status === 403) {
        window.location.replace("account.html");
        return;
      }
      $("#creator-loading").textContent = error.message;
      return;
    }

    ["#profile-name-input", "#profile-tagline-input", "#profile-bio-input", "#profile-avatar-input"].forEach(function (selector) {
      $(selector).addEventListener("input", function () {
        updateCreatorPreview({
          id: data.profile.id,
          name: $("#profile-name-input").value.trim(),
          tagline: $("#profile-tagline-input").value.trim(),
          avatar_url: $("#profile-avatar-input").value.trim(),
          is_published: data.profile.is_published
        });
      });
    });

    var voiceFile = $("#voice-clip");
    var voicePreview = $("#voice-clip-preview");
    var voiceRights = $("#voice-rights");
    var voiceSynthetic = $("#voice-synthetic");
    var voiceButton = $("#voice-clone-button");
    var voiceStatus = $("#voice-clone-status");
    var voiceObjectUrl = "";

    $("#profile-language-input").addEventListener("change", function () {
      var matching = document.querySelector("input[name='profile-language'][value='" + this.value + "']");
      if (matching) matching.checked = true;
    });

    function refreshVoiceButton() {
      var canClone = Boolean(data.profile.voice && data.profile.voice.clone_available);
      voiceButton.disabled = !canClone || !voiceFile.files.length || !voiceRights.checked || !voiceSynthetic.checked;
    }

    voiceFile.addEventListener("change", function () {
      if (voiceObjectUrl) URL.revokeObjectURL(voiceObjectUrl);
      var file = voiceFile.files && voiceFile.files[0];
      $("#voice-file-name").textContent = file ? file.name : "Choose WAV, MP3, M4A, FLAC, OGG or WebM";
      if (file) {
        voiceObjectUrl = URL.createObjectURL(file);
        voicePreview.src = voiceObjectUrl;
        voicePreview.hidden = false;
      } else {
        voicePreview.removeAttribute("src");
        voicePreview.hidden = true;
      }
      refreshVoiceButton();
    });
    voiceRights.addEventListener("change", refreshVoiceButton);
    voiceSynthetic.addEventListener("change", refreshVoiceButton);
    refreshVoiceButton();

    $("#voice-clone-form").addEventListener("submit", async function (event) {
      event.preventDefault();
      var file = voiceFile.files && voiceFile.files[0];
      if (!file || !voiceRights.checked || !voiceSynthetic.checked) return;
      if (file.size > 20 * 1024 * 1024) {
        voiceStatus.textContent = "Choose an audio file smaller than 20 MB.";
        voiceStatus.className = "error";
        return;
      }

      voiceButton.disabled = true;
      voiceButton.textContent = "Creating voice…";
      voiceStatus.textContent = "Sending this take securely to the voice provider. Keep this page open.";
      voiceStatus.className = "";
      var form = new FormData();
      form.append("clip", file);
      form.append("language", $("#voice-language").value);
      form.append("rights_confirmed", "true");
      form.append("synthetic_acknowledged", "true");

      try {
        var response = await fetch("/api/creator/voice/clone", {
          method: "POST",
          credentials: "same-origin",
          body: form
        });
        var result = {};
        try { result = await response.json(); } catch (error) { /* empty response */ }
        if (!response.ok) {
          var cloneError = new Error(result.detail || "Voice cloning failed.");
          cloneError.status = response.status;
          throw cloneError;
        }
        data.profile = result.profile;
        setVoiceBooth(data.profile);
        voiceStatus.textContent = result.message;
        voiceStatus.className = "success";
      } catch (error) {
        if (error.status === 401) {
          window.location.replace("login.html?next=creator-dashboard.html");
          return;
        }
        voiceStatus.textContent = error.message;
        voiceStatus.className = "error";
      } finally {
        setVoiceBooth(data.profile);
        refreshVoiceButton();
      }
    });

    $("#creator-profile-form").addEventListener("submit", async function (event) {
      event.preventDefault();
      var button = $("#save-profile");
      var message = $("#creator-message");
      button.disabled = true;
      button.textContent = "Saving…";
      try {
        var result = await request("/api/creator/profile", {
          method: "PUT",
          body: JSON.stringify({
            name: $("#profile-name-input").value.trim(),
            tagline: $("#profile-tagline-input").value.trim(),
            bio: $("#profile-bio-input").value.trim(),
            avatar_url: $("#profile-avatar-input").value.trim(),
            system_prompt: $("#profile-prompt-input").value.trim(),
            primary_language: $("#profile-language-input").value,
            supported_languages: Array.from(document.querySelectorAll("input[name='profile-language']:checked")).map(function (input) { return input.value; })
          })
        });
        data.profile = result.profile;
        updateCreatorPreview(data.profile);
        setMessage(message, "Profile saved.", "success");
      } catch (error) {
        setMessage(message, error.message, "error");
      } finally {
        button.disabled = false;
        button.textContent = "Save changes";
      }
    });

    $("#publish-button").addEventListener("click", async function () {
      var button = $("#publish-button");
      var message = $("#creator-message");
      button.disabled = true;
      try {
        var result;
        if (button.dataset.reviewStatus !== "approved") {
          result = await request("/api/creator/review", {
            method: "POST",
            body: "{}"
          });
        } else {
          result = await request("/api/creator/publish", {
            method: "PATCH",
            body: JSON.stringify({ is_published: button.dataset.published !== "true" })
          });
        }
        data.profile = result.profile;
        setCreatorAction(result.profile);
        setVoiceBooth(result.profile);
        updateCreatorPreview(result.profile);
        var resultMessage = result.profile.is_published ? "Your profile is live." : "Your profile is now private.";
        if (result.profile.review_status === "pending") resultMessage = "Profile sent for identity and safety review.";
        setMessage(message, resultMessage, "success");
      } catch (error) {
        setMessage(message, error.message, "error");
      } finally {
        if (data.profile.review_status !== "pending") button.disabled = false;
      }
    });
    wireLogout();
  }

  if (page === "login") initLogin();
  if (page === "signup") initSignup();
  if (page === "account") initAccount();
  if (page === "creator") initCreator();
})();
