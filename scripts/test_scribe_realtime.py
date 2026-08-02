import asyncio
import time

from app.providers.stt_scribe import (
    ScribeProviderError,
    ScribeRealtimeProvider,
)


AUDIO_FILE = "tests/audio/scribe-input.pcm"


async def run_test() -> int:
    print("")
    print("=" * 65)
    print("ELEVENLABS SCRIBE REALTIME TEST")
    print("=" * 65)

    try:
        provider = ScribeRealtimeProvider()

        print("[SCRIBE] API key found")
        print(f"[SCRIBE] Model: {provider.model}")
        print(
            f"[SCRIBE] Audio format: "
            f"{provider.audio_format}"
        )
        print(
            f"[SCRIBE] Sample rate: "
            f"{provider.sample_rate}"
        )
        print(f"[SCRIBE] Input file: {AUDIO_FILE}")

        started_at = time.perf_counter()

        transcript = await provider.transcribe_file(
            AUDIO_FILE
        )

        elapsed_ms = (
            time.perf_counter() - started_at
        ) * 1000

        print("")
        print("-" * 65)
        print(f"[FINAL TRANSCRIPT] {transcript}")
        print(
            f"[SCRIBE] Total time: "
            f"{elapsed_ms:.0f} ms"
        )
        print(
            "[SCRIBE] TRANSCRIPTION TEST PASSED"
        )
        print("=" * 65)
        print("")

        return 0

    except ScribeProviderError as error:
        print("")
        print(
            "[SCRIBE] TRANSCRIPTION TEST FAILED"
        )
        print(f"[ERROR] {error}")
        return 1

    except Exception as error:
        print("")
        print(
            "[SCRIBE] TRANSCRIPTION TEST FAILED"
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