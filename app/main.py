"""
Головний файл FastAPI додатка ProСвітло
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.database import init_db
from app.api.routes import router as api_router
from app.api.address_routes import router as address_router
import firebase_admin
from firebase_admin import credentials
from app.api.schedule_routes import router as schedule_router
from app.api.batch_routes import router as batch_router
from app.api.outage_routes import router as outage_router
from app.api.notification_routes import router as notification_router
from app.api.donation_routes import router as donation_router
from app.scheduler import start_scheduler, stop_scheduler
from app.services.telegram_service import init_telegram_service
from app.services.address_service import load_addresses_from_github
import firebase_admin
from firebase_admin import credentials

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle events для FastAPI
    Виконується при старті та зупинці сервера
    """
    # Startup
    logger.info("=" * 60)
    logger.info("Запуск ProСвітло Backend...")
    logger.info("=" * 60)
    
    # Ініціалізація бази даних
    try:
        init_db()
        logger.info("✓ База даних ініціалізована")
    except Exception as e:
        logger.error(f"✗ Помилка при ініціалізації БД: {e}")
    
    # Завантаження адрес з GitHub
    try:
        load_addresses_from_github()
        logger.info("✓ База адрес завантажена з GitHub")
    except Exception as e:
        logger.error(f"✗ Помилка при завантаженні адрес: {e}")
    
    # Ініціалізація Firebase Admin SDK
    try:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        logger.info("✓ Firebase Admin SDK ініціалізовано")
    except Exception as e:
        logger.error(f"✗ Помилка при ініціалізації Firebase: {e}")
    
    # Ініціалізація Telegram Bot (опціонально)
    try:
        if settings.TELEGRAM_ENABLED and settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHANNEL_ID:
            init_telegram_service(
                bot_token=settings.TELEGRAM_BOT_TOKEN,
                channel_id=settings.TELEGRAM_CHANNEL_ID
            )
            logger.info("✓ Telegram Bot ініціалізовано")
        else:
            logger.info("ℹ️  Telegram Bot вимкнено (встановіть TELEGRAM_ENABLED=True в .env)")
    except Exception as e:
        logger.error(f"✗ Помилка при ініціалізації Telegram: {e}")
    
    # Запуск scheduler для парсингу
    try:
        start_scheduler()
    except Exception as e:
        logger.error(f"✗ Помилка при запуску scheduler: {e}")
    
    logger.info("=" * 60)
    logger.info("ProСвітло Backend готовий до роботи!")
    logger.info(f"API документація: http://localhost:8000/docs")
    logger.info("=" * 60)
    
    yield
    
    # Shutdown
    logger.info("=" * 60)
    logger.info("Зупинка ProСвітло Backend...")
    logger.info("=" * 60)
    
    try:
        stop_scheduler()
        logger.info("✓ Scheduler зупинено")
    except Exception as e:
        logger.error(f"✗ Помилка при зупинці scheduler: {e}")
    
    logger.info("До побачення!")
    logger.info("=" * 60)


# Створення FastAPI додатка
app = FastAPI(
    title=settings.APP_NAME,
    description="Backend API для додатка ПроСвітло - відстеження відключень електроенергії",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Монтуємо статичні файли для зображень графіків
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Головний ендпоінт
@app.get("/")
async def root():
    """Перевірка роботи API"""
    return {
        "message": "Ласкаво просимо до ProСвітло API",
        "status": "working",
        "version": "1.0.0",
        "documentation": "/docs"
    }


@app.get("/health")
async def health_check():
    """Перевірка здоров'я сервера"""
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME
    }


# Підключення API роутів
app.include_router(api_router, prefix=settings.API_V1_PREFIX, tags=["API"])
app.include_router(address_router, prefix=settings.API_V1_PREFIX, tags=["Addresses"])
app.include_router(schedule_router, prefix=settings.API_V1_PREFIX, tags=["Schedules"])
app.include_router(outage_router, prefix=settings.API_V1_PREFIX, tags=["Outages"])
app.include_router(notification_router, prefix=settings.API_V1_PREFIX, tags=["Notifications"])

app.include_router(batch_router, prefix=settings.API_V1_PREFIX, tags=["Batch"])
app.include_router(donation_router, prefix=settings.API_V1_PREFIX, tags=["Donation"])

# Для запуску: uvicorn app.main:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
