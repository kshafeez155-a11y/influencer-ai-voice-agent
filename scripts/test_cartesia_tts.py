import os
import sys
import time
from pathlib import Path

from app.providers.tts_cartesia import (
    CartesiaProviderError,
    CartesiaTTSProvider,
)


DEFAULT_TEXT = (
    "Hello. Thank you for contacting our promotion team. "
    "May I know the name of your business?"
)

OUTPUT_FILE = Path("output/cartesia-test.wav")


def main() -> int:
    supplied_text = " ".join(sys.argv[1:]).strip()
    test_text = supplied_text or DEFAULT_TEXT

    print("")
    print("=" * 68)
    print("CARTESIA SONIC 3.5 STREAMING TTS TEST")
    print("=" * 68)

    try:
        provider = CartesiaTTSProvider()

        print("[CARTESIA] API key found")
        print(f"[CARTESIA] Model: {provider.model}")
        print(f"[CARTESIA] Voice ID: {provider.voice_id}")
        print(f"[CARTESIA] Sample rate: {provider.sample_rate}")
        print(f"[TEXT] {test_text}")

        started_at = time.perf_counter()

        audio_path, first_audio_ms, audio_size = (
            provider.generate_wav(
                text=test_text,
                output_file=OUTPUT_FILE,
            )
        )

        total_ms = (
            time.perf_counter() - started_at
        ) * 1000

        print("")
        print("-" * 68)
        print(
            f"[CARTESIA] First audio latency: "
            f"{first_audio_ms:.0f} ms"
        )
        print(
            f"[CARTESIA] Total generation time: "
            f"{total_ms:.0f} ms"
        )
        print(f"[CARTESIA] Audio size: {audio_size} bytes")
        print(f"[CARTESIA] Audio saved: {audio_path.resolve()}")
        print("[CARTESIA] STREAMING TTS TEST PASSED")
        print("=" * 68)

        try:
            os.startfile(audio_path.resolve())
        except OSError as error:
            print(
                "[CARTESIA] Audio created, but automatic "
                f"playback failed: {error}"
            )

        return 0

    except CartesiaProviderError as error:
        print("")
        print("[CARTESIA] STREAMING TTS TEST FAILED")
        print(f"[ERROR] {error}")
        return 1

    except Exception as error:
        print("")
        print("[CARTESIA] STREAMING TTS TEST FAILED")
        print(
            f"[UNEXPECTED ERROR] "
            f"{type(error).__name__}: {error}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())