from collections.abc import Iterator
from typing import Any

from app.providers.llm_groq import GroqLLMProvider


class StreamingLLM:
    """
    Convert streamed Groq tokens into natural speaking phrases.
    """

    def __init__(self) -> None:
        self.provider = GroqLLMProvider()

    def stream_phrases(
        self,
        messages: list[dict[str, Any]],
    ) -> Iterator[str]:
        """
        Yield text after sentence-ending punctuation.

        A long unfinished sentence is also released so the caller
        does not wait too long for speech to begin.
        """

        buffer = ""

        sentence_endings = {
            ".",
            "?",
            "!",
            ";",
            ":",
        }

        for token in self.provider.stream_messages(
            messages
        ):
            buffer += token

            stripped_buffer = buffer.rstrip()

            reached_sentence_end = (
                bool(stripped_buffer)
                and stripped_buffer[-1]
                in sentence_endings
            )

            reached_safe_length = (
                len(buffer) >= 120
                and buffer.endswith(" ")
            )

            if (
                reached_sentence_end
                or reached_safe_length
            ):
                phrase = buffer.strip()

                if phrase:
                    yield phrase

                buffer = ""

        remaining_text = buffer.strip()

        if remaining_text:
            yield remaining_text