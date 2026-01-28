"""
Парсер для аварійних та планових відключень з сайту hoe.com.ua
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Optional
import logging
from app.scraper.page_cache import has_page_changed

logger = logging.getLogger(__name__)

# Мапа РЕМів
REM_MAP = {
    4: "Городоцький РЕМ",
    23: "Кам.-Подільський РЕМ",
    24: "Летичівський РЕМ",
    12: "Старокостянтинівський РЕМ",
    21: "Хмельницький РЕМ",
    17: "Шепетівський РЕМ",
}


def parse_datetime(date_str: str, time_str: str) -> Optional[datetime]:
    """
    Парсить дату та час у datetime об'єкт
    Приклад: "06.12.2025" + "18:00" -> datetime(2025, 12, 6, 18, 0)
    """
    try:
        datetime_str = f"{date_str} {time_str}"
        return datetime.strptime(datetime_str, "%d.%m.%Y %H:%M")
    except Exception as e:
        logger.error(f"Помилка парсингу дати/часу: {date_str} {time_str} - {e}")
        return None


def extract_city_from_text(text: str) -> str:
    """
    Витягує назву міста з тексту типу "м. Хмельницький (Хмельницька громада)"
    """
    # Видаляємо "м. " або "смт. " на початку
    text = text.strip()
    if text.startswith("м. "):
        text = text[3:]
    elif text.startswith("смт. "):
        text = text[5:]
    
    # Видаляємо частину в дужках
    if "(" in text:
        text = text[:text.index("(")].strip()
    
    return text


def parse_outages(rem_id: int, type_id: int, date_range: str = "06.12.2025 - 11.12.2025") -> List[Dict]:
    """
    Парсить відключення для заданого РЕМу та типу
    
    Args:
        rem_id: ID району електромереж (4, 12, 17, 21, 23, 24)
        type_id: Тип відключення (1 - аварійні, 2 - планові)
        date_range: Період для планових відключень
    
    Returns:
        List[Dict]: Список відключень з усією інформацією
    """
    url = "https://hoe.com.ua/shutdown/eventlist"
    
    data = {
        "TypeId": str(type_id),
        "RemId": str(rem_id),
        "DateRange": date_range,
        "PageNumber": "1"
    }
    
    try:
        response = requests.post(url, data=data, timeout=30)
        response.raise_for_status()
        
        # ⚡ ОПТИМІЗАЦІЯ: Перевіряємо чи змінилася сторінка перед парсингом
        page_key = f"outages_rem{rem_id}_type{type_id}"
        if not has_page_changed(page_key, response.text):
            # Сторінка не змінилася - повертаємо None як сигнал не робити нічого
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        outages = []
        
        # Знаходимо всі рядки таблиці (tr без класу "street")
        rows = soup.find_all('tr')
        
        current_outage = None
        
        for row in rows:
            # Пропускаємо заголовок таблиці
            if row.find('th'):
                continue
            
            # Якщо це не рядок з вулицями (street)
            if 'street' not in row.get('class', []):
                # Це основний рядок з інформацією про відключення
                cells = row.find_all('td')
                
                if len(cells) >= 5:
                    # Витягуємо місто
                    city_element = cells[0].find('p', class_='city')
                    if city_element:
                        city = extract_city_from_text(city_element.get_text(strip=True))
                    else:
                        continue
                    
                    # Вид робіт
                    work_type = cells[1].get_text(strip=True)
                    
                    # Дата створення
                    created_date_str = cells[2].find('div', class_='stime').get_text(strip=True)
                    

                    # Час початку - витягуємо текст і strong окремо
                    start_cell = cells[3].find('div', class_='stime')
                    # Витягуємо дату (текст без тегів strong)
                    start_date = start_cell.get_text(strip=True)
                    start_time = "00:00"
                    # Витягуємо час з <strong>
                    start_strong = start_cell.find('strong')
                    if start_strong:
                        start_time = start_strong.get_text(strip=True)
                        # Видаляємо час з дати
                        start_date = start_date.replace(start_time, '').strip()
                    else:
                        # Якщо немає strong, пробуємо розділити
                        parts = start_date.split()
                        if len(parts) >= 2:
                            start_date, start_time = parts[0], parts[1]
                    
                    # Час відновлення - аналогічно
                    end_cell = cells[4].find('div', class_='stime')
                    end_date = end_cell.get_text(strip=True)
                    end_time = "23:59"
                    end_strong = end_cell.find('strong')
                    if end_strong:
                        end_time = end_strong.get_text(strip=True)
                        end_date = end_date.replace(end_time, '').strip()
                    else:
                        parts = end_date.split()
                        if len(parts) >= 2:
                            end_date, end_time = parts[0], parts[1]

                    # Парсимо дати
                    created_datetime = parse_datetime(created_date_str, "00:00")
                    start_datetime = parse_datetime(start_date, start_time)
                    end_datetime = parse_datetime(end_date, end_time)
                    
                    if not all([created_datetime, start_datetime, end_datetime]):
                        continue
                    
                    current_outage = {
                        'rem_id': rem_id,
                        'rem_name': REM_MAP.get(rem_id, f"РЕМ {rem_id}"),
                        'city': city,
                        'work_type': work_type,
                        'created_date': created_datetime,
                        'start_time': start_datetime,
                        'end_time': end_datetime,
                        'streets': []
                    }
            
            # Якщо це рядок з вулицями
            elif 'street' in row.get('class', []) and current_outage:
                # Знаходимо всі вулиці в цьому рядку
                street_paragraphs = row.find_all('p')
                
                for para in street_paragraphs:
                    street_name_element = para.find('strong')
                    if street_name_element:
                        street_name = street_name_element.get_text(strip=True)
                        
                        # Знаходимо номери будинків
                        house_span = para.find('span', class_='house')
                        if house_span:
                            house_numbers = house_span.get_text(strip=True)
                            
                            # Додаємо окремий запис для кожної вулиці
                            street_outage = current_outage.copy()
                            street_outage['street'] = street_name
                            street_outage['house_numbers'] = house_numbers
                            
                            # Видаляємо тимчасовий ключ
                            street_outage.pop('streets', None)
                            
                            outages.append(street_outage)
                
                # Після обробки вулиць, скидаємо current_outage
                if outages and outages[-1].get('street'):
                    current_outage = None
        
        logger.info(f"Успішно спарсено {len(outages)} відключень для РЕМ {rem_id}, тип {type_id}")
        return outages
    
    except Exception as e:
        logger.error(f"Помилка парсингу відключень для РЕМ {rem_id}: {e}")
        return []


def fetch_all_emergency_outages() -> List[Dict]:
    """
    Витягує всі аварійні відключення для всіх РЕМів
    """
    all_outages = []
    all_unchanged = True  # Флаг чи всі сторінки без змін
    
    for rem_id in REM_MAP.keys():
        outages = parse_outages(rem_id, type_id=1)
        if outages is None:
            # Сторінка не змінилася, пропускаємо
            continue
        all_unchanged = False
        all_outages.extend(outages)
    
    if all_unchanged:
        logger.info("✓ Всі сторінки аварійних відключень без змін")
        return None  # Сигнал що нічого не змінилося
    
    logger.info(f"Загалом спарсено {len(all_outages)} аварійних відключень")
    return all_outages


def fetch_all_planned_outages(date_range: str = None) -> List[Dict]:
    """
    Витягує всі планові відключення для всіх РЕМів
    
    Args:
        date_range: Період у форматі "06.12.2025 - 11.12.2025"
                   Якщо None, використовується період на 5 днів вперед
    """
    if not date_range:
        from datetime import date, timedelta
        today = date.today()
        end_date = today + timedelta(days=5)
        date_range = f"{today.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"
    
    all_outages = []
    all_unchanged = True  # Флаг чи всі сторінки без змін
    
    for rem_id in REM_MAP.keys():
        outages = parse_outages(rem_id, type_id=2, date_range=date_range)
        if outages is None:
            # Сторінка не змінилася, пропускаємо
            continue
        all_unchanged = False
        all_outages.extend(outages)
    
    if all_unchanged:
        logger.info("✓ Всі сторінки планових відключень без змін")
        return None  # Сигнал що нічого не змінилося
    
    logger.info(f"Загалом спарсено {len(all_outages)} планових відключень")
    return all_outages
