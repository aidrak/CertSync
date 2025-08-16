import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Database
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "user")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "password")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "certsyncdb")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@database:5432/certsyncdb")

    # FTP Server
    FTP_HOST: str = os.getenv("FTP_HOST", "ftp-server")
    FTP_PORT: int = int(os.getenv("FTP_PORT", "21"))
    FTP_USER: str = os.getenv("FTP_USER", "certuser")
    FTP_PASS: str = os.getenv("FTP_PASS", "ftppassword")
    FTP_PATH: str = os.getenv("FTP_PATH", "") 
    PFX_PASSWORD: str = os.getenv("PFX_PASSWORD", "supersecretpassword")

    # Let's Encrypt
    LE_EMAIL: str = os.getenv("LE_EMAIL", "youremail@example.com")
    LE_STAGING: bool = os.getenv("LE_STAGING", "True").lower() in ('true', '1', 't')

    # Security
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")

    # Default Admin User
    DEFAULT_ADMIN_USER: str = os.getenv("DEFAULT_ADMIN_USER", "admin")
    DEFAULT_ADMIN_PASSWORD: str = os.getenv("DEFAULT_ADMIN_PASSWORD", "password")

    # Logging
    LOGGING_LEVEL: str = os.getenv("LOGGING_LEVEL", "INFO")

    # Timezone
    TZ: str = os.getenv("TZ", "UTC")

    # Host Address
    HOST_ADDRESS: str = os.getenv("HOST_ADDRESS", "http://localhost")

settings = Settings()
