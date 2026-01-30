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

# Мапа РЕМів VOE (з форми на сайті)
VOE_REGIONS = [
    # Вінницькі міські ЕМ
    '23',  # Вінницькі МЕМ
    # Вінницькі центральні ЕМ
    '25', '26', '27',  # Замостянський, Тиврівський, Літинський
    # Вінницькі східні ЕМ
    '29', '30', '31', '32', '33',  # Іллінецький, Немирівський, Липовецький, Оратівський, Погребищенський
    # Гайсинські ЕМ
    '35', '36', '37', '38', '39',  # Гайсинський, Бершадський, Теплицький, Тростянецький, Чечельницький
    # Жмеринські ЕМ
    '41', '42', '43',  # Жмеринський, Барський, Шаргородський
    # Могилів-Подільські ЕМ
    '45', '46', '47', '48',  # Могилів-Подільський, Мурованокуриловецький, Чернівецький, Ямпільський
    # Тульчинські ЕМ
    '50', '51', '52', '53',  # Тульчинський, Крижопільський, Піщанський, Томашпільський
    # Хмільницькі ЕМ
    '55', '56', '57',  # Хмільницький, Калинівський, Козятинський
]


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
        
        # Спочатку отримуємо сторінку щоб взяти form_build_id
        today = date.today()
        
        logger.info("📄 [VOE] Завантажуємо сторінку для отримання form_build_id...")
        session = requests.Session()
        initial_response = session.get(VOE_EMERGENCY_URL, headers=headers, timeout=30)
        initial_response.raise_for_status()
        initial_response.encoding = 'utf-8'
        
        # Парсимо форму для отримання form_build_id
        initial_soup = BeautifulSoup(initial_response.text, 'html.parser')
        form = initial_soup.find('form', {'id': 'disconnection-search-form'})
        
        if not form:
            logger.warning("⚠️ [VOE] Форма disconnection-search-form не знайдена")
            return []
        
        # Знаходимо form_build_id
        form_build_id_input = form.find('input', {'name': 'form_build_id'})
        form_build_id = form_build_id_input.get('value') if form_build_id_input else None
        
        if not form_build_id:
            logger.warning("⚠️ [VOE] form_build_id не знайдено")
            return []
        
        logger.info(f"✅ [VOE] form_build_id: {form_build_id}")
        
        # Ітеруємо по всіх регіонах VOE (без регіону повертає порожню сторінку)
        all_outages = []
        
        for region_id in VOE_REGIONS:
            try:
                data = {
                    'year': str(today.year),
                    'month': f"{today.month:02d}",
                    'region': region_id,
                    'form_build_id': form_build_id,
                    'form_id': 'disconnection_search_form',
                    'op': 'Показати'
                }
                
                logger.debug(f"📤 [VOE] Запит регіон {region_id}...")
                
                response = session.post(
                    VOE_EMERGENCY_URL,
                    data=data,
                    headers=headers,
                    timeout=30
                )
                response.raise_for_status()
                response.encoding = 'utf-8'
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Перевіряємо чи є дані
                empty_msg = soup.find('div', class_='empty')
                if empty_msg and 'Скористайтеся формою' in empty_msg.get_text():
                    continue
                
                # Шукаємо таблицю
                table = soup.find('table')
                if table:
                    region_outages = _parse_voe_table(table, 'emergency', region_id)
                    all_outages.extend(region_outages)
                    logger.debug(f"✅ [VOE] Регіон {region_id}: {len(region_outages)} відключень")
                    
            except Exception as e:
                logger.warning(f"⚠️ [VOE] Помилка обробки регіону {region_id}: {e}")
                continue
        
        # Перевірка чи дані змінилися
        from app.scraper.page_cache import has_page_changed
        combined_hash = str(len(all_outages)) + str([o.get('start_time') for o in all_outages[:5]])
        if not has_page_changed("voe_emergency", combined_hash):
            logger.info("ℹ️ [VOE] Аварійні: дані не змінилися")
            return None
        
        outages = all_outages
        
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
        
        # Спочатку отримуємо сторінку щоб взяти form_build_id
        logger.info("📄 [VOE] Завантажуємо сторінку для отримання form_build_id...")
        session = requests.Session()
        initial_response = session.get(VOE_PLANNED_URL, headers=headers, timeout=30)
        initial_response.raise_for_status()
        initial_response.encoding = 'utf-8'
        
        # Парсимо форму
        initial_soup = BeautifulSoup(initial_response.text, 'html.parser')
        form = initial_soup.find('form', {'id': 'disconnection-search-form'})
        
        if not form:
            logger.warning("⚠️ [VOE] Форма disconnection-search-form не знайдена")
            return []
        
        form_build_id_input = form.find('input', {'name': 'form_build_id'})
        form_build_id = form_build_id_input.get('value') if form_build_id_input else None
        
        if not form_build_id:
            logger.warning("⚠️ [VOE] form_build_id не знайдено")
            return []
        
        logger.info(f"✅ [VOE] form_build_id: {form_build_id}")
        
        # Ітеруємо по всіх регіонах
        all_outages = []
        
        for region_id in VOE_REGIONS:
            try:
                data = {
                    'year': str(today.year),
                    'month': f"{today.month:02d}",
                    'region': region_id,
                    'form_build_id': form_build_id,
                    'form_id': 'disconnection_search_form',
                    'op': 'Показати'
                }
                
                logger.debug(f"📤 [VOE] Запит регіон {region_id}...")
                
                response = session.post(
                    VOE_PLANNED_URL,
                    data=data,
                    headers=headers,
                    timeout=30
                )
                response.raise_for_status()
                response.encoding = 'utf-8'
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                empty_msg = soup.find('div', class_='empty')
                if empty_msg and 'Скористайтеся формою' in empty_msg.get_text():
                    continue
                
                table = soup.find('table')
                if table:
                    region_outages = _parse_voe_table(table, 'planned', region_id)
                    all_outages.extend(region_outages)
                    logger.debug(f"✅ [VOE] Регіон {region_id}: {len(region_outages)} відключень")
                    
            except Exception as e:
                logger.warning(f"⚠️ [VOE] Помилка обробки регіону {region_id}: {e}")
                continue
        
        from app.scraper.page_cache import has_page_changed
        combined_hash = str(len(all_outages)) + str([o.get('start_time') for o in all_outages[:5]])
        if not has_page_changed("voe_planned", combined_hash):
            logger.info("ℹ️ [VOE] Планові: дані не змінилися")
            return None
        
        outages = all_outages
        
        logger.info(f"✅ [VOE] Планові: знайдено {len(outages)} відключень")
        return outages
        
    except requests.RequestException as e:
        logger.error(f"❌ [VOE] Помилка завантаження planned: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ [VOE] Помилка парсингу planned: {e}")
        logger.exception("Детальна інформація:")
        return []


