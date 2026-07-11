"""Environment-driven settings. One place, no magic."""
import os


class Settings:
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://forsyth:forsyth@localhost:5432/forsyth"
    )
    admin_key: str = os.environ.get("ADMIN_KEY", "")
    media_root: str = os.environ.get("MEDIA_ROOT", "/data/media")
    public_base_url: str = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8080")

    mqtt_host: str = os.environ.get("MQTT_HOST", "")
    mqtt_port: int = int(os.environ.get("MQTT_PORT", "1883"))
    mqtt_username: str = os.environ.get("MQTT_USERNAME", "")
    mqtt_password: str = os.environ.get("MQTT_PASSWORD", "")

    wu_enabled: bool = os.environ.get("WU_ENABLED", "false").lower() in ("1", "true", "yes")

    # optional: LLM-written weather-event summaries (falls back to rule-based)
    openai_api_key: str = os.environ.get("OPENAI_API_KEY", "")

    # readings older than this are dropped by the retention job (rollups persist)
    raw_retention_days: int = int(os.environ.get("RAW_RETENTION_DAYS", "365"))
    frame_retention_days: int = int(os.environ.get("FRAME_RETENTION_DAYS", "14"))


settings = Settings()
