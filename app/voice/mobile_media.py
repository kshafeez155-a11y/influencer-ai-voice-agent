import asyncio
import base64
import json
import re
import time
import threading
from collections import defaultdict, deque
from urllib.parse import urlencode

import structlog
from fastapi import WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect

from app.core.settings import get_settings
from app.auth.security import session_token_hash
from app.db.database import get_database
from app.telephony.twilio_voice_agent import compose_system_prompt
from app.voice.mobile_audio_sender import MobileAudioSender
from app.voice.voice_agent import VoiceAgent, VoiceAgentError
from app.voice.call_tokens import validate_call_token

log = structlog.get_logger()

_admission_lock = threading.Lock()
_active_calls = 0
_call_attempts: dict[str, deque[float]] = defaultdict(deque)


def _admit_call(client_ip: str, *, concurrent_limit: int, hourly_limit: int) -> str:
    """Reserve one bounded provider session or return a user-safe reason."""
    global _active_calls
    now = time.monotonic()
    cutoff = now - 3600
    with _admission_lock:
        attempts = _call_attempts[client_ip]
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        if len(attempts) >= hourly_limit:
            return "Hourly call limit reached. Try again later."
        if _active_calls >= concurrent_limit:
            return "All live call spots are busy. Try again shortly."
        attempts.append(now)
        _active_calls += 1
    return ""


def _release_call() -> None:
    global _active_calls
    with _admission_lock:
        _active_calls = max(0, _active_calls - 1)


class MobileTranscriptionError(RuntimeError):
    """Raised when mobile audio cannot be transcribed."""


def build_elevenlabs_url(model: str) -> str:
    """Create the ElevenLabs realtime STT URL for PCM 16kHz input."""

    query = urlencode({
        "model_id": model,
        "audio_format": "pcm_16000",
        "commit_strategy": "vad",
        "vad_threshold": "0.5",
        "vad_silence_threshold_secs": "0.8",
        "min_speech_duration_ms": "250",
        "min_silence_duration_ms": "250",
    })

    return (
        "wss://api.elevenlabs.io/v1/"
        f"speech-to-text/realtime?{query}"
    )


async def receive_elevenlabs_transcripts(
    elevenlabs_websocket,
    transcript_queue: asyncio.Queue[str | None],
    voice_agent: VoiceAgent,
    mobile_sender: MobileAudioSender,
) -> None:
    """
    Receive partial and committed user transcripts.

    A partial transcript while the AI is active triggers barge-in.
    """

    caller_speech_detected = False
    last_committed_key = ""
    last_committed_at = 0.0

    async for raw_message in elevenlabs_websocket:
        data = json.loads(raw_message)

        message_type = str(
            data.get("message_type", "")
        )

        if message_type == "session_started":
            log.info("stt_session_started")
            continue

        if message_type == "partial_transcript":
            text = str(
                data.get("text", "")
            ).strip()

            if text:
                log.debug("stt_partial", text=text)

                if (
                    voice_agent.can_be_interrupted()
                    and not caller_speech_detected
                ):
                    caller_speech_detected = True

                    interrupted = await voice_agent.interrupt()

                    if interrupted:
                        await mobile_sender.send_barge_in()

            continue

        # The timestamp-enriched committed event is a delayed companion to
        # committed_transcript, not a second user turn. Only the primary
        # committed event is authoritative for response generation.
        if message_type == "committed_transcript_with_timestamps":
            continue

        if message_type == "committed_transcript":
            text = str(
                data.get("text", "")
            ).strip()

            caller_speech_detected = False

            if text:
                committed_key = re.sub(
                    r"[^\w]+",
                    " ",
                    text.casefold(),
                ).strip()
                committed_at = time.monotonic()

                if (
                    committed_key == last_committed_key
                    and committed_at - last_committed_at < 6.0
                ):
                    log.info(
                        "stt_duplicate_ignored",
                        text=text,
                    )
                    continue

                last_committed_key = committed_key
                last_committed_at = committed_at

                log.info("stt_committed", text=text)

                await mobile_sender.send_user_transcript(text)

                await transcript_queue.put(text)

            continue

        if (
            message_type == "error"
            or message_type.endswith("_error")
            or message_type in {
                "auth_error",
                "quota_exceeded",
                "rate_limited",
                "unaccepted_terms",
                "input_error",
                "transcriber_error",
            }
        ):
            error_message = (
                data.get("error")
                or data.get("message")
                or str(data)
            )

            raise MobileTranscriptionError(
                f"ElevenLabs error "
                f"({message_type}): "
                f"{error_message}"
            )


async def process_user_transcripts(
    transcript_queue: asyncio.Queue[str | None],
    voice_agent: VoiceAgent,
    mobile_sender: MobileAudioSender,
) -> None:
    """Generate one AI response for each committed transcript."""

    while True:
        transcript = await transcript_queue.get()

        if transcript is None:
            return

        try:
            await mobile_sender.send_state("thinking")
            await voice_agent.respond_to_transcript(
                transcript
            )
            await mobile_sender.send_response_done()

        except Exception as error:
            log.error(
                "response_failed",
                error=str(error),
                error_type=type(error).__name__,
            )
            try:
                await mobile_sender.send_error(
                    "The AI could not answer. End the call and try again."
                )
            except Exception:
                pass


