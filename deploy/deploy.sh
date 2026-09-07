#!/usr/bin/env bash
# ============================================================
# Voice AI agent — deploy to the cheapest GCP VM (e2-micro)
# ============================================================
# Provisions:
#   - firewall rule  voice-agent-allow  (tcp:80, 443)
#   - static IP       voice-agent-ip
#   - e2-micro VM     voice-agent  (free tier: us-west1 / us-central1 / us-east1)
#
# Unlike a GitHub-clone workflow, this deploys the code on your disk:
#   phase 1 (provision): create the VM + firewall + static IP
#   phase 2 (sync):      scp the local repo to the VM
#   phase 3 (setup):     run deploy/bootstrap.sh on the VM
#
# Usage:
#   ./deploy/deploy.sh               # all phases
#   ./deploy/deploy.sh provision     # firewall + IP + VM only
#   ./deploy/deploy.sh sync          # upload local code to the VM
#   ./deploy/deploy.sh setup         # run bootstrap.sh on the VM
#
# Requires:
#   - gcloud CLI authenticated:  gcloud auth login
#   - A GCP project with billing (free-tier usage stays $0)
#   - deploy/voice-agent.env filled in (copy from voice-agent.env.example)
#
# WARNING: deploy/voice-agent.env is uploaded into instance metadata as
# base64. Anyone with read access to the project can read it. Fine for a
# prototype; use Secret Manager before real production use.
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null | tr -d '\n')}"
ZONE="${ZONE:-us-central1-f}"          # free-tier region
REGION="${ZONE%-*}"
VM_NAME="${VM_NAME:-voice-agent}"
IP_NAME="${IP_NAME:-voice-agent-ip}"
FIREWALL_NAME="${FIREWALL_NAME:-voice-agent-allow}"
TAG="${TAG:-voice-agent}"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/voice-agent.env}"
DOMAIN="${DOMAIN:-tac.cytieq.com}"
PHASE="${1:-all}"

echo "=============================================="
echo " Voice AI agent — GCP e2-micro deploy"
echo "=============================================="
echo "Project : ${PROJECT_ID:-<unset>}"
echo "Zone    : ${ZONE}"
echo "VM      : ${VM_NAME} (e2-micro — free tier)"
echo "Domain  : ${DOMAIN} (auto-HTTPS via Caddy)"
echo "Phase   : ${PHASE}"
echo ""

require_project() {
    if [ -z "${PROJECT_ID}" ]; then
        echo "ERROR: no GCP project set."
        echo "  Either run:  gcloud config set project YOUR_PROJECT_ID"
        echo "  or:          PROJECT_ID=YOUR_PROJECT_ID ./deploy/deploy.sh"
        exit 1
    fi
}

require_env_file() {
    if [ ! -f "${ENV_FILE}" ]; then
        echo "ERROR: ${ENV_FILE} not found."
        echo "  Create it from the template first:"
        echo "  cp ${SCRIPT_DIR}/voice-agent.env.example ${ENV_FILE}"
        echo "  # then fill in your real API keys"
        exit 1
    fi
}

require_auth() {
    echo "Checking gcloud authentication..."
    if ! gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | grep -q .; then
        echo "ERROR: gcloud is not authenticated. Run:  gcloud auth login"
        exit 1
    fi
}

get_ip() {
    IP_ADDRESS=""
    if gcloud compute addresses describe "${IP_NAME}" --region="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
        IP_ADDRESS="$(gcloud compute addresses describe "${IP_NAME}" --region="${REGION}" --project="${PROJECT_ID}" --format='value(address)')"
    fi
}

