import time
import wave
from pathlib import Path

from cartesia import Cartesia

from app.core.settings import get_settings


class CartesiaProviderError(RuntimeError):
    """Raised when Cartesia cannot generate speech."""


class CartesiaTTSProvider:
    """Generate streamed speech using Cartesia Sonic 3.5."""

    def __init__(self) -> None:
        settings = get_settings()

        self.api_key = settings.cartesia_api_key.strip()
        self.voice_id = settings.cartesia_voice_id.strip()
        self.model = settings.cartesia_model.strip()
        self.sample_rate = settings.cartesia_sample_rate

        if not self.api_key:
            raise CartesiaProviderError(
                "CARTESIA_API_KEY is missing from .env."
            )

        if not self.voice_id:
            raise CartesiaProviderError(
                "CARTESIA_VOICE_ID is missing from .env."
            )

        self.client = Cartesia(api_key=self.api_key)

    def generate_wav(
        self,
        text: str,
        output_file: str | Path,
    ) -> tuple[Path, float, int]:
        clean_text = text.strip()

        if not clean_text:
            raise ValueError("Text cannot be empty.")

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        audio_chunks: list[bytes] = []
        first_audio_ms: float | None = None
        started_at = time.perf_counter()

        print("[CARTESIA] Connecting...")

        try:
            with self.client.tts.websocket_connect() as connection:
                print("[CARTESIA] WebSocket connected")

                context = connection.context(
                    model_id=self.model,
                    voice={
                        "mode": "id",
                        "id": self.voice_id,
                    },
                    output_format={
                        "container": "raw",
                        "encoding": "pcm_s16le",
                        "sample_rate": self.sample_rate,
                    },
                )

                print("[CARTESIA] Sending text...")

                for text_chunk in self._split_text(clean_text):
                    context.push(text_chunk)

                context.no_more_inputs()

                for response in context.receive():
                    response_type = getattr(response, "type", "")
                    audio = getattr(response, "audio", None)

                    if response_type == "chunk" and audio:
                        if first_audio_ms is None:
                            first_audio_ms = (
                                time.perf_counter() - started_at
                            ) * 1000

                            print(
                                "[CARTESIA] First audio received "
                                f"in {first_audio_ms:.0f} ms"
                            )

                        audio_chunks.append(audio)

                    elif response_type == "done":
                        print("[CARTESIA] Generation completed")
                        break

                    elif response_type == "error":
                        raise CartesiaProviderError(
                            str(
                                getattr(
                                    response,
                                    "error",
                                    "Unknown Cartesia error",
                                )
                            )
                        )

        except CartesiaProviderError:
            raise

        except Exception as error:
            raise CartesiaProviderError(
                "Cartesia request failed: "
                f"{type(error).__name__}: {error}"
            ) from error

        if not audio_chunks:
            raise CartesiaProviderError(
                "Cartesia returned no audio."
            )

        complete_audio = b"".join(audio_chunks)

        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(complete_audio)

        if first_audio_ms is None:
            raise CartesiaProviderError(
                "Could not measure first-audio latency."
            )

        return output_path, first_audio_ms, len(complete_audio)

    @staticmethod
    def _split_text(text: str) -> list[str]:
        words = text.split()
        chunks: list[str] = []

        for index in range(0, len(words), 4):
            chunk = " ".join(words[index:index + 4])

            if chunk:
                chunks.append(chunk + " ")

        return chunks