# Чеклист впровадження VOE (Вінницяобленерго)

## ✅ Етап 1: Підготовка БД (1-2 дні)

### 1.1. Створити міграцію
```bash
touch migrations/003_add_region_support.py
```

### 1.2. Додати поле region у моделі
- [ ] `app/models.py` → Schedule.region
- [ ] `app/models.py` → EmergencyOutage.region
- [ ] `app/models.py` → PlannedOutage.region
- [ ] `app/models.py` → AddressQueue.region
- [ ] Додати індекси: `idx_*_region`

### 1.3. Запустити міграцію
```bash
# Тестова БД
python migrations/003_add_region_support.py

# Production (коли готово)
# Backup БД перед запуском!
```

---

## ✅ Етап 2: Конфігурація (0.5 дня)

### 2.1. Розширити config.py
- [ ] Додати `ENABLED_REGIONS: List[str]`
- [ ] Додати `VOE_ENABLED: bool = False`
- [ ] Додати `VOE_SCHEDULE_URL`
- [ ] Додати `VOE_EMERGENCY_URL`
- [ ] Додати `VOE_PLANNED_URL`

### 2.2. Перевірити конфігурацію
```python
python -c "from app.config import settings; print(settings.VOE_ENABLED)"
# Має вивести: False
```

---

## ✅ Етап 3: Створити базові парсери VOE (3-5 днів)

### 3.1. Структура файлів
```bash
mkdir -p app/scraper/providers/voe
touch app/scraper/providers/__init__.py
touch app/scraper/providers/voe/__init__.py
touch app/scraper/providers/voe/voe_parser.py
touch app/scraper/providers/voe/voe_schedule_parser.py
touch app/scraper/providers/voe/voe_announcements_parser.py
```

### 3.2. Імплементувати VOE парсер відключень
Файл: `app/scraper/providers/voe/voe_parser.py`

- [ ] `fetch_voe_emergency_outages()` - аварійні
- [ ] `fetch_voe_planned_outages()` - планові
- [ ] Тестування з реальними даними VOE
- [ ] Логування + обробка помилок

### 3.3. Імплементувати VOE парсер графіків
Файл: `app/scraper/providers/voe/voe_schedule_parser.py`

**Потрібні бібліотеки**:
```bash
pip install pdf2image
# macOS:
brew install poppler
# Ubuntu:
apt-get install poppler-utils
```

- [ ] `fetch_voe_schedule_pdf()` - завантаження PDF
- [ ] `pdf_to_images()` - конвертація PDF → PNG
- [ ] Інтеграція з `schedule_ocr_parser.py`
- [ ] Тестування з реальним PDF VOE

### 3.4. VOE оголошення (опціонально)
Файл: `app/scraper/providers/voe/voe_announcements_parser.py`

- [ ] Знайти сторінку з оголошеннями VOE
- [ ] Імплементувати парсер
- [ ] Або пропустити на MVP

---

## ✅ Етап 4: Перенести HOE у providers (1 день)

### 4.1. Рефакторинг існуючих парсерів
```bash
mkdir -p app/scraper/providers/hoe
# Перемістити:
mv app/scraper/hoe_parser.py app/scraper/providers/hoe/
mv app/scraper/outage_parser.py app/scraper/providers/hoe/hoe_outage_parser.py
mv app/scraper/schedule_parser.py app/scraper/providers/hoe/hoe_schedule_parser.py
mv app/scraper/announcements_parser.py app/scraper/providers/hoe/hoe_announcements_parser.py
```

### 4.2. Оновити імпорти
- [ ] `app/scheduler.py` → оновити imports
- [ ] Перевірити що HOE все ще працює
- [ ] Запустити тести

---

## ✅ Етап 5: Multi-region Scheduler (1-2 дні)

### 5.1. Оновити scheduler.py

**Існуючі функції → HOE**:
- [ ] `update_schedules()` → `update_schedules_hoe()`
- [ ] `check_and_notify_announcements()` → `check_announcements_hoe()`
- [ ] `update_outages()` → `update_outages_hoe()`

**Нові функції для VOE**:
- [ ] `update_schedules_voe()`
- [ ] `check_announcements_voe()`
- [ ] `update_outages_voe()`

**Об'єднуючі функції**:
- [ ] `update_all_schedules()` - викликає HOE + VOE
- [ ] `update_all_outages()` - викликає HOE + VOE
- [ ] `check_all_announcements()` - викликає HOE + VOE

### 5.2. Оновити jobs в scheduler
```python
# Замість:
scheduler.add_job(update_schedules, ...)

# Нове:
scheduler.add_job(update_all_schedules, ...)
```

### 5.3. Додати region у дані
При збереженні в БД завжди передавати:
- [ ] `region="hoe"` для HOE даних
- [ ] `region="voe"` для VOE даних

---

## ✅ Етап 6: API Endpoints (1 день)

### 6.1. Додати фільтр region
Оновити файли:
- [ ] `app/api/schedule_routes.py`
- [ ] `app/api/outage_routes.py`
- [ ] `app/api/notification_routes.py`

Додати параметр:
```python
region: str = Query(default="hoe", description="Region: hoe or voe")
```

