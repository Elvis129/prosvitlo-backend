import requests
from bs4 import BeautifulSoup
import re
from datetime import date, datetime
from typing import List, Dict, Tuple
import logging
import hashlib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_schedule_images() -> List[Dict]:
    """
    Парсить сторінку з графіками та повертає список графіків з текстовою версією
    """
    url = "https://hoe.com.ua/page/pogodinni-vidkljuchennja"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        schedules = []
        schedules_by_date = {}  # Зберігаємо всі версії для кожної дати
        
        # Шукаємо всі img теги з графіками
        images = soup.find_all('img')
        
        for img in images:
            src = img.get('src', '')
            alt = img.get('alt', '')
            
            # Фільтруємо тільки графіки (файли з певним патерном)
            if 'file' in src and '.png' in src.lower() and 'ГПВ' in alt:
                # Витягуємо дату з alt тексту (формат: ГПВ-06.12.25 або ГПВ-06.12.25_1 або ГПВ-06.12.25-_02)
                date_match = re.search(r'(\d{2})\.(\d{2})\.(\d{2})', alt)
                if date_match:
                    day, month, year = date_match.groups()
                    schedule_date = date(2000 + int(year), int(month), int(day))
                    
                    # Формуємо повний URL якщо потрібно
                    if not src.startswith('http'):
                        src = f"https://hoe.com.ua{src}"
                    
                    logger.info(f"Знайдено графік: {alt} - {schedule_date}")
                    
                    # Шукаємо текстову версію графіка на сторінці після цього img
                    text_schedule = extract_text_schedule_from_page(soup, img)
                    
                    # Генеруємо хеш для перевірки змін
                    content_hash = generate_content_hash(src, text_schedule)
                    
                    schedule_info = {
                        'date': schedule_date,
                        'image_url': src,
                        'alt_text': alt,
                        'recognized_text': text_schedule,
                        'content_hash': content_hash
                    }
                    
                    # Зберігаємо в dict - якщо для дати вже є графік, додаємо до списку
                    if schedule_date not in schedules_by_date:
                        schedules_by_date[schedule_date] = []
                    schedules_by_date[schedule_date].append(schedule_info)
        
        # Для кожної дати беремо ОСТАННІЙ (найновіший) графік
        # HOE додає суфікси типу "_02", "_03" до оновлених версій
        for schedule_date, versions in schedules_by_date.items():
            if len(versions) > 1:
                logger.warning(f"⚠️ Знайдено {len(versions)} версій графіка для {schedule_date}")
                for v in versions:
                    logger.info(f"   - {v['alt_text']}: {v['image_url']}")
                # Беремо останню версію (вона йде першою на сторінці)
                selected = versions[0]
                logger.info(f"✅ Вибрано ПЕРШУ версію (найновішу): {selected['alt_text']}")
                schedules.append(selected)
            else:
                schedules.append(versions[0])
        
        return schedules
        
    except Exception as e:
        logger.error(f"Помилка парсингу графіків: {e}")
        return []


def extract_text_schedule_from_page(soup: BeautifulSoup, img_tag) -> str:
    """
    Витягує текстову версію графіка зі сторінки після конкретного img тега
    
    Шукає наступний <ul> список після img та витягує рядки з підчергами
    """
    try:
        alt = img_tag.get('alt', '')
        logger.info(f"Шукаємо текст для графіка: {alt}")
        
        # Знаходимо батьківський елемент img (зазвичай <p>)
        parent = img_tag.parent
        if not parent:
            logger.warning(f"Не знайдено батьківський елемент для img {alt}")
            return ""
        
        # Шукаємо наступний <ul> список після батьківського <p>
        ul_element = None
        for sibling in parent.next_siblings:
            if sibling.name == 'ul':
                ul_element = sibling
                break
            # Також перевіряємо чи ul не в наступному <p> (іноді буває)
            if sibling.name == 'p':
                next_ul = sibling.find('ul')
                if next_ul:
                    ul_element = next_ul
                    break
        
        if not ul_element:
            logger.warning(f"Не знайдено <ul> список після img {alt}")
            return ""
        
        # Витягуємо всі рядки з підчергами
        text_lines = []
        for li in ul_element.find_all('li', recursive=False):
            text = li.get_text(strip=True)
            if 'підчерга' in text and '–' in text:
                text_lines.append(text)
        
        if text_lines:
            result = '\n'.join(text_lines)
            logger.info(f"Знайдено текстовий графік для {alt}: {len(text_lines)} рядків")
            return result
        else:
            logger.warning(f"Рядки з підчергами не знайдено для {alt}")
            return ""
            
    except Exception as e:
        logger.error(f"Помилка витягування текстового графіка: {e}", exc_info=True)
        return ""


def generate_content_hash(image_url: str, text: str) -> str:
    """
    Генерує хеш для перевірки змін контенту
    """
    content = f"{image_url}|{text}"
    return hashlib.md5(content.encode()).hexdigest()


def parse_queue_schedule(recognized_text: str) -> Dict[str, List[Tuple[int, int]]]:
    """
    Парсить текстовий графік і витягує години відключень для кожної черги
    
    Вхідний формат:
    • підчерга 6.2 – з 09:00 до 12:00, з 16:00 до 22:00;
    
    Повертає: {'6.2': [(9, 12), (16, 22)], '3.1': [(12, 16), (18, 23)], ...}
    де кожен tuple - це (година_початку, година_кінця)
    """
    if not recognized_text:
        return {}
    
    queue_schedules = {}
    
    try:
        lines = recognized_text.split('\n')
        
        # Паттерн для розпізнавання рядків типу:
        # • підчерга 6.2 – з 09:00 до 12:00, з 16:00 до 22:00;
        pattern = r'підчерга\s+(\d+\.\d+)\s*–\s*(.+?)(?:;|$)'
        
        for line in lines:
            match = re.search(pattern, line)
            if match:
                queue_num = match.group(1)
                intervals_text = match.group(2)
                
                # Витягуємо всі часові інтервали з рядка
                # Формат: з 09:00 до 12:00
                time_pattern = r'з\s+(\d{1,2}):(\d{2})\s+до\s+(\d{1,2}):(\d{2})'
                time_matches = re.findall(time_pattern, intervals_text)
                
                intervals = []
                for time_match in time_matches:
                    start_hour = int(time_match[0])
                    start_min = int(time_match[1])
                    end_hour = int(time_match[2])
                    end_min = int(time_match[3])
                    
                    # Конвертуємо в години (округлюємо хвилини)
                    # Якщо хвилини є (наприклад 17:30), то зберігаємо як float
                    if start_min > 0:
                        start = start_hour + start_min / 60.0
                    else:
                        start = start_hour
                        
                    if end_min > 0:
                        end = end_hour + end_min / 60.0
                    else:
                        end = end_hour
                    
                    intervals.append((start, end))
                
                if intervals:
                    queue_schedules[queue_num] = intervals
                    logger.info(f"Черга {queue_num}: {len(intervals)} інтервалів - {intervals}")
        
        if not queue_schedules:
            logger.warning("Не вдалося розпарсити жодної черги з тексту")
        else:
            logger.info(f"Успішно розпарсено {len(queue_schedules)} черг")
        
    except Exception as e:
        logger.error(f"Помилка парсингу графіка: {e}")
        return {}
    
    return queue_schedules
