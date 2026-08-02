import asyncio
import base64
import json
from pathlib import Path
from urllib.parse import urlencode

from websockets.asyncio.client import connect

from app.core.settings import get_settings


class ScribeProviderError(RuntimeError):
    """Raised when ElevenLabs Scribe cannot transcribe audio."""


class ScribeRealtimeProvider:
    """Streams raw PCM audio to ElevenLabs Scribe Realtime."""

    def __init__(self) -> None:
        settings = get_settings()

        self.api_key = settings.elevenlabs_api_key.strip()
        self.model = settings.elevenlabs_stt_model.strip()

        # Our FFmpeg command created 16 kHz, mono, signed 16-bit PCM.
        self.audio_format = "pcm_16000"
        self.sample_rate = 16000

        if not self.api_key:
            raise ScribeProviderError(
                "ELEVENLABS_API_KEY is missing from the .env file."
            )

        if not self.model:
            raise ScribeProviderError(
                "ELEVENLABS_STT_MODEL is missing from the .env file."
            )

    async def transcribe_file(self, file_path: str) -> str:
        """Stream a PCM file and return its committed transcript."""

        audio_path = Path(file_path)

        if not audio_path.exists():
            raise ScribeProviderError(
                f"Audio file was not found: {audio_path}"
            )

        if audio_path.stat().st_size == 0:
            raise ScribeProviderError(
                f"Audio file is empty: {audio_path}"
            )

        query = urlencode(
            {
                "model_id": self.model,
                "audio_format": self.audio_format,
                "commit_strategy": "manual",
                "include_language_detection": "true",
            }
        )

        websocket_url = (
            "wss://api.elevenlabs.io/v1/"
            f"speech-to-text/realtime?{query}"
        )

        headers = {
            "xi-api-key": self.api_key,
        }

        committed_transcripts: list[str] = []

        print("[SCRIBE] Connecting...")

        try:
            async with connect(
                websocket_url,
                additional_headers=headers,
                open_timeout=20,
                close_timeout=10,
                max_size=4 * 1024 * 1024,
            ) as websocket:
                print("[SCRIBE] WebSocket connected")

                receiver_task = asyncio.create_task(
                    self._receive_messages(
                        websocket,
                        committed_transcripts,
                    )
                )

                await self._send_audio(
                    websocket,
                    audio_path,
                )

                try:
                    await asyncio.wait_for(
                        receiver_task,
                        timeout=30,
                    )
                except asyncio.TimeoutError as error:
                    receiver_task.cancel()

                    raise ScribeProviderError(
                        "Timed out waiting for the committed transcript."
                    ) from error

        except ScribeProviderError:
            raise

        except Exception as error:
            raise ScribeProviderError(
                f"ElevenLabs connection failed: "
                f"{type(error).__name__}: {error}"
            ) from error

        transcript = " ".join(committed_transcripts).strip()

        if not transcript:
            raise ScribeProviderError(
                "ElevenLabs returned no committed transcript."
            )

        return transcript

    async def _send_audio(
        self,
        websocket,
        audio_path: Path,
    ) -> None:
        """Send PCM audio in realtime-sized chunks."""

        # At 16 kHz, mono, 16-bit PCM:
        # 3200 bytes represents approximately 100 ms of audio.
        chunk_size = 3200

        with audio_path.open("rb") as audio_file:
            while True:
                audio_chunk = audio_file.read(chunk_size)

                if not audio_chunk:
                    break

                message = {
                    "message_type": "input_audio_chunk",
                    "audio_base_64": base64.b64encode(
                        audio_chunk
                    ).decode("ascii"),
                    "commit": False,
                }

                await websocket.send(
                    json.dumps(message)
                )

                # Simulate realtime audio delivery.
                await asyncio.sleep(0.1)

        print("[SCRIBE] Audio fully sent")
        print("[SCRIBE] Requesting final commit")

        commit_message = {
            "message_type": "input_audio_chunk",
            "audio_base_64": "",
            "commit": True,
        }

        await websocket.send(
            json.dumps(commit_message)
        )

    async def _receive_messages(
        self,
        websocket,
        committed_transcripts: list[str],
    ) -> None:
        """Receive transcript and error events."""

        async for raw_message in websocket:
            try:
                data = json.loads(raw_message)
            except json.JSONDecodeError:
                print(
                    "[SCRIBE] Received an unreadable message"
                )
                continue

            message_type = str(
                data.get("message_type", "")
            )

            if message_type == "session_started":
                print("[SCRIBE] Session started")
                continue

            if message_type == "partial_transcript":
                text = str(
                    data.get("text", "")
                ).strip()

                if text:
                    print(f"[SCRIBE] Partial: {text}")

                continue

            if message_type == "final_transcript":
                text = str(
                    data.get("text", "")
                ).strip()

                if text:
                    print(f"[SCRIBE] Final: {text}")

                continue

            if message_type in {
                "committed_transcript",
                "committed_transcript_with_timestamps",
            }:
                text = str(
                    data.get("text", "")
                ).strip()

                if text:
                    committed_transcripts.append(text)
                    print(
                        f"[SCRIBE] Committed: {text}"
                    )

                return

            if self._is_error_message(message_type):
                error_text = (
                    data.get("error")
                    or data.get("message")
                    or str(data)
                )

                raise ScribeProviderError(
                    f"ElevenLabs error "
                    f"({message_type}): {error_text}"
                )

            print(
                f"[SCRIBE] Event received: {message_type}"
            )

    @staticmethod
    def _is_error_message(
        message_type: str,
    ) -> bool:
        known_errors = {
            "auth_error",
            "quota_exceeded",
            "rate_limited",
            "throttled",
            "unaccepted_terms",
            "queue_overflow",
            "resource_exhausted",
            "session_time_limit_exceeded",
            "input_error",
            "chunk_size_exceeded",
            "insufficient_audio_activity",
            "transcriber_error",
            "error",
        }

        return (
            message_type in known_errors
            or message_type.endswith("_error")
        )