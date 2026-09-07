# AGENTS.md — Project context for AI agents

Fast, accurate orientation for anyone (human or agent) working in this repo.
Read this first; dig into `app/` only where noted.

---

## 1. What this is

An **AI voice agent product**: fans pick an influencer persona on a website,
enter their phone number, and that influencer's **AI calls them** and holds a
natural spoken conversation. Lives at **https://tac.cytieq.com**.

- **Backend**: Python 3 / FastAPI + uvicorn. Real-time phone pipeline:
  **Twilio Media Streams** (audio) → **ElevenLabs Scribe Realtime** (STT) →
  **Groq** (LLM, streamed) → **Cartesia Sonic** (TTS, streamed) → back to Twilio.
- **Frontend**: static vanilla HTML/CSS/JS (no build step), served by Caddy.
- **Storage**: SQLite (influencer personas + call-request log). No external DB.
- **Deploy**: single GCP **e2-micro** VM (always-free tier), Caddy for
  auto-HTTPS + reverse proxy, systemd service. DNS on Cloudflare.
- **Status**: deployed and working end-to-end except **API keys are empty** —
  the web UI, APIs, and persona plumbing all work; real calls need keys (see §9).

---

## 2. Repo layout

```
influencer-ai-voice-agent/
├── app/
│   ├── main.py                 # FastAPI app: lifespan (DB init+seed), routers, /health, /info, /twilio/media-stream WS
│   ├── api/
│   │   ├── twilio_routes.py    # /twilio/voice (TwiML), /twilio/make-call (test call)
│   │   └── influencers.py      # /api/influencers CRUD, /api/call-requests, /api/call-requests (admin)
│   ├── telephony/
│   │   ├── twilio_voice_agent.py   # the voice agent: Groq→Cartesia→Twilio streaming, barge-in, persona prompts
│   │   ├── twilio_media.py         # WS handler: connects ElevenLabs, forwards audio, wires everything
│   │   └── twilio_audio_sender.py  # sends μ-law audio chunks + playback marks to Twilio
│   ├── providers/
│   │   ├── llm_groq.py             # Groq chat-completions streaming
│   │   ├── streaming_llm.py        # token stream → sentence "phrases" for TTS
│   │   ├── stt_scribe.py           # ElevenLabs Scribe realtime (file-based helper)
│   │   ├── tts_cartesia.py         # Cartesia → WAV (offline helper)
│   │   ├── cartesia_realtime.py    # queue-based Cartesia streaming (legacy/dev)
│   │   └── streaming_voice.py      # local-speaker streaming (dev-only, needs pyaudio)
│   ├── conversation/history.py     # rolling LLM message history (max 20)
│   ├── db/database.py              # SQLite wrapper + 3 seed personas
│   ├── observability/call_latency.py  # per-turn latency report printed to logs
│   └── core/settings.py            # all env config (pydantic-settings)
├── frontend/                   # static site, accounts, Creator Backstage, admin Studio, shared JS/CSS
├── deploy/
│   ├── deploy.sh               # GCP deploy: provision / sync / setup phases
│   ├── bootstrap.sh            # VM startup script: deps, venv, Caddy, systemd, smoke test
│   ├── voice-agent.env         # ⚠️ SECRETS (gitignored) — real keys live here
│   └── voice-agent.env.example # template
├── scripts/                    # local dev/test scripts (mic, pipecat, provider tests) — NOT production
├── tests/                      # minimal (audio fixtures) — no real test suite yet
├── requirements.txt            # production deps (pinned anyio! see §10)
├── requirements-dev.txt        # dev-only: pyaudio, pipecat-ai (NOT on the VM)
├── DEPLOYMENT.md               # full deployment guide (ops manual)
└── AGENTS.md                   # ← this file
```

`app/pipeline/recorded_pipeline.py` and the `scripts/`/`providers/streaming_voice.py`
pile are earlier/local experiments — the **production path is
`app/telephony/*` only**; don't wire the old pieces back in.

---

## 3. The call pipeline (production path)

One phone call, from Twilio's perspective:

