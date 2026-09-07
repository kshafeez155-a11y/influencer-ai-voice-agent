"""Public + admin API for influencers and call requests.

Public endpoints:
    GET  /api/influencers           list personas
    GET  /api/influencers/{id}      one persona
    POST /api/call-requests         request a call from an influencer

Admin endpoints require Authorization: Bearer <ADMIN_TOKEN>.
    POST   /api/influencers         create a persona
    DELETE /api/influencers/{id}    remove a persona
    GET    /api/call-requests       recent call attempts
"""

import re
from typing import Annotated, Any
from urllib.parse import quote

import structlog
from cartesia import Cartesia
from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.core.settings import get_settings
from app.db.database import get_database

log = structlog.get_logger()

router = APIRouter(
    prefix="/api",
    tags=["Influencers"],
)

_PHONE_PATTERN = re.compile(r"^\+?[0-9\s().-]{7,20}$")


# ---------------------------------------------------------
# Schemas
# ---------------------------------------------------------

class InfluencerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    tagline: str = Field(default="", max_length=140)
    bio: str = Field(default="", max_length=2000)
    avatar_url: str = Field(default="", max_length=500)
    voice_id: str = Field(default="", max_length=80)
    system_prompt: str = Field(default="", max_length=4000)


class CallRequestCreate(BaseModel):
    influencer_id: int = Field(gt=0)
    user_name: str = Field(default="", max_length=80)
    user_phone: str = Field(min_length=7, max_length=20)


class CreatorReviewUpdate(BaseModel):
    decision: str = Field(min_length=6, max_length=8)


# ---------------------------------------------------------
# Admin auth
# ---------------------------------------------------------

async def require_admin(
    authorization: Annotated[
        str | None,
        Header(),
    ] = None,
) -> None:
    """Fail closed unless the configured admin bearer token is supplied."""

    settings = get_settings()
    token = settings.admin_token.strip()

    if not token:
        raise HTTPException(
            status_code=503,
            detail="Studio is disabled until ADMIN_TOKEN is configured.",
        )

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Admin token required.",
        )

    scheme, _, supplied = authorization.partition(" ")

    if scheme.lower() != "bearer" or supplied.strip() != token:
        raise HTTPException(
            status_code=401,
            detail="Invalid admin token.",
        )


# ---------------------------------------------------------
# Voice cloning (Cartesia)
# ---------------------------------------------------------

@router.post(
    "/voice-clone",
    dependencies=[Depends(require_admin)],
)
async def clone_voice(
    clip: UploadFile = File(...),
    name: str = Form(...),
    language: str = Form(default="en"),
) -> dict[str, str]:
    """Clone a voice from an uploaded audio clip via Cartesia."""

    settings = get_settings()
    api_key = settings.cartesia_api_key.strip()

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="CARTESIA_API_KEY is not configured.",
        )

    audio_bytes = await clip.read()

    if len(audio_bytes) == 0:
        raise HTTPException(
            status_code=422,
            detail="Audio file is empty.",
        )

    if len(audio_bytes) > 20 * 1024 * 1024:
        raise HTTPException(
            status_code=422,
            detail="Audio file too large (max 20 MB).",
        )

    try:
        client = Cartesia(api_key=api_key)
        voice = client.voices.clone(
            clip=audio_bytes,
            name=name.strip(),
            language=language.strip(),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Cartesia clone failed: {exc}",
        )

    return {"voice_id": voice.id, "name": voice.name}


@router.get(
    "/voices",
    dependencies=[Depends(require_admin)],
)
async def list_voices() -> dict[str, Any]:
    """List Cartesia voices owned by this account."""

    settings = get_settings()
    api_key = settings.cartesia_api_key.strip()

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="CARTESIA_API_KEY is not configured.",
        )

    try:
        client = Cartesia(api_key=api_key)
        page = client.voices.list(is_owner=True, limit=100)
        voices = [{"id": v.id, "name": v.name} for v in page.data]
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Cartesia error: {exc}",
        )

    return {"voices": voices}


# ---------------------------------------------------------
# Influencers
# ---------------------------------------------------------

@router.get("/influencers")
async def list_influencers() -> dict[str, Any]:
    return {
        "influencers": get_database().list_influencers(),
    }


@router.get("/influencers/{influencer_id}")
async def get_influencer(influencer_id: int) -> dict[str, Any]:
    influencer = get_database().get_influencer(influencer_id)

    if influencer is None or not influencer.get("is_published"):
        raise HTTPException(
            status_code=404,
            detail="Influencer not found.",
        )

    # Never expose the persona's system prompt through the public API.
    influencer["is_demo"] = influencer.get("owner_user_id") is None
    influencer.pop("system_prompt", None)
    influencer.pop("owner_user_id", None)
    influencer.pop("is_published", None)
    influencer.pop("review_status", None)

    return {"influencer": influencer}


@router.post(
    "/influencers",
    dependencies=[Depends(require_admin)],
    status_code=201,
)
async def create_influencer(
    payload: InfluencerCreate,
) -> dict[str, Any]:
    influencer = get_database().create_influencer(
        name=payload.name.strip(),
        tagline=payload.tagline.strip(),
        bio=payload.bio.strip(),
        avatar_url=payload.avatar_url.strip(),
        voice_id=payload.voice_id.strip(),
        system_prompt=payload.system_prompt.strip(),
    )

    return {"influencer": influencer}


