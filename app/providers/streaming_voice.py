import asyncio
import queue
import re
import threading
import time
from collections.abc import Generator

import pyaudio
from cartesia import AsyncCartesia

from app.core.settings import get_settings
from app.providers.llm_groq import (
    GroqLLMProvider,
    GroqProviderError,
)
from app.providers.tts_cartesia import CartesiaProviderError


class StreamingVoiceError(RuntimeError):
    """Raised when streamed LLM-to-TTS playback fails."""


class PhraseChunker:
    """Convert LLM token fragments into speakable phrases."""

    SENTENCE_ENDINGS = {".", "?", "!", ":", ";"}

    def __init__(
        self,
        minimum_words: int = 3,
        maximum_words: int = 12,
    ) -> None:
        self.minimum_words = minimum_words
        self.maximum_words = maximum_words
        self.buffer = ""

    def add(self, token: str) -> list[str]:
        """Add a token and return any phrases ready for TTS."""

        if not token:
            return []

        self.buffer += token

        ready_phrases: list[str] = []

        while True:
            phrase = self._extract_phrase()

            if phrase is None:
                break

            ready_phrases.append(phrase)

        return ready_phrases

    def flush(self) -> str | None:
        """Return any remaining text at the end of generation."""

        remaining = self.buffer.strip()
        self.buffer = ""

        if not remaining:
            return None

        return remaining

    def _extract_phrase(self) -> str | None:
        clean_buffer = self.buffer.strip()

        if not clean_buffer:
            return None

        words = clean_buffer.split()

        # Prefer complete punctuation-delimited phrases.
        if len(words) >= self.minimum_words:
            punctuation_match = re.search(
                r"^(.+?[.!?:;])(?:\s|$)",
                clean_buffer,
            )

            if punctuation_match:
                phrase = punctuation_match.group(1).strip()

                consumed_length = punctuation_match.end()
                self.buffer = clean_buffer[
                    consumed_length:
                ].lstrip()

                return phrase

        # Avoid waiting too long when the LLM generates a long sentence.
        if len(words) >= self.maximum_words:
            phrase_words = words[:self.maximum_words]
            phrase = " ".join(phrase_words)

            remaining_words = words[self.maximum_words:]
            self.buffer = " ".join(remaining_words)

            return phrase

        return None


