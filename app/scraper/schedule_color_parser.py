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
    
    Графіки HOE мають 3 типи клітинок:
    - Сині (відключення): B - R > 38
    - Сірі (можливо відключення): B - R близько 0, але темніші (B,G,R < 230)
    - Білі (світло є): B - R близько 0, світлі (B,G,R >= 230)
    
    Args:
        cell_img: numpy array клітинки в BGR форматі
        
    Returns:
        'blue' для відключення, 'gray' для можливого відключення, 'white' для світла
    """
    if cell_img.size == 0:
        return 'white'
    
    # Обчислюємо середні значення BGR каналів
    avg_bgr = np.mean(cell_img, axis=(0, 1))
    b, g, r = avg_bgr
    
    # Головна ознака: різниця між синім і червоним каналом
    b_r_diff = b - r
    
    # Калібровано на реальних зображеннях HOE
    if b_r_diff > 38:
        return 'blue'  # Відключення (синя)
    
    # Якщо колір темніший - сіра клітинка (можливо відключення)
    if b < 230 and g < 230 and r < 230:
        return 'gray'  # Можливо відключення (сіра)
    
    return 'white'  # Світло є (біла)


def parse_schedule_table(image: np.ndarray) -> Dict[str, Dict[str, List[Tuple[int, int]]]]:
    """
    Парсить таблицю графіка відключень
    
    Структура таблиці:
    - Кожна клітинка = 1 година (перша клітинка = 00:00-01:00, друга = 01:00-02:00)
    - Сині клітинки = точне відключення
    - Сірі клітинки = можливе відключення (світло можливо не буде)
    - Білі клітинки = світло буде
    
    Returns:
        {
            '1.1': {
                'outages': [(0, 3), (10, 12)],  # Сині - точні відключення
                'possible': [(5, 8)]             # Сірі - можливі відключення
            },
            ...
        }
    """
    height, width = image.shape[:2]
    
    # Точні координати таблиці
    X_LEFT = 162
    X_RIGHT = 1547
    
    # Точні Y координати рядків (виявлено автоматично по межах)
    ROW_COORDS = [
        (319, 365),   # 1.1
        (371, 418),   # 1.2
        (424, 470),   # 2.1
        (476, 523),   # 2.2
        (529, 576),   # 3.1
        (582, 628),   # 3.2
        (634, 681),   # 4.1
        (687, 733),   # 4.2
        (739, 786),   # 5.1
        (792, 839),   # 5.2
        (845, 891),   # 6.1
        (897, 943),   # 6.2
    ]
    
    logger.info(f"📐 Розміри зображення: {width}x{height}")
    logger.info(f"📐 Таблиця: X={X_LEFT}-{X_RIGHT}")
    
    # Підчерги в порядку зверху вниз
    SUBQUEUES = ['1.1', '1.2', '2.1', '2.2', '3.1', '3.2', 
                 '4.1', '4.2', '5.1', '5.2', '6.1', '6.2']
    
    # Обчислюємо ширину стовпця
    table_width = X_RIGHT - X_LEFT
    col_width = table_width / 24
    
    logger.info(f"📐 Ширина стовпця: {col_width:.2f}px")
    
    schedule_data = {}
    
    # Проходимось по кожній підчерзі
    for idx, subqueue in enumerate(SUBQUEUES):
        row_y_start, row_y_end = ROW_COORDS[idx]
        row_height = row_y_end - row_y_start
        
        # Окремо зберігаємо сині та сірі періоди
        blue_periods = []  # Точні відключення
        gray_periods = []  # Можливі відключення
        
        blue_start = None
        gray_start = None
        
        # Проходимось по 24 годинах
        for hour in range(24):
            col_x_start = int(X_LEFT + hour * col_width)
            
            # Вирізаємо клітинку (беремо центральні 60%)
            cell_y1 = int(row_y_start + row_height * 0.2)
            cell_y2 = int(row_y_start + row_height * 0.8)
            cell_x1 = int(col_x_start + col_width * 0.1)
            cell_x2 = int(col_x_start + col_width * 0.9)
            
            # Захист від виходу за межі
            cell_y1 = max(0, min(height, cell_y1))
            cell_y2 = max(0, min(height, cell_y2))
            cell_x1 = max(0, min(width, cell_x1))
            cell_x2 = max(0, min(width, cell_x2))
            
            cell = image[cell_y1:cell_y2, cell_x1:cell_x2]
            
            if cell.size == 0:
                continue
            
            color = detect_cell_color(cell)
            
            # Обробка синіх клітинок (точні відключення)
            if color == 'blue':
                if blue_start is None:
                    blue_start = hour
                # Закриваємо сірий період якщо був
                if gray_start is not None:
                    gray_periods.append((gray_start, hour))
                    gray_start = None
            # Обробка сірих клітинок (можливі відключення)
            elif color == 'gray':
                if gray_start is None:
                    gray_start = hour
                # Закриваємо синій період якщо був
                if blue_start is not None:
                    blue_periods.append((blue_start, hour))
                    blue_start = None
            # Обробка білих клітинок (світло є)
            else:
                # Закриваємо всі відкриті періоди
                if blue_start is not None:
                    blue_periods.append((blue_start, hour))
                    blue_start = None
                if gray_start is not None:
                    gray_periods.append((gray_start, hour))
                    gray_start = None
        
        # Якщо періоди тривають до кінця доби
        if blue_start is not None:
            blue_periods.append((blue_start, 24))
        if gray_start is not None:
            gray_periods.append((gray_start, 24))
        
        schedule_data[subqueue] = {
            'outages': blue_periods,
            'possible': gray_periods
        }
        
        if blue_periods or gray_periods:
            logger.info(f"✓ Підчерга {subqueue}: відключення {blue_periods}, можливі {gray_periods}")
        else:
            logger.info(f"✓ Підчерга {subqueue}: немає відключень")
    
    return schedule_data


def parse_schedule_from_image(image_url: str) -> Dict[str, Dict[str, List[Tuple[int, int]]]]:
    """
    Головна функція парсингу графіка з картинки
    
    Args:
        image_url: URL зображення графіка
        
    Returns:
        Словник {підчерга: {'outages': [...], 'possible': [...]}}
        Наприклад: {
            '1.1': {
                'outages': [(0, 3), (10, 12)],  # Точні відключення (сині)
                'possible': [(5, 8)]             # Можливі відключення (сірі)
            }
        }
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
