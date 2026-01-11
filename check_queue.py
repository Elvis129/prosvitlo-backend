import sqlite3

conn = sqlite3.connect('/data/prosvitlo.db')
cursor = conn.cursor()

# Перевірка queue_notifications
cursor.execute('SELECT * FROM queue_notifications WHERE date = "2026-01-07" AND queue = "6.1" AND hour = 12')
result = cursor.fetchone()

if result:
    print('Push для черги 6.1 о 12:00: ТАК - вже відправлено')
    print(f'Деталі: {result}')
else:
    print('Push для черги 6.1 о 12:00: НІ - ще не відправлявся')

conn.close()
