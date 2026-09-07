(function () {
  "use strict";
  function $(selector, root) { return (root || document).querySelector(selector); }
  function $$(selector, root) { return Array.from((root || document).querySelectorAll(selector)); }
  async function fetchJSON(url, options) {
    var response = await fetch(url, options || {});
    var data = {};
    try { data = await response.json(); } catch (error) { /* empty response */ }
    if (!response.ok) throw new Error(data.detail || "Request failed. Please try again.");
    return data;
  }
  function initForms() {
    $$(".public-submission-form").forEach(function (form) {
      form.addEventListener("submit", async function (event) {
        event.preventDefault();
        var button = $("button[type=submit]", form);
        var result = $(".form-result", form);
        var data = new FormData(form);
        var payload = {
          kind: form.dataset.kind,
          name: String(data.get("name") || "").trim(),
          email: String(data.get("email") || "").trim(),
          phone: String(data.get("phone") || "").trim(),
          subject: String(data.get("subject") || "").trim(),
          message: String(data.get("message") || "").trim(),
          metadata: { page: window.location.pathname }
        };
        $$("[data-meta]", form).forEach(function (field) { payload.metadata[field.dataset.meta] = String(data.get(field.name) || "").trim(); });
        button.disabled = true;
        result.className = "form-result";
        result.textContent = "Sending…";
        try {
          var response = await fetchJSON("/api/public-submissions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
          form.reset();
          result.className = "form-result success";
          result.textContent = "Received — reference #" + response.request_id + ". We’ll review it.";
        } catch (error) {
          result.className = "form-result error";
          result.textContent = error.message;
        } finally { button.disabled = false; }
      });
    });
  }
  async function initStatus() {
    if (!$("#live-status")) return;
    var api = $("#api-status");
    var calls = $("#call-status");
    try {
      var responses = await Promise.all([fetchJSON("/health", { cache: "no-store" }), fetchJSON("/info", { cache: "no-store" })]);
      api.className = "status-pill up";
      api.textContent = responses[0].ok ? "Operational" : "Degraded";
      calls.className = "status-pill " + (responses[1].web_calls_configured ? "up" : "paused");
      calls.textContent = responses[1].web_calls_configured ? "Available" : "Paused";
      $("#status-updated").textContent = "Checked just now";
    } catch (error) {
      api.className = "status-pill down"; api.textContent = "Unavailable";
      calls.className = "status-pill paused"; calls.textContent = "Unknown";
      $("#status-updated").textContent = "Could not reach the service";
    }
  }
  function initCallState() {
    var params = new URLSearchParams(window.location.search);
    var creator = String(params.get("creator") || "your creator").slice(0, 80);
    var nameTarget = $("[data-creator-name]");
    if (nameTarget) nameTarget.textContent = creator;
    var completeLink = $("[data-complete-link]");
    if (completeLink) completeLink.href = "call-complete.html?creator=" + encodeURIComponent(creator);
    if (document.body.dataset.publicPage === "call-complete") {
      $$("[data-rating]").forEach(function (button) {
        button.addEventListener("click", function () {
          $$("[data-rating]").forEach(function (other) { other.setAttribute("aria-pressed", String(other === button)); });
          var subject = $("#feedback-subject");
          if (subject) subject.value = button.dataset.rating + " / 5";
        });
      });
    }
  }
  function boot() { initForms(); initStatus(); initCallState(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
