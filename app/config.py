from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Kinney Aviation"
    data_dir: Path = Path("./data")
    database_url: str | None = None
    host: str = "0.0.0.0"
    port: int = 8088
    seed_demo: bool = True
    annual_window_days: int = 60

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.data_dir / 'kinney.db'}"


settings = Settings()
