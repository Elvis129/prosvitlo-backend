# Налаштування збереження даних на Fly.io

## Проблема

При кожному деплої на Fly.io всі дані (device tokens, користувацькі адреси, графіки) видаляються, тому що SQLite база знаходиться в контейнері, який пересоздається.

## Рішення

Використовуємо **Fly.io Volume** - постійне сховище, яке зберігається між деплоями.

## Крок 1: Створити Volume

**ВАЖЛИВО:** Виконайте це **ДО** деплою, інакше втратите поточні дані!

```bash
# Створити volume з назвою prosvitlo_data розміром 1GB
fly volumes create prosvitlo_data --region ams --size 1
```

Якщо volume вже існує, перевірте:
```bash
fly volumes list
```

## Крок 2: Задеплоїти зміни

Тепер можна деплоїти:
```bash
fly deploy
```

## Крок 3: Перевірити що працює

Перевірте логи:
```bash
fly logs
```

Перевірте SSH підключення і файл бази:
```bash
fly ssh console
ls -lh /data/
```

## Як це працює

- **До змін:** База `prosvitlo.db` зберігалась в `./` (поточна директорія контейнера) → видалялась при деплої
- **Після змін:** База зберігається в `/data/prosvitlo.db` → це mount до volume → зберігається між деплоями

## Зміни в коді

1. `app/config.py`: 
   ```python
   DATABASE_URL: str = "sqlite:////data/prosvitlo.db"
   ```

2. `fly.toml`:
   ```toml
   [[mounts]]
     source = "prosvitlo_data"
     destination = "/data"
     initial_size = "1gb"
   ```

## Що зберігається

Після налаштування volume зберігатимуться:
- ✅ Device tokens для push-повідомлень
- ✅ Користувацькі адреси
- ✅ Історія сповіщень
- ✅ Графіки відключень
- ✅ Всі інші дані з бази

## Важливо

- Volume прив'язаний до регіону (у нас `ams` - Amsterdam)
- При видаленні додатка volume НЕ видаляється автоматично
- Можна зробити backup: `fly volumes list` → `fly ssh sftp get /data/prosvitlo.db`
