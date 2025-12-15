"""
Модуль для парсингу даних з hoe.com.ua використовуючи Selenium
для роботи з динамічним контентом (JavaScript)
"""

import logging
from typing import List, Dict, Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time

logger = logging.getLogger(__name__)

HOE_URL = "https://hoe.com.ua/page/pogodinni-vidkljuchennja"


def create_headless_browser() -> webdriver.Chrome:
    """
    Створює headless Chrome browser для парсингу
    
    Returns:
        Налаштований WebDriver instance
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")  # Новий headless режим
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Автоматичне завантаження та налаштування ChromeDriver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    return driver


def fetch_dynamic_page_content(url: str = HOE_URL, wait_time: int = 10) -> Optional[str]:
    """
    Завантаження динамічної сторінки з використанням Selenium
    
    Args:
        url: URL сторінки
        wait_time: Час очікування завантаження контенту (секунди)
    
    Returns:
        HTML контент після виконання JavaScript або None при помилці
    """
    driver = None
    try:
        logger.info(f"Запуск браузера для завантаження: {url}")
        driver = create_headless_browser()
        
        # Завантажуємо сторінку
        driver.get(url)
        logger.info("Сторінка завантажена, очікуємо виконання JavaScript...")
        
        # Чекаємо на завантаження контенту
        # Можна налаштувати під конкретні елементи сторінки
        time.sleep(wait_time)  # Базове очікування
        
        # Додаткове очікування конкретних елементів (можна кастомізувати)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception as e:
            logger.warning(f"Очікування елементів не вдалося: {e}")
        
        # Отримуємо повний HTML після виконання JavaScript
        html_content = driver.page_source
        logger.info("HTML контент успішно отримано")
        
        return html_content
        
    except Exception as e:
        logger.error(f"Помилка при завантаженні сторінки: {e}")
        return None
        
    finally:
        if driver:
            driver.quit()
            logger.info("Браузер закрито")


def parse_address_tables(html_content: str) -> List[Dict[str, str]]:
    """
    Парсинг HTML для витягування таблиць відповідності адрес до черг
    
    Args:
        html_content: HTML контент сторінки
    
    Returns:
        Список словників з адресами та їх чергами
    """
    if not html_content:
        return []
    
    soup = BeautifulSoup(html_content, 'html.parser')
    addresses_data = []
    
    logger.info("Початок парсингу таблиць адрес...")
    
    # Шукаємо всі таблиці
    tables = soup.find_all('table')
    logger.info(f"Знайдено таблиць: {len(tables)}")
    
    for table_idx, table in enumerate(tables):
        logger.info(f"Обробка таблиці {table_idx + 1}/{len(tables)}")
        
        rows = table.find_all('tr')
        
        # Спробуємо визначити структуру таблиці з заголовків
        headers = []
        if rows:
            header_row = rows[0]
            headers = [th.get_text(strip=True).lower() for th in header_row.find_all(['th', 'td'])]
            logger.info(f"Заголовки таблиці: {headers}")
        
        # Обробляємо рядки даних
        for row_idx, row in enumerate(rows[1:], 1):  # Пропускаємо заголовок
            cells = row.find_all(['td', 'th'])
            
            if len(cells) < 3:  # Мінімум: місто, вулиця, будинок
                continue
            
            try:
                # Витягуємо дані (структура може варіюватися)
                cell_texts = [cell.get_text(strip=True) for cell in cells]
                
                # Базова структура: місто, вулиця, будинок, черга
                address_data = {
                    "city": cell_texts[0] if len(cell_texts) > 0 else "",
                    "street": cell_texts[1] if len(cell_texts) > 1 else "",
                    "house_number": cell_texts[2] if len(cell_texts) > 2 else "",
                    "queue": cell_texts[3] if len(cell_texts) > 3 else None,
                    "zone": cell_texts[4] if len(cell_texts) > 4 else None,
                }
                
                # Перевіряємо валідність даних
                if address_data["city"] and address_data["street"] and address_data["house_number"]:
                    addresses_data.append(address_data)
                    
            except Exception as e:
                logger.warning(f"Помилка при обробці рядка {row_idx} в таблиці {table_idx}: {e}")
                continue
    
    logger.info(f"Парсинг завершено. Знайдено {len(addresses_data)} адрес")
    return addresses_data


def parse_outage_schedule(html_content: str) -> List[Dict[str, str]]:
    """
    Парсинг графіків відключень (час, дати)
    
    Args:
        html_content: HTML контент сторінки
    
    Returns:
        Список словників з графіками відключень
    """
    if not html_content:
        return []
    
    soup = BeautifulSoup(html_content, 'html.parser')
    schedule_data = []
    
    logger.info("Початок парсингу графіків відключень...")
    
    # Тут буде логіка для парсингу конкретних графіків
    # Структура залежить від сайту
    
    # Приклад: шукаємо елементи з класами, що містять schedule, graph тощо
    schedule_containers = soup.find_all(['div', 'section', 'table'], 
                                       class_=lambda x: x and any(keyword in str(x).lower() 
                                                                 for keyword in ['schedule', 'graph', 'час']))
    
    logger.info(f"Знайдено контейнерів з графіками: {len(schedule_containers)}")
    
    for container in schedule_containers:
        # Витягуємо інформацію про час і черги
        # Це потрібно адаптувати під реальну структуру сайту
        pass
    
    return schedule_data


def scrape_address_queue_data() -> List[Dict[str, str]]:
    """
    Головна функція для скрейпінгу таблиць відповідності адрес до черг
    Використовується рідко - тільки для оновлення статичної таблиці
    
    Returns:
        Список адрес з чергами
    """
    logger.info("Запуск парсингу таблиць адрес з Selenium...")
    
    # Завантажуємо динамічний контент
    html_content = fetch_dynamic_page_content()
    
    if not html_content:
        logger.error("Не вдалося завантажити контент")
        return []
    
    # Парсимо таблиці адрес
    addresses = parse_address_tables(html_content)
    
    # Нормалізуємо дані
    normalized = normalize_address_data(addresses)
    
    logger.info(f"Парсинг завершено. Отримано {len(normalized)} адрес")
    return normalized


def scrape_current_outages() -> List[Dict[str, str]]:
    """
    Парсинг поточних графіків відключень (без таблиць адрес)
    Використовується регулярно для оновлення актуальних графіків
    
    Returns:
        Список поточних відключень
    """
    logger.info("Запуск парсингу поточних графіків...")
    
    html_content = fetch_dynamic_page_content()
    
    if not html_content:
        logger.error("Не вдалося завантажити контент")
        return []
    
    schedules = parse_outage_schedule(html_content)
    
    logger.info(f"Знайдено графіків: {len(schedules)}")
    return schedules


def normalize_address_data(addresses: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Нормалізація даних: видалення дублікатів, очищення
    
    Args:
        addresses: Список адрес
    
    Returns:
        Нормалізований список
    """
    # Очищуємо пробіли
    for addr in addresses:
        for key, value in addr.items():
            if isinstance(value, str):
                addr[key] = ' '.join(value.split())
    
    # Видаляємо дублікати
    unique_addresses = {}
    for addr in addresses:
        key = (addr['city'], addr['street'], addr['house_number'])
        if key not in unique_addresses:
            unique_addresses[key] = addr
    
    result = list(unique_addresses.values())
    logger.info(f"Після нормалізації: {len(result)} унікальних адрес")
    return result


# Для тестування
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=== Тестування парсера з Selenium ===\n")
    
    # Тест 1: Завантаження сторінки
    print("1. Тест завантаження динамічного контенту...")
    html = fetch_dynamic_page_content()
    if html:
        print(f"   ✓ Успішно! Розмір HTML: {len(html)} символів")
        print(f"   Перші 500 символів:\n{html[:500]}\n")
    else:
        print("   ✗ Помилка завантаження\n")
    
    # Тест 2: Парсинг адрес
    print("2. Тест парсингу таблиць адрес...")
    addresses = scrape_address_queue_data()
    print(f"   Знайдено адрес: {len(addresses)}")
    if addresses:
        print(f"   Перші 3 адреси:")
        for i, addr in enumerate(addresses[:3], 1):
            print(f"      {i}. {addr}")
