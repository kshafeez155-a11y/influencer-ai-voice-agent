import base64
import json

import structlog
from fastapi import WebSocket

log = structlog.get_logger()


class MobileAudioSender:
    """
    Sends PCM s16le 16kHz audio chunks to a mobile client over WebSocket.

    Each chunk is base64-encoded and wrapped in a JSON message:
        {"event": "audio", "data": "<base64 pcm>"}
    """

    def __init__(
        self,
        websocket: WebSocket,
        interruption_event,
    ) -> None:
        self.websocket = websocket
        self.interruption_event = interruption_event

        self.total_chunks_sent = 0
        self.total_bytes_sent = 0
        self.audio_sequence = 0

    async def send_chunk(
        self,
        audio_chunk: bytes,
    ) -> bool:
        """Send one PCM audio chunk to the mobile client."""

        if not audio_chunk:
            return True

        if self.interruption_event.is_set():
            return False

        encoded_audio = base64.b64encode(
            audio_chunk
        ).decode("ascii")

        self.audio_sequence += 1

        await self.websocket.send_text(
            json.dumps({
                "event": "audio",
                "data": encoded_audio,
                "sequence": self.audio_sequence,
            })
        )

        self.total_chunks_sent += 1
        self.total_bytes_sent += len(audio_chunk)

        return True

    async def send_transcript(self, text: str) -> None:
        """Send an assistant transcript to the mobile client."""

        await self.websocket.send_text(
            json.dumps({
                "event": "transcript",
                "text": text,
            })
        )

    async def send_user_transcript(self, text: str) -> None:
        """Show the committed caller transcript in the web client."""

        await self.websocket.send_text(
            json.dumps({
                "event": "user_transcript",
                "text": text,
            })
        )

    async def send_state(self, state: str) -> None:
        """Send a small transport-agnostic call state update."""

        await self.websocket.send_text(
            json.dumps({
                "event": "state",
                "state": state,
            })
        )

    async def send_response_done(self) -> None:
        await self.websocket.send_text(
            json.dumps({"event": "response_done"})
        )

    async def send_error(self, message: str) -> None:
        await self.websocket.send_text(
            json.dumps({
                "event": "error",
                "message": message,
            })
        )

    async def send_ready(self) -> None:
        """Signal the client that the agent is ready."""

        await self.websocket.send_text(
            json.dumps({"event": "ready"})
        )

    async def send_barge_in(self) -> None:
        """Signal the client that barge-in occurred."""

        await self.websocket.send_text(
            json.dumps({"event": "barge_in"})
        )
