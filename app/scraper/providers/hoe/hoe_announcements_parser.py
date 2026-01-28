"""
Модуль для парсингу оголошень з сайту hoe.com.ua
Використовує систему базового шаблону для виявлення змін
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import logging
import hashlib
from datetime import datetime
import json
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCHEDULE_URL = "https://hoe.com.ua/page/pogodinni-vidkljuchennja"
NEWS_URL = "https://hoe.com.ua/post/novini-kompaniji"
TEMPLATE_FILE = "cache/schedule_page_template.json"


def fetch_announcements() -> List[Dict[str, str]]:
    """
    Парсинг оголошень з сайту - порівнює з базовим шаблоном
    Відправляє push ТІЛЬКИ якщо є відмінності від шаблону
    
    Returns:
        Список словників з полями: title, body, content_hash, source
    """
    announcements = []
    
    # 1. Перевіряємо сторінку графіків на зміни
    schedule_changes = _check_schedule_page_changes()
    if schedule_changes:
        announcements.extend(schedule_changes)
    
    # 2. Парсимо новини з окремої сторінки
    news_announcements = _fetch_news_page()
    announcements.extend(news_announcements)
    
    # 3. Видаляємо дублікати за хешем
    unique_announcements = _remove_duplicates(announcements)
    
    logger.info(f"Всього знайдено {len(unique_announcements)} унікальних повідомлень")
    return unique_announcements


def _check_schedule_page_changes() -> List[Dict[str, str]]:
    """
    Перевіряє сторінку графіків на зміни відносно базового шаблону
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(SCHEDULE_URL, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.text, 'html.parser')
        content_div = soup.find('div', class_='content-main')
        
        if not content_div:
            logger.warning("Не знайдено блок з контентом")
            return []
        
        # Витягуємо весь контент ДО першого зображення
        first_image = content_div.find('img')
        current_content = []
        
        # Додаємо 'li', 'ul', 'ol' для захоплення буллетів та списків
        for element in content_div.find_all(['p', 'h3', 'h4', 'li', 'ul', 'ol']):
            if first_image and element.find('img'):
                break
            if first_image and element.sourceline and first_image.sourceline:
                if element.sourceline >= first_image.sourceline:
                    break
            
            # Для списків витягуємо всі елементи li
            if element.name in ['ul', 'ol']:
                for li in element.find_all('li', recursive=False):
                    text = li.get_text(strip=True)
                    if text and len(text) > 10:
                        current_content.append(text)
            else:
                text = element.get_text(strip=True)
                if text and len(text) > 10:
                    current_content.append(text)
        
        # Генеруємо хеш поточного контенту
        current_hash = hashlib.md5('\n'.join(current_content).encode()).hexdigest()
        
        # Завантажуємо базовий шаблон
        template_data = _load_template()
        
        if not template_data:
            # Перший запуск - зберігаємо як шаблон
            _save_template(current_content, current_hash)
            logger.info("✓ Створено базовий шаблон сторінки")
            return []
        
        template_hash = template_data.get('hash')
        template_content = template_data.get('content', [])
        
        # Якщо хеш не змінився - нічого нового немає
        if current_hash == template_hash:
            logger.info("✓ Сторінка не змінилася відносно шаблону")
            return []
        
        # Хеш змінився - шукаємо що саме
        logger.info("⚠️ Виявлено зміни на сторінці графіків!")
        announcements = _analyze_changes(template_content, current_content)
        
        # Оновлюємо шаблон (якщо зміни не критичні)
        # Шаблон НЕ оновлюється якщо є важливі оголошення
        has_important = any(
            'UPD' in a.get('title', '') or 
            'Збільшення обсягу' in a.get('title', '') 
            for a in announcements
        )
        
        if not has_important and announcements:
            # Це просто оновлення сторінки без важливих оголошень
            _save_template(current_content, current_hash)
            logger.info("✓ Оновлено базовий шаблон")
        
        return announcements
        
    except Exception as e:
        logger.error(f"Помилка при перевірці сторінки графіків: {e}")
        return []


