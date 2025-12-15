"""
Налаштування підключення до бази даних SQLite
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

# Створення engine для SQLite
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False}  # Необхідно для SQLite
)

# Створення SessionLocal для роботи з БД
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base клас для моделей
Base = declarative_base()


def get_db():
    """
    Dependency для отримання сесії БД
    Використовується в FastAPI endpoints
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Ініціалізація бази даних - створення всіх таблиць
    """
    Base.metadata.create_all(bind=engine)
