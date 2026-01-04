"""
Міграція: Додавання унікального індексу для fcm_token

Додає унікальний індекс та видаляє дублікати токенів (залишає найновіший)
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
    
    print(f"Підключення до бази: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 1. Перевіряємо чи існують дублікати fcm_token
        cursor.execute("""
            SELECT fcm_token, COUNT(*) as count 
            FROM device_tokens 
            GROUP BY fcm_token 
            HAVING count > 1
        """)
        duplicates = cursor.fetchall()
        
        if duplicates:
            print(f"⚠️ Знайдено {len(duplicates)} дублікатів fcm_token")
            
            # Видаляємо дублікати, залишаючи найновіший запис (або з найпізнішою updated_at)
            for fcm_token, count in duplicates:
                print(f"  Обробка токену {fcm_token[:20]}... ({count} записів)")
                
                # Отримуємо всі записи з цим токеном
                cursor.execute("""
                    SELECT device_id, created_at, updated_at 
                    FROM device_tokens 
                    WHERE fcm_token = ?
                    ORDER BY 
                        COALESCE(updated_at, created_at) DESC
                """, (fcm_token,))
                
                records = cursor.fetchall()
                # Залишаємо перший (найновіший), видаляємо решту
                to_keep = records[0][0]
                to_delete = [r[0] for r in records[1:]]
                
                print(f"    Залишаємо: {to_keep}")
                print(f"    Видаляємо: {to_delete}")
                
                for device_id in to_delete:
                    cursor.execute("""
                        DELETE FROM device_tokens 
                        WHERE device_id = ?
                    """, (device_id,))
        else:
            print("✅ Дублікати fcm_token не знайдено")
        
        # 2. Перевіряємо чи індекс вже існує
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name='ix_device_tokens_fcm_token'
        """)
        
        if cursor.fetchone():
            print("✅ Індекс ix_device_tokens_fcm_token вже існує")
        else:
            # Створюємо унікальний індекс
            print("📝 Створення унікального індексу для fcm_token...")
            cursor.execute("""
                CREATE UNIQUE INDEX ix_device_tokens_fcm_token 
                ON device_tokens (fcm_token)
            """)
            print("✅ Унікальний індекс створено")
        
        conn.commit()
        print("✅ Міграція завершена успішно")
        
    except Exception as e:
        print(f"❌ Помилка міграції: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
