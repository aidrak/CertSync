from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings"""

    # Database
    POSTGRES_USER: str = "user"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_DB: str = "certsyncdb"
    DATABASE_URL: str = "postgresql://user:password@database:5432/certsyncdb"

    # FTP Server
    FTP_HOST: str = "ftp-server"
    FTP_PORT: int = 21
    FTP_USER: str = "certuser"
    FTP_PASS: str = "ftppassword"
    FTP_PATH: str = ""
    PFX_PASSWORD: str = "supersecretpassword"

    # Let's Encrypt
    LE_EMAIL: str = "youremail@example.com"
    LE_STAGING: bool = True

    # Security
    ENCRYPTION_KEY: str = ""

    # Default Admin User
    DEFAULT_ADMIN_USER: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = "password"

    # Logging
    LOGGING_LEVEL: str = "INFO"

    # Timezone
    TZ: str = "UTC"

    # Host Address
    HOST_ADDRESS: str = "http://localhost"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Get settings"""
    return Settings()


settings = get_settings()
