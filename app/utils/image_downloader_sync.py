"""
Утиліта для завантаження зображень графіків (синхронна версія для scheduler)
"""
import requests
import hashlib
from pathlib import Path
from typing import Optional
import logging
import os

logger = logging.getLogger(__name__)

# Перевіряємо чи є змінна середовища для використання persistent storage
USE_PERSISTENT_STORAGE = os.getenv('USE_PERSISTENT_STORAGE', 'false').lower() == 'true'

if USE_PERSISTENT_STORAGE:
    # В продакшені (Fly.io) використовуємо /data/static
    STATIC_DIR = Path("/data/static/schedules")
else:
    # Локально використовуємо app/static
    STATIC_DIR = Path(__file__).parent.parent / "static" / "schedules"

STATIC_DIR.mkdir(parents=True, exist_ok=True)
logger.info(f"📁 Static directory for images: {STATIC_DIR}")


def download_schedule_image_sync(image_url: str) -> Optional[str]:
    """
    Завантажує файл графіка (зображення або PDF) та зберігає локально (синхронна версія)
    
    Підтримувані формати:
    - Зображення: .png, .jpg, .jpeg, .gif
    - Документи: .pdf
    
    Args:
        image_url: URL файлу для завантаження
        
    Returns:
        Локальний шлях до збереженого файлу (/static/schedules/xxx.ext) або None у разі помилки
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


def check_and_redownload_missing_images(db) -> int:
    """
    Перевіряє чи існують локальні файли для графіків з БД
    Якщо файл відсутній - намагається перезавантажити з оригінального URL
    
    Returns:
        Кількість перезавантажених зображень
    """
    from app.models import Schedule
    from app.config import settings
    import re
    
    redownloaded = 0
    
    try:
        # Отримуємо всі активні графіки
        schedules = db.query(Schedule).filter(Schedule.is_active == True).all()
        
        for schedule in schedules:
            image_url = schedule.image_url
            
            # Перевіряємо чи це локальний URL
            if not image_url or not image_url.startswith(settings.BASE_URL):
                continue
            
            # Витягуємо шлях до файлу
            local_path_match = re.search(r'/static/schedules/(.+)$', image_url)
            if not local_path_match:
                continue
            
            filename = local_path_match.group(1)
            filepath = STATIC_DIR / filename
            
            # Якщо файл не існує - намагаємось його перезавантажити
            if not filepath.exists():
                logger.warning(f"⚠️ Missing image file: {filename} for schedule on {schedule.date}")
                
                # Пробуємо знайти оригінальний URL в альтернативних джерелах
                # Якщо немає - можна спробувати завантажити з hoe.com.ua знову
                from app.scraper.providers.hoe import fetch_schedule_images
                
                fresh_schedules = fetch_schedule_images()
                for fresh_schedule in fresh_schedules:
                    if fresh_schedule.get('date') == schedule.date:
                        original_url = fresh_schedule.get('image_url')
                        logger.info(f"🔄 Attempting to re-download from: {original_url}")
                        
                        new_path = download_schedule_image_sync(original_url)
                        if new_path and new_path != original_url:
                            # Оновлюємо URL в БД
                            if new_path.startswith('/static/'):
                                schedule.image_url = f"{settings.BASE_URL}{new_path}"
                            else:
                                schedule.image_url = new_path
                            db.commit()
                            redownloaded += 1
                            logger.info(f"✅ Successfully re-downloaded image for {schedule.date}")
                        break
        
        if redownloaded > 0:
            logger.info(f"✅ Re-downloaded {redownloaded} missing images")
        
    except Exception as e:
        logger.error(f"❌ Error checking missing images: {e}")
        db.rollback()
    
    return redownloaded
