"""
Міграція: Додати unique constraint на fcm_token
"""
import sqlite3
import sys


def migrate(db_path: str):
    """Додає unique constraint на fcm_token в таблиці device_tokens"""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        print("🔧 Міграція: Додавання unique constraint на fcm_token")
        print("="*70)
        
        # Крок 1: Перевіряємо чи є дублікати
        print("\n1️⃣ Перевірка дублікатів...")
        cursor.execute('''
            SELECT fcm_token, COUNT(*) as count 
            FROM device_tokens 
            GROUP BY fcm_token 
            HAVING COUNT(*) > 1
        ''')
        duplicates = cursor.fetchall()
        
        if duplicates:
            print(f"⚠️ Знайдено {len(duplicates)} дублікатів!")
            for token, count in duplicates:
                print(f"   Token {token[:40]}... зустрічається {count} разів")
                
                # Видаляємо старіші дублікати, залишаємо найновіший
                cursor.execute('''
                    DELETE FROM device_tokens 
                    WHERE fcm_token = ? 
                    AND id NOT IN (
                        SELECT id FROM device_tokens 
                        WHERE fcm_token = ? 
                        ORDER BY updated_at DESC 
                        LIMIT 1
                    )
                ''', (token, token))
                print(f"   ✅ Видалено {cursor.rowcount} старих записів")
        else:
            print("✅ Дублікатів немає")
        
        # Крок 2: Створюємо тимчасову таблицю з unique constraint
        print("\n2️⃣ Створення нової структури...")
        cursor.execute('''
            CREATE TABLE device_tokens_new (
                id INTEGER NOT NULL PRIMARY KEY, 
                device_id VARCHAR NOT NULL UNIQUE, 
                fcm_token VARCHAR NOT NULL UNIQUE, 
                notifications_enabled BOOLEAN NOT NULL, 
                platform VARCHAR NOT NULL, 
                created_at DATETIME DEFAULT (CURRENT_TIMESTAMP), 
                updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP)
            )
        ''')
        print("✅ Нова таблиця створена")
        
        # Крок 3: Копіюємо дані
        print("\n3️⃣ Копіювання даних...")
        cursor.execute('''
            INSERT INTO device_tokens_new 
            SELECT * FROM device_tokens
        ''')
        rows_copied = cursor.rowcount
        print(f"✅ Скопійовано {rows_copied} записів")
        
        # Крок 4: Видаляємо стару таблицю
        print("\n4️⃣ Видалення старої таблиці...")
        cursor.execute('DROP TABLE device_tokens')
        print("✅ Стара таблиця видалена")
        
        # Крок 5: Перейменовуємо нову
        print("\n5️⃣ Перейменування таблиці...")
        cursor.execute('ALTER TABLE device_tokens_new RENAME TO device_tokens')
        print("✅ Таблиця перейменована")
        
        # Крок 6: Створюємо індекси
        print("\n6️⃣ Створення індексів...")
        cursor.execute('CREATE INDEX ix_device_tokens_id ON device_tokens (id)')
        cursor.execute('CREATE INDEX ix_device_tokens_platform ON device_tokens (platform)')
        print("✅ Індекси створені")
        
        # Commit змін
        conn.commit()
        
        # Перевірка
        print("\n7️⃣ Перевірка результату...")
        cursor.execute('SELECT sql FROM sqlite_master WHERE type="table" AND name="device_tokens"')
        print(cursor.fetchone()[0])
        
        print("\n" + "="*70)
        print("✅ Міграція завершена успішно!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Помилка: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    # Для тестування локально
    migrate('./prosvitlo.db')
