"""
Міграція: Додавання таблиці no_schedule_notification_state
Для відстеження стану повідомлень про відсутність графіка

Запуск:
    python migrate_no_schedule_state.py
"""

import sqlite3
from datetime import datetime

def migrate():
    """Виконує міграцію"""
    
    # Локальна БД
    local_db = "./prosvitlo.db"
    
    print("=" * 60)
    print("МІГРАЦІЯ: Додавання таблиці no_schedule_notification_state")
    print("=" * 60)
    
    conn = sqlite3.connect(local_db)
    cursor = conn.cursor()
    
    try:
        # Перевіряємо чи існує таблиця
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='no_schedule_notification_state'
        """)
        
        if cursor.fetchone():
            print("✅ Таблиця no_schedule_notification_state вже існує")
        else:
            print("📝 Створення таблиці no_schedule_notification_state...")
            
            cursor.execute("""
                CREATE TABLE no_schedule_notification_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    consecutive_days_without_schedule INTEGER NOT NULL DEFAULT 0,
                    last_check_date DATE,
                    last_notification_date DATE,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Додаємо початковий запис
            cursor.execute("""
                INSERT INTO no_schedule_notification_state 
                (enabled, consecutive_days_without_schedule, updated_at)
                VALUES (1, 0, ?)
            """, (datetime.now().isoformat(),))
            
            conn.commit()
            print("✅ Таблицю створено та ініціалізовано")
        
        # Виводимо стан
        cursor.execute("SELECT * FROM no_schedule_notification_state")
        row = cursor.fetchone()
        if row:
            print("\n📊 Поточний стан:")
            print(f"  ID: {row[0]}")
            print(f"  Enabled: {'✅ Так' if row[1] else '❌ Ні'}")
            print(f"  Consecutive days: {row[2]}")
            print(f"  Last check: {row[3] or 'Ніколи'}")
            print(f"  Last notification: {row[4] or 'Ніколи'}")
            print(f"  Updated: {row[5]}")
        
        print("\n✅ Міграція локальної БД завершена успішно!")
        
    except Exception as e:
        print(f"\n❌ Помилка при міграції: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
    
    print("\n" + "=" * 60)
    print("НАСТУПНИЙ КРОК: Виконати міграцію на production")
    print("=" * 60)
    print("\nВиконай на сервері:")
    print("  fly ssh console")
    print("  python3 << 'EOF'")
    print("""
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
EOF
""")

if __name__ == "__main__":
    migrate()