1. Twilio POSTs the call webhook → `POST /twilio/voice` returns TwiML with a
   `<Stream>` pointing at `wss://tac.cytieq.com/twilio/media-stream?influencer=<id>&name=<caller>`.
2. Twilio opens that WebSocket → `handle_twilio_media_stream()` in
   `twilio_media.py`:
   - resolves the persona from `?influencer=<id>` (voice + system prompt),
   - opens an **ElevenLabs Scribe** realtime WebSocket (μ-law 8 kHz),
   - creates a `TwilioVoiceAgent` (Groq + Cartesia),
   - three concurrent tasks: forward Twilio audio → ElevenLabs;
     receive transcripts; respond to committed transcripts.
3. **Barge-in**: partial transcripts while the AI is speaking trigger a
   `clear` event to Twilio + interrupt the generation (see
   `TwilioVoiceAgent.interrupt()`).
4. On `start` event the agent speaks an **LLM-generated greeting** (greets the
   caller by name; recorded in history but not as a user turn).
5. Per committed transcript: `respond_to_transcript()` streams Groq phrases
   into one Cartesia realtime context (μ-law 8 kHz) and forwards each audio
   chunk to Twilio, ending with a playback mark.

Latency per turn is printed by `CallLatencyTracker`. All logs go to stdout
(no structured logging configured despite structlog being installed).

---

## 4. The product flow (what the user sees)

```
Landing (/) ──> Directory (/influencers.html) ──> Profile (/influencer.html?id=N)
                                                     │  "Your name" + "Your phone number"
                                                     ▼
                                        POST /api/call-requests
                                                     │  validates + dials via Twilio
                                                     ▼
                        webhook /twilio/voice?influencer=<id>&name=<caller>
                                                     │  persona travels in query params
                                                     ▼
                        /twilio/media-stream WS loads persona (voice + prompt), greets caller
```

Admin/Studio at `/admin.html`: create/delete personas, view call-request log
(token-gated client-side; token stored in `localStorage["tac_admin_token"]`).

---

## 5. Data model (SQLite, `voice_agent.db`)

```sql
influencers(id, name, tagline, bio, avatar_url, voice_id, system_prompt, created_at)
call_requests(id, influencer_id, user_name, user_phone, call_sid, status, error, created_at)
users(id, email, display_name, password_hash, role, created_at, updated_at)
user_sessions(token_hash, user_id, expires_at, created_at)
web_call_sessions(id, influencer_id, user_id, caller_name, status, duration_seconds, error, started_at, ended_at)
voice_clone_consents(id, influencer_id, user_id, provider, provider_voice_id, language, consent_version, rights_confirmed, synthetic_acknowledged, created_at)
```

- Seeded on first boot with 3 personas: Alex Morgan (fitness), Priya Sharma
  (marketing), Marco Reyes (real estate) — `_default_influencers()` in
  `app/db/database.py`.
- `VoiceDatabase` is a process-wide singleton (`get_database()`), guarded by a
  thread lock (`check_same_thread=False`).
- **Persona system prompt**: if `system_prompt` is empty, one is auto-built
  from name/tagline/bio via `compose_system_prompt()`; empty `voice_id` falls
  back to the global `CARTESIA_VOICE_ID`.

---

## 6. API surface

Public (no auth):
| Method | Path | Notes |
|---|---|---|
| GET | `/health` | `{"ok":true,...}` (Caddy + smoke tests) |
| GET | `/info` | non-secret models/config for the frontend (`pipeline.stt/llm/tts`, `twilio_configured`) |
| GET | `/api/influencers` | list personas (no `system_prompt`) |
| GET | `/api/influencers/{id}` | one persona — **`system_prompt` deliberately stripped** |
| POST | `/api/call-requests` | `{influencer_id, user_name, user_phone}` → dials Twilio; 503 if keys missing, 502 on Twilio failure |
| POST | `/twilio/voice` | TwiML webhook (`?influencer&name` query params) |
| POST | `/twilio/make-call` | legacy test call to `TEST_TO_PHONE_NUMBER` |
| WS | `/twilio/media-stream` | the audio stream |

