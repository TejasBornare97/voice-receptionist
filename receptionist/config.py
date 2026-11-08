import os
from dataclasses import dataclass

from dotenv import load_dotenv

# override=True: values in .env win over anything set system-wide on this machine
load_dotenv(override=True)


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    business_name: str = os.getenv("BUSINESS_NAME", "Riverside Physio")
    timezone: str = os.getenv("TIMEZONE", "Europe/London")
    sample_rate: int = 16000  # Whisper expects 16 kHz audio
    whisper_model: str = os.getenv("WHISPER_MODEL", "base.en")
    tts_voice: str = os.getenv("TTS_VOICE", "models/voices/en_GB-alba-medium.onnx")
    llm_model: str = os.getenv("LLM_MODEL", "claude-haiku-5-5")
    google_calendar_id: str = os.getenv("GOOGLE_CALENDAR_ID", "")
    calendar_backend: str = os.getenv("CALENDAR_BACKEND", "memory")  # "memory" or "google"


settings = Settings()