"""
Сервіс для роботи з базою адрес
Завантажує дані з GitHub та надає API для пошуку
Використовує локальне кешування з перевіркою версії
"""
import json
import requests
import logging
import os
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# URL до файлів на GitHub
ADDRESSES_DB_URL = "https://raw.githubusercontent.com/Elvis129/prosvitlo-addresses-db/main/addresses.json"
VERSION_URL = "https://raw.githubusercontent.com/Elvis129/prosvitlo-addresses-db/main/version.json"

# Локальні файли для кешування
CACHE_DIR = "cache"
CACHE_FILE = os.path.join(CACHE_DIR, "addresses.json")
VERSION_FILE = os.path.join(CACHE_DIR, "version.json")

# Глобальна змінна для кешу адрес
_addresses_cache: Optional[Dict] = None
_current_version: Optional[str] = None


def _get_remote_version() -> Optional[Dict]:
    """
    Отримує версію з GitHub
    
    Returns:
        Словник з інформацією про версію або None
    """
    try:
        response = requests.get(VERSION_URL, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.warning(f"Не вдалося отримати версію з GitHub: {e}")
        return None


def _get_local_version() -> Optional[Dict]:
    """
    Читає локальну версію з кешу
    
    Returns:
        Словник з інформацією про версію або None
    """
    try:
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Не вдалося прочитати локальну версію: {e}")
    return None


def _save_local_version(version_data: Dict):
    """
    Зберігає версію локально
    
    Args:
        version_data: Дані версії для збереження
    """
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(VERSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(version_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Не вдалося зберегти версію: {e}")


def _load_from_cache() -> Optional[Dict]:
    """
    Завантажує адреси з локального кешу
    
    Returns:
        Словник адрес або None
    """
    try:
        if os.path.exists(CACHE_FILE):
            logger.info("Завантаження адрес з локального кешу...")
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Помилка при читанні кешу: {e}")
    return None


def _save_to_cache(addresses: Dict):
    """
    Зберігає адреси в локальний кеш
    
    Args:
        addresses: Словник адрес для збереження
    """
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(addresses, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ Адреси збережено в кеш: {CACHE_FILE}")
    except Exception as e:
        logger.error(f"Не вдалося зберегти кеш: {e}")


def _download_from_github() -> Dict:
    """
    Завантажує базу адрес з GitHub
    
    Returns:
        Словник з адресами
    """
    logger.info(f"Завантаження адрес з GitHub: {ADDRESSES_DB_URL}")
    response = requests.get(ADDRESSES_DB_URL, timeout=60)
    response.raise_for_status()
    return response.json()


def load_addresses_from_github() -> Dict:
    """
    Завантажує базу адрес з GitHub або локального кешу
    Перевіряє версію і оновлює тільки при необхідності
    
    Returns:
        Словник з адресами у форматі {city: {street: {house: data}}}
    """
    global _addresses_cache, _current_version
    
    # Якщо вже завантажено в пам'ять - використовуємо
    if _addresses_cache is not None:
        logger.info("Використання адрес з оперативної пам'яті")
        return _addresses_cache
    
    try:
        # Перевіряємо версію на GitHub
        remote_version = _get_remote_version()
        local_version = _get_local_version()
        
        needs_update = False
        
        if remote_version and local_version:
            # Порівнюємо версії
            if remote_version.get('version') != local_version.get('version'):
                logger.info(f"Знайдено нову версію: {remote_version.get('version')} (поточна: {local_version.get('version')})")
                needs_update = True
            else:
                logger.info(f"Версія актуальна: {local_version.get('version')}")
        elif remote_version and not local_version:
            logger.info("Локальна версія відсутня, завантажуємо...")
            needs_update = True
        elif not remote_version and local_version:
            logger.warning("Не вдалося перевірити версію на GitHub, використовуємо локальний кеш")
        else:
            logger.warning("Не вдалося отримати інформацію про версії, завантажуємо з GitHub...")
            needs_update = True
        
        # Завантажуємо адреси
        if needs_update:
            # Завантажуємо з GitHub
            _addresses_cache = _download_from_github()
            
            # Зберігаємо в кеш
            _save_to_cache(_addresses_cache)
            
            # Зберігаємо версію
            if remote_version:
                _save_local_version(remote_version)
                _current_version = remote_version.get('version')
        else:
            # Завантажуємо з локального кешу
            _addresses_cache = _load_from_cache()
            
            if _addresses_cache is None:
                # Якщо кеш пошкоджений - завантажуємо з GitHub
                logger.warning("Локальний кеш пошкоджений, завантажуємо з GitHub...")
                _addresses_cache = _download_from_github()
                _save_to_cache(_addresses_cache)
                if remote_version:
                    _save_local_version(remote_version)
            
            if local_version:
                _current_version = local_version.get('version')
        
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
        logger.error(f"Помилка при завантаженні адрес: {e}")
        
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
    
    for city in cities:
        streets = [s for s in addresses[city].keys() if s != "Вулиця"]
        total_streets += len(streets)
        
        for street in streets:
            houses = [h for h in addresses[city][street].keys() if h != "Список будинків"]
            total_houses += len(houses)
    
    return {
        "total_cities": len(cities),
        "total_streets": total_streets,
        "total_houses": total_houses,
        "database_url": ADDRESSES_DB_URL
    }


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
