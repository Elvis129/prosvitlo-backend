"""
Міграція: Додавання поля region до таблиць відключень

Додає поле region (VARCHAR) з дефолтним значенням 'hoe' до:
- emergency_outages
- planned_outages
"""

import sqlite3
import sys
import os

# Додаємо шлях до app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def migrate():
    """Виконує міграцію бази даних"""
    
    # Визначаємо шлях до бази
    db_path = os.environ.get('DATABASE_URL', 'sqlite:///./prosvitlo.db')
    if db_path.startswith('sqlite:///'):
        db_path = db_path.replace('sqlite:///', '')
    
    print(f"📍 Підключення до БД: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("\n🔍 Перевіряємо наявність поля region...")
        
        # Перевіряємо emergency_outages
        cursor.execute("PRAGMA table_info(emergency_outages)")
        emergency_columns = [col[1] for col in cursor.fetchall()]
        
        if 'region' not in emergency_columns:
            print("➕ Додаємо поле region до emergency_outages...")
            cursor.execute("""
                ALTER TABLE emergency_outages 
                ADD COLUMN region VARCHAR DEFAULT 'hoe'
            """)
            print("✅ Поле region додано до emergency_outages")
        else:
            print("ℹ️  Поле region вже існує в emergency_outages")
        
        # Перевіряємо planned_outages
        cursor.execute("PRAGMA table_info(planned_outages)")
        planned_columns = [col[1] for col in cursor.fetchall()]
        
        if 'region' not in planned_columns:
            print("➕ Додаємо поле region до planned_outages...")
            cursor.execute("""
                ALTER TABLE planned_outages 
                ADD COLUMN region VARCHAR DEFAULT 'hoe'
            """)
            print("✅ Поле region додано до planned_outages")
        else:
            print("ℹ️  Поле region вже існує в planned_outages")
        
        conn.commit()
        
        print("\n✅ Міграція завершена успішно!")
        print("\n📊 Статистика:")
        
        # Лічимо записи по регіонам
        cursor.execute("SELECT COUNT(*) FROM emergency_outages WHERE region = 'hoe'")
        hoe_emergency = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM planned_outages WHERE region = 'hoe'")
        hoe_planned = cursor.fetchone()[0]
        
        print(f"   HOE: {hoe_emergency} аварійних, {hoe_planned} планових")
        
    except Exception as e:
        print(f"❌ Помилка при міграції: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def rollback():
    """Відміняє міграцію (видаляє поле region)"""
    
    db_path = os.environ.get('DATABASE_URL', 'sqlite:///./prosvitlo.db')
    if db_path.startswith('sqlite:///'):
        db_path = db_path.replace('sqlite:///', '')
    
    print(f"📍 Підключення до БД: {db_path}")
    print("⚠️  SQLite не підтримує ALTER TABLE DROP COLUMN")
    print("ℹ️  Для rollback треба пересоздати таблиці без поля region")

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Міграція: додавання поля region')
    parser.add_argument('--rollback', action='store_true', help='Відміняє міграцію')
    args = parser.parse_args()
    
    if args.rollback:
        rollback()
    else:
        migrate()
