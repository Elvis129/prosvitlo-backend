#!/usr/bin/env python3
import sqlite3
from datetime import date

conn = sqlite3.connect('/data/prosvitlo.db')
cursor = conn.cursor()

print("=" * 60)
print("ПЕРЕВІРКА ANNOUNCEMENT_OUTAGES")
print("=" * 60)

# Перевіряємо announcement_outages
cursor.execute('SELECT COUNT(*) FROM announcement_outages')
count = cursor.fetchone()[0]
print(f"\nВсього записів: {count}")

if count > 0:
    cursor.execute('''
        SELECT date, queue, start_hour, end_hour, announcement_text 
        FROM announcement_outages 
        ORDER BY date DESC, queue, start_hour
        LIMIT 20
    ''')
    
    print("\nОстанні 20 записів:")
    print("-" * 60)
    for row in cursor.fetchall():
        date_str, queue, start, end, text = row
        text_preview = text[:40] if text else ''
        print(f"{date_str} | Черга {queue:4s} | {start:02d}:00-{end:02d}:00 | {text_preview}")

# Перевіряємо графік на сьогодні
today = date.today()
print(f"\n{'=' * 60}")
print(f"ГРАФІК НА {today}")
print("=" * 60)

cursor.execute('SELECT parsed_data FROM schedules WHERE date = ?', (str(today),))
row = cursor.fetchone()

if row and row[0]:
    import json
    data = json.loads(row[0])
    
    if '3.2' in data:
        print(f"\nЧерга 3.2:")
        print(f"  Outages: {data['3.2'].get('outages', [])}")
        print(f"  Possible: {data['3.2'].get('possible', [])}")

conn.close()
print("\n✅ Готово")
