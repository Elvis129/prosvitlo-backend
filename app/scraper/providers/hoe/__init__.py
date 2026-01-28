"""
HOE (Хмельницькобленерго) scraper provider

Структура даних:
- Графіки: Color-based parser (PNG/JPG)
- Відключення: HTML таблиці
- Оголошення: HTML текст
"""

from .hoe_schedule_parser import fetch_schedule_images, parse_queue_schedule
from .hoe_outage_parser import fetch_all_emergency_outages, fetch_all_planned_outages
from .hoe_announcements_parser import fetch_announcements, check_schedule_availability

__all__ = [
    'fetch_schedule_images',
    'parse_queue_schedule',
    'fetch_all_emergency_outages',
    'fetch_all_planned_outages',
    'fetch_announcements',
    'check_schedule_availability',
]
