"""
VOE (Вінницяобленерго) scraper provider

Структура даних:
- Графіки: PDF → зображення → OCR або безпосередньо зображення
- Відключення: Форма з фільтрами (Рік, Місяць, РЕМ)
- Оголошення: HTML текст (TODO)

URLs:
- https://www.voe.com.ua/disconnection/emergency
- https://www.voe.com.ua/disconnection/planned
- https://www.voe.com.ua/disconnection/detailed (403 - недоступно)
- https://www.voe.com.ua/informatsiya-pro-cherhy-hrafika-pohodynnykh-vidklyuchen-hpv-1
"""

from .voe_outage_parser import (
    fetch_voe_emergency_outages,
    fetch_voe_planned_outages,
    fetch_all_voe_emergency_outages,
    fetch_all_voe_planned_outages,
)
from .voe_schedule_parser import (
    fetch_voe_schedule_images,
    parse_voe_queue_schedule,
    fetch_schedule_images,
    parse_queue_schedule,
)

__all__ = [
    'fetch_voe_emergency_outages',
    'fetch_voe_planned_outages',
    'fetch_all_voe_emergency_outages',
    'fetch_all_voe_planned_outages',
    'fetch_voe_schedule_images',
    'parse_voe_queue_schedule',
    'fetch_schedule_images',
    'parse_queue_schedule',
]
