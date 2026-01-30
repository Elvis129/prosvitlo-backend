#!/usr/bin/env python3
"""
Парсер Excel файлів від HOE для створення бази даних адрес версії 2.

Виправляє баги:
1. Формат "18А,18Б" (без пробілу) тепер розпізнається правильно
2. Всі літери (А, Б, В, Г, тощо) зберігаються
3. Дублікати автоматично видаляються
"""

import openpyxl
import json
import re
import requests
from pathlib import Path
from typing import Dict, Set
from collections import defaultdict

class AddressParser:
    """Парсер адрес з Excel файлів HOE"""
    
    def __init__(self):
        self.addresses = defaultdict(lambda: defaultdict(dict))
        self.stats = {
            'total_cities': 0,
            'total_streets': 0,
            'total_houses': 0,
            'houses_with_letters': 0,
            'duplicates_removed': 0
        }
    
    def normalize_house_numbers(self, houses_str: str) -> Set[str]:
        """
        Розбиває рядок номерів будинків на окремі номери.
        
        Обробляє edge cases:
        - "18А,18Б" (без пробілу)
        - "18А, 18Б" (з пробілом)
        - "18 А" (з пробілом перед літерою)
        - "18/1А" (дріб з літерою)
        """
        if not houses_str:
            return set()
        
        # Нормалізуємо: додаємо пробіл після коми якщо його немає
        # "18А,18Б" -> "18А, 18Б"
        normalized = re.sub(r'([А-ЯҐЄІЇа-яґєії]),(\S)', r'\1, \2', str(houses_str))
        
        # Розбиваємо по комах
        parts = [p.strip() for p in normalized.split(',')]
        
        # Прибираємо пробіли між цифрою та літерою: "18 А" -> "18А"
        houses = set()
        for part in parts:
            if part:
                # Видаляємо пробіли між цифрою/дробом та літерою
                clean = re.sub(r'(\d+(?:/\d+)?)\s+([А-ЯҐЄІЇа-яґєії])', r'\1\2', part)
                houses.add(clean)
        
        return houses
    
    def parse_excel(self, excel_path: str, source_url: str = "", is_business: bool = False):
        """
        Парсить один Excel файл.
        
        Args:
            excel_path: Шлях до Excel файлу
            source_url: URL джерела для відстеження
            is_business: True якщо це непобутові споживачі
        """
        print(f"\n📄 Парсимо: {Path(excel_path).name}")
        
        try:
            wb = openpyxl.load_workbook(excel_path)
            ws = wb.active
            
            current_city = None
            houses_found = 0
            
            for i, row in enumerate(ws.iter_rows(min_row=1, max_row=10000, values_only=True), 1):
                # Пропускаємо порожні рядки
                if not any(row):
                    continue
                
                # Пропускаємо заголовки
                if row[0] and 'населений пункт' in str(row[0]).lower():
                    continue
                
                # Структура: [Населений пункт, Вулиця, Список будинків, Черга]
                city = str(row[0]).strip() if row[0] else None
                street = str(row[1]).strip() if len(row) > 1 and row[1] else None
                houses_str = str(row[2]).strip() if len(row) > 2 and row[2] else ""
                queue = str(row[3]).strip() if len(row) > 3 and row[3] else ""
                
                # Оновлюємо поточне місто
                if city and len(city) > 2 and city[0].isupper():
                    current_city = city
                
                # Парсимо будинки
                if current_city and street and houses_str:
                    houses = self.normalize_house_numbers(houses_str)
                    
                    for house in houses:
                        # Перевіряємо чи є літера
                        has_letter = any(c.isalpha() and ord(c) > 127 for c in house)
                        if has_letter:
                            self.stats['houses_with_letters'] += 1
                        
                        # Якщо будинок вже є, зберігаємо додаткову інформацію
                        if house in self.addresses[current_city][street]:
                            self.stats['duplicates_removed'] += 1
                            existing = self.addresses[current_city][street][house]
                            # Додаємо чергу якщо різна
                            if queue and queue != existing.get('queue'):
                                if 'queues' not in existing:
                                    existing['queues'] = [existing['queue']]
                                if queue not in existing['queues']:
                                    existing['queues'].append(queue)
                        else:
                            self.addresses[current_city][street][house] = {
                                'queue': queue,
                                'source_url': source_url,
                                'is_business': is_business
                            }
                            houses_found += 1
                            self.stats['total_houses'] += 1
            
            print(f"   ✓ Додано {houses_found} будинків")
            
        except Exception as e:
            print(f"   ✗ Помилка: {e}")
    
    def save_to_json(self, output_path: str):
        """Зберігає базу даних в JSON"""
        # Конвертуємо defaultdict в звичайний dict
        result = {}
        for city, streets in self.addresses.items():
            result[city] = {}
            for street, houses in streets.items():
                result[city][street] = dict(houses)
        
        # Оновлюємо статистику
        self.stats['total_cities'] = len(result)
        self.stats['total_streets'] = sum(len(streets) for streets in result.values())
        
        # Зберігаємо
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ База даних збережена: {output_path}")
        print(f"   Міст: {self.stats['total_cities']}")
        print(f"   Вулиць: {self.stats['total_streets']}")
        print(f"   Будинків: {self.stats['total_houses']}")
        print(f"   З літерами: {self.stats['houses_with_letters']} ({self.stats['houses_with_letters']/self.stats['total_houses']*100:.1f}%)")
        print(f"   Дублікатів видалено: {self.stats['duplicates_removed']}")


