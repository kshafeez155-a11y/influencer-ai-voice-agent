"""Public intake endpoints for support, safety, and creator interest."""

import json
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.api.influencers import require_admin
from app.core.settings import get_settings
from app.db.database import get_database

router = APIRouter(prefix="/api", tags=["Public submissions"])

_KINDS = {
    "creator_application",
    "creator_request",
    "report",
    "contact",
    "data_request",
    "call_feedback",
}
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class PublicSubmissionCreate(BaseModel):
    kind: str = Field(min_length=2, max_length=40)
    name: str = Field(default="", max_length=100)
    email: str = Field(default="", max_length=254)
    phone: str = Field(default="", max_length=30)
    subject: str = Field(default="", max_length=160)
    message: str = Field(default="", max_length=5000)
    metadata: dict[str, Any] = Field(default_factory=dict)


async def require_configured_admin(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Never expose intake PII when an admin token has not been configured."""

    if not get_settings().admin_token.strip():
        raise HTTPException(
            status_code=503,
            detail="Admin access is disabled until ADMIN_TOKEN is configured.",
        )
    await require_admin(authorization)


@router.post("/public-submissions", status_code=201)
async def create_public_submission(
    payload: PublicSubmissionCreate,
) -> dict[str, Any]:
    """Store one public request without exposing private data back to clients."""

    kind = payload.kind.strip().lower()
    email = payload.email.strip().lower()
    message = payload.message.strip()

    if kind not in _KINDS:
        raise HTTPException(status_code=422, detail="Unknown submission type.")

    if email and not _EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")

    if not email and not payload.phone.strip():
        raise HTTPException(
            status_code=422,
            detail="Add an email address or phone number so we can follow up.",
        )

    if not message:
        raise HTTPException(status_code=422, detail="Tell us a little more before sending.")

    metadata_json = json.dumps(payload.metadata, ensure_ascii=True)[:4000]
    row = get_database().create_public_submission(
        kind=kind,
        name=payload.name.strip(),
        email=email,
        phone=payload.phone.strip(),
        subject=payload.subject.strip(),
        message=message,
        metadata_json=metadata_json,
    )

    return {
        "ok": True,
        "request_id": row["id"],
        "message": "We received your request.",
    }


@router.get(
    "/public-submissions",
    dependencies=[Depends(require_configured_admin)],
)
async def list_public_submissions(limit: int = 50) -> dict[str, Any]:
    """Return private intake records to an authenticated Studio operator."""

    rows = get_database().list_public_submissions(limit=limit)
    for row in rows:
        try:
            row["metadata"] = json.loads(row.pop("metadata_json"))
        except (TypeError, ValueError):
            row["metadata"] = {}
            row.pop("metadata_json", None)
    return {"submissions": rows}
