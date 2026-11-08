import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    business_name: str = os.getenv("BUSINESS_NAME", "Riverside Physio")
    timezone: str = os.getenv("TIMEZONE", "Europe/London")
    sample_rate: int = 16000  # Whisper expects 16 kHz audio


settings = Settings()