class StreamingVoiceResponder:
    """Stream Groq output into Cartesia and play PCM immediately."""

    def __init__(self) -> None:
        settings = get_settings()

        self.cartesia_api_key = (
            settings.cartesia_api_key.strip()
        )
        self.cartesia_voice_id = (
            settings.cartesia_voice_id.strip()
        )
        self.cartesia_model = (
            settings.cartesia_model.strip()
        )
        self.sample_rate = settings.cartesia_sample_rate

        if not self.cartesia_api_key:
            raise StreamingVoiceError(
                "CARTESIA_API_KEY is missing from .env."
            )

        if not self.cartesia_voice_id:
            raise StreamingVoiceError(
                "CARTESIA_VOICE_ID is missing from .env."
            )

        self.cartesia_client = AsyncCartesia(
            api_key=self.cartesia_api_key
        )

    async def speak_from_messages(
        self,
        messages: list[dict[str, str]],
    ) -> tuple[str, float, float, float]:
        """
        Stream Groq into Cartesia and play audio immediately.

        Returns:
            assistant_text,
            Groq first-token latency,
            Cartesia first-audio latency,
            playback completion time.
        """

        loop = asyncio.get_running_loop()

        token_queue: asyncio.Queue[str | None] = asyncio.Queue()
        producer_error: list[Exception] = []

        groq_first_token_ms: float | None = None
        cartesia_first_audio_ms: float | None = None

        complete_response_parts: list[str] = []

        overall_started_at = time.perf_counter()
        groq_started_at = time.perf_counter()

        def groq_worker() -> None:
            """Run the synchronous Groq stream outside the event loop."""

            nonlocal groq_first_token_ms

            try:
                groq_provider = GroqLLMProvider()

                for token in groq_provider.stream_messages(
                    messages
                ):
                    if groq_first_token_ms is None:
                        groq_first_token_ms = (
                            time.perf_counter()
                            - groq_started_at
                        ) * 1000

                    complete_response_parts.append(token)

                    asyncio.run_coroutine_threadsafe(
                        token_queue.put(token),
                        loop,
                    ).result()

            except Exception as error:
                producer_error.append(error)

            finally:
                asyncio.run_coroutine_threadsafe(
                    token_queue.put(None),
                    loop,
                ).result()

        producer_thread = threading.Thread(
            target=groq_worker,
            name="groq-stream-worker",
            daemon=True,
        )

        audio = pyaudio.PyAudio()
        speaker_stream = None

        try:
            speaker_stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                output=True,
                frames_per_buffer=1024,
            )

            print("[STREAM] Opening Cartesia WebSocket...")

            async with (
                self.cartesia_client.tts.websocket_connect()
                as websocket
            ):
                print("[STREAM] Cartesia WebSocket connected")

                context = websocket.context(
                    model_id=self.cartesia_model,
                    voice={
                        "mode": "id",
                        "id": self.cartesia_voice_id,
                    },
                    output_format={
                        "container": "raw",
                        "encoding": "pcm_s16le",
                        "sample_rate": self.sample_rate,
                    },
                    language="en",
                )

                producer_thread.start()

                async def push_groq_text() -> None:
                    chunker = PhraseChunker(
                        minimum_words=3,
                        maximum_words=12,
                    )

                    while True:
                        token = await token_queue.get()

                        if token is None:
                            break

                        print(token, end="", flush=True)

                        for phrase in chunker.add(token):
                            print(
                                f"\n[STREAM] Sending phrase: "
                                f"{phrase}"
                            )

                            await context.push(
                                phrase + " "
                            )

                    remaining_phrase = chunker.flush()

                    if remaining_phrase:
                        print(
                            f"\n[STREAM] Sending final phrase: "
                            f"{remaining_phrase}"
                        )

                        await context.push(
                            remaining_phrase + " "
                        )

                    await context.no_more_inputs()

                async def receive_and_play_audio() -> None:
                    nonlocal cartesia_first_audio_ms

                    async for response in context.receive():
                        response_type = getattr(
                            response,
                            "type",
                            "",
                        )

                        audio_chunk = getattr(
                            response,
                            "audio",
                            None,
                        )

                        if (
                            response_type == "chunk"
                            and audio_chunk
                        ):
                            if cartesia_first_audio_ms is None:
                                cartesia_first_audio_ms = (
                                    time.perf_counter()
                                    - overall_started_at
                                ) * 1000

                                print(
                                    "\n[STREAM] First audio "
                                    f"playing at "
                                    f"{cartesia_first_audio_ms:.0f} ms"
                                )

                            await asyncio.to_thread(
                                speaker_stream.write,
                                audio_chunk,
                            )

                        elif response_type == "done":
                            print(
                                "\n[STREAM] Cartesia generation "
                                "completed"
                            )
                            break

                        elif response_type == "error":
                            error_message = (
                                getattr(
                                    response,
                                    "message",
                                    None,
                                )
                                or getattr(
                                    response,
                                    "title",
                                    None,
                                )
                                or "Unknown Cartesia error"
                            )

                            raise StreamingVoiceError(
                                str(error_message)
                            )

                await asyncio.gather(
                    push_groq_text(),
                    receive_and_play_audio(),
                )

            producer_thread.join(timeout=5)

            if producer_error:
                original_error = producer_error[0]

                if isinstance(
                    original_error,
                    GroqProviderError,
                ):
                    raise original_error

                raise StreamingVoiceError(
                    "Groq streaming failed: "
                    f"{type(original_error).__name__}: "
                    f"{original_error}"
                )

            assistant_text = "".join(
                complete_response_parts
            ).strip()

            if not assistant_text:
                raise StreamingVoiceError(
                    "Groq returned no assistant text."
                )

            if groq_first_token_ms is None:
                raise StreamingVoiceError(
                    "Groq first-token latency was not measured."
                )

            if cartesia_first_audio_ms is None:
                raise StreamingVoiceError(
                    "Cartesia returned no playable audio."
                )

            complete_ms = (
                time.perf_counter() - overall_started_at
            ) * 1000

            return (
                assistant_text,
                groq_first_token_ms,
                cartesia_first_audio_ms,
                complete_ms,
            )

        except (
            StreamingVoiceError,
            GroqProviderError,
            CartesiaProviderError,
        ):
            raise

        except Exception as error:
            raise StreamingVoiceError(
                "Streaming voice response failed: "
                f"{type(error).__name__}: {error}"
            ) from error

        finally:
            if speaker_stream is not None:
                speaker_stream.stop_stream()
                speaker_stream.close()

            audio.terminate()

            close_method = getattr(
                self.cartesia_client,
                "close",
                None,
            )

            if close_method is not None:
                close_result = close_method()

                if asyncio.iscoroutine(close_result):
                    await close_result