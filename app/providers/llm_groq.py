import time
from collections.abc import Generator
from typing import Any

from groq import Groq

from app.core.settings import get_settings
from app.utils.logger import get_logger


logger = get_logger()
settings = get_settings()


class GroqProviderError(RuntimeError):
    """Raised when Groq cannot complete a request."""


class GroqLLMProvider:
    """Provides streamed responses using Groq Chat Completions."""

    def __init__(self) -> None:
        api_key = settings.groq_api_key.strip()

        if not api_key:
            raise GroqProviderError(
                "GROQ_API_KEY is missing from the .env file."
            )

        self.model = settings.groq_model.strip()

        if not self.model:
            raise GroqProviderError(
                "GROQ_MODEL is missing from the .env file."
            )

        self.client = Groq(api_key=api_key)

    def stream_response(
        self,
        user_message: str,
    ) -> Generator[str, None, None]:
        """Stream a response for a single independent message."""

        clean_message = user_message.strip()

        if not clean_message:
            raise ValueError(
                "The user message cannot be empty."
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a professional AI voice assistant "
                    "for a business. Keep every response short, "
                    "natural, and easy to speak aloud. Ask only "
                    "one question at a time. Do not invent prices "
                    "or business details."
                ),
            },
            {
                "role": "user",
                "content": clean_message,
            },
        ]

        yield from self.stream_messages(messages)

    def stream_messages(
        self,
        messages: list[dict[str, str]],
    ) -> Generator[str, None, None]:
        """Stream a response using complete conversation history."""

        self._validate_messages(messages)

        logger.info(
            "groq_request_started",
            model=self.model,
            message_count=len(messages),
        )

        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                max_completion_tokens=150,
                stream=True,
            )

            received_text = False

            for chunk in stream:
                if not chunk.choices:
                    continue

                content = chunk.choices[0].delta.content

                if content:
                    received_text = True
                    yield content

            if not received_text:
                raise GroqProviderError(
                    "Groq returned no streamed text."
                )

        except GroqProviderError:
            raise

        except Exception as error:
            raise GroqProviderError(
                "Groq request failed: "
                f"{type(error).__name__}: {error}"
            ) from error

        logger.info(
            "groq_request_completed",
            model=self.model,
        )

    @staticmethod
    def _validate_messages(
        messages: list[dict[str, str]],
    ) -> None:
        if not messages:
            raise ValueError(
                "Conversation messages cannot be empty."
            )

        allowed_roles = {
            "system",
            "user",
            "assistant",
        }

        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                raise TypeError(
                    f"Message {index} must be a dictionary."
                )

            role = str(
                message.get("role", "")
            ).strip()

            content = str(
                message.get("content", "")
            ).strip()

            if role not in allowed_roles:
                raise ValueError(
                    f"Message {index} has invalid role: {role}"
                )

            if not content:
                raise ValueError(
                    f"Message {index} has empty content."
                )


def run_streaming_test(user_message: str) -> str:
    """Run the existing visible Phase 2 test."""

    provider = GroqLLMProvider()

    print("")
    print("=" * 65)
    print("GROQ STREAMING TEST")
    print("=" * 65)
    print(f"[GROQ] Model: {provider.model}")
    print("[GROQ] API key found")
    print(f"[USER] {user_message}")
    print("[GROQ] Starting streaming request...")
    print("")
    print("Assistant: ", end="", flush=True)

    request_started_at = time.perf_counter()
    first_token_received_at: float | None = None
    response_parts: list[str] = []

    for token in provider.stream_response(user_message):
        if first_token_received_at is None:
            first_token_received_at = time.perf_counter()

        print(token, end="", flush=True)
        response_parts.append(token)

    request_completed_at = time.perf_counter()
    complete_response = "".join(response_parts).strip()

    print("")
    print("")

    if not complete_response:
        raise GroqProviderError(
            "Groq completed the request but returned no text."
        )

    if first_token_received_at is None:
        raise GroqProviderError(
            "Groq returned no streamed text tokens."
        )

    first_token_ms = (
        first_token_received_at - request_started_at
    ) * 1000

    total_ms = (
        request_completed_at - request_started_at
    ) * 1000

    print(
        f"[GROQ] First token received in "
        f"{first_token_ms:.0f} ms"
    )
    print(
        f"[GROQ] Complete response received in "
        f"{total_ms:.0f} ms"
    )
    print(
        f"[GROQ] Response length: "
        f"{len(complete_response)} characters"
    )
    print("[GROQ] STREAMING TEST PASSED")
    print("=" * 65)
    print("")

    return complete_response