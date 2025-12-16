# 🚀 Деплой на Fly.io

## Крок 1: Встановлення Fly CLI

```bash
# macOS
brew install flyctl

# Linux
curl -L https://fly.io/install.sh | sh

# Windows
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

Перевір встановлення:
```bash
flyctl version
```

## Крок 2: Авторизація

```bash
flyctl auth login
```

## Крок 3: Налаштування секретів

Додай всі змінні з твого `.env` файлу як секрети:

```bash
flyctl secrets set \
  APP_NAME="ProСвітло" \
  DEBUG="False" \
  DATABASE_URL="sqlite:///./prosvitlo.db" \
  FIREBASE_CREDENTIALS_PATH="serviceAccountKey.json" \
  TELEGRAM_BOT_TOKEN="твій_токен" \
  TELEGRAM_CHANNEL_ID="@твій_канал" \
  TELEGRAM_ENABLED="True" \
  DONATION_JAR_URL="твоє_посилання" \
  DONATION_CARD_NUMBER="твоя_картка" \
  DONATION_DESCRIPTION="опис"
```

## Крок 4: Деплой

```bash
# Перший деплой (створить додаток)
flyctl launch

# Наступні деплої
flyctl deploy
```

## Крок 5: Перевірка

```bash
# Відкрити додаток у браузері
flyctl open

# Переглянути логи
flyctl logs

# Перевірити статус
flyctl status
```

## Важливі команди

```bash
# Переглянути секрети
flyctl secrets list

# Встановити новий секрет
flyctl secrets set KEY=value

# Масштабування (якщо потрібно)
flyctl scale count 1

# Відкрити консоль
flyctl ssh console

# Перезапустити
flyctl apps restart
```

## Firebase Credentials

Для Firebase потрібно завантажити `serviceAccountKey.json`:

```bash
# Створи секрет з вмістом файлу
flyctl secrets set FIREBASE_CREDENTIALS="$(cat serviceAccountKey.json | base64)"
```

Або додай файл в .dockerignore виключення та скопіюй в Dockerfile.

## База даних

SQLite буде працювати, але дані втратяться при перезапуску. Для постійного зберігання:

```bash
# Створити volume
flyctl volumes create prosvitlo_data --size 1

# Змонтувати в fly.toml
```

Додати в `fly.toml`:
```toml
[[mounts]]
  source = "prosvitlo_data"
  destination = "/app/data"
```

## CORS

Не забудь додати домен Fly.io до ALLOWED_ORIGINS:

```bash
flyctl secrets set ALLOWED_ORIGINS='["https://твій-додаток.fly.dev"]'
```
