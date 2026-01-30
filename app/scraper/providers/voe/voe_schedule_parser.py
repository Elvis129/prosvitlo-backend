"""
VOE (Вінницяобленерго) Schedule Parser для графіків
Файл: app/scraper/providers/voe/voe_schedule_parser.py

Особливості VOE графіків:
- Можуть бути у форматі PDF (потребує конвертації)
- Або у форматі зображень (PNG/JPG)
- Структура графіка відрізняється від HOE
- Потрібен окремий парсер для розпізнавання

URL: https://www.voe.com.ua/informatsiya-pro-cherhy-hrafika-pohodynnykh-vidklyuchen-hpv-1
"""

import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta
from typing import List, Dict, Optional
import logging
import hashlib

logger = logging.getLogger(__name__)

VOE_SCHEDULE_PAGE = "https://www.voe.com.ua/informatsiya-pro-cherhy-hrafika-pohodynnykh-vidklyuchen-hpv-1"


def fetch_voe_schedule_images() -> List[Dict]:
    """
    Завантажує графіки ГПВ з VOE
    
    Якщо VOE публікує PDF - конвертуємо в зображення
    Якщо зображення - завантажуємо напряму
    
    Returns:
        List[Dict]: Список графіків для парсингу
        Формат аналогічний до HOE: [
            {
                'date': date(2026, 1, 28),
                'image_url': 'https://...',
                'recognized_text': '',  # Для VOE не використовується
                'content_hash': 'abc123...',
                'region': 'voe'
            }
        ]
    """
    try:
        logger.info("🔍 [VOE] Завантажуємо графіки...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(VOE_SCHEDULE_PAGE, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.text, 'html.parser')
        schedules = []
        
        # Шукаємо посилання на графіки
        # Варіант 1: Посилання на зображення
        image_links = soup.find_all('a', href=lambda x: x and any(ext in x.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif']))
        
        if image_links:
            logger.info(f"📷 [VOE] Знайдено {len(image_links)} посилань на зображення")
            schedules = _parse_voe_image_links(image_links)
        
        # Варіант 2: Посилання на PDF
        if not schedules:
            pdf_links = soup.find_all('a', href=lambda x: x and '.pdf' in x.lower())
            
            if pdf_links:
                logger.info(f"📄 [VOE] Знайдено {len(pdf_links)} PDF файлів")
                schedules = _parse_voe_pdf_links(pdf_links)
        
        # Варіант 3: Зображення безпосередньо на сторінці
        if not schedules:
            images = soup.find_all('img', src=lambda x: x and 'schedule' in x.lower() or 'графік' in x.lower())
            
            if images:
                logger.info(f"🖼️ [VOE] Знайдено {len(images)} зображень на сторінці")
                schedules = _parse_voe_inline_images(images)
        
        logger.info(f"✅ [VOE] Завантажено {len(schedules)} графіків")
        return schedules
        
    except requests.RequestException as e:
        logger.error(f"❌ [VOE] Помилка завантаження графіків: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ [VOE] Помилка парсингу графіків: {e}")
        logger.exception("Детальна інформація:")
        return []


def _parse_voe_image_links(links) -> List[Dict]:
    """
    Парсить посилання на зображення графіків
    
    Args:
        links: Список BeautifulSoup <a> елементів
    
    Returns:
        List[Dict]: Список графіків
    """
    schedules = []
    today = date.today()
    
    for link in links:
        try:
            href = link.get('href')
            if not href:
                continue
            
            # Якщо відносний URL - додаємо домен
            if href.startswith('/'):
                href = 'https://www.voe.com.ua' + href
            elif not href.startswith('http'):
                href = 'https://www.voe.com.ua/' + href
            
            # Витягуємо дату з назви файлу або тексту посилання
            link_text = link.get_text(strip=True)
            schedule_date = _parse_voe_date_from_text(href, link_text)
            
            if not schedule_date:
                # Якщо дату не знайдено - використовуємо сьогодні/завтра
                schedule_date = today
            
            # Генеруємо хеш для перевірки змін
            content_hash = hashlib.md5(href.encode()).hexdigest()
            
            schedule = {
                'date': schedule_date,
                'image_url': href,
                'recognized_text': '',  # VOE не використовує текстову розшифровку
                'content_hash': content_hash,
                'region': 'voe',
                'source': 'image'
            }
            schedules.append(schedule)
            
        except Exception as e:
            logger.warning(f"⚠️ [VOE] Помилка парсингу посилання: {e}")
            continue
    
    return schedules


def _parse_voe_pdf_links(links) -> List[Dict]:
    """
    Парсить посилання на PDF графіки
    
    УВАГА: PDF потребують конвертації в зображення для OCR
    Для цього потрібен pdf2image та poppler
    
    Args:
        links: Список BeautifulSoup <a> елементів
    
    Returns:
        List[Dict]: Список графіків (PDF URLs)
    """
    schedules = []
    today = date.today()
    
    for link in links:
        try:
            href = link.get('href')
            if not href:
                continue
            
            if href.startswith('/'):
                href = 'https://www.voe.com.ua' + href
            elif not href.startswith('http'):
                href = 'https://www.voe.com.ua/' + href
            
            link_text = link.get_text(strip=True)
            schedule_date = _parse_voe_date_from_text(href, link_text)
            
            if not schedule_date:
                schedule_date = today
            
            content_hash = hashlib.md5(href.encode()).hexdigest()
            
            schedule = {
                'date': schedule_date,
                'image_url': href,
                'recognized_text': '',
                'content_hash': content_hash,
                'region': 'voe',
                'source': 'pdf',  # Позначаємо що це PDF
                'needs_conversion': True  # Потребує конвертації
            }
            schedules.append(schedule)
            
            logger.info(f"📄 [VOE] PDF графік: {link_text} ({schedule_date})")
            
        except Exception as e:
            logger.warning(f"⚠️ [VOE] Помилка парсингу PDF: {e}")
            continue
    
    return schedules


def _parse_voe_inline_images(images) -> List[Dict]:
    """
    Парсить зображення які вже присутні на сторінці
    
    Args:
        images: Список BeautifulSoup <img> елементів
    
    Returns:
        List[Dict]: Список графіків
    """
    schedules = []
    today = date.today()
    
    for img in images:
        try:
            src = img.get('src')
            if not src:
                continue
            
            if src.startswith('/'):
                src = 'https://www.voe.com.ua' + src
            elif not src.startswith('http'):
                src = 'https://www.voe.com.ua/' + src
            
            alt_text = img.get('alt', '')
            title_text = img.get('title', '')
            
            schedule_date = _parse_voe_date_from_text(src, f"{alt_text} {title_text}")
            
            if not schedule_date:
                schedule_date = today
            
            content_hash = hashlib.md5(src.encode()).hexdigest()
            
            schedule = {
                'date': schedule_date,
                'image_url': src,
                'recognized_text': '',
                'content_hash': content_hash,
                'region': 'voe',
                'source': 'inline_image'
            }
            schedules.append(schedule)
            
        except Exception as e:
            logger.warning(f"⚠️ [VOE] Помилка парсингу зображення: {e}")
            continue
    
    return schedules


def _parse_voe_date_from_text(url: str, text: str) -> Optional[date]:
    """
    Витягує дату з URL або тексту
    
    Можливі формати:
    - "ГПВ 15.01.2026"
    - "grafik-2026-01-15.jpg"
    - "Графік на 15 січня"
    - "Завтра" / "Сьогодні"
    
    Args:
        url: URL файлу
        text: Текст посилання або alt
    
    Returns:
        date або None
    """
    import re
    
    combined_text = f"{url} {text}".lower()
    today = date.today()
    
    # Варіант 1: Дата в форматі DD.MM.YYYY
    pattern1 = r'(\d{2})\.(\d{2})\.(\d{4})'
    match1 = re.search(pattern1, combined_text)
    
    if match1:
        day, month, year = map(int, match1.groups())
        try:
            return date(year, month, day)
        except ValueError:
            pass
    
    # Варіант 2: Дата в форматі YYYY-MM-DD
    pattern2 = r'(\d{4})-(\d{2})-(\d{2})'
    match2 = re.search(pattern2, combined_text)
    
    if match2:
        year, month, day = map(int, match2.groups())
        try:
            return date(year, month, day)
        except ValueError:
            pass
    
    # Варіант 3: Ключові слова
    if 'завтра' in combined_text or 'tomorrow' in combined_text:
        return today + timedelta(days=1)
    
    if 'сьогодні' in combined_text or 'today' in combined_text:
        return today
    
    if 'післязавтра' in combined_text:
        return today + timedelta(days=2)
    
    # Варіант 4: Дата з місяцем словом "15 січня 2026"
    months_ua = {
        'січ': 1, 'лют': 2, 'берез': 3, 'квіт': 4, 'трав': 5, 'черв': 6,
        'лип': 7, 'серп': 8, 'вересн': 9, 'жовтн': 10, 'листопад': 11, 'груд': 12
    }
    
    for month_name, month_num in months_ua.items():
        if month_name in combined_text:
            # Шукаємо число перед місяцем
            pattern = rf'(\d{{1,2}})\s+{month_name}'
            match = re.search(pattern, combined_text)
            if match:
                day = int(match.group(1))
                # Рік - поточний або наступний
                year = today.year
                try:
                    result_date = date(year, month_num, day)
                    # Якщо дата в минулому - додаємо рік
                    if result_date < today:
                        result_date = date(year + 1, month_num, day)
                    return result_date
                except ValueError:
                    pass
    
    logger.debug(f"⚠️ [VOE] Не вдалося витягти дату з: '{combined_text[:100]}'")
    return None


def parse_voe_queue_schedule(local_path: str) -> Dict:
    """
    Парсить графік VOE з файлу
    
    VOE графіки можуть бути:
    - PDF з текстом черг (парсимо текст)
    - Зображення з кольоровим графіком (використовуємо color parser)
    
    Args:
        local_path: Локальний шлях до файлу графіка
    
    Returns:
        Dict: Мапа черг на РЕМ
        {
            "РЕМ Вінниця-1": 1,
            "РЕМ Вінниця-2": 2,
            ...
        }
    """
    try:
        logger.info(f"🎨 [VOE] Парсимо графік: {local_path}")
        
        # Якщо це PDF - парсимо текст
        if local_path.lower().endswith('.pdf'):
            logger.info("📄 [VOE] Графік у форматі PDF")
            
            from app.scraper.providers.voe.voe_pdf_parser import parse_voe_pdf_schedule
            
            queues = parse_voe_pdf_schedule(local_path)
            
            if queues:
                logger.info(f"✅ [VOE] Розпарсовано {len(queues)} черг з PDF")
                
                # Конвертуємо черги в формат РЕМ → черга
                # VOE формат: "1.1", "1.2", "2.1", "2.2", etc.
                # Перша цифра - РЕМ, друга - черга
                rem_map = {}
                for queue_str, streets in queues.items():
                    try:
                        parts = queue_str.split('.')
                        if len(parts) == 2:
                            rem_num = int(parts[0])
                            queue_num = int(parts[1])
                            
                            # Створюємо РЕМ назву
                            rem_name = f"VOE-{rem_num}"
                            rem_map[rem_name] = queue_num
                            
                    except ValueError:
                        continue
                
                return rem_map
            else:
                logger.warning("⚠️ [VOE] PDF порожній або не розпізнано")
                return {}
        
        # Якщо це зображення - використовуємо color parser
        elif any(local_path.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif']):
            logger.info("🖼️ [VOE] Графік у форматі зображення")
            
            try:
                from app.scraper.schedule_color_parser import parse_schedule_from_image
                parsed_data = parse_schedule_from_image(local_path)
                
                if parsed_data:
                    logger.info(f"✅ [VOE] Розпарсовано {len(parsed_data)} черг")
                else:
                    logger.warning("⚠️ [VOE] Графік порожній або не розпізнано")
                
                return parsed_data
                
            except Exception as e:
                logger.error(f"❌ [VOE] Помилка color parser: {e}")
                return {}
        
        else:
            logger.warning(f"⚠️ [VOE] Невідомий формат файлу: {local_path}")
            return {}
        
    except Exception as e:
        logger.error(f"❌ [VOE] Помилка парсингу графіка: {e}")
        logger.exception("Детальна інформація:")
        return {}


# Для зворотної сумісності з HOE API
def fetch_schedule_images():
    """Alias для fetch_voe_schedule_images"""
    return fetch_voe_schedule_images()


def parse_queue_schedule(schedule_data: dict):
    """Alias для parse_voe_queue_schedule"""
    return parse_voe_queue_schedule(schedule_data)
