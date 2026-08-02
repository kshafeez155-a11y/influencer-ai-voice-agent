import asyncio
import json
import threading
import time
from contextlib import suppress

from cartesia import AsyncCartesia
from fastapi import WebSocket

from app.conversation.history import ConversationHistory
from app.core.settings import get_settings
from app.observability.call_latency import CallLatencyTracker
from app.providers.streaming_llm import StreamingLLM
from app.telephony.twilio_audio_sender import TwilioAudioSender


SYSTEM_PROMPT = """
You are a professional phone voice assistant for a business promotion
agency.

The configured language for this agent is English.

Language rules:
- Always respond in English.
- Never respond in Portuguese, Spanish, French, Hindi, Telugu, Kannada,
  or any other language unless the configured language is changed.
- Understand mixed-language caller speech, but respond only in English.
- Never ask the caller to select a language.
- Do not mention language detection.

Conversation rules:
- Keep every response brief and natural.
- Use no more than two short sentences.
- Ask only one question at a time.
- Remember information already provided by the caller.
- Do not invent prices, dates, availability, services, or booking
  confirmations.
- Do not use markdown, numbered lists, or bullet points.
- Speak naturally like a professional human phone assistant.
""".strip()


class TwilioVoiceAgentError(RuntimeError):
    """Raised when a phone AI response cannot be generated."""


