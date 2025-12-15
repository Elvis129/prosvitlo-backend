"""
Утиліта для оновлення статичної таблиці адрес з hoe.com.ua

Використання:
    python -m app.utils.update_addresses

Ця команда:
1. Парсить таблиці відповідності адрес до черг з сайту hoe.com.ua
2. Оновлює таблицю address_queues в базі даних
3. Видаляє старі записи і додає нові

УВАГА: Це довга операція (може тривати 30-60 секунд через Selenium)
"""

import sys
import logging
from pathlib import Path

# Додаємо батьківську директорію до шляху
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app.models import AddressQueue, Base
from app.scraper.selenium_parser import scrape_address_queue_data

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def update_address_queue_table(db: Session, addresses: list) -> dict:
    """
    Оновлення таблиці адрес в БД
    
    Args:
        db: Database session
        addresses: Список адрес з даними
    
    Returns:
        Статистика оновлення
    """
    stats = {
        "deleted": 0,
        "added": 0,
        "updated": 0,
        "errors": 0
    }
    
    try:
        # Створюємо таблицю якщо не існує
        Base.metadata.create_all(bind=engine)
        logger.info("Таблиці БД перевірено/створено")
        
        # Видаляємо всі старі записи
        deleted_count = db.query(AddressQueue).delete()
        stats["deleted"] = deleted_count
        logger.info(f"Видалено {deleted_count} старих записів")
        
        # Додаємо нові записи
        for addr_data in addresses:
            try:
                address = AddressQueue(
                    city=addr_data.get("city"),
                    street=addr_data.get("street"),
                    house_number=addr_data.get("house_number"),
                    queue=addr_data.get("queue"),
                    zone=addr_data.get("zone")
                )
                db.add(address)
                stats["added"] += 1
            except Exception as e:
                logger.error(f"Помилка при додаванні адреси {addr_data}: {e}")
                stats["errors"] += 1
        
        # Зберігаємо зміни
        db.commit()
        logger.info(f"Додано {stats['added']} нових адрес")
        
    except Exception as e:
        logger.error(f"Помилка при оновленні БД: {e}")
        db.rollback()
        raise
    
    return stats


def main():
    """
    Головна функція для оновлення таблиці адрес
    """
    logger.info("=" * 60)
    logger.info("Початок оновлення таблиці адрес")
    logger.info("=" * 60)
    
    # Парсимо дані з сайту
    logger.info("Етап 1: Парсинг даних з hoe.com.ua...")
    try:
        addresses = scrape_address_queue_data()
        
        if not addresses:
            logger.warning("⚠️  Не отримано жодної адреси!")
            logger.info("Можливі причини:")
            logger.info("  - Сайт недоступний")
            logger.info("  - Змінилася структура сторінки")
            logger.info("  - Проблеми з ChromeDriver")
            return
        
        logger.info(f"✓ Отримано {len(addresses)} адрес")
        
        # Виводимо приклади
        logger.info("\nПриклади отриманих адрес:")
        for i, addr in enumerate(addresses[:5], 1):
            logger.info(f"  {i}. {addr['city']}, {addr['street']}, {addr['house_number']} - Черга {addr['queue']}")
        
        if len(addresses) > 5:
            logger.info(f"  ... і ще {len(addresses) - 5} адрес")
        
    except Exception as e:
        logger.error(f"✗ Помилка при парсингу: {e}")
        return
    
    # Оновлюємо БД
    logger.info("\nЕтап 2: Оновлення бази даних...")
    db = SessionLocal()
    try:
        stats = update_address_queue_table(db, addresses)
        
        logger.info("=" * 60)
        logger.info("Оновлення завершено успішно!")
        logger.info(f"  Видалено старих записів: {stats['deleted']}")
        logger.info(f"  Додано нових записів: {stats['added']}")
        logger.info(f"  Помилок: {stats['errors']}")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"✗ Помилка при оновленні БД: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
