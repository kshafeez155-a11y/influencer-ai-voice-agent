import asyncio
import time

import pyaudio

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams, VADState


SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_FORMAT = pyaudio.paInt16
BYTES_PER_SAMPLE = 2
TEST_SECONDS = 20


async def run_vad_test() -> int:
    print("")
    print("=" * 68)
    print("SILERO VAD MICROPHONE TEST")
    print("=" * 68)
    print("[VAD] The test will run for 20 seconds.")
    print("[VAD] Speak, pause, then speak again.")
    print("[VAD] Press Ctrl + C to stop early.")
    print("")

    analyzer = SileroVADAnalyzer(
        params=VADParams(
            confidence=0.65,
            start_secs=0.15,
            stop_secs=0.20,
            min_volume=0.5,
        )
    )

    # Required for this Pipecat version.
    analyzer.set_sample_rate(SAMPLE_RATE)

    samples_per_chunk = analyzer.num_frames_required()
    chunk_bytes = samples_per_chunk * BYTES_PER_SAMPLE

    print(
        f"[VAD] Required samples per chunk: "
        f"{samples_per_chunk}"
    )

    audio = pyaudio.PyAudio()

    stream = audio.open(
        format=SAMPLE_FORMAT,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=samples_per_chunk,
    )

    previous_state = VADState.QUIET
    speech_start_count = 0
    speech_stop_count = 0
    started_at = time.perf_counter()

    try:
        while time.perf_counter() - started_at < TEST_SECONDS:
            audio_chunk = stream.read(
                samples_per_chunk,
                exception_on_overflow=False,
            )

            if len(audio_chunk) != chunk_bytes:
                continue

            state = await analyzer.analyze_audio(audio_chunk)

            if (
                state == VADState.SPEAKING
                and previous_state != VADState.SPEAKING
            ):
                speech_start_count += 1
                elapsed = time.perf_counter() - started_at

                print(
                    f"[VAD] SPEECH STARTED at "
                    f"{elapsed:.2f}s"
                )

            if (
                state == VADState.QUIET
                and previous_state != VADState.QUIET
            ):
                speech_stop_count += 1
                elapsed = time.perf_counter() - started_at

                print(
                    f"[VAD] SPEECH STOPPED at "
                    f"{elapsed:.2f}s"
                )

            previous_state = state
            await asyncio.sleep(0)

    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()

    print("")
    print("-" * 68)
    print(
        f"[VAD] Speech starts detected: "
        f"{speech_start_count}"
    )
    print(
        f"[VAD] Speech stops detected: "
        f"{speech_stop_count}"
    )

    if speech_start_count < 1 or speech_stop_count < 1:
        print("[VAD] TEST FAILED")
        print(
            "[FIX] Speak clearly for 2–3 seconds and "
            "remain silent for at least 1 second."
        )
        return 1

    print("[VAD] SILERO VAD TEST PASSED")
    print("=" * 68)
    print("")

    return 0


def main() -> int:
    try:
        return asyncio.run(run_vad_test())

    except KeyboardInterrupt:
        print("")
        print("[VAD] Test stopped by user.")
        return 0

    except Exception as error:
        print("")
        print("[VAD] TEST FAILED")
        print(
            f"[ERROR] {type(error).__name__}: {error}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())