def _parse_voe_table(table, outage_type: str, region_id: str = '') -> List[Dict]:
    """
    Парсить HTML таблицю з відключеннями VOE
    
    Структура таблиці:
    0: п/п
    1: Тип відключення
    2: Плановий час закінчення
    3: Назва населеного пункту
    4: Назва вулиць, перелік будинків
    5: Початок відключення
    6: Фактичний час закінчення
    7: Час формування інформації
    
    Args:
        table: BeautifulSoup table element
        outage_type: 'emergency' або 'planned'
        region_id: ID регіону VOE
    
    Returns:
        List[Dict]: Список відключень
    """
    outages = []
    
    try:
        rows = table.find_all('tr')[1:]  # Пропускаємо заголовок
        
        for row in rows:
            cells = row.find_all(['td', 'th'])
            
            if len(cells) < 6:
                continue
            
            try:
                cell_texts = [cell.get_text(strip=True) for cell in cells]
                
                # VOE має різну кількість колонок:
                # Аварійні: 8 колонок [п/п, Тип, Плановий кінець, Місто, Вулиці, Початок, Фактичний кінець, Час формування]
                # Планові: 9 колонок [п/п, Тип, Плановий кінець, Місто, Вулиці, Статус, Початок, Фактичний кінець, Час формування]
                
                if len(cell_texts) >= 9:  # Планові відключення (9 колонок)
                    work_type = cell_texts[1]
                    planned_end = cell_texts[2]
                    city = cell_texts[3]
                    streets_houses = cell_texts[4]
                    status = cell_texts[5]  # Нова колонка "Статус"
                    start = cell_texts[6]
                    actual_end = cell_texts[7]
                elif len(cell_texts) >= 8:  # Аварійні відключення (8 колонок)
                    work_type = cell_texts[1]
                    planned_end = cell_texts[2]
                    city = cell_texts[3]
                    streets_houses = cell_texts[4]
                    status = None
                    start = cell_texts[5]
                    actual_end = cell_texts[6]
                else:
                    logger.debug(f"⚠️ [VOE] Недостатньо колонок: {len(cell_texts)}")
                    continue
                
                # Парсимо адресу: "ВІННИЦЯ: вулиця Хмельницьке шосе 116,122А"
                street = ""
                house_numbers = ""
                if ":" in streets_houses:
                    parts = streets_houses.split(":", 1)
                    if len(parts) == 2:
                        street = parts[1].strip()
                        # Відділяємо номери будинків від вулиці
                        street_parts = street.rsplit(" ", 1)
                        if len(street_parts) == 2 and any(c.isdigit() for c in street_parts[1]):
                            street = street_parts[0]
                            house_numbers = street_parts[1]
                        else:
                            # Якщо вулиця містить все разом
                            pass
                else:
                    street = streets_houses
                
                # Парсимо час (формат: "2026-01-28 22:00:00")
                start_time = _parse_voe_datetime(start)
                end_time = _parse_voe_datetime(actual_end if actual_end else planned_end)
                
                if not all([city, street, start_time, end_time]):
                    logger.debug(f"⚠️ [VOE] Пропущено рядок - не всі поля")
                    continue
                
                outage = {
                    'region': 'voe',
                    'rem_id': region_id,
                    'rem_name': f'VOE-{region_id}',
                    'city': city,
                    'street': street,
                    'house_numbers': house_numbers,
                    'work_type': work_type,
                    'created_date': datetime.now(),
                    'start_time': start_time,
                    'end_time': end_time,
                    'is_active': datetime.now() <= end_time if end_time else True,
                }
                outages.append(outage)
                
            except Exception as e:
                logger.warning(f"⚠️ [VOE] Помилка парсингу рядка: {e}")
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
            time_start_elem = item.find(class_=['start-time', 'час-початку'])
            time_end_elem = item.find(class_=['end-time', 'час-кінця'])
            
            start_time = _parse_voe_datetime(time_start_elem.get_text(strip=True)) if time_start_elem else None
            end_time = _parse_voe_datetime(time_end_elem.get_text(strip=True)) if time_end_elem else None
            
            if not all([city, street, start_time, end_time]):
                continue
            
            outage = {
                'region': 'voe',
                'rem_id': rem_name,
                'rem_name': rem_name,
                'city': city,
                'street': street,
                'house_numbers': house_numbers,
                'work_type': 'Аварійне відключення' if outage_type == 'emergency' else 'Планове відключення',
                'created_date': datetime.now(),
                'start_time': start_time,
                'end_time': end_time,
                'is_active': datetime.now() <= end_time,
            }
            outages.append(outage)
            
        except Exception as e:
            logger.warning(f"⚠️ [VOE] Помилка парсингу елемента: {e}")
            continue
    
    return outages


def _parse_voe_datetime(dt_str: str) -> Optional[datetime]:
    """
    Парсить дату/час VOE у форматі '2026-01-28 22:00:00'
    
    Args:
        dt_str: Рядок з датою/часом
    
    Returns:
        datetime або None
    """
    if not dt_str or dt_str.strip() == '':
        return None
    
    dt_str = dt_str.strip()
    
    # Формат VOE: "2026-01-28 22:00:00"
    try:
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    except:
        pass
    
    # Інші можливі формати
    formats = [
        "%Y-%m-%d %H:%M",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(dt_str, fmt)
        except:
            continue
    
    logger.debug(f"⚠️ [VOE] Не вдалося розпарсити дату: '{dt_str}'")
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