phase_provision() {
    require_project
    require_env_file
    require_auth

    echo "Setting project to ${PROJECT_ID}..."
    gcloud config set project "${PROJECT_ID}" --quiet

    echo "Enabling required APIs (compute)..."
    gcloud services enable compute.googleapis.com --project="${PROJECT_ID}" --quiet

    echo "Creating firewall rule ${FIREWALL_NAME} (tcp:80,443)..."
    if ! gcloud compute firewall-rules describe "${FIREWALL_NAME}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
        gcloud compute firewall-rules create "${FIREWALL_NAME}" \
            --project="${PROJECT_ID}" \
            --direction=INGRESS \
            --priority=1000 \
            --network=default \
            --action=ALLOW \
            --rules=tcp:80,tcp:443 \
            --source-ranges=0.0.0.0/0 \
            --target-tags="${TAG}" \
            --quiet
    else
        echo "Updating firewall rule ${FIREWALL_NAME} to keep port 8000 private."
        gcloud compute firewall-rules update "${FIREWALL_NAME}" \
            --project="${PROJECT_ID}" \
            --rules=tcp:80,tcp:443 \
            --source-ranges=0.0.0.0/0 \
            --quiet
    fi

    echo "Reserving static IP ${IP_NAME}..."
    get_ip
    if [ -z "${IP_ADDRESS}" ]; then
        IP_ADDRESS="$(gcloud compute addresses create "${IP_NAME}" \
            --region="${REGION}" \
            --project="${PROJECT_ID}" \
            --format='value(address)')"
        echo "Reserved static IP: ${IP_ADDRESS}"
    else
        echo "Static IP already exists: ${IP_ADDRESS}"
    fi

    echo "Encoding ${ENV_FILE} into VM metadata..."
    ENV_B64="$(base64 -w0 "${ENV_FILE}" 2>/dev/null || base64 "${ENV_FILE}")"
    METADATA_KEYS="voice_env_b64=${ENV_B64},voice_domain=${DOMAIN}"

    echo "Creating e2-micro VM ${VM_NAME} in ${ZONE}..."
    if gcloud compute instances describe "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
        echo "VM ${VM_NAME} already exists — updating metadata and rebooting to re-run bootstrap."
        gcloud compute instances add-metadata "${VM_NAME}" \
            --zone="${ZONE}" \
            --project="${PROJECT_ID}" \
            --metadata "${METADATA_KEYS}" \
            --metadata-from-file startup-script="${SCRIPT_DIR}/bootstrap.sh" \
            --quiet
        VM_STATUS="$(gcloud compute instances describe "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" --format='value(status)')"
        if [ "${VM_STATUS}" = "RUNNING" ]; then
            gcloud compute instances reset "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" --quiet
        else
            gcloud compute instances start "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" --quiet
        fi
    else
        gcloud compute instances create "${VM_NAME}" \
            --project="${PROJECT_ID}" \
            --zone="${ZONE}" \
            --machine-type=e2-micro \
            --image-family=debian-12 \
            --image-project=debian-cloud \
            --boot-disk-size=20 \
            --boot-disk-type=pd-standard \
            --address="${IP_ADDRESS}" \
            --tags="${TAG}" \
            --metadata "${METADATA_KEYS}" \
            --metadata-from-file startup-script="${SCRIPT_DIR}/bootstrap.sh" \
            --quiet
    fi

    get_ip
    echo ""
    echo "PROVISIONED — Static IP: ${IP_ADDRESS}"
    echo "Next: ./deploy/deploy.sh sync && ./deploy/deploy.sh setup"
}

