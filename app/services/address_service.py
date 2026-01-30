"""
Сервіс для роботи з базою адрес
Завантажує дані з локального файлу та надає API для пошуку

ВЕРСІЯ 2: Виправлено баг з літерами в номерах будинків (18А, 18Б, 18В, 18Г)
"""
import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Локальні файли бази даних
CACHE_DIR = "cache"
CACHE_FILE_V1 = os.path.join(CACHE_DIR, "addresses.json")  # Стара версія (backup)
CACHE_FILE_V2 = os.path.join(CACHE_DIR, "addresses_v2.json")  # Нова версія (основна)
VERSION_FILE = os.path.join(CACHE_DIR, "addresses_version.json")

# Глобальна змінна для кешу адрес
_addresses_cache: Optional[Dict] = None
_current_version: int = 2  # Поточна версія бази
_use_v2: bool = True  # За замовчуванням використовуємо v2


def _get_version_info() -> Dict:
    """
    Отримує інформацію про версію бази даних
    
    Returns:
        Словник з інформацією про версію
    """
    try:
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Не вдалося прочитати версію: {e}")
    
    # За замовчуванням v2
    return {
        'version': 2,
        'source': 'local',
        'created_at': '2026-01-30',
        'notes': 'Fixed house numbers with letters (18А, 18Б, etc.)'
    }


