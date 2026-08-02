import time
import wave
from pathlib import Path

import pyaudio


OUTPUT_FILE = Path("output/microphone-test.wav")

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_FORMAT = pyaudio.paInt16
CHUNK_SIZE = 1024
RECORD_SECONDS = 5


def record_audio(
    audio: pyaudio.PyAudio,
    input_device_index: int | None = None,
) -> Path:
    """Record microphone audio and save it as a WAV file."""

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("")
    print("[AUDIO] Opening microphone...")

    stream = audio.open(
        format=SAMPLE_FORMAT,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        input_device_index=input_device_index,
        frames_per_buffer=CHUNK_SIZE,
    )

    frames: list[bytes] = []

    print("")
    print("=" * 62)
    print("[AUDIO] RECORDING FOR 5 SECONDS")
    print("[AUDIO] Say: Hello, this is my microphone test.")
    print("=" * 62)

    try:
        chunks_to_record = int(
            SAMPLE_RATE / CHUNK_SIZE * RECORD_SECONDS
        )

        for current_chunk in range(chunks_to_record):
            data = stream.read(
                CHUNK_SIZE,
                exception_on_overflow=False,
            )
            frames.append(data)

            elapsed_seconds = int(
                current_chunk
                * CHUNK_SIZE
                / SAMPLE_RATE
            )

            remaining = max(
                RECORD_SECONDS - elapsed_seconds,
                0,
            )

            print(
                f"\r[AUDIO] Recording... "
                f"{remaining} seconds remaining",
                end="",
                flush=True,
            )

    finally:
        stream.stop_stream()
        stream.close()

    print("")
    print("[AUDIO] Recording finished")

    with wave.open(str(OUTPUT_FILE), "wb") as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(
            audio.get_sample_size(SAMPLE_FORMAT)
        )
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(b"".join(frames))

    print(
        f"[AUDIO] Recording saved: "
        f"{OUTPUT_FILE.resolve()}"
    )

    return OUTPUT_FILE


def play_audio(
    audio: pyaudio.PyAudio,
    audio_file: Path,
    output_device_index: int | None = None,
) -> None:
    """Play a WAV file through the selected speaker."""

    print("")
    print("[AUDIO] Playing recording in 2 seconds...")
    time.sleep(2)

    with wave.open(str(audio_file), "rb") as wav_file:
        stream = audio.open(
            format=audio.get_format_from_width(
                wav_file.getsampwidth()
            ),
            channels=wav_file.getnchannels(),
            rate=wav_file.getframerate(),
            output=True,
            output_device_index=output_device_index,
        )

        try:
            while True:
                data = wav_file.readframes(CHUNK_SIZE)

                if not data:
                    break

                stream.write(data)

        finally:
            stream.stop_stream()
            stream.close()

    print("[AUDIO] Playback finished")


def main() -> int:
    print("")
    print("=" * 62)
    print("LOCAL MICROPHONE AND SPEAKER TEST")
    print("=" * 62)

    audio = pyaudio.PyAudio()

    try:
        recording = record_audio(audio)
        play_audio(audio, recording)

        if not recording.exists():
            raise RuntimeError(
                "The microphone recording was not created."
            )

        if recording.stat().st_size == 0:
            raise RuntimeError(
                "The microphone recording is empty."
            )

        print("")
        print(
            f"[AUDIO] File size: "
            f"{recording.stat().st_size} bytes"
        )
        print(
            "[AUDIO] MICROPHONE AND SPEAKER TEST PASSED"
        )
        print("=" * 62)
        print("")

        return 0

    except Exception as error:
        print("")
        print(
            "[AUDIO] MICROPHONE AND SPEAKER TEST FAILED"
        )
        print(
            f"[ERROR] {type(error).__name__}: {error}"
        )
        return 1

    finally:
        audio.terminate()


if __name__ == "__main__":
    raise SystemExit(main())