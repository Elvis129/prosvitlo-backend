"""
Міграція БД: додає notification_sent_at та таблицю queue_notifications
"""
import sqlite3
import sys

def migrate_database(db_path):
    """Виконує міграцію бази даних"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print(f"📦 Міграція бази даних: {db_path}")
        
        # 1. Додаємо notification_sent_at до emergency_outages
        cursor.execute("PRAGMA table_info(emergency_outages)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'notification_sent_at' not in columns:
            print('➕ Додаємо notification_sent_at до emergency_outages...')
            cursor.execute('''
                ALTER TABLE emergency_outages 
                ADD COLUMN notification_sent_at TIMESTAMP
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_emergency_notification 
                ON emergency_outages(notification_sent_at)
            ''')
            print('✅ notification_sent_at додано до emergency_outages')
        else:
            print('ℹ️ notification_sent_at вже існує в emergency_outages')
        
        # 2. Додаємо notification_sent_at до planned_outages
        cursor.execute("PRAGMA table_info(planned_outages)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'notification_sent_at' not in columns:
            print('➕ Додаємо notification_sent_at до planned_outages...')
            cursor.execute('''
                ALTER TABLE planned_outages 
                ADD COLUMN notification_sent_at TIMESTAMP
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_planned_notification 
                ON planned_outages(notification_sent_at)
            ''')
            print('✅ notification_sent_at додано до planned_outages')
        else:
            print('ℹ️ notification_sent_at вже існує в planned_outages')
        
        # 3. Створюємо таблицю queue_notifications
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='queue_notifications'
        """)
        
        if not cursor.fetchone():
            print('➕ Створюємо таблицю queue_notifications...')
            cursor.execute('''
                CREATE TABLE queue_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE NOT NULL,
                    hour INTEGER NOT NULL,
                    queue TEXT NOT NULL,
                    notification_sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE INDEX idx_queue_notification_date 
                ON queue_notifications(date)
            ''')
            cursor.execute('''
                CREATE INDEX idx_queue_notification_hour 
                ON queue_notifications(hour)
            ''')
            cursor.execute('''
                CREATE INDEX idx_queue_notification_queue 
                ON queue_notifications(queue)
            ''')
            cursor.execute('''
                CREATE UNIQUE INDEX idx_queue_notification_unique 
                ON queue_notifications(date, hour, queue)
            ''')
            print('✅ Таблиця queue_notifications створена')
        else:
            print('ℹ️ Таблиця queue_notifications вже існує')
        
        conn.commit()
        print('✅ Міграція завершена успішно!')
        
    except Exception as e:
        print(f"❌ Помилка міграції: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    import os
    
    # Визначаємо шлях до БД
    if os.path.exists('/data/prosvitlo.db'):
        # На сервері
        db_path = '/data/prosvitlo.db'
    else:
        # Локально
        db_path = './prosvitlo.db'
    
    print("=" * 60)
    print("МІГРАЦІЯ: notification_sent_at + queue_notifications")
    print("=" * 60)
    migrate_database(db_path)
