"""
Міграція для створення таблиці sent_announcement_hashes
Зберігає хеші відправлених оголошень для запобігання дублюванню після перезавантаження
"""
import sqlite3
import sys
from pathlib import Path

def migrate(db_path: str):
    """Створює таблицю sent_announcement_hashes"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Перевіряємо чи таблиця вже існує
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='sent_announcement_hashes'
        """)
        
        if cursor.fetchone():
            print("✅ Таблиця sent_announcement_hashes вже існує, пропускаємо")
            return
        
        # Створюємо таблицю
        cursor.execute("""
            CREATE TABLE sent_announcement_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_hash VARCHAR UNIQUE NOT NULL,
                announcement_type VARCHAR NOT NULL DEFAULT 'general',
                title VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Створюємо індекси
        cursor.execute("""
            CREATE UNIQUE INDEX idx_sent_hash_unique 
            ON sent_announcement_hashes(content_hash)
        """)
        
        cursor.execute("""
            CREATE INDEX idx_sent_hash_created 
            ON sent_announcement_hashes(created_at)
        """)
        
        conn.commit()
        print("✅ Міграція 003: таблиця sent_announcement_hashes створена успішно")
        
    except Exception as e:
        print(f"❌ Помилка міграції 003: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python 003_add_sent_announcement_hashes.py <db_path>")
        sys.exit(1)
    
    db_path = sys.argv[1]
    migrate(db_path)
