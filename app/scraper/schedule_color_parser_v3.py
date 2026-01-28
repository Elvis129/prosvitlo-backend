"""
Адаптивний BGR-детектор що враховує різні колірні профілі для кожного рядка
Версія 3 - навчається на першій та останній клітинці кожного рядка
"""

import sys
sys.path.append('/Users/user/my_pet_project/prosvitlo-backend')

import requests
import cv2
import numpy as np
from PIL import Image
from io import BytesIO
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


# Межі таблиці (відсотки від розмірів зображення)
TABLE_TOP_PERCENT = 0.15
TABLE_LEFT_PERCENT = 0.10
TABLE_RIGHT_PERCENT = 0.85
TABLE_BOTTOM_PERCENT = 0.85


def download_schedule_image(url: str) -> Optional[np.ndarray]:
    """Завантажує зображення графіка з URL"""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        image = Image.open(BytesIO(response.content))
        img_array = np.array(image.convert('RGB'))
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        
        logger.info(f"✓ Завантажено зображення: {img_bgr.shape}")
        return img_bgr
        
    except Exception as e:
        logger.error(f"Помилка завантаження зображення {url}: {e}")
        return None


def detect_row_threshold(row_cells: List[np.ndarray]) -> Tuple[float, str]:
    """
    Визначає оптимальний поріг для конкретного рядка
    
    Args:
        row_cells: Список всіх 24 клітинок рядка
        
    Returns:
        (threshold, method) - поріг та метод детектування
    """
    if not row_cells:
        return 50.0, 'b_r_diff'
    
    # Обчислюємо BGR характеристики для всіх клітинок
    cell_features = []
    for cell in row_cells:
        if cell.size == 0:
            continue
        avg_bgr = np.mean(cell, axis=(0, 1))
        b, g, r = avg_bgr
        cell_features.append({
            'b': b,
            'g': g,
            'r': r,
            'b_r': b - r,
            'brightness': np.mean(avg_bgr)
        })
    
    if len(cell_features) < 2:
        return 50.0, 'b_r_diff'
    
    # Аналізуємо розкид значень B-R
    b_r_values = [f['b_r'] for f in cell_features]
    b_r_std = np.std(b_r_values)
    b_r_range = max(b_r_values) - min(b_r_values)
    
    # Аналізуємо яскравість
    brightness_values = [f['brightness'] for f in cell_features]
    brightness_std = np.std(brightness_values)
    brightness_range = max(brightness_values) - min(brightness_values)
    
    logger.info(f"   B-R: діапазон={b_r_range:.1f}, std={b_r_std:.1f}")
    logger.info(f"   Яскравість: діапазон={brightness_range:.1f}, std={brightness_std:.1f}")
    
    # Вибираємо метод в залежності від того, що більше варіюється
    if b_r_range > 15 and b_r_std > 5:
        # Використовуємо B-R різницю (кольоровий рядок)
        # Поріг = середина між мін і макс
        threshold = (max(b_r_values) + min(b_r_values)) / 2
        # Але не менше 10 (щоб уникнути шуму)
        threshold = max(10.0, threshold)
        logger.info(f"   → Використовуємо B-R з порогом {threshold:.1f}")
        return threshold, 'b_r_diff'
    elif brightness_range > 20:
        # Використовуємо яскравість (сірий рядок)
        threshold = (max(brightness_values) + min(brightness_values)) / 2
        logger.info(f"   → Використовуємо яскравість з порогом {threshold:.1f}")
        return threshold, 'brightness'
    else:
        # Рядок має однорідний колір - можливо помилка або немає відключень
        logger.info(f"   → Рядок однорідний, використовуємо дефолтний B-R")
        return 50.0, 'b_r_diff'


def detect_cell_color(cell_img: np.ndarray, threshold: float, method: str) -> str:
    """
    Визначає колір клітинки на основі методу та порогу
    
    Args:
        cell_img: numpy array клітинки в BGR форматі
        threshold: Пороговезначення
        method: 'b_r_diff' або 'brightness'
        
    Returns:
        'blue' для відключення, 'white' для світла
    """
    if cell_img.size == 0:
        return 'white'
    
    avg_bgr = np.mean(cell_img, axis=(0, 1))
    b, g, r = avg_bgr
    
    if method == 'brightness':
        brightness = np.mean(avg_bgr)
        # Для яскравості: темніше = відключення
        return 'blue' if brightness < threshold else 'white'
    else:  # b_r_diff
        b_r_diff = b - r
        return 'blue' if b_r_diff > threshold else 'white'


