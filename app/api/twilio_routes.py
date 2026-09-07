from urllib.parse import quote

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client
from twilio.twiml.voice_response import (
    Connect,
    Stream,
    VoiceResponse,
)

from app.core.settings import get_settings
from app.db.database import get_database
from app.api.influencers import require_admin

log = structlog.get_logger()


router = APIRouter(
    prefix="/twilio",
    tags=["Twilio"],
)


@router.post("/voice")
async def twilio_voice(
    influencer: str = "",
    name: str = "",
) -> Response:
    """Connect an inbound or outbound call to our media stream."""

    settings = get_settings()

    if settings.call_mode.strip().lower() != "twilio":
        paused_response = VoiceResponse()
        paused_response.say(
            "Phone calling is temporarily paused. Please use the web call instead."
        )
        return Response(
            content=str(paused_response),
            media_type="application/xml",
            status_code=503,
        )

    public_base_url = (
        settings.public_base_url
        .strip()
        .rstrip("/")
    )

    if not public_base_url:
        error_response = VoiceResponse()
        error_response.say(
            "The voice agent server is not configured."
        )

        return Response(
            content=str(error_response),
            media_type="application/xml",
            status_code=500,
        )

    # Optional persona: when a call webhook carries ?influencer=<id>,
    # the id is forwarded into the Stream URL so the media-stream
    # WebSocket handler can load the right voice + system prompt.
    influencer_id = influencer.strip()
    caller_name = name.strip()
    influencer_record = None

    if influencer_id:
        if influencer_id.isdigit():
            influencer_record = get_database().get_influencer(
                int(influencer_id)
            )

        if influencer_record is None:
            unavailable_response = VoiceResponse()
            unavailable_response.say(
                "The voice you requested is currently unavailable."
            )

            return Response(
                content=str(unavailable_response),
                media_type="application/xml",
            )

    websocket_base_url = public_base_url.replace(
        "https://",
        "wss://",
        1,
    )

    websocket_url = (
        f"{websocket_base_url}/twilio/media-stream"
    )

    if influencer_record is not None:
        websocket_url += (
            f"?influencer={influencer_record['id']}"
            f"&name={quote(caller_name)}"
        )

    response = VoiceResponse()

    connect = Connect()
    connect.append(
        Stream(url=websocket_url)
    )

    response.append(connect)

    return Response(
        content=str(response),
        media_type="application/xml",
    )


@router.post("/make-call", dependencies=[Depends(require_admin)])
async def make_test_call() -> dict[str, str]:
    """Ask Twilio to call the verified Indian test number."""

    settings = get_settings()

    if settings.call_mode.strip().lower() != "twilio":
        raise HTTPException(
            status_code=503,
            detail="Twilio calls are paused while web calls are active.",
        )

    account_sid = settings.twilio_account_sid.strip()
    auth_token = settings.twilio_auth_token.strip()
    from_number = settings.twilio_phone_number.strip()
    to_number = settings.test_to_phone_number.strip()

    public_base_url = (
        settings.public_base_url
        .strip()
        .rstrip("/")
    )

    missing_settings: list[str] = []

    if not account_sid:
        missing_settings.append("TWILIO_ACCOUNT_SID")

    if not auth_token:
        missing_settings.append("TWILIO_AUTH_TOKEN")

    if not from_number:
        missing_settings.append("TWILIO_PHONE_NUMBER")

    if not to_number:
        missing_settings.append("TEST_TO_PHONE_NUMBER")

    if not public_base_url:
        missing_settings.append("PUBLIC_BASE_URL")

    if missing_settings:
        raise HTTPException(
            status_code=500,
            detail=(
                "Missing configuration: "
                + ", ".join(missing_settings)
            ),
        )

    voice_webhook_url = (
        f"{public_base_url}/twilio/voice"
    )

    try:
        client = Client(
            account_sid,
            auth_token,
        )

        call = client.calls.create(
            to=to_number,
            from_=from_number,
            url=voice_webhook_url,
            method="POST",
        )

    except TwilioRestException as error:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Twilio rejected the call: "
                f"{error.msg}"
            ),
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "Could not start the call: "
                f"{type(error).__name__}: {error}"
            ),
        ) from error

    log.info(
        "test_call_requested",
        to=to_number,
        from_=from_number,
        call_sid=call.sid,
    )

    return {
        "ok": "true",
        "message": "Twilio is calling your verified number.",
        "call_sid": call.sid,
        "status": call.status,
    }
