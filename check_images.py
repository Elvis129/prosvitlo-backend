#!/usr/bin/env python3
"""
Утиліта для перевірки та відновлення відсутніх зображень графіків
"""

from app.database import SessionLocal
from app.utils.image_downloader_sync import check_and_redownload_missing_images
from app.models import Schedule
from pathlib import Path
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Головна функція"""
    db = SessionLocal()
    
    try:
        # Визначаємо шлях до статичних файлів
        USE_PERSISTENT_STORAGE = os.getenv('USE_PERSISTENT_STORAGE', 'false').lower() == 'true'
        
        if USE_PERSISTENT_STORAGE:
            static_dir = Path("/data/static/schedules")
        else:
            static_dir = Path(__file__).parent / "app" / "static" / "schedules"
        
        logger.info(f"📁 Директорія зображень: {static_dir}")
        logger.info(f"📊 Існує: {static_dir.exists()}")
        
        if static_dir.exists():
            files = list(static_dir.glob("*"))
            logger.info(f"📂 Файлів в директорії: {len(files)}")
            for f in files:
                logger.info(f"   - {f.name} ({f.stat().st_size} bytes)")
        
        # Отримуємо всі активні графіки з БД
        schedules = db.query(Schedule).filter(Schedule.is_active == True).all()
        logger.info(f"\n📋 Графіків в БД: {len(schedules)}")
        
        for schedule in schedules:
            logger.info(f"   📅 {schedule.date}: {schedule.image_url}")
        
        # Перевіряємо та перезавантажуємо відсутні
        logger.info("\n🔍 Починаємо перевірку відсутніх зображень...")
        redownloaded = check_and_redownload_missing_images(db)
        
        if redownloaded > 0:
            logger.info(f"\n✅ Перезавантажено {redownloaded} зображень")
        else:
            logger.info("\n✅ Всі зображення на місці!")
            
    except Exception as e:
        logger.error(f"❌ Помилка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