Admin (require `Authorization: Bearer <ADMIN_TOKEN>` when set; open if empty):
`POST /api/influencers`, `DELETE /api/influencers/{id}`,
`GET /api/call-requests` (phone numbers **masked**, e.g. `+1555••••567`).

Signed-in creator routes include `/api/creator/dashboard`, profile editing,
review/publish controls, and `POST /api/creator/voice/clone`. Cloning is
identity-review gated, requires explicit rights + synthetic-use confirmations,
sends the sample to Cartesia without retaining the raw upload in TAC storage,
stores the resulting voice ID and consent receipt, and activates that voice for
subsequent creator calls.

The current ADMIN_TOKEN lives in `deploy/voice-agent.env` — it is a secret;
do not print it, commit it, or hardcode it.

---

## 7. Frontend (no build step)

Plain HTML + `frontend/app.js` (one IIFE, dispatches on `<body data-page>`):
- `home` — hero, how-it-works, featured voices (top 3 from API), status pill
  polling `/health` every 30s, model chips from `/info`.
- `influencers` — full directory grid.
- `influencer` — profile + call form; client-side phone validation mirrors the
  server regex `^\+?[0-9\s().-]{7,20}$`; friendly error mapping for
  "not configured" / "twilio rejected" cases.
- `admin` — Studio: create form, existing voices (with delete), recent call
  requests table.

All dynamic rendering **HTML-escapes** user content (`esc()`) — keep it that
way. Avatar gradients derive from `id % 6`.

---

## 8. Configuration (all env, `app/core/settings.py`)

| Group | Keys |
|---|---|
| App | `APP_NAME`, `APP_ENV`, `APP_HOST`, `APP_PORT`, `LOG_LEVEL` |
| Twilio | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, `TEST_TO_PHONE_NUMBER`, `PUBLIC_BASE_URL` |
| ElevenLabs | `ELEVENLABS_API_KEY`, `ELEVENLABS_STT_MODEL` (scribe_v2_realtime) |
| Groq | `GROQ_API_KEY`, `GROQ_MODEL` (llama-3.3-70b-versatile) |
| Cartesia | `CARTESIA_API_KEY`, `CARTESIA_VOICE_ID`, `CARTESIA_MODEL` (sonic-3.5), `CARTESIA_SAMPLE_RATE` |
| Data/Admin | `DATABASE_PATH` (default `voice_agent.db`), `ADMIN_TOKEN` |
| Unused by pipeline | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `REDIS_URL`, `N8N_WEBHOOK_URL` |

Templates: `.env.example` (local) and `deploy/voice-agent.env.example` (VM).
`PUBLIC_BASE_URL` must be the public HTTPS origin (no trailing slash) — the
TwiML `wss://` URL is derived from it.

---

## 9. Deployment (GCP e2-micro, ~$0/mo)

- **VM**: `voice-agent`, e2-micro, Debian 12, 20 GB disk, in **us-central1-a**
  (deploy.sh defaults to `us-central1-f`; pass `ZONE=...` to override).
  Static IP `voice-agent-ip`; firewall `voice-agent-allow` (80/443/8000).
  GCP project: `project-806302e9-3b2a-4ccb-be8` (set via `gcloud config`).
- **Domain**: `tac.cytieq.com` → Cloudflare A record (grey cloud) → Caddy on
  the VM issues Let's Encrypt automatically.
- **Flow** (deploys the code on disk, no GitHub involved):
  1. `./deploy/deploy.sh provision` — firewall + IP + VM, env file
     base64-encoded into instance metadata, bootstrap.sh as startup script.
  2. `./deploy/deploy.sh sync` — tarballs repo (excludes secrets) → scp →
     **atomic replace**: backup `voice_agent.db` + `.env`, wipe
     `/opt/voice-agent/*`, extract, restore. Prints `EXTRACT_OK`.
  3. `./deploy/deploy.sh setup` — runs `bootstrap.sh`: apt deps, `voiceagent`
     user, `.env` from metadata, **clean venv rebuild**, `pip install`,
     Caddy (static frontend at `/`, `/api/*`, `/health`, `/info`, `/twilio/*`
     → `127.0.0.1:8000`), hardened systemd unit, smoke test → `SETUP COMPLETE`.
