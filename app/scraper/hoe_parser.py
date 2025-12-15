"""
Модуль для парсингу даних про відключення електроенергії з сайту hoe.com.ua
Використовує Excel парсер для завантаження даних з файлів
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import logging
from datetime import datetime

# Імпортуємо Excel парсер
from app.scraper.excel_parser import scrape_all_addresses

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# URL сайту для парсингу
HOE_URL = "https://hoe.com.ua/page/pogodinni-vidkljuchennja"


def fetch_page_content(url: str = HOE_URL, timeout: int = 30) -> Optional[str]:
    """
    Завантаження HTML контенту з сайту
    
    Args:
        url: URL сайту для парсингу
        timeout: Таймаут запиту в секундах
    
    Returns:
        HTML контент або None при помилці
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        response.encoding = 'utf-8'
        logger.info(f"Успішно завантажено сторінку: {url}")
        return response.text
    except requests.RequestException as e:
        logger.error(f"Помилка при завантаженні сторінки {url}: {e}")
        return None


def parse_outage_table(html_content: str) -> List[Dict[str, str]]:
    """
    Парсинг HTML контенту для витягування інформації про відключення
    
    Args:
        html_content: HTML контент сторінки
    
    Returns:
        Список словників з інформацією про відключення
    """
    if not html_content:
        return []
    
    soup = BeautifulSoup(html_content, 'lxml')
    outages_data = []
    
    # Шукаємо таблиці на сторінці
    tables = soup.find_all('table')
    
    for table in tables:
        rows = table.find_all('tr')
        
        for row in rows[1:]:  # Пропускаємо заголовок
            cells = row.find_all(['td', 'th'])
            
            if len(cells) >= 4:  # Перевіряємо, що є достатньо стовпців
                try:
                    # Витягуємо дані з клітинок (структура може відрізнятися)
                    city = cells[0].get_text(strip=True) if len(cells) > 0 else ""
                    street = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                    house_number = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                    queue = cells[3].get_text(strip=True) if len(cells) > 3 else ""
                    
                    # Опціонально: зона або час
                    zone = cells[4].get_text(strip=True) if len(cells) > 4 else None
                    schedule_time = cells[5].get_text(strip=True) if len(cells) > 5 else None
                    
                    # Перевіряємо, що є мінімальні дані
                    if city and street and house_number:
                        outage = {
                            "city": city,
                            "street": street,
                            "house_number": house_number,
                            "queue": queue or None,
                            "zone": zone,
                            "schedule_time": schedule_time,
                            "source_url": HOE_URL
                        }
                        outages_data.append(outage)
                        
                except Exception as e:
                    logger.warning(f"Помилка при парсингу рядка: {e}")
                    continue
    
    logger.info(f"Знайдено {len(outages_data)} записів про відключення")
    return outages_data


def normalize_outage_data(outages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Нормалізація даних: видалення дублікатів, очищення від зайвих пробілів
    
    Args:
        outages: Список відключень
    
    Returns:
        Нормалізований список відключень
    """
    # Видаляємо зайві пробіли
    for outage in outages:
        for key, value in outage.items():
            if isinstance(value, str):
                outage[key] = ' '.join(value.split())
    
    # Видаляємо дублікати на основі унікальної адреси
    unique_outages = {}
    for outage in outages:
        key = (outage['city'], outage['street'], outage['house_number'])
        if key not in unique_outages:
            unique_outages[key] = outage
    
    result = list(unique_outages.values())
    logger.info(f"Після нормалізації: {len(result)} унікальних записів")
    return result


def scrape_outages() -> List[Dict[str, str]]:
    """
    Головна функція для скрейпінгу даних про відключення
    Тепер використовує Excel парсер для отримання реальних даних
    
    Returns:
        Список нормалізованих даних про відключення
    """
    logger.info("Початок парсингу даних про відключення з Excel файлів...")
    
    try:
        # Використовуємо новий Excel парсер
        addresses = scrape_all_addresses()
        
        if not addresses:
            logger.warning("Не отримано даних з Excel файлів")
            return []
        
        # Конвертуємо в формат який очікує база даних
        outages = []
        for addr in addresses:
            outage = {
                "city": addr.get("city", ""),
                "street": addr.get("street", ""),
                "house_number": addr.get("house_number", ""),
                "queue": addr.get("queue"),
                "zone": None,  # В Excel файлах немає зони
                "schedule_time": None,  # Графік окремо
                "source_url": addr.get("source_url", "")
            }
            outages.append(outage)
        
        logger.info(f"Парсинг завершено. Отримано {len(outages)} записів")
        return outages
        
    except Exception as e:
        logger.error(f"Помилка при парсингу: {e}")
        return []


# Для тестування
if __name__ == "__main__":
    outages = scrape_outages()
    for i, outage in enumerate(outages[:5], 1):  # Виводимо перші 5
        print(f"\n{i}. {outage}")
