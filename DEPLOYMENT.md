# Deployment — GCP VM (cheapest: e2-micro, $0/month)

This guide deploys the **voice AI agent** (FastAPI + uvicorn, Twilio media
streams) to a single **e2-micro** Compute Engine VM on Google Cloud's
**always-free tier** — the cheapest option that can run it as a prototype:
**$0/month**.

| Item | Choice | Cost |
|---|---|---|
| Machine type | `e2-micro` (2 shared vCPUs, 1 GB RAM) | $0/mo (free tier) |
| Free-tier regions | `us-west1`, `us-central1`, `us-east1` | — |
| Disk | 20 GB standard (free tier covers 30 GB-mo) | $0 |
| Static IP | attached to running VM | $0 |
| Egress | 1 GB/mo free (plenty for a prototype) | $0 |

> Outside the three free-tier regions, `e2-micro` costs ~$6.11/mo and
> `e2-small` ~$12.23/mo. Staying in `us-west1` / `us-central1` / `us-east1`
> keeps the bill at zero.

---

## 0. Prerequisites

1. A **Google Cloud account** with a billing account linked (free-tier usage stays $0).
2. **gcloud CLI** installed and authenticated:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   ```
3. The repo on disk (the VM receives **your local code** via `gcloud compute scp` — no GitHub push needed, so uncommitted fixes deploy fine).
4. Real API keys in a `.env` file locally if you want to test calls:
   Twilio (SID, auth token, phone number), ElevenLabs, Groq, Cartesia.

---

## 1. One-time setup

```bash
# Set your project (create one in the console first if you don't have it)
gcloud config set project YOUR_PROJECT_ID

# Prepare the env file the VM will receive
cp deploy/voice-agent.env.example deploy/voice-agent.env
$EDITOR deploy/voice-agent.env   # fill in all real keys
```

**Domain — `tac.cytieq.com` (already configured):**

- `deploy/voice-agent.env.example` ships with
  `PUBLIC_BASE_URL=https://tac.cytieq.com`.
- `deploy.sh` also pushes a `voice_domain=tac.cytieq.com` metadata key.
- The startup script installs **Caddy**, which obtains a **free Let's Encrypt
  certificate** for `tac.cytieq.com` automatically and routes:
  - the **static frontend** (`frontend/`) at the root path,
  - `/health`, `/info`, `/ws/*`, and `/twilio/*` to the FastAPI app on
    `127.0.0.1:8000` (so Twilio gets the `wss://` it requires).

**One DNS step required (you control it in Cloudflare):** after the VM is
created and you have its static IP, add an A record in Cloudflare DNS for
`cytieq.com`:

```
tac  A  <STATIC_IP>   (proxy status: DNS only / grey cloud)
```

Until that record resolves, Caddy serves the app over HTTP (port 80) and
keeps retrying certificate issuance, so nothing breaks — HTTPS simply comes
alive once DNS points at the VM.

---

## 2. Deploy

```bash
./deploy/deploy.sh          # all phases
# or step by step:
./deploy/deploy.sh provision   # firewall + static IP + VM
./deploy/deploy.sh sync        # upload local code to the VM
./deploy/deploy.sh setup       # install deps, Caddy, systemd, smoke test
```

> The VM runs **your local code** — there is no GitHub clone. You can deploy
> with uncommitted changes; whatever is on disk gets uploaded.

What it does:

1. **provision** — checks gcloud auth, sets the project, enables
   `compute.googleapis.com`, creates firewall rule `voice-agent-allow`
   (TCP 8000/80/443), reserves static IP `voice-agent-ip`, and creates
   `voice-agent` (`e2-micro`, Debian 12, 20 GB disk) in `us-central1-f`
   with your env file base64-encoded into instance metadata plus the
   bootstrap startup script.
2. **sync** — waits for SSH, tarballs the repo on disk (excluding `.git`,
   `.venv`, `__pycache__`, and `deploy/voice-agent.env`), and scp's it to
   `/opt/voice-agent` on the VM.
3. **setup** — runs `deploy/bootstrap.sh` on the VM, which:
   - Installs `python3-venv`, `pip`, `git`, `curl`
   - Creates unprivileged user `voiceagent`
   - Writes `.env` from the metadata value
   - Creates a venv and runs `pip install -r requirements.txt`
   - Installs **Caddy** (auto-HTTPS for `tac.cytieq.com`, serving the
     `frontend/` static site at the root and proxying `/health`, `/info`,
     `/twilio/*` to the app)
   - Installs and starts a hardened **systemd service** (`voice-agent`)
     running `uvicorn app.main:app --host 0.0.0.0 --port 8000`
   - Smoke-checks `/health`

Watch progress:

```bash
gcloud compute ssh voice-agent --zone=us-central1-f -- \
  'sudo tail -f /var/log/voice-agent-setup.log'
```

Health check (once the service is up):

```bash
curl http://<STATIC_IP>:8000/health
# {"ok":true,"service":"voice-ai-server","environment":"production"}

# After the DNS A record points tac.cytieq.com at the VM:
curl https://tac.cytieq.com/health
```

Re-deploy after code changes: just run `./deploy/deploy.sh` again — it
re-uploads the code on disk, reboots the VM, and re-runs the setup. (Only
the `provision` step is skipped-able; `sync` + `setup` always refresh code
and restart the service.)

For a quick manual update without re-running the whole deploy:
`./deploy/deploy.sh sync && gcloud compute ssh voice-agent --zone=us-central1-f -- 'sudo systemctl restart voice-agent'`

---

