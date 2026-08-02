import asyncio
import time
from pathlib import Path

from pipecat.frames.frames import Frame, TextFrame
from pipecat.processors.frame_processor import (
    FrameDirection,
    FrameProcessor,
)

from app.providers.llm_groq import GroqLLMProvider
from app.providers.tts_cartesia import CartesiaTTSProvider


class RecordedPipelineError(RuntimeError):
    """Raised when the recorded AI pipeline fails."""


class RecordedAIProcessor(FrameProcessor):
    """Send transcription text through Groq and Cartesia."""

    def __init__(
        self,
        output_file: str | Path,
    ) -> None:
        super().__init__()

        self.output_file = Path(output_file)

        self.user_transcript = ""
        self.assistant_response = ""
        self.audio_path: Path | None = None

        self.groq_first_token_ms: float | None = None
        self.cartesia_first_audio_ms: float | None = None
        self.audio_size = 0

    async def process_frame(
        self,
        frame: Frame,
        direction: FrameDirection,
    ) -> None:
        await super().process_frame(frame, direction)

        if not isinstance(frame, TextFrame):
            await self.push_frame(frame, direction)
            return

        self.user_transcript = frame.text.strip()

        if not self.user_transcript:
            raise RecordedPipelineError(
                "The transcription TextFrame was empty."
            )

        print("")
        print("[PIPELINE] Pipecat TextFrame received")
        print(
            f"[PIPELINE] User transcript: "
            f"{self.user_transcript}"
        )

        result = await asyncio.to_thread(
            self._generate_response_and_audio,
            self.user_transcript,
        )

        (
            self.assistant_response,
            self.groq_first_token_ms,
            self.audio_path,
            self.cartesia_first_audio_ms,
            self.audio_size,
        ) = result

        print("")
        print(
            f"[PIPELINE] Assistant response: "
            f"{self.assistant_response}"
        )
        print(
            f"[PIPELINE] Audio generated: "
            f"{self.audio_path.resolve()}"
        )

        # Forward the assistant answer as another Pipecat TextFrame.
        await self.push_frame(
            TextFrame(text=self.assistant_response),
            direction,
        )

    def _generate_response_and_audio(
        self,
        transcript: str,
    ) -> tuple[str, float, Path, float, int]:
        """Run blocking Groq and Cartesia SDK operations."""

        groq_provider = GroqLLMProvider()

        print("[PIPELINE] Sending transcript to Groq...")
        print("[GROQ] Streaming response: ", end="", flush=True)

        groq_started_at = time.perf_counter()
        first_token_ms: float | None = None
        response_parts: list[str] = []

        for token in groq_provider.stream_response(transcript):
            if first_token_ms is None:
                first_token_ms = (
                    time.perf_counter() - groq_started_at
                ) * 1000

            print(token, end="", flush=True)
            response_parts.append(token)

        print("")

        assistant_response = "".join(
            response_parts
        ).strip()

        if not assistant_response:
            raise RecordedPipelineError(
                "Groq returned an empty response."
            )

        if first_token_ms is None:
            raise RecordedPipelineError(
                "Groq returned no streaming tokens."
            )

        print(
            f"[PIPELINE] Groq first token: "
            f"{first_token_ms:.0f} ms"
        )

        cartesia_provider = CartesiaTTSProvider()

        print("[PIPELINE] Sending response to Cartesia...")

        (
            audio_path,
            first_audio_ms,
            audio_size,
        ) = cartesia_provider.generate_wav(
            text=assistant_response,
            output_file=self.output_file,
        )

        return (
            assistant_response,
            first_token_ms,
            audio_path,
            first_audio_ms,
            audio_size,
        )