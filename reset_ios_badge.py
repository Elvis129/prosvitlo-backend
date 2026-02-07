#!/usr/bin/env python3
"""
Скрипт для скидання iOS badge для всіх пристроїв
Запускається один раз після деплою
"""
import sys
sys.path.insert(0, '/app')

from firebase_admin import messaging, initialize_app, credentials
import firebase_admin
from app.database import SessionLocal
from app.models import DeviceToken

# Ініціалізація Firebase
try:
    firebase_admin.get_app()
except ValueError:
    cred = credentials.Certificate('/app/serviceAccountKey.json')
    initialize_app(cred)

# Отримуємо всі iOS токени
db = SessionLocal()
ios_tokens = db.query(DeviceToken).filter(DeviceToken.platform == 'ios').all()
print(f'Знайдено {len(ios_tokens)} iOS пристроїв')

# Відправляємо тихий пуш з badge=0
success = 0
failed = 0

for token in ios_tokens:
    try:
        message = messaging.Message(
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        badge=0,
                        content_available=True
                    )
                )
            ),
            token=token.fcm_token
        )
        response = messaging.send(message)
        print(f'✅ {token.device_id[:20]}...')
        success += 1
    except Exception as e:
        print(f'❌ {token.device_id[:20]}... ERROR: {str(e)[:50]}')
        failed += 1

print(f'\n📊 Результат: успішно={success}, помилок={failed}')
db.close()