def _analyze_changes(template_content: List[str], current_content: List[str]) -> List[Dict[str, str]]:
    """
    Аналізує відмінності між шаблоном та поточним контентом
    Створює оголошення з НОВИХ параграфів + додає зв'язуючі параграфи для контексту
    """
    announcements = []
    
    # Знаходимо нові параграфи (є в current, немає в template)
    new_indices_set = set()
    for i, para in enumerate(current_content):
        if para not in template_content:
            new_indices_set.add(i)
    
    if not new_indices_set:
        logger.info("Зміни виявлені, але нових параграфів немає")
        return []
    
    logger.info(f"Знайдено {len(new_indices_set)} НОВИХ параграфів")
    
    # Створюємо групи оголошень
    # Логіка: якщо параграфи містять ключові слова про відключення - групуємо їх разом
    
    i = 0
    while i < len(current_content):
        # Пропускаємо старі параграфи, якщо вони не зв'язуючі
        if i not in new_indices_set:
            # Перевіряємо чи це зв'язуючий параграф (Відповідно:, тощо)
            para = current_content[i]
            if not ('відповідно' in para.lower() and len(para) < 50):
                i += 1
                continue
        
        # Знайшли новий або зв'язуючий параграф - починаємо групу
        current_announcement = []
        start_idx = i
        
        # Шукаємо початок оголошення (заголовок з ключовими словами)
        para = current_content[i]
        is_announcement_start = (
            'збільшення обсягу' in para.lower() or
            'зменшення обсягу' in para.lower() or
            'розпорядженням нек' in para.lower() or
            'розпорядження нек' in para.lower() or
            para.startswith('UPD') or
            para.startswith('Оновлення')
        )
        
        if is_announcement_start:
            # Це початок оголошення - збираємо всі наступні пов'язані параграфи
            current_announcement.append(para)
            i += 1
            
            # Додаємо всі наступні параграфи що стосуються цього оголошення
            while i < len(current_content):
                next_para = current_content[i]
                
                # Зупиняємось якщо це новий заголовок оголошення
                is_next_announcement = (
                    'збільшення обсягу' in next_para.lower() or
                    'зменшення обсягу' in next_para.lower() or
                    ('розпорядженням нек' in next_para.lower() and i in new_indices_set) or
                    next_para.startswith('UPD') or
                    next_para.startswith('Оновлення')
                )
                
                if is_next_announcement:
                    break
                
                # Додаємо параграф якщо він:
                # 1. Новий, АБО
                # 2. Зв'язуючий ("Відповідно:", короткий), АБО  
                # 3. Містить інформацію про черги/підчерги
                should_include = (
                    i in new_indices_set or
                    ('відповідно' in next_para.lower() and len(next_para) < 50) or
                    'підчерг' in next_para.lower() or
                    next_para.strip().startswith('•') or
                    next_para.strip().startswith('-')
                )
                
                if should_include:
                    current_announcement.append(next_para)
                    i += 1
                else:
                    # Досягли кінця оголошення
                    break
            
            # Зберігаємо оголошення
            if current_announcement:
                _save_announcement(current_announcement, announcements, 'schedule_page')
        else:
            # Це не початок оголошення - пропускаємо
            i += 1
    
    logger.info(f"Створено {len(announcements)} оголошень зі змін")
    return announcements


