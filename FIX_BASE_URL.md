# Виправлення проблеми з BASE_URL

## Проблема

У коді були hardcoded локальні адреси для формування посилань на зображення графіків:
- В `app/scheduler.py` використовувалася адреса `http://10.0.2.2:8000` (Android emulator localhost)
- В `app/utils/image_downloader.py` за замовчуванням була `http://localhost:8000`

Це призводило до того, що:
1. На продакшн сервері (Fly.io) в API відповідях повертались локальні URL замість реальних
2. Клієнтські додатки не могли завантажити зображення графіків

## Рішення

### 1. Додано конфігураційний параметр `BASE_URL`

В файлі `app/config.py`:
```python
BASE_URL: str = "http://localhost:8000"  # Базова URL для формування посилань
```

### 2. Оновлено код формування URL

В `app/scheduler.py` замінено:
```python
# Було:
image_url = f"http://10.0.2.2:8000{local_image_path}"

# Стало:
from app.config import settings
image_url = f"{settings.BASE_URL}{local_image_path}"
```

### 3. Налаштовано змінні оточення

**Для локальної розробки** (`.env`):
```bash
BASE_URL=http://localhost:8000
# Або для тестування на Android емуляторі:
BASE_URL=http://10.0.2.2:8000
```

**Для продакшн** (`fly.toml`):
```toml
[env]
  BASE_URL = "https://prosvitlo-backend.fly.dev"
```

## Як задеплоїти зміни

1. Переконайтесь що у `fly.toml` встановлено правильний `BASE_URL`
2. Задеплойте зміни:
   ```bash
   fly deploy
   ```

3. Перевірте логи після деплою:
   ```bash
   fly logs
   ```

## Перевірка

Після деплою API повинен повертати правильні URL:

**До виправлення:**
```json
{
  "schedule_image_url": "http://10.0.2.2:8000/static/schedules/abc123.png"
}
```

**Після виправлення:**
```json
{
  "schedule_image_url": "https://prosvitlo-backend.fly.dev/static/schedules/abc123.png"
}
```

## Примітка про реєстрацію токенів

Ця проблема **не впливала** на реєстрацію device tokens для push-нотифікацій. 
Токени реєструються через endpoint `/api/v1/notifications/tokens/register` і зберігаються в базі даних незалежно від BASE_URL.

Якщо токени не зберігаються на сервері, перевірте:
1. Чи правильно працює база даних на сервері
2. Чи є доступ до Firebase credentials
3. Логи сервера під час реєстрації токена
