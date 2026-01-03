"""
Оновлює queue для всіх UserAddress записів на основі AddressQueue
"""
import sqlite3
import sys

def update_queues(db_path):
    """Оновлює queue для існуючих адрес"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print(f"📦 Оновлення черг для адрес: {db_path}")
        
        # Отримуємо всі UserAddress БЕЗ queue
        cursor.execute("""
            SELECT id, city, street, house_number 
            FROM user_addresses 
            WHERE queue IS NULL
        """)
        addresses_without_queue = cursor.fetchall()
        
        if not addresses_without_queue:
            print("✅ Всі адреси вже мають queue")
            return
        
        print(f"📊 Знайдено {len(addresses_without_queue)} адрес без queue")
        
        updated = 0
        for addr_id, city, street, house_number in addresses_without_queue:
            # Шукаємо queue в AddressQueue
            cursor.execute("""
                SELECT queue FROM address_queues
                WHERE city = ? AND street = ? AND house_number = ?
            """, (city, street, house_number))
            
            result = cursor.fetchone()
            if result:
                queue = result[0]
                cursor.execute("""
                    UPDATE user_addresses 
                    SET queue = ? 
                    WHERE id = ?
                """, (queue, addr_id))
                updated += 1
                print(f"✅ Оновлено: {city}, {street}, {house_number} -> {queue}")
            else:
                print(f"⚠️ Не знайдено queue для: {city}, {street}, {house_number}")
        
        conn.commit()
        print(f"✅ Оновлено {updated} адрес")
        
    except Exception as e:
        print(f"❌ Помилка: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    import os
    
    if os.path.exists('/data/prosvitlo.db'):
        db_path = '/data/prosvitlo.db'
    else:
        db_path = './prosvitlo.db'
    
    print("=" * 60)
    print("ОНОВЛЕННЯ ЧЕРГ ДЛЯ ІСНУЮЧИХ АДРЕС")
    print("=" * 60)
    update_queues(db_path)
