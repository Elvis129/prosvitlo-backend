"""
Пошук списку адрес на VOE сайті
"""
import requests
from bs4 import BeautifulSoup

print("=" * 60)
print("🔍 ПОШУК СПИСКУ АДРЕС НА VOE")
print("=" * 60)

# Можливі URL де може бути список адрес
urls_to_check = [
    "https://www.voe.com.ua/",
    "https://www.voe.com.ua/for-customers/",
    "https://www.voe.com.ua/perelik-adr/",
    "https://www.voe.com.ua/for_customers/perelik-adr/",
    "https://www.voe.com.ua/addresses/",
    "https://www.voe.com.ua/spisok-adresov/",
    "https://www.voe.com.ua/rem/",
    "https://www.voe.com.ua/territory/",
]

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})

print("\n📄 Перевіряю можливі URL зі списками адрес...\n")

for url in urls_to_check:
    try:
        print(f"Перевіряю: {url}")
        response = session.get(url, timeout=10)
        
        if response.status_code == 200:
            print(f"  ✅ Сторінка існує!")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Шукаємо ключові слова
            text = response.text.lower()
            keywords = ['адрес', 'вулиц', 'будинк', 'рем', 'район', 'перелік']
            found_keywords = [kw for kw in keywords if kw in text]
            
            if found_keywords:
                print(f"  🔍 Знайдено ключові слова: {', '.join(found_keywords)}")
                
                # Шукаємо таблиці
                tables = soup.find_all('table')
                if tables:
                    print(f"  📊 Таблиць: {len(tables)}")
                
                # Шукаємо списки
                lists = soup.find_all(['ul', 'ol'])
                if lists:
                    print(f"  📋 Списків: {len(lists)}")
                
                # Показуємо перші 500 символів
                print(f"  📝 Початок тексту:")
                print(f"     {soup.get_text()[:200].strip()}")
            
        elif response.status_code == 404:
            print(f"  ❌ 404 - сторінка не існує")
        else:
            print(f"  ⚠️  Код: {response.status_code}")
            
    except Exception as e:
        print(f"  ❌ Помилка: {e}")
    
    print()

# Перевіряємо меню навігації на головній
print("\n" + "=" * 60)
print("🔍 АНАЛІЗ МЕНЮ НАВІГАЦІЇ")
print("=" * 60)

try:
    response = session.get("https://www.voe.com.ua/", timeout=10)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Шукаємо всі посилання
    links = soup.find_all('a', href=True)
    
    print(f"\n📋 Знайдено {len(links)} посилань")
    print("\n🔍 Посилання що містять ключові слова:\n")
    
    for link in links:
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        keywords = ['адрес', 'рем', 'район', 'перелік', 'терит', 'список', 'address', 'territory']
        if any(kw in href.lower() or kw in text.lower() for kw in keywords):
            print(f"  {text}: {href}")

except Exception as e:
    print(f"❌ Помилка аналізу меню: {e}")

print("\n" + "=" * 60)
