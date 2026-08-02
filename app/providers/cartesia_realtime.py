import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path

from cartesia import AsyncCartesia

from app.core.settings import get_settings


class CartesiaRealtimeError(RuntimeError):
    """Raised when realtime Cartesia synthesis fails."""


class CartesiaRealtimeTTS:
    """
    Receive live text fragments through a queue and stream raw
    8 kHz μ-law audio from one continuous Cartesia context.
    """

    def __init__(self) -> None:
        settings = get_settings()

        self.api_key = (
            settings.cartesia_api_key.strip()
        )
        self.voice_id = (
            settings.cartesia_voice_id.strip()
        )
        self.model_id = (
            settings.cartesia_model.strip()
        )

        if not self.api_key:
            raise CartesiaRealtimeError(
                "CARTESIA_API_KEY is missing from .env."
            )

        if not self.voice_id:
            raise CartesiaRealtimeError(
                "CARTESIA_VOICE_ID is missing from .env."
            )

        if not self.model_id:
            raise CartesiaRealtimeError(
                "CARTESIA_MODEL is missing from .env."
            )

    async def stream_text_queue(
        self,
        text_queue: asyncio.Queue[str | None],
        stop_event: asyncio.Event | None = None,
    ) -> AsyncIterator[bytes]:
        """
        Read text fragments from a queue and yield Cartesia audio.

        Put strings into text_queue while Groq is generating.
        Put None into the queue when Groq has finished.
        """

        client = AsyncCartesia(
            api_key=self.api_key,
        )

        sender_task: asyncio.Task[None] | None = None

        try:
            async with (
                client.tts.websocket_connect()
            ) as connection:
                context = connection.context(
                    model_id=self.model_id,
                    voice={
                        "mode": "id",
                        "id": self.voice_id,
                    },
                    output_format={
                        "container": "raw",
                        "encoding": "pcm_mulaw",
                        "sample_rate": 8000,
                    },
                )

                sender_task = asyncio.create_task(
                    self._send_text_queue(
                        context=context,
                        text_queue=text_queue,
                        stop_event=stop_event,
                    )
                )

                async for response in context.receive():
                    if (
                        stop_event is not None
                        and stop_event.is_set()
                    ):
                        print(
                            "[CARTESIA STREAM] "
                            "Streaming stopped"
                        )
                        break

                    response_type = getattr(
                        response,
                        "type",
                        "",
                    )

                    audio = getattr(
                        response,
                        "audio",
                        None,
                    )

                    if (
                        response_type == "chunk"
                        and audio
                    ):
                        yield audio

                    elif response_type == "done":
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
                                "error",
                                None,
                            )
                            or "Unknown Cartesia error"
                        )

                        raise CartesiaRealtimeError(
                            str(error_message)
                        )

                await sender_task

        finally:
            if (
                sender_task is not None
                and not sender_task.done()
            ):
                sender_task.cancel()

                try:
                    await sender_task
                except asyncio.CancelledError:
                    pass

            close_method = getattr(
                client,
                "close",
                None,
            )

            if close_method is not None:
                close_result = close_method()

                if asyncio.iscoroutine(
                    close_result
                ):
                    await close_result

    async def _send_text_queue(
        self,
        context,
        text_queue: asyncio.Queue[str | None],
        stop_event: asyncio.Event | None,
    ) -> None:
        """
        Continuously push queued Groq phrases to Cartesia.
        """

        fragment_number = 0

        while True:
            if (
                stop_event is not None
                and stop_event.is_set()
            ):
                print(
                    "[CARTESIA STREAM] "
                    "Text sender interrupted"
                )
                break

            text = await text_queue.get()

            if text is None:
                break

            clean_text = text.strip()

            if not clean_text:
                continue

            fragment_number += 1

            # Add a trailing space so adjacent fragments join naturally.
            text_to_push = f"{clean_text} "

            print(
                "[CARTESIA STREAM] "
                f"Pushing fragment {fragment_number}: "
                f"{clean_text}"
            )

            await context.push(
                text_to_push
            )

        await context.no_more_inputs()

        print(
            "[CARTESIA STREAM] "
            "No more text inputs"
        )


async def run_realtime_cartesia_test() -> None:
    """
    Test queue-based continuous Cartesia streaming.
    """

    output_path = Path(
        "output/cartesia_realtime_queue_test.mulaw"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    text_queue: asyncio.Queue[
        str | None
    ] = asyncio.Queue()

    stop_event = asyncio.Event()

    service = CartesiaRealtimeTTS()

    async def produce_test_text() -> None:
        fragments = [
            "Hello,",
            "thank you for calling our agency.",
            "How can I help promote your business today?",
        ]

        for fragment in fragments:
            await text_queue.put(
                fragment
            )

            await asyncio.sleep(
                0.15
            )

        await text_queue.put(
            None
        )

    producer_task = asyncio.create_task(
        produce_test_text()
    )

    started_at = time.perf_counter()
    first_audio_ms: float | None = None
    chunk_count = 0
    total_bytes = 0

    with output_path.open("wb") as audio_file:
        async for audio_chunk in (
            service.stream_text_queue(
                text_queue=text_queue,
                stop_event=stop_event,
            )
        ):
            if first_audio_ms is None:
                first_audio_ms = (
                    time.perf_counter()
                    - started_at
                ) * 1000

                print(
                    "[CARTESIA STREAM] "
                    f"First audio: "
                    f"{first_audio_ms:.0f} ms"
                )

            audio_file.write(
                audio_chunk
            )

            chunk_count += 1
            total_bytes += len(
                audio_chunk
            )

    await producer_task

    if chunk_count == 0:
        raise CartesiaRealtimeError(
            "Cartesia returned no audio chunks."
        )

    complete_ms = (
        time.perf_counter()
        - started_at
    ) * 1000

    print("")
    print("=" * 60)
    print(
        "[CARTESIA STREAM] "
        "QUEUE TEST PASSED"
    )
    print(
        "[CARTESIA STREAM] First audio: "
        f"{first_audio_ms:.0f} ms"
    )
    print(
        "[CARTESIA STREAM] Complete: "
        f"{complete_ms:.0f} ms"
    )
    print(
        "[CARTESIA STREAM] Audio chunks: "
        f"{chunk_count}"
    )
    print(
        "[CARTESIA STREAM] Audio bytes: "
        f"{total_bytes}"
    )
    print(
        "[CARTESIA STREAM] Output: "
        f"{output_path}"
    )
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(
        run_realtime_cartesia_test()
    )