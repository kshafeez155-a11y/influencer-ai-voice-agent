import asyncio

from pipecat.frames.frames import (
    EndFrame,
    Frame,
    TextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import (
    FrameDirection,
    FrameProcessor,
)


class TerminalTestProcessor(FrameProcessor):
    """Print text frames that move through the Pipecat pipeline."""

    async def process_frame(
        self,
        frame: Frame,
        direction: FrameDirection,
    ) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, TextFrame):
            print("")
            print("[PIPECAT] TextFrame received")
            print(f"[PIPECAT] Text: {frame.text}")
            print(f"[PIPECAT] Direction: {direction.name}")

        await self.push_frame(frame, direction)


async def run_test() -> int:
    print("")
    print("=" * 68)
    print("PIPECAT BASE PIPELINE TEST")
    print("=" * 68)

    processor = TerminalTestProcessor()

    pipeline = Pipeline(
        [
            processor,
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

    print("[PIPECAT] Pipeline created")
    print("[PIPECAT] Queueing test TextFrame")

    await task.queue_frame(
        TextFrame(
            text=(
                "Hello from the first Pipecat pipeline."
            )
        )
    )

    await task.queue_frame(EndFrame())

    print("[PIPECAT] Starting PipelineRunner")

    await runner.run(task)

    print("")
    print("[PIPECAT] Pipeline stopped cleanly")
    print("[PIPECAT] BASE PIPELINE TEST PASSED")
    print("=" * 68)
    print("")

    return 0


def main() -> int:
    try:
        return asyncio.run(run_test())

    except Exception as error:
        print("")
        print("[PIPECAT] BASE PIPELINE TEST FAILED")
        print(
            f"[ERROR] {type(error).__name__}: {error}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())