"""Creator-owned profile and web-call analytics endpoints."""

from typing import Annotated
from urllib.parse import urlparse

import httpx
import structlog
from fastapi import APIRouter, Cookie, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.auth import SESSION_COOKIE, public_user, require_creator
from app.core.settings import get_settings
from app.core.languages import LANGUAGES, normalise_languages
from app.db.database import get_database


router = APIRouter(prefix="/api/creator", tags=["Creator dashboard"])
log = structlog.get_logger()

VOICE_CONSENT_VERSION = "creator-voice-v1-2026-08-24"
VOICE_LANGUAGES = set(LANGUAGES)
VOICE_CONTENT_TYPES = {
    "audio/aac", "audio/flac", "audio/m4a", "audio/mp3", "audio/mp4", "audio/mpeg",
    "audio/ogg", "audio/opus", "audio/wav", "audio/webm",
    "audio/vnd.wave", "audio/x-flac", "audio/x-m4a", "audio/x-wav",
}
VOICE_EXTENSIONS = {
    ".aac", ".flac", ".m4a", ".mp3", ".oga", ".ogg", ".opus", ".wav", ".webm",
}


class CreatorProfileUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    tagline: str = Field(default="", max_length=140)
    bio: str = Field(default="", max_length=2000)
    avatar_url: str = Field(default="", max_length=500)
    system_prompt: str = Field(default="", max_length=4000)
    primary_language: str = Field(default="en", min_length=2, max_length=5)
    supported_languages: list[str] = Field(default_factory=lambda: ["en"], max_length=12)


class PublishUpdate(BaseModel):
    is_published: bool


def _profile_payload(profile: dict) -> dict:
    settings = get_settings()
    has_custom_voice = bool(profile["voice_id"])
    voice_status = "custom" if has_custom_voice else (
        "default" if settings.cartesia_voice_id else "unconfigured"
    )
    return {
        "id": profile["id"],
        "name": profile["name"],
        "tagline": profile["tagline"],
        "bio": profile["bio"],
        "avatar_url": profile["avatar_url"],
        "system_prompt": profile["system_prompt"],
        "is_published": bool(profile["is_published"]),
        "review_status": profile["review_status"],
        "primary_language": profile["primary_language"],
        "supported_languages": profile["supported_languages"],
        "call_enabled": bool(profile["call_enabled"]),
        "max_call_seconds": profile["max_call_seconds"],
        "price_per_minute_paise": profile["price_per_minute_paise"],
        "voice_ready": bool(
            profile["voice_id"] or settings.cartesia_voice_id
        ),
        "voice": {
            "status": voice_status,
            "id_suffix": profile["voice_id"][-8:] if has_custom_voice else "",
            "clone_available": bool(
                settings.cartesia_api_key
                and profile["review_status"] == "approved"
            ),
        },
        "created_at": profile["created_at"],
    }


def _avatar_url(value: str) -> str:
    clean = value.strip()
    if not clean:
        return ""
    parsed = urlparse(clean)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=422,
            detail="Profile photo must be a complete http or https URL.",
        )
    return clean


