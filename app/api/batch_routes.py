"""
API endpoints для batch-запитів (оптимізація множинних запитів)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import date
from pydantic import BaseModel
import json
import logging
import pytz

from app.database import get_db
from app.services.address_service import get_address_info
from app.scraper.schedule_parser import parse_queue_schedule
from app import crud_schedules

router = APIRouter()
logger = logging.getLogger(__name__)

# Київський часовий пояс
KYIV_TZ = pytz.timezone('Europe/Kiev')


class AddressRequest(BaseModel):
    """Адреса для запиту статусу"""
    city: str
    street: str
    house: str


class BatchStatusRequest(BaseModel):
    """Запит статусів для множини адрес"""
    addresses: List[AddressRequest]
    schedule_date: str | None = None  # YYYY-MM-DD, якщо None - сьогодні


class OutageInterval(BaseModel):
    """Інтервал відключення"""
    start_hour: float
    end_hour: float
    label: str
    is_possible: bool = False  # True для можливих відключень, False для гарантованих


class AddressStatus(BaseModel):
    """Статус для однієї адреси"""
    city: str
    street: str
    house: str
    has_power: bool
    queue: str
    message: str
    schedule_date: date | None = None
    schedule_image_url: str | None = None
    upcoming_outages: List[OutageInterval] = []


class BatchStatusResponse(BaseModel):
    """Відповідь з статусами всіх адрес"""
    statuses: List[AddressStatus]


@router.post("/schedules/batch-status", response_model=BatchStatusResponse)
async def get_batch_status(
    request: BatchStatusRequest,
    db: Session = Depends(get_db)
):
    """
    Отримати статуси відключень для множини адрес одним запитом.
    
    Оптимізує множинні запити до БД та зменшує навантаження на API.
    """
    from datetime import datetime
    
    # Визначаємо дату (використовуємо київський час!)
    if request.schedule_date:
        try:
            target_date = datetime.strptime(request.schedule_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Невірний формат дати. Використовуйте YYYY-MM-DD")
    else:
        # Використовуємо київський час для визначення сьогоднішньої дати
        kyiv_now = datetime.now(KYIV_TZ)
        target_date = kyiv_now.date()
    
    # Отримуємо графік один раз для всіх адрес
    schedule = crud_schedules.get_schedule_by_date(db, target_date)
    
    # Парсимо графік один раз
    queue_schedules = {}
    if schedule:
        try:
            if schedule.parsed_data:
                queue_schedules = json.loads(schedule.parsed_data) if isinstance(schedule.parsed_data, str) else schedule.parsed_data
            elif schedule.recognized_text:
                queue_schedules = parse_queue_schedule(schedule.recognized_text)
        except Exception as e:
            logger.error(f"Помилка парсингу графіка: {e}")
    
    # Конвертуємо списки в кортежі
    # Підтримуємо як старий формат {'1.1': [(1, 3)]}, так і новий {'1.1': {'outages': [(1, 3)], 'possible': [(5, 7)]}}
    queue_schedules_tuples = {}
    for q, intervals in queue_schedules.items():
        if isinstance(intervals, dict):
            # Новий формат з outages/possible - зберігаємо структуру
            queue_schedules_tuples[q] = {
                'outages': [tuple(i) if isinstance(i, list) else i for i in intervals.get('outages', [])],
                'possible': [tuple(i) if isinstance(i, list) else i for i in intervals.get('possible', [])]
            }
        else:
            # Старий формат - список інтервалів (для сумісності)
            queue_schedules_tuples[q] = [tuple(i) if isinstance(i, list) else i for i in intervals]
    
    # Поточна година (тільки для сьогодні)
    is_today = target_date == date.today()
    if is_today:
        # Використовуємо київський час
        now = datetime.now(KYIV_TZ)
        current_hour = now.hour + now.minute / 60.0
        logger.info(f"Поточний київський час: {now.strftime('%H:%M')}, час в годинах: {current_hour:.2f}")
    else:
        current_hour = -1
    
    # Обробляємо кожну адресу
    statuses = []
    for addr in request.addresses:
        # Отримуємо чергу для адреси
        address_info = get_address_info(addr.city, addr.street, addr.house)
        if not address_info:
            # Якщо адреса не знайдена - пропускаємо або повертаємо помилку
            statuses.append(AddressStatus(
                city=addr.city,
                street=addr.street,
                house=addr.house,
                has_power=True,
                queue="Невідомо",
                message="Адресу не знайдено",
                schedule_date=target_date,
                schedule_image_url=None,
                upcoming_outages=[]
            ))
            continue
        
        queue = address_info.get("queue", "Невідомо")
        
        # Якщо немає графіка
        if not schedule:
            statuses.append(AddressStatus(
                city=addr.city,
                street=addr.street,
                house=addr.house,
                has_power=True,
                queue=queue,
                message=f"Графік на {target_date.strftime('%d.%m.%Y')} відсутній",
                schedule_date=target_date,
                schedule_image_url=None,
                upcoming_outages=[]
            ))
            continue
        
        # Якщо графік є, але не розпарсений
        if not queue_schedules_tuples:
            statuses.append(AddressStatus(
                city=addr.city,
                street=addr.street,
                house=addr.house,
                has_power=True,
                queue=queue,
                message=f"Ваша черга: {queue}. Графік на {target_date.strftime('%d.%m.%Y')} ще не розпізнано.",
                schedule_date=schedule.date,
                schedule_image_url=schedule.image_url,
                upcoming_outages=[]
            ))
            continue
        
        # Шукаємо інтервали для черги
        queue_clean = queue.replace(". підчерга", "").replace(" підчерга", "").strip()
        user_data = queue_schedules_tuples.get(queue_clean) or queue_schedules_tuples.get(queue)
        
        if not user_data:
            statuses.append(AddressStatus(
                city=addr.city,
                street=addr.street,
                house=addr.house,
                has_power=True,
                queue=queue,
                message=f"Ваша черга: {queue}. Інформація про відключення для цієї черги не знайдена в графіку на {target_date.strftime('%d.%m.%Y')}.",
                schedule_date=schedule.date,
                schedule_image_url=schedule.image_url,
                upcoming_outages=[]
            ))
            continue
        
        # Обробляємо інтервали (підтримка старого та нового формату)
        all_outages = []
        has_power = True
        message = f"Ваша черга: {queue}."
        
        # Визначаємо формат даних
        if isinstance(user_data, dict):
            # Новий формат - об'єднуємо outages та possible для перевірки статусу
            all_intervals = user_data.get('outages', []) + user_data.get('possible', [])
            user_intervals = list(user_data.get('outages', []))
            possible_intervals = list(user_data.get('possible', []))
        else:
            # Старий формат - список кортежів
            all_intervals = user_data
            user_intervals = list(user_data)
            possible_intervals = []
        
        # ✅ Графік вже містить модифікації з оголошень (scheduler вже об'єднав інтервали)
        # Тому тут просто використовуємо parsed_data як є
        
        # Об'єднуємо всі інтервали для відображення
        all_intervals = user_intervals + possible_intervals
        
        for interval in all_intervals:
            start_hour, end_hour = interval
            
            # Визначаємо чи це можливе відключення
            is_possible_outage = interval in possible_intervals
            
            all_outages.append(OutageInterval(
                start_hour=start_hour,
                end_hour=end_hour,
                label=f"{int(start_hour):02d}:{int((start_hour % 1) * 60):02d} - {int(end_hour):02d}:{int((end_hour % 1) * 60):02d}",
                is_possible=is_possible_outage
            ))
            
            # Перевіряємо чи зараз відключення (тільки для сьогодні)
            if is_today and start_hour <= current_hour < end_hour:
                has_power = False
                end_time = f"{int(end_hour):02d}:{int((end_hour % 1) * 60):02d}"
                message = f"⚠️ Відключення до {end_time}. Черга: {queue}."
        
        if is_today and has_power:
            message = f"✅ Зараз світло є. Черга: {queue}."
        elif not is_today:
            message = f"Ваша черга: {queue}. Графік на {target_date.strftime('%d.%m.%Y')}."
        
        statuses.append(AddressStatus(
            city=addr.city,
            street=addr.street,
            house=addr.house,
            has_power=has_power,
            queue=queue,
            message=message,
            schedule_date=schedule.date,
            schedule_image_url=schedule.image_url,
            upcoming_outages=all_outages
        ))
    
    return BatchStatusResponse(statuses=statuses)
