"""Production Studio APIs for operating creators, users, calls and intake."""

import json
from typing import Annotated, Any

import httpx
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.influencers import require_admin
from app.core.languages import LANGUAGES, normalise_languages
from app.core.settings import get_settings
from app.db.database import get_database

router = APIRouter(
    prefix="/api/admin",
    tags=["Studio"],
    dependencies=[Depends(require_admin)],
)
log = structlog.get_logger()

VOICE_CONTENT_TYPES = {
    "audio/aac", "audio/flac", "audio/m4a", "audio/mp3", "audio/mp4",
    "audio/mpeg", "audio/ogg", "audio/opus", "audio/wav", "audio/webm",
    "audio/vnd.wave", "audio/x-flac", "audio/x-m4a", "audio/x-wav",
}
VOICE_EXTENSIONS = {
    ".aac", ".flac", ".m4a", ".mp3", ".oga", ".ogg", ".opus",
    ".wav", ".webm",
}


class CreatorAdminUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    tagline: str = Field(default="", max_length=140)
    bio: str = Field(default="", max_length=2000)
    avatar_url: str = Field(default="", max_length=500)
    system_prompt: str = Field(default="", max_length=4000)
    primary_language: str = Field(default="en", min_length=2, max_length=5)
    supported_languages: list[str] = Field(default_factory=lambda: ["en"], max_length=12)
    call_enabled: bool = True
    max_call_seconds: int = Field(default=300, ge=60, le=3600)
    price_per_minute_paise: int = Field(default=0, ge=0, le=1_000_000)
    is_published: bool = False
    review_status: str = Field(default="pending", min_length=6, max_length=8)


class UserAdminUpdate(BaseModel):
    role: str = Field(min_length=4, max_length=12)
    is_active: bool


class SubmissionStatusUpdate(BaseModel):
    status: str = Field(min_length=3, max_length=20)


class TopicCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=500)


class KnowledgeCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    content: str = Field(min_length=20, max_length=12_000)
    language: str = Field(default="en", min_length=2, max_length=5)


def _record(action: str, entity_type: str, entity_id: object, summary: str) -> None:
    get_database().record_admin_action(
        action, entity_type, str(entity_id), summary
    )


@router.get("/overview")
async def overview() -> dict[str, Any]:
    settings = get_settings()
    return {
        "summary": get_database().studio_overview(),
        "service": {
            "environment": settings.app_env,
            "call_mode": settings.call_mode,
            "stt_ready": bool(settings.elevenlabs_api_key),
            "llm_ready": bool(settings.groq_api_key),
            "tts_ready": bool(settings.cartesia_api_key and settings.cartesia_voice_id),
        },
    }


@router.get("/languages")
async def languages() -> dict[str, Any]:
    return {
        "languages": [
            {"code": code, "name": name} for code, name in LANGUAGES.items()
        ]
    }


@router.get("/creators")
async def creators(limit: int = 200) -> dict[str, Any]:
    return {"creators": get_database().list_all_influencers(limit)}