@router.get("/dashboard")
async def creator_dashboard(
    tac_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> dict:
    user = require_creator(tac_session)
    profile = get_database().get_creator_profile(user["id"])
    if profile is None:
        raise HTTPException(status_code=404, detail="Creator profile not found.")
    summary = get_database().creator_call_summary(profile["id"], limit=20)
    return {
        "user": public_user(user),
        "profile": _profile_payload(profile),
        "analytics": summary,
    }


@router.put("/profile")
async def update_creator_profile(
    payload: CreatorProfileUpdate,
    tac_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> dict:
    user = require_creator(tac_session)
    try:
        primary_language, supported_languages = normalise_languages(
            payload.primary_language, payload.supported_languages
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    profile = get_database().update_creator_profile(
        owner_user_id=user["id"],
        name=payload.name.strip(),
        tagline=payload.tagline.strip(),
        bio=payload.bio.strip(),
        avatar_url=_avatar_url(payload.avatar_url),
        system_prompt=payload.system_prompt.strip(),
        primary_language=primary_language,
        supported_languages=supported_languages,
    )
    return {"profile": _profile_payload(profile)}


@router.post("/voice/clone")
async def clone_creator_voice(
    clip: Annotated[UploadFile, File()],
    language: Annotated[str, Form()] = "en",
    rights_confirmed: Annotated[bool, Form()] = False,
    synthetic_acknowledged: Annotated[bool, Form()] = False,
    tac_session: Annotated[
        str | None,
        Cookie(alias=SESSION_COOKIE),
    ] = None,
) -> dict:
    """Clone the signed-in creator's authorised voice and activate it."""

    user = require_creator(tac_session)
    database = get_database()
    profile = database.get_creator_profile(user["id"])
    if profile is None:
        raise HTTPException(status_code=404, detail="Creator profile not found.")
    if profile["review_status"] != "approved":
        raise HTTPException(
            status_code=403,
            detail="Identity review must be approved before voice cloning is unlocked.",
        )
    if not rights_confirmed or not synthetic_acknowledged:
        raise HTTPException(
            status_code=422,
            detail="Confirm both voice permissions before creating a clone.",
        )

    clean_language = language.strip().lower()
    if clean_language not in VOICE_LANGUAGES:
        raise HTTPException(status_code=422, detail="That voice language is not supported yet.")

    content_type = (clip.content_type or "").lower()
    filename = (clip.filename or "").lower()
    has_audio_extension = any(filename.endswith(extension) for extension in VOICE_EXTENSIONS)
    if content_type not in VOICE_CONTENT_TYPES and not has_audio_extension:
        raise HTTPException(
            status_code=422,
            detail="Upload a WAV, MP3, M4A, FLAC, OGG, AAC, Opus, or WebM audio file.",
        )
    audio_bytes = await clip.read(20 * 1024 * 1024 + 1)
    if len(audio_bytes) < 10_000:
        raise HTTPException(status_code=422, detail="The voice sample is too short or empty.")
    if len(audio_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="The voice sample must be smaller than 20 MB.")

    settings = get_settings()
    api_key = settings.cartesia_api_key.strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="Voice cloning is not configured yet.")

    voice_name = f"{profile['name']} · TAC"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.cartesia.ai/voices/clone",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Cartesia-Version": "2026-03-01",
                },
                data={
                    "name": voice_name,
                    "language": clean_language,
                    "description": "Creator-authorised voice for TAC conversations.",
                },
                files={
                    "clip": (
                        clip.filename or "creator-voice",
                        audio_bytes,
                        content_type,
                    ),
                },
            )
            response.raise_for_status()
            cloned = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.exception(
            "creator_voice_clone_failed",
            creator_id=profile["id"],
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="The voice provider could not create this clone. Try a clean 5–30 second sample.",
        ) from exc

    voice_id = str(cloned.get("id", "")).strip()
    if not voice_id:
        raise HTTPException(status_code=502, detail="The voice provider returned an invalid clone.")

    profile = database.activate_creator_voice_clone(
        owner_user_id=user["id"],
        provider_voice_id=voice_id,
        language=clean_language,
        consent_version=VOICE_CONSENT_VERSION,
        rights_confirmed=True,
        synthetic_acknowledged=True,
    )
    log.info("creator_voice_clone_activated", creator_id=profile["id"])
    return {
        "message": "Your cloned voice is active for new conversations.",
        "profile": _profile_payload(profile),
    }


@router.patch("/publish")
async def publish_creator_profile(
    payload: PublishUpdate,
    tac_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> dict:
    user = require_creator(tac_session)
    database = get_database()
    profile = database.get_creator_profile(user["id"])
    if profile is None:
        raise HTTPException(status_code=404, detail="Creator profile not found.")

    if payload.is_published:
        if profile["review_status"] != "approved":
            raise HTTPException(
                status_code=403,
                detail="This creator profile must be approved before it can go live.",
            )
        missing = []
        if len(profile["tagline"].strip()) < 8:
            missing.append("a clear tagline")
        if len(profile["bio"].strip()) < 40:
            missing.append("a bio of at least 40 characters")
        if missing:
            raise HTTPException(
                status_code=422,
                detail="Before publishing, add " + " and ".join(missing) + ".",
            )

    profile = database.set_creator_published(
        user["id"], payload.is_published
    )
    return {"profile": _profile_payload(profile)}


@router.post("/review")
async def submit_creator_review(
    tac_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> dict:
    user = require_creator(tac_session)
    database = get_database()
    profile = database.get_creator_profile(user["id"])
    if profile is None:
        raise HTTPException(status_code=404, detail="Creator profile not found.")

    missing = []
    if len(profile["tagline"].strip()) < 8:
        missing.append("a clear tagline")
    if len(profile["bio"].strip()) < 40:
        missing.append("a bio of at least 40 characters")
    if missing:
        raise HTTPException(
            status_code=422,
            detail="Before requesting review, add " + " and ".join(missing) + ".",
        )

    if profile["review_status"] == "approved":
        return {"profile": _profile_payload(profile)}

    profile = database.set_creator_review_status(profile["id"], "pending")
    assert profile is not None
    return {"profile": _profile_payload(profile)}
