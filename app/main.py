import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from urllib.parse import urlparse

from app.api.influencers import router as influencers_router
from app.api.auth import router as auth_router
from app.api.creator import router as creator_router
from app.api.admin import router as admin_router
from app.api.voice import router as voice_router
from app.api.public_submissions import router as public_submissions_router
from app.api.twilio_routes import router as twilio_router
from app.core.settings import get_settings
from app.db.database import get_database
from app.telephony.twilio_media import (
    handle_twilio_media_stream,
)
from app.voice.mobile_media import (
    handle_mobile_media_stream,
)


def _configure_logging(log_level: str) -> None:
    """Set up structlog with console-friendly output."""

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(
                log_level.upper(), logging.INFO
            ),
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


settings = get_settings()
_configure_logging(settings.log_level)

log = structlog.get_logger()


def _check_startup_config() -> None:
    """Log which provider integrations are ready vs missing."""

    checks: list[tuple[str, str, bool]] = [
        ("Twilio", "TWILIO_ACCOUNT_SID", bool(settings.twilio_account_sid)),
        ("Twilio", "TWILIO_AUTH_TOKEN", bool(settings.twilio_auth_token)),
        ("Twilio", "TWILIO_PHONE_NUMBER", bool(settings.twilio_phone_number)),
        ("Twilio", "PUBLIC_BASE_URL", bool(settings.public_base_url)),
        ("ElevenLabs STT", "ELEVENLABS_API_KEY", bool(settings.elevenlabs_api_key)),
        ("Groq LLM", "GROQ_API_KEY", bool(settings.groq_api_key)),
        ("Cartesia TTS", "CARTESIA_API_KEY", bool(settings.cartesia_api_key)),
        ("Cartesia TTS", "CARTESIA_VOICE_ID", bool(settings.cartesia_voice_id)),
    ]

    missing: list[str] = []

    for provider, key, ok in checks:
        if not ok:
            missing.append(f"{provider} ({key})")

    if missing:
        log.warning(
            "missing_config",
            missing=missing,
            hint="Voice calls will fail until these are set.",
        )
    else:
        log.info("config_ok", message="All provider keys configured.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise SQLite, validate config, seed personas on first boot."""

    _check_startup_config()
    get_database()
    log.info(
        "startup",
        app=settings.app_name,
        env=settings.app_env,
        port=settings.app_port,
    )
    yield


is_production = settings.app_env.strip().lower() == "production"
app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json",
)

public_origin = settings.public_base_url.strip().rstrip("/")
cors_origins = [public_origin] if public_origin else [
    "http://127.0.0.1:8080", "http://localhost:8080"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

public_host = urlparse(public_origin).hostname if public_origin else None
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[host for host in [public_host, "localhost", "127.0.0.1", "testserver"] if host],
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), geolocation=(), payment=()"
    )
    if is_production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


app.include_router(twilio_router)
app.include_router(influencers_router)
app.include_router(public_submissions_router)
app.include_router(auth_router)
app.include_router(creator_router)
app.include_router(admin_router)
app.include_router(voice_router)



@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "service": settings.app_name,
        "environment": settings.app_env,
    }


@app.get("/info")
async def info() -> dict[str, object]:
    """Non-secret public info consumed by the frontend."""

    web_calls_configured = bool(
        settings.call_mode.strip().lower() == "web"
        and settings.elevenlabs_api_key
        and settings.groq_api_key
        and settings.cartesia_api_key
        and settings.cartesia_voice_id
        and (settings.web_call_signing_secret or settings.admin_token)
    )

    return {
        "app_name": settings.app_name,
        "environment": settings.app_env,
        "public_base_url": settings.public_base_url,
        "pipeline": {
            "stt": settings.elevenlabs_stt_model,
            "llm": settings.groq_model,
            "tts": settings.cartesia_model,
        },
        "voice_id": settings.cartesia_voice_id,
        "twilio_configured": bool(
            settings.twilio_account_sid
            and settings.twilio_auth_token
            and settings.twilio_phone_number
        ),
        "call_mode": settings.call_mode.strip().lower(),
        "web_calls_configured": web_calls_configured,
        "test_number_configured": bool(settings.test_to_phone_number),
    }


@app.websocket("/twilio/media-stream")
async def twilio_media_stream(
    websocket: WebSocket,
) -> None:
    await handle_twilio_media_stream(websocket)


@app.websocket("/ws/voice-chat")
async def mobile_voice_chat(
    websocket: WebSocket,
) -> None:
    await handle_mobile_media_stream(websocket)


from pathlib import Path
from fastapi.staticfiles import StaticFiles

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