async def forward_mobile_audio(
    client_websocket: WebSocket,
    elevenlabs_websocket,
    voice_agent: VoiceAgent,
    mobile_sender: MobileAudioSender,
) -> int:
    """
    Receive audio and control messages from the mobile client,
    forward audio to ElevenLabs STT.

    Returns the number of audio packets forwarded.
    """

    packet_count = 0

    while True:
        raw_message = await client_websocket.receive_text()

        message = json.loads(raw_message)

        event = str(message.get("event", ""))

        if event == "audio":
            payload = str(message.get("data", ""))

            if payload:
                # Client sends base64-encoded PCM; forward raw
                # base64 to ElevenLabs (it expects base64).
                await elevenlabs_websocket.send(
                    json.dumps({
                        "message_type": "input_audio_chunk",
                        "audio_base_64": payload,
                        "commit": False,
                    })
                )

                packet_count += 1

                if packet_count == 1:
                    log.info("first_audio_packet_forwarded")

                if packet_count % 100 == 0:
                    log.debug(
                        "audio_packets_forwarded",
                        count=packet_count,
                    )

            continue

        if event == "stop":
            log.info("client_stopped_stream")
            break

    return packet_count


async def handle_mobile_media_stream(
    websocket: WebSocket,
) -> None:
    """Run STT, Groq, Cartesia and barge-in for one mobile voice chat session."""

    settings = get_settings()

    if settings.call_mode.strip().lower() != "web":
        await websocket.close(
            code=1008,
            reason="Web calls are paused",
        )
        return

    api_key = settings.elevenlabs_api_key.strip()
    model = settings.elevenlabs_stt_model.strip()

    if not api_key:
        await websocket.close(
            code=1011,
            reason="ELEVENLABS_API_KEY is missing",
        )
        return

    client_ip = websocket.client.host if websocket.client else "unknown"
    admission_error = _admit_call(
        client_ip,
        concurrent_limit=settings.web_call_max_concurrent,
        hourly_limit=settings.web_call_max_per_ip_hour,
    )
    if admission_error:
        await websocket.close(code=1013, reason=admission_error)
        return

    await websocket.accept()

    log.info("mobile_voice_chat_connected")

    # Wait for the "start" message from the client
    try:
        raw_start = await asyncio.wait_for(
            websocket.receive_text(),
            timeout=30.0,
        )
    except (asyncio.TimeoutError, WebSocketDisconnect):
        log.warning("mobile_no_start_message")
        _release_call()
        return

    try:
        start_message = json.loads(raw_start)
    except (TypeError, ValueError):
        await websocket.close(code=1002, reason="Invalid start message")
        _release_call()
        return

    if str(start_message.get("event", "")) != "start":
        log.warning(
            "mobile_unexpected_first_message",
            event=start_message.get("event"),
        )
        await websocket.close(
            code=1002,
            reason="Expected start event",
        )
        _release_call()
        return

    # Load a public influencer. Invalid IDs must not silently fall back to a
    # generic persona because that makes the profile and spoken identity differ.
    database = get_database()
    influencer = None
    influencer_id = start_message.get("influencer_id")

    if influencer_id is None:
        await websocket.send_text(json.dumps({
            "event": "error",
            "message": "Choose an available creator before starting a call.",
        }))
        await websocket.close(code=1008, reason="Creator required")
        _release_call()
        return

    if influencer_id is not None:
        try:
            influencer_id = int(influencer_id)
            influencer = database.get_influencer(influencer_id)
        except (TypeError, ValueError):
            influencer = None

        if influencer is None or not influencer.get("is_published"):
            await websocket.send_text(json.dumps({
                "event": "error",
                "message": "This creator is not available for calls.",
            }))
            await websocket.close(code=1008, reason="Creator unavailable")
            _release_call()
            return

        signing_secret = (
            settings.web_call_signing_secret or settings.admin_token
        ).strip()
        call_token = str(start_message.get("call_token", ""))
        if not signing_secret or not validate_call_token(
            call_token,
            influencer_id=influencer_id,
            client_ip=client_ip,
            secret=signing_secret,
        ):
            await websocket.send_text(json.dumps({
                "event": "error",
                "message": "This call link expired. Close it and start again.",
            }))
            await websocket.close(code=1008, reason="Invalid call admission token")
            _release_call()
            return

        if not influencer.get("call_enabled"):
            await websocket.send_text(json.dumps({
                "event": "error",
                "message": "Calls are paused for this creator.",
            }))
            await websocket.close(code=1008, reason="Creator calls paused")
            _release_call()
            return

    caller_name = str(
        start_message.get("caller_name", "")
    ).strip()

    signed_in_user = None
    session_cookie = websocket.cookies.get("tac_session", "")
    if session_cookie:
        signed_in_user = database.get_user_by_session(
            session_token_hash(session_cookie)
        )
        if signed_in_user is not None and not caller_name:
            caller_name = signed_in_user["display_name"]

    if influencer is not None:
        log.info(
            "persona_loaded",
            name=influencer["name"],
            id=influencer["id"],
        )
    else:
        log.info("persona_default")

    transcript_queue: asyncio.Queue[str | None] = asyncio.Queue()

    # Create audio sender and voice agent
    mobile_sender = MobileAudioSender(
        websocket=websocket,
        interruption_event=asyncio.Event(),
    )

    async def on_assistant_transcript(text: str) -> None:
        await mobile_sender.send_transcript(text)

    try:
        voice_agent = VoiceAgent(
            audio_sender=mobile_sender,
            system_prompt=compose_system_prompt(
                influencer=influencer,
            ),
            voice_id=(
                influencer["voice_id"]
                if influencer is not None
                else None
            ),
            influencer_name=(
                influencer["name"]
                if influencer is not None
                else ""
            ),
            caller_name=caller_name,
            language=(
                influencer.get("primary_language", "en")
                if influencer is not None else "en"
            ),
            on_transcript=on_assistant_transcript,
            knowledge_provider=(
                lambda query: database.retrieve_creator_knowledge(
                    influencer["id"], query
                )
                if influencer is not None else ""
            ),
        )
    except VoiceAgentError:
        await mobile_sender.send_error("The voice service is not configured.")
        await websocket.close(code=1011, reason="Voice service unavailable")
        _release_call()
        return

    # Share the interruption event between sender and agent
    mobile_sender.interruption_event = voice_agent.interruption_event

    elevenlabs_url = build_elevenlabs_url(model)

    headers = {
        "xi-api-key": api_key,
    }

    transcript_receiver_task = None
    response_worker_task = None
    packet_count = 0
    call_started_at = time.monotonic()
    call_status = "completed"
    call_error = ""
    call_session_id = database.start_web_call_session(
        influencer_id=(influencer["id"] if influencer is not None else None),
        user_id=(signed_in_user["id"] if signed_in_user is not None else None),
        caller_name=caller_name,
    )

    try:
        async with connect(
            elevenlabs_url,
            additional_headers=headers,
            open_timeout=20,
            close_timeout=10,
            max_size=4 * 1024 * 1024,
        ) as elevenlabs_websocket:
            log.info("elevenlabs_ws_connected")

            # The browser should start its microphone only after STT is ready.
            await mobile_sender.send_ready()

            transcript_receiver_task = asyncio.create_task(
                receive_elevenlabs_transcripts(
                    elevenlabs_websocket,
                    transcript_queue,
                    voice_agent,
                    mobile_sender,
                )
            )

            response_worker_task = asyncio.create_task(
                process_user_transcripts(
                    transcript_queue,
                    voice_agent,
                    mobile_sender,
                )
            )

            async def greet_client() -> None:
                try:
                    await voice_agent.greet()
                except Exception:
                    try:
                        await mobile_sender.send_error(
                            "The AI could not start speaking. End the call and try again."
                        )
                    except Exception:
                        pass

            # Start greeting
            if voice_agent.greeting_requested:
                voice_agent.greeting_task = asyncio.create_task(
                    greet_client()
                )

            call_limit = min(
                settings.web_call_max_seconds,
                int(influencer.get("max_call_seconds", 300))
                if influencer is not None else settings.web_call_max_seconds,
            )
            packet_count = await asyncio.wait_for(
                forward_mobile_audio(
                    client_websocket=websocket,
                    elevenlabs_websocket=elevenlabs_websocket,
                    voice_agent=voice_agent,
                    mobile_sender=mobile_sender,
                ),
                timeout=call_limit,
            )

    except WebSocketDisconnect:
        log.info("mobile_ws_disconnected")

    except asyncio.TimeoutError:
        log.info("mobile_call_time_limit_reached")
        try:
            await mobile_sender.send_error("This call reached its time limit.")
        except Exception:
            pass

    except (
        MobileTranscriptionError,
        VoiceAgentError,
    ) as error:
        call_status = "failed"
        call_error = str(error)[:500]
        log.error("voice_agent_error", error=str(error))
        try:
            await mobile_sender.send_error(
                "The voice service could not continue. End the call and try again."
            )
        except Exception:
            pass

    except Exception as error:
        call_status = "failed"
        call_error = str(error)[:500]
        log.error(
            "pipeline_error",
            error=str(error),
            error_type=type(error).__name__,
        )
        try:
            await mobile_sender.send_error(
                "The live call disconnected. End the call and try again."
            )
        except Exception:
            pass

    finally:
        _release_call()
        database.finish_web_call_session(
            call_session_id,
            status=call_status,
            duration_seconds=int(time.monotonic() - call_started_at),
            error=call_error,
        )
        await transcript_queue.put(None)

        tasks = [
            transcript_receiver_task,
            response_worker_task,
            voice_agent.greeting_task,
        ]

        for task in tasks:
            if task is None:
                continue

            if not task.done():
                task.cancel()

        await asyncio.gather(
            *(task for task in tasks if task is not None),
            return_exceptions=True,
        )

        log.info(
            "voice_chat_ended",
            packets=packet_count,
        )
