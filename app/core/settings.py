from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # =====================================================
    # APP
    # =====================================================

    app_name: str = Field(
        default="voice-ai-server",
        alias="APP_NAME",
    )

    app_env: str = Field(
        default="development",
        alias="APP_ENV",
    )

    app_host: str = Field(
        default="127.0.0.1",
        alias="APP_HOST",
    )

    app_port: int = Field(
        default=8000,
        alias="APP_PORT",
    )

    log_level: str = Field(
        default="INFO",
        alias="LOG_LEVEL",
    )

    # =====================================================
    # TWILIO
    # =====================================================

    twilio_account_sid: str = Field(
        default="",
        alias="TWILIO_ACCOUNT_SID",
    )

    twilio_auth_token: str = Field(
        default="",
        alias="TWILIO_AUTH_TOKEN",
    )

    twilio_phone_number: str = Field(
        default="",
        alias="TWILIO_PHONE_NUMBER",
    )
    public_base_url: str = Field(
        default="",
        alias="PUBLIC_BASE_URL",
    )
    test_to_phone_number: str = Field(
        default="",
        alias="TEST_TO_PHONE_NUMBER",
    )

    # =====================================================
    # ELEVENLABS SCRIBE
    # =====================================================

    elevenlabs_api_key: str = Field(
        default="",
        alias="ELEVENLABS_API_KEY",
    )

    elevenlabs_stt_model: str = Field(
        default="scribe_v2_realtime",
        alias="ELEVENLABS_STT_MODEL",
    )

    elevenlabs_stt_audio_format: str = Field(
        default="pcm",
        alias="ELEVENLABS_STT_AUDIO_FORMAT",
    )

    elevenlabs_stt_sample_rate: int = Field(
        default=16000,
        alias="ELEVENLABS_STT_SAMPLE_RATE",
    )

    # =====================================================
    # GROQ
    # =====================================================

    groq_api_key: str = Field(
        default="",
        alias="GROQ_API_KEY",
    )

    groq_model: str = Field(
        default="llama-3.3-70b-versatile",
        alias="GROQ_MODEL",
    )

    # =====================================================
    # CARTESIA
    # =====================================================

    cartesia_api_key: str = Field(
        default="",
        alias="CARTESIA_API_KEY",
    )

    cartesia_voice_id: str = Field(
        default="",
        alias="CARTESIA_VOICE_ID",
    )

    cartesia_model: str = Field(
        default="sonic-3.5",
        alias="CARTESIA_MODEL",
    )

    cartesia_sample_rate: int = Field(
        default=24000,
        alias="CARTESIA_SAMPLE_RATE",
    )

    # =====================================================
    # SUPABASE
    # =====================================================

    supabase_url: str = Field(
        default="",
        alias="SUPABASE_URL",
    )

    supabase_key: str = Field(
        default="",
        alias="SUPABASE_KEY",
    )

    # =====================================================
    # REDIS
    # =====================================================

    redis_url: str = Field(
        default="redis://localhost:6379",
        alias="REDIS_URL",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()