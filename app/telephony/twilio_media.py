import asyncio
import json
from urllib.parse import urlencode

import structlog
from fastapi import WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect

from app.core.settings import get_settings
from app.db.database import get_database
from app.telephony.twilio_voice_agent import (
    TwilioVoiceAgent,
    TwilioVoiceAgentError,
    compose_system_prompt,
)

log = structlog.get_logger()


class TwilioTranscriptionError(RuntimeError):
    """Raised when phone audio cannot be transcribed."""


def build_elevenlabs_url(
    model: str,
) -> str:
    """Create the ElevenLabs realtime STT URL."""

    query = urlencode(
        {
            "model_id": model,
            "audio_format": "ulaw_8000",
            "commit_strategy": "vad",
            "vad_threshold": "0.5",
            "vad_silence_threshold_secs": "0.8",
            "min_speech_duration_ms": "250",
            "min_silence_duration_ms": "250",
            "include_language_detection": "true",
        }
    )

    return (
        "wss://api.elevenlabs.io/v1/"
        f"speech-to-text/realtime?{query}"
    )


async def receive_elevenlabs_transcripts(
    elevenlabs_websocket,
    transcript_queue: asyncio.Queue[
        str | None
    ],
    voice_agent: TwilioVoiceAgent,
) -> None:
    """
    Receive partial and committed caller transcripts.

    A partial transcript while the AI is active triggers barge-in.
    """

    caller_speech_detected = False

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

                    await voice_agent.interrupt()

            continue

        # ElevenLabs sends the timestamp-enriched event as a delayed companion
        # to the authoritative committed event. Treating both as turns causes
        # duplicated user speech and duplicated model responses.
        if message_type == "committed_transcript_with_timestamps":
            continue

        if message_type == "committed_transcript":
            text = str(
                data.get("text", "")
            ).strip()

            caller_speech_detected = False

            if text:
                log.info("stt_committed", text=text)

                await transcript_queue.put(
                    text
                )

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

            raise TwilioTranscriptionError(
                f"ElevenLabs error "
                f"({message_type}): "
                f"{error_message}"
            )


async def process_caller_transcripts(
    transcript_queue: asyncio.Queue[
        str | None
    ],
    voice_agent: TwilioVoiceAgent,
) -> None:
    """Generate one AI response for each committed transcript."""

    while True:
        transcript = (
            await transcript_queue.get()
        )

        if transcript is None:
            return

        try:
            await voice_agent.respond_to_transcript(
                transcript
            )

        except Exception as error:
            log.error(
                "response_failed",
                error=str(error),
                error_type=type(error).__name__,
            )


async def forward_twilio_audio(
    twilio_websocket: WebSocket,
    elevenlabs_websocket,
    voice_agent: TwilioVoiceAgent,
) -> tuple[str, str, int]:
    """Forward caller audio from Twilio to ElevenLabs."""

    stream_sid = ""
    call_sid = ""
    packet_count = 0

    while True:
        raw_message = (
            await twilio_websocket.receive_text()
        )

        message = json.loads(
            raw_message
        )

        event = str(
            message.get("event", "")
        )

        if event == "connected":
            log.info("twilio_ws_connected")
            continue

        if event == "start":
            start_data = message.get(
                "start",
                {},
            )

            stream_sid = str(
                start_data.get(
                    "streamSid",
                    "",
                )
            )

            call_sid = str(
                start_data.get(
                    "callSid",
                    "",
                )
            )

            voice_agent.set_stream_sid(
                stream_sid
            )

            if voice_agent.greeting_requested:
                voice_agent.greeting_task = (
                    asyncio.create_task(
                        voice_agent.greet()
                    )
                )

            media_format = start_data.get(
                "mediaFormat",
                {},
            )

            log.info(
                "twilio_stream_started",
                stream_sid=stream_sid,
                call_sid=call_sid,
                encoding=media_format.get("encoding"),
                sample_rate=media_format.get("sampleRate"),
            )
            continue

        if event == "media":
            packet_count += 1

            payload = str(
                message.get(
                    "media",
                    {},
                ).get(
                    "payload",
                    "",
                )
            )

            if payload:
                await elevenlabs_websocket.send(
                    json.dumps(
                        {
                            "message_type": (
                                "input_audio_chunk"
                            ),
                            "audio_base_64": payload,
                            "commit": False,
                        }
                    )
                )

            if packet_count == 1:
                log.info("first_audio_packet_forwarded")

            if packet_count % 100 == 0:
                log.debug("audio_packets_forwarded", count=packet_count)

            continue

        if event == "mark":
            mark_name = str(
                message.get(
                    "mark",
                    {},
                ).get(
                    "name",
                    "",
                )
            )

            log.debug("playback_mark", mark=mark_name)

            voice_agent.handle_playback_mark(
                mark_name
            )

            continue

        if event == "stop":
            log.info("twilio_stream_stopped")
            break

    return (
        stream_sid,
        call_sid,
        packet_count,
    )


