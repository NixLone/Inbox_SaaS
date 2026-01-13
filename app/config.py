import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # Telegram
    bot_token: str
    # Storage
    db_path: str

    # Bot polling
    poll_interval_sec: float

    # Safety / ops
    telegram_dry_run: bool
    log_level: str


def get_settings() -> Settings:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    db_path = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "app.db"))

    poll_interval_sec = float(os.getenv("POLL_INTERVAL_SEC", "1.0"))
    telegram_dry_run = os.getenv("TELEGRAM_DRY_RUN", "0").strip() in {"1", "true", "True", "yes", "Y"}
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    return Settings(
        bot_token=bot_token,
        db_path=db_path,
        poll_interval_sec=poll_interval_sec,
        telegram_dry_run=telegram_dry_run,
        log_level=log_level,
    )
