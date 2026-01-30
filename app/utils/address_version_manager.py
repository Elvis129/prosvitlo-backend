"""
Утиліта для роботи з версіями бази даних адрес.
Дозволяє перемикатися між v1 і v2 з можливістю rollback.
"""
import json
import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)

CACHE_DIR = "cache"
VERSION_FILE = os.path.join(CACHE_DIR, "addresses_version.json")
ADDRESSES_V1 = os.path.join(CACHE_DIR, "addresses.json")
ADDRESSES_V2 = os.path.join(CACHE_DIR, "addresses_v2.json")


class AddressVersionManager:
    """Менеджер версій бази даних адрес"""
    
    def __init__(self):
        self.current_version = None
        self.addresses = None
    
    def get_version_info(self) -> Dict:
        """Отримує інформацію про поточну версію"""
        try:
            if os.path.exists(VERSION_FILE):
                with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Не вдалося прочитати версію: {e}")
        
        # За замовчуванням використовуємо v1
        return {'version': 1, 'source': 'legacy'}
    
    def load_addresses(self, preferred_version: int = 2) -> Dict:
        """
        Завантажує адреси з вказаної версії.
        
        Args:
            preferred_version: Бажана версія (1 або 2). За замовчуванням 2.
        
        Returns:
            Словник адрес
        """
        # Якщо вже завантажено - повертаємо
        if self.addresses is not None and self.current_version == preferred_version:
            return self.addresses
        
        # Визначаємо файл для завантаження
        if preferred_version == 2 and os.path.exists(ADDRESSES_V2):
            filepath = ADDRESSES_V2
            version = 2
            logger.info(f"✓ Завантаження адрес з версії 2: {ADDRESSES_V2}")
        elif os.path.exists(ADDRESSES_V1):
            filepath = ADDRESSES_V1
            version = 1
            logger.info(f"ℹ️  Завантаження адрес з версії 1 (fallback): {ADDRESSES_V1}")
        else:
            raise FileNotFoundError("Не знайдено жодної версії бази даних адрес!")
        
        # Завантажуємо
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.addresses = json.load(f)
            
            self.current_version = version
            
            # Логуємо статистику
            total_cities = len(self.addresses)
            total_streets = sum(len(streets) for streets in self.addresses.values())
            total_houses = sum(
                len(houses) 
                for streets in self.addresses.values() 
                for houses in streets.values()
            )
            
            logger.info(f"✅ Завантажено адрес (v{version}):")
            logger.info(f"   Міст: {total_cities}")
            logger.info(f"   Вулиць: {total_streets}")
            logger.info(f"   Будинків: {total_houses}")
            
            return self.addresses
            
        except Exception as e:
            logger.error(f"Помилка при завантаженні адрес: {e}")
            raise
    
    def set_version(self, version: int):
        """
        Перемикає активну версію бази даних.
        
        Args:
            version: Номер версії (1 або 2)
        """
        if version not in [1, 2]:
            raise ValueError("Версія має бути 1 або 2")
        
        # Перевіряємо чи існує файл
        filepath = ADDRESSES_V2 if version == 2 else ADDRESSES_V1
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Файл версії {version} не знайдено: {filepath}")
        
        # Оновлюємо метадані
        version_info = self.get_version_info()
        version_info['version'] = version
        version_info['switched_at'] = str(datetime.now())
        
        try:
            with open(VERSION_FILE, 'w', encoding='utf-8') as f:
                json.dump(version_info, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ Версія змінена на v{version}")
            
            # Перезавантажуємо дані
            self.addresses = None
            self.load_addresses(version)
            
        except Exception as e:
            logger.error(f"Помилка при зміні версії: {e}")
            raise
    
    def get_stats_comparison(self) -> Dict:
        """Порівнює статистику між v1 та v2"""
        stats = {'v1': {}, 'v2': {}}
        
        for version in [1, 2]:
            filepath = ADDRESSES_V1 if version == 1 else ADDRESSES_V2
            if not os.path.exists(filepath):
                continue
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                total_houses = 0
                houses_with_letters = 0
                
                for city, streets in data.items():
                    for street, houses in streets.items():
                        for house in houses.keys():
                            total_houses += 1
                            if any(c.isalpha() and ord(c) > 127 for c in house):
                                houses_with_letters += 1
                
                stats[f'v{version}'] = {
                    'cities': len(data),
                    'streets': sum(len(streets) for streets in data.values()),
                    'houses': total_houses,
                    'houses_with_letters': houses_with_letters,
                    'letter_percentage': round(houses_with_letters / total_houses * 100, 2) if total_houses > 0 else 0
                }
            except Exception as e:
                logger.error(f"Помилка при читанні v{version}: {e}")
        
        return stats


# Глобальний екземпляр менеджера
_version_manager = AddressVersionManager()


def get_addresses(preferred_version: int = 2) -> Dict:
    """
    Отримує базу адрес.
    
    Args:
        preferred_version: Бажана версія (1 або 2). За замовчуванням 2.
    
    Returns:
        Словник адрес
    """
    return _version_manager.load_addresses(preferred_version)


def switch_version(version: int):
    """
    Перемикає активну версію бази даних.
    
    Args:
        version: Номер версії (1 або 2)
    """
    _version_manager.set_version(version)


def get_version_stats() -> Dict:
    """Отримує порівняльну статистику версій"""
    return _version_manager.get_stats_comparison()


if __name__ == '__main__':
    # Тестування
    from datetime import datetime
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    print("="*80)
    print("ПОРІВНЯННЯ ВЕРСІЙ БАЗИ ДАНИХ")
    print("="*80)
    
    stats = get_version_stats()
    
    for version in ['v1', 'v2']:
        if stats[version]:
            print(f"\n{version.upper()}:")
            print(f"  Міст: {stats[version]['cities']}")
            print(f"  Вулиць: {stats[version]['streets']}")
            print(f"  Будинків: {stats[version]['houses']}")
            print(f"  З літерами: {stats[version]['houses_with_letters']} ({stats[version]['letter_percentage']}%)")
    
    if stats['v1'] and stats['v2']:
        diff = stats['v2']['houses'] - stats['v1']['houses']
        print(f"\n📊 РІЗНИЦЯ:")
        print(f"  Додано будинків: {diff:+d}")
        print(f"  Додано з літерами: {stats['v2']['houses_with_letters'] - stats['v1']['houses_with_letters']:+d}")
    
    # Тест завантаження
    print("\n" + "="*80)
    print("ТЕСТ ЗАВАНТАЖЕННЯ")
    print("="*80)
    
    try:
        addresses = get_addresses(preferred_version=2)
        print(f"✅ Успішно завантажено {len(addresses)} міст")
        
        # Перевірка проблемної вулиці
        if "Хмельницький" in addresses:
            for street in addresses["Хмельницький"]:
                if "Лісогрин" in street:
                    houses = addresses["Хмельницький"][street]
                    houses_18 = [h for h in houses.keys() if '18' in h]
                    print(f"\n✓ {street}:")
                    print(f"  Будинки з '18': {sorted(houses_18)}")
                    
                    if all(h in houses for h in ['18А', '18Б', '18В', '18Г']):
                        print(f"  🎉 Літери на місці!")
                    else:
                        print(f"  ⚠️  Літери відсутні")
    
    except Exception as e:
        print(f"❌ Помилка: {e}")
        sys.exit(1)