class TwilioVoiceAgent:
    """
    Stream Groq text into Cartesia and send each audio chunk to Twilio.

    One Cartesia WebSocket context is used for the complete assistant turn.
    Groq phrases are pushed into Cartesia as soon as they are available,
    while Cartesia audio is received and forwarded to Twilio concurrently.
    """

    def __init__(
        self,
        twilio_websocket: WebSocket,
    ) -> None:
        settings = get_settings()

        self.twilio_websocket = twilio_websocket
        self.cartesia_api_key = settings.cartesia_api_key.strip()
        self.cartesia_voice_id = settings.cartesia_voice_id.strip()
        self.cartesia_model = settings.cartesia_model.strip()

        if not self.cartesia_api_key:
            raise TwilioVoiceAgentError(
                "CARTESIA_API_KEY is missing from .env."
            )

        if not self.cartesia_voice_id:
            raise TwilioVoiceAgentError(
                "CARTESIA_VOICE_ID is missing from .env."
            )

        if not self.cartesia_model:
            raise TwilioVoiceAgentError(
                "CARTESIA_MODEL is missing from .env."
            )

        self.history = ConversationHistory(
            system_prompt=SYSTEM_PROMPT,
            max_messages=20,
        )

        self.stream_sid = ""
        self.response_lock = asyncio.Lock()
        self.interruption_event = asyncio.Event()
        self.response_active = False
        self.pending_marks: set[str] = set()

    def set_stream_sid(
        self,
        stream_sid: str,
    ) -> None:
        """Store the active Twilio Media Stream SID."""

        self.stream_sid = stream_sid.strip()

    def can_be_interrupted(self) -> bool:
        """Return True while generation or Twilio playback is active."""

        return self.response_active or bool(self.pending_marks)

    async def interrupt(self) -> bool:
        """Stop the current response and clear Twilio's playback buffer."""

        if not self.can_be_interrupted():
            return False

        if self.interruption_event.is_set():
            return False

        if not self.stream_sid:
            return False

        self.interruption_event.set()

        await self.twilio_websocket.send_text(
            json.dumps(
                {
                    "event": "clear",
                    "streamSid": self.stream_sid,
                }
            )
        )

        self.pending_marks.clear()

        print("")
        print("[BARGE-IN] Caller started speaking")
        print("[BARGE-IN] Twilio playback buffer cleared")
        print("")

        return True

    def handle_playback_mark(
        self,
        mark_name: str,
    ) -> None:
        """Remove a completed or cleared Twilio playback mark."""

        clean_mark_name = mark_name.strip()

        if clean_mark_name:
            self.pending_marks.discard(clean_mark_name)

        if not self.pending_marks and not self.response_active:
            print("[PHONE AGENT] Playback finished")

    async def respond_to_transcript(
        self,
        transcript: str,
    ) -> None:
        """
        Produce one assistant turn using true text-to-audio streaming.

        Pipeline:
        final transcript
        -> Groq phrase stream
        -> one Cartesia realtime WebSocket context
        -> TwilioAudioSender.send_chunk()
        -> Twilio playback mark
        """

        clean_transcript = transcript.strip()

        if not clean_transcript:
            return

        if not self.stream_sid:
            raise TwilioVoiceAgentError(
                "Twilio stream SID has not been received yet."
            )

        async with self.response_lock:
            self.interruption_event.clear()
            self.response_active = True

            stop_producer = threading.Event()
            producer_task: asyncio.Task[None] | None = None
            latency = CallLatencyTracker()
            latency.mark_transcript_committed()

            try:
                print("")
                print(f"[PHONE AGENT] Caller: {clean_transcript}")

                self.history.add_user(clean_transcript)

                response_started_at = time.perf_counter()
                event_loop = asyncio.get_running_loop()

                phrase_queue: asyncio.Queue[
                    str | Exception | None
                ] = asyncio.Queue()

                messages = self.history.get_messages()

                def produce_groq_phrases() -> None:
                    """Run the blocking Groq iterator in a worker thread."""

                    try:
                        streaming_llm = StreamingLLM()

                        for phrase in streaming_llm.stream_phrases(
                            messages
                        ):
                            if stop_producer.is_set():
                                break

                            future = asyncio.run_coroutine_threadsafe(
                                phrase_queue.put(phrase),
                                event_loop,
                            )
                            future.result()

                    except Exception as error:
                        future = asyncio.run_coroutine_threadsafe(
                            phrase_queue.put(error),
                            event_loop,
                        )
                        future.result()

                    finally:
                        future = asyncio.run_coroutine_threadsafe(
                            phrase_queue.put(None),
                            event_loop,
                        )
                        future.result()

                producer_task = asyncio.create_task(
                    asyncio.to_thread(produce_groq_phrases)
                )

                sender = TwilioAudioSender(
                    websocket=self.twilio_websocket,
                    stream_sid=self.stream_sid,
                    interruption_event=self.interruption_event,
                    pending_marks=self.pending_marks,
                )

                assistant_parts: list[str] = []
                phrase_count = 0
                audio_chunk_count = 0
                first_phrase_at: float | None = None
                first_cartesia_audio_at: float | None = None
                first_twilio_audio_at: float | None = None

                async with AsyncCartesia(
                    api_key=self.cartesia_api_key,
                ) as cartesia_client:
                    async with (
                        cartesia_client.tts.websocket_connect()
                    ) as connection:
                        context = connection.context(
                            model_id=self.cartesia_model,
                            voice={
                                "mode": "id",
                                "id": self.cartesia_voice_id,
                            },
                            output_format={
                                "container": "raw",
                                "encoding": "pcm_mulaw",
                                "sample_rate": 8000,
                            },
                            language="en",
                        )

                        async def push_groq_text() -> None:
                            nonlocal phrase_count
                            nonlocal first_phrase_at

                            try:
                                while True:
                                    if self.interruption_event.is_set():
                                        stop_producer.set()
                                        break

                                    item = await phrase_queue.get()

                                    if item is None:
                                        break

                                    if isinstance(item, Exception):
                                        raise TwilioVoiceAgentError(
                                            "Groq phrase streaming failed: "
                                            f"{item}"
                                        )

                                    phrase = item.strip()

                                    if not phrase:
                                        continue

                                    if self.interruption_event.is_set():
                                        stop_producer.set()
                                        break

                                    phrase_count += 1

                                    if first_phrase_at is None:
                                        first_phrase_at = (
                                            time.perf_counter()
                                        )
                                        latency.mark_first_phrase_received()

                                    assistant_parts.append(phrase)

                                    print(
                                        "[PHONE AGENT] Phrase "
                                        f"{phrase_count}: {phrase}"
                                    )

                                    await context.push(f"{phrase} ")

                            finally:
                                with suppress(Exception):
                                    await context.no_more_inputs()

                        async def forward_cartesia_audio() -> None:
                            nonlocal audio_chunk_count
                            nonlocal first_cartesia_audio_at
                            nonlocal first_twilio_audio_at

                            async for response in context.receive():
                                response_type = getattr(
                                    response,
                                    "type",
                                    "",
                                )

                                if response_type == "chunk":
                                    audio = getattr(
                                        response,
                                        "audio",
                                        None,
                                    )

                                    if not audio:
                                        continue

                                    if self.interruption_event.is_set():
                                        stop_producer.set()
                                        break

                                    if first_cartesia_audio_at is None:
                                        first_cartesia_audio_at = (
                                            time.perf_counter()
                                        )
                                        latency.mark_first_cartesia_audio()

                                    await sender.send_chunk(audio)
                                    audio_chunk_count += 1

                                    if first_twilio_audio_at is None:
                                        first_twilio_audio_at = (
                                            time.perf_counter()
                                        )
                                        latency.mark_first_twilio_audio_sent()

                                elif response_type == "done":
                                    break

                                elif response_type == "error":
                                    message = (
                                        getattr(
                                            response,
                                            "message",
                                            None,
                                        )
                                        or getattr(
                                            response,
                                            "title",
                                            None,
                                        )
                                        or getattr(
                                            response,
                                            "error",
                                            None,
                                        )
                                        or "Unknown Cartesia error"
                                    )

                                    raise TwilioVoiceAgentError(
                                        f"Cartesia realtime TTS failed: "
                                        f"{message}"
                                    )

                        text_task = asyncio.create_task(
                            push_groq_text()
                        )
                        audio_task = asyncio.create_task(
                            forward_cartesia_audio()
                        )

                        try:
                            await asyncio.gather(
                                text_task,
                                audio_task,
                            )
                        except Exception:
                            stop_producer.set()

                            for task in (
                                text_task,
                                audio_task,
                            ):
                                if not task.done():
                                    task.cancel()

                            await asyncio.gather(
                                text_task,
                                audio_task,
                                return_exceptions=True,
                            )
                            raise

                stop_producer.set()

                if producer_task is not None:
                    await producer_task

                if self.interruption_event.is_set():
                    print("[PHONE AGENT] Response interrupted")
                    return

                assistant_text = " ".join(
                    assistant_parts
                ).strip()

                if not assistant_text:
                    raise TwilioVoiceAgentError(
                        "Groq returned no response text."
                    )

                if audio_chunk_count == 0:
                    raise TwilioVoiceAgentError(
                        "Cartesia returned no telephone audio."
                    )

                self.history.add_assistant(assistant_text)

                mark_name = await self._send_playback_mark()

                complete_ms = (
                    time.perf_counter()
                    - response_started_at
                ) * 1000

                print(f"[PHONE AGENT] Assistant: {assistant_text}")
                print(
                    "[PHONE AGENT] Total phrases: "
                    f"{phrase_count}"
                )
                print(
                    "[PHONE AGENT] Audio chunks sent: "
                    f"{audio_chunk_count}"
                )
                print(
                    "[PHONE AGENT] Playback mark sent: "
                    f"{mark_name}"
                )

                if first_phrase_at is not None:
                    print(
                        "[PHONE AGENT] First Groq phrase: "
                        f"{(first_phrase_at - response_started_at) * 1000:.0f} ms"
                    )

                if first_cartesia_audio_at is not None:
                    print(
                        "[PHONE AGENT] First Cartesia audio: "
                        f"{(first_cartesia_audio_at - response_started_at) * 1000:.0f} ms"
                    )

                if first_twilio_audio_at is not None:
                    print(
                        "[PHONE AGENT] First Twilio audio sent: "
                        f"{(first_twilio_audio_at - response_started_at) * 1000:.0f} ms"
                    )

                print(
                    "[PHONE AGENT] Complete response: "
                    f"{complete_ms:.0f} ms"
                )

                latency.mark_response_completed()
                latency.print_report()
                print("")

            finally:
                stop_producer.set()

                if (
                    producer_task is not None
                    and not producer_task.done()
                ):
                    with suppress(Exception):
                        await asyncio.wait_for(
                            producer_task,
                            timeout=2.0,
                        )

                self.response_active = False

    async def _send_playback_mark(self) -> str:
        """Send one Twilio mark after all response audio was queued."""

        if not self.stream_sid:
            raise TwilioVoiceAgentError(
                "Cannot send playback mark because stream SID is missing."
            )

        mark_name = (
            "assistant-response-"
            f"{int(time.time() * 1000)}"
        )

        self.pending_marks.add(mark_name)

        try:
            await self.twilio_websocket.send_text(
                json.dumps(
                    {
                        "event": "mark",
                        "streamSid": self.stream_sid,
                        "mark": {
                            "name": mark_name,
                        },
                    }
                )
            )
        except Exception:
            self.pending_marks.discard(mark_name)
            raise

        return mark_name
