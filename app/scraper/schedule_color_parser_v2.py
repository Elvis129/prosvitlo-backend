"""
Парсер графіків відключень на основі кольорів клітинок таблиці (версія 2 - BGR детектор)
Розпізнає: білий (світло є), синій (відключення)
Використовує різницю між B та R каналами для надійного розпізнавання
"""

import requests
import cv2
import numpy as np
from PIL import Image
from io import BytesIO
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


# Межі таблиці (відсотки від розмірів зображення) - калібровано для HOE
TABLE_TOP_PERCENT = 0.15    # 15% від верху
TABLE_LEFT_PERCENT = 0.10   # 10% від лівого краю  
TABLE_RIGHT_PERCENT = 0.85  # 85% ширини
TABLE_BOTTOM_PERCENT = 0.85 # 85% висоти


def download_schedule_image(url: str) -> Optional[np.ndarray]:
    """Завантажує зображення графіка з URL"""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        # Конвертуємо в numpy array через PIL
        image = Image.open(BytesIO(response.content))
        img_array = np.array(image.convert('RGB'))
        
        # Конвертуємо RGB в BGR для OpenCV
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        
        logger.info(f"✓ Завантажено зображення: {img_bgr.shape}")
        return img_bgr
        
    except Exception as e:
        logger.error(f"Помилка завантаження зображення {url}: {e}")
        return None


def detect_cell_color(cell_img: np.ndarray) -> str:
    """
    Визначає колір клітинки таблиці на основі BGR каналів
    
    Графіки HOE мають низький контраст, але надійна ознака:
    - Відключення (візуально сині/сірі): B помітно більше за R (B - R > 50)
    - Світло (візуально білі): всі канали близькі (B - R <= 50)
    
    Args:
        cell_img: numpy array клітинки в BGR форматі
        
    Returns:
        'blue' для відключення, 'white' для наявності світла
    """
    if cell_img.size == 0:
        return 'white'
    
    # Обчислюємо середні значення BGR каналів
    avg_bgr = np.mean(cell_img, axis=(0, 1))
    b, g, r = avg_bgr
    
    # Головна ознака: різниця між синім і червоним каналом
    b_r_diff = b - r
    
    # Калібровано на реальних зображеннях HOE
    # Відключення: B - R зазвичай 60-80
    # Світло: B - R близько 0 (всі канали рівні)
    if b_r_diff > 50:
        return 'blue'  # Відключення
    
    return 'white'  # Світло є


