(function () {
  "use strict";

  var TOKEN_KEY = "tac_admin_token";
  var state = { creators: [], users: [], calls: [], submissions: [], events: [], languages: [], overview: null, creatorFilter: "all", topics: [], knowledge: [] };
  var $ = function (selector, root) { return (root || document).querySelector(selector); };
  var $$ = function (selector, root) { return Array.from((root || document).querySelectorAll(selector)); };

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (character) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character];
    });
  }

  function token() { try { return localStorage.getItem(TOKEN_KEY) || ""; } catch (error) { return ""; } }
  function saveToken(value) { try { localStorage.setItem(TOKEN_KEY, value); } catch (error) { /* storage disabled */ } }
  function clearToken() { try { localStorage.removeItem(TOKEN_KEY); } catch (error) { /* storage disabled */ } }

  async function request(path, options) {
    var settings = Object.assign({}, options || {});
    settings.headers = Object.assign({}, settings.headers || {}, { Authorization: "Bearer " + token() });
    if (settings.body && !(settings.body instanceof FormData)) settings.headers["Content-Type"] = "application/json";
    var response = await fetch(path, settings);
    var data = {};
    try { data = await response.json(); } catch (error) { /* empty */ }
    if (!response.ok) {
      var message = typeof data.detail === "string" ? data.detail : "Studio request failed.";
      var problem = new Error(message); problem.status = response.status; throw problem;
    }
    return data;
  }

  function initials(name) {
    return String(name || "T").trim().split(/\s+/).slice(0, 2).map(function (part) { return part.charAt(0); }).join("").toUpperCase();
  }
  function formatDuration(seconds) {
    var value = Math.max(0, Number(seconds) || 0);
    return Math.floor(value / 60) + "m " + (value % 60) + "s";
  }
  function formatDate(value) {
    if (!value) return "—";
    return new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }
  function languageName(code) {
    var found = state.languages.find(function (language) { return language.code === code; });
    return found ? found.name : String(code || "—").toUpperCase();
  }
  function chip(value) { return '<span class="status-chip ' + esc(value) + '">' + esc(String(value || "unknown").replace(/_/g, " ")) + '</span>'; }
  function avatar(creator) {
    var style = creator.avatar_url ? ' style="background-image:url(\'' + esc(creator.avatar_url).replace(/'/g, "%27") + '\')"' : "";
    return '<span class="studio-avatar"' + style + '>' + (creator.avatar_url ? "" : esc(initials(creator.name))) + '</span>';
  }

  function selectTab(name) {
    if (!$("[data-panel='" + name + "']")) name = "overview";
    $$('[data-studio-tab]').forEach(function (button) { button.classList.toggle("active", button.dataset.studioTab === name); });
    $$('[data-panel]').forEach(function (panel) { panel.classList.toggle("active", panel.dataset.panel === name); });
    $("#studio-nav").classList.remove("open");
    $("#studio-menu").setAttribute("aria-expanded", "false");
    history.replaceState(null, "", "#" + name);
    window.scrollTo(0, 0);
    if (name === "knowledge") loadKnowledge().catch(showLoadError);
  }

  function renderOverview() {
    var summary = state.overview.summary;
    var needs = [];
    if (summary.pending_reviews) needs.push("<strong>" + summary.pending_reviews + " creator review" + (summary.pending_reviews === 1 ? "" : "s") + "</strong>");
    if (summary.open_submissions) needs.push("<strong>" + summary.open_submissions + " new inbox item" + (summary.open_submissions === 1 ? "" : "s") + "</strong>");
    $("#attention-strip").innerHTML = needs.length ? "<p>Today needs " + needs.join(" and ") + ".</p><button class='row-button primary' data-jump='inbox'>Open queue</button>" : "<p><strong>The queue is clear.</strong> No creator reviews or new inbox items need action.</p>";
    var stats = [
      ["Creators", summary.creators, summary.published + " live"],
      ["Conversations", summary.calls, formatDuration(summary.seconds) + " total"],
      ["People", summary.users, "registered accounts"],
      ["Open inbox", summary.open_submissions, summary.pending_reviews + " creator reviews"]
    ];
    $("#studio-stats").innerHTML = stats.map(function (item) { return '<article class="studio-stat"><span>' + esc(item[0]) + '</span><strong>' + esc(item[1]) + '</strong><small>' + esc(item[2]) + '</small></article>'; }).join("");
    var pending = state.creators.filter(function (creator) { return creator.review_status === "pending"; }).slice(0, 5);
    $("#overview-reviews").innerHTML = pending.length ? pending.map(function (creator) { return '<article class="studio-list-item">' + avatar(creator) + '<div><strong>' + esc(creator.name) + '</strong><span>' + esc(creator.owner_email || "Operator-created profile") + '</span></div>' + chip("pending") + '</article>'; }).join("") : '<p class="empty-note">No creator profiles are waiting.</p>';
    $("#overview-calls").innerHTML = state.calls.slice(0, 5).map(function (call) { return '<article class="studio-list-item"><span class="studio-avatar">↗</span><div><strong>' + esc(call.influencer_name || "Deleted creator") + '</strong><span>' + esc(formatDuration(call.duration_seconds)) + ' · ' + esc(formatDate(call.started_at)) + '</span></div>' + chip(call.status) + '</article>'; }).join("") || '<p class="empty-note">No calls have been recorded.</p>';
  }

  function creatorVisible(creator) {
    var query = $("#creator-search").value.trim().toLowerCase();
    var matchesSearch = !query || [creator.name, creator.owner_email, creator.tagline].join(" ").toLowerCase().includes(query);
    var filter = state.creatorFilter;
    var matchesFilter = filter === "all" || (filter === "pending" && creator.review_status === "pending") || (filter === "live" && creator.is_published && creator.call_enabled) || (filter === "paused" && (!creator.call_enabled || !creator.is_published));
    return matchesSearch && matchesFilter;
  }

  function renderCreators() {
    var rows = state.creators.filter(creatorVisible);
    $("#creator-rows").innerHTML = rows.map(function (creator) {
      var voice = creator.voice_id ? "Custom · " + creator.voice_id.slice(-8) : "House voice";
      var status = creator.is_published ? (creator.call_enabled ? "live" : "paused") : creator.review_status;
      return '<tr><td><div class="row-person">' + avatar(creator) + '<div><strong>' + esc(creator.name) + '</strong><small>' + esc(creator.owner_email || creator.tagline || "Operator-created") + '</small></div></div></td><td><strong>' + esc(languageName(creator.primary_language)) + '</strong><small>' + esc((creator.supported_languages || []).map(languageName).join(", ")) + '</small></td><td><strong>' + esc(voice) + '</strong><small>' + esc(formatDuration(creator.max_call_seconds)) + ' max</small></td><td><strong>' + esc(creator.total_calls || 0) + '</strong><small>' + esc(formatDuration(creator.total_seconds)) + '</small></td><td>' + chip(status) + '</td><td><div class="row-actions"><button class="row-button" data-edit-creator="' + creator.id + '">Edit</button><button class="row-button primary" data-upload-voice="' + creator.id + '">Voice</button></div></td></tr>';
    }).join("") || '<tr><td colspan="6"><p class="empty-note">No creators match this view.</p></td></tr>';
  }

  function renderVoices() {
    $("#language-legend").textContent = state.languages.length + " supported profile and voice languages · creator primary language drives live TTS";
    $("#voice-grid").innerHTML = state.creators.map(function (creator) {
      var tags = (creator.supported_languages || [creator.primary_language]).map(function (code) { return '<span class="language-tag">' + esc(languageName(code)) + '</span>'; }).join("");
      return '<article class="voice-card"><div class="voice-card-top">' + avatar(creator) + chip(creator.voice_id ? "active" : "house voice") + '</div><h2>' + esc(creator.name) + '</h2><p>' + (creator.voice_id ? 'Custom voice ending ·' + esc(creator.voice_id.slice(-8)) : 'Using the platform house voice') + '</p><div class="language-tags">' + tags + '</div><button class="button button-primary" type="button" data-upload-voice="' + creator.id + '">' + (creator.voice_id ? "Replace voice" : "Upload voice") + '</button></article>';
    }).join("") || '<p class="empty-note">Add a creator before uploading a voice.</p>';
  }

  function renderUsers() {
    $("#user-rows").innerHTML = state.users.map(function (user) {
      return '<tr><td><strong>' + esc(user.display_name) + '</strong><small>' + esc(user.email) + '</small></td><td>' + chip(user.role) + '</td><td>' + esc(user.total_calls || 0) + '</td><td>' + (user.influencer_id ? '<button class="row-button" data-edit-creator="' + user.influencer_id + '">Open profile</button>' : '—') + '</td><td>' + chip(user.is_active ? "active" : "suspended") + '</td><td><div class="row-actions"><button class="row-button" data-user-role="' + user.id + '">' + (user.role === "creator" ? "Make fan" : "Make creator") + '</button><button class="row-button" data-user-toggle="' + user.id + '">' + (user.is_active ? "Suspend" : "Restore") + '</button></div></td></tr>';
    }).join("") || '<tr><td colspan="6"><p class="empty-note">No accounts yet.</p></td></tr>';
  }

  function renderCalls() {
    $("#call-rows").innerHTML = state.calls.map(function (call) {
      return '<tr><td><strong>' + esc(formatDate(call.started_at)) + '</strong><small>#' + esc(call.id) + '</small></td><td>' + esc(call.influencer_name || "Deleted creator") + '</td><td><strong>' + esc(call.caller_name || "Guest") + '</strong><small>' + esc(call.user_email || "No account") + '</small></td><td>' + esc(formatDuration(call.duration_seconds)) + '</td><td>' + chip(call.status) + '</td><td><small title="' + esc(call.error) + '">' + esc(call.error ? call.error.slice(0, 90) : "—") + '</small></td></tr>';
    }).join("") || '<tr><td colspan="6"><p class="empty-note">No calls recorded.</p></td></tr>';
  }

  function renderInbox() {
    $("#inbox-grid").innerHTML = state.submissions.map(function (item) {
      var safety = item.kind === "report" ? " safety" : "";
      return '<article class="inbox-card' + safety + '"><div><strong>' + esc(item.kind.replace(/_/g, " ")) + '</strong><small>' + esc(formatDate(item.created_at)) + '</small>' + chip(item.status) + '</div><div><strong>' + esc(item.subject || item.name || "No subject") + '</strong><small>' + esc(item.email || item.phone || "No contact") + '</small><p>' + esc(item.message) + '</p></div><div class="inbox-actions"><button class="row-button" data-submission="' + item.id + '" data-status="in_progress">Claim</button><button class="row-button primary" data-submission="' + item.id + '" data-status="resolved">Resolve</button><button class="row-button" data-submission="' + item.id + '" data-status="spam">Spam</button></div></article>';
    }).join("") || '<p class="empty-note">The inbox is clear.</p>';
  }

  function renderAudit() {
    $("#audit-list").innerHTML = state.events.map(function (event) { return '<article class="audit-row"><time>' + esc(formatDate(event.created_at)) + '</time><strong>' + esc(event.action.replace(/\./g, " ")) + '</strong><div><span>' + esc(event.entity_type) + ' #' + esc(event.entity_id) + '</span><p>' + esc(event.summary) + '</p></div></article>'; }).join("") || '<p class="empty-note">No Studio changes recorded yet.</p>';
  }

  function renderKnowledgePicker() {
    var select = $("#knowledge-creator");
    var previous = select.value;
    select.innerHTML = state.creators.map(function (creator) { return '<option value="' + creator.id + '">' + esc(creator.name) + '</option>'; }).join("");
    if (previous && state.creators.some(function (creator) { return String(creator.id) === previous; })) select.value = previous;
    $("#knowledge-language").innerHTML = languageOptions("en");
  }

  function renderKnowledge() {
    $("#topic-list").innerHTML = state.topics.map(function (topic) { return '<article class="knowledge-item"><div><strong>' + esc(topic.name) + '</strong><span>' + esc(topic.description || "No description") + '</span></div><button class="row-button" data-delete-topic="' + topic.id + '">Remove</button></article>'; }).join("") || '<p class="empty-note">No topics yet. Add the areas this creator should discuss.</p>';
    $("#knowledge-list").innerHTML = state.knowledge.map(function (item) { return '<article class="knowledge-item"><div><strong>' + esc(item.title) + '</strong><span>' + esc(languageName(item.language)) + '</span><p>' + esc(item.content.slice(0, 260)) + (item.content.length > 260 ? '…' : '') + '</p></div><button class="row-button" data-delete-knowledge="' + item.id + '">Remove</button></article>'; }).join("") || '<p class="empty-note">No reference notes yet. Calls currently rely on the profile guide alone.</p>';
  }

  async function loadKnowledge() {
    var creatorId = $("#knowledge-creator").value;
    if (!creatorId) { state.topics = []; state.knowledge = []; renderKnowledge(); return; }
    var data = await request("/api/admin/creators/" + creatorId + "/knowledge");
    state.topics = data.topics || []; state.knowledge = data.knowledge || []; renderKnowledge();
  }

  function renderAll() { renderOverview(); renderCreators(); renderVoices(); renderUsers(); renderCalls(); renderInbox(); renderAudit(); renderKnowledgePicker(); }

  async function loadAll() {
    var results = await Promise.all([
      request("/api/admin/overview"), request("/api/admin/languages"), request("/api/admin/creators"),
      request("/api/admin/users"), request("/api/admin/calls"), request("/api/admin/submissions"), request("/api/admin/audit-log")
    ]);
    state.overview = results[0]; state.languages = results[1].languages || []; state.creators = results[2].creators || [];
    state.users = results[3].users || []; state.calls = results[4].calls || []; state.submissions = results[5].submissions || []; state.events = results[6].events || [];
    $("#studio-live").classList.remove("down"); $("#studio-live span").textContent = "Voice service online";
    renderAll();
  }

  function languageOptions(selected) { return state.languages.map(function (language) { return '<option value="' + esc(language.code) + '"' + (language.code === selected ? " selected" : "") + '>' + esc(language.name) + '</option>'; }).join(""); }
  function languageChecks(selected) { return state.languages.map(function (language) { return '<label><input type="checkbox" value="' + esc(language.code) + '"' + (selected.includes(language.code) ? " checked" : "") + '><span>' + esc(language.name) + '</span></label>'; }).join(""); }

  function openCreator(id) {
    var creator = state.creators.find(function (item) { return item.id === Number(id); });
    var isNew = !creator;
    creator = creator || { id: "", name: "", tagline: "", bio: "", avatar_url: "", system_prompt: "", primary_language: "en", supported_languages: ["en"], call_enabled: true, max_call_seconds: 300, price_per_minute_paise: 0, is_published: false, review_status: "pending" };
    $("#creator-dialog-title").textContent = isNew ? "Add creator" : "Edit " + creator.name;
    $("#edit-creator-id").value = creator.id; $("#edit-name").value = creator.name; $("#edit-tagline").value = creator.tagline; $("#edit-bio").value = creator.bio;
    $("#edit-avatar").value = creator.avatar_url; $("#edit-prompt").value = creator.system_prompt; $("#edit-primary-language").innerHTML = languageOptions(creator.primary_language);
    $("#edit-languages").innerHTML = languageChecks(creator.supported_languages || [creator.primary_language]); $("#edit-call-limit").value = String(creator.max_call_seconds);
    $("#edit-price").value = String((Number(creator.price_per_minute_paise) || 0) / 100); $("#edit-review").value = creator.review_status;
    $("#edit-call-enabled").checked = Boolean(creator.call_enabled); $("#edit-published").checked = Boolean(creator.is_published); $("#creator-form-message").textContent = "";
    $("#creator-dialog").showModal();
  }

  function openVoice(id) {
    var creator = state.creators.find(function (item) { return item.id === Number(id); }); if (!creator) return;
    $("#voice-creator-id").value = creator.id; $("#voice-dialog-title").textContent = "Voice for " + creator.name;
    $("#voice-language").innerHTML = languageOptions(creator.primary_language); $("#voice-clip").value = ""; $("#voice-rights").checked = false; $("#voice-disclosure").checked = false; $("#voice-form-message").textContent = "";
    $("#voice-dialog").showModal();
  }

  async function saveCreator(event) {
    event.preventDefault();
    var selectedLanguages = $$("#edit-languages input:checked").map(function (input) { return input.value; });
    var payload = { name: $("#edit-name").value.trim(), tagline: $("#edit-tagline").value.trim(), bio: $("#edit-bio").value.trim(), avatar_url: $("#edit-avatar").value.trim(), system_prompt: $("#edit-prompt").value.trim(), primary_language: $("#edit-primary-language").value, supported_languages: selectedLanguages, call_enabled: $("#edit-call-enabled").checked, max_call_seconds: Number($("#edit-call-limit").value), price_per_minute_paise: Math.round(Number($("#edit-price").value || 0) * 100), is_published: $("#edit-published").checked, review_status: $("#edit-review").value };
    var id = $("#edit-creator-id").value; var button = $("#creator-form button[type='submit']"); button.disabled = true;
    try { await request(id ? "/api/admin/creators/" + id : "/api/admin/creators", { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) }); $("#creator-dialog").close(); await loadAll(); }
    catch (error) { $("#creator-form-message").textContent = error.message; }
    finally { button.disabled = false; }
  }

  async function uploadVoice(event) {
    event.preventDefault(); var file = $("#voice-clip").files[0];
    if (!file || !$("#voice-rights").checked || !$("#voice-disclosure").checked) { $("#voice-form-message").textContent = "Choose a sample and confirm both permissions."; return; }
    var form = new FormData(); form.append("clip", file); form.append("language", $("#voice-language").value); form.append("rights_confirmed", "true"); form.append("synthetic_acknowledged", "true");
    var button = $("#voice-form button[type='submit']"); button.disabled = true; button.textContent = "Creating voice…";
    try { await request("/api/admin/creators/" + $("#voice-creator-id").value + "/voice", { method: "POST", body: form }); $("#voice-dialog").close(); await loadAll(); }
    catch (error) { $("#voice-form-message").textContent = error.message; }
    finally { button.disabled = false; button.textContent = "Create and activate voice"; }
  }

  async function updateUser(id, changes) {
    var user = state.users.find(function (item) { return item.id === Number(id); }); if (!user) return;
    await request("/api/admin/users/" + id, { method: "PATCH", body: JSON.stringify({ role: changes.role || user.role, is_active: changes.is_active == null ? user.is_active : changes.is_active }) }); await loadAll();
  }
  async function updateSubmission(id, status) { await request("/api/admin/submissions/" + id, { method: "PATCH", body: JSON.stringify({ status: status }) }); await loadAll(); }

  document.addEventListener("click", function (event) {
    var tab = event.target.closest("[data-studio-tab]"); if (tab) selectTab(tab.dataset.studioTab);
    var jump = event.target.closest("[data-jump]"); if (jump) selectTab(jump.dataset.jump);
    if (event.target.closest("[data-open-create]")) openCreator();
    var edit = event.target.closest("[data-edit-creator]"); if (edit) openCreator(edit.dataset.editCreator);
    var voice = event.target.closest("[data-upload-voice]"); if (voice) openVoice(voice.dataset.uploadVoice);
    var filter = event.target.closest("[data-creator-filter]"); if (filter) { state.creatorFilter = filter.dataset.creatorFilter; $$('[data-creator-filter]').forEach(function (button) { button.classList.toggle("active", button === filter); }); renderCreators(); }
    var userToggle = event.target.closest("[data-user-toggle]"); if (userToggle) { var user = state.users.find(function (item) { return item.id === Number(userToggle.dataset.userToggle); }); if (user) updateUser(user.id, { is_active: !user.is_active }).catch(showLoadError); }
    var userRole = event.target.closest("[data-user-role]"); if (userRole) { var roleUser = state.users.find(function (item) { return item.id === Number(userRole.dataset.userRole); }); if (roleUser) updateUser(roleUser.id, { role: roleUser.role === "creator" ? "user" : "creator" }).catch(showLoadError); }
    var submission = event.target.closest("[data-submission]"); if (submission) updateSubmission(submission.dataset.submission, submission.dataset.status).catch(showLoadError);
    var topicDelete = event.target.closest("[data-delete-topic]"); if (topicDelete) request("/api/admin/creators/" + $("#knowledge-creator").value + "/topics/" + topicDelete.dataset.deleteTopic, { method: "DELETE" }).then(loadKnowledge).catch(showLoadError);
    var knowledgeDelete = event.target.closest("[data-delete-knowledge]"); if (knowledgeDelete) request("/api/admin/creators/" + $("#knowledge-creator").value + "/knowledge/" + knowledgeDelete.dataset.deleteKnowledge, { method: "DELETE" }).then(loadKnowledge).catch(showLoadError);
    if (event.target.closest("[data-close-dialog]")) event.target.closest("dialog").close();
  });

  function showLoadError(error) { window.alert(error.message || "Studio action failed."); }
  $("#creator-search").addEventListener("input", renderCreators);
  $("#creator-form").addEventListener("submit", saveCreator);
  $("#voice-form").addEventListener("submit", uploadVoice);
  $("#knowledge-creator").addEventListener("change", function () { loadKnowledge().catch(showLoadError); });
  $("#topic-form").addEventListener("submit", async function (event) { event.preventDefault(); var id = $("#knowledge-creator").value; if (!id) return; try { await request("/api/admin/creators/" + id + "/topics", { method: "POST", body: JSON.stringify({ name: $("#topic-name").value.trim(), description: $("#topic-description").value.trim() }) }); event.target.reset(); await loadKnowledge(); } catch (error) { showLoadError(error); } });
  $("#knowledge-form").addEventListener("submit", async function (event) { event.preventDefault(); var id = $("#knowledge-creator").value; if (!id) return; var button = event.target.querySelector("button[type='submit']"); button.disabled = true; $("#knowledge-message").textContent = ""; try { await request("/api/admin/creators/" + id + "/knowledge", { method: "POST", body: JSON.stringify({ title: $("#knowledge-title").value.trim(), content: $("#knowledge-content").value.trim(), language: $("#knowledge-language").value }) }); event.target.reset(); $("#knowledge-language").innerHTML = languageOptions("en"); await loadKnowledge(); } catch (error) { $("#knowledge-message").textContent = error.message; } finally { button.disabled = false; } });
  $("#edit-primary-language").addEventListener("change", function () { var selected = $("#edit-languages input[value='" + this.value + "']"); if (selected) selected.checked = true; });
  $("#studio-menu").addEventListener("click", function () { var nav = $("#studio-nav"); var open = nav.classList.toggle("open"); this.setAttribute("aria-expanded", String(open)); });
  $("#studio-lock").addEventListener("click", function () { clearToken(); $("#studio-gate").hidden = false; $("#admin-token").value = ""; });
  $("#studio-login").addEventListener("submit", async function (event) { event.preventDefault(); saveToken($("#admin-token").value.trim()); $("#gate-message").textContent = "Checking token…"; try { await loadAll(); $("#studio-gate").hidden = true; $("#gate-message").textContent = ""; } catch (error) { clearToken(); $("#gate-message").textContent = error.message; } });

  if (token()) { loadAll().then(function () { $("#studio-gate").hidden = true; }).catch(function (error) { clearToken(); $("#gate-message").textContent = error.message; $("#studio-live").classList.add("down"); $("#studio-live span").textContent = "Studio locked"; }); }
  selectTab(location.hash.replace("#", "") || "overview");
})();
