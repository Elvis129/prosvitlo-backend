"""
Аналіз VOE PDF графіка
"""
import pdfplumber

pdf_path = "/tmp/voe_schedule.pdf"

print("=" * 60)
print("📄 АНАЛІЗ VOE PDF ГРАФІКА")
print("=" * 60)

try:
    with pdfplumber.open(pdf_path) as pdf:
        print(f"\n📋 Загальна інформація:")
        print(f"   Кількість сторінок: {len(pdf.pages)}")
        print(f"   Метадані: {pdf.metadata}")
        
        for page_num, page in enumerate(pdf.pages, 1):
            print(f"\n📄 Сторінка {page_num}:")
            print(f"   Розмір: {page.width} x {page.height}")
            
            # Витягуємо текст
            text = page.extract_text()
            if text:
                lines = text.strip().split('\n')
                print(f"   Кількість рядків тексту: {len(lines)}")
                print(f"\n   Перші 20 рядків:")
                for i, line in enumerate(lines[:20], 1):
                    print(f"      {i:2d}. {line[:80]}")
            else:
                print("   ⚠️ Текст не знайдено - можливо це зображення")
            
            # Перевіряємо таблиці
            tables = page.extract_tables()
            if tables:
                print(f"\n   ✅ Знайдено {len(tables)} таблиць")
                for i, table in enumerate(tables, 1):
                    print(f"\n   Таблиця {i}: {len(table)} рядків x {len(table[0]) if table else 0} колонок")
                    if table:
                        # Перші 3 рядки
                        for row_idx, row in enumerate(table[:3]):
                            print(f"      Рядок {row_idx}: {row}")
            else:
                print("   ⚠️ Таблиці не знайдено")
            
            # Перевіряємо зображення
            images = page.images
            if images:
                print(f"\n   🖼️  Знайдено {len(images)} зображень")
            
            # Тільки перша сторінка для огляду
            if page_num == 1:
                break

except Exception as e:
    print(f"\n❌ Помилка: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
