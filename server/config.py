from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TK_", extra="ignore")

    env: str = "development"
    database_url: str = "sqlite:///./runtime/platform.sqlite3"
    data_dir: Path = Path("runtime")
    public_base: str = "http://127.0.0.1:8000"
    admin_user: str = "admin"
    admin_password: str = "change-this-before-use"
    admin_password_hash: str = ""
    session_secret: str = "local-development-session-secret-change-me"
    license_secret: str = "local-development-license-secret-change-me"
    local_service_secret: str = "local-development-service-secret-change-me"
    update_private_key: str = ""
    update_public_key: str = ""
    session_hours: int = 8
    max_upload_mb: int = 500
    dev_verify_code: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@wdai.cc"
    verify_code_ttl_minutes: int = 10
    verify_code_cooldown_seconds: int = 60
    user_session_hours: int = 720

    @property
    def downloads_dir(self) -> Path:
        return self.data_dir / "downloads"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.downloads_dir, self.backups_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    value = Settings()
    value.ensure_dirs()
    return value
