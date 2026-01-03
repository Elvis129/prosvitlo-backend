import sqlite3
from datetime import datetime

conn = sqlite3.connect('/data/prosvitlo.db')
cursor = conn.cursor()

try:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='no_schedule_notification_state'")
    
    if not cursor.fetchone():
        print('Створення таблиці...')
        cursor.execute('''
            CREATE TABLE no_schedule_notification_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enabled BOOLEAN NOT NULL DEFAULT 1,
                consecutive_days_without_schedule INTEGER NOT NULL DEFAULT 0,
                last_check_date DATE,
                last_notification_date DATE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            INSERT INTO no_schedule_notification_state 
            (enabled, consecutive_days_without_schedule, updated_at)
            VALUES (1, 0, ?)
        ''', (datetime.now().isoformat(),))
        
        conn.commit()
        print('✅ Міграцію завершено')
    else:
        print('✅ Таблиця вже існує')
        
    cursor.execute('SELECT * FROM no_schedule_notification_state')
    print('Стан:', cursor.fetchone())
    
finally:
    conn.close()
