"""
Debug скрипт для аналізу HTML структури VOE сайту
Використання: python debug_voe_html.py
"""

import requests
from bs4 import BeautifulSoup
import sys
from datetime import date

def analyze_voe_page(url, page_name):
    """Детально аналізує структуру VOE сторінки"""
    print(f"\n{'='*80}")
    print(f"🔍 АНАЛІЗ: {page_name}")
    print(f"URL: {url}")
    print(f"{'='*80}\n")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'uk-UA,uk;q=0.9,en;q=0.8',
        }
        
        today = date.today()
        data = {
            'Year': str(today.year),
            'Month': str(today.month),
        }
        
        print(f"📤 POST дані: {data}")
        response = requests.post(url, data=data, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        print(f"\n✅ Статус: {response.status_code}")
        print(f"📏 Розмір: {len(response.text)} символів\n")
        
        # Аналіз 1: Шукаємо форми
        print("📋 ФОРМИ:")
        forms = soup.find_all('form')
        if forms:
            for i, form in enumerate(forms, 1):
                print(f"  Form {i}:")
                print(f"    Action: {form.get('action')}")
                print(f"    Method: {form.get('method')}")
                inputs = form.find_all(['input', 'select'])
                for inp in inputs:
                    print(f"    - {inp.name}: name={inp.get('name')}, type={inp.get('type')}")
        else:
            print("  ❌ Форм не знайдено")
        
        # Аналіз 2: Шукаємо таблиці
        print("\n📊 ТАБЛИЦІ:")
        tables = soup.find_all('table')
        if tables:
            for i, table in enumerate(tables, 1):
                print(f"  Table {i}:")
                print(f"    Class: {table.get('class')}")
                print(f"    ID: {table.get('id')}")
                rows = table.find_all('tr')
                print(f"    Рядків: {len(rows)}")
                if rows:
                    # Перший рядок (заголовок)
                    headers = rows[0].find_all(['th', 'td'])
                    if headers:
                        print(f"    Заголовки: {[h.get_text(strip=True) for h in headers]}")
                    # Другий рядок (дані)
                    if len(rows) > 1:
                        cells = rows[1].find_all(['td', 'th'])
                        print(f"    Приклад даних: {[c.get_text(strip=True)[:30] for c in cells]}")
        else:
            print("  ❌ Таблиць не знайдено")
        
        # Аналіз 3: Шукаємо div-контейнери
        print("\n📦 DIV КОНТЕЙНЕРИ:")
        common_classes = [
            'outage', 'disconnect', 'відключення', 'item', 'row', 
            'card', 'block', 'content', 'data', 'info'
        ]
        
        for cls in common_classes:
            divs = soup.find_all('div', class_=lambda x: x and cls in str(x).lower())
            if divs:
                print(f"  Знайдено {len(divs)} div з класом *{cls}*")
                if divs:
                    first_div = divs[0]
                    print(f"    Приклад класів: {first_div.get('class')}")
                    text = first_div.get_text(strip=True)[:100]
                    print(f"    Текст: {text}...")
        
        # Аналіз 4: Шукаємо article елементи
        print("\n📰 ARTICLE ЕЛЕМЕНТИ:")
        articles = soup.find_all('article')
        if articles:
            print(f"  Знайдено {len(articles)} article елементів")
            for i, art in enumerate(articles[:3], 1):
                print(f"  Article {i}: class={art.get('class')}")
        else:
            print("  ❌ Article не знайдено")
        
        # Аналіз 5: Шукаємо списки (ul/ol)
        print("\n📝 СПИСКИ:")
        lists = soup.find_all(['ul', 'ol'])
        if lists:
            print(f"  Знайдено {len(lists)} списків")
            for i, lst in enumerate(lists[:3], 1):
                items = lst.find_all('li')
                print(f"  List {i}: {len(items)} елементів, class={lst.get('class')}")
        else:
            print("  ❌ Списків не знайдено")
        
        # Аналіз 6: Загальна структура
        print("\n🏗️ ЗАГАЛЬНА СТРУКТУРА:")
        main_content = soup.find(['main', 'div'], id=lambda x: x and 'content' in str(x).lower())
        if main_content:
            print(f"  Main content: {main_content.name}, id={main_content.get('id')}")
        
        # Шукаємо будь-які елементи з текстом що містить ключові слова
        print("\n🔍 ПОШУК КЛЮЧОВИХ СЛІВ:")
        keywords = ['РЕМ', 'вул.', 'вулиця', 'будинок', 'час', 'дата']
        for keyword in keywords:
            elements = soup.find_all(text=lambda x: x and keyword.lower() in str(x).lower())
            if elements:
                print(f"  '{keyword}': знайдено {len(elements)} згадок")
                # Показуємо батьківські елементи
                parent_tags = set()
                for elem in elements[:5]:
                    if elem.parent:
                        parent_tags.add(elem.parent.name)
                print(f"    Батьківські теги: {parent_tags}")
        
        # Зберігаємо HTML для ручного аналізу
        filename = f"debug_{page_name.lower().replace(' ', '_')}.html"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"\n💾 HTML збережено в {filename}")
        
        return True
        
    except Exception as e:
        print(f"❌ Помилка: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Аналізує всі VOE сторінки"""
    print("\n" + "="*80)
    print("🚀 VOE HTML STRUCTURE ANALYZER")
    print("="*80)
    
    pages = [
        ("https://www.voe.com.ua/disconnection/emergency", "Emergency Outages"),
        ("https://www.voe.com.ua/disconnection/planned", "Planned Outages"),
    ]
    
    results = {}
    
    for url, name in pages:
        results[name] = analyze_voe_page(url, name)
    
    print("\n" + "="*80)
    print("📊 ПІДСУМОК")
    print("="*80)
    
    for name, success in results.items():
        status = "✅" if success else "❌"
        print(f"{status} {name}")
    
    print("\n💡 РЕКОМЕНДАЦІЇ:")
    print("1. Подивіться збережені HTML файли для детального аналізу")
    print("2. Використайте browser DevTools для інспекції сторінки")
    print("3. Перевірте чи потрібна авторизація або cookies")
    print("="*80)


if __name__ == "__main__":
    sys.exit(main())
