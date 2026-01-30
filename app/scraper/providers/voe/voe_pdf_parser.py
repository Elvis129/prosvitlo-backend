"""
VOE PDF графік парсер

Парсить PDF файли з чергами для Вінницької області
Формат: текстовий PDF з списком черг та вулиць
"""
import pdfplumber
import re
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


def parse_voe_pdf_schedule(pdf_path: str) -> Dict[str, List[str]]:
    """
    Парсить VOE PDF графік і витягує черги з вулицями
    
    Args:
        pdf_path: Шлях до PDF файлу
    
    Returns:
        Dict: {
            "1.1": ["вул.Батозька 2-14", "вул П.Запорожця 1-4", ...],
            "1.2": [...],
            ...
        }
    """
    try:
        logger.info(f"📄 [VOE] Парсимо PDF графік: {pdf_path}")
        
        queues = {}
        current_queue = None
        current_streets = []
        
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if not text:
                    logger.warning(f"⚠️ [VOE] Сторінка {page_num} порожня")
                    continue
                
                lines = text.strip().split('\n')
                
                for line in lines:
                    line = line.strip()
                    
                    # Пропускаємо заголовки
                    if any(x in line for x in ['Графік погодинного', 'по Вінницькій', 'Назва населених']):
                        continue
                    
                    # Шукаємо номер черги: "1.1", "2.3", etc.
                    queue_match = re.search(r'^(\d+\.\d+)\s', line)
                    if queue_match:
                        # Зберігаємо попередню чергу
                        if current_queue and current_streets:
                            queues[current_queue] = current_streets
                        
                        # Нова черга
                        current_queue = queue_match.group(1)
                        current_streets = []
                        
                        # Витягуємо вулиці з того самого рядка після номера черги
                        streets_part = line[len(queue_match.group(0)):].strip()
                        if streets_part:
                            current_streets.append(streets_part)
                        
                        logger.debug(f"🔹 [VOE] Знайдено чергу: {current_queue}")
                        continue
                    
                    # Якщо рядок починається з цифри без крапки - це теж може бути черга
                    queue_simple_match = re.match(r'^(\d+)\s+(\d+)\s+черга', line)
                    if queue_simple_match:
                        # Формат: "1 1 черга" -> "1.1"
                        num1 = queue_simple_match.group(1)
                        num2 = queue_simple_match.group(2)
                        
                        if current_queue and current_streets:
                            queues[current_queue] = current_streets
                        
                        current_queue = f"{num1}.{num2}"
                        current_streets = []
                        
                        # Вулиці після "черга"
                        streets_part = line[queue_simple_match.end():].strip()
                        if streets_part:
                            current_streets.append(streets_part)
                        
                        logger.debug(f"🔹 [VOE] Знайдено чергу: {current_queue}")
                        continue
                    
                    # Інакше це продовження списку вулиць
                    if current_queue and line:
                        # Пропускаємо короткі технічні рядки
                        if len(line) < 5 or line.isdigit():
                            continue
                        current_streets.append(line)
        
        # Зберігаємо останню чергу
        if current_queue and current_streets:
            queues[current_queue] = current_streets
        
        logger.info(f"✅ [VOE] Розпарсовано {len(queues)} черг")
        
        # Логуємо приклади
        for queue_num, streets in list(queues.items())[:3]:
            street_count = len(streets)
            logger.debug(f"   Черга {queue_num}: {street_count} вулиць")
        
        return queues
        
    except Exception as e:
        logger.error(f"❌ [VOE] Помилка парсингу PDF: {e}")
        logger.exception("Детальна інформація:")
        return {}


def convert_voe_queues_to_schedule_format(queues: Dict[str, List[str]]) -> Dict:
    """
    Конвертує черги VOE в формат сумісний з системою
    
    Args:
        queues: {"1.1": ["вул.Батозька 2-14", ...], ...}
    
    Returns:
        Dict: {
            "1.1": {"outages": [], "possible": []},  # Для VOE черги статичні
            ...
        }
    """
    # VOE PDF графік не містить інформацію про час відключень
    # Тільки список вулиць в кожній черзі
    # Час відключень треба брати з окремого джерела або API
    
    schedule_format = {}
    for queue_num in queues.keys():
        schedule_format[queue_num] = {
            "outages": [],  # Заповнюється з іншого джерела
            "possible": []
        }
    
    return schedule_format


if __name__ == '__main__':
    # Тест
    logging.basicConfig(level=logging.INFO)
    
    pdf_path = "/tmp/voe_schedule.pdf"
    queues = parse_voe_pdf_schedule(pdf_path)
    
    print(f"\n✅ Знайдено {len(queues)} черг")
    for queue_num, streets in list(queues.items())[:5]:
        print(f"\nЧерга {queue_num}:")
        for street in streets[:3]:
            print(f"  - {street[:80]}")
        if len(streets) > 3:
            print(f"  ... та ще {len(streets) - 3} вулиць")
