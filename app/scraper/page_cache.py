"""
Кеш для перевірки чи змінилися сторінки перед парсингом
Зберігає MD5 хеші відповідей щоб не парсити без потреби
"""

import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Глобальний словник для зберігання хешів
_page_hashes = {}


def get_content_hash(content: str) -> str:
    """Генерує MD5 хеш контенту"""
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def has_page_changed(page_key: str, new_content: str) -> bool:
    """
    Перевіряє чи змінився контент сторінки
    
    Args:
        page_key: Унікальний ключ сторінки (наприклад, "outages_rem4_type1")
        new_content: Новий HTML контент
        
    Returns:
        True якщо сторінка змінилася або це перша перевірка
        False якщо сторінка не змінилася
    """
    new_hash = get_content_hash(new_content)
    old_hash = _page_hashes.get(page_key)
    
    if old_hash is None:
        # Перша перевірка - зберігаємо і повертаємо True
        _page_hashes[page_key] = new_hash
        return True
    
    if old_hash == new_hash:
        # Контент не змінився
        logger.info(f"✓ Сторінка '{page_key}' не змінилася, пропускаємо парсинг")
        return False
    
    # Контент змінився - оновлюємо хеш
    _page_hashes[page_key] = new_hash
    logger.info(f"⚠ Сторінка '{page_key}' оновилася, запускаємо парсинг")
    return True


def clear_cache():
    """Очищає весь кеш"""
    global _page_hashes
    _page_hashes = {}
    logger.info("Кеш сторінок очищено")
