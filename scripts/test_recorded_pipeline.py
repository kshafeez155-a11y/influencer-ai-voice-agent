import asyncio
import os
import time
from pathlib import Path

from pipecat.frames.frames import EndFrame, TextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import (
    PipelineParams,
    PipelineTask,
)

from app.pipeline.recorded_pipeline import (
    RecordedAIProcessor,
    RecordedPipelineError,
)
from app.providers.stt_scribe import (
    ScribeProviderError,
    ScribeRealtimeProvider,
)


AUDIO_INPUT = Path(
    "tests/audio/scribe-input.pcm"
)

AUDIO_OUTPUT = Path(
    "output/full-pipeline-test.wav"
)


async def run_test() -> int:
    print("")
    print("=" * 72)
    print("RECORDED FULL AI PIPELINE TEST")
    print("=" * 72)

    if not AUDIO_INPUT.exists():
        print("[PIPELINE] TEST FAILED")
        print(
            f"[ERROR] Audio input not found: "
            f"{AUDIO_INPUT}"
        )
        return 1

    total_started_at = time.perf_counter()

    try:
        # -------------------------------------------------
        # 1. SPEECH TO TEXT
        # -------------------------------------------------

        print("")
        print("[PIPELINE] STEP 1 — ElevenLabs Scribe")

        scribe_provider = ScribeRealtimeProvider()

        stt_started_at = time.perf_counter()

        transcript = await scribe_provider.transcribe_file(
            str(AUDIO_INPUT)
        )

        stt_total_ms = (
            time.perf_counter() - stt_started_at
        ) * 1000

        print("")
        print(
            f"[PIPELINE] Scribe transcript: "
            f"{transcript}"
        )
        print(
            f"[PIPELINE] Scribe total time: "
            f"{stt_total_ms:.0f} ms"
        )

        # -------------------------------------------------
        # 2. PIPECAT → GROQ → CARTESIA
        # -------------------------------------------------

        print("")
        print(
            "[PIPELINE] STEP 2 — "
            "Pipecat, Groq and Cartesia"
        )

        ai_processor = RecordedAIProcessor(
            output_file=AUDIO_OUTPUT,
        )

        pipeline = Pipeline(
            [
                ai_processor,
            ]
        )

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=True,
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
        )

        runner = PipelineRunner(
            handle_sigint=False,
        )

        await task.queue_frame(
            TextFrame(text=transcript)
        )

        await task.queue_frame(
            EndFrame()
        )

        await runner.run(task)

        # -------------------------------------------------
        # 3. VERIFY RESULTS
        # -------------------------------------------------

        if not ai_processor.assistant_response:
            raise RecordedPipelineError(
                "No assistant response was generated."
            )

        if ai_processor.audio_path is None:
            raise RecordedPipelineError(
                "No audio output path was returned."
            )

        if not ai_processor.audio_path.exists():
            raise RecordedPipelineError(
                "The generated WAV file does not exist."
            )

        if ai_processor.audio_path.stat().st_size == 0:
            raise RecordedPipelineError(
                "The generated WAV file is empty."
            )

        total_ms = (
            time.perf_counter() - total_started_at
        ) * 1000

        print("")
        print("-" * 72)
        print("[PIPELINE] FINAL RESULTS")
        print("-" * 72)
        print(
            f"[USER] {ai_processor.user_transcript}"
        )
        print(
            f"[ASSISTANT] "
            f"{ai_processor.assistant_response}"
        )
        print(
            f"[METRIC] Groq first token: "
            f"{ai_processor.groq_first_token_ms:.0f} ms"
        )
        print(
            f"[METRIC] Cartesia first audio: "
            f"{ai_processor.cartesia_first_audio_ms:.0f} ms"
        )
        print(
            f"[METRIC] Generated audio size: "
            f"{ai_processor.audio_size} bytes"
        )
        print(
            f"[METRIC] Complete test time: "
            f"{total_ms:.0f} ms"
        )
        print(
            f"[OUTPUT] "
            f"{ai_processor.audio_path.resolve()}"
        )
        print(
            "[PIPELINE] RECORDED FULL PIPELINE "
            "TEST PASSED"
        )
        print("=" * 72)
        print("")

        try:
            os.startfile(
                ai_processor.audio_path.resolve()
            )
            print(
                "[PIPELINE] Opening generated audio..."
            )
        except OSError as error:
            print(
                "[PIPELINE] Audio was created, but "
                f"automatic playback failed: {error}"
            )

        return 0

    except ScribeProviderError as error:
        print("")
        print("[PIPELINE] TEST FAILED AT SCRIBE")
        print(f"[ERROR] {error}")
        return 1

    except RecordedPipelineError as error:
        print("")
        print("[PIPELINE] TEST FAILED")
        print(f"[ERROR] {error}")
        return 1

    except Exception as error:
        print("")
        print("[PIPELINE] TEST FAILED")
        print(
            f"[UNEXPECTED ERROR] "
            f"{type(error).__name__}: {error}"
        )
        return 1


def main() -> int:
    return asyncio.run(run_test())


if __name__ == "__main__":
    raise SystemExit(main())