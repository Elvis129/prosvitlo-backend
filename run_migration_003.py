#!/usr/bin/env python3
"""
Скрипт для запуску міграції 003 - додавання таблиці sent_announcement_hashes
"""
import sys
import os

# Додаємо поточну директорію до шляху
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from migrations.003_add_sent_announcement_hashes import migrate

if __name__ == "__main__":
    # Використовуємо шлях до БД з середовища або за замовчуванням
    db_path = os.getenv('DATABASE_URL', 'sqlite:////data/prosvitlo.db').replace('sqlite:///', '')
    
    print(f"Запуск міграції 003 для БД: {db_path}")
    
    try:
        migrate(db_path)
        print("✅ Міграція завершена успішно")
    except Exception as e:
        print(f"❌ Помилка міграції: {e}")
        sys.exit(1)
