"""Settings from the environment (deploy/.env)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://dates:dates@localhost:5432/dates"
    dates_key: str = ""
    trusted_proxy: str = "192.168.0.70"
    # Lets the API run without Caddy in front (local dev and tests only)
    dev_user: str = ""

    # The AI hub gateway: the Ollama API plus Whisper, with one queue for the GPU
    ollama_url: str = "http://ai-hub:11434"
    llm_model: str = "gemma4:e4b"
    embed_model: str = "nomic-embed-text"

    ha_url: str = "http://192.168.0.108:8123"
    ha_token: str = ""
    notify_targets: str = ""

    ticketmaster_key: str = ""

    photon_url: str = "http://photon:2322"
    osrm_car_url: str = "http://osrm-car:5000"
    osrm_foot_url: str = "http://osrm-foot:5000"
    searxng_url: str = "http://searxng:8080"

    data_dir: Path = Path("/data")
    # Built SvelteKit app (copied in by deploy/Dockerfile.app)
    static_dir: Path = Path("/app/static")
    default_tz: str = "America/Los_Angeles"


@lru_cache
def get_settings() -> Settings:
    return Settings()