@router.post("/creators", status_code=201)
async def create_creator(payload: CreatorAdminUpdate) -> dict[str, Any]:
    review_status = payload.review_status.strip().lower()
    if review_status not in {"pending", "approved", "rejected"}:
        raise HTTPException(status_code=422, detail="Invalid review status.")
    try:
        primary, supported = normalise_languages(
            payload.primary_language, payload.supported_languages
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if payload.is_published and review_status != "approved":
        raise HTTPException(
            status_code=422,
            detail="Approve the creator before publishing the profile.",
        )
    creator = get_database().create_influencer(
        name=payload.name.strip(),
        tagline=payload.tagline.strip(),
        bio=payload.bio.strip(),
        avatar_url=payload.avatar_url.strip(),
        voice_id="",
        system_prompt=payload.system_prompt.strip(),
        is_published=payload.is_published,
        review_status=review_status,
        primary_language=primary,
        supported_languages=supported,
        call_enabled=payload.call_enabled,
        max_call_seconds=payload.max_call_seconds,
        price_per_minute_paise=payload.price_per_minute_paise,
    )
    _record("creator.created", "creator", creator["id"], creator["name"])
    return {"creator": creator}


@router.patch("/creators/{influencer_id}")
async def update_creator(
    influencer_id: int, payload: CreatorAdminUpdate
) -> dict[str, Any]:
    review_status = payload.review_status.strip().lower()
    if review_status not in {"pending", "approved", "rejected"}:
        raise HTTPException(status_code=422, detail="Invalid review status.")
    try:
        primary, supported = normalise_languages(
            payload.primary_language, payload.supported_languages
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if payload.is_published and review_status != "approved":
        raise HTTPException(
            status_code=422,
            detail="Approve the creator before publishing the profile.",
        )
    creator = get_database().update_influencer_admin(
        influencer_id,
        name=payload.name.strip(),
        tagline=payload.tagline.strip(),
        bio=payload.bio.strip(),
        avatar_url=payload.avatar_url.strip(),
        system_prompt=payload.system_prompt.strip(),
        primary_language=primary,
        supported_languages=supported,
        call_enabled=payload.call_enabled,
        max_call_seconds=payload.max_call_seconds,
        price_per_minute_paise=payload.price_per_minute_paise,
        is_published=payload.is_published,
        review_status=review_status,
    )
    if creator is None:
        raise HTTPException(status_code=404, detail="Creator not found.")
    _record("creator.updated", "creator", influencer_id, creator["name"])
    return {"creator": creator}


@router.post("/creators/{influencer_id}/voice")
async def upload_creator_voice(
    influencer_id: int,
    clip: Annotated[UploadFile, File()],
    language: Annotated[str, Form()] = "en",
    rights_confirmed: Annotated[bool, Form()] = False,
    synthetic_acknowledged: Annotated[bool, Form()] = False,
) -> dict[str, Any]:
    creator = get_database().get_influencer(influencer_id)
    if creator is None:
        raise HTTPException(status_code=404, detail="Creator not found.")
    if not rights_confirmed or not synthetic_acknowledged:
        raise HTTPException(
            status_code=422,
            detail="Confirm voice rights and synthetic-use disclosure.",
        )
    try:
        clean_language, _ = normalise_languages(language, [language])
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    content_type = (clip.content_type or "").lower()
    filename = (clip.filename or "").lower()
    if content_type not in VOICE_CONTENT_TYPES and not any(
        filename.endswith(extension) for extension in VOICE_EXTENSIONS
    ):
        raise HTTPException(status_code=422, detail="Upload a supported audio file.")
    audio_bytes = await clip.read(20 * 1024 * 1024 + 1)
    if len(audio_bytes) < 10_000:
        raise HTTPException(status_code=422, detail="Voice sample is too short.")
    if len(audio_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Voice sample exceeds 20 MB.")
    api_key = get_settings().cartesia_api_key.strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="Voice cloning is not configured.")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.cartesia.ai/voices/clone",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Cartesia-Version": "2026-03-01",
                },
                data={
                    "name": f"{creator['name']} · TAC",
                    "language": clean_language,
                    "description": "Rights-confirmed creator voice for TAC.",
                },
                files={
                    "clip": (
                        clip.filename or "creator-voice",
                        audio_bytes,
                        content_type or "application/octet-stream",
                    )
                },
            )
            response.raise_for_status()
            cloned = response.json()
    except (httpx.HTTPError, ValueError) as error:
        log.exception(
            "admin_voice_clone_failed",
            influencer_id=influencer_id,
            error_type=type(error).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="The voice provider could not create this clone.",
        ) from error
    voice_id = str(cloned.get("id", "")).strip()
    if not voice_id:
        raise HTTPException(status_code=502, detail="Voice provider returned no voice ID.")
    updated = get_database().activate_admin_voice(
        influencer_id,
        provider_voice_id=voice_id,
        language=clean_language,
        rights_confirmed=True,
        synthetic_acknowledged=True,
    )
    _record("voice.cloned", "creator", influencer_id, clean_language)
    return {"creator": updated, "voice_id_suffix": voice_id[-8:]}


