# Директорія Data

Ця директорія використовується для зберігання статичних даних про адреси та черги відключень.

## Файли

### `addresses.json`
Повна таблиця відповідності адрес до черг. Не зберігається в Git (занадто великий файл).

### `addresses_example.json`
Приклад структури JSON файлу з адресами.

## Використання

### Імпорт адрес:
```bash
python -m app.utils.address_manager import --file data/addresses.json
```

### Експорт адрес:
```bash
python -m app.utils.address_manager export --file data/addresses.json
```

## Структура JSON

```json
[
  {
    "city": "Місто",
    "street": "Назва вулиці",
    "house_number": "Номер будинку",
    "queue": "Номер черги (1, 2, 3 тощо)",
    "zone": "Зона (опціонально)"
  }
]
```

## Як отримати повний файл

1. **Парсинг з сайту:**
   ```bash
   python -m app.utils.update_addresses
   python -m app.utils.address_manager export
   ```

2. **Отримати від команди:** Якщо у вас є доступ до резервної копії

3. **Створити вручну:** Використовуйте `addresses_example.json` як шаблон
