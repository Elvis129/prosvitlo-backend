"""
Модуль для розпізнавання графіків відключень з зображень за допомогою OCR
"""

import requests
from PIL import Image
import pytesseract
import cv2
import numpy as np
from typing import List, Dict, Optional
import logging
from datetime import datetime, timedelta
import re
from io import BytesIO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def download_image(url: str) -> Optional[Image.Image]:
    """Завантаження зображення з URL"""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return Image.open(BytesIO(response.content))
    except Exception as e:
        logger.error(f"Помилка завантаження зображення {url}: {e}")
        return None


def preprocess_image(image: Image.Image) -> np.ndarray:
    """Попередня обробка зображення для кращого розпізнавання"""
    # Конвертуємо в numpy array
    img_array = np.array(image)
    
    # Конвертуємо в grayscale
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    
    # Збільшуємо контрастність
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    
    # Бінаризація
    _, binary = cv2.threshold(enhanced, 150, 255, cv2.THRESH_BINARY)
    
    return binary


def extract_schedule_from_image(image_url: str) -> Dict:
    """
    Розпізнавання графіка відключень з зображення
    
    Returns:
        Словник з розпізнаною інформацією про графік
    """
    logger.info(f"Розпізнавання графіка: {image_url}")
    
    # Завантажуємо зображення
    image = download_image(image_url)
    if not image:
        return {"error": "Не вдалося завантажити зображення"}
    
    # Обробляємо зображення
    processed = preprocess_image(image)
    
    # Розпізнаємо текст (Ukrainian + English)
    try:
        text = pytesseract.image_to_string(processed, lang='ukr+eng')
        logger.info(f"Розпізнаний текст:\n{text[:200]}...")
    except Exception as e:
        logger.error(f"Помилка OCR: {e}")
        text = ""
    
    # Парсимо текст для витягування інформації про відключення
    schedule_data = parse_schedule_text(text)
    
    return {
        "image_url": image_url,
        "recognized_text": text,
        "schedule_data": schedule_data,
        "processed_at": datetime.now().isoformat()
    }


def parse_schedule_text(text: str) -> List[Dict]:
    """
    Парсинг розпізнаного тексту для витягування графіка
    
    Шукає паттерни типу:
    - Черга 1: 00:00-06:00, 12:00-18:00
    - Підчерга 6.1: 08:00-12:00
    """
    schedules = []
    
    # Паттерн для пошуку черг та часів
    # Приклад: "Черга 1", "6.1", "08:00-12:00", "08:00 - 12:00"
    queue_pattern = r'(?:Черга|черга|Підчерга|підчерга)?\s*(\d+(?:\.\d+)?)'
    time_pattern = r'(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})'
    
    lines = text.split('\n')
    current_queue = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Шукаємо номер черги
        queue_match = re.search(queue_pattern, line)
        if queue_match:
            current_queue = queue_match.group(1)
        
        # Шукаємо часові інтервали
        time_matches = re.findall(time_pattern, line)
        for match in time_matches:
            start_hour, start_min, end_hour, end_min = match
            
            schedule_entry = {
                'queue': current_queue or 'unknown',
                'start_time': f"{start_hour.zfill(2)}:{start_min}",
                'end_time': f"{end_hour.zfill(2)}:{end_min}",
                'is_possible': 'можливо' in line.lower() or 'possible' in line.lower()
            }
            schedules.append(schedule_entry)
            logger.info(f"Знайдено графік: Черга {schedule_entry['queue']}, {schedule_entry['start_time']}-{schedule_entry['end_time']}")
    
    return schedules


def check_current_outage(queue: str, schedules: List[Dict], current_time: datetime = None) -> Dict:
    """
    Перевірка чи є відключення для вказаної черги в даний момент
    
    Args:
        queue: Номер черги (наприклад "6.2")
        schedules: Список графіків отриманих з OCR
        current_time: Поточний час (для тестування)
    
    Returns:
        Інформація про поточний статус відключення
    """
    if current_time is None:
        current_time = datetime.now()
    
    current_hour = current_time.hour
    current_minute = current_time.minute
    current_minutes = current_hour * 60 + current_minute
    
    # Нормалізуємо номер черги
    queue_normalized = queue.replace(' ', '').replace('підчерга', '').replace('.', '.')
    queue_match = re.search(r'(\d+)\.?(\d+)?', queue_normalized)
    if not queue_match:
        return {"status": "unknown", "message": "Некоректний формат черги"}
    
    main_queue = queue_match.group(1)
    sub_queue = queue_match.group(2) if queue_match.group(2) else None
    search_queue = f"{main_queue}.{sub_queue}" if sub_queue else main_queue
    
    # Шукаємо відповідний графік
    active_outages = []
    upcoming_outages = []
    
    for schedule in schedules:
        if schedule['queue'] != search_queue:
            continue
        
        # Парсимо час початку та кінця
        start_parts = schedule['start_time'].split(':')
        end_parts = schedule['end_time'].split(':')
        
        start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])
        end_minutes = int(end_parts[0]) * 60 + int(end_parts[1])
        
        # Перевіряємо чи зараз активне відключення
        if start_minutes <= current_minutes < end_minutes:
            active_outages.append({
                **schedule,
                'ends_in_minutes': end_minutes - current_minutes
            })
        # Перевіряємо майбутні відключення (наступні 24 години)
        elif start_minutes > current_minutes:
            upcoming_outages.append({
                **schedule,
                'starts_in_minutes': start_minutes - current_minutes
            })
    
    if active_outages:
        return {
            "status": "off",
            "message": "Зараз відключення електроенергії",
            "current_outage": active_outages[0],
            "upcoming": upcoming_outages[:3]
        }
    elif upcoming_outages:
        return {
            "status": "on",
            "message": "Електроенергія є",
            "upcoming": upcoming_outages[:3]
        }
    else:
        return {
            "status": "on",
            "message": "Відключень не заплановано",
            "upcoming": []
        }


if __name__ == "__main__":
    # Тестування
    test_url = "https://hoe.com.ua/Content/Uploads/2025/12/file20251204201046288.png"
    result = extract_schedule_from_image(test_url)
    
    print("Розпізнані графіки:")
    for schedule in result.get('schedule_data', []):
        print(f"  Черга {schedule['queue']}: {schedule['start_time']}-{schedule['end_time']}")
    
    if result.get('schedule_data'):
        status = check_current_outage("6.2", result['schedule_data'])
        print(f"\nСтатус для черги 6.2: {status}")