- **Caddy routing** (in `bootstrap.sh`): API/voice paths → FastAPI; everything
  else → `frontend/` with SPA-ish `try_files ... /index.html`.
- **systemd**: `voice-agent.service`, user `voiceagent`, uvicorn on
  `0.0.0.0:8000`, `Restart=always`, hardened (`ProtectSystem=full`,
  `ReadWritePaths=/opt/voice-agent`).

Ops cheatsheet (see DEPLOYMENT.md §6 for more):
```bash
# update code + restart without full deploy
./deploy/deploy.sh sync
gcloud compute ssh voice-agent --zone=us-central1-a -- 'sudo systemctl restart voice-agent'

# logs
gcloud compute ssh voice-agent --zone=us-central1-a -- 'sudo journalctl -u voice-agent -n 100 -f'
gcloud compute ssh voice-agent --zone=us-central1-a -- 'sudo tail -f /var/log/voice-agent-setup.log'
```

---

## 10. Hard-won gotchas (do not regress these)

1. **`anyio` is pinned to `==4.14.2` in requirements.txt.** Some newer
   releases ship a broken/missing `anyio._backends` package that makes every
   FastAPI request crash with `ModuleNotFoundError: No module named
   'anyio._backends'` (surfaces as bare 500s). Don't unpin.
2. **The VM's `.venv` is rebuilt from scratch on every setup** (`rm -rf .venv`).
   A stale venv caused the same anyio corruption once — the clean rebuild is
   intentional.
3. **Deploy must never wipe `voice_agent.db` or `.env`** — sync backs them up
   and restores them around the wipe. The DB is root-owned after restore and
   gets `chown voiceagent` in bootstrap; if writes 500, check DB ownership.
4. **Admin token flow**: `ADMIN_TOKEN` lives in `deploy/voice-agent.env`
   locally and in `/opt/voice-agent/.env` on the VM. When empty, admin
   endpoints are open (prototype mode). Frontend only attaches it for admin
   calls (`auth: true`).
5. **Never expose `system_prompt`** through public endpoints (GET detail
   strips it) — personas' prompts are internal.
6. **Phone numbers are masked** in `GET /api/call-requests` responses.
7. **HTML-escape everything** rendered from API/user data in the frontend.
8. SSH to the VM can be flaky from sandboxes — retry with
   `--ssh-flag='-o ServerAliveInterval=10'`; verify externally via
   `curl https://tac.cytieq.com/...` rather than trusting SSH round-trips.

---

## 11. Local dev & validation

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # prod deps
cp deploy/voice-agent.env.example deploy/voice-agent.env              # fill keys
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000           # run

# quick validation after changes
for f in $(find app -name '*.py'); do python3 -m py_compile "$f" || echo "FAIL $f"; done
bash -n deploy/deploy.sh && bash -n deploy/bootstrap.sh
node --check frontend/app.js
```

There is no automated test suite yet — validation is compile checks + live
endpoint curls against `https://tac.cytieq.com` (or a local boot).

---

## 12. Current live state & next steps

- ✅ Site, APIs, personas, admin flow all live and verified (browser-tested,
  zero console errors).
- ✅ Security fixes from review deployed (admin token, phone masking,
  prompt-stripping, greeting-task cleanup, phone normalization, atomic sync).
- ⚠️ **Twilio / ElevenLabs / Groq / Cartesia keys are still empty** in
  `deploy/voice-agent.env` → "Call me now" returns a friendly "not configured"
  message. Filling those keys + `./deploy/deploy.sh sync && setup` is the
  single remaining step before real calls work.
- Possible next features: inbound-call routing per persona, call-request
  status webhooks (Twilio statusCallback), real auth for the Studio,
  Secret Manager instead of instance metadata.
