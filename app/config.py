"""
Конфігурація додатка
"""

from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    """Налаштування додатка"""
    
    # Application
    APP_NAME: str = "ProСвітло"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    PORT: int = 8000  # Порт для запуску (8080 на Fly.io)
    BASE_URL: str = "https://prosvitlo-backend.fly.dev"  # Базова URL для формування посилань
    
    # Database
    DATABASE_URL: str = "sqlite:////data/prosvitlo.db"  # /data - це Fly.io volume
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8080",
    ]
    
    # Firebase
    FIREBASE_CREDENTIALS_PATH: Optional[str] = None
    
    # Telegram Bot
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHANNEL_ID: Optional[str] = None
    TELEGRAM_ENABLED: bool = False
    
    # Donation settings
    DONATION_JAR_URL: Optional[str] = None
    DONATION_CARD_NUMBER: Optional[str] = None
    DONATION_DESCRIPTION: Optional[str] = None
    
    # Scheduler
    SCRAPER_INTERVAL_MINUTES: int = 30
    # Check interval: 5 for frequent checks (every 5 minutes), 60 for hourly checks
    CHECK_INTERVAL_MINUTES: int = 60
    
    # ===== Multi-region support =====
    # Supported regions: hoe (Хмельницька), voe (Вінницька)
    ENABLED_REGIONS: List[str] = ["hoe"]  # За замовчуванням тільки HOE
    
    # HOE (Хмельницькобленерго) - завжди увімкнено
    HOE_ENABLED: bool = True
    
    # VOE (Вінницяобленерго) - вимкнено до готовності
    VOE_ENABLED: bool = False
    VOE_EMERGENCY_URL: str = "https://www.voe.com.ua/disconnection/emergency"
    VOE_PLANNED_URL: str = "https://www.voe.com.ua/disconnection/planned"
    VOE_SCHEDULE_URL: str = "https://www.voe.com.ua/informatsiya-pro-cherhy-hrafika-pohodynnykh-vidklyuchen-hpv-1"
    
    # Scraper
    HOE_URL: str = "https://hoe.com.ua/page/pogodinni-vidkljuchennja"
    SCRAPER_TIMEOUT: int = 30
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
