from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    faas_base_url: str = "http://127.0.0.1:8000"
    faas_public_id: str = ""
    faas_api_key: str = ""
    faas_timeout_seconds: float = 40
    database_url: str = "sqlite:///./codearena.db"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

settings = Settings()

