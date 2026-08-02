from fastapi import FastAPI, WebSocket

from app.api.twilio_routes import router as twilio_router
from app.core.settings import get_settings
from app.telephony.twilio_media import (
    handle_twilio_media_stream,
)


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
)


app.include_router(twilio_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "status": "running",
    }


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "service": settings.app_name,
        "environment": settings.app_env,
    }


@app.websocket("/twilio/media-stream")
async def twilio_media_stream(
    websocket: WebSocket,
) -> None:
    await handle_twilio_media_stream(websocket)