from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    
    DATABASE_URL: str
    TEST_DATABASE_URL: str | None = None 
    REDIS_URL: str
    RABBITMQ_URL: str
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    RATE_LIMIT_CAPACITY: int
    RATE_LIMIT_REFILL_RATE: int
    RATE_LIMIT_TTL: int

    model_config = SettingsConfigDict(
        env_file=f".env.{os.getenv('ENVIRONMENT', 'development')}",
        extra="ignore"
    )

settings = Settings()