def parse_schedule_table(image: np.ndarray) -> Dict[str, List[Tuple[int, int]]]:
    """
    Парсить таблицю графіка відключень
    
    Структура таблиці:
    - Рядок 0: заголовки (00:00-01:00, 01:00-02:00, ... 23:00-24:00)
    - Рядки 1-12: підчерги (1.1, 1.2, 2.1, 2.2, ..., 6.2)
    - Стовпці 0-1: Черга | Підчерга
    - Стовпці 2-25: Години (24 стовпці)
    
    Returns:
        {'1.1': [(0, 3), (10, 12)], '1.2': [(5, 8)], ...}
    """
    height, width = image.shape[:2]
    
    # Калібровані координати таблиці
    TABLE_TOP = int(height * TABLE_TOP_PERCENT)
    TABLE_LEFT = int(width * TABLE_LEFT_PERCENT)
    TABLE_RIGHT = int(width * TABLE_RIGHT_PERCENT)
    TABLE_BOTTOM = int(height * TABLE_BOTTOM_PERCENT)
    
    logger.info(f"📐 Розміри зображення: {width}x{height}")
    logger.info(f"📐 Таблиця: TOP={TABLE_TOP}, LEFT={TABLE_LEFT}, RIGHT={TABLE_RIGHT}, BOTTOM={TABLE_BOTTOM}")
    
    # Підчерги в порядку зверху вниз
    SUBQUEUES = ['1.1', '1.2', '2.1', '2.2', '3.1', '3.2', 
                 '4.1', '4.2', '5.1', '5.2', '6.1', '6.2']
    
    # Вирізаємо область таблиці
    table_img = image[TABLE_TOP:TABLE_BOTTOM, TABLE_LEFT:TABLE_RIGHT]
    table_height, table_width = table_img.shape[:2]
    
    logger.info(f"📐 Розмір таблиці: {table_width}x{table_height}")
    
    # Розміри клітинок
    row_height = table_height // (len(SUBQUEUES) + 1)  # +1 для заголовка
    col_width = (table_width - int(table_width * 0.1)) // 24  # 24 години, -10% для стовпців з чергами
    
    # Зсув для пропуску перших двох стовпців (Черга | Підчерга)
    hours_start_x = int(table_width * 0.1)
    
    logger.info(f"📐 Розмір клітинки: {col_width}x{row_height}")
    
    schedule_data = {}
    
    # Проходимось по кожній підчерзі
    for idx, subqueue in enumerate(SUBQUEUES):
        row_y = row_height * (idx + 1)  # +1 бо перший рядок - заголовок
        
        outage_periods = []
        outage_start = None
        
        # Проходимось по 24 годинах
        for hour in range(24):
            col_x = hours_start_x + (col_width * hour)
            
            # Вирізаємо клітинку (беремо центральні 60% щоб уникнути меж)
            cell_y1 = row_y + int(row_height * 0.2)
            cell_y2 = row_y + int(row_height * 0.8)
            cell_x1 = col_x + int(col_width * 0.2)
            cell_x2 = col_x + int(col_width * 0.8)
            
            # Захист від виходу за межі
            cell_y1 = max(0, cell_y1)
            cell_y2 = min(table_height, cell_y2)
            cell_x1 = max(0, cell_x1)
            cell_x2 = min(table_width, cell_x2)
            
            cell = table_img[cell_y1:cell_y2, cell_x1:cell_x2]
            
            if cell.size == 0:
                continue
            
            color = detect_cell_color(cell)
            
            # Синя = відключення
            if color == 'blue':
                if outage_start is None:
                    outage_start = hour
            else:
                # Біла = світло є
                if outage_start is not None:
                    # Закриваємо період відключення
                    outage_periods.append((outage_start, hour))
                    outage_start = None
        
        # Якщо відключення триває до кінця доби
        if outage_start is not None:
            outage_periods.append((outage_start, 24))
        
        if outage_periods:
            schedule_data[subqueue] = outage_periods
            logger.info(f"✓ Підчерга {subqueue}: {outage_periods}")
        else:
            # Додаємо пусту підчергу для повноти даних
            schedule_data[subqueue] = []
            logger.info(f"✓ Підчерга {subqueue}: немає відключень")
    
    return schedule_data


def parse_schedule_from_image(image_url: str) -> Dict[str, List[Tuple[int, int]]]:
    """
    Головна функція парсингу графіка з картинки
    
    Args:
        image_url: URL зображення графіка
        
    Returns:
        Словник {підчерга: [(година_початку, година_кінця), ...]}
        Наприклад: {'1.1': [(0, 3), (10, 12)], '2.1': [(5, 8)]}
    """
    logger.info(f"🔍 Початок парсингу графіка: {image_url}")
    
    # Завантажуємо зображення
    image = download_schedule_image(image_url)
    if image is None:
        logger.error("❌ Не вдалося завантажити зображення")
        return {}
    
    # Парсимо таблицю
    try:
        schedule_data = parse_schedule_table(image)
        logger.info(f"✅ Успішно розпізнано графік: {len(schedule_data)} підчерг")
        return schedule_data
    except Exception as e:
        logger.error(f"❌ Помилка парсингу таблиці: {e}")
        logger.exception("Детальна інформація:")
        return {}


# Для тестування
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    test_url = "https://hoe.com.ua/Content/Uploads/2026/01/file20260125201810041.png"
    result = parse_schedule_from_image(test_url)
    
    print("\n" + "=" * 60)
    print("РЕЗУЛЬТАТ ПАРСИНГУ:")
    print("=" * 60)
    for subqueue, periods in sorted(result.items()):
        print(f"\nПідчерга {subqueue}:")
        if periods:
            for start, end in periods:
                print(f"  {start:02d}:00 - {end:02d}:00")
        else:
            print(f"  Немає відключень")
