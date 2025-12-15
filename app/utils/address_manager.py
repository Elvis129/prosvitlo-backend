"""
Утиліти для роботи зі статичними даними адрес
- Експорт/імпорт з JSON файлів
- Завантаження в БД
"""

import json
import logging
from pathlib import Path
from typing import List, Dict
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import AddressQueue

logger = logging.getLogger(__name__)


def export_addresses_to_json(db: Session, output_file: str = "data/addresses.json") -> int:
    """
    Експорт адрес з БД в JSON файл
    
    Args:
        db: Database session
        output_file: Шлях до вихідного JSON файлу
    
    Returns:
        Кількість експортованих адрес
    """
    try:
        # Отримуємо всі адреси
        addresses = db.query(AddressQueue).all()
        
        # Конвертуємо в словники
        addresses_data = []
        for addr in addresses:
            addresses_data.append({
                "city": addr.city,
                "street": addr.street,
                "house_number": addr.house_number,
                "queue": addr.queue,
                "zone": addr.zone
            })
        
        # Створюємо директорію якщо не існує
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Зберігаємо в JSON
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(addresses_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✓ Експортовано {len(addresses_data)} адрес в {output_file}")
        return len(addresses_data)
        
    except Exception as e:
        logger.error(f"Помилка при експорті: {e}")
        raise


def import_addresses_from_json(db: Session, input_file: str = "data/addresses.json") -> dict:
    """
    Імпорт адрес з JSON файлу в БД
    
    Args:
        db: Database session
        input_file: Шлях до JSON файлу
    
    Returns:
        Статистика імпорту
    """
    stats = {
        "loaded": 0,
        "added": 0,
        "errors": 0
    }
    
    try:
        # Читаємо JSON файл
        with open(input_file, 'r', encoding='utf-8') as f:
            addresses_data = json.load(f)
        
        stats["loaded"] = len(addresses_data)
        logger.info(f"Завантажено {len(addresses_data)} адрес з файлу")
        
        # Видаляємо старі записи
        deleted_count = db.query(AddressQueue).delete()
        logger.info(f"Видалено {deleted_count} старих записів")
        
        # Додаємо нові
        for addr_data in addresses_data:
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
                logger.error(f"Помилка при додаванні адреси: {e}")
                stats["errors"] += 1
        
        # Зберігаємо
        db.commit()
        logger.info(f"✓ Імпортовано {stats['added']} адрес в БД")
        
    except FileNotFoundError:
        logger.error(f"Файл {input_file} не знайдено")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Помилка парсингу JSON: {e}")
        raise
    except Exception as e:
        logger.error(f"Помилка при імпорті: {e}")
        db.rollback()
        raise
    
    return stats


def get_queue_for_address(db: Session, city: str, street: str, house_number: str) -> str:
    """
    Отримати чергу для конкретної адреси
    
    Args:
        db: Database session
        city: Місто
        street: Вулиця
        house_number: Номер будинку
    
    Returns:
        Номер черги або None
    """
    address = db.query(AddressQueue).filter(
        AddressQueue.city == city,
        AddressQueue.street == street,
        AddressQueue.house_number == house_number
    ).first()
    
    return address.queue if address else None


# CLI команди
if __name__ == "__main__":
    import sys
    import argparse
    
    logging.basicConfig(level=logging.INFO)
    
    parser = argparse.ArgumentParser(description="Утиліти для роботи з адресами")
    parser.add_argument("command", choices=["export", "import", "lookup"],
                       help="Команда: export, import, або lookup")
    parser.add_argument("--file", default="data/addresses.json",
                       help="Шлях до JSON файлу")
    parser.add_argument("--city", help="Місто (для lookup)")
    parser.add_argument("--street", help="Вулиця (для lookup)")
    parser.add_argument("--house", help="Номер будинку (для lookup)")
    
    args = parser.parse_args()
    
    db = SessionLocal()
    try:
        if args.command == "export":
            count = export_addresses_to_json(db, args.file)
            print(f"\n✓ Експортовано {count} адрес в {args.file}")
            
        elif args.command == "import":
            stats = import_addresses_from_json(db, args.file)
            print(f"\n✓ Імпортовано {stats['added']} адрес з {args.file}")
            if stats['errors']:
                print(f"⚠️  Помилок: {stats['errors']}")
                
        elif args.command == "lookup":
            if not all([args.city, args.street, args.house]):
                print("❌ Для lookup потрібно вказати --city, --street, --house")
                sys.exit(1)
            
            queue = get_queue_for_address(db, args.city, args.street, args.house)
            if queue:
                print(f"\n✓ Адреса: {args.city}, {args.street}, {args.house}")
                print(f"  Черга: {queue}")
            else:
                print(f"\n❌ Адресу не знайдено в базі")
                
    finally:
        db.close()
