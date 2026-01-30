"""
Детальний аналіз сторінки планових відключень VOE
"""
import requests
from bs4 import BeautifulSoup

VOE_PLANNED_URL = "https://www.voe.com.ua/disconnection/planned"

print("=" * 60)
print("🔍 АНАЛІЗ СТОРІНКИ ПЛАНОВИХ ВІДКЛЮЧЕНЬ VOE")
print("=" * 60)

try:
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    
    print(f"\n📄 GET запит: {VOE_PLANNED_URL}")
    response = session.get(VOE_PLANNED_URL, timeout=15)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Шукаємо всі форми
    forms = soup.find_all('form')
    print(f"\n📋 Знайдено {len(forms)} форм:")
    for i, form in enumerate(forms):
        form_id = form.get('id', 'no id')
        form_action = form.get('action', 'no action')
        print(f"   [{i}] id='{form_id}', action='{form_action}'")
        
        # Виводимо всі input цієї форми
        inputs = form.find_all(['input', 'select'])
        for inp in inputs[:10]:  # Перші 10
            name = inp.get('name', 'no name')
            inp_type = inp.get('type', inp.name)
            print(f"       - {name} ({inp_type})")
    
    # Шукаємо таблицю
    print(f"\n📊 Шукаємо таблицю на сторінці...")
    table = soup.find('table')
    if table:
        rows = table.find_all('tr')
        print(f"✅ Знайдено таблицю з {len(rows)} рядками")
        
        if len(rows) > 0:
            header_row = rows[0]
            headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
            print(f"\n📋 Заголовки:")
            for i, h in enumerate(headers):
                print(f"   [{i}] {h}")
    else:
        print("⚠️ Таблиця НЕ знайдена на початковій сторінці")
        
        # Може дані завантажуються через AJAX?
        print(f"\n🔍 Шукаємо індикатори AJAX...")
        scripts = soup.find_all('script')
        ajax_scripts = [s for s in scripts if 'ajax' in str(s).lower() or 'fetch' in str(s).lower()]
        print(f"   Знайдено {len(ajax_scripts)} скриптів з AJAX/fetch")
        
        # Шукаємо div з певними класами
        content_divs = soup.find_all('div', class_=lambda x: x and ('content' in x or 'table' in x))
        print(f"   Знайдено {len(content_divs)} div з класами 'content' або 'table'")
    
    # Шукаємо select для вибору регіону/дати
    print(f"\n📋 Select елементи:")
    selects = soup.find_all('select')
    for select in selects:
        name = select.get('name', 'no name')
        options = select.find_all('option')
        print(f"   {name}: {len(options)} опцій")
        if len(options) <= 5:
            for opt in options:
                val = opt.get('value', '')
                text = opt.get_text(strip=True)
                print(f"      - value='{val}': {text}")

except Exception as e:
    print(f"\n❌ Помилка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
