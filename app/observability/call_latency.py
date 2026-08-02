import time
from dataclasses import dataclass, field


@dataclass
class CallLatencyTracker:
    """
    Measure important latency points for one caller turn.
    """

    turn_started_at: float = field(
        default_factory=time.perf_counter
    )

    transcript_committed_at: float | None = None
    first_phrase_received_at: float | None = None
    first_cartesia_audio_at: float | None = None
    first_twilio_audio_sent_at: float | None = None
    response_completed_at: float | None = None

    def mark_transcript_committed(self) -> None:
        """Record when the final caller transcript is available."""

        if self.transcript_committed_at is None:
            self.transcript_committed_at = (
                time.perf_counter()
            )

    def mark_first_phrase_received(self) -> None:
        """Record when Groq produces the first complete phrase."""

        if self.first_phrase_received_at is None:
            self.first_phrase_received_at = (
                time.perf_counter()
            )

    def mark_first_cartesia_audio(self) -> None:
        """Record when Cartesia produces its first audio."""

        if self.first_cartesia_audio_at is None:
            self.first_cartesia_audio_at = (
                time.perf_counter()
            )

    def mark_first_twilio_audio_sent(self) -> None:
        """Record when the first AI audio is sent to Twilio."""

        if self.first_twilio_audio_sent_at is None:
            self.first_twilio_audio_sent_at = (
                time.perf_counter()
            )

    def mark_response_completed(self) -> None:
        """Record when the assistant response finishes."""

        if self.response_completed_at is None:
            self.response_completed_at = (
                time.perf_counter()
            )

    @staticmethod
    def _milliseconds_between(
        start: float | None,
        end: float | None,
    ) -> float | None:
        if start is None or end is None:
            return None

        return (end - start) * 1000

    @staticmethod
    def _format_latency(
        value: float | None,
    ) -> str:
        if value is None:
            return "not measured"

        return f"{value:.0f} ms"

    def print_report(self) -> None:
        """Print a readable latency report for the caller turn."""

        transcript_to_phrase = (
            self._milliseconds_between(
                self.transcript_committed_at,
                self.first_phrase_received_at,
            )
        )

        phrase_to_cartesia = (
            self._milliseconds_between(
                self.first_phrase_received_at,
                self.first_cartesia_audio_at,
            )
        )

        cartesia_to_twilio = (
            self._milliseconds_between(
                self.first_cartesia_audio_at,
                self.first_twilio_audio_sent_at,
            )
        )

        transcript_to_twilio = (
            self._milliseconds_between(
                self.transcript_committed_at,
                self.first_twilio_audio_sent_at,
            )
        )

        total_response = (
            self._milliseconds_between(
                self.transcript_committed_at,
                self.response_completed_at,
            )
        )

        print("")
        print("=" * 60)
        print("[LATENCY] CALL TURN REPORT")
        print("=" * 60)

        print(
            "[LATENCY] Transcript → Groq first phrase: "
            f"{self._format_latency(transcript_to_phrase)}"
        )

        print(
            "[LATENCY] Groq phrase → Cartesia audio: "
            f"{self._format_latency(phrase_to_cartesia)}"
        )

        print(
            "[LATENCY] Cartesia audio → Twilio send: "
            f"{self._format_latency(cartesia_to_twilio)}"
        )

        print(
            "[LATENCY] Transcript → first Twilio audio: "
            f"{self._format_latency(transcript_to_twilio)}"
        )

        print(
            "[LATENCY] Complete response time: "
            f"{self._format_latency(total_response)}"
        )

        print("=" * 60)
        print("")