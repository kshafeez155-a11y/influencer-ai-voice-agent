#!/usr/bin/env bash
# ============================================================
# Voice AI agent — GCP VM bootstrap (runs on boot, idempotent)
# ============================================================
# Installs system packages, creates the app user, writes .env
# from instance metadata, then WAITS for the application code
# to be uploaded (deploy.sh scp's the local repo to
# /opt/voice-agent). Once code is present it finishes setup:
# venv, pip deps, Caddy (auto-HTTPS), systemd unit, smoke test.
#
# Metadata keys used:
#   voice_env_b64   base64 of deploy/voice-agent.env
#   voice_domain    e.g. tac.cytieq.com
# ============================================================

set -euo pipefail

exec > >(tee -a /var/log/voice-agent-setup.log) 2>&1

export DEBIAN_FRONTEND=noninteractive

APP_USER="${APP_USER:-voiceagent}"
APP_DIR="/opt/voice-agent"
METADATA_BASE="http://metadata.google.internal/computeMetadata/v1/instance/attributes"

log() {
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"
}

log "Bootstrap starting"

# ------------------------------------------------------------
# 0. Wait for any other apt/dpkg process to release locks
# ------------------------------------------------------------
for _ in $(seq 1 60); do
    if ! fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock >/dev/null 2>&1; then
        break
    fi
    sleep 5
done

# ------------------------------------------------------------
# 1. System packages
# ------------------------------------------------------------
log "Installing system packages"
apt-get update -y
apt-get install -y \
    python3-venv \
    python3-pip \
    git \
    curl \
    ca-certificates \
    debian-keyring \
    debian-archive-keyring \
    apt-transport-https \
    gnupg \
    tar

# ------------------------------------------------------------
# 2. Unprivileged app user
# ------------------------------------------------------------
if ! id "${APP_USER}" >/dev/null 2>&1; then
    log "Creating unprivileged user ${APP_USER}"
    useradd --system --home "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi

mkdir -p "${APP_DIR}"

# ------------------------------------------------------------
# 3. Write .env from instance metadata if provided
# ------------------------------------------------------------
ENV_B64="$(curl -sf -H 'Metadata-Flavor: Google' \
    "${METADATA_BASE}/voice_env_b64" || true)"
DOMAIN="$(curl -sf -H 'Metadata-Flavor: Google' \
    "${METADATA_BASE}/voice_domain" || true)"

if [ -n "${ENV_B64}" ]; then
    log "Writing .env from instance metadata"
    echo "${ENV_B64}" | base64 -d > "${APP_DIR}/.env"
    chmod 600 "${APP_DIR}/.env"

    if [ -n "${DOMAIN}" ]; then
        if grep -q "^PUBLIC_BASE_URL=.\\+" "${APP_DIR}/.env"; then
            log "PUBLIC_BASE_URL already set; leaving as-is"
        else
            log "Setting PUBLIC_BASE_URL=https://${DOMAIN} in .env"
            sed -i '/^PUBLIC_BASE_URL=$/d' "${APP_DIR}/.env"
            echo "PUBLIC_BASE_URL=https://${DOMAIN}" >> "${APP_DIR}/.env"
        fi
    fi
else
    log "No voice_env_b64 metadata found; using existing .env if present"
fi

# ------------------------------------------------------------
# 4. Wait for application code (uploaded by deploy.sh)
# ------------------------------------------------------------
if [ ! -f "${APP_DIR}/app/main.py" ]; then
    log "Waiting for code upload to ${APP_DIR} (up to 6 min)..."
    for _ in $(seq 1 36); do
        if [ -f "${APP_DIR}/app/main.py" ]; then
            break
        fi
        sleep 10
    done
fi

if [ ! -f "${APP_DIR}/app/main.py" ]; then
    log "ERROR: code was never uploaded to ${APP_DIR}"
    log "Run: ./deploy/deploy.sh sync  (uploads the local repo)"
    exit 1
fi

chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

# ------------------------------------------------------------
# 5. Python virtual environment + dependencies
# ------------------------------------------------------------
log "Creating Python virtual environment (clean rebuild)"
cd "${APP_DIR}"
rm -rf .venv
python3 -m venv .venv
"${APP_DIR}/.venv/bin/pip" install --upgrade pip wheel setuptools
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

# ------------------------------------------------------------
# 6. systemd service (installed BEFORE Caddy so the app always
#    comes up even if the optional Caddy step fails)
# ------------------------------------------------------------
log "Installing systemd unit"

cat > /etc/systemd/system/voice-agent.service <<'UNIT'
[Unit]
Description=Voice AI agent (FastAPI + uvicorn)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=voiceagent
Group=voiceagent
WorkingDirectory=/opt/voice-agent
ExecStart=/opt/voice-agent/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
# Hardening
NoNewPrivileges=true
ProtectSystem=full
ReadWritePaths=/opt/voice-agent
PrivateTmp=true
ProtectHome=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable voice-agent
systemctl restart voice-agent

# The SQLite DB (and anything a previous root-run process created)
# must stay writable by the unprivileged app user.
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}" 2>/dev/null || true

# ------------------------------------------------------------
# 7. Caddy reverse proxy (auto-HTTPS for Twilio wss://)
#    Optional — failures here must not break the app.
# ------------------------------------------------------------
if [ -n "${DOMAIN}" ]; then
    log "Installing Caddy for ${DOMAIN}"

    # Official Caddy Debian repository (non-fatal on failure)
    if curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
        && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null \
        && apt-get update -y \
        && apt-get install -y caddy; then

        cat > /etc/caddy/Caddyfile <<CADDY
${DOMAIN} {
    encode zstd gzip
    root * /opt/voice-agent/frontend

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), geolocation=(), payment=()"
        Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' https: data:; media-src 'self' blob: https:; connect-src 'self' wss://${DOMAIN}; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        -Server
    }

    # API / voice endpoints → FastAPI backend
    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }
    handle /health {
        reverse_proxy 127.0.0.1:8000
    }
    handle /info {
        reverse_proxy 127.0.0.1:8000
    }
    handle /twilio/* {
        reverse_proxy 127.0.0.1:8000
    }
    handle /ws/* {
        reverse_proxy 127.0.0.1:8000
    }

    # Everything else → static frontend
    handle {
        file_server
    }

    handle_errors {
        @not_found expression {http.error.status_code} == 404
        rewrite @not_found /404.html
        file_server
    }
}
CADDY

        systemctl enable caddy
        systemctl restart caddy
        log "Caddy configured for https://${DOMAIN} (frontend + API routes)"
    else
        log "WARNING: Caddy install failed — app still runs on :8000 directly."
    fi
else
    log "No voice_domain metadata found; skipping Caddy (serving on :8000 directly)"
fi

# ------------------------------------------------------------
# 8. Smoke check
# ------------------------------------------------------------

for attempt in $(seq 1 15); do
    if curl -sf "http://127.0.0.1:8000/health" > /dev/null; then
        log "voice-agent is UP (http://127.0.0.1:8000/health)"

        if [ -n "${DOMAIN}" ]; then
            log "Caddy HTTPS check: curl https://${DOMAIN}/health"
            log "NOTE: HTTPS becomes live once the DNS A record for ${DOMAIN}"
            log "points to this VM's external IP (Caddy issues the certificate)."
        fi

        log "SETUP COMPLETE"
        exit 0
    fi
    sleep 2
done

log "ERROR: voice-agent did not become healthy within 30s"
log "Check: journalctl -u voice-agent -n 50"
exit 1
