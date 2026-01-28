"""
ПРИКЛАД: VOE Parser для аварійних та планових відключень
Файл: app/scraper/providers/voe/voe_parser.py

Цей файл показує як може виглядати парсер для Вінницяобленерго
УВАГА: Це шаблон, потрібно адаптувати під реальну структуру VOE сайту
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

# URLs для VOE
VOE_EMERGENCY_URL = "https://www.voe.com.ua/disconnection/emergency"
VOE_PLANNED_URL = "https://www.voe.com.ua/disconnection/planned"

# Мапа РЕМів VOE (потрібно уточнити реальні значення)
VOE_REM_MAP = {
    # Приклад, треба дізнатися реальні коди
    1: "Вінницький РЕМ",
    2: "Жмеринський РЕМ",
    3: "Могилів-Подільський РЕМ",
    # ... додати інші
}


def fetch_voe_emergency_outages() -> Optional[List[Dict]]:
    """
    Парсить аварійні відключення з VOE
    
    Returns:
        List[Dict]: Список аварійних відключень з region="voe"
        None: Якщо сторінка не змінилася або помилка
    """
    try:
        logger.info("🔍 Парсимо аварійні відключення VOE...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'uk-UA,uk;q=0.9,en;q=0.8',
        }
        
        response = requests.get(VOE_EMERGENCY_URL, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        # Перевірка чи сторінка змінилася (використовуємо існуючий механізм)
        from app.scraper.page_cache import has_page_changed
        if not has_page_changed("voe_emergency", response.text):
            logger.info("ℹ️ VOE аварійні: сторінка не змінилася")
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        outages = []
        
        # ⚠️ АДАПТУВАТИ: Структура залежить від реального HTML VOE
        # Це приклад, потрібно дослідити реальну структуру
        
        # Варіант 1: Якщо VOE використовує таблицю
        table = soup.find('table', class_='outages-table')  # Знайти реальний selector
        if table:
            rows = table.find_all('tr')[1:]  # Пропускаємо заголовок
            
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 6:  # Припустимо: РЕМ, місто, вулиця, будинки, час початку, час кінця
                    try:
                        rem_name = cells[0].get_text(strip=True)
                        city = cells[1].get_text(strip=True)
                        street = cells[2].get_text(strip=True)
                        house_numbers = cells[3].get_text(strip=True)
                        start_time_str = cells[4].get_text(strip=True)
                        end_time_str = cells[5].get_text(strip=True)
                        
                        # Парсимо дату/час (формат треба уточнити)
                        start_time = parse_voe_datetime(start_time_str)
                        end_time = parse_voe_datetime(end_time_str)
                        
                        if not all([city, street, start_time, end_time]):
                            continue
                        
                        outage = {
                            'region': 'voe',  # ⭐ ВАЖЛИВО
                            'rem_id': get_voe_rem_id(rem_name),
                            'rem_name': rem_name,
                            'city': clean_city_name(city),
                            'street': street,
                            'house_numbers': house_numbers,
                            'work_type': 'Аварійне відключення',
                            'created_date': datetime.now(),
                            'start_time': start_time,
                            'end_time': end_time,
                            'is_active': True,
                        }
                        outages.append(outage)
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Помилка парсингу рядка VOE: {e}")
                        continue
        
        # Варіант 2: Якщо VOE використовує форму з фільтрами
        # Потрібно POST запит з параметрами
        # outages = fetch_voe_with_filters(year=2026, month=1)
        
        logger.info(f"✅ VOE аварійні: знайдено {len(outages)} відключень")
        return outages
        
    except requests.RequestException as e:
        logger.error(f"❌ Помилка завантаження VOE emergency: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ Помилка парсингу VOE emergency: {e}")
        return []


def fetch_voe_planned_outages(date_range: str = None) -> Optional[List[Dict]]:
    """
    Парсить планові відключення з VOE
    
    Args:
        date_range: Період (наприклад "01.01.2026 - 31.01.2026")
        
    Returns:
        List[Dict]: Список планових відключень з region="voe"
    """
    try:
        logger.info("🔍 Парсимо планові відключення VOE...")
        
        # Якщо VOE використовує форму з фільтрами
        if date_range is None:
            from datetime import date, timedelta
            today = date.today()
            end_date = today + timedelta(days=7)
            date_range = f"{today.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"
        
        # POST запит з параметрами фільтра
        data = {
            'DateRange': date_range,
            # Додати інші параметри якщо потрібно
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        
        response = requests.post(VOE_PLANNED_URL, data=data, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        from app.scraper.page_cache import has_page_changed
        if not has_page_changed("voe_planned", response.text):
            logger.info("ℹ️ VOE планові: сторінка не змінилася")
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        outages = []
        
        # ⚠️ АДАПТУВАТИ під реальну структуру VOE
        # Аналогічно до emergency парсингу
        
        logger.info(f"✅ VOE планові: знайдено {len(outages)} відключень")
        return outages
        
    except Exception as e:
        logger.error(f"❌ Помилка парсингу VOE planned: {e}")
        return []


def fetch_voe_with_filters(year: int, month: int, rem_id: int = None) -> List[Dict]:
    """
    Парсить відключення VOE з фільтрами
    
    Використовується якщо VOE має форму пошуку з роком/місяцем/РЕМ
    """
    try:
        # Як на сторінці VOE: "Рік, Місяць, Структурна одиниця"
        data = {
            'Year': str(year),
            'Month': str(month),
        }
        
        if rem_id:
            data['RemId'] = str(rem_id)
        
        # POST на відповідний endpoint
        response = requests.post(VOE_PLANNED_URL, data=data, timeout=30)
        response.raise_for_status()
        
        # Парсити результат...
        
        return []
        
    except Exception as e:
        logger.error(f"❌ Помилка VOE з фільтрами: {e}")
        return []


def parse_voe_datetime(datetime_str: str) -> Optional[datetime]:
    """
    Парсить дату/час з VOE
    
    Приклад форматів (потрібно уточнити):
    - "14.01.2026 08:00"
    - "14/01/2026 08:00"
    - "2026-01-14 08:00"
    """
    try:
        # Спробувати різні формати
        formats = [
            "%d.%m.%Y %H:%M",
            "%d/%m/%Y %H:%M",
            "%Y-%m-%d %H:%M",
            "%d.%m.%Y %H:%M:%S",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(datetime_str.strip(), fmt)
            except ValueError:
                continue
        
        logger.warning(f"⚠️ Не вдалося розпарсити дату VOE: {datetime_str}")
        return None
        
    except Exception as e:
        logger.error(f"❌ Помилка парсингу дати VOE: {e}")
        return None


def get_voe_rem_id(rem_name: str) -> int:
    """
    Отримує ID РЕМу за назвою
    
    Потрібно створити мапу VOE РЕМів
    """
    # Перевернута мапа
    for rem_id, name in VOE_REM_MAP.items():
        if name in rem_name or rem_name in name:
            return rem_id
    
    # Якщо не знайдено - повертаємо 0 або інше дефолтне значення
    logger.warning(f"⚠️ Невідомий РЕМ VOE: {rem_name}")
    return 0


def clean_city_name(city: str) -> str:
    """
    Очищує назву міста від префіксів
    
    Приклад: "м. Вінниця (Вінницька громада)" → "Вінниця"
    """
    city = city.strip()
    
    # Видаляємо префікси
    prefixes = ['м. ', 'смт. ', 'с. ', 'м.', 'смт.', 'с.']
    for prefix in prefixes:
        if city.startswith(prefix):
            city = city[len(prefix):].strip()
            break
    
    # Видаляємо частину в дужках
    if '(' in city:
        city = city[:city.index('(')].strip()
    
    return city


# ============= Допоміжні функції для тестування =============

def test_voe_parser():
    """Тестова функція для перевірки парсера VOE"""
    logger.info("🧪 Тестуємо VOE parser...")
    
    # Тест аварійних
    emergency = fetch_voe_emergency_outages()
    if emergency:
        logger.info(f"✅ Аварійні VOE: {len(emergency)} записів")
        if emergency:
            logger.info(f"📋 Приклад: {emergency[0]}")
    
    # Тест планових
    planned = fetch_voe_planned_outages()
    if planned:
        logger.info(f"✅ Планові VOE: {len(planned)} записів")
        if planned:
            logger.info(f"📋 Приклад: {planned[0]}")
    
    logger.info("✅ Тестування завершено")


if __name__ == "__main__":
    # Запустити тест
    logging.basicConfig(level=logging.INFO)
    test_voe_parser()
