"""Public, bounded admission endpoint for web voice calls."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.settings import get_settings
from app.db.database import get_database
from app.voice.call_tokens import issue_call_token

router = APIRouter(prefix="/api", tags=["Voice admission"])


class CallTokenRequest(BaseModel):
    influencer_id: int = Field(gt=0)


@router.post("/web-call-token")
async def web_call_token(payload: CallTokenRequest, request: Request) -> dict:
    creator = get_database().get_influencer(payload.influencer_id)
    if (
        creator is None
        or not creator.get("is_published")
        or not creator.get("call_enabled")
    ):
        raise HTTPException(status_code=404, detail="Creator is not available for calls.")
    settings = get_settings()
    secret = (settings.web_call_signing_secret or settings.admin_token).strip()
    if not secret:
        raise HTTPException(status_code=503, detail="Web-call admission is not configured.")
    client_ip = request.client.host if request.client else "unknown"
    return {
        "token": issue_call_token(
            influencer_id=creator["id"], client_ip=client_ip, secret=secret
        ),
        "expires_in": 120,
        "max_call_seconds": min(
            settings.web_call_max_seconds, creator["max_call_seconds"]
        ),
    }
