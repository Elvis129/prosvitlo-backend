"""
Міграція для створення таблиці announcement_outages
"""
import sqlite3
import sys
from pathlib import Path

def migrate(db_path: str):
    """Створює таблицю announcement_outages"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Перевіряємо чи таблиця вже існує
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='announcement_outages'
        """)
        
        if cursor.fetchone():
            print("✅ Таблиця announcement_outages вже існує, пропускаємо")
            return
        
        # Створюємо таблицю
        cursor.execute("""
            CREATE TABLE announcement_outages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                queue VARCHAR NOT NULL,
                start_hour INTEGER NOT NULL,
                end_hour INTEGER NOT NULL,
                announcement_text TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notification_sent_at TIMESTAMP
            )
        """)
        
        # Створюємо індекси
        cursor.execute("""
            CREATE INDEX idx_announcement_outage_date_queue 
            ON announcement_outages(date, queue, start_hour)
        """)
        
        cursor.execute("""
            CREATE INDEX idx_announcement_outage_active 
            ON announcement_outages(is_active, date)
        """)
        
        cursor.execute("""
            CREATE INDEX idx_announcement_outage_date 
            ON announcement_outages(date)
        """)
        
        cursor.execute("""
            CREATE INDEX idx_announcement_outage_queue 
            ON announcement_outages(queue)
        """)
        
        conn.commit()
        print("✅ Міграція успішна: створено таблицю announcement_outages")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Помилка міграції: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    # Для локального тестування
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/data/prosvitlo.db"
    migrate(db_path)