def _fetch_news_page() -> List[Dict[str, str]]:
    """
    Парсить новини з окремої сторінки новин компанії.
    Переходить на кожну новину та витягує повний текст.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(NEWS_URL, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.text, 'html.parser')
        announcements = []
        
        # Шукаємо всі посилання на пости/новини
        post_links = soup.find_all('a', href=lambda x: x and '/post/' in x and x != NEWS_URL)
        
        if not post_links:
            logger.warning("Не знайдено посилань на новини")
            return []
        
        logger.info(f"Знайдено {len(post_links)} посилань на новини")
        
        # Витягуємо унікальні URL
        seen_urls = set()
        unique_links = []
        for link in post_links:
            url = link.get('href')
            if url and url not in seen_urls and url != NEWS_URL:
                seen_urls.add(url)
                if not url.startswith('http'):
                    url = 'https://hoe.com.ua' + url
                unique_links.append(url)
        
        # Беремо 3 останні унікальні новини
        for news_url in unique_links[:3]:
            try:
                news_response = requests.get(news_url, headers=headers, timeout=30)
                news_response.raise_for_status()
                news_response.encoding = 'utf-8'
                
                news_soup = BeautifulSoup(news_response.text, 'html.parser')
                
                # Шукаємо контент новини
                content_div = news_soup.find('div', class_='content-main')
                if not content_div:
                    content_div = news_soup.find('div', class_='post-content')
                
                if not content_div:
                    logger.warning(f"Не знайдено контент для {news_url}")
                    continue
                
                # Витягуємо заголовок
                title_elem = content_div.find(['h1', 'h2'])
                title = title_elem.get_text(strip=True) if title_elem else 'Новина'
                
                # Витягуємо всі параграфи
                paragraphs = []
                for p in content_div.find_all('p'):
                    text = p.get_text(strip=True)
                    if text and len(text) > 10:
                        paragraphs.append(text)
                
                if not paragraphs:
                    continue
                
                full_text = f"{title}\n\n" + '\n\n'.join(paragraphs)
                content_hash = hashlib.md5(full_text.encode()).hexdigest()
                
                announcements.append({
                    'title': '📰 Новина від Хмельницькобленерго',
                    'body': full_text[:500],
                    'full_body': full_text,
                    'content_hash': content_hash,
                    'source': 'news_page',
                    'url': news_url
                })
                
                logger.info(f"✓ Спарсено новину: {title[:50]}")
                
            except Exception as e:
                logger.error(f"Помилка при парсингу новини {news_url}: {e}")
                continue
        
        logger.info(f"Зі сторінки новин знайдено {len(announcements)} новин")
        return announcements
        
    except Exception as e:
        logger.error(f"Помилка при парсингу сторінки новин: {e}")
        return []


def _save_announcement(paragraphs: List[str], announcements: List[Dict], source: str):
    """Зберігає оголошення зі списку параграфів"""
    full_text = '\n\n'.join(paragraphs)
    content_hash = hashlib.md5(full_text.encode()).hexdigest()
    
    # Визначаємо заголовок
    first_line = paragraphs[0][:100]
    if 'UPD' in first_line or 'Оновлення' in first_line:
        title = '🔄 Оновлення графіка відключень'
    elif 'Збільшення обсягу' in first_line:
        title = '⚠️ Збільшення обсягу обмежень'
    elif 'Зменшення обсягу' in first_line:
        title = '✅ Зменшення обсягу обмежень'
    elif 'Графік оновлено' in first_line or 'Новий графік' in first_line:
        title = '📊 Оновлено графік відключень'
    else:
        title = '📢 Інформація про відключення'
    
    announcements.append({
        'title': title,
        'body': full_text[:500],
        'full_body': full_text,
        'content_hash': content_hash,
        'source': source
    })


def _remove_duplicates(announcements: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Видаляє дублікати за хешем контенту"""
    seen_hashes = set()
    unique = []
    
    for announcement in announcements:
        if announcement['content_hash'] not in seen_hashes:
            seen_hashes.add(announcement['content_hash'])
            unique.append(announcement)
        else:
            logger.info(f"Пропущено дублікат: {announcement['title'][:50]}")
    
    return unique


def _load_template() -> Optional[Dict]:
    """Завантажує базовий шаблон сторінки"""
    try:
        if os.path.exists(TEMPLATE_FILE):
            with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Помилка при завантаженні шаблону: {e}")
    return None


def _save_template(content: List[str], content_hash: str):
    """Зберігає базовий шаблон сторінки"""
    try:
        os.makedirs(os.path.dirname(TEMPLATE_FILE), exist_ok=True)
        template_data = {
            'hash': content_hash,
            'content': content,
            'updated_at': datetime.now().isoformat()
        }
        with open(TEMPLATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(template_data, f, ensure_ascii=False, indent=2)
        logger.info("✓ Шаблон збережено")
    except Exception as e:
        logger.error(f"Помилка при збереженні шаблону: {e}")


def check_schedule_availability() -> Optional[Dict[str, any]]:
    """
    Перевіряє чи доступні графіки на сьогодні
    
    Returns:
        Dict з інформацією про доступність або None
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(SCHEDULE_URL, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Шукаємо повідомлення про недоступність графіків
        not_available_text = [
            'графік ще не доступний',
            'графік відсутній',
            'інформація відсутня',
            'погодинні відключення не застосовуються'
        ]
        
        page_text = soup.get_text().lower()
        
        for text in not_available_text:
            if text in page_text:
                return {
                    'available': False,
                    'message': 'Погодинні відключення на сьогодні не застосовуються'
                }
        
        # Якщо є таблиця з графіками - значить доступні
        schedule_table = soup.find('table')
        if schedule_table:
            return {
                'available': True,
                'message': 'Графіки відключень доступні'
            }
        
        return {
            'available': False,
            'message': 'Інформація про графіки відсутня'
        }
        
    except Exception as e:
        logger.error(f"Помилка при перевірці доступності графіків: {e}")
        return None
