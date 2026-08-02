import asyncio
import base64
import json
import time
from urllib.parse import urlencode

import pyaudio
from websockets.asyncio.client import connect

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams, VADState

from app.core.settings import get_settings


SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_FORMAT = pyaudio.paInt16
BYTES_PER_SAMPLE = 2

MAX_TEST_SECONDS = 30
COMMIT_WAIT_SECONDS = 15


class LiveScribeError(RuntimeError):
    """Raised when the live microphone STT test fails."""


class LiveScribeTest:
    """Stream microphone audio to ElevenLabs Scribe Realtime."""

    def __init__(self) -> None:
        settings = get_settings()

        self.api_key = settings.elevenlabs_api_key.strip()
        self.model = settings.elevenlabs_stt_model.strip()

        if not self.api_key:
            raise LiveScribeError(
                "ELEVENLABS_API_KEY is missing from .env."
            )

        self.vad = SileroVADAnalyzer(
            params=VADParams(
                confidence=0.65,
                start_secs=0.15,
                stop_secs=0.35,
                min_volume=0.5,
            )
        )

        self.vad.set_sample_rate(SAMPLE_RATE)

        self.samples_per_chunk = (
            self.vad.num_frames_required()
        )

        self.chunk_bytes = (
            self.samples_per_chunk * BYTES_PER_SAMPLE
        )

        self.final_transcript = ""
        self.committed_event = asyncio.Event()
        self.receiver_error: Exception | None = None

    def build_websocket_url(self) -> str:
        query = urlencode(
            {
                "model_id": self.model,
                "audio_format": "pcm_16000",
                "commit_strategy": "manual",
                "include_language_detection": "true",
            }
        )

        return (
            "wss://api.elevenlabs.io/v1/"
            f"speech-to-text/realtime?{query}"
        )

    async def receive_messages(self, websocket) -> None:
        """Receive partial, committed and error events."""

        try:
            async for raw_message in websocket:
                data = json.loads(raw_message)

                message_type = str(
                    data.get("message_type", "")
                )

                if message_type == "session_started":
                    print("[LIVE STT] Session started")
                    continue

                if message_type == "partial_transcript":
                    text = str(
                        data.get("text", "")
                    ).strip()

                    if text:
                        print(
                            f"\r[LIVE STT] Partial: {text}",
                            end="",
                            flush=True,
                        )

                    continue

                if message_type in {
                    "committed_transcript",
                    "committed_transcript_with_timestamps",
                }:
                    text = str(
                        data.get("text", "")
                    ).strip()

                    print("")

                    if text:
                        self.final_transcript = text

                        print(
                            f"[LIVE STT] Committed: {text}"
                        )

                    self.committed_event.set()
                    return

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

                    raise LiveScribeError(
                        f"ElevenLabs error "
                        f"({message_type}): "
                        f"{error_message}"
                    )

        except Exception as error:
            self.receiver_error = error
            self.committed_event.set()

    async def send_audio_chunk(
        self,
        websocket,
        audio_chunk: bytes,
        commit: bool = False,
    ) -> None:
        message = {
            "message_type": "input_audio_chunk",
            "audio_base_64": base64.b64encode(
                audio_chunk
            ).decode("ascii"),
            "commit": commit,
        }

        await websocket.send(
            json.dumps(message)
        )

    async def send_commit(self, websocket) -> None:
        commit_message = {
            "message_type": "input_audio_chunk",
            "audio_base_64": "",
            "commit": True,
        }

        await websocket.send(
            json.dumps(commit_message)
        )

    async def run(self) -> str:
        """Capture one utterance and return its transcript."""

        websocket_url = self.build_websocket_url()

        print("")
        print("=" * 70)
        print("LIVE MICROPHONE → ELEVENLABS SCRIBE TEST")
        print("=" * 70)
        print(
            f"[LIVE STT] Microphone sample rate: "
            f"{SAMPLE_RATE}"
        )
        print(
            f"[LIVE STT] Samples per chunk: "
            f"{self.samples_per_chunk}"
        )
        print("[LIVE STT] Connecting to ElevenLabs...")

        headers = {
            "xi-api-key": self.api_key,
        }

        audio = pyaudio.PyAudio()
        microphone_stream = None
        receiver_task = None

        try:
            async with connect(
                websocket_url,
                additional_headers=headers,
                open_timeout=20,
                close_timeout=10,
                max_size=4 * 1024 * 1024,
            ) as websocket:
                print("[LIVE STT] WebSocket connected")

                receiver_task = asyncio.create_task(
                    self.receive_messages(websocket)
                )

                microphone_stream = audio.open(
                    format=SAMPLE_FORMAT,
                    channels=CHANNELS,
                    rate=SAMPLE_RATE,
                    input=True,
                    frames_per_buffer=(
                        self.samples_per_chunk
                    ),
                )

                print("")
                print(
                    "[LIVE STT] Speak one sentence now."
                )
                print(
                    "[LIVE STT] Example: "
                    "I want to promote my clothing business."
                )
                print(
                    "[LIVE STT] Remain silent after speaking."
                )
                print("")

                previous_state = VADState.QUIET
                speech_started = False
                commit_sent = False
                started_at = time.perf_counter()

                while (
                    time.perf_counter() - started_at
                    < MAX_TEST_SECONDS
                ):
                    audio_chunk = await asyncio.to_thread(
                        microphone_stream.read,
                        self.samples_per_chunk,
                        False,
                    )

                    if len(audio_chunk) != self.chunk_bytes:
                        continue

                    # Send all microphone audio continuously.
                    await self.send_audio_chunk(
                        websocket,
                        audio_chunk,
                    )

                    vad_state = await self.vad.analyze_audio(
                        audio_chunk
                    )

                    if (
                        vad_state == VADState.SPEAKING
                        and previous_state
                        != VADState.SPEAKING
                    ):
                        if not speech_started:
                            speech_started = True
                            print(
                                "[LIVE STT] SPEECH STARTED"
                            )

                    if (
                        speech_started
                        and vad_state == VADState.QUIET
                        and previous_state
                        != VADState.QUIET
                    ):
                        print("")
                        print(
                            "[LIVE STT] SPEECH STOPPED"
                        )
                        print(
                            "[LIVE STT] Requesting "
                            "final transcript..."
                        )

                        await self.send_commit(websocket)
                        commit_sent = True
                        break

                    previous_state = vad_state
                    await asyncio.sleep(0)

                if not speech_started:
                    raise LiveScribeError(
                        "No speech was detected. Speak more "
                        "clearly and run the test again."
                    )

                if not commit_sent:
                    print("")
                    print(
                        "[LIVE STT] Test timeout reached. "
                        "Sending final commit..."
                    )
                    await self.send_commit(websocket)

                try:
                    await asyncio.wait_for(
                        self.committed_event.wait(),
                        timeout=COMMIT_WAIT_SECONDS,
                    )
                except asyncio.TimeoutError as error:
                    raise LiveScribeError(
                        "Timed out while waiting for the "
                        "committed transcript."
                    ) from error

                if self.receiver_error:
                    raise self.receiver_error

                if not self.final_transcript:
                    raise LiveScribeError(
                        "ElevenLabs returned an empty transcript."
                    )

                if receiver_task:
                    await receiver_task

        finally:
            if microphone_stream is not None:
                microphone_stream.stop_stream()
                microphone_stream.close()

            audio.terminate()

            if (
                receiver_task is not None
                and not receiver_task.done()
            ):
                receiver_task.cancel()

                try:
                    await receiver_task
                except asyncio.CancelledError:
                    pass

        return self.final_transcript


async def run_test() -> int:
    try:
        test = LiveScribeTest()
        transcript = await test.run()

        print("")
        print("-" * 70)
        print(f"[FINAL TRANSCRIPT] {transcript}")
        print(
            "[LIVE STT] MICROPHONE TRANSCRIPTION "
            "TEST PASSED"
        )
        print("=" * 70)
        print("")

        return 0

    except LiveScribeError as error:
        print("")
        print(
            "[LIVE STT] MICROPHONE TRANSCRIPTION "
            "TEST FAILED"
        )
        print(f"[ERROR] {error}")
        return 1

    except KeyboardInterrupt:
        print("")
        print("[LIVE STT] Test stopped by user.")
        return 0

    except Exception as error:
        print("")
        print(
            "[LIVE STT] MICROPHONE TRANSCRIPTION "
            "TEST FAILED"
        )
        print(
            f"[UNEXPECTED ERROR] "
            f"{type(error).__name__}: {error}"
        )
        return 1


def main() -> int:
    return asyncio.run(run_test())


if __name__ == "__main__":
    raise SystemExit(main())