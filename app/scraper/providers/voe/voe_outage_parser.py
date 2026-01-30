"""
VOE (Вінницяобленерго) Parser для відключень
Файл: app/scraper/providers/voe/voe_outage_parser.py

Особливості VOE:
- Використовує форму з фільтрами (Рік, Місяць, Структурна одиниця)
- Структура HTML може відрізнятися від HOE
- URLs:
  - Emergency: https://www.voe.com.ua/disconnection/emergency
  - Planned: https://www.voe.com.ua/disconnection/planned
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
from typing import List, Dict, Optional
import logging
import hashlib

logger = logging.getLogger(__name__)

# VOE URLs
VOE_EMERGENCY_URL = "https://www.voe.com.ua/disconnection/emergency"
VOE_PLANNED_URL = "https://www.voe.com.ua/disconnection/planned"

# Мапа РЕМів VOE (потрібно уточнити після аналізу сайту)
VOE_REM_MAP = {
    "1": "Вінницький РЕМ",
    "2": "Жмеринський РЕМ",
    "3": "Могилів-Подільський РЕМ",
    "4": "Тульчинський РЕМ",
    "5": "Барський РЕМ",
    "6": "Гайсинський РЕМ",
    "7": "Козятинський РЕМ",
    "8": "Калинівський РЕМ",
    "9": "Немирівський РЕМ",
    "10": "Хмільницький РЕМ",
    # Додати інші при необхідності
}


def fetch_voe_emergency_outages() -> Optional[List[Dict]]:
    """
    Парсить аварійні відключення з VOE
    
    Returns:
        List[Dict]: Список аварійних відключень з region="voe"
        None: Якщо сторінка не змінилася
        []: Якщо помилка або немає даних
    """
    try:
        logger.info("🔍 [VOE] Парсимо аварійні відключення...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'uk-UA,uk;q=0.9,en;q=0.8',
        }
        
        # Спочатку отримуємо поточний рік/місяць
        today = date.today()
        
        # VOE може використовувати POST форму з фільтрами
        data = {
            'Year': str(today.year),
            'Month': str(today.month),
            # 'RemId': ''  # Всі РЕМи
        }
        
        response = requests.post(
            VOE_EMERGENCY_URL,
            data=data,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        # Перевірка чи сторінка змінилася
        from app.scraper.page_cache import has_page_changed
        if not has_page_changed("voe_emergency", response.text):
            logger.info("ℹ️ [VOE] Аварійні: сторінка не змінилася")
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        outages = []
        
        # Шукаємо таблицю або список відключень
        # Спочатку пробуємо знайти таблицю
        table = soup.find('table', class_=['table', 'outages-table', 'disconnect-table'])
        
        if table:
            outages = _parse_voe_table(table, 'emergency')
        else:
            # Якщо таблиці немає, шукаємо інші елементи
            # Можливо це div-и або список
            items = soup.find_all(['div', 'article'], class_=['outage-item', 'disconnect-item'])
            if items:
                outages = _parse_voe_items(items, 'emergency')
        
        logger.info(f"✅ [VOE] Аварійні: знайдено {len(outages)} відключень")
        return outages
        
    except requests.RequestException as e:
        logger.error(f"❌ [VOE] Помилка завантаження emergency: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ [VOE] Помилка парсингу emergency: {e}")
        logger.exception("Детальна інформація:")
        return []


def fetch_voe_planned_outages() -> Optional[List[Dict]]:
    """
    Парсить планові відключення з VOE
    
    Returns:
        List[Dict]: Список планових відключень з region="voe"
        None: Якщо сторінка не змінилася
        []: Якщо помилка або немає даних
    """
    try:
        logger.info("🔍 [VOE] Парсимо планові відключення...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'uk-UA,uk;q=0.9,en;q=0.8',
        }
        
        today = date.today()
        
        # POST форма з фільтрами
        data = {
            'Year': str(today.year),
            'Month': str(today.month),
        }
        
        response = requests.post(
            VOE_PLANNED_URL,
            data=data,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        from app.scraper.page_cache import has_page_changed
        if not has_page_changed("voe_planned", response.text):
            logger.info("ℹ️ [VOE] Планові: сторінка не змінилася")
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        outages = []
        
        # Парсимо аналогічно до emergency
        table = soup.find('table', class_=['table', 'outages-table', 'disconnect-table'])
        
        if table:
            outages = _parse_voe_table(table, 'planned')
        else:
            items = soup.find_all(['div', 'article'], class_=['outage-item', 'disconnect-item'])
            if items:
                outages = _parse_voe_items(items, 'planned')
        
        logger.info(f"✅ [VOE] Планові: знайдено {len(outages)} відключень")
        return outages
        
    except requests.RequestException as e:
        logger.error(f"❌ [VOE] Помилка завантаження planned: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ [VOE] Помилка парсингу planned: {e}")
        logger.exception("Детальна інформація:")
        return []


def _parse_voe_table(table, outage_type: str) -> List[Dict]:
    """
    Парсить HTML таблицю з відключеннями VOE
    
    Args:
        table: BeautifulSoup table element
        outage_type: 'emergency' або 'planned'
    
    Returns:
        List[Dict]: Список відключень
    """
    outages = []
    
    try:
        rows = table.find_all('tr')[1:]  # Пропускаємо заголовок
        
        for row in rows:
            cells = row.find_all(['td', 'th'])
            
            if len(cells) < 5:
                continue
            
            try:
                # Адаптуємо під реальну структуру VOE таблиці
                # Можливі варіанти колонок:
                # [РЕМ/Структурна одиниця, Місто/Населений пункт, Вулиця, Будинки, Час початку, Час кінця]
                # або
                # [Дата, Час, Адреса, Опис]
                
                # Витягуємо текст з кожної комірки
                cell_texts = [cell.get_text(strip=True) for cell in cells]
                
                # Пробуємо знайти основні поля
                rem_name = cell_texts[0] if len(cell_texts) > 0 else ""
                city = cell_texts[1] if len(cell_texts) > 1 else ""
                street = cell_texts[2] if len(cell_texts) > 2 else ""
                house_numbers = cell_texts[3] if len(cell_texts) > 3 else ""
                
                # Час може бути в різних форматах
                time_info = cell_texts[4] if len(cell_texts) > 4 else ""
                
                # Парсимо час
                start_time, end_time = _parse_voe_time(time_info, cell_texts)
                
                if not all([city, street, start_time, end_time]):
                    logger.debug(f"⚠️ [VOE] Пропущено рядок - не всі поля: {cell_texts}")
                    continue
                
                # Очищаємо назви
                city = _clean_voe_city_name(city)
                
                outage = {
                    'region': 'voe',
                    'rem_id': _get_voe_rem_id(rem_name),
                    'rem_name': rem_name,
                    'city': city,
                    'street': street,
                    'house_numbers': house_numbers,
                    'work_type': 'Аварійне відключення' if outage_type == 'emergency' else 'Планове відключення',
                    'created_date': datetime.now(),
                    'start_time': start_time,
                    'end_time': end_time,
                    'is_active': True,
                }
                outages.append(outage)
                
            except Exception as e:
                logger.warning(f"⚠️ [VOE] Помилка парсингу рядка: {e}")
                logger.debug(f"Вміст рядка: {[c.get_text(strip=True) for c in cells]}")
                continue
    
    except Exception as e:
        logger.error(f"❌ [VOE] Помилка парсингу таблиці: {e}")
    
    return outages


def _parse_voe_items(items, outage_type: str) -> List[Dict]:
    """
    Парсить список відключень (якщо не таблиця, а div-и)
    
    Args:
        items: Список BeautifulSoup elements
        outage_type: 'emergency' або 'planned'
    
    Returns:
        List[Dict]: Список відключень
    """
    outages = []
    
    for item in items:
        try:
            # Шукаємо інформацію в елементі
            rem_elem = item.find(class_=['rem', 'district', 'структурна-одиниця'])
            city_elem = item.find(class_=['city', 'місто', 'населений-пункт'])
            street_elem = item.find(class_=['street', 'вулиця', 'address'])
            houses_elem = item.find(class_=['houses', 'будинки'])
            time_elem = item.find(class_=['time', 'час', 'period'])
            
            rem_name = rem_elem.get_text(strip=True) if rem_elem else ""
            city = city_elem.get_text(strip=True) if city_elem else ""
            street = street_elem.get_text(strip=True) if street_elem else ""
            house_numbers = houses_elem.get_text(strip=True) if houses_elem else ""
            time_info = time_elem.get_text(strip=True) if time_elem else ""
            
            start_time, end_time = _parse_voe_time(time_info, [])
            
            if not all([city, street, start_time, end_time]):
                continue
            
            city = _clean_voe_city_name(city)
            
            outage = {
                'region': 'voe',
                'rem_id': _get_voe_rem_id(rem_name),
                'rem_name': rem_name,
                'city': city,
                'street': street,
                'house_numbers': house_numbers,
                'work_type': 'Аварійне відключення' if outage_type == 'emergency' else 'Планове відключення',
                'created_date': datetime.now(),
                'start_time': start_time,
                'end_time': end_time,
                'is_active': True,
            }
            outages.append(outage)
            
        except Exception as e:
            logger.warning(f"⚠️ [VOE] Помилка парсингу елемента: {e}")
            continue
    
    return outages


def _parse_voe_time(time_str: str, cell_texts: List[str]) -> tuple:
    """
    Парсить час з VOE формату
    
    Можливі формати:
    - "15.01.2026 10:00 - 15.01.2026 14:00"
    - "10:00 - 14:00"
    - "з 10:00 до 14:00"
    - Окремі колонки для початку і кінця
    
    Returns:
        (start_time, end_time): datetime objects або (None, None)
    """
    import re
    
    try:
        # Варіант 1: Повний формат з датою
        pattern1 = r'(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\s*-\s*(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})'
        match1 = re.search(pattern1, time_str)
        
        if match1:
            start_date, start_time, end_date, end_time = match1.groups()
            start_dt = datetime.strptime(f"{start_date} {start_time}", "%d.%m.%Y %H:%M")
            end_dt = datetime.strptime(f"{end_date} {end_time}", "%d.%m.%Y %H:%M")
            return start_dt, end_dt
        
        # Варіант 2: Тільки час
        pattern2 = r'(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})'
        match2 = re.search(pattern2, time_str)
        
        if match2:
            start_time, end_time = match2.groups()
            today = date.today()
            start_dt = datetime.strptime(f"{today} {start_time}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{today} {end_time}", "%Y-%m-%d %H:%M")
            return start_dt, end_dt
        
        # Варіант 3: З окремих колонок
        if len(cell_texts) >= 6:
            # Можливо start_time в cell_texts[4], end_time в cell_texts[5]
            try:
                start_str = cell_texts[4]
                end_str = cell_texts[5]
                
                # Парсимо окремо
                start_dt = _parse_single_datetime(start_str)
                end_dt = _parse_single_datetime(end_str)
                
                if start_dt and end_dt:
                    return start_dt, end_dt
            except:
                pass
        
        logger.debug(f"⚠️ [VOE] Не вдалося розпарсити час: '{time_str}'")
        return None, None
        
    except Exception as e:
        logger.debug(f"⚠️ [VOE] Помилка парсингу часу: {e}")
        return None, None


def _parse_single_datetime(dt_str: str) -> Optional[datetime]:
    """Парсить одну дату/час в різних форматах"""
    import re
    
    dt_str = dt_str.strip()
    
    # Спробувати різні формати
    formats = [
        "%d.%m.%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%d.%m.%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(dt_str, fmt)
        except:
            continue
    
    # Якщо тільки час - додаємо сьогоднішню дату
    time_pattern = r'^\d{2}:\d{2}(:\d{2})?$'
    if re.match(time_pattern, dt_str):
        today = date.today()
        try:
            return datetime.strptime(f"{today} {dt_str}", "%Y-%m-%d %H:%M")
        except:
            pass
    
    return None


def _get_voe_rem_id(rem_name: str) -> int:
    """
    Визначає ID РЕМу за назвою
    
    Args:
        rem_name: Назва РЕМу (наприклад "Вінницький РЕМ")
    
    Returns:
        int: ID РЕМу або 0 якщо не знайдено
    """
    rem_name_lower = rem_name.lower()
    
    for rem_id, name in VOE_REM_MAP.items():
        if name.lower() in rem_name_lower or rem_name_lower in name.lower():
            return int(rem_id)
    
    # Спробувати знайти за ключовими словами
    if 'вінниц' in rem_name_lower:
        return 1
    elif 'жмерин' in rem_name_lower:
        return 2
    elif 'могилів' in rem_name_lower or 'подільськ' in rem_name_lower:
        return 3
    elif 'тульчин' in rem_name_lower:
        return 4
    elif 'бар' in rem_name_lower:
        return 5
    elif 'гайсин' in rem_name_lower:
        return 6
    elif 'козятин' in rem_name_lower:
        return 7
    elif 'калинів' in rem_name_lower:
        return 8
    elif 'немирів' in rem_name_lower:
        return 9
    elif 'хмільниц' in rem_name_lower:
        return 10
    
    logger.debug(f"⚠️ [VOE] Невідомий РЕМ: {rem_name}")
    return 0


def _clean_voe_city_name(city: str) -> str:
    """
    Очищає назву міста від префіксів
    
    Приклад: "м. Вінниця (Вінницька громада)" → "Вінниця"
    """
    import re
    
    # Видаляємо префікси: м., с., смт.
    city = re.sub(r'^(м\.|с\.|смт\.)\s*', '', city)
    
    # Видаляємо текст в дужках
    city = re.sub(r'\s*\([^)]*\)', '', city)
    
    return city.strip()


# Для зворотної сумісності з HOE структурою
def fetch_all_voe_emergency_outages():
    """Alias для fetch_voe_emergency_outages"""
    return fetch_voe_emergency_outages()


def fetch_all_voe_planned_outages():
    """Alias для fetch_voe_planned_outages"""
    return fetch_voe_planned_outages()
