import sqlite3

conn = sqlite3.connect('/data/prosvitlo.db')
cursor = conn.cursor()

print("📦 Міграція бази /data/prosvitlo.db")

# Перевірка user_addresses
cursor.execute('PRAGMA table_info(user_addresses)')
columns = [col[1] for col in cursor.fetchall()]

if 'queue' not in columns:
    print('➕ Додаємо queue до user_addresses...')
    cursor.execute('ALTER TABLE user_addresses ADD COLUMN queue TEXT')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_address_queue ON user_addresses(queue)')
    print('✅ queue додано')
else:
    print('ℹ️ queue вже існує в user_addresses')

# Перевірка notifications
cursor.execute('PRAGMA table_info(notifications)')
columns = [col[1] for col in cursor.fetchall()]

if 'device_ids' not in columns:
    print('➕ Додаємо device_ids до notifications...')
    cursor.execute('ALTER TABLE notifications ADD COLUMN device_ids TEXT')
    print('✅ device_ids додано')
else:
    print('ℹ️ device_ids вже існує в notifications')

conn.commit()
conn.close()
print('✅ Міграція завершена успішно!')
