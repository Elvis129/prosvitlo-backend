"""
ПРИКЛАД: VOE Schedule Parser для графіків ГПВ (PDF)
Файл: app/scraper/providers/voe/voe_schedule_parser.py

VOE публікує графіки у форматі PDF, тому потрібен додатковий крок:
PDF → Зображення → OCR → Дані

ЗАЛЕЖНОСТІ:
pip install pdf2image

macOS:
brew install poppler

Ubuntu/Debian:
apt-get install poppler-utils
"""

import requests
from datetime import date, timedelta
from typing import List, Dict, Optional
import logging
import hashlib
import io
import os

logger = logging.getLogger(__name__)

# URL сторінки з графіками VOE
VOE_SCHEDULE_PAGE = "https://www.voe.com.ua/informatsiya-pro-cherhy-hrafika-pohodynnykh-vidklyuchen-hpv-1"

# Приклад URL PDF файлу (потрібно парсити зі сторінки динамічно)
VOE_SCHEDULE_PDF_EXAMPLE = "https://www.voe.com.ua/sites/default/files/2026-01/7.7-gpv-voe-2025-26-zima_-sayt.pdf"


def fetch_voe_schedule_images() -> List[Dict]:
    """
    Завантажує графіки ГПВ з VOE (PDF → зображення)
    
    Returns:
        List[Dict]: Список графіків з даними для OCR
        Формат: [
            {
                'date': date(2026, 1, 15),
                'image_url': 'https://...pdf',
                'image_data': PIL.Image,  # Для OCR
                'region': 'voe'
            }
        ]
    """
    try:
        logger.info("🔍 Завантажуємо графіки VOE...")
        
        # Крок 1: Завантажуємо сторінку з графіками
        page_content = fetch_voe_schedule_page()
        if not page_content:
            return []
        
        # Крок 2: Витягуємо URLs PDF файлів зі сторінки
        pdf_urls = extract_pdf_urls_from_page(page_content)
        if not pdf_urls:
            logger.warning("⚠️ Не знайдено PDF файлів на сторінці VOE")
            return []
        
        logger.info(f"📄 Знайдено {len(pdf_urls)} PDF файлів")
        
        schedules = []
        
        for pdf_info in pdf_urls:
            pdf_url = pdf_info['url']
            schedule_date = pdf_info.get('date', date.today())
            
            # Крок 3: Завантажуємо PDF
            pdf_data = download_pdf(pdf_url)
            if not pdf_data:
                continue
            
            # Крок 4: Конвертуємо PDF → зображення
            images = convert_pdf_to_images(pdf_data)
            if not images:
                continue
            
            logger.info(f"📷 PDF містить {len(images)} сторінок")
            
            # Крок 5: Обробляємо кожну сторінку
            for page_num, image in enumerate(images, start=1):
                # Визначаємо дату для кожної сторінки
                # (якщо в PDF кілька днів - треба парсити з тексту)
                page_date = schedule_date + timedelta(days=page_num - 1)
                
                schedule = {
                    'date': page_date,
                    'image_url': pdf_url,
                    'image_data': image,  # PIL Image для OCR
                    'region': 'voe',
                    'page_number': page_num,
                    'source': 'pdf',
                }
                schedules.append(schedule)
        
        logger.info(f"✅ Оброблено {len(schedules)} сторінок графіків VOE")
        return schedules
        
    except Exception as e:
        logger.error(f"❌ Помилка завантаження графіків VOE: {e}")
        return []


