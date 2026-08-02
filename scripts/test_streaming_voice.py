import asyncio
import time

from app.providers.streaming_voice import (
    StreamingVoiceError,
    StreamingVoiceResponder,
)


SYSTEM_PROMPT = """
You are a professional phone voice assistant.

Rules:
- Give a natural response of no more than two short sentences.
- Ask only one question.
- Do not use markdown.
- Do not include lists.
- Make the first phrase useful and immediately speakable.
""".strip()


TEST_MESSAGE = (
    "I want to promote my clothing business "
    "using Instagram influencers."
)


async def run_test() -> int:
    print("")
    print("=" * 72)
    print("GROQ → CARTESIA TRUE STREAMING TEST")
    print("=" * 72)
    print(f"[USER] {TEST_MESSAGE}")
    print("")
    print("[GROQ] Assistant: ", end="", flush=True)

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": TEST_MESSAGE,
        },
    ]

    try:
        responder = StreamingVoiceResponder()

        (
            assistant_text,
            groq_first_token_ms,
            cartesia_first_audio_ms,
            complete_ms,
        ) = await responder.speak_from_messages(
            messages
        )

        print("")
        print("-" * 72)
        print("[STREAM] FINAL RESULTS")
        print("-" * 72)
        print(f"[ASSISTANT] {assistant_text}")
        print(
            f"[METRIC] Groq first token: "
            f"{groq_first_token_ms:.0f} ms"
        )
        print(
            f"[METRIC] First audible Cartesia audio: "
            f"{cartesia_first_audio_ms:.0f} ms"
        )
        print(
            f"[METRIC] Complete streamed playback: "
            f"{complete_ms:.0f} ms"
        )
        print(
            "[STREAM] TRUE STREAMING VOICE TEST PASSED"
        )
        print("=" * 72)
        print("")

        return 0

    except StreamingVoiceError as error:
        print("")
        print(
            "[STREAM] TRUE STREAMING VOICE TEST FAILED"
        )
        print(f"[ERROR] {error}")
        return 1

    except KeyboardInterrupt:
        print("")
        print("[STREAM] Test stopped by user.")
        return 0

    except Exception as error:
        print("")
        print(
            "[STREAM] TRUE STREAMING VOICE TEST FAILED"
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