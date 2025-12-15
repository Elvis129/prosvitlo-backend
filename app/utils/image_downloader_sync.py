"""
Утиліта для завантаження зображень графіків (синхронна версія для scheduler)
"""
import requests
import hashlib
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent.parent / "static" / "schedules"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


def download_schedule_image_sync(image_url: str) -> Optional[str]:
    """
    Завантажує зображення графіка та зберігає локально (синхронна версія)
    
    Args:
        image_url: URL зображення для завантаження
        
    Returns:
        Локальний шлях до збереженого зображення або None у разі помилки
    """
    try:
        # Генеруємо унікальне ім'я файлу на основі URL
        url_hash = hashlib.md5(image_url.encode()).hexdigest()
        file_extension = image_url.split('.')[-1].split('?')[0]  # png, jpg, etc
        filename = f"{url_hash}.{file_extension}"
        filepath = STATIC_DIR / filename
        
        # Якщо файл вже існує, повертаємо його шлях
        if filepath.exists():
            logger.info(f"✅ Image already exists: {filename}")
            return f"/static/schedules/{filename}"
        
        # Завантажуємо зображення
        logger.info(f"📥 Downloading image from {image_url}")
        response = requests.get(image_url, timeout=30, allow_redirects=True)
        response.raise_for_status()
        
        # Зберігаємо файл
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"✅ Downloaded and saved: {filename} ({len(response.content)} bytes)")
        return f"/static/schedules/{filename}"
        
    except Exception as e:
        logger.error(f"❌ Failed to download image from {image_url}: {e}")
        # Повертаємо оригінальний URL якщо не вдалося завантажити
        return image_url
