"""
Спроба витягти адреси VOE з відключень що ми вже парсимо.
Це буде неповний список, але хоч щось.
"""

import sys
sys.path.insert(0, '/Users/user/my_pet_project/prosvitlo-backend')

from app.scraper.providers.voe.voe_outage_parser import fetch_voe_emergency_outages, fetch_voe_planned_outages
import json

def extract_addresses():
    """Витягує унікальні адреси з аварійних та планових відключень VOE"""
    
    print("=== Завантаження відключень VOE ===")
    
    # Отримуємо відключення
    emergency = fetch_voe_emergency_outages()
    planned = fetch_voe_planned_outages()
    
    print(f"Аварійних: {len(emergency)}")
    print(f"Планових: {len(planned)}")
    
    all_outages = emergency + planned
    
    # Структура для збору даних
    addresses_data = {
        "regions": set(),  # регіони (м. Вінниця, смт. Хмільник тощо)
        "streets": set(),  # вулиці
        "houses": set(),  # будинки (повні адреси)
        "all_addresses": []  # всі унікальні адреси
    }
    
    for outage in all_outages:
        address = outage.get("address", "")
        if not address or address == "Інформація відсутня":
            continue
            
        addresses_data["all_addresses"].append(address)
        
        # Простий парсинг адреси
        # Формат: "м. Вінниця, вул. Київська, 20" або "смт. Літин, вул. Центральна"
        if "," in address:
            parts = address.split(",")
            if len(parts) >= 2:
                # Перша частина - місто/селище
                region = parts[0].strip()
                addresses_data["regions"].add(region)
                
                # Друга частина - вулиця
                street = parts[1].strip()
                addresses_data["streets"].add(street)
                
                # Якщо є третя частина - номер будинку
                if len(parts) >= 3:
                    house_full = f"{region}, {street}, {parts[2].strip()}"
                    addresses_data["houses"].add(house_full)
    
    # Конвертуємо set в list для JSON
    result = {
        "regions": sorted(list(addresses_data["regions"])),
        "streets": sorted(list(addresses_data["streets"])),
        "houses": sorted(list(addresses_data["houses"])),
        "total_unique_addresses": len(set(addresses_data["all_addresses"])),
        "total_regions": len(addresses_data["regions"]),
        "total_streets": len(addresses_data["streets"]),
        "total_houses": len(addresses_data["houses"])
    }
    
    print("\n=== Статистика ===")
    print(f"Унікальних повних адрес: {result['total_unique_addresses']}")
    print(f"Унікальних регіонів: {result['total_regions']}")
    print(f"Унікальних вулиць: {result['total_streets']}")
    print(f"Адрес з будинками: {result['total_houses']}")
    
    print("\n=== Приклади регіонів ===")
    for region in result['regions'][:10]:
        print(f"  - {region}")
    
    print("\n=== Приклади вулиць ===")
    for street in result['streets'][:10]:
        print(f"  - {street}")
    
    print("\n=== Приклади повних адрес ===")
    for house in result['houses'][:10]:
        print(f"  - {house}")
    
    # Зберігаємо результат
    output_file = "voe_addresses_from_outages.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Результат збережено в {output_file}")
    
    return result


if __name__ == "__main__":
    extract_addresses()
