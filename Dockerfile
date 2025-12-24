# Використовуємо Python 3.11 slim образ
FROM python:3.11-slim

# Встановлюємо необхідні системні залежності для Selenium та ChromeDriver
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Встановлюємо робочу директорію
WORKDIR /app

# Копіюємо файл з залежностями
COPY requirements.txt .

# Встановлюємо Python залежності
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо весь проєкт
COPY . .

# Створюємо директорії для кешу та статики
RUN mkdir -p cache app/static/schedules

# Відкриваємо порт 8080 (стандарт для Fly.io)
EXPOSE 8080

# Змінна середовища для Chrome
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Змінна середовища для інтервалу перевірки (за замовчуванням 60 хвилин)
ENV CHECK_INTERVAL_MINUTES=60

# Команда запуску (використовуємо змінну PORT з Fly.io)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
