import base64
import json
import time

from fastapi import WebSocket


class TwilioAudioSenderError(RuntimeError):
    """Raised when audio cannot be sent to Twilio."""


class TwilioAudioSender:
    """
    Sends raw 8 kHz μ-law audio to Twilio Media Streams.

    Supports:
    - Sending one realtime audio chunk
    - Sending complete buffered audio
    - Sending a playback mark
    """

    def __init__(
        self,
        websocket: WebSocket,
        stream_sid: str,
        interruption_event,
        pending_marks: set[str],
    ) -> None:
        self.websocket = websocket
        self.stream_sid = stream_sid.strip()
        self.interruption_event = interruption_event
        self.pending_marks = pending_marks

        self.total_chunks_sent = 0
        self.total_bytes_sent = 0

        if not self.stream_sid:
            raise TwilioAudioSenderError(
                "Twilio stream SID is missing."
            )

    async def send_chunk(
        self,
        audio_chunk: bytes,
    ) -> bool:
        """
        Send one Cartesia μ-law audio chunk immediately.

        Returns False when playback was interrupted.
        """

        if not audio_chunk:
            return True

        if self.interruption_event.is_set():
            print(
                "[TWILIO AUDIO] Chunk discarded after interruption"
            )
            return False

        encoded_audio = base64.b64encode(
            audio_chunk
        ).decode("ascii")

        media_message = {
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {
                "payload": encoded_audio,
            },
        }

        await self.websocket.send_text(
            json.dumps(media_message)
        )

        self.total_chunks_sent += 1
        self.total_bytes_sent += len(audio_chunk)

        return True

    async def send_audio(
        self,
        audio: bytes,
        bytes_per_chunk: int = 800,
    ) -> bool:
        """
        Send already-buffered audio in smaller chunks.

        This keeps compatibility with the existing phone pipeline.
        """

        if not audio:
            raise TwilioAudioSenderError(
                "Cannot send empty audio to Twilio."
            )

        if bytes_per_chunk <= 0:
            raise TwilioAudioSenderError(
                "bytes_per_chunk must be greater than zero."
            )

        for index in range(
            0,
            len(audio),
            bytes_per_chunk,
        ):
            audio_chunk = audio[
                index:index + bytes_per_chunk
            ]

            sent = await self.send_chunk(
                audio_chunk
            )

            if not sent:
                return False

        await self.send_mark()

        print(
            "[TWILIO AUDIO] Buffered audio sent"
        )
        print(
            f"[TWILIO AUDIO] Chunks: "
            f"{self.total_chunks_sent}"
        )
        print(
            f"[TWILIO AUDIO] Bytes: "
            f"{self.total_bytes_sent}"
        )

        return True

    async def send_mark(
        self,
    ) -> str | None:
        """
        Send a mark after all response audio has been queued.
        """

        if self.interruption_event.is_set():
            return None

        mark_name = (
            "assistant-response-"
            f"{int(time.time() * 1000)}"
        )

        mark_message = {
            "event": "mark",
            "streamSid": self.stream_sid,
            "mark": {
                "name": mark_name,
            },
        }

        self.pending_marks.add(
            mark_name
        )

        await self.websocket.send_text(
            json.dumps(mark_message)
        )

        print(
            f"[TWILIO AUDIO] Mark sent: {mark_name}"
        )

        return mark_name