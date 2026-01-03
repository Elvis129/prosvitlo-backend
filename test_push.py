"""
Тестова відправка пушу на конкретний пристрій
"""
import requests
import json

BASE_URL = "http://localhost:8000"  # Локальний сервер

# Дані з логів
test_device = {
    "device_id": "SKQ1.211019.001",
    "fcm_token": "cdHQtFTrRPGGY2AV34qtao:APA91bFpyN5Rqo5Bn8WMfvLYcNY2olv8F9f1lBQi6bXAMXMT2s14_wDYqxfGBcYRN0Y1iphe_fHP88XS6seUxs39-Iy76voJLrnWFzTYqXjh-NrqYr4imgY",
    "platform": "android"
}

# Тестове повідомлення
notification = {
    "title": "🧪 Тестовий пуш",
    "body": "Це тестове повідомлення від системи ProСвітло. Якщо ви це бачите - все працює! ✅",
    "notification_type": "all",
    "category": "general",
    "data": {
        "type": "test",
        "timestamp": "2026-01-03T12:00:00Z"
    }
}

print("=" * 60)
print("ВІДПРАВКА ТЕСТОВОГО ПУШУ")
print("=" * 60)
print(f"Device ID: {test_device['device_id']}")
print(f"FCM Token: {test_device['fcm_token'][:50]}...")
print(f"Title: {notification['title']}")
print(f"Body: {notification['body']}")
print("=" * 60)

try:
    response = requests.post(
        f"{BASE_URL}/api/v1/notifications/send",
        json=notification,
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code == 200:
        print("✅ УСПІШНО ВІДПРАВЛЕНО!")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    else:
        print(f"❌ ПОМИЛКА: {response.status_code}")
        print(response.text)
        
except Exception as e:
    print(f"❌ ПОМИЛКА: {e}")