### 6.2. Створити endpoint для регіонів
Файл: `app/api/regions_routes.py`
```python
@router.get("/regions")
def get_available_regions():
    return {
        "regions": [
            {"code": "hoe", "name": "Хмельницька область", "enabled": True},
            {"code": "voe", "name": "Вінницька область", "enabled": settings.VOE_ENABLED}
        ]
    }
```

### 6.3. Зворотна сумісність
- [ ] Default `region=hoe` у всіх endpoints
- [ ] Протестувати існуючі API запити
- [ ] Переконатися що нічого не зламалось

---

## ✅ Етап 7: Тестування (3-5 днів)

### 7.1. Unit тести
- [ ] Тести для VOE парсерів
- [ ] Тести для multi-region scheduler
- [ ] Тести для API endpoints з region

### 7.2. Integration тести
```bash
# 1. Вимкнути VOE
export VOE_ENABLED=False
python -m app.main
# Перевірити що HOE працює

# 2. Увімкнути VOE
export VOE_ENABLED=True
python -m app.main
# Перевірити що обидва працюють
```

### 7.3. Тестові сценарії
- [ ] HOE графіки парсяться коректно
- [ ] VOE графіки парсяться коректно (PDF)
- [ ] Аварійні VOE зберігаються з region="voe"
- [ ] API повертає тільки HOE при `?region=hoe`
- [ ] API повертає тільки VOE при `?region=voe`
- [ ] Пуші відправляються правильним користувачам

### 7.4. Load testing
- [ ] Перевірити навантаження з 2 регіонами
- [ ] CPU/RAM під час PDF парсингу
- [ ] Час відповіді API

---

## ✅ Етап 8: Deployment (1 день)

### 8.1. Підготовка
- [ ] Backup БД
- [ ] Перевірити міграцію на staging
- [ ] Документація для команди

### 8.2. Production deploy
```bash
# 1. Deploy з VOE_ENABLED=False
fly deploy
# Переконатися що HOE працює

# 2. Увімкнути VOE через env
fly secrets set VOE_ENABLED=true

# 3. Restart
fly apps restart prosvitlo-backend

# 4. Моніторинг
fly logs -a prosvitlo-backend
```

### 8.3. Моніторинг після запуску
- [ ] Перевірити логи HOE парсерів
- [ ] Перевірити логи VOE парсерів
- [ ] Перевірити БД (нові записи з region="voe")
- [ ] Перевірити API endpoints
- [ ] Моніторити помилки перші 24 години

### 8.4. Rollback план
Якщо щось пішло не так:
```bash
# Швидко вимкнути VOE
fly secrets set VOE_ENABLED=false
fly apps restart prosvitlo-backend

# Якщо зовсім погано - rollback
fly releases
fly releases rollback <version>
```

---

## ✅ Етап 9: Адреси для VOE (5-7 днів, опціонально)

### 9.1. Дослідження
- [ ] Знайти джерело даних адрес VOE
- [ ] Перевірити `site.voe.com.ua/informuvannya-spozhyvachiv`
- [ ] Або парсити з PDF графіка

### 9.2. Імплементація
- [ ] Парсер адрес VOE
- [ ] Зберігання в `AddressQueue` з region="voe"
- [ ] API для пошуку черги за адресою VOE

### 9.3. Альтернатива (швидке рішення)
Дозволити користувачам вводити чергу вручну:
```python
# API endpoint
@router.post("/user/queue/manual")
def set_queue_manually(
    user_id: int,
    region: str,
    queue: str,
    db: Session = Depends(get_db)
):
    # Зберегти в UserAddress
    pass
```

---

## 📊 Прогрес впровадження

**Мінімальний MVP** (без адрес):
- [ ] Етап 1: Підготовка БД ✅
- [ ] Етап 2: Конфігурація ✅
- [ ] Етап 3: VOE парсери ✅
- [ ] Етап 5: Multi-region Scheduler ✅
- [ ] Етап 6: API Endpoints ✅
- [ ] Етап 7: Тестування ✅
- [ ] Етап 8: Deployment ✅

**Повний функціонал** (з адресами):
- [ ] Етап 9: Адреси VOE ✅

---

## 🔥 Швидкий старт (за один вечір)

Якщо потрібно швидко побачити результат:

### 1. БД міграція
```bash
# Додати region="hoe" до всіх таблиць
```

### 2. Простий VOE парсер
```python
# Тільки аварійні відключення (найпростіше)
# app/scraper/providers/voe/voe_parser.py
```

### 3. Scheduler
```python
# Запускати VOE парсер якщо VOE_ENABLED=True
```

### 4. Тест
```bash
export VOE_ENABLED=True
python test_voe_parser.py
```

**Результат**: За 4-6 годин можна отримати базовий парсинг аварійних VOE.

---

## ❓ Питання? Проблеми?

Створюйте issues або питайте у чаті.

### Корисні команди для дебагу:

```bash
# Перевірити конфігурацію
python -c "from app.config import settings; print(vars(settings))"

# Протестувати VOE парсер окремо
python -c "from app.scraper.providers.voe.voe_parser import *; fetch_voe_emergency_outages()"

# Перевірити БД
sqlite3 /data/prosvitlo.db "SELECT COUNT(*), region FROM schedules GROUP BY region"

# Логи
fly logs -a prosvitlo-backend | grep VOE
```
