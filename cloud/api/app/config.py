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

    # forecast layer (docs/insight-roadmap.md): open-meteo pulls, every run kept
    # so forecast-vs-observed pairs accrue. Base URLs are overridable for tests.
    forecast_enabled: bool = os.environ.get("FORECAST_ENABLED", "true").lower() in ("1", "true", "yes")
    forecast_days: int = int(os.environ.get("FORECAST_DAYS", "3"))
    forecast_ensemble: bool = os.environ.get("FORECAST_ENSEMBLE", "true").lower() in ("1", "true", "yes")
    forecast_retention_days: int = int(os.environ.get("FORECAST_RETENTION_DAYS", "730"))

    # human weather reports (app/reports.py) — the kill switch hides the whole
    # feature: POST 404s, GET says disabled, the dashboard shows no report UI
    reports_enabled: bool = os.environ.get("REPORTS_ENABLED", "true").lower() in ("1", "true", "yes")
    openmeteo_base_url: str = os.environ.get("OPENMETEO_BASE_URL", "https://api.open-meteo.com")
    openmeteo_ensemble_base_url: str = os.environ.get(
        "OPENMETEO_ENSEMBLE_BASE_URL", "https://ensemble-api.open-meteo.com")


settings = Settings()
