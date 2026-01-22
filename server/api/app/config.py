from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://insights:password@localhost/claude_insights"
    api_secret_key: str = "dev-secret-key"

    class Config:
        env_file = ".env"


settings = Settings()