@router.get("/creators/{influencer_id}/knowledge")
async def creator_knowledge(influencer_id: int) -> dict[str, Any]:
    if get_database().get_influencer(influencer_id) is None:
        raise HTTPException(status_code=404, detail="Creator not found.")
    return {
        "topics": get_database().list_creator_topics(influencer_id),
        "knowledge": get_database().list_creator_knowledge(influencer_id),
    }


@router.post("/creators/{influencer_id}/topics", status_code=201)
async def create_topic(influencer_id: int, payload: TopicCreate) -> dict[str, Any]:
    if get_database().get_influencer(influencer_id) is None:
        raise HTTPException(status_code=404, detail="Creator not found.")
    topic = get_database().create_creator_topic(
        influencer_id,
        name=payload.name.strip(),
        description=payload.description.strip(),
    )
    _record("topic.created", "creator", influencer_id, topic["name"])
    return {"topic": topic}


@router.delete("/creators/{influencer_id}/topics/{topic_id}")
async def delete_topic(influencer_id: int, topic_id: int) -> dict[str, bool]:
    if not get_database().delete_creator_topic(influencer_id, topic_id):
        raise HTTPException(status_code=404, detail="Topic not found.")
    _record("topic.deleted", "creator", influencer_id, str(topic_id))
    return {"deleted": True}


@router.post("/creators/{influencer_id}/knowledge", status_code=201)
async def create_knowledge(
    influencer_id: int, payload: KnowledgeCreate
) -> dict[str, Any]:
    if get_database().get_influencer(influencer_id) is None:
        raise HTTPException(status_code=404, detail="Creator not found.")
    try:
        language, _ = normalise_languages(payload.language, [payload.language])
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    record = get_database().create_creator_knowledge(
        influencer_id,
        title=payload.title.strip(),
        content=payload.content.strip(),
        language=language,
    )
    _record("knowledge.created", "creator", influencer_id, record["title"])
    return {"knowledge": record}


@router.delete("/creators/{influencer_id}/knowledge/{knowledge_id}")
async def delete_knowledge(
    influencer_id: int, knowledge_id: int
) -> dict[str, bool]:
    if not get_database().delete_creator_knowledge(influencer_id, knowledge_id):
        raise HTTPException(status_code=404, detail="Knowledge source not found.")
    _record("knowledge.deleted", "creator", influencer_id, str(knowledge_id))
    return {"deleted": True}


@router.get("/users")
async def users(limit: int = 200) -> dict[str, Any]:
    return {"users": get_database().list_users(limit)}


@router.patch("/users/{user_id}")
async def update_user(user_id: int, payload: UserAdminUpdate) -> dict[str, Any]:
    role = payload.role.strip().lower()
    if role not in {"user", "creator", "admin"}:
        raise HTTPException(status_code=422, detail="Invalid account role.")
    user = get_database().update_user_admin(
        user_id, role=role, is_active=payload.is_active
    )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    user.pop("password_hash", None)
    _record("user.updated", "user", user_id, f"{role}; active={payload.is_active}")
    return {"user": user}


@router.get("/calls")
async def calls(limit: int = 200) -> dict[str, Any]:
    return {"calls": get_database().list_web_calls(limit)}


@router.get("/submissions")
async def submissions(limit: int = 200) -> dict[str, Any]:
    rows = get_database().list_public_submissions(limit)
    for row in rows:
        try:
            row["metadata"] = json.loads(row.pop("metadata_json"))
        except (TypeError, ValueError):
            row["metadata"] = {}
    return {"submissions": rows}


@router.patch("/submissions/{submission_id}")
async def update_submission(
    submission_id: int, payload: SubmissionStatusUpdate
) -> dict[str, Any]:
    status = payload.status.strip().lower()
    if status not in {"new", "in_progress", "resolved", "spam"}:
        raise HTTPException(status_code=422, detail="Invalid submission status.")
    if not get_database().set_submission_status(submission_id, status):
        raise HTTPException(status_code=404, detail="Submission not found.")
    _record("submission.updated", "submission", submission_id, status)
    return {"ok": True, "status": status}


@router.get("/audit-log")
async def audit_log(limit: int = 100) -> dict[str, Any]:
    return {"events": get_database().list_admin_actions(limit)}
