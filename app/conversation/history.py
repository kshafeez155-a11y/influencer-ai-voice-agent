from copy import deepcopy


class ConversationHistory:
    """Stores the system, user, and assistant messages for one call."""

    def __init__(
        self,
        system_prompt: str,
        max_messages: int = 20,
    ) -> None:
        clean_prompt = system_prompt.strip()

        if not clean_prompt:
            raise ValueError("The system prompt cannot be empty.")

        if max_messages < 3:
            raise ValueError(
                "max_messages must be at least 3."
            )

        self.system_prompt = clean_prompt
        self.max_messages = max_messages

        self.messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": clean_prompt,
            }
        ]

    def add_user(self, text: str) -> None:
        clean_text = text.strip()

        if not clean_text:
            raise ValueError(
                "The user message cannot be empty."
            )

        self.messages.append(
            {
                "role": "user",
                "content": clean_text,
            }
        )

        self._trim_history()

    def add_assistant(self, text: str) -> None:
        clean_text = text.strip()

        if not clean_text:
            raise ValueError(
                "The assistant message cannot be empty."
            )

        self.messages.append(
            {
                "role": "assistant",
                "content": clean_text,
            }
        )

        self._trim_history()

    def get_messages(self) -> list[dict[str, str]]:
        """Return a safe copy for sending to the LLM."""

        return deepcopy(self.messages)

    def get_turn_count(self) -> int:
        """Return the number of completed assistant turns."""

        return sum(
            1
            for message in self.messages
            if message["role"] == "assistant"
        )

    def reset(self) -> None:
        """Clear the conversation but preserve the system prompt."""

        self.messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            }
        ]

    def _trim_history(self) -> None:
        """Keep the system prompt and the newest messages."""

        if len(self.messages) <= self.max_messages:
            return

        recent_messages = self.messages[
            -(self.max_messages - 1):
        ]

        self.messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            },
            *recent_messages,
        ]