@router.delete(
    "/influencers/{influencer_id}",
    dependencies=[Depends(require_admin)],
)
async def delete_influencer(influencer_id: int) -> dict[str, bool]:
    deleted = get_database().delete_influencer(influencer_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Influencer not found.",
        )

    return {"deleted": True}


@router.get(
    "/creator-reviews",
    dependencies=[Depends(require_admin)],
)
async def list_creator_reviews(limit: int = 50) -> dict[str, Any]:
    return {
        "reviews": get_database().list_creator_reviews(limit=limit),
    }


@router.patch(
    "/creator-reviews/{influencer_id}",
    dependencies=[Depends(require_admin)],
)
async def review_creator(
    influencer_id: int,
    payload: CreatorReviewUpdate,
) -> dict[str, Any]:
    decision = payload.decision.strip().lower()
    if decision not in {"approved", "rejected"}:
        raise HTTPException(
            status_code=422,
            detail="Decision must be approved or rejected.",
        )

    profile = get_database().set_creator_review_status(
        influencer_id, decision
    )
    if profile is None or profile.get("owner_user_id") is None:
        raise HTTPException(status_code=404, detail="Creator submission not found.")

    profile.pop("system_prompt", None)
    profile.pop("owner_user_id", None)
    return {"profile": profile}


# ---------------------------------------------------------
# Call requests
# ---------------------------------------------------------

@router.post("/call-requests")
async def create_call_request(
    payload: CallRequestCreate,
) -> dict[str, Any]:
    """Start an outbound Twilio call from an influencer to a number."""

    settings = get_settings()
    database = get_database()

    if settings.call_mode.strip().lower() != "twilio":
        raise HTTPException(
            status_code=503,
            detail="Phone calls are paused while web calls are active.",
        )

    influencer = database.get_influencer(payload.influencer_id)

    if influencer is None:
        raise HTTPException(
            status_code=404,
            detail="Influencer not found.",
        )

    user_name = payload.user_name.strip()
    user_phone = payload.user_phone.strip()

    if user_name and len(user_name) < 2:
        raise HTTPException(
            status_code=422,
            detail="User name is too short.",
        )

    if not _PHONE_PATTERN.match(user_phone):
        raise HTTPException(
            status_code=422,
            detail=(
                "Phone number looks invalid. Use digits with an "
                "optional + country code, e.g. +15551234567."
            ),
        )

    account_sid = settings.twilio_account_sid.strip()
    auth_token = settings.twilio_auth_token.strip()
    from_number = settings.twilio_phone_number.strip()
    public_base_url = (
        settings.public_base_url.strip().rstrip("/")
    )

    missing: list[str] = []

    if not account_sid:
        missing.append("TWILIO_ACCOUNT_SID")

    if not auth_token:
        missing.append("TWILIO_AUTH_TOKEN")

    if not from_number:
        missing.append("TWILIO_PHONE_NUMBER")

    if not public_base_url:
        missing.append("PUBLIC_BASE_URL")

    if missing:
        raise HTTPException(
            status_code=503,
            detail=(
                "Calling is not configured yet: "
                + ", ".join(missing)
            ),
        )

    voice_webhook_url = (
        f"{public_base_url}/twilio/voice"
        f"?influencer={influencer['id']}"
        f"&name={quote(user_name)}"
    )

    # Twilio wants E.164-ish digits; strip formatting before dialing.
    dial_phone = re.sub(r"[\s().-]", "", user_phone)

    call_sid = ""
    status = "requested"
    error_text = ""

    try:
        client = Client(account_sid, auth_token)

        call = client.calls.create(
            to=dial_phone,
            from_=from_number,
            url=voice_webhook_url,
            method="POST",
        )

        call_sid = call.sid
        status = call.status

        log.info(
            "outbound_call_started",
            influencer=influencer["name"],
            influencer_id=influencer["id"],
            caller=user_name or "unknown",
            call_sid=call_sid,
        )

    except TwilioRestException as error:
        status = "failed"
        error_text = error.msg or "Twilio rejected the call."

    except Exception as error:
        status = "failed"
        error_text = (
            f"{type(error).__name__}: {error}"
        )

    request_row = database.record_call_request(
        influencer_id=influencer["id"],
        user_name=user_name,
        user_phone=user_phone,
        call_sid=call_sid,
        status=status,
        error=error_text,
    )

    if status == "failed":
        raise HTTPException(
            status_code=502,
            detail=error_text,
        )

    return {
        "ok": True,
        "message": (
            f"{influencer['name']} is calling you now."
        ),
        "call_sid": call_sid,
        "status": status,
        "request_id": request_row["id"],
    }


def _mask_phone(phone: str) -> str:
    """Mask a stored phone number, keeping the prefix and suffix."""

    value = phone.strip()

    if len(value) <= 6:
        return "\u2022" * len(value)

    return (
        value[:3]
        + "\u2022" * (len(value) - 6)
        + value[-3:]
    )


@router.get(
    "/call-requests",
    dependencies=[Depends(require_admin)],
)
async def list_call_requests(
    limit: int = 20,
) -> dict[str, Any]:
    call_requests = get_database().list_call_requests(
        limit=limit,
    )

    for request in call_requests:
        request["user_phone"] = _mask_phone(
            request["user_phone"]
        )

    return {"call_requests": call_requests}
