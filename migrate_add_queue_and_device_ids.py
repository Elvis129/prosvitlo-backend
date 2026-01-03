"""
Міграція бази даних:
1. Додає поле queue до user_addresses
2. Додає поле device_ids до notifications
"""
import sqlite3
import sys

def migrate_database(db_path):
    """Виконує міграцію бази даних"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print(f"📦 Міграція бази даних: {db_path}")
        
        # Перевіряємо чи існує поле queue в user_addresses
        cursor.execute("PRAGMA table_info(user_addresses)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'queue' not in columns:
            print("➕ Додаємо поле 'queue' до таблиці user_addresses...")
            cursor.execute("""
                ALTER TABLE user_addresses 
                ADD COLUMN queue TEXT
            """)
            print("✅ Поле 'queue' додано")
        else:
            print("ℹ️ Поле 'queue' вже існує в user_addresses")
        
        # Перевіряємо чи існує поле device_ids в notifications
        cursor.execute("PRAGMA table_info(notifications)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'device_ids' not in columns:
            print("➕ Додаємо поле 'device_ids' до таблиці notifications...")
            cursor.execute("""
                ALTER TABLE notifications 
                ADD COLUMN device_ids TEXT
            """)
            print("✅ Поле 'device_ids' додано")
        else:
            print("ℹ️ Поле 'device_ids' вже існує в notifications")
        
        # Створюємо індекс для queue
        try:
            print("➕ Створюємо індекс для queue...")
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_address_queue 
                ON user_addresses(queue)
            """)
            print("✅ Індекс створено")
        except sqlite3.OperationalError as e:
            print(f"ℹ️ Індекс вже існує: {e}")
        
        conn.commit()
        print("✅ Міграція завершена успішно!")
        
    except Exception as e:
        print(f"❌ Помилка міграції: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    # Локальна база
    print("=" * 60)
    print("МІГРАЦІЯ ЛОКАЛЬНОЇ БАЗИ ДАНИХ")
    print("=" * 60)
    migrate_database("./prosvitlo.db")
    
    print("\n" + "=" * 60)
    print("ІНСТРУКЦІЯ ДЛЯ ВІДДАЛЕНОЇ БАЗИ")
    print("=" * 60)
    print("Виконайте на сервері:")
    print("1. fly ssh console")
    print("2. cd /data")
    print("3. python3 << 'EOF'")
    print(open(__file__).read())
    print("EOF")