def fetch_voe_schedule_page() -> Optional[str]:
    """Завантажує HTML сторінку з графіками VOE"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(VOE_SCHEDULE_PAGE, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
        return response.text
    except Exception as e:
        logger.error(f"❌ Помилка завантаження сторінки VOE: {e}")
        return None


def extract_pdf_urls_from_page(html_content: str) -> List[Dict]:
    """
    Витягує URLs PDF файлів зі сторінки
    
    Returns:
        List[Dict]: [{'url': 'https://...pdf', 'date': date(...)}]
    """
    from bs4 import BeautifulSoup
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        pdf_links = []
        
        # Шукаємо посилання на PDF
        # Приклад: <a href="/sites/default/files/.../gpv.pdf">Завантажити</a>
        links = soup.find_all('a', href=lambda x: x and '.pdf' in x.lower())
        
        for link in links:
            href = link.get('href')
            if not href:
                continue
            
            # Якщо відносний URL - додаємо домен
            if href.startswith('/'):
                href = 'https://www.voe.com.ua' + href
            
            # Витягуємо дату з назви файлу або тексту посилання
            # Приклад: "ГПВ ВОЕ 2025-26 зима"
            link_text = link.get_text(strip=True)
            schedule_date = parse_date_from_filename(href, link_text)
            
            pdf_links.append({
                'url': href,
                'date': schedule_date,
                'title': link_text
            })
        
        logger.info(f"📋 Знайдено {len(pdf_links)} PDF посилань")
        return pdf_links
        
    except Exception as e:
        logger.error(f"❌ Помилка парсингу PDF URLs: {e}")
        return []


def download_pdf(pdf_url: str) -> Optional[bytes]:
    """Завантажує PDF файл"""
    try:
        logger.info(f"⬇️ Завантажуємо PDF: {pdf_url}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(pdf_url, headers=headers, timeout=60)
        response.raise_for_status()
        
        # Перевірка чи це справді PDF
        if not response.content.startswith(b'%PDF'):
            logger.error("❌ Завантажений файл не є PDF")
            return None
        
        logger.info(f"✅ PDF завантажено: {len(response.content) / 1024:.1f} KB")
        return response.content
        
    except Exception as e:
        logger.error(f"❌ Помилка завантаження PDF: {e}")
        return None


def convert_pdf_to_images(pdf_data: bytes) -> List:
    """
    Конвертує PDF в список зображень (по одному на сторінку)
    
    Returns:
        List[PIL.Image]: Список зображень
    """
    try:
        from pdf2image import convert_from_bytes
        
        logger.info("🖼️ Конвертуємо PDF → зображення...")
        
        # Конвертуємо PDF в зображення
        # dpi=300 для високої якості OCR
        images = convert_from_bytes(
            pdf_data,
            dpi=300,
            fmt='png'
        )
        
        logger.info(f"✅ Створено {len(images)} зображень")
        return images
        
    except ImportError:
        logger.error("❌ pdf2image не встановлено: pip install pdf2image")
        logger.error("❌ Також потрібен poppler: brew install poppler (macOS)")
        return []
    except Exception as e:
        logger.error(f"❌ Помилка конвертації PDF: {e}")
        return []


def parse_voe_schedule_with_ocr(image_data) -> Dict:
    """
    Парсить графік з зображення використовуючи OCR
    
    Використовує існуючий schedule_ocr_parser.py
    """
    try:
        from app.scraper.schedule_ocr_parser import parse_schedule_with_ocr
        
        # Використовуємо існуючий OCR парсер
        # Він вже підтримує розпізнавання графіків
        parsed_data = parse_schedule_with_ocr(image_data)
        
        return parsed_data
        
    except Exception as e:
        logger.error(f"❌ Помилка OCR парсингу VOE: {e}")
        return {}


def parse_date_from_filename(url: str, text: str = "") -> date:
    """
    Витягує дату з назви файлу або тексту
    
    Приклад:
    - "gpv-voe-2025-26-zima" → поточна зима
    - "15.01.2026" → 15 січня 2026
    """
    import re
    
    # Спробувати знайти дату в форматі DD.MM.YYYY
    date_pattern = r'(\d{2})\.(\d{2})\.(\d{4})'
    match = re.search(date_pattern, url + " " + text)
    if match:
        day, month, year = map(int, match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            pass
    
    # Якщо не знайдено - повертаємо сьогодні
    return date.today()


def save_voe_schedule_to_db(db, schedule_data: Dict, parsed_data: Dict):
    """
    Зберігає графік VOE в БД
    
    Args:
        db: SQLAlchemy session
        schedule_data: Дані про графік (дата, URL, тощо)
        parsed_data: Розпарсені дані з OCR
    """
    from app.models import Schedule
    import json
    
    try:
        schedule_date = schedule_data['date']
        
        # Перевірка чи вже є графік на цю дату
        existing = db.query(Schedule).filter(
            Schedule.date == schedule_date,
            Schedule.region == 'voe'
        ).first()
        
        # Обчислюємо хеш для перевірки змін
        content_hash = hashlib.md5(
            json.dumps(parsed_data, sort_keys=True).encode()
        ).hexdigest()
        
        if existing:
            # Якщо хеш не змінився - не оновлюємо
            if existing.content_hash == content_hash:
                logger.info(f"ℹ️ VOE графік {schedule_date} не змінився")
                return False
            
            # Оновлюємо
            existing.image_url = schedule_data['image_url']
            existing.parsed_data = json.dumps(parsed_data)
            existing.content_hash = content_hash
            logger.info(f"✏️ Оновлено VOE графік {schedule_date}")
        else:
            # Створюємо новий
            schedule = Schedule(
                date=schedule_date,
                image_url=schedule_data['image_url'],
                parsed_data=json.dumps(parsed_data),
                content_hash=content_hash,
                region='voe',  # ⭐ ВАЖЛИВО
                is_active=True
            )
            db.add(schedule)
            logger.info(f"✨ Додано новий VOE графік {schedule_date}")
        
        db.commit()
        return True
        
    except Exception as e:
        logger.error(f"❌ Помилка збереження VOE графіка: {e}")
        db.rollback()
        return False


# ============= Інтеграція з scheduler =============

def update_voe_schedules():
    """
    Основна функція для оновлення графіків VOE
    Викликається зі scheduler.py
    """
    from app.database import SessionLocal
    
    db = SessionLocal()
    try:
        logger.info("🔄 Оновлення графіків VOE...")
        
        # 1. Завантажуємо PDF → зображення
        schedules = fetch_voe_schedule_images()
        
        if not schedules:
            logger.warning("⚠️ Не знайдено графіків VOE")
            return
        
        # 2. Парсимо кожне зображення через OCR
        for schedule_data in schedules:
            image_data = schedule_data.get('image_data')
            if not image_data:
                continue
            
            parsed_data = parse_voe_schedule_with_ocr(image_data)
            
            if not parsed_data:
                logger.warning(f"⚠️ Не вдалося розпарсити VOE графік {schedule_data['date']}")
                continue
            
            # 3. Зберігаємо в БД
            save_voe_schedule_to_db(db, schedule_data, parsed_data)
        
        logger.info("✅ Оновлення VOE графіків завершено")
        
    except Exception as e:
        logger.error(f"❌ Помилка оновлення VOE графіків: {e}")
    finally:
        db.close()


# ============= Тестування =============

def test_voe_schedule_parser():
    """Тестова функція"""
    logger.info("🧪 Тестуємо VOE schedule parser...")
    
    # Тест 1: Завантаження сторінки
    page_content = fetch_voe_schedule_page()
    if page_content:
        logger.info("✅ Сторінка VOE завантажена")
    else:
        logger.error("❌ Не вдалося завантажити сторінку")
        return
    
    # Тест 2: Пошук PDF
    pdf_urls = extract_pdf_urls_from_page(page_content)
    logger.info(f"📋 Знайдено PDF: {len(pdf_urls)}")
    for pdf in pdf_urls:
        logger.info(f"   - {pdf['url']}")
    
    # Тест 3: Завантаження PDF
    if pdf_urls:
        pdf_data = download_pdf(pdf_urls[0]['url'])
        if pdf_data:
            logger.info(f"✅ PDF завантажено: {len(pdf_data)} байт")
            
            # Тест 4: Конвертація в зображення
            images = convert_pdf_to_images(pdf_data)
            logger.info(f"✅ Створено {len(images)} зображень")
            
            if images:
                logger.info("✅ Всі тести пройдені!")
        else:
            logger.error("❌ Не вдалося завантажити PDF")
    
    logger.info("🏁 Тестування завершено")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_voe_schedule_parser()