phase_sync() {
    require_project
    require_auth

    echo "Waiting for SSH on ${VM_NAME} (zone ${ZONE})..."
    SSH_READY=""
    for _ in $(seq 1 30); do
        if gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" \
            --command 'echo ssh-ready' --quiet \
            --ssh-flag="-o StrictHostKeyChecking=no" 2>/dev/null | grep -q ssh-ready; then
            SSH_READY=1
            break
        fi
        echo "  waiting for SSH..."
        sleep 10
    done

    if [ -z "${SSH_READY}" ]; then
        echo "ERROR: could not reach ${VM_NAME} over SSH."
        exit 1
    fi

    echo "Creating source tarball (excluding .git, .venv, __pycache__, secrets)..."
    TARBALL="/tmp/voice-agent-src.tar.gz"
    tar -czf "${TARBALL}" \
        --exclude='.git' \
        --exclude='.venv' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.env' \
        --exclude='voice_agent.db' \
        --exclude='frontend/influencer_voice_app/.dart_tool' \
        --exclude='frontend/influencer_voice_app/build' \
        --exclude='frontend/influencer_voice_app/voice-chat.apk' \
        --exclude='node_modules' \
        --exclude='*/voice-agent.env' \
        -C "${REPO_DIR}" .

    echo "Uploading code to ${VM_NAME}:/tmp/..."
    gcloud compute scp "${TARBALL}" "${VM_NAME}:/tmp/voice-agent-src.tar.gz" \
        --zone="${ZONE}" --project="${PROJECT_ID}" --quiet \
        --scp-flag="-o StrictHostKeyChecking=no"

    echo "Extracting code to /opt/voice-agent (backup, wipe, restore data)..."
    gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" \
        --command "sudo mkdir -p /opt/voice-agent; sudo cp -a /opt/voice-agent/voice_agent.db /tmp/va.db.bak 2>/dev/null || true; sudo cp -a /opt/voice-agent/.env /tmp/va.env.bak 2>/dev/null || true; sudo rm -rf /opt/voice-agent/*; sudo tar -xzf /tmp/voice-agent-src.tar.gz -C /opt/voice-agent; sudo mv /tmp/va.db.bak /opt/voice-agent/voice_agent.db 2>/dev/null || true; sudo mv /tmp/va.env.bak /opt/voice-agent/.env 2>/dev/null || true; sudo chown -R voiceagent:voiceagent /opt/voice-agent 2>/dev/null || sudo chown -R root:root /opt/voice-agent; sudo chmod 600 /opt/voice-agent/.env 2>/dev/null || true; test -f /opt/voice-agent/app/main.py && echo EXTRACT_OK || echo EXTRACT_FAIL" \
        --quiet --ssh-flag="-o StrictHostKeyChecking=no"

    echo "SYNC COMPLETE — code uploaded."
}

phase_setup() {
    require_project
    require_auth

    echo "Running bootstrap.sh on ${VM_NAME} (installs deps, Caddy, systemd)..."
    echo "This takes a few minutes. Watch the setup log:"
    echo "  gcloud compute ssh ${VM_NAME} --zone=${ZONE} -- 'sudo tail -f /var/log/voice-agent-setup.log'"
    echo ""

    gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" \
        --command "sudo bash /opt/voice-agent/deploy/bootstrap.sh" \
        --quiet --ssh-flag="-o StrictHostKeyChecking=no"
}

# ============================================================
# Main
# ============================================================
case "${PHASE}" in
    provision)
        phase_provision
        ;;
    sync)
        phase_sync
        ;;
    setup)
        phase_setup
        ;;
    all)
        phase_provision
        phase_sync
        phase_setup
        ;;
    *)
        echo "Usage: $0 [provision|sync|setup|all]"
        exit 1
        ;;
esac

get_ip 2>/dev/null || true
if [ -n "${IP_ADDRESS:-}" ]; then
    echo ""
    echo "=============================================="
    echo " DEPLOYMENT SUMMARY"
    echo "=============================================="
    echo "VM           : ${VM_NAME} (zone ${ZONE})"
    echo "Static IP    : ${IP_ADDRESS}"
    echo "Domain       : https://${DOMAIN}  (Caddy auto-HTTPS)"
    echo ""
    echo "NEXT STEP — point DNS at the VM (required for HTTPS/wss):"
    echo "  In Cloudflare DNS for cytieq.com add an A record:"
    echo "    tac  A  ${IP_ADDRESS}   (DNS only / grey cloud)"
    echo "  Caddy obtains a free Let's Encrypt certificate automatically once"
    echo "  the record resolves. Then verify:  curl https://${DOMAIN}/health"
    echo ""
    echo "Twilio console: point the voice webhook to https://${DOMAIN}/twilio/voice"
    echo "=============================================="
fi
