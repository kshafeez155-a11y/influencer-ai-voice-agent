import asyncio
import time
import winsound
from pathlib import Path

from app.conversation.history import ConversationHistory
from app.providers.llm_groq import (
    GroqLLMProvider,
    GroqProviderError,
)
from app.providers.tts_cartesia import (
    CartesiaProviderError,
    CartesiaTTSProvider,
)
from scripts.test_live_scribe import (
    LiveScribeError,
    LiveScribeTest,
)


MAX_TURNS = 10

EXIT_PHRASES = {
    "bye",
    "goodbye",
    "exit",
    "stop",
    "end call",
    "thank you bye",
}

SYSTEM_PROMPT = """
You are a professional phone voice assistant for a business promotion
agency.

Rules:
- Keep replies brief and natural.
- Use no more than two short sentences.
- Ask only one question at a time.
- Remember details the user already provided.
- Do not repeat questions that were already answered.
- Do not invent prices, dates, services, or booking confirmations.
- Confirm important names and contact details when needed.
- Reply in the language used by the caller.
- Handle English and Telugu mixed speech naturally.
- If the user says goodbye, give a short polite closing.
""".strip()


def should_end_conversation(text: str) -> bool:
    normalized = " ".join(
        text.lower().strip().replace(".", " ").split()
    )

    return any(
        phrase == normalized
        or phrase in normalized
        for phrase in EXIT_PHRASES
    )


def play_wav(audio_path: Path) -> None:
    winsound.PlaySound(
        str(audio_path.resolve()),
        winsound.SND_FILENAME,
    )


async def generate_assistant_response(
    history: ConversationHistory,
) -> tuple[str, float]:
    provider = GroqLLMProvider()

    print("[GROQ] Assistant: ", end="", flush=True)

    started_at = time.perf_counter()
    first_token_ms: float | None = None
    response_parts: list[str] = []

    for token in provider.stream_messages(
        history.get_messages()
    ):
        if first_token_ms is None:
            first_token_ms = (
                time.perf_counter() - started_at
            ) * 1000

        print(token, end="", flush=True)
        response_parts.append(token)

    print("")

    response = "".join(response_parts).strip()

    if not response:
        raise GroqProviderError(
            "Groq returned an empty assistant response."
        )

    if first_token_ms is None:
        raise GroqProviderError(
            "Groq returned no streamed tokens."
        )

    return response, first_token_ms


async def create_and_play_response(
    text: str,
    turn_number: int,
) -> tuple[Path, float]:
    output_path = Path(
        f"output/continuous-turn-{turn_number}.wav"
    )

    provider = CartesiaTTSProvider()

    (
        audio_path,
        first_audio_ms,
        _audio_size,
    ) = await asyncio.to_thread(
        provider.generate_wav,
        text,
        output_path,
    )

    print("[VOICE AGENT] Playing response...")

    await asyncio.to_thread(
        play_wav,
        audio_path,
    )

    return audio_path, first_audio_ms


async def run_conversation() -> int:
    print("")
    print("=" * 74)
    print("CONTINUOUS AI VOICE CONVERSATION")
    print("=" * 74)
    print(
        "[VOICE AGENT] Speak after the listening prompt."
    )
    print(
        "[VOICE AGENT] Say goodbye, bye, exit, "
        "stop, or end call to finish."
    )
    print(
        f"[VOICE AGENT] Maximum turns: {MAX_TURNS}"
    )
    print("=" * 74)

    history = ConversationHistory(
        system_prompt=SYSTEM_PROMPT,
        max_messages=20,
    )

    for turn_number in range(1, MAX_TURNS + 1):
        print("")
        print("-" * 74)
        print(
            f"[VOICE AGENT] TURN "
            f"{turn_number}/{MAX_TURNS}"
        )
        print("-" * 74)

        turn_started_at = time.perf_counter()

        live_stt = LiveScribeTest()
        user_text = await live_stt.run()
        user_text = user_text.strip()

        if not user_text:
            print(
                "[VOICE AGENT] Empty transcript. "
                "Listening again..."
            )
            continue

        print("")
        print(f"[USER] {user_text}")

        history.add_user(user_text)

        user_requested_exit = should_end_conversation(
            user_text
        )

        assistant_text, groq_first_token_ms = (
            await generate_assistant_response(history)
        )

        history.add_assistant(assistant_text)

        print(f"[ASSISTANT] {assistant_text}")

        (
            audio_path,
            cartesia_first_audio_ms,
        ) = await create_and_play_response(
            assistant_text,
            turn_number,
        )

        complete_turn_ms = (
            time.perf_counter() - turn_started_at
        ) * 1000

        print("")
        print(
            f"[METRIC] Groq first token: "
            f"{groq_first_token_ms:.0f} ms"
        )
        print(
            f"[METRIC] Cartesia first audio: "
            f"{cartesia_first_audio_ms:.0f} ms"
        )
        print(
            f"[METRIC] Complete turn: "
            f"{complete_turn_ms:.0f} ms"
        )
        print(
            f"[OUTPUT] {audio_path.resolve()}"
        )
        print(
            f"[MEMORY] Completed turns: "
            f"{history.get_turn_count()}"
        )

        if user_requested_exit:
            print("")
            print(
                "[VOICE AGENT] Exit phrase detected."
            )
            print(
                "[VOICE AGENT] Conversation ended cleanly."
            )
            print(
                "[VOICE AGENT] CONTINUOUS VOICE "
                "TEST PASSED"
            )
            print("=" * 74)
            return 0

    print("")
    print(
        "[VOICE AGENT] Maximum turn limit reached."
    )
    print(
        "[VOICE AGENT] CONTINUOUS VOICE TEST PASSED"
    )
    print("=" * 74)

    return 0


async def run_test() -> int:
    try:
        return await run_conversation()

    except LiveScribeError as error:
        print("")
        print(
            "[VOICE AGENT] TEST FAILED AT "
            "LIVE TRANSCRIPTION"
        )
        print(f"[ERROR] {error}")
        return 1

    except GroqProviderError as error:
        print("")
        print(
            "[VOICE AGENT] TEST FAILED AT GROQ"
        )
        print(f"[ERROR] {error}")
        return 1

    except CartesiaProviderError as error:
        print("")
        print(
            "[VOICE AGENT] TEST FAILED AT CARTESIA"
        )
        print(f"[ERROR] {error}")
        return 1

    except KeyboardInterrupt:
        print("")
        print(
            "[VOICE AGENT] Conversation stopped "
            "by user."
        )
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