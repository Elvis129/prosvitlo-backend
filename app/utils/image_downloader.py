"""
Утиліта для завантаження зображень графіків
"""
import httpx
import hashlib
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent.parent / "static" / "schedules"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


async def download_schedule_image(image_url: str) -> Optional[str]:
    """
    Завантажує зображення графіка та зберігає локально
    
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
            logger.info(f"Image already exists: {filename}")
            return f"/static/schedules/{filename}"
        
        # Завантажуємо зображення
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(image_url, follow_redirects=True)
            response.raise_for_status()
            
            # Зберігаємо файл
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"Downloaded image: {filename} from {image_url}")
            return f"/static/schedules/{filename}"
            
    except Exception as e:
        logger.error(f"Failed to download image from {image_url}: {e}")
        return None


def get_local_image_url(filename: str, base_url: str = "http://localhost:8000") -> str:
    """
    Формує повний URL для локального зображення
    
    Args:
        filename: Ім'я файлу (напр. "/static/schedules/abc123.png")
        base_url: Базова URL бекенду
        
    Returns:
        Повний URL до зображення
    """
    return f"{base_url}{filename}"