def _load_from_cache() -> Optional[Dict]:
    """
    Завантажує адреси з локального файлу
    Спочатку пробує v2, якщо немає - fallback на v1
    
    Returns:
        Словник адрес або None
    """
    global _current_version
    
    try:
        # Спочатку пробуємо v2 (з виправленими літерами)
        if _use_v2 and os.path.exists(CACHE_FILE_V2):
            logger.info(f"✓ Завантаження адрес з версії 2: {CACHE_FILE_V2}")
            with open(CACHE_FILE_V2, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _current_version = 2
            logger.info("  (версія 2 - з виправленими літерами в адресах)")
            return data
        
        # Fallback на v1
        if os.path.exists(CACHE_FILE_V1):
            logger.warning(f"⚠️  Завантаження адрес з версії 1 (fallback): {CACHE_FILE_V1}")
            logger.warning("  Версія 1 має баг з літерами в номерах будинків!")
            with open(CACHE_FILE_V1, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _current_version = 1
            return data
            
    except Exception as e:
        logger.error(f"Помилка при читанні файлу бази даних: {e}")
    
    return None


def load_addresses_from_github() -> Dict:
    """
    Завантажує базу адрес з локального файлу.
    
    ПРИМІТКА: Назва функції залишена для зворотної сумісності,
    але насправді завантажує з локального файлу, а не з GitHub.
    
    Returns:
        Словник з адресами у форматі {city: {street: {house: data}}}
    """
    global _addresses_cache, _current_version
    
    # Якщо вже завантажено в пам'ять - використовуємо
    if _addresses_cache is not None:
        logger.info("Використання адрес з оперативної пам'яті")
        return _addresses_cache
    
    try:
        # Завантажуємо з локального файлу
        _addresses_cache = _load_from_cache()
        
        if _addresses_cache is None:
            # Якщо нема жодної версії - критична помилка
            error_msg = f"Файли бази даних не знайдені! Перевірте наявність {CACHE_FILE_V2} або {CACHE_FILE_V1}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        # Статистика
        total_cities = len(_addresses_cache)
        total_streets = sum(len(streets) for streets in _addresses_cache.values())
        total_houses = sum(
            len(houses) 
            for streets in _addresses_cache.values() 
            for houses in streets.values()
        )
        
        logger.info(f"✅ Адреси завантажено (версія {_current_version}): {total_cities} міст, {total_streets} вулиць, {total_houses} будинків")
        return _addresses_cache
        
    except Exception as e:
        logger.error(f"Критична помилка при завантаженні адрес: {e}")
        raise
        
        # Пробуємо завантажити з локального кешу як fallback
        cached = _load_from_cache()
        if cached:
            logger.info("Використовуємо локальний кеш як резервний варіант")
            _addresses_cache = cached
            return _addresses_cache
        
        raise


def reload_addresses() -> Dict:
    """
    Примусове перезавантаження адрес з GitHub
    
    Returns:
        Оновлений словник адрес
    """
    global _addresses_cache
    _addresses_cache = None
    return load_addresses_from_github()


def get_cities(search: Optional[str] = None) -> List[str]:
    """
    Отримати список міст/населених пунктів
    
    Args:
        search: Пошуковий запит для фільтрації
    
    Returns:
        Список назв міст
    """
    addresses = load_addresses_from_github()
    cities = list(addresses.keys())
    
    # Видаляємо технічний рядок якщо є
    cities = [c for c in cities if c != "Населений пункт"]
    
    if search:
        search_lower = search.lower()
        cities = [c for c in cities if search_lower in c.lower()]
    
    return sorted(cities)


def get_streets(city: str, search: Optional[str] = None) -> List[str]:
    """
    Отримати список вулиць для міста
    
    Args:
        city: Назва міста
        search: Пошуковий запит для фільтрації
    
    Returns:
        Список назв вулиць
    """
    addresses = load_addresses_from_github()
    
    if city not in addresses:
        return []
    
    streets = list(addresses[city].keys())
    
    # Видаляємо технічні рядки
    streets = [s for s in streets if s != "Вулиця"]
    
    if search:
        search_lower = search.lower()
        streets = [s for s in streets if search_lower in s.lower()]
    
    return sorted(streets)


def get_houses(city: str, street: str, search: Optional[str] = None) -> List[str]:
    """
    Отримати список будинків для вулиці
    
    Args:
        city: Назва міста
        street: Назва вулиці
        search: Пошуковий запит для фільтрації
    
    Returns:
        Список номерів будинків
    """
    addresses = load_addresses_from_github()
    
    if city not in addresses or street not in addresses[city]:
        return []
    
    houses = list(addresses[city][street].keys())
    
    # Видаляємо технічні рядки
    houses = [h for h in houses if h != "Список будинків"]
    
    if search:
        search_lower = search.lower()
        houses = [h for h in houses if search_lower in h.lower()]
    
    return sorted(houses, key=lambda x: (
        int(''.join(filter(str.isdigit, x))) if any(c.isdigit() for c in x) else 0,
        x
    ))


def get_address_info(city: str, street: str, house: str, db = None, schedule_date = None) -> Optional[Dict]:
    """
    Отримати повну інформацію про адресу включаючи графік відключень
    
    Args:
        city: Назва міста
        street: Назва вулиці
        house: Номер будинку
        db: Сесія бази даних (опціонально)
        schedule_date: Дата графіка (опціонально, за замовчуванням сьогодні)
    
    Returns:
        Словник з інформацією про адресу або None
    """
    from datetime import date as date_type, datetime
    import json
    
    addresses = load_addresses_from_github()
    
    if (city not in addresses or 
        street not in addresses[city] or 
        house not in addresses[city][street]):
        return None
    
    address_data = addresses[city][street][house]
    queue = address_data.get("queue")
    
    result = {
        "city": city,
        "street": street,
        "house": house,
        "queue": queue,
        "source_url": address_data.get("source_url"),
        "outage_status": None,
    }
    
    # Якщо є БД і черга - отримуємо інформацію про відключення
    if db and queue:
        try:
            from app.crud_schedules import get_schedule_by_date
            
            # Визначаємо дату
            if schedule_date:
                if isinstance(schedule_date, str):
                    target_date = datetime.strptime(schedule_date, "%Y-%m-%d").date()
                else:
                    target_date = schedule_date
            else:
                target_date = date_type.today()
            
            # Отримуємо графік
            schedule = get_schedule_by_date(db, target_date)
            
            if schedule and schedule.parsed_data:
                # Парсимо дані графіка
                if isinstance(schedule.parsed_data, str):
                    queue_schedules = json.loads(schedule.parsed_data)
                else:
                    queue_schedules = schedule.parsed_data
                
                # Знаходимо інформацію для черги адреси
                if queue in queue_schedules:
                    queue_data = queue_schedules[queue]
                    
                    result["outage_status"] = {
                        "date": str(target_date),
                        "queue": queue,
                        "schedule": queue_data
                    }
                    
                    logger.info(f"Знайдено графік для черги {queue}: outages={len(queue_data.get('outages', []))}, possible={len(queue_data.get('possible', []))}")
                else:
                    logger.warning(f"Черга {queue} не знайдена в графіку для дати {target_date}")
            else:
                logger.info(f"Графік для дати {target_date} не знайдено або немає parsed_data")
                
        except Exception as e:
            logger.error(f"Помилка при отриманні інформації про відключення: {e}")
    
    return result


def search_addresses(query: str, limit: int = 50) -> List[Dict]:
    """
    Глобальний пошук адрес
    
    Args:
        query: Пошуковий запит
        limit: Максимальна кількість результатів
    
    Returns:
        Список знайдених адрес
    """
    addresses = load_addresses_from_github()
    results = []
    query_lower = query.lower()
    
    for city, streets in addresses.items():
        if city == "Населений пункт":
            continue
            
        city_match = query_lower in city.lower()
        
        for street, houses in streets.items():
            if street == "Вулиця":
                continue
                
            street_match = query_lower in street.lower()
            
            if city_match or street_match:
                for house in list(houses.keys())[:10]:  # Обмежуємо будинки
                    if house == "Список будинків":
                        continue
                        
                    results.append({
                        "city": city,
                        "street": street,
                        "house": house,
                        "queue": houses[house].get("queue")
                    })
                    
                    if len(results) >= limit:
                        return results
    
    return results


def get_statistics() -> Dict:
    """
    Отримати статистику по базі адрес
    
    Returns:
        Словник зі статистикою
    """
    addresses = load_addresses_from_github()
    
    cities = [c for c in addresses.keys() if c != "Населений пункт"]
    
    total_streets = 0
    total_houses = 0
    houses_with_letters = 0
    
    for city in cities:
        streets = [s for s in addresses[city].keys() if s != "Вулиця"]
        total_streets += len(streets)
        
        for street in streets:
            houses = [h for h in addresses[city][street].keys() if h != "Список будинків"]
            total_houses += len(houses)
            
            # Рахуємо будинки з літерами (для діагностики)
            for house in houses:
                if any(c.isalpha() and ord(c) > 127 for c in house):
                    houses_with_letters += 1
    
    # Визначаємо версію
    version = "v2" if _use_v2 and os.path.exists(CACHE_FILE_V2) else "v1"
    
    return {
        "total_cities": len(cities),
        "total_streets": total_streets,
        "total_houses": total_houses,
        "houses_with_letters": houses_with_letters,
        "letter_percentage": round(houses_with_letters / total_houses * 100, 2) if total_houses > 0 else 0,
        "database_version": f"v{_current_version}",
        "database_source": "local"
    }


def switch_to_v1():
    """
    ROLLBACK: Перемикає на стару версію бази даних.
    Використовуйте якщо v2 викликає проблеми.
    """
    global _use_v2, _addresses_cache
    logger.warning("⚠️  ROLLBACK: Перемикання на версію 1 бази даних")
    _use_v2 = False
    _addresses_cache = None  # Скидаємо кеш
    logger.info("✓ Наступне завантаження буде використовувати v1")


def switch_to_v2():
    """
    Перемикає на нову версію бази даних (з виправленими літерами).
    """
    global _use_v2, _addresses_cache
    
    if not os.path.exists(CACHE_FILE_V2):
        logger.error("❌ Файл версії 2 не знайдено!")
        return False
    
    logger.info("✓ Перемикання на версію 2 бази даних")
    _use_v2 = True
    _addresses_cache = None  # Скидаємо кеш
    logger.info("✓ Наступне завантаження буде використовувати v2")
    return True


def validate_user_data_migration() -> Dict:
    """
    Перевіряє чи не втратять користувачі свої збережені адреси при міграції на v2.
    
    Повертає звіт про сумісність:
    - missing_in_v2: адреси що були в v1 але немає в v2
    - new_in_v2: нові адреси в v2
    - compatible: чи сумісні версії
    """
    result = {
        "compatible": True,
        "missing_in_v2": [],
        "new_in_v2": 0,
        "v1_total": 0,
        "v2_total": 0,
        "notes": []
    }
    
    try:
        # Завантажуємо v1
        if not os.path.exists(CACHE_FILE_V1):
            result["notes"].append("v1 не знайдено - нема з чим порівнювати")
            return result
        
        with open(CACHE_FILE_V1, 'r', encoding='utf-8') as f:
            v1_data = json.load(f)
        
        # Завантажуємо v2
        if not os.path.exists(CACHE_FILE_V2):
            result["notes"].append("v2 не знайдено")
            result["compatible"] = False
            return result
        
        with open(CACHE_FILE_V2, 'r', encoding='utf-8') as f:
            v2_data = json.load(f)
        
        # Порівнюємо
        for city, streets in v1_data.items():
            for street, houses in streets.items():
                for house in houses.keys():
                    result["v1_total"] += 1
                    
                    # Перевіряємо чи є в v2
                    if city not in v2_data or street not in v2_data.get(city, {}) or house not in v2_data[city][street]:
                        result["missing_in_v2"].append(f"{city}, {street}, {house}")
        
        # Рахуємо нові в v2
        for city, streets in v2_data.items():
            for street, houses in streets.items():
                result["v2_total"] += len(houses)
        
        result["new_in_v2"] = result["v2_total"] - result["v1_total"]
        
        # Висновок
        if len(result["missing_in_v2"]) == 0:
            result["compatible"] = True
            result["notes"].append("✅ Всі адреси з v1 присутні в v2")
        else:
            result["compatible"] = False
            result["notes"].append(f"⚠️  {len(result['missing_in_v2'])} адрес з v1 відсутні в v2")
        
        if result["new_in_v2"] > 0:
            result["notes"].append(f"✓ Додано {result['new_in_v2']} нових адрес")
        
    except Exception as e:
        result["compatible"] = False
        result["notes"].append(f"Помилка при порівнянні: {e}")
    
    return result


# Для тестування
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=== Тест завантаження адрес ===\n")
    
    stats = get_statistics()
    print(f"📊 Статистика:")
    print(f"   Міст: {stats['total_cities']}")
    print(f"   Вулиць: {stats['total_streets']}")
    print(f"   Будинків: {stats['total_houses']}")
    
    print("\n=== Тест пошуку міст ===")
    cities = get_cities(search="Хмель")
    print(f"Знайдено міст з 'Хмель': {len(cities)}")
    print(f"Перші 5: {cities[:5]}")
    
    if cities:
        city = cities[0]
        print(f"\n=== Тест пошуку вулиць у {city} ===")
        streets = get_streets(city, search="вул")
        print(f"Знайдено вулиць з 'вул': {len(streets)}")
        print(f"Перші 5: {streets[:5]}")
        
        if streets:
            street = streets[0]
            print(f"\n=== Тест пошуку будинків на {street} ===")
            houses = get_houses(city, street)
            print(f"Знайдено будинків: {len(houses)}")
            print(f"Перші 10: {houses[:10]}")
            
            if houses:
                house = houses[0]
                print(f"\n=== Тест отримання інформації ===")
                info = get_address_info(city, street, house)
                print(f"Інформація про {city}, {street}, {house}:")
                print(json.dumps(info, ensure_ascii=False, indent=2))