async def handle_twilio_media_stream(
    websocket: WebSocket,
) -> None:
    """Run STT, Groq, Cartesia and barge-in for one call."""

    settings = get_settings()

    api_key = (
        settings.elevenlabs_api_key.strip()
    )

    model = (
        settings.elevenlabs_stt_model.strip()
    )

    if not api_key:
        await websocket.close(
            code=1011,
            reason=(
                "ELEVENLABS_API_KEY is missing"
            ),
        )
        return

    await websocket.accept()

    log.info("phone_ai_connected")

    # Resolve the persona from the Stream URL query params
    # (injected by /twilio/voice from the call webhook).
    query_params = websocket.query_params

    influencer = None
    influencer_param = str(
        query_params.get("influencer", "")
    ).strip()

    if influencer_param.isdigit():
        influencer = get_database().get_influencer(
            int(influencer_param)
        )

    caller_name = str(
        query_params.get("name", "")
    ).strip()

    if influencer is not None:
        log.info(
            "persona_loaded",
            name=influencer["name"],
            id=influencer["id"],
        )
    else:
        log.info("persona_default")

    transcript_queue: asyncio.Queue[
        str | None
    ] = asyncio.Queue()

    voice_agent = TwilioVoiceAgent(
        twilio_websocket=websocket,
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
        knowledge_provider=(
            lambda query: get_database().retrieve_creator_knowledge(
                influencer["id"], query
            )
            if influencer is not None else ""
        ),
    )

    elevenlabs_url = (
        build_elevenlabs_url(
            model
        )
    )

    headers = {
        "xi-api-key": api_key,
    }

    transcript_receiver_task = None
    response_worker_task = None

    stream_sid = ""
    call_sid = ""
    packet_count = 0

    try:
        async with connect(
            elevenlabs_url,
            additional_headers=headers,
            open_timeout=20,
            close_timeout=10,
            max_size=4 * 1024 * 1024,
        ) as elevenlabs_websocket:
            log.info("elevenlabs_ws_connected")

            transcript_receiver_task = (
                asyncio.create_task(
                    receive_elevenlabs_transcripts(
                        elevenlabs_websocket,
                        transcript_queue,
                        voice_agent,
                    )
                )
            )

            response_worker_task = (
                asyncio.create_task(
                    process_caller_transcripts(
                        transcript_queue,
                        voice_agent,
                    )
                )
            )

            (
                stream_sid,
                call_sid,
                packet_count,
            ) = await forward_twilio_audio(
                twilio_websocket=websocket,
                elevenlabs_websocket=(
                    elevenlabs_websocket
                ),
                voice_agent=voice_agent,
            )

    except WebSocketDisconnect:
        log.info("twilio_ws_disconnected")

    except (
        TwilioTranscriptionError,
        TwilioVoiceAgentError,
    ) as error:
        log.error("voice_agent_error", error=str(error))

    except Exception as error:
        log.error(
            "pipeline_error",
            error=str(error),
            error_type=type(error).__name__,
        )

    finally:
        await transcript_queue.put(
            None
        )

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

                try:
                    await task
                except asyncio.CancelledError:
                    pass

        log.info(
            "call_ended",
            packets=packet_count,
            stream_sid=stream_sid or "unknown",
            call_sid=call_sid or "unknown",
        )