def download_excel_files():
    """Завантажує всі Excel файли з сайту HOE"""
    
    print("="*80)
    print("ЗАВАНТАЖЕННЯ EXCEL ФАЙЛІВ З HOE.COM.UA")
    print("="*80)
    
    # Отримуємо список файлів
    response = requests.get('https://hoe.com.ua/page/pogodinni-vidkljuchennja')
    content = response.text
    
    # Шукаємо всі xlsx файли
    import re
    urls = re.findall(r'href="(/Content/Uploads/[^"]+\.xlsx)"', content)
    
    print(f"\nЗнайдено {len(urls)} Excel файлів")
    
    # Створюємо папку для завантажень
    download_dir = Path('/tmp/hoe_excel_files')
    download_dir.mkdir(exist_ok=True)
    
    downloaded = []
    for i, url in enumerate(urls, 1):
        full_url = f"https://hoe.com.ua{url}"
        filename = Path(url).name
        filepath = download_dir / filename
        
        # Пропускаємо якщо вже завантажено
        if filepath.exists():
            print(f"  {i}/{len(urls)} Пропускаємо (вже є): {filename}")
            downloaded.append((str(filepath), full_url))
            continue
        
        try:
            print(f"  {i}/{len(urls)} Завантажуємо: {filename}...", end='')
            r = requests.get(full_url, timeout=30)
            r.raise_for_status()
            filepath.write_bytes(r.content)
            print(f" ✓ ({len(r.content)//1024} KB)")
            downloaded.append((str(filepath), full_url))
        except Exception as e:
            print(f" ✗ Помилка: {e}")
    
    print(f"\n✅ Завантажено {len(downloaded)} файлів в {download_dir}")
    return downloaded


def main():
    """Головна функція"""
    
    print("="*80)
    print("СТВОРЕННЯ БАЗИ ДАНИХ АДРЕС ВЕРСІЇ 2")
    print("="*80)
    
    # Крок 1: Завантажуємо файли
    files = download_excel_files()
    
    # Крок 2: Парсимо всі файли
    print("\n" + "="*80)
    print("ПАРСИНГ EXCEL ФАЙЛІВ")
    print("="*80)
    
    parser = AddressParser()
    
    for filepath, source_url in files:
        filename = Path(filepath).name
        # Визначаємо чи це непобутові споживачі
        is_business = 'непобут' in filename.lower()
        parser.parse_excel(filepath, source_url, is_business)
    
    # Крок 3: Зберігаємо результат
    output_path = '/Users/user/my_pet_project/prosvitlo-backend/cache/addresses_v2.json'
    parser.save_to_json(output_path)
    
    # Крок 4: Створюємо метадані версії
    version_info = {
        'version': 2,
        'created_at': '2026-01-30',
        'source': 'hoe.com.ua',
        'stats': parser.stats,
        'notes': 'Fixed bug with house numbers like 18А,18Б (no space after comma)'
    }
    
    version_path = '/Users/user/my_pet_project/prosvitlo-backend/cache/addresses_version.json'
    with open(version_path, 'w', encoding='utf-8') as f:
        json.dump(version_info, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Метадані версії збережені: {version_path}")
    
    # Крок 5: Тестуємо проблемну вулицю
    print("\n" + "="*80)
    print("ТЕСТ: Перевірка вул. Лісогринівецька")
    print("="*80)
    
    with open(output_path, 'r', encoding='utf-8') as f:
        db = json.load(f)
    
    if "Хмельницький" in db:
        for street, houses in db["Хмельницький"].items():
            if "Лісогрин" in street:
                print(f"\n✓ Знайдено: {street}")
                print(f"  Всього будинків: {len(houses)}")
                
                # Шукаємо будинки з 18
                houses_18 = [h for h in houses.keys() if '18' in h]
                print(f"  Будинки з '18': {sorted(houses_18)}")
                
                # Перевіряємо чи є літери
                has_18a = '18А' in houses
                has_18b = '18Б' in houses
                has_18v = '18В' in houses
                has_18g = '18Г' in houses
                
                print(f"\n  Перевірка:")
                print(f"    18А: {'✓ Є' if has_18a else '✗ НЕМАЄ'}")
                print(f"    18Б: {'✓ Є' if has_18b else '✗ НЕМАЄ'}")
                print(f"    18В: {'✓ Є' if has_18v else '✗ НЕМАЄ'}")
                print(f"    18Г: {'✓ Є' if has_18g else '✗ НЕМАЄ'}")
                
                if has_18a and has_18b and has_18v and has_18g:
                    print(f"\n  🎉 БАГ ВИПРАВЛЕНО! Всі літери на місці!")
                else:
                    print(f"\n  ⚠️  Баг все ще присутній")
    
    print("\n" + "="*80)
    print("ГОТОВО!")
    print("="*80)
    print("\nНаступні кроки:")
    print("1. Перевір cache/addresses_v2.json")
    print("2. Оновлюй код для використання v2")
    print("3. Протестуй що користувачі не втратили дані")
    print("4. Задеплой оновлення")


if __name__ == '__main__':
    main()
