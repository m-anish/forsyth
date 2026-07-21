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
    # 7 days: the dashboard offers a 7-day window, so the archive must actually
    # reach that far. Skill decays with lead time — the ensemble spread band is
    # what keeps the far end honest rather than hiding it.
    forecast_days: int = int(os.environ.get("FORECAST_DAYS", "7"))
    forecast_ensemble: bool = os.environ.get("FORECAST_ENSEMBLE", "true").lower() in ("1", "true", "yes")
    forecast_retention_days: int = int(os.environ.get("FORECAST_RETENTION_DAYS", "730"))

    # human weather reports (app/reports.py) — the kill switch hides the whole
    # feature: POST 404s, GET says disabled, the dashboard shows no report UI
    reports_enabled: bool = os.environ.get("REPORTS_ENABLED", "true").lower() in ("1", "true", "yes")

    # Optional keyed satellite basemap. Provider-agnostic: paste the full XYZ
    # raster template (key and all) and its required attribution. When set, the
    # map's "satellite" layer uses this proper hybrid (imagery + roads + labels
    # in one tileset); when empty it falls back to keyless Esri imagery + OSM
    # labels. The key rides in tile URLs — it is not a secret, so restrict it
    # to this domain in the provider's dashboard.
    satellite_tile_url: str = os.environ.get("SATELLITE_TILE_URL", "")
    satellite_attribution: str = os.environ.get(
        "SATELLITE_ATTRIBUTION",
        '© <a href="https://www.maptiler.com/copyright/">MapTiler</a> '
        '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>')
    satellite_max_zoom: int = int(os.environ.get("SATELLITE_MAX_ZOOM", "20"))

    # self-serve accounts (engagement-roadmap §4). OAuth providers appear in
    # the sign-in dialog only when their id+secret are set; redirect URI to
    # register with each provider: {PUBLIC_BASE_URL}/api/v1/auth/oauth/{provider}/callback
    signup_enabled: bool = os.environ.get("SIGNUP_ENABLED", "true").lower() in ("1", "true", "yes")
    google_client_id: str = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    github_client_id: str = os.environ.get("GITHUB_CLIENT_ID", "")
    github_client_secret: str = os.environ.get("GITHUB_CLIENT_SECRET", "")
    openmeteo_base_url: str = os.environ.get("OPENMETEO_BASE_URL", "https://api.open-meteo.com")
    openmeteo_ensemble_base_url: str = os.environ.get(
        "OPENMETEO_ENSEMBLE_BASE_URL", "https://ensemble-api.open-meteo.com")


settings = Settings()
