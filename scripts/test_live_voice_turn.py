import asyncio
import time
import winsound
from pathlib import Path

from pipecat.frames.frames import EndFrame, TextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask

from app.pipeline.recorded_pipeline import (
    RecordedAIProcessor,
    RecordedPipelineError,
)
from scripts.test_live_scribe import (
    LiveScribeError,
    LiveScribeTest,
)


OUTPUT_FILE = Path(
    "output/live-voice-turn.wav"
)


async def run_test() -> int:
    print("")
    print("=" * 72)
    print("LIVE AI VOICE TURN TEST")
    print("=" * 72)

    total_started_at = time.perf_counter()

    try:
        # -------------------------------------------------
        # STEP 1 — LIVE MICROPHONE TRANSCRIPTION
        # -------------------------------------------------

        print("")
        print("[VOICE AGENT] STEP 1 — Listen to the user")

        live_stt = LiveScribeTest()
        transcript = await live_stt.run()

        if not transcript.strip():
            raise LiveScribeError(
                "The live transcript was empty."
            )

        print("")
        print(f"[USER] {transcript}")

        # -------------------------------------------------
        # STEP 2 — PIPECAT → GROQ → CARTESIA
        # -------------------------------------------------

        print("")
        print(
            "[VOICE AGENT] STEP 2 — "
            "Generate and speak the reply"
        )

        ai_processor = RecordedAIProcessor(
            output_file=OUTPUT_FILE,
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
        # STEP 3 — VERIFY OUTPUT
        # -------------------------------------------------

        if not ai_processor.assistant_response:
            raise RecordedPipelineError(
                "Groq returned no assistant response."
            )

        if ai_processor.audio_path is None:
            raise RecordedPipelineError(
                "Cartesia returned no audio path."
            )

        if not ai_processor.audio_path.exists():
            raise RecordedPipelineError(
                "The generated audio file does not exist."
            )

        if ai_processor.audio_path.stat().st_size == 0:
            raise RecordedPipelineError(
                "The generated audio file is empty."
            )

        print("")
        print(
            f"[ASSISTANT] "
            f"{ai_processor.assistant_response}"
        )
        print(
            "[VOICE AGENT] Playing the response..."
        )

        await asyncio.to_thread(
            winsound.PlaySound,
            str(ai_processor.audio_path.resolve()),
            winsound.SND_FILENAME,
        )

        total_ms = (
            time.perf_counter() - total_started_at
        ) * 1000

        print("")
        print("-" * 72)
        print("[VOICE AGENT] FINAL RESULTS")
        print("-" * 72)
        print(f"[USER] {transcript}")
        print(
            f"[ASSISTANT] "
            f"{ai_processor.assistant_response}"
        )

        if ai_processor.groq_first_token_ms is not None:
            print(
                "[METRIC] Groq first token: "
                f"{ai_processor.groq_first_token_ms:.0f} ms"
            )

        if ai_processor.cartesia_first_audio_ms is not None:
            print(
                "[METRIC] Cartesia first audio: "
                f"{ai_processor.cartesia_first_audio_ms:.0f} ms"
            )

        print(
            f"[METRIC] Complete turn time: "
            f"{total_ms:.0f} ms"
        )
        print(
            f"[OUTPUT] "
            f"{ai_processor.audio_path.resolve()}"
        )
        print(
            "[VOICE AGENT] LIVE VOICE TURN TEST PASSED"
        )
        print("=" * 72)
        print("")

        return 0

    except LiveScribeError as error:
        print("")
        print("[VOICE AGENT] TEST FAILED AT LIVE STT")
        print(f"[ERROR] {error}")
        return 1

    except RecordedPipelineError as error:
        print("")
        print("[VOICE AGENT] TEST FAILED")
        print(f"[ERROR] {error}")
        return 1

    except KeyboardInterrupt:
        print("")
        print("[VOICE AGENT] Test stopped by user.")
        return 0

    except Exception as error:
        print("")
        print("[VOICE AGENT] TEST FAILED")
        print(
            f"[UNEXPECTED ERROR] "
            f"{type(error).__name__}: {error}"
        )
        return 1


def main() -> int:
    return asyncio.run(run_test())


if __name__ == "__main__":
    raise SystemExit(main())