def parse_schedule_table(image: np.ndarray) -> Dict[str, List[Tuple[int, int]]]:
    """Парсить таблицю графіка з адаптивним визначенням порогів для кожного рядка"""
    height, width = image.shape[:2]
    
    TABLE_TOP = int(height * TABLE_TOP_PERCENT)
    TABLE_LEFT = int(width * TABLE_LEFT_PERCENT)
    TABLE_RIGHT = int(width * TABLE_RIGHT_PERCENT)
    TABLE_BOTTOM = int(height * TABLE_BOTTOM_PERCENT)
    
    SUBQUEUES = ['1.1', '1.2', '2.1', '2.2', '3.1', '3.2', 
                 '4.1', '4.2', '5.1', '5.2', '6.1', '6.2']
    
    table_img = image[TABLE_TOP:TABLE_BOTTOM, TABLE_LEFT:TABLE_RIGHT]
    table_height, table_width = table_img.shape[:2]
    
    row_height = table_height // (len(SUBQUEUES) + 1)
    col_width = (table_width - int(table_width * 0.1)) // 24
    hours_start_x = int(table_width * 0.1)
    
    schedule_data = {}
    
    # Проходимось по кожній підчерзі
    for idx, subqueue in enumerate(SUBQUEUES):
        logger.info(f"\n🔍 Аналізуємо підчергу {subqueue}")
        row_y = row_height * (idx + 1)
        
        # КРОК 1: Збираємо всі клітинки рядка
        row_cells = []
        for hour in range(24):
            col_x = hours_start_x + (col_width * hour)
            
            cell_y1 = row_y + int(row_height * 0.2)
            cell_y2 = row_y + int(row_height * 0.8)
            cell_x1 = col_x + int(col_width * 0.2)
            cell_x2 = col_x + int(col_width * 0.8)
            
            cell_y1 = max(0, cell_y1)
            cell_y2 = min(table_height, cell_y2)
            cell_x1 = max(0, cell_x1)
            cell_x2 = min(table_width, cell_x2)
            
            cell = table_img[cell_y1:cell_y2, cell_x1:cell_x2]
            row_cells.append(cell)
        
        # КРОК 2: Визначаємо адаптивний поріг для цього рядка
        threshold, method = detect_row_threshold(row_cells)
        
        # КРОК 3: Детектуємо відключення з цим порогом
        outage_periods = []
        outage_start = None
        
        for hour, cell in enumerate(row_cells):
            if cell.size == 0:
                continue
            
            color = detect_cell_color(cell, threshold, method)
            
            if color == 'blue':
                if outage_start is None:
                    outage_start = hour
            else:
                if outage_start is not None:
                    outage_periods.append((outage_start, hour))
                    outage_start = None
        
        if outage_start is not None:
            outage_periods.append((outage_start, 24))
        
        schedule_data[subqueue] = outage_periods
        if outage_periods:
            logger.info(f"✓ Підчерга {subqueue}: {outage_periods}")
        else:
            logger.info(f"✓ Підчерга {subqueue}: немає відключень")
    
    return schedule_data


def parse_schedule_from_image(image_url: str) -> Dict[str, List[Tuple[int, int]]]:
    """Головна функція парсингу графіка з картинки"""
    logger.info(f"🔍 Початок парсингу графіка: {image_url}")
    
    image = download_schedule_image(image_url)
    if image is None:
        logger.error("❌ Не вдалося завантажити зображення")
        return {}
    
    try:
        schedule_data = parse_schedule_table(image)
        logger.info(f"✅ Успішно розпізнано графік: {len(schedule_data)} підчерг")
        return schedule_data
    except Exception as e:
        logger.error(f"❌ Помилка парсингу таблиці: {e}")
        logger.exception("Детальна інформація:")
        return {}


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