## 3. Frontend — the influencer product

The repo ships a static multi-page frontend in `frontend/` that Caddy
serves at `https://tac.cytieq.com/` (no build step — edit the files
locally and re-run `./deploy/deploy.sh sync`):

| Page | Route | Purpose |
|---|---|---|
| Landing | `/` | product hero, how-it-works, featured voices, live status |
| Directory | `/influencers.html` | grid of all AI voice personas |
| Profile | `/influencer.html?id=N` | persona bio + live browser voice call |
| Studio | `/admin.html` | create/delete personas, review call requests |

## 4. Product flow & API

The active user flow is: **browse a voice → allow the microphone on its
profile → talk with the creator's AI in the browser.** Set `CALL_MODE=web`
to keep Twilio outbound calling paused, or `CALL_MODE=twilio` to restore it.

Personas are stored in SQLite (`voice_agent.db`, created on first boot and
seeded with three sample voices). The persona travels through the call via
query params: `POST /api/call-requests` → Twilio webhook
`/twilio/voice?influencer=<id>&name=<caller>` → the TwiML `<Stream>` URL
carries the same params → the `/twilio/media-stream` WebSocket handler
loads the persona's **system prompt + voice** and starts with a spoken
greeting.

Public endpoints:

| Method | Path | Notes |
|---|---|---|
| GET | `/api/influencers` | list personas |
| GET | `/api/influencers/{id}` | one persona |
| WS | `/ws/voice-chat` | active browser PCM voice session |
| POST | `/api/call-requests` | `{influencer_id, user_name, user_phone}` → starts the Twilio call |

Admin endpoints (require `Authorization: Bearer <ADMIN_TOKEN>` when
`ADMIN_TOKEN` is set in the env; open for the prototype otherwise):
`POST /api/influencers`, `DELETE /api/influencers/{id}`,
`GET /api/call-requests`. The Studio page stores its token in the browser.

Quick test:

```bash
curl https://tac.cytieq.com/api/influencers
curl -X POST https://tac.cytieq.com/api/call-requests \
  -H 'Content-Type: application/json' \
  -d '{"influencer_id": 1, "user_name": "Sam", "user_phone": "+15551234567"}'
```

## 5. Making real Twilio phone calls (HTTPS)

Twilio refuses `ws://` media streams in production — you need `https://`.
This is already handled: the startup script installs **Caddy**, which
reverse-proxies `https://tac.cytieq.com` → `127.0.0.1:8000` and issues a
free Let's Encrypt certificate automatically (no nginx config needed).

The only manual prerequisite is the DNS record (§1):

```
tac  A  <STATIC_IP>   (DNS only / grey cloud, so Let's Encrypt can validate)
```

Want a different domain? Set `DOMAIN=your.domain ./deploy/deploy.sh` — the
Caddyfile and `PUBLIC_BASE_URL` follow automatically.

### Twilio console setup

1. Buy/verify a Twilio phone number.
2. Add `TEST_TO_PHONE_NUMBER` (your verified number) to the env file.
3. Point your Twilio phone number's **"A call comes in"** webhook to:

   ```
   https://tac.cytieq.com/twilio/voice   (POST)
   ```

4. Trigger an outbound test call to your phone:

   ```bash
   curl -X POST https://tac.cytieq.com/twilio/make-call
   ```

   (Requires `TWILIO_*` + `TEST_TO_PHONE_NUMBER` + `PUBLIC_BASE_URL` set.)

---

## 6. Operations

| Task | Command |
|---|---|
| Logs | `gcloud compute ssh voice-agent --zone=us-central1-f -- 'journalctl -u voice-agent -n 100 -f'` |
| Restart | `gcloud compute ssh voice-agent --zone=us-central1-f -- 'sudo systemctl restart voice-agent'` |
| Setup log | `gcloud compute ssh voice-agent --zone=us-central1-f -- 'sudo tail -f /var/log/voice-agent-setup.log'` |
| Update app | `./deploy/deploy.sh sync && gcloud compute ssh voice-agent --zone=us-central1-f -- 'sudo systemctl restart voice-agent'` |
| Stop (keep VM) | `gcloud compute instances stop voice-agent --zone=us-central1-f` |
| Delete everything | `gcloud compute instances delete voice-agent --zone=us-central1-f` + `gcloud compute addresses delete voice-agent-ip --region=us-central1` + `gcloud compute firewall-rules delete voice-agent-allow` |

---

## 7. Troubleshooting

- **VM never becomes healthy** → `journalctl -u voice-agent -n 50` and
  `cat /var/log/voice-agent-setup.log`. Common causes: missing API key
  (Cartesia/Groq throw at runtime only, so the service still boots), or
  `pip install` failing.
- **`pip install` fails** → the server only needs `requirements.txt`
  (production deps). `requirements-dev.txt` adds `pyaudio`/`pipecat-ai` for
  local scripts and is **not** installed on the VM. (Locally, `pyaudio`
  also needs the system package `portaudio19-dev` on Linux.)
- **Twilio says connection is not secure** → you're using `ws://`; switch to
  HTTPS (see §3).
- **Outbound call 500 "Missing configuration"** → check `TWILIO_*`,
  `TEST_TO_PHONE_NUMBER`, `PUBLIC_BASE_URL` in `deploy/voice-agent.env`.

---

## 8. Security notes

- `deploy/voice-agent.env` is **gitignored** — never commit it.
- The env file travels inside instance metadata (base64). Anyone with project
  read access can see it. **Switch to Secret Manager before real production.**
- `.env` on the VM is written with `chmod 600`.
