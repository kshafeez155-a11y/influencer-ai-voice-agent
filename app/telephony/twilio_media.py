import asyncio
import json
from urllib.parse import urlencode

from fastapi import WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect

from app.core.settings import get_settings
from app.telephony.twilio_voice_agent import (
    TwilioVoiceAgent,
    TwilioVoiceAgentError,
)


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
            print(
                "[TWILIO STT] ElevenLabs "
                "session started"
            )
            continue

        if message_type == "partial_transcript":
            text = str(
                data.get("text", "")
            ).strip()

            if text:
                print(
                    f"\r[TWILIO STT] Partial: {text}",
                    end="",
                    flush=True,
                )

                if (
                    voice_agent.can_be_interrupted()
                    and not caller_speech_detected
                ):
                    caller_speech_detected = True

                    await voice_agent.interrupt()

            continue

        if message_type in {
            "committed_transcript",
            "committed_transcript_with_timestamps",
        }:
            text = str(
                data.get("text", "")
            ).strip()

            print("")

            caller_speech_detected = False

            if text:
                print(
                    f"[TWILIO STT] Committed: {text}"
                )

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
            print(
                "[PHONE AGENT] Response failed: "
                f"{type(error).__name__}: {error}"
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
            print(
                "[TWILIO] WebSocket protocol connected"
            )
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

            media_format = start_data.get(
                "mediaFormat",
                {},
            )

            print("[TWILIO] Stream started")
            print(
                f"[TWILIO] Stream SID: "
                f"{stream_sid}"
            )
            print(
                f"[TWILIO] Call SID: "
                f"{call_sid}"
            )
            print(
                "[TWILIO] Encoding: "
                f"{media_format.get('encoding')}"
            )
            print(
                "[TWILIO] Sample rate: "
                f"{media_format.get('sampleRate')}"
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
                print(
                    "[TWILIO] First packet "
                    "forwarded to ElevenLabs"
                )

            if packet_count % 100 == 0:
                print(
                    f"[TWILIO] Forwarded "
                    f"{packet_count} packets"
                )

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

            print(
                f"[TWILIO] Playback mark: "
                f"{mark_name}"
            )

            voice_agent.handle_playback_mark(
                mark_name
            )

            continue

        if event == "stop":
            print(
                "[TWILIO] Stream stopped"
            )
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

    print("")
    print("=" * 72)
    print(
        "[TWILIO] PHONE AI WITH BARGE-IN CONNECTED"
    )
    print("=" * 72)

    transcript_queue: asyncio.Queue[
        str | None
    ] = asyncio.Queue()

    voice_agent = TwilioVoiceAgent(
        twilio_websocket=websocket
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
            print(
                "[TWILIO STT] ElevenLabs "
                "WebSocket connected"
            )

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
        print(
            "[TWILIO] Phone WebSocket disconnected"
        )

    except (
        TwilioTranscriptionError,
        TwilioVoiceAgentError,
    ) as error:
        print(
            f"[TWILIO] Voice agent error: "
            f"{error}"
        )

    except Exception as error:
        print(
            "[TWILIO] Phone pipeline error: "
            f"{type(error).__name__}: {error}"
        )

    finally:
        await transcript_queue.put(
            None
        )

        tasks = [
            transcript_receiver_task,
            response_worker_task,
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

        print("")
        print(
            f"[TWILIO] Total audio packets: "
            f"{packet_count}"
        )
        print(
            f"[TWILIO] Stream SID: "
            f"{stream_sid or 'unknown'}"
        )
        print(
            f"[TWILIO] Call SID: "
            f"{call_sid or 'unknown'}"
        )
        print("=" * 72)
        print("")